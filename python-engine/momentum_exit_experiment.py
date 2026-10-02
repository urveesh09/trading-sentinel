"""Frozen, read-only paired experiments for momentum-paper exit policies (S6a).

This extends the v1 exit study (``momentum_exit_study``) without changing it.
The same immutable LTP packet loader, path validation, pure live evaluator,
cost model and leg arithmetic are reused.  What is added:

* a freeze manifest that pins one candidate policy, its parameters, the live
  evaluator settings and a source fingerprint *before* evaluation, so a policy
  cannot be re-tuned after its outcomes are seen;
* development/holdout labelling: entries at or before the freeze time are
  ``DEVELOPMENT`` and can never be presented as held-out evidence;
* ``thesis_confirmed_extension_v1``: a candidate that changes only the
  evaluator's time-stop and target exits, and only while confirmation known
  *at that quote* holds;
* exposure metrics (MFE/MAE, giveback, time exposed, tail) and cost-stressed
  paired deltas.

It has no database, broker, HTTP, scheduler, order or message dependency and
no runtime caller.  Results are paper research only; qualification is never
assessed here and a positive sample authorizes nothing.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping, Sequence

from config import settings
from cost_schedules import equity_intraday_cost_snapshot
from momentum_exit_study import (
    ALTERNATIVE_POLICY as TARGET_HOLD_TRAIL_POLICY,
    BASELINE_POLICY,
    ExitStudyError,
    Quote,
    StudyEntry,
    _POLICY_SETTINGS,
    _canonical_bytes,
    _close,
    _deadline,
    _entry_economics,
    _finalise,
    _leg,
    _position,
    _simulate as _study_simulate,
    _validated_quote_path,
    deadline_policy_of,
    load_exit_study_packet,
    write_study_report_once,
)
from exit_experiment_metrics import paired_deltas as _paired_deltas, policy_summary as _policy_summary
from momentum_exits import ACTION_EXIT, ACTION_SCALE_OUT, ACTION_TRAIL, evaluate_momentum_exit


MANIFEST_SCHEMA = "momentum_exit_experiment_manifest_v1"
REPORT_SCHEMA = "momentum_exit_experiment_report_v1"
THESIS_POLICY = "thesis_confirmed_extension_v1"
COST_MULTIPLIERS = (1.0, 1.5, 2.0)
_SOURCE_MODULES = ("momentum_exit_study.py", "momentum_exit_experiment.py", "momentum_exits.py",
                   "exit_experiment_metrics.py", "engine.py", "cost_schedules.py")

CANDIDATE_POLICIES: dict[str, dict[str, Any]] = {
    TARGET_HOLD_TRAIL_POLICY: {
        "description": "v1 alternative: unconditional hold after target with a fixed 0.5R trail",
        "trail_distance_r": 0.5,
    },
    THESIS_POLICY: {
        "description": (
            "replace only time-stop/target exits while VWAP-at-entry, non-negative "
            "progress, running-high structure and regime confirm at that quote"
        ),
        "replaceable_exits": ["time_stop", "target_hit"],
        "require_ltp_above_vwap_at_entry": True,
        "min_progress_r": 0.0,
        "max_pullback_from_running_high_r": 0.5,
        "trail_from_running_high_r": 1.0,
        "blocked_regime_markers": ["REGIME_3", "CRISIS"],
        "volume_confirmation": "UNAVAILABLE_NOT_USED",
        "initial_stop_unchanged": True,
        "stop_never_lowered": True,
        "deadline": "15:15 Asia/Kolkata",
    },
}


def _source_fingerprint() -> str:
    """Identify the exact study/experiment/evaluator source (line-ending neutral)."""
    here = Path(__file__).resolve().parent
    digest = hashlib.sha256()
    for name in _SOURCE_MODULES:
        data = (here / name).read_bytes().replace(b"\r\n", b"\n")
        digest.update(name.encode("utf-8") + b"\0" + hashlib.sha256(data).digest())
    return f"sha256:{digest.hexdigest()}"


def _evaluator_settings() -> dict[str, Any]:
    return {name: getattr(settings, name) for name in _POLICY_SETTINGS}


def _aware(value: datetime, field: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ExitStudyError(f"{field} must be timezone-aware")
    return value


def freeze_experiment_manifest(*, experiment_id: str, candidate_policy: str,
                               frozen_at: datetime | None = None) -> dict[str, Any]:
    """Pin one candidate and the current evaluator before any evaluation."""
    experiment_id = (experiment_id or "").strip()
    if not experiment_id or len(experiment_id) > 160:
        raise ExitStudyError("experiment_id must be a non-empty <=160-character string")
    if candidate_policy not in CANDIDATE_POLICIES:
        raise ExitStudyError(f"unknown candidate policy: {candidate_policy}")
    frozen_at = _aware(frozen_at or datetime.now(timezone.utc), "frozen_at")
    return {
        "schema": MANIFEST_SCHEMA,
        "experiment_id": experiment_id,
        "baseline_policy": BASELINE_POLICY,
        "candidate_policy": candidate_policy,
        "candidate_parameters": deepcopy(CANDIDATE_POLICIES[candidate_policy]),
        "evaluator_settings": _evaluator_settings(),
        "cost_model": "engine.calc_zerodha_costs_intraday",
        "cost_schedule": equity_intraday_cost_snapshot(),
        "cost_multipliers": list(COST_MULTIPLIERS),
        "source_fingerprint": _source_fingerprint(),
        "frozen_at": frozen_at.astimezone(timezone.utc).isoformat(),
        "holdout_rule": "only entries strictly after frozen_at are HOLDOUT",
    }


def verify_experiment_manifest(manifest: Mapping[str, Any]) -> datetime:
    """Refuse evaluation unless policy, settings and source match the freeze."""
    if not isinstance(manifest, Mapping) or manifest.get("schema") != MANIFEST_SCHEMA:
        raise ExitStudyError(f"manifest schema must be {MANIFEST_SCHEMA}")
    policy = manifest.get("candidate_policy")
    if policy not in CANDIDATE_POLICIES:
        raise ExitStudyError("FROZEN_POLICY_MISMATCH: unknown candidate policy")
    expected = {
        "baseline_policy": BASELINE_POLICY,
        "cost_model": "engine.calc_zerodha_costs_intraday",
        "candidate_parameters": CANDIDATE_POLICIES[policy],
        "cost_schedule": equity_intraday_cost_snapshot(),
        "evaluator_settings": _evaluator_settings(),
        "cost_multipliers": list(COST_MULTIPLIERS),
        "source_fingerprint": _source_fingerprint(),
    }
    for field, current in expected.items():
        if _canonical_bytes({"v": manifest.get(field)}) != _canonical_bytes({"v": current}):
            raise ExitStudyError(f"FROZEN_POLICY_MISMATCH: {field} differs from the frozen manifest")
    try:
        frozen_at = datetime.fromisoformat(str(manifest.get("frozen_at")).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ExitStudyError("manifest frozen_at is invalid") from exc
    return _aware(frozen_at, "manifest.frozen_at")


def confirmation(entry: StudyEntry, ltp: float, running_high: float,
                 params: Mapping[str, Any]) -> tuple[bool, str]:
    """Thesis confirmation from facts known at this observation only."""
    r_per_share = entry.entry_price - entry.stop_loss_initial
    regime = str(entry.regime_at_entry or "")
    if any(marker in regime for marker in params["blocked_regime_markers"]):
        return False, "regime_blocked"
    if params["require_ltp_above_vwap_at_entry"]:
        if entry.vwap_at_entry is None:
            return False, "vwap_at_entry_unavailable"
        if ltp <= entry.vwap_at_entry:
            return False, "below_vwap_at_entry"
    if (ltp - entry.entry_price) / r_per_share < float(params["min_progress_r"]):
        return False, "progress_below_minimum"
    if running_high - ltp > float(params["max_pullback_from_running_high_r"]) * r_per_share:
        return False, "structure_pullback_exceeded"
    return True, "confirmed"


def _replaceable(reason: str, params: Mapping[str, Any]) -> bool:
    return any(reason == kind or reason.startswith(kind + "_") for kind in params["replaceable_exits"])


def _simulate_thesis(entry: StudyEntry, quotes: Sequence[Quote], params: Mapping[str, Any]) -> dict[str, Any]:
    """Replay the live evaluator, replacing only confirmed time-stop/target exits.

    Every decision reads the current quote and state accumulated from earlier
    quotes only.  The protective stop is checked first exactly as in v1; once a
    replacement is active, losing confirmation exits at that observation.
    """
    state: dict[str, Any] = {"position": _position(entry), "legs": [], "closed": False}
    observed_prices = [quote.ltp for quote in quotes if quote.observed_at <= _deadline(entry)]
    r_per_share = entry.entry_price - entry.stop_loss_initial
    running_high = entry.entry_price
    replaced: list[dict[str, str]] = []
    replaced_kinds: set[str] = set()
    target_released = False
    for quote in quotes:
        if quote.observed_at > _deadline(entry) or state["closed"]:
            continue
        running_high = max(running_high, quote.ltp)
        position = state["position"]
        if quote.ltp <= float(position["trailing_stop_current"]):
            _close(entry, state, quote.ltp, "protective_stop_observed", quote.observed_at)
            continue
        if replaced:
            ok, why = confirmation(entry, quote.ltp, running_high, params)
            if not ok:
                _close(entry, state, quote.ltp, f"thesis_confirmation_lost:{why}", quote.observed_at)
                continue
        decision_position = dict(position)
        if target_released:
            decision_position["target_1"] = None
        decision = evaluate_momentum_exit(decision_position, quote.ltp, quote.observed_at)
        action = decision.get("action")
        reason = str(decision.get("reason") or "exit")
        if action == ACTION_EXIT:
            if not _replaceable(reason, params):
                _close(entry, state, quote.ltp, reason, quote.observed_at)
                continue
            ok, _why = confirmation(entry, quote.ltp, running_high, params)
            if not ok:
                _close(entry, state, quote.ltp, reason, quote.observed_at)
                continue
            kind = "target_hit" if reason == "target_hit" else "time_stop"
            if kind not in replaced_kinds:
                replaced_kinds.add(kind)
                replaced.append({"at": quote.observed_at.isoformat(), "exit_replaced": reason})
            if kind == "target_hit":
                target_released = True
                position["target_1"] = None
                position["t1_fired"] = True
        elif action == ACTION_SCALE_OUT:
            sold = int(decision.get("scale_shares") or 0)
            remaining = int(position["shares"]) - sold
            if not 0 < sold < int(position["shares"]) or remaining < 1:
                state["reason"] = "invalid_scale_out_decision"
                break
            state["legs"].append(_leg(entry, sold, quote.ltp, reason, quote.observed_at))
            position["shares"] = remaining
            position["t1_fired"] = True
            position["trailing_stop_current"] = max(float(position["trailing_stop_current"]),
                                                    float(decision["new_stop"]))
        elif action == ACTION_TRAIL and decision.get("new_stop") is not None:
            position["trailing_stop_current"] = max(float(position["trailing_stop_current"]),
                                                    float(decision["new_stop"]))
        if replaced:
            trail = running_high - float(params["trail_from_running_high_r"]) * r_per_share
            if trail < quote.ltp:
                position["trailing_stop_current"] = max(float(position["trailing_stop_current"]), trail)
    if not state["closed"] and state.get("reason") != "invalid_scale_out_decision":
        deadline_quote = quotes[-1]  # validated path ends with the deadline close quote
        _close(entry, state, deadline_quote.ltp, "intraday_deadline", deadline_quote.observed_at)
    result = _finalise(entry, THESIS_POLICY, state, observed_prices)
    result["exits_replaced"] = replaced
    return result


def _exposure_metrics(entry: StudyEntry, quotes: Sequence[Quote], result: dict[str, Any]) -> dict[str, Any]:
    """Add exposure-window MFE/MAE, giveback, time exposed and cost stress."""
    if result.get("status") != "CLOSED":
        return result
    r_per_share = entry.entry_price - entry.stop_loss_initial
    initial_risk = r_per_share * entry.shares
    exit_at = datetime.fromisoformat(result["exit_at"])
    window = [quote.ltp for quote in quotes if entry.entry_at <= quote.observed_at <= exit_at]
    mfe_r = (max(window) - entry.entry_price) / r_per_share if window else 0.0
    mae_r = (min(window) - entry.entry_price) / r_per_share if window else 0.0
    gross_r = float(result["gross_pnl"]) / initial_risk
    costs = float(result["costs"])
    gross = float(result["gross_pnl"])
    return {
        **result,
        "mfe_r": round(max(0.0, mfe_r), 8),
        "mae_r": round(min(0.0, mae_r), 8),
        "giveback_r": round(max(0.0, mfe_r) - gross_r, 8),
        "minutes_exposed": round((exit_at - entry.entry_at).total_seconds() / 60.0, 4),
        "net_pnl_cost_stressed": {f"{multiplier:g}x": round(gross - multiplier * costs, 6)
                                  for multiplier in COST_MULTIPLIERS},
    }


def build_exit_experiment(packet_path: str | os.PathLike[str], manifest: Mapping[str, Any]) -> dict[str, Any]:
    """Evaluate one frozen candidate against the baseline on identical paths."""
    frozen_at = verify_experiment_manifest(manifest)
    packet, entries, grouped, input_fingerprint = load_exit_study_packet(packet_path)
    policy = str(manifest["candidate_policy"])
    params = CANDIDATE_POLICIES[policy]
    max_gap = int(packet["max_quote_gap_seconds"])
    deadline_policy = deadline_policy_of(packet)
    pairs = []
    for entry in sorted(entries, key=lambda item: item.entry_id):
        sample = "HOLDOUT" if entry.entry_at > frozen_at else "DEVELOPMENT"
        quotes, issue = _validated_quote_path(entry, grouped[entry.entry_id], max_gap, deadline_policy)
        base = {"entry_id": entry.entry_id, "admission_key": entry.admission_key,
                "ticker": entry.ticker, "source_ref": entry.source_ref,
                "entry_economics": _entry_economics(entry), "sample_class": sample}
        if issue is not None:
            unresolved = {"status": "INSUFFICIENT_EVIDENCE", "reason": issue, "legs": []}
            pairs.append({**base, "status": "INSUFFICIENT_EVIDENCE", "reason": issue,
                          "baseline": {"policy": BASELINE_POLICY, **unresolved},
                          "candidate": {"policy": policy, **unresolved}})
            continue
        baseline = _study_simulate(entry, quotes, BASELINE_POLICY)
        if policy == TARGET_HOLD_TRAIL_POLICY:
            candidate = _study_simulate(entry, quotes, TARGET_HOLD_TRAIL_POLICY)
        else:
            candidate = _simulate_thesis(entry, quotes, params)
        pairs.append({**base, "status": "COMPLETE",
                      "baseline": _exposure_metrics(entry, quotes, baseline),
                      "candidate": _exposure_metrics(entry, quotes, candidate)})

    def section(sample: str | None) -> dict[str, Any]:
        chosen = [pair for pair in pairs if sample is None or pair["sample_class"] == sample]
        return {
            "pairs": len(chosen),
            "baseline": _policy_summary([pair["baseline"] for pair in chosen]),
            "candidate": _policy_summary([pair["candidate"] for pair in chosen]),
            "paired": _paired_deltas(chosen),
        }

    report: dict[str, Any] = {
        "schema": REPORT_SCHEMA,
        "experiment_id": manifest["experiment_id"],
        "study_id": packet["study_id"],
        "input_fingerprint": input_fingerprint,
        "manifest_fingerprint": f"sha256:{hashlib.sha256(_canonical_bytes(dict(manifest))).hexdigest()}",
        "manifest": dict(manifest),
        "evidence_contract": {
            "timezone": "Asia/Kolkata", "max_quote_gap_seconds": max_gap, "deadline": "15:15",
            "deadline_quote_policy": deadline_policy,
            "missing_or_ambiguous_path": "INSUFFICIENT_EVIDENCE",
            "holdout": "entries strictly after manifest.frozen_at; others are DEVELOPMENT",
            "outcomes_are": "paper_research_only",
        },
        "pairs": pairs,
        "summary": {
            "all": section(None),
            "holdout": section("HOLDOUT"),
            "development": section("DEVELOPMENT"),
            "qualification": "NOT_ASSESSED",
            "warning": ("A paired replay is not evidence of an edge or authority to change "
                        "live or paper exits; promotion requires a reviewed holdout."),
        },
    }
    report["report_fingerprint"] = f"sha256:{hashlib.sha256(_canonical_bytes(report)).hexdigest()}"
    return report


def _read_json(path: str) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ExitStudyError(f"unreadable JSON: {path}") from exc
    if not isinstance(value, dict):
        raise ExitStudyError(f"JSON root must be an object: {path}")
    return value


def _main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Frozen read-only momentum exit experiment")
    sub = parser.add_subparsers(dest="command", required=True)
    freeze = sub.add_parser("freeze", help="write an immutable manifest before evaluation")
    freeze.add_argument("--experiment-id", required=True)
    freeze.add_argument("--candidate", required=True, choices=sorted(CANDIDATE_POLICIES))
    freeze.add_argument("--output", required=True, help="new manifest path; never overwritten")
    evaluate = sub.add_parser("evaluate", help="evaluate a frozen manifest on an immutable packet")
    evaluate.add_argument("--manifest", required=True)
    evaluate.add_argument("--input", required=True)
    evaluate.add_argument("--output", required=True, help="new report path; never overwritten")
    args = parser.parse_args(argv)
    try:
        if args.command == "freeze":
            value = freeze_experiment_manifest(experiment_id=args.experiment_id,
                                               candidate_policy=args.candidate)
        else:
            value = build_exit_experiment(args.input, _read_json(args.manifest))
        write_study_report_once(value, args.output)
    except ExitStudyError as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    raise SystemExit(_main())
