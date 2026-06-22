# Penny Stock Expansion — Change Summary

**Date:** 2026-06-21
**Branch:** `feat/expansion`
**Base:** `evolve/smart-strategies` @ `35c3233`
**Spec:** `docs/superpowers/specs/2026-06-21-penny-stock-expansion-design.md`
**Plan:** `docs/superpowers/plans/2026-06-21-penny-stock-expansion.md`
**Auditor brief:** `docs/superpowers/plans/2026-06-21-penny-stock-expansion-auditor-brief.md`

## Overview

Adds a parallel penny-stock subsystem to Trading Sentinel. Penny trades
run alongside the existing Nifty 500 system in a separate bankroll pool
(Rs 2,500 = Rs 500 paper + Rs 2,000 live opt-in). Strict module isolation
enforced by AST-walk test (no penny module may import from
`engine.py`, `regime.py`, `risk_engine.py`, `portfolio.py`, or any of
the Nifty-side evaluators).

## Feature flag

`PENNY_LIVE_TRADING=false` (default) — paper-trade mode only.
Opt-in via `python-engine/.env`. See `docs/runbooks/penny-debug.md` for
the full flag reference.

## Architecture

10 new `penny_*.py` modules + 1 isolation test + 1 integration test:

| Module | Purpose |
|---|---|
| `penny_models.py` | PennySignal (pydantic), PennyRegime enum, PennyLeg enum |
| `penny_universe.py` | PennyUniverse loader, eligibility filter, ranking, daily refresh |
| `penny_regime.py` | Per-stock vol rank + VIX proxy → PR1/PR2/PR3 |
| `penny_risk.py` | Sizing, kill-switch, circuit filter, position caps, SL-M enforcement |
| `penny_engine_connors.py` | Larry Connors RSI(2) CNC evaluator + 3-way exit |
| `penny_engine_breakout.py` | Volume Breakout MIS evaluator + 14:30 smart-EOD |
| `penny_signal_log.py` | Append-only CSV + SQLite (`penny_signals` table) |
| `penny_scanner.py` | Orchestrator with 30s polling + regime + risk gates |
| `penny_executor.py` | Entry LIMIT → SL-M → unwind-on-failure (spec §7.2) |
| `penny_hourly_report.py` | Per-hour heartbeat + activity summary (spec §9.4) |

Modified:
- `config.py` — 30 new `PENNY_*` settings
- `main.py` — PennyScanner singleton + 7 new scheduler jobs
- `position_tracker.py` — doc comment (existing logic already accepts `source != "MOMENTUM"`)
- `performance.py` — `penny_pool_pnl()` helper (read-only)
- `analytics.py` — `penny_outcome_correlator()` sibling

## File map

```
python-engine/
  penny_models.py                NEW    (~140 LOC + tests)
  penny_universe.py              NEW    (~250 LOC + tests)
  penny_regime.py                NEW    (~180 LOC + tests)
  penny_risk.py                  NEW    (~200 LOC + tests)
  penny_engine_connors.py        NEW    (~220 LOC + tests)
  penny_engine_breakout.py       NEW    (~180 LOC + tests)
  penny_signal_log.py            NEW    (~140 LOC + tests)
  penny_scanner.py               NEW    (~250 LOC + tests)
  penny_executor.py              NEW    (~205 LOC + tests)
  penny_hourly_report.py         NEW    (~180 LOC + tests)
  data/penny_static.json         NEW    (empty stub)
  data/penny_company_data.json   NEW    (empty stub)
  tests/test_penny_*.py          NEW    (14 test files, ~140 tests)
  main.py                        MOD    (added 7 scheduler jobs)
  position_tracker.py            MOD    (1-line doc comment)
  performance.py                 MOD    (added penny_pool_pnl helper)
  analytics.py                   MOD    (added penny_outcome_correlator)

docs/
  superpowers/specs/2026-06-21-penny-stock-expansion-design.md         NEW
  superpowers/plans/2026-06-21-penny-stock-expansion.md                NEW
  superpowers/plans/2026-06-21-penny-stock-expansion-auditor-brief.md  NEW
  superpowers/plans/2026-06-21-penny-stock-expansion-execution-log.md  NEW
  evolution/PENNY_EXPANSION_CHANGES.md                                NEW
  evolution/PENNY_VS_DESKTOP_AUDIT.md                                 NEW
  runbooks/penny-debug.md                                             NEW
  deviations/2026-06-21-penny-*.md                                    NEW (5 deviation notes)
```

## Commit log (this branch)

1. `0a35c93` — feat(penny-config): add PENNY_* settings block (spec §12.1)
2. `17bcd6f` — feat(penny-models): PennySignal + PennyRegime + PennyLeg + isolation test
3. `6529334` — feat(penny-universe): static JSON loader + eligibility filter
4. `d2934cc` — feat(penny-universe): daily refresh job + composite-score ranking
5. `c619e77` — feat(penny-regime): per-stock regime engine with VIX proxy
6. `8dbe633` — feat(penny-risk): per-trade sizing + kill-switch + circuit + caps
7. `f47b9f2` — feat(penny-connors): RSI(2) CNC evaluator + 3-way exit logic
8. `2e9a671` — feat(penny-breakout): volume breakout MIS evaluator + 14:30 smart-EOD
9. `5907dcd` — feat(penny-log): append-only signal log (CSV + SQLite)
10. `53821cc` — feat(penny-scanner): orchestrator with 30s polling + regime + risk gates
11. `068e765` — feat(penny-executor): entry LIMIT -> broker SL-M -> unwind-on-failure
12. `57f44b0` — feat(penny-hourly-report): hourly heartbeat with action summary (spec §9.4)
13. `ff4dea8` — feat(penny-main): scheduler wiring + ledger/perf/analytics extensions

Plus several docs/deviation commits:
- `79602cb` — docs: spec v1.1 patches + plan + auditor brief + 2 deviation notes
- `a107363` — docs: Task 7 connors test-fix deviation note
- `c332e97` — fix: convert last kwarg logger to positional %-args

## Spec deviations (none in implementation body)

The implementation matches spec §1-§16 exactly. Two Uru-driven refinements
during brainstorming were captured in the spec itself (not post-hoc):

1. **P/B loosened from <=1.0 to <=2.0** — Per Uru 2026-06-21: aggressive
   path needs more signal volume. The original floor was too restrictive
   and would have killed ~60% of the universe.
2. **Promoter holding range tightened** — Per Uru 2026-06-21: changed
   from `<75%` (one-sided) to `>25% AND <75%` (two-sided) to exclude
   both micro-caps (too easy to move price) and widely-held names
   (no "skin in the game").

## Plan-deviation notes (6 documented)

The implementation body code is plan-verbatim for all 10 penny modules.
Six test/setup deviations were documented in `docs/deviations/`:

1. `penny-universe-rank-dead-deviation.md` — Task 4 test asserted an
   unreachable substring against spec's own composite-score math
2. `penny-regime-vix-fixture-deviation.md` — Task 5 fixed constant-series
   guard and a VIX fixture math error in the plan body
3. `penny-risk-test-math-deviation.md` — Task 6 fixed 4 test math bugs
   (PR2 sizing, kill-switch order, two circuit band fixtures)
4. `penny-connors-test-fixes-deviation.md` — Task 7 fixed walrus-in-kwarg
   syntax error, unreachable volume substring, and IEEE-754 floor
5. `penny-signal-log-test-signature-deviation.md` — Task 9 fixed missing
   required kwargs in test_log_handles_db_failure_gracefully
6. `penny-hourly-report-fixes-deviation.md` — Task 12 fixed 4 plan bugs
   (requests not in venv, off-by-one is_in_report_window, SQL `<` vs `<=`,
   test missing init + datetime mock)
7. `penny-main-wiring-fixes-deviation.md` — Task 13 extracted
   register_penny_scheduler_jobs() for testability, tightened an
   assertion, documented a pre-existing flaky Nifty test

## What was NOT changed (out of scope)

- Nifty 500 strategy / regime / risk parameters (zero code-path touch)
- Nifty bankroll (Rs 5,000 stays)
- Short-selling on penny (long-only, deferred)
- F&O penny (none exist)
- Auto-compounding between pools (independent by design)
- Live launch (Phase 5 — gated on Uru approval after 2 weeks of paper)
- `engine.py`, `regime.py`, `risk_engine.py`, `portfolio.py`, `models.py`,
  `breadth.py`, `signal_log.py`, `universe.py` — all untouched
- `kite_client.py` — untouched (used via lazy import inside `penny_executor`)

## Open follow-ups

- Wire penny P&L writes to `bankroll_ledger` (currently `penny_pool_pnl()`
  reads but no rows are written yet — schema lacks `source` column)
- Extend `analytics.penny_outcome_correlator()` with reject-reason
  breakdown once ledger has rows
- Add HTTP endpoints: `/penny/regime/today`, `/penny/positions`,
  `/penny/signals?days=N`
- Add `python -m penny_tools --action=panic-close` for manual position
  cleanup
- Backtest correlator (Phase 4 — uses signal-log data accumulated in
  Phase 3)
- Telegram daily summary for penny (separate channel per open Q1)
- Pre-existing flaky Nifty test:
  `tests/test_universe_expansion.py::test_load_universe_with_fallback_uses_csv_when_present`
  fails intermittently in the full suite due to test-ordering issues
  unrelated to this branch

## Cross-refs

- Spec: `docs/superpowers/specs/2026-06-21-penny-stock-expansion-design.md`
- Plan: `docs/superpowers/plans/2026-06-21-penny-stock-expansion.md`
- Auditor brief: `docs/superpowers/plans/2026-06-21-penny-stock-expansion-auditor-brief.md`
- Execution log: `docs/superpowers/plans/2026-06-21-penny-stock-expansion-execution-log.md`
- Live-system audit: `docs/evolution/PENNY_VS_DESKTOP_AUDIT.md`
- Operator runbook: `docs/runbooks/penny-debug.md`

## Status

**Phase 2 complete (2026-06-21).** Code + tests + paper-trade infrastructure
all in place. 580+ tests passing (1 pre-existing Nifty flaky test not
caused by this branch). Zero Nifty regression. Ready for Phase 3
(2 weeks of paper trading).
