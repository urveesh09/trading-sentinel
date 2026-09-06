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

## Round-five delivery authorization corrections — 6 September 2026

- `python-engine/hedge_advisory.py`
  - Added durable, decision-scoped delivery guards keyed by account, advisory
    kind, economic decision and exposure lifecycle. Claim ownership, transport
    start, acknowledgement, failure and abandoned-claim recovery now update the
    guard in the same transaction as the generation ledger. A second generation
    cannot begin transport while an equivalent generation is owned, in flight,
    delivered or awaiting manual resolution.
  - Added a destination-scoped partner transport backoff. A Telegram 429 now
    carries forward its retry deadline to later generations and unrelated
    partner decisions, while leaving the separate operator route unaffected.
  - Added final Phase-1 dispatch authorization between claim and durable
    transport intent. It verifies policy/version, real proposal expiry,
    account and accepted snapshot identity, portfolio revision, complete input,
    valid rows and claim ownership. A final SQLite write transaction makes that
    comparison the authorization boundary; no lock is held during transport.
    Phase-2/3 proposals now carry the same account/snapshot/revision and
    generation identity, and their final authorization also rechecks the live
    readiness gate immediately before transport.
  - Malformed JSON, non-object ledger rows and unresolved pre-generation
    deliveries no longer crash cross-generation lookup or vanish from the
    decision record. They enter a read-only, underlying-scoped quarantine.
  - Added an authenticated, append-only manual-resolution path for an
    unowned ambiguous delivery. It requires operator identity, reason and
    evidence; only a confirmed non-delivery can release the decision for a
    fresh evaluation. Confirmed delivery and retirement remain terminal and
    never fabricate a Telegram acknowledgement.

- `python-engine/routes_hedge.py`
  - Added authenticated read-only delivery backlog and evidence-bearing manual
    resolution endpoints. They do not enable delivery or place orders.

- `python-engine/tests/test_hedge_advisory.py`
  - Added regressions for concurrent equivalent generations, an ambiguous
    generation whose failure write is unavailable, destination-wide rate-limit
    carry-forward (including delivery after the delay), a Phase-1 proposal
    denied before it reaches transport, scoped corruption quarantine, and
    append-only manual resolution.

### Round-five verification

- 41 direct hedge-advisory tests passed.
- 186 selected hedge, partner-input, partner transport and scheduler Python
  tests passed (one pre-existing Starlette deprecation warning).
- `git diff --check` passed.
- Gateway code was not changed. A full local gateway invocation was blocked by
  the workspace's missing `better-sqlite3` native binary for Node ABI 137;
  Jest reported 295 passing tests before 12 binding-dependent database tests
  failed. Rebuild/install the native dependency in the approved Node runtime
  before treating gateway verification as current.

The remaining round-five full historical migration and real exposure lifecycle,
fixture adapter, activity/outcome instrumentation, research basket, entry/exit
experiments and optional-AI work remain separate, unimplemented packages. This
increment makes no profit claim, does not send a live message or order, and
does not modify Production.

## Proactive product build progress — 6 September 2026

### P1 — partial, implemented foundation

- Added `python-engine/proactive_intelligence.py`: a mode-separated,
  append-only opportunity/stage-event ledger with idempotency keys and a
  funding-flow store. It explicitly distinguishes scan evaluations from unique
  opportunities and does not create orders or contribute simulated evidence to
  live profit.
- Added `/analytics/proactive-activity` and a Dashboard activity funnel. The
  view labels unavailable data rather than presenting it as healthy inactivity.
- Added focused persistence/report tests. This is the shared P1 foundation;
  diagnostics consumers, cash-flow ingestion and the P2–P7 strategy, fixture,
  simulation, learning and AI milestones remain in progress.

### P1 — partial, funding and workflow diagnostics

- Added idempotent deposits, withdrawals and expenses to the proactive ledger.
  Funding flows remain separate from trade evidence and are never described as
  profit. Added a diagnostic API for missed scan intervals and risk-approved
  opportunities with no submission/fill result; it observes and reports only,
  never forces a trade or loosens a filter.

### P2/P3 — partial, shadow proposal core

- Added deterministic completed-bar proposal builders for `trend_pullback_v1`,
  `range_reversion_v1`, and `contraction_breakout_v1`. They produce research
  proposals only; no builder has a broker or partner-delivery dependency.
- Added a shared small-capital selector that ranks proposals, prevents duplicate
  instrument exposure, respects reserved cash, and records a specific deferral
  reason instead of forcing a trade. The ₹8,000 scenario therefore chooses
  feasible evidence rather than splitting capital into uneconomic pools.
- Focused fixtures cover a completed-bar proposal, insufficient free capital
  and future-bar rejection. Scheduler/watchlist persistence, realistic fill
  simulation, outcome learning, AI, partner fixture lifecycle and end-to-end
  demonstration remain in progress.

### P2 — partial, persisted watchlist lifecycle

- Added a transactionally persisted watchlist state machine with explicit
  `WATCHING → ARMED → TRIGGERED → SELECTED/DEFERRED/REJECTED` transitions and
  invalidation/expiry exits. A repeated scan cannot reset an existing setup to
  new or extend its expiry. This is a SHADOW research lifecycle and has no
  broker execution consumer yet.

### Product-foundation correction C2 — shared shadow reservation

- Added `ShadowAllocation`: selected research proposals now have one fixed
  quantity, executable-price assumption, fees, initial risk and reserved cash.
  The simulator can consume this exact reservation and rejects a gap that would
  make it infeasible, rather than independently reusing account cash for every
  selected candidate.

### Product-foundation correction C4 — truthful scan and workflow evidence

- Added a separate idempotent scan-run ledger. Dashboard scan counts now come
  from actual scanner runs, while lifecycle events count distinct opportunities
  across the whole reporting window. Diagnostics identify a dropped
  risk-approved opportunity by its own identity; an unrelated fill cannot hide
  it. A never-configured/never-run scanner is reported as unknown, not healthy
  inactivity.

### Product-foundation correction C6 — fixture validation and reopen identity

- Fixture rows are fully validated before the first position write, so a
  malformed later row cannot leave an earlier new position committed. External
  identities are namespaced by source/account and get a new lifecycle identity
  after a complete-snapshot close, allowing a true reopen without reusing a
  closed record's identity.

### Continuous SHADOW workflow — initial integrated consumer

- Added `run_shadow_workflow`, an offline application consumer connecting
  completed-bar scan evidence, proposal generation, persisted watchlists,
  shared allocation, conservative simulation and outcome events. It accepts
  only caller-supplied fixture/read-only bars and has no broker or partner
  send path. Restart-safe event keys preserve existing lifecycle evidence.
- A focused integration test exercises the real ledger/report path. Scheduler
  registration, durable open-position management, account outcome reconciliation
  and browser demonstration remain the next integration steps.

### Continuous SHADOW workflow — scheduled fixture consumer

- Added the `proactive_shadow_workflow` five-minute scheduler registration and
  a bounded configuration consumer. It remains disabled by default and can
  run only a local JSON fixture explicitly marked `mode: SHADOW`; it never
  reads broker data, sends a partner message, or submits an order.
- Enabled-but-missing/malformed fixture input is stored as an `UNAVAILABLE`
  source state and surfaced by proactive diagnostics. It is not counted as a
  completed scan. Identical completed-bar inputs use a stable digest-based
  scan identity, so a restart or repeated scheduler tick cannot fabricate
  additional scan evidence.
- Updated scheduler and route census goldens deliberately. The route portion
  records the prior intentional proactive analytics and hedge-delivery
  visibility endpoints; the job portion records the new shadow-only consumer.

### Continuous SHADOW workflow — durable synthetic positions

- Added a separate `proactive_shadow_positions` ledger for synthetic fills and
  closed outcomes. Open SHADOW positions reserve their exact entry notional and
  entry fee from the next scan's scenario cash; realised synthetic P&L is only
  released after a recorded close. This ledger is not a broker-position table
  and cannot be used by a live order path.
- The scheduled workflow advances persisted open simulations before considering
  new setups. It consumes only new completed fixture bars, preserves an open
  position when a later fixture is malformed, and closes stop/target/deadline
  outcomes with the same conservative assumptions as initial simulation.
- Future-bar input now has a single chronological order and rejects duplicate
  timestamps/OHLC-invalid data instead of silently using ambiguous history.
  Focused regression coverage proves restart-safe reservation, later stop
  management and no duplicate simulated position creation.

### Proactive activity dashboard — synthetic outcomes

- Extended the activity response and Dashboard with account-scoped open/closed
  synthetic position counts, reserved capital, gross P&L, fees and net P&L.
  The UI explicitly calls these fixture simulations and does not mix them into
  broker-reconciled cash or present them as live profit.

### Integrated SHADOW corrections — clock and run isolation

- A workflow tick now treats its supplied timestamp as an evaluation `as_of`
  clock and only observes completed fixture bars at or before that boundary.
  Future bars cannot fill or close a position, release cash or influence
  allocation early. `run_shadow_replay` advances the same workflow through a
  strictly increasing replay clock instead of consuming a full future fixture.
- Named SHADOW runs now bind a logical account, run ID and immutable scenario
  manifest (capital, fee and slippage assumptions). Opportunity identities are
  scoped to that run, so identical setups from two accounts/scenarios persist
  independently; changing parameters requires a new run ID rather than
  silently mixing economic assumptions.
- Historical proposal bars are now chronological, completed, finite and valid
  OHLCV before they can create a setup. Post-run free cash is recomputed after
  commits. Pending no-bar setups remain non-terminal rather than being called
  expired before their entry deadline; selected watchlists complete with their
  synthetic position lifecycle.

### Integrated SHADOW corrections — durable run steps and cost continuity

- Added a durable per-run, per-`as_of` step claim/result record. An exact retry
  returns its prior committed response without additional positions, events or
  cash effects; conflicting data at the same clock is rejected, and an earlier
  clock cannot mutate a later-established run.
- Stored run cost assumptions are now authoritative for both initial fills and
  resumed open-position management. This prevents a restart from silently
  reverting a zero- or custom-cost scenario to default fee/slippage settings.
  Execution origin is recorded as `SHADOW` or `REPLAY` in the step ledger.

### Integrated SHADOW corrections — pending lifecycle sweep

- Added a persisted pending-watchlist sweep before each claimed evaluation
  step. Unfilled `WATCHING`/`ARMED`/`SELECTED` setups expire at their original
  entry deadline even when their instrument is absent from the current
  universe. Existing synthetic positions are excluded, so their independent
  management lifecycle continues after entry expiry.

### SHADOW scheduler enablement

- Enabled the `PROACTIVE_SHADOW_ENABLED` scheduler gate by default for
  promotion. The consumer still requires an explicit local fixture declaring
  `mode: SHADOW`; without one it records `FIXTURE_SOURCE_UNCONFIGURED` and
  cannot access live market data, brokers, partner delivery, orders or funding.
  Pre-existing live hedge, delivery and advanced-phase feature gates remain
  unchanged.

### P3 — partial, conservative shadow execution

- Added a long-only offline fill simulator for the shadow proposals. It sizes
  only from available scenario cash, applies disclosed spread/slippage and
  round-trip fees, records no-fill states, and treats an OHLC bar hitting both
  stop and target as stop-first ambiguity. It is research evidence only and
  cannot submit an order.

### P5 — partial, optional AI startup boundary

- `agent/agent.py` now treats a missing `MINIMAX_API_KEY` as `AI_DISABLED`,
  initializes no model client, and returns a typed unavailable review. Telegram
  configuration remains required for the alerting service itself; deterministic
  alert/watchdog operation no longer depends on an AI provider.
- Agent pipeline collection could not run in the Python-engine virtual
  environment because that environment lacks the agent dependency `requests`.
  This is a Dev environment limitation, not a reason to reintroduce the AI
  startup dependency; validate it in the agent image/environment next.

### P6 — partial, fixture lifecycle adapter

- Added `partner_fixture_adapter.py`, a Dev-only source-neutral fixture path
  using stable external position identities and the real partner-position plus
  accepted-snapshot interfaces. A complete fixture can create/reconcile a
  position; a later complete account view closes its absent exposure through
  the existing atomic snapshot transaction. It has no broker credentials or
  delivery path.
- Focused lifecycle tests cover accepted creation and complete-snapshot close.
  Corporate-action/reopen fixtures, hedge-card UI and the full end-to-end
  mocked-delivery demonstration remain in progress.
