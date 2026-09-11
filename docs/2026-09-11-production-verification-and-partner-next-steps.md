# September 11 Production audit verification and partner status

Read-only Production review of the supplied 755-line audit plus running cache.db and source. No orders/messages/config changes. New document stored in Dev. Database observations were taken after the audit cutoff and are not identical-window counts.

## Verified partner state

Default profile version 2 saved at 07:38 IST: INTRADAY, NIFTY/SENSEX, MARKET_SETUP, DIRECTIONAL_DEBIT_SPREAD, entry-cost ceiling INR100000, risk ceiling INR50000. These are profile filters, not an instruction to trade that amount or an allocation from Sentinel's INR8000. Conditional protection exposure is absent and its scope is not enabled.

Latest input states at 15:14:50 IST: both NO_ENTRY_SETUP / not_fresh_break; source bar close 15:10 IST. This means no new qualifying directional trigger, not unavailable input or an unhealthy setup. Latest-row state is not full-day proof. Both market observations are stale for future sessions until refreshed.

Current database counts: research artifacts 0, strategy qualifications 0, ideas 0, updates 0. Two independent reasons for silence: no recorded candidate and no registered qualification. Saving the profile solved onboarding but cannot replace research. hedge_enabled=False is the separate portfolio service and should not be enabled as a workaround. Broker order verification does not authorize or block generic manual advice in place of these gates.

## Corrected scheduler evidence

At review cutoff, research_quote_collection: 473 duration samples, 35 above 60 seconds, p95 91.220s, max115.096s. Worst run: provider_quote114.222s, archive_write0.837s, finalization0.0009s. FNO tick: 301 samples,16 above90s, p9593.345s, max94.081s; worst split defined_risk76.673s, futures_quote17.345s, exit_management0.003s. Statistics include eligible and non-market callbacks unless separately filtered; do not interpret their average as market-only performance.

Manual advisory:254 completed samples, none above120s, p9518.035s, max21.354s. Clock-only lifecycle:510 samples, p950.049s, max0.092s. No active advice existed, so fast lifecycle timing does not prove active message transport latency under load.

The audit's statement that every 8.3-second run exceeds a60-second interval is mathematically wrong. Long-tail provider waits, not average interval overload, are the measured concern. Do not automatically lengthen the collector to2minutes and reduce useful depth evidence.

23 old IN_FLIGHT markers remain:22 FNO from05:09–08:51 UTC and1 research from04:00 UTC. They cannot all be simultaneously running single-instance jobs. Completion writes have a100ms busy budget and wrapper exceptions are swallowed; missed completion writes are a plausible cause, not proven here. Report these as unresolved telemetry, not23 active jobs. Correlate scheduler completion and boot evidence before diagnosing hangs.

## Other audit corrections

- No orders should be placed merely to clear UNVERIFIED. Paper simulation cannot verify broker acceptance; actual implementation state uses AUTHORIZED. No broker rejection does not prove the route is authorized.
- EMA trend disagreement existed in PR#86 source; PR#87 did not introduce that filter. Verified using git show of the prior fno_engine_mom.py.
- INFO cache misses and DEBUG hits still cannot establish0% hit rate. Separate counters are required.
- Lower memory at one sample does not prove leaner code or absence of leaks; compare time series/workload.
-302/304 responses contradict zero non-2xx; use no observed4xx/5xx if supported.
- Research modules are callable through research_cli.py replay-spread; absence of scheduler/log mentions does not mean dead code. Research runs require an artifact and declared policy, not indiscriminate automatic activation.
- Six optional AI status ReadTimeouts are confirmed. Agent posts with2-second timeout in a background thread; identify the receiving endpoint/DB/upstream delay before asserting gateway overload. Disabled annotation is separate from existing agent functionality.

## Immediate next work

1. Run an archive capability inventory now: both indices, session bounds, contract proof, receipt/provider clocks, usable paired books, gaps and active-leg exit coverage. Publish counts and exclusions. No need to wait passively for a new arbitrary day.
2. Select/freeze the actual intraday policy and causal evaluator, generate its real artifact, and invoke existing CLI against retained observations. Demonstrate evaluator/policy agreement with delivery policy; do not qualify a generic research evaluator merely because its hash verifies.
3. If data supports it, produce chronological replay and held-out report; otherwise name exact missing contracts/intervals/fields and enable bounded collection of those observations. One or two technical runs validate plumbing, not positive expectancy. Session count alone is not qualification.
4. Register genuine qualifying artifacts only after review; otherwise report insufficient/negative evidence. Keep per-index qualification separate. An explicitly authorized TEST/no-advice diagnostic may verify routing now, without qualification or real trade content.
5. Diagnose provider tail latency by separating limiter wait, HTTP request, retries/batches and defined-risk stages, aligned to the35 collection and16 FNO overruns. Current provider_quote includes more than network latency. Preserve exits/update priority and measure market-only p50/p95/max. Fix measured bottleneck before changing cadence.
6. Add nonblocking telemetry completion-failure accounting/reconciliation with bounded retries or a retained fallback, and distinguish abandoned/unconfirmed records from active runs. Do not let telemetry become a trading dependency.
7. Trace six status-publish timeouts with endpoint timing and database waits. Apply bounded backoff/coalescing only as supported; preserve actual disabled/unavailable state.

## When messages can begin

No defensible date can be promised today: qualification is empty and no ideas exist. Earliest actionable message is the first valid in-session candidate after genuine per-index qualification, fresh inputs and routing/final-delivery checks. More elapsed collection days do not automatically activate anything. The next milestone is a concrete research-readiness report using current archives, not another broad software rewrite and not a broker test order. Partner needs no credentials, portfolio feed or personal strategy for generic manual advice. Profile is already saved; do not ask the owner to repeat it.

Useful future message content: exact contracts, per-lot cost/risk, trigger/invalidation/target, intraday deadline and public-condition updates. This improves clarity and discipline; profitability remains a research outcome, not a deployment claim.
