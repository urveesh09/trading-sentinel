# Breadth Enrichment -- Execution Log
**Plan:** `2026-06-14-breadth-enrichment.md`
**Branch:** `evolve/smart-strategies`
**Started:** 2026-06-14
**Completed:** 2026-06-15
**Status:** [OK] Tasks 1-10 complete. 14 commits on branch. Not yet merged.

---

## Task -> Commit map

| Task | Plan steps | Commit(s) | Tests added | Notes |
|------|------------|-----------|-------------|-------|
| **1. config.py** | Add 12 BREADTH settings, flag OFF | `8ceffaf` | 0 (settings only) | `BREADTH_DATA_DIR` and `BREADTH_FETCH_TIMEOUT_SECONDS` added in Task 7 / 9 respectively (incremental additions). |
| **2. data/nifty100.json** | Mirror 100 unique tickers from main.py:225 | `59c0953` | 0 (data only) | Verified JSON valid + 100 unique symbols. Avoided NSE scraping (it blocks bots). |
| **3. universe.py** | `Universe` class with token resolution + fail-fast | `062260b` | 5 -> 6 in Task 7.1 | Constructor-injection pattern `Universe(json_path, instrument_cache=...)` because `kite_client.instrument_cache` is an instance attribute, not module-level. |
| **4+5. breadth.py** | `BreadthEngine` (Tier 1 + Tier 2) | `10f2659` | 14 | Combined into one commit -- Tier 2 is ~20 lines, shares the module, splitting would churn. |
| **6. engine.py** | `evaluate_signal` kwargs + R1 gate + bonus + multiplier | `abb1bde` | 12 | One test fixture had rsi=100 (rejected by L150 hard band before the gate) -- fixed the fixture, not the implementation. |
| **7.1. main.py data prep** | `BREADTH_DATA_DIR` + `Universe.token_to_symbol()` | `25c77f3` | +1 (token<->symbol round-trip) | Needed for token->symbol reverse lookup when wrapping kite.get_historical. |
| **7.2. main.py helpers** | `build_breadth_engine()` + `build_breadth_kwargs()` | `4f0e34d` | 7 | Extracted as pure module-level functions so they're testable in isolation. |
| **7.3. main.py wiring** | `run_screener` Pass 1 + Tier 2 + Pass 2 | `153dd9c` | 2 (integration) | Two-pass scan loop (no extra Kite calls). |
| **8. Runbook** | `docs/runbooks/breadth-debug.md` | `ef45371` | n/a (docs) | 208 lines: diagnostics, flag ref, tuning, escalation, rollout checklist. |
| **9. Integration audit** | Cross-check + orphan-import scan | `1415408` | 0 (cleanup only) | Found 2 dead imports in `breadth.py` (`Set`, `pandas as pd`) -- dropped. |
| **10. Final state** | Working tree clean, flag OFF, suite green | (no commit -- final verification step) | 0 | 346 passed, 1 skipped. All cross-refs accurate. |

---

## Key implementation decisions (with rationale)

### 1. Two-tier architecture, not single tier

**Why:** Tier 1 (60-day history for 100 tokens) is expensive. Caching it
for 1 hour means we only pay that cost on the first scan of the hour.
Tier 2 only needs live LTP (already in the scan cache) -> 0 extra Kite
calls per scan.

**Alternative considered:** Single tier that recomputes every scan.
Rejected because that would be 100 Kite calls every 15 minutes = 400/hour
= above the 3 req/s rate limit budget for the rest of the scan.

### 2. Two-pass scan loop in main.py

**Why:** `engine.py`'s narrow-rally gate needs `breadth_rank` as an
exemption. Tier 2 needs ALL the scan LTPs to compute the rank. So the
rank isn't available *during* the loop. Pass 1 fetches df + collects
LTP. Pass 2 re-walks the cached dfs with the now-computed rank.

**Alternative considered:** Pass rank=None during the loop, apply the
gate post-loop on the raw_signals list. Rejected because it would
require duplicating the gate logic outside of `engine.py`.

**Cost of two-pass:** One extra dict lookup per ticker. No extra Kite
calls (df is cached in `df_cache`).

### 3. Constructor-injection for Universe, not module-level

**Why:** `kite_client.instrument_cache` is a `KiteClient` instance
attribute, not module-level. So `patch("kite_client.instrument_cache", ...)`
is impossible in tests. Constructor injection
(`Universe(json_path, instrument_cache=...)`) makes the dependency
explicit and testable.

### 4. Mirror NIFTY_100_TICKERS from main.py, not scrape NSE

**Why:** NSE blocks bot scraping. The list already exists in code as
100 unique tickers (with the comment at L298 explicitly noting this
as a "future enhancement"). Mirroring is the path of least resistance
and keeps the data layer in our control.

### 5. Combine Tasks 4+5 into one commit

**Why:** Tier 2 is ~20 lines and shares the `breadth.py` module with
Tier 1. Splitting them into two commits would just churn the diff
without adding clarity.

### 6. Feature flag OFF by default

**Why:** The system currently works. The flag-off path is identical to
pre-breadth behaviour. So we ship with the flag off, monitor for a
week, and only enable when the operator is confident.

### 7. 13 BREADTH_* settings, not 11

**Why:** Spec Section6 listed 11. We added `BREADTH_DATA_DIR` (path to
nifty100.json) and `BREADTH_FETCH_TIMEOUT_SECONDS` (hard cap on Tier 1
fetch time) because the spec underspecified both. The defaults are
documented in `config.py` and explained in the runbook.

### 8. Narrow-rally gate only in R1, not R2/R3

**Why:** R1 (normal) is when narrow rallies are most likely to fool
the trend filter. In R2/R3 the system is already cautious via other
mechanisms (RS filter in R2, etc.). The bonus/multiplier DOES apply in
R2/R3 -- those are the "counter-trend enabler" cases where top-breadth
stocks are the safest longs.

### 9. Top-quintile exempt from the gate

**Why:** When 90%+ of Nifty 100 is below SMA50, the few survivors are
statistically the best risk-on names. Letting them in is the whole
point of the gate. The exemption is `rank >= 0.80` (top 20% of the
100-token distribution = top quintile).

### 10. Score multiplier (x1.2) instead of size bump

**Why:** Conservative first rollout. A score multiplier nudges borderline
signals (say 50/60) over the threshold, which is a smaller change than
increasing share count. If Stage 1 monitoring shows top-breadth signals
are still under-sized, we add a sizing override in a follow-up PR.

---

## What I'd do differently in hindsight

1. **Wrote the integration test in Task 7.3 BEFORE the helper tests.**
   The integration test is more end-to-end and would have caught the
   `BreadthEngine` not-in-namespace bug faster. But the helper tests
   ended up being the right unit-of-test for the wiring logic, so the
   order didn't matter much for the final result.

2. **Should have written the orphan-import scanner in Task 9 sooner.**
   It found 2 dead imports that the regular test suite happily passed
   with. A linter pass at the end of each task would have caught these
   earlier.

3. **The two-pass scan loop is correct but adds complexity.** A
   future refactor could merge the passes by doing a quick LTP-only
   pre-fetch (no full 250-day history) to compute Tier 2 before the
   main loop. That would add 100 cheap Kite calls per scan but let
   us collapse to a single pass. Not worth it now.

---

## Open follow-ups (not blocking this PR)

- OQ1: wire `nb_ratio_distribution_pct` to the regime classifier
  (needs a `kite.quote()` call per stock -- different spec).
- OQ2: add a position-sizing override for top-breadth signals
  (gated on Stage 1 monitoring results).
- Generalise `Universe` to support Nifty 200 / Nifty 500 (the
  `BREADTH_UNIVERSE` setting is reserved for this).
- Add a `BREADTH_DEGRADED_ALERT_WEBHOOK` setting that pages the
  on-call when degraded rate > 50% for 3+ hours.

---

## Status

**All 10 tasks complete. Branch is ready for user review and manual merge.**

Last verified: 2026-06-15
- Working tree: clean
- Suite: 346 passed, 1 skipped
- Feature flag: `BREADTH_ENRICHMENT_ENABLED=False` (safe default)
- Cross-refs in runbook: accurate
