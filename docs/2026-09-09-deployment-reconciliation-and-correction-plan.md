# September 9: deployment reconciliation and correction plan

Prepared from read-only Production inspection and refreshed GitHub refs on 2026-09-09. Implementation location: Dev only. This document supersedes the deployment, token and cache conclusions in the supplied deep audit; it does not replace its retained raw evidence.

## 1. The deployment discrepancy is resolved

You did merge the changes. GitHub release branch `evolve/smart-strategies` is at `87d7ccd` (PR #85, September 8 18:31 IST), containing `e8d1ce1`. Production desktop checkout remains `2c87ecd` (PR #84). There are 35 commits between that checkout and the release branch, including the merge commit. GitHub `main` is an older, different branch and is NOT this installation's release branch.

Running python-engine image: `sha256:cebbaab7cf6aa437ff8f9629168359013ae0dc7551b8a653909e13e1c34a2f3e`. Container creation: September 8 13:07:47 UTC (18:37 IST). Compose working directory is the Production folder. Only /data is mounted; application source is baked into the image. Runtime /app/main.py SHA256 is `3d899c371dc76f662c28cf7be197b66f4c04190304ddd37d15eeed837c911e60`, exactly matching old Production source. /app/research_archive.py is absent.

Conclusion: merge succeeded, but local checkout and runtime did not advance to that merge. A container created after the merge can still contain old source. The available evidence cannot establish which deployment command was used or failed. Do not attribute this to Docker caching alone: the source checkout itself is old.

## 2. Corrections to the audit

- Token restoration failed at 06:34, but gateway auth_success and Python kite_token_set occurred at 07:53:20 IST. The audit's instruction to log in based solely on the earlier event is stale. This establishes subsequent login, not a guarantee of present token validity. Verify current authenticated read-only quote success and exchange coverage.
- INFO cache_miss counts cannot establish a hit rate: cache_hit is DEBUG in the actual Production source. The quoted data_fetch miss is in the daily OHLC path, not proof of a broken intraday cache. Measure separate cache counters before changing TTL or keys.
- Confirmed in the running DB: September 9 FNO_PAPER -2052.85, MOMENTUM_PAPER -683.55, PENNY_PAPER +12.06; total -2724.34. These are paper results, not a verified loss from the user's real capital.
- Confirmed five closed NIFTY FNO rows since August 26, all losses, approximately -4983.92. A negative sample merits investigation; five observations cannot establish long-run expectancy or justify optimizing parameters against those same losses.
- The report lists HTTP 302/304 responses while saying zero non-2xx. It may mean no 4xx/5xx; correct the label.
- September 8 log coverage is explicitly partial in the report, despite its full-day headline. Separate DB day coverage from retained logs.
- Three portfolio status/summary messages do not establish useful manual trader advice. No error logs do not prove payoff correctness, malformed-input safety, reliable delivery or absence of memory leaks.
- No_or_break is a rejection condition, not a defect or reason to loosen the strategy. Neither low acceptance nor a quiet day proves opportunity loss. The report's market-regime explanations remain hypotheses without market evidence.

## 3. P0: complete the already-merged release

Owner: deployment operator. This review made no Production edits or container changes.

1. Record current checkout, image IDs and Compose services; inspect untracked docs and migration/ directory. Preserve these and take a consistent database/volume backup using the existing operational procedure. Never delete volumes to deploy.
2. Through the normal GitHub promotion process, fetch the release branch and fast-forward the Production checkout to the reviewed PR #85 target. Verify ancestry and resulting SHA. Do not pull main by accident. Stop on unexpected tracked changes or divergent history; do not reset them away.
3. Build the application services from that updated checkout and recreate them using the established Compose deployment procedure. A restart alone does not build new application code. Preserve the existing named data volume and secrets.
4. Verify runtime source fingerprints for main.py, config.py, research_archive.py and advisory modules against the target checkout. Verify all application services, not only Python. Record image IDs, container start times and release SHA together.
5. Run health, scheduler registration, migration and authenticated read-only route smoke checks. Inspect effective settings without printing secrets. Confirm broker execution remains governed by its intended existing settings; advisory activation must not enable Sentinel orders.
6. Run the one-time read-only retained F&O export from the passive-release runbook as the application user. Validate manifest hashes/counts, writable persistent archive directory and available disk. Account for the shared daily write budget before first collection; never bypass preservation on failure.
7. During the next market session confirm BOTH NIFTY and SENSEX requested/received tokens, matching instrument master, fresh provider and receipt timestamps, usable books, collection gaps and write-budget headroom. Outside market hours, stale observations are expected and cannot validate tomorrow's feed.

Acceptance: GitHub target, desktop checkout and running service evidence agree; archive survives restart; health is green AND collection can show actual observations. If any fail, stop declaring the release complete and identify the failed stage. Rollback must retain new archives and account for database migration compatibility.

## 4. P1: prevent another invisible deployment gap

Implement in Dev as a small independent release-engineering change:

- Embed release SHA/build UTC/service name in application images and expose non-secret version metadata through health/readiness.
- Add a deploy verification script that compares expected SHA to every running application service and exits nonzero on mismatch. Capture a release receipt with image IDs and smoke outcomes.
- Surface release identity on the dashboard and in future audits. Distinguish source deployed, feature enabled, input ready, strategy qualified and message acknowledged.
- Test stale-image rejection and mixed-service rejection. Never use healthy-container status or image creation date as proof of deployed commit.

## 5. P1: partner benefit and readiness

The present three daily portfolio messages are not the requested product. The merged release suppresses legacy portfolio monitoring and introduces independent intraday NIFTY/SENSEX manual advisory. Existing profile, evidence and qualification checks still apply; deploying alone does not promise tips tomorrow.

After deployment inspect the explicit INTRADAY profile, economic limits and per-index qualification readiness. Missing genuine evidence must be reported with its exact reason, not filled with dummy qualifications. A developer can implement and run research; the partner need not supply their personal strategy, broker account or order history for generic manual advice. Risk limits/exposure assumptions still need explicit values rather than guessed large-account sizing.

Expected eventual cards: exact exchange/contracts, actionable trigger, maximum entry cost, invalidation, target, expiry and intraday deadline, plus timely invalidation/exit updates. Conditional protection requires stated exposure assumptions; a directional debit spread is not automatically a hedge of the partner's portfolio. Current two-new-ideas cap prioritizes quality, and delivery can legitimately be zero when unqualified.

Use the existing explicit TEST/no-advice diagnostic, with operator authorization, to verify Telegram routing separately from strategy qualification. It tests connectivity, not quality or profitability. No message was sent in this review.

## 6. P1: ORB forensic investigation before retuning

Produce a reproducible case pack for all five losing trades and a matched set of rejected candidates. For each: chronological completed bars, opening-range boundaries, signal and bar times in IST/UTC, contract/lot mapping at entry, option quote freshness, entry/exit assumptions, spread/fees/slippage, stop/target and maximum risk, sizing, duplicate exposure and exit trigger. Identify actual versus modelled observations explicitly.

Check especially the two August 28 short trades: independent valid signals versus duplicate/re-entry behavior; don't assume duplication from same-day direction alone. Verify September 9 stop timing and option-loss calculation. Separate gross strategy move from costs and pricing-model error. Confirm loss relative to actual risk budget, not unrelated synthetic pool balances.

Deliverables: five reconciled trade timelines, classification of defects versus ordinary losing setups, and replay regressions for any demonstrated defect. Keep the strategy paper/research until its own promotion criteria are met. Do not send it to the partner merely because it already produces paper trades.

## 7. P1: build the research that can improve advice

Continue this in parallel with forward collection; do not wait passively for an arbitrary number of days.

1. Implement the exact intraday spread policy evaluator for both indices. The older modelled single-option ORB study is not a substitute for the new two-leg policy.
2. Retain both active legs through exit, including candidates rejected or not filled. A rolling ATM-only collector can lose evidence after the market moves.
3. Replay chronologically with no future data, synchronized executable-side quotes, quantity/depth checks, conservative no-fill/partial-fill handling, fees, slippage and the real intraday exits. Missing evidence must not create a profitable fill.
4. Compare a small frozen basket of candidate policies (e.g. breakout/retest and trend pullback) against the current baseline on identical sessions. Treat these as hypotheses, not recommended profitable strategies. Avoid adding many variants until the evaluator works.
5. Report net expectancy, drawdown, cost sensitivity, sample size, opportunity coverage, no-fill rate and time-to-alert separately by index/regime/policy. Reserve unseen sessions for validation and record every attempted variant to control selection bias.
6. Generate immutable genuine artifacts and review qualifications only for the exact tested policy and horizon. AI may explain or propose hypotheses; deterministic evidence must authorize delivery.

Acceptance: outcomes reproduce from saved observations; replay cannot access later packets; cost stress and unseen-session results remain visible even if disappointing. No promised win rate, income amount or qualification date.

## 8. P2: measure efficiency and missed opportunities

Add aggregate cache hit/miss/stale/parse-failure counters by daily versus intraday path, requested interval and provider latency. Avoid restoring per-ticker INFO hit spam. Use tests with repeated identical requests and expired data to distinguish correct caching from stale reads.

Add funnel timing from valid candidate to decision, risk approval, submission and outcome. Diagnose delayed or dropped opportunities independently of strategy rejection. Review momentum time stops against saved price paths; three losses do not justify automatically tightening filters. Keep penny liquidity controls until counterfactual research demonstrates a better net result.

## 9. Delivery order and completion evidence

A. Complete PR #85 local deployment and collect a runtime release receipt.
B. Add release identity/verification and truthful cache telemetry in Dev.
C. Produce ORB case pack and repair only demonstrated correctness defects.
D. Implement exact-policy replay and active-leg evidence while collection runs.
E. Review real per-index qualifications, then activate useful advisory under existing gates and measure latency/outcomes.

Each implementation handoff must list commit, tests, runtime prerequisites, enabled behavior and what remains unproven. Do not combine paper profits, fixture simulations and broker-realized returns. The income objective is served by reducing avoidable losses and proving net edge, not by forcing message or trade volume.

No implementation, merge, deployment, live order or partner message was performed in this assessment. Dev's GitHub tracking refs were refreshed; Production was inspected read-only. This new plan is the only new work product.
