# Second review of the October 13 corrections — October 15, 2026 IST

## Scope and verdict

Read-only review of the new F1–F5 working-tree changes after Dev `8390c87`. The preceding report is `2026-10-15-oct13-fixes-independent-review.md`. No implementation changes were made by this review. Production source and runtime release remain `4fd45f3`; Dev's newest changes were still uncommitted at verification. The author-owned full-suite run and final commit receipt remain unverified here.

The changes improve the software. F2's failure/completion distinction, F3's separate stop time, and F5's execution-identity lookup address the reproduced cases. F1 and F4 are improved but still have the two reproducible gaps below. These are focused corrections to finish before declaring the review closed; no strategy redesign or threshold relaxation is needed.

## Verification

Independent commands from Dev `python-engine` using `winvenv/Scripts/python.exe`:

```text
-m pytest tests/test_oct13_audit_fixes.py -q
46 passed, 3.77s, normal exit

-m pytest tests/test_penny_edge_orchestrator.py tests/test_penny_edge_deferred_fixes.py tests/test_partner_orchestrator.py tests/test_scheduler_tick.py tests/test_scheduler_closures_invoke.py -q
99 passed, 1 skipped, 6.35s, normal exit

-m pytest tests/test_penny_hourly_report.py tests/test_penny_daily_attribution.py -q
40 passed, 1.79s, normal exit
```

**185 passed, 1 skipped**, with the existing Starlette lifespan deprecation warning in the first two runs. The separately running full engine suite was not claimed as verified. Probes used temporary stores, fake providers/executors, fake clocks and no real notification or broker calls.

## Remaining finding R1 — P2: cutoff is not enforced within the entry batch

Source: `python-engine/penny_edge_orchestrator.py:731-734` checks once before `_run_one_leg`; `:331-333` then processes candidates and awaits execution without receiving or checking the cutoff/clock.

The new tests cover a signal scan crossing 15:15 and correctly reject it. They do not cover an execution batch crossing 15:15. Independent probe ran the actual `run_penny_edge_scan` and `_run_one_leg`, with two fake candidates. First admission was 15:14:59; the first fake executor advanced the clock while returning a paper fill. The second admission occurred at **15:16**, and the summary still returned **COMPLETED / 2 entries**.

This is not evidence that the scenario occurred on October 13; it demonstrates that the stated scheduled-entry cutoff contract is not fully enforced.

Correction plan:

- Propagate the scheduled cutoff and injectable decision clock into each leg/candidate admission.
- Recheck after awaited preflight/quote work and before actual paper-fill or broker-submission authority, while keeping manual/replay defaults unchanged.
- Preserve and manage a fill legitimately accepted before the cutoff even if its acknowledgment arrives later; do not discard the position record or stop its exits.
- Acceptance: first candidate's delay prevents a second late admission; quote acquisition crossing the cutoff prevents new submission; an already accepted fill still records and recovers; exits remain operational.

## Remaining finding R2 — P2: enqueue can race delivery and lose the new page

Source: `python-engine/lifecycle_receipts.py:307-314` appends without `_OUTBOX_LOCK`; `:336-367` loads a whole-list snapshot, awaits the HTTP sender, then saves that older snapshot. The delivery lock only serializes delivery calls, not the enqueue operation.

Independent probe:

1. Queue `old-boot`, start its delivery and pause its fake sender before acknowledgment.
2. Queue `new-boot`; the call returns True and the file contains both IDs.
3. Release the old send with a delivered acknowledgment.
4. The file now contains only `old-boot`: **the newly queued restart page is lost**.

The startup receipt task and minute retry task make this interleaving possible in one process. Atomic file replacement prevents a torn JSON file but does not prevent stale-snapshot replacement.

Correction plan:

- Make enqueue and delivery state changes use the same serialized mutation contract, or use transactional row-level storage.
- An acknowledgment must update only its own alert without replacing concurrently added rows.
- Acceptance: pause old delivery, enqueue new page, acknowledge old, then confirm both persisted and the new page eventually delivered; repeat with old-send failure and concurrent delivery callers.
- Retain documented at-least-once semantics when acknowledgment is lost. Do not promise exactly-once delivery.

## What improved and what it means for October 13

Evidence source: Production `docs/2026-10-13-production-deep-audit.md`, especially the financial tables, classic Penny decomposition and acknowledged buyer-message receipts. It is retained observational evidence, not a replay under today's policy.

| October 13 observation | Effect of today's software corrections | Financial interpretation |
| --- | --- | --- |
| Both buyer cards observed invalidation at 11:45, delivered EXIT / Idea closed, then delivered target profit instructions at 14:40/14:50 | Terminal ideas refuse contradictory later messages; separate stop timestamps keep post-exit recovery out of the held path | Reduces contradictory decision support; partner fills and cash savings are unknown |
| 94-minute interruption while a NIFTY spread was open; recovered close was −₹1,038.38 | Restart evidence and acknowledged pages reveal the interruption and every book's exposure; R2 still needs correction | May shorten operator response to repeated faults; does not prevent host sleep, retroactively monitor the gap or recover this loss |
| Classic UNITEDPOLY entered ₹51.92, despite signal reference ₹52.92; settled −₹9.0411 / −3.720617R | Identity matching shows the correct fill; daily report shows −3.72R; exit provenance separates market/reference movement from the paper model | Improves diagnosis; identical fills still produce the same loss |
| UNITEDPOLY stop reference ₹51.49 became a paper fill of ₹50.97 | The fixed 1% model decrement is explicit: ₹0.52 × 9 = ₹4.68 | ₹4.68 is modeled adverse execution, not demonstrated recoverable profit or proof the real bid could fill better |
| SENSEX calls 42 and 43 used the NSE fee schedule | Future SENSEX costs use BFO consistently | Same-fill combined modeled fee correction is about ₹0.8724, not a major profitability change; recorded history stays unchanged |
| EDGE's post-restart scan skipped for absent token | Bounded token wait, success/error receipts and shared scan lock allow eligible recovery and suppress completed-day duplicates | Preserves valid future opportunities; recovered entries can win or lose; R1 must close the late-entry gap |

Quote send spacing and cancellation recovery reduce preventable data-service failures. October 13 had spacing warnings, but no measured counterfactual establishes an amount saved by today's gate. The changes to pulses/fallback cards improve delivery and instructions without changing the entry signal's statistical edge.

The system is smarter at retaining lifecycle state, recovering work and explaining its own results. Today's changes do not establish higher expected trading profit: strategy entries, exits, thresholds and the conservative Penny paper model remain unchanged. Do not re-label October 13's ordinary −₹1,119.12 paper result as profitable or add independent expiry/shadow outcomes to it.

## Rollout, rollback and remaining work

- Finish R1 and R2 in Dev, add the boundary/interleaving acceptance tests, and update guide/plan/atlas/checklist with the actual final code and commit identity.
- Record the final full-suite result, skipped/deselected cases and process-exit status; current placeholder documentation is not a completed release receipt.
- Promote only through GitHub and rebuild, verifying the actual runtime release. First-day observation still matters after tests.
- Roll back via a reviewed source revert/rebuild; retain existing terminal idea states, historical ledgers and durable receipts. No Production source, configuration, orders or service lifecycle was changed by this review.
- The two requested reference-data files remain present and readable in `/data`; code deployment is separate. Their previous provenance/freshness caveats remain.

