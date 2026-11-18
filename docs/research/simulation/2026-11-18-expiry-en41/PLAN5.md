# EN41–EN55 plan (frozen before any score)

Nov 18, 2026. The owner's instruction: run the auditor's ten slots (`docs/EXPIRY_RESEARCH_EN41_EN50.md`) plus five of my own, using everything learned so far. The goal is the most profit with the most loss control. The benchmark is E03.2 unchanged.

Nothing here changes Production, a flag, a runtime setting or a real-money limit.

## 1. What this round can and cannot prove

**Every expiry afternoon we hold is already seen:** NIFTY 2023–2026 and SENSEX Jul 2025 – Oct 2026. The database holds no NIFTY 2020–22 expiry-day chains; the pre-plan check found 0 expiry-dated option rows. So this round is **development screening**.

A slot that passes becomes a **FORWARD CANDIDATE**. It qualifies only on genuinely later sessions:
- the forward cohort is the first 20 expiry sessions per index after Nov 18, 2026;
- it runs as a disabled or isolated paper shadow through the normal GitHub path, on the owner's word;
- the plan for that cohort is frozen before its first session.

The selection ledger includes every earlier EN slot. These fifteen add to it.

**Exploratory look (hypothesis generation, recorded before design):** I ran one scan on the seen sessions (`scratchpad/en5/explore.py`).
- **An ATM straddle** bought at 12:30, 13:00, 13:30, 14:00 or 14:30 and sold at 15:14 loses on average in almost every book: −13 to −789 a pair. But its median best value after entry is +16% to +52% of cost. On most expiries the straddle goes through a sizable gain that buy-and-hold gives back.
- **No pin magnet:** the index ends closer to the 13:30 or 14:30 maximum-OI strike on only 17–57% of days, with no significant drift towards it.
- **Writer flow** (put minus call OI change) predicts the next 10 minutes weakly, at 0.1–0.3 ATR. That is too small to pay option costs.

My five slots therefore test managed volatility trades and the lessons already learned, not a pin or flow signal. Their development numbers are in-sample checks of ideas formed after this look.

## 2. Data, books and fills

**Books:**
- **NIFTY:** 197 sessions in date order: 2023, 2024, 2025 (sealed export `2026-11-02-expiry-e02`) and Jan–Oct 2026 (sealed `exam2026.sqlite`).
- **SENSEX:** 63 sessions, Jul 2025 – Oct 2026.

**Coverage:**
- Option bars: all day for NIFTY 2023–25, from 12:00 for NIFTY 2026 and SENSEX.
- A morning signal with no option bars is **unavailable**, never a loss. EN44's SENSEX book is DATA_UNAVAILABLE (no morning options). Its NIFTY 2026 mornings are counted and excluded.

**Lab:** the round-4 minute lab (`en_lab4.run_day4`, immutable).
- Decisions are taken on the completed bar; fills are at the next bar's open ± half the spread, at ordinary, adverse and severe fill levels, with 20% of the bar's volume available per fill.
- Each index uses its own lot, fees, strike step and band.
- `en_lab5.install()` adds four explicit dispatchers. With round-5 fields off they call the originals. `check()` proves results4 reproduces for E032, EN40, EN35_diag, EN32, EN28 and EN36 on every book at all three fill levels.

**Two ways to run every arm:**
1. **Fixed-cap expiries:** each session on its own, with its full day reserve, Rs 30,000 cash and no brakes. This measures signal and lifecycle quality.
2. **The Rs 30,000 wallet:** one continuous book per index.
   - The brakes (Rs 1,500 / 3,000 / 4,000) work on the **trading high-water** and never reset.
   - **50% profit retention:** after each session, `sweep = max(0, 0.5·max(P,0) − W)`, `W += sweep`, `cash = 30,000 + P − W`.
   - Losses reduce the wallet in full.
   - `retention_check()` reproduces the auditor's example.

## 3. Capital controls (auditor section 4)

| Control | What it is |
|---|---|
| `E032_25k` | Original E03.2, Rs 25,000 wallet, no retention (continuity) |
| `E032_30k` | Original tickets (calls Rs 1,250, puts Rs 2,500, Rs 5,000 a day) in the Rs 30,000 wallet |
| `E032_sym` | Equal-risk E03.2 (Rs 1,250 parents, Rs 2,500 a day) |

## 4. The fifteen slots (one primary each; diagnostics named, never candidates)

### The auditor's ten

- **EN41 / EN42 (book pressure / pressure failure): DATA_UNAVAILABLE.**
  - They need receipt-clock futures depth packets.
  - TR01 began Nov 13 inside Production's Docker volume, so it holds at most two expiry sessions, and it is not exported or sealed.
  - Exporting it is a separate, owner-authorised task. No minute substitute is allowed.
- **EN43 (weighted constituents): DATA_UNAVAILABLE.**
  - It needs dated weights and sub-minute constituent prices.
  - We hold only Kite 15-minute bars of the current basket.
- **EN44: opening range accepted, then retested.** Symmetric Rs 1,250, limit 1.04 × decision ask, 8-minute clock.
  - **Range:** freeze the 09:15–09:45 index and futures ranges.
  - **Arming:** between 09:46 and 11:30, the first completed close beyond both ranges by ≥ 0.10 ATR10, in the same direction, with the future on that side of its session VWAP.
  - **Entry:** within the next five completed minutes, the future comes within 0.25 ATR of its broken edge and closes back outside, while the index stays outside. Buy at the next bar.
  - **Limits:** one plan per direction, at most two parents.
  - **Exits:** the future closes back inside by 0.25 ATR, the 35% premium stop, the 2x rule, or the clock.
  - **Diagnostics:** `EN44_now_diag` (immediate breakout) and `EN44_noon_diag` (the same rule anchored on 12:00–12:30), plus a matched random-side null (40 seeds).
- **EN45: a failed escape back toward the futures VWAP.**
  - **Escape:** between 10:00 and 14:30, freeze the future's previous 15-minute high/low and its session VWAP. A completed close ≥ 0.25 ATR beyond one edge is the escape.
  - **Entry:** within two completed minutes, a close back inside, with the index's latest minute agreeing with the reversal. The frozen VWAP must be inside the range and ≥ 0.75 ATR from the escape close in the reversal direction. Buy the reversal at the next bar.
  - **Exits:** the future reaches the frozen VWAP; the future closes beyond the escape extreme by 0.10 ATR; the premium stop; or 5 minutes.
  - **Limits:** one plan per frozen escape.
  - **Diagnostics:** `EN45_now_diag` (immediate first fade) and the random-side null.
  - **Coverage:** the morning part exists only for NIFTY 2023–25.
- **EN46: does the remaining move pay for the option?** On equal-risk E03.2's signals, at the contract it would buy:
  - **Volatility:** local IV comes from the minute close, against the expiring forward K + C − P at the strike nearest the index. Black-Scholes on the forward, r = 0, time in trading minutes / (252 × 375).
  - **Forecast:** 8-minute physical forecast, with mean = ½ × the last-5-minute mean futures log return × 8, clipped at 2 ATR; variance = the 20-minute variance × 8.
  - **Repricing:** 21 equal quantiles, time reduced by 8 minutes.
  - **Haircut:** 2 × half the spread (model spreads; measured spreads are not held for history) plus round-trip fees.
  - **Keep the signal** only if the net is > 0 at IV and at 0.9 IV, and above the one-lot friction.
  - **Comparisons:** `EN46_zero_diag` (zero drift) and `EN36_sym_diag` (θ 0.6924 on equal-risk signals).
- **EN47: pick the strike by its response.** On equal-risk E03.2's signals, consider ATM, the first ITM and the first three OTM strikes, one lot inside Rs 1,250.
  - **Score:** g = the smaller model gain for a 0.50-ATR favourable move in 2 minutes (at IV and 0.9 IV). c = spread plus fees per unit.
  - **Pick:** buy the lowest c/g, only if g > c. Ties go to the lower reserve, then the closer strike.
  - **Control:** `EN47_native1_diag` (the native pick at one lot) on common signals.
- **EN48 (scheduled RBI decisions): INCONCLUSIVE by count.** The only officially verified RBI decision on a NIFTY expiry session in the scored history is Aug 8, 2024 (RBI press release of Mar 27, 2024, 2024-25 schedule). That is far below the support floor. The 2023-24 schedule was not verified.
- **EN49: a small model of executable net return.**
  - **Rows:** every 5-minute boundary 09:45–14:45 × side, with the native one-lot contract inside Rs 1,250.
  - **Label:** the 3-minute later bid minus the next-bar ask minus fees, over the decision reserve. A missing exit counts as a full loss.
  - **Six features:** the futures 1- and 3-minute moves / ATR; the 5/20-minute variance ratio; the 5-minute basis change / ATR; spread / ask; and minutes left / 375.
  - **Fit:** standardised ridge with penalty 1.0 and an unpenalised intercept, per index. It is fitted before each session on all earlier sessions only, and needs ≥ 40 sessions and ≥ 500 rows.
  - **Trade:** the best positive side, only if the 5th percentile of 200 session-block bootstrap refits (seed 20261118) is > 0.
  - **Exits:** the 35% stop, the 2-ATR index structure, and a 3-minute clock.
  - **Diagnostics:** `EN49_icpt_diag` (intercept only) and `EN49_trend_diag` (a fixed 0.5-ATR 3-minute trend rule), plus calibration by predicted decile.
- **EN50: is another minute worth holding?** On equal-risk E03.2's entries.
  - **Training states:** ages 2–14 of each earlier session's tickets, including the minutes after their real exit.
  - **Label:** the one-minute change in executable sale value net of the change in sell charges, over the entry price.
  - **Six features:** the futures 1- and 3-minute moves / ATR; bid / entry; bid / peak; age / 15; minutes left / 375.
  - **Fit:** ridge as in EN49. It needs ≥ 40 ticket expiries and ≥ 500 states.
  - **Early exit** after two successive non-positive predictions.
  - **Extension:** at the native 8-minute clock, extend only if the bootstrap 5th percentile is > 0, up to age 15.
  - **Native exits always win.**
  - **Diagnostics:** `EN50_3min_diag` (unconditional 3-minute exit) and `EN29_sym_diag` (stall runner).

### My five

- **EN51: managed straddle.** At 13:00, buy one lot each of the ATM call and put.
  - **Funding:** both legs plus fees must fit Rs 5,000, which is E03.2's own day ceiling. Otherwise it is refused and counted.
  - **Exits:** sell both when the straddle's sale value reaches +25% of its cost, or falls to −25%; otherwise at 15:14.
  - **Diagnostic:** `EN51_hold_diag`, held to 15:14 without the bracket.
  - **Question:** can the swing that the exploratory look found on most expiries be banked?
- **EN52: straddle that drops its loser.** The same entry and the same −25% joint stop.
  - **Leg-out:** when one leg's bid reaches 1.5× its fill, sell the other leg.
  - **The winner then runs:** its floor is its cost, it trails at half its peak, it sells at 10×, or at 15:14.
  - **Question:** can a non-directional entry turn into a directional runner without predicting direction?
- **EN53: E03.2's signals, bought at the money.** One lot of the ATM or first ITM strike, whichever has the lower round-trip cost share.
  - **Funding:** inside a symmetric Rs 2,500 ticket (Rs 5,000 a day, E03.2's ceiling).
  - **Exits:** E03.2's.
  - **Control:** `E032_30k`.
  - **Question:** EN32 learned that cheap OTM is wrong for small moves. Does that hold for E03.2's own trend signals?
- **EN54: managed straddle only when it is cheap.** EN51, entered only if straddle / (ATR10 × √(930 − minute)) ≤ 0.6924. That is EN36's frozen θ, reused, not re-chosen.
  - **Question:** a cheap straddle after recent movement should be the case most likely to pay off (volatility clustering).
- **EN55: the learned E03.2 (FORWARD-ONLY).** E03.2 with EN28's patient entry, EN27's scout-and-add and EN29's stall runner (EN35's configuration).
  - These pieces were chosen on these sessions, so its development numbers are reported and it is registered for the forward cohort, not given a development verdict.

## 5. Verdicts (applied mechanically by `en_score5.py`)

**New entries** (EN44, EN45, EN49, EN51, EN52, EN54), on every book with data, in fixed-cap mode. All of these must hold:
- ordinary net > 0;
- adverse net > 0;
- net without its best two expiries > 0;
- worst expiry ≥ −Rs 2,500;
- for directional setups, above the median of the 40-seed matched random-side null.

Fewer than 30 tickets on 20 expiries in a book means INCONCLUSIVE.

**Modifications** (EN46 and EN47 and EN50 against `E032_sym`; EN53 against `E032_30k`), per book. All of these must hold:
- ordinary ≥ control;
- adverse ≥ control;
- without-top-2 ≥ the control's;
- worst expiry ≥ the control's worst − 250;
- adverse > 0.

Support needs ≥ 20 affected parents on ≥ 10 expiries, pooled, else INCONCLUSIVE.

A modification that fails can still earn **PROTECTION ONLY** if, on every book, all three hold:
- worst expiry ≥ the control's;
- wallet drawdown ≤ the control's;
- ordinary ≥ control − 1,000.

**Tests:**
- one-sided sign-flip permutation (20,000 flips, expiry days as units) of the mean daily net (entries) or the paired daily difference (modifications);
- Holm across the ten primaries.

A development PASS that is not significant after Holm is labelled "screening pass; not significant".

**Status:**
- a development PASS becomes **FORWARD CANDIDATE**;
- otherwise the slot stays FAIL, INCONCLUSIVE, PROTECTION ONLY, DATA_UNAVAILABLE or FORWARD-ONLY.

## 6. Reported regardless (owner's anatomy rule)

- **Per arm and book:**
  - fixed-cap and wallet results at every fill level;
  - without its top two expiries;
  - worst expiry, profit factor and by year;
  - tickets by side, first exit and entry window;
  - added, removed and changed against its control;
  - best and worst tickets.
- **Wallets:** halted sessions, swept profit and the final wallet.
- **Slot diagnostics:**
  - EN49 calibration;
  - EN46 gate reasons;
  - EN47 picks against native;
  - exit paths;
  - straddle refusals.

## 7. Order and files

1. **Write the files:** `en_lab5.py`, `en_score5.py`, `PLAN5.md`.
2. **Run `check()`:** dispatcher parity, ridge equality, retention, the straddle synthetic, 285 truncation-invariance decisions, and counts only.
3. **Run `selftest`.**
4. **Run `freeze`:** it hashes this plan, the round-5 files, every transitive lab, loader and fee module, `results4.json` and both data bindings.
5. **Commit, then `score` once,** in the background, with a start receipt.
6. **Write up:** `results5.json`, `anatomy5.json`, `ANATOMY5.md`, `docs/EXPIRY_RESEARCH_EN.md` and the shared docs.
