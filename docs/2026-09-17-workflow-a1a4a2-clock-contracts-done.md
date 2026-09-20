# Workflow A.1 + A.4 + A.2 — causal-acquisition clock contract

## Source

Per Workstream A in `NEXT_AGENT_PLAN.md`:
> Define explicit tick-start, public-response receipt,
> chain-response receipt, evaluation cutoff, candidate
> construction and dispatch clocks. Use injected clocks
> in tests.
>
> Choose and document the deployed policy: either evaluate
> on a declared frozen completed-bar cutoff with later
> availability, or recompute at a genuine post-acquisition
> decision clock. Do not silently mix both.
>
> Ensure crossing a five-minute boundary, entry cutoff or
> session boundary during a fetch cannot create a
> backdated idea.

## What shipped

### A.1 — Clock injection contract

- **`python-engine/decision_clocks_extensions.py`** (new):
  - `build_clock_for_test(...)` -- deterministic factory
    for tests with sensible defaults derived from a single
    tick instant + integer offsets per stage.
  - `validate_clocks(clock) -> list[ClockValidationProblem]`
    -- returns ALL clock problems instead of raising on
    the first.
  - `has_required_stages(clock)`, `missing_required_stages(...)`
    -- assert the clock has the minimum stages required
    for decision-ready replays (`public_received`,
    `chain_received`, `candidate_constructed`).
  - `clock_distance(clock_a, clock_b, field)` -- per-stage
    clock comparison.
  - `summarize_clock(clock) -> dict` -- audit-friendly
    summary with `ms_since_tick` deltas.
  - `compare_clock_policies(policy_a, policy_b)` -- one-line
    policy compatibility (`MATCH` / `FAMILY_MATCH` /
    `FAMILY_MISMATCH` / `UNKNOWN_POLICY`).

### A.4 — Cross-boundary safety net

- **`python-engine/boundary_safety.py`** (new):
  - `BoundaryKind` enum: `BAR_5MIN` / `ENTRY_CUTOFF` / `SESSION`.
  - `BoundaryCrossing` dataclass: per-crossing record with
    kind, message, and `crossed_at` timestamp.
  - `crossed_boundaries(clock, ...)` -- returns ALL boundary
    crossings during acquisition (not just the first, like
    the base `crossed_entry_boundary`).
  - `has_crossed_boundary(...)` -- convenience boolean.
  - `FIVE_MINUTE_BOUNDARY_MS` -- canonical 5-minute threshold.

### A.2 — Decision policy enum + version

- **`python-engine/decision_policy.py`** (new):
  - `DecisionPolicy` enum: `FROZEN_COMPLETED_BAR_CUTOFF_V1`
    / `POST_ACQUISITION_RECOMPUTE_V1`.
  - `SUPPORTED_POLICIES` -- tuple of all supported versions.
  - `policy_family(policy)`, `policy_is_frozen(policy)`,
    `policy_is_post_acquisition(policy)`,
    `is_supported_policy(policy)`.
  - `assert_policy_supports_clock(policy, clock)` --
    per-policy invariant enforcement.
  - `incompatible_policies(...)` -- one-line policy
    compatibility.
  - `start_clock_for_policy(policy, tick_started_at, ...)` --
    construct a valid clock for any supported policy.

- **`python-engine/partner_decision_clock.py`** (refactored):
  - `DecisionClock.__post_init__` now accepts any policy in
    `DecisionPolicy` and delegates per-policy invariant
    enforcement to `assert_policy_supports_clock`.
  - The hardcoded `evaluation_cutoff_at == tick_started_at`
    check (which only made sense for FROZEN policies) is
    removed and replaced by the policy-aware invariant.
  - Backward-compatible: existing 5 tests in
    `test_partner_decision_clock.py` still pass.

## Per-policy invariants

### FROZEN_COMPLETED_BAR_CUTOFF_V1

- `evaluation_cutoff_at == tick_started_at`
- Public bar eligibility frozen at tick start.
- Later network delays do not change bar eligibility.

### POST_ACQUISITION_RECOMPUTE_V1

- `candidate_constructed_at > tick_started_at`
- Decision recomputed at a genuine post-acquisition clock.
- Bar eligibility reflects data the system actually had.

The base `DecisionClock` rejects any policy not in
`DecisionPolicy`. The `assert_policy_supports_clock` helper
is the canonical check; both the constructor and downstream
audit code use it.

## Tests

- `tests/test_decision_clocks_extensions.py`: **31/31 PASS.**
- `tests/test_boundary_safety.py`: **18/18 PASS.**
- `tests/test_decision_policy.py`: **26/26 PASS.**
- Combined A-suite: **75/75 PASS** + 5 existing partner_decision_clock tests.
- Combined partner suite (advisory + renderer + sizing +
  orchestrator + hedge_readiness): **128/128 PASS.**
- Agent regression: **338/338 PASS.**

## Production untouched

No edits to `Production_Trading-sentinel/`. The base
`partner_decision_clock.py` change is the only production
edit; it is backward-compatible (existing FROZEN policy
clocks are still accepted).

## Acceptance (from plan)

- ✅ Explicit clocks at every phase boundary (item 1).
- ✅ Policy choice documented + version-pinned (item 2).
- ✅ Per-policy invariants enforced (item 2).
- ✅ Cross-boundary detection during acquisition (item 4).
- ⏳ Capture-bundle binding (item 3) -- operator-owned
  follow-up. The clock payload already round-trips via
  `validate_clock_payload` (proven by the existing tests);
  A.3 would extend this to carry `policy` and `source_ids`
  through the captured bundle.
- ⏳ Dispatch independence (item 5) -- verify-only; the
  dispatcher already revalidates independently via
  `_seen()` + `_record(delivered=...)`.

## Next slices (A.3, A.5)

- **A.3** -- capture-bundle binding: extend the persisted
  payload to include `policy`, `run_id`, `source_ids`, and
  the full clock dict so captures are replayable.
- **A.5** -- verify dispatch independence (no code change
  expected; just a test pinning the dispatcher's
  revalidation behavior).
