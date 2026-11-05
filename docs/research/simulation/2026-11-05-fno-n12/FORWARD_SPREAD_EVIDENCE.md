# Forward spread evidence for regular F&O

The completed November 5 paper ledger confirms structure 38 at ₹2,545.91. The archive has no joint quote during that position's hold, so neither its native management path nor an alternative exit is available. Existing management already reads the exact persisted tokens together. Retain those responses after the native manager returns. This adds evidence without adding any provider request, scheduler job, order or settlement change.

Scope and contracts. Add an off-by-default `FNO_DR_EXIT_PATH_RECORDING` switch in Dev. Append bounded management batches using the existing guarded exit-path writer in a separate `fno_dr_exit_paths` folder. Retain only fields needed for a raw quote replay, with immutable token and position references, provider receipt and management decision clocks, native settings and settlement count. Keep incomplete reads visible. The read-only F&O exporter includes finished batches and only the defined-risk ledger rows needed to verify cash, from the same database transaction as the spread positions.

Add an explicit held-path mode to the existing defined-risk study. Require matching contract and parameter evidence, usable raw timestamps, sufficient visible exit-side size, chronological management looks and exact baseline exit clock with reconciled reason and cash. Preserve the existing sampled-archive research mode. A later alternate exit with no available observations remains unresolved or unavailable. Verify writer isolation, failure behavior, multi-lot size, clock, exporter and end-to-end synthetic settlement. Compare only forward observations after the source and candidate freeze when they exist. Keep November 5 recorded and unavailable for the new path.

Dev only. No data migration. Roll back the evidence hook by setting the switch false or reverting the isolated change through GitHub. The next independent strategy round remains distinct from the evidence collector.

## Commands for a later observation run

Use the usual finished-session F&O export. Its file manifest binds the held batches and the database containing the minimal paper ledger. The held evaluator rehashes both before use. With the Dev virtual environment, freeze before opening a scored forward panel.

```powershell
python python-engine/fno_dr_exit_experiment.py freeze --held-paths --experiment-id n012-held-forward --output <fresh-manifest>
python python-engine/fno_dr_exit_experiment.py evaluate --held-paths --db <export>/fno-replay.sqlite --archive-root <export> --manifest <fresh-manifest> --output <fresh-report>
```

Sampled and held manifests are distinct. Both bind code and settings. Older source fingerprints require their original checkout. Any held-path exit delayed beyond the native close can remain unavailable because recording follows the native open position. The synthetic regression demonstrates exact one-position settlement. It does not establish forward returns.

## Verification

The focused suite passed 125 tests on Python 3.11.9. The files exercised the spread book, spread verifier and sizing, the single-leg exit cadence and verifier, F&O orchestration and the forward export. The three-lot fixture reconciles the ledger and exact exit clock. Tests also exercise disabled recording, preservation of the native management order, insufficient size, missing legs, incomplete snapshots, duplicate clocks and a changed export hash. The Dev atlas was regenerated and indexed 304 Python modules. Production HEAD was `398d44ad` during this slice. The recorder remains disabled in Dev settings. No runtime production configuration, deployment or trade authority changed.

The held CLI ran against the previously saved November 5 export with the new forward freeze. It verified the exported database, returned zero usable pairs and marked structure 38 unavailable because the manifest binds no `fno_dr_exit_paths/2026-11-05.jsonl`. The report explicitly returns `NOT_ASSESSED` for qualification. The private availability receipt is `_local/round11/held-mode-nov5-availability.json`, SHA-256 `ac304180f5aff4be28b17255e862eaf2dea1285d0c6ad09a95babed16bb74866`.

The later full engine run used `.\winvenv\Scripts\python.exe -m pytest -q tests` from Dev `python-engine`. It exited 0 with 6,245 passed, four skipped and 53 warnings. A Penny simulated database-outage fixture emitted an unhandled-task logging message during teardown after the summary. This is a software verification run, separate from the forward strategy evidence.
