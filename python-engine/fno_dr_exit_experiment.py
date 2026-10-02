"""Frozen, structure-level defined-risk exit experiment (S6).

Research-only: callers supply exact selected-leg identities and signed packet
bytes.  It neither reads a broker nor mutates the defined-risk paper book.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
import hashlib
import math
from typing import Any, Mapping, Sequence

from momentum_exit_study import ExitStudyError

BASELINE = "defined_risk_current_target_stop_flat_v1"
TRAIL = "defined_risk_target_hold_trail_v1"
MANIFEST_SCHEMA = "fno_dr_exit_experiment_manifest_v1"
REPORT_SCHEMA = "fno_dr_exit_experiment_report_v1"


@dataclass(frozen=True)
class DrObservation:
    observed_at: datetime
    gross_pnl: float
    exit_cost: float
    hard_flat: bool = False


@dataclass(frozen=True)
class DrEntry:
    entry_id: str
    source_ref: str
    source_packet: bytes
    entry_at: datetime
    kind: str
    max_profit: float
    max_loss: float
    entry_cost: float
    legs: tuple[dict[str, Any], ...]
    observations: tuple[DrObservation, ...]


def _valid(entry: DrEntry) -> None:
    if not entry.entry_id or not entry.kind or entry.entry_at.tzinfo is None:
        raise ExitStudyError("defined-risk entry identity and timezone-aware clock are required")
    if not isinstance(entry.source_packet, bytes) or not entry.source_packet:
        raise ExitStudyError("defined-risk source packet bytes are required")
    if entry.source_ref != "sha256:" + hashlib.sha256(entry.source_packet).hexdigest():
        raise ExitStudyError("defined-risk source packet identity mismatch")
    if not all(math.isfinite(float(value)) and float(value) > 0 for value in (entry.max_profit, entry.max_loss)):
        raise ExitStudyError("defined-risk max profit/loss must be finite positive")
    if not math.isfinite(float(entry.entry_cost)) or entry.entry_cost < 0 or not entry.legs:
        raise ExitStudyError("defined-risk costs/legs are invalid")
    identities = set()
    for leg in entry.legs:
        contract = leg.get("contract") if isinstance(leg, dict) else None
        if not isinstance(contract, dict): raise ExitStudyError("exact selected leg contract is required")
        try: identity = (str(contract["underlying"]), str(contract["expiry"]), int(contract["token"]), str(contract["tradingsymbol"]), int(contract["lot_size"]))
        except (KeyError, TypeError, ValueError) as exc: raise ExitStudyError("exact selected leg identity is invalid") from exc
        if not all(identity) or identity in identities: raise ExitStudyError("duplicate/invalid selected leg identity")
        identities.add(identity)


def simulate(entry: DrEntry, policy: str) -> dict[str, Any]:
    _valid(entry)
    if policy not in (BASELINE, TRAIL): raise ExitStudyError("unknown defined-risk candidate policy")
    target, stop = .5 * entry.max_profit, -.6 * entry.max_loss
    peak = -math.inf; held_target = False; previous = entry.entry_at
    for obs in entry.observations:
        if obs.observed_at.tzinfo is None or obs.observed_at <= previous or not math.isfinite(obs.gross_pnl) or obs.exit_cost < 0:
            return {"policy": policy, "status": "INSUFFICIENT_EVIDENCE", "reason": "invalid_structure_observation"}
        previous = obs.observed_at; peak = max(peak, obs.gross_pnl)
        reason = "hard_flat" if obs.hard_flat else "stop" if obs.gross_pnl <= stop else "target" if obs.gross_pnl >= target else None
        if policy == TRAIL and reason == "target": held_target = True; reason = None
        if policy == TRAIL and held_target and not obs.hard_flat and obs.gross_pnl <= max(target, peak - .5 * entry.max_profit): reason = "trail_giveback"
        if reason:
            costs = entry.entry_cost + obs.exit_cost; net = obs.gross_pnl - costs
            return {"policy": policy, "status": "CLOSED", "reason": reason, "exit_at": obs.observed_at.isoformat(),
                    "gross_pnl": round(obs.gross_pnl, 6), "costs": round(costs, 6), "net_pnl": round(net, 6),
                    "r_multiple": round(net / entry.max_loss, 8), "target_hold_activated": held_target}
    return {"policy": policy, "status": "INSUFFICIENT_EVIDENCE", "reason": "hard_flat_observation_missing"}


def freeze_manifest(*, experiment_id: str, frozen_at: datetime) -> dict[str, Any]:
    if not experiment_id or frozen_at.tzinfo is None: raise ExitStudyError("experiment id and freeze clock are required")
    source = hashlib.sha256(b"fno_dr_exit_experiment_v1|fno_dr_book_exact_legs").hexdigest()
    return {"schema": MANIFEST_SCHEMA, "experiment_id": experiment_id, "baseline_policy": BASELINE,
            "candidate_policy": TRAIL, "trail_giveback_fraction_of_max_profit": .5,
            "source_fingerprint": "sha256:" + source, "frozen_at": frozen_at.isoformat(),
            "holdout_rule": "only entries strictly after frozen_at are HOLDOUT"}


def build_report(entries: Sequence[DrEntry], manifest: Mapping[str, Any]) -> dict[str, Any]:
    if manifest.get("schema") != MANIFEST_SCHEMA or manifest.get("baseline_policy") != BASELINE or manifest.get("candidate_policy") != TRAIL:
        raise ExitStudyError("invalid defined-risk frozen manifest")
    frozen = datetime.fromisoformat(str(manifest["frozen_at"]).replace("Z", "+00:00"))
    pairs=[]
    for entry in entries:
        base, candidate = simulate(entry, BASELINE), simulate(entry, TRAIL)
        pairs.append({"entry_id": entry.entry_id, "kind": entry.kind, "sample": "HOLDOUT" if entry.entry_at > frozen else "DEVELOPMENT", "baseline": base, "candidate": candidate})
    return {"schema": REPORT_SCHEMA, "manifest": dict(manifest), "pairs": pairs, "qualification": "NOT_ASSESSED", "authorization_effect": "NONE",
            "warning": "Structure-level paper replay is not authority to alter defined-risk exits."}
