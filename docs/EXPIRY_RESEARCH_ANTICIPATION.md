# Expiry anticipation: can we recognize the hero before buying it?

November 3, 2026. **I found weak precursor information, but no supported E03.2
or reason to increase the system's actual risk.** Five frozen rounds tested
nine primary hypotheses: larger-lot allocation, executable-tail probabilities,
after-cost return forecasts, forecast-gated sizing and nonlinear combinations.
All failed the fixed acceptance tests. E03.1 is unchanged, disabled, not deployed.

The user authorized modest extra research risk. I bounded it at 25% more
ticket/day reserve, with the same cash and absolute drawdown brakes. No engine,
config, `.env`, flag, existing schema, N11/N11T, A/B/C/D or Production change;
no download, broker, order or message. The 2023 reserve and future E03-family
exam remain untouched. These are research outcomes, not live returns.

## 1. A little more risk buys a little more money, with worse losses

E03.1 sometimes has only one lot, so at 2x it cannot both sell and retain a
runner. I tested funding a second lot on those original entries. Same original
contract, signal, stop, floor and exits; at most Rs 1,562.50 per ticket and
3,125 original premium/fees per day, versus 1,250 / 2,500. Same own Rs 25,000,
two sequential entries, three-lot ceiling, no profit recycling or leverage.

On all 105 NIFTY expiry afternoons, **continuous cash across 2024 and 2025**:

| Model, after fees | E03.1 | Second lot when affordable | Same extra budget, ordinary sizing |
|---|---:|---:|---:|
| Ordinary net | +12,426.71 | +13,548.73 | +13,458.11 |
| Adverse net | +11,497.60 | +12,437.73 | +12,415.18 |
| Worst ordinary day | -478.01 | -601.89 | -682.90 |
| Realized ordinary drawdown | 1,373.93 | 1,453.42 | 1,532.18 |
| Sampled marked ordinary drawdown* | 1,838.85 | 2,044.63 | 2,113.87 |
| Severe net | -3,234.08 | -4,130.67 | -4,130.67 |
| Worst severe day | -646.89 | -1,218.45 | -1,218.45 |

*Complete-bar model bid marks with charges, omitting unavailable/insufficient
marks; not intrabar or broker-depth NAV. Realized and marked drawdown differ.

The second-lot version earns **Rs 1,122 more**, about **9%**, with up to 25%
more reserve allowed and **12.5% more total reserve actually consumed**. Its
worst severe day nearly doubles. The increment comes from four improved and
three worsened days; removing its best incremental day leaves +407.78. The
large March 28, 2024 hero is unchanged. This is extra exposure, not a new entry
edge, and fails the risk-normalized test in both years.

The allowance also has lot-rounding cliffs. At 20% extra, the second-lot model
earns only +11,413 ordinary / +10,074 adverse; at 30%, +13,528 / +12,391. These
were fixed coarse diagnostics, not a search for the best budget. With another
fixed 1% plus one tick of execution disadvantage, its adverse net is +6,014.56,
versus unchanged E03.1's +9,113.34 under that same stress. Stops do not guarantee
their trigger price, and a full-premium loss remains possible.

## 2. I tested the factors before the move

There are **18,787 decision-time candidates** across the same 105 expiries.
At each completed afternoon minute and direction, the selector takes the
nearest affordable original one-lot option, priced 5-20, within four strikes
and the original move-reach allowance. It uses no future strike availability.

The outcomes require an actual next-bar adverse entry and a later executable
sale at a 2x or 5x trigger, before a 35% hard stop, index stop or 20-minute clock.
Future highs alone never count. This is much stricter than asking whether some
option somewhere briefly printed 5x during the afternoon.

| Executable target reached before stop/clock | 2024 | 2025 |
|---|---:|---:|
| 2x | 10.36% | 13.47% |
| 5x | 1.93% | 1.46% |

These overlapping candidates are **not 18,787 independent trades**. There are
only 105 expiry-day clusters. Eight 2025 fivefold-label experiments lack a
completed exit: they remain explicit conservative non-hits/full-premium training
losses, not removed losers or invented settlements. No-entry attempts remain
represented. Funded portfolio experiments have no unresolved positions.

The 16 causal features include option momentum/acceleration, relative traded
volume, OI changes, index/future movement, basis changes, directional efficiency,
distance/noise, minutes left, fee hurdle and option-implied forward. Training
normalization never reads test-year values. Each training expiry totals weight
one, so repeated minutes do not pretend to be thousands of independent days.

I trained 2024 before scoring 2025; reversed years are a separate backwards-time
diagnostic. The main chronological path trains on the first 13 expiries, then
refits only from completed prior quarters. Both years were already used by the
research program, so these are **seen-market model-transfer tests**, not newly
independent market validation.

## 3. What actually predicts a little, and what does not

A fixed descriptive check takes feature thresholds from 2024 and measures 2025.
It does not select a trading rule, and the observations overlap:

| 2025 candidate group | Fivefold hit rate |
|---|---:|
| All eligible candidates | **1.46%** |
| High relative traded volume | 1.77% |
| Closer strike relative to recent index noise | 2.05% |
| High recent option momentum | 1.32% |
| Strong directional futures-basis change | 1.37% |
| Low OI growth/change | 0.97% |

Volume and proximity have a small association with future heroes. **Both
groups still have negative average model returns after costs.** OI change is
not trader identity or signed dealer inventory; low growth is not necessarily
short covering. Some associations change substantially when the years reverse.
A factor that raises a rare outcome's probability slightly is not sufficient
to make a buyer profitable, much less win on most tickets.

## 4. Combined forecasts did not produce a robust trader

The first fixed logistic models predict executable doubles/heroes. Their
conservative full-premium-loss hurdle admits no trades. That is abstention,
not successful safe income. In 2025, the top 5% of the 5x model's rankings hit
only 1.69%, versus 1.46% generally; those rankings are diagnostic, not a
hindsight rule that buys the best minutes of the day.

Because that hurdle can be too conservative for a stopped trade, I separately
froze forecasts of **actual adverse net returns**, with fixed regularization
and bounded training tails. No threshold was searched. This permits profitable
low-win-rate behavior if the model can actually identify it.

On the **92-day chronological evaluation** (April 4, 2024–December 30, 2025),
each arm starts with its own Rs 25,000 and continues cash/brakes:

| Model | Ordinary net | Adverse net |
|---|---:|---:|
| E03.1, same evaluation calendar | **+6,212.55** | **+5,458.74** |
| Forecast double's after-cost return | -3,113.15 | -3,414.64 |
| Forecast hero's after-cost return | -3,052.53 | -3,061.19 |
| Fixed probability models | No entries | No entries |
| Fixed nonlinear forests | No entries | No entries |

Do not compare those 92-day numbers to the full 105-day sizing table as if
they shared a cash history. The chronological test excludes its 13 training
days, including the large March 2024 runner, from every arm's evaluation.

One result initially looks encouraging: the hero-return model trained on 2024
makes +3,641.91 ordinary / +3,483.42 adverse on 2025, slightly above E03.1's
+3,528.74 / +3,226.33. But realized drawdown is **3,533 / 3,580**, versus
**831 / 746**, and the worst ordinary day is -899.85 versus -478.01. Its
backwards-year and chronological results lose. It fails the predeclared risk
limits and cannot rescue itself with one profitable transfer.

I also tested nonlinear interactions: 64 shallow trees bootstrapped by expiry
day, fixed seed/depth, at least six distinct days per child and eight-day
shrinkage. No seed, feature, leaf or depth was chosen by test profit. They found
no positive after-cost admissions. This does not prove every nonlinear method
or faster input is useless; it rejects these fixed models on this evidence.

## 5. The model did not help allocate risk either

The final selective version keeps E03.1 completely, consulting only the existing
past-quarter hero-return forecast before funding the extra second lot. It
does not create standalone model entries or fit anything new to ticket outcomes.

It makes **+12,517.55 ordinary / +11,539.69 adverse**, only **+90.84 / +42.09**
above E03.1, while ordinary realized drawdown rises to 1,651.27 and the worst
ordinary day to -601.89. It worsens one 2024 day and improves one 2025 day;
without that incremental winner, the increment is negative. **Rejected.**

## What the deeper search changes about the explanation

The barrier is not simply finding any price prediction. Original research on
option jumps documents some delayed adjustments, yet finds actual spreads can
remove abnormal returns. Predictability and executable profit are separate.
[Kanniainen & Magris](https://arxiv.org/abs/1810.12200).

Research finding useful volume signals uses participant-class information and
other horizons that our minute history lacks. Aggregate volume or OI cannot
be renamed that richer signal.
[Michael, Cucuringu & Howison](https://arxiv.org/abs/2201.09319).

Our minute tests cannot identify subsecond leadership, queue changes, order
initiators or pre-news information. A faster loop alone has no demonstrated
edge here. A new claim would need timestamped independent quote streams and
cost/latency tests on new days, rather than more fitting to these same years.

The auction remains separate. The current cash-close framework changed in
2026; these 2024/2025 labels use the earlier regime and cannot validate a
2026 auction strategy or treat a provisional index as settlement.
[NSE CAS operational circular](https://nsearchives.nseindia.com/content/circulars/CMTR73362.pdf).

## Verification, remaining work and status

- **53 focused tests pass**: 16 new research checks and 37 unchanged native
  E02/E03/E03.1 tests. No full engine-suite claim; runtime did not change.
- **111 saved book histories** reconcile, including 1,580 repeated native
  position replays and 1,654 native sale slices: zero action/money mismatches.
  These are repeated scenarios/controls, not 1,580 independent market tickets.
- All **37,574 target labels** recompute exactly; all features recompute exactly;
  **210 real truncated-history rebuilds** match. Prior-quarter model training
  boundaries and sample/day counts verified. Offline audits attempted no network.
- Fixed 20/30% reserve neighbours and extra-friction checks retained, with
  every failed result, model coefficient/tree and acceptance decision.
- Atlas regenerated byte-identical. All earlier work, original owner bytes,
  input DB hashes and Production identity/diff preserved. No dependencies added.
- **No accepted E03.2, risk increase, live/paper enable, migration or deployment.**
  Failed models do not consume the protected E03-family future exam. That exam
  and new observed execution remain future evidence requirements, not a promise
  that these mechanisms will work. E03.1 remains the research lead.

[Technical record](research/simulation/2026-11-03-expiry-anticipation/README.md),
[verification](research/simulation/2026-11-03-expiry-anticipation/verification.json),
[all decisions](research/simulation/2026-11-03-expiry-anticipation/decisions.json).
The study status records commit/push and sealed evidence receipts.

Research **22f8845** pushed/remote-verified on the same Dev branch. [Sealed evidence report](research/simulation/2026-11-03-expiry-anticipation/evidence/REPORT.md); [pinned source verification](research/simulation/2026-11-03-expiry-anticipation/pinned-audit.json); [completion receipt](research/simulation/2026-11-03-expiry-anticipation/completion-receipt.json). After later docs change HEAD, run `verify_anticipation_evidence.py`; it preserves and verifies the original source/request/report/guard rather than weakening it.
