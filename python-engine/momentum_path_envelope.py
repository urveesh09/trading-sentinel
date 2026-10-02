"""Typed, source-bound provider envelope for passive momentum-paper paths (S4).

A SHA-256 of caller-supplied bytes proves only that the bytes did not change.
It does not prove that the separately supplied ticker, LTP or provider clock
columns came *from* those bytes.  The envelope wraps the exact Kite quote
object for one instrument under its documented ``EXCHANGE:SYMBOL`` key, and
``verify_path_quote_envelope`` re-derives ticker, LTP and provider time from
the bytes, requiring exact agreement with the stored columns.  Pure: no I/O,
no provider call.
"""
from __future__ import annotations

from datetime import datetime
import json
import math
from typing import Any, Mapping
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
ENVELOPE_SCHEMA = "kite_equity_quote_envelope_v1"


class PathEnvelopeError(ValueError):
    """The packet bytes do not support the declared observation columns."""


def encode_path_quote_envelope(*, instrument_key: str, quote: Mapping[str, Any]) -> bytes:
    """Canonical envelope bytes a quote-fanout caller passes as ``source_packet``."""
    if not isinstance(instrument_key, str) or ":" not in instrument_key:
        raise PathEnvelopeError("instrument_key must be EXCHANGE:SYMBOL")
    return json.dumps({"schema": ENVELOPE_SCHEMA, "instrument": instrument_key, "quote": dict(quote)},
                      sort_keys=True, separators=(",", ":"), default=str, allow_nan=False).encode("utf-8")


def _provider_clock(quote: Mapping[str, Any]) -> datetime:
    value = quote.get("timestamp") or quote.get("last_trade_time")
    if not isinstance(value, str) or not value.strip():
        raise PathEnvelopeError("quote has no provider timestamp")
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise PathEnvelopeError("quote provider timestamp is unparseable") from exc
    # Kite REST timestamps are exchange-local (IST) without an offset.
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=IST)


def verify_path_quote_envelope(packet: bytes, *, ticker: str, ltp: float,
                               provider_observed_at: datetime) -> None:
    """Raise unless ticker, LTP and provider time are exactly those in ``packet``."""
    try:
        value = json.loads(packet.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, AttributeError) as exc:
        raise PathEnvelopeError("packet is not a UTF-8 JSON envelope") from exc
    if not isinstance(value, dict) or value.get("schema") != ENVELOPE_SCHEMA:
        raise PathEnvelopeError(f"packet schema must be {ENVELOPE_SCHEMA}")
    instrument, quote = value.get("instrument"), value.get("quote")
    if not isinstance(instrument, str) or ":" not in instrument or not isinstance(quote, dict):
        raise PathEnvelopeError("envelope requires instrument EXCHANGE:SYMBOL and a quote object")
    if instrument.split(":", 1)[1].strip().upper() != str(ticker).strip().upper():
        raise PathEnvelopeError("envelope instrument does not match the observation ticker")
    price = quote.get("last_price")
    if (isinstance(price, bool) or not isinstance(price, (int, float)) or not math.isfinite(price)
            or price <= 0 or float(price) != float(ltp)):
        raise PathEnvelopeError("envelope last_price does not match the observation ltp")
    if provider_observed_at.tzinfo is None or _provider_clock(quote) != provider_observed_at:
        raise PathEnvelopeError("envelope provider timestamp does not match provider_observed_at")


__all__ = ["ENVELOPE_SCHEMA", "PathEnvelopeError", "encode_path_quote_envelope",
           "verify_path_quote_envelope"]
