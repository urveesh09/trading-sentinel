# Penny Telegram Commands — Operator Manual

_Last updated: 2026-06-25_

This is your reference for every `/penny` command you can send to the
Telegram bot. The bot reads your messages, forwards them to the
python-engine, and replies with the result. Authentication is built
in — only the configured `TELEGRAM_CHAT_ID` can use these commands.

---

## Quick reference

| Command | Purpose | Response time |
|---|---|---|
| `/penny stats` | Live bankroll, today's P&L, open positions, regime | ~1s |
| `/penny regime` | Current regime + the 3 reasons it was classified | ~1s |
| `/penny heatmap` | Live position heat-map (sectors + per-ticker P&L) | ~2s |
| `/penny skip TICKER` | Disable ticker from next scan onward | ~2s |
| `/penny unskip TICKER` | Re-enable ticker | ~2s |
| `/penny skips` | List currently-disabled tickers | ~1s |
| `/penny help` | Show this command list | <1s |

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
- `WARN: ... approaching SL`: position within 1.0% of its stop-loss

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
| `python-engine/penny_commands.py` | Command handlers + dispatch |
| `python-engine/data/penny_disable_overrides.json` | Runtime skip list (created by `/skip`) |
| `python-engine/data/penny_sectors.csv` | Operator-curated sector mapping (used by T2-C sector filter) |
| `node-gateway/server/services/telegram.js` | `bot.on('message')` handler that forwards `/penny` to python-engine |
| `python-engine/main.py` | `GET/POST /penny/command/{cmd}` endpoints |
| `python-engine/penny_risk.py` | `is_disabled()` reads override file every call |
