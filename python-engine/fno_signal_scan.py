"""
[PARTNER-TIPS 2026-07-18] Read-only ORB signal scan per underlying (WS2).

Thin composition of the already-pure F&O pieces -- bars fetch ->
evaluate_fno_mom -> (on a fired direction) chain snapshot + 0.55-delta
strike pick -- with ZERO executor/positions imports. This is the partner
tips bot's signal source for NIFTY/BANKNIFTY/SENSEX; the NIFTY
paper-trading path in fno_orchestrator is untouched and unaware of it.

The liquidity check here is deliberately NOT the fno_gates §7 ladder
(that needs pool/positions context): a tip on a thin chain is still a
tip -- it ships with a "thin market" tag instead of being suppressed,
because the partner may be looking at a different strike anyway.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Optional, Tuple

import pytz
import structlog

from config import settings
from fno_chain import ChainSnapshot, select_strike_by_delta, take_chain_snapshot
from fno_engine_mom import MomSignal, evaluate_fno_mom
from fno_models import ContractQuote, FnoDirection, OptionType
from fno_underlyings import UnderlyingSpec, get_instruments_for

logger = structlog.get_logger()
IST = pytz.timezone("Asia/Kolkata")

# Same frame the orchestrator uses (~14 sessions of 5-min bars for
# EMA(50) + the per-slot RVOL baseline). Duplicated from
# fno_orchestrator.RVOL_FETCH_CALENDAR_DAYS on purpose: importing the
# orchestrator here would drag the executor module graph into a
# read-only scan (and trip test_fno_isolation's spirit if not its letter).
BARS_FETCH_CALENDAR_DAYS = 21


@dataclass
class UnderlyingScan:
    """One underlying's scan outcome. sig always carries the OR/ATR/EMA
    levels when computable (evaluate_fno_mom fills them even on reject),
    which is what the morning brief reads. snap/pick are only fetched
    when a direction actually fired."""
    name: str
    sig: Optional[MomSignal] = None
    snap: Optional[ChainSnapshot] = None
    pick: Optional[Tuple[ContractQuote, float, float]] = None  # (quote, iv, delta)
    thin_chain: bool = False
    thin_reasons: List[str] = field(default_factory=list)
    error: str = ""


def _liquidity_reasons(q: ContractQuote, iv: float) -> List[str]:
    """Light sanity on the picked strike, reusing the §7 thresholds as
    plain numbers. Returns human-short reasons, empty == healthy."""
    reasons: List[str] = []
    if q.oi < settings.FNO_MIN_OI:
        reasons.append(f"OI {q.oi} < {settings.FNO_MIN_OI}")
    if q.volume < settings.FNO_MIN_VOL:
        reasons.append(f"volume {q.volume} < {settings.FNO_MIN_VOL}")
    spread = q.spread_pct
    if spread == float("inf"):
        reasons.append("one-sided book")
    elif spread > settings.FNO_MAX_SPREAD_PCT:
        reasons.append(f"spread {spread * 100:.1f}% > {settings.FNO_MAX_SPREAD_PCT * 100:.1f}%")
    if not (settings.FNO_IV_SANITY_MIN <= iv <= settings.FNO_IV_SANITY_MAX):
        reasons.append(f"IV {iv:.2f} outside sanity band")
    return reasons


async def scan_underlying(
    kite,
    spec: UnderlyingSpec,
    regime: str,
    now_ist: Optional[datetime] = None,
) -> UnderlyingScan:
    """Evaluate the ORB signal for one underlying. Never raises: every
    failure lands in .error so one broken underlying can't sink the
    others in the partner tick loop."""
    now_ist = now_ist or datetime.now(IST)
    out = UnderlyingScan(name=spec.name)
    try:
        book = get_instruments_for(spec.name)
        today = now_ist.date()
        if not book.ready(today):
            out.error = "instruments_not_ready"
            return out
        fut = book.front_future(today)
        if fut is None:
            out.error = "no_front_future"
            return out

        frm = (now_ist - timedelta(days=BARS_FETCH_CALENDAR_DAYS)).strftime(
            "%Y-%m-%d 09:15:00"
        )
        to = now_ist.strftime("%Y-%m-%d %H:%M:%S")
        bars = await kite.get_intraday_by_token(
            fut.token, frm, to, interval="5minute"
        )
        out.sig = evaluate_fno_mom(bars, regime, now_ist)

        if out.sig.direction is None:
            return out

        snap = await take_chain_snapshot(kite, book, now_ist)
        if snap is None:
            out.error = "chain_unavailable"
            return out
        out.snap = snap

        opt_type = (
            OptionType.CE if out.sig.direction == FnoDirection.LONG else OptionType.PE
        )
        pick = select_strike_by_delta(snap, opt_type, now_ist)
        if pick is None:
            out.thin_chain = True
            out.thin_reasons = ["no strike solves for IV/delta"]
            return out
        out.pick = pick
        q, iv, _delta = pick
        out.thin_reasons = _liquidity_reasons(q, iv)
        out.thin_chain = bool(out.thin_reasons)
        return out
    except Exception as exc:
        logger.error(
            "fno_signal_scan_failed underlying=%s err=%s",
            spec.name, str(exc), exc_info=True,
        )
        out.error = str(exc)
        return out
