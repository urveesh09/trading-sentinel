# Independent review of the October 8 changes

Review date: October 8, 2026 IST. Review only: no implementation, configuration change, commit, push, merge or rebuild was performed.

## Verdict and environment

The changes improve correctness, execution honesty and observability overall. The strategy additions are useful paper experiments, with insufficient evidence to call them profitable or consistent. One new integration defect should be corrected before the next expiry: the expanded Telegram summary can exceed the message limit and block later notices in the expiry outbox.

- Dev: `codex/production-correction-hedge-p0`, HEAD `302c95fc04414c20b7b1f9fe4c95d7d5dd03e979`. Reviewed `7f028ed`, `b7d3f4d`, `40d838e`, intervening owner-rule changes, current source and tests. Remote Dev was also at `302c95f` when checked.
- Production checkout and running release: `84c5226`, through the October 7 merge. The October 8 changes are not deployed. Runtime health was OK; Kite connected and scheduler running at the inspection time.
- Production assessment used its retained October 8 audit evidence and a read-only SQLite connection to the running container's expiry store. Replay writes went to isolated temporary stores only.
- Required guide, atlas, active plan and checklist were read/revalidated. Existing untracked audit/research files were left alone. This review document is the only new repository artifact.

## Findings requiring follow-up

### R1 — High: expanded expiry summary exceeds Telegram's limit

Files/contracts: `python-engine/expiry_paper.py:1358` (`format_day_summary`), `:262` (`flush_notices`), `python-engine/scheduler_setup.py:740` (paper sender), `node-gateway/server/routes/internal.js:43` and `node-gateway/server/services/telegram.js:433` (`sendAlertOnce`).

Replaying all 925 October 8 packets through current Dev produces a **4,277-character** summary before the gateway's alert prefix. The gateway sends it as one ordinary `sendMessage`. Telegram documents a 4,096-character maximum after entity parsing: <https://core.telegram.org/bots/api#sendmessage>.

This is a deterministic message-size defect on the reconstructed day, not an actual Telegram request made during this review. Its effect was reproduced with a fake sender enforcing the documented limit: seven short trade notices were accepted, the summary stayed pending, and a later simulated October 13 trade notice was not delivered. `flush_notices` breaks on the first failure and therefore retries the same permanently invalid summary ahead of later notices. Trading calculations continue; expiry notification delivery can become blocked across days.

Recommended correction: a concise operational summary plus a separate detailed report, or durable numbered chunks with per-chunk acknowledgements. Include the gateway prefix in the size budget. A permanently invalid report must not indefinitely block urgent trade notices. Preserve failed content and distinguish permanent delivery rejection from transient retry; do not silently discard it.

Acceptance: a maximum-content day, replayed October 8 summary, Unicode/prefix allowance, failure on a later chunk, retry/restart without losing accepted chunks, and a later urgent notice after a permanently rejected report. This crosses engine/gateway contracts and belongs in an explicit Dev implementation slice before promotion.

### R2 — Medium: committed F&O comparison scripts do not freeze their arms

Files: `docs/research/fno/2026-10-08-time-stop-sign/replay_time_stop.py`, `replay_old_vs_new_sign.py`, and `python-engine/fno_exit_rules.py:49,161`.

The shipped default is now `FNO_TIME_STOP_RESPECTS_PREMIUM=False`. The scripts' DEFER/SHIPPED arms do not explicitly set it back to True. On current source the nominal DEFER arm is therefore the same policy as NO_DEFER. The same issue affects old/new-sign comparisons when both inherit the False default.

The third arm also passes `FNO_TIME_STOP_DEFER_NEEDS_LOCK`, a key the current exit evaluator never reads. That arm cannot implement its advertised rule on this checkout. The retained third-row +₹6,748 result is not reproducible from the committed evaluator/script as supplied.

Independent replay on the available 18-session archive, September 10–October 7, with drawdown limit explicitly 0.15:

| Arm | Closed trades | Net ₹ | Max drawdown ₹ | Net without largest winner ₹ |
| --- | ---: | ---: | ---: | ---: |
| Current script DEFER, inherited False | 11 | 6,968.1817 | 1,990.8913 | −139.4928 |
| Explicit deferral True | 8 | −5,267.21 | 5,267.21 | −5,684.421 |
| Explicit deferral False | 11 | 6,968.1817 | 1,990.8913 | −139.4928 |
| Current script DEFER_NEEDS_LOCK, unused override | 11 | 6,968.1817 | 1,990.8913 | −139.4928 |

The main reported True/False numbers **are reproducible when the policies are explicit**. This finding concerns research reproducibility, not reversal of the live sign fix.

Recommended correction: specify every varied setting in every arm, reject unknown override keys, record source/data/configuration hashes and the starting book state, and remove or implement/version the third arm. Repeat under explicit opposite ambient defaults; the result of each declared arm must remain unchanged. Preserve the original results as historical evidence rather than overwriting them without provenance.

### R3 — Medium: overnight depth price is calculated before final cash-limited sizing

File: `python-engine/edge_overnight_paper.py:469–501`.

`walk_asks` prices `wanted` shares; affordability can then reduce the admitted `shares` without recalculating the walk. An isolated integration probe used asks of 100 shares at ₹20.10 and 900 at ₹20.30, a planned 1,000 shares and ₹6,000 cash. The book admitted 295 shares at ₹20.28. Their actual displayed-depth average is ₹20.232203, a ₹14.10 modeled overcharge before the fee difference.

The error is conservative for sorted asks, but it does not meet the claimed final-quantity average-price contract and can distort comparisons. The separate LTP-plus-25-bps floor is also a declared modeling assumption, so the recorded entry price is not always precisely the visible-book average.

Recommended correction: solve quantity, depth average and buy charges together; re-walk at the final admitted quantity. Record depth VWAP and any additional conservative price allowance separately. Acceptance must cover partial cash availability, several asks, exact fees, the quarter-of-plan floor and multiple ranked picks sharing cash.

### R4 — Medium: overnight depth has no decision-time freshness contract

Files: `python-engine/edge_overnight_paper.py:302` (`provisional_bar`), `:393` (`realism_refusal`), `:426` (`run_overnight_entry`).

The provisional-bar check only verifies the date when a timestamp exists; a missing timestamp also passes. The new entry receipt stores a quote timestamp but does not enforce its age. An isolated entry probe accepted visible asks stamped **09:00 at a 15:20 decision**. Quotes are also fetched before scanning/ranking, so scan duration adds to their age.

This establishes a latent modeling gap, not that stale overnight quotes caused an October 8 loss. Recommended correction: enforce freshness using the provider quote timestamp at admission, distinguish it from last-trade time, and re-quote shortlisted picks after an expensive scan. Missing/stale depth must give an explicit unavailable/refused result. Keep the age budget documented and evaluate refusal counts before changing it.

### R5 — Medium: selective Momentum's unavailable paths are assigned to the wrong cohort

Files: `python-engine/momentum_admission_cohorts.py:53–60`, `python-engine/momentum_paper_path_adapter.py:91–118`.

Every unavailable candidate is supplied to BASELINE_ADMISSION; SELECTIVE_ADMISSION_V1 always receives an empty unavailable list. A probe supplied an October 8 unavailable candidate and reproduced this incorrect allocation. The adapter also drops its recorded timestamp from unavailable records, preventing reliable retrospective routing.

The split is useful, but currently understates missing-path evidence in the selective cohort. Labels are inferred solely from a calendar cutoff, which also fails if the selective flag is disabled or rolled back later.

Recommended correction: retain admission time and the applied admission-policy identity for available and unavailable records, route both by that identity, and preserve an UNKNOWN cohort for legacy records that cannot be attested. Report complete candidates and missing evidence together. Leave the existing frozen allocator manifest untouched; separately fingerprint its upstream admission contract.

### R6 — Low: status-publisher guard can remain latched after a setup failure

File: `agent/agent.py:1505`.

The guard is set before `optional_ai_status()` and thread creation. Only the worker's finally block clears it. A probe making the snapshot builder raise reproduced `in_flight=True`, `failures=0`, so subsequent publishes skip indefinitely. Thread-start failure has the same structural issue.

Recommended correction: release/update the guard on setup exceptions and cover snapshot/thread-start failure. The longer timeout and non-overlap guard remain useful improvements. Requests' connect/read timeout tuple is not a total wall-clock deadline; avoid describing it as one.

### R7 — Existing architecture gap: quote endpoint budget differs from the shared limiter

File: `python-engine/kite_client.py:319`, quote calls at `:1010` and `:1150`; expiry opts into its management lane at `python-engine/expiry_paper.py:1054`.

The existing shared limiter admits three requests per second for both historical and full-quote calls. Kite's current documentation lists full quotes at **one request per second** and historical candles at three: <https://kite.trade/docs/connect/v3/exceptions/#api-rate-limit>.

The priority change preserves the existing rate and correctly reduces queue competition. It does not establish endpoint-specific broker-limit compliance, or guarantee the observed 0.28-second benchmark on every future callback. No October 8 quote-rate rejection is claimed here.

Recommended follow-up: separate endpoint budgets, consolidate quote batches where appropriate (full quotes support up to 500 instruments), and measure queue age, 429s, transport, decision lag and missed callbacks under concurrent Penny/expiry/F&O management load. Expiry and main F&O exit management share the management lane; protect both and demonstrate bounded normal/bulk service. Do not pause Swing to fix a daytime quote queue it does not use.

## What the changes improve

| Change | Assessment |
| --- | --- |
| Bought-put P&L sign | Correct. Bearish single-leg means a bought put; option P&L is exit minus entry for either direction. |
| Best-premium persistence without a futures quote | Correct and important: an open position retains a new option peak for later profit-lock decisions. The update is monotonic and restricted to OPEN rows. |
| Deferral False | A reasonable paper policy candidate with an explicit replay advantage. It time-stops insufficient underlying progress before trail activation, including losing trades; it does not only sell profitable trades. |
| Missing/empty overnight asks refused; visible quantity cap | Clearly improves the prior fail-open fill model. R3/R4 are remaining execution-contract gaps. |
| Partner observation wording and 30-date window | Correct. Sparse observations cannot prove that an unobserved price level never traded. |
| Momentum cohort split | Improves research honesty; R5 prevents treating it as a complete evidence split yet. |
| Agent timeout/non-overlap/failure streak | Useful operational improvement, with R6 as a small robustness follow-up. |
| Expiry priority, 966 slots, fresh OI, actual snapshot clocks, whole-trade excursions | Sound reliability/reporting improvements. Fresh-at-receipt quotes do not erase missed callbacks: October 8 retained 925 of 966 eligible slots, 15 gaps over 25 seconds. |
| AL and BP | Sensible shadow experiments, with no demonstrated forward edge yet. AL's price stop can gap and does not mechanically bank money like a partial sale. BP evaluates both legs' net liquidation value including fees. |

AL uses A's entry logic but maintains its own open-position state and loss budget; future entries and sizing can diverge after different exits. Do not claim every AL entry always mirrors A. For an exit-only comparison, also score matched A entry paths. BP latches a paired exit when both legs have sufficient fresh depth, then processes/retries each leg; this is not an atomic broker execution guarantee.

The whole-trade excursion report is useful: maxima are coherent simultaneous marks with closing fees, not the sum of leg peaks at different times. It is diagnostic evidence, not a rule capable of selling at the unknowable best future price.

## Independent expiry replay

A read-only export of the running Production store's October 8 ticks and positions was passed through current Dev's actual `_tick_underlying`, fee functions, exit logic and reconciliation in a temporary store. The contract catalogue was reconstructed from recorded symbols with the SENSEX 20-unit lot and 100-point strike spacing; identifiers were synthetic. Each saved callback's original started/decision/provider times and all saved depth levels were retained. Only recorded packets were available; missing callbacks were not invented.

All **12 original legs** reproduced entry symbol/time/price/lots, filled and assumed P&L, gross, fees, status, peak, stop and pending-exit state exactly. There were 16 modeled entry/exit fills, not 16 independent trades.

| Play | Whole modeled October 8 net ₹ |
| --- | ---: |
| A | −75.28 |
| B | −720.75 |
| C | −2,138.48 |
| Main A/B/C | **−2,934.51** |
| BH | −461.24 |
| C500 | −325.73 |
| D | +602.78 |
| New AL | +501.63 |
| New BP | +786.76 |

Main filled +₹508.49 and assumed −₹3,443 reconcile to the same total. AL/BP were designed using this observed day; their positive figures verify mechanics on that path, not predictive skill. They must start their scored forward cohort at the declared October 13 boundary after deployment.

## Risk and strategy recommendations

1. Correct R1 before promoting the expanded expiry report; correct R2 before using the script as repeatable decision evidence. Then close R3–R6 in small separately verified Dev slices.
2. Keep the put-sign and peak-persistence fixes. Hold AL/BP parameters fixed during the forward paper trial. Compare whole trades, every scheduled day including zero-entry days, each underlying, and each policy/execution version separately.
3. Keep the existing F&O hard capital floor while researching alternatives. The fact that a halt missed three known winners does not justify increasing future risk. A weekly reset can repeatedly forgive losses; any alternative must preserve an explicit cumulative capital-loss budget and keep exits operational during entry halts.
4. The new F&O replay makes ₹6,968, but excluding its largest winner leaves about −₹139. Judge dependence on large winners alongside net expectancy, drawdown, turnover/cost sensitivity and forward results. A trend system can legitimately depend on occasional large wins; this sample does not demonstrate steady small wins.
5. A/AL are the clearer management candidates. B/BP are auction-window experiments. C's two worthless expiries argue against increasing its budget. D's one winning expiry is insufficient for promotion: its exercise-tax reserve only bounds loss within the declared stress domain, not every conceivable index move or broker-margin scenario.
   The ₹2,500 limit is per main play, so A/B/C can together lose up to ₹7,500 within their modeled daily bounds; shadows have separate virtual budgets. These are independent paper experiments, not one funded portfolio return. If expiry strategies are later funded alongside normal F&O, their reservations, loss limits and broker margin must join the shared capital contract rather than merely summing virtual-book profits.
6. Reconcile assumed settlements against the official exchange settlement price. Keep sampled-index intrinsic values and unresolved worst-case valuations separate from filled cash. Complete the existing crash-between-ACK-and-commit/restart-open-legs/absent-final-sample recovery matrix. Delivery remains at-least-once across a crash, even with same-process flush locks.
7. The owner's 10-all-losing-expiries rule is implemented as a reporting tally and owner decision, not an automatic halt. An occasional small win can coexist with negative total expectancy; review per-play cumulative P&L/drawdown as well as that tally. Preserve the owner's stated rule until they choose a change.
8. These commits do not establish an improvement to Smart Penny's trading edge. Overnight is a distinct paper strategy. Prioritize honest entry/exit economics and regime-specific evidence before loosening Penny gates or scaling capital to reach a daily-return target.

## Verification receipt and proposed rollout checks

- Focused engine command: `winvenv/Scripts/python.exe -m pytest tests/test_expiry_paper.py tests/test_fno_profit_lock_and_reentry.py tests/test_fno_exit_rules.py tests/test_edge_overnight_paper.py tests/test_momentum_allocation_research.py tests/test_partner_content.py tests/test_partner_orchestrator.py tests/test_s5_provider_lanes.py -q`: **185 passed**, one deprecation warning, 134.61 seconds.
- Full engine: `winvenv/Scripts/python.exe -m pytest tests -q`: **5,054 passed, 4 skipped, 47 warnings**, no failed tests, 452.43 seconds. Warnings include an aiosqlite worker attempting to signal a closed event loop. The process hung after its completed summary; only the specifically identified review pytest child was stopped. This is not a clean process-exit receipt.
- Agent: from Dev root, `python-engine/winvenv/Scripts/python.exe -m pytest agent/tests -q`: **389 passed**, 6.05 seconds, normal exit.
- Explicit-arm F&O replay independently reproduced the two main table rows and the largest-winner sensitivity. The supplied scripts' default inheritance and unused third-arm key were independently demonstrated.
- Temporary overnight, cohort, status guard, summary-length and blocked-notice probes reproduced R1–R6. No real notification/order was sent.
- `git diff --check` was clean before this review artifact. No tracked Production changes were made. Existing unrelated untracked research/audit files remain.
- Gateway tests were not rerun: the reviewed commits did not change gateway source. The oversized message follows its existing unchunked sender contract, confirmed by source and Telegram's documented limit.
- One initial temporary replay database remains at `C:/Users/Urveesh/AppData/Local/Temp/sentinel-expiry-review-jrrv85gn/cache.db.expiry-paper.db`: cleanup was rejected by automatic tool policy, including an explicit non-recursive retry, with no reason beyond "blocked by policy". Subsequent replay stores closed and cleaned normally.

For an implementation slice, update the active plan/system guide, add acceptance checks for the actual cross-service cases above, regenerate the atlas when source changes, and record source/data/configuration identity in the commit receipt. Promote through GitHub only. After rebuilding, attest the running release and effective time-stop/expiry flags, check summary delivery and pending outbox counts, and watch October 13 queue/tick coverage and expiry/F&O exit latency. Roll back the specific affected change through GitHub if acceptance fails; do not restore the put-sign bug to regain old replay numbers or disable exits when entries are halted.

This review document is local and uncommitted. No implementation fixes or deployment were performed by the review.
