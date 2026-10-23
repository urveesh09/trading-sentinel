"""[O21-BS 2026-10-21] A resting broker stop under every LIVE F&O option.

The F&O stop is engine-managed because Zerodha refuses SL-M on options
(VERIFY-1). If the engine is down, nothing protects a live option: the host
restarted on Oct 16 (twice), 17, 18, 19 and 21, and Oct 16 lost 321 minutes
of market time. This module rests one SELL stop-limit (SL) order at the
broker right after a live entry fills:

  trigger = entry x (1 - FNO_STOP_PREMIUM_PCT - FNO_BACKSTOP_EXTRA_PCT)
            (default 35% under the fill, 10 points under the engine's 25% stop)
  limit   = trigger - FNO_BACKSTOP_LIMIT_GAP_PCT x trigger (default 10%),
            inside the exchange's permitted trigger-limit range for index
            options (NSE circular 54/2023: ₹10 up to a ₹50 trigger, else 20%).

The engine's own stops still act first. Before the engine sends any exit it
cancels the backstop and reads its final state, because an exit plus a
filled backstop would sell twice and leave a naked short option:
  - cancelled with nothing filled -> the engine exits as before;
  - fully filled -> the position is already flat: the backstop's fill is
    booked as the exit and no order is sent;
  - partly filled -> only the rest is sold;
  - unreadable -> nothing is sold this tick (critical log and operator page);
    the resting order still protects the position.
While no exit is due the engine re-reads the order each minute, and every
tick once the price is within 2% of the trigger, so a backstop fill is
booked even if the engine was down when it happened.

[A22-BS 2026-10-22] Never two SELLs on an uncertain record (Oct 22 audit):
  - the placement intent (state PLACING, trigger, limit) is written before
    the order is sent; if it cannot be written nothing is sent. A receipt
    lost after the send leaves PLACING without an order id, which an exit
    resolves from the order book (found: cancel and read it; absent: none
    rests; unreadable: hold) and the passive check adopts once found;
  - a ledger that cannot be read is not "no backstop": the exit holds.

[S23-BS1 2026-10-23] Order identity, not order shape (Oct 23 audit): the
order-book lookup matched symbol, SELL, SL and trigger only, so an earlier
position's COMPLETE stop with the same trigger was adopted and the current,
still-held long was booked flat. Each intent now records its own broker tag
(``BSL`` + 17 hex) and sends it with the order. Only that tag, with the row's
symbol, exchange and quantity, identifies the order. A same-shape order that
cannot be ruled out (still working, untagged after the intent, or with no
timestamp) makes the lookup "ambiguous": the exit holds and pages.

Paper books never place one (the executor returns ``paper``). The live leg
stays behind FNO_DISABLE_LIVE and the go-live bar; this adds no entry path.
"""
from __future__ import annotations

import json
import math
import uuid
from datetime import datetime, timedelta
from typing import Optional

import aiosqlite
import pytz
import structlog

from config import settings
from fno_exit_evidence import TERMINAL, RecoveryConflict, broker_time

logger = structlog.get_logger()
IST = pytz.timezone("Asia/Kolkata")

PASSIVE_CHECK_SEC = 60
# A PLACING row this young may still be on its way to the broker (the send
# is bounded by the order client's timeout): an exit waits, never guesses.
PLACING_GRACE_SEC = 30
# States that prove no backstop share can execute: cancelled with nothing
# filled, never placed, or no level. Every other state is re-read at the
# broker before an exit (a broker-cancelled order may have part-filled).
SETTLED_SAFE_STATES = ("CANCELLED", "NO_LEVEL", "PLACE_REJECTED", "NOT_ARMED")
UNCERTAIN_DISPATCH_STATES = ("PLACING", "PLACE_UNKNOWN")
NEAR_TRIGGER_PCT = 0.02
# NSE circular 54/2023, OPTIDX: trigger up to ₹50 -> ₹10 range, above -> 20%.
SMALL_TRIGGER_RS, SMALL_RANGE_RS, RANGE_PCT = 50.0, 10.0, 0.20
# [S23-BS1] Kite tags hold at most 20 characters; the prefix marks a backstop.
TAG_PREFIX = "BSL"
# The broker may stamp our own order a little before our intent clock.
INTENT_CLOCK_SKEW_SEC = 120

_DDL = """
CREATE TABLE IF NOT EXISTS fno_broker_backstops (
  position_id INTEGER PRIMARY KEY,
  source TEXT NOT NULL,
  tradingsymbol TEXT NOT NULL,
  exchange TEXT NOT NULL,
  qty INTEGER NOT NULL,
  trigger_price REAL,
  limit_price REAL,
  order_id TEXT,
  state TEXT NOT NULL,
  placed_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  evidence TEXT,
  broker_tag TEXT
)
"""
_last_check: dict = {}


def new_tag() -> str:
    return f"{TAG_PREFIX}{uuid.uuid4().hex[:17]}"


async def _ensure_table(db) -> None:
    await db.execute(_DDL)
    columns = {row[1] for row in await (await db.execute("PRAGMA table_info(fno_broker_backstops)")).fetchall()}
    if "broker_tag" not in columns:      # created before S23-BS1
        try:
            await db.execute("ALTER TABLE fno_broker_backstops ADD COLUMN broker_tag TEXT")
        except aiosqlite.OperationalError as exc:
            if "duplicate column" not in str(exc):
                raise


class BackstopUnreadable(Exception):
    """The backstop ledger could not be read: absence is not proven."""


def _down(value: float, tick: float) -> float:
    return round(math.floor(round(value / tick, 6)) * tick, 2)


def backstop_levels(entry_fill: float, tick: float, *, stop_pct: float, extra_pct: float,
                    gap_pct: float) -> Optional[tuple[float, float]]:
    """(trigger, limit) for a SELL SL order, or ``None`` when no sane level exists."""
    if entry_fill <= 0 or tick <= 0 or not 0 < stop_pct + extra_pct < 1 or gap_pct <= 0:
        return None
    trigger = _down(entry_fill * (1.0 - stop_pct - extra_pct), tick)
    allowed = SMALL_RANGE_RS if trigger <= SMALL_TRIGGER_RS else RANGE_PCT * trigger
    gap = max(min(gap_pct * trigger, allowed), tick)
    limit = _down(trigger - gap, tick)
    if trigger < 2 * tick or limit < tick or trigger - limit > allowed + 1e-9:
        return None
    return trigger, limit


async def _write(db_path: str, position_id: int, **fields) -> None:
    now = datetime.now(IST).isoformat()
    async with aiosqlite.connect(db_path) as db:
        await _ensure_table(db)
        row = await (await db.execute(
            "SELECT 1 FROM fno_broker_backstops WHERE position_id=?", (position_id,))).fetchone()
        if row is None:
            fields.setdefault("placed_at", now)
            fields["updated_at"] = now
            cols = ["position_id", *fields]
            await db.execute(f"INSERT INTO fno_broker_backstops ({', '.join(cols)}) "
                             f"VALUES ({', '.join('?' for _ in cols)})", (position_id, *fields.values()))
        else:
            fields["updated_at"] = now
            await db.execute(f"UPDATE fno_broker_backstops SET {', '.join(f'{k}=?' for k in fields)} "
                             "WHERE position_id=?", (*fields.values(), position_id))
        await db.commit()


async def _claim_intent(db_path: str, position_id: int, **fields) -> bool:
    """Record the placement intent before any send; False when the position
    already has a backstop row (one order per position, never a second)."""
    now = datetime.now(IST).isoformat()
    fields.update(placed_at=now, updated_at=now)
    cols = ["position_id", *fields]
    async with aiosqlite.connect(db_path) as db:
        await _ensure_table(db)
        cursor = await db.execute(f"INSERT OR IGNORE INTO fno_broker_backstops ({', '.join(cols)}) "
                                  f"VALUES ({', '.join('?' for _ in cols)})", (position_id, *fields.values()))
        await db.commit()
        return cursor.rowcount == 1


async def load_backstop(db_path: str, position_id: int) -> Optional[dict]:
    """The position's backstop row; ``None`` only when none was recorded.

    Raises ``BackstopUnreadable`` when the ledger cannot be read: a locked or
    failing database proves nothing about an order resting at the broker."""
    try:
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            row = await (await db.execute(
                "SELECT * FROM fno_broker_backstops WHERE position_id=?", (position_id,))).fetchone()
    except aiosqlite.OperationalError as exc:
        if "no such table" in str(exc):
            return None       # the table is created with the first intent, before any order
        raise BackstopUnreadable(str(exc)[:200]) from exc
    except (aiosqlite.Error, OSError) as exc:
        raise BackstopUnreadable(f"{type(exc).__name__}: {exc}"[:200]) from exc
    return dict(row) if row else None


async def _page(text: str, event: str) -> None:
    try:
        from operator_alert import notify_operator
        await notify_operator(text, event=event)
    except Exception as exc:
        logger.error("fno_backstop_page_failed event=%s err=%s", event, str(exc))


async def arm(db_path: str, executor, *, position_id: int, source: str, tradingsymbol: str,
              exchange: str, qty: int, fill: float, tick: float) -> dict:
    """Rest the backstop for a filled LIVE entry. Never raises."""
    if getattr(executor, "paper_mode", True) or not settings.FNO_BROKER_BACKSTOP_ENABLED:
        return {"state": "NOT_ARMED"}
    try:
        levels = backstop_levels(fill, tick, stop_pct=settings.FNO_STOP_PREMIUM_PCT,
                                 extra_pct=settings.FNO_BACKSTOP_EXTRA_PCT,
                                 gap_pct=settings.FNO_BACKSTOP_LIMIT_GAP_PCT)
        if levels is None:
            await _write(db_path, position_id, source=source, tradingsymbol=tradingsymbol, exchange=exchange,
                         qty=qty, state="NO_LEVEL", evidence=json.dumps({"fill": fill}))
            logger.critical("fno_backstop_no_level id=%d symbol=%s fill=%.2f -- engine stop only",
                            position_id, tradingsymbol, fill)
            return {"state": "NO_LEVEL"}
        trigger, limit = levels
        tag = new_tag()
        try:
            claimed = await _claim_intent(db_path, position_id, source=source, tradingsymbol=tradingsymbol,
                                          exchange=exchange, qty=qty, trigger_price=trigger, limit_price=limit,
                                          state="PLACING", broker_tag=tag)
        except Exception as exc:
            # No durable intent, no order: an unrecorded SL could later sell a second time.
            logger.critical("fno_backstop_intent_unwritten id=%d symbol=%s err=%s -- not placed, engine stop only",
                            position_id, tradingsymbol, str(exc))
            await _page(f"⚠️ F&O backstop not placed\nid={position_id} {tradingsymbol}: its ledger could not be "
                        "written, so no order was sent. Engine stop still active.", "fno_backstop_not_placed")
            return {"state": "ARM_FAILED"}
        if not claimed:
            logger.warning("fno_backstop_already_recorded id=%d symbol=%s -- no second order", position_id,
                           tradingsymbol)
            return {"state": "ALREADY_RECORDED"}
        result = await executor.place_stop_limit(tradingsymbol, qty, trigger, limit, exchange=exchange, tag=tag)
        state = {"placed": "PLACED", "rejected": "PLACE_REJECTED"}.get(result["status"], "PLACE_UNKNOWN")
        try:
            await _write(db_path, position_id, order_id=result.get("order_id"), state=state,
                         evidence=json.dumps(result.get("evidence") or {}))
        except Exception as exc:
            # The row stays PLACING without an order id: every exit first
            # looks the order up in the order book (_find_in_order_book).
            logger.critical("fno_backstop_receipt_unwritten id=%d symbol=%s state=%s order_id=%s err=%s",
                            position_id, tradingsymbol, state, result.get("order_id"), str(exc))
            await _page(f"⚠️ F&O backstop {state.lower()} but its receipt was not saved\nid={position_id} "
                        f"{tradingsymbol} order_id={result.get('order_id')}. Before any exit the engine looks it "
                        "up in the order book.", "fno_backstop_unrecorded")
            return {"state": "PLACING", "trigger": trigger, "limit": limit, "order_id": result.get("order_id")}
        if state == "PLACED":
            logger.info("fno_backstop_placed id=%d symbol=%s qty=%d trigger=%.2f limit=%.2f order_id=%s",
                        position_id, tradingsymbol, qty, trigger, limit, result.get("order_id"))
        else:
            logger.critical("fno_backstop_not_placed id=%d symbol=%s state=%s -- engine stop only",
                            position_id, tradingsymbol, state)
            await _page(f"⚠️ F&O backstop not placed\nid={position_id} {tradingsymbol} state={state}\n"
                        f"Engine stop still active. Check the order book for a stray SL order.",
                        "fno_backstop_not_placed")
        return {"state": state, "trigger": trigger, "limit": limit, "order_id": result.get("order_id")}
    except Exception as exc:
        # After the intent a PLACING row remains, which exits reconcile first.
        logger.critical("fno_backstop_arm_failed id=%d symbol=%s err=%s", position_id, tradingsymbol, str(exc))
        return {"state": "ARM_FAILED"}


def _fill_of(latest: dict) -> tuple[Optional[int], Optional[float]]:
    filled = latest.get("filled_quantity")
    filled = filled if type(filled) is int and filled >= 0 else None
    try:
        average = float(latest.get("average_price") or 0) or None
    except (TypeError, ValueError):
        average = None
    return filled, average


async def before_exit(db_path: str, executor, position_id: int, qty: int) -> dict:
    """Cancel the backstop before an engine exit and say what is left to sell.

    Returns {"action": "proceed"} (no backstop or cancelled unfilled),
    {"action": "filled", "fill_price", "order_id"} (already flat),
    {"action": "partial", "filled_qty", "fill_price", "remaining"} or
    {"action": "hold", "reason"} (state unknown: send nothing).
    """
    if executor.paper_mode:
        return {"action": "proceed"}
    try:
        row = await load_backstop(db_path, position_id)
    except BackstopUnreadable as exc:
        logger.critical("fno_backstop_ledger_unreadable id=%d err=%s -- exit held", position_id, str(exc))
        await _page_once(position_id, "unreadable",
                         f"⚠️ F&O exit held: the backstop ledger for id={position_id} could not be read. "
                         "Check the order book for a resting SL order before any exit.")
        return {"action": "hold", "reason": "backstop_ledger_unreadable"}
    if row is None or row["state"] in SETTLED_SAFE_STATES:
        return {"action": "proceed"}
    if row["state"] == "PLACING" and _age_sec(row) < PLACING_GRACE_SEC:
        return {"action": "hold", "reason": "backstop_dispatch_in_flight"}
    order_id = row.get("order_id")
    if row["state"] == "FILLED" and order_id:
        # Booked as executed by check_filled, but the exit was not settled
        # (e.g. a receipt write failed): settle from the stored fill.
        try:
            average = float(json.loads(row.get("evidence") or "{}").get("average_price") or 0)
        except (TypeError, ValueError):
            average = 0.0
        if average > 0:
            return {"action": "filled", "fill_price": average, "order_id": order_id}
    if not order_id:
        # PLACE_UNKNOWN or PLACING without an id: the broker may hold an SL
        # order this process cannot name. Look for it in today's order book;
        # only a readable book without it proves nothing rests there.
        found = await _find_in_order_book(executor, row)
        if found == "absent":
            await _write(db_path, position_id, state="CANCELLED", evidence=json.dumps({"order_book": "absent"}))
            return {"action": "proceed"}
        if found in (None, "ambiguous"):
            await _page_once(position_id, "unknown",
                             f"⚠️ F&O exit held: backstop dispatch for id={position_id} {row['tradingsymbol']} "
                             "is unknown. Check the order book, cancel any SL order, then use F&O exit recovery.")
            return {"action": "hold", "reason": "backstop_dispatch_unknown"}
        order_id = found
        await _write(db_path, position_id, order_id=order_id, state="PLACED")
    latest, cancel_error = await executor.cancel_and_read(order_id)
    status = latest.get("status")
    filled, average = _fill_of(latest)
    evidence = json.dumps({"final_status": status, "filled_quantity": filled, "average_price": average,
                           "cancel_error": cancel_error})
    if status == "COMPLETE" and average:
        await _write(db_path, position_id, state="FILLED", evidence=evidence)
        logger.warning("fno_backstop_filled_before_exit id=%d order_id=%s avg=%.2f", position_id, order_id, average)
        return {"action": "filled", "fill_price": average, "order_id": order_id}
    if status in ("CANCELLED", "REJECTED") and filled == 0:
        await _write(db_path, position_id, state="CANCELLED", evidence=evidence)
        return {"action": "proceed"}
    if status in ("CANCELLED", "REJECTED") and filled and 0 < filled < qty and average:
        await _write(db_path, position_id, state="PARTIAL", evidence=evidence)
        return {"action": "partial", "filled_qty": filled, "fill_price": average,
                "remaining": qty - filled, "order_id": order_id}
    await _write(db_path, position_id, state="UNKNOWN", evidence=evidence)
    logger.critical("fno_backstop_state_unknown id=%d order_id=%s status=%s filled=%s -- exit held",
                    position_id, order_id, status, filled)
    await _page_once(position_id, "unknown",
                     f"⚠️ F&O exit held: backstop {order_id} for id={position_id} has state {status!r}. "
                     "Reconcile at the broker before any exit.")
    return {"action": "hold", "reason": f"backstop_state_{status}"}


_paged: set = set()


def _age_sec(row: dict, now: Optional[datetime] = None) -> float:
    try:
        written = datetime.fromisoformat(str(row.get("updated_at") or row.get("placed_at")))
    except (TypeError, ValueError):
        return float("inf")
    return ((now or datetime.now(IST)) - written).total_seconds()


async def _page_once(position_id: int, reason: str, text: str) -> None:
    """One page per position and reason; the hold repeats every tick."""
    if (position_id, reason) in _paged:
        return
    _paged.add((position_id, reason))
    await _page(text, f"fno_backstop_{reason}")


def _same_order(order: dict, row: dict, *, with_trigger: bool) -> bool:
    """Same symbol, side, type, exchange and quantity (a missing broker field
    never rules an order out); with the intended trigger when asked."""
    if (order.get("tradingsymbol") != row["tradingsymbol"] or order.get("transaction_type") != "SELL"
            or order.get("order_type") != "SL"):
        return False
    if order.get("exchange") not in (None, row["exchange"]):
        return False
    quantity = order.get("quantity")
    if quantity is not None and quantity != row["qty"]:
        return False
    try:
        trigger = float(order.get("trigger_price") or 0)
    except (TypeError, ValueError):
        return True
    return not with_trigger or abs(trigger - float(row.get("trigger_price") or 0)) < 0.001


async def _find_in_order_book(executor, row: dict):
    """The backstop's order id from today's book, "absent", "ambiguous" or None (unreadable).

    [S23-BS1] An order is this intent's only when it carries the intent's tag
    (rows written before tags: when it was placed after the intent), with the
    row's symbol, exchange and quantity. Another backstop's tag, or a
    same-shape order that finished before the intent, belongs to an earlier
    position. Anything else that cannot be ruled out is "ambiguous"."""
    snapshot = getattr(executor.kite, "orders_snapshot", None)
    if snapshot is None:
        return None
    try:
        book = await snapshot()
    except Exception:
        return None
    if book is None:
        return None
    book = [o for o in book if isinstance(o, dict)]
    tag = row.get("broker_tag") or ""
    if tag:
        tagged = [o for o in book if str(o.get("tag") or "") == tag]
        if len(tagged) > 1 or (tagged and not _same_order(tagged[0], row, with_trigger=False)):
            return "ambiguous"
        if tagged:
            return tagged[0].get("order_id") or "ambiguous"
    try:
        not_before = broker_time(str(row.get("placed_at") or "")) - timedelta(seconds=INTENT_CLOCK_SKEW_SEC)
    except RecoveryConflict:
        not_before = None
    candidates = []
    for order in book:
        other_tag = str(order.get("tag") or "")
        if (not _same_order(order, row, with_trigger=True)
                or (other_tag.startswith(TAG_PREFIX) and other_tag != tag)):
            continue
        try:
            placed = broker_time(order.get("order_timestamp"))
        except RecoveryConflict:
            return "ambiguous"
        if not_before is None:
            return "ambiguous"
        if placed < not_before:
            if str(order.get("status") or "").upper() in TERMINAL:
                continue          # finished before this intent: an earlier position's
            return "ambiguous"    # still working and not attributable
        candidates.append(order)
    if tag:
        # A readable book without our tag: nothing of ours rests there, unless
        # an untagged same-shape order placed since the intent leaves doubt.
        return "ambiguous" if candidates else "absent"
    if not candidates:
        return "absent"
    if len(candidates) > 1:
        return "ambiguous"
    return candidates[0].get("order_id") or "ambiguous"


async def check_filled(db_path: str, executor, position_id: int, *, price: float,
                       now: Optional[datetime] = None) -> Optional[dict]:
    """Read (never cancel) a resting backstop; the fill when it has executed."""
    if executor.paper_mode:
        return None
    try:
        row = await load_backstop(db_path, position_id)
    except BackstopUnreadable as exc:
        logger.warning("fno_backstop_passive_check_unreadable id=%d err=%s", position_id, str(exc))
        return None
    if row is None:
        return None
    now = now or datetime.now(IST)
    trigger = float(row.get("trigger_price") or 0)
    near = price <= 0 or (trigger > 0 and price <= trigger * (1 + NEAR_TRIGGER_PCT))
    last = _last_check.get(position_id)
    if not near and last is not None and (now - last).total_seconds() < PASSIVE_CHECK_SEC:
        return None
    if (row["state"] in UNCERTAIN_DISPATCH_STATES and not row.get("order_id")
            and _age_sec(row, now) >= PLACING_GRACE_SEC):
        # A send whose receipt was lost: adopt the order once the book shows it.
        _last_check[position_id] = now
        found = await _find_in_order_book(executor, row)
        if found in (None, "absent", "ambiguous"):
            return None       # an exit settles these (absent -> none rests; else hold)
        try:
            await _write(db_path, position_id, order_id=found, state="PLACED",
                         evidence=json.dumps({"order_book": "adopted"}))
        except Exception as exc:     # still PLACING: the next check or an exit retries
            logger.warning("fno_backstop_adopt_unwritten id=%d order_id=%s err=%s", position_id, found, str(exc))
            return None
        logger.warning("fno_backstop_adopted id=%d order_id=%s", position_id, found)
        row = {**row, "order_id": found, "state": "PLACED"}
    if row["state"] != "PLACED" or not row.get("order_id"):
        return None
    _last_check[position_id] = now
    latest = await executor.order_state(row["order_id"])
    status = latest.get("status")
    filled, average = _fill_of(latest)
    if status == "COMPLETE" and average:
        await _write(db_path, position_id, state="FILLED",
                     evidence=json.dumps({"final_status": status, "filled_quantity": filled, "average_price": average}))
        logger.warning("fno_backstop_executed id=%d order_id=%s avg=%.2f", position_id, row["order_id"], average)
        return {"fill_price": average, "order_id": row["order_id"]}
    if status in ("CANCELLED", "REJECTED"):
        # Not CANCELLED/safe: a broker-cancelled order may have part-filled,
        # so before_exit re-reads it and sells only the rest.
        await _write(db_path, position_id, state=f"BROKER_{status}",
                     evidence=json.dumps({"final_status": status, "filled_quantity": filled,
                                          "status_message": str(latest.get("status_message") or "")[:200]}))
        logger.critical("fno_backstop_dropped id=%d order_id=%s status=%s -- engine stop only",
                        position_id, row["order_id"], status)
        await _page_once(position_id, "dropped", f"⚠️ F&O backstop {status.lower()} by the broker for "
                         f"id={position_id} {row['tradingsymbol']}. Engine stop still active.")
    return None
