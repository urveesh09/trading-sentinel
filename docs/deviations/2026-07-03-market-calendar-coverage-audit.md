# 2026-07-03 — Market calendar (weekend + NSE holiday) coverage audit

**Status:** Audit complete. The `market_calendar` module is sound (11/11 tests
green) but is consumed by **only 2 of 5 calendar-aware modules** and **2 of
~17 cron handlers**. The penny subsystem has **zero weekend/holiday gating**
on every cron except `_run_penny_edge_scan_safe` / `_run_penny_edge_exit_safe`
(which also lack gating — see "what was missed" below). No production
behavior change today, but the system will run every cron every Saturday,
Sunday, and NSE holiday, with predictable consequences ranging from noisy
logs to real financial-risk (force-close / auto-square).

**Scope:** Walked every `.py` module under `python-engine/` (43 files,
excluding `main_bkp.py`). Used two grep passes:
1. `grep -n "is_trading_day|is_market_open|market_calendar"` across all
   python-engine files
2. Per-cron-handler AST walk in `main.py` to check each `run_*` / `_run_*`
   function for an early-return `is_trading_day(...)` gate

## TL;DR — what the calendar knows and what it sees

| What `market_calendar.py` provides | Coverage today |
|---|---|
| `is_trading_day(date, db_path)` async — weekend + NSE holiday check | Used: swing `run_screener`, swing `_run_momentum_screener_impl` |
| `is_trading_day_sync(date, db_path)` sync — weekend + cached holidays | Used: `penny_engine_connors._trading_days_elapsed` |
| `is_market_open()` — weekend-aware 09:15–15:30 IST check | Used: swing Telegram notify gating (2 sites) |
| `next_trading_day`, `prev_trading_day` | Used: `main.py` calls `prev_trading_day` (3 sites) |
| `trading_days_between_sync(start, end, db_path)` | Used: `penny_engine_connors` only |

The calendar module is the right shape. **The gap is in callers.**

## Per-leg breakdown

### Swing subsystem (Nifty / momentum) — fully gated

**Cron handlers with weekend + holiday gate:**
- `run_screener` (main.py:1579) — checks `is_trading_day(today, ...)` at top,
  then uses `is_market_open()` to gate the Telegram notify.  Two-gate
  pattern, correct.
- `_run_momentum_screener_impl` (main.py:1984) — same two-gate pattern.

**Other calendar-aware calls:**
- `prev_trading_day(today, settings.DB_PATH)` is used in 3 places in main.py
  (mostly for premarket/regime context — see module-level scan).

**Verdict:** swing subsystem is fully aware. No fix needed.

### Penny subsystem — UNGATED

#### Cron handlers with NO weekend/holiday gate

| Cron | Schedule | Module | Verdict |
|---|---|---|---|
| `run_penny_scanner_once` | every 30s | main.py:289 | NO gate |
| `run_penny_connors_scan` | 09:30 daily | main.py:323 | NO gate |
| `run_penny_universe_refresh` | 08:00 daily | main.py:486 | NO gate |
| `run_penny_regime_compute` | 09:20 daily | main.py:539 | NO gate |
| `run_penny_regime_refresh` | 13:00 daily | main.py:554 | NO gate |
| `run_penny_eod_check` | 14:30 daily | main.py:565 | NO gate |
| `run_penny_force_close_mis` | 15:15 daily | main.py:612 | NO gate |
| `_run_penny_daily_attribution` | 15:30 daily | main.py:678 | NO gate |
| `_run_penny_eod_digest` | 16:00 daily | main.py:705 | NO gate |
| `_run_penny_heatmap` | every 5 min | main.py:743 | NO gate |
| `run_penny_hourly_report` | hourly | main.py:782 | NO gate |
| `_run_penny_edge_scan_safe` | 09:30 daily | main.py:1126 | NO gate |
| `_run_penny_edge_exit_safe` | 15:15 daily | main.py:1216 | NO gate |

**Total penny cron handlers: 13 of 13 ungated.** (Plus 2 swing handlers correctly gated.)

#### Other calendar-aware pieces in penny (good news)

- `penny_engine_connors._trading_days_elapsed` uses
  `trading_days_between_sync` (correctly holiday-aware) with a weekday-only
  fallback when the cache is empty. Added 2026-06-25 (PENNY-G6). Tested.
- `penny_backtest.py:170` skips weekends but does NOT model NSE holidays —
  explicit comment in the source says "NSE holidays are not modelled in v1".
  This is an acknowledged backtest gap (slightly underestimates alpha on
  Diwali-week windows).

#### Penny-premarket report — claims weekday, doesn't enforce

`penny_premarket_report.py:5` docstring says "every weekday" but the function
body has no `is_trading_day` gate. On a Saturday/Sunday it would read the
universe JSON and send a Telegram message claiming it's Friday's data.
Low-impact (false data, not unsafe) but noisy.

### Other modules — checked, no gate needed

- `analytics.py`, `position_tracker.py`, `performance.py` — pure DB
  utilities, no schedule, no time-of-day logic. Don't need a gate.
- `penny_universe.py`, `penny_models.py`, `penny_risk.py` — call sites
  without their own cron, invoked only by gated cron handlers above.
- `breadth.py`, `engine.py` — invoked by gated `run_screener`.

## What the picks actually did (this week)

N/A — the audit is about code, not trades. But note: the system has **never
held a trade into a Saturday** because the system only fires during market
hours on weekdays (when `is_trading_day` is checked) or, ungated, fires
exactly on day-end or weekends. The risk surface is in the *ungated* crons
that don't realize they're not on a trading day.

## What was missed — the cost of NOT gating on weekends

Concrete consequences by handler on a Saturday or Sunday:

| Cron | Cost on weekend |
|---|---|
| `run_penny_scanner_once` (30s) | Hits Kite for instrument cache, fetches ~100 quotes every 30 seconds. Weekend: quote bodies are empty/old → ~2,880 `penny_eval_skipped reason=quote_unavailable` lines per hour of unused log volume. ~69,120 over a Saturday+Sunday. Kite rate limit (3/sec) is hit but rate-limited, not throttled. |
| `run_penny_universe_refresh` (08:00) | Calls `refresh_from_kite` which fetches instrument NSE list, builds candidates, queries Yahoo corp data, writes `penny_static.json`. Hits Yahoo API on a day it won't be used. File write is harmless. |
| `run_penny_regime_compute` / `run_penny_regime_refresh` | Calls `_penny_regime_engine.compute_today(kite=kite)`. Reads from `penny_universe.json` (just-rewritten) and Kite for index data. Computes a "regime" for a non-trading day and overwrites the day-of-week regime for Monday. Minor: regime on Monday morning's compute will overwrite this stale value within minutes. |
| `run_penny_eod_check` (14:30) | If there are stray MIS positions (none expected — the Saturday pennny-edge exit is also ungated), would try to evaluate them. Empty-state expected but **handler runs unconditionally**. |
| `_run_penny_eod_digest` (16:00) | Reads bankroll, positions, regime, fires Telegram message claiming "today's P&L". On a weekend this is `+Rs 0 / 0 trades` — but it's still sent, every weekend. |
| `run_penny_force_close_mis` (15:15) | **REAL FINANCIAL RISK**: queries `get_open_positions` and force-closes MIS positions. If a Friday MIS position is held over the weekend (rare given the 1-day holding pattern, but not impossible), this will square it off at Saturday's quote (which Kite may serve for some tickers, else entry-price fallback). |
| `auto_square_momentum` (15:15) | **REAL FINANCIAL RISK**: same as above but for momentum positions. Positions opened Friday afternoon and not closed by 15:15 would be squared at 15:15 Saturday using whatever prices Kite returns. |
| `momentum_eod_warning` (15:10) | Telegram warning about pending EOD square-off — false alarm every weekend. |
| `_run_penny_daily_attribution` (15:30) | Telegram "daily P&L" for a non-trading day. Spammy but harmless. |
| `penny_edge_scan` (09:30) | Telegram "Penny Edge scan" message with zero candidates every Saturday + Sunday. Telegram noise. |
| `penny_edge_exit` (15:15) | If penny-edge held positions open across Saturday (the 3-day time-stop rule + a Friday entry would force-exit by Wednesday Monday — Tuesday Wednesday — but a Saturday check could see positions still open if holiday-counting goes wrong). Same risk as force_close_mis. |

## Why — structural explanation

There is a single source of truth (`market_calendar.py`) and a single
tested pattern (`is_trading_day(today, settings.DB_PATH)` → log → return).
The swing handlers found it because they were written first. The penny
handlers were added later (penny in May–June 2026) and the developers
(myself included, looking back at the git log of `register_penny_scheduler_jobs`
plus the new subsystems in PR #54/55/56) wired cron schedules and quit
without copying the gate pattern from swing.

Two compounding factors:

1. **No static-analysis guard test for missed gating.** There is no
   AST-walk test that asserts every registered cron handler ends with
   `is_trading_day(...)` or `is_market_open(...)` check. The bug-class
   is one missed line per handler — a guard test would have caught all
   13 missing gates in a single CI run.

2. **The `day_of_week` APScheduler feature was never used.** Zero
   `day_of_week=` arguments across all `scheduler.add_job()` calls
   (verified via `grep -n "day_of_week" main.py` → 0 matches). Had
   the cron been registered as `day_of_week="mon-fri"`, APScheduler
   would silently never fire on weekends — but the holiday gap
   would remain.

The connors engine's trading-day counting (PENNY-G6, 2026-06-25)
is the only place that added holiday-awareness after the fact, and
it's a reminder that this is a known concern that was only partially
addressed.

## Prioritised fix list

### P0 — `auto_square_momentum` + `run_penny_force_close_mis` + `_run_penny_edge_exit_safe`

These three handlers place real orders. On a weekend with stale held
positions they could fire at stale prices. **Two-line fix each:**
```python
today = datetime.now(IST).date()
if not await is_trading_day(today, settings.DB_PATH):
    logger.info("<handler_name>_skip reason=non_trading_day")
    return
```
Best placed AT THE TOP of each handler, immediately after the function
docstring and before any DB / API call. Mirrors the `run_screener`
pattern at main.py:1583–1588 exactly.

### P0 — `_run_penny_eod_digest` + `momentum_eod_warning` + `_run_penny_daily_attribution`

These three Telegram-message senders will fire on non-trading days.
**Same two-line fix** at the top of each. The visual cost is "daily
P&L summary appears at 16:00 IST every Saturday claiming +Rs 0 with
'no trades today'" — not a safety risk, but operator confusion +
Telegram noise. Cheap fix.

### P1 — `run_penny_universe_refresh` + `run_penny_regime_compute` + `run_penny_regime_refresh`

Network traffic on weekends (Kite + Yahoo calls) writing
`penny_static.json`. The file write is overwritten Monday morning so
the consequence is "we wasted 3 API calls on Saturday", but the regime
computation will **briefly claim a Saturday regime** that gets overwritten
by Monday's 09:20 compute. Could confuse a Saturday observer.

### P1 — `run_penny_scanner_once` (30-second interval)

The high-frequency one. On a 48-hour weekend this fires ~5,760 times.
Each one logs `penny_scan_complete accept=0 error=0 reject=0` once the
universe loader returns empty (cache never repopulated on weekend), so
the cost is more like "every 30s = 1 log line for 48h" → ~5,760 lines,
all non-actionable. Add the same two-line gate. The cron registration
also has `max_instances=1 + coalesce=True` so missed triggers collapse.

### P2 — `_run_penny_heatmap` + `run_penny_hourly_report`

Cosmetic: empty-state charts/messages on weekends. Two-line gate, low
priority.

### P1 (defensive) — Static analysis guard test

Add `tests/test_penny_cron_gating.py` that AST-walks main.py and
asserts every `def run_*` / `def _run_*` whose function name is referenced
in a `scheduler.add_job(...)` call must contain a call to
`is_trading_day(...)` OR a body that explicitly documents the
exception ("intentionally fires on weekends for X reason"). The pre-fix
13 failures would become 13 test errors at CI time. Defence against
the same bug class ever shipping again.

### P2 — `penny_premarket_report.py` docstring claim

Either add the gate OR change the docstring to "fires daily at HH:MM
IST" (drop the "every weekday" claim). Pre-market reports on Saturday
are harmless.

### P1 — `is_market_open()` for handlers that already filter by hour

Some handlers (e.g. `momentum_eod_warning` at 15:10) run during market
hours, but on a Saturday 15:10 `is_market_open()` would already return
False (because of the `weekday >= 5` check inside it). So a single
`is_market_open()` check at the top of each handler is **sufficient
AND** simpler than the full `is_trading_day` + DB lookup path. Trade-off
slight: `is_market_open()` doesn't check holidays, only weekends —
but for the 13:00/14:30/15:10/15:15/15:30/16:00 crons it's correct that
NSE holidays won't fire a "force close" (no risk surface because
positions that would force-close on holiday-Tuesday-15:15 should have
been force-closed on Monday's 15:15 if they'd been held, but that's a
business decision). Recommendation: **use `is_trading_day` for ALL
handlers** for full holiday coverage. The 60-second runtime cost
(async DB read for holiday cache) is dwarfed by the 30-second cron
interval.

## What's already good news

1. `market_calendar.py` exists, is tested (11/11), has both async + sync
   paths, fetches the NSE holiday list on first use, and has a SQLite
   cache so the second-and-later calls are sub-millisecond.
2. `penny_engine_connors` correctly uses `trading_days_between_sync` with
   a graceful fallback (PENNY-G6, 2026-06-25). This is the only place
   in penny that already had holiday-awareness added pre-audit.
3. `run_screener` and `_run_momentum_screener_impl` are fully gated and
   correctly use `is_market_open()` to suppress Telegram noise outside
   hours. Pattern is ready to copy.
4. APScheduler has `day_of_week="mon-fri"` available which would
   short-circuit the weekend firings at the framework level. (We don't
   use it because it doesn't handle holidays — but it's a defense
   layer worth adding for crons that genuinely only need to fire on
   trading days.)
5. No financial loss so far. The 8:00-universe-refresh on a Saturday
   just builds a slightly different candidate list (basing its
   liquidity lookback from a Friday close instead of last trading
   day) — but the file gets overwritten Monday morning before any
   decision depends on it.

## Files changed

```
docs/deviations/2026-07-03-market-calendar-coverage-audit.md   (this file)
```

No code changes shipped in this audit (it's a "see and assess" review
per the operator's request). The fix list is proposed above; the
recommended deployment shape is one PR per priority tier:

1. **PR-1 (P0, ~30 LoC):** Add `is_trading_day` gate to
   `auto_square_momentum`, `run_penny_force_close_mis`,
   `_run_penny_edge_exit_safe`, plus all 3 Telegram-message senders.
   Include the static-analysis guard test that asserts every
   scheduler-registered handler has a gate (or documented exception).
2. **PR-2 (P1, ~20 LoC):** Add the gate to the rest (universe refresh,
   regime compute, scanner, premarket report).
3. **PR-3 (P2):** Cosmetic gates on heatmap and hourly report.

PR-1 alone closes the financial-risk surface. Recommend shipping it
together with today's `c4cd186` Penny-instrument-cache fix into the
next planned maintenance window.
