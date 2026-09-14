"""Predeclared, human-reviewed qualification package assembly.

The package binds a frozen full-policy manifest to chronological held-out
outcomes.  It never writes the delivery qualification registry and therefore
cannot turn a favorable diagnostic into advice authority.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, asdict
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping
from zoneinfo import ZoneInfo


def _sha(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


@dataclass(frozen=True)
class QualificationCriteria:
    policy_sha256: str
    min_covered_sessions: int
    min_closed_outcomes: int
    max_unresolved_outcomes: int
    max_drawdown_rs: float
    stressed_fee_multiplier: float
    stressed_slippage_bps: float

    def validate(self) -> None:
        if len(self.policy_sha256) != 64 or any(c not in "0123456789abcdef" for c in self.policy_sha256.lower()):
            raise ValueError("criteria requires a frozen policy digest")
        if (any(type(value) is not int for value in (self.min_covered_sessions, self.min_closed_outcomes, self.max_unresolved_outcomes))
                or self.min_covered_sessions < 1 or self.min_closed_outcomes < 1 or self.max_unresolved_outcomes < 0):
            raise ValueError("qualification sample criteria are invalid")
        if (any(isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)
                for value in (self.max_drawdown_rs, self.stressed_fee_multiplier, self.stressed_slippage_bps))
                or self.max_drawdown_rs >= 0
                or self.stressed_fee_multiplier < 1 or self.stressed_slippage_bps < 0):
            raise ValueError("qualification risk/cost criteria are invalid")


def freeze_qualification_criteria(*, criteria: QualificationCriteria, underlying: str,
                                  training_sessions, holdout_sessions, declared_coverage,
                                  frozen_at: datetime) -> dict[str, Any]:
    """Create the immutable review contract before any declared holdout day."""
    criteria.validate()
    training, holdout = sorted(set(training_sessions)), sorted(set(holdout_sessions))
    if underlying not in {"NIFTY", "SENSEX"} or not training or not holdout or set(training) & set(holdout):
        raise ValueError("criteria manifest requires one supported index and disjoint sessions")
    try:
        training_days = [date.fromisoformat(day) for day in training]
        holdout_days = [date.fromisoformat(day) for day in holdout]
    except (TypeError, ValueError) as exc:
        raise ValueError("criteria manifest sessions must be ISO dates") from exc
    if max(training_days) >= min(holdout_days):
        raise ValueError("criteria training sessions must precede holdout sessions")
    if frozen_at.tzinfo is None or frozen_at.utcoffset() is None:
        raise ValueError("criteria frozen_at must be timezone-aware")
    if frozen_at.astimezone(ZoneInfo("Asia/Kolkata")).date() >= min(holdout_days):
        raise ValueError("criteria must be frozen before the first holdout session")
    coverage = sorted(set(tuple(item) for item in declared_coverage))
    expected = {(underlying, criteria.policy_sha256, day) for day in holdout}
    if set(coverage) != expected:
        raise ValueError("criteria declared coverage must exactly match holdout sessions and policy")
    body = {"format": "partner_qualification_criteria_v1", "underlying": underlying,
            "policy_sha256": criteria.policy_sha256, "criteria": asdict(criteria),
            "training_sessions": training, "holdout_sessions": holdout,
            "declared_coverage": [{"underlying": item[0], "policy_id": item[1], "session_date": item[2]}
                                  for item in coverage],
            "frozen_at": frozen_at.astimezone(timezone.utc).isoformat()}
    return {**body, "criteria_manifest_sha256": _sha(body)}


def write_qualification_criteria_manifest(path, manifest: Mapping[str, Any]) -> None:
    """Create immutable predeclared criteria; identical retries are idempotent."""
    import os
    import tempfile
    from pathlib import Path
    body = {key: value for key, value in manifest.items() if key != "criteria_manifest_sha256"}
    if _sha(body) != manifest.get("criteria_manifest_sha256"):
        raise ValueError("criteria manifest fingerprint mismatch")
    encoded = json.dumps(dict(manifest), sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    target = Path(path); target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".criteria-", dir=target.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(encoded); stream.flush(); os.fsync(stream.fileno())
        try:
            os.link(temporary, target)
        except FileExistsError:
            if target.read_bytes() != encoded:
                raise ValueError("criteria manifest destination already contains different evidence")
    finally:
        os.unlink(temporary)


def build_qualification_review_package(*, policy_manifest: Mapping[str, Any], criteria: QualificationCriteria,
                                       heldout_report: Mapping[str, Any], readiness: Mapping[str, Any],
                                       criteria_manifest: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Build a per-index review package with visible non-qualification states."""
    criteria.validate()
    claimed = policy_manifest.get("manifest_sha256")
    if policy_manifest.get("policy_sha256") != criteria.policy_sha256:
        raise ValueError("criteria does not match frozen policy configuration")
    if policy_manifest.get("evaluator") != "partner_manual_intraday_full_policy_v1":
        raise ValueError("only the complete deployed-policy manifest may be reviewed")
    if _sha({key: value for key, value in policy_manifest.items() if key != "manifest_sha256"}) != claimed:
        raise ValueError("full-policy manifest fingerprint mismatch")
    if heldout_report.get("automatic_qualification") is not False:
        raise ValueError("heldout report must not claim automatic qualification")
    if _sha({key: value for key, value in heldout_report.items()
             if key not in {"evidence_sha256", "review_state"}}) != heldout_report.get("evidence_sha256"):
        raise ValueError("heldout report fingerprint mismatch")
    groups = heldout_report.get("groups")
    if not isinstance(groups, list):
        raise ValueError("heldout report groups are required")
    criteria_predeclared = False
    if criteria_manifest is not None:
        criteria_body = {key: value for key, value in criteria_manifest.items()
                         if key != "criteria_manifest_sha256"}
        expected_coverage = heldout_report.get("declared_coverage")
        try:
            reconstructed = freeze_qualification_criteria(criteria=criteria,
                underlying=str(criteria_manifest.get("underlying")),
                training_sessions=criteria_manifest.get("training_sessions", ()),
                holdout_sessions=criteria_manifest.get("holdout_sessions", ()),
                declared_coverage=[(item["underlying"], item["policy_id"], item["session_date"])
                    for item in criteria_manifest.get("declared_coverage", ())],
                frozen_at=datetime.fromisoformat(str(criteria_manifest.get("frozen_at")).replace("Z", "+00:00")))
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("predeclared qualification criteria are malformed") from exc
        if (dict(reconstructed) != dict(criteria_manifest)
                or _sha(criteria_body) != criteria_manifest.get("criteria_manifest_sha256")
                or criteria_manifest.get("format") != "partner_qualification_criteria_v1"
                or criteria_manifest.get("underlying") != policy_manifest.get("underlying")
                or criteria_manifest.get("policy_sha256") != criteria.policy_sha256
                or criteria_manifest.get("criteria") != asdict(criteria)
                or criteria_manifest.get("training_sessions") != heldout_report.get("training_sessions")
                or criteria_manifest.get("holdout_sessions") != heldout_report.get("holdout_sessions")
                or criteria_manifest.get("declared_coverage") != expected_coverage
                or heldout_report.get("review_criteria_sha256") != criteria_manifest.get("criteria_manifest_sha256")):
            raise ValueError("predeclared qualification criteria do not match heldout evidence")
        criteria_predeclared = True
    per_index = []
    seen_groups = set()
    for group in groups:
        if not isinstance(group, Mapping) or group.get("underlying") not in {"NIFTY", "SENSEX"}:
            raise ValueError("review package contains an unsupported index group")
        if group["underlying"] != policy_manifest.get("underlying"):
            raise ValueError("review index does not match frozen policy")
        identity = (group["underlying"], group.get("policy_id"))
        if not isinstance(identity[1], str) or not identity[1].strip() or identity in seen_groups:
            raise ValueError("review groups must have unique policy identities")
        if identity[1] != policy_manifest.get("policy_sha256"):
            raise ValueError("heldout policy does not match frozen full-policy configuration")
        seen_groups.add(identity)
        if any(type(group.get(key, 0)) is not int or group.get(key, 0) < 0
               for key in ("closed", "no_fill", "unresolved", "unavailable")):
            raise ValueError("review outcome counts must be nonnegative integers")
        coverage = group.get("coverage")
        if not isinstance(coverage, Mapping):
            raise ValueError("review coverage must be a mapping")
        covered = sum(value == "OBSERVED" for value in coverage.values())
        closed, unresolved = int(group.get("closed", 0)), int(group.get("unresolved", 0))
        net = float(group.get("net_pnl_rs", 0.0))
        blockers = []
        if not criteria_predeclared:
            blockers.append("predeclared_review_criteria_missing")
        if heldout_report.get("evidence_contract") != "VERIFIED_FULL_POLICY_REPORTS":
            blockers.append("verified_full_policy_outcomes_missing")
        ordered = group.get("ordered_outcomes")
        drawdown = group.get("max_sequential_drawdown_rs")
        if (not isinstance(ordered, list)
                or len(ordered) != closed + unresolved + int(group.get("no_fill", 0))
                or isinstance(drawdown, bool) or not isinstance(drawdown, (int, float))
                or not math.isfinite(float(drawdown)) or float(drawdown) > 0):
            drawdown_state = "REQUIRES_ORDERED_OUTCOMES"
            blockers.append("ordered_drawdown_evidence_missing")
            drawdown = None
        else:
            drawdown = float(drawdown)
            drawdown_state = "VERIFIED"
            if any(not isinstance(item, Mapping) for item in ordered):
                raise ValueError("heldout ordered outcomes are malformed")
            opportunity_ids = [item.get("opportunity_id") for item in ordered]
            evidence_ids = [item.get("evidence_sha256") for item in ordered]
            if (any(not isinstance(item, str) or not item for item in opportunity_ids)
                    or len(set(opportunity_ids)) != len(opportunity_ids)
                    or any(not isinstance(item, str) or len(item) != 64 for item in evidence_ids)
                    or len(set(evidence_ids)) != len(evidence_ids)):
                raise ValueError("heldout outcome identities must be unique and complete")
            state_counts = {state: sum(item.get("state") == state for item in ordered)
                            for state in ("CLOSED", "NO_FILL", "UNRESOLVED")}
            try:
                entries = [datetime.fromisoformat(str(item.get("entry_at")).replace("Z", "+00:00"))
                           for item in ordered]
                exits = [datetime.fromisoformat(str(item.get("exit_at")).replace("Z", "+00:00"))
                         if item.get("exit_at") else None for item in ordered]
                if (any(clock.tzinfo is None or clock.utcoffset() is None for clock in entries)
                        or any(clock is not None and (clock.tzinfo is None or clock.utcoffset() is None)
                               for clock in exits)
                        or any(exit_clock is not None and exit_clock < entry
                               for entry, exit_clock in zip(entries, exits))
                        or any(item.get("state") == "CLOSED" and exit_clock is None
                               for item, exit_clock in zip(ordered, exits))):
                    raise ValueError
                closed_pnls = [float(item["net_pnl_rs"]) for item in ordered if item.get("state") == "CLOSED"]
                running = peak = recomputed_drawdown = 0.0
                for pnl in closed_pnls:
                    if not math.isfinite(pnl):
                        raise ValueError
                    running += pnl; peak = max(peak, running)
                    recomputed_drawdown = min(recomputed_drawdown, running - peak)
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError("heldout ordered economics are malformed") from exc
            order_keys = [((exit_clock.timestamp() if item.get("state") == "CLOSED" else float("inf")),
                           entry.timestamp(), str(item.get("opportunity_id")))
                          for item, entry, exit_clock in zip(ordered, entries, exits)]
            if (order_keys != sorted(order_keys) or state_counts["CLOSED"] != closed
                    or state_counts["NO_FILL"] != int(group.get("no_fill", 0))
                    or state_counts["UNRESOLVED"] != unresolved
                    or round(sum(closed_pnls), 4) != round(net, 4)
                    or round(recomputed_drawdown, 4) != round(drawdown, 4)):
                raise ValueError("heldout ordered economics do not match aggregate")
            if drawdown < criteria.max_drawdown_rs:
                blockers.append("maximum_drawdown_exceeds_limit")

        sensitivity = group.get("cost_sensitivity")
        sensitivity_rows = [item for item in sensitivity if isinstance(item, Mapping)] \
            if isinstance(sensitivity, list) else []
        stress_ids = [str(item.get("opportunity_id")) for item in sensitivity_rows]
        stress_rows = {identity: item for identity, item in zip(stress_ids, sensitivity_rows)}
        stressed_pnls = []
        stress_state = "VERIFIED"
        expected_ids = {str(item.get("opportunity_id")) for item in ordered} if isinstance(ordered, list) else set()
        if (not isinstance(ordered, list) or len(stress_ids) != len(set(stress_ids))
                or set(stress_ids) != expected_ids):
            stress_state = "MISSING"
            blockers.append("cost_stress_evidence_missing")
        else:
            for outcome in ordered:
                wrapper = stress_rows.get(str(outcome.get("opportunity_id")))
                artifact = wrapper.get("artifact") if wrapper else None
                if not isinstance(artifact, Mapping):
                    stress_state = "FAILED"; blockers.append("cost_stress_artifact_malformed"); break
                artifact_body = {key: value for key, value in artifact.items() if key != "evidence_sha256"}
                if (_sha(artifact_body) != artifact.get("evidence_sha256")
                        or artifact.get("format") != "intraday_spread_cost_sensitivity_v1"
                        or artifact.get("underlying") != group["underlying"]
                        or artifact.get("policy_id") != group.get("policy_id")
                        or artifact.get("can_qualify") is not False or artifact.get("can_place_orders") is not False
                        or not isinstance(wrapper.get("source_report_sha256"), str)
                        or len(wrapper.get("source_report_sha256")) != 64
                        or not isinstance(wrapper.get("source_manifest_sha256"), str)
                        or len(wrapper.get("source_manifest_sha256")) != 64):
                    stress_state = "FAILED"; blockers.append("cost_stress_artifact_scope_or_fingerprint_invalid"); break
                scenarios = artifact.get("scenarios")
                try:
                    required_fee = Decimal(str(criteria.stressed_fee_multiplier))
                    required_slippage = Decimal(str(criteria.stressed_slippage_bps))
                    matches = [row for row in scenarios if isinstance(row, Mapping)
                        and Decimal(str(row.get("fee_multiplier"))) == required_fee
                        and Decimal(str(row.get("additional_slippage_bps"))) == required_slippage] \
                        if isinstance(scenarios, list) else []
                except (InvalidOperation, ValueError):
                    matches = []
                if not matches:
                    stress_state = "MISSING"
                    blockers.append("declared_cost_stress_scenario_missing")
                    break
                if len(matches) != 1:
                    stress_state = "FAILED"
                    blockers.append("declared_cost_stress_scenario_ambiguous")
                    break
                match = matches[0]
                if match.get("state") != outcome.get("state"):
                    stress_state = "FAILED"
                    blockers.append("stressed_outcome_state_conflict")
                    break
                if outcome.get("state") == "CLOSED":
                    pnl = match.get("net_pnl_rs")
                    if (match.get("state") != "CLOSED" or isinstance(pnl, bool)
                            or not isinstance(pnl, (int, float)) or not math.isfinite(float(pnl))):
                        stress_state = "FAILED"
                        blockers.append("stressed_closed_outcome_not_executable")
                        break
                    stressed_pnls.append(float(pnl))
                elif match.get("net_pnl_rs") is not None:
                    stress_state = "FAILED"
                    blockers.append("stressed_nonclosed_outcome_has_pnl")
                    break
        stressed_running = stressed_peak = stressed_drawdown = 0.0
        for pnl in stressed_pnls:
            stressed_running += pnl
            stressed_peak = max(stressed_peak, stressed_running)
            stressed_drawdown = min(stressed_drawdown, stressed_running - stressed_peak)
        if stress_state == "VERIFIED" and stressed_drawdown < criteria.max_drawdown_rs:
            blockers.append("stressed_maximum_drawdown_exceeds_limit")
        if covered < criteria.min_covered_sessions:
            blockers.append("heldout_session_coverage_insufficient")
        if closed < criteria.min_closed_outcomes:
            blockers.append("closed_outcome_sample_insufficient")
        if unresolved > criteria.max_unresolved_outcomes:
            blockers.append("unresolved_outcomes_exceed_limit")
        if group.get("unavailable", 0):
            blockers.append("declared_holdout_coverage_unavailable")
        if not math.isfinite(net):
            blockers.append("nonfinite_net_outcome")
        per_index.append({"underlying": group["underlying"], "policy_id": group.get("policy_id"),
                          "covered_sessions": covered, "closed_outcomes": closed, "unresolved_outcomes": unresolved,
                          "net_pnl_rs": net, "drawdown_state": drawdown_state,
                          "max_sequential_drawdown_rs": drawdown, "cost_stress_state": stress_state,
                          "stressed_net_pnl_rs": round(sum(stressed_pnls), 4) if stress_state == "VERIFIED" else None,
                          "stressed_max_sequential_drawdown_rs": round(stressed_drawdown, 4) if stress_state == "VERIFIED" else None,
                          "blockers": list(dict.fromkeys(blockers)),
                          "review_state": "READY_FOR_HUMAN_REVIEW" if not blockers else "INSUFFICIENT_EVIDENCE"})
    readiness_view = {
        "collection": readiness.get("collection", "UNKNOWN"),
        "causal_research": readiness.get("causal_research", "UNKNOWN"),
        "outcome_coverage": readiness.get("outcome_coverage", "UNKNOWN"),
        "reviewed_qualification": "HUMAN_REVIEW_REQUIRED",
        "telegram_routing": readiness.get("telegram_routing", "UNKNOWN"),
    }
    deterministic = {"format": "partner_qualification_review_v1", "policy_manifest_sha256": claimed,
                     "criteria": asdict(criteria),
                     "criteria_manifest_sha256": criteria_manifest.get("criteria_manifest_sha256")
                        if criteria_manifest else None,
                     "heldout_evidence_sha256": heldout_report.get("evidence_sha256"),
                     "per_index": per_index, "readiness": readiness_view,
                     "automatic_qualification": False, "can_send_advice": False, "can_place_orders": False,
                     "limitations": ["A human must review ordered outcomes, cost stress and drawdown before registry promotion.",
                                     "A review package cannot authorize a policy whose manifest changes."]}
    return {**deterministic, "evidence_sha256": _sha(deterministic),
            "review_state": "HUMAN_REVIEW_REQUIRED" if any(row["review_state"] == "READY_FOR_HUMAN_REVIEW" for row in per_index)
            else "INSUFFICIENT_EVIDENCE"}
