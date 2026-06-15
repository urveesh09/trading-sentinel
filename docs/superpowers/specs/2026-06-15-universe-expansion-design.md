# Universe Expansion to Nifty 500 — Design Spec
**Date:** 2026-06-15
**Status:** Revised 2026-06-15 (was "Approved" covering swing only; now covers BOTH swing and momentum screeners per user direction)

**Scope:** `python-engine/main.py`, `python-engine/universe.py`, `python-engine/breadth.py`, `python-engine/config.py`, `python-engine/data/`

**No changes to:** Engine scoring (engine.py), Node Gateway, agent, DB schema, models

---

## 1. Context

Both screeners currently scan 100 Nifty 100 names. The system is configured
to scan Nifty 500 (`UNIVERSE_PATH=/data/nifty500.csv`) but BOTH screeners
fall back to the hardcoded `NIFTY_100_TICKERS` list because the CSV doesn't
exist. `run_screener` (swing) falls back at main.py:431-438, `run_momentum_screener`
(momentum) falls back at main.py:717-724.

**Goal:** Make the Nifty 500 scan actually work for **BOTH** swing and momentum
screeners. Expected impact: 3-5× more swing signals + 3-5× more momentum signals
(the breadth enrichment work is already done, so the system can now evaluate
400+ names with regime + RS filter without over-gating).

## 2. Design Decisions

### DD1: Tier 1 (breadth) stays on Nifty 100, decoupled from scan universe
Tier 1 fetches 60-day history per token in the breadth universe. With
`BREADTH_TIER1_PARALLELISM=4` and ~0.07s per Kite historical call:
- 100 tokens → ~25s, within `BREADTH_FETCH_TIMEOUT_SECONDS=90`
- 500 tokens → ~125s, exceeds timeout

Tier 1 stays on Nifty 100 for v1. The breadth "rank" for a non-Nifty-100
stock is `None` → treated as neutral in `build_breadth_kwargs()`. The
narrow-rally gate in `engine.py` still fires (using engine-wide
`breadth_pct_above_sma50` from the Nifty 100 Tier 1), so non-Nifty-100
names are still protected from a narrow-rally regime.

Future work: Tier 1 on Nifty 500 with raised timeout, or a separate
"Tier 1.5" for the rank-only computation on the extra 400 names.

### DD2: Liquidity filter = drop bottom 20% by 20-day median traded value
At scan start, compute 20-day median ADV (in ₹ crore) per ticker. Drop
tickers below `UNIVERSE_MIN_ADV_CRORE=2.0`. Expected to keep ~400 of
the 500 names.

Why median over mean: median is robust to single-day volume spikes
(block deals, earnings surprises). Why 20 days: matches the period
the existing `calc_volume_consistency` uses. Why ₹2 cr: empirical
floor for clean entry/exit in Indian mid-caps.

### DD3: Sector data deferred
Nifty 100 currently uses `"UNKNOWN"` for all sectors. The portfolio.py
sector-concentration filter is therefore a no-op. Adding real sector
data is a separate concern. v1: `data/nifty500.csv` has `"UNKNOWN"`
for all sectors, matching current behavior.

### DD4: BREADTH_UNIVERSE setting is the dispatch source of truth
Already a reserved setting (config.py:185) but currently unused.
v1: only `"NIFTY100"` is supported. Any other value logs an error
and falls back to NIFTY100. The dispatch is testable so future
universe additions are a one-line config change.

## 3. Code Changes

### `python-engine/universe.py`
- Rename `get_nifty100_tokens()` → `get_tokens()`
- Add `size` property (returns `len(self._tokens)`)
- Keep `get_nifty100_tokens()` as a deprecated alias for backward compat

### `python-engine/breadth.py`
- Read `BREADTH_UNIVERSE` setting
- Dispatch: `"NIFTY100"` → `nifty100.json`; else log error + fallback to NIFTY100
- In v1, the dispatch is effectively a no-op (only NIFTY100 supported)
- The dispatch logic is what we test — adding NIFTY200/500 support later
  is just adding new branches in this dispatch

### `python-engine/main.py`
- Add `NIFTY_500_TICKERS` (third list, ~500 entries) below the existing two
- Replace the `NIFTY_100_TICKERS` fallback in the universe loader with
  a 3-tier chain:
    1. Try CSV at `UNIVERSE_PATH`
    2. Try `NIFTY_500_TICKERS` constant (hand-curated)
    3. Crash loudly with a clear error
- Add `_filter_by_liquidity(universe, kite, today, min_adv_crore)` helper
  that drops tickers below the ADV threshold

### `python-engine/config.py`
Add 4 new settings:
```python
UNIVERSE_SIZE:                   int   = 500         # 100 or 500 — current size
UNIVERSE_TICKERS_FILE:           str   = "nifty500.json"  # mirrors nifty100.json format
UNIVERSE_MIN_ADV_CRORE:          float = 2.0         # Drop tickers with 20-day median ADV below this
UNIVERSE_LIQUIDITY_LOOKBACK_DAYS: int  = 20          # Lookback for median ADV calc
```

### `python-engine/data/nifty500.json`
NEW file. 500 unique Nifty 500 tickers, same structure as
`nifty100.json`:
```json
{
  "as_of_date": "2026-06-15",
  "source": "Hand-curated Nifty 500 constituent list (publicly available from NSE, mirrored to data/ on 2026-06-15)",
  "tickers": [
    {"symbol": "RELIANCE", "instrument_token": null},
    ...499 more...
  ]
}
```

### `python-engine/data/nifty500.csv`
NEW file. Same content as the JSON but in CSV format (matches
existing `UNIVERSE_PATH` reader):
```csv
tradingsymbol,exchange,sector
RELIANCE,NSE,UNKNOWN
TCS,NSE,UNKNOWN
...498 more...
```

## 4. Tests

- `test_universe.py`: add tests for Nifty 500 loading, `size` property, `get_nifty100_tokens` deprecated alias
- `test_main_breadth_helpers.py`: add test that `build_breadth_engine` correctly dispatches on `BREADTH_UNIVERSE` value
- `test_universe_expansion.py` (NEW): tests for liquidity filter + Nifty 500 fallback chain + BOTH
  `run_screener` (swing) and `run_momentum_screener` (momentum) loaders

## 5. Rollout

`UNIVERSE_SIZE=500` and `UNIVERSE_MIN_ADV_CRORE=2.0` are the new defaults.
The CSV/JSON are committed to the repo. Rollout is feature-flag-free
because the previous run (without these files) just hits the in-code
`NIFTY_100_TICKERS` fallback in BOTH `run_screener` and `run_momentum_screener`.
To roll back: delete the files + revert the new config defaults.

**Momentum screener caveats:**
- Hourly scans of 500 names ≈ 1000 API calls/scan (2 per ticker: intraday + 30-day daily for MC5 ATR).
- With `BREADTH_FETCH_PARALLELISM=8`, the per-scan wall time grows from ~8s (100 names) to ~62s (500 names).
- This is still <2% of the 1-hour scan interval, so the throughput budget is fine.
- Kite's rate limit is 1 req/s on intraday + 1 req/s on historical, so 8-way parallelism is the sweet spot.
- Stage 1 will monitor: scan wall time, Kite rate-limit warnings, momentum signal count delta.

**Signal count expectations (per leg, Stage 0 → Stage 1):**
- Swing: 15-25 signals/day (Nifty 100) → 40-80 signals/day (Nifty 500, ~20% filtered by liquidity).
- Momentum: 2-5 signals/day (Nifty 100) → 5-12 signals/day (Nifty 500, MC3-T/MC5/MC6 gates do most filtering).

## 6. Open follow-ups

- Real sector data (NSE/BSE/paid feed) — out of scope for v1
- Tier 1 on Nifty 500 (DD1) — needs raised timeout + parallel tuning
- ADV filter tuning: monitor for over/under-filtering in Stage 1
- Real sector data will unlock portfolio concentration limits (currently use ticker count only)
