"""Operator commands for immutable research preservation (no broker actions)."""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import asdict
from datetime import timedelta
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sentinel read-only research evidence tools")
    sub = parser.add_subparsers(dest="command", required=True)
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
    reconcile = sub.add_parser("reconcile-internal", help="write all five retained-data reconciliation investigations")
    reconcile.add_argument("--source-db", default=settings.DB_PATH)
    reconcile.add_argument("--output", required=True, help="JSON evidence output; no ledger mutation")
    reconcile.add_argument("--limit", type=int, default=1000)
    args = parser.parse_args(argv)
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
