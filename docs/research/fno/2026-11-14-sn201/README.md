# SN201–SN210: earning on Gold's quiet days by selling weekly options (Nov 14, 2026)

**Full record for Gold v6 work:** `docs/SN_WEEKLY_SELLER_AND_GOLD_V6.md` (every recipe, number, data path and rerun command).

**Owner:** "instead of staying flat, why not the system do something where it can earn little money … how do the real traders earn that money on every day? … different perspective, different instruments, different systems … the system should become smarter and smarter … make little profit money first." Also: use the new data, and try ML / LSTM.

**How it was tested**
- **Plan and freezes:** `PLAN.md`, frozen at `00564b6b` before any number. Amendment after SN203 (written before SN204), then freezes at `6847a924`, `7bdc7e73` and `4852fc05`.
- **Development:** NIFTY Apr 2022 – Aug 19 2026, 229 weekly expiries; held out by year (LOYO, 2022–2026).
- **TEST:** the latest 5% (the 9 weeks from Aug 20 to Oct 27, 2026), scored once.
- **Two unseen exams, scored once (SN209):**
  - **NIFTY** Dec 2021 – Mar 2022 (17 weeks; the owner's new download);
  - **SENSEX** Oct 2024 – Apr 2026 (83 weeks).
- **Real quotes:** the forward-panel archive, Sep 10 – Nov 12, 2026.
- **Money:**
  - 1 lot (NIFTY 65, SENSEX 20);
  - Zerodha charges (NFO / BFO) plus ₹100 per leg-lot of slippage;
  - entries at the model bid / ask, held to the expiry settlement unless a stop is hit.
- **Post-freeze fixes (two, both crashes before any number was printed):**
  - the variant list in SN203;
  - a missing index day in SN206.
  - The first logs are kept locally in `logs/` (git-ignored).

## The idea (new in the SN series)

- **Why earlier legs lost:** every earlier leg opened and closed within one day or one night. Each trade pays ₹265–1,000 in costs, and one calm day's option decay is smaller than that.
- **Who earns on calm days:** they are the days an option *seller* is paid. Gold's empty days are calm, two-way days (SN186).
- **The weekly book:**
  - sell options once a week at 15:15;
  - hold them until the weekly expiry, so costs are paid once a week;
  - collect the decay of every calm day and night in between.

## Results

| SN | Study | Development (NIFTY 2022–26) | Verdict |
|---|---|---|---|
| 201 | Seal the new data | NIFTY exam: 17 expiries, index 142 sessions (Sep 2021 – Mar 2022), sha `cbd227bf…`. SENSEX exam: 83 expiries, index from May 17 2024, sha `a272ad18…`. Lean read-only mirrors, counts only | Data |
| 202 | Is there a weekly premium? | **The plain short ATM straddle held to expiry earns +₹1.40–2.44 lakh per lot** (229 weeks, 60–65% winning weeks). Expiry payout ÷ premium averages 0.90–0.96, so sellers keep 4–10%. Worst week −₹48,308. Buying the straddle loses −₹3.0–4.0 lakh. **Every protected version (iron fly / condor) loses** (−₹43k to −₹1.67 lakh) | Premium exists only unprotected |
| 203 | 78 protected (defined-risk) weekly sellers | **0 of 78 positive.** Best −₹75,662; LOYO −₹1.38 lakh, 0 of 5 years. The protective wings recover only part of their price | FAIL |
| 204 | 38 unprotected weekly sellers | **38 of 38 positive.** **WK-S** (sell the call and put 0.5 straddle out of the money, 3 sessions before expiry, 15:15; exit if the loss reaches the premium received; else hold to expiry): **+₹3,13,523**, every year positive (+₹38k to +₹80k), LOYO +₹1,49,729 (4 of 5 years), +₹2.54 lakh at double slippage. Worst week −₹39,844, worst month **−₹51,245** (Apr 2025, misses the −₹50k rule). On Gold's empty days: +₹337 a day on average, 51.5% green. **One crash week per lot:** 5% move −₹60,798, 8% −₹1.09 lakh, 13% −₹1.89 lakh | Strong in development |
| 205 | "Sell only when insurance is expensive" (HAR forecast, refitted monthly) | The cheapest-insurance fifth of weeks averaged +₹4,066, but the filter skips too many winners: LOYO +₹1.46 lakh vs +₹3.14 lakh unfiltered (random-skip 95th percentile +₹2.89 lakh). Sizing (2 lots when rich, skip when cheap) +₹3.71 lakh, but better in only 2 of 5 years | FAIL (the sizing is not adopted) |
| 206 | Machine-learning risk model (LightGBM + LSTM, quarterly walk-forward, learning from every past week) | Out-of-sample AUC: LightGBM **0.56**, LSTM **0.49**, average 0.55. Every filter earns less than selling every week (+₹2.44–2.92 lakh vs +₹3.33 lakh) and less than random skipping | FAIL: losing weeks cannot be seen in advance |
| 207 | Gold + WK-S in one account (2023 – Aug 2026) | Gold ₹30k growing alone: +₹6.42 lakh, **55 green days** (775 days without a trade), 2023 −₹12,107. **Gold + WK-S: +₹8.76 lakh, 380 green days, every year positive** (2023 +₹31,650). Worst day −₹33,751, worst month −₹56,645. Correlation −0.09 (−0.27 on Gold's trade days): the seller partly offsets Gold | Looks like the answer, in-sample |
| 208 | Robustness | Every nearby version is positive: entry 15:05 / 15:16 / 15:25 (+₹2.45 / 2.80 / 2.74 lakh), slippage ₹300 / ₹400 (+₹2.09 / 1.64 lakh), width 0.25 / 0.75, stop none / 0.5 / 1.5 / 2.0, first session of the week. The best 10 weeks give 52% of the profit | Robust in development |
| **209** | **TEST, real quotes, two unseen exams** | Real quotes: the cost model is right (NIFTY half-spread 0.10 real vs 0.12 model; SENSEX 0.39 vs 0.35; one lot always fills). **TEST −₹23,348** (9 weeks, 44% winning). **NIFTY Dec 2021 – Mar 2022 −₹56,743** (17 weeks, 35% winning; the Russia week of Feb 21–24, 2022 alone −₹40,884). **SENSEX Oct 2024 – Apr 2026 −₹42,022** (70 weeks, 60% winning, worst month −₹70,088). Runner-up: −₹11,373 / −₹61,620 / −₹8,309. Plain always-sell straddle: −₹16,229 / −₹25,113 / +₹31,042 | **FAIL on all three unseen samples** |
| 210 | Synthesis | below | – |

## SN210: synthesis

1. **What was new:** a different time horizon (a week, not a day), a different side (seller, not buyer) and a second instrument (SENSEX).
2. **What it showed in development:**
   - The weekly variance premium is real but small: sellers keep about 4–10% of the premium on average.
   - It pays only without protection; the protection costs more than it returns.
   - The unprotected seller made money on Gold's quiet days and in every development year, and turned Gold's 55 green days into 380.
3. **What the unseen data said: no.**
   - On the three samples it had never seen, the same seller lost −₹1.22 lakh in 96 weeks: −₹1,270 a week, against +₹1,406 a week in development.
   - Costs are not the cause; real quotes match the model.
   - Most of the loss is what an open seller always risks: one shock week (Russia, Feb 2022: −₹40,884; tariffs, Apr 2025) erases months of small wins.
   - Even across 4.4 good development years the best 10 weeks made half the profit.
4. **The machine learning (LightGBM and LSTM) cannot see the losing weeks coming** (AUC 0.49–0.56), and neither can the volatility forecast. So the system cannot "know" a bad week in advance from price history; a false positive costs a shock week.
5. **How do real traders earn every day? An honest answer:**
   - SEBI's studies (FY22–FY25) found about 9 in 10 individual F&O traders lose money.
   - The steady earners are mostly firms. They either:
     - make markets and earn the bid–ask spread with speed and scale; or
     - sell options with large capital and accept occasional heavy weeks.
   - The second group is the trade tested here. At 1 lot and ₹2.5 lakh, its edge did not survive unseen data.
   - Individuals who earn daily usually have information or speed that minute data does not carry, or have not yet met their shock week.
6. **Recommendation:**
   - **Gold v5 runs as it is.** Do not trade the weekly seller with money.
   - On Gold's empty days the honest choice is still to stay flat.
   - A daily income still comes from paying out Gold's profits (SN177's salary account).
   - The new information that could change this is the tick recorder (order flow, from Mon Nov 16) and full option chains far from the money.
   - If the owner wants it, WK-S can run as a **paper-only forward watch** (≥ 20 weeks, no money). Expect about zero, with occasional large losses.
7. **Data now seen:**
   - NIFTY Sep 2021 – Mar 2022 (the index at every minute; options at 14:55–15:29);
   - SENSEX May 2024 – Apr 2026 (the same).
   - Treat both as seen for any future test.
   - Still unseen: NIFTY Oct–Nov 2021 options (not downloaded yet), NIFTY 2021 Jan–Sep and 2020 (not downloaded), and the NIFTY 1-second Jan 16 – Apr 2 2026 archive (not used here).

## Files

- **Plan and engine:** `PLAN.md`, `wk.py` (the weekly-book engine), `feat.py` (HAR and features).
- **Studies:** `sn201.py` … `sn209.py`, with `results-sn201.json` … `results-sn209.json` and `logs/`.
- **`_local` (not committed):** exam mirrors `mirror-nifty-exam.sqlite`, `mirror-sensex-exam.sqlite`; caches `wk-*.pkl`; picks, the HAR fit, the ML models and decisions.
