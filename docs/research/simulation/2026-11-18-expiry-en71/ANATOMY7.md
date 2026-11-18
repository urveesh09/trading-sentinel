# Round 7 (EN71–EN85): where each slot won and lost

Scored once on Nov 18, 2026 by `score7.py`, under `PLAN7.md` (frozen at `47a29999` before any score). Every number is a **development screen** on sessions examined before.
- All tables: `ANATOMY7-tables.md`. Machine-readable: `results7.json` and `anatomy7.json`.
- Post-score reporting fixes, labelled as such: `post7.py` → `post7-fixes.json`.
- Unless marked otherwise, all rupees are after charges, at today's lots and charges, with fixed-cap independent sessions.
- The matched envelope: ₹2,500 a parent and ₹2,500 day room, at most two parents, decisions 13:00–14:29.

## Bottom line

**No strategy qualifies.**
- No hypothesis is INCOME-LIKE or TAIL-LIKE.
- All 19 testable Holm-adjusted p-values are 1.0 (the five unavailable cells enter at 1 by rule).
- E03.2 stays the paper main and EN55 the registered forward candidate, both unchanged.

**One genuinely new piece of information appeared**, but it does not pay yet:
- On NIFTY, two new information sources pick the right side better than chance: the option-implied forward (EN75) and option writers' OI flow (EN83).
  - Each beat the 90th percentile of its own 40-seed random-side null: +₹5,844 against p90 +₹1,077, and +₹4,722 against p90 +₹76.
  - The OI side beat the plain price side at the same bars in every year (2023–2026).
- But they are mostly **the same information**: same side on 81 of the 93 sessions where both fired; per-session net correlation 0.61.
- And it **does not convert into reliable profit**:
  - Both lose at adverse fills.
  - Both lose without their two best days. They share the same best day, Sep 12, 2024 (+₹11,209 / +₹12,059).
  - Their after-fee paired intervals against E03 and against cash include zero.

**The hurdle is now measured (EN71).**
- To pay, a forecast must pick the right side about 61–70% of the time at an arbitrary 5-minute clock.
- A fixed 8-minute hold at bar fills needs ~0.70; one bar of latency raises that to ~0.70–0.80.
- E03's own clocks are different: buying either side there averages +₹55 a decision with a coin toss. But that clock value vanishes after one bar of delay.
- E03's causal side was right 57.1% of the time at a fixed hold (63 decisions).

**Three protection-like results on NIFTY**: EN72 scout, EN81 one bar later, EN84 participation.
- They are mechanically labelled: lower drawdown at a return cost of at most ₹25 a session, or a gain with no credible interval.
- None is new alpha.
- EN81 is the only one with more money (+₹6,393 against +₹3,006). Its delay curve is a single spike: 2 and 3 bars late are worse than on time, and the native-budget version made less than native E03.2. That reads as noise or a filter effect, not a mechanism.

## The prerequisite: the fill-estimator repair

Estimator version 2 (`pk7.py`; erratum `../2026-11-18-expiry-en56/ERRATA-20261118b.md`):
- Every fill now needs post-arrival evidence, reported as LOWER, QUEUE and UPPER bounds.
- On Nov 17, P0's 44/50 fills hold under every bound, and its net is unchanged (−₹1,658).
  - 16 fill times move later, by a median 1.4 s.
  - The audit's 4 unsupported witnesses all fill later on genuine post-arrival trades.
- The round-6 conclusion stands: resting bids filled mostly on falling options.

## EN71 — the information and execution frontier (diagnostic)

**Reproduction.**
- EN56's library reproduces: 315,200 NIFTY rows, mean −₹79.49 at ₹2,500 and 8 minutes.
- The audit's F2 also reproduces: 89.3% of filled rows sit in opposite-side pairs.
  - The frozen run printed 0.8% because the reporting function pooled bar indices across sessions.
  - `post7.py` corrects it per session: 22,716 of 25,440.

**Canonical table.** 3,546 grid rows and 77 E03 rows on NIFTY. At delay 0 the E03-chooser action was filled 5,679 times, unaffordable 1,339 times, not filled 74 times.

| NIFTY, expected net per decision | p .50 | .55 | .60 | .70 | .80 | 1.00 |
|---|---:|---:|---:|---:|---:|---:|
| 5-minute grid, next bar | −68 | −37 | −5 | +58 | +122 | +248 |
| grid, 1 bar late | −62 | −46 | −29 | +4 | +37 | +102 |
| grid, 3 bars late | −51 | −39 | −26 | 0 | +26 | +77 |
| E03's clocks, next bar | +55 | +100 | +144 | +233 | +322 | +500 |
| E03's clocks, 1 bar late | −32 | −11 | +10 | +51 | +93 | +177 |

**What it says.**
- **An arbitrary clock.** A forecast must be right about 61% of the time just to break even with next-bar fills, and about 70% with one bar of latency.
  - The useless predictor (p = 0.5) is negative in every one of 200 seeded draws (share positive 0.0).
  - The oracle is hugely positive. So the harness separates them.
- **E03's clocks carry value by themselves.** Even a coin-toss side earns there at the next bar. But one bar later the same coin loses, so the value is the first minute's move.
  - E03's real side was right 57.1% of the time, earning +₹34 an expiry [−41, +120] against a random side's +₹20.5 at a fixed hold.
- **Ceilings (untradeable).**
  - Knowing the direction at fixed strike and clock is worth +₹4,150 an expiry on the grid.
  - The best action at a fixed clock is worth +₹6,250.
  - Per oracle action: gross +₹342, spread costs ₹16, fees ₹52.
- **Direction is the binding limit.** Spread and fees are a hurdle of about ₹70 an action, but the gap between a coin and a 70% forecast is far larger. No action class is retired: even the direction-only oracle pays everywhere.
- **SENSEX** looks similar on the grid (break-even p ≈ 0.6 at the next bar). Its E03-clock rows (14) are too few to read.
- **Nov 17 packet latency pilot** (33 actions, one day, no verdict): a coin-toss side made +₹56 at 1 s and lost −₹47 at 10 s.

## EN72 — marketable scout (PROTECTION-LIKE on NIFTY; SENSEX INCONCLUSIVE)

**Result.** NIFTY −₹91 (adverse +₹1,033) against E03_env +₹3,006. Paired −₹15.7 a session [−39.8, +6.6].

**Mechanics.**
- 56 parents: 51 split, 5 one-lot (indivisible, fully sized).
- 25 adds were bought on confirmation.
- On the 55 matched parents the scout earned ₹2,545 less, of which ₹495 was extra fees. Changed admissions: one extra parent, −₹552.

**Where it won and lost.**
- It cut the worst expiry (−₹992 against −₹1,464) and the liquidation drawdown (3,895 against 3,939).
- It gave up winners: winners start at half size, and the add comes late.
- Puts +₹2,708 and calls −₹2,799. Stops −₹7,118 on 13 tickets.

**Stresses.**
- An extra order charge costs it ₹1,322, because the add is an extra order.
- Missed exits leave +₹3,305.

**Lesson.** Without the patient entry, the scout alone is protection at a price, not an improvement. Round 6's scout-only wallet result does not survive as a fixed-cap edge in the matched envelope.

## EN73 — ridge on all sessions, priced through the option (FAIL, both indices)

**Result.** NIFTY −₹17,094 on 171 parents; SENSEX −₹5,277.

**Forecast, genuinely forward** (each expiry never trained its model):
- NIFTY: out-of-sample MSE 1.0037× the intercept's (worse); information coefficient 0.068; sign right 53.2%.
- SENSEX: 0.9955×, 0.116, 54.7%. The stale future is suspected.

**Conversion failure.**
- The value model over-predicted the 8-minute option value by a median 9.4% (mean absolute error 37%).
- Its positive lower bounds were model optimism, so it bought far too often.

**Controls.**
- Zero drift −₹1,979; intercept-only −₹10,551; expiry-only −₹5,297.
- So the drift forecast made it worse than no forecast at all.
- Random-side null median −₹20,974, p90 −₹10,574: no side information.

**Where it won and lost.** 25 stops −₹20,014 and 22 structure exits −₹12,154; 9 doubles +₹14,808.

**Lesson.** Ten price features on 120 ordinary sessions forecast 8-minute futures moves no better than an average. Mapping a weak forecast through an option model adds error, not edge.

## EN74 — constituent flow: DATA UNAVAILABLE

No dated index weights and no second-level constituent quotes exist, so no bar substitute was run. The capture contract is in `registration/EN74.json`.

## EN75 — option-implied forward (NIFTY FAIL, with side information shown; SENSEX FAIL)

**Result.**
- NIFTY +₹5,844 on 177 parents over 119 expiries; adverse −₹1,423; catastrophe −₹25,510.
- Paired against E03_env +₹14.4 a session [−118, +180]; against cash [−98, +191].

**Side information.** Random-side null median −₹13,590, p90 +₹1,077. The candidate is above p90.

**Controls.**
- Future-only momentum at the same bars: −₹11,328. So the synthetic forward's side beats the future's own recent move by ₹17,000.
- 3 bars late: +₹5,180, so the information lasts minutes, not seconds.
- One strike: +₹6,509.

**Mechanism (1,156 NIFTY events).**
- The future moved toward the innovation 56.2% of the time within 1 bar and 55.6% within 3 bars (+1.6 points in 3 bars, +2.5 in 8).
- The options themselves came back 62% of the time.
- So the option market mildly leads, but 56% is below the ~61% the grid hurdle needs.

**Where it won and lost.**
- Calls +₹5,822, puts +₹23.
- 5 doubles +₹23,687 and 120 time exits +₹14,412; 35 stops −₹25,727.
- By year: 2023 −₹2,934, 2024 +₹11,068, 2025 +₹3,622, 2026 −₹5,911. Without the best two expiries: −₹10,172.

**SENSEX −₹19,200.** Its future moved "toward" 65.7% while the cash index moved against (−5.9 points): a stale future catching up, not information.

**Nov 17 packet pilot.** 99.4% of seconds had at least 3 fresh strike pairs; 99 events; the future moved toward 62% of them at 30 s.

## EN76 — the normal-F&O signal on expiry (NIFTY FAIL; SENSEX INCONCLUSIVE)

**Result.** NIFTY −₹6,024 on 36 parents (null median −₹6,595, p90 −₹4,136); SENSEX +₹3,283 on 15.

**What fired.** Mostly the low-ADX put pullback: TPB_LOW 40 of 64 NIFTY window signals. ADX ≥ 30 held on only 38 of 197 NIFTY expiries.

**The signal itself, before any option** (8-minute futures move):

| Sessions | Move | Right |
|---|---|---|
| NIFTY expiry | +0.97 points | 48.4% |
| NIFTY normal afternoons (56 signals) | +1.48 points | 55.4% |
| NIFTY morning (09:45–12:00) | −1.91 points | — |
| SENSEX expiry | +31.6 points | 73.9% (23 signals; the thin future again) |

**Lesson.** The signal's direction is roughly coin-like on expiry afternoons and modestly better on normal afternoons. Expiry underperformance is a direction problem first; affordability is second. The pinned source ran in isolation with no parity gap (the Production and Dev modules are identical).

## EN77 — news after receipt: DATA UNAVAILABLE

No prospective timestamped corpus exists. The capture contract is in `registration/EN77.json`.

## EN78 — basis repair (INCONCLUSIVE, both indices)

**Result.** NIFTY −₹1,612 on 14 parents.

**Mechanism (177 events through the day).**
- The gap closed within 8 bars on 57%, by +5.9 points.
- The cash index did most of the repairing: median cash share 1.01; cash-led on 59%.
- So the future does lead the cash. But in the window, too few events reach an option, and those lost.

**Controls.**
- Future lead alone −₹5,296; basis reversion −₹1,323; momentum −₹2,210.
- SENSEX: 6 parents.

**Lesson.** The lead is real (as EN38 found) and finished within a minute or two. At three quoted future spreads (13.2 points) it is rare and too small for an option.

## EN79 — cash-aware selector (INCONCLUSIVE)

**NIFTY.**
- It chose cash on 133 sessions and E03_env on 64, for +₹1,664 on 15 parents.
- Compare E03_env +₹3,006 and round-robin −₹12,415. The best fixed expert in hindsight was E03_env.
- Its wallet stayed positive (P +₹2,176, swept ₹2,301, liquidation drawdown 2,634), where E03_env's wallet ended −₹3,445.
- It missed 5 recovery winners of at least ₹1,250.

**SENSEX.** It chose E03_env 53 times, for +₹3,369.

**Lesson.** It learned "mostly cash" on NIFTY. That is protection, not smart trading, and too few parents to judge.

## EN80 — one shared wallet (engine checks; fixture only)

**Checks.**
- Restart equivalence holds (260 sessions split at 130: identical).
- Cash is conserved, and no session exceeded its room.

**Fixture: E03_env on both indices.**
- Ordinary P −₹2,436.
- Adverse halts on 2025-02-13.

**Block scenarios (2, 4, 8 weeks; 1,000 one-year paths).**
- No path reaches the ₹4,000 halt: at the ₹3,000 brake the quarter-size room buys almost nothing, so losses stop first.
- The median one-year P is +₹875 to +₹1,712; the 5th percentile is −₹2,871 to −₹3,197.

**No candidate is eligible**, so no combined book is formed.

## EN81 (mine) — one bar later (PROTECTION-LIKE on NIFTY; SENSEX INCONCLUSIVE)

**Result.**
- NIFTY +₹6,393 (adverse +₹4,795) on 41 parents against E03_env +₹3,006.
- Paired +₹17.2 [−35.5, +76.8], p 0.288.
- Wallet +₹5,021, never halted.

**But the curve is a spike.** Two bars late +₹338; three bars late +₹1,339. The native budget one bar late made +₹4,879 against native E03.2's +₹14,275.

**Mechanism.** 18 of 59 intents became no trade at the later bar: the capped limit, or too small a fill, refused them. The delay acts as a filter against chasing. EN71 shows the plain fixed-hold value at E03's clocks falls with delay.

**Where it won.** Puts +₹6,736 and 6 doubles +₹11,062. 2025 +₹10,862; other years negative or flat.

**Lesson.** Not a robust improvement. If anything, "do not chase a jump" is the candidate idea, and it would need its own registration.

## EN82 (mine) — the normal book's ADX regime on E03 (INCONCLUSIVE)

**NIFTY.**
- ADX ≥ 30 days: −₹1,425 on 11 parents.
- **ADX < 30 days: +₹4,432 on 44.** The trend regime that helps the normal book does not help E03 on expiry. If anything it points the other way.

**SENSEX: a frozen-code routing defect.** The gate was filled only from NIFTY records, so SENSEX found no ADX and never traded.
- `post7.py` reran the frozen arms with SENSEX reading NIFTY's ADX, as the plan says.
- 1 parent, −₹142; the inverse control made +₹5,309 on 6. The verdict is unchanged (INCONCLUSIVE).

## EN83 (mine) — option writers' OI flow (NIFTY FAIL, with side information shown)

**Result.**
- +₹4,722 on 167 parents over 117 expiries; adverse −₹3,886.
- Paired +₹8.7 [−139, +193].
- Random-side null median −₹11,491, p90 +₹76.

**Controls.**
- The 15-minute price sign at the same bars −₹1,920. The OI side beat it in every year: +₹345, +₹2,021, +₹2,946, +₹1,329.
- The contrarian side −₹21,128.
- The OI side agrees with price 88% of the time. Its value is in the 12% where it disagrees.

**Data.** OI was verified on Nov 17 to be known at each bar's end.

**Where it won and lost.**
- 10 doubles +₹27,275 and 100 time exits +₹16,407; 49 stops −₹36,888.
- Best day Sep 12, 2024 (+₹12,059), the same as EN75's. Without the best two: −₹11,557.

**Lesson.** Positioning flow in the option market carries some directional information that price does not. It overlaps EN75's synthetic forward. It is too weak (well below the ~61–70% hurdle) to pay through cheap OTM 8-minute tickets after fees, at adverse fills.

## EN84 (mine) — participation gate (PROTECTION-LIKE on NIFTY; SENSEX INCONCLUSIVE)

- NIFTY +₹2,694 on 33 parents (inverse +₹663 on 23) against E03_env +₹3,006.
- High-participation entries do a little better per ticket, but the split is small.
- Worst expiry −₹1,114 against −₹1,464; liquidation drawdown 3,043 against 3,939.
- Protection at a small cost, not an edge.

## EN85 (mine) — the forward machine (built and tested)

- `fwd7.py` scores each new expiry once into `forward7/ledger.jsonl` with the frozen code. It refuses changed code and records MISSING sessions with the missing inputs.
- **Dry run** (`fwd-dryrun.json`), on the last 8 NIFTY and 4 SENSEX expiries plus NIFTY Nov 17:
  - Nov 17 was recorded MISSING: index 0/210 and front-future 0/210 minutes in Breeze.
  - The 12 eligible sessions scored 34 arms each.
  - A rerun appended nothing, and the recomputation was identical.
  - 72 arm-days match the scorer's own day results exactly.
- **Planning numbers from development activity:**
  - E03_env needs about 72 NIFTY expiries to reach 20 parents over 10 traded expiries, and 180 on SENSEX (beyond the 100-expiry limit).
  - EN75 and EN83 need about 23 NIFTY expiries. They are the most active.
  - EN55 needs about 58 NIFTY expiries.

## Calibration of the test (the auditor's request)

- Twenty pairs of independent random-entry controls (both null): the sign-flip test rejected at 0.05 once (5%), and the week-block interval covered zero 19 times (95%). The machinery is honest.
- But a planted +₹100 per traded session was detected only 3 times in 20 (15% power) over 197 expiries.
- **An edge of that size is usually invisible in this history.** In 40 forward expiries it is hopeless. Only a large edge can be confirmed quickly.

## What carries forward

- **Registrations.** Every primary and control is registered (`registration/`) for the forward cohort from SENSEX Nov 19 and NIFTY Nov 23. The forward machine is ready; it needs the per-expiry Breeze downloads (request 7).
- **EN55's registered comparison is unchanged.**
- **The one new lead worth more work** is option-market flow (EN75/EN83). The binding limit is converting about 56% direction into money:
  - a cheaper action class;
  - a longer hold, where the 2.5-point 8-bar drift could grow;
  - or a stricter event threshold.
  - Any of these is a new registration, on new expiries only.
- **Limits.**
  - Today's lots and charges throughout; no historical lot or tax replay.
  - No VIX crisis label for N11.
  - SENSEX futures are 46% stale minutes.
  - Packet evidence is one session.
  - Every fill is modelled.
