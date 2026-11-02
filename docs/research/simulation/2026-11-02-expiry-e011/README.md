# E01.1 study

Plain-language report: [docs/EXPIRY_RESEARCH_E011.md](../../../EXPIRY_RESEARCH_E011.md). Plan frozen before September was read: [PLAN.md](PLAN.md). Result: [OUTCOME.md](OUTCOME.md). Next exam: [EXAM_YEAR.md](EXAM_YEAR.md).

## Order of events

| Commit | What |
|---|---|
| f457d9b | Freeze: plan, arms, September panel, tests, hashes. No September ticket's later price read. |
| 7818c62 | Score: `score.py` once, `results.json`, `OUTCOME.md`. |
| 3c23adf | Engine: `CE011`, `CE011R`, `verify_native.py`. This deliberately changes `python-engine/expiry_paper.py`, so `freeze.py verify` no longer matches the working tree. To reproduce the score, check out f457d9b. |
| next | The owner's order: E01.1 becomes the main C (expiry-v4), the old C runs on as `CL`, `CE011` is gone. `verify_main.py` proves the swap against 3c23adf. `verify_native.py`, `arms.py` and the lab read `POLICIES["C"]` and `CE011` as they were: use 3c23adf or f457d9b to run them. |

## Files

| File | What |
|---|---|
| `e011_lab.py` | The fast replay. Calls the engine's own functions. |
| `parity.py`, `parity.json` | The lab against E01's stored native results: 72 legs, ordinary and adverse, zero mismatches. |
| `verify_native.py`, `native-parity-*.json` | The engine against the lab and E01's stored results, through the real tick and store. |
| `verify_main.py`, `native-parity-NATIVE_V4.json` | The swap: new C = old CE011, new CL = old C, all else unchanged, 290 legs, zero mismatches. |
| `genome.py`, `view_ga.py` | The genome search and its leave-one-session-out folds. |
| `one_gene.py`, `second_look.py` | One change at a time from E01, by session. Their output is kept under `_local/`. |
| `arms.py` | The frozen arms. |
| `sept.py`, `spreads.json`, `preflight_sept.py`, `preflight-sept.json` | The September adapter, its spread model and the check made before freezing. |
| `panel.py` | September's ticket admission rules. |
| `seen_table.py`, `score.py`, `results.json`, `view.py` | The frozen tests and their result. |
| `round2_map.py`, `round2-map.json` | 162 nearby exit rules on all 25 tickets, after the score. Picks nothing. |
| `test_e011.py` | The lab's own tests. |

`_local/` is private and ignored: compacted sessions, the September snapshot, index minutes, genome runs, native books. `_local/ga-no-stop-bug/` and `_local/one_gene-no-stop-bug.json` are the runs invalidated by the bug described in `PLAN.md`, kept as evidence.

## To run

Use `python-engine/winvenv/Scripts/python.exe`, from this folder. `prepare.py` once, then any of the above. No network, no broker, no Telegram, no ICICI call. The September snapshot and index mirror were copied read-only by `preflight_sept.py` and `mirror_index.py`, which refuse to overwrite.
