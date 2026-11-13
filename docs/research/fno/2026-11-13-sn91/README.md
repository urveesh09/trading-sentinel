# SN91: how many rupees of wallet behind each lot (Gold v5, from ₹30k) (Nov 13, 2026)

**Question (the owner):** is the per-year growth just size, and does more money mean more profit?

**Answer:**
- Fixed wallets are identical every year (refilled).
- Growth wallets are ONE continuous account (not reset each year), so later years trade more lots.
- The fair per-year comparison is one lot (v5 at ₹15k, 1 lot: 2023 +397, 2024 +52,158, 2025 +48,506, 2026 +50,094). The edge is per lot and steady from 2024.

**Test (`sn91.py`, `results.json`):** lots = floor(W / X), halved on low-volatility days.

| ₹ per lot | Fixed ₹30k net | Grow from ₹30k, stop after 3: net | Worst day |
|---|---:|---:|---:|
| 10,000 | 2,82,344 | 8,54,671 | −22,536 |
| 12,500 | 2,80,508 | 8,24,186 | −22,536 |
| **15,000 (deployed)** | **2,80,508** | **8,50,882** | **−21,113** |
| 20,000 | 2,13,890 | 6,60,126 | −20,830 |

**What it teaches:**
- More leverage per rupee adds nothing: what the wallet can buy at real premiums, and the 20% day stop, already cap the lots.
- Less leverage costs profit.
- ₹15k per lot is on the plateau. More profit comes from more starting money (linear, with proportionally bigger worst days and refills), not from more lots per rupee.
