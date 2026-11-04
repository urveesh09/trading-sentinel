# Can the next 30 minutes be predicted? (2026-11-04)

The owner asked whether the Sentinel could have seen the partner's falls, or a rise, coming, and with what
confidence.

**Script:** `predictability.py`. **Output:** `results.json`. It reads the sealed research datasets, read-only:
NIFTY index 1-minute candles, Dec 2023 – Oct 2026.

**Method:**
- A decision every 5 minutes from 09:30 to 14:59. Every feature uses only candles up to that minute.
- Features: the run over the last 5, 15, 30 and 60 minutes; the move since the open; the gap; the position in
  the day's range; recent volatility; the time of day.
- Two models: logistic regression, and a binned look-up table. Both are trained on 2024 only and tested once on
  2025 (247 sessions) and on Jan–Oct 2026 (190 sessions), never refitted.
- "Base rate" means always saying the commoner side.

| Question (next 30 min) | 2025 test | 2026 test | Reading |
|---|---|---|---|
| Up or down? Accuracy (base rate) | 52.4% (50.9%) | 51.7% (52.1%) | A coin flip. In 2026 it was worse than always saying "down". |
| Up or down? AUC (0.5 = chance) | 0.53 | 0.53 | No usable signal. |
| Its 10% most confident "up" calls, right | 55% | 52% | Still close to a coin flip. |
| Big fall (≥0.5%): normal rate | 1.2% | 1.7% | |
| Big fall: in its riskiest 10% of moments | 6.7% | 5.1% | 3–5× more likely, still rare. |
| Big rise (≥0.5%): normal rate / riskiest 10% | 1.0% / 4.7% | 1.7% / 6.0% | The same moments. |
| Big-move AUC, logistic (fall / rise) | 0.82 / 0.79 | 0.60 / 0.76 | Size of the move is partly forecastable. |

**What the models can see:** both big-move models lean mostly on recent volatility. That means they can see when
a big move is more likely. They cannot see which way it will go.

**Descriptive base rates (small samples):**
- **After a ≥0.5% NIFTY rise in the first 30 minutes:** the next 30 minutes kept rising on 23% (2025, 13 days) and
  38% (2026, 8 days) of days. A big fall followed within 30 minutes on 8–13% of them.
- **After a ≥0.5% fall in the first 30 minutes:** it kept falling on 46–50% of days.
- **Gao et al.'s intraday momentum on NIFTY** (first half-hour sign against the last half-hour): 52% / 50% / 48%
  in 2024 / 2025 / 2026. Nothing here.

**Conclusion.** On this data, from public 1-minute prices, the direction of the next 30 minutes cannot be
predicted, and a fall is never "destined". What can be seen is when the market is unusually likely to move a lot,
either way. The sensible response to that is smaller size, which the Sentinel's own book already does (N11 sizes
by volatility). That is a forecast of risk, not of direction.
