# Opening-drive persistence before the chain request

The regular signal pass awaits `fno_book.drive_today` before requesting an option chain. On a cold path it opens and commits a SQLite connection for each historical opening drive and a separate one for the current row. The in-memory warm path already returns immediately. This change keeps the synchronous dependency and batches the ordered historical and current rows in one transaction. That preserves the meaning of a failed book evaluation and avoids background writes during entry decisions.

Change `python-engine/fno_book.py` and its focused storage tests. Preserve schema setup, seed precedence, per-underlying identity, existing rows via `INSERT OR IGNORE`, exact recorded values and source labels, historical median and cache behavior. If the insert fails, the batch must roll back, and a retry must be able to complete. No provider, schedule, risk or configuration change. Acceptance requires matching rows and `(value, side)` on a synthetic cold benchmark, a shorter measured cold run on the same machine, focused book/orchestrator parity and regenerated atlas. Benchmark results are local to SQLite storage and do not measure broker order latency.

Dev-only implementation. Rollout would use the normal GitHub path after review. Revert the isolated commit to roll back. No migration or changed persisted row format.

## Verification

On the local Windows engine, sixteen alternating before/after runs per case compared the implementation at `7011f4b` with the batch. Every run used a fresh temporary SQLite database and the deterministic `_bars` test fixture. The old and new result tuples and complete persisted row sets matched on all 32 pairs.

| Prior sessions in frame | Old median | Batch median | Old p90 | Batch p90 |
|---|---:|---:|---:|---:|
| 7 | 29.41 ms | 23.72 ms | 34.20 ms | 26.16 ms |
| 20 | 112.28 ms | 39.38 ms | 116.23 ms | 40.98 ms |

The five focused files `test_fno_book.py`, `test_fno_book_start.py`, `test_fno_orchestrator.py`, `test_fno_n11.py` and `test_fno_n11_second_lot.py` passed 153 tests. The first draft of the new rollback fixture had too few prior completed sessions to yield the asserted `HIGH` side. The final fixture warms the earlier backfills and proves that a failed insert rolls back the batch and that retry preserves an existing row. `python scripts/build_system_code_atlas.py` indexed 304 modules.
