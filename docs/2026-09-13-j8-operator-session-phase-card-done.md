# J.8 — Operator dashboard session-phase card: done and committed

## What landed

| File | Type | Purpose |
|---|---|---|
| `node-gateway/client/src/utils/sessionPhase.js` | utility (new) | Pure session-phase utility: bounded phase → colour class + display label + `isExecutionBlockedByPhase`. Exports `VALID_SESSION_PHASES`, `PHASE_DISPLAY_LABEL`, `PHASE_COLOR_CLASS`, `coercePhase`, `describePhase`, `isExecutionBlockedByPhase`. Never throws. |
| `node-gateway/client/src/components/SessionPhaseBadge.jsx` | component (new) | Compact chip rendering phase + colour + lock-icon when phase blocks execution. `data-testid` and `data-phase` for test selectors. |
| `node-gateway/client/src/components/SessionPhaseCard.jsx` | component (new) | Full card showing phase label, broker-order verdict, and short description (one per phase). Renders "Broker orders blocked" with lock icon when blocked. |
| `node-gateway/client/src/components/StatusBar.jsx` | component (modified) | Reads `health.session_phase` and renders `<SessionPhaseBadge>` next to the binary "Open/Closed" indicator. |
| `node-gateway/client/src/components/SignalCard.jsx` | component (modified) | New `sessionPhase` prop. `actionDisabled` now considers the bounded phase via `isExecutionBlockedByPhase` — mirrors the J.7 server gate so the operator's view of the EXEC button matches what the server will accept. |
| `node-gateway/client/src/pages/Dashboard.jsx` | component (modified) | Reads `healthData.session_phase`, passes to `<SignalCard>`, and renders a new `<SessionPhaseCard>` section between `ActivityFunnel` and the Partner Advisory grid. |
| `node-gateway/client/tests/sessionPhase.test.mjs` | test (new) | 15 tests across 6 describe-blocks via Node's built-in test runner: phase enumeration, label/color completeness, coercePhase (null/undefined/garbage), execution-blocked (8 blocking + 2 allowed + bad inputs), describePhase bundle, colour-bucket assertions. |

## Verification snapshot

| Check | Result |
|---|---|
| **Node `sessionPhase.test.mjs`** | **15/15 PASS** |
| **Client full unit suite** | **40 pass / 0 fail** (was 25/0/0 at J.7 close; +15 new) |
| **Node full suite (defensive, post-J.8 client changes)** | **380 pass / 4 skip / 0 fail** (no regression; J.8 changed no Node code) |
| **Python J-slice (defensive)** | **209 pass / 0 fail warnings-fatal** (no regression) |
| Every bounded phase has a label + colour | **10/10** (asserted in `every bounded phase has a label and a color class`) |
| Fail-closed contract | **All bad inputs (null, undefined, garbage strings, numbers) return `executionBlocked: true`** |

## J.8 design

### Why this slice

Before J.8, the dashboard surfaced `market_open` (binary) only. Operators viewing the dashboard couldn't tell if the market was in `CONTINUOUS_TRADING`, `CAS_MATCHING`, `PRE_MARKET`, etc. — only "Open" vs "Closed". For J.7's CAS-aware gating to be operator-visible, the dashboard must show the bounded phase. J.6 gave the Node side visibility into the bounded phase via `health.session_phase`; J.8 surfaces that to the React UI.

### What J.8 does NOT do (out of scope)

- It does not add a Jest + React Testing Library setup — the project uses Node's built-in `node:test` for client-side pure-utility tests (existing pattern). Adding RTL would be a separate slice.
- It does not change the `isMarketOpen` binary — both indicators coexist (binary shows "Open/Closed" + bounded badge shows the phase). The binary remains the contract for the existing 25-client test that asserts on `market_open`.
- It does not change the Node `/health` endpoint — J.6 already exposes `session_phase`. J.8 only consumes it.
- It does not add a separate page or route — the session-phase card lives on the existing Dashboard page.

### The single-source-of-truth pattern

The bounded phase → colour / label / execution-blocked mapping lives in `utils/sessionPhase.js` (one file). Components import from there. A future phase-set change (e.g. adding a new CAS sub-window per a future NSE circular) surfaces as a single-file review here + `market_calendar.py` + `market-hours.js` (Node side).

The fail-closed contract: any non-bounded input (null, undefined, garbage strings, numbers, objects) returns `executionBlocked: true`. The dashboard mirror matches the server gate: misconfigured health payload or network blip must NOT silently allow an order that the server would reject.

### Wiring

```
health.session_phase  (Node /health response, exposed by J.6)
       │
       ├──► StatusBar: <SessionPhaseBadge phase={sessionPhase} />
       │                Compact chip in the top status row.
       │
       ├──► SessionPhaseCard (new section on Dashboard)
       │                Full card with label, broker-order verdict, and description.
       │
       └──► SignalCard: isExecutionBlockedByPhase(sessionPhase)
                        Mirrors the J.7 server gate; disables EXEC button when blocked.
```

The dashboard operator sees the bounded phase in three places:
1. StatusBar — compact badge in the top bar
2. SessionPhaseCard — full card with explanation
3. SignalCard — the EXEC button is disabled when the phase blocks (with the binary `market_open` indicator still showing "Closed" if applicable)

### Test pattern (Node `node:test`, no Jest)

The project uses Node's built-in `node:test` runner for client-side pure-utility tests. The pattern is straightforward: import the utility, write `test(name, fn)` blocks with `assert.equal`. J.8 follows this pattern — no new dependencies, no Jest setup, no RTL.

## What was changed for fail-closed correctness

The first iteration of `isExecutionBlockedByPhase(phase)` was:

```js
if (!phase) return true;
return BLOCKING_PHASES.has(phase);
```

This returned `false` for unrecognised strings (e.g. `'UNKNOWN_PHASE'`). The contract should be fail-closed: any non-bounded input must block. The test `isExecutionBlockedByPhase never throws on bad input` caught this. The fix:

```js
if (typeof phase !== 'string') return true;
if (VALID_SESSION_PHASES.indexOf(phase) < 0) return true;
return BLOCKING_PHASES.has(phase);
```

Now any non-bounded string (or non-string input) returns `true` (blocked). This matches the "fail closed for safety" pattern documented in the J.7 done-doc.

## Operator runbook

### How to verify the session-phase card

1. Start the dashboard dev server: `cd node-gateway/client && npm run dev`
2. Open the dashboard at http://localhost:5173 (or whatever Vite reports)
3. The top status bar shows "Market: Open" + a coloured badge (green when CONTINUOUS_TRADING, yellow when PRE_MARKET / CAS_*, red when CLOSED / UNKNOWN)
4. The "Session Phase" section on the dashboard shows the full card with the phase label, the bounded phase string in monospace, and "Broker orders blocked" with a lock icon (or "Broker orders accepted" without)
5. Active signals show the EXEC button disabled (greyed) when the phase blocks execution

### How to verify fail-closed behaviour

The unit tests `isExecutionBlockedByPhase never throws on bad input` and `coercePhase handles null and undefined inputs` cover the fail-closed contract. The session-phase card falls back to UNKNOWN (red, broker orders blocked) when `health.session_phase` is missing or unparseable.

## Files modified (final list)

```
node-gateway/client/src/utils/sessionPhase.js                  +131 lines (new)
node-gateway/client/src/components/SessionPhaseBadge.jsx       +52 lines (new)
node-gateway/client/src/components/SessionPhaseCard.jsx        +99 lines (new)
node-gateway/client/src/components/StatusBar.jsx               +10 lines (modified)
node-gateway/client/src/components/SignalCard.jsx              +19 lines (modified)
node-gateway/client/src/pages/Dashboard.jsx                    +14 lines (modified)
node-gateway/client/tests/sessionPhase.test.mjs                 +181 lines (new)
```
