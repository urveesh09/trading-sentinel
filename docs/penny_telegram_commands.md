# Penny Telegram Commands — Operator Manual

_Last updated: 2026-06-25 (Phase A + B + C of operator console)_

This is your reference for every slash command you can send to the
Telegram bot — penny, nifty, and cross-subsystem. The bot reads your
messages, forwards them to the python-engine, and replies with the
result. Authentication is built in — only the configured
`TELEGRAM_CHAT_ID` can use these commands.

**All slash commands are read-only.** Per operator mandate (2026-06-25),
they do NOT execute trades, skip tickers, or change settings. To act
on signals, use the inline callback buttons on signal alerts or the
HTTP API.

---

## Quick reference

| Command | Purpose | Response time |
|---|---|---|
| `/penny stats` | Penny bankroll, today's P&L, open positions, regime | ~1s |
| `/penny regime` | Penny regime + the 3 reasons it was classified | ~1s |
| `/penny heatmap` | Live position heat-map (sectors + per-ticker P&L) | ~2s |
| `/penny skip TICKER` | Disable ticker from next scan onward | ~2s |
| `/penny unskip TICKER` | Re-enable ticker | ~2s |
| `/penny skips` | List currently-disabled tickers | ~1s |
| `/penny help` | Show this command list | <1s |
| `/nifty stats` | Nifty bankroll, deployed, today's P&L | ~1s |
| `/nifty swing` | Top 5 swing signals by score | ~1s |
| `/nifty momentum` | Top 5 momentum signals by score | ~1s |
| `/nifty regime` | Nifty market regime + age | ~1s |
| `/nifty circuit` | Nifty circuit-breaker state (halted? why?) | ~1s |
| `/nifty help` | Show nifty command list | <1s |
| `/health` | All subsystems status (penny + nifty) | ~1s |
| `/regime` | Penny + nifty regime side-by-side | ~1s |
| `/status` | One-screen all-systems view (bankroll, today's P&L) | ~1s |
| `/performance` | Nifty performance summary | ~1s |

---

## `/penny stats` — live snapshot

**What you get:**
```
Penny stats [PAPER]
Bankroll: Rs 2500
Today: +Rs 145 across 3 trades
Open positions: 2
Regime: PR2_ELEVATED
```

**Field meanings:**
- `Bankroll`: current Rs in your penny pool (paper or live, depending on `PENNY_LIVE_TRADING` config)
- `Today`: net P&L from trades closed today (after costs)
- `Open positions`: count of positions still in the book (MIS + CNC, `OPEN` or `CLOSED_T1` status)
- `Regime`: today's regime — `PR1_CALM` (5% sizing), `PR2_ELEVATED` (2.5%), `PR3_HOT` (0%, all new entries blocked), or `UNKNOWN`

**When to use:**
- Start of day, mid-day, end of day — anytime you want a snapshot
- Before deciding to override risk settings manually

---

## `/penny regime` — why are we in PR1/PR2/PR3 today

**What you get:**
```
Penny regime: PR2_ELEVATED
  computed: 2026-06-25
  - vol_rank=0.78 between PR1 max 0.70 and PR2 max 0.90
  - vix_proxy=0.62 between PR1 max 0.70 and PR2 max 0.90
      raw: Nifty 50 is -2.5% vs 50-day EMA
  - breadth=0.5 (placeholder; weighted 20% in regime score)
  => classified PR2_ELEVATED (sizing: 2.5% of bankroll per trade)
```

**Field meanings:**
- `vol_rank`: 0-1 measure of how volatile penny stocks are (worst across universe)
- `vix_proxy`: 0-1 measure of Nifty 50's distance below its 50-day EMA
- `raw: Nifty 50 is X% vs 50-day EMA`: raw input for drift monitoring
- `breadth`: placeholder (currently 0.5 = neutral). Wired but not yet a real input.
- `=> classified`: the final regime + sizing implication

**When to use:**
- When you see the hourly report say "regime: PR2" and want to know _why_
- When you suspect a regime is about to flip — check if either input is near a threshold (e.g. vol_rank=0.69 = 0.01 below PR2 boundary)
- When Nifty is having a bad day and you want to confirm the system is reacting

---

## `/penny heatmap` — live position heat-map

**What you get:**
```
Penny heat-map (15:42 IST) - 4 open, 4 priced
  Steel       [GOLDSTAR-SM +2.1% / BAJAJHIND -1.4%]   +0.4% avg
  Realty      [ARENTERP +0.8%]                       +0.8%
  Unmapped    [21STCENMGM -0.5% / OMFURN-ST +1.2%]  +0.4%
WARN: ARENTERP approaching SL (-2.1% from entry, SL at -3%)
```

**Field meanings:**
- `4 open, 4 priced`: total positions vs how many got a live price (n/a = quote failed)
- Per-sector line: tickers in that sector, per-ticker P&L %, average P&L % for the sector
- `Unmapped`: tickers not in `penny_sectors.csv` (operator-curated)
- `WARN: ... approaching SL`: position within `PENNY_HEATMAP_WARN_PCT` of its stop-loss (default 1.0%, configurable in `config.py` for tighter/looser sensitivity)

**When to use:**
- When you see a position in the hourly report and want its live P&L
- When a sector is having a rough day — concentration risk visible
- After a manual entry or override — confirm the new exposure looks right
- The same body is auto-pushed every 15 minutes during market hours — but you can pull on-demand between fires

**Note:** this is **information-only**. It does NOT trigger exits. SL-M at the broker + 14:30 smart-EOD + 15:00 force-close own exits.

---

## `/penny skip TICKER` — disable a ticker

**What you send:** `/penny skip GOLDSTAR-SM`

**What you get back:** `✓ GOLDSTAR-SM will be skipped from the next penny scan (~30s). Persistence: survives container restart.`

**What it does:**
- Adds the ticker to `python-engine/data/penny_disable_overrides.json`
- Next scanner cycle (within 30 seconds) excludes the ticker from evaluation
- Survives container restarts (file is on disk, not in memory)
- Telegram reply confirms the action

**When to use:**
- You see a ticker behaving oddly in the hourly report and want it paused for the day
- You want to test a specific ticker exclusion without editing `.env`
- Sector is crashing and you want to skip all tickers in that sector (do it one ticker at a time — or grow `penny_sectors.csv` and let T2-C's gate handle it)

**What it does NOT do:**
- It does NOT close any open position in that ticker. To close an open position, wait for SL-M or EOD, or close manually via the broker.
- It does NOT affect the Nifty (swing/momentum) subsystem. Only penny.

**Side note:** case doesn't matter — `/penny skip reliance` and `/penny skip RELIANCE` are equivalent. Ticker's stored uppercase.

---

## `/penny unskip TICKER` — re-enable a ticker

**What you send:** `/penny unskip GOLDSTAR-SM`

**What you get back:** `✓ GOLDSTAR-SM re-enabled. Next scan will evaluate it again.`

**What it does:**
- Removes the ticker from the runtime disable list
- The ticker reappears in the eligible universe for the next scan

**When to use:**
- You `/skip`-ed a ticker in the morning and want it back in the afternoon
- You sent the wrong ticker — undo

**Note:** even after un-skipping, the ticker might still be filtered by `PENNY_DISABLE_TICKERS` (the env-var list). Use `/penny skips` to see what's currently disabled and from which source.

---

## `/penny skips` — list currently-disabled tickers

**What you get:**
```
Penny runtime disable list (2 tickers, updated 2026-06-25T11:34:12+00:00):
GOLDSTAR-SM, RELIANCE
```

Or, if nothing is disabled:
```
Penny runtime disable list: (empty)
```

**Field meanings:**
- The list includes ONLY tickers in the runtime override file. If you have tickers in `PENNY_DISABLE_TICKERS` env-var, those are NOT shown here (they're set at server start).
- `updated` shows when the last `/skip` or `/unskip` happened (UTC).

**When to use:**
- Before market open to check what's pending from yesterday
- After a `/skip` to confirm the write landed
- To share state with yourself when debugging "why isn't this ticker firing?"

---

## `/penny help` — list of commands

**What you get:** the same quick-reference table at the top of this manual.

**When to use:**
- You forgot the syntax for a command
- You want to know what's available without reading this doc

---

## What's NOT exposed (deliberately)

The following operations are NOT in the chat interface because they're too risky for an SMS-style interface:

| Operation | Why not | Where to do it |
|---|---|---|
| Execute a trade | Fat-finger from phone = real money bug | Use the existing callback buttons on signal alerts |
| Close an open position | SL-M is the safety net; bypassing it manually is risky | Wait for SL-M / 14:30 EOD / 15:00 force-close, OR close via broker directly |
| Change bankroll | Affects sizing for every trade | Edit `.env` and restart container |
| Change regime thresholds | Affects every classification for the day | Edit `config.py` and redeploy |
| Change sector filter settings | Affects every gate | Edit `config.py` |

If you find yourself wanting one of these from chat, that's a signal
that the system needs a different UI layer (or a phone-call escalation
procedure) — not that we should add it to the chat.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Command returns `Error: python-engine unreachable` | Python container down OR network issue between gateway and engine | `docker ps` to check container; `docker logs node-gateway --since 5m` to see gateway errors |
| Command returns `Unknown command` | Typo or unsupported subcommand | `/penny help` to see the list |
| `/skip` succeeds but next scan still includes the ticker | Override file not readable, or write didn't sync (rare) | `docker exec python-engine cat /data/penny_disable_overrides.json` (note: path is `python-engine/data/...` relative; the actual mounted path may differ — check `PENNY_DISABLE_OVERRIDES_PATH` in `config.py`) |
| `/heatmap` shows all `n/a` | Kite token expired OR market closed | Check `docker logs python-engine --since 5m | grep kite_` for auth errors |
| `/regime` returns "engine not initialised" | Python-engine crashed during startup | `docker logs python-engine --since 5m` |

---

## Where this lives in the code

| File | Purpose |
|---|---|
| `python-engine/penny_commands.py` | Command handlers + dispatch (penny + cross-subsystem) |
| `python-engine/nifty_commands.py` | Read-only Nifty command handlers |
| `python-engine/penny_health.py` | `/health` + `/regime` cross-subsystem view |
| `python-engine/operator_status.py` | `/status` + `/performance` + EOD digest |
| `python-engine/data/penny_disable_overrides.json` | Runtime penny skip list (created by `/penny skip`) |
| `python-engine/data/penny_sectors.csv` | Operator-curated sector mapping (used by T2-C sector filter) |
| `node-gateway/server/services/telegram.js` | `bot.on('message')` handler with prefix routing for `/penny`, `/nifty`, `/health`, `/regime`, `/status`, `/performance` |
| `python-engine/main.py` | `/penny/command/{cmd}`, `/nifty/command/{cmd}`, `/command/{cmd}` endpoints |
| `python-engine/penny_risk.py` | `is_disabled()` reads penny override file every call |

---

## Cross-subsystem commands (Phase A + B + C, 2026-06-25)

The following commands don't have a `/penny` or `/nifty` prefix. They
return views across both subsystems. They're all read-only.

### `/health` — system diagnostic

**What you get:**
```
System health: OK
Penny: regime=PR1_CALM, last_regime=today, open=2
Nifty: regime=BULL, last_scan=5 min ago, open=1
Bankroll (nifty pool): Rs 5000
```

Or when degraded:
```
System health: DEGRADED
⚠ penny regime not refreshed recently
Penny: regime=UNKNOWN, last_regime=never, open=0
Nifty: regime=BULL, last_scan=just now, open=0
```

**Field meanings:**
- `overall_status`: `OK` or `DEGRADED`. Anything that can't be read or is stale shows DEGRADED.
- `Penny: regime=X, last_regime=Y`: penny's regime + how recently it was computed
- `Nifty: regime=X, last_scan=Y`: nifty's market regime + how long since last scanner run
- `⚠ ...`: warnings for stale data or halted subsystems

**When to use:**
- Anytime you want to know if everything is alive without SSHing in
- After a holiday or weekend to confirm both subsystems woke up
- When the hourly report looks weird — check if data is fresh

**Note:** the full structured JSON is available at `GET /health` if
you want every field (banks, halt_reasons, etc.).

### `/regime` — penny + nifty regimes side by side

**What you get:**
```
Regimes:
  Penny: PR2_ELEVATED (last: today)
  Nifty: BULL (last: 5 min ago)
```

If anything is stale or halted, a `⚠` line is added below.

**When to use:**
- Quick check without the full health output
- When you want to see regime drift ("penny regime was last refreshed yesterday" = bad)

### `/status` — one-screen all-systems view

**What you get:**
```
System status (15:42 IST)
Penny (PR2_ELEVATED): Rs 2600 (est) | today +Rs 100 | open=2
Nifty (BULL): Rs 5000 | today +Rs 150 | open=1
```

If halted: a `⚠ HALTED: ...` line at the top.

**Field meanings:**
- `(REGIME)`: current regime in parentheses
- `Rs NNNN (est)`: estimated penny balance (true balance is approximated; see `/penny attribution` for exact)
- `Rs NNNN`: actual nifty bankroll from `nifty_bankroll()`
- `today ±Rs N`: today's net P&L across both pools
- `open=N`: count of open positions per pool

**When to use:**
- Quick daily check
- The "all-in-one" view; if you only send one command per day, make it this one

### `/performance` — Nifty performance summary

**What you get:**
```
Performance (Nifty subsystem)
Trades: 10 (W:6 L:4) | Win rate: 60.0%
Avg R: +1.20
Realised: +Rs 500 | Unrealised: +Rs 50
Total: +Rs 550
```

Note: Nifty-only by strict-separation stance. For penny attribution,
use `/penny attribution` (the 15:30 IST daily attribution message).

**When to use:**
- End of day / end of week review
- Comparing live performance to your backtest baseline

### What's NOT exposed (still)

The operator console (`/health`, `/regime`, `/status`, `/performance`) is
**read-only by mandate**. The same constraint applies to `/nifty` commands.
Only the original `/penny skip TICKER` and `/penny unskip TICKER` mutate
state, and they're penny-only.
