# SN186–SN200: an extra leg for Gold's empty days — frozen plan (Nov 13–14, 2026, before any score)

## The owner's brief (Nov 13, night)

> "whatever data we have at this moment in our device, you are allowed to use it … We don't want to replace Gold. We want to provide an additional leg for the empty days … the commonality of those days when Gold does not trade … Remove the rule of 10% … on the gap days you have to earn a fixed amount of ₹1000 or ₹1500 … whatever the wallet size … I allow you to even change wallet sizes for the gap days … maybe try LSTM … 91% of the time … bought at 9:20 … ₹1500 … losses mitigated … while ensuring we earn money … do till SN 200 … update the documentation."

**The goal:** a second leg that trades only when Gold v5 does not. It aims at a fixed **₹1,000 or ₹1,500** a day, at any wallet the leg needs, and must be profitable with losses kept small.

## Days, data and split

- **Empty day (development and TEST):** a session where Gold v5 (SN110 player, ₹15k) has no trade.
  - On NIFTY 2022, which has no Gold replay, the causal proxy is **yesterday's daily ADX < 30** (Gold's call side and three of four setups shut; SN76).
  - Its overlap with true empty days on development is reported.
- **Development:** the 705 sessions before 2026-08-20. **TEST:** the latest 5% (2026-08-20 … 10-28), scored once by SN198.
- **New unseen data (the owner's word, Nov 13):**
  - NIFTY 2022 Apr–Dec, already downloaded (ICICI Breeze, targets nifty-2022-q2/q3/q4).
  - It is sealed read-only into this folder's `_local` (SN195) and scored once by SN196 with every pick frozen beforehand.
  - SENSEX Oct 2024 – Apr 2026 is also on disk; it needs a SENSEX lab (lot 20, step 100, its own cost scale) and is left for the next round, stated so.
- **Money:**
  - Zerodha charges plus ₹205 per lot per single-leg trade; ₹100 per leg-lot for multi-leg structures.
  - Sensitivity: ₹400 per lot and 1 minute late.

## The fixed-amount rules (the owner's change)

- **Daily goal:** ₹1,000 or ₹1,500, whatever the wallet. The day stops once it is reached.
- **Day loss limit:** 2× the goal unless a study says otherwise.
- **Wallets:** chosen per structure (₹15k one leg, ₹30k for two legs, ₹1.5 lakh for a defined-risk seller). Lots are fixed by the study (usually 1), never "as many as the wallet buys" (SN164: more lots, more costs).

## The pass rule for an empty-day leg (all must hold)

1. Development leave-one-year-out (LOYO) held-out sum > 0 with ≥ 3 of 4 years positive.
2. It beats its matched random null's 95th percentile.
3. It is > 0 at ₹400 per lot and 1 minute late (development).
4. It is > 0 without its best 5 days (development).
5. TEST net ≥ 0 (SN198) and the NIFTY 2022 net > 0 (SN196), each against its null.

A pass means **paper leg candidate**; real money needs the forward record and the owner's word.

## The 15 studies

| SN | Study | Rule (frozen) |
|---|---|---|
| 186 | **The commonality of Gold's empty days** | Empty vs Gold days on causal morning features (ADX, gap, opening-range width, R_today, VIX ratio, weekday, days to expiry) and on what the day then did (range, trend efficiency, open→close, max move after 10:00). k-means (k = 4) clusters of empty days on 09:45 features; each cluster's hindsight best simple play (to show where money existed). How well 09:45 features separate Gold days from empty days (logistic AUC, LOYO). Descriptive. |
| 187 | **The 91% trade, both sides** | On empty days buy 1 lot ATM CE + 1 lot ATM PE (₹30k wallet) at 09:20 (and at 10:00). Exits: (a) close both when the pair's net reaches +₹1,000 / +₹1,500, stop −₹2,000 / −₹3,000, else 15:10; (b) sell the first leg that reaches +₹1,500 on its own, then close the other immediately. LOYO over the grid; null = the same at a random minute 09:30–14:30. |
| 188 | **Small fixed target on hot empty days** | Empty days whose R_today at 10:00 is in the causal top 40%: the first 15-minute range break after 10:00 buys 1 lot ATM; target +₹1,000 / +₹1,500, stop −₹1,000 / −₹1,500; up to 2 attempts, goal-locked. LOYO; null = random side at the same minutes. |
| 189 | **Variance seller on calm forecasts** | Empty days with SN171's HAR forecast / implied < κ (κ ∈ {0.75, 0.85, 0.95}): sell an ATM iron fly with ±200 wings (1 lot, ₹1.5 lakh wallet) at 10:00. Take +₹1,000 / +₹1,500, stop −₹3,000 / −₹4,500, else 15:10. LOYO; null = random empty days. |
| 190 | **The volatility-regime leg** | High forecast (ρ ≥ 1.1): buy SN171's straddle (₹30k). Low forecast: SN189's pick. Otherwise no trade. Empty days only. LOYO on the joined ledger. |
| 191 | **LSTM entry model** | Sequences of the last 60 one-minute bars (index returns, range, distance to VWAP, ATM premiums, minute of day) at 10:00, 11:00, 12:00, 13:00 and 14:00. Labels: ATM CE / PE, +₹1,000 before −₹1,000 (1 lot) by 15:10. A 2-layer LSTM (64 units, dropout 0.2, Adam 1e-3, 8 epochs, seed 191) trained per development year-fold (train on earlier years only) and finally on all development. Policy: the best of CE / PE if P ≥ θ (θ from {0.5, 0.55, 0.6} by the fold scores); goal lock. Against LightGBM on the same rows and labels and the random null. |
| 192 | **LSTM volatility forecast** | The same morning sequence (09:15–10:00) → rest-of-day realised variance. Out-of-sample R² by year against HAR (SN171); if better, SN171's κ = 1.1 rule with the LSTM forecast. |
| 193 | **LSTM direction (the "stock prediction" claim)** | Sequences of 60 one-minute bars → the sign of the next 15 minutes at every 15-minute mark 09:45–14:30. Out-of-sample accuracy by year against 50%, "same as the last 15 minutes" and "opposite"; then trade it (ATM, +₹1,000 / −₹1,000, goal lock) on empty days. |
| 194 | **Stacked ensemble** | Logistic stack of LightGBM P, LSTM P and HAR ρ (fitted on earlier years only) for the SN191 decisions; same policy and null. |
| 195 | **NIFTY 2022 sealed** | Read-only mirror of NIFTY Apr–Dec 2022 (index, futures, options, daily bars) from the Breeze history database into `_local`, exported with the house year-dataset tool and hashed. A data audit only (sessions, strikes per session, gaps); no strategy reads it before SN196's freeze. |
| 196 | **The NIFTY 2022 exam** | Frozen before running: SN95-L (10:00 hot straddle, fixed R_today threshold = the development 80th percentile), SN171 (HAR β from development, κ 1.1, both wallets) and every SN187–SN194 pick that passed development, on 2022's proxy-empty days. Matched nulls. Scored once. |
| 197 | **The empty-day leg ledger** | Gold v5 first; on its empty days the leg (the passing picks, else the forward watches) with the fixed goal. ₹15k / ₹30k Gold plus the leg's wallet; development, per year, wage days of ₹1,000 / ₹1,500, worst month. |
| 198 | **The frozen TEST** | Every SN187–SN194 pick on 2026-08-20 … 10-28, scored once. |
| 199 | **Leg wallet and growth** | For any passing leg: its wallet (₹15k / ₹30k / ₹50k / ₹1.5 lakh) and a growth rule (+50% after its profit equals its wallet, at most 3 steps) at a fixed ₹1,000 / ₹1,500 goal, with the refills it needed. |
| 200 | **Synthesis and the download plan** | What the empty days are, what (if anything) fills them, what goes on paper, and the data to fetch next. |

## Order

P1 (SN186–SN190) and P2 (SN191–SN194) freeze before they run. SN195 seals 2022 and audits it. SN196's script and SN198's are frozen before either is run. SN197 and SN199 use development only.
