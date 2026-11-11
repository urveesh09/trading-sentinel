# N13 forward check: the lock on one look a minute, on the paper book's recorded live looks

Declared Nov 11, 2026, after the owner's "go on do it and test if it works good". These sessions were already recorded, and their outcomes are known in outline from RESULTS.md, so this is a declared post-hoc check, not an exam. It is committed before `forward_cadence.py` is run.

## Data

The data is Production, read-only: `/data/research/fno_exit_paths` (every exit look of a held paper position, Oct 27 – Nov 11), the quote archive `/data/research/quotes/<day>` for the same days, and `fno_positions` rows from Oct 27. All of it was copied into a scratch folder. It covers 19 closed paper positions.

## Arms

- **CURRENT:** each look with the exit settings recorded with it (the trend lock changes them between looks). It must reproduce the stored live exit.
- **MINUTE:** CURRENT with `FNO_PROFIT_LOCK_LOOK_SEC` 55, run through `fno_lock_cadence.evaluate`. That is the engine change.

After the live exit, both arms continue on the archive's quotes of the same contract until the first gap over 180 s, and an arm still open then is unresolved.

## How it is read (fixed now)

- Only positions where CURRENT reproduces the live exit count.
- The paired difference is MINUTE minus CURRENT over positions both arms resolve. Unresolved MINUTE positions are listed and never priced.
- The agreed bar for changing a live lock rule is at least 20 scored trades (`fno_exit_cadence`). This window cannot reach it. It is reported as forward evidence, and the owner's "go on do it" is the decision.
- **The MINUTE arm counts as working** if it is not worse than CURRENT on the paired difference and no scored position loses more than ₹1,000 against CURRENT. If it is worse, the switch stays in Dev at 0 (the old cadence), and the work continues.
