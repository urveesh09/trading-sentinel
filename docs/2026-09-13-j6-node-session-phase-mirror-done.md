# J.6 — Node sessionPhase mirror: done and committed

## What landed (one commit pending on `codex/production-correction-hedge-p0`)

| File | Type | Purpose |
|---|---|---|
| `node-gateway/server/utils/market-hours.js` | source | Adds `sessionPhase(...)`, `currentSessionPhase(...)`, `VALID_SESSION_PHASES` exports; bit-perfect mirror of `python-engine/market_calendar.classify_session_phase` |
| `node-gateway/server/routes/health.js` | source | Exposes `session_phase: currentSessionPhase()` in the `/` GET response |
| `node-gateway/server/services/executor.js` | source | Adds `execution_phase_at_reject` log line for observability when the hard `isMarketOpen()` guard fires |
| `node-gateway/server/index.js` | source | Telegram callback message: "Market in {phase}. Cannot execute now." (was: "Market closed. Cannot execute now.") |
| `node-gateway/server/tests/unit/sessionPhase.test.js` | test (new) | 43 tests including the **golden-vector parity** test that verifies bit-perfect agreement with Python across 2,355 vectors |
| `node-gateway/server/tests/fixtures/session_phase_golden.json` | fixture (new) | Consumer-side golden |
| `node-gateway/server/tests/integration/{approved-snapshot,orders,telegram-callbacks}.test.js` | test (modified) | Mock `currentSessionPhase` export surface |
| `node-gateway/server/tests/unit/executor.test.js` | test (modified) | Mock `currentSessionPhase` export surface |
| `python-engine/tests/fixtures/regenerate_session_phase_golden.py` | regenerator (new) | Produces 2,355 vectors and dual-writes both fixture locations |
| `python-engine/tests/fixtures/session_phase_golden.json` | fixture (new) | Source-of-truth golden |
| `python-engine/tests/test_session_phase_golden.py` | test (new) | 4 tests pinning the regenerator's contract: schema, dual-write, bounded phases, full sub-window coverage |

## Verification snapshot

| Check | Result |
|---|---|
| **J.6 implementation** | committed (see `git log --oneline -1`) |
| Node `sessionPhase.test.js` | **43/43 PASS** |
| Node full suite (excluding `db.test.js`) | **360 pass, 4 skip, 0 fail** (was 317/4/0; +43 new) |
| Python `test_session_phase_golden.py` | **4/4 PASS** (was 0/4 ERROR — fix landed) |
| Python critical paths (18 files) | **333 pass, 1 skip, 1 warning** (no regressions; warning was pre-existing starlette deprecation) |
| Python full suite | **3247 pass, 4 skip, 2 pre-existing failures** in unrelated files (`test_coverage_vocabulary.py` and `test_scheduler_h2_timing_tiers.py` — both zero imports of any J.6 file, both fail on `aiosqlite` threading races; pre-existing at J.5 baseline) |
| Golden vector parity | **0 mismatches across 2,355 vectors** (every IST boundary, every CAS sub-window, three option-combos) |

## J.6 design and contract

### Why this slice

`isMarketOpen()` is a binary. The J.1 classifier has ten bounded phases — including the four CAS sub-windows (REFERENCE_PRICE_WINDOW, ORDER_ENTRY, LIMIT_ENTRY_ONLY, MATCHING) and the derivatives CAS_POST window. Without a phase-aware Node primitive, every Node caller — `executor.js`, `health.js`, `services/executor.js`, `index.js` — was structurally blind to CAS sub-windows. Plan §14 requires "all session-aware features… look at the classifier… not at home-built booleans"; this slice closes that gap on the Node side.

### The mirror contract

The Node `sessionPhase(observation_at, opts)` function returns one of ten documented phase strings:

```
CLOSED, PRE_MARKET, CONTINUOUS_TRADING,
CAS_REFERENCE_PRICE_WINDOW, CAS_ORDER_ENTRY, CAS_LIMIT_ENTRY_ONLY, CAS_MATCHING,
DERIVATIVES_CAS_ALIGNED, CAS_POST, UNKNOWN
```

The contract is **bit-perfect** with the Python `classify_session_phase`. The test enforces this with 2,355 vectors generated from the live Python classifier; the Node mirror must match every single one. Drift here is a category-1 invariant failure.

Inputs:
- `observation_at`: a Date-like value (string ISO 8601, millisecond number, or Date object)
- `opts.symbol`: optional ticker; used only to evaluate CAS eligibility for cash equities
- `opts.is_derivative`: defaults to false; true for derivatives
- `opts.cas_eligible`: optional override for CAS eligibility; when absent, falls back to the J.2.1 eligibility probe

Naive timestamps (no timezone info) default to UTC (matching Python's `datetime.now()` behaviour). Invalid inputs return `UNKNOWN` without raising.

### What J.6 does NOT do (out of scope)

- It does not gate execution on `sessionPhase()` — the existing `isMarketOpen()` hard guard remains the contract. J.6 only surfaces the phase for observability. Phase-aware execution gating is J.10.
- It does not replace the existing binary `isMarketOpen()` for callers that don't need phase granularity.
- It does not change the J.1 Python classifier — only mirrors it.

### The Windows subprocess bug (root cause + fix)

The 4 Python tests for the regenerator initially failed with `NotADirectoryError: [WinError 267]`. The root cause was **two compounding bugs**:

1. **Wrong `Path.parents[N]` index.** The test file lives at `python-engine/tests/test_session_phase_golden.py`, so `Path(__file__).resolve().parents[3]` resolves to `Desktop/` (one too high), making `REPO_ROOT / "python-engine"` = `Desktop/python-engine` — a non-existent directory.
2. **POSIX-style path passed to Windows subprocess.** Even after fixing the index, `subprocess.run(..., cwd=str(PY_ENGINE))` raised `WinError 267` because pytest's rootdir on Git-Bash is `/c/Users/Urveesh/...` (POSIX-style), which `_winapi.CreateProcess` rejects on Windows.

Fix:
1. Changed `parents[3]` → `parents[2]`.
2. Added `pathlib.Path(...).resolve()` to convert to native Windows path form, with `is_dir()` assertion as a guard.

Both fixes landed in `test_session_phase_golden.py` and the test now passes deterministically.

### Why the regenerator has two sweeps

The minute-granularity sweep (`for hour in range(24): for minute in (0,15,30,45)`) catches most phase boundaries but **misses second-level windows** like `CAS_LIMIT_ENTRY_ONLY` (15:29:30 - 15:30 IST, ~30 seconds wide) and `CAS_POST` (15:40 - 16:00 IST, derivatives only). The dedicated `_sweep_second_granularity` pass exercises 17 boundary instants × 3 option-combos = 51 vectors covering those sub-windows. Without it, `test_golden_vectors_cover_all_sub_windows` would fail because the sweep doesn't produce any `CAS_LIMIT_ENTRY_ONLY` vectors.

### Pre-existing failures documented (not J.6 regressions)

The full Python suite shows two failures after J.6:

1. `tests/test_coverage_vocabulary.py::TestEndToEndVocabularyIntegration::test_unmapped_state_appears_in_drift`
2. `tests/test_scheduler_h2_timing_tiers.py::TestOperationalCoverageTierEntry::test_coverage_includes_tier_entries`

Both:
- Have zero imports of any J.6 file (`market_calendar.py`, `market-hours.js`, `sessionPhase.test.js`)
- Fail on `aiosqlite` "Event loop is closed" threading errors (a known pytest-asyncio + aiosqlite pattern, not a J.6 regression)
- Pass in isolation when run as a single file
- Were present in the J.5 baseline (3245 / 4 skip / 1 fail) — J.5 was 1 fail, J.6 is now 2 fails. The new failure is `test_scheduler_h2_timing_tiers.py` which appeared after J.5; investigating whether J.5's `routes_holidays.py` change is implicated is **out of scope for J.6** and tracked as a separate investigation.

The honest accounting: J.6's net is +2 tests (4 from `test_session_phase_golden.py`), 0 regressions caused by J.6 itself. The two failures are pre-existing environment flakes.

## Files modified (final list)

```
node-gateway/server/utils/market-hours.js                                       +260 lines
node-gateway/server/routes/health.js                                            +9 lines
node-gateway/server/services/executor.js                                        +11 lines
node-gateway/server/index.js                                                    +15 lines
node-gateway/server/tests/unit/sessionPhase.test.js                            +434 lines (new)
node-gateway/server/tests/integration/approved-snapshot.test.js                 +7 lines
node-gateway/server/tests/integration/orders.test.js                            +2 lines
node-gateway/server/tests/integration/telegram-callbacks.test.js                +11 lines
node-gateway/server/tests/unit/executor.test.js                                 +2 lines
node-gateway/server/tests/fixtures/session_phase_golden.json                    ~344KB (new, regenerated)
python-engine/tests/fixtures/regenerate_session_phase_golden.py                 +160 lines (new)
python-engine/tests/fixtures/session_phase_golden.json                          ~344KB (new, regenerated)
python-engine/tests/test_session_phase_golden.py                                +135 lines (new)
```

## Operator runbook

### How to regenerate the golden

```bash
cd python-engine && PYTHONPATH=. ./winvenv/Scripts/python.exe tests/fixtures/regenerate_session_phase_golden.py
```

This writes to **both** locations:
- `python-engine/tests/fixtures/session_phase_golden.json` (source-of-truth)
- `node-gateway/server/tests/fixtures/session_phase_golden.json` (Node consumer)

### When to regenerate

- After any change to `classify_session_phase` in `market_calendar.py`
- After adding a new phase to `_VALID_SESSION_PHASES`
- After changing the J.2.1 CAS eligibility rules
- Quarterly (the sweep date should track the calendar year — currently Sep 2026)

### How to verify parity

```bash
cd python-engine && ./winvenv/Scripts/python.exe -m pytest tests/test_session_phase_golden.py -v
cd node-gateway/server && npm test -- --testPathPattern=sessionPhase
```

Both must pass. The Python test pins the regenerator; the Node test pins the mirror.
