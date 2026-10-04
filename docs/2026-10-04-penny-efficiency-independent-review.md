# Penny efficiency: independent review and discussion — October 4, 2026

**Subsequent authorized work:** the owner approved the comparison/rounding/tick
corrections after this review. [Implementation receipt](2026-10-04-penny-corrections-and-relative-strength-slice.md)
records the Dev-local fixes and tests; [researched next strategy](2026-10-04-penny-consistent-returns-strategy.md)
records the new proposal. The findings/reproductions and no-source-edit receipt
below describe the original review stage. Do not treat their historical noise
quantities or source status as the corrected implementation.

Review baseline: Dev `a6747406094f607b3e120a5c2b185603ac3b6b8b`, branch
`codex/production-correction-hedge-p0`. Clean worktree on entry. A fresh
`git ls-remote --heads origin codex/production-correction-hedge-p0` confirms that
exact commit is pushed. Production HEAD, read through Git metadata only, is
`044c016`; the new Dev work is not being described as deployed.

The owner requested review, web research and discussion of further Penny
improvements and a 1–2% daily return aspiration. This is a **review and proposed
development sequence**, not authorization exercised to change strategies,
funding, flags or Production. No source edits, broker calls, new historical
scoring, push, merge or deployment in this task. F&O is not being redeveloped.

## What the new work establishes

The older subset-only-filter diagnosis is no longer a complete description.
`adaptive_penny_policy.py` and its lifecycle wiring now implement setup states,
alternative entry timing, structural sizing, churn memory and thesis exits.
Studies retained unsuccessful candidates instead of declaring sophistication
profitable. Own-cash daily replays and freeze-before-score tooling are useful
advances. Most alternative policies did not outperform their baselines.

| Penny evidence | Result | Meaning |
| --- | --- | --- |
| Original baseline, untouched Sep 7–23 plus Oct 1 | 24 closes, +₹63.17; 6 positive sessions among 11 sessions with trades | Small, coverage-selected lifecycle sample; neither daily consistency nor live qualification |
| PEN_TRADER_V1, same untouched dates | 91 closes, −₹102.94 | More recognized setups increased gross losses as well as costs |
| PEN_TRADER_V1_THESIS, same dates | 283 closes, −₹104.89; gross +₹41.34, costs ₹146.23 | Freed capacity and churn can consume a small gross edge |
| PEN_TRADER_V2, same dates | 80 closes, −₹17.02 | Development gains did not survive the untouched test |
| Noise stop, documented seen Sep 7–Oct 1 development | 39 closes, +₹93.19 vs baseline 42 / +₹78.35; realized DD ₹32.40 vs ₹45.10 | Promising modest development improvement, not an untouched result |
| Noise stop plus +1R breakeven, same seen dates | 44 closes, −₹13.26 | The tested quick breakeven policy harmed results; do not enable it merely to bank profits faster |

T1 numbers were checked in stored results/reports, not inferred from test counts.
The noise-stop figures above are the documented round-3 development evidence;
the January–July Kite `penny-noise-t3` freeze/results have not been completed.
Sources: [T1 receipt](2026-10-04-t1-penny-edge-trader-slice.md),
[stored T1 results](research/yahoo/2026-10-04-penny-trader-oos/results.json) and
[round-3 development slice](2026-10-04-momentum-penny-smarter-slice.md).

The gain is not uniform. **Inference from rounded published totals**, assuming
the same underlying snapshot/configuration: subtracting Sep 24–30 (noise
+₹35.78, baseline +₹15.18) from all seen days leaves approximately +₹57.41
versus +₹63.17 on the remaining dates. Noise wins in the already-seen five-day
development subset but trails on the remainder. This subtraction is not a new
backtest, a newly untouched test or proof of inferior future performance; it
does make the aggregate +₹93 versus +₹78 an insufficient promotion argument.

The baseline used a ₹100,000 paper book and ₹500 per-stock cap. A favorable
rupee total must not be divided by the ₹2,000 live allocation and advertised
as an owner-budget backtest. That requires a separately frozen replay.

The runtime now has `PENNY_NOISE_STOP_ENABLED=True`, so the noise floor affects
paper admissions once promoted. `PENNY_LIVE_TRADING` defaults false. The older
round-3 slice's statement that runtime Penny strategy is unchanged was superseded
by `a674740`; documentation must describe that owner-selected exception explicitly.
Shared-helper reuse is good, but it introduces a study-baseline problem below.

## Actionable findings before interpreting the next study

### P1 — the planned noise-stop study no longer isolates its hypothesis

`penny_lifecycle_replay._evaluate` calls the shipped evaluator for every arm.
That evaluator now applies the noise floor by default. Only afterwards does
`PEN_NOISE_STOP` call `noise_floored_decision`. Thus the `penny-noise-t3` BASELINE
already receives the intervention it is meant to compare against. Its declared
arms set only `candidate_policy`; the Lab schema has no explicit stop-policy
control. Reapplying the helper does not reconstruct the old stop.

Reproduced without market data: on a valid ₹5.08 close / ₹5.07 low setup,
the evaluator with noise OFF returns entry ₹5.10, stop ₹5.07, 98 shares;
noise ON returns stop ₹5.02, 38 shares. Applying the named NOISE arm to the ON
decision returns that same stop and quantity. The pending A/B comparison can
therefore be identical or affected by repeat-rounding rather than measure the
old-to-new policy delta. This does **not** invalidate T1 receipts generated
before the runtime default changed.

Correction proposal: make stop policy an explicit immutable replay input,
applied exactly once. Preserve a named pre-noise baseline and the current
runtime baseline; specify which one each hypothesis compares with. Freeze
effective risk/cost/stop settings and validate their values before scoring.
The study currently hashes source files and data but its pre-registration does
not bind every environment-resolved Penny setting. Same source with different
environment flags is not necessarily the same experiment. Do not freeze/run
the current T3 definition unchanged or rewrite old receipts in place.

### P2 — stop rounding violates the promised preserved-risk invariant

`noise_floor_stop` sizes using an unrounded distance and then rounds the stop.
Actual rounded distance can be greater or smaller than the sizing distance.
Using permitted sub-₹500 notional:

- Entry ₹5.10, old stop ₹5.07, 98 shares: old planned risk ₹2.94.
- Helper returns stop ₹5.02 and 38 shares: actual planned risk ₹3.04.
- Entry ₹10.10 can return a ₹0.15 stop distance although the 1.5% floor is ₹0.1515.

These are small absolute amounts but contradict the helper's safety contract.
Quantize the stop in the protective direction using the instrument tick, then
size from the **final** distance with exact integer/Decimal arithmetic. Keep
the original nominal risk bound in the current policy; decline zero quantities.
Add boundary/property regressions, including unchanged already-wide stops.

### P2 — the live executor uses coarser prices than the research stop

`penny_executor.snap_to_tick` hardcodes ₹0.10. That can be a valid price multiple,
but it is unnecessarily coarse for many cheap stocks. In the example above,
the intended ₹5.02 sell trigger becomes ₹5.00, increasing trigger-distance
risk to ₹3.80 at the same 38 shares, before any entry slippage/stop-limit failure.
Entry limits are also snapped up. This is an existing execution mismatch, not
a new regression proven by the noise-stop commit; live Penny remains OFF.

Use actual instrument tick metadata and assess risk against executable entry
limits and rounded protection, followed by confirmed-fill reconciliation.
Do not represent the signal stop as the eventual broker fill. Kite exposes
[`tick_size`](https://kite.trade/docs/connect/v3/market-quotes/), and the NSE
[2024 circular](https://nsearchives.nseindia.com/content/circulars/CMTR62174.pdf)
introduced ₹0.01 ticks below ₹250 for specified securities with monthly review.
Current instrument metadata, not a hardcoded historical rule, must own the tick.
SL-limit protection still has gap/non-fill risk after accurate rounding.

## The daily target and capital efficiency

Treat the requested 1–2% as net return on **beginning-of-day Penny allocated
equity**, including unused cash and all costs, rather than the stock's price
move or return on one position. With ₹2,000 this is ₹20–₹40 per session.
That level can occur on particular good days; current evidence does not support
it as a consistent average or a promise for every day. For scale only, compounding
1% and 2% over 252 sessions produces approximately 12.27× and 146.97× starting
equity. This arithmetic is not a forecast or a reason to increase risk.

A real design trade-off: the new stop preserves the risk already implied by a
tiny candle-low stop, rather than sizing afresh against a chosen trade budget.
For a helper input of entry ₹20, old stop ₹19.95, 25 shares (₹500 notional),
it returns stop ₹19.70 and four shares (₹80 notional). Planned risk remains
about ₹1.20 instead of ₹1.25. That is faithful to its stated intent but sharply
reduces deployed capital. It may explain why favorable price moves translate
into few rupees. It does not prove that deploying more would be profitable.

Three ₹500 MIS caps allow at most ₹1,500 simultaneous notional before noise
resizing. Against the paper ₹100,000 book that is only 1.5%; against ₹2,000
it is 75%. The same trade amounts produce very different allocation returns.
Report cash utilization and net profit per capital-day alongside net expectancy
and marked downside. Idle cash is acceptable when eligible trades lack edge.

A possible **later research** sizing policy chooses the final structural/noise
stop first and then allocates a conservative explicit risk budget, inside existing
per-stock cash, own-cash and portfolio loss ceilings. This increases some trades'
exposure relative to today's preserved tiny risk. It is a material policy change,
not a rounding correction and not approved here. Prove entry/exit expectancy
first; compare it on owner-sized money before recommending any runtime change.

## How I would develop next

| Sequence | Problem / files and contracts | Acceptance | Rollout / rollback |
| --- | --- | --- | --- |
| 1. Correct comparison and price arithmetic | Penny breakout/noise helper, lifecycle/Lab, pre-registration runner, executor's tick interface. Preserve existing strategy constraints and original-risk ceiling. | Distinct frozen old/new stop arms; effective settings bind; quantity × final executable distance stays within the declared budget. Rounding and fill/protection counterexamples pass. No broker calls during review tests. | Dev fixes and offline fixtures first. Any runtime promotion goes through GitHub; flag OFF selects the pre-noise policy. Existing positions retain their admitted protection. |
| 2. Finish the pending independent stop study | January–July Kite coverage, committed freeze, same causal clocks/costs, original and owner-sized books separately. Capture unresolved/open exposure and daily marked returns. | Baseline receipt parity on archived development data, correct A/B difference, untouched run once; net after costs, adverse-fill bounds, winner concentration and daily return distribution. Current symbols/constant regime/proxy fills remain explicit limitations. | No live activation from a promising study. Paper observation first; do not claim full-system parity or reuse this holdout after seeing it. |
| 3. Isolate the next improvement | Maximum two newly declared candidates in a new round. First: volatility/structure-aware **stop only on shipped entries**, versus corrected fixed noise floor. Second, if data supports it: entry selection/execution readiness on those same setups using liquidity, spread, volume persistence and chase distance. Existing V1's combined changes are not retried under a new name. | Paired comparisons at equal cash/risk; all failed/no-fill paths retained. Attribute gross edge versus execution cost. Do not simultaneously change universe, entries, exits and sizing. Depth-dependent variants require forward quote evidence. | Offline/shadow, default OFF. Disable only new entries on rollback; exits stay operational. |
| 4. Improve timing and cash use only after evidence | Bounded pre-entry watchlist, actual quotes/limits/confirmed fills; at most one separately frozen earlier-session or risk-allocation hypothesis after stage 3. | Measure missed setups, quote/scan latency and all candidates' false starts. Demonstrate net improvement on fresh data with marked drawdown within existing ceilings; owner-budget study required for sizing. | Separate approval for material capital-use/runtime changes. No new F&O load, cash transfers, shared defaults or risk-cap increases. |

Do not repeat the all-stock opening-range breakout as if it were untried: the
development slice already reports losses for that experiment and for a local
stocks-in-play implementation. A later earlier-session candidate must have a
specific new hypothesis and use a fresh window. The present 10:30 start and
60-second scan are reasonable things to measure; neither is automatically the
cause of the losses. Use multi-minute evidence for setup persistence and quotes
for execution, without changing completed-bar availability or claiming HFT speed.

Tomorrow's Production discussion should distinguish **paper observation** of
the owner-selected noise floor from qualification for real-money Penny. Resolve
the rounding/study findings first. Reconcile the three previously documented
PENNY_PAPER blob-price rows through a separate reviewed maintenance path; they
were not repaired or used as trustworthy performance records here. Do not merge
or switch on live flags as part of this review. Momentum direct execution remains
default OFF; the full branch also contains F&O changes needing their own review.

## Web research: useful ideas and transfer limits

- [Zarattini, Barbon and Aziz, university-hosted paper](https://www.alexandria.unisg.ch/server/api/core/bitstreams/3c2989c4-688d-4d78-8a71-f02690990d51/content): selecting unusually active US stocks improved their ORB model. But their universe excluded stocks below $5 and low liquidity, allowed long/short and up to 4× leverage, and used US costs. Its headline returns are not evidence for our no-leverage NSE Penny book. The design clue is which opportunities to concentrate on, not copying its rules or return claims.
- [Cont, Kukanov and Stoikov](https://arxiv.org/abs/1011.6402): short-horizon price impact in 50 US stocks related to order-flow imbalance and market depth. A local execution-readiness hypothesis can consider persistent bid/ask support, spread and depth. Top-five periodic broker snapshots are not the full event feed used in that study; apparent depth can disappear, and candles cannot reconstruct it.
- [Kite streaming](https://kite.trade/docs/connect/v3/websocket/) provides depth and order updates; [orders documentation](https://kite.trade/docs/connect/v3/orders/) distinguishes submission from execution. Use these to record actual timing/fill evidence in a bounded future adapter, protecting F&O subscription/request/exit capacity. No new connection or subscription was made here.
- [SEBI's equity-cash intraday study](https://www.sebi.gov.in/sebi_data/attachdocs/jul-2024/1721818619980.pdf) found losses common and associated greater trading frequency with more loss-makers. That population result does not judge our algorithm, but supports treating turnover and costs as part of the objective rather than forcing a daily trade/profit quota.

Review recommendation: keep what has survived testing, correct the measurable
contracts, and investigate execution/capital efficiency before another large
entry rewrite. Rejecting failed candidates is progress; it does not establish
a repeatable daily edge.

## Verification and scope receipt

Fresh focused test command:

```powershell
.\python-engine\winvenv\Scripts\python.exe -m pytest python-engine/tests/test_penny_noise_stop.py python-engine/tests/test_penny_engine_breakout.py python-engine/tests/test_penny_trader_replay.py python-engine/tests/test_adaptive_penny_policy.py python-engine/tests/test_penny_isolation.py python-engine/tests/test_preregistered_study_runner.py -q
```

**45 passed**. Small in-memory reproductions demonstrated risk-rounding,
executor snapping, capital shrinkage and old/new policy contamination; the
temporary settings toggle was restored without writing configuration. Existing
test passes do not cover those identified invariants. Stored T1 aggregate
figures and the baseline's actual ₹100,000/₹500 settings were verified.

This is a Penny-focused source/tooling/documentation review of commits since
`434c4cc`, not a full independent audit of every changed F&O/gateway path or a
new Production performance assessment. Earlier full-suite pass/failure totals
are historical receipts, not rerun or independently attributed in this task.
No source declarations changed, so atlas regeneration is unnecessary. New
review/handover documentation remains Dev-local and uncommitted; reviewed
implementation `a674740` is pushed, not promoted by this work.

Delivery checks: `git -c core.safecrlf=false diff --check` passed; source diff
for Python/scripts/gateway/agent is empty. Local review/evidence links,
handover redirects, referenced Python files and scope/test-receipt assertions
were checked with Dev Python. No implementation commit or migration required.
