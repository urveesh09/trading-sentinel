# SN80–SN85 (Nov 13, 2026): the web's day-type claims, a different perspective for Gold's empty days, and Gold sizing

## Web research

Retail sources claim:
- **narrow CPR** (central pivot range from yesterday's H/L/C) means a trend day, and wide CPR a range day;
- a **tight opening range "coils"** before a sharp move.

The sources (optionx.trade CPR guide, TradingView CPR scripts and charts, Marketcalls' VWAP test, a TradingQnA 9:20 straddle thread) are blogs and scripts without backtests, and Marketcalls' own VWAP backtest failed.

## SN80: the claims tested (descriptive, 2023 – Oct 2026, 702 ranked sessions; `results.json`)

| Group | Average range | Range after 09:45 | Share of days with range ≥ 1.3% |
|---|---:|---:|---:|
| Narrow CPR (bottom third vs the last 20 days) | 0.885% | 0.783% | 15.3% |
| Wide CPR | 0.999% | 0.883% | 18.6% |
| Tight 09:15–09:45 range | 0.736% | 0.676% | 7.6% |
| Wide 09:15–09:45 range | 1.184% | 1.009% | **34.3%** |

**Both claims are false on NIFTY.** Volatility clusters: a wide first 30 minutes predicts a big day; a tight one stays small.

## SN81–SN83: opening-range break on Gold-free days (ADX < 30), filtered by the web's claims

- **Exits:** HOLD (3 or 6-ATR index trail to 15:00) or QUICK (index target 0.5 or 1 R, 45 minutes).
- **Money:** one lot, charges + ₹205; NULL = random side on the same days and minutes.
- **Result:** every real variant loses. The best four-year total was −₹23,731. Held out: −₹39,536, against random's −₹26,233.

## SN84: the same break, only on wide-opening-range / wide-CPR Gold-free days (`results-sn84.json`)

- **Best:** about break-even (+₹301 over 73 days).
- **Held out:** −₹34,697, against random's −₹17,712. Random sides on the same days did as well.
- **What it teaches:** these days do move, but the break's direction is a coin flip. N11's setups are where the direction edge lives.

## SN85: Gold v5's second lot by the opening-range width (`results-sn85.json`)

| Version | C (₹30k sized) | G3 |
|---|---:|---:|
| v5 (second lot on yesterday's volatility) | +₹2,80,508 | +₹3,99,906 |
| OR-wide instead | +₹2,40,154 | +₹3,45,583 |
| OR-wide or volatility | +₹2,78,583 | +₹3,95,236 |

Held out: v5 picked in 15 of 16 folds. Yesterday's volatility already carries the "big day" information for Gold.

## What SN80–SN85 teach

- Quick exits with a small cap lose because each round trip costs about ₹85–120 per lot against a coin-flip direction, and the cap removes the rare big days where all the profit is.
- Day type (big or small) can be predicted; direction on Gold's empty days cannot, from price.
- SN Gold v5 stays the best.
