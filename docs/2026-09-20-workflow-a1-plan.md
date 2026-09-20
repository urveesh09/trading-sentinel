# Plan — A1: CAS eligibility three-state + owner authority entry-only halt

Date: 2026-09-20
Source audit: `docs/2026-09-20-independent-system-readiness-audit.md` §3-A1
Priority: P0 (highest of audit defects)

## Problem and user-visible impact

`is_cas_eligible(symbol)` currently returns a boolean. The `False` branch
collapses five distinct states:

1. The list is configured and the symbol is in it -> `True`.
2. The list is configured and the symbol is NOT in it -> `False`.
3. The list is empty (the documented default) -> `False`.
4. The list cannot be parsed / `config` import fails -> `False`.
5. `symbol` is `None`, non-string, or empty -> `False`.

States 3, 4, 5 are observation-time-UNAVAILABLE, not "verified NOT in
list". A signed empty-list answer is not proof that a stock is
non-CAS-eligible. The audit captured this defect independently.

The Node resolver currently requires a boolean from
`/market-session/cas-eligibility` and accepts the false result as
resolved evidence. When the configuration is empty (which is the
default), every symbol is treated as "verified not CAS-eligible" and
the affected-window guard effectively becomes a no-op.

## User-visible impact today

- Cash orders placed at 15:15-15:30 IST for symbols that *are* CAS-eligible
  in Production's empty-configuration case are not blocked.
- Owner manual execution can place a trade even when the engine does not
  know whether CAS applies.
- Independent audit (20 September) verified that an in-window RELIANCE
  probe returns `allowed=True`, `phase=CONTINUOUS_TRADING` -- the gate
  does not fire when the configuration is empty.

## Files and contracts affected

  - `python-engine/market_calendar.py` -- replace `is_cas_eligible`
    with a three-state result; keep a legacy boolean shim for the
    test-suite byte-identity (the audit note is the source of truth).
  - `python-engine/routes_market_session.py` -- emit the three-state
    value + a coverage / as-of metadata block.
  - `python-engine/config.py` -- document `CAS_PHASE1_FNO_UNDERLYINGS`
    as the only authoritative membership source.
  - `node-gateway/server/services/cas-eligibility.js` -- surface
    three-state to `entrySessionVerdict`; fail closed when UNKNOWN.
  - `python-engine/tests/test_market_session_route.py` -- extend with
    three-state coverage (ELIGIBLE, NOT_ELIGIBLE, UNKNOWN).
  - New `python-engine/tests/test_cas_eligibility_three_state.py`
    with focused unit tests.
  - New `node-gateway/server/tests/unit/cas-eligibility-three-state.test.js`
    with parity coverage.
  - `docs/2026-09-20-workflow-a1-cas-three-state-done.md` -- done doc.

## Implementation steps

1. **Define `CasEligibilityState`** as a `StrEnum` with three values:
   `ELIGIBLE`, `NOT_ELIGIBLE`, `UNKNOWN`. Frozen module-level constant.
2. **Refactor `is_cas_eligible`** into:
   - `resolve_cas_eligibility(symbol) -> CasEligibilityState`:
     returns UNKNOWN on config import failure / empty list / bad
     input; returns ELIGIBLE / NOT_ELIGIBLE from the membership set.
   - `is_cas_eligible(symbol) -> bool`: keep this for J.1 / J.3 legacy
     callers; returns `True` only when state is ELIGIBLE.
   - `cas_eligibility_reason(symbol) -> str`: returns one of
     `"listed"`, `"not_listed"`, `"config_import_failed"`,
     `"empty_membership_list"`, `"invalid_symbol"`, `"unknown"`.
3. **Expose membership metadata** in `routes_market_session.py`:
   `coverage` (symbol-set membership), `as_of_utc` (server-time stamp),
   `source_hash` (sha256 of the configured CSV), `state` (enum),
   `reason` (enum).
4. **Wire Node resolver** to surface `state`/`reason` and fail closed
   when state is UNKNOWN. The signature input changes from
   `casEligible: boolean` to `casEligibility: { state, reason,
   sourceVersion }`. Old boolean field stays for one release as
   derived: `casEligible = state === 'ELIGIBLE'`.
5. **Fail-closed behaviour** at the executor: any UNKNOWN during the
   affected window blocks new entries. Exit handling continues to use
   the pre-existing market-closed / phase error classes.
6. **Owner entry-only global halt**: add a config knob
   `OWNER_LIVE_ENTRY_HALT` (default `False`). When `True`, the engine
   refuses any new entry (F&O, EDGE, Momentum, Penny) outside shadow
   while exits and management continue. Surface in the operator
   readiness report.
7. **Audit log**: every UNKNOWN resolution during the affected window
   emits a `cas_eligibility_unknown` event to the structured log so
   operators can see when the configuration is missing.
8. **Stale membership**: a date bound -- when membership data is
   older than `CAS_MEMBERSHIP_MAX_AGE_DAYS` (default 30), the resolver
   returns UNKNOWN with reason `stale_membership`. Already partially
   present via `NSE_HOLIDAYS_VALID_THROUGH`; extend the pattern.

## Acceptance / negative / restart / timing tests

  - ELIGIBLE: configured, symbol present, expected.
  - NOT_ELIGIBLE: configured, symbol absent, expected.
  - UNKNOWN:
    - empty `CAS_PHASE1_FNO_UNDERLYINGS`.
    - `config` import raises.
    - symbol is `None` / non-string / empty.
    - membership data older than max age.
  - In affected window (15:15-15:30 IST), an UNKNOWN state must cause
    `entrySessionVerdict.allowed == False` with phase
    `CAS_ELIGIBILITY_UNKNOWN` (distinct from existing
    `CAS_ELIGIBILITY_UNAVAILABLE`).
  - Exit-only paths remain allowed (MarketClosedError / phase class
    not used by exits).
  - Python/Node parity: the resolver on each side must agree on
    ELIGIBLE/NOT_ELIGIBLE/UNKNOWN for the same input.
  - Latency crossing boundary: a 15:14:59 fetch returning ELIGIBLE
    and a 15:15:01 fetch returning UNKNOWN must not both succeed
    silently (the second must block).
  - Restart: `OWNER_LIVE_ENTRY_HALT` is read fresh at process start;
    changes do not require a config-reload API; document the restart
    requirement.

## Data and configuration migration

  - No data migration. Existing tables are untouched.
  - One new config knob: `OWNER_LIVE_ENTRY_HALT` (env var, default
    `False`). Documented in `python-engine/config.py` with the
    explicit list of entry paths it gates.
  - `CAS_MEMBERSHIP_MAX_AGE_DAYS` (env var, default `30`). Documented
    alongside `NSE_HOLIDAYS_VALID_THROUGH`.

## Rollout and rollback

  - Dev only.
  - New config knobs default to safe behaviour (halt OFF, age 30
    days).
  - The legacy `is_cas_eligible` boolean is preserved; the only new
    field in `/market-session/cas-eligibility` is `state` /
    `casEligibility`. Backward-compatible for callers reading only
    `cas_eligible`.
  - Rollback = revert commit. No DB migration; no scheduled jobs
    depend on the new state.

## Status and verified commit

  - Plan committed before implementation: this doc.
  - Implementation commits follow this plan.

## Documentation updated

  - `docs/2026-09-20-workflow-a1-cas-three-state-done.md` (new).
  - `python-engine/market_calendar.py` docstring: rewrite the
    three-state contract.
  - `python-engine/routes_market_session.py` docstring: enumerate
    the new fields.

## Unresolved limits and exact next action

  - Operator input still required: a populated
    `CAS_PHASE1_FNO_UNDERLYINGS` (CSV from the current NSE master).
    Until populated, every symbol is UNKNOWN in the affected window
    and entries are blocked. This is the intended fail-closed
    behaviour; the operator must supply the live list.
  - `OWNER_LIVE_ENTRY_HALT` defaults OFF. A separate decision (out
    of scope for this slice) is needed to flip it on for Monday's
    session.
  - Next action: implement steps 1-8 above; run full test suite;
    commit + push + done-doc.
