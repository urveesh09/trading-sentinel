# Hedge audit remediation — 5 September 2026

## Scope

This is a Dev-only correction increment on
`codex/production-correction-hedge-p0`. It responds to the implementation
review without changing Production files, databases, broker state or Telegram
destinations.

## Implemented corrections

- `python-engine/hedge_advisory.py`
  - A portfolio with any unreconciled open row now reports
    `PARTIAL_RECONCILIATION`; a reconciled subset cannot be labelled ready for
    whole-portfolio advice.
  - An empty Phase-1 builder result is recorded as `INPUT_UNAVAILABLE`, not
    `NO_HEDGE_NEEDED`. The latter must be supported by an explicit risk-band
    conclusion rather than inferred from an empty list.
  - A Phase-1 proposal key now includes a material position/leg fingerprint.
    An unchanged recommendation deduplicates; a changed quantity or structure
    can produce a new version during the same day.
  - Remote acknowledgement is committed to the delivery claim before optional
    service-state summaries. If ancillary state refresh fails after a known
    acknowledgement, the persisted delivery result remains non-retryable.
  - Shadow evaluations are stored immutably with an evaluation id, rendered
    text, sanitized detail and evaluation timestamp. `last_shadow_candidate`
    remains a convenience pointer rather than the evidence ledger.

- `python-engine/partner_bot.py`
  - A hedge claim now maps to exactly one Telegram POST. Timeout ambiguity and
    429 retry-after information are returned to the advisory ledger instead of
    being overwritten by a later in-process retry response.

- `node-gateway/server/services/executor.js` and `services/kite.js`
  - Margin evidence strictly accepts real finite numeric fields, prefers
    `live_balance` over raw `cash`, rejects disabled/malformed equity segments,
    excludes collateral, and uses product-specific broker order-margin evidence
    when the gateway supports it. Full notional is explicitly labelled as a
    conservative fallback policy, not broker-required margin.

- `python-engine/tools/runtime_audit.py`
  - Cross-boot market-hour gaps are now reported as P1 coverage gaps, distinct
    from same-process scheduler freezes. Premarket restart gaps remain evidence
    only.

- `python-engine/penny_edge_engine.py`
  - Missing or malformed bar dates return `invalid_data` instead of raising.

- Scheduler golden contracts now include exactly the two intentional hedge
  summary jobs.

## Validation

- 71 focused Python tests passed: hedge advisory/transport, runtime audit,
  EDGE diagnostics and scheduler surface contracts.
- 46 gateway executor tests passed, including funds divergence, malformed
  balance fields and product-specific broker-margin cases.
- Python compilation, Node syntax checks and whitespace validation passed.

## Deliberately not represented as complete

The review’s R1 delivery milestone still requires an approved partner input
adapter/account mapping and a genuine sourced India-VIX producer. The existing
authenticated intake/reconciliation APIs remain source-neutral, but this change
does not invent an external account feed or mark a stale manual row fresh.

No live Telegram canary, broker order, Production migration, or claim that a
partner received a current personalized hedge review was made. Those require
the mapped source, fresh reconciled data, review of destination/content, and
explicit send authorization.
