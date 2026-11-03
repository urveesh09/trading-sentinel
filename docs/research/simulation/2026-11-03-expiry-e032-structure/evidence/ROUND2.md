# Round 2: failed auction and physical-versus-priced movement

Written after the committed Round 1 scores. All 2024/2025 remain seen. PATIENT
lost ordinary/adverse profit (11,753 / 9,770 vs 12,427 / 11,498); OPTION_LED
halted in losses. Do not tune these into a new optimum.

Two new primary mechanisms, no change to the loss allowance or E03.1 exits:

1. **RECLAIM** changes the entry. A completed index bar sweeps the previous
   20-bar low/high and closes back inside, with a body in the reclaimed direction.
   The independent future must also sweep/reclaim its own previous 20-bar
   boundary on that same bar. Buy the reclaimed direction's original cheap
   option using inherited four-strike, price, reach and fee constraints. This
   tests failed auctions/reversals instead of efficient-trend pullbacks. No
   minimum sweep distance, volume threshold or optimized pattern settings.
2. **VALUE_CHECK** retains E03.1 entry/strike. Estimate the expiry forward from
   the median of K+call-put at the three nearest contemporaneous paired strikes
   within 100 points. Invert that ticket's current price into a normal-model
   total standard deviation. Project its eight-minute value with remaining
   implied variance plus eight minutes of trailing 30-minute realized variance.
   Directional drift is the smaller of index/future ten-minute mean returns,
   less one standard error (trailing noise/sqrt(10)), floored at zero. Admit
   only if projected bid less buy/sell fees exceeds the current ask. Use the
   normal model only as a **hypothetical signal**, never a historical fill.
   The expiry-forward snapshot avoids confusing monthly futures basis with
   same-day exercise value. No claim that price-derived sigma equals physical
   probabilities, stationary skew or known settlement. Missing/invalid pairs
   mean refusal, not guessed prices. Original entry limit stays 10%.

Shared acceptance is PLAN.md; both candidates must pass the same material-gain
test. No new optimized coefficients. Freeze implementation/tests before scoring.
Record all years, fills, continuous and reset-year books, daily/trade evidence.
Remaining: score; if useful stress mechanisms without choosing a best threshold;
otherwise close with learning and a concrete microstructure evidence contract.

Research caution: NIFTY's published final index close uses constituents' last
half-hour weighted closes. A minute index average is not that official value.
No supposed last-minute settlement arbitrage or synthetic settlement proceeds
will be credited. U.S. SPX studies motivate hypotheses but do not prove NIFTY edge.
