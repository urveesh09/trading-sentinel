"""Evidence-driven F&O position sizing: shrink fast when losing, grow slowly when proven.

Pure (no I/O), shared by the live tick and the research replay. The owner's
rule is that a loss shrinks the capital that earns, so the book must not keep
paying full size into a losing streak, and it may only press harder after it
has shown, on enough closed trades, that it is winning:

* Drawdown from the equity peak: >= ``cut1`` halves the risk budget, >= ``cut2``
  quarters it. (The 15% drawdown halt in the entry brakes stops entries.)
* Proven edge: with >= ``up1_trades`` closed trades at profit factor >=
  ``up1_pf`` and equity within ``near_peak`` of its high, size steps to 1.25x;
  with >= ``up2_trades`` at >= ``up2_pf``, to 1.5x. Never above 1.5x.
* Two strikes: after ``two_strike_losses`` losing single-leg closes in one IST
  day, no further single-leg entries that day (management continues).

The multiplier scales the per-trade risk budget and its rupee ceiling; the
lot ceiling, the structural max-loss cap and every entry brake stay hard.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Sequence

import pytz

IST = pytz.timezone("Asia/Kolkata")
MAX_MULTIPLIER = 1.5


@dataclass(frozen=True)
class AdaptiveRiskPolicy:
    enabled: bool = True
    cut1_drawdown: float = 0.04
    cut2_drawdown: float = 0.08
    up1_trades: int = 20
    up1_pf: float = 1.3
    up2_trades: int = 40
    up2_pf: float = 1.5
    near_peak: float = 0.02
    two_strike_losses: int = 2


@dataclass(frozen=True)
class RiskStance:
    multiplier: float
    reason: str
    drawdown_pct: float
    closed_trades: int
    profit_factor: float | None
    single_leg_losses_today: int
    single_leg_halted_today: bool


@dataclass(frozen=True)
class Close:
    """One completed trade of either paper book."""
    at: datetime          # aware completion instant
    pnl: float            # net rupees
    single_leg: bool


async def read_book_closes(db_path: str, source: str) -> list[Close]:
    """Completed trades of both paper books for one source (read-only).

    The only I/O in this module; kept here so the single-leg tick and the
    capped-loss book read identical evidence.
    """
    import aiosqlite
    closes: list[Close] = []
    async with aiosqlite.connect(db_path) as db:
        async with db.execute("SELECT name FROM sqlite_master WHERE type='table'") as cursor:
            tables = {row[0] for row in await cursor.fetchall()}
        queries = []
        if "fno_positions" in tables:
            queries.append(("SELECT exit_time, pnl FROM fno_positions WHERE source=? AND status='CLOSED' "
                            "AND exit_time IS NOT NULL AND pnl IS NOT NULL", True))
        if "fno_dr_positions" in tables:
            queries.append(("SELECT closed_at, pnl FROM fno_dr_positions WHERE source=? AND status='CLOSED' "
                            "AND closed_at IS NOT NULL AND pnl IS NOT NULL", False))
        for sql, single_leg in queries:
            async with db.execute(sql, (source,)) as cursor:
                for stamp, pnl in await cursor.fetchall():
                    at = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
                    closes.append(Close(at if at.tzinfo else IST.localize(at), float(pnl), single_leg))
    return closes


def policy_from_settings() -> AdaptiveRiskPolicy:
    from config import settings
    return AdaptiveRiskPolicy(
        enabled=bool(settings.FNO_ADAPTIVE_RISK_ENABLED),
        cut1_drawdown=float(settings.FNO_RISK_CUT1_DRAWDOWN_PCT),
        cut2_drawdown=float(settings.FNO_RISK_CUT2_DRAWDOWN_PCT),
        up1_trades=int(settings.FNO_RISK_UP1_MIN_TRADES), up1_pf=float(settings.FNO_RISK_UP1_MIN_PF),
        up2_trades=int(settings.FNO_RISK_UP2_MIN_TRADES), up2_pf=float(settings.FNO_RISK_UP2_MIN_PF),
        near_peak=float(settings.FNO_RISK_NEAR_PEAK_PCT),
        two_strike_losses=int(settings.FNO_TWO_STRIKE_LOSSES),
    )


def _profit_factor(pnls: Sequence[float]) -> float | None:
    gains = sum(p for p in pnls if p > 0)
    losses = -sum(p for p in pnls if p < 0)
    if losses <= 0:
        return None if gains <= 0 else float("inf")
    return gains / losses


def risk_stance(closes: Sequence[Close], *, allocation: float, now: datetime,
                policy: AdaptiveRiskPolicy) -> RiskStance:
    """The sizing stance at ``now`` from closes completed at or before it."""
    visible = sorted((c for c in closes if c.at <= now), key=lambda c: c.at)
    today: date = now.astimezone(IST).date()
    losses_today = sum(1 for c in visible if c.single_leg and c.pnl < 0 and c.at.astimezone(IST).date() == today)
    halted = losses_today >= policy.two_strike_losses
    equity = peak = allocation
    for close in visible:
        equity += close.pnl
        peak = max(peak, equity)
    drawdown = (peak - equity) / peak if peak > 0 else 1.0
    pf = _profit_factor([c.pnl for c in visible])
    stance = dict(drawdown_pct=round(drawdown, 6), closed_trades=len(visible),
                  profit_factor=None if pf is None else round(pf, 4),
                  single_leg_losses_today=losses_today, single_leg_halted_today=halted)
    if not policy.enabled:
        return RiskStance(1.0, "adaptive_risk_disabled", **stance)
    if drawdown >= policy.cut2_drawdown:
        return RiskStance(0.25, "drawdown_cut2", **stance)
    if drawdown >= policy.cut1_drawdown:
        return RiskStance(0.5, "drawdown_cut1", **stance)
    near_peak = drawdown <= policy.near_peak
    if near_peak and pf is not None and len(visible) >= policy.up2_trades and pf >= policy.up2_pf:
        return RiskStance(MAX_MULTIPLIER, "proven_edge_up2", **stance)
    if near_peak and pf is not None and len(visible) >= policy.up1_trades and pf >= policy.up1_pf:
        return RiskStance(1.25, "proven_edge_up1", **stance)
    return RiskStance(1.0, "base", **stance)
