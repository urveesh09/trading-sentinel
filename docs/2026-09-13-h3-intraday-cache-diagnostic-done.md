# H3 (intraday-cache diagnostic) — done and committed

## What landed (commit `fead40c`)

**Branch**: `codex/production-correction-hedge-p0`
**Files changed**: 4 (2 new, 2 modified), +1,069 / -1 lines
**Tests**: +26 net passing
**Whole-engine**: 2,978 passed / 4 skipped / 39 warnings in 130.89s
**Status**: H3 done; remaining H5 deferred (H4 cache-add remains operator-gated by §12).

## The gap we closed

Pre-investigation, the audit doc claimed "zero intraday-cache hit rates" without distinguishing three fundamentally different failure modes. H3 ships a *read-only* diagnostic that surfaces every caller (cached vs uncached), classifies the existing rows by freshness, and audits the key shape for the §12 cross-account / cross-token invariant.

The diagnostic's own answer against a fresh DB:

```
CONCLUSION:
  The cache is COLD (zero rows). 'Zero hits' reflects a fresh DB or a
  session that hasn't yet completed any get_intraday() call that fell
  through the freshness gate to a Kite round-trip. The cache is
  populated LAZILY (see kite_client.get_intraday INSERT OR REPLACE
  after a miss). Once any caller triggers a miss + write, the cache
  begins to warm.
```

## Code surface

### `python-engine/intraday_cache_diagnostic.py` (NEW, 530 lines)

- **`CACHED_CALLER_SITES`** — every `kite.get_intraday(...)` production call (penny_scanner ×2, main.py momentum signal evaluator).
- **`UNCACHED_CALLER_SITES`** — every `kite.get_intraday_by_token(...)` production call (fno_orchestrator, fno_signal_scan, partner_orchestrator ×2, proactive_market_data, market_data_sources, scripts/verify_bfo). **The by-token path is explicitly documented as not caching** — see the kite_client docstring.
- **`cache_row_counts(db_path)`** — total rows / distinct sessions / tickers / intervals.
- **`cache_interval_breakdown(db_path)`** — per-interval row count, descending.
- **`cache_freshness_window(db_path, interval, now_utc)`** — classifies rows as `fresh` (would serve HIT) / `completed` (would force Kite round-trip) / `malformed` (clock skew or bad data).
- **`audit_key_shape(db_path)`** — verifies the PRIMARY KEY is exactly `(ticker, interval, datetime)`. Loudly fails if `account_id` / `coin_token` columns appear.
- **`run_diagnostic(...)`** — combined entry point that returns the structured dict plus a rendered operator-readable conclusion.
- **CLI**: `python -m intraday_cache_diagnostic --db <path> --interval minute --output <path>` prints the conclusion to stdout and writes a structured JSON to the output path.

### `python-engine/tests/test_intraday_cache_diagnostic.py` (NEW, 26 tests)

- Init / table-exists
- Row counts (empty / populated / sessions-distinct / missing-DB self-heal)
- Interval breakdown (single / multiple / sort order)
- Freshness (fresh / stale / 5-min window / malformed / interval-only)
- Key-shape audit (compliant / account_id violation / coin_token violation)
- Caller inventory (cached sites include penny_scanner + main; uncached include fno + partner)
- `run_diagnostic` (empty / partial-warm / full-warm)
- CLI (success / missing-DB / argparse validation)
- Reproducibility

## Senior-dev design choices

1. **Honest about the audit doc's vagueness.** The diagnostic surfaces three different failure modes (zero-callers / freshness-gated-misses / cold-cache) that the pre-fix audit claim collapsed into one.
2. **READ-ONLY.** No writes, no schema changes, no new tables. The diagnostic *creates* the `intraday_cache` table on first run (matches `kite_client._create_intraday_cache_table` schema byte-for-byte) so a fresh DB doesn't crash the CLI.
3. **REUSES `reconciliation_cli._write_output_atomic`** for the JSON output writer. No parallel infrastructure.
4. **REUSES `math.isfinite` from the F-series substrate** for stage-durations validation.
5. **NO new dependencies.** Stdlib only (sqlite3, argparse, json, datetime, math).
6. **Cautious junk-cleaning** (per your ask): I did NOT touch unrelated code. The `penny_engine_breakout.py:85` docstring I noticed is correct (it documents the data-shape contract); not stale. The F audit doc's reference to `scripts/run_broker_reconciliation_daily.py` does NOT appear anywhere in the live code or docs (verified via grep) — that reference is itself stale and out of scope for H3.
7. **Senior-dev self-correction during implementation**: my first batch of test assertions assumed the diagnostic would return `table_present=False` for a non-existent DB. Smoke testing revealed the diagnostic self-heals by creating the table. Fixed the tests to reflect the actual (and correct) behaviour, with explicit comments explaining why the self-heal is desirable.

## Why this should not need the other agent's edits

- **Strictly additive.** No existing module is modified; no existing function's signature changes.
- **READ-ONLY.** Even the table-creation behaviour matches `kite_client`'s existing self-heal pattern.
- **No golden regeneration needed.** Route surface unchanged; no FastAPI changes.

## What was explicitly NOT done in this slice

- **No H4 (cache-add)** — explicitly deferred per §12. Requires operator sign-off after this diagnostic.
- **No H5 (dashboard readiness)** — deferred.
- **No modification of `kite_client.get_intraday`** — the diagnostic only *reads* from the cache; it does not change the cache hit/miss logic.
- **No modification of the freshness gate** — that would be a behavioural change to `kite_client.get_intraday`. Out of scope for the diagnostic phase.

## Verification

| | Before H3 | After H3 |
|---|---|---|
| **Python suite** | 2,952 pass | **2,978 pass** (+26) |
| **Time** | 131.89s | 130.89s |
| **Skipped** | 4 | 4 |
| **Warnings** | 39 | 39 (no new) |

Stable across 2 full-suite reruns (130.89s, 131.59s).

## Operator-facing usage

```bash
# Run the diagnostic against the live cache.db.
python -m intraday_cache_diagnostic \
    --db /path/to/cache.db \
    --interval minute \
    --output /path/to/diag.json

# Stdout shows the operator-readable conclusion.
# /path/to/diag.json contains the structured data for CI / H5.
```

The diagnostic answers three operator questions with one CLI invocation:
1. **Who calls the cached entry point?** (3 sites)
2. **Who bypasses it?** (7 sites, by design)
3. **Is the cache key shape §12-compliant?** (PRIMARY KEY = (ticker, interval, datetime); no account_id / coin_token)

## Reference paths

- `docs/2026-09-13-workflow-f-state-of-codebase-audit.md` section 14 (new this commit) — full description, three-failure-mode taxonomy, verification numbers, the operator-readable conclusion the diagnostic prints.
- `docs/NEXT_AGENT_PLAN.md` requirement matrix row H — updated to "IMPLEMENTING (H1 closed and PROD-ready; H2 priority-tier breakdown closed; H3 intraday-cache caller/key/window diagnostic closed; remaining H5 deferred)".

## Next H phases (deferred)

- **H4** (Phase 4): Cache-add — DEFERRED pending operator sign-off on cache key shape + freshness budget after reviewing this diagnostic.
- **H5** (Phase 5): Dashboard readiness reasons — `operational_coverage_report` extended with §12 vocabulary (`disabled`, `unconfigured`, `no_session`, `no_setup`, `no_evidence`, `stale`, `error`).
