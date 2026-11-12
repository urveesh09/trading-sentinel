# SN08: N11 with its quality refusals relaxed (Nov 12, 2026): the benchmark stays

**Setup:** `sn08_lab.py` replays N11 through its own lab chain (shipped engine), relaxing:
- the stretched-entry skip;
- the low-ADX-day direction rule (puts only);
- the low-day 14:00 cutoff.

`score8.py` plays each book in the ₹15,000 wallet (one lot, the out-of-the-money substitute, ₹3,000 day limit, Zerodha charges + ₹205).

| Book | 2023 | 2024 | 2025 | 2026 | Total | Won/lost/none | Refilled |
|---|---:|---:|---:|---:|---:|---|---:|
| **N11 (benchmark)** | −7,059 | 35,618 | 39,114 | 44,322 | **1,11,995** | 55/63/624 | 91,635 |
| LATE (no 14:00 cutoff) | −18,350 | 33,089 | 38,187 | 44,925 | 97,851 | 56/68/618 | 1,04,473 |
| WITH_TREND (low-day calls in uptrends) | −4,688 | 12,209 | 15,547 | 38,377 | 61,445 | 47/85/610 | 1,06,734 |
| LATE+WITH_TREND | −15,979 | 12,611 | 12,279 | 40,437 | 49,348 | 50/91/601 | 1,18,168 |
| BOTH (low-day either side) | −13,377 | 22,703 | 33,088 | 36,170 | 78,584 | 73/133/536 | 1,69,491 |
| BOTH+LATE | −29,185 | 13,646 | 29,844 | 34,772 | 49,077 | 76/147/519 | 1,97,149 |
| NOSTRETCH | −17,792 | 17,798 | 12,807 | 44,222 | 57,035 | 59/87/596 | 1,43,783 |
| NOSTRETCH+LATE | −29,847 | 16,878 | 11,880 | 42,176 | 41,087 | 59/96/587 | 1,63,292 |
| ALL relaxed | −25,732 | −27,828 | 772 | 29,311 | −23,477 | 81/169/492 | 2,47,851 |

- **Held out**, choosing among these on three years, the benchmark is picked for every year (`results.json`).
- **Each relaxation adds trading days and losing days faster than profit.** N11's quality rules are where its edge is.
