"""Crash-tolerant session rotation for append-only operational CSV evidence.

The current session remains at the configured path for existing dashboards and
operators.  At the first write of a new IST session, the prior complete file
is moved into a sibling evidence archive with its header and bytes unchanged;
an append-only manifest records its digest.  No routine retention deletion is
performed here: archive expiry requires a separate backup/restore policy.
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import tempfile
import threading
from datetime import datetime
from pathlib import Path
from typing import Iterable, Mapping, Sequence
from zoneinfo import ZoneInfo


IST = ZoneInfo("Asia/Kolkata")
_LOCK = threading.RLock()


def _session_date(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("CSV evidence row needs a non-empty scanned_at timestamp")
    try:
        observed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("CSV evidence scanned_at must be ISO-8601") from exc
    if observed.tzinfo is None or observed.utcoffset() is None:
        raise ValueError("CSV evidence scanned_at must be timezone-aware")
    return observed.astimezone(IST).date().isoformat()


def _paths(csv_path: str) -> tuple[Path, Path, Path, Path]:
    current = Path(csv_path)
    archive_dir = current.parent / (current.stem + ".sessions")
    return (
        current,
        current.with_name(current.name + ".session.json"),
        archive_dir,
        archive_dir / "manifest.jsonl",
    )


def _atomic_bytes(path: Path, contents: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".session-", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(contents)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _write_header(path: Path, columns: Sequence[str]) -> None:
    import io
    buffer = io.StringIO(newline="")
    csv.DictWriter(buffer, fieldnames=list(columns)).writeheader()
    _atomic_bytes(path, buffer.getvalue().encode("utf-8"))


def _read_state(path: Path) -> str | None:
    if not path.exists():
        return None
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    session = state.get("session_date") if isinstance(state, dict) else None
    return session if isinstance(session, str) and len(session) == 10 else None


def _write_state(path: Path, session_date: str) -> None:
    _atomic_bytes(path, json.dumps({"session_date": session_date}, sort_keys=True).encode("utf-8"))


def _digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _append_manifest(path: Path, *, session_date: str, archive: Path) -> None:
    record = {
        "archive": archive.name,
        "bytes": archive.stat().st_size,
        "session_date": session_date,
        "sha256": _digest(archive),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = (json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    with path.open("ab") as handle:
        handle.write(encoded)
        handle.flush()
        os.fsync(handle.fileno())


def _archive_current(current: Path, archive_dir: Path, manifest: Path, session_date: str) -> None:
    if not current.exists() or current.stat().st_size == 0:
        return
    archive_dir.mkdir(parents=True, exist_ok=True)
    target = archive_dir / f"{session_date}.csv"
    if target.exists():
        if _digest(target) != _digest(current):
            raise FileExistsError(f"refusing to overwrite retained CSV archive: {target}")
        current.unlink()
        return
    os.replace(current, target)
    _append_manifest(manifest, session_date=session_date, archive=target)


def append_session_rows(
    csv_path: str, columns: Sequence[str], rows: Iterable[Mapping[str, object]],
) -> dict[str, object]:
    """Append a same-session batch and rotate prior evidence without loss.

    The return value is bounded operational evidence suitable for a structured
    log.  It contains no row payloads or secrets.
    """
    batch = list(rows)
    if not batch:
        return {"rows": 0, "rotated": False, "session_date": None}
    session_dates = {_session_date(row.get("scanned_at")) for row in batch}
    if len(session_dates) != 1:
        raise ValueError("CSV evidence batch must belong to one IST session")
    session_date = session_dates.pop()
    current, state_path, archive_dir, manifest = _paths(csv_path)
    with _LOCK:
        prior_session = _read_state(state_path)
        rotated = False
        if prior_session is None and current.exists() and current.stat().st_size:
            # A pre-S3 file has no trustworthy session identity. Preserve it
            # separately rather than assigning its rows to today's session.
            legacy_name = "legacy-" + _digest(current)[:16]
            _archive_current(current, archive_dir, manifest, legacy_name)
        elif prior_session is not None and prior_session != session_date:
            _archive_current(current, archive_dir, manifest, prior_session)
            rotated = True
        if not current.exists():
            _write_header(current, columns)
        _write_state(state_path, session_date)
        with current.open("a", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(columns), extrasaction="ignore")
            writer.writerows(batch)
            handle.flush()
            os.fsync(handle.fileno())
    return {"rows": len(batch), "rotated": rotated, "session_date": session_date}
