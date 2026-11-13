# SN186–SN200: an extra leg for Gold's empty days (Nov 13–14, 2026)

**Owner:** "We don't want to replace Gold. We want to provide an additional leg for the empty days … the commonality of those days … remove the rule of 10% … a fixed amount of ₹1000 or ₹1500 … whatever the wallet size … maybe try LSTM … use whatever data we have on the device … till SN 200."

**How it was tested**
- **Plan:** `PLAN.md`, frozen at `4462f86f`. Each phase was frozen before it ran (`4462f86f`, `09714777`, `5deb4c7f`).
- **Split:** development = 705 sessions before 2026-08-20. TEST = the latest 5% (Gold's empty days 2026-08-20 … 10-28), scored once by SN198.
- **New unseen data:** NIFTY Apr–Dec 2022, sealed by SN195 and scored once by SN196.
- **Costs:** charges plus ₹205 per leg (₹100 per leg-lot for the four-leg fly).
- **The goal:** a fixed ₹1,000 / ₹1,500 a day, with lots fixed (usually 1).
- **Two post-freeze print fixes (no number seen before the fix):** SN196 crashed on its first print (a number-format error) and was rerun unchanged; the first log is kept as `_local/sn196-v1-crash.log`.

## The commonality of Gold's empty days (SN186, development: 594 empty vs 111 Gold days)

| Measure (median) | Gold days | Empty days | Meaning |
|---|---|---|---|
| Yesterday's daily ADX | 28.3 | **20.8** | Empty days follow weak-trend days (N11 then allows puts only, SN76) |
| First-30-minute range | 0.43% | 0.37% | Quieter openings |
| VIX against its own median | 1.02 | 0.98 | Calmer fear |
| Day's range | 0.85% | 0.77% | Smaller days |
| Open → close | **−0.32%** | **+0.03%** | Gold earns on falling days; empty days end flat |
| Biggest move after 10:00 | 0.50% | 0.48% | They still move, but back and forth |

- **Clusters:** four k-means groups of empty days. No simple play pays in any of them, except a rare high-VIX group (37 days) where the 10:00 straddle averaged +₹554. A cluster router chosen by LOYO made −₹2,579.
- **Can 09:45 tell a Gold day from an empty day?** Partly: AUC 0.66–0.72.

## Results

| SN | Study | Development (held out by year) | Verdict |
|---|---|---|---|
| 187 | **The 91% trade on both sides** (ATM CE + PE at 09:20 / 10:00, pair goal ₹1,000 / ₹1,500 or first leg to +₹1,500) | **−₹3.94 lakh**, 0 of 4 years (random minute: −₹3.63 lakh) | Fail. The winning leg's +₹1,500 is paid for by the other leg |
| 188 | Small fixed target on hot empty days (range break, ₹1,000 / ₹1,500, 1 lot) | −₹86,715 (null −₹75,827) | Fail |
| 189 | Variance seller on calm forecasts (iron fly ±200, ₹1.5 lakh) | −₹1.51 lakh; on all empty days the fly reaches +₹1,000 on **6 of 590** | Fail. Weekly options 2+ days out don't decay enough in one session to pay four legs |
| 190 | Volatility-regime leg (buy straddle when the forecast is high, sell the fly when low) | −₹1.10 lakh | Fail |
| 191 | **LSTM entry** (60-minute sequences, ±₹1,000) | Out-of-sample AUC **0.53 / 0.50**; never confident enough to trade. LightGBM AUC 0.51, −₹4,001 | Fail: no information |
| 192 | **LSTM volatility** vs HAR | R² 0.15 / 0.44 / 0.40 vs HAR **0.26 / 0.45 / 0.55** | HAR wins all three years |
| 193 | **LSTM 15-minute direction** (the "stock prediction" claim) | Accuracy **51.1% / 52.0% / 49.9%**, the base rate (always "up" 51.2 / 51.3 / 49.8%). "Opposite of the last 15 minutes" 51–53%. Traded: −₹71,667 | Fail: no better than a coin |
| 194 | Stacked ensemble | Never trades | Fail |
| 195 | NIFTY Apr–Dec 2022 sealed | 184 sessions, 145 lab sessions, 25–43 option series a day, complete index minutes | Data |
| **196** | **NIFTY 2022 exam (unseen year)** on proxy-empty days (yesterday's ADX < 30) | **SN95-L −₹4,490** (10 trades, 3 wins; null 95th +₹6,211); **SN171 −₹1,740 / −₹1,657** (2 trades each). Coin-flip ₹1,000 1-lot: −₹50,301 | **The forward watches fail an unseen year** |
| 197 | The empty-day leg (SN95-L → SN126-L → SN171) beside Gold | Leg alone **+₹39,086** at ₹15k in 3.6 years (59 trade days, 0.45 days a month at ≥ ₹1,000; in-sample for SN95-L / SN126-L). Gold + leg: 1.3 goal days a month vs Gold alone 0.84 | Small, in-sample |
| 198 | **Frozen TEST** (26 empty days) | Leg +₹2,407 at ₹15k (2 trades), +₹196 at ₹30k. All failed picks lose; the LSTM entry never trades; LSTM direction −₹3,004 | Too few trades to judge |
| 199 | Leg wallet and growth | Linear in lots: ₹1.5 lakh fixed +₹3.9 lakh in-sample, but 2025 −₹81k and worst month −₹69,605 | Scaling multiplies the losing years too |

## SN200: synthesis

1. **What empty days are:** weak-trend, calm, flat-closing days.
   - The market still moves about 0.5% after 10:00, but in both directions.
   - Buying options needs a directional move bigger than the premium's decay plus costs; selling needs a decay bigger than four legs' costs. Neither happens reliably.
2. **The 91% observation is real but not tradeable.**
   - With hindsight, one side of a 09:20 buy reaches +₹1,500 on 91% of days.
   - Buying both sides to "catch" it loses ₹3.9 lakh, because the other side's loss arrives at the same time.
3. **Deep learning (LSTM) finds no more than the simpler models did:** about 50% direction accuracy, AUC 0.50–0.53, and HAR forecasts volatility better. Short-horizon index direction is close to unpredictable from price history. Many "high accuracy" LSTM demos predict the price level (which is nearly yesterday's price) rather than the change, or scale data with future values; scored on direction without leaks, ours sits at about 50%.
4. **The one edge found in 2023–2026 (volatility persistence: SN95-L / SN171) did not survive 2022,** the only truly unseen year. It stays a paper watch only, and its record now counts against it.
5. **Fixed ₹1,000 / ₹1,500 targets and bigger wallets don't change the arithmetic.** Each trade costs ₹265–600 and hits its target on about 30% of attempts, so a fixed target is a cost.
6. **Recommendation for empty days:**
   - stay flat;
   - let Gold's profits pay the daily wage (SN177's salary account);
   - keep SN95-L / SN171 as paper watches only;
   - look for new information that price history lacks: the tick recorder (order-book flow from Nov 16), SENSEX (a second index; a SENSEX lab is the next build), the expiry book on expiry days, and event days.
7. **Data to fetch next (ICICI Breeze, via the skill):**
   - `nifty-2022-q1-fno` (Jan–Mar 2022; probe first, ~1,000 requests);
   - `sensex-2024-jan-sep-fno` (completes SENSEX 2024; ~3,000+ requests).
   - Then, as new targets on the owner's word: NIFTY 2021 and 2020 (probe first).
