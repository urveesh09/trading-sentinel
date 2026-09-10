# Workstreams correction implementation record — 2026-09-10

## Scope and state

Implemented in Dev on `codex/production-correction-hedge-p0`. Production was
not read or changed by this implementation.

This increment repairs evidence contracts and reporting. It does not qualify a
strategy, enable an order path, send partner advice, or claim broker statement
reconciliation.

## Implemented

### Kite completed-bar boundary

- `python-engine/proactive_market_data.py` now accepts the real
  `KiteClient.get_intraday_by_token` DataFrame contract: a `datetime` named,
  timezone-naive IST `DatetimeIndex`. Naive values are localized explicitly;
  unordered, duplicate, mixed, or ambiguous data is rejected.
- A bar is usable only after its interval close at the actual post-request
  receipt clock. The provenance records request, per-instrument receipt, and
  final receipt times; it never relabels the scan-start clock as receipt.
- The mapping must declare `token`, `basis` (`SPOT` or `FUTURE`) and an archived
  master raw SHA-256. The matching dated master must prove token, underlying,
  exchange and instrument basis. Bare token mappings are rejected.
- Contract-master archival retains valid `INDEX` records as well as option and
  future records, allowing a dated spot identity to be proven when it exists.
- The shadow runner uses the recorded receipt clock as its evaluation time.
  Zero index volume remains valid OHLCV data; it is not upgraded to equity
  tradability evidence.

### Intraday debit-spread replay

- `LegQuote` includes immutable token, option type, strike, expiry, quantity,
  and master digest evidence.
- Replay validates full-lot non-boolean integer depth/quantity, distinct legs,
  matching expiry/type, call/put vertical ordering, exchange, no stale/future
  observations, session start/day/expiry, and maximum economic width.
- The evidence identity now includes policy windows, freshness/synchronisation,
  cost, slippage, execution-delay assumptions and contract provenance. Different
  assumptions cannot share an evidence hash.
- The replay remains conservative and research-only. A missing exit is still
  unresolved, not an assumed benign expiry payoff.

### Research-report integrity

- A frozen manifest constructor predeclares dataset, code revision, sessions,
  thresholds, and policy groups. A supplied manifest is cryptographically
  verified against the report input.
- Reports deduplicate stable evidence identities, check session claims against
  actual replay entry dates, retain rejected/no-fill/unresolved outcomes, and
  separate deterministic evidence hashing from report creation time.
- Reports expose sequential drawdown and clearly mark unseen-session behavior
  as not measured. Legacy callers without a pre-persisted manifest remain
  explicitly insufficient for readiness.
- `intraday_spread_chronological.py` now selects the first executable signal
  and first policy exit from receipt-ordered observations. It retains an active
  entry and records no timely executable exit as unresolved, preventing
  caller-selected entry/exit cherry-picking.
- `intraday_spread_holdout.py` adds a frozen, per-index/policy holdout summary.
  It rejects overlapping train/holdout dates and duplicate evidence while
  retaining closed, no-fill, and unresolved outcomes. It cannot qualify,
  deliver, or place an order.

### Five-source reconciliation evidence

- `python-engine/reconciliation_evidence.py` produces read-transaction sheets
  for `MOMENTUM`, `EDGE_LIVE`, `MOMENTUM_PAPER`, `PENNY_PAPER`, and `EDGE_PAPER`.
  Each states scope, time range, realized amount, adjustments, closed/partial/
  open counts, invalid amount count, costs coverage, and broker status.
- Stable origin matching flags duplicated ledger origins, missing positions,
  source/P&L mismatches, and non-finite amounts. The bounded detail output now
  declares pagination/truncation rather than implying completeness.

### Scheduler in-flight evidence

- `scheduler_telemetry.py` creates an in-flight run marker before awaiting an
  instrumented job and updates that same record on completion. A crash leaves
  an explicit unfinished marker, distinguished by boot ID from a current run.
- Timing reports separately count executed runs, scheduler rejections and
  in-flight runs. Telemetry uses a short SQLite lock budget; a locked telemetry
  store cannot prevent an exit, lifecycle or collection callback from running.
- Quote collection now reports separate provider-quote, archive-finalization,
  archive-write and archive-journal durations to the scheduler timing journal.

## Validation

`237` connected targeted Python tests passed, covering proactive workflow integration,
completed-bar data, replay, report artifacts, reconciliation, archive,
scheduler telemetry, partner advisory, hedge routes, F&O lifecycle and
performance behavior, chronological replay, held-out comparisons, archive
adapters and in-flight scheduler behavior. `git diff --check` passed.

## Still intentionally pending

- Adapter work to turn retained active-leg quote packets into declared
  chronological strategy signals, including partial-leg execution exposure.
  `intraday_spread_archive_adapter.py` now completes the safe input half: it
  reads immutable journals, proves both legs against the archived master,
  pairs only same-receipt books and reports partial batches. It deliberately
  requires a separately hashed deterministic signal artifact before assigning
  a non-zero signal score.
- Observed-session collection and held-out, per-index/policy comparison needed
  for any human qualification decision.
- DB timing-stage telemetry, production contention measurements and capacity
  isolation validation.
- Broker statement imports are required for external reconciliation; the five
  sheets are internal retained-ledger evidence only.

None of the pending work authorizes hiding warnings or promoting an advisory.
