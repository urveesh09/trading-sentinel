# N10.1: improve the mechanics without manufacturing a winning backtest

November 2, 2026. Dev research only. Source freeze `c567f8e`
preceded every score. Controls `f4f92f2` reproduced all
16 prior annuals and 856 economic lifecycles. Production was not edited,
restarted or deployed. No order, Telegram message, capital or live setting changed.

## What was tested

Exactly two hypotheses, specified in [PLAN.md](PLAN.md), on the SAME already
studied 2023–26 years. No feature grid, new entry filter, strategy/member/side
exclusion, threshold tuning or extra size beyond N10's three-lot research cap.

**WATCH_FLAT** corrects N10's excessive floor release: a release requires a flat
account, insufficient free equity for a typical one-lot contract, a selected
contract no more expensive than the median of the last 20 earlier closed shadow
trades, and N10's original 20 newly closed profitable paper outcomes. The 5%
slice and 75% deepest bound remain. A rejected expensive option while holding
another trade is not evidence that the account is permanently stuck.

**PREMIUM_LOCK** also changes the earned third lot. An underlying-price trail
does not guarantee an option price. Before adding, the option's BID must support
a raised premium stop whose net proceeds cover the added lot's 25% premium-stop
loss plus both tranches' fees and extra stress. A refused add changes no stop.
Retry is explicit once per observed minute above+1R; one successful add maximum,
never from 14:45, no re-add after a stopped child. Existing native exits continue.

The 15 earned lots in the original N10 all had cost-aware premium-stop losses greater
than their declared child-risk proxy;12 original combined premium-backstop
exposures exceeded5000. These are alternative planned-risk measurements, not
additional realized losses. An underlying stop may exit sooner; it does not
guarantee the premium. See [diagnosis](n10-risk-diagnosis.json).

## Annual results

Rs 250,000 FRESH each year, normalized 65-unit lots, current fees, archived
candle-derived modeled bid/ask and extra stress. These annual totals are NOT
one compounded account. All amounts below are modeled rupees, never broker P&L.

| Book | 2023 | 2024 | 2025 | 2026 to Oct 28 | Total |
|---|---:|---:|---:|---:|---:|
| N08 | -37,581 | 76,294 | 58,647 | 104,924 | 202,284 |
| N09.1 | -32,684 | 76,294 | 46,738 | 99,870 | 190,218 |
| N10 one try | -32,898 | 79,334 | 46,738 | 105,311 | 198,484 |
| N10 retry | -32,898 | 88,805 | 51,583 | 125,786 | 233,275 |
| N10.1 WATCH_FLAT | -32,898 | 88,805 | 51,583 | 125,786 | 233,275 |
| N10.1 PREMIUM_LOCK | -32,684 | 80,030 | 54,122 | 100,120 | 201,588 |

| Book | Worst day | Worst annual closed drawdown | Double-cost total | Without own top five winners |
|---|---:|---:|---:|---:|
| N10 retry | -6,127 | 13.21% | 168,672 | 106,281 |
| N10.1 WATCH_FLAT | -6,127 | 13.21% | 165,934 | 106,281 |
| N10.1 PREMIUM_LOCK | -6,127 | 13.13% | 128,938 | 62,059 |

- **N10.1 WATCH_FLAT:** does NOT pass economic superiority. Failed checks: higher four-year profit, profit under doubled extra costs, account value at every tested cost.
- **N10.1 PREMIUM_LOCK:** does NOT pass economic superiority. Failed checks: higher four-year profit, profit under doubled extra costs, profit excluding the five best winners, account value at every tested cost.

The strict benchmark was N10 RETRY, not the easier N08 or N09.1 total. Passing
mechanical safety/correctness checks is a separate finding and cannot turn a
failed economic test into success. WATCH_FLAT leaves the inherited retry and
underlying-risk proxy unchanged; only PREMIUM_LOCK repairs the latter.

## Continuous account and cost robustness

No yearly deposit/reset. Carry equity, the floor, decision-observed WATCH peak and consumed
paper evidence across all four years. Cost 199/200/202/400 means the EXTRA cost
function `(base + base/40 * lots)*lots`; modeled spread and current native fees
remain in every arm. The original N10 fine cliff map held its quadratic term
fixed, so these newly declared tests must not be mislabelled as exact replays
of that old map. All three new accounts face the identical cost function.

| One continuous Rs 250,000 account | Cost 199 | Cost 200 | Cost 202 | Cost 400 |
|---|---:|---:|---:|---:|
| N10 retry | 427,697 | 427,440 | 427,111 | 410,161 |
| N10.1 WATCH_FLAT | 427,712 | 427,452 | 425,872 | 400,420 |
| N10.1 PREMIUM_LOCK | 429,214 | 401,475 | 428,392 | 361,046 |

WATCH paper evidence remains N10's frozen one-lot N08 stream at its original
base stress cost, including in cost-stress arms. Stress changes actual simulated
book cash/reserves/stop funding, not that observer's evidence model. This is a
declared inherited assumption, not a fully re-estimated double-cost shadow.

Lowering the floor spends MORE of the account's lifetime loss budget. It is not
a free recovery or proven predictive edge. The research's 75% bound and three
lots do not change the live 15% halt or one-lot trial. A planned option stop can
gap or fail; all premium remains funded above the floor, and the replay exits
at observed bids, not invented trigger-price fills.

## Attribution and uncertainty

`results.json` records each year's matched-entry delta, changed exits, added
and missed trades, earned-lot contributions, net without the five largest
winners, and 201-week paired comparisons with a 4-week block bootstrap. These
are descriptive uncertainty on seen data, not a new significance test or a
posterior probability of profitability. Read the matched delta alongside the
added/missed net: new admissions can arise from cash/brake feedback rather than
better forecasting. A price-backed stop may protect gains but cut a winning
trade's normal pullback; that opportunity cost stays in the result.

Earned-lot net itself is 34,695
for PREMIUM_LOCK versus 30,440 for N10.
The remainder of total net (original positions plus admission/cash feedback)
is 166,893
versus 202,836.
Thus a better-looking add-on contribution can still harm the whole strategy.
Do not tighten the profitable base trade solely to justify another lot. Any
future alternative should preserve base exits and budget added risk honestly,
using actual cash/option-stop exposure rather than guaranteed continuation.

## Verification

80 declared annual executions: 16 controls, 16 candidate annual/cost experiments,
48 continuous year slices. Maximum TWO replay workers. 100 distinct focused tests
pass (27 N10.1/independent validation, 49 N10, 24 native cost/planner/exit/replay).
No full-engine-suite claim. Atlas regenerated: 291 modules, no diff.

Independent checks: `{"books": 80, "cash_identities": 6066, "funded_adds": 71, "modeled_prices": 8608, "money": 4125, "native_admissions": 3914, "premium_stop_lifecycles": 71, "states": 76, "watch_attempts": 1465, "watch_releases": 6}`.
The audit independently calculates fee arithmetic, reconciles cash including
child closes, checks exact modeled quote prices, own-cash/full-premium reserves,
funded-stop economics, every new premium stop's observed life, strictly earlier
paper evidence/non-reuse and window-keyed terminal state/continuity. Cash-event
drawdowns are retained beside the published combined-trade closed-drawdown basis.
Neither is mark-to-market/open-position drawdown. See [VERIFICATION.md](VERIFICATION.md).

The separate [WATCH peak audit](watch-peak-audit.json) reconstructs actual
closed-cash peaks at every release, including carried history. Every observed
release uses the correct peak and respects its 75% bound. Its saved terminal
`best` can lag a final winning close in 18
windows because WATCH updates during planning. The audit retains BOTH that
decision-observed field and the independently calculated actual peak, without
rewriting the frozen policy or its cash. Update tracking on every settlement
before an operational integration; do not advertise a stale terminal field as
an exact high-water mark. No historical release was justified by that lag here.

## Limitations and next action

- Every 2023–26 year was already seen. Even two well-motivated hypotheses may
  still benefit from selection. No claim of an overfit-free profitable strategy.
- 2023 remains a losing year. No known-in-advance day classifier or direction
  edge has been established. Safer position management cannot manufacture one.
- Modeled one-minute quotes are not executable depth; prior clipped requests
  and coverage gaps remain. Lot 65/current fees are normalized research, not
  dated historical broker returns. Stop gaps/slippage/live failures can be worse.
- A Rs 12,500–15,000 one-lot trial cannot inherit this Rs 250,000 reserve policy.
  Do not remove its risk guardrails or allocate more capital from these results.
- Keep the original N10 [2022 exam](../2026-11-01-fno-n10/EXAM_2022.md) unchanged.
  2022 was not acquired, opened or analyzed here. Any new-arm exam needs a
  separately frozen supplement BEFORE reading that data. Its strict driver was
  added after the original round-two source freeze; bind the actual driver too.
- Next useful evidence is a separately frozen forward shadow of N08/N10 and
  the retained correction, with keyed admissions, quote paths, cash/floor and
  actual fee/latency records, fixed review dates/minimum evidence and no broker
  authority. Registering a scheduled task/deploying this code is separate work.

Research wrappers are not a shipping runtime feature. Keep all prior results,
including the failed price-backed hypothesis. No more same-year parameter search
in this round. Primary references: [SOURCES.md](SOURCES.md).
