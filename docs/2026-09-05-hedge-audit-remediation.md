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

- 147 focused Python tests passed: hedge advisory/transport, the source-neutral
  input-refresh contract, runtime audit, EDGE diagnostics, scheduler closure
  invocation and scheduler surface contracts.
- 46 gateway executor tests passed, including funds divergence, malformed
  balance fields and product-specific broker-margin cases.
- Python compilation, Node syntax checks and whitespace validation passed.

## Deliberately not represented as complete

The review’s R1 delivery milestone still requires an approved partner input
adapter/account mapping and a genuine sourced India-VIX producer. A
source-neutral `partner_input_refresh.py` contract is now scheduled every two
minutes: an approved adapter may supply a complete timestamped snapshot of
known position ids plus an independently timestamped VIX observation. Complete
snapshots reconcile changed quantities and close only absent rows owned by that
source; partial snapshots never infer a close. The default adapter URL is empty
and surfaces `INPUT_ADAPTER_UNCONFIGURED`, so this code does not invent an
external account feed or mark a stale manual row fresh.

No live Telegram canary, broker order, Production migration, or claim that a
partner received a current personalized hedge review was made. Those require
the mapped source, fresh reconciled data, review of destination/content, and
explicit send authorization.

## Round-two remediation — 5 September 2026

This follow-up implements the P1 correction packages from
`2026-09-05-hedge-remediation-round2-audit-and-roadmap.md` in Dev only.

- `python-engine/hedge_advisory.py`
  - Phase 1 now canonicalizes `LegSpec.opt_type` as its actual string model;
    a valid protective-put or futures proposal no longer crashes before the
    sender because of an enum `.value` access.
  - Proposal identity is a pure, sorted economic representation of positions
    and selected legs. Reconciliation timestamps are excluded, while quantity,
    price/Greek exposure and contract changes supersede a proposal.
  - Every whole-portfolio phase uses the latest accepted complete snapshot
    envelope. Missing, partial, stale and future envelopes block evaluation;
    a verified empty account is reported distinctly.
  - Delivery claims retain rendered text, proposal expiry and attempt history.
    Timeout ambiguity requires manual recovery, 429 responses honour their
    retry-after time, permanent rejection is terminal, and an expired proposal
    is retired before transport. A two-minute recovery job uses the same ledger
    for due unambiguous retries.

- `python-engine/hedge_analytics.py` and `partner_input_refresh.py`
  - Snapshot envelopes now require source, account id, snapshot id, monotonic
    sequence, observed time and completeness. The last accepted watermark is
    persisted per source/account, with payload hashes for idempotent replay.
  - All reconciliation events, inferred closures and snapshot-watermark update
    are one SQLite transaction. Invalid later rows or write failures roll back
    the entire snapshot; readers cannot observe a mixed portfolio version.
  - Old/future/stale/replayed envelopes are rejected before promotion. Partial
    envelopes never infer closures. Greeks must be complete when provided;
    unknown gamma/theta/vega are not converted to zero.
  - Adapter authentication now uses a dedicated adapter bearer token rather
    than Sentinel's shared internal-service secret. Optional configured source
    and account bindings reject mismatched input before any write.

- `node-gateway/server/services/executor.js`
  - A present negative, null or malformed `live_balance` now fails closed;
    `cash` is a legacy fallback only when the live-balance field is absent.

- `python-engine/scheduler_setup.py` and scheduler golden contracts
  - Added `partner_hedge_delivery_recovery` at every two minutes, offset from
    input refresh and evaluation jobs. The scheduler surface and closure census
    explicitly cover the new job.

### Round-two verification

- 155 focused Python tests passed, covering hedge advisory/transport, snapshot
  transaction/order rules, Phase 3 gate, scheduler contracts, runtime audit
  and adjacent F&O/Penny scheduler surfaces.
- 46 gateway executor tests passed, including invalid live-balance fallback.
- Scheduler golden contracts were regenerated deliberately and then validated.

The external rollout prerequisites remain unchanged: an approved adapter and
account mapping, scoped credential provisioning, source coverage for new and
reopened identities, a genuine VIX producer, and explicit live-message
authorization. Production remains unmodified.
