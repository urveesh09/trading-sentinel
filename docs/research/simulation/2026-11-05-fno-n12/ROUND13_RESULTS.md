# Late-session price discovery results

The [scope and pass rules](ROUND13.md) were frozen at `a854223`. The 14:46–15:09 trade has a different clock from the cited U.S. result. All five windows are previously seen development data. The comparison used exact option minute observations and modeled bid and ask. It did not infer execution depth from volume.

| Window | Signals | Trades | Signed NIFTY points across signals | Base net | Adverse net |
|---|---:|---:|---:|---:|---:|
| 2022 partial | 41 | 6 | +294.3 | +₹3,244.70 | +₹2,044.70 |
| 2023 | 65 | 42 | −15.3 | −₹11,755.97 | −₹20,155.97 |
| 2024 | 49 | 9 | −268.0 | −₹8,090.55 | −₹9,890.55 |
| 2025 | 43 | 12 | +97.3 | −₹1,524.89 | −₹3,924.89 |
| 2026 available window | 46 | 5 | +253.9 | −₹77.26 | −₹1,077.26 |
| Total | 244 | 74 | +362.2 | −₹18,203.97 | −₹33,003.97 |

**Rejected.** The paper cash-risk cap excluded 170 candidates. All 74 admissions had exact minute exits. Settled trades lost ₹3,403.97 even with no added allowance beyond modeled bid/ask and broker charges. Removing the five best adverse trades reduced the adverse result to −₹38,679.80. The measured index move covers all 244 signals and cannot establish the economics of the cheaper 74 options. Results are conditional on replay admissions, not a combined account equity curve. No selection, full portfolio rerun or trial sizing follows.

On November 5 the observed NIFTY singles already opened at 09:45, 10:51 and 11:30, so the idle-day gate would refuse a new late entry. The actual three singles net stays ₹4,821.18 and the distinct spread stays ₹2,545.91. The exact spread exit path remains unavailable. [November 5 decision evidence](nov5-capital-results.json).

Run `round13.py` with `N12_YEAR` set to each year from 2022 through 2026 under the Dev virtual environment. The five completed receipts bind the original data and control hashes, show the funnel and preserve all admitted tickets. No runtime code or settings changed in this research round.
