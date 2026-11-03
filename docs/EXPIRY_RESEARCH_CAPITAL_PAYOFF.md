# Expiry: capital reuse and directional payoff investigation

No new strategy generation earned implementation. **E03.1 remains the latest
implemented expiry research candidate**, with its Dev paper switch off. Six new
alternatives were frozen in three rounds, scored and rejected. No native engine,
configuration, schema, flag, actual risk, Production or download changed.

The owner explicitly widened research risk authority. I tested whether daily
turnover restrictions, the two-ticket limit, or the option payoff itself blocked
earnings. These are distinct from another exit-parameter search, the earlier
fixed-time/quiet-day iron butterfly, and the earlier extra-lot/size studies.

## Scope and interpretation

105 selected NIFTY expiry-minute tapes: 52 in 2024 and 53 in 2025. Both years
were already used repeatedly to design earlier versions. These are seen-year
counterfactuals, not validation or actual historical returns. No 2023 or original
fresh-data exam price was opened. SENSEX/full 2026 chain tests are unavailable in
this frozen set. Minute OHLC cannot qualify an instant-entry/microsecond edge.

Each arm starts with its own 25,000 cash; current 65-unit lots and current native
NFO costs normalize comparisons. Continuous 2024-to-2025 cash and reset-year
experiments are separate. Severe uses each next bar's high to buy/low to sell;
this changes which orders fill, so it is a stress scenario, not a monotone
same-trade haircut. Twenty-percent bar-volume capacity and estimated spreads
are proxies, not executable depth. These books are not Sentinel system profit.

## Three rounds

1. NET_RISK_LEDGER frees returned principal and removes two-ticket/gross-spend
   limits, while realized daily cash minus the full new ticket reserve must stay
   above the funded daily loss allowance. PROFIT_REENTRY uses positive closed
   profits only after the original first two tickets. Neither uses paper peak
   gains to fund entry. Original signal, contract and E03.1 exits stay fixed.
2. CREDIT_8M / CREDIT_TREND use the same trend-pullback direction to sell the
   first opposite-side OTM option and buy protection 50 points farther away.
   This makes money on a modest favorable move or decay rather than requiring
   an exploding cheap option. Eight-minute and underlying-thesis hold policies
   are the two frozen primary arms. Entries end at 15:00, flat trigger 15:14.
3. HYBRID_8M / HYBRID_TREND keep the original cheap-ticket eligibility. A plan
   with multiple lots retains E03.1; only an eligible one-lot plan can become
   credit, if funded at decision. A failed next-bar credit fill cannot fall back
   to a long based on the observed result. All positions share one sequential
   cash/risk/cooldown ledger within that arm.

Credit/hybrid daily original risk reserve is 5,000 instead of 2,500, with the
same inherited 1,500/3,000/4,000 cash drawdown brakes. The user did not impose
these research caps; I chose them before scoring. Rejection does not depend on
the caps: no new primary alternative beats E03.1 in both reset years.

## Continuous-book money (rupees after model fees)

| Model | Ordinary net | Worse fills | Severe fills | Worst ordinary day | Realized drawdown | Ordinary fees |
|---|---:|---:|---:|---:|---:|---:|
| E031 | 12,426.71 | 11,497.60 | -3,234.08 | -478.01 | 1,373.93 | 2,100.79 |
| NET_RISK_LEDGER | 12,426.71 | 11,497.60 | -3,599.64 | -478.01 | 1,373.93 | 2,100.79 |
| PROFIT_REENTRY | 12,426.71 | 11,497.60 | -3,234.08 | -478.01 | 1,373.93 | 2,100.79 |
| CREDIT_8M | -1,754.69 | -2,397.74 | -1,511.22 | -1,206.57 | 2,001.43 | 717.94 |
| CREDIT_TREND | -2,148.32 | -2,794.60 | -585.50 | -1,206.57 | 2,506.26 | 718.32 |
| HYBRID_8M | 7,105.60 | 6,307.66 | -424.84 | -513.36 | 1,417.74 | 3,534.90 |
| HYBRID_TREND | 8,394.84 | 7,213.81 | -121.63 | -1,397.66 | 1,890.19 | 3,425.41 |

Realized drawdown is from day-close cash peaks; it is not intraday NAV. For
ordinary fills the independently reconstructed complete-bar NAV drawdowns were
1,838.85 for E03.1, 1,741.67 for HYBRID_8M and 2,397.96 for HYBRID_TREND.
The eight-minute hybrid's lower sampled NAV drawdown comes with much less profit;
it is not an income improvement. No missing NAV marks occurred in primary runs.

## Reset-year experiments (do not add these to continuous-book money)

| Model | 2024 ordinary | 2024 worse | 2025 ordinary | 2025 worse |
|---|---:|---:|---:|---:|
| E031 | 8,897.97 | 8,271.27 | 3,528.74 | 3,226.33 |
| NET_RISK_LEDGER | 8,897.97 | 8,271.27 | 3,528.74 | 3,226.33 |
| PROFIT_REENTRY | 8,897.97 | 8,271.27 | 3,528.74 | 3,226.33 |
| CREDIT_8M | -1,754.69 | -2,397.74 | 622.98 | -194.63 |
| CREDIT_TREND | -2,148.32 | -2,794.60 | -1,341.45 | -1,441.26 |
| HYBRID_8M | 5,418.28 | 5,008.91 | 1,687.32 | 1,298.75 |
| HYBRID_TREND | 7,131.73 | 6,115.42 | 711.76 | 1,098.39 |

The ledgers add no ordinary/worse-fill tickets at all: all three still take 41
over the two years. NET worsens severe fills to -3,599.64 versus -3,234.08.
Here the original cash/entry limits are not the earnings bottleneck.

E03.1 ordinary net excluding its best day is 6,576.75. HYBRID_8M leaves 1,255.64
and HYBRID_TREND 2,544.88. HYBRID_8M's 2024 reset turns negative without its best
day; HYBRID_TREND's 2025 reset does too. Every new continuous increment excluding
its largest incremental day is nonpositive. Full checks: decisions.json.

## Do inherited brakes hide a good credit strategy?

No. With no drawdown brakes, but cash/collateral and funded daily risk still
binding, CREDIT_8M takes 44 ordinary tickets and loses 2,630.64; CREDIT_TREND
takes 44 and loses 1,496.99. Their ordinary fees are 4,362.89 and 4,356.99.
The 8-minute version makes 1,732.25 before fees but loses after fees. Without
brakes HYBRID_8M stays 7,105.60 and HYBRID_TREND drops to 7,486.10.

Fixed controls do not supply a replacement. Unbraked adverse reverse-direction
credit loses 7,979.34; 6/10-minute holds lose 5,217.62 / 5,395.30. Additional
one-percent-plus-tick friction loses 3,962.30. A 100-point hedge barely trades
(one continuous trade, none in the 2025 reset) because its full reserve rarely
fits the daily cap. That result establishes limited feasibility, not a broad
claim that wide spreads cannot work. All 60 diagnostic histories are retained.

## What the losses and winners teach

- The original one-lot positions earned 6,858.27 over 31 ordinary tickets.
  They were not dead weight just because they cannot leave a partial runner.
  Nine two-lot positions earned 5,121.72 and one three-lot position earned 446.72.
  This is attribution on seen data, not a new lot-count trading filter.
- A trend view does not automatically transfer between payoffs. Credit changes
  which strike is exposed, caps favorable gains, needs a hedge and four orders,
  and faces a different losing path. Its upfront receipt is not earned profit.
- E03.1's 41 ordinary tickets included 20 negative tickets,
  classified by final exit: 9 STOP, 1 STRUCTURE, 8 TIME, 2 TRAIL. A stop/trail
  trigger is followed by a later fill and cannot guarantee its price. Exact
  ticket cash/events are retained; no loss is excluded from the books.
- Several high-return days remain influential. Credit does not discover new
  hero moves; it gives up the convex long-option gain on replaced positions.
- Faster polling has no measured profit here. Without timestamped bid/ask depth,
  order-arrival, partial-fill and cancellation evidence, treating a price jump
  as an earlier executable order would invent the edge being sought.

Final-exit counts are mutually exclusive (loss-attribution.json).
No inference that *all* market jumps come from a named participant or a unique
cause follows from these OHLC/OI files. Earlier skeletal bootstrap loss-year
percentages are conditional model outputs, not calibrated future probabilities.

## Execution, margin and residual assets

Vertical terminal loss is bounded by strike width less credit before costs.
That accounting identity is described by [Zerodha Varsity](https://zerodha.com/varsity/chapter/bull-put-spread/)
and the [Options Industry Council](https://www.optionseducation.org/strategies/all-strategies/bear-call-spread-credit-call-spread).
Neither establishes an intraday fill or an Indian broker margin requirement.
[NSE's margin rules](https://www.nseindia.com/static/products-services/equity-derivatives-margins)
use SPAN and additional margin components. Historical broker SPAN/ELM, atomic
basket execution and queue positions were not available here.

The model therefore requires full width plus liquidation/fee buffer in own cash
and explicitly reports margin/execution as UNQUALIFIED. A losing cash-only model
does not need optimistic broker leverage to be rejected. Shorts are closed first;
an unsellable fully paid long hedge would be retained as a zero-lower-bound asset
with assumed writeoff separate from realized fills. An unclosed short halts the
book and makes following dates unavailable. No such residual/unresolved exposure
occurred in the 108 primary/control histories or 60 fixed diagnostics.

## Verification and reproducibility

- Freezes committed before their scores: f34ceb9 ledger, ff34d6b credit,
  2d0fe98 hybrid, 698a128 diagnostics. Sources/rules/results remain immutable.
- The ledger baseline reproduces 99 independent-year position/event histories
  across fills (an earlier progress note called these histories imprecisely).
  Hybrid control reproduces baseline day cash and complete original events.
- 108 primary/control histories replay exactly; 1,037 repeated long positions
  match shipped E03.1 actions/fees, 991 credit positions reconcile leg cash/fees,
  reserves and clocks; 54 actual input prefixes rebuild without future readings.
  Another 60 diagnostic histories independently reconcile. These repetitions
  are verification coverage, not independent statistical samples.
- Original prefix audit exited 1: the old research cache keyed temporary objects
  by Python id, which can be reused. Source/error retained. Frozen v2 uses the
  uncached original signal for prefixes and checks cached full signals against it;
  primary scores unchanged. Full scored tapes stay alive, so that collision did
  not contaminate these scores. No native engine cache was changed.
- 49 focused checks pass; new Python compiles; regenerated 295-module atlas is
  unchanged. Full engine suite was not rerun because native code did not change.
- ledger_guard.py verifies selected DBs, 713 older/source evidence hashes, exact
  owner documentation suffixes and Production identity/diff after each commit.
  Python 3.11.9 / NumPy 1.26.4; offline scoring; no provider calls or 2023 read.

Commands from the run folder (use python-engine/winvenv/Scripts/python.exe):
ledger_study.py score; credit_study.py score; hybrid_study.py score;
payoff_diagnostics.py score; payoff_audit_v2.py; package_report.py.
Score files are append-only: rerunning a completed score intentionally refuses
to overwrite. Audit functions replay and compare existing results instead.
Raw chosen-year SQLite inputs remain ignored in the earlier E02 _local folder;
hashes/required dependency locations are in initial.json and evidence/data-proof.json.

## Decision and remaining work

No E03.2 or increased live risk is justified by this round. E03.1 itself remains
a seen-year paper hypothesis and loses under severe fills. No generation name
can make that evidence stronger. Keep the frozen fresh-data family exam intact
and gather genuinely new executable paper outcomes before increasing size.
If researching execution next, test decision-to-fill prices/quote age/fees on
new timestamped quotes and compare rejected orders too; record fast orders before
evaluating them. No current finding warrants changing the trading engine.

Dev research is committed/pushed through the receipts recorded in STATUS.md and
completion-receipt.json. Production, N11, A/B/C/D and native E variants are
unchanged; no migration or rollout is needed. Research rollback is stopping this
isolated lab. Sealed receipts: evidence/REPORT.md, with pinned verification after
later documentation commits. Passing receipts/tests verify mechanics and hashes,
not future profitability or partner qualification.
