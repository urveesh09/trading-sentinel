# 2026-06-24 — Strict-separation: Nifty subsystem isolated from Penny

## Problem

The penny bankroll integration (commits 9203dd7 and eb1ff78) opened a
door that exposed a deeper issue: **the two subsystems were not
actually separate in the risk math**, even though the user (Uru
2026-06-22, 2026-06-24) has always treated them as separate modules.

Specifically:

1. **`current_bankroll()` reads the LAST ledger row**, regardless of
   source. After a penny close happens, the last row is PENNY. So
   `current_bankroll()` returned `INITIAL_BANKROLL + swing_pnl + penny_pnl`
   instead of `INITIAL_BANKROLL + swing_pnl`.

2. **`check_circuit_breakers()` calls `current_bankroll()`**, then uses
   that number for:
   - `CB_FLOOR_PCT` floor (40% of INITIAL_BANKROLL = Rs 2,000)
   - `CB_DAILY_LOSS_PCT` daily loss halt (20% of current bankroll)
   - `CB_MAX_DRAWDOWN_PCT` peak-to-trough (50%)
   - Consecutive-loss streak (last 10 trades, all sources)

   All four were silently influenced by penny P&L. A penny loss could
   artificially trip the swing floor, or a penny win could inflate the
   swing daily-loss threshold.

3. **Swing `RiskEngine`** was constructed with `current_bankroll()`,
   so swing position sizing was sized off a penny-contaminated number.
   Same for the momentum pool size, the `/signals`, `/momentum-signals`,
   `/performance`, and `/bankroll` endpoints.

## User intent

Uru 2026-06-24: "from the start I wanted them to be separate module
systems only." This means penny and Nifty (swing + momentum) must not
contaminate each other in:
- Position sizing math
- Risk gate math
- Endpoint responses

## Decision: strict separation via a dedicated helper

A new helper `performance.nifty_bankroll(db_path)` returns the
**Nifty-subsystem balance** = `INITIAL_BANKROLL + SUM(pnl WHERE source
IN ('SYSTEM', 'MOMENTUM'))`. Penny rows are excluded by construction.

All 7 internal callers in `main.py` switched from `current_bankroll()`
to `nifty_bankroll()`:

| Line | Caller | Why |
|---|---|---|
| 882 | `run_screener` (swing) | swing `RiskEngine.bankroll` |
| 1102 | swing post-close sync | swing `RiskEngine.update_bankroll` |
| 1121 | `/signals` endpoint | swing display |
| 1167 | `run_momentum_screener` | momentum pool size = 50% of swing balance |
| 1461 | `/momentum-signals` endpoint | momentum display |
| 1816 | `/performance` endpoint | swing display |
| 1871 | `/bankroll` endpoint | now reports Nifty-subsystem balance |

Additionally `check_circuit_breakers()` was updated to:
- Read bankroll from `nifty_bankroll()` instead of `current_bankroll()`
- Filter `peak` (used by drawdown CB) to Nifty rows only:
  `MAX(bankroll_after) WHERE source IN ('SYSTEM', 'MOMENTUM')`
- Filter daily-PnL query to Nifty rows
- Filter consecutive-loss streak to Nifty rows

## What `current_bankroll()` does now

The legacy function is unchanged in behavior — it still reads the last
ledger row, which can be a PENNY row. **No production code calls it
anymore.** It remains public in `performance.py` for backwards
compatibility with external test suites and any out-of-tree consumers.
The integration tests in `tests/test_main_api.py` etc. continue to
expect `body["bankroll"] == INITIAL_BANKROLL` (5000) for empty ledgers,
which both `current_bankroll()` and `nifty_bankroll()` agree on, so
those tests still pass.

## Operational impact after this lands

- `/bankroll` continues to show `Rs 5,000.0` on a fresh prod DB. After
  the **first swing trade**, it shows `Rs 5,000 ± swing_pnl`. After
  penny trades start flowing in, **`/bankroll` no longer moves on
  penny P&L** — that's the visible change.
- `/bankroll/breakdown` shows swing and penny independently, plus the
  combined informational number.
- **Swing CBs are now strictly honest**: a penny loss cannot
  artificially trip or inflate the swing floor / daily-loss / drawdown
  triggers. Penny has its own kill-switch in `PennyRiskEngine`
  (`PENNY_DAILY_KILL_SWITCH_PCT = 0.20` of `PENNY_LIVE_BANKROLL`
  = Rs 400/day limit).
- **Swing position sizing is now strictly honest**: swing RiskEngine
  always sees the swing-only balance, not penny-contaminated.
- **Momentum pool size is now strictly honest**: 50% of swing balance,
  not 50% of swing+penny.

## Risk math delta (concrete)

| Scenario | Before strict separation | After strict separation |
|---|---|---|
| Swing at 5,000, penny loses 1,500 | swing "bankroll" reads 3,500; CB floor at 2,000 not tripped yet but sizing is reduced; daily loss threshold is 700 | swing bankroll still 5,000; CB unchanged; penny has its own 400/day kill-switch |
| Swing at 4,000, penny loses 2,000 | swing "bankroll" reads 2,000; CB floor AT the limit, daily loss threshold is 400 | swing bankroll still 4,000; CB unchanged; penny may have hit its own kill-switch |
| Swing at 3,500, penny wins 2,000 | swing "bankroll" reads 5,500; CB floor trivially safe; daily loss threshold is 1,100 (loosened by penny win!) | swing bankroll still 3,500; floor tripped at 2,000; daily loss threshold is 700 (honest) |

The third row is the most important change: penny wins no longer
loosen the swing CB. That's more conservative for swing, which is
the right default for strict separation.

## What did NOT change

- `INITIAL_BANKROLL = 5000.0`
- `PENNY_LIVE_BANKROLL = 2000.0`, `PENNY_PAPER_BANKROLL = 500.0`
- `CB_FLOOR_PCT = 0.40`, `CB_DAILY_LOSS_PCT = 0.20`, etc.
- `PennyRiskEngine` penny kill-switch logic (`PENNY_DAILY_KILL_SWITCH_PCT`)
- The `source` column on `bankroll_ledger`
- The `ledger_writer` injection in `PennyRiskEngine`
- `/bankroll/breakdown` shape (still returns `swing`, `penny`, `combined`, `as_of`)

## Files changed

- `python-engine/performance.py` — new `nifty_bankroll()`; CB internals
  use it + filter to Nifty sources
- `python-engine/main.py` — 7 internal callers switched to
  `nifty_bankroll()`; added import
- `python-engine/tests/test_performance.py` — 10 new
  `TestNiftyBankroll` tests
- `docs/deviations/2026-06-24-penny-strict-separation-deviation.md` —
  this doc

## Test impact

10 new tests covering:
- empty/swing/momentum/penny row handling
- penny-row-doesn't-contaminate (regression guard)
- penny-row-doesn't-contaminate-even-when-last (load-bearing test)
- check_circuit_breakers_uses_strict_separation (CB guard)
- check_circuit_breakers_does_count_swing_loss (positive case)
- check_circuit_breakers_consecutive_streak_ignores_penny (CB2 guard)
- check_circuit_breakers_penny_loss_does_not_break_swing_streak
  (CB2 inverse direction)

Full targeted suite: 213 passed (203 previous + 10 new), 0 failures.
Full project suite: 632 passed, 3 pre-existing failures in
test_universe_expansion + test_performance paper-mode (test isolation
issues unrelated to this change — verified by stashing my diff and
re-running).