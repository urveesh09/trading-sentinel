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

## SN86–SN88: big-day prediction + the put edge + the opening drive, on Gold-free days (`sn86.py`, `results-sn86.json`)

| Idea (gold-free, wide opening range) | Four years | By year | Note |
|---|---:|---|---|
| Plain puts at 09:45, HOLD 6-ATR trail | +18,592 | +2,258 / −3,678 / +25,059 / −5,047 | All 2025 |
| Down opening drive (≥ 0.6 of the range) → puts, QUICK 1R | +315 | – | – |
| Opening drive, either side | – | – | Loses |
| Downside break only | – | – | Loses |

- No variant is positive in every year.
- **Held out:** −₹38,179, against random sides at −₹16,292.

## SN89: the combination check

SN Gold v5 plus the best empty-day sleeve from SN81–SN88. Every sleeve candidate loses held out (SN81–SN84 and SN86–SN88: −₹34k to −₹40k each), so any combination is worse than v5 alone on years it did not choose on. v5 alone stays the best.

## SN90: what SN76–SN89 settle

1. **Why Gold sits out (SN76):** on 609 of its 620 empty days N11 has no setup. Low-ADX days allow only trend-pullback puts; the empty days are slow up-grinds and narrow ranges.
2. **Those days have no intraday edge we could find:**
   - option buying at 1-minute (SN04–SN09) and 1-second resolution (SN78/SN79: worse than random on unseen Jul–Nov);
   - option selling (SN77);
   - the web's day-type rules (SN80–SN84: false on NIFTY);
   - puts and opening drives on predicted big days (SN86–SN88).
3. **Why quick exits with a small cap lose:** each round trip costs about ₹85–120 per lot, direction there is a coin flip, and the cap removes the rare big days that carry Gold's profit (SN45: the 10 best days hold ~77% of it).
4. **What is true and useful:**
   - a wide 09:15–09:45 range predicts a big day (34% vs 8%);
   - Gold's profit lives on big-range and down days;
   - yesterday's volatility already sizes Gold well (SN85).
5. **Recommendation:**
   - keep SN Gold v5 unchanged and stay flat on its empty days;
   - judge it by its forward check;
   - new empty-day work needs information price can't give (event calendar, global cues before the open), not more entry rules on the same data.
