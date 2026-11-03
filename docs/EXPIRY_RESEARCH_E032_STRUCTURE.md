# E03.2, a different investigation: what survives costs?

November 3, 2026. **No supported E03.2 replacement emerged. E03.1 remains the
lead research candidate, disabled and not deployed.** I tested six distinct
mechanisms and a quote-level fast-trading idea, rather than search more E03.1
thresholds. None earned a material improvement with comparable downside.
The useful new finding is an actual small price-prediction effect that trading
costs completely consume.

All work is isolated Dev research. No engine, scheduler, flags, `.env`, existing
database schema, Production, N11/N11T or A/B/C changes. No download, broker call,
order or message. NIFTY 2023 and the separately frozen future exam stay protected.

## What the new mechanisms did

The same 105 NIFTY expiry afternoons in 2024/2025, the same continuous Rs 25,000
book, current normalized 65-unit lots, current fees and drawdown brakes:

| Mechanism | Ordinary net | Adverse net | Worst ordinary day | Decision |
|---|---:|---:|---:|---|
| **E03.1 control** | **+12,426.71** | **+11,497.60** | **-478.01** | Remains lead |
| Patient entry: wait at decision last price, at most three minutes | +11,753.37 | +9,769.72 | -526.42 | Earns less in both years |
| Option-led entry: paired call/put prices move before a trend-pullback signal | -4,030.96 | -4,140.70 | -556.65 | Loses and halts |
| Failed auction: index and future sweep and reclaim their prior range | -2,614.92 | -2,825.84 | -711.66 | Loses |
| Value check: expected eight-minute move must pay for decay and fees | +6,292.86 | +5,642.96 | -478.01 | Removes profitable trades |
| Nearer-money debit vertical: change theta/vega and cap the payoff | +1,850.30 | +791.72 | -651.23 | Much less; loses in 2025 |
| Symmetric long butterfly: buy an interval payoff | -4,020.59* | -4,174.11* | -954.22* | Rejected; unresolved exposure |

*Butterfly values include a conservative full-premium charge for an unresolved
pack. They are retained failed-model diagnostics, **not verified closed-book
returns**. That model also frees the conservatively written-off pack for later
sessions, so its continuation cannot establish a valid flat overnight book.
The evidence receipt rejects its portfolio claim. No official settlement was
invented. The other five alternatives also fail the predefined comparison.

Both years had already been used extensively. Committing these mechanisms
before scoring prevents changing the story after a score; it **does not** make
the years untouched again. The option-led book stops trading after its 2024
drawdown halt; its continuous 2025 zero activity is not a safe or profitable year.

## The fast-entry/fast-exit test

This uses actual recorded five-level quotes, rather than minute-price fill
guesses. Four already-seen NIFTY expiry dates have adequate five-level packets:
October 13, 19, 27 and November 3, 2026. October 6 contains compact top-level
packets and is unavailable for this test, not a zero-return day.

The fixed idea: buy a cheap OTM option when displayed five-level bid size newly
exceeds ask size by 2:1, with spot and future moving in its direction. Decide
on one snapshot, buy one lot from the **next** snapshot's asks, then measure
the first available bid-depth exit after 30 or 120 seconds, including native
charges. Limits, quote freshness, actual whole-lot depth and the Rs 1,250 ticket
ceiling apply. No fill is awarded on the decision quote or an intrabar touch.

| Average per measurable one-lot event | 30 seconds | 120 seconds |
|---|---:|---:|
| Midpoint movement | +3.09 | -3.86 |
| Spread and depth cost | 3.73 | 3.74 |
| Buy/sell fees | 48.64 | 48.62 |
| **Net executable markout** | **-49.28** | **-56.22** |
| Positive after costs | 15.8% | 21.1% |

There are 315 signals per horizon, 298 measurable entries and 17 refused
entries, with no missing exit among those entries. These are overlapping
conditional observations across **four days**, not 298 independent new trades.
**Their sum is not portfolio P&L.** Each day's average net is negative at both
horizons. The observational control without a pressure crossing is negative
too (-55.68 / -57.25 mean); this is not a randomized causal comparison.

At 30 seconds the small gross prediction is consumed by spread/depth even
before fees. Native fees average about 9.2% of premium for these one-lot
observations. Restricting quote age to two seconds still gives -46.20 / -60.40;
waiting an extra entry snapshot gives -51.62 / -59.98. No winning age or latency
setting was selected.

The recordings arrive roughly every ten seconds. Request waits and quote ages
are recorded separately; neither measures exchange order latency. This rules
out **this observed scalp**, not every possible subsecond edge. It cannot
justify a faster scheduler or increased capital.

## What failed, and why it matters

- **A better buy price can lose the trade.** Patient entry saves money on some
  tickets but misses winners and admits other losing fills. Its severe-fill
  model improves from E03.1's -3,234.08 to +29.61, but removing its best severe
  day leaves -1,108.46; 2024 alone still loses 410.45. This is a risk/profit
  tradeoff, not a dominant replacement. Under another fixed 1% plus tick of
  execution friction it earns only +4,407.57 ordinary / +3,571.44 adverse,
  against the control's +11,364.46 / +9,113.34.
- **Another signal source is not automatically information.** A broad
  call/put-price impulse and a failed-range-break pattern buy many moves that
  do not continue enough to pay. Both lose in each reset-year experiment.
- **A model of fair value can remove genuine convex winners.** The normal-model
  gate uses only current prices and past volatility/drift, but stationarity,
  stable skew and Gaussian movement are hypotheses. It cuts the large 2024
  runner and does not improve 2025. Model prices never become fill prices.
- **Financing a nearer option changes the economics.** The vertical reduces
  the long premium but caps winners and doubles execution legs. The butterfly
  adds another leg and loses if the move overshoots its profitable interval.
  More fees and coordinated fills outweigh their attraction here. Simultaneous
  per-leg fills are explicitly hypothetical, not proven atomic broker execution
  or margin offsets. Terminal payoff bounds do not guarantee liquidation prices.

## What deeper research actually supports

Short-horizon order-book research uses changes in supply and demand, including
quote updates. Trade volume alone is a weaker substitute. We do not possess
that history in the 2024/2025 minute chains, and ten-second snapshots miss book
events. This motivated the new pressure test; it does not establish an Indian
options edge. [Cont, Kukanov & Stoikov](https://arxiv.org/abs/1011.6402).

High open interest does not reveal which side dealers hold. Research estimating
dealer gamma uses buyer/seller-capacity trade records, information our history
does not contain. There is no justified signed dealer-gamma signal hiding in
our OI totals. U.S. findings are not a NIFTY validation.
[Amaya et al., 0DTE Index Options and Market Volatility](https://cdn.cboe.com/resources/education/research_publications/gammasqueezes.pdf).

A further trap is settlement. A simple average of minute index prices is not
the official NIFTY closing index built from constituent closing prices, so no
last-minute settlement arbitrage is credited here.
[Nifty Indices calculation FAQ](https://www.niftyindices.com/resources/index-concepts/faqs).

Claims that Rs 20 lakh became Rs 10 crore describe a 50-fold outcome; without
verified complete account history, losses, capital changes and executable fills,
they supply neither an entry rule nor evidence of repeatability. This study
does not establish whether any particular story is true or false.

## What is retained

E03.1 stays unchanged. The earlier fixed 8% entry-limit hypothesis stays in its
original, independently frozen exam. The six mechanisms here are rejected;
PATIENT remains an offline execution-risk diagnostic. No E03.2 switch or
paper book was added just to produce a version number.

The useful next distinction is **predicting a price** versus **predicting a move
large enough to trade after all costs**. A future microstructure study needs
streamed, time-aligned quotes, latency measurement and a genuinely new set of
expiry dates. Kite full-mode packets can supply five-level quotes and exchange
timestamps; they still cannot prove our queue priority or every order event.
No subscription or connection was started here.
[Official Kite streaming documentation](https://kite.trade/docs/connect/v3/websocket/).

The existing future E03-family exam is preserved, and the separate data/test
contract is [NEXT_EXAM.md](research/simulation/2026-11-03-expiry-e032-structure/NEXT_EXAM.md).
Neither an account-size increase nor an activation is part of this work.

## Verification and status

- All E03/E03.1 daily events and money reproduced before primary scoring.
- Every one of 63 frozen primary book histories reproduced offline; 1,287
  repeated position records independently reconciled for cash, fees, pack legs,
  reserves and causal clocks. These are not 1,287 independent market trades.
- **55 focused checks passed**: 18 new research checks and 37 unchanged native
  E02/E03/E03.1 checks. No full engine-suite claim: runtime code did not change.
- Atlas regenerated and byte-identical; all original owner working bytes,
  earlier research, selected-year data and Production identity/diff preserved.
- Every failed output remains. Three primary freezes and the quote-evaluator
  freeze preceded their scores. Qualification is false; no guarantee of profit
  or of a stop filling at its trigger.

Technical record and reproducible commands:
[README](research/simulation/2026-11-03-expiry-e032-structure/README.md),
[verification](research/simulation/2026-11-03-expiry-e032-structure/verification.json),
[daily results](research/simulation/2026-11-03-expiry-e032-structure/daily-results.csv).
Commit/push and sealed-report receipts follow in the study status record.

Research **9950a6c** is pushed and remote-verified on the same Dev branch. No deployment or flag change. [Sealed report](research/simulation/2026-11-03-expiry-e032-structure/evidence/REPORT.md); [pinned verification](research/simulation/2026-11-03-expiry-e032-structure/pinned-audit.json); [completion receipt](research/simulation/2026-11-03-expiry-e032-structure/completion-receipt.json). After documentation changes HEAD, run `verify_structure_evidence.py`; it checks the original source commit without relaxing or rewriting the helper guard, request or report.
