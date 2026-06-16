# Universe Expansion — Operator Runbook

**Audience:** Whoever is on-call when the scan behaves unexpectedly.
**Spec:** `docs/superpowers/specs/2026-06-15-universe-expansion-design.md`
**Plan:** `docs/superpowers/plans/2026-06-15-universe-expansion.md`

---

## What this feature does

Expands **BOTH** the swing and momentum screeners from Nifty 100 (100 names) to
Nifty 500 (500 names — NSE official EQ series, 2026-06-16). A 20-day median ADV
filter drops the bottom ~20% by traded value, so the live scan universe is
typically ~400 names.

**Expected impact (per leg, Stage 0 → Stage 1):**

| Leg | Before (Nifty 100) | After (Nifty 500) | Notes |
|---|---|---|---|
| Swing | 15-25 signals/day | 40-80 signals/day | ~20% filtered by liquidity |
| Momentum | 2-5 signals/day | 5-12 signals/day | MC3-T/MC5/MC6 gates do most filtering |

**Cost impact:**

- `run_screener` (2×/day): +62s liquidity filter → +2 min/day
- `run_momentum_screener` (hourly): +62s liquidity filter → +6.5 min/day
- **Total: +8.5 min/day of API-bound compute**, well within Kite's 3 req/s limit
  with `BREADTH_FETCH_PARALLELISM=8`.

**Tier 1 (breadth) is NOT expanded** — it stays on Nifty 100 due to the 90s
timeout constraint (DD1 in the spec). Non-Nifty-100 stocks get a `None` rank
from `build_breadth_kwargs` and are treated as neutral by the engine. The
narrow-rally gate still fires correctly because it uses engine-wide
`breadth_pct_above_sma50` from the Nifty 100 Tier 1.

---

## Quick diagnostics

### "Universe loaded from code" log line, not "from CSV"

The 3-tier fallback chain prefers the CSV at `UNIVERSE_PATH`, but falls back
to the in-code `NIFTY_500_TICKERS` (loaded from `data/nifty500.json` at module
init). If you see `"universe_loaded_from_code"` in the log:

- The CSV is missing or unreadable.
- The CSV is at `python-engine/data/nifty500.csv` — should be committed in the
  repo. Check `git status` and the file path.

This is **not an error** — the scan will still run on 500 names from the
in-code list. But fix the CSV before the next deploy.

### "liquidity_filter_complete" log line

This is informational. With defaults (`UNIVERSE_MIN_ADV_CRORE=2.0`), expect
~100 names dropped from 500. If more are dropped:

- The market may be unusually illiquid (temporary — wait for the next scan).
- Your `UNIVERSE_MIN_ADV_CRORE` is set too high. Lower it to keep more names.

If fewer are dropped than expected (e.g. 0):

- The threshold is too low for the current market. Raise it to drop illiquid
  tail.

### "universe_load_failed_all_paths" error

Both the CSV and the in-code list failed. Catastrophic — fix before market
open. Check:

1. Does `python-engine/data/nifty500.json` exist? (Source of truth for
   `NIFTY_500_TICKERS`.)
2. Does `python-engine/data/nifty500.csv` exist? (Used by the CSV path.)
3. Is `.env` pointing `UNIVERSE_PATH` at a valid file? (Default is
   `/data/nifty500.csv` — check that the path is mounted in the container.)
4. Is the JSON file well-formed? `python3 -c "import json; json.load(open('python-engine/data/nifty500.json'))"`
   should not raise.

### "breadth_universe_unsupported" warning

Means `BREADTH_UNIVERSE` is set to something other than `"NIFTY100"`. v1 only
supports `NIFTY100`. The engine continues to operate on the caller-provided
universe (which is fine — this is just a noisy log line). Set
`BREADTH_UNIVERSE=NIFTY100` in `.env` to silence.

---

## Feature flag reference

| Env var | Default | What it does |
|---------|---------|--------------|
| `UNIVERSE_SIZE` | `500` | Current size. Only 100 and 500 are supported in v1. |
| `UNIVERSE_TICKERS_FILE` | `nifty500.json` | Filename inside `BREADTH_DATA_DIR`. Currently unused — the in-code list (loaded from `nifty500.json` at module init) is the source of truth. |
| `UNIVERSE_MIN_ADV_CRORE` | `2.0` | Liquidity floor. Set to 0 to disable filtering entirely (escape hatch). |
| `UNIVERSE_LIQUIDITY_LOOKBACK_DAYS` | `20` | Lookback window for median ADV. |
| `BREADTH_UNIVERSE` | `NIFTY100` | Which universe Tier 1 breadth computes on. **NIFTY500 not supported in v1** — see spec DD1. |

---

## How to add or remove a ticker

The Nifty 500 constituents are reviewed semi-annually by NSE. To update the
list:

1. Get the new list from
   `https://archives.nseindia.com/content/indices/ind_nifty500list.csv` (EQ
   series only — exclude BE series entries).
2. Edit `python-engine/data/nifty500.json` (and the CSV mirror
   `python-engine/data/nifty500.csv`).
3. Validate:
   ```bash
   cd ~/trading-sentinel
   python3 -c "
   import json
   data = json.load(open('python-engine/data/nifty500.json'))
   symbols = [t['symbol'] for t in data['tickers']]
   assert len(symbols) == 500, f'Expected 500, got {len(symbols)}'
   assert len(set(symbols)) == 500, 'Duplicates'
   print('OK', len(symbols), 'tickers')
   "
   ```
4. Commit on the current branch.
5. Restart python-engine so the in-code `NIFTY_500_TICKERS` reloads from JSON.

**For daily tweaks (e.g. dropping a name that's behaving badly):** edit the
CSV at `python-engine/data/nifty500.csv` only. The CSV is preferred over the
in-code list (first tier of the fallback chain). Restart python-engine.

---

## Why is Tier 1 still on Nifty 100?

Tier 1 fetches 60-day history for 100 Nifty 100 stocks in ~25s. With 500
stocks, it'd take ~125s and exceed the 90s timeout. So Tier 1 is **decoupled
from the trading universe** — it stays on Nifty 100 (a stable, liquid
subset). The narrow-rally gate still works because it uses engine-wide
breadth (Nifty 100), not per-stock rank. For non-Nifty-100 stocks, the breadth
rank is `None` (treated as neutral).

Future work: Tier 1 on Nifty 500 with raised timeout, or a separate
"Tier 1.5" for the rank-only computation on the extra 400 names.

---

## Rolling back

The simplest rollback is to disable the feature:

```bash
# In python-engine/.env
UNIVERSE_SIZE=100           # or delete the file
UNIVERSE_MIN_ADV_CRORE=0    # disable liquidity filter
```

If you need to revert the code:

```bash
cd ~/trading-sentinel
git revert <commit-hash>   # or: git checkout main
```

The CSV/JSON files can be deleted to force the old in-code
`NIFTY_100_TICKERS` fallback (the first 50 entries are the swing subset
maintained at `main.py:357`; the second 100 entries at `main.py:365` are the
full Nifty 100).

---

## When to escalate

Open a high-priority ticket if:

- Signal count is 0 for 2+ hours after the change (universe is too small or
  filter is too aggressive).
- Liquidity filter is dropping >50% of names (the market may have changed;
  review the threshold).
- `"universe_load_failed_all_paths"` appears (no fallback path available —
  fix before market open).
- Kite rate-limit warnings fire during scans (the 8-way parallelism may be
  too aggressive; reduce `BREADTH_FETCH_PARALLELISM`).

---

## Cross-references

- **Spec:** `docs/superpowers/specs/2026-06-15-universe-expansion-design.md`
- **Plan:** `docs/superpowers/plans/2026-06-15-universe-expansion.md`
- **Change summary:** `docs/evolution/UNIVERSE_EXPANSION_CHANGES.md`
- **Branch-vs-desktop audit:** `docs/evolution/UNIVERSE_VS_DESKTOP_AUDIT.md`
- **Settings:** `python-engine/config.py` (`UNIVERSE_*` block)
- **Filter:** `python-engine/main.py` (`_filter_by_liquidity` helper)
- **Fallback loader:** `python-engine/main.py` (`_load_universe_with_fallback`)
- **Dispatch:** `python-engine/breadth.py` (BREADTH_UNIVERSE check in `__init__`)
