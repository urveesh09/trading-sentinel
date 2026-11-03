# SENSEX signal source: front future or index? (research, Nov 3)

**Question.** SENSEX futures trade thinly: a median of 8 contracts per 5-minute bar on Nov 2. The partner cards and
the paper book both read the SENSEX future's 5-minute prices. Would the index give better signals?

**Data.** The Breeze minute history (`sentinel-operations/breeze-history-20261029/data/breeze-history.sqlite`),
opened read-only, Dec 2025 to Oct 28, 2026 (seen data; no 2023 rows read). The front future is the nearest
expiry each day. Bars are 09:15–15:25.

**How far the future's close strays from the index** (index + the day's median basis), 225 days:

| | SENSEX | NIFTY (contrast) |
| --- | --- | --- |
| futures contracts per 5-min bar, median | 11 | 668 |
| gap, median (points) | 20.3 | 4.9 |
| gap, p90 / p99 (points) | 54 / 109 | 14 / 34 |
| gap > ½ index ATR(14) | 26% of bars | 18% |
| gap > 1 index ATR | 6% | 3.8% |
| 5-min move correlation, future vs index | 0.79 | 0.90 |

**Signal replay.** The shipped momentum engine (`evaluate_fno_mom`) runs from 09:50 to 14:45 on two inputs:
- (a) the front future's bars;
- (b) the index bars plus the basis measured 09:15–09:45 that day (known by the first decision).

Both use NIFTY futures volume for RVOL, as the book does. The first signal of each direction per day is
compared over 210 days. Follow-through is measured on the index, which the options track, signed in the
signal's direction.

| First signals | n | index move +30 m (mean / median) | +60 m (mean / median) | share up at +60 m |
| --- | --- | --- | --- | --- |
| both, at the future's time | 100 | +14.3 / +16.1 | +18.2 / +3.7 | 52% |
| future only | 28 | −5.7 / +8.2 | −24.7 / −18.5 | 44% |
| index only | 26 | −41.8 / −42.2 | −60.6 / −95.8 | 28% |

**Reading.**
- The source changes about a third of the signals.
- The signals only the index would add are the worst group.
- Switching SENSEX to index bars is **not** supported. The future's price stays the signal source, matching
  the shipped book and its research.
- The samples are small and this is follow-through, not option P&L, so nothing here is a new rule.
- The fix that is supported, and is made (N05-S1): partner SENSEX cards now measure participation on NIFTY
  futures, as the book does. Before, they used SENSEX's own thin volume.

Files:
- `sensex_basis.py` and `nifty_basis.py` (the gap table);
- `sensex_signal_replay.py` (the replay and follow-through);
- `signal_replay_results.txt`.
