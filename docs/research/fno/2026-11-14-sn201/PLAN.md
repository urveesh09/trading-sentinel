# SN201–SN210: earn on Gold's quiet days by holding a protected weekly option sale (frozen plan, Nov 14, 2026, before any score)

## The owner's brief (Nov 14)

> "instead of staying flat, why not the system do something where it can earn little money … honestly is it impossible? Then how do the real traders earn that money on every day? … even on the days Gold doesn't trade … some profit and some loss and the system should know that … You have 10 slots. Do different perspective, different instruments, different systems … the system should become smarter and smarter … even if there are false positives … I will not force any fixed amount, make little profit money first." Also: "Go ahead with this new data … train some model, mix of machine learning, LSTM."

## Why this family (what SN01–SN200 already rule out)

- Every earlier SN leg opened and closed **inside one day or one night**. Each round trip pays costs (₹265–1,000 a structure), and the one-day option decay on calm days is smaller than that:
  - intraday buyers: SN161–SN199;
  - intraday iron flies: SN95, SN189;
  - the overnight fly / condor: SN124, a 2–3 point edge against 4 legs of costs, −₹850 a night;
  - the morning volatility crush: SN128;
  - the last half-hour: SN125;
  - learners: SN131–SN150, SN191–SN194.
- Gold's empty days are **calm, two-way, flat-closing days** (SN186). Those are the days an option *seller* is paid.
- The documented way professionals earn steadily from index options is to be the **seller of insurance**, with defined risk, accepting occasional losing weeks: the variance risk premium; Muravyev & Ni (JFE 2020) for the overnight part; SEBI's FY22–FY25 studies, where retail option buyers lose and proprietary and institutional traders earn.
- **New perspective:** hold one defined-risk short-premium position for the life of the weekly expiry.
  - Costs are paid **once a week**, not once a day.
  - The position collects decay on **every** calm day and night, including all of Gold's empty days.
  - Gold earns on trending (falling) days, when a seller loses, so the two may offset each other. SN206 measures this.

## Data and split

- **Development (seen):**
  - NIFTY Apr 2022 – Aug 19 2026: the sealed year datasets, plus `2026-11-13-sn186/_local/dataset-nifty-2022`.
  - Years for leave-one-year-out (LOYO): 2022 (Apr–Dec), 2023, 2024, 2025, 2026 (to Aug 19), by the entry day.
- **TEST (the latest 5%, as before):** weekly expiries whose first session is on or after 2026-08-20, through the dataset end (Oct 28, 2026). Scored once (SN208). The one week that spans Aug 20 is in neither part.
- **Exam 1, NIFTY, unseen:** the owner's new download (Nov 14; Breeze targets `nifty-2022-q1-fno` and `nifty-2021-q4-fno`).
  - Weekly expiries Dec 2, 2021 – Mar 24, 2022 (17 weeks with complete option days), plus the index from Sep 2021 for warm-up.
  - Oct–Nov 2021 options are not downloaded yet.
  - Sealed by SN201, scored once by SN209.
- **Exam 2, SENSEX, unseen:** weekly expiries Oct 2024 – Apr 2026, with the index from Jan 2024 for warm-up.
  - Lot 20, strike step 100, BSE (BFO) charges.
  - Sealed by SN201, scored once by SN209.
- **The other new data** (NIFTY 1-second, Jan 16 – Apr 2 2026) serves a minute-scale question. A weekly position entered at 15:15 does not use it; the earlier 1-second studies (SN78–SN90, SN147, SN157) found no intraday edge in it.
- **Mirrors are lean:**
  - the index at every minute;
  - option closes from 14:55 to 15:29 only (all the engine reads);
  - read-only from the Breeze database;
  - hashed;
  - counts only until SN209.

## The weekly book (WK): mechanics, all fixed here

- **One position per weekly expiry, 1 lot** (NIFTY 65, SENSEX 20, today's lots for every year), entered at the **15:15 close** of the k-th session before expiry (k = 1 is the day before expiry; k = F is the week's first session, the day after the previous expiry, usually 4 sessions before).
- **ATM and size:**
  - ATM = the strike where call and put are closest in price (put–call parity), at 15:15.
  - Q = the ATM straddle's price.
  - Strike distances are multiples of Q, rounded to the strike step, at least 1 step, so the same rule fits NIFTY and SENSEX.
- **Structures:**
  - **IF q:** iron fly. Short ATM call and put, long wings at ±q·Q.
  - **IC m q:** iron condor. Short call at ATM + m·Q and short put at ATM − m·Q, long wings q·Q beyond them.
- **Fills:**
  - Sell at the model bid, buy at the model ask (the house spread table, calibrated to real quotes in SN109; SENSEX uses the table on premium ÷ 3.25 × 3.25).
  - Zerodha charges per leg (NFO or BFO schedule).
  - A **slippage stress per leg-lot per round trip: ₹100 (the scoring level)**, with ₹0 / ₹50 / ₹200 reported.
- **Exits:**
  - **settle:** held to expiry, settled on the intrinsic value at the index's 15:00–15:29 average on expiry day (NSE's closing-price method, approximated); charged as a round trip at intrinsic (conservative);
  - **pre:** closed at 15:15 on the session before expiry;
  - **stop L:** closed at a 15:15 mark on any later session before expiry when the mark (after exit costs) is ≤ −L × the entry credit.
- **Marks:**
  - each session's 15:15 value gives the daily mark-to-market;
  - a leg with no print that day (outside the downloaded strikes) is marked at intrinsic + 0.5 point and counted;
  - a wing strike beyond the downloaded strikes moves inward to the farthest priced strike (at least one step past its short strike; counted); an entry with any leg still missing is skipped and counted.
- **Risk per lot** = (wing width − credit) × lot. The wallet needed is the broker's margin, roughly the maximum loss plus a buffer; the owner checks it on Zerodha before any money.

## The pass rule (paper candidate), all must hold

1. Development LOYO held-out sum > 0 with ≥ 4 of 5 years positive, at ₹100 per leg-lot.
2. Development > 0 at ₹200 per leg-lot and > 0 without the best 5 weeks.
3. The 5th percentile of 2,000 week-resampled development totals > 0.
4. TEST net ≥ 0 (SN208).
5. NIFTY exam > 0 **and** SENSEX exam > 0 (SN209).

A filter (SN204 / SN205) must also beat the unfiltered pick, and the 95th percentile of a random skip of the same number of weeks, held out. Passing means **paper only**. Real money needs a forward record and the owner's word.

## The 10 studies

| SN | Study | Rule (frozen) |
|---|---|---|
| 201 | **Seal the new data** | Lean read-only mirrors of NIFTY Sep 2021 – Mar 2022 and SENSEX Jan 2024 – Apr 2026 (index every minute; options 14:55–15:29 of the exam expiries) into `_local`; hashes, counts, strikes per session, missing days. No price is read. |
| 202 | **Is there a weekly premium? (description)** | On development: sell the ATM straddle and each structure at k = 1, 2, 3, F, hold to settlement. Per year: the settlement move ÷ Q (below 1 means sellers are paid), gross and net per week, win rate, worst week; the long straddle as the mirror. The IF 1.0 k = F daily marks on Gold's empty days vs Gold days. Description only. |
| 203 | **The frozen grid, chosen held out** | 6 structures {IF 0.5, IF 1.0, IC 0.5/0.5, IC 0.5/1.0, IC 1.0/0.5, IC 1.0/1.0} × k ∈ {1, 2, 3, F} × exit {settle, pre (k ≥ 2)} × stop {none, L = 1 (k ≥ 2)}: 78 variants. Only variants entered in ≥ 80% of the weeks they could trade are eligible (the downloaded strikes reach about ±1 straddle at the week's start, so wide condors often cannot be priced, and skipping exactly the high-volatility weeks would bias them). WK-A = the eligible variant with the best development total (the LOYO sum is the honest estimate of choosing that way); the runner-up is kept for the exams. LOYO picks the best on the other 4 years and scores the held-out year. Plateau (the pick's neighbours), ₹0 / 50 / 100 / 200, without the best 5 / 10 weeks, the week-resampled 5th percentile, max loss and margin proxy. The pick is **WK-A**. |
| 204 | **Sell only when insurance is expensive (HAR timing; the model refits every month)** | Daily realised variance (5-minute squares plus the overnight gap). HAR forecast of the holding period's variance, refitted monthly on all earlier days. ρ = forecast sd ÷ (Q / 0.8S). WK-A only when ρ ≤ κ, κ ∈ {0.8, 0.9, 1.0, 1.1} by LOYO; also a 2-lot / 1-lot / skip sizing at ρ ≤ 0.8 / ≤ 1.1 / > 1.1. Null: random skip with the same per-year count (2,000 draws). |
| 205 | **Machine learning risk model (LightGBM and LSTM, walk-forward)** | Label: the WK-A structure loses at ₹100. Samples: every k (k is a feature). Features at entry: Q/S, ρ, log RV day / week / month, 5- and 20-day returns, today's range, open→15:15, distance to the 20-day mean, skew (short put − short call) ÷ Q, credit ÷ max loss, k, weekday. LightGBM (7 leaves, 200 trees, lr 0.03, min leaf 20, seed 205). LSTM (the last 20 sessions of log RV, return, range, gap, plus k; hidden 16, dropout 0.2, 30 epochs, Adam 1e-3, seed 205). Quarterly expanding refits (needs ≥ 80 training samples; untrained weeks trade unfiltered). Skip when the predicted loss probability ≥ the 67th percentile of training predictions; also the average of the two. Null: random skip of the same count. Models refitted on all development are saved for the exams. |
| 206 | **Gold + the weekly book in one account** | Development 2023 – Aug 2026: Gold v5 ₹30k growing (production) day nets + WK-A (and the best filter if it passed) daily marks. Green / red days, on Gold's empty days the book's daily result and green share, worst day / week / month, correlation, per year, a ₹1 lakh book wallet. |
| 207 | **Robustness of WK-A** | Entry at 15:05 / 15:16 / 15:25. Costs ×2. Marks with estimated legs excluded. The 10 worst weeks with dates. Each year's worst month. The share of profit from the best 10 weeks. |
| 208 | **TEST and real quotes** | WK-A (+ passing filters) on the TEST weeks, scored once. Real bid/ask from the forward-panel archive (Sep 10 – Nov 13, 2026) at 15:15 for WK-A's legs: real vs model half-spread, NIFTY and SENSEX; TEST entries in the archive repriced on real quotes (1 lot, walking the depth). |
| 209 | **The two unseen exams** | WK-A, its LOYO runner-up and the passing filters (HAR betas and ML models frozen from development) on NIFTY Dec 2021 – Mar 2022 and SENSEX Oct 2024 – Apr 2026. Per week, per quarter, worst week; the always-sell ATM straddle as the reference. Scored once. |
| 210 | **Synthesis** | What to run (paper), its wallet and margin, what the owner should expect on quiet days and on trend days, how it sits beside Gold, and the honest answer to "how do real traders earn every day". Docs updated. |

## Order and freezes

1. This plan and `wk.py` (the engine) are committed before any number.
2. SN201 seals the data. SN202 and SN203 run on development.
3. SN204 / SN205 / SN206 / SN207 scripts are frozen, then run.
4. SN208 / SN209 scripts are frozen before they run, each once.
5. Fixes after a freeze are disclosed in the script and the README, and the first log is kept.

## Amendment after SN202–SN203 (Nov 14, written before any SN204–SN210 script)

**What SN202–SN203 found:**
- **SN202:** the weekly premium exists, but only **unprotected**.
  - The short ATM straddle held to settlement earned +₹1.40–2.44 lakh per lot over 229 weeks (₹100 per leg-lot).
  - Settlement payout ÷ Q: mean 0.90–0.96. Worst week −₹48,308.
  - Every protected structure lost (−₹43k to −₹1.67 lakh). Most lose even before slippage: wings at ±0.5–1 straddle recover only part of their price.
- **SN203:** **0 of 78** defined-risk variants are positive. WK-A (IC 1.0/1.0 k1 settle) made −₹75,662, LOYO −₹1.38 lakh. **The defined-risk weekly book fails.**
- **Post-freeze fix (disclosed):** the variant list compared "F" with a number and crashed before printing anything (`logs/sn203-v1-crash.log`).

**Consequence:**
- SN204–SN210 study the **unprotected weekly seller (WK-S)**. Wings do not cap its risk; size, stops at the 15:15 marks, timing and the wallet do.
- This direction was chosen on development and is disclosed as such. TEST and the two exams stay unseen and decide.

**Revised studies (same rules as above unless stated):**

| SN | Study |
|---|---|
| 204 | **WK-S grid:** {STRADDLE, STRANGLE 0.5 (short ATM ± 0.5 Q)} × k ∈ {1, 2, 3, F} × exit {settle, pre} × stop {none, 0.5, 1.0 × credit at a 15:15 mark}: 38 variants. Eligibility ≥ 80%; LOYO; WK-S = the best eligible total; the runner-up is kept. Pass checks 1–3; the 10 worst weeks; each year's worst month; drawdown. Tail scenarios: index moves of 3 / 5 / 8 / 13% at today's level. WK-S daily marks on Gold's empty days vs Gold days. Wallet ₹2.5 lakh per lot (a margin proxy the owner checks on Zerodha). |
| 205 | **HAR timing on WK-S** (the SN204 rule above, applied to WK-S) |
| 206 | **ML risk model on WK-S** (the SN205 rule above; label = WK-S loses) |
| 207 | **Gold + WK-S in one account** (the SN206 rule above; WK-S wallet ₹2.5 lakh) |
| 208 | **Robustness of WK-S** (the SN207 rule above) |
| 209 | **TEST, real quotes and the two unseen exams** (the SN208 and SN209 rules above), each scored once: WK-S, its runner-up and the passing filters |
| 210 | **Synthesis** |

**One extra pass rule for an open-risk seller:**
6. The worst development month is better than −₹50,000 per lot (20% of the ₹2.5 lakh wallet).
