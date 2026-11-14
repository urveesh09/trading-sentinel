# The weekly option seller (SN201–SN220) and the road to Gold v6 — the complete record (Nov 14, 2026)

**Read this first for any Gold v6 work.** It records everything done on Nov 14, 2026:
- every version of the weekly seller, with its exact recipe and every number;
- why it is not deployed;
- how to rebuild and rerun it from scratch;
- what to try next.

The owner believes SN201–SN220 hold the entry point for Gold v6 ("some of which were actually good and successful … they may be our source and entry point for Gold V6 … we will try again in the coming SN strategies"). This file is written so that the next session can start from here.

Companion files:
- `docs/SN_STRATEGY_HISTORY.md`: section 1 is the overall resume point; its last sections are SN201–SN210, SN211–SN220 and the open items;
- `docs/SN_TESTING_PROCEDURE.md`: sections 12–13 cover the weekly engines;
- `docs/research/fno/2026-11-14-sn201/README.md` and `docs/research/fno/2026-11-14-sn211/README.md`: the study tables.

---

## 1. Status in one paragraph

- **Gold v5 (paper, Production `826f0727`) is unchanged.** There is no Gold v6.
- **The weekly option seller is the most promising gap-day idea in 220 studies.** On NIFTY 2022–26 every unprotected version made money; the best (WK-S) made +₹3.14 lakh per lot, with every year positive. With Gold in one account it gave 380 green days against Gold's 55.
- **On the three samples it had never been tuned on, it lost.** That held with and without seven kinds of smart exit (−₹71k to −₹1.57 lakh over 96 weeks).
- **It is not deployed, and is not on paper.**
- **The honest tests left:**
  - NIFTY Oct–Nov 2021 options (download unfinished);
  - NIFTY 2020 / Jan–Sep 2021 (not downloaded);
  - a forward paper record.

## 2. What the owner asked, Nov 14 (in their words)

1. **The download text:** "Tell me what do I tell to download tomorrow on iCICi after I login." The text was given; section 8 has the outcomes.
2. **SN201–SN210:** "instead of staying flat, why not the system do something where it can earn little money … how do the real traders earn that money on every day? … different perspective, different instruments, different systems … the system should become smarter and smarter … make little profit money first", plus "train some model, mix of machine learning, LSTM".
3. **SN211–SN220:** "there were some noteworthy ones … that actually earned money, but certain days wiped it all off … a smart fail safe mechanism … master the exit … slice down the losses as much as possible while ensuring that the profit is maintained … a gold V6 which includes gold V5 and the gap covering strategy."
   - **Correction given:** WK-S is not a better *entry*; it sells options and is paid on quiet days. On unseen data it also lost outside its single worst week (NIFTY 2021–22 was −₹15,859 without the Russia week).
4. **Docs:** "thoroughly document … the initial 200 to 210 strategies, some of which were actually good … I will compact the session." This file is the answer.

## 3. Why a weekly seller (the idea)

- Every SN leg before SN201 opened and closed within one day or one night, so it paid ₹265–1,000 of costs per trade against a smaller one-day option decay.
- Gold's empty days (~84% of sessions) are calm, two-way, flat-closing days (SN186). Those are the days an option **seller** is paid.
- **The weekly book:** sell once a week at 15:15, hold until the weekly expiry, pay costs once, and collect the decay of every calm day and night.
- **The literature:**
  - the variance risk premium;
  - Muravyev & Ni (JFE 2020) on overnight option returns;
  - SEBI's FY22–FY25 studies: about 9 in 10 individual F&O traders lose, while firms that make markets or sell options with large capital earn.

## 4. The recipes (exact, as coded in `wk.py` / `wk2.py`)

**Common to all:**
- **Contracts:** NIFTY nearest weekly options, 1 lot (65 units; SENSEX 20), today's lot for every year.
- **Timing:** each position is entered at the **15:15 close** of the k-th session before expiry (k = 1 is the day before expiry; "F" is the week's first session).
- **ATM and Q:** ATM = the strike where call and put are closest in price; Q = that ATM straddle's price. Distances are multiples of Q, rounded to the strike step, at least one step.
- **Fills:**
  - sell at the model bid, buy at the model ask (the house spread table; SENSEX uses it on premium ÷ 3.25 × 3.25);
  - Zerodha charges (NFO / BFO schedules in `python-engine/cost_schedules.py`);
  - **₹100 per leg-lot slippage**.
- **Settlement:** at expiry, at intrinsic value against the index's 15:00–15:29 average, charged as a round trip (conservative).
- **Marks:** a leg with no print on a mark day is marked at intrinsic + 0.5 point.

**WK-S** (the SN204 pick; `("STRANGLE 0.5", 3, "settle", 1.0)`):
- **Entry:** at 15:15, 3 sessions before expiry (Tuesday expiry → Thursday 15:15), sell 1 call at ATM + 0.5·Q and 1 put at ATM − 0.5·Q.
  - Typical in 2025–26: index ~24,700, Q ~255 points, short strikes ~±150 points, credit ~148 points ≈ ₹9,600 per lot.
- **Fail-safe:** at the 15:15 close of each later session before expiry, close if the position's value (after exit costs) is ≤ −1 × the entry credit.
- **Otherwise:** hold to settlement.
- **Wallet:** about ₹2.5 lakh per lot as a margin proxy. **Not verified on Zerodha.**

**The runner-up** (`("STRADDLE", "F", "settle", 0.5)`): sell the ATM straddle on the week's first session at 15:15; stop at 0.5 × credit at a 15:15 mark; else settle.

**WK-G = WK-S + the expiry-day gate** (SN217; rule `{"gate": -0.25}`): at the 15:15 mark of the day before expiry, close unless the index is no more than 0.25·Q beyond either short strike (call strike + 0.25·Q ≥ index ≥ put strike − 0.25·Q); else hold into expiry.

**Breach + gate** (SN218 pair; `{"breach": 0.5, "gate": -0.25}`):
- the gate, plus a minute-level exit when the index is 0.5·Q beyond a short strike;
- the exit executes at the next minute with fresh prints, paying +₹100 per leg-lot if before 09:20.

**The pre base** (`("STRANGLE 0.5", 3, "pre", 1.0)`): like WK-S, but always closed at 15:15 on the day before expiry. It never holds through expiry day.

**The always-sell ATM straddle** (`("STRADDLE", 1, "settle", None)`): sell the ATM straddle at 15:15 the day before expiry, hold to settlement. This is the least-selected rule, a reference.

## 5. Every number

### 5a. Development (NIFTY Apr 2022 – Aug 19 2026; 229 weekly expiries; per lot, ₹100 per leg-lot)

| Version | Net | By year 2022 / 23 / 24 / 25 / 26 | Win % | Worst week | Worst month | Notes |
|---|---:|---|---:|---:|---:|---|
| Short ATM straddle, settle, k = 1 / 2 / 3 / F (SN202) | +1,73,682 / +1,40,350 / +2,44,267 / +2,26,677 | – | 65.1 / 61.4 / 59.8 / 62.4 | −28,989 / −42,212 / −48,308 / −48,308 | – | Payout ÷ Q 0.90–0.96: sellers keep 4–10% of the premium. The long straddle loses −₹3.0–4.0 lakh |
| 78 protected iron flies / condors (SN203) | **0 of 78 positive** (best −75,662) | – | – | – | – | Wings at ±0.5–1 Q recover only part of their price |
| **WK-S** (SN204) | **+3,13,523** | +79,743 / +43,757 / +38,494 / +74,112 / +77,417 | 62.3 | −39,844 | −51,245 (Apr 2025) | 223 weeks; LOYO +1,49,729 (4/5 years); ₹200 per leg +2,53,555; without the best 5 +2,23,476; bootstrap p5 +89,868; drawdown 68,120; 32 of 53 months positive |
| Runner-up STRADDLE kF stop 0.5 (SN204) | +3,13,166 | +37,033 / +33,842 / +1,07,579 / +84,598 / +50,113 | 59.4 | −33,692 | −62,677 | |
| All 38 unprotected variants (SN204) | **38 of 38 positive** (+43k to +3.14 lakh) | – | – | – | – | Broad plateau |
| WK-S sized by HAR (SN205 rule B: 2 lots / 1 / skip) | +3,71,361 | +66,985 / +27,806 / +57,522 / +63,469 / +1,55,579 | – | −60,911 | – | Beats WK-S in 2 of 5 years only |
| WK-S skip-when-cheap (SN205 rule A, LOYO) | +1,46,228 | – | – | – | – | Random-skip 95th percentile +2,89,061: FAIL |
| LightGBM / LSTM / average filters (SN206) | +2,88,780 / +2,91,664 / +2,44,498 | – | – | – | – | Out-of-sample AUC 0.564 / 0.49 / 0.551; unfiltered +3,32,835 on the same weeks: FAIL |
| **WK-G** (SN217) | **+3,04,942** | +81,818 / +7,694 / +43,727 / +1,31,144 / +40,559 | – | −32,745 | −32,138 | CVaR 5% −16,438 vs −22,252 |
| Breach 0.5 + gate (SN218) | +2,16,866 | – | – | −32,745 | −29,771 | |
| Pre base (SN204 / SN212) | +1,72,695 | +62,693 / −8,578 / +35,622 / +61,061 / +21,896 | – | −32,745 | −30,886 | |

**WK-S robustness (SN208):**
- **Entry time:** 15:05 / 15:16 / 15:25 gives +2.45 / +2.80 / +2.74 lakh.
- **Slippage:** ₹300 / ₹400 per leg-lot gives +2.09 / +1.64 lakh, all years positive.
- **Strike width:** 0.25 / 0.75 Q gives +1.93 / +1.58 lakh.
- **Stop:** none / 0.5 / 1.5 / 2.0 × credit gives +2.32 / +2.78 / +2.50 / +2.51 lakh.
- **Entry day:** k = 2 / F gives +1.56 / +3.06 lakh.
- **Concentration:** the best 10 weeks make 52% of the profit.

**Where WK-S loses (SN212, development):**
- Overnight gaps **earn** (+₹1.62 lakh in all weeks).
- Losing weeks lose on **expiry day (−₹4.17 lakh)** and intraday (−₹2.99 lakh).
- Only 8 of 139 winners were ever down 1× the credit.
- After the index touches a short strike (93% of weeks), holding was better 60% of the time (+₹1,634 a week).

**Smart exits on WK-S (SN213–SN217, development net / worst week / worst month):**

| Exit | Net | Worst week | Worst month |
|---|---:|---:|---:|
| Breach −0.25 / 0 / 0.25 / 0.5 Q | −10,354 / −3,431 / +1,14,513 / +2,94,011 | −32,745 / −32,745 / −39,844 / −39,844 | −61,235 / −61,003 / −62,617 / −49,901 |
| Minute loss stop 0.5 / 1 / 1.5 / 2 × credit | +2,25,188 / +2,71,550 / +2,80,782 / +3,08,292 | −39,844 | −53,311 / −57,678 / −51,245 / −51,245 |
| Profit take 0.5 / 0.7 × credit | +2,84,833 / +2,96,272 | −39,844 | −56,305 / −51,245 |
| Speed 0.3 / 0.5 / 0.7 Q in 30 minutes | −37,312 / +39,741 / +1,72,569 | −32,745 / −39,844 / −39,844 | −56,578 / −59,863 / −60,208 |
| Protect on breach 0 / 0.25 | +1,25,698 / +1,62,398 | −32,745 / −39,844 | −60,312 / −61,422 |
| Event calendar (skip Budget / RBI / election weeks) | +2,11,480 | −39,844 | −35,105 |
| **Expiry-day gate** −0.25 / 0 / 0.25 / 0.5 | **+3,04,942** / +2,70,448 / +2,26,634 / +1,75,914 | −32,745 | **−32,138** / −32,138 / −35,508 / −30,886 |

- **SN218, combinations:** none cut the worst week by 30%. The April 2025 weekend gap (−₹32,745) cannot be exited; LOYO +2.21 lakh.

**Gold + seller in one account (SN207 / SN219; 2023 – Aug 19 2026; Gold v5 ₹30k growing):**

| Account | Net | Green days | Worst day | Worst week | Worst month | 2023 / 2024 / 2025 / 2026 |
|---|---:|---:|---:|---:|---:|---|
| Gold alone | +6,42,173 | 55 (775 days without a trade) | −21,113 | −25,188 | −38,531 | −12,107 / +1,87,476 / +2,92,811 / +1,73,992 |
| Gold + WK-S | +8,75,953 | 380 | −33,751 | −40,460 | −56,645 | +31,650 / +2,25,970 / +3,66,923 / +2,51,409 |
| Gold + WK-G | +8,65,297 | 350 | −33,751 | −39,662 | −31,981 | −4,413 / +2,31,203 / +4,23,955 / +2,14,551 |
| Gold + breach + gate | +8,08,954 | 306 | −33,751 | −39,662 | −36,169 | −27,399 / +2,64,322 / +3,90,605 / +1,81,427 |
| Gold + pre base | +7,52,174 | 277 | −33,751 | −39,662 | −31,981 | −20,684 / +2,23,098 / +3,53,872 / +1,95,888 |

- **Correlation, WK-S vs Gold:** −0.09 on all days, −0.27 on Gold's trade days. The seller partly offsets Gold.
- **WK-S on Gold's empty days:** +₹266 a day on average, including the days with no position (+₹337 on days with a position, 51.5% green).

### 5b. The samples it was not tuned on (scored once each: SN209 on Nov 14, then the SN219 second look)

| Version | TEST (9 weeks, Aug 20 – Oct 27 2026) | NIFTY Dec 2021 – Mar 2022 (17 weeks) | SENSEX Oct 2024 – Apr 2026 | Total |
|---|---:|---:|---:|---:|
| WK-S | −23,348 (44% won) | −56,743 (35% won; Russia week −40,884) | −42,022 (70 weeks, 60% won, worst month −70,088) | **−1,22,113** |
| Runner-up straddle kF | −11,373 | −61,620 | −8,309 (83 weeks) | −81,302 |
| WK-S sized by HAR (rule B) | −12,236 (1 week) | −81,831 | +37,459 (51 weeks) | −56,608 |
| Always-sell ATM straddle k1 | −16,229 | −25,113 | **+31,042** (83 weeks, 61% won) | **−10,300 (≈ flat)** |
| Defined-risk iron condor (WK-A) | −11,003 | −14,700 | −15,219 | −40,922 (smallest worst weeks: −5.6k to −8.7k) |
| WK-G (gate) | −5,074 | −52,773 | −99,023 | −1,56,870 |
| Breach 0.5 + gate | −19,923 | **+7,971** (worst week −7,602) | −1,02,993 | −1,14,945 |
| Pre base | **+6,308** (78% won) | −7,241 | −70,208 | −71,141 |

- **Real quotes (SN209, forward archive, Sep 10 – Nov 12 2026, 15:15):** the cost model is right. NIFTY half-spread is 0.10 real vs 0.12 model; SENSEX 0.39 vs 0.35. One lot always fills. TEST entries repriced on real quotes: +₹17.

## 6. What we learned (keep these)

1. **The premium is real but small.** Sellers keep about 4–10% of the weekly premium, and it is paid only unprotected: near wings cost more than they return.
2. **The profit pattern:** overnight decay and expiry-day decay pay. Expiry-day moves and weekend gaps take it back.
3. **In-sample breadth is not proof.** 38 of 38 variants were positive in 2022–26, yet the best ones lost on all three other samples. The plain, least-selected rule (always-sell ATM straddle, k1) ended about flat on them.
4. **Forecasting the bad weeks failed:** HAR timing, LightGBM and LSTM all reach AUC 0.49–0.56.
5. **Exits cut tails but cannot create an edge.** The gate cut the development worst month by 37% and lost more on SENSEX. Breach + gate turned the NIFTY 2021–22 Russia week from −₹40,884 into a −₹7,602 worst week, but lost on SENSEX.
6. **Different samples disagreed.**
   - SENSEX liked holding through expiry day (the plain straddle and HAR sizing were positive there).
   - TEST liked never holding through expiry day (the pre base was positive).
   - NIFTY 2021–22 liked tight risk control (breach + gate).
   - A version that works on all three has not been found.

## 7. Ideas for the next Gold v6 attempt (NOT tested; each needs a frozen plan)

1. **Trend timing for the seller.** Gold's empty days follow weak-trend days (yesterday's ADX 20.8 vs 28.3, SN186). Sell only in weeks that start after low-ADX days, using Gold's own trend knowledge. HAR *volatility* timing failed (SN205); *trend* timing was never tried.
2. **Cheap far wings as disaster insurance (±2–3 Q).**
   - SN203 tested near wings only, because the downloaded strikes reach about ±1 Q at the week's start.
   - This needs a Breeze download of far strikes (a new target, on the owner's word).
3. **Less exposure:** the always-sell straddle on the day before expiry (k1) was the least bad on unseen data (≈ flat). Combine it with breach + gate or trend timing.
4. **The seller as Gold's hedge, not a profit source:** it is negatively correlated on Gold's trade days (−0.27). Size it small and judge it by the account's worst month, not by its own profit.
5. **A forward paper shadow:** zero cost, and every week is genuinely unseen data. It needs a small Dev module and a deploy on the owner's word.
6. **True crash test:** NIFTY 2020 (March 2020) and Jan–Sep 2021. These need a new Breeze target and a probe; ICICI may not serve them.

**The bar for Gold v6 (owner's goal: profit kept, big losses cut):**
- **Development:** positive in ≥ 4 of 5 years held out.
- **Tail:** the worst month at least a third smaller than WK-S's.
- **Unseen data:** positive on data it was never tuned on. What remains: the NIFTY Oct–Nov 2021 options once downloaded, NIFTY 2020/2021, forward paper.
- **Money:** paper first; real money only on the owner's word.

## 8. Data (where everything is and what is seen)

| Data | Where | Status |
|---|---|---|
| NIFTY development, Apr 2022 – Oct 28 2026 (year datasets, all minutes) | `wk.DEV_SOURCES` in `docs/research/fno/2026-11-14-sn201/wk.py` (paths under `docs/research/simulation/2026-11-01-fno-n08/_local`, `fno/2026-10-30-day-router/_local`, `fno/2026-10-30-nifty-2025-test/_local`, `fno/2026-10-29-year-genome/_local`, `fno/2026-11-13-sn186/_local`) | Seen |
| NIFTY exam, Sep 2021 – Mar 2022 (index every minute; options of the expiries Dec 2 2021 – Mar 24 2022) | lean `2026-11-14-sn201/_local/mirror-nifty-exam.sqlite` (sha `cbd227bf…`); full minutes `2026-11-14-sn211/_local/mirror-nifty-exam-full.sqlite` (sha `9bd6ed0f…`) | Seen (SN209, SN219) |
| SENSEX exam, index May 17 2024 – Apr 30 2026; options of the expiries Oct 4 2024 – Apr 30 2026 | lean `…sn201/_local/mirror-sensex-exam.sqlite` (sha `a272ad18…`); full `…sn211/_local/mirror-sensex-exam-full.sqlite` (sha `1e7e2af3…`) | Seen (SN209, SN219) |
| Real-quote archive Sep 10 – Nov 12 2026 | `~/sentinel-operations/fno-forward-panel-20261028/…/_local/exports/20261113T103001Z` (via `2026-11-13-sn101/qa.py`) | Seen |
| NIFTY 1-second Jan 16 – Apr 2 2026 | the Breeze folder (downloaded Nov 14) | Not used |
| NIFTY Oct–Nov 2021 options | `nifty-2021-q4-fno`: 410 of 957 option requests | **Unseen, unfinished** |
| NIFTY 2020, Jan–Sep 2021 | – | Not downloaded |
| SENSEX Jan–Sep 2024 | – | ICICI does not serve it (probe failed) |

**ICICI downloads done Nov 14 (the downloading agent, through the skill):**
- `nifty-2022-q1-fno`: 58 sessions, Jan 3 – Mar 28. Mar 29–31 have no minute index, and Jan 12 lacks both ATM legs.
- NIFTY 1-second fallback: 60 sessions (Apr 2 back to Jan 16, 2026); 204 of 215 complete; Jan 1–15 left.
- `nifty-2021-q4-fno`: index 44 of 44, futures 75 of 75, options 410 of 957.
- `sensex-2024-jan-sep-fno`: probe failed (Dec 4 2023, Jan 2 2024, May 6 2024).

`_local` folders are git-ignored. After a fresh checkout, rebuild the mirrors read-only from `~/sentinel-operations/breeze-history-20261029/data/breeze-history.sqlite`, using `sn201.mirror(und, sn201.SPECS[und])` and `sn211.mirror(und, path, lo, hi)`. The caches `_local/wk-*.pkl` rebuild themselves on first use (about 20 seconds).

## 9. How to rerun or extend

- **Python:** `C:\Users\Urveesh\sentinel-ml-venv\Scripts\python.exe` (numpy 1.26.4, LightGBM 4.5.0, scikit-learn 1.5.2, PyTorch 2.5.1 CPU). Run from the study folder.
- **Result files are written once:** every `snNNN.py` refuses to run if its `results-snNNN.json` exists. New work goes into a new folder with new SN numbers and a frozen `PLAN.md`.

**Recompute WK-S on development (folder `docs/research/fno/2026-11-14-sn201`):**

```python
import wk
D = wk.dev_data()                                   # cached NIFTY development
weeks = wk.split(wk.expiries(D), "dev")             # 229 weekly expiries ("test" = the latest 9)
trades = wk.book(wk.NIFTY, D, weeks, ("STRANGLE 0.5", 3, "settle", 1.0))
print(wk.stats(trades))                             # net 313523, by_year, worst ...
E = wk.exam_data("SENSEX")                          # a lean exam mirror (seen)
print(wk.stats(wk.book(wk.SENSEX, E, wk.expiries(E), ("STRANGLE 0.5", 3, "settle", 1.0))))
```

**Minute-level exits (folder `docs/research/fno/2026-11-14-sn211`):**

```python
import wk2; wk = wk2.wk
D = wk.dev_data(); weeks = wk.split(wk.expiries(D), "dev")
mins = wk2.Minutes("dev")                           # or wk2.Minutes("NIFTY") / ("SENSEX") with wk.exam_data(...)
tr = wk2.book2(wk.NIFTY, D, mins, weeks, wk2.WK_S, {"breach": 0.5, "gate": -0.25})
print(wk2.summary(tr))                              # net, worst, worst_month, cvar5, fired, hedges
```

- **Rules:** `breach`, `loss`, `profit`, `speed`, `protect`, `calendar`, `gate` (combine them in one dict).
- **Engine pieces:**
  - `wk.trade` handles a single week;
  - `wk.daily_changes(t)` gives the daily P&L for portfolios;
  - Gold v5 day nets: `p4.gold("Rs 30k growing (production)")` (`docs/research/fno/2026-11-13-sn161/p4.py`; `sn207.py` shows the import).
- **New structures:** add them to `wk.STRUCTS` or `wk.legs_for`.

## 10. Commits (all on `codex/production-correction-hedge-p0`, pushed)

- **SN201–SN210:** `00564b6b` (plan and engine), `6847a924`, `7bdc7e73`, `4852fc05`, `8192ccf5`; docs `09fbf5f8`.
- **SN211–SN220:** `2c2d1b66` (plan and engine), `2693893f`, `f8a5b533`, `436295ca`; docs `ce51c3ea`.
- **Before them (Nov 13–14 night):** SN186–SN200 `4462f86f` … `d08e02fd`, docs `e5f60227`.
- **Production:** `826f0727` (Nov 13), unchanged all day.
