# SN131–SN140: the Smart Sentinel, phase D (frozen before any scoring, Nov 13, 2026)

## What the owner asked

"if they can do it as humans, why can the system not ... I don't need rule-based or filtering systems. I need that smart Sentinel ... if you need resources, tell me."

## What "smart" means here

No hand-written entry rule. At every minute the system *learns* what each action is worth after costs:
- buy the ATM call;
- buy the ATM put;
- for 5 / 15 / 30 / 60 minutes;
- or do nothing.

It uses ~45 measures of the market and acts only when its learned expectation beats costs. It relearns every quarter from everything before (walk-forward). A second learned model decides when to get out. Faster versions learn from 1-second prices and from real 5-level order-book quotes. Sizing follows the model's confidence.

The truth-test is unchanged:
- all choices are frozen here;
- predictions are always made without the future;
- strict costs (₹205 per lot per trade, Zerodha charges, ask in / bid out);
- random-policy and shuffled-label controls.

## Engine (`sm.py`, frozen)

- **Rows:** every minute 09:30–14:45 of the 742 sealed sessions (2023 – Oct 28 2026), ~234k rows.
- **Features:** 44 causal features (list in `sm.FEATURES`):
  - multi-scale index moves in ATR units;
  - position in the day's range, the opening range and VWAP;
  - EMA slopes;
  - realised volatility short vs since the open, and realised ÷ implied (R_today), implied change over 30 minutes;
  - ATM call / put premium and skew;
  - futures and option volume surges, basis change;
  - minute, days to expiry, weekday;
  - yesterday's ADX, ATR%, VIX ratio, previous-day move and range;
  - the Gold-free flag, new highs / lows, the share of up-minutes, the largest bar.
- **Labels:** for CE and PE × 5 / 15 / 30 / 60 minutes:
  - executable net (ask in, bid out, charges, ₹205);
  - the gross bid-to-bid change (for the exit model).
- **Model:** LightGBM regression, fixed parameters (`sm.PARAMS`, 400 rounds).
- **Walk-forward:** retrained at every quarter start 2024 Q1 – 2026 Q4 on all earlier rows, with a one-session purge. 2023 only trains.
- **Threshold:** θ ∈ {0, 100, 200, 300, 500, 800} chosen per quarter on the training window's last ~125 sessions, by a model trained before them.
- **Policy (`sm.simulate`):**
  - one position at a time;
  - at a flat minute take the (side, horizon) with the highest prediction if it exceeds θ;
  - the next decision comes after the exit;
  - the day stops opening trades once its loss reaches the room (₹3k at ₹15k, ₹6k at ₹30k).

## The studies

### SN131 — is there anything to learn?

Out-of-sample:
- per target, the rank correlation of prediction with realised net (all, by year);
- the realised net by prediction decile, and the top decile against zero.

Description; it gates nothing.

### SN132 — the smart entry policy

The walk-forward policy, 1 lot, ₹15k / ₹3k room, on all days (primary) and on Gold-free days.

**Pass (all required):**
- net 2024–2026 > 0;
- ≥ 2 of 3 years positive;
- above the random policy's 95th percentile (same trades per day, random minute / side / horizon);
- positive without its best 5 days;
- positive at ₹400 and with entries 1 minute late (SN140);
- the shuffled-label control ≤ 0 (SN140).

### SN133 — the learned exit

Gross continuation models (CE / PE × 5 / 15 / 30) via the same walk-forward. For SN132's entries:
- hold while any horizon predicts a positive bid-to-bid change from here;
- exit at the first minute where none does;
- capped at twice the chosen horizon or 15:10.

Against SN132's fixed horizons on identical entries.

**Preferred** if better in total and in ≥ 2 of 3 years.

### SN134 — learning on top of a simple event (meta-decision)

- **Events:** every fresh 3-minute move ≥ 1.5 ATR × √3, any day.
- **Model:** a walk-forward model trained only on event rows predicts the 15-minute net in the move's direction; take the event when the prediction > θ (nested).
- **Against:** all events taken, and random.
- **Pass:** SN132's rule.

### SN135 — the 1-second learner

1. **Data:** archive A (Apr 6 – Jul 27 2026) trains, archive B (Jul 28 – Nov 12) tests once, chronologically.
2. **Decisions:** every 10 seconds 09:20–15:00 when the opening-ATM strike is within 100 points.
3. **Features:** index moves over 5 / 10 / 30 / 60 / 120 / 300 / 600 s, second-level volatility, option mid moves, print staleness, time, distance to strike, the day's move and range.
4. **Labels:** CE / PE executable net over 30 / 60 / 120 / 300 s (house spread, charges, ₹205).
5. **Model and threshold:** LightGBM; θ from A's last 17 days with a model on A's first 60.
6. **Policy:** as SN132.
7. **Pass:** B net > 0 at ₹205, above random's 95th, positive without the best 5 days.

### SN136 — the order-book learner (real quotes, 40 sealed days)

1. **Decisions:** every minute 09:20–15:00, NIFTY nearest expiry, ATM by smallest |call mid − put mid|.
2. **Features:** option and futures spreads, top-1 and top-5 depth imbalance, 1 / 3 / 5-minute mid moves, volume changes, time.
3. **Labels:** real ask in, real bid out after 1 / 3 / 5 / 10 minutes (charges + ₹100, the measured latency allowance; ₹205 reported).
4. **Split:** train on the first 25 days, test on the last 15 (the last 9 unseen by any SN rule).
5. **Pass:** test net > 0 at ₹100 and ₹205, above random.

### SN137 — adaptive learning

As SN132, but retrained monthly, with recent sessions weighted more (half-life 60 sessions); θ reused from SN132's quarter.

### SN138 — ensemble

The average of SN132's and SN137's predictions, as one policy.

### SN139 — confidence sizing

At ₹30k / ₹6k room, applied to each of SN132 / 137 / 138 (no picking of a best after scoring):
- 1 lot when the prediction is in (θ, 2θ];
- 2 lots when it is in (2θ, 4θ];
- 3 lots above 4θ (θ = 0 → 1 lot).

Against 1 lot.

### SN140 — honesty checks on each of SN132 / 137 / 138

- ₹400 stress;
- entries 1 minute late;
- a shuffled-label control (labels permuted within each training day, then the same walk-forward; run for SN132's engine);
- by-quarter results;
- the count of everything tried.

## After phase D

Phase E (SN141–SN150) is planned after these results: integration with Gold, wallets and the live-paper design for anything that passes, and the exact resources needed.
