"""Completed-bar inputs for the read-only proactive SHADOW workflow.

This deliberately does *not* wrap a quote client.  A decision is made only
from bars whose exchange close is at or before the evaluation clock.  The
initial provider is a recorded-response adapter so the contract, provenance
and failure behaviour can be exercised without credentials or live orders.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


class CompletedBarDataError(ValueError):
    """A source failure that must be reported as unavailable, never healthy."""


@dataclass(frozen=True)
class CompletedBarSnapshot:
    """Validated, time-bounded bar data and non-price provenance.

    ``decision_bars`` contains no future bar.  ``outcome_bars`` is intentionally
    separate so the caller can pass it to the existing incremental simulator;
    that simulator applies the same evaluation clock again before using it.
    """

    decision_bars: dict[str, list[dict[str, Any]]]
    outcome_bars: dict[str, list[dict[str, Any]]]
    provenance: dict[str, Any]


def _utc(value: object, *, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value))
    except (TypeError, ValueError) as exc:
        raise CompletedBarDataError(f"{field} is not an ISO timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise CompletedBarDataError(f"{field} must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _normalise_bar(row: object, *, instrument: str) -> tuple[datetime, dict[str, Any]]:
    if not isinstance(row, dict):
        raise CompletedBarDataError(f"{instrument} contains a non-object bar")
    stamp = _utc(row.get("timestamp"), field=f"{instrument}.timestamp")
    try:
        open_, high, low, close, volume = (
            float(row[key]) for key in ("open", "high", "low", "close", "volume")
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise CompletedBarDataError(f"{instrument} bar is incomplete") from exc
    if (not all(math.isfinite(value) and value > 0 for value in (open_, high, low, close))
            or not math.isfinite(volume) or volume < 0
            or low > min(open_, close) or high < max(open_, close)):
        raise CompletedBarDataError(f"{instrument} bar violates OHLCV bounds")
    # Do not retain provider-specific, mutable fields as decision inputs.
    return stamp, {
        "timestamp": stamp.isoformat(), "open": open_, "high": high,
        "low": low, "close": close, "volume": volume,
    }


def load_recorded_completed_bar_snapshot(
    path: str | Path, *, as_of: datetime, max_age: timedelta,
) -> CompletedBarSnapshot:
    """Load one captured provider response without exposing future bars.

    Required fixture fields are ``mode=SHADOW``, ``provider``, ``received_at``,
    ``timeframe``, ``adjustment_version`` and ``instruments``.  Each instrument
    has a stable provider ``instrument_id`` and a list of completed OHLCV bars.
    The capture timestamp is not treated as a price timestamp; a stale capture
    is unavailable even when its schema is otherwise valid.
    """
    if max_age <= timedelta(0):
        raise ValueError("max_age must be positive")
    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise ValueError("as_of must be timezone-aware")
    as_of = as_of.astimezone(timezone.utc)
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, TypeError, json.JSONDecodeError) as exc:
        raise CompletedBarDataError("recorded provider response is unreadable") from exc
    if not isinstance(payload, dict) or payload.get("mode") != "SHADOW":
        raise CompletedBarDataError("recorded provider response must declare mode=SHADOW")
    provider = str(payload.get("provider", "")).strip()
    timeframe = str(payload.get("timeframe", "")).strip()
    adjustment_version = str(payload.get("adjustment_version", "")).strip()
    if not provider or not timeframe or not adjustment_version:
        raise CompletedBarDataError("provider, timeframe and adjustment_version are required")
    received_at = _utc(payload.get("received_at"), field="received_at")
    age = as_of - received_at
    if age > max_age:
        raise CompletedBarDataError("recorded provider response is stale")
    # A response received materially in the future cannot be used to make a
    # past decision, even if all its individual bars happen to be older.
    if received_at > as_of + timedelta(seconds=1):
        raise CompletedBarDataError("recorded provider response was received after evaluation clock")
    instruments = payload.get("instruments")
    if not isinstance(instruments, dict) or not instruments:
        raise CompletedBarDataError("instruments must be a non-empty object")

    decision: dict[str, list[dict[str, Any]]] = {}
    outcome: dict[str, list[dict[str, Any]]] = {}
    mapping: dict[str, str] = {}
    latest_exchange_at: datetime | None = None
    total_bars = 0
    for instrument, item in sorted(instruments.items()):
        if not isinstance(instrument, str) or not instrument or not isinstance(item, dict):
            raise CompletedBarDataError("instrument mapping is invalid")
        instrument_id = str(item.get("instrument_id", "")).strip()
        rows = item.get("bars")
        if not instrument_id or not isinstance(rows, list) or not rows:
            raise CompletedBarDataError(f"{instrument} requires instrument_id and non-empty bars")
        normalised = [_normalise_bar(row, instrument=instrument) for row in rows]
        normalised.sort(key=lambda pair: pair[0])
        if any(right[0] <= left[0] for left, right in zip(normalised, normalised[1:])):
            raise CompletedBarDataError(f"{instrument} has duplicate or unordered timestamps")
        # A captured provider response cannot contain a bar that had not closed
        # when that response was received.  Accepting one would turn an offline
        # replay fixture into a source of look-ahead bias.
        if any(stamp > received_at for stamp, _bar in normalised):
            raise CompletedBarDataError(f"{instrument} bar closes after received_at")
        mapping[instrument] = instrument_id
        outcome[instrument] = [bar for _stamp, bar in normalised]
        decision[instrument] = [bar for stamp, bar in normalised if stamp <= as_of]
        if not decision[instrument]:
            raise CompletedBarDataError(f"{instrument} has no completed bar at evaluation clock")
        latest = decision[instrument][-1]["timestamp"]
        latest_stamp = _utc(latest, field=f"{instrument}.timestamp")
        latest_exchange_at = max(latest_exchange_at, latest_stamp) if latest_exchange_at else latest_stamp
        total_bars += len(normalised)

    source_hash = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    provenance = {
        "provider": provider,
        "timeframe": timeframe,
        "adjustment_version": adjustment_version,
        "instrument_mapping": mapping,
        "received_at": received_at.isoformat(),
        "latest_exchange_at": latest_exchange_at.isoformat() if latest_exchange_at else None,
        "freshness_seconds": round(max(0.0, age.total_seconds()), 3),
        "fresh_until": (received_at + max_age).isoformat(),
        "dataset_sha256": source_hash,
        "instrument_count": len(decision),
        "bar_count": total_bars,
        "source_kind": "RECORDED_COMPLETED_BARS_V1",
    }
    return CompletedBarSnapshot(decision_bars=decision, outcome_bars=outcome, provenance=provenance)
