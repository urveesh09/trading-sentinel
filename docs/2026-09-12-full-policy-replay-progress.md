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
- `research_cli replay-full-policy` now loads a decision capture, verified candidate/master bundle, session quote journals, explicit execution assumptions and lifecycle capture paths. Reports are fingerprint-checked and atomically created without overwrite; identical retries are allowed.
- Replay accepts fingerprinted public capture paths, recomputes the closed-bar observation from saved OHLCV, preserves actual response receipt, and records source fingerprints/provenance. Mixed archive/caller observations, duplicate captures, stale observations and scope/hash mismatches are rejected. Source coverage remains explicitly SUPPLIED_CAPTURES_ONLY.
- Directional candidate construction now passively retains the full instrument map, observed option/futures chain and explicit profile after public-management work. It records a conservative post-acquisition receipt timestamp, with capture success/failure counters and isolated errors. Profile sequence fields are normalized on reload; optional futures quote evidence is preserved.

## Verification

53 tests passed across connector, chronological replay, full-policy evaluator and archive adapter. A new unmocked integration fixture builds raw CSV/canonical masters and hashed quote packets, runs the real signal/candidate builder and archive adapter, and reaches a real replay invalidation exit. Altered normalized quotes remove the decision book. Other regressions cover between-book breach/recovery, actual-receipt exit delay, cancellation before delayed entry, unresolved breach without a later book, execution-time capital/risk breaches, and cost reserves. Synthetic fixtures do not establish Production evidence completeness or profitability.

## Required next work

Broader checkpoint validation: 88 tests passed across full-policy replay, qualification/review, public capture, CLI qualification, signal artifacts, research, base replay, holdout, chronology and archive adapter.

Public-capture follow-up: the same broader suite now passes 91 tests, including verified capture-to-replay integration and late-receipt/stale/scope/hash checks.

Candidate-capture follow-up: 64 focused capture/orchestrator/connector/qualification tests passed, including archive round-trip, identical retry and rejection of late chain evidence at the earlier tick clock. One existing Starlette lifespan deprecation warning remains. Capture orchestration timing/load and conditional-protection capture still require further coverage; this is not release acceptance.

Candidate capture acceptance checkpoint: 128 combined research/orchestrator tests passed. Explicit two-index tests establish that public management precedes capture and simulated disk failure does not stop candidate construction. CLI verifies fingerprints of content-addressed candidate captures before parsing their evidence. This proves ordering/failure isolation in fixtures, not bounded disk latency or Production load. Conditional-protection capture and acquisition/decision clock separation remain pending.

A/B follow-up: Dev now uses `FROZEN_COMPLETED_BAR_CUTOFF_V1`. Public-bar eligibility stays fixed at tick start, while actual public/chain request and receipt clocks and the later candidate-construction clock are retained. V2 public/candidate captures share run/account/index identity; legacy v1 artifacts are unchanged. A per-attempt SQLite journal records independent public/candidate outcomes and requested/received contracts, and readiness derives typed session gaps instead of counting files. Conditional-protection inputs use the same capture schema. Archive wait is bounded and a timeout is explicitly outcome-unknown. Focused acceptance passed 185 tests. The scheduler coroutine leak is also fixed with a 41-test RuntimeWarning-sensitive suite; Production observation remains pending.

1. Connect the new per-attempt schedule coverage to full-policy review so sparse supplied events cannot establish an uninterrupted lifecycle. Cost-sensitivity stream propagation is implemented.
2. Extend delayed execution validation to contemporary spread-quality rules and cost-model calibration. Cost-inclusive profile capital/risk checks at the changed book are implemented; they do not establish the accuracy of fee/slippage assumptions.
3. Proven pre-decision books and explicit frozen-cutoff/acquisition/construction clocks are supported in Dev. Constituent quote timestamps remain unchanged, and deadline/session crossings are suppressed. Verify this behavior after release; never move receipts backwards to manufacture causality.
4. Extend the unmocked master/quote integration fixture with archived public-input provenance, missing-leg, restart, sparse-book and deadline cases. Public observations in the current integration test are explicit fixture inputs, not loaded from a verified public archive.
5. Public input loading, offline CLI and immutable reports are implemented. Add held-out review integration only after complete and unresolved outcomes and coverage are represented faithfully.
6. Run the full release acceptance suite before promotion. The 88-test research checkpoint is not full release acceptance. Evaluate genuine collected sessions afterwards; no fixed number of days guarantees qualification.

The connector is not scheduled, does not register qualifications, and does not enable partner messages. The existing intraday profile does not need to be resubmitted for this development work.

## Offline command

Run from the Dev python-engine directory with its configured Python environment. Replace the example paths and digest with real retained evidence. Repeat `--public-capture` for every relevant observation in the session. The command reads the exchange-local decision session's quote journal automatically.

```powershell
.\winvenv\Scripts\python.exe -m research_cli replay-full-policy `
  --archive-root "C:\research-archive" `
  --underlying NIFTY `
  --public-input "C:\research-archive\partner-public-inputs\SESSION\NIFTY\DECISION_SHA.json" `
  --public-capture "C:\research-archive\partner-public-inputs\SESSION\NIFTY\DECISION_SHA.json" `
  --candidate-evidence "C:\research-inputs\observed-chain-and-profile.json" `
  --master-sha256 "ACTUAL_RAW_MASTER_SHA256" `
  --policy "C:\research-inputs\execution-policy.json" `
  --output "C:\research-results\unique-run.json"
```

Execution policy JSON uses ChronologicalPolicy fields, with duration fields expressed in seconds. Explicitly declare measured fees, slippage and manual delay; zero defaults are not evidence of zero real-world costs. Candidate contracts are selected by the actual strategy, not hand-picked by this command. Output state CLOSED describes a simulated result; it is never a profitability qualification. Exit code 0 means the diagnostic completed, including NO_FILL/UNRESOLVED/INSUFFICIENT_EVIDENCE. Invalid input or conflicting output returns 2.

The end-to-end CLI fixture checks an unresolved result with only an initial public capture, identical retries, and rejection of altered-cost overwrite. It does not prove an operational session has complete evidence.
