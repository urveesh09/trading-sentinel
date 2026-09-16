# Workflow C.B.2 — agent dedup file observability (F-7 from prod audit)

## Source

The 2026-09-15 production deep audit
(`Production_Trading-sentinel/docs/2026-09-15-production-deep-audit.md`)
flagged F-7:

> 🟡 F-7 (MED, infra): `agent_dedup.json` is MISSING from `/tmp` — agent processed **zero momentum signals** today. The "momentum signal pipeline" is running every 2 min but reports "No signals found or Quant Engine unreachable". The pipeline is sleeping. Coupled with F-2 (0 LTP events), this may all be the same root cause: **momentum engine isn't receiving price quotes**.

The audit noted the dedup file's absence. The ROOT CAUSE was upstream (zero signals processed means `_save_dedup_state` was never called). The bounded fix: ensure the dedup file exists whenever the agent boots, regardless of whether any signals were processed.

## What landed

|| File | Type | Purpose |
|---|---|---|---|
| `agent/agent.py` | source (extended) | `_load_dedup_state` writes today's initial empty-state file on a missing or stale file |
| `agent/tests/test_agent_pipeline.py` | test (extended) | 5 new tests in `TestDedupStateFile` pinning the contract |
| `docs/2026-09-15-workflow-c-b2-dedup-observability-done.md` | doc (new) | This file |

## The shift in defensive posture

Before this slice:

- Agent boots → `_load_dedup_state` → file missing → `FileNotFoundError` → `pass` → in-memory set is empty.
- Pipeline runs → finds 0 signals → `_save_dedup_state` is never called → file never created.
- Operator inspects `/tmp/agent_dedup.json` → file missing → cannot distinguish "agent booted today" from "agent never booted".

After this slice:

- Agent boots → `_load_dedup_state` → file missing → `_save_dedup_state` is called → file created with `{"date": <today>, "ids": []}`.
- Pipeline runs → finds 0 signals → file already exists from boot. No further write needed.
- Operator inspects `/tmp/agent_dedup.json` → file present with today's date and `ids` array → clean confirmation "agent booted today, processed these signals (possibly zero)".

## Key design choices

- **Read-only dedup mechanism preserved.** The in-memory dedup behavior (missing file → re-alert on next boot) is unchanged. The file is now a side-effect observability improvement, not a behavior change.
- **Atomic write is reused.** `_save_dedup_state` already uses temp + `os.replace`; the new call site is the same code path. No new atomic-write primitive.
- **Stale file overwrite.** When the on-disk file's date != today, the helper overwrites with today's empty state. Otherwise yesterday's stale file would falsely look like a "fresh boot" marker that didn't actually run today.
- **No new dependencies.** Stdlib only (`json`, `os`).

## Defensive regression

| Test file | Tests | Δ |
|---|---|---|
| `test_agent_pipeline.py` | 53 | +5 (in `TestDedupStateFile`) |

Agent full suite: **330/330 PASS** in 4.02s (was 325; +5 net for C.B.2).

0 regressions.

## Operator-facing runbook

After this slice deploys to PROD:

- The agent will write `/tmp/agent_dedup.json` at boot with today's date and an empty `ids` array.
- Operators can confirm the agent booted today by checking the file exists with today's date.
- Operators can confirm signals were processed by checking `ids` is non-empty.
- The dedup mechanism itself (re-alert on next boot when file is missing) is unchanged — except now the file is reliably created at boot.

## Critical invariants preserved

- The in-memory `processed_signals_today` set is empty after a missing-file load (same as pre-fix).
- The atomic write discipline in `_save_dedup_state` is unchanged.
- The 4-day-old `clear_memory()` mechanism is unchanged.
- All existing dedup-related tests in `test_agent_pipeline.py` pass.

## What's still on Category B's backlog

Per the original investigation (operator-required):
- **B1** — adequate genuine held-out evidence (real production sessions).
- **B3** — exchange-specific settlement assumption confirmation.

Per the production audit (still open):
- **F-2** — LTP fanout 0 events (upstream Kite API issue, not code-fixable from dev).
- **F-4** — penny universe stale (root cause not clear from audit logs alone).
- **F-5** — features invisible in runtime (no opt-in triggered today).
- **F-6** — GRAVISSHO not booked (operator-side decision).
- **F-1** — dashboard bootstrap race (App.jsx guard is already correct).
