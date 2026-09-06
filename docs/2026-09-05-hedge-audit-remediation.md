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

## Round-three safety hardening — 6 September 2026

Implemented from the follow-up audit while retaining its two pre-existing Dev
fixes:

- `python-engine/hedge_analytics.py` and `partner_input_refresh.py`
  - The service is now explicitly **single-account**. An enabled importer
    requires configured approved source and account values, persists the first
    accepted binding, and rejects any later source/account switch before a
    portfolio mutation or inferred close.
  - Advisory code reads the accepted envelope, open rows and reconciled rows
    in one SQLite read transaction (`PartnerEvaluationInput`), preventing an
    evaluation made from mixed committed versions.
  - Fresh envelopes cannot make stale/future position marks or VIX readings
    appear current.

- `python-engine/hedge_advisory.py` and `partner_bot.py`
  - All post-dispatch transport exceptions are treated as ambiguous, not as
    safe network retries. Send intent is durable before the sole POST; an
    abandoned in-flight claim requires manual recovery after its lease.
  - An acknowledgement persistence fault remains ambiguous even if its
    fallback marker also fails; it cannot fall through into a normal retry.
  - Scheduled recovery honours the hedge kill switch and revalidates Phase-1
    account/snapshot policy, calendar/session and current complete portfolio.
    It retires superseded/ineligible proposals and never replays Phase-2/3
    rendered advice; those require fresh generation.
  - Proposal identity now represents executable side, contract, expiry, lots
    and account scope, not routine prices or Greeks. Observation changes remain
    audit evidence rather than a new partner instruction.

### Round-three verification

- 185 Python tests passed across the audit-selected and adjacent hedge/F&O
  suites (79 primary safety tests plus 106 supporting tests).
- 46 gateway executor tests passed.
- Compilation and diff checks passed.

This remains Dev-only and deliberately does not claim production readiness.
The real adapter lifecycle for new/reopened/corporate-action positions and the
separately authorized live delivery canary remain external release gates.

## Round-four ledger and revision corrections — 6 September 2026

- `python-engine/hedge_advisory.py`
  - Post-dispatch failures cannot be downgraded to `internal_error`: if the
    authoritative failure write fails after a timeout/disconnect, the durable
    transport-started claim remains ambiguous and is never auto-replayed.
  - `retired` is terminal. Retirement uses an optimistic compare-and-set on
    the exact retry record and refuses to clear a live claim token owned by
    another worker.
  - Explicit absence from `PartnerEvaluationInput` is preserved; the
    whole-portfolio gate no longer starts a second read and mixes versions.
  - Phase-1 delivery now separates an economic `decision_id` from an expiring
    `generation_id`. Delivered or ambiguous decisions suppress equivalent
    generations; an expired, unsent generation can be replaced only by a
    fresh evaluation generation.

- `python-engine/hedge_analytics.py`
  - Added a monotonic `partner_hedge_portfolio_revision`, advanced inside the
    same write transaction for new positions, manual reconciliations/closes,
    and accepted snapshots.
  - Consistent evaluation input includes the revision and invalid-open-row
    count. Invalid stored open rows fail readiness instead of disappearing
    into an apparently complete portfolio.

- `python-engine/tests`
  - Added orchestration regressions for timeout plus failed authoritative
    ledger write, terminal retirement, explicit absent snapshots, and manual
    mutation revision invalidation.

The real adapter lifecycle and operator workflow for manual ambiguity remain
deployment gates. These changes strengthen unattended safety; they do not
claim that partner delivery or income performance is proven in Production.

Round-four verification: 189 selected Python tests passed (one pre-existing
Starlette deprecation warning), compilation and diff checks passed. Gateway
executor verification remains the existing 46 passing tests; no gateway code
changed in this increment.
