"""[O27h 2026-10-27] Tell the owner when the trend-day pullback shadow signals. Messages only; it never trades.

On Oct 27 the owner asked for the O27f trend-day VWAP pullback to run as a shadow beside the shipped strategy and
"see it work tomorrow". The paper and live books keep the shipped opening-range break (the proving week freezes
their rules); ``fno_shadow`` records the pullback's every evaluation in ``fno_shadow_evaluations``. On each F&O
tick this module reads today's accepted rows of the alerted variants and sends one owner message per new thesis
(variant, day, direction): the bar, the futures level, its stop and target, and the option it would buy when a
resolved chain priced it. A message that does not reach Telegram is tried again on the next tick (the thesis is
marked told only once it went). Signals outside the entry window are not told: the book would not act on them.
The whole trade (fills, exits, costs) is scored after the close by forward panel B (O27g), not here.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Awaitable, Callable, Optional

import aiosqlite
import structlog

from config import settings

logger = structlog.get_logger()
ALERTED = {"FNO_TREND_PULLBACK": "trend-day VWAP pullback"}
EXITS = "exits: 3R target, a 2-hour time stop, a 2-ATR trail, flat by 15:10"


def _points(value) -> str:
    return f"{float(value):,.1f}"


def alert_text(variant: str, row: dict) -> str:
    """One owner message for an accepted shadow row (``features`` and ``outcome`` already decoded)."""
    features, outcome = row["features"], row["outcome"]
    bar = str(row["bar_ts"])[11:16]
    side = "LONG (calls)" if row["direction"] == "LONG" else "SHORT (puts)"
    text = (f"F&O shadow, not traded: the {ALERTED[variant]} signalled {side} on {row['underlying']} at the "
            f"{bar} bar. Futures {_points(features['close'])}; stop {_points(features['stop_underlying'])}, "
            f"target {_points(features['target_underlying'])}; {EXITS}.")
    if outcome.get("available"):
        text += (f" It would buy at the ask of ₹{float(outcome['entry_at_observed_ask']):,.2f} "
                 f"(delta {abs(float(outcome['delta_at_evaluation'])):.2f}, lot {int(outcome['quantity'])}).")
    return text + (" The paper and live books keep trading the current strategy; this shadow's full trade is "
                   "scored after the close in forward panel B.")


async def _init(db_path: str) -> None:
    from fno_shadow import init_fno_shadow_db
    await init_fno_shadow_db(db_path)
    async with aiosqlite.connect(db_path) as db:
        await db.execute("CREATE TABLE IF NOT EXISTS fno_shadow_alert_told (variant TEXT NOT NULL, "
                         "candidate_key TEXT NOT NULL, told_at TEXT NOT NULL, text TEXT NOT NULL, "
                         "PRIMARY KEY(variant, candidate_key))")
        await db.commit()


def _in_entry_window(bar_ts: str) -> bool:
    """The judged bar closes inside the book's entry window (its 5-minute close is when a tick can act)."""
    stamp = datetime.fromisoformat(str(bar_ts))
    closes = stamp.hour * 60 + stamp.minute + 5
    return int(settings.FNO_ENTRY_START_MIN) <= closes < int(settings.FNO_ENTRY_END_MIN)


async def check(db_path: str, now: datetime,
                notify: Optional[Callable[..., Awaitable[bool]]] = None) -> list[str]:
    """Send one message per new accepted thesis of an alerted shadow variant today. Returns the texts sent.
    Never raises: it must not disturb the tick."""
    if not bool(getattr(settings, "FNO_SHADOW_OWNER_ALERTS", True)):
        return []
    try:
        await _init(db_path)
        day = now.date().isoformat()
        marks = ",".join("?" for _ in ALERTED)
        async with aiosqlite.connect(db_path) as db:
            rows = await (await db.execute(
                f"SELECT variant, candidate_key, bar_ts, underlying, direction, features_json, outcome_json "
                f"FROM fno_shadow_evaluations WHERE trading_date=? AND accepted=1 AND variant IN ({marks}) "
                f"ORDER BY bar_ts", (day, *ALERTED))).fetchall()
            told = {(v, k) for v, k in await (await db.execute(
                f"SELECT variant, candidate_key FROM fno_shadow_alert_told WHERE variant IN ({marks}) "
                f"AND candidate_key LIKE ?", (*ALERTED, f"{day}|%"))).fetchall()}
        first: dict = {}
        for variant, key, bar_ts, underlying, direction, features, outcome in rows:
            if key and (variant, key) not in told and (variant, key) not in first and _in_entry_window(bar_ts):
                first[(variant, key)] = {"bar_ts": bar_ts, "underlying": underlying, "direction": direction,
                                         "features": json.loads(features), "outcome": json.loads(outcome)}
        if not first:
            return []
        if notify is None:
            from operator_alert import notify_operator as notify
        sent = []
        for (variant, key), row in first.items():
            text = alert_text(variant, row)
            if not await notify(text, event="fno_shadow_signal"):
                continue                                   # told on a later tick
            async with aiosqlite.connect(db_path) as db:
                await db.execute("INSERT OR IGNORE INTO fno_shadow_alert_told(variant,candidate_key,told_at,text) "
                                 "VALUES(?,?,?,?)", (variant, key, now.isoformat(), text))
                await db.commit()
            logger.info("fno_shadow_alert_sent variant=%s key=%s", variant, key)
            sent.append(text)
        return sent
    except Exception as exc:              # a shadow message never fails the F&O tick
        logger.warning("fno_shadow_alert_failed err=%s", type(exc).__name__)
        return []
