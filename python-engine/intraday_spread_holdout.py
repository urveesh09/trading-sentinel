"""Frozen per-index/policy held-out summaries for chronological spread replay."""
from __future__ import annotations

import hashlib
import json
import math
from datetime import date, datetime
from dataclasses import dataclass
from typing import Iterable, Mapping, Any

from intraday_spread_chronological import ChronologicalReplay
from intraday_spread_replay import ReplayResult


@dataclass(frozen=True)
class HeldOutCase:
    underlying: str
    policy_id: str
    session_date: str
    replay: ChronologicalReplay
    # Stable upstream identity, not a rendered report/evidence hash.  It binds
    # the case to its selected opportunity before holdout aggregation.
    opportunity_id: str
    signal_artifact_sha256: str
    cost_sensitivity: Mapping[str, Any] | None = None
    source_report: Mapping[str, Any] | None = None


def _digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def _ordered_clock(value: object) -> float:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("heldout outcomes require ISO event clocks") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("heldout outcome clocks must be timezone-aware")
    return parsed.timestamp()


def _outcome_order(row: Mapping[str, Any]) -> tuple[float, float, str]:
    entry = _ordered_clock(row.get("entry_at"))
    exit_value = row.get("exit_at")
    exit_clock = _ordered_clock(exit_value) if exit_value else float("inf")
    if exit_clock < entry or (row.get("state") == "CLOSED" and not exit_value):
        raise ValueError("heldout exit clock precedes entry or is missing")
    # Drawdown is a realised-equity sequence, so closed outcomes are ordered
    # by close time. Non-closed exposure follows without contributing P&L.
    realised = exit_clock if row.get("state") == "CLOSED" else float("inf")
    return realised, entry, str(row.get("opportunity_id"))


def _validated_cost_sensitivity(value: Mapping[str, Any], *, underlying: str,
                                policy_id: str, replay: ChronologicalReplay) -> list[Mapping[str, Any]]:
    body = {key: item for key, item in value.items() if key != "evidence_sha256"}
    scenarios = value.get("scenarios")
    if (_digest(body) != value.get("evidence_sha256")
            or value.get("format") != "intraday_spread_cost_sensitivity_v1"
            or value.get("can_qualify") is not False or value.get("can_place_orders") is not False
            or value.get("underlying") != underlying or value.get("policy_id") != policy_id
            or not isinstance(scenarios, list) or not scenarios):
        raise ValueError("full-policy cost sensitivity fingerprint or scope mismatch")
    coordinates: set[tuple[float, float]] = set()
    baseline = []
    for row in scenarios:
        if not isinstance(row, Mapping):
            raise ValueError("full-policy cost sensitivity scenario is malformed")
        try:
            if (isinstance(row["fee_multiplier"], bool)
                    or isinstance(row["additional_slippage_bps"], bool)):
                raise ValueError
            fee, slippage = float(row["fee_multiplier"]), float(row["additional_slippage_bps"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("full-policy cost sensitivity scenario is malformed") from exc
        coordinate = (fee, slippage)
        if (not math.isfinite(fee) or not math.isfinite(slippage) or fee < 1 or slippage < 0
                or coordinate in coordinates):
            raise ValueError("full-policy cost sensitivity coordinates are invalid or duplicated")
        coordinates.add(coordinate)
        if coordinate == (1.0, 0.0):
            baseline.append(row)
    if len(baseline) != 1:
        raise ValueError("full-policy cost sensitivity requires one baseline scenario")
    expected = replay.result
    base = baseline[0]
    if (base.get("state") != replay.state or base.get("reason") != expected.reason
            or base.get("net_pnl_rs") != expected.net_pnl_rs
            or base.get("evidence_sha256") != replay.evidence_sha256):
        raise ValueError("cost sensitivity baseline does not match chronological replay")
    return scenarios


def canonical_cost_sensitivity_fingerprint(scenarios: list[Mapping[str, Any]]) -> str:
    """[WORKFLOW-C.A3 2026-09-15] Deterministic fingerprint of a
    cost-sensitivity scenarios list, ordered by
    ``(fee_multiplier, additional_slippage_bps)``.

    The qualification review needs to verify that the
    cost-stress runs used the SAME scenario set across
    qualification windows. ``case.cost_sensitivity`` is
    provided by the caller and its scenarios array order
    is whatever the upstream code chose. Without a
    deterministic pin, two runs of the SAME logical
    scenario set can produce DIFFERENT ``evidence_sha256``
    values (because the upstream ordering may differ).

    This helper computes a stable SHA-256 hex digest over
    the scenarios SORTED by ``(fee_multiplier,
    additional_slippage_bps)``. The pin is invariant under
    input-order permutations, so the operator can compare
    pins across qualification windows to prove the
    scenario set is unchanged.

    The helper is total -- a non-list input degrades to an
    empty digest (the operator can still detect a
    malformed input by comparing against the canonical
    empty-string fingerprint). Non-finite or missing
    coordinates sort stably via string-coercion of the
    tuple, which preserves ``(fee, slippage)`` ordering
    when the values are well-formed. The validation in
    ``_validated_cost_sensitivity`` already enforces
    well-formed coordinates, so the sort is deterministic
    for any payload that survived validation.
    """
    if not isinstance(scenarios, list):
        return _digest([])
    sortable = []
    for row in scenarios:
        if not isinstance(row, Mapping):
            sortable.append((0, 0, row))
            continue
        try:
            fee = float(row.get("fee_multiplier", 0))
            slippage = float(row.get("additional_slippage_bps", 0))
        except (TypeError, ValueError):
            fee, slippage = 0.0, 0.0
        sortable.append((fee, slippage, dict(row)))
    sortable.sort(key=lambda triple: (triple[0], triple[1]))
    return _digest([row for _, _, row in sortable])


def heldout_case_from_full_policy_report(report: Mapping[str, Any], *,
                                         signal_artifact_sha256: str) -> HeldOutCase:
    """Bind a verified deployed-policy replay report to held-out review.

    This is deliberately strict: review cannot be fed a hand-built low-level
    result while claiming it came through the deployed full-policy evaluator.
    """
    if report.get("format") != "partner_full_policy_replay_v1":
        raise ValueError("full-policy replay report format is required")
    body = {key: value for key, value in report.items() if key != "evidence_sha256"}
    if _digest(body) != report.get("evidence_sha256"):
        raise ValueError("full-policy replay report fingerprint mismatch")
    manifest = report.get("manifest")
    if not isinstance(manifest, Mapping) or manifest.get("evaluator") != "partner_manual_intraday_full_policy_v1":
        raise ValueError("deployed full-policy manifest is required")
    manifest_body = {key: value for key, value in manifest.items() if key != "manifest_sha256"}
    if _digest(manifest_body) != manifest.get("manifest_sha256"):
        raise ValueError("full-policy manifest fingerprint mismatch")
    payload = report.get("replay")
    if not isinstance(payload, Mapping) or not isinstance(payload.get("result"), Mapping):
        raise ValueError("complete chronological replay payload is required")
    state = str(payload.get("state"))
    result = ReplayResult(**dict(payload["result"]))
    if state not in {"CLOSED", "NO_FILL", "UNRESOLVED"} or result.state != state or report.get("state") != state:
        raise ValueError("full-policy replay outcome states conflict")
    rejected = payload.get("rejected_entry_reasons", ())
    if not isinstance(rejected, (list, tuple)):
        raise ValueError("chronological rejection evidence is malformed")
    replay = ChronologicalReplay(result=result, state=state,
        attempted_entries=int(payload.get("attempted_entries", 0)),
        rejected_entry_reasons=tuple(str(item) for item in rejected),
        active_entry_at=payload.get("active_entry_at"), exit_trigger=payload.get("exit_trigger"),
        observation_count=int(payload.get("observation_count", 0)),
        evidence_sha256=str(payload.get("evidence_sha256", "")))
    if replay.evidence_sha256 != result.evidence_sha256:
        raise ValueError("chronological replay evidence identity conflicts")
    sensitivity = report.get("cost_sensitivity")
    if sensitivity is None:
        if report.get("economics_contract") is not None:
            raise ValueError("declared full-policy economics are missing")
        retained_sensitivity = None
    elif isinstance(sensitivity, Mapping):
        if report.get("economics_contract") != "FULL_POLICY_ECONOMICS_V1":
            raise ValueError("full-policy economics contract is missing")
        _validated_cost_sensitivity(sensitivity, underlying=str(manifest.get("underlying")),
                                    policy_id=str(manifest.get("policy_sha256")), replay=replay)
        retained_sensitivity = dict(sensitivity)
    else:
        raise ValueError("full-policy cost sensitivity is malformed")
    decision_id = report.get("decision_id")
    policy_id = manifest.get("policy_sha256")
    underlying = manifest.get("underlying")
    try:
        decision_at = datetime.fromisoformat(str(manifest.get("decision_at")))
    except ValueError as exc:
        raise ValueError("full-policy decision clock is invalid") from exc
    if (decision_at.tzinfo is None or not isinstance(decision_id, str) or not decision_id
            or underlying not in {"NIFTY", "SENSEX"} or not isinstance(policy_id, str) or not policy_id
            or len(signal_artifact_sha256) != 64
            or any(char not in "0123456789abcdef" for char in signal_artifact_sha256.lower())):
        raise ValueError("full-policy held-out identity is invalid")
    return HeldOutCase(str(underlying), policy_id, decision_at.date().isoformat(), replay,
                       decision_id, signal_artifact_sha256.lower(), retained_sensitivity, dict(report))


def build_heldout_comparison(*, dataset_sha256: str, code_revision: str,
                              training_sessions: Iterable[str], holdout_sessions: Iterable[str],
                              declared_coverage: Iterable[tuple[str, str, str]],
                              cases: Iterable[HeldOutCase], review_criteria_sha256: str | None = None) -> dict:
    """Summarise pre-separated sessions without selecting a winning policy.

    The result never auto-qualifies.  Empty/no-fill/unresolved sessions remain
    in their group counts, which prevents an attractive subset of closed
    outcomes from standing in for all collected opportunities.
    """
    if len(dataset_sha256) != 64 or any(char not in "0123456789abcdef" for char in dataset_sha256.lower()):
        raise ValueError("dataset_sha256 must be a SHA-256 hex digest")
    train, holdout = sorted(set(training_sessions)), sorted(set(holdout_sessions))
    if not code_revision.strip() or not train or not holdout or set(train) & set(holdout):
        raise ValueError("non-overlapping non-empty training and holdout sessions are required")
    try:
        if max(date.fromisoformat(day) for day in train) >= min(date.fromisoformat(day) for day in holdout):
            raise ValueError("training sessions must precede all holdout sessions")
    except ValueError as exc:
        if str(exc) == "training sessions must precede all holdout sessions":
            raise
        raise ValueError("training and holdout sessions must be ISO dates") from exc
    declared = sorted(set(declared_coverage))
    if not declared or any(index not in {"NIFTY", "SENSEX"} or not policy or day not in holdout
                           for index, policy, day in declared):
        raise ValueError("declared coverage must name NIFTY/SENSEX policy and holdout session")
    if review_criteria_sha256 is not None and (len(review_criteria_sha256) != 64
            or any(char not in "0123456789abcdef" for char in review_criteria_sha256.lower())):
        raise ValueError("review criteria identity must be a SHA-256 digest")
    submitted = list(cases)
    all_full_policy_cost_evidence = bool(submitted)
    seen_evidence: set[str] = set()
    seen_opportunities: set[tuple[str, str, str, str]] = set()
    groups: dict[str, dict] = {}
    for index, policy, day in declared:
        key = f"{index}:{policy}"
        groups.setdefault(key, {"underlying": index, "policy_id": policy,
                                "sessions": [], "coverage": {}, "closed": 0, "no_fill": 0,
                                "unresolved": 0, "unavailable": 0, "net_pnl_rs": 0.0,
                                "evidence_ids": [], "opportunity_ids": [], "signal_artifact_ids": [],
                                "ordered_outcomes": [], "cost_sensitivity": []})["coverage"].setdefault(day, "UNAVAILABLE")
    for case in submitted:
        if ((case.underlying, case.policy_id, case.session_date) not in declared
                or not case.opportunity_id or len(case.signal_artifact_sha256) != 64):
            raise ValueError("case does not belong to declared NIFTY/SENSEX holdout session")
        key = f"{case.underlying}:{case.policy_id}"
        stable_identity = (case.underlying, case.policy_id, case.session_date, case.opportunity_id)
        if case.replay.evidence_sha256 in seen_evidence or stable_identity in seen_opportunities:
            raise ValueError("duplicate chronological evidence identity")
        seen_evidence.add(case.replay.evidence_sha256); seen_opportunities.add(stable_identity)
        if case.source_report is None:
            all_full_policy_cost_evidence = False
        else:
            verified = heldout_case_from_full_policy_report(case.source_report,
                signal_artifact_sha256=case.signal_artifact_sha256)
            if any(getattr(verified, field) != getattr(case, field) for field in
                   ("underlying", "policy_id", "session_date", "replay", "opportunity_id",
                    "signal_artifact_sha256", "cost_sensitivity")):
                raise ValueError("heldout case differs from its verified full-policy report")
            public_sources = case.source_report.get("public_sources")
            source_rows = public_sources.get("sources") if isinstance(public_sources, Mapping) else None
            source_master = case.source_report["manifest"].get("contract_master_sha256")
            if (case.source_report.get("public_evidence_contract") != "VERIFIED_ARCHIVED_FUTURE_SCOPE_V1"
                    or not isinstance(source_rows, list) or not source_rows
                    or any(not isinstance(source, Mapping)
                           or source.get("public_scope_state") != "VERIFIED_CONTRACT_SCOPE"
                           or not isinstance(source.get("public_scope"), Mapping)
                           or _digest(source["public_scope"]) != source.get("public_scope_sha256")
                           or source["public_scope"].get("contract_master_raw_sha256") != source_master
                           for source in source_rows)):
                all_full_policy_cost_evidence = False
        if case.cost_sensitivity is None:
            all_full_policy_cost_evidence = False
        else:
            _validated_cost_sensitivity(case.cost_sensitivity, underlying=case.underlying,
                                        policy_id=case.policy_id, replay=case.replay)
        bucket = groups[key]
        state = case.replay.state
        # A session may contain multiple independent candidate decisions.  The
        # matrix tracks whether it was observed; outcome counts preserve every
        # attempted opportunity rather than discarding later losses/no-fills.
        bucket["coverage"][case.session_date] = "OBSERVED"
        bucket["sessions"].append(case.session_date); bucket["evidence_ids"].append(case.replay.evidence_sha256)
        bucket["opportunity_ids"].append(case.opportunity_id); bucket["signal_artifact_ids"].append(case.signal_artifact_sha256.lower())
        bucket["ordered_outcomes"].append({"session_date": case.session_date,
            "entry_at": case.replay.result.entry_at, "exit_at": case.replay.result.exit_at,
            "state": state, "net_pnl_rs": case.replay.result.net_pnl_rs,
            "opportunity_id": case.opportunity_id, "evidence_sha256": case.replay.evidence_sha256})
        if case.cost_sensitivity is not None:
            # [WORKFLOW-C.A3 2026-09-15] Deterministic
            # scenario-set fingerprint. The pin is invariant
            # under input-order permutations of the scenarios
            # list -- two qualification windows that used the
            # same logical scenario set produce the same pin
            # regardless of how the upstream code ordered
            # them. The pin is computed AFTER the scenarios
            # are validated (so a malformed scenario set has
            # already raised by this point -- the bucket is
            # only constructed for cases that survived
            # ``_validated_cost_sensitivity``).
            scenario_fingerprint = canonical_cost_sensitivity_fingerprint(
                list(case.cost_sensitivity.get("scenarios", ())),
            )
            bucket["cost_sensitivity"].append({"opportunity_id": case.opportunity_id,
                "source_report_sha256": case.source_report.get("evidence_sha256") if case.source_report else None,
                "source_manifest_sha256": case.source_report.get("manifest", {}).get("manifest_sha256")
                    if case.source_report else None,
                "cost_sensitivity_sha256": scenario_fingerprint,
                "artifact": dict(case.cost_sensitivity)})
        if case.replay.state == "CLOSED":
            pnl = case.replay.result.net_pnl_rs
            if pnl is None or not math.isfinite(float(pnl)):
                raise ValueError("closed heldout replay requires finite net P&L")
            bucket["closed"] += 1; bucket["net_pnl_rs"] += float(pnl)
        elif case.replay.state == "NO_FILL":
            bucket["no_fill"] += 1
        elif case.replay.state == "UNRESOLVED":
            bucket["unresolved"] += 1
        else:
            raise ValueError("heldout replay has an unsupported state")
    for bucket in groups.values():
        bucket["unavailable"] = sum(state == "UNAVAILABLE" for state in bucket["coverage"].values())
        bucket["sessions"] = sorted(set(bucket["sessions"])); bucket["evidence_ids"].sort(); bucket["opportunity_ids"].sort()
        bucket["signal_artifact_ids"] = sorted(set(bucket["signal_artifact_ids"]))
        bucket["ordered_outcomes"].sort(key=_outcome_order)
        bucket["cost_sensitivity"].sort(key=lambda row: row["opportunity_id"])
        bucket["net_pnl_rs"] = round(bucket["net_pnl_rs"], 4)
        running = peak = max_drawdown = 0.0
        for row in bucket["ordered_outcomes"]:
            if row["state"] == "CLOSED":
                running += float(row["net_pnl_rs"])
                peak = max(peak, running)
                max_drawdown = min(max_drawdown, running - peak)
        bucket["max_sequential_drawdown_rs"] = round(max_drawdown, 4)
        evaluated = bucket["closed"] + bucket["no_fill"] + bucket["unresolved"]
        bucket["evaluated"] = evaluated
        bucket["expectancy_rs"] = round(bucket["net_pnl_rs"] / evaluated, 4) if evaluated else None
    deterministic = {"format": "intraday_spread_heldout_v1", "dataset_sha256": dataset_sha256.lower(),
                     "code_revision": code_revision.strip(), "training_sessions": train, "holdout_sessions": holdout,
                      "groups": [groups[key] for key in sorted(groups)], "case_count": len(submitted),
                      "declared_coverage": [{"underlying": index, "policy_id": policy, "session_date": day}
                                            for index, policy, day in declared],
                     "evidence_contract": "VERIFIED_FULL_POLICY_REPORTS" if all_full_policy_cost_evidence
                     else "LEGACY_CHRONOLOGICAL_CASES",
                     "review_criteria_sha256": review_criteria_sha256.lower() if review_criteria_sha256 else None,
                     "automatic_qualification": False, "can_place_orders": False,
                     "limitations": ["A held-out summary is not evidence of future profitability.",
                                     "External collection coverage and unresolved exits must be reviewed by a human."]}
    return {**deterministic, "evidence_sha256": _digest(deterministic), "review_state": "HUMAN_REVIEW_REQUIRED"}
