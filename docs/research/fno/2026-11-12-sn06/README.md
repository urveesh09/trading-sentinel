# SN06: N11's entry ingredients without its big-money rules (Nov 12, 2026): NOT PROVEN

**Freeze:** `77c3c49b`. **Search:** 15,600 rule sets:
- setups on 5-minute or 1-minute bars;
- yesterday's daily ADX gate (from all 966 trading days);
- the DMI direction, N11-style index exits;
- no stand-aside, kill switches or premium cap;
- ₹15,000, one lot, ₹3,000 day limit, Zerodha charges + ₹205;
- an activity floor of ≥ 25% of sessions.

**Rule result (`results.json`):**

| | Held-out years positive | Held-out sum |
|---|---:|---:|
| SN06 picks | 1 of 4 (2026) | **−₹62,251** |
| Random entries, same gates and exits | – | −₹1,50,624 |

- **First active search that clearly beats random held out:** the gate and the 5-minute setups carry information, but not enough to pay for the trades.
- **The ALL-fold pick (in-sample):** a 5-minute EMA 9/34 cross, calls only, on ADX < 30 days, ITM1, one trade a day. Results: −433 / +25,202 / −2,574 / +19,974 = +₹42,169, trading on 51% of sessions.

**The combination, scored honestly after the verdict (`combo_heldout.py`):** N11 on its days, SN06 on the rest.

| | Four years |
|---|---:|
| In-sample combination | +₹2,00,937 |
| Combination with each year's SN06 pick chosen without that year | **+₹68,243** |
| Benchmark alone | +₹1,11,995 |
| Held-out SN06 on N11's empty days | −₹43,751 |

**Benchmark (SN02) by year, wallet stopped after step k** (one lot per ₹15,000, +₹205), shown as profit / refilled:

| Stop after | 2023 | 2024 | 2025 | 2026 | Total | Refilled |
|---|---|---|---|---|---:|---:|
| 0 | −7,059 / 20,564 | 35,618 / 14,915 | 39,114 / 34,651 | 44,322 / 21,505 | 1,11,995 | 91,635 |
| 1 | −7,059 / 20,564 | 35,506 / 15,027 | 30,932 / 45,407 | 50,611 / 28,780 | 1,09,991 | 1,09,777 |
| 2 | −7,059 / 20,564 | 35,506 / 15,027 | 46,673 / 74,060 | 83,516 / 53,202 | 1,58,636 | 1,62,852 |
| 3 | −7,059 / 20,564 | 35,506 / 15,027 | 46,961 / 76,830 | 1,36,262 / 80,932 | 2,11,670 | 1,93,352 |
| 4 | −7,059 / 20,564 | 35,506 / 15,027 | 46,961 / 76,830 | 1,97,113 / 1,12,702 | 2,72,521 | 2,25,122 |
| 5 | −7,059 / 20,564 | 35,506 / 15,027 | 46,961 / 76,830 | 2,17,409 / 1,17,346 | 2,92,818 | 2,29,766 |

**The benchmark stays.**
