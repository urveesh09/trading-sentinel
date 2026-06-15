# Breadth Enrichment — Design Spec
**Date:** 2026-06-14
**Status:** Awaiting user approval
**Scope:** New `python-engine/breadth.py`, `python-engine/universe.py`; hooks in `python-engine/main.py`, `python-engine/engine.py`; feature flag in `python-engine/config.py`
**No changes to:** Node Gateway, Agent, regime.py core logic, DB schema, models.py, VIX-free regime engine, scan cadence, scheduler timing

---

## 1. Context & Root Cause

The system has no real market-breadth signal. The `breadth` field flowing into `RegimeEngine.update_regime()` is a Nifty-close-vs-EMA50 ratio mapped to a 0.30–0.70 band (see `main.py:295-301`) — a single-index proxy, not actual market participation.

The deep-research gap analysis (`trading-sentinel-evolution/deep-research-gap-analysis.md`, 2026-05-25) flagged this as **GAP 5**, severity Medium, effort Low, alpha impact Medium. The user (this session, 2026-06-14) chose to prioritise hardening over new alpha sources but also stated a hard constraint: **the system must not go to cash in every down market, and must keep finding uptrending stocks when the index is falling.**

The existing `MomentumGate` (spec `2026-05-11-momentum-gate-improvements-design.md`) already filters signal *quality*; breadth enrichment adds a *market-context* layer that is independent of the gate stack.

### What the system can already do
- Regime detection (VIX-free, ATR-compression + realized vol, R1/R2/R3) — works
- 13-factor composite signal scoring with regime scaling — works
- Stock-level RS vs Nifty in R3 (single-stock, no universe ranking) — works

### What the system cannot do
- Quantify how many stocks in the broader universe are participating in a move
- Rank stocks *relative to their peers* on a normalised participation axis
- Decide whether an R1 signal is set in a "narrow rally" or "broad rally" context
- Pick up counter-trend winners systematically during R2/R3

---

## 2. Goals

1. Compute **real market breadth** over a defined universe (Nifty 100, see §6.4) every scan cycle.
2. Use breadth as a **stock-level scoring input** (relative-strength rank), so the system surfaces winners in any regime — including R2/R3.
3. Add a **narrow R1 gate** that uses breadth to *restrict* R1 entries to leading stocks in a narrow rally, without going to cash.
4. Ship behind a **feature flag** for safe rollout and instant revert.

## 3. Non-Goals

- No new strategy types (no pairs, no market-neutral). Out of scope for hardening bucket.
- No ML / walk-forward validation. Hand-tuned thresholds with documented rationale.
- No replacement of the existing Nifty-EMA50 breadth proxy in `regime.py`. Both signals coexist.
- No options flow, no macro calendar, no CVD. Out of scope for this design.

---

## 4. Architecture (3 Layers)

### Layer 1 — Universe Management (NEW: `python-engine/universe.py`)

Defines and serves the breadth-eligible ticker list. Pure config + caching.

- **Source:** NSE Nifty 100 list, loaded from a static file `python-engine/data/nifty100.json` (committed). Nifty 100 covers ~80% of Nifty 500 breadth signal at 20% cost.
- **Refresh policy:** Static. List changes ~1-2 symbols per quarter. Update via PR.
- **Cache:** In-memory `set[str]` of instrument tokens, loaded once at process start. Refreshed only on instrument-cache invalidation (same hook the existing `kite_client.py` uses).
- **Why not Nifty 500?** Kite rate limit (3 req/s) + 500 historical fetches per scan cycle risks head-of-line blocking. Nifty 100 is the institutional standard (see gap analysis).

### Layer 2 — Breadth Computation (NEW: `python-engine/breadth.py`)

Computes breadth metrics and per-stock relative-strength rank.

**Inputs (per scan cycle):**
- Nifty 100 instrument tokens from `universe.py`
- For each token: 50-day daily close series (cached, refreshed daily)

**Outputs:**
- `breadth_pct_above_sma50` — float 0.0–1.0 (e.g. 0.42 = 42 of 100 stocks above their SMA50)
- `breadth_rank_map` — `dict[instrument_token, float 0.0–1.0]` where 1.0 = top of distribution

**Algorithm:**
```
for token in nifty100_universe:
    closes = kite.historical(token, period=60d, interval="day")
    sma50 = closes["close"].rolling(50).mean().iloc[-1]
    last_close = closes["close"].iloc[-1]
    distance_pct = (last_close - sma50) / sma50       # signed % above/below SMA50
    is_above = last_close > sma50

breadth_pct_above_sma50 = count(is_above) / len(universe)

# Rank by distance_pct (most above = top)
sorted_distances = sorted(all_distance_pcts)
for token, dist in zip(universe, all_distances):
    breadth_rank[token] = percentile_rank(dist, sorted_distances)
```

**Performance:**
- 100 tickers × 60-day daily history × 4 scans/hour = 400 fetches/hour
- At 3 req/s = ~2 min cumulative fetch time spread across scans. Acceptable.
- Use a **stale-while-revalidate cache**: if breadth was computed < 1 hour ago, return cached; otherwise recompute. Reduces live fetches to once per hour max.

**Failure handling:**
- If Kite historical fetch fails for >10% of universe, return `breadth_pct_above_sma50 = None` and an empty `breadth_rank_map`. Signal flag this as `breadth_data_degraded=True` in scan logs.
- Caller decides what to do with `None` (see §7.1).

### Layer 3 — Integration (MODIFIED: `python-engine/engine.py` + `python-engine/main.py`)

Three integration points, all gated by feature flag `BREADTH_ENRICHMENT_ENABLED`.

#### Integration Point A: Stock-level scoring bonus (always on when flag enabled)
- In `engine.py` signal scoring block (~line 430, after the existing 7 scoring factors), add:
  ```python
  if BREADTH_ENRICHMENT_ENABLED and breadth_rank is not None:
      if breadth_rank >= 0.80:    score += 15   # top 20% of universe
      elif breadth_rank >= 0.60:  score += 7    # top 40%
      elif breadth_rank < 0.20:   score -= 10   # bottom 20% (laggard penalty)
  ```
- This is the **counter-trend enabler**: in R2/R3, a stock in the top 20% of the breadth distribution still gets +15, keeping it in signal-eligible territory even when most stocks are below SMA50.

#### Integration Point B: R1 narrow-rally gate (R1 regime only)
- After score is finalised, if `regime == R1` and `breadth_pct_above_sma50 < 0.40`:
  - Hard-reject the signal **unless** `breadth_rank >= 0.80` (top quintile leader)
  - Log `narrow_rally_filtered=True` for diagnostics
- If `breadth_pct_above_sma50 is None` (degraded): skip the gate, allow the signal. Don't punish on missing data.

#### Integration Point C: Regime context visibility
- In `main.py` scan cycle, after computing breadth, attach to scan log:
  - `breadth_pct_above_sma50` (or `null`)
  - `breadth_data_degraded` boolean
  - Distribution histogram bucket counts (for trending) — optional, off by default

---

## 5. Components (File-Level)

| File | Action | Purpose |
|------|--------|---------|
| `python-engine/universe.py` | NEW | Nifty 100 ticker list loader + cache |
| `python-engine/data/nifty100.json` | NEW | Static Nifty 100 symbol/instrument list (committed) |
| `python-engine/breadth.py` | NEW | `BreadthEngine` class with `compute_breadth()` + `rank_breadth()` + stale-cache logic |
| `python-engine/tests/test_breadth.py` | NEW | Unit tests for breadth + rank logic (mocked Kite) |
| `python-engine/tests/test_universe.py` | NEW | Test universe loads, cache works |
| `python-engine/config.py` | MODIFY | Add `BREADTH_ENRICHMENT_ENABLED: bool = False` (default off for safe rollout) + thresholds |
| `python-engine/main.py` | MODIFY | Wire `BreadthEngine` into scan cycle, pass rank to `engine.py` |
| `python-engine/engine.py` | MODIFY | Integration Points A + B in signal scoring |
| `python-engine/tests/test_engine.py` | MODIFY | Test breadth-rank scoring + narrow-rally gate |
| `docs/runbooks/breadth-debug.md` | NEW | Operator guide: "breadth is None / degraded / what to check" |

---

## 6. Configuration

All new settings go in `python-engine/config.py`:

```python
# === Breadth Enrichment (2026-06-14) ===
BREADTH_ENRICHMENT_ENABLED:    bool  = False   # Feature flag — OFF by default
BREADTH_UNIVERSE:              str   = "NIFTY100"   # Reserved for future
BREADTH_CACHE_TTL_SECONDS:     int   = 3600    # 1h stale-while-revalidate
BREADTH_FETCH_TIMEOUT_SECONDS: int   = 90      # Max time to compute breadth
BREADTH_NARROW_RALLY_THRESHOLD: float = 0.40   # R1 gate fires below this
BREADTH_NARWAY_GATE_EXEMPT_RANK: float = 0.80  # Top quintile bypasses gate
BREADTH_RANK_BONUS_TOP:        int   = 15      # +15 if rank >= 0.80
BREADTH_RANK_BONUS_MID:        int   = 7       # +7 if rank >= 0.60
BREADTH_RANK_PENALTY_BOTTOM:   int   = -10     # -10 if rank < 0.20
BREADTH_DATA_DEGRADED_THRESHOLD: float = 0.10  # >10% fetch failures = degraded
```

### 6.4 Why Nifty 100 (recap)
- ~80% of Nifty 500's breadth signal at 20% of the Kite cost
- All 100 stocks are liquid; Kite historical fetches reliable
- Nifty 100 ≈ existing scan universe (Nifty 50 + Nifty Next 50) → coherent
- Gap analysis explicitly recommends Nifty 100 as "institutional middle ground"

---

## 7. Data Flow

### 7.1 Happy path (per scan cycle, every 15 min)

```
main.py scan tick
  └── breadth_engine.get_or_compute()              # cache hit → <10ms
        ├── (cache miss) compute_breadth()
        │     ├── universe.get_nifty100_tokens()  # ~1ms, in-memory
        │     ├── kite.historical(t, 60d, "day")   # parallel, 100 fetches
        │     ├── sma50 + distance_pct per token   # ~50ms numpy
        │     └── rank → breadth_rank_map          # ~5ms
        └── returns (breadth_pct, rank_map, degraded=False)
  └── engine.score_signal(stock_data, regime, breadth_rank=stock's rank)
        ├── Integration Point A: score += bonus
        └── Integration Point B: if R1 + narrow → maybe reject
  └── scan log records breadth_pct + degraded flag
```

### 7.2 Degraded path (Kite fetch failures)
- `BreadthEngine` returns `breadth_pct=None`, `rank_map={}`, `degraded=True`
- Integration Point A: scoring bonus skipped (rank missing)
- Integration Point B: narrow-rally gate **skipped** (allow the signal — don't punish on missing data)
- Scan log records `breadth_data_degraded=True` with reason
- Telegram warning sent once per day if degraded (debounced) — "Breadth data degraded, falling back to regime-only filters. Check Kite historical endpoint."

### 7.3 Feature flag off
- All breadth code paths early-return
- `engine.py` and `main.py` behave exactly as today
- Zero runtime cost

---

## 8. Error Handling

| Failure | Behaviour |
|---------|-----------|
| Kite rate-limit (429) on breadth fetch | Exponential backoff per token (1s, 2s, 4s, max 8s); if still failing, mark token as `None` and continue. Aggregate failure rate > 10% → degraded. |
| Kite historical returns empty data for a token | Treat as `None`, exclude from universe count, log token in `breadth_debug` |
| Nifty 100 JSON missing or malformed | `UniverseError` raised at startup — fail-fast, do not start engine |
| Stale cache (TTL expired, Kite unreachable) | Return last-good values with `breadth_data_stale=True` flag; surface in scan log |
| Scan time exceeds `BREADTH_FETCH_TIMEOUT_SECONDS` | Abort breadth compute, return degraded, do not block scan |
| Rank bonus produces score > 100 | Clamp to 100 (existing code does this at line 430) |

---

## 9. Testing Strategy

### 9.1 Unit tests (`test_breadth.py`)
- `compute_breadth` with synthetic universe: 60 stocks above SMA50, 40 below → returns 0.60
- `rank_breadth` with known distance_pct distribution → verify percentile mapping
- Cache TTL: first call fetches, second call within TTL returns cached
- Cache TTL expiry: mock time, verify refetch
- Degraded path: mock 15% Kite failures → returns `degraded=True`, `breadth_pct=None`

### 9.2 Unit tests (`test_universe.py`)
- Loads Nifty 100 JSON, verifies 100 tokens
- Cache hit on second call (no file re-read)
- Raises `UniverseError` on missing/malformed JSON

### 9.3 Engine integration tests (`test_engine.py` modifications)
- Score signal with `breadth_rank=0.85` (R1, healthy breadth) → +15 bonus applied
- Score signal with `breadth_rank=0.15` (R1, healthy breadth) → -10 penalty applied
- Score signal with `breadth_rank=None` → no bonus/penalty
- R1 narrow-rally: `breadth_pct=0.30, rank=0.50` → rejected with `narrow_rally_filtered=True`
- R1 narrow-rally: `breadth_pct=0.30, rank=0.90` → accepted (top quintile exempt)
- R1 narrow-rally: `breadth_pct=0.30, rank=None` (degraded) → accepted (skip gate)
- R2 narrow-rally: gate does NOT fire (R1 only)
- R3 narrow-rally: gate does NOT fire (R1 only)

### 9.4 Backtest validation (manual, not automated)
- Run `backtest.py` over 2023-06 to 2024-06 with `BREADTH_ENRICHMENT_ENABLED=False` (baseline) and `=True` (with breadth)
- Compare: total signals, win rate, R-multiple distribution
- Acceptance: win rate improvement ≥ 2pp OR R-multiple tail (P10) improvement ≥ 0.1R, with signal count reduction < 30% (i.e. we're tightening, not starving)

---

## 10. Rollout & Revert

### 10.1 Rollout stages
1. **Stage 0 (this PR):** Ship code with `BREADTH_ENRICHMENT_ENABLED=False`. Run for 1 week, verify `breadth.py` works in production by reading scan logs (degraded flag should be `False`).
2. **Stage 1:** Flip flag to `True` in `.env`. Run 1 week, monitor:
   - Signal count delta (expect 5-15% reduction from narrow-rally filter)
   - Win rate (expect 1-3pp improvement)
   - Breadth-data-degraded alerts (expect zero)
3. **Stage 2:** After 2 weeks of clean data, remove flag, make `True` the default in `config.py`. Keep `BREADTH_ENRICHMENT_ENABLED` as a config key but default it on.

### 10.2 Revert
- Set `BREADTH_ENRICHMENT_ENABLED=False` in `.env` and restart. Takes effect on next scan cycle.
- No code rollback needed. The flag is the kill switch.
- Old behaviour (Nifty-EMA50 proxy breadth, no rank, no gate) is preserved verbatim when flag is off.

---

## 11. Open Questions

1. **Should `breadth.py` also compute Nifty/BankNifty ratio distribution across the universe?** (The existing regime penalty uses a single Nifty/BankNifty close ratio; an "Nifty-BN ratio breadth" — % of stocks with NB ratio above 30th percentile — would be richer. Deferred — not in current design.)
2. **Should the breadth rank also feed `risk_engine.position_sizer`?** (Top-ranked stocks could get a size bump.) Deferred — would require extra risk-engine testing.
3. **Refresh cadence: should breadth recompute on every scan or hourly?** Design defaults to hourly via stale-while-revalidate. Will validate in Stage 1.

---

*Spec written by: Hermes (brainstorming session, 2026-06-14). Awaiting user review before proceeding to writing-plans skill.*
