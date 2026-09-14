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
from datetime import datetime, timezone
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

    The capture document's bounded phase lives at
    ``rows[i].classifier_phase`` for each row i (per the
    J.3 schema in ``tools/j2_cas_probe.py::CAPTURE_JSON_SCHEMA``).
    A capture may have multiple rows (one per probed symbol);
    the gate aggregates by phase so a multi-row capture can
    increment more than one branch's counter in a single
    review. The first row's phase wins for the per-file
    "is this a CAS capture" classification.
    """
    try:
        doc = json.loads(capture_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(doc, dict):
        return None
    rows = doc.get("rows")
    if not isinstance(rows, list) or len(rows) == 0:
        return None
    # The first row's classifier_phase is the canonical one
    # for the capture; rows after the first are documented to
    # be the same underlying under different observation
    # parameters.
    first = rows[0]
    if not isinstance(first, dict):
        return None
    phase = first.get("classifier_phase")
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


# [WORKFLOW-J.10.CLOSURE 2026-09-13] Operator-facing SUMMARY.md
# surface. The gate's verdict is rendered into a persistent
# markdown file at ``docs/j2_captures/SUMMARY.md`` (the path is
# parameterised so tests can write to a tmp_path). This is the
# audit surface for the J.10 gate -- without SUMMARY.md, the
# verdict is invisible to anyone who isn't running the CLI.
#
# The contract is fail-closed: ``update_summary`` ALWAYS reflects
# the gate's ``verdict`` field. If the operator mistakenly thinks
# they have all 6 branches captured and ``update_summary`` would
# have produced REACHABLE, but the gate disagrees, the SUMMARY
# shows UNREACHABLE. The SUMMARY can never claim more than the
# gate can prove.

_SUMMARY_TEMPLATE = """\
# J.10 CAS-branch reachability SUMMARY

This file is the persistent, human-readable surface for the J.10
gate's verdict. It is regenerated by
``python -m tools.cas_reachability_check --update-summary``
(and by ``tools/j2_capture_review.py`` happy-path) so operators
see the latest verdict without re-running the CLI.

**Captures directory**: {captures_dir}
**Generated at**: {generated_at_utc} UTC

## Verdict

**{verdict}** -- coverage **{coverage_pct:.1f}%**
({captures_scanned} captures scanned, {captures_skipped} skipped
as malformed / non-bounded).

## Captured per branch

| Branch | Captures |
|---|---|
{branch_rows}{missing_section}## How to add captures

1. Run the staging-only probe:
   ```bash
   python -m tools.j2_cas_probe.py \
       --symbols RELIANCE --observation-at 15:22:00 IST \
       --output docs/j2_captures/2026-09-10/RELIANCE_15_22.json
   ```
2. Validate the capture:
   ```bash
   python -m tools.j2_capture_review.py \\
       docs/j2_captures/2026-09-10/RELIANCE_15_22.json
   ```
   A passing review auto-updates this SUMMARY via ``update_summary``.
3. Repeat for each of the 6 required branches (5 CAS
   sub-windows + DERIVATIVES_CAS_ALIGNED). The gate flips to
   REACHABLE when every branch has at least one capture.

## What the gate enforces

Per plan §14, ``auction-imbalance research is excluded`` and
``any auction-based strategy is separate research with auction
execution semantics, not an extension of a continuous-market
fill model``. The gate exists so that future auction-aware code
MUST pass ``tools/cas_reachability_check.py`` before shipping.
This SUMMARY is the audit trail.
"""


def _format_missing_section(missing_phases: list[str]) -> str:
    """Render the missing-branches section. Returns an empty
    string when the gate is REACHABLE (no missing branches);
    returns a markdown ``## Missing branches`` block when
    UNREACHABLE.
    """
    if not missing_phases:
        return ""
    lines = ["", "## Missing branches", ""]
    lines.append("The gate is **UNREACHABLE** until each of the")
    lines.append("following branches has at least one capture:")
    lines.append("")
    for phase in missing_phases:
        lines.append(f"- [ ] {phase}")
    lines.append("")
    return "\n".join(lines) + "\n"


def update_summary(
    report: dict[str, Any],
    summary_path: Path,
    *,
    captures_dir: Path | None = None,
) -> None:
    """[WORKFLOW-J.10.CLOSURE 2026-09-13] Render the gate's
    verdict into ``summary_path`` as a deterministic markdown
    document.

    Pure / total contract:
      * Never raises (the gate's verdict is always available;
        a corrupt / absent captures directory produces an
        UNREACHABLE report).
      * The SUMMARY always reflects ``report['verdict']`` --
        no fail-open path. If the gate is UNREACHABLE, the
        SUMMARY cannot claim REACHABLE.
      * Idempotent: running twice with the same report produces
        the same bytes except for the ``Generated at`` line.

    The ``captures_dir`` argument is optional; when provided, it
    is rendered into the SUMMARY so operators know where the
    source data lives. The default falls back to the standard
    ``docs/j2_captures/`` path.
    """
    summary_path = Path(summary_path)
    summary_path.parent.mkdir(parents=True, exist_ok=True)

    # Build the per-branch table rows.
    branch_rows_lines: list[str] = []
    for phase, count in report["captured_phases"].items():
        marker = "yes" if count > 0 else "no"
        branch_rows_lines.append(
            f"| {phase} | {count} ({marker}) |"
        )
    branch_rows = "\n".join(branch_rows_lines) + "\n" if branch_rows_lines else ""

    # Build the missing-branches section.
    missing_section = _format_missing_section(report["missing_phases"])

    # Compose the SUMMARY body. Use the gate's verdict directly;
    # never coerce it. ``captures_dir`` defaults to the
    # canonical J.3 path.
    captures = (
        str(captures_dir) if captures_dir is not None
        else "docs/j2_captures/"
    )
    body = _SUMMARY_TEMPLATE.format(
        captures_dir=captures,
        generated_at_utc=datetime.now(timezone.utc).isoformat(),
        verdict=report["verdict"],
        coverage_pct=report["coverage_pct"],
        captures_scanned=report["captures_scanned"],
        captures_skipped=report["captures_skipped"],
        branch_rows=branch_rows,
        missing_section=missing_section,
    )
    summary_path.write_text(body, encoding="utf-8")
