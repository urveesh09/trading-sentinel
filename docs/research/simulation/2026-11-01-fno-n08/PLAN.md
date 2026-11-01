# N08 plan: repair the weaknesses of N04, N05 and N07, then face 2023

**Owner's request (Nov 1, 2026):** understand the weaknesses of N07, N04 and N05, make an N08 that keeps the small losses and earns more, do what the other agent wanted to do next, and test on all four years together.

**Status of this file:** written before NIFTY 2023 was opened. Research only: no application, configuration, Production, lot-limit or real-money change.

## How the years are used

- **2024, 2025 and 2026 are development years**, all seen many times. Anything found on them proves nothing by itself.
- **2023 is the test.** It has never been replayed. No rule here looked at it, and it opens only after `freeze.json` is committed.
- **One opening.** Everything that sees 2023 is listed in the freeze, and nothing is tuned after it opens.
- **It uses up the O31e exam too** (`docs/research/fno/2026-10-31-weak-spots/freeze-2023.json`). Those six books run unchanged and are scored by their own rule in the same opening.

## What the diagnosis found (2024-26, N07, 169 trades)

| Finding | Evidence |
|---|---|
| Giving back profit is a small problem | 66 of 85 losers never reached 0.5R of premium gain, and they lost Rs 1,25,199. The 19 that did reached it lost Rs 19,899. "51 of 86 losers were once profitable" is mostly tiny positive snapshots. |
| Stops are mostly right | Only 27 of 85 stopped trades stood above entry by 15:10 |
| Profit locks don't pay | 19 lock settings: the best added Rs 4,214 and cost 2025 Rs 2,170 |
| Cutting TPB early hurts | The half-clock stall on TPB cost Rs 46,065: stalled TPB trades recover |
| Low-day trades in the direction of the daily trend don't work | Calls cost Rs 83,700; skipping puts in a daily uptrend cost Rs 47,545 |
| Event days offer nothing to act on | 7 trades in three years, +Rs 4,078 |
| The morning low-day trade is the edge | First low-day TPB of the day between 11:30 and 12:00: 27 trades, +Rs 48,261, positive every year. The other low-day trades are close to flat, and those from 14:00 lose. |
| The largest losses are 3-lot trades | Worst trades -6,910, -5,032, -4,916 |
| The trail on EFF and OR20 is tight | 1.0 ATR -Rs 20,089, 1.5 (today) 0, 2.0 +Rs 20,369, 2.5 +Rs 21,580, 3.0 +Rs 15,923: a plateau, on very few trades |

## N08

N07 (N03's four strategies, skip rule, ADX 30, one-lot low-day TPB, EFF retest, premium-aware early cut) with four changes:

1. **W, wider trail:** EFF and OR20 trail at 2 ATR, as TPB already does. Shipped break unchanged.
2. **E, early two lots:** a low-day TPB entered before 12:00 may take up to 2 lots. The planner's risk limit still applies.
3. **L, late stop:** no low-day TPB entry from 14:00: too little time is left for a trade that earns by being held to the close.
4. **C, no third lot:** nothing above 2 lots. This gives up some profit to cut the worst losses.

**N08 on 2024-26:** Rs 76,294 / 58,647 / 1,04,924, worst annual closed fall 4.70%, worst trade -5,107, worst day -9,720.
**N07 on 2024-26:** Rs 57,982 / 52,023 / 77,135, 4.77%, -6,910, -9,482.

**Against that gain:** five trades supply Rs 44,312 of the Rs 52,724. 80 books were tried on the same three years. The weekly t of 2.08 ignores that search. It is a lead, not a finding.

## Files and contracts

- `n08_rules.py`: pure rules. `n08_lab.py`: patches on the unchanged replay stack. `exam_2023.py`: freeze, seal, warm, bind, run.
- `test_n08.py`, `parity-*.json`: rule edges, and N03/N04/N05/N07 reproduced trade for trade; every N08 code path on and nothing changed equals N07; the 2023 route aimed at sealed 2025 data equals the stored 2025 results.
- `screen-1..4.json`, `heldout.json`, `diagnosis.json`: the search and its results, failures included.
- `freeze.json`: sources, books, rules. `data-binding-2023.json`: hashes and decisions, committed before any 2023 replay.

## Acceptance, fixed now

- **N08 passes 2023** if its 2023 net is above zero and at or above N07's, and its largest closed fall on 2023 is no larger than N07's.
- **N08 passes the four years** if it is positive in every year and its four-year total is above each of N03, N04, N05 and N07.
- **Verdict:** N08 becomes the lead research candidate only if it passes both. Otherwise it stays a seen-year lead, and the result is reported as it is.
- **The O31e exam** is scored by its own frozen rule.
- **Nothing changes in the system on this.** The owner decides. Real money needs shadow evidence and real fills first.

## Rollout and rollback

Dev research only. Rollback: nothing to roll back. N08 is not in the engine.

## Remaining after this study

- Keyed shadow comparison of N04, N05, N07 and N08 on fresh sessions (the other agent's next step). It can't be done on history.
- Real fills and costs from the Nov 2 test, to replace the assumed extra cost. N07's exit behaves the same with or without that assumption; N04's doesn't.
- `repair-ceiling` (52 requests, owner's word): all replays here ran on the cut data.
- The engine change, if the owner chooses N08: all four parts are settings or small routing changes, but E and L have no engine switch yet.
