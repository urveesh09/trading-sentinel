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

### P6 correction — atomic fixture portfolio promotion

- Fixture-discovered positions are now inserted only within the same SQLite
  transaction that validates, reconciles and accepts their complete account
  snapshot. A rejected sequence, watermark, ownership or later-row validation
  error rolls back both the new identities and the snapshot evidence; no
  partial fixture portfolio is visible to analytics.
- The generic input normalizer supports an internal `position_key` reference
  only when it is paired exactly with a staged `PartnerPosition`. Ordinary
  adapters retain their existing integer position-ID contract. A fixture retry
  hashes its immutable source payload rather than local generated IDs, so an
  exact retry remains idempotent after the first import resolves those IDs.
- Fixture marks and new-position timestamps retain the source observation
  time, rather than relabelling delayed source data with local receipt time.
  Regression tests cover rejected ordered envelopes without residual rows and
  exact source-fixture retry idempotency.

### P6 extension — complete offline option fixture support

- The Dev fixture adapter now carries option expiry, strike and explicit
  delta/gamma/theta/vega through both staged creation and reconciliation. It
  applies the same F&O lot-unit and non-fictional-Greek validation as the real
  partner input boundary, rather than treating option exposure as equity or
  silently assigning zero Greeks.
- Equity deliverability evidence is also preserved when supplied by a fixture.
  A regression imports and reconciles a complete NIFTY put fixture; no broker,
  order or messaging path is involved.

### P5 extension — bounded optional-AI annotations

- Added a one-worker, bounded optional-AI queue in the agent service. Requests
  are keyed by immutable decision fields plus an event-evidence digest, have a
  per-review expiry, short-lived result cache, daily request ceiling and a
  provider-failure circuit breaker. Late results are discarded, never reused.
- Momentum may opt into this asynchronous annotation path only when both its
  reject policy and unavailable-review policy are explicitly advisory. The
  deterministic alert then carries `AI_REVIEW_PENDING` rather than treating a
  pending model call as approval. A configured hard veto retains its existing
  synchronous policy; this change does not silently weaken it.
- The queue is disabled by default and has not been enabled in Production.
  Dependency-free worker tests cover cache, queue saturation, circuit open and
  late-result discard. The checked-in Linux agent virtualenv cannot execute
  from this Windows host mount, while the Python-engine environment lacks its
  `requests` dependency; full agent-suite validation remains for its supported
  container/CI runtime.

### N5 correction — truthful SHADOW scanner health

- Completed-bar history is now classified as `READY`, `INSUFFICIENT_HISTORY`,
  `INVALID_HISTORY` or `STALE_HISTORY` before proposal construction. Only
  ready input can record a successful scan; unavailable data records an
  explicit unavailable scan instead of a flattering `NO_COMPLETED_SETUP`.
- Regression coverage verifies an insufficient malformed fixture produces
  `UNAVAILABLE/INSUFFICIENT_HISTORY` and no proposal. This remains offline
  research evidence and does not affect any order or broker path.

### N5 correction — repairable SHADOW lifecycle evidence

- Added an idempotent repair pass that derives missing `FILLED`/`CLOSED`
  lifecycle events from the authoritative synthetic-position ledger after an
  interrupted write. It never creates a second position, alters cash, changes
  a price or replays a fill; it only restores absent immutable evidence.
- The workflow runs this repair after its durable step claim. Regression
  coverage proves a persisted fill is repaired once and subsequent passes are
  no-ops.

### P1 extension — scoped synthetic cash and valuation disclosure

- The proactive activity API and Dashboard now show each synthetic account/run's
  scenario capital, free cash after open reservations and realised outcomes,
  alongside gross, fees and net. The calculation is tied to the immutable run
  manifest; legacy records explicitly show capital as unavailable.
- Open synthetic positions do not yet have a persisted current mark, so the UI
  labels unrealised P&L as unavailable rather than displaying entry notional as
  a fabricated valuation. All values remain clearly labelled fixture/SHADOW
  research, never broker-reconciled profit.

### P1 correction — completed-bar synthetic marks

- Added restart-safe `marked_price` and `marked_at` fields to synthetic
  positions, including a non-destructive schema migration. New and managed
  open positions receive a mark only from the close of an observed completed
  fixture bar. Closed positions retain their exit mark but report no
  unrealised P&L.
- The activity response exposes marked gross and net-after-entry-fee
  unrealised values, with `MARKED`, `PARTIALLY_MARKED` or `UNAVAILABLE` state.
  Free cash intentionally excludes unrealised profit/loss until a simulated
  exit is recorded.

### P4 extension — costed SHADOW outcome comparison

- Added a read-only research comparison over closed synthetic positions. It
  groups policies only within their immutable account/run assumptions and
  reports gross P&L, declared costs, net P&L, expectancy, risk-normalised
  expectancy, win/loss composition, profit-factor availability, chronological
  closed-trade drawdown and observed exit reasons. Malformed completed rows are
  counted and excluded rather than silently converted to zero-return trades.
- A conservative 20-completed-outcome threshold leaves every smaller sample in
  `INSUFFICIENT_CLOSED_OUTCOMES`; even a larger sample remains
  `COLLECTING_EVIDENCE`, not a profit or promotion claim. Historical outcomes
  have no distinct exit-policy tag, so the response explicitly reports that an
  exit-policy A/B comparison is unavailable rather than inventing one.
- Exposed the comparison at `/analytics/proactive-comparison` and in the Dev
  Research Center. The contract is hard-labelled `SHADOW`, research-only and
  incapable of placing orders; it does not change broker, hedge, delivery,
  sizing or live-strategy behaviour.

### P4 extension — frozen matched entry/exit trials

- Added an immutable SHADOW research-run ledger for matched entry/exit trials.
  Each frozen run records the exact proposal geometry, price bars, scenario
  cash and cost assumptions; reusing a run ID with changed input is rejected.
  Exact reruns are idempotent. This is intentionally separate from the
  scheduled shadow-position ledger and cannot open a synthetic or broker
  position.
- The initial experiment registry evaluates every supplied opportunity under
  next-executable-open, bounded-pullback-limit and completed-bar-confirmation
  entries, crossed with stop/target/time and a bounded 60-minute time exit.
  It retains closed, open, no-fill and invalid outcomes so delay and missed
  opportunities cannot be hidden by reporting only winners.
- `/analytics/proactive-research-comparison`, its authenticated gateway proxy
  and the Dev Research Center render all profile rows with insufficient-sample
  states. No profile is selected, promoted or allowed to modify incumbent
  execution; volatility-trail and thesis-invalidation challengers remain
  explicitly unimplemented rather than being represented by a misleading
  substitute.

### P7 foundation — reproducible isolated SHADOW demonstration

- Added an offline Dev command that creates a **new** SQLite evidence database
  and runs the actual SHADOW workflow through a deterministic multi-session
  fixture. Run it from the Dev checkout with:

  `python-engine\\winvenv\\Scripts\\python.exe python-engine\\scripts\\run_proactive_shadow_demo.py --db C:\\temp\\proactive-shadow-demo.db`

  It proves pending-entry expiry across an empty later universe, shared-cash
  selection versus an unaffordable independent candidate, completed-bar target
  management, costed dashboard/API reporting and immutable matched trial
  persistence. The output is JSON with explicit SHADOW/no-order contract flags
  and assertions. It uses only `SYNTH:*` symbols and rejects an existing DB
  path rather than overwriting evidence.
- While exercising the demo, a historical-entry issue was found and fixed:
  cash released by a later close could previously admit a different policy at
  an earlier already-observed bar. Such candidates now record
  `MISSED_ENTRY_WINDOW_NO_HISTORICAL_BACKFILL` and remain non-executable. A
  regression runs the full demo and verifies exactly one synthetic closed fill.
- This is a P7 foundation, not a claim that the required AI-outage, partner
  lifecycle or browser-evidence portions of the broader demonstration are
  complete. It has no Production, broker, delivery or scheduler activation.

### P6 extension — deterministic hedge-card evidence API

- Added an authenticated read-only card API for persisted partner hedge SHADOW
  evaluations. Cards expose phase, review type, account, underlying, contracts,
  validity, portfolio revision, decision/generation identities and rendered
  evidence. They are hard-labelled `NOT_SENT_SHADOW_EVIDENCE` with both send
  and trade authority false; partner confirmation and delivery recovery remain
  separate workflows.
- This API is available to the Dev gateway at `/partner/hedge/cards`. It does
  not create advice, change a readiness gate, call a transport or mutate a
  partner position. Fixture lifecycle cards and browser UI integration remain
  the next P6 work.

### P6 completion — visible cards and fixture lifecycle demonstration

- The Dev Dashboard now renders authenticated partner hedge review cards from
  `/api/proxy/partner/hedge/cards?limit=12`. They show only persisted SHADOW
  evidence, including contracts, review time, recorded/current portfolio
  revisions, and an explicit `SEND: NO · TRADE: NO` boundary. There is no card
  action and no UI route that can call a delivery or broker endpoint.
- A card is now marked `SUPERSEDED` whenever its recorded portfolio revision
  differs from the current account-wide revision. This prevents an older
  review from looking current after a complete snapshot changes exposure.
- `partner_lifecycle_demo.py` and
  `scripts/run_partner_lifecycle_demo.py` create a new isolated database and
  exercise the real Dev fixture adapter through create → complete-snapshot
  close → reopen. The demo then verifies two position lifecycles, a revision
  advance and a superseded old card while asserting no send/trade authority.
  Run it with:

  `python-engine\winvenv\Scripts\python.exe python-engine\scripts\run_partner_lifecycle_demo.py --db C:\temp\partner-lifecycle-demo.db`

  The command refuses an existing database rather than overwriting evidence.
  It is fixture-only and has no broker, partner transport, scheduler or
  Production configuration dependency.

### Optional-AI operational evidence — outage-safe UI

- `agent/async_reviews.py` now exposes bounded queue counters only (pending,
  cache, daily budget and circuit state); it never exposes prompts, model
  output or credentials. `agent.py` derives an explicit optional-AI state and
  asynchronously publishes it once per minute and at startup to the internal
  engine endpoint. A failed status publish is deliberately non-blocking.
- `optional_ai_status.py` stores the authenticated worker report separately
  from decisions. It makes no report, corrupt report and stale report explicit
  and hard-codes `execution_authority: NONE` and `can_place_orders: false`.
  The Dashboard displays that evidence through
  `/api/proxy/analytics/optional-ai-status`, with `OUTAGE_CIRCUIT_OPEN` visibly
  distinct from a healthy ready annotation service.
- Optional AI remains an annotation. The status path cannot approve, reject,
  size, send, deliver or place a trade; deterministic signal/risk/delivery
  behaviour continues when the provider is absent or circuit-open.

### Validation for the P6/UI/AI evidence completion

- `python-engine\winvenv\Scripts\python.exe -m pytest
  python-engine\tests\test_optional_ai_status.py
  python-engine\tests\test_partner_lifecycle_demo.py
  python-engine\tests\test_partner_fixture_adapter.py
  python-engine\tests\test_hedge_advisory.py -q` passed 51 tests.
- The authenticated gateway proxy contract passed 12 focused tests and the
  dashboard production build passed. The local agent virtual environment is a
  Linux layout and cannot run on this Windows checkout; both edited agent
  modules passed `py_compile` here. Run the agent suite in its Linux/Docker
  environment before promotion:

  `cd agent && .venv/bin/python -m pytest tests/test_async_reviews.py tests/test_agent_pipeline.py -q`

### P7 extension — five-session diagnostics and verified browser rendering

- Added `proactive_session_diagnostics()` and the authenticated
  `/analytics/proactive-session-diagnostics?sessions=5` route. It uses the
  shared local NSE calendar (cached/static fallback, never a network refresh)
  to enumerate eligible sessions. Each report is scoped by policy, account and
  mode so one account's later scan cannot make another scope appear healthy.
  It separates missing/unavailable scan evidence from viable opportunities,
  deferrals and unique fill-or-close outcomes.
- The report emits `TWO_ELIGIBLE_SESSIONS_NO_VIABLE_CANDIDATES` only when the
  two most recent eligible sessions both scanned successfully with no viable
  opportunity, and `FIVE_ELIGIBLE_SESSIONS_SPARSE_FILLS` only after all five
  sessions scanned successfully with one or fewer unique filled/closed
  opportunities. Neither diagnosis changes any strategy gate or has order
  authority. The Dashboard renders these scoped explanations directly.
- The deterministic proactive SHADOW demo now seeds the same persisted
  scan/event interfaces across five eligible sessions and asserts both
  diagnostics. This is evidence of sparse activity, not an instruction to
  force an order or relax a risk/cost constraint.
- Browser rendering was verified against the actual Dashboard component using
  its Dev-only evidence mode. It visibly rendered the synthetic activity/cash
  card, a superseded partner card with no-send/no-trade labels, an
  `OUTAGE_CIRCUIT_OPEN` AI panel with no authority, and both session findings.
  The mode is guarded by both Vite's `DEV` flag and
  `VITE_EVIDENCE_DEMO=true`, contains a prominent synthetic-data banner, and
  disables the fixture hooks' HTTP requests. It cannot be enabled in a normal
  production build and is not evidence of live balances, authenticated API
  connectivity, broker execution or partner delivery. To reproduce locally:

  ```powershell
  $env:VITE_EVIDENCE_DEMO = 'true'
  Set-Location node-gateway\client
  npm run dev -- --host 127.0.0.1
  ```

  Open `http://127.0.0.1:5173/`. Do not use this mode for operational review;
  it is a visual regression/demo fixture only.

### Remaining product-plan work after this increment

The following is still intentionally incomplete and must not be described as
production-ready income automation:

- Atomic/repairable multi-table economic writes and stale-worker ownership for
  cash, position and outcome evidence; the existing separate-write recovery
  work remains a correctness priority.
- Account/run selectors and complete drill-down of cash, reserves, fees,
  realised result and marked unrealised result across all reporting surfaces.
- Wiring the retained entry/exit trials into Backtest Lab, exit-quality and
  strategy-health consumers with calibration/uncertainty evidence.
- Full partner corporate-action fixture coverage, mocked delivery/recovery and
  fresh post-supersession evaluation. The implemented demo covers close/reopen
  and invalidation only.
- One unified multi-service acceptance command covering restart recovery, AI
  outage publishing, partner lifecycle and authenticated Dev services. The
  current proactive, lifecycle and browser fixtures are individually
  reproducible, not a proof of all running containers together.
- External, separately authorised work: live market-data adapter/canary,
  broker/account reconciliation, real partner account mapping/delivery and
  forward performance evidence. None is enabled or implied by this Dev code.
