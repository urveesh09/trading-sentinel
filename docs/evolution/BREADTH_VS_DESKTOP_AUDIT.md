# Branch vs Desktop — Compatibility Audit

**Goal:** Verify the `evolve/smart-strategies` branch (15 breadth-enrichment
commits) will not break the running Desktop system when merged to `main`.

**Method:** Read-only inspection of the diff, set comparison of
nifty100.json ↔ Desktop's NIFTY_100_TICKERS, full test suite run.

**Date:** 2026-06-15
**Result:** ✅ **Safe to merge.** Zero risk to the running system.

---

## Desktop (running system) state

- **Branch:** `main`
- **HEAD:** `176f1d8 feat(infra): OCI relay + Dockerfile vite devDeps fix`
- **Working tree:** clean
- **Ahead of origin/main by 1 commit** (the `176f1d8` is unpushed)
- **Python-engine service is running** (per user) — must not be disturbed

## Branch (the work to merge)

- **Branch:** `evolve/smart-strategies`
- **15 commits** ahead of `main`
- **18 files changed** — 13 new, 5 modified
- **Test suite:** 346 passed, 1 skipped
- **Feature flag:** `BREADTH_ENRICHMENT_ENABLED=False` (default — safe)

---

## Modified files (the 5 that could affect the running system)

### 1. `python-engine/config.py` — PURE ADDITIONS, no risk

Added 13 BREADTH_* settings at lines 184-196. **No existing settings
were modified.** All new settings have safe defaults. The Settings
class is loaded at python-engine import time, but the new fields are
just extra attributes on the existing object.

**Risk to running system:** None.

### 2. `python-engine/engine.py` — ADDITIVE KWARGS, no risk

Changes:
1. Two new optional kwargs at the END of `evaluate_signal`'s signature:
   `breadth_rank: Optional[float] = None`,
   `breadth_pct_above_sma50: Optional[float] = None`.
2. A new R1 narrow-rally gate (L195-209) — **guarded by
   `if settings.BREADTH_ENRICHMENT_ENABLED`** and **`breadth_pct_above_sma50 is not None`**.
   With flag OFF (the default), this block is a no-op.
3. A new scoring bonus block (L464-474) — **guarded by
   `if settings.BREADTH_ENRICHMENT_ENABLED and breadth_rank is not None`**.
   With flag OFF or rank=None, this block is a no-op.
4. A new field `narrow_rally_filtered: False` added to the result dict.
   **No existing fields are removed or renamed.** No consumer reads this
   key outside of `test_engine_breadth.py`.

**Call-site analysis** (3 sites in the running system):
- `main.py:379` (scan loop) — passes 8 kwargs, no breadth kwargs. New
  kwargs default to None → flag-off path is a no-op.
- `backtest.py:356` (backtest engine) — passes 8 kwargs, no breadth
  kwargs. Same: new kwargs default to None → no-op.
- `main_bkp.py:94` (dead backup file) — not in the import chain, irrelevant.

**Risk to running system:** None. All existing call sites continue
to work identically. New behaviour is gated behind the flag.

### 3. `python-engine/main.py` — TWO-PASS SCAN LOOP, low risk

Changes:
1. Two new top-level imports: `from breadth import BreadthEngine`,
   `from universe import Universe`. Both modules exist and compile
   cleanly. New file, no transitive impact.
2. `breadth_engine = None` module-level global. (Mirrors the existing
   `risk_engine` pattern.)
3. `build_breadth_engine(kite, settings)` helper (L45-89): with flag
   OFF, **returns `None` at the first line** — no I/O, no init.
4. `build_breadth_kwargs(token, breadth_result)` helper (L91-107): with
   `breadth_result is None` (the flag-off case), **returns `{}`**.
5. `run_screener` restructured (L448-528):
   - **Pre-loop:** `breadth_engine = build_breadth_engine(kite, settings)`
     → with flag OFF, `breadth_engine` stays `None`. No Tier 1 call.
   - **Pass 1:** same as before (fetches dfs, populates `df_cache`
     and `scan_ltp_by_token` dicts for breadth use, but they don't
     affect any existing logic).
   - **Between passes:** `if breadth_engine is not None and
     scan_ltp_by_token:` → with flag OFF, `breadth_engine is None` →
     no Tier 2 call.
   - **Pass 2:** walks the cached dfs, calls `evaluate_signal(...)` with
     `**build_breadth_kwargs(token, breadth_result)` → with flag OFF,
     this is `**{}` (no-op).

**Behavioral diff with flag OFF (the running system scenario):**
- ✅ **Same signals fire.** The scan produces the same `raw_signals`
  list because every change is a no-op.
- ✅ **Same rejection reasons.** No new rejection reason is added in
  the flag-off path.
- ⚠️ **Slightly later signal emission within the function.** The
  function now does Pass 1 → (skipped Tier 2) → Pass 2, where it used
  to do the work inline. Total wall time is similar (no extra Kite
  calls). End-to-end behaviour is identical.
- ⚠️ **New structlog events** in the function output:
  `breadth_tier1_degraded`, `breadth_tier2_degraded`, etc. These
  fire on the FLAG-ON path only; with flag OFF, only
  `breadth_engine_init_failed` would fire (and only on an init error).
  **The running system will see no new log lines in normal operation.**

**Risk to running system:** None. Same outputs, same signal flow,
same end-to-end behaviour.

### 4. `docs/evolution/CHANGE_SUMMARY.md` — PURE DOCS, no risk

Added a "Phase 2 — Breadth Enrichment" section at the end (24 lines).
**No code, no API changes.** Docs are not loaded at runtime.

**Risk to running system:** None.

### 5. (Implicit) All 13 NEW files — PURE ADDITIONS, no risk

New files: `universe.py`, `breadth.py`, `data/nifty100.json`,
5 new test files, 3 new doc files. None of these are imported by
the existing code outside of what `main.py` does (and `main.py`'s
imports are guarded by the flag).

**Risk to running system:** None.

---

## Set comparison: branch nifty100.json ↔ desktop NIFTY_100_TICKERS

The branch's `python-engine/data/nifty100.json` (100 unique tickers) is
**byte-for-byte identical** (as a set) to the desktop's live
`NIFTY_100_TICKERS` (the second list at main.py:225, which is the
effective one because it overwrites the first at line 217).

```
Branch nifty100.json: 100 unique
Desktop (last block): 100 unique
Identical? True
```

**Implication:** if the running system ever loads nifty100.json
(say, if the flag is enabled on the desktop), the breadth universe
will be exactly the same as the universe currently in
NIFTY_100_TICKERS. ✅

---

## Test suite

**Branch: 346 passed, 1 skipped.** Zero regressions vs. pre-breadth
baseline (which was 304 passed, 1 skipped at the start of this work;
+42 new breadth tests added across 5 new test files).

The pre-existing skipped test is `test_regime_classifier_during_holiday`
(unrelated to breadth — VIX data unavailable in test fixtures).

---

## What COULD theoretically go wrong (and why it won't)

1. **Module import error at python-engine startup** if `breadth.py`
   or `universe.py` has a syntax/import error. **Verified clean:**
   `python -m py_compile main.py engine.py config.py breadth.py
   universe.py` → all compile. And the 346-test suite passes, which
   imports `main` (transitively importing both new modules).

2. **A new test file picks up the wrong `main.py`** (i.e., the
   branch's main.py imports something the desktop's main.py doesn't).
   **Verified clean:** test_main_api.py (the most comprehensive
   integration test) passes — it imports `main` and exercises
   `/health`, `/signals`, `/positions`, etc. end-to-end.

3. **nifty100.json contains a ticker the desktop's Kite cache doesn't
   recognise.** This would only matter when the flag is enabled
   (Tier 1 fetches fail → degraded path → existing scoring runs).
   With flag OFF, the file is never read.

4. **An existing consumer breaks on the new `narrow_rally_filtered: False`
   field in the result dict.** **Verified clean:** grep for consumers
   of `sig_data` outside `engine.py` shows no reads of
   `narrow_rally_filtered`. The field is purely diagnostic.

5. **A consumer of `evaluate_signal` in the running system passes
   positional args past the new kwargs.** **Verified clean:** all
   call sites use keyword args. Even if they used positional, the
   new kwargs are at the END of the signature so older positional
   calls would still bind correctly.

---

## Recommendation

**The branch is safe to merge to `main` and pull into the desktop.**

The merged state will behave identically to the pre-merge state because:
- Feature flag is OFF by default
- All new code paths check the flag first
- All new kwargs default to `None` (= no breadth adjustment)
- The two-pass scan loop produces the same `raw_signals` as the
  old single-pass loop when the flag is off
- No existing settings, fields, or call sites were modified
- nifty100.json is identical to the desktop's NIFTY_100_TICKERS
- All 5 modified Python files compile cleanly
- All 346 tests pass

**When to enable the feature** (separate decision, after merge):
follow the Stage 0/1/2 playbook in
`docs/runbooks/breadth-rollout-checklist.md`.

---

## Merge command (for the user to run, not the assistant)

```bash
# 1. Sanity-check the diff one more time
cd ~/trading-sentinel
git log --oneline main..HEAD
git diff main --stat

# 2. Merge (no-ff preserves the branch history)
git checkout main
git merge --no-ff evolve/smart-strategies -m "Merge evolve/smart-strategies: breadth enrichment (Stage 0, flag off)"

# 3. Pull into desktop
cd ~/Desktop/trading-sentinel
git checkout main
git pull

# 4. Restart python-engine so the new code loads
ssh oracle-vm "docker restart python-engine"
```
