# Review of a6d8307 and 4416229

## Verdict

Substantial improvement, but not ready for strategy qualification or a blanket production green light. Evidence-only components can be considered for staged deployment after their normal integration checks; the new research path must remain explicitly unqualified. No Production edits or live messages/orders were performed.

Reviewed contract normalization, chronological replay, archive adapter, held-out summaries and existing replay sequence. 34 selected tests passed across chronological/holdout/archive replay, basic replay/reports, completed bars, telemetry and reconciliation. Full application tests and new Production measurements were not performed in this review.

## Small correction implemented

Chronological deadline trigger now converts packet clocks to IST. Archive packets use UTC; previously 09:45 UTC was compared numerically against 15:15, so an otherwise executable management-deadline exit could be missed. Added UTC-input regression with quiet price thresholds; it closes at the exchange deadline.

## Improvements accepted at code-review level

Real Kite DataFrame contract normalization and stronger instrument provenance were added. Replay now has structured leg metadata and broader configuration identity. Reconciliation includes five-source internal summaries. Scheduler now has in-flight markers. Chronological and held-out helpers exist. These are meaningful changes, not just relabelled warnings. A passing helper test is not proof of full production integration or profitable advice.

## Remaining code corrections (do not wait for market data)

1. P0 research correctness: replay_intraday_debit_spread returns exit_observation_missing before validating entry debit positivity/width. The chronological runner interprets that return as an accepted active entry. Move all entry economics checks before the missing-exit branch. Test nonpositive debit and over-width debit with no exit, and prove a later valid signal is not blocked by a false active entry.
2. P1 signal provenance: archive adapter accepts a caller-provided signal mapping plus a 64-character digest. This does not verify artifact content, policy identity, source cutoff or generation time. Implement a loaded, content-verified deterministic signal artifact tied to source observations and receipt cutoffs. Propagate its identity into replay/result manifests, not only an outer adapter object. Test tampered contents, future source packets and wrong policy.
3. P1 holdout integrity: HeldOutCase labels can declare a different index/policy/date from the underlying replay. The comparison checks membership of the supplied label but not replay identity. Bind underlying/policy/session into typed replay results, validate labels against them, parse actual session dates, require training precede holdout, and expose missing declared sessions/policy groups. Reject duplicate opportunities and missing/non-finite CLOSED P&L instead of converting absent P&L to zero. Test relabelled training results and omitted losing/unresolved sessions.
4. P1 execution model: adding a delay to the clock while reusing the earlier book is a modelling assumption, not evidence the book remained executable at execution. Use subsequent observations for delayed fills or mark unavailable; retain partial-leg execution uncertainty. The current finite-sample simultaneous two-leg model must not be presented as confirmed manual execution.
5. P1 operational work remains in code: DB stage timing and capacity isolation are explicitly still pending in the implementation record. Measurements are needed to tune capacity, but bounded failure tests, accurate queue/lock telemetry and exit-priority integration do not require a broker statement or a new trading session.
6. Prior partner review gaps are not closed by these commits: independent management when entry-chain fetching fails, conditional protection independent of direction, current read-time freshness and quiet-tick qualification visibility. Track these separately; research upgrades do not repair the delivery pipeline.

## Genuine evidence dependencies

- New active-leg sessions and reliable exit observations for execution-quality research.
- Chronologically held-out observations after policy freezing; do not retroactively designate tuned sessions unseen.
- Next-session measured provider/DB/archive waits and missed eligible invocations for contention conclusions.
- Actual owner broker statement/account scope for external reconciliation, not partner credentials.

Internal discrepancy investigation can proceed from retained ledgers and positions without external statements; missing linkage must remain explicit. Implementing a deterministic strategy artifact is development/research work, not something the owner must invent. Merely recording its hash is insufficient.

## Next implementation sequence

A. Fix entry acceptance ordering and holdout/result identity contracts with adversarial regression tests.
B. Verify signal-artifact content and causal input linkage; record honest execution model limitations.
C. Complete partner-management freshness gaps and bounded scheduling integration.
D. Deploy reviewed evidence changes through GitHub with release verification; collect the required actual-session measurements.
E. Publish five internal reconciliation finding sheets and genuinely held-out strategy reports. External statement evidence stays a separate status.

Qualification remains blocked until both code contracts and genuine evidence pass review. Preserve positive and negative results. No claim of tomorrow's tips or profitable strategy follows from these commits.
