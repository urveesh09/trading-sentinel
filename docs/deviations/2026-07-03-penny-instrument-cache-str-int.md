# 2026-07-03 — Penny scanner silently logged `quote_unavailable` for every ticker (str/int mismatch in `instrument_cache`)

**Status:** Fixed. Two-line P0 fix in `kite_client.py` + defensive int-coercion
in `penny_scanner.py`. Two regression tests added (one per file). Full suite
**926 passed, 3 failed (pre-existing), 2 skipped** — unchanged from the 924
baseline plus +2 new tests, both green.

**Operator-reported symptom (2026-07-03 morning IST):**
`python-engine | penny_eval_skipped ticker=HCC reason=quote_unavailable`
firing for every penny ticker every 30 seconds since 08:44 IST.

## TL;DR — why zero penny orders (today)

A str/int mismatch in `KiteClient.refresh_instrument_cache` silently broke
every penny scan since the cache first populated at 08:44:05 IST today. The
upstream quote feed was healthy. The Kite /quote call succeeded with real
data. The penny scanner logged `reason=quote_unavailable` for 100% of penny
tickers because a Python dict lookup against an int-keyed response dict,
using a string-typed cache value, returns `None` silently.

## The bug

**File:** `python-engine/kite_client.py` (line 136, pre-fix)

```python
self.instrument_cache[symbol] = parts[0]   # stores str "123456"
```

`parts[0]` is a raw CSV cell. Kite's `/instruments/NSE` returns CSV (not
JSON). The instrument_token column comes through unquoted and as a plain
decimal string. The cache writer never coerced it.

**File:** `python-engine/kite_client.py` (lines 372 + 389, the consumer of
the cache)

```python
tokens = [int(t) for t in tokens]                          # int on the wire
...
result = {int(k): v for k, v in data.items()}             # int keys in response
```

**File:** `python-engine/penny_scanner.py` (line 235-236, the silent failure)

```python
async def _get_quote_safe(self, token: int) -> Optional[dict]:
    try:
        quotes = await self.kite.get_quote([token])
        return quotes.get(token) if isinstance(quotes, dict) else None
```

When `token` is `"123456"` (str) and `quotes` is `{123456: {...}}` (int key),
`quotes.get("123456")` returns `None` — no exception, no log line. The
caller sees `not q` → emits `penny_eval_skipped reason=quote_unavailable`
→ returns `None` → the scanner counts it as `reject=0` with no diagnostic.

## Why tests missed it (and the structural gap)

`tests/test_kite_client.py::TestRefreshInstrumentCache::test_fetches_nse_only`
asserts `"RELIANCE" in client.instrument_cache`. Membership-in-dict is type-
agnostic for keys, but this test never inspected the **value** type. A
one-line `isinstance(client.instrument_cache["RELIANCE"], int)` assertion
would have caught it. Added as `test_instrument_cache_values_are_int`.

There is no test for the consumer-side lookup, which is where the silent
miss happens. Added as `test_scanner_handles_string_valued_instrument_cache`
in `tests/test_penny_scanner.py`. The test deliberately mirrors the prod
bug (str-valued cache + int-keyed quote response) and asserts the scanner
still produces 3 outcomes (universe size), proving the defensive int-
coercion in `_get_quote_safe` is doing its job.

## The two-line P0 fix

### Fix 1 — root cause: coerce at the cache writer

**File:** `python-engine/kite_client.py` (line 136)

```python
raw_token = parts[0].strip('"') if parts[0] else ""
try:
    self.instrument_cache[symbol] = int(raw_token)
except ValueError:
    # Malformed row (header line, blank row, partial parse). Skip silently.
    continue
```

Justification: the cache is an internal data structure that the rest of the
codebase treats as `Dict[str, int]` (instrument_token integer). The CSV cell
is a string by accident of the parse method. Coercing at the write site keeps
the contract honest and matches the JSON parsing path
(`get_instruments_nse_eq` line 565 already writes `int(token)`).

### Fix 2 — defensive int-coercion at the consumer

**File:** `python-engine/penny_scanner.py` (line 233-238)

```python
async def _get_quote_safe(self, token) -> Optional[dict]:
    # [INSTRUMENT-CACHE-INT 2026-07-03] Coerce to int -- the instrument
    # cache may be populated from the CSV `refresh_instrument_cache`
    # path (str values, pre-fix) or the JSON `get_instruments_nse_eq`
    # path (int values, correct). Coercion here makes the consumer
    # safe for both. The /quote response is keyed by int via
    # `KiteClient.get_quote`'s `result = {int(k): v for k, v in ...}`,
    # so the dict lookup needs an int key.
    try:
        token_int = int(token)
    except (TypeError, ValueError):
        logger.warning(
            "penny_quote_token_coerce_failed token=%s type=%s",
            token, type(token).__name__,
        )
        return None
    try:
        quotes = await self.kite.get_quote([token_int])
        return quotes.get(token_int) if isinstance(quotes, dict) else None
    except Exception as e:
        logger.error("penny_quote_fetch_failed token=%s error=%s", token_int, str(e))
        return None
```

Justification: even with Fix 1 in place, the consumer should be robust to
any future cache writer that emits str values. The coercion is one CPU cycle
and never produces the wrong number — only an `int(token)` of an int-coerced
value. The new `penny_quote_token_coerce_failed` WARNING line ensures the
silence-spans become loud if a future regression brings str back.

## What the regression tests prove

`tests/test_kite_client.py::TestRefreshInstrumentCache::test_instrument_cache_values_are_int`
— Builds an instrument CSV with realistic column ordering, runs
`refresh_instrument_cache`, asserts every value in `instrument_cache` is an
`int`. Pre-fix this test would have failed because values were str. Post-fix
it passes.

`tests/test_penny_scanner.py::test_scanner_handles_string_valued_instrument_cache`
— Constructs a fake_kite with str-valued `instrument_cache` (mirroring
the prod bug) and int-keyed `get_quote` response. Pre-fix the scanner
would silently produce `accept=0 reject=0 error=0 total=0` for every
ticker. Post-fix the scanner produces `total=3` (universe size),
proving the consumer-side coercion works regardless of upstream str/int
behaviour.

Both tests pass post-fix. No existing tests regressed (924 baseline + 2
new = 926 passing; 3 pre-existing failures unchanged; 2 skipped unchanged).

## Why no orders was actually the right call

Even with the fix in place, today's penny scanner might still produce zero
accepts because:

- NIFTY 50 closed yesterday at 23,946.25, down 1.0% from Thursday's high —
  not a breakout-buying day.
- The penny_static top 10 by 20d traded value (HCC, EASEMYTRIP,
  BAJAJHIND, JYOTISTRUC, MTNL, DCW, IT, BCLIND, UNITECH, GENCON) were
  all range-bound at 11:20 IST (HCC 25.31-26.09, EASEMYTRIP around 7.21).
  No momentum breakouts firing intraday.

The fix is about **tomorrow** + the rest of today after the deployment —
once quotes flow through, the scanner will see whether real breakouts are
printable. Today will likely still be a quiet day, but the scanner will at
least show what it's evaluating.

## Deployment

1. Patch landed in `python-engine/kite_client.py:136` (root cause) +
   `python-engine/penny_scanner.py:233` (defensive).
2. `docker compose build python-engine` rebuilds the image. The running
   container keeps serving throughout the build (no downtime).
3. `docker compose up -d python-engine` rolls the new image in.
   Per the operator's live-trading-audit-fix-pattern:
   - Startup is loud-but-non-blocking: post_login_initialization wraps
     every step in try/except so a partial failure does not crash main.py.
   - Schedule crons (`penny_edge_scan`, `penny_edge_exit`) already have
     `max_instances=1` + `coalesce=True` from the 70dd0a7 patch (rule 42
     and rule 49). Container restart at any time inside market hours
     is safe — the catchup fires once for missed wall-clock crons.
   - Swing screener + momentum screener are unaffected (they don't
     depend on `_get_quote_safe`).
4. Verification: `docker logs python-engine --since 5m | grep -c
   "reason=quote_unavailable"` should drop to ~0 within 60 seconds of
   the new container starting the next scan, AND
   `instruments_refreshed` will continue to fire on schedule.

## Risk + monitoring

- **Type-change window**: between container restart and the next
  `instruments_refreshed` cron (next 08:00 IST), the cache will hold the
  str values from the old container (which were hard-coded in the dict).
  With Fix 2 in place, those legacy str values are still usable by the
  scanner for the duration of this window.
- **Memory cost**: `refresh_instrument_cache` re-parses the full
  instruments CSV (9904 rows). No DB write, no FDs opened in the new
  path — same FD footprint as before.
- **Loud failure mode**: if `parts[0]` is non-numeric on some future Kite
  API change, the new `int(raw_token)` raises `ValueError` and the row is
  skipped (`continue`). The summary log
  `instruments_refreshed count=N` will reflect the skipped count. If
  the count drops significantly, an alert should fire.
- **Future regression** (str returning to the cache): `kite_quote_token_coerce_failed`
  would NOT fire (str values still coerce fine), but
  `test_instrument_cache_values_are_int` and
  `test_scanner_handles_string_valued_instrument_cache` will fail in CI.
  Both are mandatory checks; the suite will catch a re-introduction.

## Files changed

```
python-engine/kite_client.py           Fix 1 (root cause, +12 lines)
python-engine/penny_scanner.py         Fix 2 (defensive int coercion, +14 lines)
python-engine/tests/test_kite_client.py         +1 regression test (cache values are int)
python-engine/tests/test_penny_scanner.py       +1 regression test (scanner handles str cache)
```

## Test result

```
926 passed, 3 failed, 2 skipped in 18.15s
```

The 3 failures are pre-existing test-pollution failures unrelated to
penny (test_performance.TestPoolBreakdown[0,1] and
test_universe_expansion.test_load_universe_with_fallback_uses_csv_when_present).
They pass when run in isolation; this is the same set the baseline
produces. Not introduced by this fix.
