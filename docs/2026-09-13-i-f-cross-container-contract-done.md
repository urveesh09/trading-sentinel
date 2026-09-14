# I.F (cross-container contract test) — done and committed

## What landed (commit `a226ec3`)

**Branch**: `codex/production-correction-hedge-p0`
**Files changed**: 3 (2 modified, 1 new), +624 / -0 lines.

| File | Lines | Purpose |
|---|---|---|
| `python-engine/optional_ai_status.py` | +4 | Consistency fix in `load_optional_ai_status`: NOT_REPORTED and CORRUPT_REPORT paths now return explicit None values for `reported_at`, `reported_state`, `received_at`, and `detail={}` so every key is always present. |
| `python-engine/tests/test_optional_ai_cross_container_contract.py` | NEW, 17 tests | Versioned contract test: envelope acceptance, nothing dangerous crosses, round-trip preservation, public-GET contract, versioned contract table. |
| `agent/tests/test_optional_ai_status_usefulness.py` | +132 / -0 | I.F agent-side: `TestAgentPayloadContract` asserts the agent's payload keys are a subset of the documented contract. |

## The versioned contract

The contract is documented as **frozen sets** at the top of `test_optional_ai_cross_container_contract.py`:

```python
AGENT_PAYLOAD_KEYS = frozenset({
    "state", "reported_at", "async_requested", "policy_allows_annotation",
    "reason", "queue", "usefulness",  # optional
})

ENGINE_PERSISTED_KEYS = frozenset({
    "async_requested", "policy_allows_annotation", "queue", "reason",
    "execution_authority", "can_place_orders", "usefulness",  # conditional
})

ENGINE_QUEUE_KEYS = frozenset({
    "pending", "cached", "daily_requests", "daily_budget",
    "max_pending", "circuit_state",
})

ENGINE_USEFULNESS_KEYS = frozenset({
    "total_completed_reviews", "cache_hits", "cache_misses",
    "circuit_opens", "response_seconds_last", "verdict_counts",
})

ENGINE_VERDICT_KEYS = frozenset({
    "APPROVE", "APPROVE_WITH_CONCERNS",
    "REVIEW_UNAVAILABLE", "REJECT",
})
```

If a future engineer adds a key on the producer side without updating the engine, or vice-versa, **a clear failure message** points to the drift:
- `"agent payload drifted from contract: {...}"`
- `"engine persisted undocumented keys: {...}"`
- `"agent usefulness drifted from engine allow-list: {...}"`

## Senior-dev design choices

1. **Versioned contract, not strict equals.** A legitimate schema addition requires deliberate change: update the contract table, update the validator, run the suite. The test fails until both sides agree.
2. **Frozen sets at the top of the file.** The contract is a single source of truth; tests import it and assert against it. A typo in a future test is caught by the contract table.
3. **The contract tests are bidirectional.** Both the agent side (payload keys) and the engine side (persisted keys, public-GET keys) have explicit tests. Drift in either direction fails the suite.
4. **The §13 contract is hardcoded at the engine.** `execution_authority` is always `"NONE"` and `can_place_orders` is always `False`. The agent cannot override these — a test asserts that even an attempted override is silently ignored.
5. **A real bug was caught.** Pre-I.F, `load_optional_ai_status` returned a dict that was *missing keys* on the NOT_REPORTED/CORRUPT_REPORT paths. The dashboard couldn't iterate over `loaded["received_at"]` reliably. Fixed in 4 lines: explicit None values on those paths. Caught by `TestPublicGetContract.test_return_keys_are_exactly_documented`.

## Verification

| | Before I.F | After I.F |
|---|---|---|
| **Agent suite** | 174 pass | **177 pass** (+3) |
| **python-engine suite** | 3,072 pass | **3,089 pass** (+17) |
| **Dashboard build** | OK | OK |
| **Time** | 144.92s | ~145s (similar) |
| **Skipped / warnings** | 4 / 42 | 4 / 42 (no new categories) |

## Self-corrections during I.F

1. **`asyncio.run` inside an event loop** (same lesson as I.C) — caught and fixed.
2. **`AsyncReviewQueue.__new__` skips `__init__` so `_lock` doesn't exist** — caught by `test_usefulness_keys_match_engine_allow_list`. Fixed by building a simple stub class instead of `__new__`-ing a real one.
3. **Engine-side contract gap (NOT_REPORTED missing keys)** — caught by `TestPublicGetContract`. Fixed with a 4-line consistency patch. This is a *real bug fix* surfaced by the test, not a test-only change.

## Real bug fix: `load_optional_ai_status` consistency

Before I.F:
```python
if row is None:
    return {**base, "state": "NOT_REPORTED", "stale": True,
            "note": "..."}  # missing: reported_at, reported_state, received_at, detail
```

After I.F:
```python
if row is None:
    return {**base, "state": "NOT_REPORTED", "stale": True,
            "reported_at": None, "reported_state": None,
            "received_at": None, "detail": {},
            "note": "..."}  # all documented keys present
```

Operators iterating over `loaded["received_at"]` now always find a key — either the ISO string or `None`. The dashboard no longer needs to special-case "is this key present?".

## Combined I.A + I.B + I.C + I.F state

**All four recommended slices from `docs/2026-09-13-i4-deep-research.md` are now SHIPPED:**
- ✅ **I.A** — bridge I3 usefulness metrics (`980636e`)
- ✅ **I.B** — surface I1 provenance in the alert (`d1e7d4f`)
- ✅ **I.C** — `operational_coverage_report` includes optional AI (`89a9804`)
- ✅ **I.F** — cross-container contract test (`a226ec3`)

The four-slice plan is complete. The optional-AI subsystem now:
1. Captures bounded usefulness counters on the agent side (I3)
2. Surfaces provenance on every review (I1)
3. Persists provenance and bounded counters in the engine (I.A)
4. Surfaces provenance to the operator in the alert (I.B)
5. Integrates the optional-AI producer into the dashboard's `OperationalCoverage` (I.C)
6. Asserts the cross-container contract at CI time (I.F)

## Remaining deferred opportunities (per I4 deep research)

- **D** — Source-event classification (plan §13 explicit gap; deferred — new annotation logic, separate slice)
- **E** — Periodic self-evaluation cron (deferred — low value)
- **G** — Per-ticker annotation breakdown (deferred — medium value, high cost)

## Next steps

The I series is now substantially complete. Awaiting your call to:
- proceed to the next workstream (J — CAS and market-session correctness)
- implement one of the deferred I.D / I.E / I.G opportunities
- ship as-is for the 2026-09-14 PROD target
