"""[WORKFLOW-J.10 2026-09-13] CAS-branch reachability gate.

Plan §14 says ``auction-imbalance research is excluded`` and
``any auction-based strategy is separate research with auction
execution semantics, not an extension of a continuous-market
fill model``. J.10 ships the **gate** that enforces this
boundary -- not the strategy itself.

The gate answers: "have the CAS sub-window branches of
``classify_session_phase`` been exercised by real production
call sites?"

It walks ``docs/j2_captures/`` (the J.3 receipt directory) and
emits a structured verdict:

    {
        "verdict": "REACHABLE" | "UNREACHABLE",
        "captured_phases": {"PHASE": count, ...},
        "missing_phases": ["PHASE", ...],
        "coverage_pct": float,  # % of CAS branches with >=1 capture
        "captures_scanned": int,
        "captures_skipped": int,  # malformed / non-bounded
    }

The gate is pure / total: never raises, returns the documented
shape for any filesystem state.

Coverage requirement: every branch in
``CAS_BRANCHES_REQUIRING_EVIDENCE`` must have >=1 capture.
CONTINUOUS_TRADING / PRE_MARKET / CLOSED are NOT in this list
because they are exercised by every market-day signal arrival
and don't need separate J.3 broker-behaviour evidence.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from market_calendar import _VALID_SESSION_PHASES


# CAS sub-window branches + DERIVATIVES_CAS_ALIGNED that need
# real broker-behaviour evidence before any auction-aware
# strategy can be built on top of ``classify_session_phase``.
# CONTINUOUS_TRADING / PRE_MARKET / CLOSED are exercised by
# every market-day signal; they don't need separate J.3 captures.
CAS_BRANCHES_REQUIRING_EVIDENCE: tuple[str, ...] = (
    "CAS_REFERENCE_PRICE_WINDOW",
    "CAS_ORDER_ENTRY",
    "CAS_LIMIT_ENTRY_ONLY",
    "CAS_MATCHING",
    "CAS_POST",
    "DERIVATIVES_CAS_ALIGNED",
)

# Defensive: if _VALID_SESSION_PHASES ever drops a CAS phase
# (a future slice removing CAS_POST, for instance), the gate
# must surface the drift as a category-1 invariant failure.
# ``REQUIRED_PHASES_SUBSET_OF_VALID`` is the assertion.
_REQUIRED_PHASES_SUBSET_OF_VALID: bool = all(
    phase in _VALID_SESSION_PHASES
    for phase in CAS_BRANCHES_REQUIRING_EVIDENCE
)
if not _REQUIRED_PHASES_SUBSET_OF_VALID:
    raise RuntimeError(
        "CAS_BRANCHES_REQUIRING_EVIDENCE includes a phase that "
        "is not in market_calendar._VALID_SESSION_PHASES; the "
        "gate's required-set and the mirror's bounded set "
        "have drifted. Update both in lockstep."
    )


def _safe_phase_from_capture(capture_path: Path) -> str | None:
    """Read a single J.3 capture and return its documented
    classifier phase. Returns None for malformed / non-bounded
    captures (the gate counts them as skipped, not fatal).
    """
    try:
        doc = json.loads(capture_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    # J.3 capture schema: classifier.phase is the bounded
    # string produced by ``classify_session_phase``. Some
    # early captures may have classifier at the top level
    # -- be lenient about that for backward compat.
    phase = None
    if isinstance(doc, dict):
        classifier = doc.get("classifier")
        if isinstance(classifier, dict):
            phase = classifier.get("phase")
        if phase is None:
            phase = doc.get("phase")
    if not isinstance(phase, str):
        return None
    if phase not in _VALID_SESSION_PHASES:
        return None
    return phase


def cas_reachability_report(captures_dir: Path) -> dict[str, Any]:
    """Walk ``captures_dir`` and produce the reachability
    verdict. Pure / total -- never raises.

    Layout (per docs/j2_captures/README.md):
        captures_dir/
            YYYY-MM-DD/
                RELIANCE_15_10.json
                RELIANCE_15_17.json
                ...
            SUMMARY.md                       (ignored)
            README.md                        (ignored)
            review_log.md                    (ignored)

    Anything that does not end in ``.json`` is ignored.
    Anything that is a J.3 capture but malformed / non-bounded
    is counted as ``captures_skipped`` and does not contribute
    to coverage.
    """
    captured: dict[str, int] = {
        phase: 0 for phase in CAS_BRANCHES_REQUIRING_EVIDENCE
    }
    captures_scanned = 0
    captures_skipped = 0

    captures_root = Path(captures_dir)
    if not captures_root.exists():
        missing = list(CAS_BRANCHES_REQUIRING_EVIDENCE)
        return {
            "verdict": "UNREACHABLE",
            "captured_phases": {phase: 0 for phase in captured},
            "missing_phases": missing,
            "coverage_pct": 0.0,
            "captures_scanned": 0,
            "captures_skipped": 0,
        }

    for capture_path in sorted(captures_root.rglob("*.json")):
        captures_scanned += 1
        phase = _safe_phase_from_capture(capture_path)
        if phase is None:
            captures_skipped += 1
            continue
        if phase in captured:
            captured[phase] += 1

    missing = [phase for phase, count in captured.items() if count == 0]
    coverage_pct = round(
        100.0 * (len(CAS_BRANCHES_REQUIRING_EVIDENCE) - len(missing))
        / len(CAS_BRANCHES_REQUIRING_EVIDENCE),
        1,
    )
    verdict = "REACHABLE" if not missing else "UNREACHABLE"

    return {
        "verdict": verdict,
        "captured_phases": captured,
        "missing_phases": missing,
        "coverage_pct": coverage_pct,
        "captures_scanned": captures_scanned,
        "captures_skipped": captures_skipped,
    }


def format_report(report: dict[str, Any]) -> str:
    """Human-readable rendering of a reachability report.
    Operator-facing: shows the verdict, coverage percentage,
    and missing phases.
    """
    lines = [
        f"J.10 CAS-branch reachability: {report['verdict']}",
        f"  coverage:        {report['coverage_pct']:.1f}%",
        f"  captures scanned: {report['captures_scanned']}",
        f"  captures skipped: {report['captures_skipped']}",
        "  captured per branch:",
    ]
    for phase, count in report["captured_phases"].items():
        marker = "+" if count > 0 else "-"
        lines.append(f"    [{marker}] {phase}: {count}")
    if report["missing_phases"]:
        lines.append("  missing branches (need at least 1 capture each):")
        for phase in report["missing_phases"]:
            lines.append(f"    [ ] {phase}")
    return "\n".join(lines)


def write_report(report: dict[str, Any], out_path: Path) -> None:
    """Persist the report as JSON. Idempotent for the same
    input -- writes the same shape on every call.
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(report, indent=2, sort_keys=True),
        encoding="utf-8",
    )
