# B0 — one offline backtest entry point and an honest shipped-strategy catalogue (October 3, 2026)

Parent: [October 3 plan](2026-10-03-backtesting-and-fno-safety-plan.md), B0.

## Problem

Backtests are scattered across Lab adapters, research scripts and ad-hoc
CLIs:
- No single list says which shipped strategies have which fidelity of
  backtest.
- No reproducible run binds code, settings and data identities.
- Comparisons can silently mix different datasets.
- The `scope` label (added in B2) is still `UNSPECIFIED` for the older
  adapters.

## Contract

1. **`python-engine/backtest_catalogue.py`** (pure).
   - One row per shipped strategy, recording its book, product, live gating,
     registered adapters with their scopes, a status and the planned B-step.
   - Status values: `LIFECYCLE`, `EVALUATOR_ONLY`, `PROXY_ONLY`,
     `NOT_ADAPTED`, `UNAVAILABLE` and `EXCLUDED_BY_OWNER` (B5).
   - Validation: every adapter it names exists in `STRATEGY_REGISTRY`, and
     every registry adapter is catalogued.
2. **Honest scopes for the existing adapters:**
   - the Swing daily and Penny daily-proxy adapters, and the walk-forward
     variant, are `PROXY` (not the shipped strategy);
   - Momentum 15-minute is `EVALUATOR` until B4 verifies it;
   - F&O is `UNAVAILABLE`.
3. **`scripts/backtest_snapshot_collector.py`** (stdlib only, so it can be
   streamed into a container).
   - Reads `intraday_cache` (all labels) for the tickers and window, and
     `ohlcv_cache` from `start − history_days` to `end`, in one read-only
     transaction with bounded rows.
4. **`python-engine/backtest_cli.py` commands**
   - `catalogue`.
   - `snapshot --db PATH | --container NAME`. Writes a **new** SQLite file
     with the two tables plus a `snapshot_manifest` row: the request, the
     source, and a SHA-256 over canonical rows. It refuses to overwrite.
   - `coverage --snapshot S --strategy ID`. Reports the B1 status counts and
     reasons for the strategy's interval, plus a daily summary.
   - `run --snapshot S --strategy ID --from --to [--config JSON] --out NEW.json`.
     - Verifies the snapshot hash first.
     - Then runs the adapter's `snapshot_config` / `snapshot_assumptions`
       (only the default assumptions are accepted) and
       `prepare` / `execute` / `normalize`.
     - Writes a report containing the scope, metrics, warnings and result,
       plus a **policy manifest** with the Git commit and dirty flag,
       SHA-256 of the adapter engine and `backtest_lab.py`, a hash of all
       non-secret settings plus that strategy family's settings, and the
       snapshot hash and dataset fingerprint.
     - Settings keys matching TOKEN, SECRET, KEY, PASSWORD, CHAT, URL or
       ACCOUNT are never written.
   - `compare A B`. Refuses unless both use the same snapshot hash and
     window; outputs metric differences.
   - `report R`. Prints the summary.
5. **No Production routes, broker calls or order capability.** Arbitrary
   strategies or callbacks cannot run; only registry IDs can.

## Acceptance

- The catalogue and registry agree. Every adapter has a non-`UNSPECIFIED`
  scope.
- Snapshot: the copy is read-only (the source is unchanged), the hash is
  deterministic, and overwrite is refused.
- `run` produces a report with the policy manifest and no secret keys. A
  tampered snapshot is refused.
- `compare` refuses different snapshots or windows and diffs identical ones.
- An end-to-end run with the MIS lifecycle adapter on a synthetic snapshot
  works.

## Rollout and rollback

- **Rollout.** Offline and Dev only. New modules plus scope labels.
- **Rollback.** Revert them; Lab behaviour is unchanged.

## Implementation result (Dev only; not pushed, not deployed)

Implemented as contracted:
- `backtest_catalogue.py`;
- `scripts/backtest_snapshot_collector.py`;
- `python-engine/backtest_cli.py`;
- honest scopes on the older adapters (Swing and the Penny daily proxies
  `PROXY`, Momentum `EVALUATOR`, F&O `UNAVAILABLE`).

**Verification.** `tests/test_backtest_cli.py` plus `tests/test_backtest_lab.py`
gave **22 passed** (with the known HTTPX deprecation). Covered:
- the catalogue and registry agree;
- the snapshot copy leaves the source DB untouched, and overwrite is refused;
- an end-to-end MIS lifecycle run produces a report with a secret-free
  policy manifest;
- `compare` works on identical runs;
- a tampered snapshot is refused.

**Not yet run on real data:** Production is stopped.

**Remaining B-series work:** B3 (Swing and EDGE parity), B4 (Momentum and
Range lifecycle) and B6 (reporting and holdout). B5 is excluded by the
owner.
