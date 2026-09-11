# Partner qualification: remaining development plan

## Decision

Further development is required. Waiting alone will accumulate quotes without fixing the mismatch between the research evaluator and the deployed strategy, or ensuring selected contracts remain observable. Continue collection while implementing the work below in Dev. Promote through GitHub; do not edit Production directly or bypass qualification.

Evidence: [completed assessment](research-assessment-2026-09-11/qualification-readiness-report.md), including reproducible results and retention diagnostics. Two sessions contained 61,335 packets but no qualifying advisory outcome sample. Basic book quality is useful evidence, not proof of profitability.

## 1. Full-policy causal research adapter — first priority

- Trace and reuse the actual deployed advisory signal and candidate evaluation functions. Avoid implementing a second, subtly different strategy.
- Replace the limited close-versus-trigger qualification path for this policy with complete opening-range, fresh-crossing, ATR, EMA, relative-volume, regime, stop/target and spread/profile validation.
- Freeze an immutable policy manifest per index and structure; bind configuration, evaluator version, dated contracts and input fingerprints to each decision.
- Retain the exact bars and historical baselines needed by that evaluator. Distinguish provider event time, receipt time and retrospective retrieval. Missing contemporaneous evidence must remain explicit.
- Persist accepted, rejected and no-setup decisions, selected legs and numeric thesis. Do not force opportunities to create a sample.

Acceptance: identical fixed inputs produce matching deployed/research decisions and reasons for both indices. Regression cases cover rejected setups, fresh crossings, missing baselines, future inputs, stale data and contract changes. No simplified artifact can qualify the full policy by name alone.

## 2. Durable selected-leg collection — parallel priority

- Persist candidate/active leg subscriptions by decision, exchange, token and dated master; retain them across restart and rolling strike-universe changes through the declared management deadline.
- Prioritize active legs within provider limits. Make capacity shortfalls and dropped observations explicit; do not silently replace an active contract with a nearby strike.
- Record requested/received tokens, provider/receipt timestamps, gaps and per-leg coverage. Release subscriptions only after all dependent decisions are terminal and the evidence window closes.
- Measure provider stage latency before changing polling intervals. Longer intervals alone can worsen replay coverage. Preserve exit/lifecycle isolation from optional collection work.

Acceptance: move the ATM universe, restart collection and simulate partial responses; original active legs remain requested and missing packets are reported. No unbounded subscription growth or new blocking of public-condition management.

## 3. Costed chronological replay and current-data diagnostic

- Reuse the existing replay CLI/modules where correct. Bind actual policy decisions to both option legs and immutable source evidence.
- Model full-lot executable bid/ask, both-leg costs, manual response delay and cost/slippage sensitivity. Preserve incomplete fills and unresolved exits as explicit outcomes.
- Specify the exact exit cutoff and how the first quote after that cutoff is treated. Never invent an exact-deadline fill or infer an unobserved intrabar stop price.
- Produce separate NIFTY/SENSEX September 10–11 diagnostic reports now, retrieving historical bars where available with provenance. These dates are development data, not an untouched holdout.
- Report unique decisions, rejections, fills/no-fills, missing evidence and coverage; report net outcomes only where supported. Zero trades is a valid diagnostic result.

Acceptance: future packets cannot affect earlier decisions; missing exits cannot become wins or disappear from the denominator; repeated runs are reproducible. Output includes an evidence manifest and limitations, not only summary P&L.

## 4. Qualification review package and operator readiness

- Before examining future evaluation outcomes, freeze held-out session selection, coverage requirements, sample/uncertainty criteria, cost stress and drawdown limits. Document their rationale; quote counts are not independent trade samples.
- Produce a per-index review package binding policy version, source hashes, costs, held-out outcomes, unresolved cases and uncertainty. Reuse existing artifact/qualification registry and authentication boundaries.
- Show distinct readiness states: collection, causal research, outcome coverage, reviewed qualification and Telegram routing. Include concrete blocker reasons and next action.
- Register only genuinely reviewed evidence supporting the exact deployed policy. A negative result remains unqualified; investigate or freeze a revised policy for a new evaluation.

Acceptance: development diagnostics and insufficient evidence cannot authorize delivery; qualification is invalidated by incompatible policy changes. Existing intraday timing and final-dispatch checks continue to pass.

## Delivery sequence and completion boundary

1. Implement and test steps 1–2 in Dev; deploy the verified collection improvement through GitHub while research work continues.
2. Complete step 3 against retained evidence; publish the diagnostic even if no strategy trades are reconstructable.
3. Freeze step 4 criteria, collect future held-out evidence and run the review. This is the part that requires elapsed market sessions, not just coding.
4. Enable actionable recommendations only for an index/policy with a valid reviewed qualification, fresh inputs, an eligible setup and working delivery configuration.

The intraday profile already exists; the partner does not need to supply a personal strategy or broker credentials for this work. A clearly labelled Telegram TEST message can independently verify transport when explicitly authorized; it does not qualify trading advice. No profit or calendar-date guarantee follows from completing the code.

Developer handoff: deliver focused commits, relevant regression results, the two-session diagnostic, and an updated readiness report distinguishing implemented code from missing operational evidence. Do not mark qualification complete merely because tests pass.
