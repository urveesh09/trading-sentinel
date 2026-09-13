# H4.B — Proposed cache for ``get_intraday_by_token`` (DEFERRED)

## Status

**PROPOSAL — NOT IMPLEMENTED.** This is a one-pager written
during H4 (cache-add for ``get_intraday``, the symbol-keyed path).
The ``get_intraday_by_token`` path is *intentionally* uncached
today; this doc captures the design work for an operator
sign-off gate. No code changes are proposed for this slice.

## Why H4 did not touch ``get_intraday_by_token``

The path is documented in ``kite_client.py`` as:

> "No sqlite caching: the F&O signal loop re-reads the full session
> every tick and today's candles change every 5 minutes, so a cache
> would only serve stale bars."

That docstring is correct **for the current F&O call shape**. The
F&O signal loop calls ``get_intraday_by_token`` once per token per
5-minute tick and re-reads the FULL session (from start-of-day up
to the current minute). Two facts make a cache hazard-prone:

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

## What H4 left in place

The H4 cache-semantics work targeted ``get_intraday`` (symbol-keyed)
only. The new explicit knobs:

| Knob | Default | Purpose |
|---|---|---|
| ``INTRADAY_CACHE_FRESHNESS_SECONDS`` | 0 | Leniency budget on the existing freshness gate |
| ``INTRADAY_CACHE_INCLUDE_FORMING`` | False | §12 completed-bar cutoff (excludes forming candles from the returned set) |
| ``INTRADAY_CACHE_MIN_CANDLES`` | 4 | Minimum candles for a HIT (existing VWAP floor, made explicit) |

The by-token path remains untouched. The existing
``get_intraday_by_token`` docstring stays accurate.

## What a future H4.B would need to design

For an operator to sign off on caching ``get_intraday_by_token``,
the following must be specified **before** any code is written:

1. **Forming-bar exclusion policy**: is the cache HIT path also
   required to exclude the most recent forming candle? If yes, the
   same §12 filter applies. If no, the operator must accept that
   F&O signals may briefly consume a forming candle.
2. **Per-interval key**: ``get_intraday`` is keyed by
   ``(ticker, interval, datetime)``. ``get_intraday_by_token`` is
   keyed by ``(instrument_token, interval, datetime)``. The
   existing primary key is per-ticker; an instrument_token-keyed
   cache would be a new table or a new column on the existing
   table.
3. **Rate-limit impact**: how many ``get_intraday_by_token`` calls
   per minute per day does F&O + partner make today? A cache that
   saves <10% of round-trips is not worth the design complexity.
4. **Warming strategy**: the existing ``get_intraday`` cache warms
   on first miss + write. The F&O loop calls ``get_intraday_by_token``
   every 5 minutes; warming is automatic but the cache would
   always be one tick behind Kite.

## Operator decision (required before H4.B code)

| Decision | Options | Default if no answer |
|---|---|---|
| Forming-bar policy | exclude (matches §12) / include | exclude |
| Key column | instrument_token / extend primary key | instrument_token (new index, no schema change) |
| Rate-limit threshold | cache if savings ≥ N% | ≥25% |
| Warming | lazy (current pattern) / eager (cron) | lazy |

Once those four are settled, a follow-up H slice can implement the
cache under the same H4 contract: ``(instrument, interval,
completed-bar cutoff, freshness)``.

## Acceptance criteria for any future H4.B implementation

- No change to ``get_intraday_by_token`` callers' contract.
- Cache HIT preserves §12 forming-bar exclusion by default.
- Cache key is **never** mixed with the symbol-keyed path.
- Whole-engine test count grows by ≥10 with no regressions.
- New diagnostic (``intraday_cache_diagnostic``) reports
  hit-rate, miss-rate, and freshness-window-staleness for the
  by-token path independently of the symbol-keyed path.
