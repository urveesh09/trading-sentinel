# Current-system retrospective assessment — October 3, 2026

Testing finds activity in several modules, but retained history does not support
a complete quarter portfolio backtest or a full replay of today's F&O policy.
Penny MIS is not a zero-trade system in Production. Its strict replay is sparse
largely because very little complete minute history survives in the frozen cache.
None of these results establishes current-policy profitability or qualification.

The owner requested tests first and discussion of improvements afterward. No
threshold, entry/exit, sizing, capital allocation or execution policy was tuned.
The only engine correction closes EDGE's SQLite read handle on return/exception;
its first failed run is preserved and subsequent runs bind the corrected source.

## Design and evidence

- F&O: September 17–October 1, 2026 inclusive, IST.
- Other modules: July 1–September 30, 2026 inclusive, Q3. The source calendar
  declares 65 sessions. Momentum also has a separately declared August 11–
  September 30 diagnostic; it does not replace the failed full-quarter attempt.
- Current Dev source baseline: `556209c`, plus the recorded EDGE handle correction.
  Production checkout/release is `044c016`; its historical operational records
  span changing versions. Dev algorithms and Production history are distinguished.
- Fixed current universes: 100 Penny names (file as of October 1) and 500 stock
  names. Historical membership, regime, breadth, events, scheduler priority,
  broker acceptance and fills are not reconstructed by these universes.
- Production's engine was stopped during collection and remains stopped at the
  final read-only check. Its stable DB, WAL and universe files were copied into
  Dev, with stopped-state checks before/after. One local read-only transaction
  collected 873,285 intraday and 213,184 daily rows. Legacy SQLite BLOB values
  were preserved as bytes rather than converted into money or valid prices.
- Frozen snapshots, source/config/settings hashes, raw report hashes and failed
  attempts are retained. Large evidence is in ignored local `_local/`; tracked
  manifests and receipts bind it. Copying quote journals was not atomic with SQL.
- These retrospective windows are DEVELOPMENT research, not untouched holdouts.
  No provider calls, new data purchase, orders, service restart or promotion.

[Pre-execution plan](2026-10-03-current-system-backtest-plan.md) and
[machine receipts](research/2026-10-03-current-system/) contain the exact contracts.
All monetary numbers below are rupees. Missing results are unavailable, not zero.
Offline adapters bind their declared Dev defaults, not reconstructed historical
runtime environment overrides. For example, standalone Penny uses its existing
100,000 paper bankroll and 500 per-stock cap; the joint study uses 2,000 cash.
Momentum retains 4,500/2,500 bankroll/pool defaults. These are simulation
contracts, not a reallocation of the owner's live book budgets. The research
cash reconciler is not the live P1 fee/buffer reservation protocol.

## Module comparison

| Module | What was actually tested | Result | What remains unproven |
| --- | --- | --- | --- |
| F&O single-leg | Full-policy attempt plus recorded-entry exit attempts | Full policy unavailable; all 9 exit paths insufficient | Current entry selection, pricing, risk admission and executable exits backward through the window |
| F&O debit spreads / iron condors | Existing defined-risk exit contracts against recorded rows | All 7 retained structures unavailable: exact bound leg identities absent | Current structures, executable multi-leg fills, shared capital and margin admission |
| Classic Penny MIS | Shipped minute evaluator, paper admission and tracker lifecycle; complete sessions only | 1 closed trade, **+37.43**, 0 unresolved; PARTIAL | Full-quarter performance and historical scanner/context |
| Classic Penny CNC Connors | Shipped paper scanner/tracker on evidenced partial daily candles | 0 entries from 1,487 evaluations; net unavailable | Whether valid missing sessions would generate trades; live CNC behavior |
| Joint Penny cash | MIS/CNC streams reconciled against unchanged 2,000 cash default | 1 admitted/closed; cash 2,037.43, locked 0; PORTFOLIO_PARTIAL | Full historical scheduler and other books' admission |
| Adaptive Penny EDGE/Connors | Current daily scanner including ranking/selection | 1,242 candidate appearances, 168 daily selections across 65 scans | Fills, entries, exits, shared cash and profitability |
| Intraday Momentum | Current MOM_BASE evaluator and declared virtual T1 exit | Quarter unavailable; Aug 11–Sep 30 diagnostic: 18 virtual closes, **−89.13** | 16 exits use next-day data because EOD is missing; live partial runner, regime, broker and shared cash |
| Swing | Shipped daily evaluator with actual required index history | Unavailable: no evaluable sessions after index warm-up | Any valid entry/exit or quarter performance |
| Range Reversion | Shipped completed-bar evaluator | 32,411 decisions; 1,095 ENTER verdicts | Whether those verdicts turn into profitable executable trades |
| Partner advisory/protection | Catalogue/source boundary checked | No historical money-book adapter or qualification result | Advisory/protection outcomes; cannot be counted as auto-trades |

Candidate appearances, selections, ENTER verdicts and accepted signals are not
filled trades. Results from these scopes cannot be added into one system profit.
Old daily proxy adapters and constant-IV synthetic options were not substituted
for the shipped paths. The joint Penny replay reuses MIS/CNC streams and must not
be counted as an additional independent strategy profit.

## F&O: recorded cash versus a fresh policy backtest

The exactly linked paper subset was refreshed from retained position/ledger
evidence. It is unchanged from the earlier assessment:

| Recorded paper book | Closed outcomes | Wins/losses | Window cash | Profit factor | Realized cash drawdown |
| --- | ---: | --- | ---: | ---: | ---: |
| Single-leg | 9 | 5 / 4 | +10,755.67 | 4.23 | 2,056.25 |
| Defined-risk spreads | 7 | 5 / 2 | +3,187.60 | 3.70 | 850.66 |

Combined recorded cash is +13,943.27. It is **not** a fresh current-policy
backtest. No FNO_LIVE sample exists in this evidence. Global older-history
reconciliation still has missing/duplicate terminal-cash problems; the small
exactly linked window does not reconcile the entire July–October history.
Recorded paper settlements, including legacy spread modeled economics, do not
prove broker executable fills or current pricing realism.

Single-leg gains depend heavily on two winners of approximately 7,434.53 and
4,710.54. Removing both leaves approximately **−1,389.40**. Removing the best
spread winner leaves +1,527.03. This is a concentration diagnostic, not a reason
to cut winning trades earlier. Sixteen outcomes across a small, correlated
session sample cannot establish dependable expectancy. Realized cash drawdown
also omits intratrade and open-position losses.

For new tests, the registered full-policy Lab runner explicitly remains
UNAVAILABLE until verified futures instrument/timeframe inputs are supported.
The retained token cache has some five-minute rows, but a token count alone
does not supply a verified full-policy input contract and complete executable
options selection history.

Nine single-leg recorded entries were also tried against retained quote
journals. The original full-day packets correctly rejected pre-entry receipts.
The separately preserved post-entry retry had 63–270 paired observations per
entry; **all nine** still failed the existing 120-second maximum-gap contract.
No gap was removed or gate relaxed. All seven spread entries failed exact leg
identity validation. Therefore no fresh exit-replay P&L is reported. Manifest
candidate scaffolding is not a scored improvement or permission to change exits.

## Penny: activity, gates, coverage and exits

Production operational evidence contradicts “no trades in three months.” The
quarter contains **84 accepted MIS signal observations across 29 stocks**, with
1,723,330 rejected observations. The later-added execution audit contains 27
ENTRY_FILLED/POSITION_CREATED events and 16 settled exit events. These audit
counts do not provide complete quarter profitability or prove every accepted
signal filled. Repeated scanner evaluations are correlated observations.

Only 17 of those accepted observations belong to the frozen current 100-name
Penny universe; 67 are outside it. Today's membership cannot reproduce the
historical scanner simply by applying current code backward.

| Requested Penny stock-days | Complete | Partial | Unavailable |
| --- | ---: | ---: | ---: |
| July (2,300) | 1 | 38 | 2,261 |
| August (2,100) | 149 | 374 | 1,577 |
| September (2,100) | 39 | 895 | 1,166 |
| Quarter (6,500) | **189** | **1,307** | **5,004** |

The primary complete-session replay can use only **2.91%** of requested
stock-days. Across its 70,875 evaluations, the largest rejections are volume
pace (28,484), time window (25,155), breakout confirmation (16,340) and circuit
proximity (659). It accepted/filled one SIGACHI trade on August 18: 18 shares
at 27.58, exit at 29.69, gross 37.98 less 0.552 charges = **37.428** net.
The shipped tracker exited at 14:30 using `SMART_EOD:within_0_5R_of_target`.
One favorable outcome and zero realized drawdown are not strategy validation.

The predeclared **allow-gaps sensitivity** used 1,496 stock-days, preserving
the incomplete data designation. It produced 17 accepted signals, 14 fills,
9 closes and **5 unresolved trades**. Two admissions were occupied and one had
an already breached stop. Closed outcomes were 2 wins / 7 losses, **+54.81** net,
profit factor 2.48 and realized closed-cash drawdown 37.14. Removing its best
winner leaves **+0.29**; the existing adverse-fill bound is **−11.59**.
The five unresolved trades are not zero losses or proven profitable exits.
These numbers describe a closed subset, not a total portfolio return.

The same sensitivity was applied to joint MIS/CNC cash accounting. Of 14
lifecycle fills, the joint 2,000 cash ledger admits **7**, settles **3** and
retains **4 unresolved**; 7 additional fills are cash-rejected. Realized P&L is
**+79.59**, free cash **118.03**, and locked entry notional **1,961.56**.
The equality 118.0313 + 1,961.56 = 2,000 + 79.5913 reconciles cash movements;
locked notional is not marked equity or proof of its recoverable value.
This admission-selected closed subset differs from standalone MIS's nine
closes and must not be aggregated with them. Daily
standalone MIS lifecycle replay does not reconstruct cross-day portfolio
occupancy; the joint ledger makes that limitation visible without manufacturing
missing exits.

In the recorded Production funnel, roughly 39.1% of MIS rejections concern
volume, 29.1% the time window, 17.1% breakout confirmation and 5.4% PR3/HOT.
Another 8.1% have opaque `evaluator returned None` reasons. Those historical
reasons span changing versions; they are not current-policy gate attribution.
They nevertheless identify the diagnostics to retain for a later improvement
discussion. Loosening all gates solely to increase counts is not supported by
the fragile sensitivity result.

CNC had zero accepted Production signals in the retained quarter and zero
entries in the current replay. The replay lacked partial-candle evidence for
5,013 stock-days. Its 1,487 evaluations rejected RSI below-threshold (535),
below-200-SMA (439), below-50-SMA (261), RSI not rising for two bars (149), and
insufficient history (103). That is a restrictive combination on the observed
subset, but not proof of zero opportunity across missing dates.

EDGE is materially more active at the evaluator level: 1,242 candidate
appearances and 168 selections. Selections may repeat stocks on different
days. Neither is a trade count, and a full EDGE exit/cash lifecycle remains
absent. The Windows cleanup fix enables deterministic offline testing without
changing this scanner's numeric decisions.

## Momentum, Swing and Range

Momentum's full Q3 request fails on missing/legacy interval provenance.
Verified 15-minute retention begins August 11. On the fixed 500-name universe,
July has no usable 15-minute stock-days, August has 6,486 partial/4,014 unavailable,
and September 9,945 partial/555 unavailable. None meets the full 25-bar
complete-session contract; many end around 14:30. The separate shorter test
retains these coverage limits instead of claiming a complete quarter.

The shorter diagnostic uses unchanged MOM_BASE defaults: bankroll 4,500,
momentum pool 2,500, declared BULL/REGIME_1_NORMAL context, shadow slippage/MIS
costs, stop-before-target for ambiguous bars, and full quantity at T1. It does
not model the live partial T1 runner/trail or account-wide admission. The
Production quarter separately contains 218 accepted Momentum signal
observations, which are historical activity rather than the diagnostic's fills.

The shorter diagnostic processed 359,105 bars across 499 evidenced stocks and
33 sessions. It accepted 19 prefixes yielding 18 distinct ticker-day candidates.
All 18 virtual trades closed: 6 wins / 12 losses, gross **−47.93**, costs **41.21**,
net **−89.13**, profit factor **0.53**, mean R **−0.187**, and realized simulated
drawdown **134.82**. Dominant rejections were no recent VWAP crossover (233,628),
minimum candles (49,293), volume surge (37,863), late entry (15,918) and failing
to hold VWAP after crossing (14,899).

**Exit fidelity is the key limitation:** 16 of 18 closes use the adapter's
`overnight_gap_exit` at the next available later-day bar; only one is a stop and
one is a target. Missing end-of-day bars prevent the intended intraday time exit.
These are the existing virtual replay rules, not evidence that the live system
held MIS overnight. Its −89.13 cannot be attributed to today's live exit policy
or regarded as a reliable intraday performance estimate. A later lifecycle
adapter must leave such missing exits unresolved rather than using next-day
prices as a substitute for a known intraday settlement.

The adapter scored three chronological splits (−66.39, −12.31 and +4.16).
`oos.available=true` means its arithmetic split was scored, **not** a predeclared
untouched holdout or full-system qualification. Only MOM_BASE was tested and
the date window was already historical.

Swing fails because aligned NIFTY/BANKNIFTY prior history is below its required
214-row ATR baseline. Aligned prior rows are 69 on July 1, 98 on August 11 and
133 on September 30. The retained BANKNIFTY series begins March 17. This is
missing warm-up evidence, not a finding that Swing generated zero opportunities.
No ETF or tested stock was used as an invented index substitute.

Range produced 1,095 ENTER decisions, 1,943 WAIT_NO_LOWER_TOUCH,
350 WAIT_RANGE_EXPANDING and 29,023 WAIT_RANGE_NOT_INTACT. It can recognize
candidate setups. Until its actual execution/exit/cash lifecycle is bound, these
counts cannot tell whether it enters or exits profitably.

## Completion and discussion boundary

All frozen runs finished, including unavailable and failed attempts. No result
replaces an unavailable primary. [Consolidated machine summary](research/2026-10-03-current-system/summary.json)
and [integrity receipt](research/2026-10-03-current-system/verification.json)
record final manifests, report/data hashes and preservation checks.

An additional review found that the partial Penny ledger sorts timestamp
strings, while MIS entries are UTC and exits are IST. The actual primary and
sensitivity cash metrics were independently recomputed with normalized UTC
clocks and **agree exactly**, so this defect did not change these results.
It remains a prospective parity defect for same-day mixed-offset streams.
Before expanding this adapter, normalize all aware clocks to UTC, preserve
CNC date-only exit conservatism, and test cross-offset ordering, identical-clock
ties and partial settlement. Do not label the current ledger FULL_PORTFOLIO.

Final verification: 28 focused tests passed (one existing HTTPX deprecation),
Python compilation/diff checks, immutable snapshot/raw report verification,
unchanged original/final metrics, current transitive policy hashes, raw-to-compact
operational counts and deterministic atlas regeneration. Source/research commit
and immediate post-commit consistency are recorded in the
[completion receipt](2026-10-03-current-system-test-completion.md).
No runtime configuration or migration impact; Dev only, no push/deployment.

The evidence supports a later discussion in this order: historical coverage and
point-in-time context; Penny admission-to-fill and unresolved-exit diagnosis;
CNC gate interactions; EDGE/Range/Swing lifecycle binding; Momentum partial
runner and shared-capital parity; executable F&O instrument/quote capture and
winner concentration. A strategy change needs its own frozen comparison and
future qualification window. No “smarter” strategy implementation is part of
this test request.
