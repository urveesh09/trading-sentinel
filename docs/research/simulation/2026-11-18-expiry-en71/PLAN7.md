# Round 7 (EN71–EN85): the auditor's ten plus five of mine — frozen before any score

November 18, 2026. Research only, in Dev. The registered EN55 forward comparison, E03.2 on paper, the engine, configuration, `.env`, scheduler and Production stay unchanged (Production checkout read at `55b5e942`).

The handoff is `docs/EXPIRY_RESEARCH_EN71_EN80.md`; the audit is `docs/research/simulation/2026-11-18-expiry-review-en71/AUDIT.md`. Every history session here has been examined before, so every number this round produces is a **development screen**. Only the forward cohort registered in s.5 (EN85) can produce evidence, and no slot earns a real-money recommendation.

## 1. Prerequisite: the fill-estimator repair (outside the strategy IDs)

`pk7.py` adds estimator version 2: post-arrival evidence only, reported as LOWER, QUEUE and UPPER bounds, with the cancellation race labelled. It was recomputed on Nov 17 before this plan was written; the erratum is `../2026-11-18-expiry-en56/ERRATA-20261118b.md`.

The P0 fill count is unchanged (44 of 50) under every bound, and the conclusion stands: resting bids filled mostly on options that then fell. Version 1's results stay as published. Every passive fill in this round is labelled modelled, never confirmed.

## 2. Data, harness and envelope

**Books (unchanged from round 6).**
- NIFTY: 197 expiry afternoons, 2023-01-25 to 2026-10-27.
- SENSEX: 63 expiry afternoons, 2025-07-29 to 2026-10-08.
- No date holds both expiries, so one shared wallet runs sessions in date order exactly.

**All-session futures store (`fut7.py`, new).** Read-only from the Breeze history database.
- Each session's dated front future is the nearest expiry on or after the session with at least 300 minutes that day.
- NIFTY: 1,890 sessions with index minutes; 1,879 with a front future (2019-03-01 to 2026-10-28).
- SENSEX: 553 sessions with index minutes (from 2024-05-17); 483 with a front future (2024-09-06 to 2026-10-15). 46.4% of SENSEX afternoon future minutes from 2025 carry zero volume.

**Open interest.**
- NIFTY's sealed exports carry option OI every minute, 2023–2026. SENSEX carries none.
- Timing check against the recorder on Nov 17 (`facts7.json`): of 8,700 Breeze minute candles, 8,530 equal the recorder's OI at the bar's end. The other 170 equal an earlier value, and none equals only a later one. A candle's OI is therefore known by its bar's end.

**Quoted future spread.** The NIFTY front future's median quoted spread on Nov 17, 13:00–14:30, is 4.4 points over 5,560 fresh packets (p90 9.4). SENSEX has no measurement and uses the same number.

**Pinned normal-F&O source.**
- Taken by `git archive 55b5e942 python-engine` into `_local/pinned/`, with no `.env`, so the shipped defaults apply. These modules are identical in Dev at HEAD.
- `n11x.py` runs it in its own isolated process (`python -I`), never importing the lab or any runtime database.

**Harness.**
- `run_day7` is a hooked copy of `run_day6`. With every hook off it equals `run_day6` on 24,180 arm-days (all round-6 rule arms without the EN63/EN65/ladder hooks, both books, three fill levels), and the wallets are equal.
- The vectorised Black formula equals the lab's on 4,000 draws.
- Fill levels and charges are the frozen round-6 ones (hashed in the freeze): ordinary, adverse and catastrophe; next-bar open ± half spread; 20% of bar volume.

**The matched envelope (`ENV7`), used by every strategy primary and control unless marked native.**

| Setting | Value |
|---|---|
| Parent reserve | ₹2,500, symmetric by side, at most three lots |
| Daily room | ₹2,500. Realised losses consume it; profits add nothing. Every initial buy and add must fit the room left. |
| Parents | At most two submissions and two parents a day, one open at a time; no automatic flip |
| Window | Decisions 13:00–14:29 |
| Entry | E03's chooser (`choose4`) and capped marketable limit (chase 8%); an unaffordable side is an abstention |
| Exits | E03.2's exit ladder unchanged (35% stop, 1× target with half and runner, 8-minute clock, flat 15:14) |
| Wallet | ₹30,000 per policy; 50% of cumulative positive profit swept; brakes ₹1,500 / ₹3,000 / ₹4,000 on the trading high-water; wallet cash, swept cash and the two combined shown separately |

Native E03.2 and EN55 are also shown at their own budgets.

**Normalisation.** Every result uses today's lots (NIFTY 65, SENSEX 20) and today's charges. A historical lot and tax replay is not implemented: no dated catalogue for 2023–2025 exists in the repository. This is a stated limitation.

## 3. Statistics and verdicts (applied mechanically by `score7.py`)

**Family.** 24 strategy hypotheses: EN72, EN73, EN74, EN75, EN76, EN77, EN78, EN79, EN81, EN82, EN83 and EN84, each on NIFTY and on SENSEX.

| Cells | Status | Entered as |
|---|---|---|
| EN74 both indices, EN77 both indices, EN83 SENSEX | DATA UNAVAILABLE | p = 1 in Holm |

**Paired comparison.**
- Every hypothesis is compared with the matched control **E03_env**, expiry by expiry. Every session counts, no-trade days at zero.
- EN79 uses its own fixed-cap ledger.

**Statistics.**
- **Blocks.** Sessions are grouped into calendar-week blocks (ISO weeks).
- **Test.** A one-sided sign-flip randomisation test on the week-block sums of the paired difference, with 20,000 flips and deterministic seeds (`SEED + 10 × family index`). The same test is run against cash.
- **Interval.** A 95% percentile interval of the mean per session from a calendar-week block bootstrap (20,000 draws). It is an interval, never called a p-value.
- **Holm** adjusts across the 24 hypotheses.
- **Calibration of the test itself.** Twenty pairs of independent random-entry E03 controls (both null) report:
  - how often the test rejects at 0.05;
  - how often the interval covers zero;
  - how often a planted +₹100 per traded session is detected.
- **Side information.** Each new-information setup (EN73, EN75, EN76, EN78, EN83) also runs a 40-seed random-side null. A candidate at or below the null's 90th percentile is reported as "side information not shown" and cannot be INCOME-LIKE or TAIL-LIKE.

**Classification (development screen), fixed now.**

| Label | Conditions |
|---|---|
| **INCONCLUSIVE** | Fewer than 20 executed parents or fewer than 10 traded expiries. |
| **INCOME-LIKE** | All of: ordinary net > 0; adverse net > 0; paired interval vs E03_env entirely above 0; Holm-adjusted p ≤ 0.05; interval vs cash entirely above 0; net without the two best expiries > 0; paired difference without the candidate's two best expiries > 0; side information shown where required. |
| **TAIL-LIKE** | All of: ordinary and adverse net > 0; mean paired difference > 0; at least 3 distinct expiries each ≥ ₹2,500; side information shown where required. Always labelled as dependent on rare large winners. |
| **PROTECTION-LIKE** | Worst expiry no worse than the control's; wallet liquidation drawdown lower; return cost per session ≤ ₹25. Never called new alpha. |
| **FAIL** | Everything else. |

Stresses are reported for every primary, not used as gates:
- one extra order charge per parent (₹23.60);
- every sale one bar late (missed exits);
- for non-delay arms, the entry one bar late.

Changed parents against E03_env and the anatomy (where it won and lost) are reported for every primary.

## 4. The auditor's ten

**EN71 — tradable-information and execution frontier (diagnostic; `frontier7.py`).**
- **Reproduction first.** EN56's library is regenerated and its paired-side share reported (the audit's F2).
- **The table.** One canonical decision table keyed (index, date, bar) on two clock sets: the 5-minute grid 13:00–14:25, and E03's own causal signal bars in the window.
- **Actions per row.** Each side's frozen-chooser contract, bought at the next bar plus delay inside the capped limit and sold at the first executable bar 8 bars later. The two sides are dependent actions.
- **Forecasts.** E03's causal side, its accuracy against 50%, a random side and cash.
- **Untradeable ceilings, labelled.** C1 direction known over the hold; C2 the best executable action at a fixed clock; C3 EN56's whole-day maximum.
- **Synthetic predictors.** They pick the direction-oracle's side with probability p ∈ {0.50, 0.55, 0.60, 0.70, 0.80, 1.00}. The expected net per row is exact; 200 seeded draws give the dispersion. They run at bar delays 0, 1, 2 and 3. The Nov 17 packet latencies of 1, 3 and 10 s are a pilot.
- **Lesson.** The smallest p that pays at each clock set and delay. If even p = 1 cannot pay in an action class, retire that class.

**EN72 — marketable scout.**
- **Primary.** E03.2's entry, chooser and exits with EN55's scout only: half first (whole lots; a one-lot parent is fully sized and gets no add), the add only on its confirmation trigger, never averaging down. No patient entry, no stall runner.
- **Controls.** E03_env; EN55_env; EN72_blind_ctl (the same split, the second half bought two bars later with no favourable check).
- **Diagnostic.** EN72_e8_diag (efficiency 0.8, named diagnostic only).
- **Reports.** Split vs one-lot parents, adds, and the P&L split into matched parents (fees, price and size) and changed admissions.

**EN73 — learn the underlying on all sessions, then price the option (`prep7.py`).**
- **Model.** A ridge for the 8-minute futures log return: penalty 10, unpenalised intercept, standardised on training. Fit on the 120 prior covered sessions (every session, not only expiries), using nonoverlapping 8-minute windows with decisions at 12:00, 12:08, … 14:48, equal weight per session. The next 20 sessions give grouped calibration residuals. Fewer sessions means abstain.
- **Inputs.**
  - trailing 1-, 3-, 8- and 20-minute returns;
  - 30-minute realised volatility;
  - time-adjusted futures volume (the last 8 minutes against the median of the 10 prior sessions);
  - distance from the session VWAP;
  - position in the 09:15–09:45 opening range;
  - prior-day index return;
  - time of day.
- **Decision.**
  - Each side's frozen-chooser contract is valued at the bar's implied volatility over the residual distribution, sold at the modelled bid with both charges.
  - Trade the stronger side when the lower bound across calibration days is above zero (mean − 1.645 × sd / √20); otherwise stay in cash.
- **Controls.** Zero drift with the same volatility; an intercept-only model on all sessions; the same ridge on expiry sessions only (at least 40 prior expiries).
- **Diagnostic.** An implied-volatility shift (the median 8-minute relative change at the money over the prior 20 expiries).
- **Forecast scores are genuinely forward** (each expiry's windows never trained its model): out-of-sample MSE against the intercept, information coefficient and sign hit. The model-value error against the actual later close is also reported.

**EN74 — weighted constituent flow.** DATA UNAVAILABLE. There are no dated index weights and no second-level constituent quotes on a receipt clock.
- **Capture contract for a forward start**, still to be built:
  - the previous-close top ten constituents by dated official weight;
  - their quotes and depth with the index future and the chain, on one receipt clock;
  - at least 95% of decision windows with quote ages ≤ 2 s;
  - 60 prior covered sessions before any model.
- No bar substitute is run.

**EN75 — cross-strike synthetic forward.**
- **Primary, development layer on minute bars** (a weaker claim than the packet design):
  - **Parity interval** per strike: from K + C(bid) − P(ask) to K + C(ask) − P(bid). Bid and ask come from the frozen half-spread model on the bar close, at the 5 strikes nearest the future. Both legs must have traded in the bar; a stale leg is missing.
  - **Basis removed.** The prior 20-minute median basis to the future is subtracted.
  - **Up bar.** At least 3 strikes whose interval lies wholly above the future plus half its quoted spread plus the basis MAD. A down bar is the mirror image.
  - **Event.** The first bar of 3 successive such bars.
- **Controls.** Future-only 3-minute momentum at the same bars; the innovation 3 bars late; a one-strike (nearest) estimator.
- **Mechanism.** Does the future move toward the innovation at 1, 3 and 8 bars, or do the options come back?
- **Packet pilot (Nov 16–17).** Code and coverage only, no verdict.
- **Gate.** On SENSEX a thin future makes the basis largely stale. This is reported, not hidden.

**EN76 — the normal-F&O signal on expiry, without its capital rules.**
- **Dispatch.** The pinned dispatcher (`n11x.py`), exactly as `fno_orchestrator.py` lines 1849–1864:
  1. `evaluate_fno_mom`, with SENSEX passing NIFTY's futures frame as `rvol_bars`;
  2. then `fno_book.n11_signal(with_participation(bars, rvol_bars), …)`.
- **State.**
  - Yesterday's NIFTY daily ADX side comes from `fno_book.daily_adx` / `adx_side` (daily bars from Breeze index minutes).
  - EFF's retest state is the module's own, evaluated on every closed 5-minute bar in date order, in that process only.
  - 21 calendar days of 5-minute front-future frames are used.
  - Regime is `REGIME_1_NORMAL` (the VIX crisis label is not rebuilt).
- **Signals.** Each fires 15 s after its bar closes and maps to the matched envelope and the common E03 exits.
- **Morning signals** (09:45–12:00) are reported as signal-only futures moves: the tapes hold the chain from 12:00, so morning options are untestable.
- **Control.** The same signal on 450 normal NIFTY afternoons (2025-01-01 to 2026-10-28, evaluated from 12:30, which cannot change any 13:00+ signal), reported as signal-only 8-minute futures moves: no option quotes exist for those days.
- The source and dispatch manifest is recorded: the pinned tree hash, settings, the branch that fired, and the reject reasons.

**EN77 — news after actual receipt.** DATA UNAVAILABLE. There is no prospective, timestamped corpus with our receipt times.
- **Capture contract**, still to be built: RBI decisions and top-ten-weight results releases, with the original document, the first public timestamp, our first successful receipt time and revisions.
- At least 20 eligible releases on 10 expiries are needed before a mechanism review.

**EN78 — basis repair (development layer on minute bars).**
- **Basis.** Future − index. The prior 60-minute median and MAD are subtracted.
- **Event.** The first of 3 successive bars with the innovation beyond both 3 MAD and 3 quoted future spreads. One event per excursion, re-armed once back inside 1 MAD.
- **Primary.** Within 3 bars of the event, wait for a completed bar in which the cash moves toward the future while the future keeps at least half the innovation. Then buy in the innovation's direction.
- **Controls.** The future's lead alone (at the event, the same direction); unconditional basis reversion (at the event, the opposite direction); matched own-future momentum at the primary's bars.
- **Repair decomposition.** The 8-bar cash move, future move, repair, and the cash share of the repair.
- **SENSEX** counts only bars where the future traded.

**EN79 — cash-aware selector (`alloc7.py`).**
- **Experts.** CASH, E03_env, EN72, and EN60's CUSUM setup with both sides retained (EN60_env, its own 15-minute hold). All use the matched envelope.
- **Selection.** One expert per session by the highest log weight; ties go to CASH, then the listed order. Weights start equal.
- **Update.** After each session, each log weight moves by 0.1 × clip(net / 2,500, −1, 1) from its fixed-cap shadow ledger. Log-weight spreads are capped at 10.
- **Controls.** Cash; each fixed expert; round-robin; the retrospective best fixed expert (labelled UNTRADEABLE).
- **Reports.** Immutable pre-session receipts; the wallet run at the chosen expert's live cash and brake; missed recovery winners (CASH chosen while the best fixed expert made ≥ ₹1,250).

**EN80 — one shared wallet (engine; `alloc7.py`).**
- **Engine.** Both indices' sessions in date order, one wallet, the same brakes and sweep, one ₹2,500 day room. Admissions are recomputed at the current cash and brake state.
- **Checks.** Cash conservation, reservations within room, and restart equivalence (a run stopped halfway and resumed from its state equals the uninterrupted run).
- **Scenarios.** Calendar-week block resampling (2, 4 and 8 weeks; both indices and empty weeks kept; 1,000 one-year paths; ordinary and adverse on identical calendars). These are conditional scenarios, not probabilities.
- **Combined policy, fixed now.** Only EN72–EN78 variants that independently pass their forward criteria may enter. The earliest eligible signal wins; slot number breaks ties. One open position, the same ₹2,500 room, and a new combined forward cohort.
- **Until then.** No candidate is eligible, so the engine runs only a labelled fixture (E03_env on both indices).

## 5. My five

**EN81 — is E03 a bar early?** Round 6's +1-bar perturbation made EN55's wallet +₹23,957, which is seen-data motivated. The mechanism question is whether E03's pullback entry buys the bottom of a one-minute dip that keeps falling.
- **Primary.** E03_env with the entry order one bar later (the capped limit still binds, so a rise past it is a refusal).
- **Diagnostics.** 2 and 3 bars; the native budget with 1 bar.
- **Control.** E03_env.
- EN71's E03-clock delay curve is the mechanism view.

**EN82 — the normal book's trend regime on expiry.**
- **Rule.** E03_env only on sessions where yesterday's NIFTY daily ADX(14) ≥ 30. This is the pinned engine's formula and N11's shipped threshold, not tuned here. SENSEX reads NIFTY's ADX, as N11 does.
- **Diagnostic.** ADX ≥ 25.
- **Control.** ADX < 30 only.
- It isolates N11's gate from N11's signal (EN76).

**EN83 — option writers' open-interest flow (NIFTY).**
- **Score.** S = (Δput OI − Δcall OI) over 15 bars at the five strikes around the index, divided by their starting OI. Put writing reads as up.
- **Signal.** A fresh crossing of the 80th percentile of |S| over the previous 20 covered expiries.
- **Controls.** The 15-minute futures return sign at the same bars (does OI add to price?); the contrarian side (diagnostic); the random-side null.
- **Data note.** OI was verified to be known by its bar's end (s.2).

**EN84 — participation.**
- **Rule.** E03_env only when the last closed 5-minute NIFTY future bar's time-adjusted volume is ≥ 1.2. This is the pinned `_rvol_time_adjusted`, 10-day lookback, N11's shipped FNO_MIN_RVOL. SENSEX reads NIFTY's participation, as the shipped signal does.
- **Control.** Below 1.2 only.

**EN85 — the forward cohort machine (`fwd7.py`).** The stepping stone.
- **Ledger.** One append-only ledger (`forward7/ledger.jsonl`) for every registered arm.
- **Sessions.** Each new expiry from SENSEX 2026-11-19 and NIFTY 2026-11-23 is scored exactly once, with the frozen code. The runner refuses changed code. The tape is built by the frozen builder from Breeze rows.
- **MISSING.** Any session lacking index, front future or chain is MISSING, with the missing inputs named; never a zero day.
- **Review and continuation.** Scheduled review at 40 eligible expiries per index, continuing to 100 if support is short.
- **Registration.** One `registration/<slot>.json` per slot, written by the freeze, with rule dumps and hashes.
- **Tests.**
  - A dry run on the last 8 NIFTY and 4 SENSEX historical expiries plus one known-MISSING session (NIFTY Nov 17: no Breeze future), flagged DRY_RUN and never counted.
  - An idempotence check: a rerun appends nothing, and recomputation is identical.
  - A power table: expected expiries to the support floor per arm, from development activity.

## 6. Facts seen before the freeze (counts only; no rupees)

**Checks.**

| Check | Result |
|---|---|
| Parity with round 6's loop | 24,180 arm-days |
| Causal checks | 222 decisions unchanged with later bars erased and later sessions corrupted |
| Mechanics | Loss room, two parents, delay, blind add, gates, extra fee, missed exits |
| Known signals | The ridge recovers a planted drift; SYNF75 fires on a planted option lead |

**Matched-envelope activity, ordinary fills.**

| Arm | NIFTY parents | NIFTY expiries | SENSEX parents | SENSEX expiries |
|---|---|---|---|---|
| E03_env | 55 | 48 | 7 | 7 |
| EN72 | 56 | 48 | 7 | 7 |
| EN81 | 41 (of 59 intents) | 36 | 5 | 5 |

SENSEX's E03-derived cells will therefore be INCONCLUSIVE on support.

**Setup counts in the window (bars with a signal / days).**

| Setup | NIFTY | SENSEX |
|---|---|---|
| SYNF75 | 270 / 129 | 279 / 63 |
| BASIS78 events entered | 20 / 19 | 6 / 6 |
| OI83 | 285 / 128 | — |
| RIDGE73 (bars with a positive lower bound) | 2,240 / 99 | 740 / 52 |
| RIDGE73 zero-drift control | 1,441 / 33 | 86 / 3 |

- RIDGE73 had a model on every NIFTY and SENSEX book day; the expiry-only control on 157 NIFTY and 23 SENSEX days.
- SENSEX's SYNF75 fires on every session, consistent with a stale future.

**N11 counts.** The isolated run (`n11-signals.json`, pinned tree `be31474ce7d1…`) covers 552 sessions with none missing (the warm-up is at least 11 sessions). Signals in the 13:00–14:29 window:

| Sessions | Signals | Days | Branches | Days with ADX ≥ 30 |
|---|---|---|---|---|
| NIFTY expiry | 64 | 35 | TPB_LOW 40, TPB 12, EFF 7, SHIPPED 3, OR20 2 | 38 of 197 |
| SENSEX expiry | 23 | 12 | TPB_LOW 16, TPB 4, EFF 3 | 8 of 63 |
| NIFTY normal afternoons | 56 | — | — | 46 of 292 |

- Morning signals, 09:45–12:00: 42 NIFTY and 17 SENSEX.
- The participation reading is known on every window bar.

## 7. Files and commands

`fut7.py`, `n11x.py`, `prep7.py`, `en_lab7.py`, `frontier7.py`, `alloc7.py`, `pk7.py`, `check7.py`, `score7.py`, `fwd7.py`; `registration/`; `forward7/` (created by the first forward run).

```
& 'C:\Users\Urveesh\sentinel-ml-venv\Scripts\python.exe' -B pk7.py                 # estimator v2 + EN58 erratum
& 'C:\Users\Urveesh\sentinel-ml-venv\Scripts\python.exe' -I -B n11x.py n11-days.json n11-signals.json
& 'C:\Users\Urveesh\sentinel-ml-venv\Scripts\python.exe' -B check7.py
& 'C:\Users\Urveesh\sentinel-ml-venv\Scripts\python.exe' -B score7.py selftest | freeze | score
& 'C:\Users\Urveesh\sentinel-ml-venv\Scripts\python.exe' -B fwd7.py dryrun | status | run
```
