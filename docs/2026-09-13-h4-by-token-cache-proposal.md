# H4.B — Cache-add for ``get_intraday_by_token``

## Status

**SHIPPED** — `bfb42ac`. This was originally a one-pager written
during H4 (cache-add for ``get_intraday``, the symbol-keyed path)
proposing the by-token cache-add. The proposal's four operator
decisions were resolved as:

| Decision | Resolution |
|---|---|
| Forming-bar policy | **exclude** (matches §12) for intraday; **exempt** for daily (see `_INTERVALS_EXEMPT_FROM_FORMING_FILTER`) |
| Key column | New `intraday_cache_by_token` table (sibling of `intraday_cache`) keyed on `(instrument_token, interval, datetime)` |
| Rate-limit threshold | N/A — the four semantics ship unconditionally. Lazy warming on first miss + write. |
| Warming | Lazy (current pattern) |

## What landed

- New `_intraday_cache_gate_evaluate` helper at module scope
  in `kite_client.py`. The four §12 semantics in one place:
  instrument, interval, completed-bar cutoff, freshness. Both
  `get_intraday` and `get_intraday_by_token` call it.
- H4.A's `get_intraday` was refactored to call the helper; all
  13 H4.A semantics tests still pass byte-for-byte.
- New `intraday_cache_by_token` table: PRIMARY KEY
  `(instrument_token, interval, datetime)`, F&O-only `oi`
  column. Created lazily on first call.
- HIT path filters by completed-bar cutoff (default ON),
  re-checks `min_candles` after the filter, falls through to
  API on miss.
- MISS path: 5-attempt retry loop with `2 ** attempt` backoff
  on 429/503/504, write-through to `intraday_cache_by_token`
  via INSERT OR REPLACE on the PRIMARY KEY (idempotent on retry).
- `_interval_minutes("day")` returns 1440 (was raising
  `ValueError`; `partner_orchestrator.py:1578` etc. call with
  `interval="day"` for `realized_vol_20d` — pre-fix was a
  latent production crash).
- `_INTERVALS_EXEMPT_FROM_FORMING_FILTER = {"day"}` exempts
  daily from the forming-bar filter (today's daily candle is
  not "forming" in the §12 sense).

## Diagnostic extension

`intraday_cache_diagnostic.py` now reports both tables. New
`cache_by_token_row_counts` / `cache_by_token_interval_breakdown`
query the new table. `_render_conclusion` shows by-symbol and
by-token stats side-by-side. `BY_TOKEN_CALLER_SITES` supersedes
`UNCACHED_CALLER_SITES` (kept as a back-compat alias).

## Verification

- 13 new tests in `test_intraday_cache_by_token_semantics.py`
  all passing.
- Whole-engine: 2,991 → 3,004 passed / 4 skipped / 39 warnings.
  No regressions.

## Real bugs found and fixed during H4.B

1. **`_interval_minutes("day")` raised `ValueError`**: pre-H4.B
   never called this helper, so the bug was hidden. The H4.A
   refactor introduced the call, exposing it. Production callers
   in `partner_orchestrator.py` use `interval="day"` for
   realised-vol — they would have crashed on first call.
   Fixed by adding `day → 1440` to `_interval_minutes`.
2. **Mock `raise_for_status` mismatch**: production
   `httpx.HTTPStatusError` carries `e.response.status_code`;
   my mocks used a bare `Exception`. Fixed by using
   `httpx.HTTPStatusError` with proper request/response args.

## Original proposal text (preserved for context)

The sections below reproduce the original proposal text from
the H4 commit (`d1d6e15`), kept here for historical context
so a future agent can see what was proposed vs. what shipped.
The proposal's "operator decision required" gate was resolved
on 2026-09-13 in favour of shipping with the four defaults
above (the proposal's own "default if no answer" column).

### Why H4 did not touch ``get_intraday_by_token``

The path was documented in ``kite_client.py`` as:

> "No sqlite caching: the F&O signal loop re-reads the full session
> every tick and today's candles change every 5 minutes, so a cache
> would only serve stale bars."

That docstring was correct **for the current F&O call shape**. The
F&O signal loop calls ``get_intraday_by_token`` once per token per
5-minute tick and re-reads the FULL session (from start-of-day up
to the current minute). Two facts made a cache hazard-prone:

1. **Forming vs. completed candles**. Every 5-minute candle is
   forming from ``t`` to ``t + 5min``; a Kite round-trip at minute
   ``t + 2min`` returns a partial candle. Caching that partial
   candle and serving it on the next tick would mean the F&O
   signal is computing VWAP against a half-formed candle -- a
   §12 "do not mix mutable forming bars with completed historical
   bars" violation.
2. **Re-reads the full session**. The call is *not* a delta
   request; it's a full-window request. A cache HIT would need to
   return every candle in the requested window, including the
   most recent. The forming/completed discrimination becomes
   operational, not theoretical.

H4.B resolves both concerns: the §12 forming-bar filter excludes
forming candles from the HIT path, so a HIT serves strictly
completed candles.

### Operator decisions (resolved)

| Decision | Options | Resolution | Default if no answer |
|---|---|---|---|
| Forming-bar policy | exclude (matches §12) / include | **exclude** | exclude |
| Key column | instrument_token / extend primary key | **instrument_token** (new sibling table, no schema change to existing) | instrument_token (new index, no schema change) |
| Rate-limit threshold | cache if savings ≥ N% | N/A — unconditional, lazy warming | ≥25% |
| Warming | lazy (current pattern) / eager (cron) | **lazy** | lazy |

### Acceptance criteria (met)

- ✅ No change to ``get_intraday_by_token`` callers' contract.
- ✅ Cache HIT preserves §12 forming-bar exclusion by default.
- ✅ Cache key is **never** mixed with the symbol-keyed path
  (separate tables).
- ✅ Whole-engine test count grew by ≥10 with no regressions
  (+13 tests in `test_intraday_cache_by_token_semantics.py`).
- ✅ Diagnostic (``intraday_cache_diagnostic``) reports
  per-table counts and breakdowns independently for the
  by-token path and the symbol-keyed path.

