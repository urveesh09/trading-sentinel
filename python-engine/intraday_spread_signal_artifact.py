"""Immutable, causal signal artifacts for intraday-spread research.

Quote archives are observations, not a strategy.  This module records the
deterministic evaluator output that selected a quote decision, binds it to the
policy/config/source evidence and rejects hand-written score dictionaries.
It is intentionally research-only and has no broker or dispatch imports.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from intraday_spread_replay import ReplayInputError


FORMAT = "intraday_spread_signal_artifact_v1"
EVALUATOR_ORB_THRESHOLD_V1 = "orb_threshold_v1"


def _sha(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()


def _digest(value: object, field: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value.lower()):
        raise ReplayInputError(f"{field} must be a SHA-256 hex digest")
    return value.lower()


def _stamp(value: object, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ReplayInputError(f"{field} must be an ISO timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ReplayInputError(f"{field} must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _orb_input(value: object, *, session: str, cutoff: datetime) -> tuple[dict[str, Any], float, datetime, datetime]:
    """Normalize causal inputs for the fixed, reproducible ORB threshold rule."""
    if not isinstance(value, Mapping):
        raise ReplayInputError("signal evaluator input is missing")
    direction = str(value.get("direction", "")).upper()
    if direction not in {"LONG", "SHORT"}:
        raise ReplayInputError("signal evaluator direction is invalid")
    try:
        close, trigger = float(value.get("close")), float(value.get("trigger"))
    except (TypeError, ValueError) as exc:
        raise ReplayInputError("signal evaluator close/trigger is invalid") from exc
    if not math.isfinite(close) or not math.isfinite(trigger) or close <= 0 or trigger <= 0:
        raise ReplayInputError("signal evaluator close/trigger is non-finite")
    packets = value.get("source_packets")
    if not isinstance(packets, list) or not packets:
        raise ReplayInputError("signal evaluator requires causal source packets")
    receipts: list[datetime] = []
    normalized_packets: list[dict[str, str]] = []
    packet_ids: set[str] = set()
    for packet in packets:
        if not isinstance(packet, Mapping):
            raise ReplayInputError("signal evaluator source packet is invalid")
        receipt = _stamp(packet.get("received_at"), "signal.evaluator_input.source_packet.received_at")
        if receipt.date().isoformat() != session or receipt > cutoff:
            raise ReplayInputError("signal evaluator source packet is future or cross-session")
        packet_id = packet.get("packet_id")
        if not isinstance(packet_id, str) or not packet_id:
            raise ReplayInputError("signal evaluator source packet id is invalid")
        if packet_id in packet_ids:
            raise ReplayInputError("signal evaluator source packet id is duplicate")
        packet_ids.add(packet_id)
        receipts.append(receipt)
        normalized_packets.append({"packet_id": packet_id, "received_at": receipt.isoformat()})
    normalized = {"direction": direction, "close": close, "trigger": trigger,
                  "source_packets": sorted(normalized_packets, key=lambda row: (row["received_at"], row["packet_id"]))}
    score = 1.0 if (direction == "LONG" and close >= trigger) or (direction == "SHORT" and close <= trigger) else 0.0
    return normalized, score, min(receipts), max(receipts)


def _canonical_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and normalize the immutable content before hashing it."""
    if not isinstance(payload, Mapping) or payload.get("format") != FORMAT:
        raise ReplayInputError("signal artifact format is invalid")
    normalized: dict[str, Any] = {"format": FORMAT}
    for field in ("evaluator_id", "policy_id", "underlying", "session_date"):
        value = payload.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ReplayInputError(f"signal artifact {field} is required")
        normalized[field] = value.strip().upper() if field == "underlying" else value.strip()
    if normalized["underlying"] not in {"NIFTY", "SENSEX"}:
        raise ReplayInputError("signal artifact underlying is unsupported")
    if normalized["evaluator_id"] != EVALUATOR_ORB_THRESHOLD_V1:
        raise ReplayInputError("signal artifact evaluator is not registered for reproducibility")
    try:
        date.fromisoformat(normalized["session_date"])
    except ValueError as exc:
        raise ReplayInputError("signal artifact session_date is invalid") from exc
    for field in ("evaluator_sha256", "policy_sha256", "config_sha256"):
        normalized[field] = _digest(payload.get(field), field)
    manifests = payload.get("source_manifests")
    if not isinstance(manifests, list) or not manifests:
        raise ReplayInputError("signal artifact requires source manifests")
    normalized_manifests: list[dict[str, str]] = []
    for item in manifests:
        if not isinstance(item, Mapping) or not isinstance(item.get("reference"), str) or not item["reference"].strip():
            raise ReplayInputError("signal artifact source manifest reference is invalid")
        normalized_manifests.append({"reference": item["reference"].strip(), "sha256": _digest(item.get("sha256"), "source_manifest.sha256")})
    normalized["source_manifests"] = sorted(normalized_manifests, key=lambda item: (item["reference"], item["sha256"]))
    signals = payload.get("signals")
    if not isinstance(signals, list):
        raise ReplayInputError("signal artifact signals must be a list")
    normalized_signals: list[dict[str, Any]] = []
    seen: set[str] = set()
    session = normalized["session_date"]
    for item in signals:
        if not isinstance(item, Mapping):
            raise ReplayInputError("signal artifact signal is invalid")
        decision_id = item.get("decision_id")
        if not isinstance(decision_id, str) or not decision_id or decision_id in seen:
            raise ReplayInputError("signal artifact decision_id is missing or duplicate")
        seen.add(decision_id)
        received = _stamp(item.get("received_at"), "signal.received_at")
        cutoff = _stamp(item.get("decision_cutoff"), "signal.decision_cutoff")
        if received.date().isoformat() != session or cutoff.date().isoformat() != session or cutoff > received:
            raise ReplayInputError("signal artifact contains non-causal or cross-session source data")
        evaluator_input, recomputed_score, source_start, source_end = _orb_input(
            item.get("evaluator_input"), session=session, cutoff=cutoff)
        try:
            score = float(item.get("score"))
        except (TypeError, ValueError) as exc:
            raise ReplayInputError("signal artifact score is invalid") from exc
        if not math.isfinite(score) or score != recomputed_score:
            raise ReplayInputError("signal artifact score does not reproduce from evaluator input")
        normalized_signals.append({
            "decision_id": decision_id, "received_at": received.isoformat(),
            "decision_cutoff": cutoff.isoformat(), "score": score,
            "source_receipt_bounds": {"start": source_start.isoformat(), "end": source_end.isoformat()},
            "evaluator_input": evaluator_input,
        })
    normalized["signals"] = sorted(normalized_signals, key=lambda item: (item["received_at"], item["decision_id"]))
    return normalized


def write_signal_artifact(path: str | Path, payload: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and atomically write deterministic artifact content.

    The artifact digest covers content only.  No creation timestamp is added,
    so repeat generation from equivalent causal input has identical identity.
    """
    canonical = _canonical_payload(payload)
    result = {**canonical, "artifact_sha256": _sha(canonical)}
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(json.dumps(result, sort_keys=True, separators=(",", ":")), encoding="utf-8")
    os.replace(temporary, target)
    return result


def generate_orb_threshold_artifact(
    path: str | Path, *, underlying: str, policy_id: str, evaluator_sha256: str,
    policy_sha256: str, config_sha256: str, session_date: str,
    source_manifests: list[Mapping[str, Any]], decisions: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    """Generate, rather than accept, scores for the registered ORB rule.

    Each decision supplies only raw causal inputs and its decision clock. The
    score and source bounds are derived here. Packets after a decision cutoff
    are rejected and cannot alter an earlier decision on a later replay.
    """
    signals = []
    for decision in decisions:
        if not isinstance(decision, Mapping):
            raise ReplayInputError("signal decision is invalid")
        cutoff = _stamp(decision.get("decision_cutoff"), "decision_cutoff")
        received = _stamp(decision.get("received_at"), "received_at")
        canonical_input, score, _start, _end = _orb_input(
            decision.get("evaluator_input"), session=session_date, cutoff=cutoff)
        signals.append({"decision_id": decision.get("decision_id"), "received_at": received.isoformat(),
                        "decision_cutoff": cutoff.isoformat(), "score": score,
                        "evaluator_input": canonical_input})
    return write_signal_artifact(path, {"format": FORMAT, "evaluator_id": EVALUATOR_ORB_THRESHOLD_V1,
        "evaluator_sha256": evaluator_sha256, "policy_id": policy_id, "policy_sha256": policy_sha256,
        "config_sha256": config_sha256, "underlying": underlying, "session_date": session_date,
        "source_manifests": source_manifests, "signals": signals})


def load_signal_artifact(path: str | Path, *, underlying: str | None = None,
                         policy_id: str | None = None, session_date: str | None = None,
                         source_root: str | Path | None = None) -> dict[str, Any]:
    """Load only an untampered artifact compatible with the requested replay."""
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, TypeError, json.JSONDecodeError) as exc:
        raise ReplayInputError("signal artifact is unreadable") from exc
    if not isinstance(raw, Mapping):
        raise ReplayInputError("signal artifact root is invalid")
    claimed = _digest(raw.get("artifact_sha256"), "artifact_sha256")
    canonical = _canonical_payload({key: value for key, value in raw.items() if key != "artifact_sha256"})
    if _sha(canonical) != claimed:
        raise ReplayInputError("signal artifact digest does not match contents")
    for field, expected in (("underlying", underlying), ("policy_id", policy_id), ("session_date", session_date)):
        if expected is not None and canonical[field] != expected:
            raise ReplayInputError(f"signal artifact {field} does not match replay")
    if source_root is not None:
        root = Path(source_root).resolve()
        for manifest in canonical["source_manifests"]:
            candidate = (root / manifest["reference"]).resolve()
            if root not in candidate.parents or not candidate.is_file():
                raise ReplayInputError("signal artifact source manifest is missing")
            try:
                actual = hashlib.sha256(candidate.read_bytes()).hexdigest()
            except OSError as exc:
                raise ReplayInputError("signal artifact source manifest is unreadable") from exc
            if actual != manifest["sha256"]:
                raise ReplayInputError("signal artifact source manifest digest does not match")
    return {**canonical, "artifact_sha256": claimed}


def artifact_scores_by_receipt(artifact: Mapping[str, Any]) -> dict[str, float]:
    """Map exact archive receipt packets to reproducible evaluator scores."""
    canonical = _canonical_payload({key: value for key, value in artifact.items() if key != "artifact_sha256"})
    return {item["received_at"]: item["score"] for item in canonical["signals"]}
