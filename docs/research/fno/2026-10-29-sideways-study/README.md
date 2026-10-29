# O29i: what works on the days the trend gate sits out (sideways markets)

**Finding (in-sample on the year, per lot): the failed opening-range breakout is the one famous range-day entry that held up in both halves of the year and beat random entries.** The prior-day high/low rejection was positive in every variant but small. VWAP-band reversion and RSI(2) did not hold up. Nothing is changed in the system; adding a sideways-day strategy is the owner's call.

- Freeze `d5b08c9` was committed before scoring. It re-froze `2eed9af` when the O29h follow-up changed a bound engine file; nothing had been scored.
- 69 books ran through the shipped book (O29f BookReplay via O29g's lab), NIFTY Jan 1 – Oct 28 2026.
- Each sideways member trades only on days when yesterday's NIFTY daily ADX(14) is below 25.

## Results (per lot, sideways days only)

| Family | Variants positive (full year) | Median ₹ | H1 pick → H2 ₹ | H2 pick → H1 ₹ | Helps (frozen check) |
| --- | ---: | ---: | ---: | ---: | --- |
| **FADE: failed opening-range break** | 12 / 16 | +5,867 | **+6,752** | **+12,533** | **yes** |
| PDL_FADE: rejection of yesterday's high or low | 8 / 8 | +5,936 | +553 | +2,869 | yes (small) |
| VWAP_REVERT: VWAP-band rejection | 6 / 16 | −5,954 | −18,846 | +5,251 | no |
| RSI2: 5-minute RSI(2) extremes | 5 / 8 | +1,877 | −5,093 | −1,247 | no |
| Random entries on the same days (20 books) | 6 / 20 | −7,324 | median −891 (H1) | median −4,861 (H2) | yardstick |

The best variants:

| Book | Year ₹ | H1 | H2 | Trades | Worst day ₹ | Green / red months |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| FADE, 20-min range, stop beyond the failed extreme, 2.4R, live exits | 30,134 | 23,382 | 6,752 | 119 | −4,315 | 7 / 2 |
| FADE, 20-min range, structural stop, 1.5R, late exits | 24,086 | 16,782 | 7,304 | 103 | −3,616 | 7 / 2 |
| PDL_FADE, 1.5 ATR stop, 1.5R, live exits | 12,486 | 11,932 | 553 | 33 | −1,904 | 5 / 3 |

## Joined to the live trend book (UNION_ADX trades the trending days, the fade the sideways days; never both on one day)

| Book (per lot, Jan 1 – Oct 28) | Net ₹ | Trades | Worst day ₹ | Max DD ₹ | Green / red months | One-lot weeks from ₹15,000: up / down | Worst week end ₹ |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| UNION_ADX alone (live since Oct 29) | 80,912 | 106 | −6,485 | 12,519 | 5 / 1 | 8 / 5 (31 without a trade) | 12,893 |
| **UNION_ADX + FADE (OR20, 2.4R, live exits)** | **111,046** | 225 | −6,485 | 19,217 | **9 / 1** | 22 / 18 | 10,788 |
| UNION_ADX + PDL_FADE (1.5 ATR, 1.5R) | 93,398 | 139 | −6,485 | 11,853 | 7 / 3 | 19 / 15 | 12,893 |

- **Adding the fade** makes the book active almost every week and lifts the year per lot by about +₹30k, but it also brings many more down weeks (18 against 5). The prior-day rejection adds less (+₹12.5k) with no extra drawdown.
- **Smaller size on sideways days** (the owner's idea) is natural here: these rows are per lot. Capping the sideways member at 1 lot keeps the sideways risk at one lot even when the trend book sizes up.

## Caveats

- **In-sample:** the ADX split itself was found on this year (O29g). The fade's two-fold check is the only cross-check here.
- **Contrast with earlier work:** in O29b, on 17 two-way days in Sep–Oct, fades did no better than random. On the year's 120-odd low-ADX days, the failed-break fade held up. More days, and a different sideways definition (multi-day trend strength rather than one morning).
- **The clean test** is NIFTY 2025, never used to find either rule. The download starts at 08:00 IST Oct 30 after the owner's ICICI login, and the frozen books are scored unchanged.

## Files

- `lab_i.py` (the four families, gated to sideways days; plugs into O29g/O29f), `analyze_i.py`, `test_lab_i.py` (2 passed; every family causal).
- `freeze.json`, `results.json`, and the ignored `_local/` (raw replays).
