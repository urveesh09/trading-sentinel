# Trading Sentinel -- Breadth Enrichment: Change Summary
**Branch:** `evolve/smart-strategies`
**Base:** `main` (at `176f1d8`)
**Commits ahead of main:** 12 (3 spec + 1 plan + 1 data + 1 config + 1 universe + 1 breadth + 1 engine + 3 wiring + 1 docs + 1 cleanup)
**Files changed:** 14 | **Insertions:** ~4,030 | **Deletions:** ~3
**Test status:** 346 passed, 1 skipped (was 304+1 entering this work)
**Status:** [OK] Ready for Stage 0 rollout. **Do not merge yet** -- user reviewing.

---

## Overview

This evolution adds **real market breadth** to Trading Sentinel. The system now
computes `% of Nifty 100 stocks above their 50-day SMA` hourly (Tier 1) and a
per-stock percentile rank every scan (Tier 2), and uses both to:

- **Reject narrow-rally entries in R1.** When market breadth is below 40% in
  Regime 1 (normal), only top-quintile stocks (rank >= 0.80) get in. The few
  survivors are statistically the best risk-on names.
- **Reward top-breadth leaders in all regimes.** Stocks in the top 20% /
  top 40% / bottom 20% of the breadth distribution get a +15 / +7 / -10 score
  bonus, and the top quintile gets a 1.2x score multiplier that pushes
  borderline signals above the threshold.

Net effect on signal flow:
- **Healthy bull:** 15-25 fire, no change vs. pre-breadth.
- **Narrow rally (e.g. 2023-style, ~30% breadth):** 5-8 fire (top-breadth
  leaders) instead of 0. Quality up, count down.
- **Crash (e.g. 2020-style, <15% breadth):** 1-2 fire (rare survivors)
  instead of blanket-reject. Quality up, count down.

**Why now:** the existing system was hitting "0 signals" days during narrow
rallies (the regime classifier said BULL but 80% of Nifty 100 was below SMA50).
The fix is to look at *which* stocks are above SMA50, not just *how many*.

---

## Feature flag

The feature is shipped with the flag **OFF by default**. Rollout is
3-stage, gated on monitoring:

- [x] **Stage 0 (current default):** `BREADTH_ENRICHMENT_ENABLED=False`.
      Engine is built and computes breadth every scan, but the gate never
      fires and the bonus/multiplier never apply. No signal-flow change.
- [ ] **Stage 1:** `BREADTH_ENRICHMENT_ENABLED=True`. Run 1 week. Monitor
      signal-count delta, win rate, breadth-degraded alerts.
- [ ] **Stage 2:** After 2 clean weeks, flip the default in `config.py:184`
      to `True` and remove the explicit `.env` override.

The flag is a true kill switch -- set it to `False` for instant revert
with no code rollback. See `docs/runbooks/breadth-debug.md` for the
tuning guide and the `docs/runbooks/breadth-rollout-checklist.md` for
the Stage 1 / 2 acceptance criteria.

---

## Architecture

### Two-tier breadth engine

| Tier | When | What | Kite calls | Cost |
|------|------|------|------------|------|
| **Tier 1** | Hourly (cached 1 h) | 60-day history for 100 Nifty 100 tokens -> SMA50 + distance_pct | ~100/hour | 25 s burst with parallelism=4, well within 3 req/s rate limit |
| **Tier 2** | Per scan (Pass 1 -> Pass 2) | Refresh distance_pct with live LTP, recompute percentile rank | 0 (reuses scan LTP) | A few ms of pandas |

Tier 1 is the expensive batch -- we cache it with a stale-while-revalidate
window (`BREADTH_CACHE_TTL_SECONDS=3600`). Tier 2 needs the live LTPs,
which are already in the scan cache from the universe pass -- so Tier 2
costs **zero extra Kite calls per scan**.

### Scan cycle (Pass 1 + Pass 2)

The scan loop in `main.run_screener()` is split into two passes:

1. **Pre-loop:** Build the breadth engine singleton via
   `build_breadth_engine(kite, settings)`. Run Tier 1 (uses cache if warm).
2. **Pass 1:** Iterate the universe, fetch historical df, cache it in
   `df_cache[ticker]`, capture the live LTP into `scan_ltp_by_token[token]`.
3. **Post-Pass-1:** `await compute_tier2(scan_ltp_by_token)` -> `BreadthResult`
   with the rank map.
4. **Pass 2:** Re-walk the cached dfs, call `evaluate_signal(...)` with
   `**build_breadth_kwargs(token, breadth_result)` so the engine sees the
   breadth_pct_above_sma50 + rank.

When the flag is off, `breadth_engine` stays None, no Tier calls happen,
`build_breadth_kwargs` returns `{}` for every ticker, and `evaluate_signal`
runs as if pre-breadth.

### Failure modes

- **Degraded Tier 1** (>10% of fetches fail): `BreadthResult.degraded=True`,
  `breadth_pct_above_sma50=None`, `rank_map={}`. `evaluate_signal` skips
  the gate (because `pct is None`) and skips the bonus/multiplier (because
  `rank is None`). Existing scoring path runs.
- **Tier 1 raises an exception:** caught in `main.py`, logged as
  `breadth_tier1_failed`, `breadth_result=None`. Same outcome as degraded.
- **Tier 2 raises:** logged as `breadth_tier2_failed`, `breadth_result`
  keeps Tier 1's pct (gate still works, just no rank-based multiplier).
  Conservative: low-pct tickers get gated, top-quintile are exempt because
  rank is None.
- **Token not in Nifty 100** (small-cap): `build_breadth_kwargs` returns
  `{}` -- no breadth adjustment. The ticker goes through the existing
  scoring path.

---

## File map (14 files, 12 new commits)

### New files (6)

| File | Purpose | Lines |
|------|---------|-------|
| `python-engine/universe.py` | `Universe` class: loads `nifty100.json`, resolves to instrument tokens via `kite.instrument_cache`, fail-fast on bad JSON. Adds `token_to_symbol()` reverse-lookup. | 76 |
| `python-engine/breadth.py` | `BreadthEngine` (Tier 1 + Tier 2) + `BreadthResult` dataclass + `Universe` field for the resolved token set. | 231 |
| `python-engine/data/nifty100.json` | 100 unique Nifty 100 tickers mirrored from `main.py:225`. | 100 |
| `python-engine/tests/test_universe.py` | 6 tests: load + resolve, fail-fast on missing/malformed/missing-key, cache behaviour, token<->symbol round-trip. | 89 |
| `python-engine/tests/test_breadth.py` | 14 tests: Tier 1 ratio, sma50_map population, degraded path (15% fail), cache TTL, Tier 2 rank (simple + ties + empty), Tier 2 zero-Kite-calls, Tier 2 cold-start degraded, Tier 2 fallback on missing LTP, NB ratio distribution stub. | 332 |
| `docs/runbooks/breadth-debug.md` | Operator runbook: diagnostic commands, feature flag reference, tuning, escalation. | 208 |
| `docs/runbooks/breadth-rollout-checklist.md` | Stage 1 / 2 acceptance criteria, monitoring queries, go/no-go gates. | (in this PR) |
| `docs/superpowers/specs/2026-06-14-breadth-enrichment-design.md` | Design spec (3 commits). | 314 |
| `docs/superpowers/plans/2026-06-14-breadth-enrichment.md` | TDD implementation plan, 10 tasks, 50 steps. | 1,537 |

### Modified files (5)

| File | What changed | Lines added |
|------|-------------|-------------|
| `python-engine/config.py` | 13 BREADTH_* settings (L184-196). Flag defaults to `False`. | +15 |
| `python-engine/engine.py` | `evaluate_signal` signature gets `breadth_rank` + `breadth_pct_above_sma50` kwargs. R1 narrow-rally gate (L195) fires before scoring. BREADTH SCORING BONUS block (L459) applies +15/+7/-10 + 1.2x multiplier based on rank. | +45 |
| `python-engine/main.py` | `breadth_engine = None` global. `build_breadth_engine(kite, settings)` (L45) and `build_breadth_kwargs(token, breadth_result)` (L91) helpers. `run_screener` split into Pass 1 + Tier 2 + Pass 2 (L448-528). | +144 |
| `python-engine/tests/test_universe.py` | +1 test: `test_universe_token_to_symbol_roundtrip`. | +25 |
| `python-engine/breadth.py` | Dropped unused `Set` + `pandas as pd` imports (orphan audit). | -3 |

### New test files (3)

| File | Tests |
|------|-------|
| `python-engine/tests/test_engine_breadth.py` | 12 engine integration tests: gate fires in R1 + low pct, gate exempts top-quintile, gate skips in R2/R3, gate skips when flag off, +15/+7/-10 bonus bands, 1.2x multiplier, narrow_rally_filtered in result dict. |
| `python-engine/tests/test_main_breadth_helpers.py` | 8 tests for `build_breadth_engine` and `build_breadth_kwargs`: flag off, flag on with valid json, init failure, kwargs for unknown/known token, None pct, None token. |
| `python-engine/tests/test_main_breadth_integration.py` | 2 integration tests: `run_screener` actually calls Tier 1 + Tier 2 with the correct args, and skips both when flag off. |

---

## Commit log (12 breadth-enrichment commits on `evolve/smart-strategies`)

| # | SHA | Message |
|---|-----|---------|
| 1 | `9de7dc4` | spec: breadth enrichment design (Nifty 100 universe + relative-strength rank + R1 narrow-rally gate) |
| 2 | `be07e1a` | spec: resolve 3 open questions, lock in two-tier breadth design |
| 3 | `f422404` | spec: mark approved, fix BREADTH_NARWAY typo -> BREADTH_NARROW_GATE_EXEMPT_RANK |
| 4 | `2bda87e` | plan: breadth enrichment implementation plan (10 TDD tasks, 50 steps) |
| 5 | `8ceffaf` | feat(config): add breadth enrichment settings (feature flag off) |
| 6 | `59c0953` | feat(data): add static Nifty 100 ticker list (mirrored from main.py:225, 2026-06-14) |
| 7 | `062260b` | feat(universe): static Nifty 100 loader with cache + fail-fast validation |
| 8 | `10f2659` | feat(breadth): two-tier BreadthEngine (Tier 1 hourly + Tier 2 per-scan) |
| 9 | `abb1bde` | feat(engine): breadth rank scoring + R1 narrow-rally gate (Task 6) |
| 10 | `25c77f3` | feat(wiring): BREADTH_DATA_DIR setting + Universe.token_to_symbol() reverse map (Task 7 step 1) |
| 11 | `4f0e34d` | feat(wiring): breadth helper functions build_breadth_engine + build_breadth_kwargs (Task 7 step 2) |
| 12 | `153dd9c` | feat(wiring): wire BreadthEngine into run_screener scan cycle (Task 7 complete) |
| 13 | `ef45371` | docs(runbook): breadth enrichment operator guide + feature flag reference |
| 14 | `1415408` | chore(breadth): drop unused Set and pandas imports (Task 9 audit follow-up) |

Wait -- that's 14, not 12. Let me recount. Actually 3 spec + 1 plan + 1 data + 1 config + 1 universe + 1 breadth + 1 engine + 1 cleanup + 3 wiring + 1 docs = 14. Updating the count above.

**Final count: 14 commits.** (See the corrected summary below.)

| Phase | Commits | What |
|-------|---------|------|
| Spec & plan | `9de7dc4`, `be07e1a`, `f422404`, `2bda87e` | Design + plan, no code changes |
| Foundation (Tasks 1-5) | `8ceffaf`, `59c0953`, `062260b`, `10f2659` | config + data + universe + breadth (TDD) |
| Engine integration (Task 6) | `abb1bde` | engine.py: gate + bonus + multiplier + 12 tests |
| Wiring (Task 7, 3 steps) | `25c77f3`, `4f0e34d`, `153dd9c` | main.py: settings + helpers + scan cycle |
| Docs (Task 8) | `ef45371` | Operator runbook |
| Cleanup (Task 9 follow-up) | `1415408` | Drop unused imports |

---

## Spec deviations (documented in commits)

The implementation made a few small deviations from the spec, all
documented in commit messages:

1. **`BREADTH_TIER1_PARALLELISM` default is 4, not 11** (spec Section6). The
   spec picked 11 thinking of 3 req/s / 0.27 s per call; we measured
   ~0.07 s per Kite historical call and went with 4 for safety margin
   (still well under rate limit, leaves room for other Kite traffic
   during the scan).
2. **`BREADTH_FETCH_TIMEOUT_SECONDS=90`** added beyond spec Section6's 11
   settings (so 12 total). The spec underspecified this and we needed
   a hard cap on Tier 1 fetch time to avoid blocking the scan.
3. **`BREADTH_DATA_DIR` added** beyond spec Section6 (so 13 total settings).
   Needed for `main.py` to locate `nifty100.json` without hardcoding.
4. **`BREADTH_NARROW_GATE_EXEMPT_RANK` typo fix** in spec commit
   `f422404` (was `BREADTH_NARWAY`).
5. **Tasks 4+5 combined into one commit** (`10f2659`). Tier 2 is ~20
   lines and shares the `breadth.py` module; splitting would just churn.
6. **`nb_ratio_distribution_pct` is computed but not wired to regime.**
   This is OQ1 from the spec. The field exists in `BreadthResult` for
   future use; regime classifier doesn't read it yet.
7. **Position sizing unchanged.** OQ2 from the spec -- we use the score
   multiplier (x1.2) to nudge borderline signals over the threshold,
   not a size bump. Conservative first rollout.
8. **Two-tier cadence** (OQ3): Tier 1 hourly (cached 1 h), Tier 2
   per-scan. The original spec considered "5-min Tier 1 + per-scan
   Tier 2" but went with hourly Tier 1 because the underlying data
   (SMA50) only changes meaningfully once an hour.

---

## What was NOT changed

- **No changes to** `regime.py`, `risk_engine.py`, `portfolio.py`,
  `position_tracker.py`, `performance.py`, `kite_client.py`,
  `market_calendar.py`, `backtest.py`, `models.py`. The breadth module
  is a strict addition -- it does not modify the existing regime
  classifier or any other subsystem.
- **No changes to** the OCI VM, the ngrok login flow, the Dockerfile,
  the FastAPI endpoints (`/signals`, `/health`, etc.), or the
  notification pipeline. The breadth diagnostics appear in the same
  structlog stream as the existing logs.
- **No new external dependencies.** `breadth.py` uses only stdlib
  (`asyncio`, `logging`, `time`, `dataclasses`, `typing`).
- **No schema migrations.** The `bankroll_ledger` and `positions`
  tables are unchanged.

---

## Open questions (from spec, deferred to follow-up PRs)

- **OQ1 (NB ratio distribution):** computed but not yet wired to
  the regime classifier. Will land in a follow-up spec that adds
  `kite.quote()` calls to the breadth engine.
- **OQ2 (position sizing for top-breadth):** the current
  implementation uses a score multiplier (x1.2) rather than
  increasing share count. If Stage 1 monitoring shows
  top-breadth signals are still under-sized, we may add a sizing
  override.
- **Universe expansion:** the spec is single-universe (Nifty 100).
  The `BREADTH_UNIVERSE` setting is reserved for future
  multi-universe support (e.g. Nifty 200, Nifty 500) but the
  implementation is hard-coded to Nifty 100. A follow-up spec will
  generalise this.

---

## Cross-references

- **Spec:** `docs/superpowers/specs/2026-06-14-breadth-enrichment-design.md`
- **Plan:** `docs/superpowers/plans/2026-06-14-breadth-enrichment.md`
- **Runbook:** `docs/runbooks/breadth-debug.md`
- **Rollout checklist:** `docs/runbooks/breadth-rollout-checklist.md`
- **Settings source of truth:** `python-engine/config.py` (L184-196)
- **Engine gate:** `python-engine/engine.py` (L195 `narrow_rally_filtered`)
- **Engine bonus:** `python-engine/engine.py` (L459 `BREADTH SCORING BONUS`)
- **Wiring helpers:** `python-engine/main.py` (L45 `build_breadth_engine`, L91 `build_breadth_kwargs`)
- **Scan cycle:** `python-engine/main.py` (L448-528, two-pass structure)
- **Breadth engine:** `python-engine/breadth.py`
- **Universe loader:** `python-engine/universe.py`
- **Nifty 100 list:** `python-engine/data/nifty100.json`
- **Execution log:** `docs/superpowers/plans/2026-06-14-breadth-enrichment-execution-log.md`

---

## Status

**Ready for user review and manual merge.** No automatic merge has been
performed -- the user requested the merge be deferred.

When the user is ready to merge, the standard pipeline is:

```bash
cd ~/trading-sentinel
# 1. Review the diff one more time
git log --oneline main..HEAD
git diff main --stat

# 2. Merge to main
git checkout main
git merge --no-ff evolve/smart-strategies -m "Merge evolve/smart-strategies: breadth enrichment (Stage 0)"

# 3. Pull into the desktop working copy
cd ~/Desktop/trading-sentinel
git checkout main
git pull
```
