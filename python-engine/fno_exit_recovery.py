"""Evidence-backed, operator-authorized reconciliation of one F&O exit intent.

Broker order/trade/position reads are deliberately required on every resolve.
The broker's daily order book cannot prove an older unknown dispatch; those
intents remain blocked for statement-level manual reconciliation.
"""
from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import aiosqlite

from fno_costs import calc_fno_costs
from fno_positions import init_fno_positions_db
from performance import allocation_for_source

IST = ZoneInfo("Asia/Kolkata")
TERMINAL = {"COMPLETE", "CANCELLED", "REJECTED"}


class RecoveryConflict(ValueError):
    """Evidence is ambiguous or no longer matches the durable intent."""


async def pending_exit_intents(db_path: str) -> list[dict]:
    """Return local evidence only; this does not imply broker reconciliation."""
    try:
        read_uri = Path(db_path).resolve(strict=True).as_uri() + "?mode=ro"
    except (OSError, ValueError) as exc:
        raise RecoveryConflict("F&O recovery database unavailable") from exc
    async with aiosqlite.connect(read_uri, uri=True) as db:
        db.row_factory = aiosqlite.Row
        try:
            cur = await db.execute("""
                SELECT i.position_id, i.source, i.created_at, p.status,
                       p.tradingsymbol, p.qty, p.lot_size, p.entry_premium,
                       p.settlement_generation, r.id AS receipt_id
                FROM fno_exit_intents i
                JOIN fno_positions p ON p.id=i.position_id AND p.source=i.source
                LEFT JOIN fno_exit_execution_receipts r
                  ON r.position_id=i.position_id AND r.source=i.source
                ORDER BY i.created_at, i.position_id
            """)
            return [dict(row) for row in await cur.fetchall()]
        except aiosqlite.OperationalError as exc:
            raise RecoveryConflict("F&O recovery schema unavailable") from exc


def _positive_int(value, field: str, *, allow_zero: bool = False) -> int:
    if type(value) is not int or value < (0 if allow_zero else 1):
        raise RecoveryConflict(f"invalid {field}")
    return value


def _price(value, field: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise RecoveryConflict(f"invalid {field}") from exc
    if not math.isfinite(result) or result <= 0:
        raise RecoveryConflict(f"invalid {field}")
    return result


def _broker_time(value: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise RecoveryConflict("missing broker fill timestamp")
    try:
        parsed = datetime.fromisoformat(value.strip())
    except ValueError as exc:
        raise RecoveryConflict("invalid broker fill timestamp") from exc
    return parsed.replace(tzinfo=IST) if parsed.tzinfo is None else parsed.astimezone(IST)


async def verify_broker_exit(
    kite, *, intent: dict, account_id: str, order_id: str,
    known_recovered_orders: frozenset[str] = frozenset(),
    now: datetime | None = None,
) -> dict:
    """Cross-check the same-day order, its trades and net broker position."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise RecoveryConflict("naive inspection clock")
    if not account_id or not order_id or len(account_id) > 80 or len(order_id) > 80:
        raise RecoveryConflict("account and order ID are required")
    try:
        claimed = datetime.fromisoformat(intent["created_at"])
    except (KeyError, ValueError) as exc:
        raise RecoveryConflict("invalid intent clock") from exc
    if claimed.tzinfo is None or claimed.astimezone(IST).date() != now.astimezone(IST).date():
        raise RecoveryConflict("broker daily order book cannot verify an older intent")
    orders = await kite.orders_snapshot()
    trades = await kite.order_trades(order_id)
    positions = await kite.get_broker_positions()
    if not isinstance(orders, list) or not isinstance(trades, list) or not isinstance(positions, dict) or not isinstance(positions.get("net"), list):
        raise RecoveryConflict("broker order, trade or position evidence unavailable")
    matches = [o for o in orders if isinstance(o, dict) and str(o.get("order_id")) == order_id]
    if len(matches) != 1:
        raise RecoveryConflict("order ID absent or duplicated in broker order book")
    order = matches[0]
    symbol = intent["tradingsymbol"]
    source = intent["source"]
    qty = _positive_int(intent["qty"], "position quantity")
    for field, expected in (("placed_by", account_id), ("tradingsymbol", symbol),
                            ("exchange", "NFO"), ("product", "MIS"),
                            ("transaction_type", "SELL"), ("tag", source[:20])):
        if str(order.get(field) or "") != expected:
            raise RecoveryConflict(f"broker order {field} mismatch")
    if str(order.get("status") or "").upper() not in TERMINAL:
        raise RecoveryConflict("broker order is not terminal")
    if _broker_time(order.get("order_timestamp")) + timedelta(seconds=1) < claimed.astimezone(IST):
        raise RecoveryConflict("broker order predates exit intent")
    if _positive_int(order.get("quantity"), "order quantity") != qty:
        raise RecoveryConflict("broker order quantity differs from local residual")
    filled = _positive_int(order.get("filled_quantity"), "filled quantity", allow_zero=True)
    if filled > qty:
        raise RecoveryConflict("filled quantity exceeds local position")
    if str(order["status"]).upper() == "COMPLETE" and filled != qty:
        raise RecoveryConflict("COMPLETE order has incomplete fill")
    for other in orders:
        if (not isinstance(other, dict) or str(other.get("order_id")) == order_id
                or other.get("placed_by") != account_id
                or other.get("tradingsymbol") != symbol):
            continue
        if str(other.get("order_id")) in known_recovered_orders:
            if str(other.get("status") or "").upper() not in TERMINAL:
                raise RecoveryConflict("previously reconciled order is not terminal")
            continue
        # An entry BUY before this intent may be the position being closed.
        # Any other order can hide fills or offset the net quantity.
        other_time = _broker_time(other.get("order_timestamp"))
        if (other.get("transaction_type") != "BUY"
                or other_time >= claimed.astimezone(IST)
                or str(other.get("status") or "").upper() not in TERMINAL):
            raise RecoveryConflict("another same-symbol broker order is not reconciled")
    trade_qty = 0
    weighted = 0.0
    fill_times = []
    seen_trade_ids = set()
    for trade in trades:
        if not isinstance(trade, dict):
            raise RecoveryConflict("malformed broker trade")
        trade_id = str(trade.get("trade_id") or "")
        if not trade_id or trade_id in seen_trade_ids:
            raise RecoveryConflict("missing or duplicate broker trade ID")
        seen_trade_ids.add(trade_id)
        for field, expected in (("order_id", order_id), ("tradingsymbol", symbol),
                                ("exchange", "NFO"), ("product", "MIS"),
                                ("transaction_type", "SELL")):
            if str(trade.get(field) or "") != expected:
                raise RecoveryConflict(f"broker trade {field} mismatch")
        n = _positive_int(trade.get("quantity"), "trade quantity")
        px = _price(trade.get("average_price"), "trade price")
        trade_qty += n
        weighted += n * px
        fill_time = _broker_time(trade.get("fill_timestamp"))
        if fill_time + timedelta(seconds=1) < claimed.astimezone(IST):
            raise RecoveryConflict("broker fill predates exit intent")
        fill_times.append(fill_time)
    if trade_qty != filled:
        raise RecoveryConflict("trade quantity disagrees with order fill")
    if filled and (not fill_times or max(fill_times) > now.astimezone(IST)):
        raise RecoveryConflict("broker fill timestamp is missing or future")
    remaining = qty - filled
    net = [p for p in positions["net"] if isinstance(p, dict)
           and p.get("exchange") == "NFO" and p.get("product") == "MIS"
           and p.get("tradingsymbol") == symbol]
    if len(net) > 1:
        raise RecoveryConflict("duplicate broker net positions")
    broker_qty = _positive_int(net[0].get("quantity"), "broker net quantity", allow_zero=True) if net else 0
    if broker_qty != remaining:
        raise RecoveryConflict("broker net quantity differs from expected residual")
    evidence = {"account_id": account_id, "order": order, "trades": trades,
                "net_position": net, "observed_at": now.isoformat()}
    evidence_json = json.dumps(evidence, sort_keys=True, default=str,
                               separators=(",", ":"), ensure_ascii=True)
    if len(evidence_json.encode("utf-8")) > 65536:
        raise RecoveryConflict("broker evidence exceeds retained limit")
    digest = hashlib.sha256(evidence_json.encode("utf-8")).hexdigest()
    return {"status": str(order["status"]).upper(), "filled_qty": filled,
            "remaining_qty": remaining, "fill_price": weighted / filled if filled else None,
            "fill_time": max(fill_times).isoformat() if filled else None,
            "evidence_sha256": digest, "evidence_json": evidence_json}


async def resolve_exit_intent(
    db_path: str, kite, *, position_id: int, source: str,
    expected_created_at: str, account_id: str, order_id: str, operator: str,
    now: datetime | None = None,
) -> dict:
    """Verify live broker facts, then atomically resolve one claimed intent."""
    if source != "FNO_LIVE" or not operator or len(operator.strip()) > 100:
        raise RecoveryConflict("live source and named operator are required")
    if type(position_id) is not int or position_id <= 0:
        raise RecoveryConflict("invalid position ID")
    await init_fno_positions_db(db_path)
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("""SELECT i.created_at, i.source, p.status,
            p.tradingsymbol, p.qty, p.lot_size, p.entry_premium,
            p.settlement_generation FROM fno_exit_intents i JOIN fno_positions p
            ON p.id=i.position_id AND p.source=i.source
            WHERE i.position_id=? AND i.source=?""", (position_id, source))
        row = await cur.fetchone()
        if row is None or row["created_at"] != expected_created_at or row["status"] != "OPEN":
            raise RecoveryConflict("intent missing, changed or position not open")
        cur = await db.execute("SELECT 1 FROM fno_exit_execution_receipts WHERE position_id=?", (position_id,))
        if await cur.fetchone():
            raise RecoveryConflict("full-fill receipt exists; settle that receipt first")
        intent = dict(row)
        cur = await db.execute("SELECT order_id FROM fno_exit_recoveries WHERE position_id=? AND source=?", (position_id, source))
        known_orders = frozenset(str(r[0]) for r in await cur.fetchall())
    proof = await verify_broker_exit(kite, intent=intent, account_id=account_id,
                                     order_id=order_id, known_recovered_orders=known_orders,
                                     now=now)
    filled, remaining = proof["filled_qty"], proof["remaining_qty"]
    lot_size = _positive_int(intent["lot_size"], "lot size")
    if remaining and remaining % lot_size:
        raise RecoveryConflict("residual is not a whole lot; manual reconciliation required")
    from performance import init_ledger
    await init_ledger(db_path)
    resolved_at = datetime.now(timezone.utc).isoformat()
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("BEGIN IMMEDIATE")
        try:
            cur = await db.execute("""SELECT i.created_at, p.qty, p.status,
                p.settlement_generation, p.entry_premium, p.tradingsymbol,
                p.gross_pnl, p.costs, p.pnl, p.initial_max_loss_rupees,
                p.max_loss_rupees
                FROM fno_exit_intents i JOIN fno_positions p ON p.id=i.position_id
                WHERE i.position_id=? AND i.source=? AND p.source=?""",
                (position_id, source, source))
            current = await cur.fetchone()
            if (current is None or current["created_at"] != expected_created_at
                    or current["status"] != "OPEN" or current["qty"] != intent["qty"]
                    or current["settlement_generation"] != intent["settlement_generation"]):
                raise RecoveryConflict("intent or position changed during broker inspection")
            generation = int(current["settlement_generation"])
            ledger_id = None
            if filled:
                generation += 1
                px = proof["fill_price"]
                gross = (px - float(current["entry_premium"])) * filled
                costs = calc_fno_costs(float(current["entry_premium"]), px, filled)
                pnl = gross - costs
                cur = await db.execute("SELECT COALESCE(SUM(pnl),0) FROM bankroll_ledger WHERE source=?", (source,))
                prior = float((await cur.fetchone())[0])
                bankroll_before = allocation_for_source(source) + prior
                cur = await db.execute("""INSERT INTO bankroll_ledger
                    (timestamp,event_type,ticker,pnl,bankroll_before,bankroll_after,
                     source,notes,origin_ref,settlement_generation)
                    VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    (resolved_at, "TRADE_CLOSED", current["tradingsymbol"], pnl,
                     bankroll_before, bankroll_before + pnl, source,
                     f"fno_exit_recovery order={order_id} qty={filled}",
                     f"fno_position:{position_id}", generation))
                ledger_id = cur.lastrowid
                total_gross = float(current["gross_pnl"] or 0) + gross
                total_costs = float(current["costs"] or 0) + costs
                total_pnl = float(current["pnl"] or 0) + pnl
                original_risk = float(current["initial_max_loss_rupees"] or 0)
                residual_risk = float(current["max_loss_rupees"] or 0) * remaining / intent["qty"]
                cur = await db.execute("""UPDATE fno_positions SET qty=?, lots=?,
                    status=?, settlement_generation=?, exit_time=?, exit_date=?,
                    exit_premium=?, exit_reason=?, gross_pnl=?, costs=?, pnl=?,
                    r_multiple=?, max_loss_rupees=?, exit_order_id=?
                    WHERE id=? AND source=? AND status='OPEN'
                    AND qty=? AND settlement_generation=?""",
                    (remaining, remaining // lot_size, "OPEN" if remaining else "CLOSED",
                     generation, proof["fill_time"], proof["fill_time"][:10],
                     px if not remaining else None,
                     "operator_reconciled_exit" if not remaining else None,
                     total_gross, total_costs, total_pnl,
                     total_pnl / original_risk if original_risk > 0 else 0.0,
                     residual_risk, order_id if not remaining else None,
                     position_id, source, intent["qty"], intent["settlement_generation"]))
                if cur.rowcount != 1:
                    raise RecoveryConflict("position changed before accounting")
            cur = await db.execute("DELETE FROM fno_exit_intents WHERE position_id=? AND source=? AND created_at=?",
                                   (position_id, source, expected_created_at))
            if cur.rowcount != 1:
                raise RecoveryConflict("intent changed before resolution")
            await db.execute("""INSERT INTO fno_exit_recoveries
                (position_id,source,intent_created_at,order_id,operator,account_id,
                 broker_evidence_sha256,broker_evidence_json,terminal_status,filled_qty,remaining_qty,
                 fill_price,settlement_generation,ledger_id,resolved_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (position_id, source, expected_created_at, order_id, operator.strip(),
                 account_id, proof["evidence_sha256"], proof["evidence_json"], proof["status"], filled,
                 remaining, proof["fill_price"], generation, ledger_id, resolved_at))
            await db.commit()
        except Exception:
            await db.rollback()
            raise
    return {"position_id": position_id, "source": source,
            "order_id": order_id, "terminal_status": proof["status"],
            "filled_qty": filled, "remaining_qty": remaining,
            "settlement_generation": generation, "ledger_id": ledger_id,
            "broker_evidence_sha256": proof["evidence_sha256"]}
