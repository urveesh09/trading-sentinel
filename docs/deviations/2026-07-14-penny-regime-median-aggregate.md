# Deviation 2026-07-14: penny regime aggregate is the MEDIAN, not the max (spec §6.2 is wrong)

**Spec reference:** penny spec §6.2 — *"the highest per-stock realized vol rank
across the universe"* is the day's aggregate (worst-case-wins, for safety).

**Where:** `python-engine/penny_regime.py` (`update_vol_rank`,
`_aggregate_vol_rank`), `python-engine/penny_scanner.py` (both feed sites),
`python-engine/config.py` (`PENNY_RISK_PCT_PR3`),
`python-engine/tests/test_penny_audit_phase2_fixes.py`
(`TestVolRankWorstCaseWins` → `TestVolRankMedianAggregate`).

**Status:** implemented on `feat/alpha-tier0`. Not yet deployed.

## The spec's rule is not conservative — it is an unconditional shutdown

Spec §6.2 aggregates the per-stock vol ranks by taking the **maximum** across the
universe. The implementation went further and made it a **monotonic ratchet**:

```python
def update_vol_rank(self, ticker_vol_rank: float) -> None:
    if self._vol_rank is None or ticker_vol_rank > self._vol_rank:
        self._vol_rank = ticker_vol_rank      # only ever goes UP
```

The arithmetic makes PR3 unavoidable. This is deterministic, not bad luck:

1. `compute_vol_rank()` is **not** a cross-sectional rank. It is `sd / 0.10`,
   **saturating at exactly 1.0** for any stock with ≥ 10% daily realized vol
   (`penny_regime.py`, the `if sd >= 0.10: return 1.0` branch).
2. Penny stocks routinely clear 10% daily vol. In any 100-name penny universe,
   **several names return exactly 1.0 every single day**.
3. Therefore `max(...)` over the universe is ≈ 1.0 within minutes of the first
   scan — every day, without exception.
4. `classify()` returns `PR3_HOT` at `vol_rank >= 0.90`.
5. `PENNY_RISK_PCT_PR3 = 0.0` meant PR3 sized every position at **0 shares**, so
   every candidate was rejected.

And because the aggregate only ratcheted upward, it could never recover within
the day even if the tape calmed down.

## What it cost

- **0 accepts in 349,297 lifetime evaluations** of the penny MIS breakout leg.
- **93.4%** of a typical day's rejects (35,096 of 37,556 on 2026-07-14) read
  `regime PR3_HOT (no new entries)`.
- The penny Connors leg: 0 accepts in 240 evaluations.

Two of the four strategy families have never taken a single trade.

This is the same failure *shape* as the `day_high` anchor bug
(`docs/penny-prod-bugs-2026-07-10.md`): a gate that cannot be satisfied by any
market state, sitting quietly in production and looking like "no setups today".

Note the immediate cause was a *previous fix*. Roadmap 3.6 (2026-07-12) added
`bars_per_day=375` scaling to `compute_vol_rank` because the unscaled 1-minute
stdev produced `vol_rank ≈ 0` for every ticker — the input was dead weight. That
fix was correct in isolation, but it is what pushed the saturating max-aggregate
over the PR3 line permanently.

## The deviation

**Aggregate by median, recomputed from the current cross-section on every scan.**

```python
self._vol_ranks[ticker] = ticker_vol_rank          # keyed, overwrites
self._vol_rank = statistics.median(self._vol_ranks.values())
```

The regime should describe **the market**, not its single worst member. The
median can also **cool down**, which the ratchet could not.

Ranks are keyed by ticker so a re-scan of the same name *overwrites* its previous
reading. Unkeyed, every 30-second scan tick would append another sample and the
median would drift with scan count rather than track the market.

**And PR3 now throttles instead of killing:** `PENNY_RISK_PCT_PR3` `0.0 → 0.01`.

A 0-size regime is not merely conservative, it is **unfalsifiable**: it can never
produce an accept, so no watchdog, backtest or A/B test can ever tell you whether
PR3 was the right call. A hot tape should be traded *small*, not *not at all*.
This also restores the falsifiability invariant the repo already enforces for
every F&O gate.

## Why not just raise the PR3 threshold instead?

Because the aggregate would still be ≈ 1.0 every day. Any threshold below 1.0
fires; a threshold at 1.0 makes PR3 unreachable instead of permanent. Either way
the *input* carries no information once it is a max over a saturating score. The
aggregation is the bug, not the cutoff.

## Safety argument

The spec's intent — *don't trade full size into a hot tape* — is preserved:

- A genuinely hot tape moves the **median**, not just the max, so PR3 still fires
  when the universe as a whole is volatile.
- PR3 still cuts size to 1% (from 5% in PR1), a 5× reduction.
- The per-stock circuit-band, sector, event and liquidity gates are untouched.
- `PENNY_PER_STOCK_CAP`, the daily kill switch and the position caps are untouched.

What changes is that **one** hot stock can no longer silence the other 99.

## Verification

- `TestVolRankMedianAggregate` — median aggregate, one-hot-stock-cannot-hijack,
  regime-can-cool-down, rescan-overwrites-not-appends.
- The decisive test is **an accept**: run the scanner over a trading day and
  assert `accepts > 0`. A gate that has never once fired is not a strategy.
- Follow-up (roadmap 0.5): the zero-accept watchdog *was* scheduled and stayed
  silent through all 349,297 evaluations. Fixing the gate does not fix the alarm
  that failed to report it.
