# Round 10 implementation plan: EN111–EN125 (written before any round-10 money exists)

## 0. Scope and state

The auditor's specification is `docs/EXPIRY_RESEARCH_EN111_EN120.md`, with its review in REVIEW10.md and SOURCES10.md. This plan implements:

- the auditor's EN111–EN118 and EN120;
- EN119 as SOURCE-GATED (section 4.9);
- five of my own families, EN121–EN125 (section 5).

The owner asked for five extra slots derived from everything learned so far.

| | |
|---|---|
| Location | Research only, in Dev, in this folder |
| Unchanged | Runtime, configuration, `.env`, scheduler, broker and Production; E03.2 paper main and EN55's forward registration; round-9 files, freezes and results |
| Data | All 197 NIFTY and 63 SENSEX expiry afternoons were already studied. Every number is a development description, not a qualification |

**Problem.** Round 9 found three useful parts for the rare EN87 impulses:

- the nearer one-lot contract;
- the +150% first target;
- the 12-minute hold.

It also found many inert or harmful parts. Its chronological selection rule required 10 parents per 60 expiries. That rule was mismatched to EN87's activity of 7–10 parents per 60 expiries. Round 10 has three aims:

1. test the good parts jointly and in context;
2. test flexible actions (management, contract, range trades, learned action values, a controller);
3. use my five families to test whether the good parts carry over to the busier books, remove known bad parts, and check robustness.

## 1. Corrections carried forward from REVIEW10

- **R3: typed dependencies.** Every configuration declares `needs` explicitly, for example `("OI",)`; string spelling no longer decides. SENSEX configurations that need OI are DATA UNAVAILABLE. `test10.dependencies` runs every NIFTY configuration that does not declare OI on sampled sessions with OI removed, and requires identical ledgers. Every configuration that declares OI must change on at least one session, or it is reported as "declared, unused".
- **R4: markouts.** Any markout diagnostic shows four things separately: gross executable-price markout, explicit buy and sell charges, net hypothetical markout, and the actual matched-reference lifecycle P&L. No unsubmitted order is called a winner.
- **R7.** The COMPONENTS9 boundary statement is corrected in `../2026-11-18-expiry-en96/ADDENDUM9.md`, together with R3 and R4. No archived file is edited.
- **Selection.** The round-9 floor (10 parents in 60 expiries) stays frozen for round 9. Round 10 separates three things: mechanism anatomy, learned-model support, and nomination (sections 6–7).

## 2. Simulator (`lab10.py`)

`run_day10` is a copy of `lab9.run_day9` with hooks. With every round-10 field at its default it reproduces all 301 directly comparable round-9 configurations exactly. The three EN101 random controls need their training rate; they are checked separately in `test10.parity`.

- **Per-event profile.** `meta["prof10"]` is a tuple of Rule field replacements, applied from contract choice through the whole position life: target, hold, runner, stop and hooks. Room, day loss room, intents, parents, cooldown and wallet stay the book's.
- **Management hooks (`mg10`).** Native hard exits keep priority in every hook: stop, trail, lock, structure, target and FLAT_TIME (15:14). A dated compulsory exit always wins.
  - EN113 fast OI;
  - EN114 activity clock;
  - HOLDALL: a fixed clock that also ends runners;
  - VOLRATIO;
  - EN116 state-conditional continuation;
  - EN117 range exits;
  - EN125 OI wall.
- **Choosers.**
  - `RESP` (EN115): the response fit, plus the CONSTBETA and EQRES controls;
  - `NEAREST`: EN100's nearest affordable contract (EN100's choice when one lot is set; otherwise the most whole lots that fit, at most `max_lots × multiplier`);
  - LEGACY: `choose4`.
  - `admit9`: the legacy one-lot chooser must be able to fund an entry, which is round 9's causal eligibility.
- **Run-level stress (`stress10`, EN124).** Two settings of L7.PERT7: `sell_delay` (every sale one bar late) and `extra_fee` (one more order charge per parent, ₹23.60).
- **Fills and capacity** are unchanged:
  - completed bars, next-bar executable fill ± half-spread;
  - frozen ordinary, adverse and catastrophe scenarios;
  - 20% of bar volume as a capacity proxy.

  Reserve covers full premium plus buy charges plus one order charge per lot; `reserve ≤ room` is asserted on every position. A position open at the end of the session is unresolved and written off at entry value.

## 3. Causal features (`features10.py`, `hmm10.py`)

**Covered session.** At least 95% of window minutes (13:00–14:29) are finite for the series concerned. For HMM sessions: at least 80 of 90 valid observations. Histories update only after a session is finished.

- **Fast OI (EN113).** S_L is computed with round-8 accumulation on the current ATM ±2 basket, for L ∈ {1, 3, 5}. q_L,p is the p-th percentile of pooled |S_L| over the prior 20 covered sessions' window minutes, with at least 200 values. During a position, S_L is evaluated on the fixed entry basket (round-8 `basket(t, entry_i)`). The difference between the current basket used for the threshold and the fixed basket used in the hold is a disclosed approximation; phase zero reports both distributions during EN87 holds.
- **Extension (EN112).** X = d·(F_t − F_{t−15}) / ATR10_t.
  - rank40: the share of same-direction E03 signal minutes with X ≤ current X, over the prior 40 covered sessions, needing at least 20 prior events. This is the literal definition.
  - rank_all: the same over all prior covered sessions, needing at least 20 events. This is the pre-registered geometry revision (section 8).
  - Acceleration: d·(F_t − F_{t−3})/3 ≥ d·(F_t − F_{t−15})/15.
- **Minute observations (EN116/118/120).**
  - ER10, as in round 9;
  - M5 = (F_t − F_{t−5}) / ATR10, signed;
  - RVR = √(mean ΔF² over the last 5) / √(mean ΔF² over the last 30).
  - ER10 rank: the ECDF of the current ER10 against pooled window ER10 values of the prior 40 covered sessions (at least 200 values).
- **One-lot friction/reserve.** Taken for the nearest affordable contract at the nominal room of ₹2,500 and cash of ₹30,000.
- **OI z (EN118).** clip(d·S15 / q_REF, −3, 3).
- **v0 (EN114).** The mean of ΔF² over the 30 increments ending at the decision bar. It must be positive and the source complete.
- **Volatility-ratio reference.** The median of window-minute v over the prior 40 covered sessions.

## 4. Auditor families: exact rules and resolutions

### 4.1 EN111: contract × target × hold (18 cells)

- **Entries:** EN87's, unchanged (round-8 GATE arm).
- **Contract:** `LEGACY_UP_TO_3` (EN87) or `NEARER_ONE_LOT` (NEAREST, one lot, admit, no friction cap).
- **Target:** {+100%, +125%, +150%} on the liquidation bid.
- **Hold:** {8, 10, 12} minutes from fill.

At target, legacy multi-lot positions sell half and keep the native runner. A one-lot position cannot half-sell, so it exits completely at target (native `solo_runner` off).

**Controls:**
- nine equal-one-lot companions (LEGACY at one lot × target × hold), mapped to every cell;
- no-partial exit (`split` off) for target {1, 1.5} × hold {8, 12};
- references EN87, E03_env and E032_native.

**Comparators:** EN87 for the deployable comparison; the one-lot companion for the contract mechanism.

### 4.2 EN112: maturity changes management, never admission (18 cells)

- **Entries:** EN87's.
- **Context:**
  - EXTENSION_RANK: fresh means rank ≤ 0.5;
  - ACCELERATION: fresh means accelerating;
  - BOTH: fresh means both.
  - Mature is the valid complement. A missing feature means original management.
- **Assignment:** FRESH_GETS_ROOM or MATURE_GETS_ROOM.
- **Profile:** TARGET_ONLY (target 1.5, hold 8), HOLD_ONLY (target 1.0, hold 12) or BOTH (1.5, 12).

The profile is frozen per parent at admission. The contract stays legacy, up to three lots.

**Controls:**
- each fixed profile applied to every entry (3);
- the reversed assignment, which is already a cell;
- random assignment (18), one per cell: a seeded coin per event, at the cell's room rate among EN87 events on training dates (date index < 100), with missing features counted as no-room.

### 4.3 EN113: fast OI deterioration (12 cells)

- **Base:** EN87 entries and contract, target 1.0, hold 12.
- **Deterioration** at bar i: d·S_L(i) < −q_L,p on the fixed entry basket. It is confirmed when this holds at bars i and i−1, both at or after the fill bar and both valid. Unchanged OI is not opposition.
- **Rules at the 8-minute clock** (the first base bar with age ≥ 8):
  - if a fast input is missing, exit (TIME_MISSING): the native 8-minute cap;
  - DENY_EXTENSION exits there if deterioration is confirmed at that clock, and otherwise holds to 12.
- **EXIT_WITH_GIVEBACK** works at any bar, base or runner: exit all remaining lots when deterioration is confirmed and the liquidation bid is at most 90% of the best bid of the previous three bars (bars at or after the fill).

No flips or adds.

**Controls:**
- fixed 8 (EN87) and fixed 12;
- price-giveback alone;
- fast OI alone, for each lag and percentile (6), exiting on confirmation;
- a source-lag companion for each cell (12), with S_L one bar stale.

Fewer than 5 changed parents is ACTIVATION-LIMITED.

### 4.4 EN114: activity clock with a wall ceiling (18 cells)

- **Base:** EN87 entries, target 1.0. The native time stop is replaced.
- **Activity:** A = Σ ΔF² / v0, from the fill bar's increment onward. After at least 4 wall minutes:
  - exit (ACTIVITY) when A ≥ budget {4, 8, 12};
  - exit (WALL) when age ≥ ceiling {8, 12, 16}.
- **Scope:** BASE_ONLY (runners keep native handling) or BASE_AND_RUNNER.
- **Missing increments are not quiet:** the rule falls back to the native 8-minute exit (TIME_FALLBACK).

No reset after a partial.

**Controls:**
- fixed holds {4, 8, 12, 16} × scope (8, using HOLDALL for runner scope);
- VOLRATIO: hold = clip(round(8·√(vref/v0)), 4, 16);
- matched-average-hold controls computed at score time. For each cell, round(mean base holding minutes on training dates < 100) gives a fixed hold with the same scope.

### 4.5 EN115: contract chosen by observed response (12 cells)

- **Base:** EN87 clocks, one lot, legacy one-lot eligibility.
- **Candidates:** EN100's affordable one-lot quoted contracts of the needed kind.
- **Fit.** For each candidate, over endpoints k with k and k−3 inside the last W bars, W ∈ {20, 40, 60}:
  - x = (F_k − F_{k−3}) / ATR10_i;
  - y = (P_k − P_{k−3}) / P_i, where P is the option close (a historical-close proxy; no simultaneous quotes exist).
  - At least 15 valid endpoints and Sxx > 0 are required.
  - Ridge: β = Sxy / (Sxx + λ), λ ∈ {1, 10}; α = ȳ − βx̄ (unpenalised intercept); MAD of the residuals.
- **Score:** lot·P_i·(α + β·d − rp·MAD) − spread − buy and sell order charges, with rp ∈ {0, 1}. Highest score wins; ties go to the lower reserve, then strike, then id. No score gate. With no usable fit, the legacy one-lot is used (logged RESP_FALLBACK).

**Controls:**
- nearest one lot (same as EN111:0010), legacy one lot, min-friction one lot;
- CONSTBETA for every cell (12): β replaced by the candidates' median;
- EQRES: the response pick's reserve given to the legacy chooser, at most 3 lots.

If the response choice equals NEAREST everywhere, the cell is reported as DUPLICATE.

### 4.6 EN116: causal HMM state (8 cells)

- **Model:** diagonal-Gaussian, K ∈ {2, 3}, on (ER10, M5, RVR) window minutes of the prior 40 covered sessions.
  - Standardiser and ±4 clip fitted on training only.
  - Deterministic quantile initialisation on ER, at most 100 EM iterations, variance floor 1e-3, equal-day weights.
  - Degenerate if any state's share is below 2% or a parameter is non-finite.
- **Refit:** every {1, 5} new covered sessions.
- **Filter:** resets each day to the fitted π and updates on valid observations only. No smoothing.
- **Trend states:** pTrend sums the filtered probabilities of states whose mean ER is at least the median of the states' means.
- **Activation:** pTrend ≥ 0.6 activates, IMMEDIATE (one bar) or TWO_BAR (two consecutive valid bars); pTrend < 0.4 clears.
- **Effect at EN87 admission.**
  - Active: nearest one lot, target 1.5, hold 12.
  - From minute 8 the base holds on only while the state is active and the fee-adjusted liquidation P&L is positive; otherwise STATE_TIME.
  - Inactive, warm-up or degenerate: original EN87, logged.

**Controls:**
- the fixed high profile (EN111:0018) and EN87;
- an ER10 state matched to each refit's training activation rate (8): active when ER10 ≥ that training quantile;
- a seeded random state mapping of the same size (8).

**Diagnostic:** the next 5 minutes' |ΔF|/ATR and ER, compared between active and inactive states.

### 4.7 EN117: cost-qualified range rejection (16 cells)

- **Event, at bar i in 13:00–14:29:**
  - bands q10/q90 of the 30 futures closes F[i−31..i−2], with ER30 below 0.25 and positive width;
  - F[i−1] < q10 − buffer·ATR and F[i] inside the band gives a call (d = +1); the mirror gives a put.
  - Only the first valid rejection per side per day counts, and the two events must be at least 5 minutes apart. The book's envelope is shared.
- **Contract:** nearest affordable, one lot.
- **Gate:** the fixed fit (W 40, λ 10) of the chosen contract gives the gain lot·P·(α + β·d·dist/ATR), where dist is the distance to the target. It must exceed the coverage multiple {1, 2} × (spread + buy and sell charges). With no fit, the event is unavailable.
- **Exits:** levels frozen at admission.
  - RANGE_STRUCT: F beyond the band edge by the stop buffer {0.25, 0.5}·ATR;
  - RANGE_TARGET: midpoint, or q75 for calls and q25 for puts;
  - the native premium ladder (stop 35%, trail, lock, target +100%);
  - hold 8;
  - the index structure stop is disabled (the range stop replaces it).

  No runners or adds.
- **Buffer:** {0, 0.25}·ATR.
- **SENSEX:** the two event bars need a fresh futures bar.

**Controls:**
- cost gate off (8);
- opposite direction and seeded random direction at the same clocks, gate off, with native exits only (8 + 8).
- Cash is zero.

The round-13/32/45 range adapters have no parity port here; that control is recorded as unavailable.

### 4.8 EN118: supported net action values (12 cells × {WITH_OI, NO_OI})

- **Universe.** E03_env signal minutes plus EN117 default events (0.25, MIDPOINT, 0.5, coverage 2), deduplicated by minute. Each minute is a flat-book opportunity.
- **Actions:**

  | Action | Contract | Target | Hold | Available at |
  |---|---|---|---|---|
  | CASH | — | — | — | every opportunity |
  | LEGACY_100_8 | legacy, up to 3 lots | 1.0 | 8 | E03 minutes |
  | NEARER_100_8 | nearest one lot | 1.0 | 8 | E03 minutes |
  | NEARER_150_12 | nearest one lot | 1.5 | 12 | E03 minutes |
  | RANGE | EN117 default | EN117 default | EN117 default | range minutes |

- **Labels.** Each event-action pair is replayed as a single-event lifecycle (₹30,000 cash, ₹2,500 room) under the adverse scenario; no-fill earns 0.
  - reward r = net / 2500;
  - loss l = max(0, −net) / 2500.
- **Features:**
  - ER10;
  - extension rank (rank_all), not applicable for range events (0.5);
  - elapsed (minute − 780)/90;
  - one-lot friction/reserve;
  - OI z (WITH_OI only).

  Standardised on training data.
- **Learners.**
  - RIDGE, λ LIGHT 1 / HEAVY 10.
  - STUMP: one split per target, on training quantiles 10–90%. The minimum leaf is LIGHT 20 / HEAVY 40 distinct dates.

  Weights are equal per date. One model each for r and l per action.
- **Score:** r̂ − 0.5·l̂ − k·σ, with k ∈ {0, 1, 2}. σ is the standard deviation of r̂ − 0.5·l̂ over 200 fixed-seed date-bootstrap refits. Cash scores 0.
- **Choice:** the highest positive score among supported, applicable actions; exact ties follow the fixed id order.
- **Support:** at least 20 prior distinct dates where the action was funded, and at least 40 training dates. With no supported action, EN87's action is used if this is an EN87 event, otherwise cash.

**Walk-forward:** fits at 100, 120, 140, 160 and 180 on all prior dates, applied to the next block; dates 180–196 are the last 17.

**Controls:**
- MEAN: the unconditional action means;
- fixed profiles: E03_env, NEARER_100_8 at E03, NEARER_150_12 at E03, EN117 default;
- direction-only: a ridge forecast of d·(F_{i+8} − F_i)/ATR acting LEGACY_100_8 when positive, otherwise cash;
- EN87;
- cash.

### 4.9 EN119: urgency-dependent execution (12 cells), SOURCE-GATED

The rule needs at least 20 synchronized expiry sessions of option, futures and index quotes, fresh depth, and post-arrival trades. The available packets are the TR01 Nov 16–17 exports: one or two expiries, read-only. No download, export or recorder change is authorised. `score10` writes the source count; all 12 cells are registered SOURCE_GATED with no minute-bar substitute.

### 4.10 EN120: interpretable controller in one wallet (12 cells)

- **Profiles:**
  - EN87 (legacy/100/8 at EN87 minutes);
  - EN111 (nearest one lot/150/12 at EN87 minutes);
  - EN117 default (range minutes);
  - cash.
- **Routing features:** ER10 rank, RVR, one-lot friction/reserve of the event.
- **Labels:** single-event adverse lifecycles, as in EN118.
- **Tree.** Depth {1, 2} on training quantile thresholds (10–90%), with every leaf at least 20 distinct dates. It maximises Σ_leaves W·max(0, max_p V_p):
  - V_p is the date-weighted mean of r − 0.5·l over the leaf's events where p is available;
  - W is the leaf's date weight.

  Leaf values are buffered by 1 × the bootstrap standard deviation (200 date resamples).
- **Refit:** every {5, 20} dates from 100 on all prior dates.
- **Decision.** At an opportunity minute, the controller takes the highest buffered value among available, supported profiles, if positive; otherwise cash. An exact tie goes to EN87 if it is valid, otherwise cash. No supported profile means EN87 if valid, otherwise cash.
- **Switching margin** {0, 0.1, 0.25} (units of ₹2,500): the previously chosen profile is kept unless another one exceeds it by the margin. The state persists across days and updates at every opportunity minute. The contract and management stay frozen while inventory exists.

**Controls:**
- each fixed profile;
- a fixed-priority union (EN87 minute → EN111 profile; otherwise range → EN117);
- a past-P&L chooser in EN79 style: each day, the profile with the best cumulative adverse P&L on prior dates.

### 4.11 Learned-policy selection (EN116, EN118, EN120)

At each outer boundary s, the three inner blocks are [s−60, s−40), [s−40, s−20) and [s−20, s). Each cell is fitted on dates before the block start; EN116's causal ledgers are used as they are.

- **Score:** the per-block mean paired adverse net per scheduled expiry against EN87; the ranking uses the median over the three blocks.
- **Constraints:**
  - no halt in the 60-date ordinary or adverse inner wallet;
  - at least 5 funded parents in the inner window. This is round 10's registered floor; round 9's floor of 10 stays for round 9.
- **Choice.** The best learned cell wins only if its median strictly exceeds the best passing fixed comparator. Otherwise the fixed comparator is chosen, and failing that EN87.

The outer policies are stitched into one ₹30,000 wallet from date 100. Same-date reference wallets are shown beside it.

## 5. My families EN121–EN125 (`families10-own.json`)

| Slot | Family | Cells | Question |
|---|---|---:|---|
| EN121 | Good-part transfer: book {E03_env, E032_native, EN55_native} × contract {LEGACY, NEAREST_ONE_LOT, NEAREST_SAME_ROOM} × target {1.0, 1.5} × hold {8, 12} | 36 | Do round 9's exit and contract parts help the busier books (55–68 NIFTY parents) and SENSEX (no OI needed)? Are they a property of E03 impulses rather than of 25 EN87 trades? |
| EN122 | Native E03.2 structure: window end {14:29, 15:00} × put multiplier {1, 2} × money {NATIVE, ENVELOPE} × geometry {DEFAULT, JOINT} × gate {NONE, CALLS_ONLY} | 32 | E03.2's paper money (+₹14,275 across independent sessions) is unreachable: its wallet halts on 2024-01-18. Which structural part causes that? Can the joint geometry, or gating only the losing calls (E03.2 calls −₹569; EN87 calls +₹3,302), keep the winners without the halt? No loss reactions. |
| EN123 | One-lot protection shape: base {EN87, E03_env} × target {1.0, 1.5} × at-target {SELL_ALL, RUNNER_KEEP_0.5, RUNNER_KEEP_0.7} × stop {0.35, 0.25}; nearest one lot, hold 8 | 24 | Removes the nearer contract's bad part: its larger stop losses. A one lot cannot half-sell, so this asks whether a solo runner or a tighter stop captures spikes better. |
| EN124 | Execution stress: base {EN87, EN87_JOINT, E03_env_JOINT, E032_JOINT} × stress {ENTRY+1 bar, SELL+1 bar, FEE+1 order (₹23.60), ALL} | 16 | Do the leads survive one minute of latency and extra charges? This is real money for the partner. |
| EN125 | OI wall: EN87 entries × contract {LEGACY, NEAREST_ONE_LOT} × wall {FROZEN_AT_ENTRY, CURRENT} × trigger {AT_WALL, HALF_STEP_BEFORE} × action {EXIT_ALL, TIGHTEN_TRAIL_0.8} | 16 | New information. Is the largest same-kind OI concentration among the next four strikes ahead a level where expiry moves stall? |

**Definitions.**
- JOINT: nearest one lot, target 1.5, hold 12.
- NEAREST_SAME_ROOM: the nearest affordable contract with the most whole lots that fit the book's room, at most `max_lots × multiplier`.
- CALLS_ONLY: calls need d·S15 > q_REF; puts are ungated.
- EN122 ENVELOPE money is the round-8 envelope. NATIVE money is slots 2 with no day-loss room, no intent or parent cap, and room_mode ''. A cell at (900, 2, NATIVE, DEFAULT, NONE) must reproduce E032_native exactly, and one at (870, 1, ENVELOPE, DEFAULT, NONE) must reproduce E03_env.
- EN121 and EN122 cells equal to a reference must reproduce its ledger hash. This is a parity receipt.
- EN125 wall: among the four nearest strikes of the trade's kind strictly ahead of the index close, the largest own-kind OI. At least two must be finite. Ties go to the nearer strike. CURRENT uses bar i−1's wall. TIGHTEN raises the stop to 80% of the peak bid and then keeps trailing at 80%. It applies to all remaining lots.
- **Comparators:**
  - EN121: its own book's reference;
  - EN122: E032_native, with E03_env also shown;
  - EN123: EN87 or E03_env, plus the matched nearest-one-lot cell;
  - EN124: the same-stress EN87 cell (deployable) and its own unstressed base (cost of stress);
  - EN125: EN87, or the nearest-one-lot cell EN111:0010 for the nearer contract.
- **Needs:** EN121, EN123/E03 and EN124's non-EN87 bases run on SENSEX too, because they need no OI.

## 6. Evaluation

Configurations are run on NIFTY (and on SENSEX unless they need OI), under the ordinary, adverse and catastrophe scenarios.

**For every configuration:**
- independent-session totals;
- continuous ₹30,000 wallets from date 0 (ordinary and adverse), with brakes at 1,500/3,000/4,000 and a 50% sweep, never reset;
- by year and quarter;
- with and without the best one and best two days;
- losing dates; fees and order counts; minutes held; reserve; first-exit reasons;
- unresolved positions;
- whether the gains were reachable before a halt (independent sum versus wallet P at the first halt);
- an entry+1 adverse stress companion run (NIFTY).

**Paired comparison with the comparator:**
- descriptive day-group t, labelled uncalibrated;
- ticket comparison: matched, changed, candidate-only and reference-only;
- changed parents, giving the labels ACTIVATION-LIMITED (fewer than 5), SPARSE ECONOMIC SCREEN (5–19) or SCREENED (20 or more).

**Duplicate groups** use identical ordinary and adverse ledger hashes.

**Learned policies** have walk-forward ledgers for dates 100–196 per cell, plus the selected stitched policy (section 4.11).

**Chronological selection view.** For every family, the section 4.11 rule is applied to its cells: same floor, comparator and fixed-comparator tie. It is labelled a view, not evidence.

**Inference** is descriptive only. The calibration receipts show over-rejection; no significance claim is made.

## 7. Nomination (at most two)

A fixed configuration is a DEVELOPMENT CANDIDATE only if all of these hold on NIFTY against its primary comparator:

1. at least 20 changed parents, or at least 20 candidate parents when its entries differ;
2. adverse paired mean per expiry above 0, and the adverse paired sum without the two best days at least 0;
3. better adverse results in at least 3 of the 4 calendar years 2023–2026;
4. ordinary and adverse wallets from date 0 with no halt, and final P at least the comparator's;
5. at least half of its one-axis registered neighbours have an adverse paired mean above 0;
6. the entry+1 adverse net above the comparator's entry+1 adverse net;
7. where it runs on SENSEX: SENSEX adverse paired sum at least 0.

A learned procedure is a candidate only if its stitched policy (from date 100) satisfies all of these:
- adverse wallet with no halt and P above EN87's same-date P;
- paired adverse mean above 0 and the sum without the best two days at least 0;
- at most 2 of the 6 boundaries on fallback;
- the selection did not reduce to a fixed comparator.

Candidates are ranked by the adverse paired sum without the best two days, per expiry. At most two are nominated in `registration10/`. Each nomination is for a new prospective paper observation only; it is not qualified, promoted or deployed. Prospective floors: at least 40 covered expiries per index, at least 20 funded parents, one final review, and the owner's decision.

## 8. Phase zero: outcome-blind activation, before any round-10 P&L

`phase10.py` writes `phase0-10.json` without computing any P&L or position outcome. It uses signal clocks and nominal windows (decision+1 to +12 minutes), not actual exits.

**Checks:**
- EN112: state counts by context;
- EN113: confirmed-deterioration counts in nominal holds, and the fixed versus current basket |S_L|;
- EN114: the distribution of activity-exhaustion minutes;
- EN115: the share where the response choice differs from NEAREST, and fit availability;
- EN116: state occupancy and activation at EN87 minutes;
- EN117: event and gate-pass counts;
- EN118/EN120: support dates per action (funded excluded, since funding is an outcome; dates with an applicable event);
- EN121–EN125: contract changes, wall reach in nominal windows, SENSEX availability.

Each axis must reach both sides of its rule. If a family is inert or its variants identical, it is recorded as NOT IDENTIFIED / DUPLICATE. One documented geometry-only revision is allowed before the freeze, and the original is kept in the registry and trials ledger.

**Pre-registered revision for EN112.** If rank40 is defined for fewer than 20% of EN87 events, EXTENSION_RANK and BOTH use rank_all. No threshold revision may be based on winners or losses.

## 9. Acceptance before scoring

| Check | Requirement |
|---|---|
| `test10.parity` | hooks off: all round-9 configurations' hashes |
| `test10.references` | EN121 and EN122 reference-equal cells |
| `test10.dependencies` | OI removed: identical ledgers when OI is not declared; declared-OI cells change |
| `test10.causal` | feature, model and action prefix checks (truncated future data gives identical decisions) |
| `test10.unit` | hooks on synthetic tapes: activity exhaustion, OI confirmation, giveback, wall, range exits, response fit, HMM determinism and restart equality, learned support and fallback, profile freezing, reserve invariants, stress |
| `score10 selftest` | the pipeline on a truncated registry and calendar, printing counts only |

Then `freeze10.json` (code, data, registry and procedure hashes) is committed before `score10 score`, which runs once. After the score: `verify10.py` reconciles results through fresh-process reruns of samples from every family and every learned boundary, ledger identities, and selection re-derivation. Hash integrity, ledger identity and economic validity are reported separately.

## 10. Rollout and rollback

| | |
|---|---|
| Rollout | Documentation and research files only. Commit in Dev on `codex/production-correction-hedge-p0` and push. No deployment, configuration or Production change |
| Rollback | Revert this round's commits. Earlier rounds are untouched |
| Atlas | Unchanged: no runtime source changes |
| Shared docs | Prepended sections only, preserving other agents' unstaged edits (CRLF-safe staging) |
