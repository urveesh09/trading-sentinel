# O30c: why the live book broke even on 2025, and which cases help (both NIFTY years)

**Why it failed:**
- **One strategy turned.** EFF lost ₹21,796 per lot in 2025 inside the live book, after making ₹29,629 in 2026.
- **The trend gate locked TPB out of its best 2025 days:** TPB made ₹31,869 on the days the gate kept it out.
- **2026 was mostly a falling market and 2025 a rising one.** The book's puts paid in both years (+₹27,484 and +₹63,120). Its calls lost in 2025 (−₹27,214).

**What helps:**
- **Of 15 cases fixed in advance, one adds something real:** let TPB trade on the days the gate is closed.
  - 2025: +₹34,246 per lot. 2026: −₹680, essentially unchanged.
  - Both years: +₹1,14,748 against +₹81,183 for the live book.
  - By the strict frozen rule it still counts as a miss (2026 is ₹680 lower), so it is a candidate, not proof.
- **Every case suggested afterwards by the investigation made the book worse,** even on the data it came from.

Research only; nothing in the system changed.

- **Freezes:** Tier 1 (cases from standard trading logic, the rule, and the investigation script) `a98b1f5`, committed before any case replay or investigation. Tier 2 (cases from the investigation) `b0defde`.
- **Data:** NIFTY 2025 (248 sessions, the sealed O30 data) and Jan–Oct 2026 (203 sessions, O29f), through the same shipped book, per lot of 65.
- **Sanity check:** the base books reproduce the earlier runs exactly: the live book +₹271 / +₹80,912, and UNION +₹27,140 / −₹2,691.

## 1. The investigation (`diagnose_c.py`, `diagnosis.json`)

| | 2025 | 2026 |
| --- | --- | --- |
| The market | Rising on 55% of days (DMI), median ADX 22 | Falling on 77% of days, median ADX 18 |
| Live book by strategy (trades, ₹) | EFF 74, **−21,796**; SHIPPED 29, +8,970; OR20 19, +8,299; TPB 16, +4,797 | EFF 56, +29,629; SHIPPED 21, +23,851; OR20 21, +4,070; TPB 8, +23,362 |
| Live book: calls / puts | −27,214 / +27,484 | +17,793 / +63,120 |
| TPB alone: trend days / other days | +4,825 / **+31,869** | +45,480 / −3,424 |
| EFF alone: trend days / other days | −14,547 / +14,166 | +39,589 / −51,772 |
| Breakouts (SHIPPED, OR20) with / against the daily trend | +33,059 / −32,581 | +18,602 / −17,497 |
| All four: entries before 10:00, after 14:00 | −8,274, −3,177 | −5,689, −16,184 |

- **ADX ≥ 25 "trend days" are not a law of the market.** They were the good days for every strategy in 2026. In 2025, EFF and TPB did better on the other days.
- **Losses come from the stop exits in both years; profits come from a few trailing-stop winners.** That is normal for trend strategies.
- **The only day feature better on the same side in all four half-years** was a larger-than-usual 20-day move.

## 2. Tier 1: cases fixed before the investigation (per lot; the rule: beat the base in both years, not worse in 3 of 4 half-years, ≥ 40 trades a year)

| Case | 2025 ₹ | 2026 ₹ | Both ₹ | vs base 2025 | vs base 2026 | Verdict |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| **Live book + TPB trades on days the gate is closed** | 34,517 | 80,232 | **114,748** | **+34,246** | −680 | miss (2026 by ₹680) |
| Same, with TPB first | 34,517 | 80,284 | 114,800 | +34,246 | −628 | miss |
| Live book + trade only with the trend (20-day EMA) | −5,568 | 94,969 | 89,401 | −5,839 | +14,057 | no |
| Live book + only with the trend (DMI) | −11,261 | 75,945 | 64,684 | −11,532 | −4,967 | no |
| Live book + only when DMI and EMA agree | −7,842 | 84,490 | 76,648 | −8,113 | +3,578 | no |
| Live book + TPB first | 271 | 81,035 | 81,306 | 0 | +123 | no (no change) |
| Live book + TPB all days + DMI direction | −4,994 | 94,347 | 89,353 | −5,265 | +13,435 | no |
| **Live book (base)** | **271** | **80,912** | **81,183** | — | — | — |
| No gate + only with the trend (EMA / DMI / both) | 8,072 / 10,603 / 9,989 | 77,529 / 39,821 / 66,599 | — | all worse | all better | no |
| No gate + TPB first | 30,326 | −1,737 | 28,590 | +3,186 | +954 | **yes, but small** (base UNION) |
| Other day gates instead of ADX ≥ 25 (ADX ≥ 20, high volatility, trend regime) | 13,519 / −6,183 / 1,208 | 62,877 / 57,385 / 48,662 | — | all worse | all better | no |
| **No gate (UNION, base)** | 27,140 | −2,691 | 24,449 | — | — | — |

- **The direction case on the 20 random-entry books:**
  - **2025:** it helped 16 of them, median +₹4,456.
  - **2026:** it helped 11 of them, median +₹2,296.
  - So "with the trend" is a mild general effect. On the real book it cut the 2025 trades that made money.
- **"TPB on the closed days" trades more often.**
  - **Weeks (both years):** 35 up and 41 down, against 14 up and 18 down for the live book.
  - **Months:** 13 green and 9 red.
  - **Max drawdown:** ₹33,331, against ₹31,482.
  - **Worst one-lot week:** ends at ₹7,826 from ₹15,000, the same as the live book.

## 3. Tier 2: cases from the investigation (in-sample; found by looking at both years)

| Case | 2025 ₹ | 2026 ₹ | Both ₹ | Max DD ₹ |
| --- | ---: | ---: | ---: | ---: |
| Live + TPB on closed days | 34,517 | 80,232 | 114,748 | 33,331 |
| + entries only 10:00–14:00 | 30,495 | 79,903 | 110,398 | 40,937 |
| + breakouts only with the trend + 10:00–14:00 | 26,790 | 75,174 | 101,964 | 40,424 |
| + breakouts only with the trend | 30,655 | 53,404 | 84,060 | 42,987 |
| Live book | 271 | 80,912 | 81,183 | 31,482 |
| Four strategies on days after a large 20-day move | 6,758 | 62,985 | 69,742 | 22,000 |
| Live + breakouts only with the trend | −1,885 | 56,937 | 55,052 | 31,143 |
| No gate + breakouts only with the trend | 33,609 | −51,544 | −17,935 | 108,120 |

- **None of them beats "TPB on closed days", even on the data that suggested them.**
- **Why the breakout rule fails inside the book:** a passed-over breakout frees the slot for another strategy's signal, often EFF's. The tables count each strategy alone; the book does not trade that way.

## 4. Over-tuning: what this study shows

- **What a careless search looks like:** a pattern looks solid when the past is sliced (breakouts with the trend, no entries after 14:00), then fails as soon as it is built in. This study shows that happening here.
- **What we did instead:**
  - The cases were fixed in advance with one textbook setting each.
  - A case had to win in both years, not just in total.
  - Ideas found by looking are kept apart.
- **One case survives,** and it adds a strategy that was already in the book; it doesn't fine-tune numbers.
- **The clean test it still needs:**
  - **NIFTY 2024**, which no study has used (ICICI should serve it; about 4,500 requests, one day of the allowance).
  - **Then the forward panel.**
  - **The 2024 rule (frozen here):** beat the live book over the year and not be worse in either half.
- **The hypotheses for 2024,** to be frozen before its data is opened:
  - **The candidate:** TPB on the closed days.
  - **What the investigation points at:** EFF as the unstable member, and the calls-vs-puts asymmetry.

## Files

- **Tier 1:** `lab_c.py` (cases and routing), `analyze_c.py`, `diagnose_c.py`, `test_lab_c.py` (3 passed), `freeze.json`, `results.json`, `diagnosis.json`.
- **Tier 2:** `lab_c2.py`, `test_lab_c2.py` (2 passed), `freeze-tier2.json`, `results-tier2.json`.
- **Raw replays:** the ignored `_local/`.
