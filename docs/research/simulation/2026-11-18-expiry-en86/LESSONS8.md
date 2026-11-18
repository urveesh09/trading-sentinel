# Round 8 — reviewed conclusions and practical decisions

Read this with ANATOMY8.md, its complete tables and the immutable results8.json.
These conclusions were written after the single frozen score. No candidate was
retuned or promoted. All figures below are modeled paper research after charges.

## What actually improved

**EN87 is the useful lead from this round.** It combines E03's existing timing
with a strong agreeing OI state. On the same 2,500 symmetric parent/day envelope:

| NIFTY, 197 studied expiries | Matched E03 | EN87 |
|---|---:|---:|
| Independent-session ordinary net | 3,006.43 | 6,114.14 |
| Independent-session adverse net | 2,245.82 | 5,840.68 |
| Net without the best two expiries | -1,298.13 | 2,644.90 |
| Parents / traded expiries | 55 / 48 | 25 / 23 |
| Worst expiry | -1,463.85 | -1,463.85 |
| Continuous 30,000 wallet ordinary net | -3,445.43 | 5,305.89 |
| Continuous wallet adverse net | -4,034.97 | 4,948.38 |
| Wallet ordinary liquidation drawdown | 3,938.99 | 2,448.21 |

The worst single expiry is unchanged. The improvement is lower accumulated
wallet drawdown and better sample payoff, not elimination of a large individual
loss.

How it earned the difference: it retained 25 same-clock/same-side parents and
excluded 30 control parents. Those 30 included **13 winners and 17 losers**, net
**-2,601.10**. Changed available room/size on retained parents adds **506.61**.
The total sample improvement is 3,107.71; it is not entirely a pure forecast-side
effect. The unrelated-day OI control made -118.16 ordinary / -387.72 adverse,
but its much lower activity is not a matched-exposure significance test.

The win rate is only 12/25, or 48%. The average winning trade is 1,071.46 and the
average losing trade is -518.72. This illustrates why trade win rate alone cannot
judge profitability. This is different from an underlying-direction hit rate;
do not compare 48% directly with EN71's conditional direction-accuracy curve.

## Why EN87 is not an established replacement

- Newest studied year **2026 still loses -2,451.29** ordinary (-1,662.73 adverse).
  Annual ordinary results: 2023 +570.77, 2024 +2,094.68, 2025 +5,899.98, 2026
  -2,451.29. Do not hide the recent weakness behind the cumulative improvement.
- The paired mean gain is only **15.78 per expiry**, with a long-group 95%
  interval **[-46.07, +75.60]**. Its raw comparison p is 0.292 and Holm18 p is 1.
  Neither superiority to E03 nor positive expected income is established.
- All dates have already been used for research. A committed freeze protects
  this version from tuning during scoring; it cannot make these dates untouched.
- It is **less active**, not faster or more comprehensive: 25 parents over197
  expiries. At that historical pace, twenty parents need roughly 158 expiries.
  The registered 100-expiry limit is likely to finish INCONCLUSIVE. Do not lower
  the support requirement or widen the gate after seeing this result.
- EN87's ordinary net is about 31 per expiry across the whole sample. It does
  not meet the owner's earlier daily high-return ambition. Capital sitting idle
  is not counted as a profitable trade, and no separate-module profits are added.
- Native E03 made 14,275.20 in independent sessions, but uses different sizing
  and made -4,122.87 in its continuous wallet. Do not claim EN87 beats native
  E03 on every metric; the fair primary comparison is the matched envelope.

Practical decision: **forward comparison only, unchanged size, separate shadow
identity**. Keep E03.2 and EN55 registrations unchanged. EN87 is not a reason to
commit real capital, loosen the drawdown brake or replace the main paper policy.

## What each of the remaining slots taught us

**EN86, received information.** The synchronized Nov17 pilot covers 5,367/5,400
decision seconds (99.4%). It has 99 overlapping events but only 10 independent
eight-minute-separated events. Mean signed future move is 1.49 points at 30 seconds and
0.41 at 180 seconds over the available event observations. One day cannot validate the
mechanism, a profitable direction forecast, its regime persistence or paper fills.
The required 20 covered expiries / 100 nonoverlapping events are absent.

At raw OI clocks, the canonical one-lot fixed-eight-minute action lost 11,164.09,
versus random-side expectation -10,163.61. At residual clocks it lost 28,298.49
versus -38,782.50 random. These are overlapping hypothetical actions, not wallet
P&L. They show that a lead is not portable across size/exit/admission choices,
and that beating random can still mean losing money. All canonical controls
(price, lag, unrelated day, leave-traded-strike-out) remain in results8.json.

**EN88, residual OI.** -10,865.26 ordinary / -23,578.85 adverse on 252 parents.
Compared with raw EN83 it adds 213 different parents losing 12,380.95. Shared-clock
parents change by only -40.93. Stripping the price relationship and making this
residual-crossing rule more active did not create a fundable edge. That does not
prove every possible conditional OI forecast lacks information.

**EN89, better entry price.** -3,531.18 / -3,296.83 on 31 parents. The deterministic
delay control loses 5,342.08 / 9,528.99. The pullback rule helps versus that delay
but still loses. It uses entirely different entry clocks from the immediate raw
book, so “bought cheaper” cannot be asserted from total P&L. Reclaims can fail,
while profitable runaways never offer the required pullback/ceiling.

**EN90, contraction.** -3,027.34 / -8,661.12. It removes 83 raw parents whose net
was -5,165.57, but adds 103 losing 12,885.09. The decomposition is a correct
identity and identifies distinct OI changes; its specified entry rule does not
pay. OI contraction does not prove a particular trader was covering a short.

**EN91, longer holding.** +18,686.48 / +3,371.47 independent-session net. On 158
shared parents, holding longer adds 17,828.03. Examples: August 7, 2025 adds 12,085.35
and September 7, 2023 adds 6,875.88. There is real payoff opportunity after eight minutes
in some studied trades. But January 13, 2026 gives back 1,780.83 versus the short hold;
ordinary2026 alone loses 10,659.84. Without its two best days the whole book
loses 7,979.36. Most decisively, its continuous wallet loses 3,972.02 and reaches
the halt on May 23, 2024 (adverse: April 18). **Reject it for a continuous wallet.**
The frozen mechanical TAIL SCREEN label describes concentrated independent-day
payoffs; it is not an approval and must not hide the survival failure. There is
no drawdown reset or fresh money to recover access to the later winners.

**EN92, more responsive option.** -1,674.30 / -9,713.69. On 159 shared clocks it
improves net 963.85 versus the one-lot old chooser, but 34 additional parents lose
2,244.75. The contract can improve some matched opportunities while changing
affordability/admissions in a harmful way. A matched-contract improvement does
not establish improvement of the complete trader. Those “new-only” parents are
an explanatory cohort, not an observable hindsight filter we may now deploy.

**EN93, direct net forecast.** -516.94 / -1,010.61 on only 9 funded parents. It
has 51 eligible historical model dates and nine positive conservative-score
potential events. Intercept/no-information controls select none in the same
forecast panel. The selected sample is too small and loses; better calibration
cannot be claimed. Keep INCONCLUSIVE under the registered support rule; do not
turn the zero threshold down just to force activity.

**EN94, information exit.** +2,400.11 / -5,274.56. On 165 shared parents it gives
back 1,278.03, and a changed admission misses another 844.27 winner. It saves some
losers, but on September 12, 2024 it cuts 3,409.19 off the large call winner. Price/OI
reversals can interrupt genuine runners. Faster exit is not automatically better.

**EN95, combination.** -2,150.61 / -3,062.52 on 35 parents. Removing its information
exit produces exactly the same total: the extra exit did not alter the funded
combined path. Removing the reclaim entry is less bad ordinary (-367.20) but
much worse adverse (-8,455.28). No component mixture is promoted. The predetermined
combination prevents choosing an attractive-looking ablation after seeing money.

## Data, implementation and evidence limits

- NIFTY:197 previously studied afternoons, 2023–Oct2026;196 have >=95% OI
  decision coverage under the new panel contract. Source/warmup abstentions and
  gaps remain visible. No performance-selected day exclusions are made.
- SENSEX:63 baseline-control afternoons; its OI is not supplied, so every new
  OI-dependent strategy is DATA UNAVAILABLE, never a zero-profit book.
- Raw EN83 in this version earns4,522.41 ordinary rather than round7's4,722.49;
  new source/zero/covered-history semantics change a parent. Its adverse result
  is unchanged. The old record is preserved; comparisons here use the explicit
  new raw control, not a silently rewritten historical baseline.
- Next-bar opens, synthetic spreads and20%-of-bar-volume capacity are declared
  bar proxies, not an observed order book at the opening instant. The packet
  pilot is information research, not a full packet-lifecycle test of all slots.
- Engine source/configuration, E03.2 and EN55 policies, `.env`, main F&O, broker
  orders, Telegram and Production were not changed. No downloads were made.

Verification:24 mechanics tests plus3 post-score reporting checks;2,340 control
arm-days with identical order ledgers;216 signal prefixes;51 chronological model
checks and6 prefix forecasts;196 financial identities,2,603 parents,5,363 order
events,1,773 primary-day replays. The12-date forward rehearsal produced97 eligible
arm-days exactly matching the score; the second run added zero results. Strict
coverage excluded some dates and missing SENSEX OI stayed missing.

The3 extra reporting tests accompany a versioned `review8.py` adapter: a cell
with no eligible observations reports null money, not an empty sum of zero. It
also makes the continuous-wallet rejection of EN91 explicit. Frozen source,
strategy parameters and scored results are unchanged. No full engine-suite pass
is claimed because this task changes only research and documentation.

Next useful work is prospective source evidence and an unchanged EN87 comparison
with honest activity/power expectations. Do not manufacture a more active “winner”
from these already inspected results. The causal information may be weak,
transient, priced into the option, or simply not exploitable by the permitted
premium budget; this round narrows those questions but does not settle them.
