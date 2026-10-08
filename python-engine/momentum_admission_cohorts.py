"""Momentum allocation holdout split by upstream admission policy (O8-T6, 2026-10-08).

The frozen allocation manifest (``momentum_allocation_research``) fingerprints
the allocator, paper sizing, exits and costs, but not the gate that decides
which signals become candidates. From the October 8 session the live Momentum
candidates pass the selective entry gate (``momentum_selective``), so the
holdout after that date is a different population. This module runs the
unchanged frozen report once per admission population instead of pooling
them. It lives outside the fingerprinted modules on purpose: editing them
would invalidate the existing freeze.

Read-only research, like the report it wraps: no database write, order or
message path, and no qualification.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from momentum_allocation_research import Candidate, build_allocation_report
from momentum_exit_study import ExitStudyError, write_study_report_once

SCHEMA = "momentum_allocation_cohorts_v1"
# (name, first admission clock). Append a row whenever the upstream gate changes.
ADMISSION_POPULATIONS: tuple[tuple[str, datetime | None], ...] = (
    ("BASELINE_ADMISSION", None),
    ("SELECTIVE_ADMISSION_V1", datetime(2026, 10, 8, 3, 30, tzinfo=timezone.utc)),   # 09:00 IST Oct 8
)


def admission_population(batch_at: datetime) -> str:
    """The admission policy in force when a candidate was admitted at ``batch_at``."""
    label = ADMISSION_POPULATIONS[0][0]
    for name, started in ADMISSION_POPULATIONS[1:]:
        if started is not None and batch_at >= started:
            label = name
    return label


UNATTRIBUTED = "UNATTRIBUTED"


def _unavailable_population(record: Mapping[str, Any]) -> str:
    """The population of a candidate whose path could not be built, from its
    admission clock; store-level gaps without one are ``UNATTRIBUTED``."""
    raw = record.get("recorded_at")
    try:
        at = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return UNATTRIBUTED
    if at.tzinfo is None:
        return UNATTRIBUTED
    return admission_population(at)


def build_cohort_reports(candidates: Sequence[Candidate], manifest: Mapping[str, Any], *,
                         deadline_policy: str,
                         unavailable: Sequence[Mapping[str, Any]] = ()) -> dict[str, Any]:
    """One frozen allocation report per admission population, never pooled."""
    by_population, keys = {}, {}
    for name, _started in ADMISSION_POPULATIONS:
        chosen = [item for item in candidates if admission_population(item.batch_at) == name]
        missing = [dict(record) for record in unavailable if _unavailable_population(record) == name]
        keys[name] = sorted(item.admission_key for item in chosen)
        by_population[name] = build_allocation_report(chosen, manifest, deadline_policy=deadline_policy,
                                                      unavailable=missing)
    return {
        "schema": SCHEMA,
        "admission_populations": [{"name": name, "from": None if started is None else started.isoformat(),
                                   "candidates": len(keys[name]), "admission_keys": keys[name],
                                   "unavailable": len(by_population[name]["unavailable_candidates"])}
                                  for name, started in ADMISSION_POPULATIONS],
        "by_population": by_population,
        "unattributed_unavailable": [dict(record) for record in unavailable
                                     if _unavailable_population(record) == UNATTRIBUTED],
        "qualification": "NOT_ASSESSED", "authorization_effect": "NONE",
    }


def _main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Momentum allocation holdout per admission population")
    parser.add_argument("--db", required=True, help="engine SQLite (opened read-only)")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    try:
        from momentum_paper_path_adapter import build_allocation_candidates
        manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
        built = build_allocation_candidates(args.db)
        value = build_cohort_reports(built["candidates"], manifest,
                                     deadline_policy=built["deadline_quote_policy"],
                                     unavailable=built["unavailable_candidates"])
        write_study_report_once(value, args.output)
    except (ExitStudyError, OSError, ValueError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    raise SystemExit(_main())
