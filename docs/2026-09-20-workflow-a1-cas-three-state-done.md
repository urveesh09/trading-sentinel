# Workflow A1 — CAS eligibility three-state + owner authority entry-only halt (DONE)

Date: 2026-09-20
Source audit: `docs/2026-09-20-independent-system-readiness-audit.md` §3-A1
Branch: `codex/production-correction-hedge-p0`
Status: ✅ shipped

## Problem

The legacy `market_calendar.is_cas_eligible(symbol) -> bool` collapsed
five distinct states into a single boolean:

| Input | Legacy return | Operational meaning |
|---|---|---|
| Configured list, symbol present | `True` | Verified ELIGIBLE |
| Configured list, symbol absent | `False` | Verified NOT_ELIGIBLE |
| List empty (the documented default) | `False` | **No information** |
| `config` import fails | `False` | **No information** |
| Symbol is `None` / non-string / empty | `False` | **No information** |

The last three should not be reported as `False` because they are
"unknown", not "verified absent". The Node resolver accepted the
false result as resolved evidence, so an empty membership list
silently turned the affected-window guard into a no-op. The audit
captured this with an in-window RELIANCE probe returning
`allowed=True`, `phase=CONTINUOUS_TRADING`.

Per `docs/2026-09-20-independent-system-readiness-audit.md` §4, the
audit also flagged that manual Momentum Telegram execution remains
broker-capable after the per-sleeve live-disable switches, so the
operator has no single lever to silence all new entries while
preserving exits.

## Fix

1. **Three-state resolver.** `resolve_cas_eligibility(symbol) ->
   CasEligibilityState` returns `ELIGIBLE`, `NOT_ELIGIBLE`, or
   `UNKNOWN`. The legacy `is_cas_eligible(symbol) -> bool` is
   preserved as a derived shim that returns `True` only when the
   state is `ELIGIBLE`.
2. **Six reason codes.** `cas_eligibility_reason(symbol) ->
   CasEligibilityReason` returns stable strings: `listed`,
   `not_listed`, `empty_membership_list`, `config_import_failed`,
   `invalid_symbol`, `stale_membership`.
3. **Membership provenance.** A `CasMembershipMetadata` dataclass
   surfaces `configured_size`, `raw_csv_sha256`, `max_age_days`,
   `is_stale`. Operators can see what the resolver knows and when it
   knew it.
4. **Route update.** `/market-session/cas-eligibility` now emits
   `state`, `reason`, `coverage`, `as_of_utc` alongside the derived
   `cas_eligible`. HMAC signature covers `symbol|state|reason|version`.
5. **Node resolver parity.** `entrySessionVerdict` now returns the
   new `state`/`reason`/`coverage` fields and surfaces
   `CAS_ELIGIBILITY_UNKNOWN` as a distinct phase from
   `CAS_ELIGIBILITY_UNAVAILABLE`. UNKNOWN blocks entry explicitly.
6. **Owner entry-only halt.** `OWNER_LIVE_ENTRY_HALT` (env var,
   default `False`) is a master kill-switch that refuses every NEW
   entry outside shadow. Exits and management continue.
7. **Per-channel controls.** `OWNER_LIVE_ENTRY_HALT_CHANNELS`
   (comma-separated channel list, default empty) silences named
   sleeves without halting the rest.
8. **Audit log.** UNKNOWN resolutions during the affected window
   emit a `cas_eligibility_unknown` event so operators can see when
   the configuration is missing.

## Files

| File | Change |
|---|---|
| `python-engine/market_calendar.py` | Added `CasEligibilityState`, `CasEligibilityReason`, `CasMembershipMetadata`, `resolve_cas_eligibility`, `cas_eligibility_reason`, `cas_membership_max_age_days`. `is_cas_eligible` is now a derived shim. |
| `python-engine/routes_market_session.py` | Emits `state`, `reason`, `coverage`, `as_of_utc`; HMAC signature updated. |
| `python-engine/config.py` | Two new env knobs: `OWNER_LIVE_ENTRY_HALT` (default False), `OWNER_LIVE_ENTRY_HALT_CHANNELS` (default empty). |
| `python-engine/owner_entry_halt.py` | New module: `EntryHaltVerdict`, `HaltChannel`, `is_owner_entry_halted`. |
| `node-gateway/server/services/cas-eligibility.js` | Three-state projection, `CAS_ELIGIBILITY_UNKNOWN` phase, structured eligibility payload. |
| `python-engine/tests/test_cas_three_state_and_owner_halt.py` | New: 26 tests pinning the three-state contract + halt surface. |
| `python-engine/tests/test_market_session_route.py` | Extended: 5 tests including UNKNOWN coverage. |
| `node-gateway/server/tests/unit/cas-eligibility.test.js` | Extended: 11 tests including three-state parity. |

## Tests

  - `tests/test_cas_three_state_and_owner_halt.py` — **26/26 PASS**.
  - `tests/test_market_session_route.py` — **5/5 PASS** (3 new tests).
  - `node-gateway/server/tests/unit/cas-eligibility.test.js` —
    **11/11 PASS** (4 new tests).
  - python-engine full suite — **4153 passed, 4 skipped**.
  - node-gateway server tests — no regressions observed (CAS + executor suites both green).

## Acceptance

The audit-required acceptance checks are met:

  - Empty `CAS_PHASE1_FNO_UNDERLYINGS` now reports
    `state=UNKNOWN, reason=empty_membership_list` (was `cas_eligible=False`,
    silently turning the guard off).
  - Genuine RELIANCE probe in the affected window returns
    `phase=CAS_ELIGIBILITY_UNKNOWN` (was `CONTINUOUS_TRADING`).
  - Genuinely non-CAS stock (`TCS`) reports
    `state=NOT_ELIGIBLE, reason=not_listed` (verified absent).
  - Python/Node parity: Node `entrySessionVerdict` accepts the new
    `state`/`reason` fields; rejects payloads missing them; HMAC
    signature covers all four fields.
  - Exit handling remains permitted (the halt refuses NEW entries;
    exits use the existing MarketClosedError / CasPhaseError
    surfaces).
  - `OWNER_LIVE_ENTRY_HALT=True` blocks every channel with reason
    `global_owner_entry_halt`; per-channel CSV blocks only the named
    sleeve. Config-import failure refuses every entry (fail closed).

## Operator decisions still required

  - Populate `CAS_PHASE1_FNO_UNDERLYINGS` with the current NSE
    Phase-1 membership CSV. Until populated, every symbol is
    UNKNOWN in the affected window and entries are blocked.
  - Decide whether to flip `OWNER_LIVE_ENTRY_HALT=True` for the
    Monday session. Default OFF; a separate decision is required.
  - Optionally set `OWNER_LIVE_ENTRY_HALT_CHANNELS` to silence a
    single sleeve (e.g. `momentum`).

## Rollout / rollback

  - Dev only.
  - Backward-compatible: `cas_eligible` boolean is preserved as a
    derived field.
  - Rollback = revert commit. No DB migration; no scheduled jobs
    depend on the new state.
