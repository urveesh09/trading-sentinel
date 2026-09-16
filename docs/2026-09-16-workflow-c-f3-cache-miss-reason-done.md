# Workflow C.F3 — surface `cache_miss_reason` in kite_client (F-3 from prod audit)

## Source

Per the 2026-09-16 production deep audit F-3:
> 🟡 F-3 (MED, $): `intraday_cache` 0% hit rate — chronic finding, now escalated
> - **Evidence:** 54 `data_fetch` events today, 54 `cache_miss`, 0 `cache_hit`.
> - Per skill recipe pitfall 41: "When this appears again, treat it as HIGH ($)." This is the **4th consecutive audit** with 0% cache hit rate. Every per-ticker price request hits Kite — will hit rate limits at scale.
> - **Recommended action:** Investigate the cache write path. Either (a) the cache key has drifted (writer/reader mismatch), (b) the cache isn't being written at all (writer broken), or (c) the TTL is too short.

The audit's "recommended action" is investigation, not a fix. The bounded dev-side fix is **observability**: surface WHICH condition caused the cache_miss so the next audit can attribute the 0% rate to one of:
1. `no_rows` — empty cache (writer broken).
2. `insufficient_rows` — date window mismatch.
3. `date_window_miss` — last cached date < requested to_date.
4. `freshness_exceeded` — `(now - last_fetched) >= 86400` (TTL too short).
5. `timestamp_parse_failed` — `fetched_at` couldn't be parsed.

## What landed

| File | Type | Purpose |
|---|---|---|
| `python-engine/kite_client.py` | source (extended) | 5-reason classification in `get_historical`; new `cache_miss_reason` field on the `data_fetch` log line |
| `python-engine/tests/test_kite_client_cache_miss_reason_f3.py` | test (new) | 6 tests pinning the reason-classification contract |
| `docs/2026-09-16-workflow-c-f3-cache-miss-reason-done.md` | doc (new) | This file |

## The shift in defensive posture

Before this slice, the `data_fetch` event logged `event_type=cache_miss` (or `cache_hit`) with no diagnostic context. The audit observed 0% hit rate but couldn't tell whether:
- The cache writer is broken (every ticker triggers `no_rows`).
- The TTL is too aggressive (every ticker triggers `freshness_exceeded`).
- The date window is misaligned (every ticker triggers `date_window_miss`).

After this slice, the `data_fetch` event carries `cache_miss_reason=<one of 5>`. The next audit's diagnostic query becomes:

```sql
SELECT cache_miss_reason, count(*) FROM data_fetch_events
WHERE event_type='cache_miss' AND timestamp >= '2026-09-17'
GROUP BY cache_miss_reason
```

Result: actionable signal. If `freshness_exceeded` dominates, the TTL is the culprit. If `no_rows` dominates, the writer is broken. The audit can now ATTRIBUTE.

## Key design choices

- **Backward compatible**: `cache_miss_reason` is a new KEY on the existing `cache_miss` event. Existing log consumers that don't know the field ignore it.
- **Defensive at each step**: every entry point that could cause a miss has its own reason; no "unknown" bucket unless something genuinely novel happens.
- **`timestamp_parse_failed` is included** even though it's rare (a schema drift in `fetched_at` format would silently flip every ticker to cache miss — exactly the audit's `no_rows` panic mode). Including it gives operators a smoke signal.
- **All 5 reasons are testable** — each maps to a specific seeded-DB state in the test fixture.
- **The reason flows through `record_collection_run`**: it's a journal annotation, not just a log line.

## Test discipline

6 tests pin the contract:
- `test_no_rows_logs_no_rows_reason`: empty cache → `no_rows`.
- `test_insufficient_rows_logs_reason`: 2 rows for 60-day window → `insufficient_rows`.
- `test_date_window_miss_logs_reason`: 30 rows up to 2025-01-30, request to 2025-02-15 → `date_window_miss`.
- `test_freshness_exceeded_logs_reason`: 30 rows with `fetched_at = 2 days ago` → `freshness_exceeded`.
- `test_timestamp_parse_failed_logs_reason`: malformed `fetched_at` → `timestamp_parse_failed`.
- `test_cache_hit_does_not_emit_cache_miss`: 65 fresh rows → no cache_miss log.

The tests use `monkeypatch` to patch `kite_client.logger` with a MagicMock — the kite_client uses `structlog` (not stdlib logging), so pytest's `caplog` (which captures stdlib logging) does not capture structlog events. The patched logger records `.info()` / `.debug()` / `.error()` calls on a MagicMock's `.side_effect`, which the tests inspect.

## Defensive regression

| Test file | Tests | Δ |
|---|---|---|
| `test_kite_client_cache_miss_reason_f3.py` | 6 | +6 (new file) |
| `test_kite_client.py` | 28 (incl. 1 skip) | 0 |
| `test_kite_client_methods.py` | unchanged | 0 |

74/74 PASS across `test_kite_client*.py` + `test_research_quote_runtime_cap_f2.py` + `test_research_archive.py`. Zero regressions.

## What this does NOT solve

- The audit's F-3 ask is "investigate the writer" — this slice surfaces observability but does NOT investigate. The next audit will run the SQL and attribute the cause.
- The 86400-second freshness threshold is unchanged. If the audit reveals `freshness_exceeded` is dominant, a follow-up slice could make it configurable.
- The 80% coverage floor (`_min_rows = max(2, _expected_td * 0.8)`) is unchanged. If `insufficient_rows` dominates, a follow-up slice could tune it.

## Critical invariants preserved

- `get_historical` public API unchanged.
- `ohlcv_cache` table schema unchanged.
- `data_fetch` event still emits `event_type=cache_miss` / `cache_hit` (existing log consumers see no breaking change).
- The LOG-HYGIENE discipline from 2026-07-17 is preserved: cache hits stay at `debug` level (not `info`).
- The 28 existing kite_client tests pass without modification.

## Operator runbook

After deploy to PROD:

1. The next audit's diagnostic query becomes actionable:
   ```sql
   SELECT cache_miss_reason, count(*) FROM data_fetch_events
   WHERE event_type='cache_miss' AND timestamp >= '2026-09-17'
   GROUP BY cache_miss_reason
   ```

2. Expected outcomes:
   - **All `freshness_exceeded`**: TTL is the bottleneck. Lower it.
   - **All `date_window_miss`**: scanner window is misaligned with the cache write schedule. Adjust scan cadence.
   - **All `no_rows`**: cache writer is broken. Investigate the kite_client writer path.
   - **All `timestamp_parse_failed`**: schema drift in `fetched_at` — smoke signal.

3. The bounded fix is purely diagnostic. No cache behaviour changed.

## What's still open on the audit

- F-2 (scheduler cascade-skip) — DONE in this session (separate commit).
- F-4 (agent silent) — by-design (no signals accepted).
- F-5 (shadow evaluation) — healthy.
- F-6 through F-10 — RESOLVED today.
- F-11 (partner hedge) — operator-owned.
- F-3 (intraday_cache 0% hit rate) — observability DONE; root-cause investigation pending operator SQL.

PROD untouched. Dev only.
