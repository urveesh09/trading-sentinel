# SN161–SN185: the daily wage (Nov 13, 2026)

**Owner:** "the main goal of starting the whole SN series was not yearly return. It was a daily 10% target … a daily wage … ₹1500 … never felt that hard … if this system is sent to somebody who is living on a daily wage, they will never be able to live … try cheaper futures and options … 5% or 3% you keep for testing the latest data … if the system knows when to enter and when to exit the system will learn … a smart trading Sentinel, not just a filtering system."

**How it was tested**
- **Plan:** `PLAN.md`, frozen at `8d91837d` before any score. Each phase's scripts were frozen before they ran: `8d91837d`, `f2d8de08`, `62186118`, `e63fd462`, `b38b606c`.
- **Split:** TEST = the latest 5% (37 sessions, 2026-08-20 … 10-28), scored once by SN181. Development = the 705 earlier sessions. Phases P1–P4 report development numbers only.
- **Money:** Zerodha charges plus ₹205 per lot (house slippage), as many lots as the wallet buys, wage lock at +10%, day limit −20%.
- **The null:** the same exits on the same days with random entries.
- **One post-score fix:** `p4.gold` kept every day by default, so the first run of SN177–SN180 put TEST-day Gold profit into a few totals: SN179's sums and the "refilled" figures. It was fixed and rerun; the old files are kept as `results-*-v1-test-days-included.json`. Gold is today's system, not a candidate, and nothing was chosen from it.

## P1: the wage arithmetic (development)

| SN | Study | Result | Lesson |
|---|---|---|---|
| 161 | Wage calendar of today's system | Gold v5 at ₹15k: **0.8 wage days a month** (37 of 705 sessions); with SN95-L and SN126-L, 1.1. Production ₹30k: 1.1 / 1.3 | Gold is a fortune-maker, not a wage-payer: big days, few days |
| 162 | Seen vs kept | With hindsight, one side of a 09:20 ATM buy touches +₹1,500 on **91% of days** (average peak +₹5,688). A random side touches it on 58% but keeps it at 15:10 on 25%, and loses ₹2.83 lakh | This is what the partner sees: the wage is visible most days, but only in hindsight |
| 163 | The coin-flip wage trader (the null) | A wage on up to **58% of days** (wage ₹750, stop ₹3,000), yet **−₹4.1 lakh**. ±₹1,500: 29% wage days, −₹3.78 lakh. Even with zero slippage: −₹1.23 lakh. More attempts lose more | Many wage days is easy; money is not. The stop pays for the wins |
| 164 | Cheaper contracts | ATM is least bad (−₹3.78 lakh). OTM 1–4 strikes buy more lots, so costs grow faster than hits (OTM4: −₹15.6 lakh). The debit spread is worst. The range break beats random but still loses ₹2.92 lakh | Cheap contracts multiply costs. One NIFTY future (~₹16 lakh of index) needs margin far above ₹15k |
| 165 | Capital ladder | A fixed ₹1,500 wage on ₹1 lakh with 6 lots sits inside the round-trip costs (₹1,200+), so it loses. A 10% wage at every wallet behaves like ₹15k scaled up | Costs are per lot; a wage must be large against them |

## P2: learning when to enter and exit (development)

| SN | Study | Result | Lesson |
|---|---|---|---|
| 166 | Triple-barrier dataset (+₹1,500 vs −₹1,500, 4 actions, every minute; 294 sampled labels re-simulated, 0 mismatches) | +₹1,500 comes first on **31% (ATM call) / 28% (ATM put)** of minutes; always trading costs ₹508–614 a trade. No minute, weekday, gap or volatility bucket is positive | Break-even needs ~50%; the market gives ~30% after costs |
| 167 | LightGBM wage classifier (49 features, quarterly walk-forward) | Best threshold 0.6: **−₹1,00,529** vs the random null −₹89,298 (95th −₹58,767). **Worse than random.** Its top features are day-level (gap, yesterday's range, ADX, VIX) | The model learns which days move, not which side or minute pays |
| 168 | Meta-labelled signals (range break, VWAP cross, 1-minute impulse, EMA cross) | Ungated −₹3.91 lakh. The gate's best answer is to almost never trade: 21 trades in 2.6 years, −₹1,499 | The smart filter's honest answer: do not trade these signals |
| 169 | Learned exit (7,184 entries, 184k in-trade states) | Trims losses 7–10% (random entries −₹7.9 → −₹7.1 lakh), but stays negative and removes wage days | Knowing when to exit helps a little; it cannot make a no-edge entry pay |
| 170 | Online contextual bandit over six day-plays | −₹43,578 on 2024–26 (seeds −₹78k … −₹10k) vs random play −₹1.84 lakh. The best fixed play by LOYO is **no trade** | Online learning learns mostly to sit out, which is the right answer here |

## P3: other perspectives (development)

| SN | Study | Result | Verdict |
|---|---|---|---|
| 171 | **Volatility forecast (HAR-RV)** vs the straddle's implied, at 10:00 | ₹15k 1-OTM strangle (κ 1.1, hold): LOYO **+₹23,087** (23 trades, 3 of 4 years; null 95th ₹1,130). ₹30k ATM straddle: **+₹56,653** (43 trades, 4 of 4; null 95th ₹6,120). This morning's realised volatility carries the forecast (coefficient 0.59) | **Development pass.** The same mechanism as SN95-L (volatility persistence), now on all days. Thin: 6–12 trades a year |
| 172 | Afternoon window (13:15) | −₹3.39 lakh (= random) | Fail |
| 173 | Opening gap fade / follow | −₹36,293, 0 of 4 years | Fail |
| 174 | Quiet-day VWAP reversion | −₹5.60 lakh | Fail |
| 175 | 1-second impulse + learned exit | Validation −₹2.32 lakh vs a fixed 3-minute hold −₹2.03 lakh | Fail |

## P4: the wage itself (development)

| SN | Study | Result |
|---|---|---|
| 176 | Wage day player (Gold → forward watches → SN171 on the remaining days) | ₹15k: **1.2 wage days a month**, +₹1.57 lakh. ₹30k production: 1.3, +₹6.96 lakh. ₹50k: 1.2, +₹11.5 lakh |
| 177 | **Salary account**: one account trades Gold and pays a fixed wage every session from its balance | To never miss a payment from Gold ₹30k fixed + watches: **₹3.15 lakh to pay ₹750 a session, ₹4.9 lakh for ₹1,000, ₹8.45 lakh for ₹1,500** |
| 178 | Sweep vs compound (Gold ₹30k) | Compounding +₹6.42 lakh vs monthly sweep +₹2.17 lakh. Only **52% of months are positive** either way (median month +₹565–679) |
| 179 | Robustness | Gold ₹15k at ₹400 per lot +₹55,437; 1 minute late +₹87,370; player without its best 5 days +₹95,628. Month bootstrap: a losing month 39%, a month with ≥ 10 wage days **0%**, a losing year 4% |
| 180 | Starting price grid | Wage days a month 1.1–1.3 at every wallet; profit scales with capital (₹1 lakh growing: +₹24.1 lakh, worst month −₹1.22 lakh) |

## P5: the TEST and the answer

**SN181, the frozen TEST** (2026-08-20 … 10-28, 37 sessions, scored once). **No candidate passes.**

| Scored on TEST | Net | Wage days | Note |
|---|---|---|---|
| Gold v5 ₹15k (today's system, reference) | **+₹29,628** | 6 (2.0 a month) | 11 trade days, worst day −₹1,906 |
| Gold v5 ₹30k growing (production, reference) | **+₹2,08,710** | 7 (2.3 a month) | 11 trade days, worst day −₹12,163 |
| SN176 wage day player ₹15k / ₹30k | +₹27,914 / +₹2,04,785 | 6 / 7 | The companions added one losing day each |
| Coin-flip wage trader (the null) | −₹19,511 (5th–95th −₹31,222 … −₹7,309) | 30% of days | |
| SN164 range break | −₹28,616 | 9 | Below the null |
| SN167 wage classifier | −₹4,515 (10 days) | 3 | Null 95th +₹2,437 |
| SN168 meta-label gate | 0 (no trade) | 0 | It learned not to trade |
| SN169 learned exit | random −₹60,161 → −₹54,024; signals −₹1,30,091 → −₹1,16,824 | – | Trims about 10% of losses again |
| SN170 bandit | −₹4,329 (seeds −₹10,530 … +₹1,607) | – | "No trade" made 0 |
| **SN171 volatility forecast** (development pass) | ₹15k strangle: **no qualifying day**; ₹30k straddle: **−₹2,901 (2 trades)** | 0 | TEST was a calm stretch; too few hot days to judge |
| SN172 / SN173 / SN174 | −₹20,072 / 0 / −₹35,889 | – | Failed development too |
| SN175 1-second learned exit (Nov 2–12) | −₹49,349 vs fixed holds −₹50,821 … −₹51,921 | – | Failed development too |

**SN182, real quotes** (Sep 10 – Oct 28, the archive's 5-level depth; post-freeze data-path fix: the export folder had rotated):
- **Coin-flip wage trader:** −₹171 a trade on real quotes against the model's −₹465 (427 paired trades).
- **The gap is the house slippage:** real minus model is ₹214 a lot, the house's ₹205 a lot, which SN115 measured as the 39-second reaction delay.
- **Real spread:** the half-spread at entry is only ₹0.14, so buying more lots is cheap in spread terms; the cost is delay and charges.
- **Range break:** +₹1,394 over 23 trades on real quotes before any delay cost. Too few trades to mean anything.

**SN183, expiry days:**
- **Source:** the stored expiry results (E032 `late-results.json`) hold only the frozen 13:00–15:00 exam slice: 3 trades in 2024, none in 2025.
- **Why it can't answer:** no day-by-day record of the expiry book was stored, so wage days on expiry days are **not measured here**.
- **To answer it:** replay the expiry tapes with a day ledger. That is future work.

**SN184, the honest wage table** (`results-sn184.json`):
- **Every wallet:** about 1.2 wage days a month in development and 2.0–2.3 on TEST, from Gold v5 alone.
- **Paying ₹750 every session** from Gold (₹30k fixed) needs about **₹3.15 lakh** in the account; ₹1,500 needs about **₹8.45 lakh**.

## SN185: what SN161–SN185 teach

1. **A daily wage is easy to see and hard to keep.**
   - With hindsight, +₹1,500 is visible on 91% of days. A coin-flip trader with a wage lock "earns its wage" on 30–58% of days.
   - It still loses money every year, because the stop pays for the wins and every round trip costs about a third of the wage.
   - This is exactly the partner's experience.
2. **Every route to more trading days failed against random:**
   - more attempts, cheaper contracts (more lots, more costs) and bigger wallets with a fixed ₹1,500;
   - learned entries, learned gates, learned exits and an online bandit;
   - the afternoon window, opening gaps, VWAP reversion and 1-second impulses.
   - **What the machine learned:** to trade almost never. On these days, with these data, that is the smart answer, not a filter.
3. **The one repeatable gap-day edge is volatility persistence.**
   - SN95-L, and now the HAR forecast SN171: a busy morning keeps the day busy, while the 10:00 straddle price assumes it won't.
   - It passed development, but it fires 6–12 times a year, and TEST (a calm stretch) gave it almost no days.
   - It stays on the forward watch list, with the tick recorder's data from Nov 16.
4. **A daily wage can still come from the system, by paying it rather than earning it daily.**
   - Gold v5 earns in lumps: about half of months positive, with large winning days.
   - A salary account pays a fixed sum every trading day from Gold's balance. With Gold at ₹30k fixed plus the watches, it needs about ₹3.15 lakh to pay ₹750 a session and about ₹8.45 lakh to pay ₹1,500, without missing a day from 2023 to Aug 2026 (development, in-sample).
   - That is the honest way to give a wage-earner a daily income from this edge.
5. **Next:**
   - keep Gold v5 (paper) as it is;
   - keep SN95-L, SN126-L and SN171 as forward watches;
   - use the tick recorder's chain data from Nov 16;
   - with the owner's word, run one sealed test of SN171 / SN95-L on the unseen SENSEX Oct 2024 – Dec 2025 data, which doubles the hot-day sample.
