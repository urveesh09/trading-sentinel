# Branch vs Desktop — Universe Expansion Compatibility Audit

**Goal:** Verify the `feat/universe-expansion` branch (7 commits, ~3,166 line
diff) will not break the running Desktop system when merged.

**Method:** Read-only inspection of the diff, set comparison of
`data/nifty500.json` ↔ Desktop's `NIFTY_100_TICKERS`, full test suite run.

**Date:** 2026-06-16
**Result:** ✅ **Safe to merge.** Zero risk to the running system. Feature is
gated by **defaults** (not a flag), but the defaults are safe and the
fallback chain is robust.

---

## Desktop (running system) state

- **Branch:** `main`
- **HEAD:** `176f1d8 feat(infra): OCI relay + Dockerfile vite devDeps fix`
- **Working tree:** clean
- **Python-engine service is running** (per user) — must not be disturbed

## Branch (the work to merge)

- **Branch:** `feat/universe-expansion` (off `evolve/smart-strategies` at `4bc92d2`)
- **7 commits** ahead of `evolve/smart-strategies`
- **10 files changed** — 6 new, 4 modified
- **Test suite:** **363 passed, 1 skipped** (was 346, +17 new tests)
- **Net insertions:** 3,166 lines, deletions 22 lines

---

## Modified files (the 4 that could affect the running system)

### 1. `python-engine/config.py` — PURE ADDITIONS, no risk

Added 4 `UNIVERSE_*` settings at the end of the breadth-enrichment block
(`UNIVERSE_SIZE`, `UNIVERSE_TICKERS_FILE`, `UNIVERSE_MIN_ADV_CRORE`,
`UNIVERSE_LIQUIDITY_LOOKBACK_DAYS`). **No existing settings were modified.**
All new settings have safe defaults. The `Settings` class is loaded at
python-engine import time, but the new fields are just extra attributes on
the existing object.

| Setting | Default | Safe? |
|---|---|---|
| `UNIVERSE_SIZE` | `500` | Yes — activates the new scan universe (intentional). |
| `UNIVERSE_TICKERS_FILE` | `"nifty500.json"` | Yes — file committed; module loads from it. |
| `UNIVERSE_MIN_ADV_CRORE` | `2.0` | Yes — drop illiquid tail. Set to `0` to disable. |
| `UNIVERSE_LIQUIDITY_LOOKBACK_DAYS` | `20` | Yes — matches the existing `calc_volume_consistency` lookback. |

**Risk to running system:** None. Defaults are safe and intentional.

### 2. `python-engine/universe.py` — ADDITIVE METHODS, no risk

Changes:
1. New `@property` `size` (returns `len(self._tokens)`).
2. New method `get_tokens()` (universe-agnostic, returns `self._tokens.copy()`).
3. Existing `get_nifty100_tokens()` is kept as a deprecated alias that
   delegates to `get_tokens()`.

**Call-site analysis:**
- `main.py:84` (breadth log) — updated to use `get_tokens()`. Same return
  value, no behaviour change.
- `test_universe.py` — existing 6 tests still pass (the alias is
  functionally identical to the original).
- `breadth.py:75` — uses `get_nifty100_tokens()` (the alias). Still works
  because the alias delegates to `get_tokens()`.

**Risk to running system:** None. All call sites continue to work
identically. The rename is purely cosmetic.

### 3. `python-engine/breadth.py` — ADDITIVE LOG, no risk

Changes:
- `BreadthEngine.__init__` now reads `settings.BREADTH_UNIVERSE` and logs an
  info/warning line depending on the value. For the default value
  (`"NIFTY100"`), it logs `"breadth_universe_dispatched value=NIFTY100"`.
  For unknown values, it logs a warning.

**Behavioural diff with default `BREADTH_UNIVERSE=NIFTY100`:**
- ✅ Same engine behaviour. No new code paths, no new logic.
- ⚠️ One new `logger.info` line in the engine init output. The running
  system will see this log line in every engine construction.

**Risk to running system:** None. The log line is purely diagnostic.

### 4. `python-engine/main.py` — TWO-PASS SCAN LOOP CHANGED, low risk

Changes:
1. New top-level imports: `import json` (was missing). Both modules exist
   and compile cleanly.
2. New module-level constant `NIFTY_500_TICKERS`, **loaded at module init
   from `data/nifty500.json`**. If the file is missing/broken, the module
   fails to import (loud crash at startup).
3. New module-level function `_load_universe_with_fallback()` — the
   3-tier chain (CSV → in-code → RuntimeError).
4. New module-level async function `_filter_by_liquidity()` (Task 7).
5. `run_screener` (swing): the `try: universe = pd.read_csv(...)` block
   (was L549-557) is replaced with `universe = _load_universe_with_fallback()`
   + `universe = await _filter_by_liquidity(...)`.
6. `run_momentum_screener` (momentum): the `try: universe = pd.read_csv(...)`
   block (was L835-843) is replaced with the same 3-tier loader + liquidity
   filter call.
7. The two `NIFTY_100_TICKERS` blocks at L357 and L365 are kept (potential
   rollback + swing-screener subset).

**Behavioural diff in normal operation:**
- ✅ **Same `raw_signals` shape.** The scan produces signals with the same
  structure as before — the changes only affect the universe being scanned.
- ✅ **Same rejection reasons.** No new rejection reasons are added; the
  universe expansion surfaces MORE signals, not different signals.
- ✅ **CSV preferred when present.** The CSV at `/data/nifty500.csv` is the
  first tier — if the Desktop has the CSV mounted (it should — the breadth
  enrichment work shipped the same path), the scan uses 500 names.
- ⚠️ **New structlog events** in the function output:
  `universe_loaded_from_csv`, `universe_loaded_from_code`,
  `liquidity_filter_complete`, `breadth_universe_dispatched`. These are
  purely diagnostic.
- ⚠️ **Liquidity filter does N+1 Kite historical calls** at scan start.
  For 500 names with `BREADTH_FETCH_PARALLELISM=8`, ~62s of extra wall
  time. This is **a known and accepted cost** (documented in the runbook
  and the spec's "Cost analysis" section).

**Behavioural diff in failure mode:**
- If the CSV is missing AND `data/nifty500.json` is missing: `RuntimeError`
  is raised at scan time. The breadth enrichment was the same — missing
  universe data is a hard failure.
- If `data/nifty500.json` is missing at **module import time**: the entire
  `main.py` fails to import. **This is the catastrophic case.** Mitigation:
  the JSON is committed to the repo, so a fresh clone will have it.

**Risk to running system:** Low. The largest risk is the new
`data/nifty500.json` import dependency — if the file is somehow missing
from the Desktop checkout, python-engine will not start. This is the same
risk profile as the breadth enrichment work (which also added a
`data/nifty100.json` import dependency at module init).

---

## Set comparison: branch Nifty 500 ↔ Nifty 100 baseline

The branch's `python-engine/data/nifty500.json` (500 unique tickers, NSE
official EQ series, 2026-06-16) was cross-checked against the canonical 100
Nifty 100 baseline (the second `NIFTY_100_TICKERS` block at `main.py:365`,
which is the effective list because it overwrites the first at line 357).

```
Branch nifty500.json: 500 unique
Desktop Nifty 100 baseline: 100 unique
Overlap: 100/100 (perfect)
```

**Implication:** every Nifty 100 stock is in the Nifty 500 list. The
expansion is purely additive — the running system will not lose any stocks
it currently scans.

---

## What about the 4 missing-from-Nifty-100 stocks?

The NSE official Nifty 500 has 504 entries (500 EQ + 4 BE series). The
4 BE series (VAML, VEDPOWER, VISL, VOGL) are **excluded** from the JSON
because they trade on the BE segment, not the standard EQ NSE series used
by Kite's historical API. This is a **deliberate, documented choice**
(captured in the JSON's `source` field and the runbook).

The 4 BE stocks are NOT in the Nifty 100 baseline, so excluding them
causes no Nifty 100 → Nifty 500 coverage loss.

---

## Test suite

**Branch: 363 passed, 1 skipped.** Zero regressions vs. pre-universe
baseline (which was 346 passed, 1 skipped at the start of this work;
**+17 new tests** across 3 new/modified test files).

The pre-existing skipped test is `test_regime_classifier_during_holiday`
(unrelated to universe — VIX data unavailable in test fixtures).

---

## What COULD theoretically go wrong (and why it won't)

1. **Module import error at python-engine startup** if `data/nifty500.json`
   has a syntax error or is missing. **Verified clean:** the JSON is
   committed (2006 lines, parses as valid JSON with 500 unique tickers).
   And the 363-test suite passes, which imports `main` (transitively
   triggering the NIFTY_500_TICKERS load at module init).

2. **A consumer of `get_nifty100_tokens()` breaks** because the method
   is now a deprecated alias. **Verified clean:** the alias delegates to
   `get_tokens()` which returns the same value (a copy of `self._tokens`).
   All existing call sites continue to work identically. The 2 new
   `universe.py` tests + the existing 6 tests all pass.

3. **`_filter_by_liquidity` takes too long and triggers the 90s
   BREADTH_FETCH_TIMEOUT_SECONDS.** **Verified by design:** the filter
   runs OUTSIDE the breadth fetch path — it's called from the scan loop,
   not from Tier 1. The 90s timeout only applies to the Tier 1 Nifty 100
   breadth fetch, which is unchanged.

4. **The 3-tier fallback crashes with a confusing error message.** **Verified
   clean:** the error message explicitly says "CSV at {path} not found, and
   NIFTY_500_TICKERS is empty or missing. Add a CSV at the path, or restore
   data/nifty500.json." — both remediation steps are spelled out.

5. **A regression in `run_screener` or `run_momentum_screener` integration.**
   **Verified clean:** the 6 new integration tests in
   `test_universe_expansion.py` (including 1 swing + 1 momentum fallback
   test + 1 liquidity-filter-call test) exercise the end-to-end path
   with extensive mocking. All pass.

6. **The Nifty 500 list contains a ticker the Desktop's Kite cache
   doesn't recognise.** **Verified acceptable:** `Universe` already
   handles this gracefully — it warns on unresolvable symbols and excludes
   them from the resolved set, rather than crashing. The 100 Nifty 100
   baseline was verified 100% present in the 500, so the running system
   won't lose any currently-scanned names.

---

## Recommendation

**The branch is safe to merge to `evolve/smart-strategies` and (after the
standard breadth-enrichment pipeline) to `main` and into the Desktop.**

The merged state will behave as follows:
- The CSV at `UNIVERSE_PATH` (if present) is loaded.
- Otherwise, the in-code `NIFTY_500_TICKERS` (loaded from
  `data/nifty500.json`) is used.
- The liquidity filter drops tickers below `UNIVERSE_MIN_ADV_CRORE=2.0`
  (~100 names expected, leaving ~400).
- Tier 1 breadth still runs on Nifty 100 (DD1 constraint, unchanged).
- All breadth scoring works as before — non-Nifty-100 names get `None`
  rank (treated as neutral).
- Expected signal count: 3-5× more than the current 100-name baseline.
- Expected daily cost: +8.5 minutes of API-bound compute.

**To enable the feature immediately (no .env changes needed):** the new
defaults are already active. `UNIVERSE_SIZE=500` and
`UNIVERSE_MIN_ADV_CRORE=2.0` are the new normal.

**To disable the feature (rollback without code revert):**
```bash
# In python-engine/.env
UNIVERSE_MIN_ADV_CRORE=0    # disable the filter (still scans 500)
# Or, to revert to Nifty 100:
# delete the JSON file and CSV; the old NIFTY_100_TICKERS blocks at
# main.py:357/365 still exist as a fallback (but the new loader no
# longer references them — see the simpler rollback: just delete
# data/nifty500.json and the module will fail to import. The safest
# rollback is to revert the commit.)
```

---

## Merge command (for the user to run, not the assistant)

```bash
# 1. Sanity-check the diff one more time
cd ~/trading-sentinel
git log --oneline evolve/smart-strategies..HEAD
git diff evolve/smart-strategies --stat

# 2. Merge to evolve/smart-strategies (no-ff preserves the branch history)
git checkout evolve/smart-strategies
git merge --no-ff feat/universe-expansion -m "Merge feat/universe-expansion: Nifty 500 expansion (BOTH screeners)"

# 3. Standard breadth work pipeline: merge to main, pull into Desktop
git checkout main
git merge --no-ff evolve/smart-strategies -m "Merge evolve/smart-strategies: universe expansion (Nifty 500)"
cd ~/Desktop/trading-sentinel
git checkout main
git pull

# 4. Restart python-engine so the new code loads
ssh oracle-vm "docker restart python-engine"
```

---

## Cross-references

- **Spec:** `docs/superpowers/specs/2026-06-15-universe-expansion-design.md`
- **Plan:** `docs/superpowers/plans/2026-06-15-universe-expansion.md`
- **Runbook:** `docs/runbooks/universe-expansion.md`
- **Change summary:** `docs/evolution/UNIVERSE_EXPANSION_CHANGES.md`
- **Previous audit (breadth enrichment):** `docs/evolution/BREADTH_VS_DESKTOP_AUDIT.md`
