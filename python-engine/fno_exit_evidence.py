"""[F0-R4 2026-10-03] One pure interpretation of a broker exit packet.

``verify_broker_exit`` (live, operator-authorised recovery) and the shared
F&O risk reader (which must never call the broker) both derive the exit's
facts from the same order/trades/net-position packet through
``derive_exit_facts``. The reader additionally binds the retained packet to
its immutable receipt, the position's entry economics and the frozen cost
schedule with ``validate_retained_exit_receipt``.

A matching digest proves only that the stored packet was not changed apart
from its digest; it is not broker authenticity. These checks remove the
empty-payload and inconsistent-edit paths, not a determined rewrite of
receipt, packet and digest together (which the immutability triggers guard).
"""
from __future__ import annotations

from datetime import datetime, timedelta
import hashlib
import json
import math
from typing import Optional
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
TERMINAL = {"COMPLETE", "CANCELLED", "REJECTED"}
MAX_EVIDENCE_BYTES = 65536
_COST_RATE_KEYS = (
    "brokerage_flat_per_order", "stt_sell_pct", "exchange_pct", "sebi_pct",
    "stamp_duty_buy_pct", "ipft_pct", "gst_pct",
)


class RecoveryConflict(ValueError):
    """Evidence is ambiguous or no longer matches the durable intent."""


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


def broker_time(value: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise RecoveryConflict("missing broker fill timestamp")
    try:
        parsed = datetime.fromisoformat(value.strip())
    except ValueError as exc:
        raise RecoveryConflict("invalid broker fill timestamp") from exc
    return parsed.replace(tzinfo=IST) if parsed.tzinfo is None else parsed.astimezone(IST)


def derive_exit_facts(
    *, order: dict, trades: list, net_position: list, account_id: str, order_id: str,
    source: str, tradingsymbol: str, intent_qty: int, intent_created_at: datetime,
    observed_at: datetime,
) -> dict:
    """Derive status, quantities, weighted fill price and time from one packet.

    ``net_position`` is the broker net list already narrowed to NFO/MIS rows
    of ``tradingsymbol``. Raises ``RecoveryConflict`` on any disagreement.
    """
    if not isinstance(order, dict) or not isinstance(trades, list) or not isinstance(net_position, list):
        raise RecoveryConflict("broker order, trade or position evidence unavailable")
    if intent_created_at.tzinfo is None or observed_at.tzinfo is None:
        raise RecoveryConflict("naive evidence clock")
    claimed = intent_created_at.astimezone(IST)
    qty = _positive_int(intent_qty, "position quantity")
    if str(order.get("order_id")) != order_id:
        raise RecoveryConflict("broker order order_id mismatch")
    for field, expected in (("placed_by", account_id), ("tradingsymbol", tradingsymbol),
                            ("exchange", "NFO"), ("product", "MIS"),
                            ("transaction_type", "SELL"), ("tag", source[:20])):
        if str(order.get(field) or "") != expected:
            raise RecoveryConflict(f"broker order {field} mismatch")
    if str(order.get("status") or "").upper() not in TERMINAL:
        raise RecoveryConflict("broker order is not terminal")
    if broker_time(order.get("order_timestamp")) + timedelta(seconds=1) < claimed:
        raise RecoveryConflict("broker order predates exit intent")
    if _positive_int(order.get("quantity"), "order quantity") != qty:
        raise RecoveryConflict("broker order quantity differs from local residual")
    filled = _positive_int(order.get("filled_quantity"), "filled quantity", allow_zero=True)
    if filled > qty:
        raise RecoveryConflict("filled quantity exceeds local position")
    if str(order["status"]).upper() == "COMPLETE" and filled != qty:
        raise RecoveryConflict("COMPLETE order has incomplete fill")
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
        for field, expected in (("order_id", order_id), ("tradingsymbol", tradingsymbol),
                                ("exchange", "NFO"), ("product", "MIS"),
                                ("transaction_type", "SELL")):
            if str(trade.get(field) or "") != expected:
                raise RecoveryConflict(f"broker trade {field} mismatch")
        n = _positive_int(trade.get("quantity"), "trade quantity")
        px = _price(trade.get("average_price"), "trade price")
        trade_qty += n
        weighted += n * px
        fill_time = broker_time(trade.get("fill_timestamp"))
        if fill_time + timedelta(seconds=1) < claimed:
            raise RecoveryConflict("broker fill predates exit intent")
        fill_times.append(fill_time)
    if trade_qty != filled:
        raise RecoveryConflict("trade quantity disagrees with order fill")
    if filled and (not fill_times or max(fill_times) > observed_at.astimezone(IST)):
        raise RecoveryConflict("broker fill timestamp is missing or future")
    remaining = qty - filled
    if len(net_position) > 1:
        raise RecoveryConflict("duplicate broker net positions")
    for row in net_position:
        if (not isinstance(row, dict) or row.get("exchange") != "NFO"
                or row.get("product") != "MIS" or row.get("tradingsymbol") != tradingsymbol):
            raise RecoveryConflict("broker net position identity mismatch")
    broker_qty = (_positive_int(net_position[0].get("quantity"), "broker net quantity", allow_zero=True)
                  if net_position else 0)
    if broker_qty != remaining:
        raise RecoveryConflict("broker net quantity differs from expected residual")
    return {"status": str(order["status"]).upper(), "filled_qty": filled,
            "remaining_qty": remaining, "fill_price": weighted / filled if filled else None,
            "fill_time": max(fill_times).isoformat() if filled else None,
            "trade_ids": sorted(seen_trade_ids)}


def encode_evidence(evidence: dict) -> tuple[str, str]:
    evidence_json = json.dumps(evidence, sort_keys=True, default=str,
                               separators=(",", ":"), ensure_ascii=True)
    if len(evidence_json.encode("utf-8")) > MAX_EVIDENCE_BYTES:
        raise RecoveryConflict("broker evidence exceeds retained limit")
    return evidence_json, hashlib.sha256(evidence_json.encode("utf-8")).hexdigest()


def valid_cost_snapshot(snapshot: object) -> bool:
    if not isinstance(snapshot, dict) or not isinstance(snapshot.get("schedule_version"), str) \
            or not snapshot["schedule_version"]:
        return False
    rates = snapshot.get("rates")
    if not isinstance(rates, dict):
        return False
    for key in _COST_RATE_KEYS:
        value = rates.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)) \
                or not math.isfinite(float(value)) or float(value) < 0:
            return False
    return True


def _aware(value) -> Optional[datetime]:
    try:
        parsed = datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo is not None else None


def validate_retained_exit_receipt(
    receipt: dict, *, source: str, tradingsymbol: str, position_entry_premium: object,
) -> tuple[str, list[str]]:
    """Bind one stored recovery receipt to its retained packet and economics.

    Returns ``(reason, trade_ids)``; ``reason`` is empty when the receipt is
    consistent. Never calls the broker and never reprices with live settings.
    """
    from fno_costs import calc_fno_costs_from_snapshot

    raw = receipt.get("broker_evidence_json")
    digest = receipt.get("broker_evidence_sha256")
    if not isinstance(raw, str) or not isinstance(digest, str) or len(digest) != 64:
        return "recovery_payload_mismatch", []
    encoded = raw.encode("utf-8")
    if len(encoded) > MAX_EVIDENCE_BYTES or hashlib.sha256(encoded).hexdigest() != digest:
        return "recovery_payload_mismatch", []
    try:
        packet = json.loads(raw)
    except (TypeError, ValueError):
        return "recovery_payload_mismatch", []
    created = _aware(receipt.get("intent_created_at"))
    observed = _aware(packet.get("observed_at")) if isinstance(packet, dict) else None
    filled, remaining = receipt.get("filled_qty"), receipt.get("remaining_qty")
    if (not isinstance(packet, dict) or packet.get("account_id") != receipt.get("account_id")
            or created is None or observed is None
            or type(filled) is not int or type(remaining) is not int):
        return "recovery_payload_mismatch", []
    try:
        facts = derive_exit_facts(
            order=packet.get("order"), trades=packet.get("trades"),
            net_position=packet.get("net_position"), account_id=str(receipt.get("account_id") or ""),
            order_id=str(receipt.get("order_id") or ""), source=source,
            tradingsymbol=tradingsymbol, intent_qty=filled + remaining,
            intent_created_at=created, observed_at=observed,
        )
    except (RecoveryConflict, KeyError, TypeError, AttributeError):
        return "recovery_payload_mismatch", []
    if (facts["status"] != receipt.get("terminal_status") or facts["filled_qty"] != filled
            or facts["remaining_qty"] != remaining):
        return "recovery_payload_mismatch", []
    entry = receipt.get("entry_premium")
    if entry is not None:
        try:
            if not math.isclose(float(entry), float(position_entry_premium),
                                rel_tol=0.0, abs_tol=1e-9):
                return "recovery_entry_economics_mismatch", []
        except (TypeError, ValueError):
            return "recovery_entry_economics_mismatch", []
    if filled:
        fill = receipt.get("fill_price")
        if not isinstance(fill, (int, float)) or not math.isclose(
                float(fill), facts["fill_price"], rel_tol=1e-9, abs_tol=1e-6):
            return "recovery_payload_mismatch", []
        if entry is None:
            return "recovery_entry_economics_mismatch", []
        try:
            snapshot = json.loads(receipt.get("cost_snapshot_json") or "")
        except (TypeError, ValueError):
            snapshot = None
        if not valid_cost_snapshot(snapshot):
            return "recovery_cost_provenance_unavailable", []
        expected = calc_fno_costs_from_snapshot(float(entry), float(fill), filled, snapshot)
        costs = receipt.get("costs")
        if not isinstance(costs, (int, float)) or not math.isclose(
                float(costs), expected, rel_tol=0.0, abs_tol=0.01):
            return "recovery_cost_mismatch", []
    return "", facts["trade_ids"]
