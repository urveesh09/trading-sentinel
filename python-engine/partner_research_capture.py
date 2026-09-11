"""Retain observed advisory inputs without granting trade or send authority."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import asdict
from pathlib import Path
from research_archive import guarded_write, _admit_bytes


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
