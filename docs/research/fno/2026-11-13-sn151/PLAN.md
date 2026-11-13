# SN151–SN160: the hot-day program (frozen before any scoring, Nov 13, 2026)

**Owner:** "Go ahead even more ... if that fails learn from it, try something else ... some machine learning some automated, something mixed ... improve the gap days."

## What 150 studies leave standing on gap days

1. **Volatility persistence (SN101 / SN111):** when the morning moves more than its options price, it keeps moving.
   - The 10:00 straddle on those days beats matched random days (p = 0.002).
   - It is thin and lumpy, fails the concentration check, and is the frozen forward watch SN95-L.
2. **Big bursts on hot days (SN126):** +₹4,414 held out; negative at ₹400; forward watch SN126-L.
3. **Everything else:**
   - directional rules, sells, overnight, constituents, the order book;
   - free-form learners (SN131–SN150): they lose about their cost or choose not to trade.

## What phase F does

It digs only where an edge was found, from new angles, and mixes rules with learning:
- more hot moments (rolling windows, yesterday, expiry days);
- better admission (a learned probability, rule + model consensus);
- better management (legging out);
- the partner-speed version on hot days only.

## Common rules

- **Instrument:** the ATM straddle (1 lot each leg), bought at the ask and sold at the bid. Premium ≤ ₹15k, ₹3k stop on the combined mark; hold to 15:10 unless stated.
- **Costs:** Zerodha charges + ₹205 per leg-lot (strict). ₹400 per leg-lot and 1-minute-late entries are the robustness checks.
- **Hot thresholds:** causal expanding quantiles from earlier sessions only.
- **Days:** Gold-free (yesterday's ADX < 30) is primary, all days secondary.
- **Selection:** leave one year out over each study's small fixed grid. Random-admission control at the same rate per year, 2,000 draws.
- **Pass (each study):**
  - held-out net > 0 strict;
  - ≥ 3 of 4 years positive (≥ 2 of 3 where only three years are scored);
  - above the random 95th percentile;
  - positive without its best 5 days;
  - positive at ₹400 / leg and 1 minute late.
- **Preference rule (SN156):** better than holding both legs in total, in ≥ 3 of 4 years, and without the best 5 days.
- **Short data (SN153 / SN157):** a chronological split, labelled development evidence.

## The studies

### SN151 — "is it hot right now?", every 30 minutes

- **Checkpoints:** 10:00, 10:30 … 13:00.
- **R_w:** σ of the last w minutes' 1-minute index returns ÷ the ATM straddle's implied per-minute σ.
- **Entry:** the first checkpoint whose R_w is in the causal top 20% of all earlier sessions' checkpoint values (for that w) buys the straddle.
- **Grid:** w ∈ {45, 90} × exit ∈ {15:10, 120 minutes} = 4.

### SN152 — yesterday hot, today?

- **Signal:** yesterday's full-session R (σ of 1-minute returns 09:20–15:10 ÷ implied σ at 15:10), only when yesterday is the previous trading day in the cache.
- **Trade:** a straddle today at 09:20 or 09:45 when that R is in the causal top 20% / 33%.
- **Grid:** 4.

### SN153 — the expiry-day hot straddle

- **Data:** SN10's 56 NIFTY expiry days (10-second opening-ATM legs; minute index and future from the sealed datasets). Gold never trades these days.
- **R_today at 10:00:** 1-minute index σ since 09:20 ÷ the opening-ATM straddle's implied σ over the minutes left today (0 days to expiry, no overnight).
- **Hot:** the causal quantile over earlier expiry days (≥ 10).
- **Trade:** buy at 10:00, exit 12:00 or 13:00 (the owner's expiry cutoff); ₹3k stop.
- **Grid:** q ∈ {0.20, 0.33} × 2 exits.
- **Split:** choose on the first 28 days, score the last 28.

### SN154 — a learned "will today's straddle pay?" probability

1. **Rows:** one per session at 10:00 (SN102's 11 features + the 30-minute opening range, ADX, VIX ratio, previous range).
2. **Label:** the 10:00 straddle held to 15:10 nets > 0 (strict).
3. **Model:** logistic regression (standardised, C = 0.5), leave one year out.
4. **Admission:** p ≥ p*, p* ∈ {0.30, 0.35, 0.40, 0.45, 0.50} chosen on the training years by straddle net.

### SN155 — rule and model must agree

The trade is taken only when SN95-L's hot flag is on *and* SN154's held-out probability ≥ 0.5.
- **Against:** SN95-L alone on identical days.
- **Pass:** better than SN95-L in total and in ≥ 3 of 4 years, and positive without the best 5 days.

### SN156 — leg out of a winning straddle

On SN95-L days:
- once a leg's bid reaches +X% of its ask, sell that leg and hold the other to 15:10 (₹3k stop on the remaining position's loss);
- X ∈ {50%, 100%};
- against holding both.

### SN157 — partner-speed momentum on hot days (1-second archives)

1. **Hot day:** R_today at 10:00 computed from the 1-second index (sampled each minute) and the opening-ATM straddle; causal top 20% over earlier archive days (≥ 15).
2. **Entry:** on hot days, 10:00–15:00, every 10 s: a fresh 60-second index move ≥ k × the σ of 60-second moves over the previous 30 minutes buys the opening-ATM leg in its direction (strike within 100 points).
3. **Exit:** sell h seconds later at the bid; one position at a time; ₹3k room.
4. **Grid:** k ∈ {2, 3} × h ∈ {60, 180}.
5. **Split:** choose on archive A's hot days, score archive B's.
6. **Controls:** the same rule on cold days, and a random side.

### SN158 — the hot-day book

SN95-L + SN126-L + any SN151–SN157 survivor as one separate ₹15k sleeve (one position at a time, shared ₹3k day limit, earliest signal first), per year. Compared with putting the same ₹15k into Gold (₹45k vs ₹30k + sleeve, SN116's lesson).

### SN159 — robustness of survivors

- a bootstrap 95% interval of the per-trade mean;
- per year;
- ₹400 / leg;
- 1 minute late.

### SN160 — scoreboard, synthesis, the forward watches
