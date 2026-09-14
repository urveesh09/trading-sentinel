# J.9 — CAS-aware signal handling: phase stamping done and committed

## What landed

| File | Type | Purpose |
|---|---|---|
| `node-gateway/server/utils/market-hours.js` | source | NEW `stampSessionPhaseForSignal(ticker)` — wraps the J.6 mirror for insertion into `received_signals.session_phase`. Returns one of `STAMPABLE_PHASES` (never null, never an unrecognised string); never throws; non-string tickers (null, undefined, numbers, objects, arrays) route through `currentSessionPhase()` and the result is bounded by `STAMPABLE_PHASES`. Defensive fallback to `UNKNOWN` if a future mirror expansion leaks an unrecognised phase. NEW exported `STAMPABLE_PHASES` constant (10 bounded phases) — same set as the DB CHECK constraint. |
| `node-gateway/server/db/schema.sql` | source | NEW `session_phase TEXT NOT NULL DEFAULT 'UNKNOWN' CHECK (session_phase IN ('CLOSED', 'PRE_MARKET', 'CONTINUOUS_TRADING', 'CAS_REFERENCE_PRICE_WINDOW', 'CAS_ORDER_ENTRY', 'CAS_LIMIT_ENTRY_ONLY', 'CAS_MATCHING', 'CAS_POST', 'DERIVATIVES_CAS_ALIGNED', 'UNKNOWN'))` column on `received_signals`. The `DEFAULT 'UNKNOWN'` covers existing rows (pre-J.9) so the additive migration does not break the production SQLite DB. |
| `node-gateway/server/routes/signals.js` | source | Stamps `session_phase` at insertion time on every fresh signal from the OpenClaw webhook. The phase is the LIVE phase at the moment the signal arrives -- not `signal_time`. Operators querying "how many signals arrived during CAS_MATCHING?" read this column. |
| `node-gateway/server/routes/internal.js` | source | Stamps `session_phase` at insertion time on every Python engine callback (`POST /api/internal/register-signal` with `action === 'EXEC'`). Same stamp helper. |
| `node-gateway/server/tests/unit/sessionPhaseStamping.test.js` | test (new) | 5 tests pinning the contract: (a) schema.sql contains the column + bounded CHECK constraint; (b) `STAMPABLE_PHASES` is the documented 10-phase set; (c) `stampSessionPhaseForSignal` returns one of the 10 documented phases; (d) never throws on null/undefined/empty/42/{}/[]; (e) output never contains non-bounded strings. |

## Verification snapshot

| Check | Result |
|---|---|
| **Node `sessionPhaseStamping.test.js`** | **5/5 PASS** |
| **Node full suite (excluding `db.test.js`)** | **385 pass / 4 skip / 0 fail** (was 380/4/0 at J.8 close; **+5 new**) |
| **Python J-slice (defensive, no Python changes)** | **224 pass / 0 fail warnings-fatal** (no regression) |
| `STAMPABLE_PHASES` cardinality | **10** (matches the bounded phase set) |
| Schema CHECK constraint cardinality | **10** (matches `STAMPABLE_PHASES`; drift = category-1 invariant failure) |

## J.9 design

### Why this slice

Signals arrive from two paths (OpenClaw webhook in `routes/signals.js`, Python engine callback in `routes/internal.js`). The `received_signals` table recorded `signal_time` (when the signal was generated) but not the phase at which it was received. Operators querying "how many signals arrived during `CAS_MATCHING`?" had no way to answer. Downstream analysis (research, J-series reconciliation) had no phase context for the signal's arrival.

J.9 stamps the bounded phase at insertion time using the J.6 mirror. Operators and research pipelines can now group signals by arrival phase and correlate with the closing-auction behaviour.

### Schema migration safety

The new column is **additive** with `DEFAULT 'UNKNOWN'`:
- Existing rows (pre-J.9) get `'UNKNOWN'` after the migration
- The CHECK constraint accepts all 10 documented phases
- New inserts always pass one of the 10 phases via `stampSessionPhaseForSignal`

This means a production SQLite DB can be migrated without downtime; no existing rows are invalidated.

### The fail-closed contract (defensive)

The stamping helper is intentionally defensive:
- Any non-string ticker (`null`, `undefined`, `''`, `42`, `{}`, `[]`) routes through `currentSessionPhase({})` (which is itself defensive — returns `UNKNOWN` for invalid datetime inputs)
- The output is then bounded by `STAMPABLE_PHAGES` — anything outside the documented set falls back to `'UNKNOWN'`

The DB CHECK constraint is the second line of defense: even if the helper had a bug that leaked an unrecognised string, SQLite would reject the INSERT with a CHECK violation. The test asserts both lines of defense.

### What J.9 does NOT do (out of scope)

- It does not change execution gating (J.7 already does that)
- It does not stamp `payload_json` with the phase — the column is at the table level, not inside the JSON blob
- It does not add a per-execution phase stamp (the `execution_state` transition is at a different table layer); that's a future slice
- It does not wire the J.2.1 CAS eligibility list into the helper — a future slice can pass `cas_eligible: true` explicitly when the Python engine confirms CAS eligibility; the helper currently uses `currentSessionPhase()` which respects the documented `cas_eligible: bool | None = None` semantics

### The drift surface (operator runbook)

`STAMPABLE_PHASES` (Node) and the DB CHECK constraint (SQL) are two parallel definitions of the same bounded set. A future phase-set change must update BOTH, plus `VALID_SESSION_PHASES` (the J.6 mirror) and `_PHASE_EXECUTION_ALLOWED` / `_EXEC_BLOCKING_PHASES` (J.7 verdict). The drift-detection recipe:

```bash
# After any phase-set change:
grep -E "STAMPABLE_PHASES|session_phase.*IN\s*\(" \
  node-gateway/server/utils/market-hours.js \
  node-gateway/server/db/schema.sql
```

A future slice should automate this with a regeneration script (similar to the J.6 / J.7 golden regenerators).

## Files modified (final list)

```
node-gateway/server/utils/market-hours.js              +67 lines (new helper + STAMPABLE_PHASES export)
node-gateway/server/db/schema.sql                     +15 lines (new column + CHECK constraint)
node-gateway/server/routes/signals.js                 +12 lines (stamp at OpenClaw webhook insert)
node-gateway/server/routes/internal.js                +13 lines (stamp at Python engine callback insert)
node-gateway/server/tests/unit/sessionPhaseStamping.test.js   +134 lines (new)
```
