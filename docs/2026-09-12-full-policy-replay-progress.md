# Full-policy replay integration checkpoint

Dev only. Production has not been changed. This is not a release or strategy qualification approval.

## Current-state finding

At resumption Dev HEAD was 841131e, containing e043276 and 5a565df. The previously described unfinished partner_full_policy_replay.py was absent, so it was recreated against the checked-out interfaces.

## Implemented

- Recompute the deployed signal, candidate and profile validation; replay only the selected spread contracts.
- Require matching evaluation/archive master identity and the archived decision-time bid/ask/depth to match the selected candidate.
- Preserve archive partial-batch diagnostics; missing decision books and missing public lifecycle observations are explicit insufficient-evidence results.
- Bind exits to candidate underlying invalidation/target levels and management deadline. Bound delayed-entry validity by candidate expiry and retain at least its estimated round-trip cost.
- Consume independent public events in receipt order. Keep a breach pending through price recovery or missing books; measure exit delay from its actual receipt. Duplicate/unordered events and mixed embedded/independent evidence are rejected.
- Cancel a delayed entry when invalidation or target is crossed before execution. Reject an already-crossed thesis or missing/stale initial public observation.
- Recheck the actual execution debit plus round-trip fee reserve and entry slippage against the tighter declared/profile capital and risk limits. Bind entry timing to the profile window. Cost-sensitivity runs preserve independent public events across every scenario.
- Every output remains diagnostic, with qualification, delivery and order authority false.
- Replay accepts fingerprinted public capture paths, recomputes the closed-bar observation from saved OHLCV, preserves actual response receipt, and records source fingerprints/provenance. Mixed archive/caller observations, duplicate captures, stale observations and scope/hash mismatches are rejected. Source coverage remains explicitly SUPPLIED_CAPTURES_ONLY.

## Verification

53 tests passed across connector, chronological replay, full-policy evaluator and archive adapter. A new unmocked integration fixture builds raw CSV/canonical masters and hashed quote packets, runs the real signal/candidate builder and archive adapter, and reaches a real replay invalidation exit. Altered normalized quotes remove the decision book. Other regressions cover between-book breach/recovery, actual-receipt exit delay, cancellation before delayed entry, unresolved breach without a later book, execution-time capital/risk breaches, and cost reserves. Synthetic fixtures do not establish Production evidence completeness or profitability.

## Required next work

Broader checkpoint validation: 88 tests passed across full-policy replay, qualification/review, public capture, CLI qualification, signal artifacts, research, base replay, holdout, chronology and archive adapter.

Public-capture follow-up: the same broader suite now passes 91 tests, including verified capture-to-replay integration and late-receipt/stale/scope/hash checks.

1. Validate independent public-stream completeness against archive provenance and coverage manifests; sparse supplied events alone cannot establish an uninterrupted lifecycle. Cost-sensitivity stream propagation is implemented.
2. Extend delayed execution validation to contemporary spread-quality rules and cost-model calibration. Cost-inclusive profile capital/risk checks at the changed book are implemented; they do not establish the accuracy of fee/slippage assumptions.
3. Support proven pre-decision books and explicit decision availability clocks rather than requiring exact equal timestamps. Never move receipts backwards to manufacture causality.
4. Extend the unmocked master/quote integration fixture with archived public-input provenance, missing-leg, restart, sparse-book and deadline cases. Public observations in the current integration test are explicit fixture inputs, not loaded from a verified public archive.
5. Bind public input provenance, expose the connector through the offline CLI, and retain immutable outcome/evidence reports. Add held-out review integration only after complete and unresolved outcomes are represented faithfully.
6. Run the full release acceptance suite before promotion. The 88-test research checkpoint is not full release acceptance. Evaluate genuine collected sessions afterwards; no fixed number of days guarantees qualification.

The connector is not scheduled, does not register qualifications, and does not enable partner messages. The existing intraday profile does not need to be resubmitted for this development work.
