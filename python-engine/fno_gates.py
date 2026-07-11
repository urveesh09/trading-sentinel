"""
[FNO-GATES 2026-07-10] Entry gates with mandatory witnesses (spec §7 + §9.1).

Production penny ran a mathematically unsatisfiable breakout gate for
nine months (bar_close > running day_high, 215,814 evaluations, zero
accepts) while passing every health check. The defence adopted here from
the FIRST commit: every gate is an object that ships a `witness_input()`
constructing an input which PASSES it, and CI asserts satisfiability for
every gate (tests/test_fno_gate_falsifiability.py). A gate without a
witness does not merge.

Gates evaluate in spec §7 order; the first failure is THE reject_reason
written to /data/fno_signals.csv, which feeds the zero-accept watchdog's
histogram (§9.2). `pool_below_min_viable` dominating that histogram is
HEALTHY self-regulation (expensive-premium day), not a dead gate --
fno_accept_watchdog knows the difference.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, List, Optional, Tuple

from config import settings
from fno_risk import min_viable_pool


@dataclass
class GateContext:
    """Everything the §7 ladder needs, snapshot at evaluation time."""
    # §7.1 calendar / session
    now_min: int                    # minutes since IST midnight
    is_trading_day: bool
    is_expiry_day: bool
    # §7.2 regime
    regime: str
    # §7.3 microstructure (selected contract)
    oi: int
    volume: int
    bid: float
    ask: float
    ltp: float
    quote_age_sec: float
    # §7.4 freak-trade
    forward: float
    strike: float
    is_call: bool
    iv: Optional[float]
    # §7.5 capital
    pool: float
    premium: float                  # planned fill (ask)
    lot_size: int
    open_premium: float
    open_positions: int
    trades_today: int
    # §7.6 kill switches
    active_kill_switches: List[str] = field(default_factory=list)
    chain_age_sec: float = 0.0


@dataclass(frozen=True)
class Gate:
    name: str
    _check: Callable[[GateContext], bool]
    _witness: Callable[[], GateContext]

    def accepts(self, ctx: GateContext) -> bool:
        return self._check(ctx)

    def witness_input(self) -> GateContext:
        return self._witness()


def make_witness_context() -> GateContext:
    """One context that passes EVERY gate under default settings.

    Arithmetic check against §3: premium 100.2 x lot 75 x stop 25% =
    Rs 1,879 risk = 1.879% of the Rs 1,00,000 pool -> min_viable_pool
    Rs 93,938 < pool. Committed Rs 7,515 < the Rs 15,000 premium cap.
    """
    return GateContext(
        now_min=10 * 60,            # 10:00 IST, inside 09:45-14:45
        is_trading_day=True,
        is_expiry_day=False,
        regime="REGIME_1_NORMAL",
        oi=10_000,
        volume=5_000,
        bid=99.8,
        ask=100.2,
        ltp=100.0,
        quote_age_sec=10.0,
        forward=25_000.0,
        strike=25_000.0,
        is_call=True,
        iv=0.15,
        pool=settings.FNO_PAPER_BANKROLL,
        premium=100.2,
        lot_size=75,
        open_premium=0.0,
        open_positions=0,
        trades_today=0,
        active_kill_switches=[],
        chain_age_sec=5.0,
    )


def _mid(ctx: GateContext) -> float:
    return (ctx.bid + ctx.ask) / 2.0 if ctx.bid > 0 and ctx.ask > 0 else ctx.ltp


def _intrinsic(ctx: GateContext) -> float:
    if ctx.is_call:
        return max(0.0, ctx.forward - ctx.strike)
    return max(0.0, ctx.strike - ctx.forward)


ALL_ENTRY_GATES: List[Gate] = [
    # ---- §7.1 calendar / session ------------------------------------
    Gate("trading_day", lambda c: c.is_trading_day, make_witness_context),
    Gate(
        "entry_window",
        lambda c: settings.FNO_ENTRY_START_MIN <= c.now_min < settings.FNO_ENTRY_END_MIN,
        make_witness_context,
    ),
    Gate(
        "expiry_day_block",
        lambda c: settings.FNO_EXPIRY_DAY_ENTRIES or not c.is_expiry_day,
        make_witness_context,
    ),
    # ---- §7.2 regime ---------------------------------------------------
    Gate("regime_not_crisis", lambda c: c.regime != "REGIME_3_CRISIS", make_witness_context),
    # ---- §7.3 liquidity / microstructure -------------------------------
    Gate("min_oi", lambda c: c.oi >= settings.FNO_MIN_OI, make_witness_context),
    Gate("min_volume", lambda c: c.volume >= settings.FNO_MIN_VOL, make_witness_context),
    Gate("two_sided_market", lambda c: c.bid > 0 and c.ask > 0, make_witness_context),
    Gate(
        "max_spread",
        lambda c: _mid(c) > 0 and (c.ask - c.bid) / _mid(c) <= settings.FNO_MAX_SPREAD_PCT,
        make_witness_context,
    ),
    Gate(
        "quote_freshness",
        lambda c: c.quote_age_sec <= settings.FNO_MAX_QUOTE_AGE_SEC,
        make_witness_context,
    ),
    # ---- §7.4 freak-trade guard (model-free first, model-based second) --
    Gate("intrinsic_floor", lambda c: c.premium >= _intrinsic(c), make_witness_context),
    Gate(
        "quote_envelope",
        lambda c: c.bid * 0.9 <= c.ltp <= c.ask * 1.1,
        make_witness_context,
    ),
    Gate(
        "iv_sanity",
        lambda c: c.iv is not None
        and settings.FNO_IV_SANITY_MIN <= c.iv <= settings.FNO_IV_SANITY_MAX,
        make_witness_context,
    ),
    # ---- §7.5 capital ---------------------------------------------------
    Gate(
        "pool_min_viable",
        lambda c: c.pool >= min_viable_pool(
            c.premium, c.lot_size,
            settings.FNO_STOP_PREMIUM_PCT, settings.FNO_MAX_RISK_PCT,
        ),
        make_witness_context,
    ),
    Gate(
        "open_premium_cap",
        lambda c: c.open_premium + c.premium * c.lot_size
        <= settings.FNO_MAX_OPEN_PREMIUM_PCT * c.pool,
        make_witness_context,
    ),
    Gate(
        "concurrency",
        lambda c: c.open_positions < settings.FNO_MAX_CONCURRENT,
        make_witness_context,
    ),
    Gate(
        "trades_per_day",
        lambda c: c.trades_today < settings.FNO_MAX_TRADES_PER_DAY,
        make_witness_context,
    ),
    # ---- §7.6 kill switches ----------------------------------------------
    Gate("kill_switches_clear", lambda c: not c.active_kill_switches, make_witness_context),
    Gate(
        "chain_freshness",
        lambda c: c.chain_age_sec <= settings.FNO_MAX_CHAIN_AGE_SEC,
        make_witness_context,
    ),
]

# Reject reasons must be stable strings (signal-log schema contract):
# they are the gate names.
_REJECT_BY_GATE = {g.name: g.name for g in ALL_ENTRY_GATES}


def evaluate_entry_gates(ctx: GateContext) -> Tuple[bool, str]:
    """Run the §7 ladder in order. Returns (ok, first_reject_reason)."""
    for gate in ALL_ENTRY_GATES:
        if not gate.accepts(ctx):
            # Spec §3/§9.2 taxonomy: the min-viable rejection keeps its
            # spec name so the watchdog can classify it as self-regulation.
            if gate.name == "pool_min_viable":
                return False, "pool_below_min_viable"
            return False, gate.name
    return True, ""
