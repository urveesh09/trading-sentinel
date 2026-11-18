# EN26–EN40 plan, plus the first exam on fresh 2026 NIFTY and SENSEX afternoons (frozen before any score)

Nov 18, 2026. Owner's instruction: run the auditor's ten slots (`docs/EXPIRY_RESEARCH_EN26_EN35.md`) plus five slots of my own (EN36–EN40), and use the expiry afternoons downloaded today. Every slot must teach something specific even if it fails. The benchmark is **E03.2 unchanged**.

Nothing in this plan changes Production, any runtime flag or any real-money limit. A pass makes an arm a candidate for a disabled paper shadow; promotion still needs the forward count (at least 20 new closed paper tickets) and the owner's word.

## 1. Data

### 1.1 Development (seen)
NIFTY 2023, 2024 and 2025 expiry chains: the sealed export `2026-11-02-expiry-e02/_local/data.sqlite`, the same tapes as round 3. All of it is seen.

### 1.2 The new export (`en4_data.py`)
Today's download wrote 1-minute option candles into the Breeze history database and packaged the same rows into `expiry-afternoons-1minute-20261118.zip`. Each day has the opening at-the-money strike ± 10 strikes, calls and puts, from 12:00 to the close. A pre-plan check found the zip and the database identical: same rows, same strikes, same closes on every file.

`en4_data.py export` copies read-only into `_local/exam2026.sqlite`, the same way `export_data.py` built the 2023–25 export:
- the index, all day 09:15–15:29;
- the dated front future, the nearest expiry on or after the day, all day;
- the expiring options, 12:00–15:29.

A data binding (`data-binding4.json`) records the hashes, the per-day row counts and the zip cross-check. Tapes are built exactly as `exam2023.build_tapes` builds them. The only change is that the symbol names carry the index.

A day enters only if all three hold:
- the download resolved every contract request (42 of 42);
- the database holds at least 200 index minutes and 200 future minutes between 12:00 and 15:29;
- the options carry the expiry equal to the day.

**Excluded:**

| Day(s) | Reason |
|---|---|
| NIFTY Nov 3, Nov 9 and Nov 17, 2026 | No Breeze index or futures candles; these days are also seen through live paper |
| SENSEX Oct 29, Nov 5 and Nov 12, 2026 | No Breeze index or futures candles |
| SENSEX Oct 15 and Oct 22, 2026 | Thin future: 187 and 132 of 210 minutes, under the 200-minute rule |
| SENSEX Jul 22, 2025 | Partial: 9 of 42 contracts |
| SENSEX before Jul 22, 2025 | Never attempted |

### 1.3 Cohorts and what is already seen

| Book | Days | Status |
|---|---|---|
| **N-X1** NIFTY Jan 6 – Sep 8, 2026 | 36 | **Untouched** for any expiry-afternoon option strategy |
| N-X2 NIFTY Sep 15 – Oct 27, 2026 | 7 | Partly seen: forward-panel quotes (EN16/EN18) and live paper of the E01/E03 family |
| **S-X1** SENSEX Jul 29, 2025 – Sep 3, 2026 | 58 | **Untouched** for expiry-afternoon OTM chains. SN251–SN272 read the SENSEX index, futures and the opening-ATM pair (mornings), never these chains |
| S-X2 SENSEX Sep 10 – Oct 8, 2026 | 5 | Partly seen: forward-panel quotes |

- **Exam verdicts use N-X1 and S-X1 only.** X2 is reported apart and in an "all" line, never in a verdict.
- After this score every cohort is seen.
- NIFTY 2020–22 and SENSEX before Jul 2025 remain data requests.

### 1.4 Index specifications
These are the live engine's, from `python-engine/expiry_e02.py` `UNDERLYINGS`:

| | NIFTY | SENSEX |
|---|---|---|
| Lot | 65 | 20 |
| Fees | NFO schedule | BFO schedule |
| Strike step | 50 | 100 |
| Premium band per unit | Rs 5–20 | Rs 16.25–65 (the same rupees a lot) |
| Choose cap (e03) | 200 points | 400 points |
| Pre-filter (e02) | 400 points | 800 points |
| Coverage rule | first OTM to 200 points | first OTM to 400 points |

Unchanged on both:
- the rupee tickets: Rs 1,250 a call, Rs 2,500 a put, Rs 5,000 a day;
- the brakes at Rs 1,500 / 3,000 / 4,000 of drawdown;
- the Rs 25,000 book;
- the fill model (next bar's open ± half the spread, `half()` by premium; 20% of the bar's volume).

A pre-plan check on the 2026 recorded quotes (count and price only) supports using that fill model on SENSEX:
- median quoted spread in the band, 13:00–15:00: Rs 0.10 on SENSEX against a model 2 × half of Rs 0.10;
- Rs 0.05 on NIFTY against a model Rs 0.05.

## 2. The lab (`en_lab4.py`)

`run_day4` is `en_lab3.run_day` generalised to an index specification, plus the new hooks below. `en_lab3` and all earlier receipts stay immutable.

`en_lab4.check()` must prove, before the freeze:
1. NIFTY spec with every hook off reproduces E03.2 (`en_lab2.run`) day by day on 2023–25 at all three fill levels.
2. NIFTY spec reproduces `en_lab3` day by day for each frozen round-3 arm used here (EN11, EN12, EN12_full_sale_diag, EN13, EN14, EN14_immediate_diag, EN21, EN25) on 2023–25 at all three fill levels.
3. E03.1 through `run_day4` equals `r8b_lab.run` E03.1 day by day (needed for the family tests).
4. `choose4` with the NIFTY spec returns exactly `L.choose`'s pick on every 2023–25 signal minute.
5. SENSEX spec unit checks:
   - BFO fee arithmetic, lot 20, strike step 100;
   - a synthetic tape trade reconciles to the paisa.
6. It prints counts only, never rupees.

## 3. Arms

All arms:
- run in their own continuous Rs 25,000 book per cohort, with the brakes;
- are fully cash-funded, long options only;
- are scored at ordinary, adverse and severe fills;
- must pass the index's coverage rule for every decision.

New setups use symmetric Rs 1,250 tickets (`put_mult` 1, Rs 2,500 day reserve).

### Controls and held round-3 parts (definitions frozen in `en_lab3.ARMS`)
- `E032` is the control. `E031` is used for the family tests.
- **Held from round 3, scored on the exam as `DATA_REQUESTS.md` item 1 promised:**

  | Arm | What it tests | Rule |
  |---|---|---|
  | `EN21` | scale-in | R-EXIT |
  | `EN25` | resting bid | R-EXIT |
  | `EN12` | runner vs full sale | R-EXIT |
  | `EN14` | second wave | R-NEW |

- **Comparison controls:** `EN11`, `EN12_full_sale_diag`, `EN13` and `EN14_immediate_diag`.

### The auditor's ten (minute-cadence adaptations stated plainly)

**EN26: confirm damage before exiting faster** (R-EXIT). Minute adaptation; the 10-second version is DATA_UNAVAILABLE and is a forward recorder (TR01) job.
- **Applies to:** non-runner tickets, before 15:14.
- **Watch:** a completed minute whose option low, read as a bid (`down(low − half(low))`), is at or below the loss stop (a stop still below the entry price), while its completed bid is still above it (so the native stop did not fire), starts SUSPECT.
- **Confirmation:** the next completed minute only. All three must hold, with S, F and A the index close, future close and ATR10 at the decision bar:
  - bid ≤ 1.10 × stop;
  - d × (index − S) ≤ −0.5 A;
  - d × (future − F) < 0.
- **If confirmed:** exit everything at the next bar (reason DAMAGE).
- **Otherwise:** SUSPECT clears. A new touch on the confirmation minute starts a new SUSPECT.
- **Native exits win** on any minute where they fire.
- **Diagnostic `EN26_cat_diag`:** only a catastrophe trigger. A completed minute whose low bid ≤ 0.40 × entry exits at the next bar.
- **Reported:** losses saved against recoveries cut, on the same tickets as E03.2 and EN11.

**EN27: give the scout longer to earn an add** (R-EXIT).
- **First buy:** for a planned E03.2 ticket of P ≥ 2 lots, buy ⌈P/2⌉. The rest stays in the parent's reserve; there is no new money. One-lot tickets are unchanged.
- **Add:** one add, P − first lots. The signal can come at a completed minute aged 2–6 bars after the first fill, before the 8-minute clock, with no exit reason, no pending exit and not a runner. All of these must hold:
  - d × (index − S) ≥ 0.25 A;
  - the last completed change of both the index and the future is in d's direction;
  - the bid is above the first fill;
  - the structure is intact.
- **Add fill:** at the next bar, with a limit of the fresh ask × 1.08, shrunk to fit the parent's unused reserve.
- **After the add:** the entry becomes the weighted average and the stop = max(old stop, 0.65 × new average). The stop never moves down. The clock keeps its original start.
- **Reported:** adds made and their net, half-only tickets against the control, and the extra fees.

**EN28: patient entry with a bounded fallback** (R-EXIT). Minute adaptation: rest one bar instead of 10 seconds.
- **Rest:** at decision bar i, rest a bid at P = `down(close − half(close))` during bar i+1.
- **Passive fill (conservative bound):** at P, when bar i+1's low ≤ P − 0.05 (ordinary) or P − 0.10 (adverse and severe), for at most 10% of that bar's volume.
- **Fallback:** the remainder is cancelled at the end of bar i+1. At bar i+2 one marketable buy is allowed if both hold:
  - d × (future(i+1) − future(i)) > 0;
  - the structure is intact.
- **Fallback limit:** min(`down(decision ask × 1.04)`, the original reserve-based limit). The size is shrunk to fit the remaining reserve.
- **Missed:** if nothing fills, the ticket is missed and recorded.
- **Exits** start at the first fill. Every fill pays its own fees.
- **After a fallback fill:** the entry is the weighted average and the stop = max(current stop, 0.65 × average).
- **Diagnostic `EN28_opt_diag`:** the optimistic bound (low ≤ P, 20% of volume).

**EN29: a runner that must keep earning its hold** (R-EXIT).
- **Unchanged:** the same 2x partial sale as E03.2.
- **Exit test:** after it, track the most favourable index extreme since the sale. Exit the remainder (RUNNER_STALL) when both hold:
  - two successive completed minutes made no new favourable extreme;
  - the future closes through its prior two-minute opposing swing: for a call, below the lower of the two previous lows; mirrored for a put.
- **Native exits** (trail, hero target, 15:14) come first.
- Expected INCONCLUSIVE: there are only five 2x tickets in 2023–25.

**EN30: second wave at a held base** (R-NEW).
- **Impulse:** EN14's frozen detector (2.5 ATR in three minutes, the future agreeing, 13:00–14:45). S0 is the impulse start, mid the impulse midpoint, R0 the impulse range.
- **Scan:** the next six completed minutes.
  - The favourable extreme updates with what has been seen.
  - Abort if the index or the future closes back through its own midpoint.
- **Base:** the first bar whose retrace from the extreme is 25–50% of R0 sets the base, at that bar's adverse extreme.
  - Invalid if a later close is beyond the base by 0.25 ATR.
- **Trigger:** a later completed minute, still within the six, that closes through the prior minute's high (call) or low (put) in both the index and the future.
- **Exits:** structure at base ∓ 0.25 ATR, plus the native premium stop, 8-minute clock and 2x rule.
- **One plan per impulse.** A no-pullback run is counted as missed.
- **Also compared** with EN14 and EN14_immediate_diag.

**EN31: reverse only after the opposite move is accepted** (R-EXIT, on the E03.2 book).
- **Arms only after** an E03.2 ticket closes at a loss whose first sale was STOP or STRUCTURE, with a second intent still free.
- **Frozen from the failed ticket's 10 pre-signal minutes:** the index range (high, low, mid) and the future range. The opposite edge is the low for a failed call and the high for a failed put.
- **Watch:** within the 10 completed minutes after the exit, buy the opposite side when all hold:
  - the index AND the future close beyond the opposite edge on two consecutive minutes;
  - no close since the exit regained the old midpoint;
  - at least one counter-move bar occurred.
- **Exits:** structure on a close back inside the edge, plus the native stop and clock.
- **E03.2's ordinary signals** stay live during the watch; whichever comes first takes the intent.
- **The reversal ignores E03.2's 5-minute re-entry cooldown;** it has its own two-minute confirmation. The bar on which the losing ticket was sold counts as the first watched minute.
- **Diagnostic `EN31_flip_diag`:** the opposite side bought immediately after every such stop.

**EN32: a different contract for the range trade** (R-NEW, plus feasibility).
- **Signals:** EN13's frozen range signals and exits, unchanged.
- **Contract:** one lot of the at-the-money strike or the first in-the-money strike for d, whichever has the smaller round-trip cost share. The cost share is 2 × half plus buy and sell fees per unit, over the ask.
- **Funding:** it must fit the same Rs 1,250 reserve with a limit of ask × 1.08, else the signal is refused.
- **Reported:** affordable share of signals, refusals, and the result against EN13.
- NOT FEASIBLE if fewer than 10 tickets result over 2023–25.

**EN33: a measured cross-index lag.**
- **Data limits:**
  - BANKNIFTY futures are not held;
  - 30-second receipt-clock windows cannot be built from minute bars.
  - That version is DATA_UNAVAILABLE.
- **Minute adaptation, on S-X1 days:** NIFTY front future (leader) → SENSEX index (follower), 13:00–15:00.
  1. **Lead-lag measurement:** the correlation of SENSEX's next-minute return with NIFTY's future return this minute, with and without SENSEX's own return this minute (partial correlation).
  2. **Event markout:** the event is |z_leader| ≥ 2 and 0 ≤ s × z_follower ≤ 0.5, with z = the 1-minute change over the standard deviation of the previous 10 changes. The follower must also move in direction s on the next minute.
     - Buy one lot of the E03.2 contract pick at the following bar.
     - Sell 4 minutes later at the bid, after fees, without funding.
     - Compare with the same markout at random minutes (40 seeds, the same count per day).
- **FAIL** at minute resolution unless:
  - the lag correlation ≥ 0.05; AND
  - the event markout is > 0 and above the random median.

**EN34: the later expiry when its economics fit.**
- **Feasibility first, on the 2026 recorded quotes** (19 sessions, seen):
  - at every minute 13:00–15:00, the cheapest whole lot of the next expiry's at-the-money or first OTM strike, by side;
  - the decision-time ask is walked through the depth for one lot, plus fees;
  - the reserve is Rs 1,250 for a call and Rs 2,500 for a put.
- **NOT FEASIBLE** if under 5% of minutes fit; the slot stops there.
- Otherwise DATA_UNAVAILABLE for a payoff test: no historical next-expiry chains are held (data request 3).

**EN35: the combination.** EN28 entry, then the EN27 scout and add, then the EN29 runner, on E03.2's signals.
- **Eligibility:** only if EN27, EN28 and EN29 each PASS development is EN35 eligible. Otherwise it is **NOT READY**.
- **Interaction diagnostic:** it is run regardless and labelled as such, to show whether:
  - the patient entry suppresses adds;
  - the scout cuts big winners;
  - the runner returns more than it saves.

### My five (EN36–EN40)

**EN36: buy gamma only when it is cheap** (R-EXIT, a filter on E03.2's signals).
- **Ratio:** at the decision, ratio = the at-the-money straddle (call close + put close at the strike nearest the index, both bars present) / (ATR10 × √(930 − minute)). The denominator is the reach rule's expected move.
- **Filter:** keep the signal only if ratio ≤ θ; a missing straddle drops it.
- **θ** is the median of this ratio over every coverage-available E03.2 signal minute in NIFTY 2023–25. It is a feature distribution, not an outcome. It is computed before the freeze by `en_lab4.theta()` and written here: **θ = 0.6924**, the median of 88 signal minutes, all of which had a straddle (`python en_lab4.py theta`). It holds on both indices because the ratio has no units.
- **Question:** does paying little for movement improve E03.2's tickets?

**EN37: the chain's flow agrees** (R-EXIT, a filter).
- **Turnover:** sum close × volume over the OTM calls (0 < K − index ≤ 4 steps) and over the OTM puts (0 < index − K ≤ 4 steps).
- **Acceleration:** the last 5 completed bars per bar, over bars i−19..i−5 per bar.
- **Filter:** keep a call only if call acceleration > put acceleration, and a put only if put acceleration > call acceleration. Each side needs at least three strikes; missing data drops the signal.
- **Question:** do buyers' contracts lead?

**EN38: the futures lead the cash** (R-EXIT, a filter).
- **Basis:** b = future close − index close.
- **Filter:** keep the signal only if d × (b_i − b_{i−5}) > 0; missing data drops it.
- **Question:** does futures demand in the trade's direction mark better tickets?

**EN39: trade only the steady window** (exam-only hypothesis).
- **Rule:** E03.2 with entries 14:00–14:30 only (start 840, end 870).
- **Where it comes from:** the 2023–25 anatomy, where 14:00–14:30 was positive in all three years (+740, +1,741, +2,847).
- **Development verdict:** none. The window was selected on that data, and 2024's 14:30 hero makes it fail there by construction.
- **Scoring:** only the exam's R-EXIT applies.

**EN40: E03.2 without the put double** (exam-only hypothesis).
- **Rule:** E03.2 with `put_mult` 1 (put tickets Rs 1,250, day reserve Rs 2,500).
- **Where it comes from:** the 2x put size came from 2024–25 in-sample (round 8), and the 2023 exam's put edge failed.
- **Question:** does doubling puts still earn on fresh data?
- **Scoring:** exam R-EXIT only (the development verdict is known: 2024's puts made the in-sample case). Family test 6 is reported beside it.

## 4. Harness repair R1 (`rec2026b.py`, not a strategy slot)

The auditor's three concrete faults in `rec2026` are fixed in a separately named file. The original `rec2026.py` and its results stay as frozen receipts.
- **The scheduled clock exit never uses an earlier quote.** It takes the first usable quote at or after m+9 up to 15:14. Otherwise the ticket is UNRESOLVED and counted at minus its premium and fees in the funded outcome.
- **Lots are sized from the decision-minute ask** with a limit of ask × 1.08, against a reserve fixed at the decision. The m+1 walked fill must be at or below that limit, else REFUSED.
- **Front future:** the dated nearest expiry on or after the day, not the most-covered contract.
- **Quote age:** a quote counts only if usable and its age (receipt − provider) is ≤ 10 seconds.
- **Unfilled and unexitable decisions** stay in the counts.

EN16-R1 and EN18-R1 are re-scored under round 3's own verdict rules, and the change against the original verdicts is reported.

## 5. Risk dial K1 (report, frozen limits from `RISK_PLAN.md`)

- **Sizes:** E03.2 at k ∈ {1, 1.5, 2, 2.5, 3}. Ticket and day reserves, lot cap and brakes are scaled by k.
- **Records:**
  - (a) NIFTY 2023–25 + N-X1, continuous;
  - (b) S-X1.
- **Limits:**
  - skeptical losing-year chance ≤ 30%;
  - skeptical 95th-percentile drawdown ≤ Rs 5,000;
  - the exact severe-fill replay loses ≤ Rs 6,250 over the record.
- **Recommended size:** the largest k that passes all three on both records. Otherwise 1.
- A size is the owner's deployment setting after forward evidence; nothing here changes it.

## 6. Verdicts (applied mechanically by `en_score4.py`)

### Stage D: development, NIFTY 2023–25
Round 3's rules, unchanged.

**R-EXIT**, all of:
- every year ≥ E03.2 on ordinary, adverse and without-best-day;
- severe sum ≥ E03.2 − 1,000;
- worst day ≥ −2,500;
- adverse sum > 0.
- Fewer than 6 moved tickets → INCONCLUSIVE.

**R-NEW**, all of:
- every year ordinary > 0;
- adverse sum > 0;
- without-best-day ≥ 0 every year;
- above the 40-seed matched-null median every year;
- worst day ≥ −2,500.
- Fewer than 10 tickets → INCONCLUSIVE.

EN30 must also beat EN14 on summed ordinary.

EN39 and EN40 get no development verdict (see above).

### Stage X: exam, N-X1 and S-X1, each its own book

**R-EXIT-X** per book, all of:
- ordinary, adverse and without-best-day ≥ E03.2 on the same book;
- severe ≥ E03.2 − 1,000;
- worst day ≥ −2,500;
- adverse > 0.
- Fewer than 3 moved tickets in a book → that book is INCONCLUSIVE.

**R-NEW-X** per book, all of:
- ordinary > 0;
- adverse > 0;
- without-best-day ≥ 0;
- above its 40-seed matched-null median;
- worst day ≥ −2,500.
- Fewer than 8 tickets in a book → INCONCLUSIVE.

### Final status per slot
- **CANDIDATE:** Stage D PASS AND Stage X PASS on both books AND the auditor's evidence minimum over development + both X1 books:
  - for an exit or execution change, ≥ 20 affected parent tickets on ≥ 10 expiries;
  - for a new setup, ≥ 30 funded tickets on ≥ 20 expiries.

  A CANDIDATE may become a disabled paper shadow. Under the owner's promotion rule it becomes main only after it beats E03.2 on the forward count.
- **EXAM-ONLY PASS:** Stage X PASS on both books without a Stage D pass (EN39, EN40, or a development failure). A forward-shadow suggestion at most; never main.
- **ONE-INDEX:** a pass on only one book. Reported; no candidate.
- Otherwise the worst applicable of FAIL, INCONCLUSIVE, NOT_ADAPTED, DATA_UNAVAILABLE, NOT FEASIBLE or NOT READY.

### The E03-family exam, again (continuity, unchanged tests)
On each X1 book:
- **test 7:** E03.2 stands. All of:
  - ordinary > 0 and adverse > 0;
  - without-best-day > 0;
  - no day below −2,500;
  - reported beside a 40-seed E03.2 random-entry null.
- **test 1:** E03.1 stands.
- **test 5:** E03.2 against E03.1.
- **test 6:** E03.1's put tickets earn more per ticket than its call tickets.

E02 and E03 are not rerun: they are superseded. If E03.2 does not stand on SENSEX, that is reported to the owner. Whether to keep SENSEX on the paper book is the owner's call.

### Anatomy (owner's rule)
For every arm, per year or book:
- results by side, by first exit and by entry window;
- tickets added, removed or changed against E03.2, with their rupee effect;
- the best and worst tickets;
- the slot diagnostics above.

## 7. Order and files

1. Write `en4_data.py`, `en_lab4.py`, `en_score4.py`, `rec2026b.py` and `en33_lag.py`. `en_lab4.synthetic()` checks the new mechanisms on synthetic tapes:
   - EN27: half first, the add, a stop that never falls;
   - EN28: fallback timing and limit, partial fills, a miss when the future turns;
   - EN26: the confirmation minute;
   - EN29: the stall minute;
   - EN31: the reversal minute and structure level, and the flip on the exit bar.

   `rec2026b.check()` proves the repairs on synthetic records:
   - a missing clock quote waits forward;
   - unresolved, stale and above-limit tickets are refused;
   - sizing is done at the decision.
2. `en4_data.py export` + `check`.
3. `en_lab4.py check` (parity and counts only). `en_lab4.theta()` writes θ into this plan.
4. `en_score4.py selftest`, using two days per cohort and two seeds, with no rupees printed.
5. `en_score4.py freeze`, then commit, then `en_score4.py score` exactly once (start receipt; refuses a second run). The hashes cover:
   - this plan;
   - the four new files;
   - every transitively imported lab, loader and fee module (`en_lab3`, `en_lab2`, `en_lab`, `en_base`, `exam2023b`, `exam2023`, `r8b_lab`, the e031, e03 and e02 labs, `data.py`, `riskdial.py`, `expiry_paper.py`, `cost_schedules.py`);
   - both data bindings.
6. Results go to `results4.json` and `anatomy4.json`; the narrative to `ANATOMY4.md`; the plain section to `docs/EXPIRY_RESEARCH_EN.md`, the README and the shared docs.
