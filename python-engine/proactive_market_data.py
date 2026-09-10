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
from typing import Any, Callable, Mapping

import pandas as pd
import pytz


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


async def load_kite_completed_bar_snapshot(
    kite: Any, *, instruments: Mapping[str, Mapping[str, Any]], as_of: datetime,
    max_age: timedelta, archive_root: str | Path, interval: str = "5minute",
    receipt_clock: Callable[[], datetime] | None = None, isolate_failures: bool = True,
) -> CompletedBarSnapshot:
    """Read completed Kite candles only; no quote, order, or fixture authority.

    Kite candle timestamps mark the start of the interval, so a five-minute bar
    is usable only once ``timestamp + 5 minutes <= as_of``.  This is stricter
    than treating a current incomplete candle as a completed observation.
    """
    if not getattr(kite, "access_token", None):
        raise CompletedBarDataError("Kite completed-bar source has no access token")
    if max_age <= timedelta(0) or not instruments:
        raise CompletedBarDataError("Kite completed-bar source is unconfigured")
    as_of = _utc(as_of, field="as_of")
    if interval != "5minute":
        raise CompletedBarDataError("only 5minute completed bars are supported")
    # One unavailable index must not erase evidence for the other.  The
    # single-instrument path below remains strict; this fan-out only merges
    # independently verified results and reports failures in provenance.
    if isolate_failures and len(instruments) > 1:
        good: dict[str, CompletedBarSnapshot] = {}
        failures: dict[str, str] = {}
        for name, specification in sorted(instruments.items()):
            try:
                good[name] = await load_kite_completed_bar_snapshot(
                    kite, instruments={name: specification}, as_of=as_of, max_age=max_age,
                    archive_root=archive_root, interval=interval, receipt_clock=receipt_clock,
                    isolate_failures=False,
                )
            except CompletedBarDataError as exc:
                failures[name] = str(exc)
        if not good:
            raise CompletedBarDataError("Kite completed-bar source unavailable for every configured index")
        decision = {name: snapshot.decision_bars[name] for name, snapshot in good.items()}
        provenance_rows = {name: snapshot.provenance for name, snapshot in good.items()}
        receipts = [snapshot.provenance["received_at"] for snapshot in good.values()]
        payload = {"provider": "KITE", "interval": interval, "as_of": as_of.isoformat(),
                   "good": {name: row["dataset_sha256"] for name, row in provenance_rows.items()}, "failures": failures}
        return CompletedBarSnapshot(decision_bars=decision, outcome_bars=decision, provenance={
            "provider": "KITE", "timeframe": interval, "adjustment_version": "provider_unadjusted",
            "instrument_mapping": {name: row["instrument_mapping"][name] for name, row in provenance_rows.items()},
            "per_index": {name: {"state": "OBSERVED", "dataset_sha256": row["dataset_sha256"]} for name, row in provenance_rows.items()}
                         | {name: {"state": "UNAVAILABLE", "reason": reason} for name, reason in failures.items()},
            "received_at": max(receipts), "dataset_sha256": hashlib.sha256(
                json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
            "instrument_count": len(good), "bar_count": sum(len(rows) for rows in decision.values()),
            "source_kind": "KITE_COMPLETED_BARS_V1", "partial_failure": bool(failures),
        })
    # The caller's clock only limits the request range.  It is not evidence
    # that a response was available at that instant.  Every bar is assessed at
    # the actual post-request receipt clock below.
    request_at = as_of
    start = (request_at - timedelta(days=4)).date().isoformat()
    end = request_at.date().isoformat()
    decision: dict[str, list[dict[str, Any]]] = {}
    mapping: dict[str, str] = {}
    latest_close: datetime | None = None
    receipts: dict[str, datetime] = {}
    master_provenance: dict[str, dict[str, str]] = {}
    for name, specification in sorted(instruments.items()):
        token, master = _validated_kite_instrument(
            name, specification, archive_root=archive_root,
        )
        try:
            frame = await kite.get_intraday_by_token(token, start, end, interval)
        except Exception as exc:
            raise CompletedBarDataError(f"Kite completed-bar request failed for {name}") from exc
        received_at = _utc((receipt_clock or (lambda: datetime.now(timezone.utc)))(), field=f"{name}.received_at")
        receipts[name] = received_at
        if not isinstance(frame, pd.DataFrame) or frame.empty:
            raise CompletedBarDataError(f"Kite completed-bar response is empty for {name}")
        starts = _kite_client_datetime_index(frame, instrument=name)
        bars = []
        for start_at, (_, row) in zip(starts, frame.iterrows()):
            try:
                close_at = start_at + timedelta(minutes=5)
                raw = {"timestamp": close_at.isoformat(), "open": row["open"], "high": row["high"],
                       "low": row["low"], "close": row["close"], "volume": row.get("volume", 0)}
                _, bar = _normalise_bar(raw, instrument=name)
            except (KeyError, TypeError, ValueError, CompletedBarDataError) as exc:
                raise CompletedBarDataError(f"Kite completed-bar row is invalid for {name}") from exc
            # Kite timestamps are interval starts.  A current interval cannot
            # be a decision input, even when the network request started later.
            if close_at <= received_at:
                bars.append(bar)
        if not bars:
            raise CompletedBarDataError(f"Kite has no completed bar at evaluation clock for {name}")
        bars.sort(key=lambda item: item["timestamp"])
        if len({item["timestamp"] for item in bars}) != len(bars):
            raise CompletedBarDataError(f"Kite has duplicate completed bars for {name}")
        close_at = _utc(bars[-1]["timestamp"], field=f"{name}.close_at")
        if received_at - close_at > max_age:
            raise CompletedBarDataError(f"Kite completed bars are stale for {name}")
        decision[name], mapping[name] = bars, str(token)
        master_provenance[name] = master
        latest_close = max(latest_close, close_at) if latest_close else close_at
    received_at = max(receipts.values())
    payload = {"provider": "KITE", "timeframe": interval, "instrument_mapping": mapping,
               "master_provenance": master_provenance, "bars": decision,
               "request_at": request_at.isoformat(), "received_at": received_at.isoformat()}
    provenance = {"provider": "KITE", "timeframe": interval, "adjustment_version": "provider_unadjusted",
                  "instrument_mapping": mapping, "master_provenance": master_provenance,
                  "request_at": request_at.isoformat(), "received_at": received_at.isoformat(),
                  "per_instrument_received_at": {name: value.isoformat() for name, value in receipts.items()},
                  "latest_exchange_at": latest_close.isoformat() if latest_close else None,
                  "freshness_seconds": max(0.0, (received_at - latest_close).total_seconds()) if latest_close else None,
                  "fresh_until": (latest_close + max_age).isoformat() if latest_close else None,
                  "dataset_sha256": hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
                  "instrument_count": len(decision), "bar_count": sum(len(rows) for rows in decision.values()),
                  "source_kind": "KITE_COMPLETED_BARS_V1"}
    return CompletedBarSnapshot(decision_bars=decision, outcome_bars=decision, provenance=provenance)


def _kite_client_datetime_index(frame: pd.DataFrame, *, instrument: str) -> list[datetime]:
    """Normalize the *actual* ``KiteClient`` DataFrame contract.

    ``KiteClient.get_intraday_by_token`` puts its ``datetime`` column into a
    timezone-naive IST ``DatetimeIndex``.  Accepting timestamp-looking data in
    an arbitrary column caused the old adapter to test a shape the client never
    returns.  A naive index is therefore explicitly IST, while an aware index
    retains its supplied offset.  Object/mixed indexes and DST ambiguity are
    rejected rather than guessed.
    """
    if not isinstance(frame.index, pd.DatetimeIndex) or frame.index.name != "datetime":
        raise CompletedBarDataError(f"Kite completed-bar datetime index is invalid for {instrument}")
    if frame.index.hasnans or not frame.index.is_monotonic_increasing or frame.index.has_duplicates:
        raise CompletedBarDataError(f"Kite completed-bar datetime index is unordered for {instrument}")
    try:
        index = frame.index.tz_localize("Asia/Kolkata", ambiguous="raise", nonexistent="raise") if frame.index.tz is None else frame.index
        return [stamp.to_pydatetime().astimezone(timezone.utc) for stamp in index]
    except (TypeError, ValueError, pytz.AmbiguousTimeError, pytz.NonExistentTimeError) as exc:
        raise CompletedBarDataError(f"Kite completed-bar datetime index is ambiguous for {instrument}") from exc


def _validated_kite_instrument(
    name: str, specification: Mapping[str, Any], *, archive_root: str | Path,
) -> tuple[int, dict[str, str]]:
    """Resolve a token only when a dated archived master proves its identity."""
    if name not in {"NIFTY", "SENSEX"} or not isinstance(specification, Mapping):
        raise CompletedBarDataError("Kite instrument mapping must declare NIFTY/SENSEX specifications")
    token = specification.get("token")
    basis = str(specification.get("basis", "")).upper()
    master_sha256 = str(specification.get("master_sha256", "")).lower()
    if isinstance(token, bool) or not isinstance(token, int) or token <= 0:
        raise CompletedBarDataError(f"Kite token is invalid for {name}")
    if basis not in {"SPOT", "FUTURE"} or len(master_sha256) != 64 or any(c not in "0123456789abcdef" for c in master_sha256):
        raise CompletedBarDataError(f"Kite basis and archived master digest are required for {name}")
    expected_exchange = "NSE" if name == "NIFTY" and basis == "SPOT" else "BSE" if basis == "SPOT" else "NFO" if name == "NIFTY" else "BFO"
    for manifest_path in sorted(Path(archive_root).glob("contract-masters/**/manifest.json"), reverse=True):
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if manifest.get("raw_sha256") != master_sha256:
                continue
            for line in (manifest_path.parent / "contracts.jsonl").read_text(encoding="utf-8").splitlines():
                row = json.loads(line)
                if (str(row.get("instrument_token")) == str(token)
                        and str(row.get("underlying", "")).upper() == name
                        and str(row.get("exchange", "")).upper() == expected_exchange
                        and ((basis == "FUTURE" and row.get("instrument_type") == "FUT")
                             or (basis == "SPOT" and row.get("instrument_type") == "INDEX"))):
                    return token, {"basis": basis, "master_sha256": master_sha256,
                                   "exchange": expected_exchange, "tradingsymbol": str(row.get("tradingsymbol", ""))}
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            continue
    raise CompletedBarDataError(f"Kite token mapping has no matching archived current master for {name}")
