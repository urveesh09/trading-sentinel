# Universe Expansion — Change Summary

**Branch:** `feat/universe-expansion`
**Base:** `evolve/smart-strategies` (at `4bc92d2`)
**Status:** ✅ Implementation complete. Awaiting user review and merge.

---

## Overview

Expands **BOTH** the swing and momentum screeners from 100 Nifty 100 names to
500 Nifty 500 names (with a 20-day median ADV filter that drops ~100 illiquid
names). Expected impact: 3-5× more swing signals + 3-5× more momentum
signals.

**Tier 1 (breadth) is NOT expanded** — it stays on Nifty 100 due to the 90s
fetch timeout constraint (DD1 in the spec). This is a **documented design
decision**, not a missing feature. See `docs/runbooks/universe-expansion.md`
for the rationale.

---

## File map

### New files (8)

| File | Lines | Purpose |
|------|-------|---------|
| `python-engine/data/nifty500.json` | ~2,000 | 500 unique Nifty 500 tickers (NSE official EQ series, 2026-06-16). Source of truth for the in-code fallback. |
| `python-engine/data/nifty500.csv` | ~500 | CSV mirror in `UNIVERSE_PATH` format (`tradingsymbol, exchange, sector`). All `sector=UNKNOWN` (DD3 — real sector data deferred). |
| `python-engine/tests/test_universe_config.py` | 25 | Tests for the 4 new `UNIVERSE_*` config settings. |
| `python-engine/tests/test_universe_expansion.py` | 350 | Tests for the liquidity filter + Nifty 500 fallback chain + BOTH `run_screener` and `run_momentum_screener` integration. |
| `docs/runbooks/universe-expansion.md` | 200 | Operator runbook (diagnostics, flags, escalation, rollback). |
| `docs/evolution/UNIVERSE_EXPANSION_CHANGES.md` | (this file) | Change summary following the breadth-enrichment pattern. |
| `docs/evolution/UNIVERSE_VS_DESKTOP_AUDIT.md` | 150 | Branch-vs-desktop compatibility audit. |

### Modified files (4)

| File | What changes | Lines added |
|------|-------------|-------------|
| `python-engine/config.py` | 4 new `UNIVERSE_*` settings (UNIVERSE_SIZE=500, UNIVERSE_TICKERS_FILE, UNIVERSE_MIN_ADV_CRORE=2.0, UNIVERSE_LIQUIDITY_LOOKBACK_DAYS=20). No existing settings modified. | +5 |
| `python-engine/universe.py` | New `get_tokens()` (universe-agnostic) + `size` property; `get_nifty100_tokens()` kept as deprecated alias. | +30 |
| `python-engine/breadth.py` | `BreadthEngine.__init__` reads `BREADTH_UNIVERSE` setting and logs on unknown values (DD4 dispatch). Uses stdlib logging format (not structlog, which the plan's example assumed). | +20 |
| `python-engine/main.py` | NIFTY_500_TICKERS constant (loaded from JSON at module init); `_load_universe_with_fallback()` helper; call into it from BOTH `run_screener` and `run_momentum_screener`; `_filter_by_liquidity` call from BOTH sites after universe load. The two `NIFTY_100_TICKERS` blocks at L357 and L365 are kept (potential rollback + swing-screener subset). | +130 |

---

## Commit log

8 commits on `feat/universe-expansion` ahead of `evolve/smart-strategies`:

| SHA | Type | Description |
|-----|------|-------------|
| `4e72073` | feat(data) | Add static Nifty 500 ticker list (NSE official EQ series, 2026-06-16) |
| `ea8c5f0` | feat(data) | Add Nifty 500 CSV mirror (UNIVERSE_PATH format, sector=UNKNOWN) |
| `ad92406` | feat(config) | Add universe-expansion settings (size, tickers file, ADV floor, lookback) |
| `06ede99` | refactor(universe) | Rename `get_nifty100_tokens` to `get_tokens` + add `size` property + deprecated alias |
| `5543b65` | feat(breadth) | Wire `BREADTH_UNIVERSE` setting through `BreadthEngine` (DD4 dispatch) |
| `05eb5a6` | feat(main) | Add `_filter_by_liquidity` helper (20-day median ADV floor, DD2) |
| `acd08c8` | feat(main) | Wire Nifty 500 fallback chain + liquidity filter into BOTH screeners |
| (this commit) | docs(universe) | Operator runbook + change summary + branch-vs-desktop audit |

Total: 8 commits, 0 spec deviations, 0 spec surprises.

---

## Design decisions (from spec, all honoured)

- **DD1: Tier 1 (breadth) stays on Nifty 100.** Decoupled from scan universe.
  Non-Nifty-100 stocks get `None` rank (treated as neutral). Implemented and
  documented in `breadth.py` BREADTH_UNIVERSE dispatch + runbook.
- **DD2: Liquidity filter = drop bottom 20% by 20-day median traded value.**
  Implemented in `_filter_by_liquidity` (main.py). Default
  `UNIVERSE_MIN_ADV_CRORE=2.0` keeps ~400 of 500 names.
- **DD3: Sector data deferred.** All sectors in `nifty500.csv` are `UNKNOWN`
  (matching the existing Nifty 100 CSV behavior). Documented as a follow-up PR.
- **DD4: `BREADTH_UNIVERSE` setting is the dispatch source of truth.**
  Implemented in `breadth.py` BreadthEngine.__init__. v1 only supports
  `NIFTY100`; other values log a warning and the engine continues with the
  caller-provided universe.

---

## Spec deviations

**None.** The implementation faithfully follows the spec.

**Minor stylistic deviation (called out in the breadth.py commit message, not
a behaviour change):** the spec's `breadth.py` BREADTH_UNIVERSE dispatch
example used structlog-style kwargs (`logger.warning("event", key=value)`).
`breadth.py` uses stdlib `logging`, not structlog. The dispatch logging was
adapted to stdlib format (`logger.warning("event value=%s", value)`). This is
semantically equivalent and matches the rest of the file's logging style.

---

## What was NOT changed

- `engine.py` — swing engine scoring logic is untouched. The breadth
  rank field accepts `None` for non-Nifty-100 names (treated as neutral by
  `build_breadth_kwargs`).
- Node Gateway, agent, DB schema, models.
- The NSE-blocking constraint: Nifty 500 list is hand-curated from the
  official NSE archives CSV (downloaded once, not scraped).
- The two `NIFTY_100_TICKERS` blocks in `main.py` (L357 and L365) — kept for
  potential rollback and as the source of truth for the swing-screener
  subset (L357). They are no longer used in the fallback chain.

---

## Test count progression

| Milestone | Pass | Delta | Notes |
|-----------|------|-------|-------|
| Baseline (pre-universe-expansion) | 346 | — | After breadth enrichment work. |
| + 4 new config tests (Task 4) | 350 | +4 | |
| + 2 new universe tests (Task 5) | 352 | +2 | |
| + 2 new breadth tests (Task 6) | 354 | +2 | |
| + 3 new liquidity tests (Task 7) | 357 | +3 | |
| + 6 new fallback/screener tests (Task 8) | **363** | +6 | **+17 net, no regressions** |

Plan target was 360+. We're 3 over. Zero pre-existing tests modified or
deleted.

---

## Cross-references

- **Spec:** `docs/superpowers/specs/2026-06-15-universe-expansion-design.md`
- **Plan:** `docs/superpowers/plans/2026-06-15-universe-expansion.md`
- **Runbook:** `docs/runbooks/universe-expansion.md`
- **Audit:** `docs/evolution/UNIVERSE_VS_DESKTOP_AUDIT.md`
- **Settings:** `python-engine/config.py` (UNIVERSE_* block)
- **Filter:** `python-engine/main.py` (`_filter_by_liquidity` helper)
- **Fallback loader:** `python-engine/main.py` (`_load_universe_with_fallback`)
- **Dispatch:** `python-engine/breadth.py` (BREADTH_UNIVERSE check in `__init__`)

---

## Recommended next steps (for the user)

1. **Review the runbook + audit** (`docs/runbooks/universe-expansion.md` and
   `docs/evolution/UNIVERSE_VS_DESKTOP_AUDIT.md`) — these are the operational
   artifacts.
2. **Sanity-check the diff:** `git diff evolve/smart-strategies --stat` in
   `~/trading-sentinel`.
3. **Decide on merge:** the branch is on `feat/universe-expansion`. Per the
   user's "do not merge yet" preference (carried over from the breadth work),
   **do not auto-merge**. Leave for user review.
4. **After merge to `evolve/smart-strategies`:** standard breadth work
   pipeline applies — merge to `main`, pull into `~/Desktop/trading-sentinel`,
   restart python-engine.
5. **After pull into Desktop:** monitor the 2 swing scans + 6 momentum scans
   in Stage 0. The new defaults (`UNIVERSE_SIZE=500`, `UNIVERSE_MIN_ADV_CRORE=2.0`)
   are safe — they activate the expansion without any further config.
