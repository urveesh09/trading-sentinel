# J.1 — CAS-aware session classifier (slice for workstream J)

## Problem

Plan §14 requires inventorying hard-coded clocks and introducing an
exchange/security/session-phase model after verifying effective dates
and broker behavior. The deep-research doc
(`docs/2026-09-13-workflow-j-deep-research.md`) surfaced:

  1. Zero CAS awareness in `market_calendar.py` and `market-hours.js`.
  2. `EXPIRY_CUTOFF` constants assume 15:30 for both cash and
     derivatives, but equity derivatives close at 15:40.
  3. Holiday lists disagree between Python and Node.
  4. `stamp_session_phase` is a placeholder returning
     `_SESSION_PHASE_UNKNOWN` for every input.

We have verified NSE/BSE effective dates from primary sources. We
have NOT verified broker behavior (no live broker in Dev). Therefore
this slice introduces the classifier, leaves existing behavior
unchanged, and surfaces the gaps via tests.

## Senior-dev design analysis

The single most important design choice: **do not change any
production behavior in this slice.** Per plan §14, broker-behaviour
verification is required before introducing a session-aware
strategy. We add a classifier and constants; everything else stays
as-is. The classifier is the seam that J.2 (or any future
CAS-eligible strategy) will consume.

The classifier must:

  1. Be **pure**: given (timestamp_utc, symbol, exchange), return
     a phase. No I/O.
  2. Be **total**: every (timestamp, symbol) returns a known phase.
     Unknown instruments return UNKNOWN, not raise.
  3. Be **documented**: each phase has a primary-source citation.
  4. Be **side-effect-free**: it does not touch the DB, does not
     log, does not call the broker.

## Files affected

EDIT `python-engine/market_calendar.py`:
  - Add `SessionPhase` enum (CLOSED / PRE_MARKET / CONTINUOUS_TRADING
    / CAS_REFERENCE_PRICE_WINDOW / CAS_ORDER_ENTRY /
    CAS_LIMIT_ENTRY_ONLY / CAS_MATCHING / CAS_POST /
    DERIVATIVES_CLOSE / UNKNOWN).
  - Add named constants: `MARKET_OPEN_TIME = time(9, 15)`,
    `MARKET_CLOSE_TIME = time(15, 30)`,
    `DERIVATIVES_CLOSE_TIME = time(15, 40)`,
    `CAS_OPEN_TIME = time(15, 15)`,
    `CAS_CLOSE_TIME = time(15, 35)`,
    `CAS_POST_CLOSE_TIME = time(16, 0)`.
  - Add `classify_session_phase(observation_at, symbol=None,
    is_derivative=False) -> SessionPhase` — pure function.
  - Add `is_cas_eligible(symbol: str) -> bool` — Phase 1 list is
    empty in Dev; returns False with a documented reason. Operators
    populate via config later.

EDIT `python-engine/proactive_intelligence.py`:
  - `stamp_session_phase` now calls the classifier.
    Behaviour change: the manifest key will carry the
    `SessionPhase` value (or "UNKNOWN" when no symbol).

EDIT `python-engine/tests/test_market_calendar.py`:
  - New tests for ordinary day phases.
  - CAS window tests (15:15, 15:25, 15:32 IST).
  - Derivatives close test (15:35 IST on a derivatives symbol).
  - Holiday tests.
  - Pre-market test.
  - Unknown-symbol test.

EDIT `python-engine/tests/test_session_phase_placeholder.py`:
  - Existing tests assert `_SESSION_PHASE_UNKNOWN` is returned.
    We preserve that for `symbol=None` (no instrument context).
    New tests assert that with a symbol and CAS time, the
    classifier returns the correct CAS phase.

NEW `python-engine/tests/test_session_classifier.py`:
  - Bounded classifier tests.

NO CHANGES to:
  - `fno_chain.py` — `EXPIRY_CUTOFF_HOUR/_MIN = 15, 30` stays.
    The 15:30 → 15:40 mismatch is documented but not fixed (plan
    §14: "Preserve earlier strategy deadlines unless explicitly
    revised and qualified").
  - `hedge_strategies.py` — same reasoning.
  - `market-hours.js` — out of scope (Container B). Defer to J.2.
  - Holidays in `market-hours.js` — out of scope. Defer to J.2.

## Dependencies

  - Existing `market_calendar.py` (IST, NSE_HOLIDAYS_STATIC,
    is_market_open, is_trading_day_sync, _load_holidays_sync).
  - Existing `proactive_intelligence.py` (`stamp_session_phase`,
    `_SESSION_PHASE_UNKNOWN`).

## Acceptance / negative / restart / timing tests

  - ≥10 new tests in `test_market_calendar.py` and
    `test_session_classifier.py` covering:
    * ordinary day (09:30, 12:00, 14:55 IST) → CONTINUOUS_TRADING
    * pre-market (09:05 IST) → PRE_MARKET
    * closed before open (08:00 IST) → CLOSED
    * closed after market close (16:30 IST) → CLOSED
    * CAS reference price window (15:17 IST) → CAS_REFERENCE_PRICE_WINDOW
    * CAS order entry (15:22 IST) → CAS_ORDER_ENTRY
    * CAS limit entry only (15:27 IST) → CAS_LIMIT_ENTRY_ONLY
    * CAS matching (15:32 IST) → CAS_MATCHING
    * CAS post window (15:40 IST) → CAS_POST
    * Derivatives close (15:35 IST, is_derivative=True) → DERIVATIVES_CLOSE
    * Holiday (any time) → CLOSED
    * Weekend (Saturday) → CLOSED
    * Symbol without CAS eligibility → CAS window still returns the
      CAS phase (the classifier is phase-based, not eligibility-
      based); `is_cas_eligible` returns False.
  - Existing tests pass (174 agent + 3089 python-engine unchanged).
  - `stamp_session_phase(None)` still returns "UNKNOWN" — preserved
    behaviour for the existing call sites.
  - `stamp_session_phase(some_datetime)` returns the correct phase
    for that IST timestamp.
  - Whole-engine green.

## Rollout and rollback

  - No production code paths changed (the new classifier is
    invoked by `stamp_session_phase` but the existing call sites
    pass `observation_at=None` or a non-symbol, so the output
    remains "UNKNOWN" for the production manifest).
  - Rollback = git revert. The classifier is additive.

## Status and verified commit

  - Status: IMPLEMENTING
  - Branch: `codex/production-correction-hedge-p0`
  - HEAD before: `0f7120b`

## Documentation updated

  - `docs/2026-09-13-workflow-j-deep-research.md` (DONE)
  - `docs/2026-09-13-workflow-j-classifier-done.md` (planned)
  - `docs/NEXT_AGENT_PLAN.md` matrix row J — IMPLEMENTING

## Unresolved limits and exact next action

  - Phase 1 CAS eligibility list is empty. Operator must populate.
    This is documented in `is_cas_eligible`.
  - Broker-behaviour verification NOT done. J.2 (broker-feed probe
    on a CAS-eligible stock at 15:15 IST) is the next slice.
  - `market-hours.js` parity deferred.
  - Holiday reconciliation between Python and Node deferred.
