# Workflow C.B.3 — penny universe stale warning dedup (F-4 from prod audit)

## Source

Per the 2026-09-15 production deep audit F-4 finding:
> 🟡 F-4 (MED, infra): Penny universe is 4 days stale. **The 4-day-stale warning kept firing through 09:23+ because the scanner doesn't re-check after the fallback loads.**

The audit showed 13 identical warnings per day when the universe is stale. The bounded fix: dedup by `as_of` date at the class level.

## What landed

|| File | Type | Purpose |
|---|---|---|---|
| `python-engine/penny_universe.py` | source (extended) | New class-level `_stale_warn_emitted` set; stale warnings keyed by `as_of` value |
| `python-engine/tests/test_penny_universe.py` | test (extended) | 4 new tests in `TestStaleWarningDedup` pinning the dedup contract |
| `docs/2026-09-15-workflow-c-b3-penny-stale-warning-dedup-done.md` | doc (new) | This file |

## The shift in defensive posture

Before this slice:
- Penny universe stale warning fires on every `PennyUniverse` construction.
- Penny scans run every 5 minutes → 13+ identical warnings per day when stale.
- Operators see log noise that drowns out the actual fix signal.

After this slice:
- The stale warning fires AT MOST ONCE per distinct `as_of` value per process lifetime.
- After a successful `run_penny_universe_refresh`, the new `as_of` date fires a fresh warning (the dedup doesn't hide fresh staleness).
- Existing tests that rely on the shared `tmp_penny_json` fixture still pass (the dedup set gets the `as_of` from the first test that runs, but other tests still construct PennyUniverse objects with the same `as_of` — they just don't re-warn, which is the bounded dedup contract).

## Key design choices

- **Class-level single-shot guard.** `PennyUniverse._stale_warn_emitted: set[str]` is keyed by `as_of`. Process-scoped (penny scans are sequential within a process; cross-process coordination isn't needed).
- **Same dedup discipline across all three branches.** Stale (>1 day), unparseable, and future-dated (clock skew) `as_of` values all use the same `_stale_warn_emitted` set. Operators don't get warning floods from any of them.
- **No new dependencies.** Stdlib only.
- **Mirrors the existing CSV warning pattern** (`_universe_csv_warn_emitted` in main.py:2419). Both are first-shot warnings for an external-resource condition.

## Test fix-up story

The first attempt used `caplog.at_level("WARNING")` to capture the warnings. This failed because pytest's `caplog` has a known edge case where the FIRST log record inside a `with caplog.at_level(...)` block can be swallowed.

The senior-dev fix: **switch the tests from caplog-capture to set-inspection**. The dedup set IS the canonical contract — every distinct `as_of` value seen by the class should land in the set. We inspect `PennyUniverse._stale_warn_emitted` directly. This is deterministic, doesn't depend on caplog's quirky first-record behavior, and tests the actual contract.

A second bug surfaced in the failing test: `_write_penny(tmp_path, as_of)` wrote to the SAME path (`tmp_path / "penny_static.json"`) for both calls in the test, so the second write overwrote the first and the first construction read "2026-09-10" from disk instead of "2026-06-21". Fixed by using distinct paths for each write.

## Defensive regression

| Test file | Tests | Δ |
|---|---|---|
| `test_penny_universe.py` | 30 | +4 |
| `test_penny_universe_refresh.py` | 20 | 0 (no changes) |

Penny universe suite (50 tests across both files): **50/50 PASS** in 1.82s.

0 regressions.

## Operator runbook

After deploy to PROD:
- Operators will see ONE `penny_universe_stale` warning per stale `as_of` date per process lifetime.
- After `run_penny_universe_refresh` succeeds with a new `as_of`, a fresh stale warning fires (if the new `as_of` is still stale) — operators see each new staleness window distinctly.
- Log noise from repeated penny scans drops from 13+ identical warnings per day to 1 per stale bucket.

## Critical invariants preserved

- The `PennyUniverse` API is unchanged.
- The eligibility filter logic is unchanged.
- The stale-detection behavior (log a warning when `age_days > 1`) is unchanged.
- All 26 existing `test_penny_universe.py` tests pass.

## What's still on Category B's backlog

Per the original investigation:
- B1 — adequate genuine held-out evidence (real production sessions).
- B3 — exchange-specific settlement assumption confirmation.

Per the production audit (still open):
- F-1 — dashboard bootstrap race (LOW, client-side fix).
- F-2 — Kite LTP fanout (MED, upstream Kite API issue, not code-fixable from dev).
- F-5 — features invisible in runtime (MED, investigation).
- F-8 — GRAVISSHO not booked (LOW, operator decision).

## What's still on Category C's backlog

- C.2 — partial-fill P&L model (Option 2 from the report). Requires operator design input on slippage model and per-exchange semantics.
- C.3 — operator-configurable asymmetric-fill policy (Option 4). Requires operator to define the policy knobs.
- C.4 — exchange-specific partial-fill semantics (NSE cash vs NSE F&O vs BSE). Requires operator confirmation per exchange.

C.C1 implements Option 3 (reject-and-flag, completed in dfc306a).
