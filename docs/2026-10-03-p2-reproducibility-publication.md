# P2 — Reproducibility and exclusive research publication (Dev only)

`backtest_cli.policy_manifest` now recursively discovers and hashes local
Python imports reachable from the adapter engine modules. A helper/cost/exit
dependency change is therefore visible in the manifest rather than silently
appearing compatible.

Snapshots and JSON reports are now built as sibling temporary artifacts and
published through exclusive hard-link creation. A competing writer cannot
replace a completed archived artifact between an existence check and write.
The losing writer gets the existing no-overwrite refusal; failed temporary
artifacts are removed. Existing manifests and reports remain readable.

Verification: `python-engine/winvenv/Scripts/python.exe -m pytest
python-engine/tests/test_backtest_cli.py python-engine/tests/test_backtest_lab.py -q`
returned **26 passed**, with one existing httpx deprecation warning. No market
data was collected, and no strategy, broker, runtime setting, Production file,
schema, push or deployment changed.
