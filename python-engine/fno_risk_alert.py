"""[O24i 2026-10-24] Tell the owner when the F&O paper book's risk state changes. Messages only.

The owner left the drawdown-halt question to this system's judgement (Oct 24). Decision: the halt stays as it
is. The 15% drawdown halt is measured on equity against the ₹2.5L allocation since inception, because:
  - the July-August losses (27 single-leg trades, 6 winners, about -₹26.8k) were made by the same entry signal
    as today (the NIFTY opening-range signal is unchanged since the Jul 22 RVOL fix; later changes were sizing,
    exits and a re-entry confirmation after a stop), so re-anchoring the halt would hide a real record and
    loosen the one hard capital limit;
  - a recent-peak base is the same number today (equity has never been above the allocation);
  - for real money a capital floor that a losing strategy cannot reset is the point of having one.
What changes is that a halt is no longer silent (it was a log line only). On every F&O tick this module
compares the paper book's state with the last one told, and on a change sends one owner message:
  - the size tier (fno_adaptive_risk.risk_stance: base, 0.5x or 0.25x in a drawdown, larger when proven),
    with the drawdown from the peak;
  - entry halts starting or clearing (fno_shared_risk.entry_halts: the drawdown halt, the daily, weekly and
    monthly loss brakes, the consecutive-loss pause; and the two-strike day halt), with the equity and its
    distance to the 15% line.
The last state told is kept in ``fno_risk_alert_state``, so a restart does not repeat it; the first look at a
calm book (normal size, no halt) is only remembered. A message that does not reach Telegram is tried again on
the next tick (the state is saved only once it went).
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Awaitable, Callable, Optional

import aiosqlite
import structlog

from config import settings

logger = structlog.get_logger()
SOURCE = "FNO_PAPER"
TIERS = {"base": "normal size (1x)", "drawdown_cut1": "half size (0.5x)", "drawdown_cut2": "quarter size (0.25x)",
         "proven_edge_up1": "1.25x (proven edge)", "proven_edge_up2": "a larger size (proven edge)",
         "adaptive_risk_disabled": "normal size (adaptive risk off)"}
HALTS = {"drawdown_halt": "the 15% drawdown halt", "daily_loss_halt": "the daily loss brake",
         "weekly_loss_halt": "the weekly loss brake", "monthly_loss_halt": "the monthly loss brake",
         "consecutive_loss_pause": "the consecutive-loss pause", "two_strike_day_halt": "two losses today"}


def _rupees(value: float) -> str:
    return f"₹{value:,.0f}"


def risk_text(previous: Optional[dict], state: dict, *, equity: Optional[float], allocation: float,
              drawdown_pct: Optional[float]) -> str:
    """The owner's message for a change of state (``previous`` None: the first one after deploy)."""
    line = allocation * (1.0 - float(settings.FNO_MAX_DRAWDOWN_PCT))
    where = ""
    if equity is not None:
        gap = equity - line
        where = (f" Paper equity {_rupees(equity)}: {_rupees(gap)} above the 15% halt line ({_rupees(line)})."
                 if gap >= 0 else f" Paper equity {_rupees(equity)}: under the 15% halt line ({_rupees(line)}).")
    tier = TIERS.get(state["tier"], state["tier"])
    drawdown = f", {drawdown_pct:.1%} under its peak" if drawdown_pct else ""
    halts = [HALTS.get(h, h) for h in state["halts"]]
    if previous is None:
        head = f"F&O paper risk: {tier}{drawdown}; " + (f"entries halted by {', '.join(halts)}." if halts else
                                                        "no entry halt.")
        return head + where + " You will hear when this changes."
    parts = []
    if previous["tier"] != state["tier"]:
        parts.append(f"size now {tier}{drawdown}")
    started = [HALTS.get(h, h) for h in state["halts"] if h not in previous["halts"]]
    cleared = [HALTS.get(h, h) for h in previous["halts"] if h not in state["halts"]]
    if started:
        parts.append(f"entries halted by {', '.join(started)}")
    if cleared:
        parts.append(f"{', '.join(cleared)} cleared" + ("" if state["halts"] else ": entries open again"))
    icon = "⚠️" if started or (previous["tier"] != state["tier"] and state["tier"].startswith("drawdown")) else "ℹ️"
    text = f"{icon} F&O paper: {'; '.join(parts)}." + where
    if "drawdown_halt" in state["halts"] and "drawdown_halt" not in previous["halts"]:
        text += (" No new paper trade is opened until equity is back above the line; the shadows and the replay "
                 "keep recording. Keeping, re-anchoring or ending the halt is your decision.")
    return text


async def _init(db_path: str) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute("CREATE TABLE IF NOT EXISTS fno_risk_alert_state (source TEXT PRIMARY KEY, state TEXT NOT NULL, "
                         "told_at TEXT NOT NULL)")
        await db.commit()


async def _last(db_path: str) -> Optional[dict]:
    async with aiosqlite.connect(db_path) as db:
        row = await (await db.execute("SELECT state FROM fno_risk_alert_state WHERE source=?", (SOURCE,))).fetchone()
    try:
        return json.loads(row[0]) if row else None
    except ValueError:
        return None


async def _save(db_path: str, state: dict, now: datetime) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute("INSERT INTO fno_risk_alert_state(source,state,told_at) VALUES(?,?,?) ON CONFLICT(source) "
                         "DO UPDATE SET state=excluded.state, told_at=excluded.told_at",
                         (SOURCE, json.dumps(state, sort_keys=True), now.isoformat()))
        await db.commit()


async def check_paper(db_path: str, now: datetime,
                      notify: Optional[Callable[..., Awaitable[bool]]] = None) -> Optional[str]:
    """Compare the paper book's risk state with the last one told; on a change, tell the owner. Returns the text
    sent (None: nothing changed, or it could not be read). Never raises: it must not disturb the tick."""
    try:
        from fno_adaptive_risk import policy_from_settings as adaptive_policy, read_book_closes, risk_stance
        from fno_shared_risk import init_shared_fno_risk_db, policy_from_settings, shared_fno_entry_policy
        await init_shared_fno_risk_db(db_path)
        await _init(db_path)
        allocation = float(settings.FNO_PAPER_BANKROLL)
        decision = await shared_fno_entry_policy(db_path, source=SOURCE, pool_rs=allocation,
                                                 today_ist=now.date(), policy=policy_from_settings())
        stance = risk_stance(await read_book_closes(db_path, SOURCE), allocation=allocation, now=now,
                             policy=adaptive_policy())
        halts = {str(h).split(" ", 1)[0] for h in decision.active_halts}
        if stance.single_leg_halted_today:
            halts.add("two_strike_day_halt")
        view = getattr(decision, "view", None)
        if view is not None and not getattr(view, "available", True):
            return None                   # the ledger could not be read: nothing is claimed
        order = list(HALTS)                # the most serious first
        state = {"tier": stance.reason,
                 "halts": sorted(halts, key=lambda h: (order.index(h) if h in order else len(order), h))}
        previous = await _last(db_path)
        if previous == state:
            return None
        if previous is None and state == {"tier": "base", "halts": []}:
            await _save(db_path, state, now)   # the first look at a calm book: remembered, nothing to tell
            return None
        text = risk_text(previous, state, equity=getattr(view, "equity_rs", None), allocation=allocation,
                         drawdown_pct=stance.drawdown_pct)
        if notify is None:
            from operator_alert import notify_operator as notify
        if await notify(text, event="fno_paper_risk_state"):
            await _save(db_path, state, now)
            logger.info("fno_risk_alert_sent state=%s", state)
            return text
        return None
    except Exception as exc:              # a risk message never fails the F&O tick
        logger.warning("fno_risk_alert_failed err=%s", type(exc).__name__)
        return None
