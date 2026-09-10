# Final Dev Green acceptance manifest

## Scope and identity

This records the Dev implementation of the D1–D9 acceptance plan at the commit that adds this file. It is a software-contract sign-off for monitored deployment only: it does not qualify a strategy, authorise a broker order, or claim a future profit. Production was not edited.

## Gate evidence

| Gate | Implemented acceptance contract | Primary regression evidence |
| --- | --- | --- |
| D1 | Entry pair/economics validate before an exit. Accepted entries retain debit, paid entry cost and conservative loss bound when exits are missing/late. Delayed manual execution selects a subsequent real packet, expires/cancels deterministically, and streams reject mixed sessions. | `test_intraday_spread_replay.py`, `test_intraday_spread_chronological.py` |
| D2 | `intraday_spread_signal_artifact.py` atomically writes/verifies canonical evaluator, policy, config, source and signal evidence. The archive adapter accepts verified artifact files, not score dictionaries, and checks source-manifest bytes. | `test_intraday_spread_signal_artifact.py`, `test_intraday_spread_archive_adapter.py` |
| D3 | Holdout reports require chronological train/holdout sessions, declared coverage cells, stable opportunity IDs and signal-artifact IDs. Unavailable/no-fill/unresolved cases remain visible and non-finite closed P&L is rejected. | `test_intraday_spread_holdout.py` |
| D4 | Existing active-idea management stays on its public-underlying branch before directional-chain construction; invalidation remains ahead of reminders and lifecycle runs independently. No partner order/holding inspection was added. | `test_partner_orchestrator.py`, `test_partner_manual_advisory.py` |
| D5 | Advisory input status uses API read-time freshness and an injected clock with explicit `STALE`, `FUTURE_CLOCK`, `UNAVAILABLE`, and `HEALTHY_NO_SETUP` states. Older attempts cannot overwrite newer observations. | `test_partner_manual_advisory.py`, `test_hedge_routes.py` |
| D6 | Telemetry preserves in-flight/completed/rejected facts with bounded retention and never blocks locked-DB work. A controlled test proves the lifecycle wrapper completes while bulk collection is held. | `test_scheduler_telemetry.py`, `test_scheduler_closures_invoke.py` |
| D7 | Five source sheets are always emitted for MOMENTUM, EDGE_LIVE, MOMENTUM_PAPER, PENNY_PAPER and EDGE_PAPER. They include query/parameter scope, snapshot hash, ledger/bankroll delta counts and explicit internal-only status. | `test_reconciliation_evidence.py`, `test_performance.py` |
| D8 | Completed Kite bars validate archived master/basis, exclude current bars and isolate a failed index. `research_cli.py replay-spread` is a read-only archive → verified signal artifact → chronological replay path and honestly returns insufficient evidence. | `test_proactive_market_data.py`, `test_proactive_intelligence.py` |
| D9 | Connected Dev regression and interface suites are executed below. Test artifacts remain outside qualification storage; these modules add no transport or order authority. | Commands below |

## Reproduction commands and results

Run from `python-engine` in the Dev working copy:

```powershell
& .\winvenv\Scripts\python.exe -m pytest tests/test_intraday_spread_replay.py tests/test_intraday_spread_chronological.py tests/test_intraday_spread_archive_adapter.py tests/test_intraday_spread_signal_artifact.py tests/test_intraday_spread_holdout.py tests/test_partner_manual_advisory.py tests/test_partner_orchestrator.py tests/test_reconciliation_evidence.py tests/test_proactive_market_data.py tests/test_proactive_intelligence.py tests/test_operational_coverage.py tests/test_scheduler_telemetry.py tests/test_scheduler_closures_invoke.py tests/test_hedge_routes.py tests/test_fno_orchestrator.py tests/test_fno_dr_book.py tests/test_performance.py -q
```

Result at implementation time: **253 passed**. The repository currently emits one Starlette lifespan deprecation warning.

Dashboard validation from `node-gateway/client`: `npm run test:unit` (**23 passed**) and `npm run build` (**passed**).

Gateway validation from `node-gateway/server` was attempted with `npm test -- --runInBand` but is **not accepted as passing** on this host: the installed `better-sqlite3` package lacks a compatible Node ABI native binding. The command must be rerun in the repository's compatible container/runtime before release; no gateway result is inferred from the Python or client suites.

## Enabled behaviour and hard limitations

* All added replay, artifact, holdout and CLI paths are research-only and set `can_place_orders: false`.
* Missing profiles, absent source manifests, stale/future clocks, partial books, unavailable index data and missing exits remain visible failure states. None creates P&L, qualification or delivery.
* An accepted historical spread entry with an absent exit is unresolved risk, not a closed loss or rejected idea.
* Source-manifest references must be immutable files below the selected archive root. A digest alone is insufficient.

## Pending operational prerequisites (not code defects)

1. Deploy through the reviewed GitHub workflow and verify image revision, schema, volumes, archive disk reserve and scheduler timing.
2. Save an explicit INTRADAY NIFTY/SENSEX advisory profile and separately test any authorised routing; profile success is not delivery success.
3. Collect active two-leg bid/ask/depth records and write a deterministic signal artifact from declared causal data. Run replay and a predeclared heldout report; negative or insufficient evidence remains unqualified.
4. Observe a complete relevant market session for real latency and lifecycle coverage. The Dev isolation test is not a Production latency benchmark.
5. Supply scoped broker statements only if external cash reconciliation is wanted. The five sheets are internal investigations, not broker reconciliation.
6. Run the gateway Jest contracts in the compatible Node/container runtime, resolving the local `better-sqlite3` ABI mismatch without changing application semantics.

## Deliberate backlog, outside D1–D9

No speculative strategy, profit threshold, broker integration or partner order monitoring was added. Those require a separate reproducible plan.
