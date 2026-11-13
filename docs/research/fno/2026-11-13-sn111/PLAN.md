# SN111–SN115: frozen plan, phase B (written after phase A's results, committed before any phase B scoring, Nov 13, 2026)

Owner: "try better permutations or better perspectives or better ideas in SN111 to SN115 ... deeper and more meaningful ... correct testing."

**What phase A taught (`../2026-11-13-sn101/README.md`):**
1. The one real empty-day signal is realised volatility running hot against the option price at 10:00. It is narrow (top decile), lumpy and thin after strict costs.
2. Premium and expiry choice matter.
3. Hold convex trades to 15:10.
4. Constituents, banks, the order book and SENSEX add no direction.
5. Our simulated fills are honest or conservative.

Phase B asks *why* the signal works, whether a cheaper expression of it exists, whether Gold itself shares the mechanism, and what latency really costs. Every study is fixed in advance; the only grid (SN113) has 3 settings.

Research only. The SN92 harness and phase A helpers are imported, never edited. Seen data throughout: these are development results, judged by the rules below.

## Common rules

- **Costs:** strict ₹205 per leg-lot (single leg ₹205/lot), ₹400 reported.
- **Wallet:** the straddle family at ₹15k ceiling / ₹3k room unless stated.
- **Days:** "SN95-L days" = the 35 Gold-free days with R_today in the causal top 20% at 10:00 and the straddle affordable at ₹15k; "all signal days" = the 47 such days without the Gold-free condition.
- **Preference rule (SN112 / SN114):** an alternative expression is *preferred* only if it beats the ATM straddle on identical days in total, in ≥ 3 of 4 years, and without the best 5 days. A preferred expression goes to phase C; it is not adopted here.

## SN111 — where the straddle's money comes from (description)

Every session at 10:00, by R_today decile:
- the straddle, call leg and put leg (pure hold to 15:10, strict);
- **volatility persistence:** σ of 1-minute index returns 10:00–15:10 ÷ σ_imp at 10:00;
- **implied catch-up:** σ_imp at 15:10 ÷ σ_imp at 10:00, ATM each time;
- |move 10:00→15:10| ÷ the straddle's price;
- **trend continuation:** sign of 10:00→15:10 equals sign of 09:15→10:00.

Plus the correlation of R_today with later realised ÷ implied. No rule is chosen.

## SN112 — is the straddle a hidden direction trade? (one fixed rule)

On SN95-L days and all signal days, buy at 10:00 only the ATM leg in the direction of 09:15→10:00 (`with-trend`), or only the other leg (`against`), against the straddle; ₹3k room; hold to 15:10.
- **Control:** a random leg each day (2,000 draws).
- **Preferred** (common rule above) AND above the random 95th percentile.

## SN113 — does Gold share the mechanism? (diagnostic + one 3-setting skip rule)

1. **Diagnostic:** Gold v5's trades (₹15k and ₹30k) by R_today at the entry minute — terciles of a causal expanding rank — per-lot net by year.
2. **Rule:** skip a Gold entry when its R_today is below the causal q-quantile of all earlier Gold entry ratios (≥ 30 earlier). q ∈ {0.10, 0.20, 0.33}. This is a market condition known at entry, not a loss-reaction rule.
3. **Scoring:** leave one year out at every wallet against v5.
4. **SN92's Gold pass rule:**
   - LOYO beats v5 at ₹30k sized and G3;
   - ≥ 3 of 4 held-out years at or above v5;
   - worst day not worse by more than 10%;
   - the advantage survives +₹400 and 1-minute-late entries.

## SN114 — a cheaper structure for the same signal (fixed set of 4)

On SN95-L days at 10:00, hold to 15:10, ₹3k room, strict:
- the ATM straddle (K);
- the 1-step strangle (K+50 CE, K−50 PE);
- the 2-step strangle (K+100 CE, K−100 PE);
- the 1-step in-the-money pair (K−50 CE, K+50 PE).

Each is skipped when unpriced or its premium exceeds ₹15k. The preference rule applies.

## SN115 — what latency really costs (measurement, real data)

1. **Production's paper entries.** Read the paper book's NIFTY positions inside the 40 sealed quote days, from `fno-replay.sqlite` in the same export (hash-checked).
   - The delay from the signal bar's close to the fill.
   - **Signal-to-fill cost:** the fill premium minus the option's archived mid at the signal bar's closing minute, per lot.
   - **The adverse move after the fill:** mid 1 and 5 minutes later minus the fill-minute mid, signed for a buyer, per lot.
2. **Scheduled control:** the same measures for the ATM call and put bought at 10:00 on every quote day.
3. **Output:** measured cost per lot for signal entries vs clock entries, against the ₹205 stress. No cost gate changes.
