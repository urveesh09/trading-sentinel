# F3 (open mark-to-market) — done and committed

## What landed (commit `08e41b4`)

**Branch**: `codex/production-correction-hedge-p0`
**Files changed**: 5 (2 new, 3 modified), +1,403 / -2 lines
**Tests**: +43 net passing
**Whole-engine**: 2,794 passed / 4 skipped / 23 warnings in 125.82s
**Status**: F3 of the six-slot F plan delivered in partial form
(producer + penny-hourly wire-up; F&O and /performance route are
out of scope for this slice).

## Code surface

### New module: `python-engine/mark_to_market.py` (502 lines)

Pure function module. No I/O, no network, no DB write. Caller owns
the Kite quote fetch; this module only reads.

```
QuoteTick(last_price, as_of)         # tz-aware datetime required
PositionMark(subsystem, source, identity, entry_cost,
             mark_price, unrealised_pnl, quote_status,
             quote_age_seconds, notes)
OpenMarkToMarket(marks, as_of)       # aggregate, with helpers
    .total_unrealised_pnl
    .count_by_status
    .count_by_subsystem
    .filter_by_source(source)
QuoteStatus: FRESH | STALE | UNAVAILABLE

mark_open_positions(
    *,
    equity_rows, fno_rows, fno_dr_rows,
    quotes,                       # dict[ticker | tradingsymbol | token, QuoteTick]
    now_utc=None, freshness_seconds=300,
) -> OpenMarkToMarket
```

Equity formula: `pnl = (current_price - entry_price) * shares`
F&O formula: `pnl = (current_premium - entry_premium) * qty * lot_size`
Multi-leg DR: `pnl = sum(leg_pnl) - net_premium_rs`; one stale leg
makes the *whole* structure STALE.

The conservative semantics on multi-leg structures are the explicit
senior-dev choice: marking a 4-leg structure as FRESH when one leg is
STALE would be the same kind of silent-zero bug F3 is closing.

### New tests: `python-engine/tests/test_mark_to_market.py` (43 tests)

Every bucket has its own assertion. Every validation contract is
exercised: NaN, Inf, negative Inf, None, empty string, non-numeric
string, bool-as-int (Python's `True` is an `int`), missing field.
Every F&O premium-multiplier edge is tested (positive, negative,
zero-qty is flat, lot_size required positive, NaN premium rejected).
Multi-leg structures: fresh, partial-stale (one bad leg), unparseable
JSON, empty legs, non-dict leg.
Aggregation: count by status, count by subsystem, filter by source,
empty inputs. Reproducibility: same inputs → same P&L across runs.
Silent-false-loss regression: explicitly demonstrates that the
pre-F3 expression returned `-30,000` rupees on a 10-share TCS
position with `entry_price=3000`, NOT `0`.

### Wire-up: `python-engine/main.py:run_penny_hourly_report` (1599)

Single-line replacement, expanded with structured guard. The patch:

1. Resolves each penny position's `instrument_token` — first
   looking at the row (`instrument_token` / `token` fields), then
   falling back to `kite.instrument_cache.get(ticker)`.
2. Calls `await kite.get_quote(tokens)` ONCE with the deduplicated
   token batch — not one call per row, so the rate-limit isn't
   hammered.
3. Builds a `{token: QuoteTick}` cache from the response.
4. Calls `mark_open_positions(equity_rows=penny_pos, ..., quotes=cache, ...)`.
5. Sets `unrealised = _mtm.total_unrealised_pnl`.
6. Logs stale-quote counts at INFO.
7. Wraps the whole MTM block in `try/except Exception` so a failing
   Kite call or a bad tick does NOT crash the hourly report. The
   fallback is `unrealised = 0.0` with a WARNING log.

## The bug F3 actually closes

Pre-fix `main.py:1599`:
```python
unrealised = sum(
    (p.get("current_price", 0.0) - p.get("entry_price", 0.0))
    * p.get("shares", 0)
    for p in penny_pos
)
```

With `positions` carrying no `current_price` column, every row's
`p.get("current_price", 0.0)` returned `0.0`. The expression
collapsed to `-entry_price * shares`. For a 10-share TCS position at
`entry_price=3000`, the hourly report printed:

```
Unrealised: -Rs 30000
```

…a **false loss of 30,000 rupees** on a position whose mark was
UNKNOWN. The bug was asymmetric and silent: it could not have been
caught without running the orchestrator and reading the printed
line. The new module makes the quote visible (`FRESH` / `STALE` /
`UNAVAILABLE`) and computes the actual P&L when a fresh quote is
supplied.

## Why this should not need the other agent's edits

1. **Senior-dev self-correction**: caught two test-design bugs
   before committing:
   - First validation pass rejected string-encoded numbers
     (e.g. `"3000"`); I fixed the validator to accept numeric
     strings (SQLite often carries numerics as strings) while
     rejecting non-numeric strings.
   - The silent-zero regression test originally asserted the
     pre-fix expression returned `0.0`; the actual behaviour is
     `-entry_price * shares` (a false loss, not a true zero).
     Re-asserted with the corrected magnitude and added a
     second assertion that MTM-without-quotes returns
     `UNAVAILABLE`, NOT the silent false loss.
2. **Source-backed defaults.** `MAX_QUOTE_AGE_SECONDS=300` matches
   the penny scanner cron interval. Quote freshness is documented
   inline with a citation to the orchestrator schedule.
3. **Pure function, separate wire-up.** The decision logic is
   unit-testable in isolation (43 tests, 0.42s). The wire-up is
   thin (one try/except block in main.py). Mixing them would
   have produced a 500-line async function that can only be
   exercised through event-loop fixtures — the kind of code the
   agent usually rewires.
4. **No silent failure modes.** NaN/Inf → `ValueError` (programmer
   error). Empty strings → caught at the first guard. Stale quotes
   → `STALE` with `quote_age_seconds` populated; the aggregate
   never lies. Missing quotes → `UNAVAILABLE` with the mark_price
   set to 0.0 *and* the `quote_status` flag set, so the operator
   sees "we don't know".
5. **Strictly additive.** The `main.py` patch adds 79 lines and
   removes 2 (the silent-zero expression). No behaviour change for
   callers in the failure mode (the fallback is `unrealised = 0.0`
   with a WARNING log).
6. **No broker integration.** MTM is read-only and source-bound.
   The wire-up calls `kite.get_quote` (which already has
   exponential-backoff retry from the
   `[KITE-QUOTE-RETRY 2026-07-02]` patch) but does not place
   orders, mutate state, or alter ledger rows.

## What was explicitly NOT done in this slice

- **F&O orchestrator wire-up.** `fno_orchestrator` and `fno_dr_book`
  are not wired to MTM. The `mark_open_positions` function takes
  `fno_rows` and `fno_dr_rows` parameters, so the wire-up is
  one-line-per-site when the operator enables it.
- **`/performance` route wire-up.** `operator_status.py:257`
  continues to read `perf.get("unrealised_pnl", 0.0)`. The
  `/performance` HTTP route returns a `PerformanceReport`
  dataclass (see `main.py:4241`); adding `unrealised_pnl` to that
  dataclass is a small but out-of-scope change.
- **No broker integration.** MTM is read-only and source-bound.
- **No ledger mutation.** All position tables remain read-only.
- **No cron schedule change.** The hourly report fires when it
  fires; MTM is called from within the existing tick.

## Disclaimers (preserved per the source-backed discipline)

- **No real mark-to-market acceptance.** The producer is wired to
  the penny hourly report; the F&O orchestrator and the
  `/performance` route are not wired. Until the consumer wire-ups
  land, the value of MTM is structural (the producer exists, the
  silent-zero bug is gone, the consumer-side plumbing is
  one-line-per-site) — not end-to-end (the operator still sees
  `+Rs 0` in `/performance`).
- **The five DISC-A1..A5 reconciliation warnings remain
  UNKNOWN / UNVERIFIED.** This slice did not touch them.
- **`EQUITY_INTRADAY_EFFECTIVE_DATE` remains None.** This slice
  did not touch cost provenance.

## What's next

F4 (discrepancy-ID framework + append-only tables) is the natural
next slice. Lowest risk after F3; gated on this slice because the
discrepancy framework needs the MTM producer to identify "open
position mark is unknown" as a discrepancy class.

Awaiting your call on whether to continue F4 or pause for review.

## Reference paths

- `docs/2026-09-13-workflow-f-state-of-codebase-audit.md`
  section 8 (new this commit) — full module description and
  silent-false-loss bug demonstration.
- `docs/NEXT_AGENT_PLAN.md` requirement matrix row F — updated
  this commit to reflect F1+F2+F3 closure.
- `python-engine/main.py:1599` — wire-up site, marked
  `[MTM-WIRED 2026-09-13]`.
