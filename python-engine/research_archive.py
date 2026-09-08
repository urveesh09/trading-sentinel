"""Immutable, non-trading market-data evidence archive.

The operational ``cache.db`` is a short-retention analytics store.  This
module deliberately writes *only* to a separate research directory so that
preserving evidence never changes the live advisory or trading database.
It labels every record by what was actually observed; LTP/OI snapshots are
not upgraded to quote/depth data.
"""
from __future__ import annotations

import csv
import gzip
import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

import structlog

logger = structlog.get_logger()
ARCHIVE_FORMAT = "sentinel-research-v1"
EVIDENCE_OPTION_LTP_OI = "OPTION_LTP_OI_SNAPSHOT"
EVIDENCE_OBSERVED_QUOTE = "OBSERVED_QUOTE_REPLAY"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: Optional[datetime] = None) -> str:
    return (value or utc_now()).astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _atomic_bytes(path: Path, contents: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".research-", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(contents)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _require_capacity(root: Path, reserve_bytes: int, required_bytes: int = 0) -> None:
    root.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(root).free < max(0, reserve_bytes) + max(0, required_bytes):
        raise OSError("research archive free-space reserve reached")


def _safe_component(value: str) -> str:
    return "".join(c if c.isalnum() or c in "._-" else "_" for c in value)[:120]


def _sqlite_readonly(path: str) -> sqlite3.Connection:
    # URI quoting avoids a path containing '#' or '?' changing the URI.
    return sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone() is not None


def _rows_as_dicts(cursor: sqlite3.Cursor) -> List[Dict[str, Any]]:
    fields = [description[0] for description in cursor.description or []]
    return [dict(zip(fields, row)) for row in cursor.fetchall()]


def _coverage(rows: Sequence[Mapping[str, Any]], timestamp_field: str = "snap_ts") -> Dict[str, Any]:
    stamps = sorted(str(row[timestamp_field]) for row in rows if row.get(timestamp_field) is not None)
    return {"row_count": len(rows), "first_timestamp": stamps[0] if stamps else None,
            "last_timestamp": stamps[-1] if stamps else None}


def export_operational_fno_evidence(
    source_db_path: str,
    archive_root: str,
    underlyings: Sequence[str] = ("NIFTY", "SENSEX"),
    *,
    exported_at: Optional[datetime] = None,
    source_commit: Optional[str] = None,
    cutoff_before: Optional[str] = None,
    reserved_free_bytes: int = 0,
) -> Dict[str, Any]:
    """Read a consistent snapshot from an operational SQLite DB and export it.

    The source is opened with SQLite ``mode=ro`` and a read transaction; no
    source DDL, checkpoint, vacuum, or retention action is performed.  The
    resulting JSONL files are atomically published with a checksummed manifest.
    Re-running makes a new immutable capture instead of mutating a prior one.
    """
    requested = sorted({name.strip().upper() for name in underlyings if name.strip()})
    if not requested:
        raise ValueError("at least one underlying is required")
    exported_at = exported_at or utc_now()
    stamp = exported_at.strftime("%Y%m%dT%H%M%SZ")
    root = Path(archive_root)
    capture = root / "operational-fno" / stamp
    if capture.exists():
        raise FileExistsError(f"immutable capture already exists: {capture}")

    conn = _sqlite_readonly(source_db_path)
    try:
        conn.execute("BEGIN")  # stable WAL-aware read snapshot, never a file copy
        schema_rows = _rows_as_dicts(conn.execute(
            "SELECT name, sql FROM sqlite_master WHERE type IN ('table','index','view') ORDER BY name"
        ))
        placeholders = ",".join("?" for _ in requested)
        missing_tables: List[str] = []
        chain_rows: List[Dict[str, Any]] = []
        fut_rows: List[Dict[str, Any]] = []
        if _table_exists(conn, "fno_chain_oi"):
            sql = f"SELECT rowid AS _archive_rowid,* FROM fno_chain_oi WHERE upper(underlying) IN ({placeholders})"
            params: List[Any] = list(requested)
            if cutoff_before:
                sql += " AND snap_ts<?"; params.append(cutoff_before)
            chain_rows = _rows_as_dicts(conn.execute(sql + " ORDER BY underlying,snap_ts,expiry,strike,opt_type", params))
        else:
            missing_tables.append("fno_chain_oi")
        if _table_exists(conn, "fno_fut_snap"):
            sql = f"SELECT rowid AS _archive_rowid,* FROM fno_fut_snap WHERE upper(underlying) IN ({placeholders})"
            params = list(requested)
            if cutoff_before:
                sql += " AND snap_ts<?"; params.append(cutoff_before)
            fut_rows = _rows_as_dicts(conn.execute(sql + " ORDER BY underlying,snap_ts", params))
        else:
            missing_tables.append("fno_fut_snap")
        conn.commit()
    finally:
        conn.close()

    files = {
        "fno_chain_oi.jsonl": b"".join(_canonical_json(row) + b"\n" for row in chain_rows),
        "fno_fut_snap.jsonl": b"".join(_canonical_json(row) + b"\n" for row in fut_rows),
        "source_schema.json": _canonical_json(schema_rows) + b"\n",
    }
    # Atomic publication can temporarily consume approximately one extra copy.
    _require_capacity(root, reserved_free_bytes, sum(len(value) for value in files.values()) * 2)
    file_manifest: Dict[str, Dict[str, Any]] = {}
    for filename, data in files.items():
        _atomic_bytes(capture / filename, data)
        file_manifest[filename] = {"sha256": _sha256_bytes(data), "bytes": len(data)}
    manifest = {
        "format": ARCHIVE_FORMAT,
        "kind": "operational_fno_export",
        "evidence_level": EVIDENCE_OPTION_LTP_OI,
        "exported_at_utc": _iso(exported_at),
        "source": {"db_path": str(Path(source_db_path).resolve()), "mode": "sqlite_readonly_snapshot",
                   "commit": source_commit},
        "requested_underlyings": requested,
        "cutoff_before": cutoff_before,
        "missing_tables": missing_tables,
        "coverage": {"fno_chain_oi": _coverage(chain_rows), "fno_fut_snap": _coverage(fut_rows)},
        "files": file_manifest,
        "limitations": ["Contains observed LTP/OI/volume analytics snapshots only.",
                        "Does not contain historical bid/ask prices, quantities, depth, or fill outcomes."],
    }
    _atomic_bytes(capture / "manifest.json", _canonical_json(manifest) + b"\n")
    return {"path": str(capture), **manifest}


def verify_export_manifest(capture_path: str) -> bool:
    """Check complete marker, every named file hash and row identity fields."""
    base = Path(capture_path)
    try:
        manifest = json.loads((base / "manifest.json").read_text(encoding="utf-8"))
        for filename, expected in manifest["files"].items():
            if _sha256_bytes((base / filename).read_bytes()) != expected["sha256"]:
                return False
        for filename in ("fno_chain_oi.jsonl", "fno_fut_snap.jsonl"):
            for line in (base / filename).read_bytes().splitlines():
                if "_archive_rowid" not in json.loads(line):
                    return False
        return True
    except (OSError, KeyError, TypeError, json.JSONDecodeError):
        return False


def verify_fno_export_for_cutoff(archive_root: str, cutoff_ist: str) -> bool:
    """True only if an immutable archive covers every pre-cutoff source row.

    This is intentionally conservative: a manifest with an empty archive or a
    capture that ends before the requested cutoff does not authorise deletion.
    """
    root = Path(archive_root) / "operational-fno"
    if not root.exists():
        return False
    for manifest_path in sorted(root.glob("*/manifest.json"), reverse=True):
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            final = manifest["coverage"]["fno_chain_oi"]["last_timestamp"]
            if final is not None and str(final) >= cutoff_ist:
                return True
        except (OSError, KeyError, TypeError, json.JSONDecodeError):
            continue
    return False


def archive_contract_master(
    archive_root: str, *, provider: str, segment: str, raw_csv: str,
    observed_at: Optional[datetime] = None,
    reserved_free_bytes: int = 0,
) -> Optional[Dict[str, Any]]:
    """Store a dated raw master and canonical contract records, immutably.

    Identity includes exchange plus full contract terms.  A raw token is never
    treated as a permanent identity, so token reuse and lot-size changes remain
    visible in the archive rather than silently overwriting one another.
    """
    if not raw_csv:
        return None
    observed_at = observed_at or utc_now()
    raw = raw_csv.encode("utf-8")
    digest = _sha256_bytes(raw)
    day = observed_at.strftime("%Y-%m-%d")
    base = Path(archive_root) / "contract-masters" / _safe_component(provider) / _safe_component(segment) / day / digest
    if (base / "manifest.json").exists():
        return json.loads((base / "manifest.json").read_text(encoding="utf-8"))
    records: List[Dict[str, Any]] = []
    for record in csv.DictReader(raw_csv.splitlines()):
        try:
            instrument_type = (record.get("instrument_type") or "").upper()
            if instrument_type not in {"CE", "PE", "FUT"}:
                continue
            expiry = (record.get("expiry") or "")[:10]
            if not expiry:
                continue
            records.append({
                "provider": provider, "exchange": (record.get("exchange") or segment).upper(),
                "segment": (record.get("segment") or segment).upper(),
                "underlying": (record.get("name") or "").upper(),
                "tradingsymbol": (record.get("tradingsymbol") or "").upper(),
                "instrument_token": str(record.get("instrument_token") or ""),
                "expiry": expiry, "strike": float(record.get("strike") or 0),
                "instrument_type": instrument_type, "lot_size": int(record.get("lot_size") or 0),
                "tick_size": float(record.get("tick_size") or 0),
            })
        except (TypeError, ValueError):
            continue
    records.sort(key=lambda item: (item["exchange"], item["underlying"], item["expiry"],
                                   item["strike"], item["instrument_type"], item["tradingsymbol"]))
    canonical = b"".join(_canonical_json(record) + b"\n" for record in records)
    _require_capacity(Path(archive_root), reserved_free_bytes, (len(raw) + len(canonical)) * 2)
    _atomic_bytes(base / "raw.csv", raw)
    _atomic_bytes(base / "contracts.jsonl", canonical)
    manifest = {"format": ARCHIVE_FORMAT, "kind": "contract_master", "provider": provider,
                "segment": segment, "observed_at_utc": _iso(observed_at), "raw_sha256": digest,
                "canonical_sha256": _sha256_bytes(canonical), "contract_count": len(records),
                "identity": "exchange+underlying+tradingsymbol+expiry+strike+instrument_type+lot_size+tick_size",
                "limitations": ["Token mappings are dated observations; instrument tokens may be reused."]}
    _atomic_bytes(base / "manifest.json", _canonical_json(manifest) + b"\n")
    return manifest


def archive_candidate_evidence(
    archive_root: str, *, advisory_id: str, candidate_payload: Mapping[str, Any],
    validation_reasons: Sequence[str], recorded_at: Optional[datetime] = None,
    reserved_free_bytes: int = 0,
) -> Dict[str, Any]:
    """Pin every evaluated advisory candidate, including rejected ones.

    The payload is supplied by the deterministic advisory validator and
    includes both legs' displayed bid/ask/size fields.  It is evidence of a
    displayed snapshot, not a claimed fill, and never changes delivery state.
    """
    recorded_at = recorded_at or utc_now()
    content = {
        "format": ARCHIVE_FORMAT, "kind": "evaluated_advisory_candidate",
        "advisory_id": advisory_id, "recorded_at_utc": _iso(recorded_at),
        "evidence_level": "LIVE_CURRENT_PREVIEW",
        "candidate": dict(candidate_payload),
        "validation_reasons": sorted(set(validation_reasons)),
        "delivery_or_order_action": "none",
        "limitations": ["Exact displayed quotes are pinned for audit only; no order/fill/partner position is observed."],
    }
    payload = _canonical_json(content) + b"\n"
    _require_capacity(Path(archive_root), reserved_free_bytes, len(payload) * 2)
    digest = _sha256_bytes(payload)
    destination = Path(archive_root) / "candidate-evidence" / recorded_at.strftime("%Y-%m-%d") / _safe_component(advisory_id) / digest
    _atomic_bytes(destination / "evidence.json", payload)
    return {"path": str(destination), "sha256": digest, "evidence_level": content["evidence_level"]}


class QuoteArchive:
    """Bounded append-only quote writer with crash recovery and finalisation."""
    def __init__(self, archive_root: str, *, max_queue: int = 2_000,
                 reserved_free_bytes: int = 1_073_741_824, session_max_bytes: int = 268_435_456):
        self.root = Path(archive_root)
        self.max_queue = max_queue
        self.reserved_free_bytes = reserved_free_bytes
        self.session_max_bytes = session_max_bytes
        self._sequence = 0
        self._dropped = 0
        self.writer_id = uuid.uuid4().hex
        self._recovered_paths: set[Path] = set()

    def _check_capacity(self) -> None:
        _require_capacity(self.root, self.reserved_free_bytes)

    def append(self, event: Mapping[str, Any]) -> bool:
        """Append a normalised observed packet; never fabricate a missing level."""
        self._check_capacity()
        received = str(event.get("received_at_utc") or _iso())
        day = received[:10]
        path = self.root / "quotes" / day / "quotes.jsonl.open"
        self._recover_open_tail(path)
        normal = dict(event)
        self._sequence += 1
        normal.setdefault("format", ARCHIVE_FORMAT)
        normal.setdefault("evidence_level", EVIDENCE_OBSERVED_QUOTE)
        normal.setdefault("received_at_utc", received)
        normal["writer_id"] = self.writer_id
        normal["writer_sequence"] = self._sequence
        contents = _canonical_json(normal) + b"\n"
        used = path.stat().st_size if path.exists() else 0
        if used + len(contents) > self.session_max_bytes:
            self._dropped += 1
            raise OSError("research session byte budget reached")
        # One writer is called from one scheduler job.  O_APPEND + fsync means
        # a process crash leaves at most an incomplete final line, recovered on
        # next finalisation rather than a false completed segment.
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "ab") as handle:
            handle.write(contents)
            handle.flush()
            os.fsync(handle.fileno())
        self._update_latest_observation(normal)
        return True

    def _update_latest_observation(self, event: Mapping[str, Any]) -> None:
        name = str(event.get("contract", {}).get("underlying", "")).upper()
        if not name:
            return
        path = self.root / "latest-observations.json"
        try:
            current = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        except (OSError, json.JSONDecodeError):
            current = {}
        current[name] = {"received_at_utc": event.get("received_at_utc"),
                         "provider_timestamp_utc": event.get("provider_timestamp_utc"),
                         "provider_timestamp_parse_error": event.get("provider_timestamp_parse_error"),
                         "depth_state": event.get("depth_state")}
        _atomic_bytes(path, _canonical_json(current) + b"\n")

    def _recover_open_tail(self, path: Path) -> None:
        """Quarantine a corrupt tail before a new writer appends valid JSON."""
        if path in self._recovered_paths or not path.exists():
            self._recovered_paths.add(path)
            return
        valid: List[bytes] = []
        bad = b""
        with open(path, "rb") as handle:
            for line in handle:
                try:
                    json.loads(line)
                    if bad:
                        bad += line
                    else:
                        valid.append(line)
                except (UnicodeDecodeError, json.JSONDecodeError):
                    bad += line
        if bad:
            recovery = path.with_name(f"{path.name}.corrupt-{uuid.uuid4().hex}")
            _atomic_bytes(recovery, bad)
            _atomic_bytes(path, b"".join(valid))
            logger.error("research_quote_tail_quarantined path=%s discarded_bytes=%d", str(path), len(bad))
        elif valid and not valid[-1].endswith(b"\n"):
            # JSON is complete but not newline-delimited.  Repair before the
            # next append so two valid documents cannot fuse into one bad row.
            _atomic_bytes(path, b"".join(valid) + b"\n")
            logger.warning("research_journal_missing_newline_repaired path=%s", str(path))
        self._recovered_paths.add(path)

    def record_collection_run(self, result: Mapping[str, Any], *, expected_interval_sec: int) -> Dict[str, Any]:
        """Durably journal successes, gaps and disabled/error outcomes."""
        self._check_capacity()
        now = utc_now()
        day = now.strftime("%Y-%m-%d")
        path = self.root / "collection-runs" / day / "runs.jsonl"
        self._recover_open_tail(path)
        prior_received = None
        if path.exists():
            try:
                for line in path.read_bytes().splitlines()[-1:]:
                    prior_received = json.loads(line).get("recorded_at_utc")
            except (OSError, ValueError, json.JSONDecodeError):
                prior_received = None
        record = {"format": ARCHIVE_FORMAT, "kind": "collection_run", "writer_id": self.writer_id,
                  "recorded_at_utc": _iso(now), "expected_interval_sec": expected_interval_sec,
                  "prior_recorded_at_utc": prior_received, "result": dict(result)}
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "ab") as handle:
            handle.write(_canonical_json(record) + b"\n")
            handle.flush(); os.fsync(handle.fileno())
        return record

    def finalize_day(self, day: str) -> Optional[Dict[str, Any]]:
        source = self.root / "quotes" / day / "quotes.jsonl.open"
        if not source.exists():
            return None
        valid: List[bytes] = []
        with open(source, "rb") as handle:
            for line in handle:
                try:
                    json.loads(line)
                    valid.append(line)
                except (UnicodeDecodeError, json.JSONDecodeError):
                    logger.warning("research_quote_partial_line_discarded day=%s", day)
        payload = b"".join(valid)
        digest = _sha256_bytes(payload)
        final = source.with_name(f"quotes-{digest[:16]}.jsonl.gz")
        if not final.exists():
            fd, temporary = tempfile.mkstemp(prefix=".research-", suffix=".gz", dir=str(source.parent))
            try:
                with os.fdopen(fd, "wb") as raw_handle:
                    with gzip.GzipFile(fileobj=raw_handle, mode="wb", mtime=0) as zipped:
                        zipped.write(payload)
                    raw_handle.flush(); os.fsync(raw_handle.fileno())
                os.replace(temporary, final)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
        manifest = {"format": ARCHIVE_FORMAT, "kind": "observed_quote_segment",
                    "day": day, "event_count": len(valid), "raw_sha256": digest,
                    "path": final.name, "finalized_at_utc": _iso(),
                    "dropped_events": self._dropped}
        _atomic_bytes(final.with_suffix(".manifest.json"), _canonical_json(manifest) + b"\n")
        source.unlink()
        return manifest

    def finalize_prior_days(self, current_day: str) -> List[Dict[str, Any]]:
        """Finish only old open segments; never seal the active session."""
        base = self.root / "quotes"
        if not base.exists():
            return []
        finalized: List[Dict[str, Any]] = []
        for directory in sorted(base.iterdir()):
            if directory.is_dir() and directory.name < current_day:
                item = self.finalize_day(directory.name)
                if item is not None:
                    finalized.append(item)
        return finalized


def readiness_view(archive_root: str, underlyings: Iterable[str] = ("NIFTY", "SENSEX")) -> Dict[str, Any]:
    """Per-index evidence readiness; archive presence is never qualification."""
    root = Path(archive_root)
    masters = list((root / "contract-masters").glob("**/manifest.json")) if root.exists() else []
    segments = list((root / "quotes").glob("**/*.manifest.json")) if root.exists() else []
    names = [name.upper() for name in underlyings]
    def latest_master(name: str) -> Optional[dict]:
        found = []
        for path in masters:
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                contracts = (path.parent / "contracts.jsonl").read_text(encoding="utf-8")
                if f'"underlying":"{name}"' in contracts:
                    found.append(data)
            except (OSError, json.JSONDecodeError):
                continue
        return max(found, key=lambda item: str(item.get("observed_at_utc", "")), default=None)
    latest_runs: List[dict] = []
    runs_dir = root / "collection-runs"
    if runs_dir.exists():
        for path in sorted(runs_dir.glob("**/runs.jsonl"))[-3:]:
            try:
                latest_runs.extend(json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line)
            except (OSError, json.JSONDecodeError):
                continue
    last_run = max(latest_runs, key=lambda item: str(item.get("recorded_at_utc", "")), default=None)
    per_index = {}
    try:
        latest_observations = json.loads((root / "latest-observations.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        latest_observations = {}
    for name in names:
        master = latest_master(name)
        gaps = [gap for run in latest_runs for gap in run.get("result", {}).get("gaps", []) if gap.get("underlying") == name]
        latest_quote = latest_observations.get(name)
        # Active segment is bounded to one session; inspect it without reading
        # historical partitions on the request path.
        for path in sorted((root / "quotes").glob("*/quotes.jsonl.open"))[-1:]:
            try:
                for line in path.read_text(encoding="utf-8").splitlines():
                    event = json.loads(line)
                    if event.get("contract", {}).get("underlying") == name and event.get("depth_state") == "USABLE":
                        latest_quote = event
            except (OSError, json.JSONDecodeError):
                pass
        per_index[name] = {
            "master": {"observed_at_utc": master.get("observed_at_utc"), "raw_sha256": master.get("raw_sha256"), "contract_count": master.get("contract_count")} if master else None,
            "recent_gap_count": len(gaps), "latest_gap": gaps[-1] if gaps else None,
            "last_collection_run_utc": max((r.get("recorded_at_utc") for r in latest_runs if name in r.get("result", {}).get("indices", {}) or any(g.get("underlying") == name for g in r.get("result", {}).get("gaps", []))), default=None),
            "last_valid_quote_utc": latest_quote.get("received_at_utc") if latest_quote else None,
            "provider_timestamp_utc": latest_quote.get("provider_timestamp_utc") if latest_quote else None,
            "quote_observation_status": "OBSERVED_USABLE" if latest_quote and latest_quote.get("depth_state") == "USABLE" else "NOT_YET_OBSERVED",
            "qualification": "NOT_EVALUATED_HERE",
        }
    usage = shutil.disk_usage(root) if root.exists() else None
    return {"archive_path": str(root), "archive_exists": root.exists(),
            "underlyings": names, "per_index": per_index,
            "master_snapshots": len(masters), "finalized_quote_segments": len(segments),
            "collection_runs": len(latest_runs), "latest_collection_run": last_run,
            "storage": {"bytes_free": usage.free, "bytes_total": usage.total} if usage else None,
            "evidence_levels": [EVIDENCE_OPTION_LTP_OI, EVIDENCE_OBSERVED_QUOTE],
            "advisory_independent": True,
            "limitations": ["Archive presence is not a strategy qualification or execution guarantee."]}
