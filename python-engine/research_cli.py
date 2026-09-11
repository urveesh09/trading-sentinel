"""Operator commands for immutable research preservation (no broker actions)."""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import asdict
from datetime import datetime, timedelta
from pathlib import Path

from config import settings
from research_archive import export_operational_fno_evidence


def _json_file(path: str) -> dict:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError(f"unreadable JSON file: {path}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return value


def _replay_spread(args: argparse.Namespace) -> dict:
    """Run archive -> verified signal -> chronological replay without writes."""
    from intraday_spread_archive_adapter import SpreadContractIdentity, build_spread_observations, read_archived_quote_events
    from intraday_spread_chronological import ChronologicalPolicy, replay_chronological_debit_spread

    long_contract = SpreadContractIdentity(**_json_file(args.long_contract))
    short_contract = SpreadContractIdentity(**_json_file(args.short_contract))
    policy_config = _json_file(args.policy)
    for key in ("execution_delay", "execution_max_wait", "signal_expiry", "max_quote_age", "max_leg_sync"):
        if key in policy_config and isinstance(policy_config[key], (int, float)):
            policy_config[key] = timedelta(seconds=float(policy_config[key]))
    policy = ChronologicalPolicy(**policy_config)
    if policy.policy_id != args.policy_id:
        raise ValueError("policy file identity does not match --policy-id")
    days = [day.strip() for day in args.days.split(",") if day.strip()]
    events = read_archived_quote_events(args.archive_root, days=days)
    built = build_spread_observations(events=events, long_contract=long_contract, short_contract=short_contract,
        master_sha256=args.master_sha256, archive_root=args.archive_root, signal_artifact_path=args.signal_artifact,
        policy_id=args.policy_id, session_date=args.session_date)
    if not built.observations:
        return {"state": "INSUFFICIENT_EVIDENCE", "reason": "no_complete_two_leg_observations",
                "observation_count": 0, "partial_batches": list(built.partial_batches), "ignored_events": built.ignored_events,
                "signal_artifact_sha256": built.signal_provenance_sha256, "can_place_orders": False}
    replay = replay_chronological_debit_spread(underlying=long_contract.underlying, expiry=long_contract.expiry,
        observations=built.observations, policy=policy)
    return {"state": replay.state, "replay": asdict(replay), "partial_batches": list(built.partial_batches),
            "ignored_events": built.ignored_events, "signal_artifact_sha256": built.signal_provenance_sha256,
            "can_place_orders": False}


def _full_policy_diagnostic(args: argparse.Namespace) -> dict:
    """Evaluate the complete deployed signal from explicitly-provenanced bars."""
    import pandas as pd
    from partner_qualification import evaluate_deployed_full_policy, write_full_policy_decision, load_candidate_evidence

    raw = pd.read_csv(args.bars)
    if "bar_start" not in raw.columns:
        raise ValueError("bars CSV requires bar_start")
    parsed = pd.to_datetime(raw.pop("bar_start"), errors="raise")
    # The deployed evaluator expects naive exchange-local bar starts. An
    # offset-aware input is converted to Asia/Kolkata before stripping tz.
    if getattr(parsed.dt, "tz", None) is not None:
        parsed = parsed.dt.tz_convert("Asia/Kolkata").dt.tz_localize(None)
    raw.index = parsed
    provenance = _json_file(args.bar_provenance)
    for key in ("event_at", "received_at", "retrieved_at"):
        if isinstance(provenance.get(key), str):
            provenance[key] = datetime.fromisoformat(provenance[key].replace("Z", "+00:00"))
    decision_at = datetime.fromisoformat(args.decision_at.replace("Z", "+00:00"))
    candidate_inputs = {}
    if getattr(args, "candidate_evidence", None):
        book, snapshot, profile = load_candidate_evidence(_json_file(args.candidate_evidence),
                                                        underlying=args.underlying, decision_at=decision_at,
                                                        archive_root=getattr(args, "archive_root", None),
                                                        master_sha256=args.contract_master_sha256)
        candidate_inputs = {"book": book, "snapshot": snapshot, "profile": profile}
    decision = evaluate_deployed_full_policy(
        underlying=args.underlying, bars=raw, regime=args.regime, decision_at=decision_at,
        bar_provenance=provenance, contract_master_sha256=args.contract_master_sha256,
        **candidate_inputs,
    )
    result = write_full_policy_decision(args.output, decision)
    return {"state": result["state"], "reason": result["reason"], "decision_id": result["decision_id"],
            "path": str(Path(args.output)), "can_qualify": False, "can_place_orders": False}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sentinel read-only research evidence tools")
    sub = parser.add_subparsers(dest="command", required=True)
    captured = sub.add_parser("captured-policy-diagnostic", help="re-evaluate a fingerprinted public-input capture; no qualification")
    captured.add_argument("--public-input", required=True)
    captured.add_argument("--underlying", required=True, choices=["NIFTY", "SENSEX"])
    captured.add_argument("--output", required=True)
    captured.add_argument("--candidate-evidence", help="offline observed contracts, chain and explicit profile JSON")
    captured.add_argument("--contract-master-sha256")
    captured.add_argument("--archive-root", help="verify supplied contract terms against archived raw master")
    export = sub.add_parser("export-fno", help="read-only export of operational NIFTY/SENSEX OI snapshots")
    export.add_argument("--source-db", default=settings.DB_PATH)
    export.add_argument("--archive-root", default=settings.RESEARCH_ARCHIVE_PATH)
    export.add_argument("--underlyings", default=settings.RESEARCH_ARCHIVE_UNDERLYINGS,
                        help="comma-separated underlying names; default NIFTY,SENSEX")
    replay = sub.add_parser("replay-spread", help="read-only archive-to-signal-to-chronological spread research")
    replay.add_argument("--archive-root", default=settings.RESEARCH_ARCHIVE_PATH)
    replay.add_argument("--days", required=True, help="comma-separated archive ISO session dates")
    replay.add_argument("--long-contract", required=True, help="JSON file matching SpreadContractIdentity")
    replay.add_argument("--short-contract", required=True, help="JSON file matching SpreadContractIdentity")
    replay.add_argument("--master-sha256", required=True)
    replay.add_argument("--signal-artifact", required=True)
    replay.add_argument("--policy", required=True, help="frozen ChronologicalPolicy JSON; duration fields are seconds")
    replay.add_argument("--policy-id", required=True)
    replay.add_argument("--session-date", required=True)
    full_policy = sub.add_parser("full-policy-diagnostic", help="write a causal complete-policy signal diagnostic; no delivery/qualification")
    full_policy.add_argument("--underlying", required=True, choices=["NIFTY", "SENSEX"])
    full_policy.add_argument("--bars", required=True, help="CSV with bar_start,open,high,low,close,volume")
    full_policy.add_argument("--regime", required=True)
    full_policy.add_argument("--decision-at", required=True, help="timezone-aware ISO decision clock")
    full_policy.add_argument("--bar-provenance", required=True, help="JSON event/receipt/retrieval provenance")
    full_policy.add_argument("--contract-master-sha256")
    full_policy.add_argument("--archive-root", help="verify supplied contract terms against archived raw master")
    full_policy.add_argument("--candidate-evidence", help="observed JSON contracts, snapshot, receipt and explicit profile; offline only")
    full_policy.add_argument("--output", required=True, help="atomic full-policy decision output")
    reconcile = sub.add_parser("reconcile-internal", help="write all five retained-data reconciliation investigations")
    reconcile.add_argument("--source-db", default=settings.DB_PATH)
    reconcile.add_argument("--output", required=True, help="JSON evidence output; no ledger mutation")
    reconcile.add_argument("--limit", type=int, default=1000)
    args = parser.parse_args(argv)
    if args.command == "captured-policy-diagnostic":
        try:
            from partner_research_capture import load_public_input
            from partner_qualification import evaluate_deployed_full_policy, write_full_policy_decision, load_candidate_evidence
            bars, regime, at, provenance = load_public_input(args.public_input, underlying=args.underlying)
            candidate_inputs = {}
            if args.candidate_evidence:
                book, snapshot, profile = load_candidate_evidence(_json_file(args.candidate_evidence),
                                                                 underlying=args.underlying, decision_at=at,
                                                                 archive_root=args.archive_root,
                                                                 master_sha256=args.contract_master_sha256)
                candidate_inputs = {"book": book, "snapshot": snapshot, "profile": profile}
            decision = evaluate_deployed_full_policy(underlying=args.underlying, bars=bars, regime=regime,
                                                     decision_at=at, bar_provenance=provenance,
                                                     contract_master_sha256=args.contract_master_sha256, **candidate_inputs)
            result = write_full_policy_decision(args.output, decision)
            print(json.dumps({"state": result["state"], "reason": result["reason"], "path": args.output,
                              "can_qualify": False}, sort_keys=True))
            return 0
        except (ValueError, KeyError, TypeError, OSError) as exc:
            print(json.dumps({"state": "UNAVAILABLE", "reason": str(exc), "can_qualify": False}), file=sys.stderr)
            return 2
    if args.command == "export-fno":
        try:
            result = export_operational_fno_evidence(
                args.source_db, args.archive_root,
                [name.strip() for name in args.underlyings.split(",") if name.strip()],
                reserved_free_bytes=settings.RESEARCH_RESERVED_FREE_BYTES,
            )
        except Exception as exc:
            print(json.dumps({"exported": False, "error": str(exc)}), file=sys.stderr)
            return 1
        print(json.dumps({"exported": True, "path": result["path"], "coverage": result["coverage"]}, sort_keys=True))
        return 0
    if args.command == "replay-spread":
        try:
            print(json.dumps(_replay_spread(args), sort_keys=True, default=str))
        except Exception as exc:
            print(json.dumps({"state": "RESEARCH_INPUT_REJECTED", "error": str(exc), "can_place_orders": False}), file=sys.stderr)
            return 1
        return 0
    if args.command == "full-policy-diagnostic":
        try:
            print(json.dumps(_full_policy_diagnostic(args), sort_keys=True))
        except Exception as exc:
            print(json.dumps({"state": "RESEARCH_INPUT_REJECTED", "error": str(exc), "can_place_orders": False}), file=sys.stderr)
            return 1
        return 0
    if args.command == "reconcile-internal":
        try:
            from reconciliation_evidence import reconciliation_evidence_report
            report = asyncio.run(reconciliation_evidence_report(args.source_db, limit=args.limit))
            target = Path(args.output)
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_suffix(target.suffix + ".tmp")
            temporary.write_text(json.dumps(report, sort_keys=True, indent=2, default=str), encoding="utf-8")
            temporary.replace(target)
        except Exception as exc:
            print(json.dumps({"written": False, "error": str(exc)}), file=sys.stderr)
            return 1
        print(json.dumps({"written": True, "path": str(target), "status": report.get("status"),
                          "source_sheets": len(report.get("source_sheets") or [])}, sort_keys=True))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
