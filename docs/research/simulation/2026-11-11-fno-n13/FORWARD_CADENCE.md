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

## Result (run Nov 11, `forward-cadence.json`)

One correction was made before the run, and it changed no rule: the script's path to `python-engine` was one folder short (`parents[2]` → `parents[3]`), so the first launch failed on import.

| | Count |
|---|---:|
| Closed paper positions, Oct 27 – Nov 11 | 19 |
| Skipped: settings not recorded with a look (`settings_unbound`) | 5 |
| Scored (CURRENT reproduces the live exit) | 14 |
| Both arms resolved | 13 |
| MINUTE unresolved | 1 |
| Changed by MINUTE | 2 |
| **Paired difference, MINUTE − CURRENT** | **−₹202.62** |

- **Position 48** (SENSEX 73200 CE, Oct 28): live lock +₹177.78; MINUTE sold later at −₹24.84.
- **Position 58** (NIFTY 24350 CE, Nov 5): live lock +₹1,028.70. MINUTE holds, and is still open when the archive's quotes of the contract stop at 13:47:54. The next quote is at 13:51:45, a 231-second gap against the 180-second limit. At 13:47:54 its bid and best were ₹303.30, its lock floor ₹228.65, and its trail was active. It is unresolved, and the rule never prices it. For reference only, not counted: the one-lot record, which looks about once a minute under the same OR20 exits, sold the same contract at 14:22:52 on its trail at ₹252.20.

**Verdict by the declared rule: not passed** (the paired difference is below zero). `FNO_N13_LOCK_LOOK_SEC` stays 0 in Dev, so the old 10-second cadence is unchanged. The evidence is two changed trades, so it is thin either way. The archive cutoff is the declared rule and is not loosened for this window.

**Next:** re-run `forward_cadence.py` on sessions from Nov 12 onward, with the same arms and the same rule, once the window holds at least 20 scored trades. The live looks keep being recorded, and nothing needs to run in Production.
