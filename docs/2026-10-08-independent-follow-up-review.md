# Independent follow-up review — 8 October 2026

## Verdict and scope

The follow-ups substantially improve reliability, accounting and the honesty of the research. The real October 8 expiry summary overflow is fixed. They do not establish a profitable strategy, and not every earlier review item is fully closed.

Reviewed Dev HEAD / origin `codex/production-correction-hedge-p0`: `74e360230ff1fc9d947e7100bc800bc405cdfe80`, including expiry `c4329bc` / `ce2c7f4` and general `fc58da3` / `74e3602`. Production checkout and `origin/evolve/smart-strategies` were `84c522676d457bdad5aa716a0ba220f851a394d0`. These follow-ups were not deployed at review time; running containers were healthy. No source, configuration or Production files were edited for this review. This report is a local, uncommitted Dev artifact.

Required system guide, atlas, active plan and handover checklist were read and checked against the checkout. The earlier independent review and the unrelated October 5 Kite log were preserved.

## Independently verified

| Check | Result |
| --- | --- |
| Expiry, overnight, endpoint-budget and Momentum allocation research tests | 104 passed |
| Main route surface and provider lane tests | 15 passed |
| Scheduler coroutine guards and timing tiers | 29 passed |
| Agent suite | 390 passed |
| Focused engine total | 148 passed; includes all 49 expiry tests |

Commands, from Dev (engine paths relative to `python-engine`):

```powershell
.\winvenv\Scripts\python.exe -m pytest tests/test_expiry_paper.py tests/test_edge_overnight_paper.py tests/test_kite_endpoint_budget.py tests/test_momentum_allocation_research.py -q
.\winvenv\Scripts\python.exe -m pytest tests/test_main_surface_characterization.py tests/test_s5_provider_lanes.py -q
.\winvenv\Scripts\python.exe -m pytest tests/test_scheduler_h1_coroutine_guards.py tests/test_scheduler_h2_timing_tiers.py -q
# From repository root:
.\python-engine\winvenv\Scripts\python.exe -m pytest agent/tests -q
```

All these runs exited normally. The complete 5,065-test engine run was not independently repeated. The handover checklist records 5,064 passing plus one surface-golden mismatch, followed by regeneration and four passing surface tests; the author's reported final total should not be confused with this review's independent focused run. A reported full-suite hang after the summary is still a process-cleanup limitation, not a clean full-run exit.

### Expiry replay and delivery

Replayed 925 retained October 8 snapshots exported read-only from Production through the current expiry code, using a temporary research database. All 12 original position legs matched the retained trade fields and amounts. Main results remained A −₹75.28, B −₹720.75, C −₹2,138.48: total −₹2,934.51. Existing shadows remained BH −₹461.24, C500 −₹325.73 and D +₹602.78. New AL / BP reproduced +₹501.63 / +₹786.76 on this same development day.

The 4,277-character summary splits into parts of 3,472 and 826 characters. A simulated transient failure on part two caused a retry of part two only; part one was attempted once, part two twice. Seven trade notices and two summary parts were accepted without duplicate accepted content in that scenario. No real Telegram messages or broker orders were sent.

This confirms the practical overflow repair and normal per-part acknowledgement. It is not an exactly-once guarantee: a crash or lost response after Telegram accepts a message but before the database marks it sent can still cause a duplicate on retry.

### F&O research

Ran the committed `replay_time_stop.py` comparison on the local archived September 10–October 7 sample with the declared 15% drawdown setting and explicit deferral settings. Temporary output only:

| Arm | Closed trades | Net | Worst drawdown | Net excluding best trade |
| --- | ---: | ---: | ---: | ---: |
| Hold beyond time stop / DEFER | 8 | −₹5,267.21 | ₹5,267.21 | −₹5,684.42 |
| Bank at time stop / NO_DEFER | 11 | +₹6,968.18 | ₹1,990.89 | −₹139.49 |

The two published figures now reproduce. Marking the removed +₹6,748 temporary-policy arm as not reproducible is correct. Banking is the better setting on this sample, but its net still depends on the best trade. This is archived-path replay, not a fresh historical full-system backtest or prospective profitability evidence. Keep the drawdown halt unchanged while evaluating the frozen policy forward.

The overnight cash trim now re-walks the final purchased quantity and charges its actual price. The immediate Momentum unavailable-record attribution repair is correct, as is releasing the agent guard when setup fails. Recording actual policy/configuration identity with future Momentum admissions would be stronger than a calendar boundary alone.

## Remaining actionable findings

### F1 — Overnight admission uses the clock from before the scan (P2)

`python-engine/edge_overnight_paper.py:479–575` captures `now` at entry, before quotes, the potentially lengthy scan and the new shortlist re-quote. The post-scan admission still evaluates trade age and writes the entry using that old time. The 15:29 cutoff is checked by catch-up admission, not rechecked after the scan in this function.

Reproduction with an advancing injected clock: begin at 15:20, finish scan and return a genuinely fresh shortlist quote at 15:31. The current code opens one position, records it at 15:20, and accepts it after `ENTRY_LATEST = 15:29`. This did not require malformed provider timestamps.

A separate consistent packet, timestamp and last-trade time both 15:18 at a 15:20 decision, is accepted. A recent HTTP response and the 30-minute last-trade activity rule do not independently prove fresh executable depth. There is no separate provider quote timestamp TTL or future-time sanity check here.

Recommended correction: read an injectable decision clock after refresh, recheck the trading window before committing, record the actual decision time, and validate provider snapshot freshness separately from last-trade activity. Declare the quote TTL explicitly rather than copying the activity threshold. Reject missing/stale/improbably future snapshot evidence.

Acceptance: scan and refresh crossing 15:29 refuse admission; recorded timestamps reflect actual decisions; stale/missing/future quote timestamps refuse; fresh depth with an older last trade is handled according to the distinct declared activity policy. Existing cash/depth tests must continue to pass.

### F2 — Two permanently bad outbox rows still block healthy later notices (P2)

Both `expiry_paper.py:295–337` and `edge_overnight_paper.py:239–277` use the same `stepped` heuristic. Once one aged failed row is skipped, a failure on the next row stops the round regardless of that row's existing failure count or the underlying cause.

Reproduction in both books: enqueue two independently and permanently rejected notices followed by one healthy notice. A fake sender accepts the healthy content and rejects only the first two. After eight rounds, the healthy notice has never even been attempted. The gateway is healthy in this scenario.

One poisoned row is fixed; multiple poisoned rows are not. A second content rejection cannot reliably identify a gateway outage.

Recommended correction: preserve delivery error classification across the gateway boundary, distinguish permanent content rejection from retryable transport/rate-limit failure, and retry known bad rows separately with backoff while allowing healthy urgent notices to progress. Keep failed records for inspection. Retain ordered outage handling and per-part acknowledgement.

Acceptance: two or more permanent rejections followed by healthy content progress; a genuine gateway outage does not hammer all queued rows; an acknowledged part is not resent during normal retries; restart and lost-ack behaviour is documented and tested.

### F3 — Provider budget is useful instrumentation, not a completed limit fix

Official Kite documentation specifies quotes at 1 request/second, historical candles at 3, and orders/other endpoints at 10. Full quotes support up to 500 instruments per request:

- https://kite.trade/docs/connect/v3/exceptions/
- https://kite.trade/docs/connect/v3/market-quotes/

The new `/ops/provider-budget` endpoint is protected by the internal-secret check and measures instrumented calls in the engine process. The shared three-request/second limiter remains unchanged. A warning does not enforce the endpoint budget.

Counter scope is incomplete: `refresh_instrument_cache` (`kite_client.py:627`) and `get_funds_margins` (`kite_client.py:1954`) dispatch HTTP without recording the endpoint. A fake HTTP probe performed both requests and observed two HTTP calls but zero budget calls. The order counter can also record an admission that is subsequently refused before HTTP dispatch. Node gateway traffic is outside the engine counter, so these are not account-wide totals.

Independently parsed the retained October 8 engine log: 262 textual occurrences of “429”, zero actual HTTP-status-429 or quote-retry-status-429 matches. The author's correction is supported by the retained log. Absence of a logged rejection does not establish adherence to the documented limit.

Recommended next slice: instrument actual dispatch and response outcomes consistently, show process start/window scope, coordinate quote batching and priority, then enforce the quote-specific budget without reducing all endpoint traffic to one global rate. Keep main F&O exits and expiry freshness as explicit acceptance requirements. Merely waiting to observe a rejection leaves a known contract mismatch open.

Acceptance: instrument all relevant engine paths; blocked orders do not count as dispatched; expose actual 429 outcomes; exercise concurrent Penny scanning, main F&O exits and expiry ticks with endpoint-specific budgets and batched quotes; measure maximum critical-request wait and quote freshness. The impact of other processes must be accounted for or explicitly declared outside scope.

## Recommended rollout and remaining work

1. Fix F1 and F2 in Dev before calling the overnight and outbox review fully closed. Both are bounded correctness repairs, not strategy redesigns.
2. Treat F3 as shared-provider work with an explicit batching/budget plan. Do not apply an untested global slowdown or pause unrelated modules without evidence.
3. Preserve A/B/C policies and AL/BP paper-only forward scoring from October 13. AL can gap below its intended gain lock; BP exits are sequential and can produce asymmetric fills. Those limitations are now correctly documented. Do not promote D on one profitable expiry or enlarge C after two worthless expiries.
4. Keep separate fill and modeled-settlement results, verify sampled settlement against exchange evidence, and complete the planned crash/recovery delivery checks. Evaluate each play and underlying separately, include zero-trade days and best-day-removed results.
5. Through GitHub only, promote the reviewed commit plus any accepted repairs and rebuild the relevant services together. Verify running commit/image identity, daily login and instrument refresh, both outboxes and the provider-budget endpoint. A normal morning login is sufficient if the daily session and instrument refresh are valid; 12:59 means 12:59 PM IST.

No configuration or database migration was applied by this review. Proposed repairs should retain existing outbox records; any added delivery-state fields need additive migration and restart coverage. Roll back through GitHub to the last reviewed image/commit while preserving paper databases and separating results by policy version. Never edit Production directly or treat passing tests as a profitability verdict.

Overall: better operational quality, reproducible research and more honest risk communication. The October 8 summary blocker is closed. Overnight decision timing, multiple bad messages and shared endpoint budget work remain. Deployment and forward results are separate requirements.
