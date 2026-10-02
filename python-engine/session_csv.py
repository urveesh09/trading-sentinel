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


def _append_manifest(path: Path, *, session_date: str, archive: Path,
                     recovered: bool = False) -> None:
    record = {
        "archive": archive.name,
        "bytes": archive.stat().st_size,
        "session_date": session_date,
        "sha256": _digest(archive),
    }
    if recovered:
        record["recovered_after_interrupted_rotation"] = True
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = (json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    with path.open("ab") as handle:
        # A crash mid-append can leave a torn final line without a newline.
        # Terminate it first so this record stays independently parseable;
        # the torn bytes are kept (append-only) and skipped by readers.
        if handle.tell() > 0:
            with path.open("rb") as reader:
                reader.seek(-1, os.SEEK_END)
                if reader.read(1) != b"\n":
                    handle.write(b"\n")
        handle.write(encoded)
        handle.flush()
        os.fsync(handle.fileno())


def _manifest_archives(path: Path) -> set[str]:
    names: set[str] = set()
    if not path.exists():
        return names
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue  # torn line from an interrupted append
        if isinstance(record, dict) and isinstance(record.get("archive"), str):
            names.add(record["archive"])
    return names


def _reconcile_manifest(archive_dir: Path, manifest: Path) -> None:
    """Record any archived CSV whose manifest append was interrupted.

    ``os.replace`` into the archive happens before the manifest append, so a
    crash between them leaves retained bytes without a record.  This is
    idempotent and only appends; it never rewrites or deletes evidence.
    """
    if not archive_dir.is_dir():
        return
    recorded = _manifest_archives(manifest)
    for archive in sorted(archive_dir.glob("*.csv")):
        if archive.name not in recorded:
            _append_manifest(manifest, session_date=archive.stem, archive=archive, recovered=True)


def _is_header_only(path: Path, columns: Sequence[str]) -> bool:
    """True when the file holds exactly the header for ``columns`` (no evidence)."""
    import io
    buffer = io.StringIO(newline="")
    csv.DictWriter(buffer, fieldnames=list(columns)).writeheader()
    try:
        return path.read_bytes() == buffer.getvalue().encode("utf-8")
    except OSError:
        return False


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
        if prior_session != session_date or not current.exists():
            # Rotation paths only: repair a manifest append interrupted by a
            # crash after the archive move (cheap; the archive is tiny).
            _reconcile_manifest(archive_dir, manifest)
        if prior_session != session_date and current.exists() and _is_header_only(current, columns):
            # A header written for a session whose state was never recorded
            # (crash between the two) contains no evidence.  Archiving it under
            # the prior session would collide with that session's real archive.
            current.unlink()
        if prior_session is None and current.exists() and current.stat().st_size:
            # A pre-S3 file has no trustworthy session identity. Preserve it
            # separately rather than assigning its rows to today's session.
            legacy_name = "legacy-" + _digest(current)[:16]
            _archive_current(current, archive_dir, manifest, legacy_name)
        elif prior_session is not None and prior_session != session_date:
            _archive_current(current, archive_dir, manifest, prior_session)
            rotated = True
        # Record the new session before creating its header: a crash between
        # the two then resumes this session instead of mislabelling the file.
        if prior_session != session_date:
            _write_state(state_path, session_date)
        if not current.exists():
            _write_header(current, columns)
        with current.open("a", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(columns), extrasaction="ignore")
            writer.writerows(batch)
            handle.flush()
            os.fsync(handle.fileno())
    return {"rows": len(batch), "rotated": rotated, "session_date": session_date}
