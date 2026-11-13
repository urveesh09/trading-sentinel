# SN101–SN110 (phase A): the other agent's programme, built and scored (Nov 13, 2026)

**Owner:** run the other agent's SN101–SN110 (`docs/SN101_SN110_RESEARCH_REVIEW.md`, that agent's local file), then SN111–SN120. "I don't want fast testing, but correct testing."

- **Frozen** at `728f15f8` (`PLAN.md`) before any scoring. The numbers are in `results-*.json`; console logs stay local in the git-ignored `logs/`.
- **Costs:** multi-leg structures use the **strict ₹205 per leg-lot** basis this phase.
- **Corrections after scoring** (measurement bugs, kept on record):
  - SN109 and SN103 first compared some exits with *stale* archive quotes. The archive only follows ~11 strikes near the money, so a contract that drifts away has no fresh quote at 15:10. Both now require a quote from the exit minute or the one before.
  - The first outputs are kept as `results-sn109-v1-stale-exit-quotes.json` and `results-sn103-v1-no-exit-freshness.json`.
  - SN106 crashed on a number-format bug in its print, before writing anything, and was rerun unchanged.

**One line:** the straddle signal is real but thin. Nothing in phase A beats Gold v5 or reaches the Gold v6 bar. The real quotes say our cost model is honest.

## Results

| SN | Question | Result | Verdict |
|---|---|---|---|
| 101 | Is SN95's straddle a volatility signal, or a premium / expiry / stop effect? | **The signal is real:** the signal days' +₹17,145 (strict) vs 5,000 matched random sets (same days-to-expiry and premium tercile) averaging −₹29,654, **p = 0.002** (all days p = 0.0006). Only the **top R_today decile** is positive (+₹701 a day pure hold; deciles 1–9 lose ₹496–1,034). The **₹15k premium cap is part of it:** a ₹20k cap adds 31 expensive straddles and cuts the result to +₹3,114 (−₹2,670 with a ₹4k stop). The stop size barely matters. | Information: YES. Still thin: −₹22,251 without the best 5 days |
| 102 | A model of the straddle's remaining value (semivariance, jumps, efficiency, premium, expiry, range…) | Forecast correlation **0.19** vs 0.09 (R_today alone) and −0.12 (premium + expiry). Held out (choose on 3 years, score the 4th): **+₹19,686** at ₹15k, years [+10,839, +5,204, −1,673, +5,316]. Random admission 95th percentile −₹15,823; ₹400/leg +₹9,511; 1 minute late +₹17,254. But **−₹12,702 without its best 5 days**, and walk-forward is only +₹394 | NOT PROVEN (fails only the concentration check; walk-forward ≈ 0) |
| 103 | Which expiry buys the move? (real quotes, 24 days) | Next week's ATM straddle lost **₹16,480** vs ₹22,365 for the nearest; better on 75% of days; **−₹24.9 vs −₹53.3 per ₹1,000 of premium**. But it costs ₹27.6k vs ₹17.5k | Description: slower decay, needs a ≥ ₹30k wallet |
| 104 | Does the straddle give its profit back? | It does (mean best point +₹2,534; 46% reach +₹1,000 and then give back ₹2,576 on average). But **taking it early destroys it:** giveback exit −₹7,959 and 13:00 exit −₹1,254, against hold +₹17,145 | NOT PROVEN: hold to 15:10 |
| 105 | Banks moving while NIFTY cancels them (BANKNIFTY proxy from 12 bank stocks) | The cancellation state continues by **+1.2 basis points** (95% interval −13.7 to +15.8, 17 cases); no forecast gain | NOT PROVEN: no case for buying BANKNIFTY option data |
| 106 | SN95's rule on SENSEX (145-date panel) | Every day −₹29,064; admitted −₹7,619 (16 trades). On the 42 common dates SENSEX lost less than NIFTY (−₹18,144 vs −₹35,016: a later expiry, as in SN103) | NOT PROVEN (partial data) |
| 107 | RBI decision days (17) vs 85 matched days | **Implied volatility falls 4.7% by 10:30** (interval −7.3% to −2.1%) vs −0.5%. The option bought at 10:30 in the direction of 10:00–10:30: +₹394 mean vs −₹399 (interval spans zero). The straddle after release +₹189 vs −₹584 (8 vs 33) | Description: a real IV crush; too few events to trade |
| 108 | Order-book absorption (NIFTY future, real 5-level depth, 1 snapshot a minute) | No forecast gain at 5 / 15 / 30 minutes (all intervals span zero) | NOT PROVEN (minute snapshots are not a flow tape) |
| 109 | The real execution hurdle | See below | The cost model is honest |
| 110 | Gold v5 + the straddle in one account | ₹30k fixed **+₹13,780 (+4.9%)**, ₹30k growing (stop 3) **+₹39,537 (+4.6%)**. The maximum drawdown worsens (₹26,851 vs ₹18,467). At ₹400/leg: +₹1,129 / **−₹25,999**. Hurts G2/G3 (it only trades once the wallet leaves ₹15k free) | Fails the Gold v6 bar (≥ 15%, no worse drawdown, robust) |

### SN109: what real quotes say about our costs (40 sealed days, ~580k option quotes)

| Premium | Real median spread | Model spread | Real / model |
|---|---:|---:|---:|
| ₹0–50 | 0.10 | 0.10 | 0.92 |
| ₹50–100 | 0.20 | 0.20 | 1.00 |
| ₹100–150 | 0.35 | 0.30 | 1.09 |
| ₹150–200 | 0.45 | 0.45 | 1.02 |
| ₹200–300 | 0.65 | 0.60 | 1.13 |
| ₹300–450 | 1.10 | 0.80 | **1.46** |
| ₹450+ | 1.85 | 0.90 | **2.06** |

- **Size:** 1, 2, 3 and even 6 lots fill inside the five displayed levels at the best price. Round trip against the mid is about ₹29–31 per lot (90th percentile ₹49–56); thin in 0.2% of minutes at 6 lots.
- **Time:** quotes are about 1 second old. A one-minute delay moves an option's mid by a median ₹135 per lot. That, not the spread, is what the ₹205 stress has to cover.
- **Gold's own trades:** on Gold v5's 7 research trades with fresh real quotes, the real ask was ₹115 per lot *cheaper* than the model's and the real exit bid ₹130 per lot *better*. The research does not flatter Gold's fills.
- **Rule:** no cost gate changes (₹205 / ₹400 stay). The model under-states spreads only above ₹300 premium, which matters for deep-ITM legs and SENSEX.

## What phase A teaches (carried into SN111–SN120)

1. **There is one real piece of information on empty days:** realised volatility running hot against the option price at 10:00. It is narrow (top decile), lumpy (a few big days) and thin after strict costs.
2. **Premium and expiry choice matter as much as the signal.** Cheap straddles carry the result, and later expiries decay half as fast per rupee.
3. **Hold the convex trade to the close.** Every early exit tested (SN104, and before it SN01/SN03/SN11/SN27) cuts the tail that pays for everything.
4. **No new direction information:** constituents, banks, order book and SENSEX add nothing at the resolutions we have.
5. **Our fills are honest or conservative.** Results are not inflated by the simulator.
