# N012-A2 results: N012-A stays as frozen; no better neighbour, and its gain sits next to a cliff

Frozen at `4c8d607` before any arm was run. 135 annual replays (27 arms × 5 seen NIFTY windows), ₹2,50,000 fresh each window, N11T entries and costs unchanged. In every window the centre arm reproduced Round 30's `TREND_ONLY` exactly (net, counts, drawdown, worst day, daily nets). `score.py` reproduced N012-A's +₹4,051.45 and +₹710.38 after its five best days. Full table: `results.json`.

## Verdict (frozen five-check rule)

**N012-A is the best of the 27 arms on all five windows, and it stays the candidate with its own numbers.** The search fails out of fold: −₹4,240.59 against N012-A's +₹4,051.45.

| Check | Result |
|---|---|
| 1. The search's held-out sum beats N012-A | **FAIL**: −₹4,240.59. With 2026 held out, the search picks T 0.75, which loses ₹6,887.49 in 2026. |
| 2. After the five best days, the pick beats N012-A | FAIL. The pick is N012-A itself (₹710.38). |
| 3. Worst day and drawdown no worse | pass (−₹5,640.85, 6.97%) |
| 4. No window below −₹2,500 | pass |
| 5. Grid neighbours positive on average | pass, barely: neighbours +4,051, +4,051, +1,868, −5,712, +3,390, −3,725 |

## What the grid shows

| Increment over N11T | Jun–Dec 2022 | 2023 | 2024 | 2025 | Jan–Oct 2026 | Total |
|---|---:|---:|---:|---:|---:|---:|
| **N012-A** (A 0.65, T 0.60) | +305 | +405 | 0 | +1,937 | +1,405 | **+4,051** |
| Trail lock off (A 0.65, T OFF) | +305 | +230 | 0 | +1,450 | +1,405 | +3,390 |
| Gentler (A 0.55, T 0.60) | 0 | +405 | 0 | +924 | +538 | +1,868 |
| Gentlest (A 0.55, T OFF) | 0 | +230 | 0 | +438 | +538 | +1,207 |
| Tighter on adverse (A 0.75) | +305 | +405 | 0 | +1,937 | −8,359 | −5,712 |
| Tighter trail lock (T 0.75) | +305 | +405 | 0 | +2,452 | −6,887 | −3,725 |
| Both tighter (A 0.75, T 0.75) | +305 | +405 | 0 | +2,452 | −16,651 | −13,489 |

- **The SUPPORT keep does nothing.** At 0.25, 0.35 and 0.45 every trade in every window is identical. When the trend supports the trade, the option is near its best, so the lock's floor is not reached there. N012-A in practice is "keep more of the gain once the 5-minute trend turns against the trade".
- **Tightening helps a little, and more tightening hurts a lot.** All 12 arms at A ≤ 0.65 and T ≤ 0.60 are positive, and none loses money in any window. Every arm at A 0.75 or T 0.75 loses in 2026, between ₹6,887 and ₹16,651. 2026 is the most recent window and the closest to today's market. N012-A sits at the last good step before that cliff.
- **12 of 27 arms beat N11T.** The gentlest version (A 0.55, trail lock off) never loses in a window but adds only ₹1,207 in total.

## What this means for the deploy

N012-A is deployed with its frozen numbers (S 0.35, A 0.65, T 0.60; `fno_trend_lock.py`, `FNO_TREND_LOCK_ENABLED`). The rule says to keep it, and every rejected direction is worse. It is not qualified. The gain is small (+1.5%), it is in-sample, and one step tighter loses money on 2026.

The live loop looks every 10 seconds, against one look a minute in this replay. The adverse condition (two falling 5-minute buckets, and the price at or under the last bucket close) can therefore be met at more looks than replayed. That is the same cadence gap the native lock has, and its 8-second confirmation still applies.

Forward paper is the only fresh evidence. The new SENSEX months cannot replay the book (zero OI on every minute; see PLAN.md). The NIFTY January–May 2022 exam stays sealed.

## Verification

- `freeze.json` source hashes were checked at every run, and so was `round1.verify_freeze()` (data manifests and the N11/N11T control hashes).
- The centre arm equals Round 30 in all five windows. All runs finished with zero unresolved positions.
- Runtime parity: `python-engine/tests/test_fno_trend_lock.py` loads this rule's research source. The engine `Trend` matched it on random walks at 10-second and 60-second looks, and `trend_params` matched it on every status, lock and trail combination. One engine-loop test holds a supported give-back that the native lock sells.
