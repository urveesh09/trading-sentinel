# H4.B (cache-add for `get_intraday_by_token`) — done and committed

## What landed (commit `bfb42ac`)

**Branch**: `codex/production-correction-hedge-p0`
**Files changed**: 3 (1 new, 2 modified), +1,033 / -120 lines.

| File | Lines | Purpose |
|---|---|---|
| `python-engine/kite_client.py` | +260/-120 | New `_intraday_cache_gate_evaluate` helper, `_create_intraday_cache_by_token_table`, `_INTERVALS_EXEMPT_FROM_FORMING_FILTER`, `_interval_minutes("day") = 1440`, `get_intraday_by_token` rewritten with HIT/MISS/writing-through. `get_intraday` refactored to use the shared gate. |
| `python-engine/intraday_cache_diagnostic.py` | +85/-15 | `BY_TOKEN_CALLER_SITES` (back-compat alias `UNCACHED_CALLER_SITES`), `cache_by_token_row_counts`, `cache_by_token_interval_breakdown`, `run_diagnostic` extended with `by_token_*` keys, `_render_conclusion` shows both tables side-by-side, `__all__` updated. |
| `python-engine/tests/test_intraday_cache_by_token_semantics.py` | NEW, 13 tests | Five test classes covering all four explicit semantics + MISS-path contract + cross-path isolation + reproducibility. |

## The four §12 semantics, now on the by-token path

Same shape as H4.A's by-symbol path, via the shared
`_intraday_cache_gate_evaluate` helper:

| §12 property | Implementation | Operator knob |
|---|---|---|
| Instrument | PRIMARY KEY `(instrument_token, interval, datetime)` | (n/a) |
| Interval | Same PRIMARY KEY | (n/a) |
| **Completed-bar cutoff** | `datetime < to_datetime` filter | `INTRADAY_CACHE_INCLUDE_FORMING=False` (daily exempt) |
| Freshness | `last_cached_dt >= to_dt_obj - interval_mins - freshness_seconds` | `INTRADAY_CACHE_FRESHNESS_SECONDS=0` |
| (Implied) Min-candles floor | Re-checked after forming-bar filter | `INTRADAY_CACHE_MIN_CANDLES=4` |

**Defaults preserve the pre-H4.B behaviour for the by-symbol path
and ship strict semantics for the by-token path.** Daily interval is
exempt from the forming-bar filter because today's daily candle is
not "forming" in the §12 sense.

## Real bugs found and fixed during H4.B

1. **`_interval_minutes("day")` raised `ValueError`.** Pre-H4.B
   never called this helper, so the bug was hidden. The H4.A
   refactor introduced the call, exposing it. Production callers
   in `partner_orchestrator.py` use `interval="day"` for
   `realized_vol_20d` — they would have crashed on first call
   in PROD on 2026-09-14. **This was a real latent PROD
   blocker.** Fixed by adding `day → 1440` to
   `_interval_minutes`.
2. **Mock `raise_for_status` mismatch** in tests: production
   `httpx.HTTPStatusError` carries `e.response.status_code`;
   the original tests used a bare `Exception`. Fixed by using
   `httpx.HTTPStatusError` with proper request/response args.

## Senior-dev design choices

1. **Shared gate via `_intraday_cache_gate_evaluate`.** Pre-H4.B
   the gate logic was inline in `get_intraday` only; H4.B
   extracts it to a module-level helper that both paths call.
   Single source of truth — §12 semantics can never drift
   between the by-symbol and by-token paths.
2. **H4.A refactored, not duplicated.** The H4.A path was
   surgically rewritten to call the shared gate. All 13 H4.A
   semantics tests still pass byte-for-byte; the debug log
   events keep their legacy `ticker` field while gaining
   `source_kind`/`source_id` for cross-cutting diagnostics.
3. **Daily interval exempt.** A daily candle has no "forming"
   problem in the cache sense; today's daily candle IS today's
   candle. Forcing the forming-bar exclusion on daily would
   drop today's row entirely (`datetime == to_datetime`). The
   exempt set is `_INTERVALS_EXEMPT_FROM_FORMING_FILTER`.
4. **MISS path failure contract preserved.** Returns empty
   DataFrame on failure (not raise). The 5-attempt retry loop
   with `2 ** attempt` backoff on 429/503/504 is preserved.
   Write-through uses `INSERT OR REPLACE` on the PRIMARY KEY
   so retries are idempotent.
5. **Diagnostic extended, not duplicated.** Same render
   function with `by_token_row_counts` and
   `by_token_interval_breakdown` keys. Operators see
   by-symbol and by-token stats side-by-side.
6. **No schema change to existing `intraday_cache`.** New
   table is created lazily on first `get_intraday_by_token`
   call.

## Verification

| | Before H4.B | After H4.B |
|---|---|---|
| **Python suite** | 2,991 pass | **3,004 pass** (+13 H4.B) |
| **Time** | 141.78s | 141.41s |
| **Skipped** | 4 | 4 |
| **Warnings** | 39 | 39 (no new) |
| **Existing kite_client tests** | 28 pass | 28 pass |
| **H4.A semantics tests** | 13 pass | 13 pass (refactored to use shared gate) |
| **H3 diagnostic tests** | 26 pass | 26 pass (extended, still pass) |

Stable across the full-suite rerun. The H4.B file alone runs
in 6.62s.

## Self-corrections during H4.B

1. **`_interval_minutes("day")` regression** — the helper
   didn't accept `"day"`. Caught by
   `TestCompletedBarCutoffByToken::test_daily_interval_exempt`.
   Fixed at the source.
2. **`raise_for_status` mock mismatch** — tests used a bare
   `Exception`; production uses `httpx.HTTPStatusError`.
   Caught by `TestMissPathContract::test_miss_returns_empty_on_api_failure`
   and `test_retry_on_429`. Fixed by using the real
   `httpx.HTTPStatusError`.

## Next H phases

- **H5 (dashboard readiness reasons)** — deferred. Per the
  user's direction, this is the active task starting now.
