"""Retain observed advisory inputs without granting trade or send authority."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import asdict
from pathlib import Path
from research_archive import guarded_write, _admit_bytes


@guarded_write
def persist_candidate_input(archive_root, *, book, snapshot, profile, evaluation_at, received_at):
    """Retain the observed candidate inputs, including a conservative receipt clock.

    received_at must be sampled after acquisition, never copied from the tick's
    start. A later receipt is retained even when it prevents causal approval.
    """
    from partner_qualification import _clock
    _clock(evaluation_at, "evaluation_at")
    _clock(received_at, "received_at")
    if snapshot is None or _clock(snapshot.taken_at, "snapshot taken_at") > received_at:
        raise ValueError("candidate snapshot cannot follow receipt")
    def quote_payload(quote):
        value = asdict(quote)
        value.pop("contract")
        return {"token": quote.contract.token, **value}
    payload = {"format": "partner_observed_candidate_input_v1", "underlying": book.underlying,
        "segment": book.segment, "evaluation_at": evaluation_at.isoformat(),
        "received_at": received_at.isoformat(), "profile": asdict(profile),
        "contracts": [asdict(contract) for contract in sorted(book.by_symbol.values(), key=lambda c: c.token)],
        "snapshot": {"taken_at": snapshot.taken_at.isoformat(), "expiry": snapshot.expiry.isoformat(),
            "forward": snapshot.forward, "parity_forward": snapshot.parity_forward, "lot_size": snapshot.lot_size,
            "quotes": [quote_payload(quote) for _, quote in sorted(snapshot.quotes.items())],
            "future_quote": quote_payload(snapshot.fut_quote) if snapshot.fut_quote else None},
        "can_qualify": False}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str, allow_nan=False).encode()
    digest = hashlib.sha256(encoded).hexdigest()
    directory = Path(archive_root) / "partner-candidate-inputs" / received_at.date().isoformat() / book.underlying
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"{digest}.json"
    if target.exists():
        if target.read_bytes() != encoded:
            raise ValueError("candidate archive fingerprint mismatch")
    else:
        _admit_bytes(len(encoded))
        fd, temporary = tempfile.mkstemp(prefix=".candidate-", dir=directory)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(encoded)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                os.link(temporary, target)
            except FileExistsError:
                if target.read_bytes() != encoded:
                    raise ValueError("candidate archive fingerprint mismatch")
        finally:
            os.unlink(temporary)
    return {"state": "OBSERVED", "path": str(target), "sha256": digest, "can_qualify": False}


def load_public_lifecycle(paths, *, underlying, max_age_seconds):
    """Recompute closed-bar public observations from verified retained inputs.

    Receipt is when the response was available, never the historical bar close.
    The result proves the supplied captures only, not that no captures are absent.
    """
    from datetime import datetime, timedelta
    import math
    from zoneinfo import ZoneInfo
    from fno_engine_mom import evaluate_fno_mom
    if not math.isfinite(max_age_seconds) or max_age_seconds <= 0:
        raise ValueError("public maximum age must be finite and positive")
    observations, sources = [], []
    seen = set()
    for path in paths:
        target = Path(path)
        if target.stem in seen:
            raise ValueError("duplicate public capture")
        seen.add(target.stem)
        frame, regime, evaluation_at, provenance = load_public_input(target, underlying=underlying)
        if frame.index.tz is not None:
            frame.index = frame.index.tz_convert("Asia/Kolkata").tz_localize(None)
        signal = evaluate_fno_mom(frame, regime, evaluation_at.astimezone(ZoneInfo("Asia/Kolkata")))
        try:
            observed = datetime.strptime(signal.bar_ts, "%Y-%m-%d %H:%M:%S").replace(
                tzinfo=ZoneInfo("Asia/Kolkata")) + timedelta(minutes=5)
            price = float(signal.close)
        except (TypeError, ValueError, AttributeError) as exc:
            raise ValueError("capture has no usable closed-bar observation") from exc
        # Evaluation may precede receipt; that fact remains in source metadata.
        received = provenance["received_at"]
        if (not math.isfinite(price) or price <= 0 or observed > evaluation_at
                or observed > received or (received - observed).total_seconds() > max_age_seconds):
            raise ValueError("capture public observation is future, stale or invalid")
        observations.append(dict(observed_at=observed, received_at=received, price=price))
        sources.append(dict(sha256=target.stem, evaluation_at=evaluation_at.isoformat(),
                            received_at=received.isoformat(), provenance_state=provenance["state"]))
    observations.sort(key=lambda item: item["received_at"])
    if any(first["received_at"] == second["received_at"] for first, second in zip(observations, observations[1:])):
        raise ValueError("conflicting public captures share a receipt")
    return {"observations": observations, "sources": sorted(sources, key=lambda item: item["sha256"]),
            "coverage": "SUPPLIED_CAPTURES_ONLY", "can_qualify": False}


def load_public_input(path, *, underlying):
    """Validate retained bytes and reconstruct the original evaluation inputs."""
    from datetime import datetime
    import pandas as pd
    from partner_qualification import _bars_payload, _clock
    target = Path(path)
    raw = target.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if target.stem != digest:
        raise ValueError("public-input filename fingerprint mismatch")
    value = json.loads(raw)
    if (value.get("format") != "partner_observed_public_input_v1"
            or value.get("underlying") != underlying
            or value.get("bar_start_timezone") != "Asia/Kolkata"):
        raise ValueError("public-input scope or format mismatch")
    at = _clock(datetime.fromisoformat(value["evaluation_at"]), "evaluation_at")
    received = _clock(datetime.fromisoformat(value["received_at"]), "received_at")
    frame = pd.DataFrame(value["bars"])
    frame.index = pd.to_datetime(frame.pop("bar_start"), errors="raise")
    _bars_payload(frame)
    # Reconstruct the original scan, never silently move its decision clock
    # forward to make the fetch appear available earlier than it was.
    provenance = {"state": "CONTEMPORANEOUS" if received <= at else "RETROSPECTIVE",
                  "source": f"retained-public-input:{digest}", "event_at": None,
                  "received_at": received, "retrieved_at": received}
    return frame, value["regime"], at, provenance


@guarded_write
def persist_public_input(archive_root, scan, *, regime: str, evaluation_at) -> dict:
    """Content-address a full fetched frame plus honest evaluation/receipt clocks.

    Receipt can be after the scanner's original evaluation clock. Preserve
    that fact: the artifact is observed input, not automatic causal approval.
    """
    bars = getattr(scan, "research_bars", None)
    received = getattr(scan, "research_received_at", None)
    if bars is None or received is None:
        return {"state": "UNAVAILABLE", "reason": "observed_bars_missing"}
    from partner_qualification import _bars_payload
    frame = bars.copy()
    if getattr(frame.index, "tz", None) is not None:
        frame.index = frame.index.tz_convert("Asia/Kolkata").tz_localize(None)
    rows = _bars_payload(frame)
    if not rows:
        return {"state": "UNAVAILABLE", "reason": "observed_bars_empty"}
    payload = {
        "format": "partner_observed_public_input_v1", "underlying": scan.name,
        "future_token": scan.research_future_token, "regime": regime,
        "evaluation_at": evaluation_at.isoformat(), "received_at": received.isoformat(),
        "source": "KITE_HISTORICAL_5MINUTE_OBSERVED_RESPONSE",
        "bar_start_timezone": "Asia/Kolkata", "bars": rows,
        "signal": asdict(scan.sig) if scan.sig is not None else None,
        "error": scan.error, "can_qualify": False,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str, allow_nan=False).encode()
    digest = hashlib.sha256(encoded).hexdigest()
    directory = Path(archive_root) / "partner-public-inputs" / received.date().isoformat() / scan.name
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"{digest}.json"
    if target.exists():
        if hashlib.sha256(target.read_bytes()).hexdigest() != digest:
            raise ValueError("existing public-input evidence hash mismatch")
    else:
        _admit_bytes(len(encoded))
        fd, temporary = tempfile.mkstemp(prefix=".capture-", dir=directory)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(encoded)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, target)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
    return {"state": "OBSERVED", "sha256": digest, "path": str(target), "bar_count": len(rows),
            "can_qualify": False}
