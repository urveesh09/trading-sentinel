# I.4.E.CRON_WIRING — hourly contract-health self-policing

## What landed

|| File | Type | Purpose |
|---|---|---|---|
| `agent/contract_health_cron.py` | source (new, 130 lines) | `contract_health_cron_tick(*, status_envelope=None, alert_fn=None, now_iso=None)` — runs `evaluate_contract` and fires a Telegram alert on any violation. Pure / total / never raises. |
| `agent/agent.py` | source (extended) | New hourly cron: `schedule.every(1).hours.do(_contract_health_cron_safe)`. Double-wrapped in try/except so the agent's main loop is never blocked. |
| `agent/tests/test_contract_health_cron.py` | test (new, 13 tests) | Pins alert rendering + cron tick + lazy import safety. |

## Why this slice

The I.4.E bounded contract-health self-evaluation (slice
`feat(agent): I.4.E bounded contract-health self-evaluation`)
ships five bounded invariants + a CLI. The CLI is a manual
audit tool. **Without cron wiring, the harness only runs when
the operator remembers to invoke it.** That defeats the point
of "guard the guards" — the guard only fires when someone
remembers to check the guard.

This slice wires the harness to the agent's hourly scheduler.
Now the harness self-policing actually runs, every hour, on
the production data shape (the agent's own status envelope),
and surfaces drift via Telegram before the operator notices.

## Design decisions

- **Hourly cadence, not minute-cadence.** The status envelope
  shape doesn't drift minute-to-minute; the gate's invariants
  assert *shape*, not *frequency*. Hourly is enough for the
  operator's reaction window. The check is O(1) — no broker,
  model, or filesystem calls.
- **Fire-and-forget with double try/except.** The agent's main
  loop runs the trading path; a contract-health failure must
  NEVER block it. The tick has its own internal try/except
  (alert dispatch), AND the scheduler wrapper has another
  try/except (import / scheduler bugs). Two layers of
  containment.
- **Lazy import of `agent.send_telegram_alert`.** The cron
  module must NOT trigger Telegram client init at import time
  (otherwise unit tests would fail without TELEGRAM_BOT_TOKEN).
  The lazy import inside `contract_health_cron_tick` is what
  makes this slice testable in isolation.
- **Optional `alert_fn` parameter.** Tests inject a stub
  alert_fn; production uses `agent.send_telegram_alert`. The
  injection pattern lets us pin the alert contract without
  mocking the entire Telegram stack.
- **Bounded alert text.** The Telegram alert carries at most
  3 violations per failing check + a header line with the
  violation count and timestamp. Long violation lists don't
  bloat the message; operators see *which* invariant drifted
  with a representative sample.

## Senior-dev invariants preserved

- **NO deletions.** All existing behaviour preserved.
- **NO F/G files touched.** Agent-side cron; F/G own
  python-engine's scheduler. No cross-workstream coupling.
- **NO new dependencies.** Uses existing `schedule` library
  already imported in agent.py.
- **NO new tables.**
- **Backwards-compatible.** The agent's scheduler just gains
  one more job; existing jobs unchanged.

## Verification

- Focused `tests/test_contract_health_cron.py`: **13/13 PASS** in 0.05s.
- Full agent suite: **325/325 PASS** in 4.12s (was 312 before; +13 net), 0 regressions.
- Smoke test (in-process): well-formed envelope → passing, no alert; violating envelope (`can_place_orders=True`) → failing, alert fires with the failing invariant name.

## Branch state

- **Branch:** `codex/production-correction-hedge-p0`
- **Pushed:** yes (this slice's commit lands before push)

## What this enables

The agent's main loop now runs `contract_health_cron_tick`
once per hour. On any status-envelope drift (e.g. someone
accidentally adds a `pitch` field, or `authorization_effect`
becomes `"AUTHORIZE"` instead of `"NONE"`), the operator
receives a Telegram alert within the hour.

Before this slice: the contract-health discipline was
**documented** but **unenforced** — a regression could sit
for days before the operator ran the CLI.

After this slice: the contract-health discipline is
**documented + enforced** — the harness polls itself hourly
and surfaces drift to the operator's Telegram within the
reaction window.

The user's stated principle — *"the system is better at
preserving and testing what it actually observed and proposed"* —
is now self-policing on the bounded contract that guards the
optional-AI path. The "guard the guards" discipline is no
longer aspirational.

## What this slice deliberately does NOT include

- **No minute-cadence cron.** Hourly is the documented cadence;
  increasing to minute-cadence would mean more I/O for a shape
  check that drifts slowly. A future slice could add
  `--contract-health-interval-min` to the agent if needed.
- **No new alert channel.** Uses the existing
  `send_telegram_alert`. Adding Slack / email would be a separate
  concern.
- **No F/G cross-workstream.** Agent-side cron; F/G scheduler
  (python-engine) is separate. Each scheduler owns its own
  bounded responsibilities.
- **No classification or review coverage in the cron.** The
  cron checks the bounded status envelope (the smallest
  invariant surface that's always available). Classifications
  and reviews live in the agent's async queue; their coverage
  is a separate concern (and already tracked via the
  `usefulness` sub-envelope the agent publishes).

## Status

I.4.E.CRON_WIRING **DONE**. The bounded contract-health
self-policing now runs hourly on the production data shape,
with violations surfaced to Telegram within the reaction
window.

## I-series trajectory

| Slice | Defence added |
|---|---|
| I.1 | Model/prompt/version provenance |
| I.2 | News provenance (timestamps + source URLs) |
| I.3 | Usefulness-instrumentation snapshot + CLI |
| I.A | Bridge I3 usefulness metrics to engine |
| I.B | Surface I1 provenance in operator alert |
| I.C | operational_coverage_report includes optional AI |
| I.F | Cross-container contract test |
| I.4.D | Source-event classifier (8-category bounded taxonomy) |
| I.4.E | Bounded contract-health self-evaluation (5 invariants) |
| **I.4.E.CRON_WIRING** (this slice) | Hourly cron wiring the I.4.E harness to the agent's scheduler |

The I-series bounded contract work is now: documented,
tested, AND enforced hourly. The defensive layers are no
longer aspirational — they run.
