# O30m: a "kind of day → strategy" router, tested across years, and the 2024 exam (O30f)

**Picking a strategy for each kind of day failed on the year it did not see,** in all six ways of describing a day. The reason: across 114 strategies, a strategy's 2025 result says almost nothing about its 2026 result (rank correlation 0.12, and −0.36 to 0.18 inside each kind of day).
- **What did hold in both years is one family, the trend pullback (TPB).** It held across many exits and genomes, not one lucky setting.
- **The best book found is still the O30c candidate:** the live book + TPB on the days the gate is closed, +₹1,14,748 per lot over both years (+₹34,517 / +₹80,232).
- **It goes to the one-time NIFTY 2024 exam,** frozen before the 2024 data exists.

Research only; nothing in the system changed.

## Method (freeze `2bcec04`, committed before any replay)

- **Library:** 134 single strategies, each replayed always-on over NIFTY 2025 (248 sessions) and Jan–Oct 2026 (203) through the same shipped book, per lot of 65.
  - The four named strategies × five exits (+ VWAP exit).
  - 8 seeded genomes of each O27f lab family (trend pullback, prior-day break, VWAP band, momentum burst) + the O27f TPB genome.
  - NOISE_BAND and LATE_MOMO.
  - All 48 range-day variants (FADE, VWAP_REVERT, PDL_FADE, RSI2).
  - UNION, and 20 random-entry books.
- **Kinds of day:** each day is described before trading, using six declared ways of combining:
  - **Macro (yesterday's daily bars):** trend strength (ADX ≥ 25), trend direction (DMI), 20-day volatility, the trend regime.
  - **Micro:** the 09:45 opening drive.
- **The router:** for each kind of day, take the strategy whose worst half-year there is best, in one of three direction modes (any direction, with the daily trend, or against it). If nothing is positive with enough trades, sit out.
- **The check:** choose on 2025 and score on 2026, and the reverse. The router must beat the live book, the O30c candidate and 200 random routers on the unseen year, both ways.

## Results

**The cross-year check** (per lot on the unseen year; estimated by slicing each strategy's own trades):

| Ways of describing a day | Chosen on 2025 → 2026 | Random | Chosen on 2026 → 2025 | Random | Passes |
| --- | ---: | ---: | ---: | ---: | --- |
| Trend strength | −27,522 | 1,179 | −54,559 | −12,184 | no |
| + direction | −21,407 | −4,372 | −5,049 | −9,991 | no |
| + direction + volatility | −32,990 | −6,416 | −16,702 | −3,891 | no |
| Trend regime + direction | −22,920 | −6,792 | −24,102 | −5,086 | no |
| Trend strength + opening drive | −79,000 | −2,960 | −23,305 | −12,302 | no |
| + direction + opening drive | −45,711 | −4,631 | 2,942 | −13,771 | no |

The references on the unseen years were: the live book +₹80,912 on 2026 and +₹271 on 2025; the O30c candidate +₹80,232 and +₹34,517.

**Exact replays** (trend strength + direction) confirm it, and show over-tuning plainly:

| Router | Year it was built on | The other year |
| --- | ---: | ---: |
| Chosen on 2026 | **+1,10,602** (2026) | **−34,803** (2025) |
| Chosen on 2025 | +55,084 (2025) | −13,787 (2026) |

**Winners do not repeat** (`persistence.json`):
- 2026's biggest winners lost heavily in 2025:

  | Strategy | 2026 | 2025 |
  | --- | ---: | ---: |
  | VWAP band (genome 3) | +55,925 | −34,247 |
  | FADE OR20 1.5R | +47,555 | −32,772 |
  | LATE_MOMO day 0.6% | +45,264 | −37,232 |
  | NOISE_BAND 5-min | +41,178 | −36,596 |

- 14 of the 114 strategies were positive in both years, and 0 of the 20 random books. Of the 14:
  - TPB with five different exits (OWN, RUN, LATE, LOOSE, LIVE) and with the VWAP exit;
  - the O27f TPB genome;
  - two other trend-pullback genomes;
  - SHIPPED (small);
  - two prior-day-break genomes.

**Books with the robust family** (exact, per lot):

| Book | 2025 | 2026 | Both | Max DD | Green / red months | One-lot weeks up / down (worst end) |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| **Live + TPB on closed days (O30c)** | 34,517 | 80,232 | **114,748** | 33,331 | 13 / 9 | 35 / 41 (₹7,826) |
| Live book | 271 | 80,912 | 81,183 | 31,482 | 9 / 5 | 14 / 18 (₹7,826) |
| ROBUST_CORE (TPB, two pullback genomes, SHIPPED) | 19,200 | 59,630 | 78,830 | 37,483 | 15 / 7 | 43 / 46 (₹9,167) |
| TPB alone | 36,694 | 42,056 | 78,750 | **22,896** | 14 / 8 | 34 / 32 (**₹10,265**) |
| UNION_DRIVE (live until Oct 29) | 64,712 | 7,288 | 72,000 | 57,189 | 16 / 6 | 41 / 47 (₹8,379) |

Adding more robust strategies did not beat TPB alone. They take TPB's turns.

## What this means

- **Strategies that win big in one kind of year and lose in the other do exist.** But nothing we can read before the session tells which one will win next. Choosing by past results per kind of day is picking last year's winners.
- **What survives a change of year:**
  - the trend-pullback idea (TPB);
  - letting it trade on more days (the O30c case).
- **Data limit:** two years is not enough to learn a reliable day-by-day switch from this library. 2024, the forward panel and more years can test the idea again later. They do not justify switching now.

## The 2024 exam (`freeze-2024.json`, `lab_f.py`, frozen at `2a57ede`)

- **The books:** 23, among them the live book, the O30c candidate, TPB alone, ROBUST_CORE, the 14 both-years strategies alone and the routers.
- **The rules (RULE_2024):**
  - The O30c candidate is confirmed if it beats the live book on 2024 and is not worse in either half.
  - "Positive in both years" carries over if at least 9 of the 14 are positive on 2024 and their median beats the rest of the library.
- **Steps once the other agent has run `download2024.py`** (see the download guide):
  1. `python lab_f.py mirror24`, then `python lab_f.py export24`, with `O30F_YEAR=2024` for both.
  2. `O30F_YEAR=2024 python lab_f.py run --jobs 4`, in slices. It also replays the whole library for the persistence rule.
- **The engine must be unchanged since O29i** (the run checks this). After any engine change, run from a worktree at `2a57ede`.

## Files

- `lab_m.py`: the library, the routing and the run.
- `analyze_m.py`: `select` (the cross-year check) and `report` (exact).
- `test_lab_m.py`: 2 passed.
- `freeze.json`, `routers.json`, `results.json`.
- `persistence_m.py` and `persistence.json`: written after the verdict, to explain it.
- `lab_f.py` and `freeze-2024.json`: the 2024 exam.
