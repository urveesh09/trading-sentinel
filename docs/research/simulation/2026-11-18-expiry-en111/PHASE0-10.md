# Round 10 phase zero: activation before any money (receipt `phase0-10.json`, script `phase10.py`)

**Scope.** These counts come only from signal clocks, features and nominal windows (decision+1 to +12 bars). No P&L and no position outcome was computed or inspected.

EN87 has 38 signal minutes (34 signal runs) on 27 NIFTY dates. That is the ceiling on what any EN87-based family can change.

| Family | What was checked | Finding | Decision |
|---|---|---|---|
| EN111 | Contract differences at E03 minutes | The nearest one lot differs from the legacy contract in 49 of 77 E03 minutes | Identified |
| EN112 | States by context | rank40, the literal rule, is defined for **0 of 38** EN87 minutes: the median number of prior same-direction events in 40 sessions is 7, against a minimum of 20. ACCELERATION gives 7 fresh and 31 mature. rank_all gives 9 fresh, 13 mature and 16 missing | **Pre-registered geometry revision.** EN112:r1 cells (EXTENSION_RANK and BOTH) use rank_all. The 12 literal cells stay registered and are reported NOT IDENTIFIED: they equal EN87 by construction |
| EN113 | Confirmed fast deterioration in nominal holds | **L1: 0 of 38 windows.** The median 1-minute \|S\| is 0.0 on both the fixed and current baskets, so OI does not update minute to minute in this source. L3: 9 (p80) and 4 (p90); L5: 7 and 3. Fixed and current basket medians agree (L3 0.0219 / 0.0219; L5 0.0395 / 0.0372) | L1 cells are **NOT IDENTIFIED** (they will equal fixed-12). L3/L5 are activation-limited but active. No revision: the lack of 1-minute updates is the finding |
| EN114 | Exhaustion age of the activity budget | Budget 4: ≤8 minutes in 33 of 38. Budget 8: 23 ≤8, 9 in 9–12, 2 in 13–16, 4 never. Budget 12: 18 / 9 / 4 / 7. No v0 missing | Both sides reached |
| EN115 | Response choice against NEAREST and legacy | The response pick equals NEAREST in **37–38 of 38** minutes (differs once, at λ10/rp1); it differs from legacy one lot in 27–28. No fallback; 5 minutes unaffordable | **DUPLICATE of NEAREST.** Per lot, the scenario score ranks by P·β, which is largest for the nearest contract. The cells stay and are reported as duplicates. No objective change (a per-reserve score would be a different policy, not a units fix) |
| EN116 | State occupancy and activation at EN87 admissions | Every model is active at **34 of 34** non-warm-up EN87 admissions (all K, refit and persistence settings). Window occupancy is 27–57%. Warm-up covers the first 41 sessions. The random mapping is active at 15–27 of 34 | **Admission mapping NOT IDENTIFIED**: EN87 impulses are always high-ER states. The cells test only the minute-8 state-and-profit continuation against EN111:0018 (fixed nearest/150/12). No threshold revision |
| EN117 | Events and cost-gate passes | NIFTY: 359 events on 194 dates at buffer 0, and 296 on 182 at buffer 0.25. Gate passes at coverage 2: MIDPOINT 118–145, OPPOSITE_QUARTILE 201–244. SENSEX: 72 and 57 events | Identified (the gate binds on both sides) |
| EN118 / EN120 | Applicable-event dates before each boundary | NIFTY applicable dates before 100 / 140 / all: E03 events 34 / 45 / 58, range events 90 / 126 / 181, EN87 events 13 / 20 / 27. SENSEX: E03 events 9 in all, range events 38 | EN87/EN111 profiles cannot reach the 20-funded-date support before about boundary 140; fallback until then is expected and reported |
| EN121 / EN122 | Same-room lots and windows | Same-room nearest contract: 1 lot in 50 minutes, 2 in 12, 3 in 5. E03 minutes: 77 to 14:29, 104 to 15:00. The calls-only gate removes 22 of 43 call minutes. SENSEX: 14 E03 minutes | Identified |
| EN123 / EN124 | — | These act on every parent's exit ladder or execution | Activation is measured after the score (first-exit reasons) |
| EN125 | Walls in nominal windows | A wall exists at 38 of 38 minutes. Distance quartiles are 2.3 / 5.2 / 8.8 ATR. Reached AT within 8 minutes: 6. HALF_STEP: 13 within 8 minutes, 18 within 12 | Activation-limited but active on both triggers |

## Consequences registered before the freeze

- **EN112:** 12 revision cells, `EN112:r1:*`, plus their random-assignment controls at the revised room rate.
- **EN113 L1, EN115 and EN116's admission mapping:** these are scored as registered. They are reported as NOT IDENTIFIED or DUPLICATE before their money is read. Their P&L is not used to claim that the mechanism works or fails.
- **Labels are fixed now.** A family whose cells cannot change at least 5 parents is ACTIVATION-LIMITED, whatever its P&L.
