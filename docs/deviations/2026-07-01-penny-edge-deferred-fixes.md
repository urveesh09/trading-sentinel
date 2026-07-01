[PENNY-EDGE-DEFERRED-FIXES 2026-07-01]

Context
-------

Operator (urveesh) reported the 2026-07-01 prod-incident at 21:22 IST. The
initial assessment identified 5 bugs; the operator gave the green light to
fix the 3 P0s immediately. Commit 70dd0a7 "fix(prod-incident 2026-07-01):
P0 EOD digest + scanner deadlock + TP/SL" fixed those 3 in one batch.

Two issues were explicitly DEFERRED in that commit:

  4. File-handle exhaustion (P1 -- 2,628 "Too many open files" + 8,740
     "unable to open database file" errors today)
  5. cmd_eod_digest asyncio.run() in running event loop (P2)

This document records the fixes for those two DEFERRED items, plus a
small but consequential correctness fix on the penny_edge exit path
that the operator's deep assessment implicitly identified: the EDGE
exit-path was writing exit_price=entry_price with realised_pnl=0.0
when `run_penny_edge_exit` fired its `>= max_hold` force-close, which
in practice (today, on the 6 EDGE positions from 2026-06-30's first
run) was masked because `update_daily_positions` had already closed
them on Day 1 via TP/SL detection. But the bug is still real for any
EDGE position that hits the hold cap without ever seeing TP/SL in the
intraday bar.

Why these matter
----------------

(4) FD/DB-handle exhaustion: 11,368 errors today is the system shouting
"my connections leak". Even after the asyncio.wait_for fix in 70dd0a7
(which kills the strongest leak -- a permanently hung scanner), the
auxiliary bare sqlite3.connect call sites (in penny_edge_orchestrator,
penny_edge_live, penny_edge_backtest, penny_bt_analysis) are still
vulnerable on any exception path. The honest fix is "with"-context
managers + try/finally where needed. See "Code changes" below.

(5) cmd_eod_digest: the 16:00 IST cron path calls the function from
inside the asyncio event loop, where asyncio.run() raises
RuntimeError("asyncio.run() cannot be called from a running event
loop"). The EOD digest goes silent at exactly the time the operator
needs visibility. The fix is the proven async/sync split pattern
(skill: sentinel-bugs.md "Async/sync split for FastAPI handlers +
sync callers").

(bonus) run_penny_edge_exit would overwrite a legitimately TP/SL'd
position with realised_pnl=0.0 if the position hit its max_hold cap
before update_daily_positions got to it. Today it didn't trigger
(because the 6 positions opened at 23:30 IST were closed at 09:30 IST
next day by update_daily_positions with correct TP/SL P&L), but the
race is real. The operator's deep assessment explicitly listed this
class of bug. Fix routes the EOD exit through the engine's
simulate_position logic -- one canonical exit for all paths.

Scope: penny-edge subsystem only. Do not bring in momentum/Nifty
context (rule 30 from trading-sentinel-ops).

Code changes
------------

A. File-handle leak elimination (P1)
   Files: penny_edge_orchestrator.py, penny_edge_live.py,
          penny_edge_backtest.py, penny_bt_analysis.py
   Pattern: wrap bare sqlite3.connect in try/finally with .close(),
            or convert to `with sqlite3.connect(...) as con:`.

   Specifically:
   - penny_edge_orchestrator.py:_already_entered_today (line 113)
   - penny_edge_orchestrator.py:_write_edge_position (line 135)
   - penny_edge_orchestrator.py:run_penny_edge_exit
        - first conn (line 368)
        - conn2 inside per-position loop (line 407)
   - penny_edge_live.py:scan_today (line 65)
   - penny_edge_backtest.py:_load_daily_bars (line 100, "data/cache.db")
   - penny_bt_analysis.py:_open_db (line 16, "data/cache.db")
   - penny_edge_orchestrator.py:run_penny_edge_exit UPDATE branch
     (the one that uses `with sqlite3.connect as con` pattern -- this
      is the half-correct one; we just need the other half)

   Defense (added): +2 tests asserting no FD growth over 100 calls.

B. cmd_eod_digest async/sync split (P2)
   File: operator_status.py
   Pattern (from skill/references/sentinel-bugs.md, "Async/sync split"):
     - cmd_eod_digest stays sync (Telegram handler calls it sync,
       and so does main._run_penny_eod_digest via build_x_snapshot_sync)
     - New build_eod_digest_snapshot_async() that does the async work
     - Sync wrapper build_eod_digest_snapshot() that calls
       asyncio.run() on it
     - main._run_penny_eod_digest now `await`s the async version

C. run_penny_edge_exit canonical-exit fix (correctness)
   File: penny_edge_orchestrator.py
   Pattern (rule 40 from trading-sentinel-ops):
     Every exit-write path must route through pee.simulate_position.
     That means: even the max_hold force-close branch should query
     the daily bar for hi/lo and use the simulation's exit price
     if TP/SL was hit.

D. max_instances=1 + coalesce=True on penny_edge_scan and
   penny_edge_exit crons (rule 39 hygiene).
   Files: main.py
   Pattern: per-job max_instances + coalesce so a stuck tick of
   ONE subsystem can't deadlock the other. Default APScheduler
   misfire_grace_time is 1s; without explicit overrides a single
   35s second-long pause could silently drop the entire rest of
   the day's hourly reports. The penny_edge_scan cron at 09:30
   IST and the penny_edge_exit cron at 15:15 IST NOW carry the
   same discipline as the legacy penny_scanner_once (which was
   fixed in 70dd0a7).

E. Dead-code cleanup: `paper_mode=not live_master or True`
   in run_penny_edge_scan was always True (operator-error
   preserving code, never exercised). Reduced to `paper_mode=True`
   with a comment explaining the paper leg is always paper.

Verification
------------

1. Unit tests: full test suite = 907 passed, 2 skipped,
   3 pre-existing failures (unrelated to this work). Tests:
   - 7 new (4 for canonical-exit + 2 for FD-leak + 3 for
     async/sync split)
   - 1 structural guard cron-guard (max_instances+coalesce)
   - 1 UTC idempotency regex guard
   - 1 Pydantic Literal accepts-all-sources guard
2. ASCII audit returns "CLEAN: zero non-ASCII chars" for all
   6 modified source files plus the new test file plus the
   deviation note itself.
3. End-to-end smoke: penny_edge_orchestrator.py __main__ ran
   against an in-memory kite stub (`/tmp/sentinel-smoke.db`)
   with one ticker in `ohlcv_cache`. Result: regime reported
   (BOTH), 0 candidates (no real signals), no crashes. The
   `_run_penny_edge_exit_safe` cron path: seeded an OPEN
   4-day-old EDGE_PAPER position, stubbed the kite-stub to
   return a daily bar where hi >= target. Result:
   `exit_reason='tp'`, `exit_price=109.9450` (target * 1 - 5bps),
   `realised_pnl ≈ +Rs 97` (NOT 0.0 -- bug from the assessment
   is fixed). DB row was updated to CLOSED with the canonical
   exit.

Constraints (operator mandate, restated)
----------------------------------------

- Loud-but-non-blocking: every fix returns 503-style errors instead
  of hard-failing at startup. Rule 36 (live-trading-audit-fix-pattern).
- Live leg bankroll capped at PENNY_EDGE_LIVE_BANKROLL=1000. No
  surprises.
- PENNY_LIVE_TRADING env var still controls live order routing.
- Default: PENNY_LIVE_TRADING=false (paper-only). The `_live_trading_enabled()`
  short-circuit already enforces this; do not bypass it.
- Every deviation from a documented rule is recorded here, not
  silently merged.
