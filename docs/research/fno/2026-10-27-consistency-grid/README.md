# F&O consistency grid — 2026-10-27 (O27)

The owner's request on Oct 27 was to test many mixed-and-matched strategies on the archived F&O sessions: "I don't want the most earning one. I want the one that is most consistent."

This file was written and `freeze.json` committed **before any arm was scored**. The results section below the line is added after the run, and the frozen part is not edited.

## What is replayed

Every arm is the whole NIFTY single-leg paper book, run through `python-engine/fno_policy_replay.py`:
- the live entry plan, strike choice, sizing and loss brakes;
- the exit ladder at fast-exit cadence (each archived quote batch, about 60 s);
- buys at the ask and sells at the bid, with real charges.

Each arm changes one entry signal and one exit setting; everything else is the shipped book: target 1.8R, the 25% premium backstop, hard flat at 15:10, 3 trades a day and the expiry-day block.

**Entries: 5 families, each with and without the EMA check.**

| Entry | Definition |
| --- | --- |
| OR30 | The shipped break: a 30-minute opening range and the first close beyond it ±0.25 ATR (`evaluate_fno_mom`). |
| OR20 / OR45 | The same, with a 20- or 45-minute range (recorded shadow variants). |
| CONFIRM1 | One confirming bar after the cross, with extension of at most 0.35 ATR (recorded shadow variant). |
| CONT | The break, or after it a pullback to within 0.25 ATR of the break level followed by a bar that resumes (recorded shadow variant). |
| *_NOEMA | The same entry without the multi-day EMA(21/50) agreement (`FnoShadowVariant.ema_filter=False`). |

**Exits: 4 locks × 3 time stops × 3 trails.**

| Axis | Values, in neighbour order |
| --- | --- |
| Profit lock | TIGHT (arms at 0.25R, keeps 60% of the best gain), LIVE (0.40R, keeps 50%), LATE (0.80R, keeps 50%), OFF. All have a 0.10R floor. |
| Time stop | 30, 45 or 75 minutes, needing 0.5R by then. |
| Trail after the target | 0.6, 1.0 or 1.5 ATR. |

That makes 10 entries × 36 exits = 360 ranked arms, plus one parity arm.
- **CURRENT** is `OR30|LOCK_LIVE|T45|TR1.0`, the shipped book. The freeze checks that the live settings still equal it.
- **The parity arm** evaluates the shipped break through the variant code path, with the EMA check on. It must trade exactly as CURRENT; otherwise the with/without-EMA comparison is confounded.

## Data

- **Source:** a read-only export of the Production research archive (`scripts/export_fno_replay_dataset.py`, run Oct 27 at 16:30 IST).
- **Sessions:** 29 NIFTY sessions, Sep 10 – Oct 26, all sealed. They are kept out of git under `_local/dataset/`; `freeze.json` binds the manifest hash.
- **A_select (choosing):** Sep 10 – Oct 9, 19 sessions.
- **B_check (checking):** Oct 12 – Oct 26, 10 sessions. Expiry days count as sessions; the single-leg book does not trade on them.
- **Settings:** all 123 effective `FNO_*` settings in Dev equal Production's. They were compared by per-key hash, and only names were printed.

**All of this data has been seen before.**
- A_select was used by earlier F&O studies.
- B_check was the Oct 24 entry study's decision window.
- Oct 21, 23 and 26 are the days whose rejected breaks prompted the no-EMA entries. A no-EMA arm that passes B is therefore partly circular.

The grid can rank robustness on seen data; it cannot qualify anything. The first untouched evidence is forward sessions from Oct 28.

## Selection rule (frozen)

1. **Consistency score (CS)** for an arm in a window = net excluding its best winner ÷ max(max drawdown, ₹1,000). It rewards profit that does not depend on one trade and is earned with a small drawdown.
2. **Eligible on A:** at least 8 trades, net > 0, and net excluding the best winner > 0.
3. **Score = plateau CS:** the median CS on A of the arm and its exit neighbours. A neighbour has the same entry and is one step away on exactly one axis. A lucky spike surrounded by losing settings scores low; a region that works scores high.
4. **Rank:** plateau CS, highest first. Ties go to the higher green-week share on A, then fewer red days, then the name.
5. **Check on B:** net ≥ 0, and max drawdown ≤ max(1.5 × CURRENT's B drawdown, ₹5,000).
6. **Recommended:** the first ranked arm that passes the check. If none passes, keep CURRENT.

**What a recommendation allows:** a broker-free live shadow plus a nightly replay forward.
- There is no paper or live change in the proving week (Oct 26–30). The Nov 2 real-money test mirrors the paper book.
- Promotion is the owner's call, made on forward evidence.

## Run

```
python scripts/run_fno_consistency_grid.py freeze --data docs/research/fno/2026-10-27-consistency-grid/_local/dataset --out docs/research/fno/2026-10-27-consistency-grid
python scripts/run_fno_consistency_grid.py run --out docs/research/fno/2026-10-27-consistency-grid --jobs 6
```

`run` refuses to start if any bound source, dataset file or setting has changed since the freeze.
- Each arm is replayed once over the whole window, and its trades are split by entry date. Sizing and brakes therefore carry over from A into B, as they would live.
- Each arm's report is written once under `_local/arms/`.
- The parsed sessions are cached under `_local/observations/`.

---

## Results

Pending: filled in after `run`.
