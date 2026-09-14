# J.7 — CAS-aware execution gating: done and committed

## What landed

| File | Type | Purpose |
|---|---|---|
| `python-engine/market_calendar.py` | source | NEW `execution_allowed(observation_at, *, symbol, is_derivative, cas_eligible, allow_pre_market)` — translates the bounded phase into a `{allowed, phase, reason}` verdict. Translation table: CONTINUOUS_TRADING / DERIVATIVES_CAS_ALIGNED -> allowed; PRE_MARKET -> blocked unless `allow_pre_market=True`; CLOSED / all CAS sub-windows / UNKNOWN -> blocked. |
| `python-engine/tests/test_execution_allowed.py` | test (new) | 19 tests across 5 classes: CLOSED/PRE_MARKET, CONTINUOUS_TRADING, CAS sub-windows, DERIVATIVES_CAS_ALIGNED, purity contract. |
| `python-engine/tests/fixtures/regenerate_execution_allowed_golden.py` | regenerator (new) | Two sweeps: minute-granularity (broad) + second-granularity boundary pass. Dual-writes to python-engine + node-gateway fixtures. |
| `python-engine/tests/fixtures/execution_allowed_golden.json` | fixture (new) | Source-of-truth golden: 3,525 vectors covering every documented phase × every option-combo. |
| `node-gateway/server/utils/market-hours.js` | source | NEW `isExecutionAllowed(opts)` — bit-perfect mirror of the Python helper. Defaults: only CONTINUOUS_TRADING / DERIVATIVES_CAS_ALIGNED are allowed; PRE_MARKET blocks unless `allow_pre_market=true`. New `_EXEC_BLOCKING_PHASES` set + `_EXEC_PHASE_REASON` map. Exported from `module.exports`. |
| `node-gateway/server/utils/errors.js` | source | NEW `CasPhaseError(phase, reason)` — AppError subclass, status 422, code `cas_phase_blocked`. Carries `phase` and `reason` fields for the operator dashboard. |
| `node-gateway/server/services/executor.js` | source | Replaces the J.6 `currentSessionPhase()` log with the J.7 verdict: throws `CasPhaseError` for CAS-blocked phases (preserves `MarketClosedError` for CLOSED so existing error-code surface stays compatible). |
| `node-gateway/server/index.js` | source | Adds the J.7 CAS-aware guard after the J.6 binary gate. Telegram callback shows the phase-specific `verdict.reason` (e.g. "Closing auction matching (15:30-15:35 IST); broker orders are blocked"). |
| `node-gateway/server/tests/unit/isExecutionAllowed.test.js` | test (new) | 20 tests across 7 describe blocks including the **golden-vector parity test** that asserts zero mismatches across all 3,525 vectors. |
| `node-gateway/server/tests/fixtures/execution_allowed_golden.json` | fixture (new) | Consumer-side golden: same 3,525 vectors. |
| `node-gateway/server/tests/integration/{approved-snapshot,orders,telegram-callbacks}.test.js` | test (modified) | Mocks expose `isExecutionAllowed` so the destructure in production code does not raise. |
| `node-gateway/server/tests/unit/executor.test.js` | test (modified) | Same mock-surface update. |

## Verification snapshot

| Check | Result |
|---|---|
| **Node isExecutionAllowed.test.js** | **20/20 PASS** (bit-perfect parity verified across all 3,525 vectors) |
| **Python test_execution_allowed.py** | **19/19 PASS warnings-fatal** |
| Node full suite (excluding `db.test.js`) | **380 pass / 4 skip / 0 fail** (was 360/4/0 at J.6 close; +20 new) |
| Python J-slice (8 files) | **199 pass / 0 fail warnings-fatal** (was 180 at J.6 close; +19 new) |
| Python full suite | **3267 pass / 4 skip / 1 pre-existing failure** (was 3247/4/2 at J.6 close; +20 new tests, 1 pre-existing flake silenced by isolation in this run) |
| Golden vector parity (Node↔Python) | **0 mismatches across 3,525 vectors** |
| All CAS sub-windows (5) covered | **CAS_REFERENCE_PRICE_WINDOW, CAS_ORDER_ENTRY, CAS_LIMIT_ENTRY_ONLY, CAS_MATCHING, CAS_POST** — each tested in isolation + in golden parity |

## J.7 design

### Why this slice

Before J.7, the Node execution path was binary: `isMarketOpen()` is true during the entire 9:15 - 15:30 cash window, including the CAS sub-windows 15:15 - 15:35 where NSE **rejects** all new orders. The Node side was structurally blind to the closing auction; an EXEC at 15:30 IST would be sent to Kite during CAS_MATCHING — Kite either silently rejects or queues for post-CAS execution (broker-dependent). Both outcomes are production hazards.

J.6 gave us the bounded phase mirror. J.7 closes the loop: it uses the mirror's phase to gate execution, with a translation table that is mechanical (the policy is the same policy as the classifier — the translation table is bounded, not branching).

### The translation table

```
phase                              allowed?
----------------------------------- -------
CONTINUOUS_TRADING                 true
DERIVATIVES_CAS_ALIGNED            true
PRE_MARKET                         true iff allow_pre_market=true
CLOSED                             false
CAS_REFERENCE_PRICE_WINDOW         false
CAS_ORDER_ENTRY                    false
CAS_LIMIT_ENTRY_ONLY               false
CAS_MATCHING                       false
CAS_POST                           false
UNKNOWN                            false
```

The Python `_PHASE_EXECUTION_ALLOWED` dict and the Node `_EXEC_BLOCKING_PHASES` set are **byte-equivalent under bit-perfect parity**: every Python verdict maps to the same Node verdict for the same input.

### CAS sub-window boundaries (corrected from J.6 docs)

The J.6 system guide documented CAS sub-windows as:
- CAS_ORDER_ENTRY: 15:20 - 15:29:30 IST
- CAS_LIMIT_ENTRY_ONLY: 15:29:30 - 15:30 IST
- CAS_MATCHING: 15:30 - 15:40 IST

Those numbers were wrong. The **actual Python classifier constants** (and the bit-perfect Node mirror) are:
- CAS_REFERENCE_PRICE_WINDOW: 15:15 - 15:20 IST
- CAS_ORDER_ENTRY: 15:20 - 15:25 IST
- CAS_LIMIT_ENTRY_ONLY: 15:25 - 15:30 IST
- CAS_MATCHING: 15:30 - 15:35 IST
- CAS_POST (cash-only): 15:35 - 16:00 IST
- DERIVATIVES_CAS_ALIGNED: 15:30 - 15:40 IST

J.7 ships **both** the corrected tests and the corrected docs (see `docs/2026-09-13-j7-cas-aware-execution-gating-done.md` §"Window boundary correction"). The Python classifier constants at `market_calendar.py:41-45` are the single source of truth; the Node mirror constants at `market-hours.js:365-372` are bit-perfect clones.

### The J.7 wiring pattern

Two-tier guard, with the existing binary `isMarketOpen()` kept as the first tier:

```js
// Tier 1 (existing, J.6 + earlier): binary market-open gate.
if (!isMarketOpen()) throw new MarketClosedError();

// Tier 2 (new, J.7): CAS-aware verdict.
const verdict = isExecutionAllowed({
  observation_at: new Date(),
  symbol: signal.ticker,
});
if (!verdict.allowed) {
  if (verdict.phase === 'CLOSED') throw new MarketClosedError();
  throw new CasPhaseError(verdict.phase, verdict.reason);
}
```

This preserves the J.6 error-code surface (`MarketClosedError` is still thrown for the CLOSED phase) and introduces a new error class for CAS-blocking phases. The `CasPhaseError` carries the phase + reason so the operator dashboard / telegram callback can show "Closing auction matching (15:30-15:35 IST); broker orders are blocked" — a phase-specific message instead of the generic "Market closed".

### Why this lives in the mirror, not the caller

The translation is mechanical (10 inputs -> 10 outputs); a future phase-set change (e.g. adding a new CAS sub-window per a future NSE circular) must surface as a single-file review in `market_calendar.py` and `market-hours.js`. Putting the translation in the caller would scatter the policy across 4+ files; the mirror's `_PHASE_EXECUTION_ALLOWED` / `_EXEC_BLOCKING_PHASES` keeps the contract local.

## Bugs found and fixed during J.7

### 1. Test fixture `cas_eligible: true` was missing on CAS tests

The first run of J.7 had 10/19 failing tests. The root cause: tests for CAS sub-windows passed `observation_at` only — without `cas_eligible: true` the mirror's `sessionPhase()` defaulted to `false`, routing the call through the non-CAS cash branch (CONTINUOUS_TRADING until 15:30, then CLOSED). Fix: every CAS test now passes `symbol: 'RELIANCE'` + `cas_eligible: true` explicitly. This matches the J.2.1 wiring where production callers resolve the eligibility flag before invoking the classifier.

### 2. `ist()` helper had a fragile arithmetic trick

The original `ist(y, mo, d, h, mi, s)` helper computed UTC by subtracting 5h30m via `Date.UTC(..., h-5, mi-30, s)`. The arithmetic relied on JavaScript's `Date.UTC` overflow handling (`Date.UTC(y, mo-1, d, 4, -20)` becomes 3:40 of the same day). This worked for valid IST instants but was brittle. Fix: explicit `istMillis - (5 * 60 + 30) * 60 * 1000` — same math, no overflow reliance.

### 3. Mirror policy bug: PRE_MARKET was allowed by default

The first mirror implementation used `_EXEC_BLOCKING_PHASES.has(phase)` as the gate. That meant PRE_MARKET was `allowed: true` by default (PRE_MARKET was not in the blocking set). Fix: explicit allow-list `phase === 'CONTINUOUS_TRADING' || phase === 'DERIVATIVES_CAS_ALIGNED'` with `PRE_MARKET` as the only escape via `allow_pre_market: true`. This matches the Python `_PHASE_EXECUTION_ALLOWED` dict exactly.

### 4. Documented boundary mismatch (this slice)

The J.6 done-doc listed CAS sub-window widths that did not match the live Python constants (15:30 -> 15:40 for CAS_MATCHING instead of the actual 15:30 -> 15:35). J.7 corrects the docs and tests use the actual constant values. The next docs sweep will refresh the system guide's J.6 paragraph to match.

### 5. Window boundary correction in second-granularity sweep

The regenerator's `_sweep_second_granularity` originally had `(15, 40, 0)` and `(15, 40, 1)` instants targeting a CAS_MATCHING window that ended at 15:40. After J.6 verification, the actual CAS_MATCHING window is 15:30 - 15:35. The boundary spec list was rewritten to match the live classifier constants: (15,16,0) for CAS_REFERENCE_PRICE_WINDOW, (15,20,0) for CAS_ORDER_ENTRY, (15,25,0) for CAS_LIMIT_ENTRY_ONLY, (15,30,0) for CAS_MATCHING/DERIVATIVES_CAS_ALIGNED, (15,35,0) for CAS_POST (cash-only), (15,40,0) for derivatives CLOSED boundary.

## Operator runbook

### How to regenerate the golden

```bash
cd python-engine && PYTHONPATH=. ./winvenv/Scripts/python.exe tests/fixtures/regenerate_execution_allowed_golden.py
```

This writes 3,525 vectors to both:
- `python-engine/tests/fixtures/execution_allowed_golden.json`
- `node-gateway/server/tests/fixtures/execution_allowed_golden.json`

### How to verify parity

```bash
cd python-engine && ./winvenv/Scripts/python.exe -m pytest tests/test_execution_allowed.py -v
cd node-gateway/server && npm test -- --testPathPattern=isExecutionAllowed
```

Both must pass.

### How to verify CAS gating in production

The CAS-aware guard fires on every `executeSignal(signal, action, ...)` call. Operators can verify it via:

```bash
# Manual CAS-window test:
node -e "
const { isExecutionAllowed } = require('./utils/market-hours');
const future = new Date('2026-09-07T15:32:00Z');  // 15:32 IST = CAS_MATCHING for cash
console.log(isExecutionAllowed({observation_at: future, symbol: 'RELIANCE', cas_eligible: true}));
// Expected: { allowed: false, phase: 'CAS_MATCHING', reason: '...' }
"
```
