# EN56–EN70 plan (frozen before any score)

Nov 18, 2026. The owner's instruction: run the auditor's ten slots (`docs/EXPIRY_RESEARCH_EN56_EN65.md`), enriched where useful, plus five of my own. Each slot must teach something, and if no better strategy appears, the round should leave a stepping stone towards the best one we have. The owner wants profitable, active and well-protected, with thorough and correct testing, and is in no rush.

Nothing here changes Production, a flag, a runtime setting or a real-money limit. EN55's forward test (`FORWARD5.md` and `ERRATA-20261118.md`, commit `e16bee2f`) is untouched: no idea from this round is folded into EN55.

## 1. What this round can and cannot prove

**Every expiry afternoon we hold is already seen:** NIFTY 2023 – Oct 2026 (197 sessions) and SENSEX Jul 2025 – Oct 2026 (63). So is the one recorded expiry, NIFTY Nov 17 (packets).
- Every result here is **development screening**.
- A slot that passes is a **FORWARD CANDIDATE** at most. It would need its own registration on later sessions, and it never replaces or modifies EN55's registered test.

**The selection ledger** holds every earlier EN slot (EN01–EN55), every diagnostic variant, and the other agents' expiry studies (SN378 synthetic forward, SN451 hedging momentum, EN23 last-half-hour momentum). These fifteen slots add to it. I checked before designing my five, so that none repeats a closed test.

**Repairs made before any score** (the audit's prerequisites):
1. **Calendar and qualification erratum** for EN55's forward test: committed `e16bee2f`.
2. **Observable candidates:** EN61's (and its ridge controls') candidate rows depend only on information at the decision. A future NO_FILL is an outcome, never a reason to drop the row.
3. **Quantity-aligned labels:** every label uses the executor's actual quantity, order count, fees and exit policy.
4. **Packet freshness:** every packet read in this round must have a positive, uncrossed top of book, an exchange time no later than its receipt, an exchange age ≤ 2 s at use, and its window's validity flag at entries *and* exits.
5. **Q28 relabelled:** volume-at-bid proxy and price-through proxy, never "conservative / optimistic".

## 2. Data, harness and books

**Books:** the round-5 books, in date order.
- **NIFTY:** 197 sessions. 2023–25 from the sealed `2026-11-02-expiry-e02` export, with all-day chains of about ±6–9 strikes; Jan–Oct 2026 from the sealed `exam2026.sqlite`, with 21 strikes from 12:00.
- **SENSEX:** 63 sessions, with 21 strikes from 12:00.
- Six late sessions lack Breeze index minutes (NIFTY Nov 3, 9, 17; SENSEX Oct 29, Nov 5, 12) and stay out of the books.

**Packets:** the read-only TR01 export `sentinel-operations/tr01-export-20261118` (802 chunks, hash-verified by `tr01.verify()`).
- Its Nov 17 session is the only recorded expiry, and only for NIFTY.
- It contains the NIFTY and SENSEX index, two futures each, the expiring and next two expiries' chains (41 strikes × CE/PE), and INDIA VIX.

**Harness: `en_lab6.run_day6`**, a hooked copy of the immutable `en_lab4.run_day4`. `check()` proves it reproduces `run_day4`, day by day, for E03.2, EN55, E032_sym and every round-5 arm that runs through `run_day4`, on both books at all three fill levels. All of round 5's dispatchers are reused unchanged (`en_lab5.install()`). The hooks, all off by default:

| Hook | What it does |
|---|---|
| `parent_cap` | Caps one parent's all-in reserve |
| `max_intents` | Caps entry intents a day (an intent is a submitted entry order, filled or not) |
| `ladder="stop_only"` | Replaces the native exit ladder with the 35% premium stop, the slot's own exits, the clock and the flat |
| Slot exits (`XSPEC`) | Setup-specific exits, evaluated before the native ladder; a latched exit is never withdrawn |
| `core_bank` | EN65's core sale, plus its profit-funded child |
| `liq_pick` | EN63's contract choice |
| Perturbations | Extra adverse ticks, one bar of extra delay on marketable fills, passive-fill ambiguity scenarios |
| Intraday marking | Every open position marked at each bar's low bid after sell charges, giving the worst intratrade equity |

**Fills:**
- **Marketable:** decisions are on the completed bar, and fills come from a later bar's open ± half the spread, at ordinary, adverse or severe level, with at most 20% of that bar's option volume.
- **Entry limits:** a new marketable limit is `down(1.04 × decision ask)` and must fit the reserve. Native E03.2 / EN55 controls keep their own 1.08.
- **No fill:** an entry that cannot fill on its next bar is NO_FILL.
- **Exits:** an exit that cannot fill is retried on later bars. If it is never filled by 15:29, the ticket is UNRESOLVED and loses the whole premium.
- **Within one bar:** when both barriers fall in the same bar, the adverse one wins.

**Clocks:**
- New minute setups decide **12:30–14:30**, hold non-runners at most **15 minutes**, and are flat by **15:14**.
- Native E03.2 / EN55 keep 13:00–15:00 and 8 minutes.

**Funding:**
- **New standalone entries (EN60/61/62/64):** one parent per expiry, at most Rs 2,500 all-in (premium + charges + one more order charge per lot), at most 3 lots, at most 3 intents, no averaging.
- **Equal-envelope control `E032_env`:** E03.2 unchanged except one Rs 2,500 parent per expiry (calls and puts alike).
- **Rs 1,250 diagnostic:** every new setup is also shown at Rs 1,250, never chosen.
- **The other slots:** EN58 keeps EN55's budget; EN59 Rs 2,500 for the whole pair; EN63 one lot inside Rs 2,500; EN65 a Rs 2,000 core plus a child of at most Rs 500.

**Books run two ways:**
1. **Fixed-cap expiries:** each session on its own, with its full reserve, Rs 30,000 cash and no brakes.
2. **One continuous Rs 30,000 wallet per index:**
   - brakes at Rs 1,500 / 3,000 / 4,000 of trading drawdown from the trading high-water, never reset;
   - 50% profit sweep `max(0, 0.5·max(P,0) − W)`, swept money never returned;
   - cash = 30,000 + P − W, and cash + sweeps = 30,000 + realised net (asserted).
   - **Liquidation drawdown** is reported separately: the trading high-water minus the worst intratrade marked equity.

## 3. Shared rules for verdicts (frozen now)

**Support floors:**
- **New entries (EN60, EN61, EN62, EN64):** ≥ 30 funded parents over ≥ 20 expiries.
- **Modifications (EN58, EN59, EN63, EN65, EN67):** ≥ 20 affected parents over ≥ 10 expiries. Affected means the ledger differs from the control's parent at the same decision, or exists in only one arm.
- Below the floor the verdict is INCONCLUSIVE, whatever the rupees.

**NEW-ALPHA DEVELOPMENT CANDIDATE** (EN60, EN61, EN62, EN64), per index. All must hold:
1. support;
2. fixed-cap net > 0 at ordinary **and** adverse fills;
3. net without its two best expiries > 0;
4. net above `E032_env` at ordinary and adverse;
5. worst expiry no worse than `E032_env`'s;
6. Holm-adjusted p < 0.10.

**IMPROVEMENT CANDIDATE** (modifications), per index, against its named control. All must hold:
1. support;
2. ordinary and adverse net ≥ the control's;
3. net > 0;
4. worst expiry no worse than the control's;
5. its wallet halts no earlier than the control's;
6. Holm-adjusted p < 0.10.

**PROTECTION ONLY:** not an improvement, but with support:
- ordinary and adverse net ≥ the control's − Rs 25 × expiries;
- **and** either a better worst expiry or a smaller wallet liquidation drawdown.

It is labelled protection, never "more profitable".

**FAIL:** otherwise.

**The family test.** Nine strategy primaries (EN58–EN65 and EN67) × two indices = **18 hypotheses**, Holm-corrected together.
- **New alpha:** H0 is mean net per expiry ≤ 0.
- **Modifications:** H0 is mean (arm − control) per expiry ≤ 0.
- **The p-value:** a one-sided expiry bootstrap, 20,000 resamples of whole expiries (seed 20261118): `p = (1 + #{mean* ≤ 0}) / 20,001`.
- **Caveats:** this is approximate for skewed P&L and is not a policy replay. A slot without support enters the family with p = 1.

**Evaluation sessions.**
- EN61 is scored from its first non-abstaining session per index (≥ 40 training + 10 calibration sessions); EN62 from its first session with thresholds (20 covered expiries).
- Their controls (`E032_env`) and their nulls are measured on **the same sessions**.
- Every other slot uses every session.

**Diagnostics** (EN56, EN57, EN66, EN68, EN69) are ANSWERED or INSUFFICIENT EVIDENCE. EN70 is PARITY PASS / FAIL. No diagnostic setting can become a rule without a later registration.

**Every arm reports:** net by fill level, net without its best and two best expiries, worst expiry, tickets, winners, by year and by side, by first exit, fees, unresolved tickets, the wallet (P, swept, halts, first halt) and the liquidation drawdown.

## 4. The auditor's ten (their specification; my clarifications in *italics*)

### EN56: the executable opportunity map and the fee ceiling (diagnostic)

**The library:**
- **Decision times:** every 5 minutes from 12:30 to 14:30 (25 times).
- **Contracts:** both sides; ATM, first ITM and the first two OTM strikes (ladder offsets −1, 0, +1, +2 from ATM in the side's OTM direction) with a finite quote at the decision.
- **Reserves:** Rs 1,250 and Rs 2,500. The quantity is the most whole lots (≤ 3) whose `down(1.04 × ask)` limit fits.
- **Horizons:** 3, 8, 15 and 30 minutes, censored at 15:14 (censoring is flagged).
- **Entry:** the next bar, under the frozen limit, at ordinary (and adverse) fills.
- **Missing cases:** NO_FILL, unaffordable and missing cases stay in every per-decision denominator at zero.

**Per row:**
- gross, entry and exit slippage, every fee, and net;
- the worst and best marked liquidation value inside the hold (bar lows / highs after sell charges);
- minutes to the first net-positive marked exit;
- unresolved exposure;
- the unfunded underlying diagnostic, d × Δfuture in ATR and in rupees at the entry delta (Black-76 on the expiring parity forward). It is never an option P&L.

**Controls:**
- fees removed (diagnostic);
- spread removed (diagnostic: fills at the bar open);
- *the same library evaluated at E03.2's own decision minutes and side, against the unconditional grid of the same cell, and against a random side at those minutes.*

**Hindsight ceiling (not a strategy, not wealth):** per expiry, the best library row at each reserve.
- Expiries whose best net is ≥ Rs 250 and ≥ Rs 1,250.
- How often that best row first went through −35% (the native stop) or an unfillable interval.

**Packets:** the same library on NIFTY Nov 17, from depth-walked recorder quotes, beside the recorder-built minute-bar proxy (EN70), reported separately.

**ANSWERED** when every book's library is reconciled. *The question "is the affordable opportunity too small, or are we choosing the wrong moments?" is answered by comparing the conditional means and the ceiling.*

### EN57: what EN55's survival comes from (diagnostic)

**Arms:** the full 2 × 2 × 2 of patient entry, half-first scout and stall runner on E03.2, including E03.2 and EN55. Fixed-cap and wallet, both indices, all three fill levels.

**Reconciliation, per parent:**
- planned and filled lots, fallback and add lots;
- buy cash, sale cash, fees per order;
- a cash identity (asserted to a paisa);
- *matched-decision attribution against E03.2:* Δ on matched parents, plus new parents, minus lost parents.

**Concentration:** E03.2's two best NIFTY expiries removed one at a time and together (fixed-cap and wallet rerun).

**Robustness for E03.2 and EN55** (no brake is changed):
- 0, 1 or 2 extra adverse ticks on every marketable fill (and the passive threshold moved the same number of ticks);
- one extra bar of delay on every marketable fill;
- passive ambiguity, *a look-ahead stress only*: **ADVERSARIAL** grants a resting bid's fill only when that option's close 8 bars later is below the bid price, so losers fill and winners don't; **NO_PASSIVE** means resting bids never fill, leaving the fallback only;
- fresh Rs 30,000 wallets from each calendar-quarter start, run to the book's end (reported separately, never a cash injection).

**Reported:**
- how many perturbations cross the Rs 4,000 halt;
- which later tickets disappear;
- whether an adverse perturbation *raises* wallet P&L;
- the split of each component's effect into size, fees and exits on matched parents.

**ANSWERED** when all eight arms reconcile.

### EN58: patience or aggression chosen from information at entry (packets; modification of EN55's entry)

**Intents:** EN55's parent intents on NIFTY Nov 17, built from the recorder minute tape (EN70); EN58 is the first tranche's execution.
- **Contract and quantity:** EN55's own.
- **Limit:** min(EN55's original limit, `down(1.04 × decision walked ask)`).
- **Latency:** 1 s for every order and cancellation.

**Policies:**
- **P0, control: EN55's 60-second translation.** Rest at the best bid for 60 s, filled by the price-through proxy. If unfilled, one marketable fallback within the limit if the future rose in the signal direction over those 60 s and the structure is intact. *Named translation, not native parity.*
- **P1:** all aggressive.
- **P2:** a fixed 3-second wait, then the same fallback rule on the latest 10-s future move.
- **P3, EN58:** if the future moved in the signal direction over the previous 10 s **and** microprice > mid, P1; otherwise P2. The resting order is cancelled early on an adverse 0.10 ATR10 future move. Any fill during the 1-s cancel window counts, and no duplicate buy is sent while a cancel is unresolved.

**Passive fill:** the price-through proxy (later best ask ≤ our bid, or LTP ≤ bid − 0.05) is primary. The volume-at-bid proxy is the alternative. Where they disagree, three scenarios: both ways, plus an ADVERSARIAL one (ambiguous losers fill, ambiguous winners don't).

**Measures per intent:**
- fill status, price and cost against the decision mid;
- decision-mid markouts at 10 / 60 / 180 s;
- fill-price markouts at 60 / 180 s after the scenario fill;
- the missed-winner cost;
- P&L to EN55's 8-minute exit, sold into walked bids.

**Mechanics diagnostic:** the same four policies on one-lot orders every 5 minutes, 13:00–15:00, both sides, nearest OTM Rs 5–20, as named diagnostics.

**Verdict: INCONCLUSIVE by construction** (one session). If EN55 has no intent on Nov 17, the primary has zero observations.

### EN59: the whole straddle's cash flow after leg-out (modification of EN52)

**Entry:** at 13:00, EN52's ATM call and put, one lot each, the **whole pair ≤ Rs 2,500** including all charges.
- An unaffordable pair is refused and recorded.
- If one leg fails to fill, the filled leg is sold on the next bar (ONE_LEG recovery).
- Every leg's buy and sell is a separate ledger event.

**Exits:**
- **Before leg-out:** the joint stop at a pair liquidation value ≤ 75% of the original outlay.
- **Leg-out** only when (a) the stronger leg's bid ≥ 1.5 × its entry **and** (b) the pair's after-fee liquidation P&L ≥ +10% of the outlay; then the weaker leg is sold.
- **After that sale fills:** `package_P = weak-leg sale cash after fee + survivor's after-fee liquidation − original outlay`. The survivor is sold when package_P < ½ of its highest positive value since the sale, at 10× (native hero), or at 15:14.

**Control:** EN52 at the same Rs 2,500 cap, on the common-eligible sample.

**Comparators (never selectable):**
- EN52 at Rs 5,000 (continuity);
- closing the whole pair when (b) first holds (with the joint stop);
- EN51's ±25% bracket at Rs 2,500.

### EN60: sequential evidence of a new move (new entry)

**The detector:**
- For each completed future minute from 12:30, `z = log return / max(sd of the previous 30 log returns, tick / future)`. The tick is 0.10 for NIFTY and 0.05 for SENSEX, read from the dated catalogue.
- `C+ = max(0, C+ + z − 0.25)` and `C− = max(0, C− − z − 0.25)`, both starting at 0 at 12:30.
- **Arming:** the first crossing of 4.5 arms that direction, if the cash index's 2-minute change agrees. Otherwise the event expires.
- **Reset:** both accumulators reset to 0 after any event.
- **Structural origin:** the future close at the triggering accumulator's latest zero.

**Entry:** the native reachable contract (E03.2's band, reach and cap) inside Rs 2,500, at a later fill.

**Exits:**
- an independent opposite accumulator, starting at 0 on admission, crossing 2.25;
- a future close beyond the origin by 0.25 × the decision ATR10, against the position;
- the native 35% stop, trail, lock, 2× split and runner;
- 15 minutes;
- 15:14.

The native index-structure exit is replaced by the origin rule. At most 3 intents and 1 parent.

**Controls:**
- `E032_env`;
- the first 5-minute-range breakout: the futures range of the five bars ending 12:30, then the first futures close beyond it from 12:31 to 14:30 with the index's 2-minute change agreeing, one plan per direction, origin at the broken edge, the same exits without the accumulator;
- a random side at EN60's trigger times (40 seeds).

**Reported:** failed and missed triggers, index-disagreement expiries, and the move already spent before admission (d × (fill-bar future open − origin) / ATR).

### EN61: a 15-minute payoff model with aligned quantities (new entry)

**Candidates:** every 5 minutes, 12:30–14:30, both sides, the native contract inside Rs 2,500 (≤ 3 lots, 1.04 limit), built from decision-time data only.

**Eight fixed features:**
1. signed 1-minute future move / ATR10;
2. signed 3-minute future move / ATR10;
3. variance ratio of 5- to 20-minute returns;
4. signed 5-minute basis change / ATR10;
5. spread / ask;
6. time left / 375;
7. planned round-trip charges / planned reserve;
8. signed strike distance / ATR10.

**Outcome (it is also the executor):**
- the next-bar entry under the limit with actual fill lots, giving the filled reserve `Rcash`;
- each bar from the fill, the marked liquidation at the bar low / high after sell charges, minus the outlay;
- **LOSS** at ≤ −0.25·Rcash, checked first; **WIN** at ≥ +0.50·Rcash; sold on the next bar;
- otherwise **TIMEOUT**, sold at fill + 15 bars or at the flat;
- otherwise **NO_FILL**, which pays zero;
- UNRESOLVED counts as a LOSS with the full premium lost.

**The label** is the class, plus the realised net / Rcash.

**The model:**
- `HistGradientBoostingClassifier(max_depth=2, max_leaf_nodes=4, max_iter=32, learning_rate=0.05, min_samples_leaf=100, l2_regularization=1.0, early_stopping=False, random_state=20261118)`, with natural class frequencies;
- one model per index, refit before every session on all earlier sessions except the latest 10;
- a temperature T ∈ [0.1, 10] fitted on those 10 by log loss (golden-section on log T);
- per-class payoffs are the calibration means of net / Rcash.

**Trading:**
- **Abstain**, with the reason, unless there are ≥ 40 training sessions, 10 calibration sessions, ≥ 500 training rows and ≥ 20 calibration rows of every funded class with probability > 0.
- **Expected net** = Σ p·payoff. Trade the better side when it exceeds `order charge / planned reserve`.
- The first such decision of the day is the intent; if it gets NO_FILL, the next is tried (≤ 3 intents, 1 parent).

**Controls (same sessions, same executor family):**
1. **R1:** EN49 corrected (six features, one lot, 3-minute label, NO_FILL rows kept at 0, EN49's mean > 0 and bootstrap p5 > 0 rule);
2. **R2:** a quantity-aligned 3-minute ridge;
3. **R3:** a quantity-aligned 15-minute ridge on the primary's own label;
4. **R4:** intercept-only class frequencies × payoffs.

All arms score from the same first session per index. *SENSEX reaches its first scored session only at session 51 of 63, so INCONCLUSIVE is expected there.*

**Environment:** `sentinel-ml-venv`, scikit-learn 1.5.2 and numpy 1.26.4, recorded in the freeze (the engine's numpy).

### EN62: option-specific pressure relief (new entry)

**Grid:** every 5 minutes, 12:30–14:30.

**Direction:** d = the sign of the future's 3-minute move, if |move| ≥ 0.50 ATR10 and the index's 3-minute change agrees.

**Contract:** side d's native contract inside Rs 2,500.

**Residual:**
- **Forward:** F = K + C − P at the strike nearest the index, from the same bar. There is no carry adjustment: same-expiry parity on the expiry day.
- **Earlier IV:** the IV of that contract 10 minutes earlier, from its close and that bar's forward.
- **Repricing:** `repriced = Black-76(F now, K, T now, earlier IV)`.
- **Residual** = (close − repriced) / close 10 minutes earlier.

**Rejections:** zero bar volume at either time (stale), a failed IV inversion, or a missing forward.

**Threshold:** the 5th percentile of all grid residuals (both sides' native contracts, every grid time) in the same 30-minute bucket over the **preceding 20 covered expiries** of that index. The first 20 sessions are warm-up.

**Entry** when residual < that threshold and d agrees.

**Exits:**
- the residual (recomputed with the same earlier IV) reaches that bucket's median;
- a future close beyond the frozen 3-minute adverse extreme;
- the 35% stop;
- 15 minutes;
- 15:14.

This uses `ladder=stop_only`.

**Controls:**
- direction-only: the first direction-qualified grid time, same contract and exits, *except the residual target*. It has no residual thesis, and the pre-freeze smoke test showed that target firing at once on 113 of its 175 NIFTY tickets. See section 7;
- a random side at EN62's trigger times (40 seeds);
- decay-only: the residual repriced at the *earlier* forward, with its own threshold.

The matched sample is the days where EN62 and direction-only are both eligible.

### EN63: liquid exposure at a matching horizon (modification of E03.2's contract and clock)

**Entry:** the first affordable E03.2 signal per expiry, one lot, Rs 2,500 all-in, 1.04 limit.

**EN63's contract:** among ATM, first ITM and first OTM of the signal side, with no Rs 5–20 band, the smallest round-trip friction / premium. The friction is (2 × half-spread + buy and sell charges per unit) / ask. Ties go closer to ATM, then to the lower reserve.

**Clock:** native exits, but non-runners are held at most **15 minutes**.

**The 2 × 2:**

| | 8 minutes | 15 minutes |
|---|---|---|
| Native contract | **Control** | Native, 15 min |
| EN63's contract | EN63's contract, 8 min | **Primary** |

Each is one lot, one parent, Rs 2,500.

**Cash-matched diagnostic:** the native contract with the most whole lots (≤ 3) within EN63's actual reserve. It counts as matched when spending is within 10%; otherwise it is reported as unmatched.

**Reported:** reserve and net per reserved rupee beside raw rupees.

### EN64: continuation after a rise in price impact (new entry)

**Impact:** `impact = |log return| / sqrt(max(0.25, minute futures volume / median of the previous 30))`. It needs positive, finite per-minute volume on the bar and the previous 60.

**Event:**
- impact ≥ 3 × the median of the previous 30 impacts;
- the last three returns' signed efficiency `d·Σr / Σ|r|` ≥ 0.60, where d is the current return's sign;
- the index's latest minute agrees;
- 12:30–14:30, at most 3 intents.

**Entry:** the native contract inside Rs 2,500.

**Exits:**
- a future close beyond the event bar's opposing extreme by 0.10 ATR10;
- a non-positive signed efficiency of the next three returns (checked once, at event + 3);
- the native stop, trail, lock, 2× and runner (no index-structure exit);
- 15 minutes;
- 15:14.

**Controls:**
- a random side at the event minutes (40 seeds);
- magnitude only: |r| ≥ 3 × the median of the previous 30 |r|, with the same efficiency and index rules;
- EN24-style absolute volume: volume ≥ 3 × the median of the previous 30, with the same rules.

*SENSEX futures volume is thin (about 70 zero-volume minutes a day), so its coverage is reported and support may fail.*

### EN65: bank the core, then a strictly profit-funded tail (modification of E03.2's payoff allocation)

**The core:** E03.2's first affordable signal, one parent, a symmetric **Rs 2,000** all-in core.
- Native protective exits stay (stop, trail, lock, structure, clock); the native 2× split is replaced.
- **CORE_BANK:** at the first bar where the whole core's after-fee liquidation profit ≥ its entry premium + buy fee, the entire core is sold.

**The child, only after that sale has filled with realised profit G > 0:**
- The index's and the future's 2-minute direction must still agree with the signal.
- **Reserve** = min(0.5·G, Rs 500, the remaining Rs 2,500 day reserve).
- **Contract:** the closest OTM strike whose one lot, `down(1.04 × ask)` limit and all charges fit; if none fits, no child.
- **Exits:** the core's structure level, the 35% stop, the runner trail max(entry, ½ peak) from 2×, 10×, 15 minutes, 15:14. No second child.

**The ledger asserts** that realised core + child ≥ G − child reserve ≥ G / 2.

**Control:** the same core with no child (bank only).

**Comparators:**
- native E03.2 split / runner at one Rs 2,500 parent (`E032_env`);
- EN12 (cover lots + runner structure) at one Rs 2,500 parent.

## 5. My five

### EN66: one wallet for both indices (portfolio diagnostic, the auditor's combined-book contract)

**Arms:** E03.2, EN55, E032_sym and EN67's primary.

**The book:** NIFTY and SENSEX sessions merged in date order on their common period (Jul 29, 2025 – Oct 2026). NIFTY goes first if two share a date.
- One Rs 30,000 wallet.
- One trading high-water and one set of brakes.
- 50% sweeps.
- Reservations are shared, so each session's budget is limited by the cash left.

**Reported:** parents per week, the wallet path, halts, sweeps and liquidation drawdown, against the two separate wallets over the same weeks.

**Question:** does trading two expiries a week make the book steadier, or only bigger? This is also a dry run of the combined ledger that EN55's qualification layer uses.

### EN67: what more activity costs (strategy modification of EN55, with a diagnostic frontier)

**Primary `EN55_ACTIVE`:** EN55 with signals from **12:30** (not 13:00) and pullback efficiency **0.6** (not 0.7). Everything else is EN55's.

**Control:** EN55.

**Frontier (diagnostic, never selectable):** efficiency 0.5 / 0.6 / 0.7 / 0.8 × start 12:30 / 13:00 (8 arms, including EN55 and the primary). Reported as the marginal rupees per added ticket against EN55, by book and year.

**Verdict:** the modification rules apply, plus the primary must actually be more active: ≥ 1.25 × EN55's tickets.

**Question:** if extra trades carry negative expectancy, then "more active" means more losses. The owner gets that answer in rupees per trade.

### EN68: the probability of a halt (risk diagnostic, a policy replay rather than a shuffle)

**Arms:** E03.2, EN55, E032_sym and EN67's primary.

**Method:**
1. Each session's day result is computed at every brake scale (1, ½, ¼). The cash is always far above the budget; this is asserted.
2. 2,000 one-year paths (52 expiries) per index are drawn as circular blocks of 4 consecutive expiries (seed 20261118).
3. Each path runs the wallet policy exactly: brakes on the trading high-water, 50% sweeps, halts.
4. The combined two-index book (EN66) is drawn in blocks of 4 weeks.

**Reported:**
- P(a halt within the year);
- P(year-end P < 0);
- the median, 5th and 95th percentile year-end P;
- the expected sweep.

**Question:** how likely is a fresh Rs 30,000 book to halt in its first year? This is the stepping stone to any real-money conversation. It resamples seen sessions, so it is not a forecast.

### EN69: why the puts earn (mechanism diagnostic)

**Tickets:** every E03.2 and EN55 parent (fixed-cap, ordinary).

**Decomposition:** each sale's lots, from the entry decision close to the exit decision close, by sequential full revaluation (Black-76, parity forward, IV inverted from the closes):
- **underlying** = V(F₁, T₀, σ₀) − V(F₀, T₀, σ₀);
- **time** = V(F₁, T₁, σ₀) − V(F₁, T₀, σ₀);
- **volatility** = V(F₁, T₁, σ₁) − V(F₁, T₁, σ₀).

These sum exactly to the mark change.
- **Execution** = the fill-based gross − the mark change × units.
- **Fees** are the charges paid.
- Tickets whose IV cannot be inverted are reported as underlying + time.

**Library:** across all EN56 library rows at the 8-minute horizon (Rs 2,500), the mean IV change of calls and of puts, conditional on the sign of the underlying move.

**Question:** is the put edge structural (puts gain IV as the index falls, calls lose IV as it rises), or is it direction on a few days? A structural answer would justify an asymmetric design later.

### EN70: recorder minute tapes and parity (forward stepping stone)

**The builder:** minute bars from TR01 packets, labelled by bar start, the same as Breeze.
- **Index:** LTP OHLC by exchange time.
- **Futures and options:** the LTPs of packets whose cumulative volume rose, by last-trade time; bar volume = the change in cumulative volume.

The rows go into a scratch SQLite with `exam2026.sqlite`'s schema and are built by `en4_data.build`, the same code path as every 2026 tape.

**Parity on NIFTY Nov 17,** against the Breeze 1-minute candles held for that day (front future, all day; the 21 expiring strikes, 12:00–15:29; read-only). Breeze has no index minutes that day.
- **PARITY PASS** needs both:
  - (i) ≥ 95% of matched option bars with Breeze volume > 0, and ≥ 95% of futures bars, have |close difference| ≤ 0.10 for options and ≤ 2 ticks for the future;
  - (ii) running E03.2 and EN55 on the recorder tape and on a Breeze-options tape (recorder index and future in both, since Breeze holds neither for Nov 17) gives the same decisions, contracts and lots.
- If Breeze has no futures minutes for the day, the futures clause cannot be met, and the verdict is PARITY NOT ESTABLISHED with that reason.

**Outputs:** the TR01 Nov 17 tape for EN56 (packets) and EN58 (intents), and EN55 / E03.2 ledgers on Nov 17 (seen; descriptive only).

**What a pass means:** this builder becomes the A2 fallback in the forward test's data order (`ERRATA-20261118.md`). Each later export still needs the owner's OK.

## 6. Facts gathered before the freeze (no rupees looked at)

**Parity of the hooked harness:**
- `run_day6` reproduces `run_day4` on **15,600 arm-days**: every round-5 `run_day4` arm, both books, all three fill levels.
- `run_wallet6` equals `run_wallet`, and the pair engine equals `straddle_day` (EN51 / EN52 at Rs 5,000 and Rs 2,500, ordinary and adverse).
- **Causal checks:** 627 decisions are unchanged with every later bar erased, or with only the fill bar repriced (the audit's counterexample).
- **Mechanics:** the package floor, the EN52 gate, perturbations and marked equity pass on synthetic tapes.
- **Selftest:** the whole pipeline on truncated books passes.

**A smoke test printed counts and first-exit reasons only.** It changed one design: EN62's direction-only control lost its residual target (above).
- I also saw that EN65's six NIFTY children in the smoke test all left by their premium stop. No rule was changed for that.

**Counts (ordinary fills; intents / funded parents / expiries with a parent):**

| Arm | NIFTY (197) | SENSEX (63) |
|---|---|---|
| E03.2 | 70 / 66 / 58 | 12 / 12 / 11 |
| EN55 | 71 / 68 / 59 | 12 / 10 / 9 |
| E032_env | 61 / 59 / 59 | 11 / 11 / 11 |
| EN60 CUSUM | 180 / 159 / 159 | 54 / 48 / 48 |
| EN62 residual | 98 / 94 / 94 (176 sessions with thresholds) | 22 / 22 / 22 (43) |
| EN64 impact | 177 / 166 / 166 | **0**: SENSEX futures volume is never positive on the 61 bars the rule needs (0 covered minutes) |
| EN63 liquid contract | 67 / 64 / 64 | 9 / 6 / 6 |
| EN65 core + child | 62 / 60 / 60 | 11 / 10 / 10 |
| EN59 package (Rs 2,500 pair) | 21 / 21 / 21: 175 pairs refused for reserve | **0**: all 63 refused |
| EN67 EN55_ACTIVE | 219 / 204 / 138 | 45 / 41 / 27 |

**EN61:**
- **NIFTY:** 147 scored sessions from 2024-01-11 and 7,942 candidate rows. The model has a positive expected net on 40 decision days. R1 has none, R2 one, R3 and R4 none. No session abstained for class support.
- **SENSEX:** 13 scored sessions from 2026-07-16 and 2,710 rows. The model trades on 4 decision days.

**EN70 parity numbers (data quality, not returns), seen before this freeze:**
- 8,700 matched option bars; volume ratio median 1.00; closes within Rs 0.10 on **83.2%**.
- By price band: 99.7% under Rs 5, 83% at Rs 5–20, 56% at Rs 20–100, 76% above Rs 100.
- The best clock alignment is the unshifted one.
- The 95% criterion was written before these numbers and is **not changed**.
- Breeze holds **no NIFTY futures minutes after Oct 28** and no index minutes for Nov 17, so the futures clause cannot be met. EN70's verdict will therefore be PARITY NOT ESTABLISHED.
- The forward test's data order (`ERRATA-20261118.md` A2) then needs Breeze index **and** futures downloads for each session. That is a data request.

**EN58:** EN55 made **one** intent on the recorder tape of Nov 17, so its primary has one observation.

## 7. Files

| File | Role |
|---|---|
| `PLAN6.md` | This plan |
| `en_lab6.py` | `run_day6`, setups, straddle package, EN65 child, EN56 library, EN57/EN66–EN69 |
| `en_ml6.py` | EN61's candidates, labels, model and ridge controls |
| `pk6.py` | EN70's builder and parity, EN58, EN56 packets |
| `en_score6.py` | The selftest, freeze, start receipt, single score and verdicts |
| `freeze6.json` | Hashes of every file, transitive lab file and data binding |
| `results6.json`, `anatomy6.json` | Written once |
| `ANATOMY6.md` | Where every slot won and lost |
