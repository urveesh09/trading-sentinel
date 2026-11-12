# SN05: more days from the house strategy library, and wallet stops per strategy (Nov 12, 2026)

**What was tested:**
- The O30m library: 136 strategies, replayed always-on by the shipped engine on NIFTY 2024–2026, including 20 random-entry books.
- Each was played in the ₹15,000 wallet: one lot, the out-of-the-money substitute, one position, ₹3,000 day limit, Zerodha charges + ₹205.
- **The procedure:** a greedy priority list, N11 first, then library books added while they raise the training years. Chosen on two years and scored on the third. The same procedure with only the random books is the NULL.
- **Files:** `sn05.py` → `results.json`.

**Result:**

| | 2024–2026 |
|---|---:|
| N11 alone, the best of all 137 | **+₹1,19,054** |
| The next best, `REF\|LIVE` | +₹20,426 |
| `L\|PDL_BREAK\|4` | +₹12,261 |
| Most others | lose |
| Held-out portfolio (books added) | +₹1,08,411, worse than N11 alone |

- The random books were never added.
- With all three years, the procedure adds nothing.

## Wallet stopped after step k, per strategy

`caps.py` → `results-caps.json`. Jan 2023 – Oct 2026, 742 sessions, one lot per ₹15,000 of wallet, +₹205.

| Strategy | Stop after | Profit | Won/lost/no trade | Refilled | Worst day |
|---|---|---:|---|---:|---:|
| A benchmark | 0 / 2 / 3 / 5 | 1,11,995 / 1,58,636 / 2,11,670 / 2,92,818 | 55/63/624 → 58/70/614 | 91,635 → 2,29,766 | −2,998 → −15,158 |
| B without SHIPPED | 0 / 2 / 3 / 5 | 1,13,861 / 1,70,063 / 2,28,908 / 3,43,173 | 56/58/628 → 59/65/618 | 82,896 → 2,67,377 | −2,998 → −22,730 |
| C puts only | 0 / 2 / 3 / 5 | 91,454 / 1,44,599 / 1,80,719 / 2,23,108 | 46/51/645 → 49/57/636 | 77,216 → 1,50,367 | −2,998 → −10,099 |
| D benchmark + no new trade at +10% | 0 / 2 / 3 / 5 | 1,06,990 / 1,51,811 / 1,94,174 / 2,46,331 | 55/63/624 → 59/69/614 | 91,635 → 2,24,289 | −2,998 → −15,158 |

B and C are in-sample picks: on held-out years neither beat A (SN03).

## Across SN01–SN05

About 37,000 rule sets were tested. The more a book trades outside N11's setups, the more it loses after charges.
