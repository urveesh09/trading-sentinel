"""
[FNO-RISK 2026-07-10] The constitution of the F&O subsystem (spec §4).

Owns:
  max_loss(legs, lot_size)      -- rupee max loss; math.inf if unbounded
  validate_position(legs, ...)  -- the ONLY order-path entry point; there is
                                   no code path that places an order for a
                                   position whose max_loss is inf. No config
                                   flag, no env var, no force=True kwarg.
  min_viable_pool(...)          -- per-trade pool floor (spec §3)
  kill_switch_status(...)       -- daily / weekly / monthly / consecutive
  fno_go_live_check(...)        -- promotion as a function, not a judgment

Purity rules (spec §4):
  - max_loss() is pure: no I/O, no options_math import, no model, no IV.
    The expiry P&L of any option combination is continuous piecewise-linear
    in the underlying S with kinks only at the strikes, so its minimum is at
    S=0, at a strike, or in a tail. That is exact, model-free arithmetic.
  - This module carries the heaviest test coverage in the repository
    (tests/test_fno_max_loss.py; 100% branch on max_loss is a P0 exit
    criterion and a go-live gate).
"""
from __future__ import annotations

import math
from datetime import date, timedelta
from typing import List, Optional, Tuple

import structlog

from config import settings
from fno_models import Leg, OptionType

logger = structlog.get_logger()


# ---------------------------------------------------------------------------
# §4 max_loss -- pure, model-free, exact
# ---------------------------------------------------------------------------

def _pnl_points(legs: List[Leg], S: float) -> float:
    """Expiry P&L in index points per 1 lot-unit, at underlying S."""
    total = 0.0
    for leg in legs:
        if leg.opt_type == OptionType.CE:
            payoff = max(0.0, S - leg.strike)
        else:
            payoff = max(0.0, leg.strike - S)
        total += leg.quantity * (payoff - leg.premium)
    return total


def max_loss(legs: List[Leg], lot_size: int) -> float:
    """Rupee max loss of a position. Returns math.inf if unbounded.

    Algorithm (spec §4): evaluate pnl(S) at S=0 and at every strike; the
    right tail is unbounded-down iff the summed call quantity is negative
    (puts contribute 0 as S -> inf); the left tail is always finite because
    pnl(0) is finite and is covered by the S=0 evaluation.
    """
    if not legs:
        return 0.0
    if lot_size <= 0:
        raise ValueError(f"lot_size must be positive, got {lot_size}")

    slope_right = sum(
        leg.quantity for leg in legs if leg.opt_type == OptionType.CE
    )
    if slope_right < 0:
        return math.inf

    eval_points = [0.0] + [leg.strike for leg in legs]
    worst = min(_pnl_points(legs, s) for s in eval_points)
    return max(0.0, -worst * lot_size)


def validate_position(
    legs: List[Leg], lot_size: int,
    max_loss_cap: Optional[float] = None,
) -> Tuple[bool, str, float]:
    """The order-path gate. Every proposed position from every strategy
    passes through here before an order is placed (spec §4).

    Returns (ok, reject_reason, max_loss_rupees). Rejection on inf is
    UNCONDITIONAL -- deliberately no override parameter exists.
    """
    ml = max_loss(legs, lot_size)
    if math.isinf(ml):
        return False, "max_loss_unbounded", ml
    # Structural cap: bounds the frozen-engine catastrophe case (the
    # whole premium), NOT the working stop-based risk -- that one is
    # FNO_MAX_LOSS_PER_TRADE, enforced in sizing (lots_for_pool).
    # See the SPEC-DEVIATION note in config.py.
    cap = (
        max_loss_cap if max_loss_cap is not None
        else settings.FNO_MAX_STRUCTURAL_LOSS_PER_TRADE
    )
    if ml > cap:
        return False, "max_loss_over_cap", ml
    return True, "", ml


# ---------------------------------------------------------------------------
# §3 capital arithmetic
# ---------------------------------------------------------------------------

def min_viable_pool(
    premium: float, lot_size: int, stop_pct: float, max_risk_pct: float,
) -> float:
    """Pool required to take ONE lot of this contract within the risk cap.

    Evaluated per trade at entry, not once per day: premium is expensive
    precisely when IV is high, so this rejection IS the volatility filter
    (spec §3 -- the most important property in the spec). On expensive-
    premium days the module correctly reports zero trades.
    """
    if max_risk_pct <= 0:
        return math.inf
    return (premium * lot_size * stop_pct) / max_risk_pct


def lots_for_pool(
    pool: float, premium: float, lot_size: int,
    stop_pct: float, max_risk_pct: float, max_lots: int,
    max_risk_rupees: Optional[float] = None,
) -> int:
    """How many lots the pool admits under the per-trade risk cap
    (the tighter of pool * max_risk_pct and FNO_MAX_LOSS_PER_TRADE).
    0 means pool_below_min_viable -- decline, never oversize."""
    if premium <= 0 or lot_size <= 0:
        return 0
    risk_per_lot = premium * lot_size * stop_pct
    if risk_per_lot <= 0:
        return 0
    budget = pool * max_risk_pct
    cap = max_risk_rupees if max_risk_rupees is not None else settings.FNO_MAX_LOSS_PER_TRADE
    budget = min(budget, cap)
    affordable = int(budget // risk_per_lot)
    return max(0, min(affordable, max_lots))


# ---------------------------------------------------------------------------
# §7.6 kill switches -- computed from fno_positions (IST dates), not from
# in-memory state, so they survive container restarts.
# ---------------------------------------------------------------------------

async def kill_switch_status(
    db_path: str, source: str, pool: float, today_ist: date,
) -> List[str]:
    """Returns the list of ACTIVE kill switches (empty = clear to trade).

    Daily 6% / weekly 12% / monthly 20% of pool, plus 6 consecutive
    losses -> pause one day. Weekly+monthly exist because options bleed
    slowly enough to walk under a daily limit every day for a month.
    Fails CLOSED on DB errors: an unreadable ledger means no entries.
    """
    import aiosqlite
    active: List[str] = []
    iso_year, iso_week, _ = today_ist.isocalendar()
    week_start = date.fromisocalendar(iso_year, iso_week, 1)
    month_start = today_ist.replace(day=1)
    try:
        async with aiosqlite.connect(db_path) as db:
            # Rule 57: preflight the table before querying it.
            async with db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='fno_positions'"
            ) as cur:
                if await cur.fetchone() is None:
                    logger.info(
                        "fno_db_unready reason=fno_positions_missing "
                        "FIX=first tick creates it; treating all switches as clear"
                    )
                    return []

            async def _pnl_since(day: date) -> float:
                async with db.execute(
                    "SELECT COALESCE(SUM(pnl), 0.0) FROM fno_positions "
                    "WHERE source=? AND status='CLOSED' AND exit_date >= ?",
                    (source, day.isoformat()),
                ) as c:
                    row = await c.fetchone()
                    return float(row[0]) if row and row[0] is not None else 0.0

            day_pnl = await _pnl_since(today_ist)
            week_pnl = await _pnl_since(week_start)
            month_pnl = await _pnl_since(month_start)
            if day_pnl <= -settings.FNO_DAILY_KILL_PCT * pool:
                active.append(f"daily_loss_halt pnl={day_pnl:.0f}")
            if week_pnl <= -settings.FNO_WEEKLY_KILL_PCT * pool:
                active.append(f"weekly_loss_halt pnl={week_pnl:.0f}")
            if month_pnl <= -settings.FNO_MONTHLY_KILL_PCT * pool:
                active.append(f"monthly_loss_halt pnl={month_pnl:.0f}")

            # Consecutive losses: trailing streak over closed positions.
            async with db.execute(
                "SELECT pnl, exit_date FROM fno_positions "
                "WHERE source=? AND status='CLOSED' "
                "ORDER BY exit_time DESC LIMIT ?",
                (source, settings.FNO_MAX_CONSECUTIVE_LOSSES),
            ) as c:
                rows = await c.fetchall()
            if len(rows) >= settings.FNO_MAX_CONSECUTIVE_LOSSES and all(
                r[0] is not None and float(r[0]) < 0 for r in rows
            ):
                # Pause 1 trading day after the streak completes: entries
                # resume the second day after the last loss (calendar-day
                # approximation; a weekend only lengthens the pause, which
                # errs safe).
                last_loss = date.fromisoformat(rows[0][1])
                if today_ist <= last_loss + timedelta(days=1):
                    active.append(
                        f"consecutive_loss_pause streak={len(rows)} last={last_loss}"
                    )
    except Exception as exc:
        logger.error("fno_kill_switch_query_failed err=%s", str(exc))
        return [f"kill_switch_db_error {exc}"]  # fail closed
    return active


# ---------------------------------------------------------------------------
# §11 go-live gate -- promotion is a function, not a judgment call.
# Thresholds were fixed on 2026-07-10, BEFORE any paper equity curve
# existed to rationalise against. Do not tune them to fit the curve.
# ---------------------------------------------------------------------------

async def fno_go_live_check(
    db_path: str,
    current_atm_premium: Optional[float] = None,
    lot_size: Optional[int] = None,
    sl_mechanism_verified: bool = False,
    max_loss_branch_cov_ok: bool = False,
) -> List[str]:
    """Returns unmet conditions. The live leg refuses to arm if non-empty."""
    import aiosqlite
    unmet: List[str] = []
    pool = settings.FNO_LIVE_BANKROLL

    # 1. pool >= min_viable_pool for the current ATM contract
    if current_atm_premium is not None and lot_size:
        need = min_viable_pool(
            current_atm_premium, lot_size,
            settings.FNO_STOP_PREMIUM_PCT, settings.FNO_MAX_RISK_PCT,
        )
        if pool < need:
            unmet.append(f"pool_below_min_viable need={need:.0f} have={pool:.0f}")
    else:
        unmet.append("atm_premium_unknown")

    # 2. >= 40 paper trading days AND >= 60 paper trades
    # 3. paper profit factor >= 1.2
    try:
        async with aiosqlite.connect(db_path) as db:
            async with db.execute(
                "SELECT COUNT(*), COUNT(DISTINCT exit_date), "
                "COALESCE(SUM(CASE WHEN pnl > 0 THEN pnl END), 0.0), "
                "COALESCE(SUM(CASE WHEN pnl < 0 THEN -pnl END), 0.0) "
                "FROM fno_positions WHERE source='FNO_PAPER' AND status='CLOSED'",
            ) as cur:
                row = await cur.fetchone()
        n_trades, n_days, gross_win, gross_loss = (
            int(row[0]), int(row[1]), float(row[2]), float(row[3]),
        )
        if n_days < settings.FNO_GO_LIVE_MIN_TRADING_DAYS:
            unmet.append(f"paper_days={n_days}<{settings.FNO_GO_LIVE_MIN_TRADING_DAYS}")
        if n_trades < settings.FNO_GO_LIVE_MIN_TRADES:
            unmet.append(f"paper_trades={n_trades}<{settings.FNO_GO_LIVE_MIN_TRADES}")
        pf = (gross_win / gross_loss) if gross_loss > 0 else 0.0
        if pf < settings.FNO_GO_LIVE_MIN_PROFIT_FACTOR:
            unmet.append(f"profit_factor={pf:.2f}<{settings.FNO_GO_LIVE_MIN_PROFIT_FACTOR}")
    except Exception as exc:
        unmet.append(f"paper_stats_unreadable {exc}")

    # 4. no liveness-heartbeat gap > 5 min in the last 30 days.
    # The heartbeat writes to docker logs, not the DB; this condition is
    # checked by the operator runbook (grep recipe in ops rule 62) and
    # attested via env flag once tooling lands. Until then it is unmet
    # by construction -- which is the safe default.
    if not bool(getattr(settings, "FNO_LIVENESS_30D_CLEAN", False)):
        unmet.append("liveness_30d_not_attested")

    # 5. SL mechanism verified against the LIVE broker (closes VERIFY-1
    # empirically -- a real order placed and cancelled, not a unit test).
    if not sl_mechanism_verified:
        unmet.append("sl_mechanism_not_broker_verified")

    # 6. max_loss() at 100% branch coverage (CI-attested).
    if not max_loss_branch_cov_ok:
        unmet.append("max_loss_branch_coverage_not_attested")

    return unmet
