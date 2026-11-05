# SENSEX catch-up results

The [screen](ROUND14.md) was frozen at `67f726c`. It used the already sealed SENSEX futures archive from July 1, 2025 through October 27, 2026, the original NIFTY development tapes and their frozen native N11T admissions. It requests no data. The scope includes 327 NIFTY calendar sessions. There were 86 expiry or identity exclusions, 22 SENSEX and one NIFTY incomplete futures clocks, and 218 complete paired sessions. Four complete sessions were excluded because the native N11T book had already entered.

| Window | Complete paired sessions | Signals | Signed NIFTY futures points | Median signed points |
|---|---:|---:|---:|---:|
| 2025 source span | 80 | 5 | −95.0 | −17.80 |
| 2026 source span | 138 | 6 | −192.5 | −36.35 |

**Rejected.** Both samples were smaller than 20 and had negative medians. The paired signed movement totaled −287.5 points. Removing the five best dates and subtracting the five-point screen hurdle for the remaining six produced −315.7 points. None of the 11 signal windows overlapped a later N11T entry. No option execution, cash change, whole-book profit or inverse-trading claim follows. The date span excludes November 5, so it makes no alternate claim about that session.

Run `round14.py` in the Dev environment. It verifies the original dated futures tape, controls and source hashes, and writes a new receipt only if no same-name result exists. The two observed windows are development evidence.
