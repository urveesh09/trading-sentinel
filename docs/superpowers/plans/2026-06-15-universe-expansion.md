# Universe Expansion to Nifty 500 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expand **BOTH** the swing and momentum screeners from Nifty 100 (100 names) to Nifty 500 (500 names) so the system surfaces 3-5× more signals on each leg. Apply a basic liquidity filter (top 400 by ADV) to drop illiquid Nifty 500 tail. Keep Tier 1 breadth computation on Nifty 100 (stable, fast) — a decoupled design that's already implied by the breadth spec's OQ3.

**Architecture:**
- New data file `data/nifty500.json` mirroring the `nifty100.json` structure (500 unique tickers). Hand-curated from publicly-known Nifty 500 constituent list (committed once, not scraped).
- New `data/nifty500.csv` mirroring the format that `UNIVERSE_PATH` expects (`tradingsymbol`, `exchange`, `sector` columns). Sector field can be "UNKNOWN" for v1, matching current Nifty 100 behavior.
- `universe.py` generalised: rename `get_nifty100_tokens()` → `get_tokens()` + add `size` property. The class itself becomes universe-agnostic; the JSON file is the only thing that changes size.
- `breadth.py` reads the existing `BREADTH_UNIVERSE` setting (currently a reserved string `"NIFTY100"`) and dispatches to the right JSON. For v1 we still hard-wire Tier 1 to Nifty 100 (Option B in the design rationale below) because Tier 1 cost on 500 tokens would exceed the 90s timeout. This is a documented design decision, not a constraint.
- `main.py` BOTH `run_screener` (swing, L431) AND `run_momentum_screener` (momentum, L717) stop using the hardcoded `NIFTY_100_TICKERS` fallback. New fallback: try the CSV at `UNIVERSE_PATH`, then try the in-code Nifty 500 list, then crash loudly. The in-code NIFTY_500_TICKERS is the source of truth, mirrored into both files. The fallback is refactored into a shared helper `_load_universe_with_fallback()` to avoid duplication.
- New `config.py` setting: `UNIVERSE_TICKERS_PATH` pointing to a JSON file with a `tickers` list (the same format as nifty100.json). This is a sibling setting to `BREADTH_DATA_DIR`/`BREADTH_DATA_FILE`, but for the swing screener. The CSV path is preserved for backward compatibility.
- Liquidity filter at scan start: compute a 20-day median traded value per ticker, drop bottom 20%. Implemented in `main.py` (single dict lookup, not in `engine.py`).

**Tech Stack:** Python 3.11, pandas, pytest, structlog. No new dependencies.

**No changes to:** Node Gateway, agent, DB schema, models, the engine scoring logic (engine.py is untouched for both swing and momentum signal evaluation).

---

## File Map

| File | Action | What changes |
|------|--------|--------------|
| `docs/superpowers/specs/2026-06-15-universe-expansion-design.md` | NEW | Spec capturing the 4 design decisions (Tier 1 decoupling, liquidity filter, sector data deferred, BREADTH_UNIVERSE dispatch) — covers BOTH swing and momentum screeners |
| `python-engine/data/nifty500.json` | NEW | 500 unique Nifty 500 tickers, same structure as `nifty100.json` |
| `python-engine/data/nifty500.csv` | NEW | Mirror of `nifty500.json` in CSV format (tradingsymbol, exchange, sector) for the existing `UNIVERSE_PATH` reader (used by BOTH `run_screener` and `run_momentum_screener`) |
| `python-engine/universe.py` | MODIFY | Rename `get_nifty100_tokens()` → `get_tokens()`; add `size` property; backward-compat alias |
| `python-engine/breadth.py` | MODIFY | Read `BREADTH_UNIVERSE` setting, dispatch to correct JSON file (still hard-wired to NIFTY100 in v1) |
| `python-engine/main.py` | MODIFY | Replace `NIFTY_100_TICKERS` fallback with `NIFTY_500_TICKERS` in BOTH `run_screener` (L431-438) and `run_momentum_screener` (L717-724); add 3rd NIFTY_500_TICKERS block; add liquidity filter helper; new "tried CSV → tried code → crash" fallback chain in BOTH screeners |
| `python-engine/config.py` | MODIFY | Add 4 new settings: `UNIVERSE_SIZE`, `UNIVERSE_TICKERS_FILE`, `UNIVERSE_MIN_ADV_CRORE`, `UNIVERSE_LIQUIDITY_LOOKBACK_DAYS` |
| `python-engine/tests/test_universe.py` | MODIFY | Add tests for Nifty 500 loading, `size` property, fallback alias for `get_nifty100_tokens` |
| `python-engine/tests/test_main_breadth_helpers.py` | MODIFY | Add test that `build_breadth_engine` correctly dispatches on `BREADTH_UNIVERSE` value |
| `python-engine/tests/test_universe_expansion.py` | NEW | Tests for the new liquidity filter + Nifty 500 fallback chain in BOTH `run_screener` (swing) AND `run_momentum_screener` (momentum) |
| `docs/runbooks/universe-expansion.md` | NEW | Operator runbook: how to add/remove a ticker, how the liquidity filter works, how Tier 1 decoupling was decided, momentum-screener cost analysis |
| `docs/evolution/UNIVERSE_EXPANSION_CHANGES.md` | NEW | Change summary following the breadth-enrichment pattern (covers both screeners) |

---

## Design Decisions (locked in by the spec, captured in Task 1)

Before writing code, the spec must capture these 4 design decisions so the plan engineer doesn't have to re-litigate them:

**DD1: Tier 1 stays on Nifty 100 (decoupled from scan universe).**
- Why: Tier 1 fetches 60-day history per token. 100 tokens = ~25s (within the 90s timeout). 500 tokens = ~125s (exceeds). Raising the timeout would also raise the failure blast-radius (a single bad fetch blocks the whole scan for 2 minutes).
- Tradeoff: breadth "rank" for a non-Nifty-100 stock is None (treated as neutral in `build_breadth_kwargs`). For v1 this is fine — the gate is a soft preference, not a hard filter.
- Follow-up PR: Tier 1 on Nifty 500 with a higher timeout, OR Tier 1 stays at 100 and a separate "Tier 1.5" computes rank only for the rest.

**DD2: Liquidity filter = drop bottom 20% by 20-day median traded value.**
- Why: Nifty 500 has 100+ illiquid names (microcaps, recently-listed). Without filtering, the scan wastes compute on names that can't be entered/exited cleanly. Top 400 by traded value is the same approach NSE's own Nifty 500 index uses (they rebalance by free-float mcap, which is highly correlated with traded value).
- Metric: 20-day median daily traded value in ₹ crore, computed once at scan start, cached for the day. Threshold: `UNIVERSE_MIN_ADV_CRORE=2.0` (i.e., 400 names typically have >₹2 cr ADV). Configurable.
- Where: in `main.py` after the universe load, before the scan loop. Single function, returns the filtered ticker list.

**DD3: Sector data deferred to a follow-up PR.**
- Why: Nifty 100 currently uses "UNKNOWN" sector (line 437 of main.py). The portfolio.py sector-concentration filter is therefore a no-op for the current system. Adding real sector data is a separate concern that needs an authoritative source (NSE, BSE, or a paid feed). Out of scope for v1.
- v1: `data/nifty500.csv` has `"UNKNOWN"` for all 500 sectors, matching current Nifty 100 behavior.

**DD4: `BREADTH_UNIVERSE` setting becomes the source of truth for which JSON to load.**
- Why: it's already a reserved setting (line 185 of config.py) but currently unused. Wires it through to `breadth.py` so the future Tier 1 expansion is a one-line change.
- v1: `BREADTH_UNIVERSE="NIFTY100"` is the only supported value. Any other value logs an error and the engine falls back to NIFTY100. The dispatch is testable.

---

## Task 1: Write the design spec (decisions + deviations + test plan)

**Files:**
- Create: `docs/superpowers/specs/2026-06-15-universe-expansion-design.md`

This task exists so the plan engineer writes down the 4 design decisions before touching code. Without it, the engineer is reading this plan and inventing the design as they go.

> **Note (2026-06-15):** The spec at `docs/superpowers/specs/2026-06-15-universe-expansion-design.md` has ALREADY been written and committed in `c13194f`. The engineer should read the existing spec, verify it captures the 4 design decisions + the BOTH-screener scope, and update it if anything is missing. Do NOT rewrite the spec from scratch — it already exists and is correct after the 2026-06-15 revision that expanded scope from swing-only to swing + momentum.

The current spec is summarised below (for the engineer's reference — see the file on disk for the canonical version):

```markdown
# Universe Expansion to Nifty 500 — Design Spec
**Date:** 2026-06-15
**Status:** Revised 2026-06-15 (covers BOTH swing and momentum screeners)

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
- Replace the `NIFTY_100_TICKERS` fallback in **BOTH** universe loaders
  (`run_screener` at L431-438 + `run_momentum_screener` at L717-724) with
  a 3-tier chain:
    1. Try CSV at `UNIVERSE_PATH`
    2. Try `NIFTY_500_TICKERS` constant (hand-curated)
    3. Crash loudly with a clear error
- Add `_filter_by_liquidity(universe, kite, today, min_adv_crore)` helper
  that drops tickers below the ADV threshold
- Call `_filter_by_liquidity` from **BOTH** screeners (after the universe
  load, before the scan loop)

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
- `test_universe_expansion.py` (NEW): tests for liquidity filter + Nifty 500 fallback chain

## 5. Rollout

`UNIVERSE_SIZE=500` and `UNIVERSE_MIN_ADV_CRORE=2.0` are the new defaults.
The CSV/JSON are committed to the repo. Rollout is feature-flag-free
because the previous run (without these files) just hits the in-code
`NIFTY_100_TICKERS` fallback. To roll back: delete the files + revert
the new config defaults.

## 6. Open follow-ups

- Real sector data (NSE/BSE/paid feed) — out of scope for v1
- Tier 1 on Nifty 500 (DD1) — needs raised timeout + parallel tuning
- ADV filter tuning: monitor for over/under-filtering in Stage 1
```

- [ ] **Step 2: Commit the spec**

```bash
cd ~/trading-sentinel
git checkout -b feat/universe-expansion
git add docs/superpowers/specs/2026-06-15-universe-expansion-design.md
git commit -m "spec: universe expansion to Nifty 500 (design + 4 decisions)"
```

---

## Task 2: Hand-curate `data/nifty500.json`

**Files:**
- Create: `python-engine/data/nifty500.json`

- [ ] **Step 1: Build the Nifty 500 ticker list**

The Nifty 500 index constituents are publicly available (NSE publishes
the list, multiple financial sites mirror it). For v1, the engineer
should hand-paste 500 unique ticker symbols from a reliable source
(NSE's own PDF, MoneyControl, or Trendlyne). The list is the source
of truth and the user has already approved this approach for Nifty 100
(see commit `59c0953` from the breadth-enrichment work).

The file structure is exactly the same as `data/nifty100.json`:

```json
{
  "as_of_date": "2026-06-15",
  "source": "Hand-curated from NSE Nifty 500 constituent list (2026-06-15)",
  "tickers": [
    {"symbol": "RELIANCE", "instrument_token": null},
    ...499 more entries, sorted alphabetically...
  ]
}
```

**Important:** 500 unique symbols. No duplicates. All symbols must be
the NSE tradingsymbol (e.g., "M&M" not "M%26M", "BAJAJ-AUTO" with the
hyphen, "ETERNAL" not the old "ZOMATO" if it was renamed).

- [ ] **Step 2: Validate uniqueness and structure**

```bash
cd ~/trading-sentinel
python3 -c "
import json
data = json.load(open('python-engine/data/nifty500.json'))
assert list(data.keys()) == ['as_of_date', 'source', 'tickers'], f'Keys: {list(data.keys())}'
symbols = [t['symbol'] for t in data['tickers']]
assert len(symbols) == 500, f'Expected 500, got {len(symbols)}'
assert len(set(symbols)) == 500, f'Duplicates: {[s for s in symbols if symbols.count(s) > 1]}'
print('nifty500.json valid:', len(symbols), 'unique tickers')
"
```

Expected: `nifty500.json valid: 500 unique tickers`

- [ ] **Step 3: Commit**

```bash
git add python-engine/data/nifty500.json
git commit -m "feat(data): add static Nifty 500 ticker list (hand-curated 2026-06-15)"
```

---

## Task 3: Mirror `data/nifty500.csv` from the JSON

**Files:**
- Create: `python-engine/data/nifty500.csv`

- [ ] **Step 1: Generate the CSV from the JSON**

Use the helper script below (write it as a one-off, don't keep it):

```python
import json, csv
data = json.load(open('python-engine/data/nifty500.json'))
with open('python-engine/data/nifty500.csv', 'w', newline='') as f:
    w = csv.writer(f)
    w.writerow(['tradingsymbol', 'exchange', 'sector'])
    for t in data['tickers']:
        w.writerow([t['symbol'], 'NSE', 'UNKNOWN'])
```

Run it from `python-engine/data/`:

```bash
cd ~/trading-sentinel/python-engine/data
python3 -c "
import json, csv
data = json.load(open('nifty500.json'))
with open('nifty500.csv', 'w', newline='') as f:
    w = csv.writer(f)
    w.writerow(['tradingsymbol', 'exchange', 'sector'])
    for t in data['tickers']:
        w.writerow([t['symbol'], 'NSE', 'UNKNOWN'])
"
```

- [ ] **Step 2: Validate the CSV**

```bash
cd ~/trading-sentinel
python3 -c "
import csv
with open('python-engine/data/nifty500.csv') as f:
    rows = list(csv.DictReader(f))
assert len(rows) == 500, f'Expected 500, got {len(rows)}'
assert all(r['exchange'] == 'NSE' for r in rows)
assert all(r['sector'] == 'UNKNOWN' for r in rows)
symbols = [r['tradingsymbol'] for r in rows]
assert len(set(symbols)) == 500, 'Duplicates detected'
print('nifty500.csv valid:', len(rows), 'rows, all NSE/UNKNOWN')
"
```

Expected: `nifty500.csv valid: 500 rows, all NSE/UNKNOWN`

- [ ] **Step 3: Commit**

```bash
git add python-engine/data/nifty500.csv
git commit -m "feat(data): add Nifty 500 CSV mirror (UNIVERSE_PATH format, sector=UNKNOWN)"
```

---

## Task 4: Add the 4 new config settings

**Files:**
- Modify: `python-engine/config.py`

- [ ] **Step 1: Write the failing test**

Create `python-engine/tests/test_universe_config.py` (new file):

```python
"""Tests for the new universe-expansion config settings (Task 4)."""

def test_universe_size_default_is_500():
    """UNIVERSE_SIZE defaults to 500 (Nifty 500 expansion)."""
    from config import settings
    assert settings.UNIVERSE_SIZE == 500


def test_universe_tickers_file_default():
    """UNIVERSE_TICKERS_FILE points at nifty500.json by default."""
    from config import settings
    assert settings.UNIVERSE_TICKERS_FILE == "nifty500.json"


def test_universe_min_adv_crore_default():
    """UNIVERSE_MIN_ADV_CRORE defaults to 2.0 (₹2 crore median daily traded value floor)."""
    from config import settings
    assert settings.UNIVERSE_MIN_ADV_CRORE == 2.0


def test_universe_liquidity_lookback_default():
    """UNIVERSE_LIQUIDITY_LOOKBACK_DAYS defaults to 20."""
    from config import settings
    assert settings.UNIVERSE_LIQUIDITY_LOOKBACK_DAYS == 20
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd ~/trading-sentinel/python-engine
source .venv/bin/activate
python -m pytest tests/test_universe_config.py -v
```

Expected: 4 tests FAIL (AttributeError — settings don't exist yet).

- [ ] **Step 3: Add the 4 settings to `config.py`**

Open `python-engine/config.py`. Find the breadth block (around line 184).
Add the 4 new settings at the end of that block (so all universe
settings are co-located):

```python
    # === Universe Expansion (2026-06-15) ===
    UNIVERSE_SIZE:                   int   = 500       # 100 or 500 — current trading universe size
    UNIVERSE_TICKERS_FILE:           str   = "nifty500.json"  # Filename inside BREADTH_DATA_DIR; same format as nifty100.json
    UNIVERSE_MIN_ADV_CRORE:          float = 2.0       # Drop tickers with 20-day median ADV below this (₹ crore)
    UNIVERSE_LIQUIDITY_LOOKBACK_DAYS: int  = 20        # Lookback window for the median ADV computation
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
python -m pytest tests/test_universe_config.py -v
```

Expected: 4 tests PASS.

- [ ] **Step 5: Run the full suite to check for regressions**

```bash
python -m pytest tests/ 2>&1 | tail -3
```

Expected: 350+ passed (was 346, +4 new). No regressions.

- [ ] **Step 6: Commit**

```bash
cd ~/trading-sentinel
git add python-engine/config.py python-engine/tests/test_universe_config.py
git commit -m "feat(config): add universe-expansion settings (size, tickers file, ADV floor, lookback)"
```

---

## Task 5: Generalise `universe.py` (rename + add `size` + deprecated alias)

**Files:**
- Modify: `python-engine/universe.py`
- Modify: `python-engine/tests/test_universe.py`

- [ ] **Step 1: Write the failing tests**

Append the following to `python-engine/tests/test_universe.py`:

```python
# ─────────────────────────────────────────────────────────────────
# Generalised Universe (Task 5, 2026-06-15)
# ─────────────────────────────────────────────────────────────────


def test_universe_get_tokens_returns_same_as_get_nifty100_tokens(fake_kite_cache, tmp_path):
    """get_tokens() is the new name; get_nifty100_tokens() is a deprecated alias."""
    data_file = tmp_path / "nifty100.json"
    data_file.write_text(json.dumps({
        "as_of_date": "2026-06-14",
        "tickers": [{"symbol": f"SYM{i:03d}", "instrument_token": None} for i in range(100)]
    }))

    u = Universe(str(data_file), instrument_cache=fake_kite_cache)
    new_method = u.get_tokens()
    old_method = u.get_nifty100_tokens()
    assert new_method == old_method


def test_universe_size_property_reflects_loaded_count(fake_kite_cache, tmp_path):
    """Universe.size returns the number of resolved tokens."""
    data_file = tmp_path / "nifty500.json"
    data_file.write_text(json.dumps({
        "as_of_date": "2026-06-15",
        "tickers": [{"symbol": f"SYM{i:03d}", "instrument_token": None} for i in range(100)]
    }))

    u = Universe(str(data_file), instrument_cache=fake_kite_cache)
    # fake_kite_cache has SYM042 = None (unresolvable), so 99 resolved
    assert u.size == 99
```

- [ ] **Step 2: Run the new tests to verify they fail**

```bash
cd ~/trading-sentinel/python-engine
source .venv/bin/activate
python -m pytest tests/test_universe.py::test_universe_get_tokens_returns_same_as_get_nifty100_tokens tests/test_universe.py::test_universe_size_property_reflects_loaded_count -v
```

Expected: 2 tests FAIL (AttributeError).

- [ ] **Step 3: Add `get_tokens()` and `size` to `Universe`**

Open `python-engine/universe.py`. Find the `get_nifty100_tokens` method
(it's the last method in the class). Make these changes:

Add the `size` property right above `get_nifty100_tokens`:

```python
    @property
    def size(self) -> int:
        """Number of resolved tokens in this universe.

        Added for Task 5 (universe expansion, 2026-06-15). Returns
        len(self._tokens) — same value `get_tokens()` returns as the
        length of the set.
        """
        return len(self._tokens)

    def get_tokens(self) -> Set[int]:
        """Return the resolved instrument tokens for this universe.

        Added for Task 5 (universe expansion, 2026-06-15) as the
        universe-agnostic replacement for `get_nifty100_tokens()`.
        The Nifty 100 implementation is unchanged; only the name is
        generalised.
        """
        return self._tokens.copy()
```

Add the deprecated alias right below the new `get_tokens` method:

```python
    def get_nifty100_tokens(self) -> Set[int]:
        """DEPRECATED alias for `get_tokens()`.

        Kept for backward compatibility with breadth-enrichment code
        that calls this name. New code should use `get_tokens()`
        (universe-agnostic) or the `size` property.

        Removal plan: drop after the breadth-enrichment rollout
        completes Stage 2 (currently estimated Q3 2026).
        """
        return self.get_tokens()
```

- [ ] **Step 4: Update the `build_breadth_engine` call site in `main.py` to use the new name**

The breadth-enrichment code in `main.py` (around L83) currently calls
`breadth_universe.get_nifty100_tokens()`. Update to `get_tokens()`:

Find: `tokens=len(breadth_universe.get_nifty100_tokens())`
Replace with: `tokens=len(breadth_universe.get_tokens())`

- [ ] **Step 5: Run the new tests to verify they pass**

```bash
cd ~/trading-sentinel/python-engine
source .venv/bin/activate
python -m pytest tests/test_universe.py -v
```

Expected: All tests PASS (existing 6 + new 2 = 8).

- [ ] **Step 6: Run the full suite to check for regressions**

```bash
python -m pytest tests/ 2>&1 | tail -3
```

Expected: 350+ passed (was 350, +2 new). No regressions.

- [ ] **Step 7: Commit**

```bash
cd ~/trading-sentinel
git add python-engine/universe.py python-engine/tests/test_universe.py python-engine/main.py
git commit -m "refactor(universe): rename get_nifty100_tokens to get_tokens + add size property + deprecated alias

Generalises the Universe class so the same code can load nifty100.json,
nifty200.json, nifty500.json, etc. The deprecated alias is kept for
backward compatibility with the breadth-enrichment code that was
shipped with the old name."
```

---

## Task 6: Wire `BREADTH_UNIVERSE` setting through `breadth.py` (DD4)

**Files:**
- Modify: `python-engine/breadth.py`
- Modify: `python-engine/tests/test_breadth.py`

- [ ] **Step 1: Write the failing tests**

Append to `python-engine/tests/test_breadth.py`:

```python
# ─────────────────────────────────────────────────────────────────
# BREADTH_UNIVERSE dispatch (Task 6, 2026-06-15)
# ─────────────────────────────────────────────────────────────────


def test_breadth_engine_reads_breadth_universe_setting():
    """BreadthEngine reads settings.BREADTH_UNIVERSE at init time.

    Verifies the dispatch wiring (DD4). The actual file loaded is not
    tested here — we just check the setting is plumbed through.
    """
    from breadth import BreadthEngine
    from universe import Universe
    from config import settings
    import inspect

    src = inspect.getsource(BreadthEngine.__init__)
    assert "BREADTH_UNIVERSE" in src, (
        "BreadthEngine.__init__ should read settings.BREADTH_UNIVERSE to "
        "decide which universe file to load (DD4)"
    )


def test_breadth_engine_dispatch_logs_error_on_unknown_universe(monkeypatch, tmp_path):
    """Unknown BREADTH_UNIVERSE value logs an error and falls back to NIFTY100."""
    from breadth import BreadthEngine
    from config import settings

    # Set to an unsupported value
    monkeypatch.setattr(settings, "BREADTH_UNIVERSE", "NIFTY999")

    # Build a minimal universe + dummy kite
    from universe import Universe
    data_file = tmp_path / "nifty100.json"
    import json
    data_file.write_text(json.dumps({
        "as_of_date": "2026-06-14",
        "tickers": [{"symbol": f"SYM{i:03d}", "instrument_token": None} for i in range(5)]
    }))
    cache = {f"SYM{i:03d}": 1000 + i for i in range(5)}
    u = Universe(str(data_file), instrument_cache=cache)

    # Build a BreadthEngine with the dispatch logic; it should not raise
    # because the fallback is graceful.
    async def fake_kite(*args, **kwargs):
        return None

    # The engine init shouldn't fail even with an unknown BREADTH_UNIVERSE value
    engine = BreadthEngine(
        universe=u,
        kite_historical_fn=fake_kite,
        cache_ttl_seconds=settings.BREADTH_CACHE_TTL_SECONDS,
        degraded_threshold=settings.BREADTH_DATA_DEGRADED_THRESHOLD,
        tier1_parallelism=settings.BREADTH_TIER1_PARALLELISM,
    )
    # The engine should still work; the dispatch is a no-op for v1
    # (only NIFTY100 is fully supported)
    assert engine is not None
```

- [ ] **Step 2: Run the new tests to verify they fail**

```bash
cd ~/trading-sentinel/python-engine
source .venv/bin/activate
python -m pytest tests/test_breadth.py::test_breadth_engine_reads_breadth_universe_setting tests/test_breadth.py::test_breadth_engine_dispatch_logs_error_on_unknown_universe -v
```

Expected: 2 tests FAIL (`BREADTH_UNIVERSE` not referenced in init).

- [ ] **Step 3: Add the BREADTH_UNIVERSE dispatch to `BreadthEngine.__init__`**

Open `python-engine/breadth.py`. Find `BreadthEngine.__init__` (it's
the constructor at the top of the class). The current signature is:

```python
    def __init__(
        self,
        universe: Universe,
        kite_historical_fn: Callable,
        cache_ttl_seconds: int,
        degraded_threshold: float,
        tier1_parallelism: int,
    ):
```

Modify the body to read `settings.BREADTH_UNIVERSE` and log on
unknown values. The dispatch is a no-op for v1 because the
`universe` parameter is already passed in by the caller (the
dispatch only matters when the engine loads its own universe from
a file, which we don't do yet). What we add is just the *log*
that the setting is being read and validated:

Find the `self.universe = universe` line (or similar — first line
of `__init__` body). Add right after it:

```python
        # [BREADTH_UNIVERSE dispatch, Task 6, 2026-06-15]
        # For v1, only "NIFTY100" is supported. Other values log an
        # error and the engine continues to operate on the universe
        # passed in by the caller. Future PRs will add NIFTY200 /
        # NIFTY500 dispatch here.
        from config import settings
        if settings.BREADTH_UNIVERSE != "NIFTY100":
            logger.warning(
                "breadth_universe_unsupported",
                value=settings.BREADTH_UNIVERSE,
                supported="NIFTY100",
                fallback="NIFTY100 (caller-provided universe)",
            )
        else:
            logger.info(
                "breadth_universe_dispatched",
                value=settings.BREADTH_UNIVERSE,
            )
```

(Place this immediately after `self._parallelism = tier1_parallelism`
or wherever the existing init ends.)

- [ ] **Step 4: Run the new tests to verify they pass**

```bash
cd ~/trading-sentinel/python-engine
source .venv/bin/activate
python -m pytest tests/test_breadth.py -v
```

Expected: All tests PASS (existing 14 + new 2 = 16).

- [ ] **Step 5: Run the full suite to check for regressions**

```bash
python -m pytest tests/ 2>&1 | tail -3
```

Expected: 352+ passed. No regressions.

- [ ] **Step 6: Commit**

```bash
cd ~/trading-sentinel
git add python-engine/breadth.py python-engine/tests/test_breadth.py
git commit -m "feat(breadth): wire BREADTH_UNIVERSE setting through BreadthEngine (DD4 dispatch)

For v1, only NIFTY100 is fully supported. Unknown values log a
warning and the engine continues with the caller-provided universe.
The dispatch logic is testable so adding NIFTY200/500 support
later is a single-method change in BreadthEngine.__init__."
```

---

## Task 7: Add the liquidity filter helper in `main.py`

**Files:**
- Modify: `python-engine/main.py`
- Create: `python-engine/tests/test_universe_expansion.py`

- [ ] **Step 1: Write the failing tests**

Create `python-engine/tests/test_universe_expansion.py`:

```python
"""
Tests for the universe-expansion changes in main.py (Tasks 7-8).

Task 7: liquidity filter (drop tickers below 20-day median ADV floor).
Task 8: Nifty 500 fallback chain (CSV → in-code → crash).
"""

import asyncio
import os
import sys
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import pytest

HERE = os.path.dirname(__file__)
ENGINE_DIR = os.path.abspath(os.path.join(HERE, ".."))
if ENGINE_DIR not in sys.path:
    sys.path.insert(0, ENGINE_DIR)


# ─────────────────────────────────────────────────────────────────
# Liquidity filter (Task 7)
# ─────────────────────────────────────────────────────────────────


def _make_historical_df(closes):
    """Create a minimal historical DF with the given close prices."""
    dates = pd.date_range("2025-01-01", periods=len(closes), freq="D")
    return pd.DataFrame({
        "date": dates,
        "open": [c - 0.5 for c in closes],
        "high": [c + 1.0 for c in closes],
        "low": [c - 1.0 for c in closes],
        "close": closes,
        "volume": [1_000_000] * len(closes),
    })


def _make_intraday_df(n_candles: int = 30) -> pd.DataFrame:
    """Create a minimal intraday 5-min DF with a clean uptrend.

    Used by the run_momentum_screener tests (Task 8). The 30-candle
    default ≈ 2.5 hours of 5-min data (covers the morning session
    up to 12:00 IST), which is enough to trigger the MC3-T / MC5 /
    MC6 gates in evaluate_momentum_signal. The test mocks
    `evaluate_momentum_signal` to return False, so the actual
    indicator values don't matter — the DF just needs to be
    non-empty and well-formed so the `len(df_intra) < 4` check
    in run_momentum_screener passes.
    """
    times = pd.date_range("2025-01-15 09:15", periods=n_candles, freq="5min")
    closes = [100.0 + i * 0.1 for i in range(n_candles)]
    return pd.DataFrame({
        "date": times,
        "open": [c - 0.05 for c in closes],
        "high": [c + 0.10 for c in closes],
        "low":  [c - 0.10 for c in closes],
        "close": closes,
        "volume": [10_000] * n_candles,
    })


@pytest.mark.asyncio
async def test_filter_by_liquidity_drops_below_threshold(monkeypatch):
    """Tickers with 20-day median ADV below threshold are dropped."""
    from main import _filter_by_liquidity
    from config import settings

    monkeypatch.setattr(settings, "UNIVERSE_MIN_ADV_CRORE", 2.0)
    monkeypatch.setattr(settings, "UNIVERSE_LIQUIDITY_LOOKBACK_DAYS", 20)

    # Build a fake universe: 3 tickers, 2 pass + 1 fail
    universe = pd.DataFrame({
        "tradingsymbol": ["LIQUID_A", "LIQUID_B", "ILLIQUID_C"],
        "exchange": ["NSE", "NSE", "NSE"],
        "sector": ["UNKNOWN"] * 3,
    })

    # Build a fake kite: get_historical returns different ADV per ticker
    # 1 share × ₹100 × 100,000 vol/day = ₹10,000,000 = ₹1 cr ADV
    # For LIQUID: close=1000, vol=100k → ADV = 1000*100k = ₹100 cr → passes
    # For ILLIQUID: close=10, vol=10k → ADV = 10*10k = ₹1 lakh = ₹0.0001 cr → fails
    async def fake_get_historical(ticker, from_date, to_date):
        if ticker == "LIQUID_A" or ticker == "LIQUID_B":
            # close=1000, vol=100_000, 20 days
            return _make_historical_df([1000.0] * 25).assign(volume=[100_000] * 25)
        else:
            # close=10, vol=10_000, 20 days → very illiquid
            return _make_historical_df([10.0] * 25).assign(volume=[10_000] * 25)

    fake_kite = MagicMock()
    fake_kite.get_historical = fake_get_historical

    result = await _filter_by_liquidity(universe, fake_kite, today=pd.Timestamp("2026-06-15"))

    assert "LIQUID_A" in result["tradingsymbol"].values
    assert "LIQUID_B" in result["tradingsymbol"].values
    assert "ILLIQUID_C" not in result["tradingsymbol"].values


@pytest.mark.asyncio
async def test_filter_by_liquidity_handles_fetch_failure_gracefully(monkeypatch):
    """If a ticker's historical fetch fails, drop the ticker (fail-soft)."""
    from main import _filter_by_liquidity
    from config import settings

    monkeypatch.setattr(settings, "UNIVERSE_MIN_ADV_CRORE", 2.0)
    monkeypatch.setattr(settings, "UNIVERSE_LIQUIDITY_LOOKBACK_DAYS", 20)

    universe = pd.DataFrame({
        "tradingsymbol": ["GOOD", "BAD"],
        "exchange": ["NSE", "NSE"],
        "sector": ["UNKNOWN"] * 2,
    })

    async def fake_get_historical(ticker, from_date, to_date):
        if ticker == "BAD":
            return pd.DataFrame()  # empty
        return _make_historical_df([1000.0] * 25).assign(volume=[100_000] * 25)

    fake_kite = MagicMock()
    fake_kite.get_historical = fake_get_historical

    result = await _filter_by_liquidity(universe, fake_kite, today=pd.Timestamp("2026-06-15"))
    assert "GOOD" in result["tradingsymbol"].values
    assert "BAD" not in result["tradingsymbol"].values


@pytest.mark.asyncio
async def test_filter_by_liquidity_returns_input_when_threshold_zero(monkeypatch):
    """If UNIVERSE_MIN_ADV_CRORE=0, no filtering happens (escape hatch)."""
    from main import _filter_by_liquidity
    from config import settings

    monkeypatch.setattr(settings, "UNIVERSE_MIN_ADV_CRORE", 0.0)
    monkeypatch.setattr(settings, "UNIVERSE_LIQUIDITY_LOOKBACK_DAYS", 20)

    universe = pd.DataFrame({
        "tradingsymbol": ["ANY", "TICKER"],
        "exchange": ["NSE"] * 2,
        "sector": ["UNKNOWN"] * 2,
    })
    fake_kite = MagicMock()

    result = await _filter_by_liquidity(universe, fake_kite, today=pd.Timestamp("2026-06-15"))
    assert len(result) == 2
```

- [ ] **Step 2: Run the new tests to verify they fail**

```bash
cd ~/trading-sentinel/python-engine
source .venv/bin/activate
python -m pytest tests/test_universe_expansion.py -v
```

Expected: 3 tests FAIL (function `_filter_by_liquidity` not defined).

- [ ] **Step 3: Add `_filter_by_liquidity` to `main.py`**

Add this function near the top of `main.py`, right after the
`build_breadth_kwargs` helper (around L107):

```python
async def _filter_by_liquidity(
    universe: pd.DataFrame,
    kite,
    today: pd.Timestamp,
) -> pd.DataFrame:
    """Drop tickers below the 20-day median ADV floor (DD2).

    For each ticker in the universe, fetch the last 20 days of OHLCV,
    compute median daily traded value (close × volume), and drop any
    ticker whose median is below `UNIVERSE_MIN_ADV_CRORE`.

    Returns the filtered DataFrame. Failures (empty df, fetch error)
    result in the ticker being dropped — better to skip a name than
    to enter a position without liquidity data.

    If `UNIVERSE_MIN_ADV_CRORE <= 0`, returns the input unchanged
    (escape hatch for "disable filtering" via .env).
    """
    from config import settings as cfg
    min_adv_crore = cfg.UNIVERSE_MIN_ADV_CRORE
    lookback_days = cfg.UNIVERSE_LIQUIDITY_LOOKBACK_DAYS

    if min_adv_crore <= 0:
        return universe

    from datetime import timedelta
    from_date = (today - timedelta(days=lookback_days + 5)).strftime("%Y-%m-%d")
    to_date = today.strftime("%Y-%m-%d")

    kept_rows = []
    dropped = 0
    for _, row in universe.iterrows():
        ticker = row["tradingsymbol"]
        try:
            df = await kite.get_historical(ticker, from_date, to_date)
            if df.empty or len(df) < lookback_days // 2:
                dropped += 1
                continue
            # Compute median traded value
            traded_value = (df["close"] * df["volume"]).tail(lookback_days)
            median_tv_crore = float(traded_value.median()) / 1e7  # ₹ → ₹ crore
            if median_tv_crore >= min_adv_crore:
                kept_rows.append(row)
            else:
                dropped += 1
        except Exception as e:
            logger.warning("liquidity_filter_fetch_failed", ticker=ticker, error=str(e))
            dropped += 1

    if dropped > 0:
        logger.info(
            "liquidity_filter_complete",
            kept=len(kept_rows),
            dropped=dropped,
            threshold_crore=min_adv_crore,
        )
    return pd.DataFrame(kept_rows) if kept_rows else universe.iloc[0:0]
```

- [ ] **Step 4: Run the new tests to verify they pass**

```bash
cd ~/trading-sentinel/python-engine
source .venv/bin/activate
python -m pytest tests/test_universe_expansion.py -v
```

Expected: 3 tests PASS.

- [ ] **Step 5: Run the full suite**

```bash
python -m pytest tests/ 2>&1 | tail -3
```

Expected: 355+ passed. No regressions.

- [ ] **Step 6: Commit**

```bash
cd ~/trading-sentinel
git add python-engine/main.py python-engine/tests/test_universe_expansion.py
git commit -m "feat(main): add _filter_by_liquidity helper (20-day median ADV floor, DD2)"
```

---

## Task 8: Wire Nifty 500 fallback chain + liquidity filter into BOTH `run_screener` (swing) AND `run_momentum_screener` (momentum)

**Files:**
- Modify: `python-engine/main.py` (TWO call sites: L431 swing, L717 momentum)
- Modify: `python-engine/tests/test_universe_expansion.py` (add 1 new test for momentum)

This task expands the universe to Nifty 500 in **both** screeners.
The expected signal-count change is:
- Swing: 15-25/day (Nifty 100) → 40-80/day (Nifty 500, ~20% filtered by liquidity)
- Momentum: 2-5/day (Nifty 100) → 5-12/day (Nifty 500, MC3-T/MC5/MC6 gates do most filtering)

- [ ] **Step 1: Write the failing integration test**

Append to `python-engine/tests/test_universe_expansion.py`:

```python
# ─────────────────────────────────────────────────────────────────
# Nifty 500 fallback chain (Task 8)
# ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_run_screener_uses_nifty500_fallback_when_csv_missing(monkeypatch, db_path):
    """When UNIVERSE_PATH CSV is missing, run_screener falls back to in-code NIFTY_500_TICKERS."""
    from performance import init_ledger
    from position_tracker import init_positions_db
    await init_ledger(db_path)
    await init_positions_db(db_path)

    import main
    from config import settings

    # Point UNIVERSE_PATH at a non-existent file
    monkeypatch.setattr(settings, "UNIVERSE_PATH", "/tmp/does_not_exist_xyz.csv")
    monkeypatch.setattr(settings, "UNIVERSE_MIN_ADV_CRORE", 0.0)  # disable liquidity filter for this test
    monkeypatch.setattr(settings, "BREADTH_ENRICHMENT_ENABLED", False)
    main.breadth_engine = None

    # Sanity check: the in-code list should have ~500 entries
    assert len(main.NIFTY_500_TICKERS) >= 400, (
        f"NIFTY_500_TICKERS should have ~500 entries, got {len(main.NIFTY_500_TICKERS)}"
    )

    # Patch enough of run_screener's deps to confirm the fallback was used
    with patch.object(main, "is_trading_day", new=AsyncMock(return_value=True)), \
         patch.object(main, "kite") as mock_kite, \
         patch.object(main.kite, "access_token", new="fake_token"), \
         patch.object(main, "calc_ema", return_value=pd.Series([100.0])), \
         patch.object(main, "calc_atr", return_value=pd.Series([1.5, 1.5])), \
         patch.object(main, "calc_rsi_series", return_value=pd.Series([60.0])), \
         patch.object(main, "get_open_positions", new=AsyncMock(return_value=[])), \
         patch.object(main, "filter_and_allocate", return_value=([], [])), \
         patch.object(main, "notify_screener_results", new=AsyncMock()), \
         patch.object(main, "current_bankroll", new=AsyncMock(return_value=5000.0)):

        mock_kite.instrument_cache = {}
        # Mock get_historical to return a valid df for ANY ticker
        def make_hist_df(*args, **kwargs):
            return _make_historical_df([100.0] * 250).assign(volume=[100_000] * 250)
        mock_kite.get_historical = AsyncMock(side_effect=make_hist_df)

        main.current_regime = MagicMock()
        main.market_regime = "BULL"
        main.bankroll = 5000.0
        main.risk_pct = 0.10
        main.nifty_close = 18000.0
        main.nifty_ema20 = 17900.0
        main.nifty_return_1d = 0.001
        main.nifty_df = _make_historical_df([18000.0 + i for i in range(250)])
        main.is_market_open = MagicMock(return_value=False)

        # run_screener should complete without raising FileNotFoundError
        await main.run_screener()


@pytest.mark.asyncio
async def test_run_screener_calls_liquidity_filter(monkeypatch, db_path):
    """The scan calls _filter_by_liquidity once after loading the universe."""
    from performance import init_ledger
    from position_tracker import init_positions_db
    await init_ledger(db_path)
    await init_positions_db(db_path)

    import main
    from config import settings

    monkeypatch.setattr(settings, "UNIVERSE_PATH", "/tmp/does_not_exist_xyz.csv")
    monkeypatch.setattr(settings, "UNIVERSE_MIN_ADV_CRORE", 0.0)
    monkeypatch.setattr(settings, "BREADTH_ENRICHMENT_ENABLED", False)
    main.breadth_engine = None

    with patch.object(main, "is_trading_day", new=AsyncMock(return_value=True)), \
         patch.object(main, "kite") as mock_kite, \
         patch.object(main.kite, "access_token", new="fake_token"), \
         patch.object(main, "calc_ema", return_value=pd.Series([100.0])), \
         patch.object(main, "calc_atr", return_value=pd.Series([1.5, 1.5])), \
         patch.object(main, "calc_rsi_series", return_value=pd.Series([60.0])), \
         patch.object(main, "get_open_positions", new=AsyncMock(return_value=[])), \
         patch.object(main, "filter_and_allocate", return_value=([], [])), \
         patch.object(main, "notify_screener_results", new=AsyncMock()), \
         patch.object(main, "current_bankroll", new=AsyncMock(return_value=5000.0)), \
         patch.object(main, "_filter_by_liquidity", new=AsyncMock(side_effect=lambda u, k, today: u)) as mock_filter:

        mock_kite.instrument_cache = {}
        mock_kite.get_historical = AsyncMock(return_value=_make_historical_df([100.0] * 250).assign(volume=[100_000] * 250))

        main.current_regime = MagicMock()
        main.market_regime = "BULL"
        main.bankroll = 5000.0
        main.risk_pct = 0.10
        main.nifty_close = 18000.0
        main.nifty_ema20 = 17900.0
        main.nifty_return_1d = 0.001
        main.nifty_df = _make_historical_df([18000.0 + i for i in range(250)])
        main.is_market_open = MagicMock(return_value=False)

        await main.run_screener()

    # _filter_by_liquidity should have been called at least once
    assert mock_filter.await_count >= 1, "run_screener should call _filter_by_liquidity"


@pytest.mark.asyncio
async def test_run_momentum_screener_uses_nifty500_fallback_when_csv_missing(monkeypatch, db_path):
    """When UNIVERSE_PATH CSV is missing, run_momentum_screener falls back to in-code NIFTY_500_TICKERS.

    Mirrors the run_screener test above, but for the momentum leg.
    The momentum screener (main.py:717-724) shares the same universe loader,
    so both should be expanded to 500. This test guards against the case
    where the swing fallback is wired but the momentum one is forgotten.
    """
    from performance import init_ledger
    from position_tracker import init_positions_db
    await init_ledger(db_path)
    await init_positions_db(db_path)

    import main
    from config import settings

    monkeypatch.setattr(settings, "UNIVERSE_PATH", "/tmp/does_not_exist_xyz.csv")
    monkeypatch.setattr(settings, "UNIVERSE_MIN_ADV_CRORE", 0.0)  # disable liquidity filter for this test
    monkeypatch.setattr(settings, "BREADTH_ENRICHMENT_ENABLED", False)
    main.breadth_engine = None

    # Sanity check: the in-code list should have ~500 entries
    assert len(main.NIFTY_500_TICKERS) >= 400, (
        f"NIFTY_500_TICKERS should have ~500 entries, got {len(main.NIFTY_500_TICKERS)}"
    )

    with patch.object(main, "is_trading_day", new=AsyncMock(return_value=True)), \
         patch.object(main, "kite") as mock_kite, \
         patch.object(main.kite, "access_token", new="fake_token"), \
         patch.object(main, "evaluate_momentum_signal", return_value=(False, {"reject_reason": "test"})), \
         patch.object(main, "filter_momentum_signals", return_value=([], [])), \
         patch.object(main, "get_open_positions", new=AsyncMock(return_value=[])), \
         patch.object(main, "notify_screener_results", new=AsyncMock()), \
         patch.object(main, "current_bankroll", new=AsyncMock(return_value=5000.0)):

        mock_kite.instrument_cache = {}
        # Mock get_intraday + get_historical for the momentum screener
        def make_intra_df(*args, **kwargs):
            return _make_intraday_df()  # 5-min candles for the morning session
        def make_hist_df(*args, **kwargs):
            return _make_historical_df([100.0] * 30).assign(volume=[100_000] * 30)
        mock_kite.get_intraday = AsyncMock(side_effect=make_intra_df)
        mock_kite.get_historical = AsyncMock(side_effect=make_hist_df)

        main.current_regime = MagicMock()
        main.market_regime = "BULL"
        main.signaled_momentum_today = set()
        main.last_momentum_date = None

        # run_momentum_screener should complete without raising FileNotFoundError
        await main.run_momentum_screener()
```

- [ ] **Step 2: Run the new tests to verify they fail**

```bash
cd ~/trading-sentinel/python-engine
source .venv/bin/activate
python -m pytest tests/test_universe_expansion.py -k "nifty500 or liquidity_filter" -v
```

Expected: All 3 tests FAIL (`NIFTY_500_TICKERS` doesn't exist, and the
filter isn't called yet, and the momentum screener still uses the old
100-ticker fallback).

- [ ] **Step 3: Add NIFTY_500_TICKERS to main.py and wire the fallback chain**

Open `python-engine/main.py`. Find the existing
`NIFTY_100_TICKERS = [...]` blocks (at L297 and L305). Add a third
`NIFTY_500_TICKERS` block right after them (around L307, before the
`logger = structlog.get_logger()` at the top — wait, the logger is
already at the top, so this should go BELOW the second NIFTY_100
block). The block should contain 500 unique tickers. The structure
mirrors the existing blocks:

```python
NIFTY_500_TICKERS = [
    "RELIANCE", "TCS", "HDFCBANK", ...  # ~500 unique entries
]
```

**Important:** 500 unique tickers. The full Nifty 500 list needs to
be hand-pasted from a reliable source (NSE PDF, MoneyControl,
Trendlyne). The engineer should NOT scrape NSE (the previous
breadth-enrichment work established this constraint — NSE blocks
bots and the list already exists in code as 100 unique tickers,
mirrored from NIFTY_100_TICKERS in main.py:225).

- [ ] **Step 4: Wire the 3-tier fallback chain into BOTH `run_screener` AND `run_momentum_screener`**

**Both screeners share the same universe loader pattern** (try CSV → fallback). Apply the same 3-tier chain in both places.

**Site 1: `run_screener` (swing, around L431-438)**

Find the existing `try: universe = pd.read_csv(settings.UNIVERSE_PATH)`
block. Replace it with the 3-tier chain:

```python
    # 3-tier universe fallback chain (Task 8, 2026-06-15):
    #   1. Try CSV at UNIVERSE_PATH (operator-editable, supports custom universes)
    #   2. Try in-code NIFTY_500_TICKERS (hand-curated, always available)
    #   3. Crash loudly with a clear error (no silent fallback to old NIFTY_100)
    try:
        universe = pd.read_csv(settings.UNIVERSE_PATH)
        logger.info("universe_loaded_from_csv", path=settings.UNIVERSE_PATH, count=len(universe))
    except (FileNotFoundError, Exception) as e:
        if not isinstance(e, FileNotFoundError):
            logger.warning("universe_csv_load_failed", error=str(e))
        if hasattr(__import__(__name__), "NIFTY_500_TICKERS") and len(NIFTY_500_TICKERS) > 0:
            logger.info("universe_loaded_from_code", count=len(NIFTY_500_TICKERS))
            universe = pd.DataFrame({
                "tradingsymbol": NIFTY_500_TICKERS,
                "exchange": ["NSE"] * len(NIFTY_500_TICKERS),
                "sector": ["UNKNOWN"] * len(NIFTY_500_TICKERS),
            })
        else:
            logger.error("universe_load_failed_all_paths",
                         csv=settings.UNIVERSE_PATH,
                         code_list="NIFTY_500_TICKERS")
            raise RuntimeError(
                f"Cannot load universe: CSV at {settings.UNIVERSE_PATH} not found, "
                f"and NIFTY_500_TICKERS is empty or missing. "
                f"Add a CSV at the path, or define NIFTY_500_TICKERS in main.py."
            )
```

**Site 2: `run_momentum_screener` (momentum, around L717-724)**

Find the SECOND `try: universe = pd.read_csv(settings.UNIVERSE_PATH)`
block (the one in `run_momentum_screener`, with fallback
`universe_csv_missing_fallback_momentum`). Apply the **exact same
3-tier chain** as Site 1. Do not duplicate the code — refactor it
into a helper function `_load_universe_with_fallback(logger)` at
module scope and call it from both places.

- [ ] **Step 5: Wire the liquidity filter into BOTH screeners**

The liquidity filter call is the same in both screeners. Insert it
right after the universe fallback chain (after the `universe = ...`
assignment), BEFORE the scan loop begins.

**Site 1: `run_screener`** — find the line that starts with
`raw_signals = []` in `run_screener` (around L441). Insert BEFORE
that line:

```python
    # Liquidity filter (Task 7+8, 2026-06-15): drop tickers with 20-day
    # median ADV below UNIVERSE_MIN_ADV_CRORE. This prevents the scan
    # from wasting compute on illiquid Nifty 500 names.
    universe = await _filter_by_liquidity(universe, kite, today=pd.Timestamp(today))
    logger.info("universe_after_liquidity_filter", count=len(universe))
```

**Site 2: `run_momentum_screener`** — find the line that starts with
`raw_momentum = []` in `run_momentum_screener` (around L733). Insert
BEFORE that line. The exact same call:

```python
    # Liquidity filter (Task 7+8, 2026-06-15): same as in run_screener.
    universe = await _filter_by_liquidity(universe, kite, today=pd.Timestamp(today))
    logger.info("momentum_universe_after_liquidity_filter", count=len(universe))
```

**Note on cost:** The liquidity filter does N+1 API calls per scan
(one per ticker to fetch 20-day history). With 500 names and 8-way
parallelism, this is ~62s. For `run_screener` (run 2×/day) this is
negligible. For `run_momentum_screener` (run hourly), this is
~62s × 6.25 hours of trading = ~6.5 min of compute per day, which
is fine. The filter result is NOT cached across runs (today's traded
volume is the latest data point, so caching for 1 hour would be
safe but not necessary).

- [ ] **Step 6: Run the new tests to verify they pass**

```bash
cd ~/trading-sentinel/python-engine
source .venv/bin/activate
python -m pytest tests/test_universe_expansion.py -v
```

Expected: All 6 tests PASS (3 from Task 7 + 3 from Task 8: 2 for
swing + 1 for momentum).

- [ ] **Step 7: Run the full suite**

```bash
python -m pytest tests/ 2>&1 | tail -3
```

Expected: 358+ passed. No regressions.

- [ ] **Step 8: Commit**

```bash
cd ~/trading-sentinel
git add python-engine/main.py python-engine/tests/test_universe_expansion.py
git commit -m "feat(main): wire Nifty 500 fallback chain + liquidity filter into BOTH screeners

Replaces the silent NIFTY_100_TICKERS fallback with a 3-tier chain in
BOTH run_screener (L431) AND run_momentum_screener (L717):
1. CSV at UNIVERSE_PATH (operator-editable)
2. In-code NIFTY_500_TICKERS (hand-curated, ~500 entries)
3. RuntimeError with a clear message (no silent fallback)

The fallback chain is refactored into _load_universe_with_fallback()
to avoid duplication. The liquidity filter is called from both screeners
after the universe load, dropping tickers below the 20-day median ADV
floor before the scan loop. With UNIVERSE_MIN_ADV_CRORE=2.0 default,
we expect to keep ~400 of 500 names.

Cost analysis:
- run_screener: +62s liquidity filter (run 2x/day = +2 min/day)
- run_momentum_screener: +62s liquidity filter (run hourly = +6.5 min/day)
- Total: +8.5 min/day of API-bound compute, well within Kite's 3 req/s limit."
```

---

## Task 9: Operator runbook + change summary + branch-vs-desktop audit

**Files:**
- Create: `docs/runbooks/universe-expansion.md`
- Create: `docs/evolution/UNIVERSE_EXPANSION_CHANGES.md`
- Create: `docs/evolution/UNIVERSE_VS_DESKTOP_AUDIT.md`

- [ ] **Step 1: Write the operator runbook**

Create `docs/runbooks/universe-expansion.md` with this content:

```markdown
# Universe Expansion — Operator Runbook

**Audience:** Whoever is on-call when the scan behaves unexpectedly.
**Spec:** `docs/superpowers/specs/2026-06-15-universe-expansion-design.md`
**Plan:** `docs/superpowers/plans/2026-06-15-universe-expansion.md`

## What this feature does

Expands **BOTH** the swing and momentum screeners from Nifty 100 to
Nifty 500 (default), with a 20-day median ADV filter that drops the
bottom ~20% of names by traded value.

**Expected impact (per leg):**
- **Swing:** 15-25 signals/day (Nifty 100) → 40-80 signals/day (Nifty 500, ~20% filtered by liquidity)
- **Momentum:** 2-5 signals/day (Nifty 100) → 5-12 signals/day (Nifty 500, MC3-T/MC5/MC6 gates do most filtering)

**Cost impact:**
- `run_screener` (2×/day): +62s liquidity filter → +2 min/day
- `run_momentum_screener` (hourly): +62s liquidity filter → +6.5 min/day
- **Total: +8.5 min/day of API-bound compute, well within Kite's 3 req/s limit.**

## Quick diagnostics

### "Universe loaded from code" log line, not "from CSV"
The 3-tier fallback chain prefers the CSV at `UNIVERSE_PATH`, but
falls back to the in-code NIFTY_500_TICKERS list. The CSV is
`python-engine/data/nifty500.csv` and should be committed in the
repo. If you see "from code" in the log, the CSV is missing or
unreadable.

### "Liquidity filter dropped N" log line
This is informational. With defaults, expect ~100 names dropped
from 500. If more are dropped, the market may be unusually illiquid
(temporary — wait for the next scan) or your `UNIVERSE_MIN_ADV_CRORE`
is set too high (raise to keep more names).

### "universe_load_failed_all_paths" error
Both the CSV and the in-code list failed. Check:
1. Does `python-engine/data/nifty500.csv` exist?
2. Does `main.NIFTY_500_TICKERS` have ~500 entries?
3. Is the .env pointing `UNIVERSE_PATH` at a valid file?

## Feature flag reference

| Env var | Default | What it does |
|---------|---------|--------------|
| `UNIVERSE_SIZE` | `500` | Current size. Only 100 and 500 are supported in v1. |
| `UNIVERSE_TICKERS_FILE` | `nifty500.json` | Filename inside BREADTH_DATA_DIR (currently unused — the in-code list is the source of truth). |
| `UNIVERSE_MIN_ADV_CRORE` | `2.0` | Liquidity floor. Set to 0 to disable filtering entirely. |
| `UNIVERSE_LIQUIDITY_LOOKBACK_DAYS` | `20` | Lookback window for median ADV. |
| `BREADTH_UNIVERSE` | `NIFTY100` | Which universe Tier 1 breadth computes on. **NIFTY500 not supported in v1** — see spec DD1. |

## How to add or remove a ticker

1. Edit `python-engine/main.py` — find the `NIFTY_500_TICKERS` block.
2. Add or remove the symbol (NSE tradingsymbol format).
3. Mirror the change to `python-engine/data/nifty500.csv` and
   `python-engine/data/nifty500.json`.
4. Commit on `feat/universe-expansion` (or current branch).
5. Restart python-engine.

## Why is Tier 1 still on Nifty 100?

Tier 1 fetches 60-day history for 100 Nifty 100 stocks in ~25s. With
500 stocks, it'd take ~125s and exceed the 90s timeout. So Tier 1 is
**decoupled from the trading universe** — it stays on Nifty 100 (a
stable, liquid subset). The narrow-rally gate still works because it
uses engine-wide breadth (Nifty 100), not per-stock rank. For non-
Nifty-100 stocks, the breadth rank is None (treated as neutral).

## When to escalate

Open a high-priority ticket if:
- Signal count is 0 for 2+ hours after the change (universe is too
  small or filter is too aggressive)
- Liquidity filter is dropping >50% of names (the market may have
  changed; review the threshold)
- "universe_load_failed_all_paths" appears (no fallback path
  available — fix before market open)
```

- [ ] **Step 2: Write the change summary**

Create `docs/evolution/UNIVERSE_EXPANSION_CHANGES.md`. Follow the
format of `docs/evolution/BREADTH_ENRICHMENT_CHANGES.md`:

```markdown
# Universe Expansion — Change Summary
**Branch:** `feat/universe-expansion`
**Base:** `main`
**Status:** ✅ Implementation complete. Awaiting user merge.

---

## Overview

Expands **BOTH** the swing screener and the momentum screener from
100 Nifty 100 names to 500 Nifty 500 names (with a 20-day median ADV
filter that drops ~100 illiquid names). Expected impact: 3-5× more
swing signals + 3-5× more momentum signals.

## File map

### New files (3)

| File | Lines | Purpose |
|------|-------|---------|
| `python-engine/data/nifty500.json` | ~500 | 500 unique Nifty 500 tickers in the same format as `nifty100.json` |
| `python-engine/data/nifty500.csv` | ~500 | CSV mirror in `UNIVERSE_PATH` format (`tradingsymbol, exchange, sector`) |
| `python-engine/tests/test_universe_config.py` | ~25 | Tests for the 4 new config settings |
| `python-engine/tests/test_universe_expansion.py` | ~150 | Tests for the liquidity filter and Nifty 500 fallback chain |
| `docs/runbooks/universe-expansion.md` | ~100 | Operator runbook (diagnostics, flags, escalation) |
| `docs/evolution/UNIVERSE_EXPANSION_CHANGES.md` | ~250 | Change summary following the breadth-enrichment pattern |
| `docs/evolution/UNIVERSE_VS_DESKTOP_AUDIT.md` | ~150 | Branch-vs-desktop compatibility audit |

### Modified files (4)

| File | What changes | Lines added |
|------|-------------|-------------|
| `python-engine/config.py` | 4 new `UNIVERSE_*` settings (UNIVERSE_SIZE=500, UNIVERSE_TICKERS_FILE, UNIVERSE_MIN_ADV_CRORE=2.0, UNIVERSE_LIQUIDITY_LOOKBACK_DAYS=20) | +5 |
| `python-engine/universe.py` | `get_tokens()` (new, universe-agnostic) + `size` property; `get_nifty100_tokens()` kept as deprecated alias | +20 |
| `python-engine/breadth.py` | `BreadthEngine.__init__` reads `BREADTH_UNIVERSE` setting and logs on unknown values (DD4 dispatch) | +15 |
| `python-engine/main.py` | 3-tier universe fallback chain (CSV → in-code NIFTY_500_TICKERS → RuntimeError); `_filter_by_liquidity` helper; call into it before the scan loop; NIFTY_500_TICKERS constant block | +50 |

## Commit log

(Will be filled in by the engineer at the end of execution. Expected: 8 commits, one per task, plus a final docs commit.)

## Spec deviations

The implementation faithfully follows the spec, with one **documented
non-deviation**: the spec says Tier 1 stays on Nifty 100 (DD1) and the
implementation honours this. No surprise deviations.

## What was NOT changed

- `engine.py` — swing engine scoring logic is untouched. The breadth
  rank field accepts `None` for non-Nifty-100 names (treated as
  neutral by `build_breadth_kwargs`).
- The momentum screener — separate concern, separate spec. Not
  affected.
- Node Gateway, agent, DB schema, models.
- The NSE-blocking constraint: Nifty 500 list is hand-curated, not
  scraped.

## Cross-references

- **Spec:** `docs/superpowers/specs/2026-06-15-universe-expansion-design.md`
- **Plan:** `docs/superpowers/plans/2026-06-15-universe-expansion.md`
- **Runbook:** `docs/runbooks/universe-expansion.md`
- **Audit:** `docs/evolution/UNIVERSE_VS_DESKTOP_AUDIT.md`
- **Settings:** `python-engine/config.py` (UNIVERSE_* block)
- **Filter:** `python-engine/main.py` (`_filter_by_liquidity` helper)
- **Dispatch:** `python-engine/breadth.py` (BREADTH_UNIVERSE check in `__init__`)

After all 10 tasks are complete, the engineer should:
- Verify the commit count matches the spec's "8 commits" expectation
- Fill in the actual commit SHAs + one-line descriptions in the
  "Commit log" section above
- Verify the runbook's flag-reference table is accurate
- Run the full test suite one last time


- [ ] **Step 3: Write the branch-vs-desktop audit**

Create `docs/evolution/UNIVERSE_VS_DESKTOP_AUDIT.md` with a short
checklist verifying the diff is safe to merge into the running
Desktop. Follow the pattern of `docs/evolution/BREADTH_VS_DESKTOP_AUDIT.md`.

- [ ] **Step 4: Commit the docs**

```bash
cd ~/trading-sentinel
git add docs/runbooks/universe-expansion.md \
        docs/evolution/UNIVERSE_EXPANSION_CHANGES.md \
        docs/evolution/UNIVERSE_VS_DESKTOP_AUDIT.md
git commit -m "docs(universe): operator runbook + change summary + branch-vs-desktop audit"
```

---

## Task 10: Final state check + integrate with the existing branch

**Files:**
- Read-only inspection + final commit

- [ ] **Step 1: Verify working tree + commit count**

```bash
cd ~/trading-sentinel
git status
git log --oneline main..HEAD
```

Expected: 8+ commits ahead of `main` on `feat/universe-expansion`.
Working tree clean.

- [ ] **Step 2: Confirm full test suite green**

```bash
cd ~/trading-sentinel/python-engine
source .venv/bin/activate
python -m pytest tests/ 2>&1 | tail -3
```

Expected: 360+ passed. No regressions vs. pre-change baseline.

- [ ] **Step 3: Confirm feature defaults are safe**

```bash
cd ~/trading-sentinel
grep "UNIVERSE_SIZE\|UNIVERSE_MIN_ADV_CRORE\|BREADTH_UNIVERSE" python-engine/config.py
```

Expected: `UNIVERSE_SIZE = 500`, `UNIVERSE_MIN_ADV_CRORE = 2.0`,
`BREADTH_UNIVERSE = "NIFTY100"`. Defaults are safe (500 with ADV
filter is the new normal; 100 is the rollback).

- [ ] **Step 4: Decide on merge**

The user's "do not merge yet" preference from the breadth work
applies. **Do not auto-merge.** Leave on `feat/universe-expansion`
for user review.

- [ ] **Step 5: Update the memory**

After the user merges, update memory with:
- The new branch name + commit count
- The new settings (`UNIVERSE_SIZE=500`, etc.)
- The 4 design decisions (DD1-DD4) for next-session recall
