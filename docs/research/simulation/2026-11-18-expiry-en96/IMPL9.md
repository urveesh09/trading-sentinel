# Round 9 implementation plan and pre-score resolutions (EN96–EN110)

Status: FROZEN WITH `freeze9.json` BEFORE ANY CANDIDATE MONEY WAS COMPUTED. Development research only, in Dev.
Starting commit `366d0b0d` (the auditor's EN96–EN105 handoff). Production stays `55b5e942`; no engine, configuration,
`.env`, scheduler, broker or Production change.

**Owner (Nov 18):**
- Implement the auditor's ten families EN96–EN105 (`docs/EXPIRY_RESEARCH_EN96_EN105.md`, `families9.json`).
- Add five slots of my own.
- Each slot is a family of variations, not one try. "Ensure correctness … try to get the best result."

## 1. Problem, files and checks

**Problem:** find out whether EN87's lesson (E03 timing plus agreeing OI) can be made more robust, more active or more
profitable, and which parts of the earlier failures can be kept. Every variation, control and neighbour is reported, and
no setting is tuned after the score.

| File | Role |
|---|---|
| `round8.py` | Path setup; round-8/round-7 modules read-only; round 8's network denial |
| `signals9.py` | Causal information series (all lookbacks/baskets), context features, SYN/BASIS scores, event and arm builders |
| `lab9.py` | `run_day9`: a hooked copy of `lab8.run_day8`, plus choosers, continuation, damage exit, staged adds and wallets |
| `families9.py` | Grid expansion (both manifests), specs, rules, per-session builders, controls and references |
| `families9-own.json` | My five families EN106–EN110 (87 configurations) |
| `search9.py` | Stage B chronological selection; EN105 composition |
| `stats9.py` | Long-group t (descriptive) and the family max-t (uncalibrated diagnostic, see section 7) |
| `score9.py` | Selftest, freeze, the one-shot score, diagnostics and registration |
| `test9.py`, `test9_unit.py` | Parity, reproduction, causality and mechanics checks |

**Checks before the freeze**, each with a receipt that must say PASS:

| Receipt | What it shows |
|---|---|
| `parity9.json` | `run_day9` with every hook off equals `run_day8` on all 25 round-8 arms, both indices, three fill levels, plus wallets (15,342 arm-days, 0 mismatches) |
| `reproduce9.json` | Every spec-built reference cell equals its archived reference session by session at all three fill levels. Covered cells: EN96 (15, 80, 20); EN97 w2/current/pooled; EN99 immediate; EN100 legacy/unbounded vs EN87 one lot; EN103 full; EN106 bridge 870/1/MATCHED; EN108 0.7/20/80; EN109 0/3/x; EN110 0.35/1.0/0.5; EN106 native GATE 80 = bridge 900/2/NATIVE. The reference threshold and gate array also equal round 8. |
| `causal9.json` | 972 prefix checks: every series, context feature, basis, synthetic forward and arm decision is unchanged when the future of the session is erased. Thresholds are unchanged when later sessions are removed. |
| `unit9.json` | 17 synthetic mechanics checks: zero vs missing OI, strict baskets, jackknife, frozen anchor, threshold warm-up, gate/veto/tilt/graded caps, arms (one active arm, TTL, information loss, ceiling, reclaim, EN104 priority/opposite/structure/unconditional), contract admission and rankings, the staged plan's add reserve and impossible splits, continuation (activation, two failures, missing, absolute cap, runner exempt, native priority), damage (consecutive count, reset), stage add consuming a buy submission, constant-rule wallet identity, registry counts |
| `selftest9.json` | The whole pipeline on a 70-session NIFTY / 30-session SENSEX prefix with a reduced registry; counts only, no money printed |

## 2. The money and the references (unchanged from round 8)

- **Matched envelope.** It is used for every EN96–EN105 cell and for EN107–EN110:
  - ₹30,000 own-cash wallet; ₹2,500 parent and day room;
  - realised losses consume the room and profits add none;
  - at most three lots, two buy submissions and two parents a day, one open position;
  - decisions 13:00–14:29;
  - the ₹1,500/3,000/4,000 drawdown brakes and the 50% sweep (`lab8.wallet` semantics, never reset).
- **References:**
  - **EN87**, the round-8 arm itself, is the reference of every family except EN100 and EN106.
  - **EN100:** EN87 at one lot.
  - **EN106:** native E03.2 (`E032_native`).
- **Archived controls**, run unchanged through `run_day9`: E03_env, EN83, EN94, the unrelated-day EN87 and EN55_native.
- **Fidelity:** BAR_LIFECYCLE. Decisions read the completed bar and fill at the next bar's open ± the declared half-spread. Adverse and catastrophe stresses as in round 8.
- **SENSEX:** OI is unavailable, so every OI-dependent SENSEX cell is DATA UNAVAILABLE with null money. Scorable on SENSEX:
  - the references;
  - EN107's SYN, BASIS and SYN_OR_BASIS cells;
  - EN108's ungated timing controls.

  Stage B needs ≥ 100 sessions, so SENSEX has full-grid results only (63 sessions).

## 3. Information measures (all families)

- **S_L** at minute i = Σ[(C_{i−L} − C_i) + (P_i − P_{i−L})] / Σ(C_{i−L} + P_{i−L}) over the basket's pairs whose four endpoints exist. Zero OI is valid; a missing endpoint drops the pair.
- **Reference representation** (L=15, ±2 strikes around the current ATM, pooled):
  - It uses round 8's exact code (a narrower basket is allowed, ≥ 3 valid pairs), so EN87 reproduces exactly.
  - Other lookbacks on this basket (EN96) use the same accumulation.
- **Every other EN97 representation** needs the full centred basket in the session's catalogue, else that minute is unavailable.
  - Pooled needs ≥ max(2, ⌈0.6·pairs⌉) valid pairs.
  - The jackknife needs ≥ 3 valid pairs and takes the median of the leave-one-pair-out S values.
  - The frozen-13:00 anchor is unavailable before 13:00.
  - The ±3 catalogue is complete on 99% of window minutes.
- **Thresholds q(series, H, p).** The p-th percentile of |x| pooled over the window minutes (13:00–14:29) of the prior H covered sessions of that series.
  - Covered means ≥ 95% finite in the window.
  - ≥ 200 values are required.
  - The current and later sessions are never read.
  - This is round 8's estimator, with unequal day weighting disclosed. It is computed for every series × H {20, 40} × p {60, 70, 80, 90}.
- **SYN** is the round-8 synthetic-forward innovation: the median of K + C − P − F over 5 near strikes, minus its prior-20-minute median. Positive means bullish.
- **BASIS** is e = (F − index) minus its prior-60-minute median (≥ 40 values). Positive means bullish.
- On SENSEX, SYN and BASIS need a futures bar with volume (stale futures are unavailable).
- **Context features:**
  - ATR A = E03's completed 10-bar ATR (`features[10][:,4]`).
  - X = d·(F_i − F_{i−15})/A.
  - ER10 = |F_i − F_{i−10}| / Σ|ΔF| over the window.
  - An invalid value means abstain.

## 4. Family rules and resolutions (the spec's text applies where not restated)

**EN96 (32).**
- Gate E03_env clocks by d·S_L > q(L, p, H).
- Controls:
  - no gate (E03_env);
  - sign only (d·S15 > 0);
  - raw crossings (EN83);
  - unrelated day (round-8 mapping: the 20th prior covered session, same minute).
- Activity-matched random retention of E03 signals:
  - Matching is per (calendar quarter, 30-minute bin) on EN87's realised kept counts.
  - 40 seeds, ordinary and adverse.
  - This control matches realised counts rather than training rates, so it is a stricter descriptive comparison.
- The common-40 warm-up companion compares every cell on the sessions where all 32 thresholds exist.

**EN97 (18).**
- Each representation has its own q80/H20.
- One-minute-lagged OI control (own threshold).
- Diagnostics at EN87 events: valid pairs, largest-pair share, ATM boundary changes, and the leave-traded-pair test. The test drops the traded strike's pair and checks whether agreement survives; it is never a trading rule.

**EN98 (12).**
- Keep EN87 events with valid X and ER10, X ≤ max (∞ = unbounded) and ER10 ≥ min.
- The unbounded/0 cell equalled EN87 on every session (no EN87 clock lacks the features).
- Sign-reversed diagnostics: keep only X > 0.5 / 1 / 2.

**EN99 (17 bar + 12 packet).**
- Every EN87 event becomes an arm, frozen at arming:
  - side;
  - ATR;
  - contract, by the legacy chooser at nominal ₹2,500/₹30,000;
  - event ask.
- One active arm: a new event while an arm is open is logged ARM_ACTIVE.
- On each later completed bar within the TTL (bar i+1 … i+TTL):
  - disarm if minute ≥ 14:30, if S ≤ q or is missing, or if the futures or contract quote is missing;
  - qualify when the style condition holds and the contract ask ≤ ceiling × event ask (above the ceiling it keeps waiting).
- Styles:
  - CONFIRM: d·(F_b − F_i) ≥ x·A.
  - RECLAIM: a pullback of the running favourable futures-close extreme ≥ y·A, then a close beyond the previous bar's futures high (call) or low (put). The same bar may complete both, as in round 8's EN89.
- The first qualifying bar submits once: limit = min(ask × 1.08, ceiling × event ask), whole lots up to three, fill at the next bar or unfilled.
- Deterministic-delay controls at +1/+3/+5.
- The packet block is SOURCE-GATED (not scored).

**EN100 (9).**
- One lot for every cell and control.
- Candidates: every contract of the signal's kind with a quote, a positive bid and 20%-bar capacity ≥ 1 lot whose full premium and charges fit at limit = min(ask × 1.08, money).
- Friction = (ask − bid)·lot + buy fee + sell fee, divided by the one-lot reserve at that limit.
- Rankings:
  - NEAREST: distance to ATM, then strike, then id.
  - MINFRIC: friction ratio, then distance, then strike, then id.
  - LEGACY: the round-8 pick, with the friction cap applied to it.
- Admission: the legacy one-lot chooser must fund an entry first.
- Unrestricted controls: NEAREST and MINFRIC without the admission rule or friction cap.

**EN101 (18).**
- At the first decision where the native TIME exit fires (≥ 8 bars from the actual fill), extend only if both hold:
  - fee-adjusted liquidation P&L > activation × the parent's original reserve;
  - the evidence holds.
- Evidence:
  - INFORMATION: d·S15 on the basket fixed at the fill > 0.5·q (that session's q).
  - PRICE: d·(F_i − F_{i−3}) > 0, and the close has not broken the adverse extreme of the previous three completed futures bars.
  - BOTH: both of the above.
- During the extension, permission is checked every completed minute:
  - two consecutive failures sell everything;
  - a missing observation sells everything;
  - the cap is absolute from the fill.
- Native protective and target exits keep priority. A native runner (after TARGET_BASE) keeps its own rules with no time cap; this is explicit in the state machine.
- Controls:
  - fixed holds of 12/16/24;
  - an equal-activity random extension at the training rate. The rate is the mean extension rate of the six cells with that cap on the first 100 sessions; random extensions hold to the cap with native exits only.

**EN102 (18).**
- On EN87 entries, after the native decision returns nothing, the chosen conjunction must hold on n consecutive minutes; a missing input resets the count. Parts of the conjunction:
  - d·S15 (fixed fill basket) < −k·q;
  - damage, one of: NONE; ENTRY (d·(F_i − F_decision) < −0.25·A); STRUCTURE (a close beyond the previous three bars' adverse extreme).
- It applies in every state including the runner, as EN94 did. Runner-state exits are reported separately.
- Controls:
  - damage only (no OI), entry or structure × n = 1/2/3;
  - round-8 EN94 (archived).

**EN103 (13).**
- Planned lots N are the most lots, up to the chooser's lots, such that the first tranche at its limit plus an add at 1.40 × the decision ask (with its own charges) fit the room and cash.
- The first tranche is max(1, ⌊N·f⌋).
- Under the three-lot cap, f = ⅓ and f = ½ give identical splits. This is a finding: the cells deduplicate and are kept in the ledger.
- The add fires once, at the first completed minute where all of these hold:
  - liquidation bid ≥ first price × (1 + gain);
  - d·S15 (fixed basket) > q; for the "entry strength" cell, also ≥ d·S15 at the fill;
  - no runner, before 14:30, no pending exit.
- The add consumes a buy submission (it counts toward the two-a-day ceiling). Its limit is min(ask × 1.08, 1.40 × decision ask).
- An add above that cap is not submitted and stays available.
- The episode's total reserve never exceeds the parent's room (asserted).
- Controls: the conservative full entry at N; native EN87.

**EN104 (18).** The EN87 core runs at q80. Arms come only from E03 events with valid S and q that fail the gate.
- Each arm freezes: side, contract, event ask, and the structure reference (the three prior futures bars' adverse extreme).
- Cancellation:
  - an immediate EN87 event at the same clock cancels the arm and trades;
  - an opposite E03 signal, a missing input, a broken structure (for STRUCTURE_HOLDS) or 14:30 cancels it.
- Entry: the earliest bar within the TTL with d·S15 > q_delay, the validity condition, and ask ≤ 1.08 × event ask.
- E03_STILL_SAME means E03's own evaluator signals the same side at that minute.
- The ₹2,500 day room, two submissions and two parents are shared with the core.
- Control: failed-gate E03 events entered unconditionally at +TTL.

**EN105 (64).** For each boundary, each gene's component is the Stage B selection, on that boundary's inner window, of:

| Gene | Selected from |
|---|---|
| Signal | EN96 ∪ EN97 |
| Context | EN98 |
| Entry | EN99 bar cells |
| Contract | EN100 |
| Management | EN101 ∪ EN102 |
| Size | EN103 staged cells |

- A fallback means the gene resolves to the reference and is logged.
- The combined rule uses that representation's series, threshold and fixed basket for context, arms and management.
- The contract gene keeps the selected chooser and friction cap, but sizes up to three lots with the shared routine.
- All 64 genotypes are scored on the inner window (selection by the same objective; ties go to fewer genes) and on the outer block.
- One-lot panel; single-gene and pair ablations.

**EN106 (my slot, 23): EN87's information on native E03.2.** This is the direct "beat E03.2" test.
- Native block, E03.2's own clocks (13:00–14:59), 2× puts and ₹5,000 day:
  - GATE: d·S15 > q_p;
  - VETO: skip only when d·S15 < −q_p; missing evidence keeps the trade;
  - TILT: every signal kept; one lot unless d·S15 > q_p;
  - each at p = 60/70/80/90 on q(REF, H20).
- Bridge block, GATE q80: window end 870/900 × put multiplier 1/2 × money MATCHED/NATIVE. It decomposes which native component interacts with the gate.
- EN55 block: GATE, VETO and TILT at q80 on EN55 native.
- Reference: E032_native.

**EN107 (16 NIFTY, 6 SENSEX-scorable): second information sources.**
- Agreement flags at E03_env clocks, each d·x > q(x, H20, p):
  - OI (S15);
  - SYN;
  - BASIS.
- Combinations: SYN, BASIS, OI∨SYN, OI∧SYN, OI∨BASIS, OI∧BASIS, SYN∨BASIS, two of three; each at p = 70/80. A missing source counts as no agreement.

**EN108 (18): looser timing, stronger information.**
- E03's efficiency 0.5/0.6/0.7 × premium ceiling 20/30 × OI gate p = 70/80/90.
- Controls: the five ungated looser-timing books.

**EN109 (12): information-graded sizing.**
- z = d·S15/q80 sets the lot cap:

  | z | Lot cap |
  |---|---|
  | < 0 | 0 |
  | [0, 1) | weak (0 or 1) |
  | [1, z_hi) | agree (1, 2 or 3) |
  | ≥ z_hi | 3 |

- z_hi = 1.5 or 2.
- Missing evidence means no trade.
- Descriptive dose-response: E03_env clocks' one-lot 8-minute action net by z bin.

**EN110 (18): exit geometry for informed parents.** EN87 entries; option stop 25/35/50%, base target 60/100/150%, runner keep 0.5/0.7. Everything else is native.

## 5. Stage B (chronological development selection)

- **Calendar:** the frozen book's 197 NIFTY sessions in date order. 196 are OI-covered; missing observations stay missing.
- **Outer blocks:** boundaries at 100, 120, 140, 160 and 180, with the last block 17 sessions long. Boundary 197 is the final selection, which is the forward nominee.
- **Inner window:** at boundary s it is sessions s−60 … s−1, three blocks of 20. Earlier sessions provide only warm-up.
- **Constraints** for a non-reference choice (all must pass):
  - ≥ 10 funded parents and activity in ≥ 2 inner blocks;
  - reconciled ledgers;
  - no halt in the continuous inner wallets, ordinary and adverse;
  - both inner wallets end positive;
  - ordinary inner net without the best two sessions ≥ 0;
  - median block paired adverse improvement vs the family reference ≥ 0.
- **Ranking:** that median (per scheduled session). Ties go to lower liquidation drawdown, then fewer genes, then the id. If nothing passes, the family reference is used, and the failed-constraint counts are logged.
- **Outer application:**
  - The selected policy runs unchanged over the next block.
  - The stitched wallet starts once at ₹30,000 on session 100, keeps cash, sweep and brakes across blocks and policy changes, and stops when its brake does. Matched references are stitched the same way.
  - Full-calendar fixed-variant wallets from session 0 are reported separately; the two are never merged.
- Independent-session results are sliced from full-calendar runs (they are path-free); every wallet is re-run.

## 6. Labels and champions (frozen rules)

- **INCONCLUSIVE — selection support:** no candidate passed in ≥ 3 of the 5 outer folds.
- **DEVELOPMENT CANDIDATE:** all of the following hold.
  - The stitched outer wallet is positive at ordinary and adverse fills, never halts, and its adverse P is ≥ the stitched reference's.
  - The outer paired adverse mean is > 0, with ≥ 10 outer parents.
  - For the most-selected cell:
    - ≥ 50% of its numeric neighbours (one adjacent step on one ordinal axis) beat the reference on the full grid (adverse);
    - its full-calendar adverse net is > 0 and its net without the best two is ≥ 0;
    - its full-calendar wallets never halt.

  EN105 has no fixed cell, so the neighbour condition does not apply to it.
- **MECHANISM ONLY:** ≥ 50% of the family's behaviourally changed cells beat the reference (adverse, full grid), with a positive median gain, but the chronological selection failed.
- **NO IMPROVEMENT:** otherwise.
- **Champions:** at most two in total, one profit/continuation and one risk/entry family. Each is the DEVELOPMENT CANDIDATE with the largest stitched adverse gain in its category.
  - The nominated configuration is that family's final-boundary selection.
  - It is written to `registration9/` as a prospective test only. The forward floors are 40 covered expiries, 20 funded parents and 100 scheduled; the primary endpoint is paired adverse net per scheduled covered expiry vs its frozen reference.
  - EN87's historical pace would not reach 20 parents in 100 expiries; this is disclosed.

## 7. Inference: descriptive only

The family max-t did not pass calibration (`calibration9.json`): exact 2^8 sign flips of eight chronological groups, max studentised, 30 correlated configurations at 35% activity, 1,000 paths per null.

| Null | Family max-t rejects at 5% | Holm over long-group t (`calibration9-holm.json`) |
|---|---|---|
| Gaussian | 5.1% | 4.5% |
| Negatively skewed | 9.7% | 8.8% |
| Heavy-tailed | 4.4% | 3.4% |
| AR(0.6) | 7.1% | 4.3% |

A planted ₹100 per active session is detected only 4–11% of the time.

**Decision, made before the score:** no significance claim. Per-cell long-group intervals, the uncalibrated family max-t and Stage B's outer blocks are descriptive only. The spec allows this ("report descriptive uncertainty and no new significance claim").

## 8. Not done, by design

- The packet block of EN99 needs ≥ 20 synchronized packet expiries; there is one.
- SENSEX OI is unavailable.
- No forward runner for round-9 nominees exists: a nominee's forward test needs request 7's per-expiry index and futures minutes and a separate registration.
- All 197 NIFTY afternoons were studied before this round; the chronological selection is a stress test, not restored out-of-sample evidence.

## 9. Rollout and rollback

- Research files in this folder plus documentation pointers.
- Commits: implementation and freeze, then results, then anatomy/docs.
- Push to `codex/production-correction-hedge-p0`. No deployment.
- Rollback: revert this folder and its doc pointers. Earlier rounds' frozen files are never edited.
