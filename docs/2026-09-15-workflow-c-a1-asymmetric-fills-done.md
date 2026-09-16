# Workflow C.A1 — asymmetric-fills diagnostic

## What landed

|| File | Type | Purpose |
|---|---|---|---|
| `python-engine/intraday_spread_archive_adapter.py` | source (extended) | New `asymmetric_batches` field on `ArchiveObservationBuild`; new `_has_executable_depth` helper; new `ASYMMETRIC_EXECUTION_QUALITY` diagnostic in `build_spread_observations` |
| `python-engine/partner_full_policy_replay.py` | source (extended) | New `asymmetric_batches` key in the report dict; new `asymmetric_execution_quality_before_decision` rejection reason (fail-closed) |
| `python-engine/tests/test_intraday_spread_archive_adapter.py` | test (extended) | 15 new tests (6 asymmetric-fill scenarios + 9 executable-depth helper unit tests) |
| `python-engine/tests/test_partner_full_policy_replay.py` | test (extended) | 2 new tests covering the fail-closed report path and the post-decision transparency case |
| `docs/2026-09-15-workflow-c-a1-asymmetric-fills-done.md` | doc (new) | This file |

## The shift in defensive posture

The plan row at `NEXT_AGENT_PLAN.md:197` flagged "asymmetric actual fills are not modeled" as an unresolved C-workstream item. Previously:

- A multi-leg spread with one executable leg and one insufficient-depth leg was **silently** rejected at the replay layer with the generic `book_not_executable_for_full_lot` reason.
- The operator couldn't attribute the rejection to a specific leg without re-running the replay.
- The full-policy replay had no path to fail-closed when the asymmetric case hit the decision book.

After this slice:

- The archive layer detects the asymmetric case and surfaces a structured `ASYMMETRIC_EXECUTION_QUALITY` diagnostic naming the executable leg, the insufficient leg, and the observed bid/ask/lot_size on each side.
- The full-policy replay treats a pre-decision asymmetric batch as `INSUFFICIENT_EVIDENCE` (fail-closed), mirroring the existing `partial_book_before_decision` discipline.
- Post-decision asymmetric batches surface in the report for transparency but don't fail the replay.

## Key design choices

- **Distinct from PARTIAL_LEG_OBSERVATION.** A `PARTIAL_LEG_OBSERVATION` means "the leg had no packet at all" (the other leg's event never arrived). An `ASYMMETRIC_EXECUTION_QUALITY` means "both legs have valid packets and both pass the basic `_leg()` validation, but only one leg has executable depth." These are operationally different — a PARTIAL is a missing-packet data gap, an ASYMMETRIC is a liquidity gap on one leg while the other leg is fine.
- **Distinct from CONFLICTING_LEG_OBSERVATION.** A CONFLICTING is per-leg packet contention (multiple distinct valid packets for the same leg at the same receipt time). An ASYMMETRIC is no contention — exactly one valid packet per leg.
- **Distinct from "both legs insufficient" (the symmetric case).** When both legs fail the depth check, the diagnostic does NOT fire — the archive layer constructs the observation and the replay layer rejects the whole pair downstream with `book_not_executable_for_full_lot`. This is the pre-existing behavior; A1 only narrows the diagnostic to the asymmetric case.
- **`_has_executable_depth` is defensive.** It explicitly excludes `bool` from the integer check (Python's `bool` is a subclass of `int`), rejects negative depths, and treats non-positive `lot_size` as not executable.
- **Fail-closed at the report layer.** A pre-decision asymmetric batch is treated as `INSUFFICIENT_EVIDENCE` with reason `asymmetric_execution_quality_before_decision`. The decision cannot claim a fully executable two-leg book at decision time when one leg was thin.
- **Backward-compatible dataclass change.** `asymmetric_batches` defaults to `None` on `ArchiveObservationBuild`. Callers that don't read the field are unaffected. The `tuple(asymmetric) if asymmetric else None` pattern in the constructor keeps the dataclass clean.

## Defensive regression

Workflow C surface (10 test files): **134/134 PASS** in 4.45s (was 117; +17 net for A1).

| Test file | Tests | Δ |
|---|---|---|
| `test_intraday_spread_archive_adapter.py` | 28 | +15 |
| `test_partner_full_policy_replay.py` | 16 | +2 |

0 regressions.

## Operator runbook

The diagnostic surfaces automatically. Operators running the existing CLI:

```bash
python -m research_cli replay-full-policy \
    --archive-root <archive> \
    ...
```

will now see `asymmetric_batches` in the report dict. If a pre-decision asymmetric case is observed, the report's `state` is `INSUFFICIENT_EVIDENCE` and `reason` is `asymmetric_execution_quality_before_decision`. The `asymmetric_batches` list contains entries like:

```json
{
  "received_at": "2026-09-10T04:30:00+00:00",
  "state": "ASYMMETRIC_EXECUTION_QUALITY",
  "executable": ["long"],
  "insufficient": ["short"],
  "depth_by_leg": {
    "long": {"bid_depth": 75, "ask_depth": 75, "lot_size": 75},
    "short": {"bid_depth": 1, "ask_depth": 1, "lot_size": 75}
  }
}
```

so the operator can investigate WHY the insufficient leg was thin.

## Critical invariants preserved

- `PARTIAL_LEG_OBSERVATION` behavior unchanged (still surfaces when a leg has no packet).
- `CONFLICTING_LEG_OBSERVATION` behavior unchanged.
- The replay-layer `book_not_executable_for_full_lot` rejection still fires for the symmetric (both-legs-insufficient) case.
- `ArchiveObservationBuild` is a `frozen=True` dataclass; the new field has a `None` default so existing instantiations are unaffected.
- The plan's other C residuals (held-out determinism pin, manifest drift CLI, etc.) remain on the Category A backlog.
