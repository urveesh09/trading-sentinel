# SN03: trying to beat the SN02 benchmark, and the wallet stopped after step k (Nov 12, 2026)

Research only, in Dev. No runtime change, no Production write, no order. All entries are in-sample: N11 was shaped on 2023–2026. Every change is chosen on three years and scored on the fourth.

## The benchmark (SN02)

- **Rules:**
  - N11's entries and exits, one NIFTY lot in a fixed ₹15,000 wallet;
  - the strike one step further out of the money when a lot costs more than ₹15,000;
  - one position at a time, a ₹3,000 day limit, no 10% cap.
- **Charges:** Zerodha's current list, checked on Nov 12 against zerodha.com/charges and identical to `fno_costs`:
  - ₹20 per order;
  - STT 0.15% on the sell side;
  - NSE transaction charge 0.03553%;
  - SEBI ₹10 per crore;
  - stamp duty 0.003% on the buy side;
  - 18% GST;
  - IPFT.
- **Stress:** +₹205 per lot per trade for slippage.

**Benchmark, Jan 2023 – Oct 2026 (742 sessions):**

| | |
|---|---|
| Profit | +₹1,11,995 (2023 −7,059; 2024 +35,618; 2025 +39,114; 2026 +44,322) |
| Days | 55 won, 63 lost, 624 with no trade |
| Refilled by the owner | ₹91,635 (the sum of losing days), against ₹2,03,630 won on winning days |
| Worst day | −₹2,998 |

## Round 1 (`sn03_run.py`, `results-round1.json`)

- **B, entry filters** (16):
  - the best in-sample was "drop SHIPPED", +₹1,13,861;
  - held out, the picks made +₹1,08,692, under the benchmark;
  - "puts only" cut losing days from 63 to 51 but earned +₹91,454.
- **C, exit changes** (19):
  - quick profits and breakeven stops raise winning days (up to 73) but cut profit;
  - quick profit at +₹500 lost ₹25,412, and at +₹1,000 lost ₹6,219;
  - held out, the picks chose the benchmark 3 of 4 times.
- **D, more trading days** (N11's sister books NO_STAND, R0.85, N15, N25 and the mixes): more losing days and a worse 2023. Held out: +₹88,687.

## Round 2 (`sn03_run2.py`, `results-round2.json`)

- **The 10% day target as "no new trade once the day is up":**
  - +₹1 → +₹96,823;
  - ₹1,500 → +₹1,06,990;
  - the same losing days.
- **Strike** one step in or out of N11's: +₹79k to +₹1.03 lakh.
- **2 lots when affordable:** +₹1,16,374, with more losing days and a worse 2023.
- **Best combination in-sample** ("drop SHIPPED" plus no new trade at +₹1,500): +₹1,14,921. Held out: +₹1,02,288.

## Round 3 (`sn03_run3.py`, `results-round3.json`)

- **Confirm before buying** (wait 1–5 minutes for the option to rise 0–5%): +₹10k to +₹55k. It misses the fast winners.
- **Leave a trade not working after 5–30 minutes:** −₹12,782 to +₹1,05,770, with more losing days (up to 90).
- **Held out:** the benchmark was picked in all four years.

**Verdict after 3 rounds and 66 variants: nothing beats the benchmark on held-out years.**
- N11's own exits already carry its edge.
- Losing days can be cut only by trading less or exiting earlier, and both cut profit by more than they save.

## The wallet: growth stopped after step k

Lots follow the wallet: one lot per ₹15,000, so ₹22,500 → 1 lot, ₹33,750 → 2, ₹50,625 → 3, ₹75,938 → 5, ₹1,13,906 → 7. A step comes after net profit equal to the wallet; the loss limit is 20% of the wallet. All figures at +₹205.

| Stop growing after | Profit | Won on winning days | Refilled | Days won/lost/none | Worst day | Largest fall | Wallet at the end | Steps on |
|---|---:|---:|---:|---|---:|---:|---:|---|
| 0 (farm ₹15,000) | 1,11,995 | 2,03,630 | 91,635 | 55/63/624 | −2,998 | 11,225 | 15,000 | – |
| 1 | 1,09,991 | 2,19,768 | 1,09,777 | 58/70/614 | −4,498 | 13,410 | 22,500 | Nov 5 2024 |
| 2 | 1,58,636 | 3,21,488 | 1,62,852 | 58/70/614 | −6,744 | 21,400 | 33,750 | + Jan 21 2025 |
| 3 | 2,11,670 | 4,05,022 | 1,93,352 | 58/70/614 | −10,117 | 21,400 | 50,625 | + Oct 30 2025 |
| 4 | 2,72,521 | 4,97,643 | 2,25,122 | 58/70/614 | −15,158 | 28,341 | 75,938 | + Mar 23 2026 |
| 5 or more | 2,92,818 | 5,22,584 | 2,29,766 | 58/70/614 | −15,158 | 28,341 | 1,13,906 | + Oct 8 2026 |

- **Only 5 steps happened in four years,** so every cap from 5 up is the same.
- **Step 1 alone is slightly worse than farming.** At ₹22,500 the book still buys one lot, but it buys dearer contracts instead of the out-of-the-money substitute, and its loss limit is larger.
- **Each step multiplies the swings:** the worst day goes from −₹2,998 to −₹15,158, and the refills from ₹91,635 to ₹2,29,766.
- **2023 lost money at every cap.** The start was not easier.

## Next

The frozen forward check in `../2026-11-12-sn02/FORWARD.md` (from Nov 13, ≥ 20 trades) is unchanged and is still the only honest test. Nothing found here changes SN02's rules.
