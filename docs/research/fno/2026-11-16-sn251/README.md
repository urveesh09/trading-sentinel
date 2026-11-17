# SN251–SN275: Gold's gap days from Gold's own wallet, without margin (Nov 16, 2026)

**Owner (Nov 16):**
- "why not consider hedging and only option selling in wk-H … much less risk … the deposit needed will be also much less";
- "use the same wallet that the Gold V5 is using … I don't want to use margin because there is potential of unlimited loss … the amount we can refill [is] by max the wallet's full amount … in those gap days, please earn me the money possible … option buying every day has a potential to earn more than 10%";
- "25 slots till SN 275 … new perspective".

**Answer in one line:** no gap-day strategy that uses only Gold's ₹30k wallet, without margin, passed. Every one lost on development data or on the unseen exams, or both. Options-only WK-H (wings instead of futures) loses on every sample. Buying options every day loses ₹150–660 per lot per day.

## How it was tested

- **Freezes:**
  - plan `PLAN.md` at `fb7e7523` before any number;
  - the engine (`gl.py`, `ow.py`) at `0555a559`;
  - the Block C runner and SN256–SN257 at `fbc949aa`; SN258–SN263 at `e60e28ba`;
  - the amendment (SN271–SN272) at `c22d0b0f`; SN269 at `4773927b`.
  - Every slot ran once.
- **Samples:**
  - DEV: NIFTY Apr 2022 – Aug 19 2026, 850 sessions;
  - TEST: Aug 20 – Oct 28 2026, 37 sessions;
  - **two new buyer exams**, never used for any intraday or overnight buyer rule:
    - **EXAM-N**: NIFTY Oct 2020 – Mar 2022, 286 sessions;
    - **EXAM-S**: SENSEX Oct 2024 – Apr 2026, 306 sessions;
  - each sample has full-day minutes of the current weekly contract.
  - No sample has expiry-day option minutes or next-week contracts.
- **Costs:**
  - Zerodha's current F&O charges, plus ₹205 per lot per leg per round trip;
  - bid/ask at the close ± half the P75 spread (SENSEX scaled);
  - a ₹3,000 stop (10% of ₹30k) on minute closes;
  - overnight positions are valued at the next session's prices, plus ₹100 per lot per leg for an exit before 09:20.
- **Pass rule (frozen):**
  - G1: DEV net > 0 and ≥ 3 of 5 years positive;
  - G2: beats a same-budget random null (95th percentile);
  - G3: both exams positive;
  - G4: DEV positive at ₹400 and one minute late.
  - The pick in each slot is the variant with the best worst DEV year (max-min), from ≤ 12 variants. Only the pick runs on the exams.
- **One wallet (`ow.py`):**
  - SN110's contract: the leg only when Gold is flat; ≥ ₹15k left free; its stop 10% of the wallet inside the shared 20% room; Gold's signal closes the leg.
  - With no leg it reproduces Gold v5 exactly (₹8,50,882, 742 days, 0.0 rupee difference).

## Results

| SN | Study | Result | Verdict |
|---|---|---|---|
| 251 | **Options-only WK-H** (the owner's question): WK-H's timing, wings instead of futures, 5 WK samples, per lot | Iron fly ±0.5 / 1.0 / 2.0 × straddle: −2,67,416 / −2,61,580 / −2,72,393 in total (0, 0, 1 of 5 samples positive); iron condors −2.13 to −2.18 lakh (0 of 5). Largest possible loss per lot (DEV median): IF 1.0 ₹4,190, IC 0.5/0.5 ₹2,954; they would fit 20% of ₹30k. WK-H with futures: +3.86 lakh (band 0.6), +4.19 lakh (band 0.8), 4 of 5 | **Wings cut the risk and the deposit, and lose the profit** |
| 252 | Census and the one-wallet player | Jan 2023 – Oct 2026: 944 sessions, Gold traded on 133, **811 gap days** (609 non-expiry + 202 expiry). Gold v5 ₹30k growing +₹8,50,883, 25 of 46 months positive. ₹750 a session is covered on average; ₹1,500 needs ₹697 more per gap day; 10% of the wallet needs ₹6,484 more per gap day | Parity exact |
| 253 | Seal the exams | DEV 850, TEST 37, EXAM-N 286, EXAM-S 306 sessions; ATM legs priced on ≥ 99.7%. ADX: SN06's algorithm, ≤ 1.8 points from SN06's file (bar construction); DEV uses SN06's own file | Data sealed |
| 254 | The old hot-day watches on both exams | SN95-L: EXAM-N −17,654 (19 trades, 4 won), EXAM-S −8,541 (21). SN171: EXAM-N lost every trade (−2,420 / −6,362). SENSEX port parity 0 mismatches | **FAIL**; volatility persistence has now failed three unseen samples |
| 255 | The literal ask: buy every day | First-5-minute side: DEV −2,68,858 (−₹317 a day), EXAM-N −59,979, EXAM-S −46,741. 09:45 drive side: −2.86 lakh / −1.44 lakh / −1.02 lakh. 10:00 straddle every day: −5.63 lakh / −1.84 lakh / −1.77 lakh. Random side: 0 of 200 seeds positive on DEV | **Activity costs ₹150–660 per lot per day** |
| 256 | Weekend / holiday long straddle | Best: −2,30,015 DEV (226 weekends, 20% won), EXAM-N −49,479, EXAM-S −83,629; worse than random nights | FAIL |
| 257 | Weekday overnight longs | Best (ATM call after a down day, to 09:45): DEV −77,799, EXAM-N −22,969, EXAM-S −85,047. NIFTY's close-to-open drift is real (+0.06–0.21% a night, t up to 6) but options cannot collect it | FAIL |
| 258 | Multi-session swing | Pick (10-day breakout, 1 session): DEV −70,500, EXAM-N +16,972, EXAM-S +1,920 | FAIL (works only in trending years) |
| 259 | Calendar and events | Pick (Budget-day straddle): DEV −13,172 (4), exams +7,462 / −6,578 (2 each). RBI-day straddles −20,857; turn-of-month calls −654; pre-holiday calls +13,331 (not the pick) | FAIL |
| 260 | Big opening gaps | Pick (fade ≥ 0.8%): DEV −35,428, EXAM-N −24,720, EXAM-S −11,952; every play lost on DEV | FAIL |
| 261 | WK-H's mirror, the cheap weekly straddle | Pick: DEV −31,126 (23), EXAM-N +88 (10), EXAM-S −12,076 (6) | FAIL |
| 262 | LightGBM move-size model | Top 10%: DEV 2023–26 −43,547 (39), EXAM-N −11,734, EXAM-S +13,524 | FAIL |
| 263 | Confirmed gap-day afternoons (14:00, low ADX) | Pick: DEV −2,20,560 (658), EXAM-N −33,102, EXAM-S −80,887 | FAIL |
| 264 | Expiry days (Gold never trades them) | No unseen expiry-day minutes exist; E03.2's +21,518 is in-sample, mostly after 14:00 (outside the owner's SN expiry rule); on Production paper it has placed **0 tickets** since Nov 5 (cash ₹25,000 = peak) | No verdict; flat |
| 265–268 | Survivors: robustness, the wallet, wallets, combinations | No survivor | Not run |
| 269 | **The daily wage from one wallet** (Gold v5 alone, no new money) | See below | – |
| 270 | Synthesis | Below | – |
| 271 | Overnight index ETF (cash, no margin; amendment) | 15:20 → 09:16–09:30 on ₹30k: every variant ≤ 0 on DEV (weekday nights −9,537 over 813 nights); pick −4,440 DEV, −1,364 / −3,737 exams. The drift sits in the closing and opening prints, which cannot be traded, and the ₹15.34 DP fee is 0.05% a night | FAIL |
| 272 | Calls before a weekday holiday (post-hoc, disclosed) | DEV +13,331 (45), TEST +4,643 (2), EXAM-N +25,327 (9, one +27.6k trade), EXAM-S +8,884 (17). G2 fails: worst year −8,390 vs null p95 −3,860 | FAIL by rule; positive on all four, ~10 trades a year |
| 273–275 | Reserve | SN273 needed an SN271 pass | **Unused** |

## SN269: the daily wage from Gold v5's own wallet (in-sample, Jan 2023 – Oct 2026)

**Pot rules:**
- Gold's profits are banked; a wallet step (×1.5) is paid from the bank;
- losing days are refilled from the bank, else from the owner's pocket;
- a fixed wage is paid every calendar session (expiry days included), else from the pocket.

| Start | Gold net | Wage ₹500: pocket / bank at end | Wage ₹750: pocket / bank at end | Last day the pocket is needed (₹750) |
|---|---:|---:|---:|---|
| Jan 2023 | 8,50,883 | 1,99,488 / 5,07,121 | 3,12,988 / 3,84,621 | Oct 31 2024 |
| Jan 2024 | 8,90,928 | 63,955 / 5,34,134 | 1,16,205 / 4,11,634 | Oct 31 2024 |
| Apr 2024 | 6,08,576 | 1,33,812 / 3,52,637 | 2,26,062 / 2,85,637 | Sep 24 2025 |
| Jan 2025 | 4,22,962 | 93,769 / 2,19,981 | 1,87,050 / 2,00,512 | Sep 23 2026 |
| Jan 2026 | 1,87,946 | 51,884 / 67,080 | 96,884 / 61,330 | Sep 23 2026 |

- Gold earns about ₹900 a session on average, so ₹500–750 a session is affordable over years.
- Gold's profit comes in lumps, so the owner advances ₹0.5–3.1 lakh first, depending on the start, and gets it back from the bank later.
- ₹1,500 a session is not covered from most starts.
- Full table: `results-sn269.json`.

## SN270: synthesis

1. **The owner's first question.**
   - Wings (an options-only hedge) do make the risk fixed and the deposit small. Iron-fly 1.0: at most ₹4,200 per lot.
   - But the wings cost about as much as the weekly edge, and every winged version lost on 4–5 of 5 samples.
   - The futures hedge is what makes WK-H profitable, and futures need margin.
2. **The owner's second request.**
   - No strategy found here earns on gap days from Gold's ₹30k with bought options (or defined-risk spreads) after costs:
     - on the 2020–22 NIFTY and 2024–26 SENSEX data nobody had used for buyers;
     - in 13 new studies;
     - including LightGBM, overnight and weekend holds, events, gaps, swings and afternoons.
   - Buying every day loses ₹150–660 per lot per day on every sample, the option-buyer arithmetic behind SEBI's finding that about 9 in 10 F&O traders lose.
3. **The one real effect seen, the overnight drift, cannot be collected:**
   - options lose to decay;
   - a cash ETF loses to the opening price and the DP fee;
   - futures would need margin.
4. **Pre-holiday calls** were positive on all four samples but failed the null and were chosen after the fact. About 10 trades a year: a forward paper watch at most, on the owner's word.
5. **What to do:**
   - keep the SN wallet flat on gap days;
   - take a daily income from Gold through a wage pot (SN269), knowing the owner advances money in the first 1–2 years;
   - keep WK-H (Gold v7) on Production paper: it is the only gap-day earner found, for the day the owner has the margin.

## Files

- **Plan:** `PLAN.md` (with the Nov 16 amendment).
- **Code:** `gl.py` (sessions, prices, positions, books), `ow.py` (one-wallet player), `legs.py`, `slot.py`.
- **Studies:** `sn251.py` … `sn272.py`, `events.json`, `results-sn251.json` … `results-sn272.json`.
- **Logs:** `logs/` (git-ignored).
- **Local data:** `_local/` (git-ignored session caches `gl-devall.pkl`, `gl-examn.pkl`, `gl-exams.pkl`; source hashes in `results-sn253.json`).
- **Disclosed fixes:**
  - `sn251.py` printed the largest possible loss as None; `sn251_maxloss.py` reads it from the same entries (no result changed);
  - `slot.py` gained an optional DEV-years argument after SN256–SN257 ran (their gates are unchanged);
  - SN271's exams are partly seen (SN257 printed the drift).
