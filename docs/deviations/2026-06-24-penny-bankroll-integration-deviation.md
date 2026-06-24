# 2026-06-24 — Penny bankroll integration (ledger source column)

## Problem

The penny subsystem (Rs 2,500 testing pool per Uru 2026-06-22 opt-in) was
operating in a parallel universe from the dashboard:

- Swing/momentum P&L wrote to `bankroll_ledger` (via `performance.record_trade_close`).
- Penny P&L wrote **only** to `PennyRiskEngine.daily_pnl` (an in-memory counter).
- The dashboard's `/bankroll` endpoint read `current_bankroll()` which returns
  the last row of `bankroll_ledger` — so it never reflected penny wins/losses.
- The dashboard's `CB_DAILY_LOSS_PCT = 20%` was computed off the swing-only
  bankroll, so a penny loss couldn't trigger the swing circuit breaker even
  if it consumed most of the penny pool.

The `source` column was already designed into the codebase (`performance.py`,
`analytics.py`, `main.py:1686`) but never added to the schema. Both
`performance.penny_pool_pnl()` (line 121) and `analytics.penny_outcome_correlator()`
(line 579) had a comment saying "this is a placeholder that will start returning
real data once the penny executor writes there."

## Approach

Dependency injection. The isolation rule
(`tests/test_penny_isolation.py`) forbids penny code from importing
`engine`, `regime`, `risk_engine`, `performance`, or `portfolio`. So
`PennyRiskEngine.record_close()` cannot call `record_trade_close` directly.

The fix:

1. **`performance.py`** — added `source TEXT NOT NULL DEFAULT 'SYSTEM'`
   to `bankroll_ledger` (CREATE + idempotent ALTER migration for existing
   DBs). Extended `record_trade_close(..., source="SYSTEM")` with a new
   keyword-only argument. Existing callers don't change behavior (default
   `"SYSTEM"`).

2. **`penny_risk.py`** — added optional `ledger_writer` parameter to
   `PennyRiskEngine.__init__` (default `None` preserves back-compat).
   `record_close()` schedules `loop.create_task(self._ledger_writer(ticker, net))`
   when a writer is provided. No import from `performance` — the rule is
   preserved.

3. **`penny_scanner.py`** — added optional `ledger_writer` parameter that
   is forwarded to the internal `PennyRiskEngine`.

4. **`main.py`** — defined a single shared
   `async def _penny_ledger_writer(ticker, pnl)` that calls
   `performance.record_trade_close(..., source="PENNY")`. Wired into
   `_get_penny_scanner()` (30s scan path), the hourly-report path
   (`run_penny_hourly_report` callsite), and `_penny_daily_reset()`
   (so the writer survives the midnight IST reset).

## Why injection (not a direct import)

Three reasons:

1. **Isolation rule.** `test_penny_isolation.py` enforces that penny code
   cannot import `performance`. A direct import would fail that test.
2. **Testability.** `PennyRiskEngine(bankroll=2000.0)` still works with
   no writer — 21 existing tests rely on this signature. The new behavior
   is opt-in via the `ledger_writer` parameter.
3. **Backward compatibility.** Penny paper mode never hit the ledger
   before; this commit doesn't change that. Only live penny closes now
   write to the ledger.

## Why not add a column to a separate `penny_bankroll_ledger` table

Two reasons:

1. **Designed-in pattern.** `performance.py`, `analytics.py`, and
   `main.py:1686` already assume a single `bankroll_ledger` with a
   `source` column. Adding a second table would require rewriting all
   three call sites, plus any future endpoint that wants to show
   "total bankroll across both subsystems."
2. **Net worth.** The user (Uru 2026-06-24) wants the dashboard to show
   one combined number: swing + momentum + penny. A single ledger with a
   `source` column lets `current_bankroll()` (which reads the last row)
   naturally reflect whichever subsystem traded last. Two tables would
   require a UNION ALL on every read.

## Schema migration

The `ALTER TABLE` migration is wrapped in `try/except` and silently
swallows the "duplicate column name" error. This is correct because:

- New DBs: CREATE TABLE includes `source`, ALTER raises, we ignore it.
- Old DBs (created before 2026-06-24): ALTER succeeds, adds the column
  with default 'SYSTEM' on every existing row (so legacy data is still
  attributed to "SYSTEM").

## Files changed

- `python-engine/performance.py` — schema + `source` param + comment update
- `python-engine/penny_risk.py` — `ledger_writer` injection in
  `PennyRiskEngine`, scheduled write in `record_close`
- `python-engine/penny_scanner.py` — `ledger_writer` forwarded to inner
  `PennyRiskEngine`
- `python-engine/main.py` — shared `_penny_ledger_writer` and 3 wiring
  sites (scanner, hourly report, daily reset)
- `python-engine/tests/test_performance.py` — 9 new tests
  (TestSourceColumn class) covering schema, default, explicit source,
  idempotency, migration, and aggregation
- `python-engine/tests/test_penny_risk.py` — 5 new tests covering
  writer invocation, back-compat, failure isolation, and isolation rule

## Test impact

- 14 new tests added (9 + 5).
- All 562 existing engine tests still pass.
- 194 penny + performance tests pass (180 original + 14 new).

## Operational impact

After this lands on production:

- Penny live trades will write to `bankroll_ledger` with `source='PENNY'`.
- `/bankroll` endpoint will reflect penny P&L as it happens.
- `CB_DAILY_LOSS_PCT` will see the combined swing + penny exposure.
- `performance.penny_pool_pnl()` and `analytics.penny_outcome_correlator()`
  stop returning empty buckets and start returning real numbers.

## Follow-ups (not in this commit)

1. The login-at-8:30 vs 8:00-universe-refresh question (raised by Uru
   2026-06-24) — `penny_universe_refresh` doesn't early-return when
   `kite.access_token` is empty. Add an explicit `if not kite.access_token:
   logger.warning(...); return` guard to make the staleness visible in logs.
   Tracked separately.
2. The penny universe refresh also fires even with no token, which
   silently keeps yesterday's universe. Same fix applies.