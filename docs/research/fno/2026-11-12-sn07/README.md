# SN07: the real N11 book with its big-money rules switched off (Nov 12, 2026)

**Setup:**
- `sn07_lab.py` replays N11 through its own lab chain (shipped engine), with settings per book:
  - **S1:** kill switches, drawdown halt and premium cap off, no stand-aside;
  - **S2:** S1 plus 6 trades a day;
  - **S3:** S2 plus 3 open positions.
- **Parity:** the stock N11 replay reproduces the stored N11 trades exactly in all four years.
- **Scoring:** `score7.py` plays each book's trades in the ₹15,000 wallet (one lot, the out-of-the-money substitute, ₹3,000 day limit, Zerodha charges + ₹205).

**Wallet results:**

| Book | Engine trades | 2023 | 2024 | 2025 | 2026 | Total | Won/lost/none | Refilled |
|---|---:|---:|---:|---:|---:|---:|---|---:|
| N11 (benchmark) | 181 | −7,059 | 35,618 | 39,114 | 44,322 | **1,11,995** | 55/63/624 | 91,635 |
| S1 rules off | 244 | −30,644 | 35,618 | 40,991 | 44,322 | 90,287 | 64/90/588 | 1,29,693 |
| S2 + 6 a day | 249 | −33,015 | 35,618 | 40,991 | 44,322 | 87,916 | | 1,32,065 |
| S3 + 3 open | 250 | −33,015 | 35,618 | 40,991 | 44,322 | 87,916 | | 1,32,065 |

- **The extra trades are almost all from 2023,** where the stand-aside had held back 52 trades, and they lose.
- **N11's no-trade days come from its setups not appearing,** not from its money rules. The stand-aside protects a small wallet too.

**Speed** (`speed.py`, `results-speed.json`): the replay buys at the first minute after the 5-minute bar closes (49 of 74 trades in 2025).
- Buying at the bar's own closing minute (no delay): +₹1,08,818. No gain.
- The "2 minutes earlier" row buys before the bar is complete. It is look-ahead and invalid.
