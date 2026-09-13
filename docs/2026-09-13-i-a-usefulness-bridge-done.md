# I.A (usefulness-bridge agent → engine) — done and committed

## What landed (commit `980636e`)

**Branch**: `codex/production-correction-hedge-p0`
**Files changed**: 6 (4 modified, 2 new), +650 / -1 lines.

| File | Lines | Purpose |
|---|---|---|
| `agent/agent.py` | +13 | New `OPTIONAL_AI_REPORT_USEFULNESS` env var; `optional_ai_status()` includes `usefulness` envelope under the flag, only when the queue has been created. |
| `agent/tests/test_optional_ai_status_usefulness.py` | NEW, 4 tests | Default flag omits, opt-in includes, no-queue omits, flag is read once per module load. |
| `python-engine/optional_ai_status.py` | +97 | New `_ALLOWED_USEFULNESS_KEYS`, `_ALLOWED_VERDICT_KEYS` allow-lists; new `_clean_usefulness` strict validator; persistence path stores clean envelope in `detail["usefulness"]`. |
| `python-engine/routes_ops.py` | +7 | `OptionalAiStatusPayload` accepts `usefulness` field (real bug caught by tests: Pydantic was silently dropping it). |
| `python-engine/tests/test_optional_ai_usefulness_bridge.py` | NEW, 21 tests | Validator, persistence, route surface, bounded contract (no review payload leak, no prompt leak, no credential leak). |
| `node-gateway/client/src/pages/Dashboard.jsx` | +36 | `OptionalAiEvidence` renders bounded usefulness evidence panel with `Not enabled` fallback. |

## The bounded contract

| Field | Type | Range | Source |
|---|---|---|---|
| `total_completed_reviews` | int | ≥ 0 | `AsyncReviewQueue` |
| `cache_hits` | int | ≥ 0 | `AsyncReviewQueue` |
| `cache_misses` | int | ≥ 0 | `AsyncReviewQueue` |
| `circuit_opens` | int | ≥ 0 | `AsyncReviewQueue` |
| `response_seconds_last` | float or None | ≥ 0 | `AsyncReviewQueue` |
| `verdict_counts.APPROVE` | int | ≥ 0 | `AsyncReviewQueue` |
| `verdict_counts.APPROVE_WITH_CONCERNS` | int | ≥ 0 | `AsyncReviewQueue` |
| `verdict_counts.REVIEW_UNAVAILABLE` | int | ≥ 0 | `AsyncReviewQueue` |
| `verdict_counts.REJECT` | int | ≥ 0 | `AsyncReviewQueue` |

The validator **rejects** any unknown key (does NOT silently drop) so a future agent code change can't smuggle in fields like `pitch` or `rationale`. The four verdict buckets are always emitted (missing buckets default to zero) so the dashboard can assume the contract shape.

## Senior-dev design choices

1. **Opt-in by default.** `OPTIONAL_AI_REPORT_USEFULNESS` defaults to `false`. Existing operator dashboards see no change. The rollback path is one env var; no code change required.
2. **No zero-fill when the queue has never run.** The envelope is included only when `_optional_ai_queue is not None` — a never-used agent never publishes zeros that masquerade as data.
3. **Strict validator.** Any unknown key, type mismatch, or out-of-range value raises `ValueError`. The route maps to HTTPException(422). The previous report remains on disk so operators see the contract drift rather than silently losing the prior record.
4. **Derived numbers computed on the dashboard side.** Cache hit rate is calculated by the dashboard from `cache_hits` and `cache_misses`. The bridge never ships derived numbers — operators can verify the math themselves.
5. **Real bug caught by tests.** The `OptionalAiStatusPayload` Pydantic model did not declare `usefulness`. Pydantic's default `ignore_unknown_keys=True` would have silently dropped the field at the route boundary. Tests caught this; the fix was a one-line Pydantic declaration.
6. **No cross-container expansion of the agent surface.** The agent's `usefulness_snapshot()` is unchanged; only the producer (`optional_ai_status`) wraps it.

## Verification

| | Before I.A | After I.A |
|---|---|---|
| **Agent suite** | 149 pass | **153 pass** (+4) |
| **python-engine suite** | 3,026 pass | **3,047 pass** (+21) |
| **Dashboard build** | OK | OK |
| **Time** | 140.06s | 142.67s |
| **Skipped** | 4 | 4 |
| **Warnings** | 39 | 39 + 3 (httpx TestClient deprecations; same category as existing baseline) |

## Self-corrections during I.A

1. **Test fixture mismatch.** My first cut of route-surface tests took the `db_path` fixture, but the route handlers bind to `settings.DB_PATH` (the global) — the per-test tmp DB was bypassed. Fixed by removing the fixture from route tests; route tests now write to the global DB and rely on `INSERT OR REPLACE` for idempotency.
2. **Pydantic silently dropped `usefulness`.** The first run of the route tests returned 200 even for malformed envelopes because Pydantic stripped the unknown field before the validator ever saw it. Real bug in the bridge: the field would have been lost at the route boundary. Fixed by declaring `usefulness: dict | None = None` on `OptionalAiStatusPayload`.

## Phase I.A closure

The I.A opportunity from `docs/2026-09-13-i4-deep-research.md` is now SHIPPED. The dashboard renders the new bounded counters with a clear `Not enabled` fallback for operators who haven't opted in. Operators who want the bridge can set `OPTIONAL_AI_REPORT_USEFULNESS=true` on the agent and immediately see verdict counts, cache hit rate, last response time, and circuit-open counts.

## Next steps

The recommended I.A + I.B + I.C + I.F slice list from the deep research:
- **I.A** ✅ shipped (`980636e`)
- **I.B** — surface I1 provenance in the operator alert (10-20 lines)
- **I.C** — `operational_coverage_report` includes optional AI (~30-50 lines)
- **I.F** — cross-container contract test (≥1 round-trip test)

Awaiting your call to proceed to I.B or another slice.
