# SN31–SN50 (Nov 13, 2026): twenty more perspectives on SN Gold v3 → SN Gold v4

- **Lab:** `lab.py`, a copy of the frozen `../sn-gold/gold_v3.py` with extra knobs. v3 itself is never edited (`../sn-gold/verify_gold.py` re-checks it).
- **Scoring:** every variant at every wallet:
  - A: ₹15k, 1 lot;
  - B: ₹20k, 1 lot;
  - C: ₹30k sized;
  - growth from ₹15k, stopped after 0, 2, 3 (Gold) or 5 steps.
- **Selection:** chosen on three years and scored on the fourth, per wallet.
- **Costs:** Zerodha charges + ₹205 per lot per trade, 20% day limit, refills.
- **In-sample:** all of it, for the entries.

| SN | Perspective | Result | What it taught | Kept |
|---|---|---|---|---|
| 31 | Extension threshold (0 / 25 / 50%) | 25% best; 0% within ₹3k | v3 sits on a plateau, not a cliff | v3 as is |
| 32 | Extension trail width (2 / 3 / 4 ATR) | 3 best | Same | v3 as is |
| 33 | Two strikes in the money when it fits | B +₹1,51,508, G3 +₹3,37,510; A worse | Deeper in the money pays when the money per lot allows | → 38/43 |
| 34 | More scale-ins (2–3 adds) | Mixed, not better held out | One add is enough | No |
| 35 | Scale-in only on high-volatility days / before 14:00 / puts | Worse or mixed | – | No |
| 36 | Volatility line ×0.8–1.25 | ×1.0 best | The median is the right line | v3 as is |
| 37 | Second lot by today's intraday range | Worse than yesterday's volatility | – | No |
| 38 | Deepest in-the-money strike that fits (up to 2 or 3) | B +₹1,52,902 / +₹1,59,282, G3 +₹3,40,367, A worse | Depth must follow the money per lot | → 43 |
| 39 | Growth step ×1.25 / ×2, step after 50% / 150% | ×2: G3 +₹6,71,141 (scale, bigger worst days). After 50%: G3 +₹3,53,357 | Step size is the owner's lever, not an edge | Lever |
| 40 | Day limit 15 / 25 / 30% | 15% worse, 25–30% marginal | 20% is fine | v3 as is |
| 41 | At most 1 or 2 trades a day | Worse (1 a day: G3 +₹2,11,059) | N11's later trades of a day add value | No |
| 42 | Start the growing wallet at ₹20k / 25k / 30k | Stop after 3: +₹3,72,712 / +₹4,71,478 / +₹5,73,459; worst day −₹13,492 / −₹16,972 / −₹21,113 | More starting money, the same scale | Lever |
| 43 | **In-the-money depth by money per lot** (< ₹17.5k → 1, < ₹20k → 2, else 3) | **A unchanged; B +₹1,59,282 (held-out pick every fold); C ≈; G3 +₹3,26,853** | Never worse than v3 at any wallet | **v4** |
| 44 | Bootstrap of one year from weeks | A ₹15k: median +₹31,369, 5th pct +₹480, 4.7% chance of a losing year, refill median ₹24,154 (95th ₹36,505). C: median +₹54,560, 6% losing years | Risk in one year | – |
| 45 | Without the best days | A: +₹1,30,530 → +₹74,493 (best 5 out) → +₹30,055 (best 10 out) | Profit is concentrated in a few huge days: never cap winners | – |
| 46 | Why 2023 loses | TPB −₹6,253 on 15 trades in 2023; +₹19.9k to +₹32.7k a year after | 2023 was TPB's bad year | – |
| 47 | v4 robustness | ≥ v3 at every wallet at +₹300 and +₹400 stress; fine with entries 1 minute late | – | – |
| 48 | Owner's growth levers on v4 | Step after 50% profit: G3 **+₹3,53,995 with the same worst day** (−₹10,119). ×2 steps: +₹6,78,897, worst −₹23,934 | Earlier steps help without more risk at cap 3 | Lever |
| 49 | Freeze v4 next to v3 | `../sn-gold/SN_GOLD_V4.json`, `gold_v4.py`, `verify_gold_v4.py`, tag `sn-gold-v4`; v3 untouched | – | – |
| 50 | This report and `../sn-gold/FORWARD_V4.md` | – | – | – |

## SN Gold v4, by year: profit / refilled

| Wallet | 2023 | 2024 | 2025 | 2026 | Total | Refilled | Won/lost/none | Worst day |
|---|---|---|---|---|---:|---:|---|---:|
| A ₹15k | −8,430 / 23,354 | 47,279 / 15,931 | 41,587 / 36,226 | 50,094 / 22,468 | 1,30,530 | 97,979 | 55/63/624 | −2,998 |
| B ₹20k | −8,939 / 25,432 | 65,972 / 14,234 | 40,593 / 50,531 | 61,656 / 32,810 | 1,59,282 | 1,23,007 | 62/67/613 | −3,997 |
| C ₹30k | −21,192 / 42,439 | 92,170 / 25,583 | 57,836 / 62,997 | 99,135 / 47,930 | 2,27,949 | 1,78,949 | 58/71/613 | −5,994 |
| Grow, stop after 2 | −8,430 / 23,354 | 69,482 / 19,938 | 72,295 / 70,713 | 1,09,397 / 52,125 | 2,42,744 | 1,66,130 | 59/70/613 | −6,740 |
| **Grow, stop after 3** | −8,430 / 23,354 | 69,482 / 19,938 | 91,027 / 98,269 | 1,74,774 / 76,949 | **3,26,853** | 2,18,510 | 58/71/613 | −10,119 |
| Grow, stop after 5 | −8,430 / 23,354 | 69,482 / 19,938 | 1,05,095 / 1,38,619 | 3,79,672 / 1,89,374 | 5,45,819 | 3,71,285 | 58/71/613 | −22,740 |

**With the owner's lever "step after 50% profit"** (growth stopped after 3): +₹3,53,995, worst day −₹10,119.
