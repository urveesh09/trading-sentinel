# Round 3: change the payoff, not the E03.1 thresholds

Round two failed: the reclaim book lost and halted; the value filter earned
6,293 ordinary / 5,643 adverse versus E03.1's 12,427 / 11,498. No retuning.

Two primary shapes use **the same E03.1 index/future signal**, stops, holding
clock, 2x partial/runner, cooldown, daily slots and continuous drawdown brakes:

1. **DEBIT_VERTICAL** buys the first out-of-the-money strike and sells the next
   50-point strike further out in the same direction, same expiry, equal lots.
   An ATM outright lost in the previous study; financing it with the capped
   upper payoff is a different theta/vega exposure, not a new ATM price band.
2. **BUTTERFLY** buys that same first out-of-the-money strike, sells twice as
   many lots 50 points farther out, buys equal lots 100 points farther out.
   A symmetric long butterfly buys a bounded interval payoff rather than an
   unlimited directional tail. Its value can fall after the index overshoots.

The earlier single-long full-premium reservation is explicitly generalized
for this *research-only* round: at most 1,250 per ticket / 2,500 per day in
net debit plus entry charges and one exit-order allowance per pack/leg.
At most three packs. All long legs' gross premium plus their charges must fit
the same own cash before credit from shorts; no leverage or naked short payoff.
Each short is covered by the simultaneously modelled long combination.
Every leg is within 200 points of current spot. No farther-strike hindsight.
First OTM anchor only; unaffordable/missing shape means no entry, not search
over later strikes. Ordinary/adverse/severe per-leg fills, current fees, and
20% per-leg volume proxy apply independently; pack capacity is the minimum of
all legs' whole-lot capacities. Fee is per actual order, including the 2x short.

Execution is a **hypothetical simultaneous pack**, not a claim of atomic
broker execution or guaranteed margin offsets. Intrabar sequences, legging,
queue, exchange spread-book availability and broker margin are unavailable.
At entry a zero/negative quoted debit is refused; no stale-price arbitrage.
If the next executable pack exceeds 110% of decision debit or reservation,
refuse it. Negative exit pack value is charged, not clipped to zero or the
terminal payoff. Therefore forced liquidation can lose more than terminal
maximum loss; report this explicitly and reject if risk acceptance fails.
Any unresolved pack is counted, all original debit lost conservatively, no
official settlement/terminal intrinsic value invented. Quotes are actual bars;
normal-model values from round two never become fill prices.

Shared PLAN.md material-gain acceptance and seen-year limits still apply.
Also require no leg mismatch or uncovered terminal loss; adverse ex-best >0
per year. No engine implementation or live trading authorized by this pack model.
Freeze source/tests before score; retain all financial identities and failures.
