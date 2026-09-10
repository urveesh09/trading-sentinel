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

### Five-source reconciliation evidence

- `python-engine/reconciliation_evidence.py` produces read-transaction sheets
  for `MOMENTUM`, `EDGE_LIVE`, `MOMENTUM_PAPER`, `PENNY_PAPER`, and `EDGE_PAPER`.
  Each states scope, time range, realized amount, adjustments, closed/partial/
  open counts, invalid amount count, costs coverage, and broker status.
- Stable origin matching flags duplicated ledger origins, missing positions,
  source/P&L mismatches, and non-finite amounts. The bounded detail output now
  declares pagination/truncation rather than implying completeness.

## Validation

`228` targeted Python tests passed, covering proactive workflow integration,
completed-bar data, replay, report artifacts, reconciliation, archive,
scheduler telemetry, partner advisory, hedge routes, F&O lifecycle and
performance behavior. `git diff --check` passed.

## Still intentionally pending

- Chronological strategy signal/entry/exit selection from retained active-leg
  observations, including partial-leg and no-timely-exit exposure accounting.
- Observed-session collection and held-out, per-index/policy comparison needed
  for any human qualification decision.
- Provider/DB/archive timing-stage telemetry, in-flight visibility, contention
  measurements and capacity isolation validation.
- Broker statement imports are required for external reconciliation; the five
  sheets are internal retained-ledger evidence only.

None of the pending work authorizes hiding warnings or promoting an advisory.
