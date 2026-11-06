# N012-B development screen

The single allowed development run under freeze `2758869` returned the following net P&L on the existing ₹250,000 NIFTY-only windows. The partial 2022 window starts in June and the 2026 window ends October 28.

| Window | A | B | B − A |
|---|---:|---:|---:|
| June–December 2022 | −₹10,297.38 | −₹10,297.38 | ₹0.00 |
| 2023 | −₹11,131.51 | −₹11,131.51 | ₹0.00 |
| 2024 | ₹95,040.33 | ₹94,092.18 | −₹948.15 |
| 2025 | ₹65,415.09 | ₹65,415.09 | ₹0.00 |
| 2026 through October 28 | ₹129,167.29 | ₹129,375.62 | ₹208.33 |
| **Sum** | **₹268,193.82** | **₹267,454.00** | **−₹739.82** |

| Arm | Worst daily net | Largest within-window closed drawdown | Net / drawdown | Net / absolute worst day |
|---|---:|---:|---:|---:|
| N11T | −₹5,640.85 | ₹17,809.29 | 14.83 | 46.83 |
| A | −₹5,640.85 | ₹17,504.38 | 15.32 | 47.54 |
| B | −₹5,640.85 | ₹17,504.38 | 15.28 | 47.41 |

Both candidates closed every opened position. B cleared the ₹2,500 annual shortfall limit and failed the aggregate rule. Drop B. The January–May exam roster is N11T, A and informational N11. A's ₹4,051.45 seen-window gain over N11T is a 1.53% improvement. These returns sum separately initialized windows and the ratios use their largest observed downside. The ₹15,000 diagnostic has separate funding and execution requirements. The original Round 30 promotion criteria remain unmet.

The five `n012-b-screen-YYYY.json` outputs retain the paired daily series and the volatility input counts. Six focused tests passed with `python -m pytest test_n012_ab.py test_round30.py -q`. The one allowed development run completed once across the five windows. No unseen option or futures prices were opened. See the [exam protocol](EXAM_2022_H1.md) and [deployed control audit](DEPLOYED_CONTROL.md).
