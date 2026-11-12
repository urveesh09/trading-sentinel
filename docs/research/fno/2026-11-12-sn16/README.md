# SN16–SN18 (Nov 12, 2026): three new ideas on N11's days, each scored at every wallet

Research only. Entries are N11's (in-sample). Wallets for every variant:
- **A:** ₹15k, 1 lot;
- **B:** ₹20k, 1 lot;
- **C:** ₹30k, the second lot on high-volatility days;
- **G:** grow from ₹15k, stopped after 0–5 steps.

Zerodha charges + ₹205, 20% day limit, refills. The benchmark reproduces exactly in every wallet. Selection: chosen on three years and scored on the fourth, per wallet (`results.json`).

## SN16: let N11's winners run past its clock

If a trade is up at least +x at N11's exit, keep it with a trail (premium give-back, or an index trail of k × 1-minute ATR) until 15:10. 12 variants.

**The best, "≥ +25%, index trail 3 ATR", per year (profit / refilled):**

| Wallet | 2023 | 2024 | 2025 | 2026 | Total | Benchmark | Refilled | Won/lost/none | Worst day |
|---|---|---|---|---|---:|---:|---:|---|---:|
| A | −7,059 / 20,564 | 37,343 / 14,915 | 37,842 / 34,651 | 45,441 / 21,505 | 1,13,567 | 1,11,995 | 91,635 | 55/63/624 | −2,998 |
| B | −7,591 / 21,096 | 50,147 / 12,118 | 30,083 / 44,856 | 51,943 / 28,272 | 1,24,582 | 1,24,093 | 1,06,342 | 60/69/613 | −3,997 |
| C | −1,011 / 28,153 | 78,324 / 23,967 | 43,317 / 57,622 | 89,601 / 45,995 | 2,10,231 | 2,08,778 | 1,55,737 | 59/70/613 | −5,997 |
| G stop after 2 | −7,059 / 20,564 | 43,522 / 17,488 | 54,342 / 61,265 | 89,405 / 49,476 | 1,80,210 | 1,50,460 | 1,48,793 | 59/70/613 | −6,739 |
| G stop after 3 | −7,059 / 20,564 | 43,522 / 17,488 | 56,805 / 79,656 | 1,46,921 / 73,481 | 2,40,189 | 2,01,565 | 1,91,189 | 59/70/613 | −10,117 |
| G stop after 5 | −7,059 / 20,564 | 43,522 / 17,488 | 56,805 / 79,656 | 2,73,204 / 1,35,127 | 3,66,472 | 2,79,873 | 2,52,835 | 59/70/613 | −22,730 |

**Held out:**

| Wallet | Picks | Benchmark |
|---|---:|---:|
| A | +1,09,030 | 1,11,995 |
| B | +1,19,665 | 1,24,093 |
| C | +2,01,989 | 2,08,778 |
| G3 | **+2,37,980** | 2,01,565 |

**What it teaches:**
- N11's clock exits leave only a little on the table at a fixed wallet (± a few thousand, noise).
- In a growing wallet the kept winners arrive when lots are bigger, and the gain compounds.
- The losing days are unchanged.

## SN17: re-enter after a winning N11 trade

Buy again when the index makes a new extreme beyond the exit level within 30 or 90 minutes. 8 variants.
- Every variant loses money against the benchmark at every wallet. The best at A made +₹93,973; at C, +₹1,77,780.
- **What it teaches:** after N11 wins, the move is mostly over, and the follow-through cannot be bought.

## SN18: size the second lot by days to expiry instead of volatility

| Rule (C wallet) | Four years |
|---|---:|
| **Volatility (SN13)** | **+₹2,08,778** |
| DTE ≤ 2 | +₹1,63,397 |
| DTE ≥ 3 | +₹1,64,278 |
| Volatility and DTE ≤ 2 | +₹1,75,427 |
| Volatility or DTE ≤ 2 | +₹1,96,750 |

**What it teaches:** realised volatility is the sizing signal. Option cheapness near expiry is not.
