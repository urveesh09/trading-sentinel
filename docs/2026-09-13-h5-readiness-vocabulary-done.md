# H5 (dashboard readiness vocabulary) — done and committed

## What landed (commit `b9cfc44`)

**Branch**: `codex/production-correction-hedge-p0`
**Files changed**: 3 (2 new, 1 modified), +636 / -2 lines.

| File | Lines | Purpose |
|---|---|---|
| `python-engine/coverage_vocabulary.py` | NEW, ~250 lines | Bounded dashboard readiness vocabulary: 7 §12 descriptors, 8-state mapping, validator, drift dataclass, summary. |
| `python-engine/operational_coverage.py` | +24/-2 | End-of-report call to `validate_coverage_report`; drift attached to report under `vocabulary_drift`, logged at WARNING. |
| `python-engine/tests/test_coverage_vocabulary.py` | NEW, 22 tests | Descriptor count, mapping, validator, end-to-end integration with `operational_coverage_report`. |

## The seven §12 descriptors

| Descriptor | Dashboard meaning |
|---|---|
| `DISABLED` | The source is registered but explicitly turned off. No data will arrive until an operator enables it. |
| `UNCONFIGURED` | The source has not been configured (no path, no key, no profile). The producer cannot run. |
| `NO_SESSION` | No live or recorded session has produced evidence for this source yet. |
| `NO_SETUP` | The producer ran, but the current session has no setup to report (e.g. a healthy no-trade day). |
| `NO_EVIDENCE` | The producer ran, attempted to record evidence, but none arrived (timeout, upstream outage, instrument gap). |
| `STALE` | The producer last succeeded more than the freshness budget ago. |
| `ERROR` | The producer failed (HTTP error, JSON parse failure, or circuit-breaker open). |

## Mapping from producer states to descriptors

| Producer `state` | §12 descriptor |
|---|---|
| `HEALTHY_NO_SETUP` | `NO_SETUP` |
| `AVAILABLE` | `NO_EVIDENCE` |
| `UNAVAILABLE` | `NO_EVIDENCE` |
| `UNCONFIGURED` | `UNCONFIGURED` |
| `OBSERVED` | `STALE` |
| `SCHEDULER_REJECTED` | `ERROR` |
| `NOT_YET_OBSERVED` | `NO_SESSION` |
| `OBSERVED_USABLE` | `NO_SETUP` |

## Senior-dev design choices

1. **State drift is hard, reason drift is soft.** States are the
   bounded vocabulary contract between `operational_coverage.py`
   and the dashboard UI; reasons are producer-specific strings
   that evolve frequently. A new `state` is a vocabulary violation
   (flagged). A new `reason` is informational (not flagged).
2. **No deletion, no replacement.** The validator adds a
   `vocabulary_drift` key to the report; the existing keys are
   unchanged. The `OperationalCoverage` dashboard component
   continues to render the same `state`/`reason` strings; H5
   only adds boundedness to the producer contract.
3. **Self-validating without halting.** The validator logs at
   WARNING and attaches the drift list to the report. It does
   NOT raise — operators see the gap in their log pipeline AND
   in the report's `vocabulary_drift` field. A future agent
   introducing a new state cannot silently change dashboard
   colours.
4. **Single source of truth.** `STATE_TO_DESCRIPTOR` is a
   frozen dict at import time. The test
   `test_all_eight_states_mapped` asserts that any change to
   the producer's state vocabulary forces a corresponding
   change to the mapping — no silent drift.
5. **Dashboard UI gets a free reference.** `vocabulary_summary()`
   returns a JSON-serialisable dict with all seven descriptors,
   their human-readable displays, and the state-to-descriptor
   mapping. The dashboard can render this as a "what does this
   state mean?" reference panel.

## State-vs-reason drift semantics (explicit)

| Drift type | Semantic | Validator behaviour |
|---|---|---|
| Unmapped state | HARD — vocabulary gap | Flagged in `vocabulary_drift`, logged at WARNING |
| Missing state | HARD — producer bug | Flagged in `vocabulary_drift`, logged at WARNING |
| Unmapped reason on mapped state | SOFT — informational only | Not flagged (reasons evolve) |
| Empty reason | SOFT — not flagged | (covered by "reasons evolve") |

## Verification

| | Before H5 | After H5 |
|---|---|---|
| **Python suite** | 3,004 pass | **3,026 pass** (+22 H5 tests) |
| **Time** | 141.41s | 141.27s |
| **Skipped** | 4 | 4 |
| **Warnings** | 39 | 39 (no new) |
| **Existing operational_coverage test** | 1 pass | 1 pass (extended, still pass) |

## Self-corrections during H5

1. **First draft made reason drift HARD too.** Caught by my own
   test design — the existing test fixture uses reason
   `"no_or_break"` which is a real producer reason not in my
   initial `KNOWN_REASONS`. Refactored to the state-vs-reason
   asymmetry: states are bounded, reasons are informational.
   This is the correct senior-dev design because reasons are
   producer-specific and evolve; trying to enumerate them
   creates churn without value.
2. **First end-to-end test was structurally wrong.** I tried
   to inject an unmapped state by patching
   `partner_manual_advisory.load_advisory_input_status` to
   return a `stage="WATCHING"`. But `operational_coverage.py`
   maps `WATCHING` stage → `UNAVAILABLE` state (mapped). Fixed
   by patching the `_coverage` builder directly so the
   unmapped state passes through unchanged.

## H-series status (full)

| Phase | Status | Commit |
|---|---|---|
| H1 (coroutine guard) | DONE | `dc298e5` + `14961e9` |
| H2 (priority-tier breakdown) | DONE | `52f625e` + `23f332a` |
| H3 (intraday-cache diagnostic) | DONE | `fead40c` + `9780109` |
| H4 (cache-add for by-symbol path) | DONE | `d1d6e15` + `2734851` |
| H4.B (cache-add for by-token path) | DONE | `bfb42ac` + `2b992b8` |
| **H5 (dashboard readiness vocabulary)** | **DONE** | **`b9cfc44`** |

## Next steps (per plan §15)

The H workstream is complete. The remaining workstreams per
`docs/NEXT_AGENT_PLAN.md` are:
- I — optional AI and news (annotation validity TESTED_DEV)
- J — CAS and market-session correctness (NOT_STARTED)

Both are independent of H and ready for the next active slice.
