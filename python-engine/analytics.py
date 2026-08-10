"""
[ANALYTICS 2026-06-16] Self-improving analytics layer for Trading Sentinel.

Three things this module does, all from the data we already persist:

1. Gate-funnel report -- counts which MC-gate rejection reasons kill the most
   signals. The first place to look when "I'm getting too few / too many
   signals" or "entries aren't great" is this.

2. Outcome correlator -- joins closed trades (from positions + bankroll_ledger)
   with their original signal-log row (from momentum_signals) to compute
   "what was the gate fingerprint of trades that won vs lost." Reveals which
   gates actually predict success.

3. Strategy suggestions -- turns (1) + (2) into 3-5 actionable changes the
   operator can A/B. Always returns the reasoning + the data backing it, so
   nothing is a black-box recommendation.

Public API (all async, all take db_path):
  init_analytics_db(db_path)                          -- idempotent
  record_trade_outcome(db_path, ticker, pnl, r_mult)   -- wired in main.py on close
  gate_funnel_report(db_path, days)                    -> dict
  outcome_correlator(db_path, days)                    -> dict
  strategy_suggestions(db_path, days)                  -> dict

CLI: `python -m analytics --days 14`  (prints a human report)

Design rules:
- All writes are best-effort. An analytics failure must NOT break live trading.
- No new third-party deps. SQLite + stdlib only.
- Schemas are forward-compatible: only ADD columns/tables, never rename.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import datetime, timezone, timedelta
from typing import Optional

import aiosqlite
import structlog

from config import settings

logger = structlog.get_logger()


# --------------------------------------------------------------------
# Schema
# --------------------------------------------------------------------

# trade_outcomes: one row per CLOSED momentum trade. Joins closed position
# with the signal-log row that produced it (so we can correlate gate state
# with realized P&L).
CREATE_TRADE_OUTCOMES_SQL = """
CREATE TABLE IF NOT EXISTS trade_outcomes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker          TEXT    NOT NULL,
    closed_at       TEXT    NOT NULL,
    realised_pnl    REAL    NOT NULL,
    r_multiple      REAL,
    scan_id         TEXT,
    regime          TEXT,
    close           REAL,
    stop_loss       REAL,
    target_1        REAL,
    volume_ratio    REAL,
    rvol_ratio      REAL,
    rsi_7           REAL,
    minutes_from_open INTEGER,
    strategy_version TEXT,
    notes           TEXT,
    UNIQUE(ticker, closed_at)
);
CREATE INDEX IF NOT EXISTS idx_outcomes_closed_at ON trade_outcomes(closed_at);
CREATE INDEX IF NOT EXISTS idx_outcomes_ticker     ON trade_outcomes(ticker);
CREATE INDEX IF NOT EXISTS idx_outcomes_regime     ON trade_outcomes(regime);
"""


async def init_analytics_db(db_path: str) -> None:
    """Idempotent. Call from main.py startup alongside init_positions_db."""
    try:
        async with aiosqlite.connect(db_path) as db:
            for stmt in CREATE_TRADE_OUTCOMES_SQL.split(";"):
                s = stmt.strip()
                if s:
                    await db.execute(s)
            await db.commit()
    except Exception as e:
        logger.error("analytics_init_failed", error=str(e))


# --------------------------------------------------------------------
# 1. Record a trade outcome (called from main.py on position close)
# --------------------------------------------------------------------

async def record_trade_outcome(
    db_path: str,
    ticker: str,
    realised_pnl: float,
    r_multiple: Optional[float] = None,
    notes: Optional[str] = None,
) -> Optional[str]:
    """Record a closed trade + join with the latest signal-log row for that ticker.

    Returns the scan_id of the matched signal-log row, or None if no match.
    Idempotent on (ticker, closed_at) -- re-recording the same close is a no-op.
    """
    # Idempotent -- safe to call on every close
    try:
        await init_analytics_db(db_path)
    except Exception as e:
        # [ROADMAP-4.3 2026-07-13] Was a bare `pass`, which is doubly bad:
        # the write below then runs against a table that may not exist and
        # fails anyway -- but two levels up, where the cause is gone.
        logger.warning("analytics_init_failed error=%s", str(e))
    try:
        closed_at = datetime.now(timezone.utc).isoformat()
        cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            try:
                cur = await db.execute(
                    """SELECT scan_id, regime, close, stop_loss, target_1,
                              volume_ratio, rvol_ratio, rsi_7, minutes_from_open,
                              strategy_version
                       FROM momentum_signals
                       WHERE ticker = ? AND accepted = 1 AND scanned_at >= ?
                       ORDER BY scanned_at DESC LIMIT 1""",
                    (ticker, cutoff),
                )
                row = await cur.fetchone()
            except aiosqlite.OperationalError:
                # Table doesn't exist yet -- log a minimal outcome
                await db.execute(
                    """INSERT OR IGNORE INTO trade_outcomes
                       (ticker, closed_at, realised_pnl, r_multiple, notes)
                       VALUES (?, ?, ?, ?, ?)""",
                    (ticker, closed_at, realised_pnl, r_multiple,
                     notes or "no_signal_log_table"),
                )
                await db.commit()
                return None
            if not row:
                # No matched signal -- log a minimal outcome so we still have the P&L
                await db.execute(
                    """INSERT OR IGNORE INTO trade_outcomes
                       (ticker, closed_at, realised_pnl, r_multiple, notes)
                       VALUES (?, ?, ?, ?, ?)""",
                    (ticker, closed_at, realised_pnl, r_multiple,
                     notes or "no_matched_signal"),
                )
                await db.commit()
                return None
            await db.execute(
                """INSERT OR IGNORE INTO trade_outcomes
                   (ticker, closed_at, realised_pnl, r_multiple, scan_id, regime,
                    close, stop_loss, target_1, volume_ratio, rvol_ratio, rsi_7,
                    minutes_from_open, strategy_version, notes)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (ticker, closed_at, realised_pnl, r_multiple, row["scan_id"],
                 row["regime"], row["close"], row["stop_loss"], row["target_1"],
                 row["volume_ratio"], row["rvol_ratio"], row["rsi_7"],
                 row["minutes_from_open"], row["strategy_version"], notes),
            )
            await db.commit()
            return row["scan_id"]
    except Exception as e:
        logger.error("record_outcome_failed", ticker=ticker, error=str(e))
        return None


# --------------------------------------------------------------------
# 2. Gate-funnel report
# --------------------------------------------------------------------

async def gate_funnel_report(db_path: str, days: int = 7) -> dict:
    """Count rejections by reason over the last `days`.

    Returns:
      {
        "days": N,
        "scanned_total": int,
        "accepted": int,
        "rejected": int,
        "rejection_rate": float,    # 0..1
        "by_reason": [
            {"reason": "MC3_volume_surge_insufficient", "count": N, "pct": 0.32},
            ...
        ],
        "as_of": iso8601,
      }
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    try:
        async with aiosqlite.connect(db_path) as db:
            try:
                cur = await db.execute(
                    """SELECT
                           SUM(CASE WHEN accepted=1 THEN 1 ELSE 0 END) AS acc,
                           SUM(CASE WHEN accepted=0 THEN 1 ELSE 0 END) AS rej,
                           COUNT(*) AS total
                       FROM momentum_signals
                       WHERE scanned_at >= ?""",
                    (cutoff,),
                )
                r = await cur.fetchone()
            except aiosqlite.OperationalError:
                # Table doesn't exist yet -- fresh DB. Return empty funnel.
                return {
                    "days": days, "scanned_total": 0, "accepted": 0,
                    "rejected": 0, "rejection_rate": 0.0,
                    "by_reason": [], "as_of": datetime.now(timezone.utc).isoformat(),
                }
            accepted = r[0] or 0
            rejected = r[1] or 0
            total    = r[2] or 0

            cur = await db.execute(
                """SELECT reject_reason, COUNT(*) AS n
                   FROM momentum_signals
                   WHERE scanned_at >= ? AND accepted = 0 AND reject_reason != ''
                   GROUP BY reject_reason
                   ORDER BY n DESC""",
                (cutoff,),
            )
            rows = await cur.fetchall()
        by_reason = [
            {"reason": r[0] or "(empty)", "count": r[1],
             "pct": round(r[1] / rejected, 4) if rejected else 0.0}
            for r in rows
        ]
        return {
            "days": days,
            "scanned_total": total,
            "accepted": accepted,
            "rejected": rejected,
            "rejection_rate": round(rejected / total, 4) if total else 0.0,
            "by_reason": by_reason,
            "as_of": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        logger.error("funnel_report_failed", error=str(e))
        return {"days": days, "error": str(e), "by_reason": []}


# --------------------------------------------------------------------
# 2b. Unified per-strategy funnel  [STRATEGY-FUNNEL 2026-07-20]
# --------------------------------------------------------------------
# gate_funnel_report above is momentum-only. This composes ALL strategies
# (penny / momentum / edge / fno) with per-strategy paper-vs-live P&L, so
# passivity is impossible to hide -- the daily "are we actually trading,
# and making money?" heartbeat (Phase 1.1 of the activation plan).

# Which signal-eval table + filter backs each division's activity, keyed by
# the ledger `source` tag from performance._division_registry(). SYSTEM
# (swing) has no reject-reason eval log in cache.db -> P&L-only row.
_FUNNEL_ACTIVITY = {
    "MOMENTUM":   ("momentum_signals", "scanned_at",   ""),
    "PENNY":      ("penny_signals",    "scanned_at",   "leg='MIS'"),
    "PENNY_PAPER":("penny_signals",    "scanned_at",   "leg='MIS'"),
    "EDGE_PAPER": ("penny_signals",    "scanned_at",   "leg IN ('CNC','EDGE')"),
    "EDGE_LIVE":  ("penny_signals",    "scanned_at",   "leg IN ('CNC','EDGE')"),
    "FNO_PAPER":  ("fno_signals",      "evaluated_at", ""),
    "FNO_LIVE":   ("fno_signals",      "evaluated_at", ""),
}


async def _funnel_activity(db, table, ts_col, day_iso, extra_where):
    """(evals, accepts, top-3 reject reasons) for one signal table on one day.
    Best-effort: a missing table/column yields zeros, never an exception."""
    where = f"substr({ts_col},1,10)=?"
    if extra_where:
        where += f" AND {extra_where}"
    evals = accepts = 0
    top = []
    try:
        async with db.execute(
            f"SELECT SUM(CASE WHEN accepted=1 THEN 1 ELSE 0 END), COUNT(*) "
            f"FROM {table} WHERE {where}", (day_iso,)
        ) as cur:
            row = await cur.fetchone()
            if row:
                accepts = int(row[0] or 0)
                evals = int(row[1] or 0)
        async with db.execute(
            f"SELECT reject_reason, COUNT(*) AS n FROM {table} "
            f"WHERE {where} AND accepted=0 AND reject_reason != '' "
            f"GROUP BY reject_reason ORDER BY n DESC LIMIT 3", (day_iso,)
        ) as cur:
            top = [{"reason": r[0], "n": int(r[1])} for r in await cur.fetchall()]
    except Exception as e:
        logger.warning("funnel_activity_failed table=%s error=%s", table, str(e))
    return evals, accepts, top


async def strategy_funnel(db_path: str, day_iso: Optional[str] = None) -> dict:
    """Per-strategy activity (evals/accepts/top-rejects) + today's P&L and
    open-position count, live vs paper. One row per division. Reuses
    performance._division_registry() for the source -> (label, mode) map and
    bankroll_ledger for realised P&L, so it never drifts from /bankroll/divisions."""
    import aiosqlite
    from datetime import datetime, timezone, timedelta
    if day_iso is None:
        IST = timezone(timedelta(hours=5, minutes=30))
        day_iso = datetime.now(IST).date().isoformat()
    from performance import _division_registry

    strategies = []
    live_pnl = paper_pnl = 0.0
    async with aiosqlite.connect(db_path) as db:
        pnl_today, trades_today = {}, {}
        try:
            async with db.execute(
                "SELECT source, COALESCE(SUM(pnl),0.0), "
                "SUM(CASE WHEN event_type!='INITIAL' THEN 1 ELSE 0 END) "
                "FROM bankroll_ledger WHERE substr(timestamp,1,10)=? GROUP BY source",
                (day_iso,),
            ) as cur:
                for r in await cur.fetchall():
                    pnl_today[r[0]] = float(r[1] or 0.0)
                    trades_today[r[0]] = int(r[2] or 0)
        except Exception as e:
            logger.warning("funnel_pnl_failed error=%s", str(e))

        open_by_source = {}
        try:
            async with db.execute(
                "SELECT source, COUNT(*) FROM positions "
                "WHERE status IN ('OPEN','CLOSED_T1') GROUP BY source"
            ) as cur:
                for r in await cur.fetchall():
                    open_by_source[r[0]] = int(r[1])
            async with db.execute(
                "SELECT source, COUNT(*) FROM fno_positions "
                "WHERE UPPER(status) IN ('OPEN','LIVE','ACTIVE') GROUP BY source"
            ) as cur:
                for r in await cur.fetchall():
                    open_by_source[r[0]] = open_by_source.get(r[0], 0) + int(r[1])
        except Exception as e:
            logger.warning("funnel_open_failed error=%s", str(e))

        active_classic_penny_source = (
            "PENNY" if settings.PENNY_LIVE_TRADING else "PENNY_PAPER"
        )
        for key, label, source, pool_id, allocated, mode in _division_registry():
            act = _FUNNEL_ACTIVITY.get(source)
            # Classic Penny writes one shared evaluation stream. Attribute it
            # only to the scanner's current execution mode; showing it on both
            # static registry rows would double-count the same work and make
            # an inactive live book look active while paper mode is armed.
            if source in {"PENNY", "PENNY_PAPER"} and source != active_classic_penny_source:
                act = None
            evals = accepts = 0
            top = []
            if act:
                evals, accepts, top = await _funnel_activity(
                    db, act[0], act[1], day_iso, act[2]
                )
            pnl = round(pnl_today.get(source, 0.0), 2)
            strategies.append({
                "key": key, "label": label, "source": source, "mode": mode,
                "evals": evals, "accepts": accepts, "top_rejects": top,
                "trades_today": trades_today.get(source, 0),
                "pnl_today": pnl, "open_positions": open_by_source.get(source, 0),
                "activity_tracked": act is not None,
            })
            if mode == "live":
                live_pnl += pnl
            else:
                paper_pnl += pnl

    return {
        "day": day_iso,
        "strategies": strategies,
        "totals": {"live_pnl": round(live_pnl, 2), "paper_pnl": round(paper_pnl, 2)},
    }


def _rupees(v: float) -> str:
    return f"{'+' if v >= 0 else '-'}₹{abs(v):,.2f}"


def format_strategy_funnel(data: dict) -> str:
    """Telegram/CLI text for strategy_funnel()."""
    if data.get("error"):
        return f"Strategy funnel: error ({data['error']})"
    lines = [f"\U0001F4CA Strategy funnel — {data.get('day', '')}"]
    for s in data.get("strategies", []):
        tag = "\U0001F7E2 live" if s["mode"] == "live" else "\U0001F4DD paper"
        lines.append(f"\n{s['label']} [{tag}]")
        if s.get("activity_tracked"):
            lines.append(
                f"  scans {s['evals']} · accepts {s['accepts']} "
                f"· open {s['open_positions']}"
            )
            for tr in s.get("top_rejects", [])[:3]:
                lines.append(f"    ✗ {tr['n']}× {tr['reason']}")
        else:
            lines.append(f"  open {s['open_positions']} (no scan log)")
        lines.append(
            f"  trades {s['trades_today']} · P&L {_rupees(s['pnl_today'])}"
        )
    t = data.get("totals", {})
    lines.append(
        f"\nToday: live {_rupees(t.get('live_pnl', 0.0))} "
        f"· paper {_rupees(t.get('paper_pnl', 0.0))}"
    )
    return "\n".join(lines)


# --------------------------------------------------------------------
# 2c. Promotion ladder  [STRATEGY-PROMOTION 2026-07-20]
# --------------------------------------------------------------------
# Deprecated ledger-only research ladder. It may identify a paper strategy for
# further review, but never authorizes live capital: it lacks distinct-candidate,
# OOS, profit-factor, provenance, repeat-inflation and reconciliation gates.
# `/research/promotion-readiness` is the stronger contract.

def _max_drawdown(pnls: list) -> float:
    """Max peak-to-trough drawdown (rupees, >=0) of the cumulative curve."""
    cum = peak = mdd = 0.0
    for p in pnls:
        cum += p
        peak = max(peak, cum)
        mdd = max(mdd, peak - cum)
    return mdd


def _promotion_bar() -> dict:
    from config import settings
    return {
        "min_trades": int(getattr(settings, "PROMOTION_MIN_TRADES", 100)),
        "provisional_trades": int(getattr(settings, "PROMOTION_PROVISIONAL_TRADES", 30)),
        "max_dd_pct": float(getattr(settings, "PROMOTION_MAX_DD_PCT", 0.25)),
    }


async def _min_viable_trade_cost(db, division_key: str) -> "float | None":
    """Smallest amount of capital this division can possibly commit to one trade.

    [STRUCTURAL-VIABILITY 2026-07-26] Returns None where there is no hard floor:
    equity books can always buy a single share, so any allocation admits *some*
    trade. Whether it is a good trade is an edge question, not a tradeability one.

    Options are different -- contracts trade in lots, so the floor is
    `premium x lot_size` for ONE lot and cannot be scaled down. Measured from this
    book's own cheapest historical entry rather than a guessed constant, so the
    figure stays true as premiums and lot sizes change. Returns None before the
    book has traded: absence of data is not evidence of unaffordability.
    """
    if division_key not in ("fno_paper", "fno_live"):
        return None
    source = "FNO_PAPER" if division_key == "fno_paper" else "FNO_LIVE"
    try:
        async with db.execute(
            "SELECT MIN(entry_premium * lot_size) FROM fno_positions WHERE source=?",
            (source,),
        ) as cur:
            row = await cur.fetchone()
    except Exception:
        return None                      # table absent before the first F&O trade
    if not row or row[0] is None or float(row[0]) <= 0:
        return None
    return float(row[0])


async def promotion_report(db_path: str) -> dict:
    """Per-strategy paper->live promotion check from the trade ledger."""
    import aiosqlite
    from performance import _division_registry

    bar = _promotion_bar()
    # [STRUCTURAL-VIABILITY 2026-07-26] The real, spendable account -- the ceiling
    # on what any division could be allocated on promotion. Paper pools are
    # notional and deliberately not used here.
    real_capital = float(getattr(settings, "INITIAL_BANKROLL", 0.0) or 0.0)
    strategies = []
    try:
        async with aiosqlite.connect(db_path) as db:
            for key, label, source, pool, allocated, mode in _division_registry():
                async with db.execute(
                    "SELECT pnl FROM bankroll_ledger "
                    "WHERE source=? AND event_type='TRADE_CLOSED' ORDER BY timestamp",
                    (source,),
                ) as cur:
                    pnls = [float(r[0] or 0.0) for r in await cur.fetchall()]
                n = len(pnls)
                total = round(sum(pnls), 2)
                expectancy = round(total / n, 2) if n else 0.0
                mdd = round(_max_drawdown(pnls), 2)
                dd_budget = round(allocated * bar["max_dd_pct"], 2) if allocated else None

                reasons = []
                if n < bar["provisional_trades"]:
                    reasons.append(f"insufficient_sample:{n}/{bar['provisional_trades']}")
                if n and expectancy <= 0:
                    reasons.append(f"negative_expectancy:{expectancy}")
                if dd_budget is not None and mdd > dd_budget:
                    reasons.append(f"drawdown_over_budget:{mdd}>{dd_budget}")

                # [STRUCTURAL-VIABILITY 2026-07-26] A paper book whose smallest
                # possible trade costs more than the capital it would be given can
                # never be promoted, however good its paper record looks -- and its
                # paper record is not evidence about anything the account could have
                # done. F&O is the live example: the cheapest single NIFTY lot ever
                # traded was Rs 5,967 and the real Nifty account is Rs 4,884, so not
                # one lot was ever affordable. Its Rs 250,000 notional allocation
                # also inflated the drawdown budget to Rs 62,500 -- 12.8x the whole
                # account -- so Rs 10,841 of losses still read as "within budget".
                #
                # Report that as its own blocking reason instead of letting the book
                # sit at "insufficient_sample" forever, which reads as "keep waiting"
                # when the truth is "this cannot be traded at this capital".
                # Compared against REAL capital, not `allocated`. Comparing it to
                # the book's own notional would defeat the point: FNO_PAPER's
                # Rs 250,000 allocation is the fiction being tested, and a
                # Rs 5,967 lot trivially "fits" inside it. The account itself is
                # the hard ceiling on anything this book could ever be handed, so
                # that is what a lot has to fit inside.
                min_trade = await _min_viable_trade_cost(db, key)
                if min_trade is not None and min_trade > real_capital:
                    reasons.append(
                        f"structurally_unaffordable:one_lot_{int(min_trade)}"
                        f">whole_account_{int(real_capital)}"
                    )

                if mode == "live":
                    verdict = "no_data" if not n else ("healthy" if expectancy > 0 else "underperforming")
                elif reasons:
                    verdict = "not_ready"
                elif n < bar["min_trades"]:
                    verdict = "provisional"          # bar met, sample still building
                else:
                    verdict = "legacy_candidate_for_research_review"

                strategies.append({
                    "key": key, "label": label, "source": source, "mode": mode,
                    "trades": n, "total_pnl": total, "expectancy": expectancy,
                    "max_drawdown": mdd, "dd_budget": dd_budget,
                    "min_viable_trade": round(min_trade, 2) if min_trade is not None else None,
                    "verdict": verdict, "blocking_reasons": reasons,
                })
    except Exception as e:
        logger.error("promotion_report_failed error=%s", str(e))
        return {
            "error": str(e), "strategies": [], "bar": bar,
            "research_only": True, "can_place_orders": False, "deprecated": True,
            "warning": "Deprecated ledger-only ladder; use /research/promotion-readiness. It never authorizes live trading.",
        }
    return {
        "strategies": strategies, "bar": bar,
        "research_only": True, "can_place_orders": False, "deprecated": True,
        "warning": "Deprecated ledger-only ladder; use /research/promotion-readiness. It never authorizes live trading.",
    }


def format_promotion_report(data: dict) -> str:
    if data.get("error"):
        return (
            "Deprecated ledger-only research ladder: error "
            f"({data['error']}). Use /research/promotion-readiness; no authorization is granted."
        )
    bar = data.get("bar", {})
    icon = {"legacy_candidate_for_research_review": "✅", "provisional": "\U0001F7E1", "not_ready": "⛔",
            "healthy": "\U0001F7E2", "underperforming": "\U0001F534", "no_data": "➖"}
    lines = [
        "\U0001F393 Deprecated ledger-only research ladder "
        f"(bar: ≥{bar.get('min_trades')} trades, +expectancy, DD≤{int(bar.get('max_dd_pct',0)*100)}%)"
    ]
    lines.append("Research only; use /research/promotion-readiness. This does not authorize live trading.")
    for s in data.get("strategies", []):
        lines.append(
            f"\n{icon.get(s['verdict'],'')} {s['label']} [{s['mode']}] — {s['verdict']}"
        )
        lines.append(
            f"  {s['trades']} trades · expectancy {_rupees(s['expectancy'])}"
            f" · P&L {_rupees(s['total_pnl'])} · maxDD ₹{s['max_drawdown']:,.0f}"
        )
        # [STRUCTURAL-VIABILITY 2026-07-26] Show the one-lot floor next to the
        # allocation whenever it binds, so an unaffordable book reads as
        # unaffordable rather than as merely under-sampled.
        mvt = s.get("min_viable_trade")
        if mvt and s.get("dd_budget") is not None:
            lines.append(f"  min viable trade ₹{mvt:,.0f} (1 lot)")
        for r in s.get("blocking_reasons", []):
            lines.append(f"    ✗ {r}")
    ready = [s['label'] for s in data.get("strategies", []) if s['verdict'] == "legacy_candidate_for_research_review"]
    lines.append("\nLegacy candidates for research review: " + (", ".join(ready) if ready else "none yet"))
    return "\n".join(lines)


# --------------------------------------------------------------------
# 3. Outcome correlator
# --------------------------------------------------------------------

async def outcome_correlator(db_path: str, days: int = 14) -> dict:
    """Correlate gate fingerprint with realized P&L.

    Splits closed trades into winners (r > 0) and losers (r <= 0) and computes
    the average value of each gate-state field for each group. Reveals which
    gates are actually predictive vs just decorative.

    Returns:
      {
        "days": N,
        "n_trades": int,
        "n_winners": int, "n_losers": int,
        "win_rate": float,
        "avg_r": float, "avg_r_winners": float, "avg_r_losers": float,
        "by_regime": [
          {"regime": "REGIME_1_NORMAL", "trades": N, "win_rate": 0.6, "avg_r": 0.8},
          ...
        ],
        "winners_avg": { field: value, ... },
        "losers_avg":  { field: value, ... },
        "predictive_gates": [ "volume_ratio", ... ],   # gates where diff > 20%
      }
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    FIELDS = ["volume_ratio", "rvol_ratio", "rsi_7", "minutes_from_open", "close"]
    try:
        async with aiosqlite.connect(db_path) as db:
            cur = await db.execute(
                f"""SELECT realised_pnl, r_multiple, regime, {", ".join(FIELDS)}
                    FROM trade_outcomes
                    WHERE closed_at >= ? AND r_multiple IS NOT NULL""",
                (cutoff,),
            )
            rows = await cur.fetchall()
        if not rows:
            return {"days": days, "n_trades": 0, "predictive_gates": []}

        winners = [r for r in rows if (r[1] or 0) > 0]
        losers  = [r for r in rows if (r[1] or 0) <= 0]
        n = len(rows)
        nw = len(winners)
        nl = len(losers)
        avg_r  = sum((r[1] or 0) for r in rows) / n
        avg_rw = sum((r[1] or 0) for r in winners) / nw if nw else 0.0
        avg_rl = sum((r[1] or 0) for r in losers)  / nl if nl else 0.0

        def _avg(idx: int, group: list) -> Optional[float]:
            vals = [r[idx] for r in group if r[idx] is not None]
            return round(sum(vals) / len(vals), 3) if vals else None

        winners_avg = {f: _avg(3 + i, winners) for i, f in enumerate(FIELDS)}
        losers_avg  = {f: _avg(3 + i, losers)  for i, f in enumerate(FIELDS)}

        # Predictive = at least 20% relative difference between winner and loser avg
        predictive = []
        for f in FIELDS:
            w, l = winners_avg[f], losers_avg[f]
            if w is None or l is None:
                continue
            denom = max(abs(w), abs(l), 1e-9)
            if abs(w - l) / denom > 0.20:
                predictive.append(f)

        # By regime breakdown
        by_regime_map: dict = {}
        for r in rows:
            reg = r[2] or "UNKNOWN"
            by_regime_map.setdefault(reg, []).append(r)
        by_regime = []
        for reg, g in sorted(by_regime_map.items()):
            n_reg = len(g)
            wins_reg = sum(1 for x in g if (x[1] or 0) > 0)
            avg_r_reg = sum((x[1] or 0) for x in g) / n_reg
            by_regime.append({
                "regime": reg,
                "trades": n_reg,
                "win_rate": round(wins_reg / n_reg, 4),
                "avg_r": round(avg_r_reg, 3),
            })

        return {
            "days": days,
            "n_trades": n,
            "n_winners": nw, "n_losers": nl,
            "win_rate": round(nw / n, 4) if n else 0.0,
            "avg_r": round(avg_r, 3),
            "avg_r_winners": round(avg_rw, 3),
            "avg_r_losers": round(avg_rl, 3),
            "by_regime": by_regime,
            "winners_avg": winners_avg,
            "losers_avg":  losers_avg,
            "predictive_gates": predictive,
        }
    except Exception as e:
        logger.error("outcome_correlator_failed", error=str(e))
        return {"days": days, "n_trades": 0, "predictive_gates": [], "error": str(e)}


# --------------------------------------------------------------------
# 4. Strategy suggestions
# --------------------------------------------------------------------

async def strategy_suggestions(db_path: str, days: int = 14) -> dict:
    """Reads funnel + outcomes, returns 3-5 actionable suggestions.

    Each suggestion includes:
      - headline (1 line)
      - evidence (the data that triggered it)
      - action (what to flip in config)
      - confidence ("high" if n >= 20 trades, "medium" if 5-20, "low" if < 5)

    Rules (in priority order):
      1. If 1 reason accounts for >40% of rejections AND n_trades >= 10:
         "Reason X is your bottleneck. Consider relaxing it."
      2. If predictive_gates is non-empty AND n_trades >= 10:
         "Gates A, B differ between winners and losers by >20%. Consider
          tighter threshold on the side that's worse for winners."
      3. If win_rate < 0.40 AND n_trades >= 10:
         "Win rate below 40% -- consider raising the entry bar (require more
          gates to pass, e.g. enable MC7 RVOL)."
      4. If avg_r_losers < -1.5R:
         "Losers exceed -1.5R avg -- consider tighter stop or position sizing."
      5. If by_regime shows R1 winning >60% AND R2/R3 < 40%:
         "R1 is your edge. Consider disabling R2 entries until you have more
          R2 data."
    """
    funnel   = await gate_funnel_report(db_path, days=days)
    outcomes = await outcome_correlator(db_path, days=days)
    n_trades = outcomes.get("n_trades", 0)
    confidence = "high" if n_trades >= 20 else "medium" if n_trades >= 5 else "low"

    suggestions = []

    # Rule 1: dominant rejection reason
    by_reason = funnel.get("by_reason", [])
    if by_reason and funnel.get("rejected", 0) >= 10:
        top = by_reason[0]
        if top["pct"] > 0.40:
            suggestions.append({
                "headline":  f"'{top['reason']}' kills {top['pct']*100:.0f}% of signals",
                "evidence":  f"{top['count']} of {funnel['rejected']} rejections in last {days} days",
                "action":    f"Consider relaxing the {top['reason']} gate (lower threshold or extend window)",
                "confidence": confidence,
                "rule":      "dominant_rejection",
            })

    # Rule 2: predictive gates
    pred = outcomes.get("predictive_gates", [])
    if pred and n_trades >= 10:
        for g in pred:
            w = outcomes["winners_avg"].get(g)
            l = outcomes["losers_avg"].get(g)
            if w is None or l is None:
                continue
            if w > l:
                suggestions.append({
                    "headline":  f"Winners have higher {g} ({w}) than losers ({l})",
                    "evidence":  f"{g} avg differs by {abs(w-l):.2f} between winner/loser cohorts",
                    "action":    f"Consider raising the {g} floor (require higher value to pass)",
                    "confidence": confidence,
                    "rule":      "predictive_gate_higher_for_winners",
                })
            else:
                suggestions.append({
                    "headline":  f"Winners have lower {g} ({w}) than losers ({l})",
                    "evidence":  f"{g} avg differs by {abs(w-l):.2f} between winner/loser cohorts",
                    "action":    f"Consider lowering the {g} threshold (accept more in this range)",
                    "confidence": confidence,
                    "rule":      "predictive_gate_lower_for_winners",
                })

    # Rule 3: low win rate
    win_rate = outcomes.get("win_rate", 0.0)
    if win_rate < 0.40 and n_trades >= 10:
        suggestions.append({
            "headline":  f"Win rate is {win_rate*100:.0f}% (target >= 40%)",
            "evidence":  f"{outcomes.get('n_winners', 0)} wins / {n_trades} trades in last {days} days",
            "action":    "Tighten the entry bar -- enable MOMENTUM_USE_RVOL=True (MC7) to filter further",
            "confidence": confidence,
            "rule":      "low_win_rate",
        })

    # Rule 4: oversized losers
    avg_rl = outcomes.get("avg_r_losers", 0.0)
    if avg_rl is not None and avg_rl < -1.5:
        suggestions.append({
            "headline":  f"Average losing trade is {avg_rl:.2f}R (target >= -1.0R)",
            "evidence":  f"avg_r_losers={avg_rl:.2f} from {outcomes.get('n_losers', 0)} losing trades",
            "action":    "Tighten stop-loss or reduce position size; check MOMENTUM_ATR_FUEL_BUFFER",
            "confidence": confidence,
            "rule":      "oversized_losers",
        })

    # Rule 5: regime divergence
    for r in outcomes.get("by_regime", []):
        reg = r["regime"]
        wr  = r["win_rate"]
        n   = r["trades"]
        if reg == "REGIME_1_NORMAL" and wr > 0.60 and n >= 5:
            for r2 in outcomes.get("by_regime", []):
                if r2["regime"] != reg and r2["win_rate"] < 0.40 and r2["trades"] >= 5:
                    suggestions.append({
                        "headline":  f"{reg} wins {wr*100:.0f}% but {r2['regime']} wins {r2['win_rate']*100:.0f}%",
                        "evidence":  f"R1: {r['trades']} trades, R2/3: {r2['trades']} trades",
                        "action":    f"Consider disabling {r2['regime']} entries until more data confirms edge",
                        "confidence": confidence,
                        "rule":      "regime_divergence",
                    })

    # Always include an "insufficient data" hint when n is tiny
    if n_trades < 5:
        suggestions.append({
            "headline":  f"Only {n_trades} closed trades in last {days} days",
            "evidence":  "Sample size too small for reliable suggestions",
            "action":    "Keep logging. Re-run analytics in 7-14 days.",
            "confidence": "low",
            "rule":      "insufficient_data",
        })

    return {
        "days": days,
        "n_trades": n_trades,
        "confidence": confidence,
        "funnel_summary": {
            "scanned_total": funnel.get("scanned_total", 0),
            "accepted": funnel.get("accepted", 0),
            "rejected": funnel.get("rejected", 0),
            "rejection_rate": funnel.get("rejection_rate", 0.0),
        },
        "outcome_summary": {
            "win_rate": win_rate,
            "avg_r": outcomes.get("avg_r", 0.0),
            "avg_r_winners": outcomes.get("avg_r_winners", 0.0),
            "avg_r_losers": avg_rl,
        },
        "suggestions": suggestions,
        "as_of": datetime.now(timezone.utc).isoformat(),
    }


# --------------------------------------------------------------------
# 5. Human report (CLI)
# --------------------------------------------------------------------

def _bar(label: str, count: int, max_count: int, width: int = 40) -> str:
    if max_count <= 0:
        return f"  {label}: (no data)"
    filled = int(width * count / max_count)
    return f"  {label:<42} {'#' * filled:<{width}} {count}"


async def print_report(db_path: str, days: int = 14) -> None:
    funnel   = await gate_funnel_report(db_path, days=days)
    outcomes = await outcome_correlator(db_path, days=days)
    sugg     = await strategy_suggestions(db_path, days=days)

    print("=" * 70)
    print(f"  TRADING SENTINEL -- ANALYTICS REPORT (last {days} days)")
    print(f"  As of: {sugg.get('as_of', '?')}")
    print("=" * 70)
    print()
    print("[1] GATE FUNNEL")
    print(f"    Scanned:   {funnel.get('scanned_total', 0)}")
    print(f"    Accepted:  {funnel.get('accepted', 0)}")
    print(f"    Rejected:  {funnel.get('rejected', 0)} "
          f"({funnel.get('rejection_rate', 0)*100:.1f}%)")
    by_reason = funnel.get("by_reason", [])
    if by_reason:
        max_n = by_reason[0]["count"]
        print("    Top rejection reasons:")
        for r in by_reason[:8]:
            print(_bar(r["reason"], r["count"], max_n))
    else:
        print("    (no rejections logged)")

    print()
    print("[2] OUTCOME CORRELATION")
    nt = outcomes.get("n_trades", 0)
    if nt == 0:
        print("    No closed trades in this window. Run the system a few more days.")
    else:
        print(f"    Trades:    {nt}  "
              f"({outcomes.get('n_winners', 0)}W / {outcomes.get('n_losers', 0)}L)")
        print(f"    Win rate:  {outcomes.get('win_rate', 0)*100:.1f}%")
        print(f"    Avg R:     {outcomes.get('avg_r', 0):.3f}  "
              f"(W: {outcomes.get('avg_r_winners', 0):.3f}, "
              f"L: {outcomes.get('avg_r_losers', 0):.3f})")
        pred = outcomes.get("predictive_gates", [])
        if pred:
            print(f"    Predictive gates: {', '.join(pred)}")
        else:
            print("    Predictive gates: (none -- no field differs >20% between W/L)")
        br = outcomes.get("by_regime", [])
        if br:
            print("    By regime:")
            for r in br:
                print(f"      {r['regime']:<25} n={r['trades']:<3} "
                      f"win={r['win_rate']*100:.0f}%  avg_r={r['avg_r']:.2f}")

    print()
    print("[3] SUGGESTIONS")
    suggestions = sugg.get("suggestions", [])
    if not suggestions:
        print("    No suggestions (insufficient data or no issues detected).")
    else:
        for i, s in enumerate(suggestions, 1):
            print(f"    {i}. [{s['confidence'].upper()}] {s['headline']}")
            print(f"       Evidence: {s['evidence']}")
            print(f"       Action:   {s['action']}")
            print()

    print("=" * 70)


# --------------------------------------------------------------------
# CLI entry: python -m analytics --days 14
# --------------------------------------------------------------------

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Trading Sentinel analytics")
    parser.add_argument("--days", type=int, default=14, help="Lookback window in days")
    parser.add_argument("--db", type=str, default=None, help="Override DB path")
    args = parser.parse_args()

    db = args.db or settings.DB_PATH
    asyncio.run(print_report(db, days=args.days))

async def penny_outcome_correlator(db_path: str, days: int = 14) -> dict:
    """
    [PENNY-ANALYTICS 2026-06-21] Outcome correlator filtered to source='PENNY'
    positions. Joins bankroll_ledger (with source column) to penny_signals.

    Returns the same shape as outcome_correlator() but only penny rows.
    Read-only -- returns empty buckets if no penny P&L is in the ledger yet.
    """
    import aiosqlite
    from datetime import datetime, timezone, timedelta
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    out = {"total": 0, "winners": 0, "losers": 0, "win_rate": 0.0,
           "by_reject_reason": {}, "by_regime": {}, "days": days}
    try:
        async with aiosqlite.connect(db_path) as db:
            async with db.execute(
                "SELECT pnl FROM bankroll_ledger "
                "WHERE source='PENNY' AND timestamp >= ?",
                (cutoff,),
            ) as cur:
                rows = await cur.fetchall()
    except Exception:
        return out
    if not rows:
        return out
    pnls = [r[0] or 0.0 for r in rows]
    out["total"] = len(pnls)
    out["winners"] = sum(1 for p in pnls if p > 0)
    out["losers"] = sum(1 for p in pnls if p < 0)
    out["win_rate"] = out["winners"] / out["total"] if out["total"] > 0 else 0.0
    return out


# ---------------------------------------------------------------------------
# [ROADMAP-5.1 2026-07-13] Real edge statistics over trade_outcomes.
# ---------------------------------------------------------------------------

async def edge_statistics(
    db_path: str, days: int = 90, strategy: Optional[str] = None
) -> dict:
    """Expectancy, profit factor, max drawdown and bootstrapped 95% CIs.

    The maths lives in edge_stats.py as pure functions; this is only the DB
    adapter. Two details in the query are load-bearing:

      * ORDER BY closed_at -- max_drawdown walks the equity curve in close
        order and deliberately refuses to sort for itself, because it cannot
        know which timestamp the caller meant. Feeding it unordered rows would
        produce a plausible, wrong drawdown.
      * r_multiple is allowed to be NULL. Older rows predate the column, and
        edge_stats drops them from the R statistics rather than counting them
        as 0.0 R -- which would drag expectancy toward zero and make a real
        edge look like noise. Rupee statistics still use every row.

    Default window is 90 days, not the 7/14 used elsewhere: these statistics
    need a sample, and a 14-day window on this system's trade frequency cannot
    supply one. The report says so rather than quietly returning a number --
    see `reliable` and `verdict`.
    """
    from edge_stats import Trade, edge_report

    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    sql = (
        "SELECT realised_pnl, r_multiple FROM trade_outcomes "
        "WHERE closed_at >= ?"
    )
    params: list = [cutoff]
    if strategy:
        sql += " AND strategy_version = ?"
        params.append(strategy)
    sql += " ORDER BY closed_at ASC"

    try:
        async with aiosqlite.connect(db_path) as db:
            cur = await db.execute(sql, params)
            rows = await cur.fetchall()
    except Exception as e:
        logger.error("edge_statistics_failed error=%s", str(e))
        return {"days": days, "n": 0, "verdict": "no_data", "error": str(e)}

    trades = [Trade(pnl=r[0] or 0.0, r=r[1]) for r in rows]
    report = edge_report(trades)
    report["days"] = days
    report["strategy"] = strategy

    # [ROADMAP-5.2 2026-07-13] Assert the cost bypass is OFF, in the report.
    #
    # PENNY_BROKERAGE_BYPASS zeroes every penny cost. On a Rs 2,500 bankroll,
    # Rs 20/order + STT + GST is not a rounding error -- it is most of the edge.
    # An expectancy computed while that flag was on is not a slightly-optimistic
    # number, it is a fictional one, and it is exactly the number an operator
    # would use to decide to scale up.
    #
    # So the report carries the flag and REFUSES to certify an edge while it is
    # set. Better to withhold a verdict than to hand back "edge_demonstrated"
    # earned by not paying brokerage.
    from config import settings as _settings

    bypassed = bool(_settings.PENNY_BROKERAGE_BYPASS)
    report["brokerage_bypass_active"] = bypassed
    if bypassed:
        report["costs_are_fictional"] = True
        report["verdict"] = "invalid_costs_bypassed"
        report["warning"] = (
            "PENNY_BROKERAGE_BYPASS is ON: all penny costs are zeroed, so this "
            "expectancy is gross, not net. On a Rs 2,500 bankroll the costs are "
            "most of the edge. Turn the flag off and re-run before believing any "
            "of these numbers."
        )
        logger.warning(
            "edge_statistics_with_costs_bypassed n=%s -- report is gross P&L, "
            "not net; verdict withheld", report.get("n"),
        )

    return report
