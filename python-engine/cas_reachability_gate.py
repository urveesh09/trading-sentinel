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

from cas_reachability_dedup import (
    FINGERPRINT_HEX_LENGTH,
    dedup_count,
    fingerprint_of,
)
from cas_reachability_freshness import (
    capture_age_days,
    is_within_max_age,
)


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


def cas_reachability_report(
    captures_dir: Path,
    *,
    max_age_days: float | None = None,
) -> dict[str, Any]:
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

    [WORKFLOW-J.10.FRESHNESS 2026-09-14] ``max_age_days`` is an
    optional freshness filter. When supplied (positive float),
    captures whose ``generated_at_utc`` is older than
    ``now_utc - max_age_days`` are skipped and counted under
    the new ``captures_skipped_stale`` field. The default
    (``None``) preserves the pre-freshness behaviour: every
    capture counts regardless of age. Stale vs malformed are
    distinct categories -- ``captures_skipped`` is for
    "couldn't parse the schema", ``captures_skipped_stale`` is
    for "parsed fine but too old".
    """
    captures: dict[str, int] = {
        phase: 0 for phase in CAS_BRANCHES_REQUIRING_EVIDENCE
    }
    # [WORKFLOW-J.10.CLOSURE 2026-09-14] Per-branch catalog of
    # capture paths. The SUMMARY surfaces this so operators
    # can see exactly which captures back each branch -- the
    # per-branch count alone hides the actual evidence.
    captures_by_branch: dict[str, list[str]] = {
        phase: [] for phase in CAS_BRANCHES_REQUIRING_EVIDENCE
    }
    # [WORKFLOW-J.10.DEDUP 2026-09-14] Per-branch fingerprint
    # tracking. A fingerprint is SHA-256[:16] of the capture
    # bytes; the gate dedups within each branch so a duplicate
    # capture (operator retry, accidental copy) does not silently
    # inflate the branch's count toward the REACHABLE threshold.
    # The dedup is per-branch: the same fingerprint can back
    # TWO branches only when the capture genuinely exercises
    # both (a multi-row capture); the gate's row[0] classifier
    # phase determines the canonical phase, so a fingerprint
    # will never legitimately appear under two distinct branches.
    fingerprints_by_branch: dict[str, list[str]] = {
        phase: [] for phase in CAS_BRANCHES_REQUIRING_EVIDENCE
    }
    # ``fingerprints_by_branch`` records EVERY fingerprint seen
    # under the branch (including duplicates); ``dedup_count``
    # of this list yields the per-branch duplicate count.
    # We only count the first occurrence toward ``captures[phase]``
    # (the REACHABLE threshold); subsequent occurrences are
    # surfaced via ``duplicates_by_branch[phase]`` for audit.
    captures_scanned = 0
    captures_skipped = 0

    captures_root = Path(captures_dir)
    if not captures_root.exists():
        missing = list(CAS_BRANCHES_REQUIRING_EVIDENCE)
        return {
            "verdict": "UNREACHABLE",
            "captured_phases": {phase: 0 for phase in captures},
            "missing_phases": missing,
            "coverage_pct": 0.0,
            "captures_scanned": 0,
            "captures_skipped": 0,
            "captures_by_branch": captures_by_branch,
            "duplicates_by_branch": {
                phase: 0 for phase in CAS_BRANCHES_REQUIRING_EVIDENCE
            },
            "captures_skipped_stale": 0,
        }

    captures_skipped_stale = 0
    for capture_path in sorted(captures_root.rglob("*.json")):
        captures_scanned += 1
        # [WORKFLOW-J.10.FRESHNESS 2026-09-14] Freshness filter.
        # When ``max_age_days`` is set, captures older than the
        # threshold are skipped BEFORE the dedup logic -- the
        # fingerprint and phase parsing are wasted work for a
        # capture that won't count anyway. Stale is its own
        # skip category; malformed captures continue to be
        # counted under ``captures_skipped``.
        if max_age_days is not None:
            age = capture_age_days(capture_path)
            if not is_within_max_age(age, max_age_days):
                captures_skipped_stale += 1
                continue
        phase = _safe_phase_from_capture(capture_path)
        if phase is None:
            captures_skipped += 1
            continue
        if phase in captures:
            # [WORKFLOW-J.10.DEDUP 2026-09-14] Dedup by fingerprint.
            # Two captures with the same fingerprint under the same
            # branch are the same observation -- the operator
            # retried the probe without changing inputs, or the file
            # was accidentally copied. We count the FIRST occurrence
            # toward the branch's coverage; subsequent occurrences
            # increment ``duplicates_by_branch[phase]`` so the SUMMARY
            # surfaces the redundancy but the gate's verdict stays
            # count-driven on UNIQUE observations.
            fp = fingerprint_of(capture_path)
            if fp is None:
                # Unreadable: treat as skipped (defensive -- the
                # file already passed the schema check above so this
                # path is rare; the gate counts it as "we couldn't
                # verify it's a duplicate").
                captures_skipped += 1
                continue
            # ``fingerprints_by_branch`` records EVERY fingerprint
            # seen, including duplicates -- that's what makes
            # ``dedup_count`` work at the end of the loop. We only
            # increment ``captures[phase]`` for the first occurrence.
            fp_already_seen = fp in fingerprints_by_branch[phase]
            fingerprints_by_branch[phase].append(fp)
            if fp_already_seen:
                # Still record the path in captures_by_branch so the
                # catalog surfaces the redundant capture; operators
                # can see "RELIANCE_15_17.json appears twice" and
                # investigate. Path is the FIRST observed order
                # (sorted) so the catalog is deterministic.
                try:
                    rel = capture_path.relative_to(captures_root)
                except ValueError:
                    rel = capture_path
                rel_str = str(rel)
                if rel_str not in captures_by_branch[phase]:
                    captures_by_branch[phase].append(rel_str)
                continue
            captures[phase] += 1
            # Relative path so the SUMMARY is portable; falls
            # back to the absolute path when a non-captures_root
            # capture shows up (defensive).
            try:
                rel = capture_path.relative_to(captures_root)
            except ValueError:
                rel = capture_path
            captures_by_branch[phase].append(str(rel))

    duplicates_by_branch = {
        phase: dedup_count(fingerprints_by_branch[phase])
        for phase in CAS_BRANCHES_REQUIRING_EVIDENCE
    }
    missing = [phase for phase, count in captures.items() if count == 0]
    coverage_pct = round(
        100.0 * (len(CAS_BRANCHES_REQUIRING_EVIDENCE) - len(missing))
        / len(CAS_BRANCHES_REQUIRING_EVIDENCE),
        1,
    )
    verdict = "REACHABLE" if not missing else "UNREACHABLE"

    return {
        "verdict": verdict,
        "captured_phases": captures,
        "missing_phases": missing,
        "coverage_pct": coverage_pct,
        "captures_scanned": captures_scanned,
        "captures_skipped": captures_skipped,
        "captures_by_branch": captures_by_branch,
        "duplicates_by_branch": duplicates_by_branch,
        "captures_skipped_stale": captures_skipped_stale,
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
    ]
    # [WORKFLOW-J.10.FRESHNESS 2026-09-14] Stale-skip count
    # surfaces in the human-readable output when the report
    # used a freshness filter. Default reports (no filter)
    # show 0 here, which is the right answer -- "no captures
    # were filtered out as stale".
    stale = report.get("captures_skipped_stale", 0)
    if stale > 0:
        lines.append(f"  captures skipped (stale): {stale}")
    lines.append("  captured per branch:")
    for phase, count in report["captured_phases"].items():
        marker = "+" if count > 0 else "-"
        lines.append(f"    [{marker}] {phase}: {count}")
    # [WORKFLOW-J.10.CLOSURE 2026-09-14] Per-branch catalog
    # for the human-readable CLI output. Operators running the
    # CLI without --json still see exactly which captures
    # back each branch.
    captures_by_branch = report.get("captures_by_branch", {})
    if any(captures_by_branch.values()):
        lines.append("  captures catalog:")
        for phase, paths in captures_by_branch.items():
            if not paths:
                continue
            lines.append(f"    [{phase}]")
            for p in paths:
                lines.append(f"      - {p}")
    # [WORKFLOW-J.10.DEDUP 2026-09-14] Per-branch duplicates
    # in the human-readable report. The duplicates are
    # informational (verdict is driven by UNIQUE captures);
    # the operator sees them so they can prune if they want.
    duplicates_by_branch = report.get("duplicates_by_branch", {})
    if duplicates_by_branch and any(duplicates_by_branch.values()):
        lines.append("  duplicates (per-branch, by SHA-256[:16] fingerprint):")
        for phase, dup_count in duplicates_by_branch.items():
            if dup_count > 0:
                lines.append(f"    [{phase}] {dup_count} duplicate(s)")
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
as malformed / non-bounded{stale_clause}).

## Captured per branch

| Branch | Captures |
|---|---|
{branch_rows}
{catalog_section}{missing_section}## Duplicate captures

{duplicates_section}

Captures whose SHA-256[:{fingerprint_hex_length}] fingerprint
appears more than once under the same branch are counted ONCE
toward coverage and surfaced here so operators can prune the
redundancy. The gate's verdict is driven by **unique** observations
-- an accidental ``cp RELIANCE_15_17.json RELIANCE_15_17.bak.json``
will not flip the gate to REACHABLE.

## How to add captures

The J.10 gate requires at least one capture from each of the
6 bounded branches. Each branch has a fixed IST window; the
probe command below targets one branch at a time.

| Branch | IST window (start..end) |
|---|---|
| CAS_REFERENCE_PRICE_WINDOW | 15:15:00 .. 15:19:59 |
| CAS_ORDER_ENTRY | 15:20:00 .. 15:24:59 |
| CAS_LIMIT_ENTRY_ONLY | 15:25:00 .. 15:29:59 |
| CAS_MATCHING | 15:30:00 .. 15:34:59 |
| CAS_POST (cash) | 15:35:00 .. 15:59:59 |
| DERIVATIVES_CAS_ALIGNED | 15:30:00 .. 15:39:59 |

1. Run the staging-only probe for each branch. ISO 8601
   timestamps; naive defaults to IST.
   ```bash
   # CAS_REFERENCE_PRICE_WINDOW example
   python -m tools.j2_cas_probe.py \
       --symbols RELIANCE \
       --observation-at 2026-09-14T15:17:00 \
       --output docs/j2_captures/2026-09-14/RELIANCE_15_17.json

   # CAS_ORDER_ENTRY example (different time, same day)
   python -m tools.j2_cas_probe.py \
       --symbols RELIANCE \
       --observation-at 2026-09-14T15:22:00 \
       --output docs/j2_captures/2026-09-14/RELIANCE_15_22.json
   ```
2. Validate each capture:
   ```bash
   python -m tools.j2_capture_review.py \
       docs/j2_captures/2026-09-14/RELIANCE_15_17.json
   ```
   A passing review auto-updates this SUMMARY via
   ``update_summary``.
3. Repeat for each of the 6 required branches (5 CAS
   sub-windows + DERIVATIVES_CAS_ALIGNED). The gate flips to
   REACHABLE when every branch has at least one capture.

A passing review also surfaces in the "Captures catalog"
section above, so operators can confirm without re-running
the CLI.

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


def _format_duplicates_section(duplicates_by_branch: dict[str, int]) -> str:
    """[WORKFLOW-J.10.DEDUP 2026-09-14] Render the
    duplicate-captures section. Returns a single line when every
    branch has zero duplicates (the common case); returns a
    per-branch table otherwise.

    The section is purely informational -- it does not influence
    the gate's verdict. The verdict remains count-driven on
    UNIQUE observations; duplicates are surfaced so the operator
    can prune them if they wish.
    """
    total = sum(duplicates_by_branch.values())
    if total == 0:
        return "_No duplicate captures detected._"
    lines = [
        "The following branches contain duplicate captures "
        "(same fingerprint, multiple files). The gate counts "
        "each branch's UNIQUE captures toward the REACHABLE "
        "threshold; duplicates here are for your audit only.",
        "",
        "| Branch | Duplicates |",
        "|---|---|",
    ]
    for phase, dup_count in duplicates_by_branch.items():
        if dup_count > 0:
            lines.append(f"| {phase} | {dup_count} |")
    return "\n".join(lines)


def _format_catalog_section(captures_by_branch: dict[str, list[str]]) -> str:
    """Render a per-branch catalog of capture paths. Each
    branch is shown as a markdown sub-heading followed by a
    bulleted list of relative paths. Branches with zero
    captures render ``(no captures yet)`` so operators see
    the gap explicitly.

    The catalog is purely informational -- it does not
    influence the gate's verdict (that's still purely
    count-driven per ``captures_by_branch[phase] >= 1``).
    """
    lines = ["", "## Captures catalog", ""]
    lines.append(
        "Each branch lists every capture that contributed to its"
    )
    lines.append("count. Paths are relative to the captures directory.")
    lines.append("")
    for phase, paths in captures_by_branch.items():
        lines.append(f"### {phase}")
        if paths:
            for p in paths:
                lines.append(f"- `{p}`")
        else:
            lines.append("- _(no captures yet)_")
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

    # [WORKFLOW-J.10.CLOSURE 2026-09-14] Per-branch catalog of
    # capture paths. The gate already reads each capture; we
    # just persist the path metadata so the SUMMARY can show
    # operators which captures back each branch. Pure-read.
    catalog_section = _format_catalog_section(
        report.get("captures_by_branch", {})
    )

    # Build the missing-branches section.
    missing_section = _format_missing_section(report["missing_phases"])

    # [WORKFLOW-J.10.DEDUP 2026-09-14] Build the duplicates
    # section from the new ``duplicates_by_branch`` field.
    duplicates_by_branch = report.get(
        "duplicates_by_branch",
        {phase: 0 for phase in CAS_BRANCHES_REQUIRING_EVIDENCE},
    )
    duplicates_section = _format_duplicates_section(duplicates_by_branch)

    # [WORKFLOW-J.10.FRESHNESS 2026-09-14] Build the stale
    # clause for the verdict paragraph. Default reports (no
    # freshness filter) show empty string -- the SUMMARY reads
    # exactly as it did pre-freshness. When the gate filtered
    # stale captures, the SUMMARY shows the count.
    stale_count = int(report.get("captures_skipped_stale", 0))
    stale_clause = (
        f", {stale_count} skipped as stale (--captures-since filter)"
        if stale_count > 0
        else ""
    )

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
        stale_clause=stale_clause,
        branch_rows=branch_rows,
        catalog_section=catalog_section,
        missing_section=missing_section,
        duplicates_section=duplicates_section,
        fingerprint_hex_length=FINGERPRINT_HEX_LENGTH,
    )
    summary_path.write_text(body, encoding="utf-8")
