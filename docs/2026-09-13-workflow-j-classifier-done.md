# J.1 (CAS-aware session classifier) — done and committed

## What landed (commit `d82258f`)

**Branch**: `codex/production-correction-hedge-p0`
**Files changed**: 4 (1 modified, 3 new), +1,003 / -0 lines.

| File | Lines | Purpose |
|---|---|---|
| `python-engine/market_calendar.py` | +240 | Central session constants + `classify_session_phase` + `is_cas_eligible` |
| `python-engine/tests/test_session_classifier.py` | NEW, 41 tests | Bounded classifier contract tests |
| `docs/2026-09-13-workflow-j-deep-research.md` | NEW | Verified NSE/BSE facts, hard-coded clocks inventory |
| `docs/2026-09-13-workflow-j-classifier-plan.md` | NEW | Plan slice (problem/files/acceptance/rollback) |

## Verified NSE/BSE facts (from primary sources, 2026-09-13)

| Source | Effective | Detail |
|---|---|---|
| NSE/CMTR/72394 | 2026-01-19 | CAS Phase 1 introduced |
| NSE/CMTR/73362 | 2026-03-18 | CAS SOP |
| NSE/CMTR/76170 | 2026-09-07 | Index futures CAS-aligned price band |
| NSE CAS page | current | CAS 15:15–15:35; continuous 09:15–15:30 cash; 09:15–15:40 derivatives |
| BSE Notice 20260801-2 | 2026-08-03 | BSE derivatives CAS 15:15–15:40 |

## What the classifier produces

Ten bounded phase values, each with a documented NSE source:

| Phase | IST window |
|---|---|
| `CLOSED` | weekend, 00:00-08:59, 16:00-23:59 |
| `PRE_MARKET` | 09:00-09:14 |
| `CONTINUOUS_TRADING` | 09:15-15:14 (cash) / 09:15-15:29 (derivatives) |
| `CAS_REFERENCE_PRICE_WINDOW` | 15:15-15:19 (CAS-eligible cash) |
| `CAS_ORDER_ENTRY` | 15:20-15:24 (CAS-eligible cash) |
| `CAS_LIMIT_ENTRY_ONLY` | 15:25-15:29 (CAS-eligible cash) |
| `CAS_MATCHING` | 15:30-15:34 (CAS-eligible cash) |
| `DERIVATIVES_CAS_ALIGNED` | 15:30-15:39 (derivatives) |
| `CAS_POST` | 15:35-15:59 (CAS-eligible cash) |
| `UNKNOWN` | `observation_at is None` |

## Senior-dev design choices

1. **Zero production behaviour change.** The classifier is **additive**; `is_market_open`, `is_trading_day`, `stamp_session_phase`, and all production call sites are unchanged.
2. **Pure and total.** `classify_session_phase` does no I/O, no clock, no DB, no logging, no broker call. Every input returns one of 10 phases. Never raises.
3. **Phase-only (not holiday-aware).** The classifier does NOT consult `NSE_HOLIDAYS_STATIC`. Callers that need holiday-awareness combine this with `is_trading_day_sync`. The two concerns are deliberately separate.
4. **CAS eligibility list empty in Dev.** `is_cas_eligible` returns `False` for every symbol with a documented reason. Operators populate the list in a future slice when they know. The classifier still labels CAS windows correctly (CAS-aware phase names exist) but eligibility is explicit `False` until then.
5. **`stamp_session_phase` contract preserved.** The existing G forward-compat seam still returns `_SESSION_PHASE_UNKNOWN` for every input. The new classifier is **available** for J.2+ callers; it does not yet replace the placeholder, because plan §14 requires broker-behaviour verification before strategy-aware phases can be trusted.
6. **Derivatives CAS-aligned band as a separate phase.** NSE/CMTR/76170 effective 2026-09-07 introduces a ±3% price band for index/stock futures from 15:30-15:40 IST. This is **not** the same as cash CAS matching — derivatives don't have an order entry / order matching cycle, just an aligned price band. The classifier returns `DERIVATIVES_CAS_ALIGNED` for derivative symbols in 15:30-15:39 IST.

## Verification

| | Before J.1 | After J.1 |
|---|---|---|
| **python-engine targeted tests** (calendar + sessions) | 59 | **100** (+41) |
| **F/G critical + J critical (warning-fatal)** | (not measured) | **225/225 pass** |
| **Agent suite** | 177 pass | 177 pass (unchanged) |
| **Dashboard build** | OK | OK |
| **Whole-suite in isolation** | 3,089 | 3,130 when run in isolation; full-suite run shows the same 2 pre-existing intermittent failures (test_mark_to_market, test_scheduler_h2_timing_tiers — both pass in isolation, documented as cross-test isolation noise by the parallel agent) |

## Self-corrections during J.1

1. **`datetime` import** — I initially added a spurious `timezone as _dt_timezone` import I didn't use. Caught on the second review and reverted.
2. **CAS eligibility semantics** — my first cut treated `15:15-15:29` for derivatives as falling through to `CLOSED`. Caught by manual trace: equity derivatives trade continuously through 15:29 IST (NSE equity derivatives end at 15:40). Fixed by adding the derivative-specific branch.
3. **Boundary at 15:40 IST** — my first cut had `< deriv_close` for the CAS-aligned band (correct) but no fallback for `deriv_close ≤ time < cas_post_end` (derivatives 15:40-15:59 IST). At exactly 15:40 IST the classifier was returning `UNKNOWN` (the defensive fallback). Caught by the manual test harness; fixed by adding the explicit `CLOSED` branch.
4. **CAS eligibility test setup** — the Phase 1 list is empty in Dev, so the CAS-window tests needed a `monkeypatch` to simulate an operator-populated list. Added the `cas_eligible_world` fixture.

## What was NOT changed (explicitly preserved)

- `fno_chain.py::EXPIRY_CUTOFF_HOUR/_MIN = 15, 30` — the 15:30 → 15:40 mismatch for derivatives is **documented** but **not fixed** (per plan §14: "Preserve earlier strategy deadlines unless explicitly revised and qualified").
- `hedge_strategies.py::_EXPIRY_CUTOFF = time(15, 30)` — same reasoning.
- `market-hours.js` (Container B) parity — deferred to J.2.
- Holiday reconciliation between Python and Node — deferred to J.2.
- `stamp_session_phase` (the G forward-compat seam) — unchanged.
- Broker-behaviour verification — NOT done (no live broker in Dev); required before J.2 can change strategy behaviour.

## Honest scope statement

J.1 is the **smallest correct slice**. It introduces the classifier and central constants without changing any production behaviour. The classifier is the seam J.2+ callers will use when broker behaviour is verified (real Kite probe at 15:15 IST on a CAS-eligible stock). Until then, the classifier is available but unused in production code paths.

## Next steps

Awaiting your call to:
- proceed to J.2 (CAS eligibility list + broker-behaviour probe),
- run a fresh whole-engine sanity check,
- or pivot to another slice.
