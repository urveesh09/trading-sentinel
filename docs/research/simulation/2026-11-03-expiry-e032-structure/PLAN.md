# E03.2 second investigation: information and execution

Owner request November 3, 2026: investigate mechanisms beyond parameter search,
including microstructure, and earn a materially better expiry rule if evidence permits.
This explicitly reopens the seen-year research stopped by the earlier E03.2 plan.

## Contracts and boundaries

- Dev only. Preserve every original working byte, earlier failure, freeze and receipt.
- NIFTY 2024/2025's 105 expiry-minute tapes are **seen development**, forever.
  NIFTY 2023 and the pending 2026 E03-family exam remain protected. No download,
  broker, scheduler, provider, messaging, flag, Production or capital change.
- Same E03.1 stops, runners, 65-unit normalized lot, fees, 25,000 own cash,
  1,250 ticket, 2,500 daily original-premium reserve, two sequential tickets and
  continuous cash/drawdown brakes. Current lot/fees are a normalized experiment.
- Four-strike causal selection cap retained. No historical theoretical option
  prices or trade-volume-as-order-imbalance claims. Minute data cannot validate
  queue priority, subsecond execution, signed flow or dealer inventory.
- Shipped E03/E03.1 controls must reproduce all daily money/events before scoring.
  Decisions read completed bars; executions use the next bar and inherited
  ordinary/adverse/severe fills, costs and capacity. Stops can gap.

## Round 1, two distinct candidates frozen before score

1. **PATIENT**: retain E03.1's entry signal and chosen contract. Instead of paying
   up to 10% above its decision ask, leave a buy limit at the decision last trade,
   good for the next three bars, with no repricing or chase. Fill only if the
   next executable open plus the scenario's crossing costs is within that limit;
   an intrabar touch never earns a fill. Cancel after three attempts, 15:00,
   or a completed underlying reversal beyond one decision ATR. Preserve the
   original decision's index stop; start the holding clock on actual fill.
   Hypothesis: reduce price-spike adverse selection without inventing spread capture.
2. **OPTION_LED**: a new entry source, same E03.1 exits and cash. Use the three
   nearest strikes to *current* spot (within 100 points; both calls and puts
   quoted with volume now and three bars earlier). At least two pairwise
   call/put log-price-ratio changes must agree with the median direction; median
   directional change must exceed its own preceding 20-bar median absolute
   three-bar change. Spot and independent future must agree over three bars.
   Require a new direction crossing (not repeated same-direction signals).
   This is an option-price leadership **proxy**, not signed order flow.

## Decisions and validation

At most two primary candidates per round. Preserve every negative result. Any
later round needs its own mechanism, code, committed freeze and fixed tests;
no genome over the old E03.1 thresholds. Robustness diagnostics cannot silently
become a new optimum. A candidate is materially better only if:

- Each year ordinary/adverse net beats E03.1; continuous net exceeds it by 25%
  at both fills; both years' ex-best-day net positive.
- Continuous incremental net excluding its best incremental day positive;
  worst day and realized drawdown no more than 10% worse than the baseline;
  no unresolved exposure or enlarged reserve. Report marked drawdown separately.
- Delay, added friction, neighbouring *mechanisms*, concentration, random controls
  and chronological stability support it. Severe losses are never hidden.

Even a passing seen-year result is only a paper hypothesis. A real qualification
needs independent execution evidence and the separately frozen future exam.
No claim that any rule can ensure profits or zero loss. If none passes, deliver
the concrete failed mechanisms, useful findings and an executable next research
contract; do not rename failure as a winning E03.2.

## Files, checks, rollout and remaining work

All new research and frozen outputs in this directory; plain report will be
`docs/EXPIRY_RESEARCH_E032_STRUCTURE.md`. Engine unchanged unless a supported
candidate later earns separate disabled-paper implementation and tests.
Unit checks target causal signals, no lookahead, limit expiry/cancel, gaps,
cash and event parity. No engine changes means no repeated full engine suite.
Update guide/plan/checklist on every commit, staging only our new prefixes;
atlas regenerated only if engine declarations change. Verify immediately after
every commit and remote after push. Rollback: stop this isolated research;
there is no runtime migration, activation or deployment to roll back.

Remaining at freeze: literature and metadata audit, baseline, two primary scores,
mechanism diagnosis, independent checks, report/receipts and Dev push.
