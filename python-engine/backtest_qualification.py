"""Append-only prospective holdout protocol for Backtest Lab (P4).

Dates are not evidence of non-observation. A qualification is therefore only
created before its holdout begins, freezes exact policy/snapshot fingerprints,
and receives a new immutable evaluation event whenever it is run.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import time
import uuid


class QualificationError(ValueError):
    pass


def canonical_sha256(value: object) -> str:
    return "sha256:" + hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def _read(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise QualificationError(f"invalid qualification registry line {number}") from exc
        if not isinstance(row, dict):
            raise QualificationError(f"invalid qualification registry line {number}")
        rows.append(row)
    return rows


def _lock(path: Path) -> Path:
    lock = path.with_suffix(path.suffix + ".lock")
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise QualificationError(f"qualification registry is locked: {lock}") from exc
    os.close(fd)
    return lock


def _append(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = (json.dumps(row, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()
    fd = os.open(path, os.O_APPEND | os.O_CREAT | os.O_WRONLY)
    try:
        os.write(fd, encoded)
        os.fsync(fd)
    finally:
        os.close(fd)


def freeze(*, registry: str, strategy_id: str, development_window: tuple[str, str],
           holdout_window: tuple[str, str], snapshot_sha256: str, policy: dict,
           request_config: dict, now: datetime | None = None) -> dict:
    """Create a pre-holdout immutable record; never mutate registry history."""
    now = now or datetime.now(timezone.utc)
    dev_start, dev_end = map(date.fromisoformat, development_window)
    held_start, held_end = map(date.fromisoformat, holdout_window)
    if dev_start > dev_end or held_start > held_end or held_start <= dev_end:
        raise QualificationError("invalid, overlapping development/holdout windows")
    if held_start <= now.date():
        raise QualificationError("retroactive holdout freeze refused: holdout must begin strictly after registry creation date")
    path = Path(registry).resolve()
    lock = _lock(path)
    try:
        rows = _read(path)
        for row in rows:
            if row.get("event") == "FROZEN" and row.get("strategy_id") == strategy_id and row.get("holdout_window") == list(holdout_window):
                raise QualificationError("holdout window already frozen for this strategy; create a new future window")
        record = {
            "schema": "sentinel_holdout_registry_v1", "event": "FROZEN",
            "qualification_id": f"HQ_{uuid.uuid4().hex}", "created_at": now.isoformat(),
            "strategy_id": strategy_id, "development_window": list(development_window),
            "holdout_window": list(holdout_window), "snapshot_sha256": snapshot_sha256,
            "policy_sha256": canonical_sha256(policy), "request_config_sha256": canonical_sha256(request_config),
            "policy": policy, "request_config": request_config,
            "untouched_verified": False,
            "status": "PROSPECTIVELY_FROZEN",
            "reason": "Frozen before holdout start; registry records future evaluations but cannot prove no external observation.",
        }
        _append(path, record)
        return record
    finally:
        lock.unlink(missing_ok=True)


def frozen_record(registry: str, qualification_id: str) -> tuple[dict, list[dict]]:
    rows = _read(Path(registry).resolve())
    frozen = next((row for row in rows if row.get("event") == "FROZEN" and row.get("qualification_id") == qualification_id), None)
    if frozen is None:
        raise QualificationError("qualification id is not frozen in this registry")
    events = [row for row in rows if row.get("qualification_id") == qualification_id and row.get("event") == "EVALUATED"]
    return frozen, events


def validate_run(*, registry: str, qualification_id: str, strategy_id: str,
                 window: tuple[str, str], snapshot_sha256: str, policy: dict,
                 request_config: dict) -> dict:
    frozen, events = frozen_record(registry, qualification_id)
    if frozen.get("strategy_id") != strategy_id or frozen.get("holdout_window") != list(window):
        raise QualificationError("qualification strategy/window differs from its frozen holdout")
    if frozen.get("snapshot_sha256") != snapshot_sha256:
        raise QualificationError("qualification snapshot differs from its frozen evidence")
    if frozen.get("policy_sha256") != canonical_sha256(policy):
        raise QualificationError("qualification policy changed after freeze")
    if frozen.get("request_config_sha256") != canonical_sha256(request_config):
        raise QualificationError("qualification request configuration changed after freeze")
    return {"qualification_id": qualification_id, "frozen_at": frozen["created_at"],
            "prior_evaluations": len(events), "status": "FIRST_EVALUATION" if not events else "REUSED_HOLDOUT",
            "untouched_verified": False}


def record_evaluation(*, registry: str, qualification_id: str, report_sha256: str,
                      now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    path = Path(registry).resolve()
    lock = _lock(path)
    try:
        frozen, events = frozen_record(str(path), qualification_id)
        row = {"schema": "sentinel_holdout_registry_v1", "event": "EVALUATED",
               "qualification_id": qualification_id, "at": now.isoformat(),
               "report_sha256": report_sha256, "ordinal": len(events) + 1,
               "status": "EVALUATED" if not events else "EVALUATED_REUSED"}
        _append(path, row)
        return row
    finally:
        lock.unlink(missing_ok=True)
