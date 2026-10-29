# O29g: why the F&O strategies lost, when they won, and a trend-strength gate

**In-sample finding, not yet proof.** All the strategies win in trending regimes and lose in range-bound ones, and yesterday's daily trend strength (ADX) tells the two apart before the session starts. Gating on it turned the year from losing months into mostly flat ones. The idea came from looking at this same year, so it now goes to a clean test on NIFTY 2025 (data available from ICICI, downloading Oct 30) and to the forward panel.

- Freeze `9d450aa` was committed before scoring.
- 137 books, Jan 1 – Oct 28 2026, on the sealed O29f dataset, through the shipped book via O29f's BookReplay.
- Research only; nothing changed.

## 1. Why: the day's environment, known before the session (`features.py`)

The daily result of each strategy (per lot) was split by features known before the trade. Each feature was split above or below its own median over the previous 60 sessions, and the split was tested in each half of the year. "Stable" means the same side was better in both halves.

| Feature (from yesterday's daily bars) | SHIPPED | OR20 | EFF | TPB | Live UNION_DRIVE |
| --- | --- | --- | --- | --- | --- |
| ADX(14) above usual | better, both halves | better, both | better, both | better, both | +₹377/day vs −₹425 (H1); +₹568 vs −₹530 (H2) |
| 20-day realised vol above usual | better, both | better, both | better, both | better, both | better, both |
| 20-day move above usual | better, both | better, both | better, both | better, both | better, both |
| Yesterday's range below usual | better, both | better, both | better, both | — | better, both |
| Yesterday a trending candle | better, both | better, both | better, both | better, both | better, both |
| Opening drive (09:45, the live gate) | low better | not stable | not stable | not stable | **not stable**: H1 went the wrong way |

- **In hindsight**, 81 of the 203 sessions were trend days (close and open at least half the range apart). SHIPPED, OR20, TPB and the live book made their money on those days and lost on the others.
- **The day before expiry was the best day by far**, per lot over the year: TPB +₹42,718 and the live book +₹33,714.

## 2. The gates on the year (per lot)

| Book | Year ₹ | Without best day ₹ | H1 Jan–May ₹ | H2 Jun–Oct ₹ | Trades | Worst day ₹ | Max DD ₹ | Green / red months | Green / red weeks |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Live UNION_DRIVE | 7,288 | — | 4,204 | 3,083 | 205 | −6,251 | 57,189 | 6 / 4 | 18 / 23 |
| TPB always | 42,056 | — | 30,799 | 11,257 | 85 | −5,528 | 22,896 | 6 / 4 | 18 / 14 |
| **TPB, ADX ≥ 20** | **54,816** | 36,333 | 38,353 | 16,463 | 36 | **−4,415** | **7,641** | 5 / 2 | **12 / 2** |
| **All four, ADX ≥ 25** | **80,912** | 33,625 | 62,997 | 17,915 | 106 | −6,485 | 12,519 | **5 / 1** | 11 / 5 |
| SHIPPED, ADX ≥ 25 | 32,494 | 12,446 | 22,144 | 10,350 | 30 | −4,066 | 4,066 | 6 / 0 | 8 / 4 |
| EFF, ADX ≥ 25 | 45,822 | — | 22,739 | 23,083 | 79 | −9,268 | 23,294 | 4 / 2 | 9 / 7 |
| All four, ADX ≥ 20 | 62,877 | 15,589 | — | — | 138 | −6,508 | 27,913 | 5 / 2 | 11 / 11 |
| TPB + breakouts at ADX ≥ 20 | 47,124 | −164 | — | — | 199 | −6,508 | 42,263 | 4 / 6 | 18 / 21 |

- **What the gate does:** with yesterday's ADX under 25, the book stays out. That held for almost all of May to August, the months that sank the live book. With ADX ≥ 25, "all four" made 0 trades from May to August.
- **The one-lot real-money rules** (₹15,000 a week, the ₹7,000 floor, 44 weeks):

  | Book | Up / down weeks | Worst week end ₹ |
  | --- | ---: | ---: |
  | TPB, ADX ≥ 20 | 9 / 2 (33 weeks without a trade) | 10,265 |
  | All four, ADX ≥ 25 | 8 / 5 | 12,893 |
  | Live UNION_DRIVE | 17 / 21 | 8,379 |

- **Two-fold check** (choose the gate on one half, score it on the other):
  - SHIPPED and OR20 beat "always on" in both directions.
  - EFF and TPB did not. TPB's H1 pick (ADX ≥ 20) beat always-on on H2 (+₹16,463 against +₹11,257). Its H2 pick (ADX ≥ 25) did not beat always-on on H1.
- **Luck check:**
  - ADX ≥ 20 on the 20 random-entry books improved 13 of them, with a median change of +₹4,976.
  - They still lose overall (median −₹14,138).
  - So the gate removes bad regimes, but the entry rule still decides whether the good regimes pay.
- **Profit concentration:** a large share sits in February and October, the two strongest trend months. "Without best day" is about half the total.

## 3. The two published ideas (adapted honestly; neither held up here)

| Book | Year ₹ (per lot) | H1 | H2 | Note |
| --- | ---: | ---: | ---: | --- |
| NOISE_BAND, k 1.0, every 30 min (as published) | −33,399 | −8,564 | −24,835 | Zarattini, Aziz & Barbon's SPY rule does not transfer to bought NIFTY options with our exits |
| NOISE_BAND, k 1.0, every 5 min | 41,178 | 33,358 | 7,821 | erratic: 5 green / 5 red months, DD ₹59,555 |
| LATE_MOMO, first half-hour 0.3% (Gao et al.) | 8,000 | 20,207 | −12,207 | positive in H1 and negative in H2 in every variant |
| LATE_MOMO, day move 0.3%, high vol | 60,546 | 65,867 | −5,321 | the same regime flip |
| TPB + LATE_MOMO | 57,301 | 46,088 | 11,213 | not better than TPB, ADX ≥ 20, with more trades |

## What this means

1. **Our strategies are trend strategies and should trade only in trending regimes.** Yesterday's ADX is a simple, published (Wilder's), pre-session way to tell. It acts like a smart sit-out, not a loss-reaction block: it decides before the day starts, from the market, not from our own losses.
2. **The best consistent shape found:** TPB, only when yesterday's ADX ≥ 20. It trades rarely (36 times in 10 months), with the smallest worst day (−₹4,415 per lot), the smallest drawdown (₹7,641) and 12 green against 2 red weeks. Second: all four strategies at ADX ≥ 25.
3. **This is in-sample.** The clean tests, all frozen as they are now:
   - **NIFTY 2025.** ICICI serves it. The download starts at 00:10 IST on Oct 30, after SENSEX, and continues the next night.
   - **SENSEX 2026.**
   - **The forward panel.** Adding these books to it is the owner's call.

## Files

- `features.py` (the descriptive split), `lab_g.py` (gates, NOISE_BAND, LATE_MOMO, books; plugs into O29f), `analyze_g.py`, `test_lab_g.py` (4 passed).
- `freeze.json` and `results.json`.
- The raw replays are in the ignored `_local/`.
