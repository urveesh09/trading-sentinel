# EN01–EN05: improvements to E03.2, the main expiry ticket (plan frozen before scoring)

Written November 17, 2026, after the recommender agent's audit of Production. The audit found:
- E03.2 has opened no paper tickets in its four live sessions (Nov 5 SENSEX, Nov 9 NIFTY, Nov 12 SENSEX,
  Nov 17 NIFTY). Its efficiency gate rejected 404 of 480 window checks.
- Two exit defects: a double-used bid at 15:14, and a stuck leg that blocks the next expiry.
- A December 7 close-time question.

The owner's order: five slots, EN01 to EN05. Each slot is an improvement on the E03.2 baseline, tested on
our data.

## Data, and what it can and cannot show

| Source | Expiry days | Status |
|---|---|---|
| Breeze minute chains, NIFTY 2024 + 2025 | 105 | **SEEN.** E03.2 was fitted here, so it is development data only. |
| Breeze minute chains, NIFTY 2023 | 48 | **Protected exam** (`EXAM_E03_FAMILY.md`). Never read here. It is opened only on the owner's word, after this plan's arms are frozen. |
| Breeze NIFTY 2019–2022, SENSEX 2024–2026, NIFTY 2026 | — | **No same-day-expiry afternoon option rows** (census `census.json`). They cannot replay E03.2. |
| Production 10-second recordings, Oct 6 – Nov 5 2026 | 10 (5 NIFTY, 5 SENSEX) | Real 5-level books (copy in `2026-11-05-fno-expiry-followup/_local`). Used for an engine replay sanity check only: about two tickets, far too few for a decision. |
| Forward-panel quote archive, Sep 10 – Nov 13 2026 | 20 | One snapshot a minute. Used here for a descriptive SENSEX check only. |

**Disclosure before scoring:**
- I listed E03.2's 39 lab tickets (sides, times, exit reasons). EN05 was motivated by seeing put tickets
  sold at the 8-minute clock while in profit.
- EN04's 3x put size already passed the frozen risk limits after the fact in round 8 (`putdial.json`).
  That is not new evidence; EN04 re-tests it with neighbours.
- EN03's put gate has not been looked at.

## The five slots

**EN01: honest exits (engine, Dev).** These are the audit's items 1 to 3.
- One exit per quote snapshot: a latched exit and the 15:14 flat sale never both fill on one displayed bid.
- Every sale gets its own notice.
- A leg still open after its session is valued at settlement: intrinsic at our sampled post-auction index
  before Dec 7, otherwise the worst case. This value is assumed, never a fill. The book then carries on
  instead of returning `UNRESOLVED_PRIOR_DAY` forever. The hourly reconcile settles it the same evening.
- From NSE CAS 2.0 (Dec 7, 2026) no paper fill is booked at or after the expiring contracts' 15:30 close.
  Every flat time is capped two minutes before that close, so A/B/C's 15:38 becomes 15:28. Nothing
  changes before Dec 7.
- Acceptance: tests reproduce each defect (they fail on the old code and pass on the new), and the
  expiry test files pass. The lab has none of these paths, so lab results are unchanged.

**EN02: the 13:00 warm-up (engine, Dev).**
- The live recorder started at 12:59, so E03.2's 12-bar signal could not decide before about 13:11. The
  lab decides from 13:00 with the morning's bars. Two of the 39 lab tickets (+Rs 1,715) were decided in
  13:00–13:10.
- Recording now starts at 12:47. A, B and C act only inside their own 13:00+ windows.
- Acceptance: E03.2 can decide at 13:00; the slot count is 1,038; the expiry tests pass.

**EN03: more put tickets.**
- Put signals need efficiency ≥ `put_eff` instead of 0.70. Calls are unchanged.
- Grid: `put_eff` in {0.65, 0.60, 0.55}.

**EN04: more money on the side that earns.**
- Put tickets at `put_mult` in {2.5, 3, 3.5} times the call's Rs 1,250. The current value is 2. The lot cap
  is round(3 × mult) and the day reserve is Rs 2,500 × mult.

**EN05: a put runner at the clock.**
- Today, a put ticket of 2 lots or more still open at its 8-minute clock is sold whole. Under EN05, if its
  bid is at least `put_runner` × entry, half the lots (rounded up) are sold. The rest becomes E03's runner:
  floor at cost, half the peak kept, sold at 10x or from 15:14.
- Calls are unchanged.
- Grid: `put_runner` in {1.1, 1.2, 1.3}.

## Decision rules (fixed now; `en_score.py` applies them mechanically)

The control is E03.2 from the same run (`en_lab.E032`, which reproduces +21,517.55).
- Each year is run as its own Rs 25,000 book.
- "Continuous" means both years as one book.
- Fill levels: ordinary, adverse, severe.

An arm **beats E03.2** when all of these hold:
1. In 2024 and in 2025 separately, net ≥ E03.2's at ordinary AND at adverse fills.
2. In each year, net without that year's best day (ordinary) ≥ E03.2's.
3. The continuous severe-fill net ≥ E03.2's severe net − Rs 1,000.
4. The continuous worst day (ordinary) ≥ −Rs 2,500.

How each slot's setting is adopted:
- **EN03:** the loosest `put_eff` that beats E03.2, provided every grid point between it and 0.70 also
  beats E03.2. Otherwise EN03 fails.
- **EN04:** 3x is adopted only if 2.5x, 3x and 3.5x all beat E03.2 AND all pass `RISK_PLAN.md`'s frozen
  limits on the continuous book:
  - skeptical losing-year chance ≤ 30%;
  - skeptical 95th-percentile drawdown ≤ Rs 5,000;
  - severe net ≥ −Rs 6,250.

  Otherwise EN04 fails and puts stay at 2x.
- **EN05:** 1.2 is adopted if it and at least one neighbour beat E03.2. Otherwise EN05 fails.

**Combination:**
- If two or more of EN03–EN05 are adopted, their combination is scored.
- It is the candidate only if it beats E03.2 (rules 1–4) and beats each adopted single arm at continuous
  ordinary and adverse.
- If the combination fails, the single adopted arm with the higher continuous adverse net is the candidate.

**What an adoption means:**
- In-sample development on seen data; a hypothesis.
- An adopted candidate can run as a paper shadow beside E03.2.
- It replaces E03.2 as main only after the frozen 2023 exam (owner's word) or the forward count passes.
- Reported regardless: per-year tables, ticket counts, net without the best day, worst day, drawdown,
  and the incremental tickets.

## 2026 sanity check (no decision)

Every adopted arm runs on the 10 Production-recorded sessions:
- E03.2 and the arms run through the engine's own `run_tick` (an engine Variant).
- Or, where no engine variant exists, through the lab rule on the recorded minute closes.

Reported, never used to choose.

## Rollout and rollback

- EN01 and EN02 are engine changes in Dev.
- An adopted strategy arm becomes a disabled-by-default paper Variant in `expiry_e02.py` with its own
  database, like E03.1.
- Nothing is deployed until the owner says so, through the GitHub release flow.
- Rollback: `EXPIRY_MAIN_STRATEGY` and the variant flags; EN02 by setting `TICK_START` back to 12:59.
