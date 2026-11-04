# Overnight v2 enrichment — November 4, 2026

## Problem, authority and boundaries

Owner requests creative improvement beyond Overnight v2: strategy, portfolio,
execution and architecture are open. Audit current Dev `6e822e6`, preserve ON_V2,
old shadows, prior research/exam results and owner changes. All implementation
is in Dev. No deployment, real order, capital change or Breeze request.
Production evidence may be read/exported consistently and read-only.

## Contracts and intended files

New research-only enrichment module/runner and tests; new study artifacts here.
Reuse the broad overnight-v2 candidate data, shipped signals and fee functions.
Keep observations apart from next-session outcomes. Fixed Rs 25,000 risk capital
with no profit reinvestment is primary; compare inside identical execution and
fill assumptions. Preserve missing exits/carries and all failures.
Potential runtime enrichment is a separate, disabled paper/evidence path only
if its research or execution contract is supported. Do not rewrite the old
ON_V2 shadow, its history or frozen source to improve an old result.

## Research sequence

1. Verify the actual V2 baseline, phase clocks, fixed-capital accounting,
   corporate-action basis and causal inputs. Inspect current Production's
   overnight book/Oct-21 shadows by read-only export, without order/quote APIs.
2. Freeze no more than two candidate architectures in each of two development
   rounds. Start with (a) two-stock diversification/downside-risk allocation,
   (b) a funded regular/post-close execution split to reduce non-fill reliance.
   A second round may combine supported mechanisms or test a different payoff;
   explanations/changes must come from development evidence only.
3. Development: the already-seen broad 2023–2026 Yahoo and 2025–2026 Kite panels.
   Prior 2019–2022 exam is now seen and is secondary robustness, not a new exam.
4. Acquire public older history only into this new run, freeze an independent
   2015–2018 historical check before opening any of its prices/outcomes. Current
   surviving membership and split cuts remain explicit limitations; backwards
   historical generalisation is not a forward untouched-market qualification.
   No other reserved Penny/F&O/Breeze exam is used.
5. Freeze finalists and acceptance before the older-history score. Preserve
   all arms, sources, decisions, cash ledgers, coverage failures and stresses.

## Acceptance and audits

Require the same capital, costs, clock and fill model as V2; net and ex-best
positive, at least 10% more net than V2 or at least 20% lower drawdown with
at least 95% of V2 net, no unresolved exposure and >=100 closes on an adequate
historical check. Report annual results and complete opportunity denominators.
Test true-quantity/cash/fee identities, prefix causality, fixed-size withdrawals,
partial fills and adversarial winner non-fills. Compare execution changes at
equal fill availability; never market conditional official-close P&L as fills.
An architecture can improve robustness without improving ideal full-fill net;
report those as different outcomes, not one chosen headline.

## Execution research

Current Zerodha bulletin states post-close 15:50–16:00 and market pre-open
entry 09:00–09:05 (changed September 7). NSE's generic timings still show an
older 15:40 close-session start; archive dated authoritative evidence and use
the broker-supported window for broker-dependent logic. Quote volume does not
prove our order filled. Pre/post snapshots must exclude CAS volume where
applicable and preserve provider/receipt/last-trade timestamps. No live order
probe is authorized by this research request.

## Rollout/rollback and documentation

Commit freezes before scoring. Update guide/active plan/checklist with each
implementation commit, regenerate the atlas for declarations, and verify docs
immediately after commits. Stage only this task's slices; preserve owner bytes.
Any new shadow/collector stays disabled unless explicitly supported and within
the authorized paper scope. Rollback removes/disables only new paths; V2/book/
Oct-21 shadows remain unchanged. No schema migration of existing books, secrets,
dependencies or Production files is intended. Record source/commit/push/deploy
identity, verification commands/results and environmental limits.

## Initial status

Plan only; no new strategy score or code change yet. Existing Dev owner changes
and untracked parity files remain preserved. Production checkout `5e30ce0`.

## Round 1 outcome and round 2 freeze

Implementation/freeze commit 4d95c71; seven unit tests passed. Both panels
scored against identical native V2, four declared models, fixed capital.
Full-fill diversification lost 15% Yahoo net for 25% lower DD, failing the
95%-net hurdle. Half-regular routing lost 16% ideal net but increased
50%-winning-fill stress net by 41% (Yahoo) and 74% (Kite). It is a conditional
robustness candidate, not full-fill dominance. Kite leaves one exposure at the
end of available cached bars, so is partial evidence, not a formal pass.

Round 2: keep first ranked eligible pick; change its equal-weight second
partner only with >=20% lower estimated downside risk. Second hypothesis:
route half early only when the causal shrunk overnight mean clears full
modeled roundtrip costs; otherwise all post-close. No new learned predictor.
Older public acquisition: 874 requested, 443 returned, 710167 rows; no outcome
inspection or strategy score. Fresh check still sealed. Timing: use dated
broker's 15:50-16:00, not stale generic 15:40 start.

## Finalist decision before older outcomes

Round2 frozen commit a8976d1, nine unit tests passed. Anchoring preserved
more profit but failed improvement thresholds; reject both diversification
arms. Cost-aware routing preserved 96.5% ideal Yahoo net and raised net at
50% winner fills from 81310 to 96062, with lower DD. Half-regular remained
the best minimum-net development arm across four declared models, albeit
with much lower ideal profit. Freeze BOTH unchanged finalists now.

Separate predeclared robustness acceptance for older history: all four
models positive net/ex-best, >=100 closes, no open exposure; minimum net
across four models at least 10% above V2 minimum; maximum DD <=1.5x V2
maximum. This objective follows development diagnostics and is frozen
before older outcomes. Original same-model thresholds remain reported,
especially full-fill dominance. A robustness pass is not a full-fill pass.
No arm modification or new candidate after the older opening.

New script prepares public raw prices with validation and no repair, uses
original future split restrictions plus older split events, and builds
current shipped candidates. Universe survivorship and future split cuts
limit this check. Scoring cash/trade identities are assertions.
