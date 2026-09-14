# I.C (operational_coverage includes optional AI) — done and committed

## What landed (commit `89a9804`)

**Branch**: `codex/production-correction-hedge-p0`
**Files changed**: 5 (3 modified, 2 new), +663 / -2 lines.

| File | Lines | Purpose |
|---|---|---|
| `python-engine/coverage_vocabulary.py` | +11 | 7 new states in `STATE_TO_DESCRIPTOR` for the optional-AI lifecycle. |
| `python-engine/operational_coverage.py` | +61 / -2 | `optional_ai` producer block; asyncio.gather now loads optional-AI status. |
| `python-engine/tests/test_coverage_vocabulary.py` | +17 / -1 | Updated state count assertion + expanded allow-list test. |
| `python-engine/tests/test_coverage_vocabulary_optional_ai.py` | NEW, 13 tests | Vocabulary mapping for the optional-AI states. |
| `python-engine/tests/test_operational_coverage_optional_ai.py` | NEW, 12 tests | Producer integration: state pass-through, enabled flags, usefulness envelope, drift-free, coexistence. |

## What the optional-AI producer emits

| Field | Source |
|---|---|
| `state` | Engine's `load_optional_ai_status` (pass-through: READY, DISABLED_*, OUTAGE_CIRCUIT_OPEN, UNAVAILABLE, STALE, NOT_REPORTED, CORRUPT_REPORT) |
| `enabled` | `False` for DISABLED_* and NOT_REPORTED; `True` otherwise |
| `counts.pending` / `counts.cached` / `counts.daily_requests` / `counts.daily_budget` / `counts.circuit_state` | From the engine's persisted queue snapshot |
| `counts.stale` | True if the report is older than the freshness window |
| `counts.usefulness` | I.A usefulness envelope, when present; `None` when the operator hasn't opted in |
| `identity.execution_authority` | Always `NONE` (per §13) |
| `identity.can_place_orders` | Always `False` (per §13) |

## Senior-dev design choices

1. **Single producer, not per-account.** The agent is a single worker, not a per-index pipeline like `manual_advisory:NIFTY`. One `optional_ai` producer captures the bounded reality.
2. **Deliberate `UNAVAILABLE` sharing with manual-advisory.** The same word maps to `NO_EVIDENCE` for both producers. Both mean "we tried but no useful answer arrived." The dashboard distinguishes by `producer_id`.
3. **All 7 new states are vocabulary-mapped; no drift.** The H5 validator passes — operators see no warnings when the agent reports any of the 8 engine-emittable states.
4. **No dashboard change needed.** `OperationalCoverage` already iterates over all producers and filters only `scheduler:*` keys; `optional_ai` appears automatically.
5. **`enabled` semantics preserve the §13 contract.** Operator-disabled states set `enabled=False`; provider-failure states set `enabled=True` (the system is configured to run, it's the provider that's down).
6. **Usefulness envelope is `None` when absent.** The dashboard can distinguish "operator hasn't opted in" from "operator opted in but no reviews yet."

## Verification

| | Before I.C | After I.C |
|---|---|---|
| **Agent suite** | 174 pass | 174 pass (unchanged) |
| **python-engine suite** | 3,047 pass | **3,072 pass** (+25) |
| **Dashboard build** | OK | OK |
| **Time** | 141.58s | 144.92s |
| **Skipped / warnings** | 4 / 42 | 4 / 42 (no new categories) |

## Self-corrections during I.C

1. **Test fixture: `asyncio.run` inside an event loop.** My first cut of the helper used `asyncio.run()` to call `record_optional_ai_status`, which fails inside pytest-asyncio's running loop. Fixed by making the helper an `async def` and using `await` from the test body.
2. **`NOT_REPORTED` is engine-side, not agent-POSTable.** My first loop tried to POST `NOT_REPORTED`, which the engine's `_ALLOWED_STATES` rejects — that's correct behaviour. Fixed by separating "agent-POSTable states" (READY, DISABLED_*, OUTAGE_CIRCUIT_OPEN) from "engine-side states" (STALE, NOT_REPORTED, CORRUPT_REPORT). The latter are tested via `load_optional_ai_status` directly.
3. **`UNAVAILABLE` already in the vocabulary.** Pre-I.C, the manual-advisory producer emitted `UNAVAILABLE` and mapped to `NO_EVIDENCE`. I assumed the optional-AI's `UNAVAILABLE` would map to `ERROR` (different semantic — call failed). The test caught this collision: my parameterization was wrong, and the right answer is to keep the shared mapping. The dashboard distinguishes by `producer_id`. Tests updated to document the shared mapping.
4. **State count was 16, not 15.** I miscounted by hand (forgot UNAVAILABLE was already in the original). The test caught the off-by-one. Fixed and the docstring now correctly says 16.

## Combined I.A + I.B + I.C state

Three of the four recommended slices from `docs/2026-09-13-i4-deep-research.md` are now SHIPPED:
- ✅ **I.A** — bridge I3 usefulness metrics (`980636e`)
- ✅ **I.B** — surface I1 provenance in the alert (`d1e7d4f`)
- ✅ **I.C** — `operational_coverage_report` includes optional AI (`89a9804`)

Remaining:
- **I.F** — cross-container contract test (the simplest of the four; a round-trip test that POSTs a known-bad envelope and asserts the engine rejects it)

## Next steps

Awaiting your call to proceed to I.F, or another slice.
