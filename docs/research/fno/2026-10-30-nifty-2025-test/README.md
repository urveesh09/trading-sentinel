# O30: the 2026 strategies on NIFTY 2025, a clean test

**The trend gate and the sideways fades did not hold up on 2025.**
- **The live book, UNION_ADX** (all four strategies, only when yesterday's ADX ≥ 25), made **+₹271 per lot over all of 2025**: flat, with a ₹31,482 drawdown.
- **The failed-break fade and the prior-day rejection lost** on 2025's sideways days.
- **TPB alone** (the trend-day VWAP pullback) was the one thing positive in both years.

Nothing in the system was changed.

- **Freeze `7d9eeb3`** was committed before any 2025 replay. It holds 76 books, the verdict rule and the analysis script, and the engine files were checked unchanged since O29i.
- **Data:** NIFTY Jan 1 – Dec 31 2025, ICICI Breeze 1-minute bars.
  - **Sessions:** 248. Oct 21, Diwali, is dropped: the only trading was the one-hour Muhurat session.
  - **What was replayed:** the same shipped book (O29f BookReplay), per lot of 65.
  - **Why 2025 is clean:** no rule, gate or variant was chosen on it.
- **2026 comes from the stored O29f/O29g/O29i replays.** It is in-sample and was not re-scored.

## 1. The frozen verdicts

| Question (rule frozen before scoring) | 2025 result | Verdict |
| --- | --- | --- |
| UNION_ADX > 0 and beats UNION (no gate), UNION_DRIVE and the gated random books' median | +₹271; UNION +₹27,140; UNION_DRIVE +₹64,712; random median −₹13,969 | **No** |
| FADE (main variant) > 0 on sideways days and beats the random sideways books' median | −₹14,518 (random median −₹22,894) | **No** |
| PDL_FADE (main variant), the same test | −₹12,775 | **No** |
| TPB at ADX ≥ 20 > 0 and beats TPB always | +₹24,680 against +₹36,694 | **No** (both positive) |
| Add the fade on sideways days? | UNION_ADX + FADE −₹14,248 | **No** |

## 2. 2025 per lot

| Book | Year ₹ | Jan–Jun ₹ | Jul–Dec ₹ | Trades | Worst day ₹ | Max DD ₹ | Green / red months |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| UNION_DRIVE (live until Oct 29) | 64,712 | 44,260 | 20,452 | 270 | −7,015 | 29,542 | 10 / 2 |
| TPB always | 36,694 | 8,955 | 27,739 | 107 | −6,859 | 14,966 | 8 / 4 |
| UNION (all four, no gate) | 27,140 | 41,352 | −14,212 | 410 | −6,281 | 29,091 | 7 / 5 |
| TPB, ADX ≥ 20 | 24,680 | 6,776 | 17,904 | 73 | −6,859 | 14,966 | 7 / 3 |
| **UNION_ADX (live now)** | **271** | 3,350 | −3,079 | 138 | −6,281 | 31,482 | 4 / 4 |
| FADE, main variant (sideways days) | −14,518 | −1,500 | −13,018 | 123 | −3,885 | 25,557 | 6 / 5 |
| PDL_FADE, main variant (sideways days) | −12,775 | −10,031 | −2,744 | 49 | −3,693 | 18,383 | 2 / 8 |
| UNION_ADX + FADE | −14,248 | — | — | 261 | −6,281 | 43,126 | 7 / 5 |

- **The gate in 2025:** yesterday's ADX was ≥ 25 on 71 of 248 sessions, mostly in Jan–Apr and August. There were none in June, July, September or December.
  - UNION_ADX lost ₹22,171 in February 2025.
  - In 2025 the gate cut most of what the ungated four would have made (UNION +₹27,140).
- **Strategies alone, always on:**
  - TPB +₹36,694, SHIPPED +₹6,521, EFF −₹381, OR20 −₹6,043.
  - Under the ADX ≥ 25 gate: SHIPPED +₹2,832, TPB +₹1,989, OR20 −₹416, EFF −₹13,581.
- **Random-entry books, median per lot:** always −₹24,576; under the gate −₹13,969; sideways days −₹22,894.
- **One-lot weeks from ₹15,000:**

  | Book | Up / down weeks | Worst week end ₹ |
  | --- | ---: | ---: |
  | UNION_ADX | 6 / 13 | 7,826 |
  | UNION_DRIVE | 24 / 26 | 9,162 |
  | TPB always | 19 / 19 | 11,003 |
  | TPB, ADX ≥ 20 | 11 / 15 | 11,003 |

## 3. Both years together: 2025 + Jan–Oct 2026, per lot (22 months)

| Book | 2026 ₹ (in-sample) | 2025 ₹ (clean) | Both ₹ | Trades | Worst day ₹ | Max DD ₹ | Green / red months |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| UNION_ADX + FADE | 111,046 | −14,248 | 96,798 | 486 | −6,485 | 43,126 | 16 / 6 |
| UNION_ADX (live now) | 80,912 | 271 | 81,183 | 244 | −6,485 | 31,482 | 9 / 5 |
| **TPB, ADX ≥ 20** | 54,816 | 24,680 | **79,496** | 109 | −6,859 | **14,966** | 12 / 5 |
| **TPB always** | 42,056 | 36,694 | **78,750** | 192 | −6,859 | 22,896 | 14 / 8 |
| UNION_DRIVE | 7,288 | 64,712 | 72,000 | 475 | −7,015 | 57,189 | 16 / 6 |
| UNION (no gate) | −2,691 | 27,140 | 24,449 | 727 | −8,622 | 60,166 | 11 / 11 |

- **The ranking flips between years:**
  - UNION_DRIVE was nearly the worst in 2026 and the best in 2025.
  - UNION_ADX was the best in 2026 and flat in 2025.
  - This is the O27f lesson again: past rank is not future rank.
- **Only TPB was positive in both years in both forms.** It also had the smallest drawdowns and the fewest trades. It is also the only component positive on every window tested so far: the Sep–Oct 2026 quote archive, Jan–Oct 2026 and 2025.
- **Candles flatter results.** On the overlap with the recorded quotes, the candle data came out about ₹100–200 per trade per lot better (O29f). The more trades a book makes, the larger that haircut:
  - UNION_ADX's 2025 (138 trades) is likely a loss with real quotes.
  - TPB's (107 trades) stays positive.

## Caveats

- **2025 is now seen.** Any choice made on this table, such as picking TPB, is chosen on both years. The forward panel is the remaining clean check.
- **The regime label is UNKNOWN in 2025,** as it was in Jan–Jul 2026, so the crisis filter never fires.
- **The ADX reading in early January 2025** rests on about 60 daily bars (the daily history starts Oct 3, 2024). It is close to, but may differ slightly from, a long-history reading.
- **One gap day:** Jan 31, 2025 has no index bars before 11:53 (a Breeze gap). Jan 30, 2026 has the same gap.

## Files

- `lab_t.py`: the sealed 2025 copy and dataset, the books, the rule, and a resumable warm-up.
- `analyze_t.py`: the frozen analysis.
- `test_lab_t.py`: 2 passed. The books are the ones frozen on 2026, and the copy holds 2025 only.
- `freeze.json` and `results.json`.
- The ignored `_local/` holds the copy, the dataset and the raw replays.
