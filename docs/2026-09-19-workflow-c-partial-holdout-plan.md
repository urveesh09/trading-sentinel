# Workflow C.C2.HOLDOUT — modeled partial-fill held-out provenance

**Status:** IMPLEMENTED_TESTED_AND_PUSHED_DEV. Implementation commit `6348fdb`
and verification receipt `070e9c0` were pushed to
`origin/codex/production-correction-hedge-p0`. Production was not changed.

## Problem

The full-policy evaluator returns pre-decision asymmetric execution as
`CLOSED / partial_fill_modeled`, but it returns before emitting the replay
payload required by `heldout_case_from_full_policy_report`. Consequently the
outcome cannot enter the held-out comparison, and a future hand-built adapter
could accidentally make modeled partial P&L indistinguishable from a fully
executed two-leg close.

## Files and contracts

- `python-engine/partner_full_policy_replay.py`: emit a fingerprinted
  chronological payload for the modeled partial outcome. It remains CLOSED,
  as selected by the operator, but declares a separate
  `MODELED_PARTIAL_FILL_V1` economics contract and does not fabricate full
  cost-sensitivity evidence. Correct the inherited execution-economics defect:
  mid-plus-2bps is an adverse entry-slippage cost (never a positive profit),
  and an unpriceable missing leg fails closed instead of becoming a zero-P&L
  close. Naive/malformed asymmetric receipt clocks are excluded safely.
- `python-engine/intraday_spread_holdout.py`: validate the modeled-partial
  attribution against the replay and source report; retain its provenance on
  `HeldOutCase`; publish `full_closes` and `modeled_partial_closes` whose sum
  must equal `closed`.
- `python-engine/partner_qualification_review.py`: verify the split and expose
  it in the review package. Modeled partials do not upgrade the held-out
  evidence contract to `VERIFIED_FULL_POLICY_REPORTS` without cost-stress and
  archived-public-scope evidence.
- Focused tests pin actual evaluator-to-heldout flow, tamper rejection,
  aggregate invariants, and qualification propagation.

## Acceptance checks

1. Existing focused Workflow C baseline remains green (54 tests before the
   slice).
2. A real `replay_full_policy` modeled-partial result is accepted by the
   held-out adapter and counted once as CLOSED and once as modeled partial.
   Its modeled execution P&L is non-positive; a degenerate book cannot close.
3. Normal CLOSED outcomes count as full closes; mixed groups satisfy
   `full_closes + modeled_partial_closes == closed` independent of input order.
4. Rehashed contradictions in partial flag/reason/diagnostics or aggregate
   counts fail closed.
5. The qualification package exposes both close counts and cannot mistake the
   modeled-partial artifact for verified full-policy economics.
6. Focused tests, broader Workflow C regression, compilation, atlas generation
   and documentation consistency checks pass.

## Rollout and rollback

This is Dev-only diagnostic/research schema output. It changes no database,
configuration, broker call, delivery authority, retained artifact, or
Production file. Promote through GitHub. Consumers must tolerate the two new
additive group fields and two additive ordered-outcome fields. Roll back the
single implementation commit to restore the prior non-ingestible behavior;
existing immutable reports remain readable.

## Remaining Workflow C work after this slice

Real multi-session archived public captures, sufficient predeclared held-out
coverage, exchange-calendar/settlement evidence, and human qualification are
operator/runtime evidence tasks. This slice does not prove profitability,
deployment, delivery readiness, or actual broker fills.

## Verification receipt

- Focused model/full-policy/held-out/review: 90 passed in 3.82s.
- Broader qualification/held-out group: 134 passed in 4.34s.
- Workflow C/research/orchestrator group: 226 passed with one existing
  Starlette lifespan deprecation warning in 8.43s. The same command with
  `-W error` stopped at orchestrator import after 196 passes because that known
  deprecation became an error; it did not expose a slice failure.
- Whole Python engine: 4,069 passed, four skipped, 42 documented deprecation
  warnings in 214.71s. JUnit:
  `C:/Users/Urveesh/AppData/Local/Temp/sentinel-workflow-c-partial-holdout-20260919.xml`.
- Atlas regenerated at 202 modules. Compilation and `git diff --check` pass.
