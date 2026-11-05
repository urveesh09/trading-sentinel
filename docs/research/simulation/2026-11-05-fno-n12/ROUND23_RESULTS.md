# Round 23 results. The early window still affects the later book

Both NIFTY arms were frozen at `7554e46` before scoring. The N11 and N11T trades matched the prior receipts in every window. The strategy tests passed three checks. Every early position settled before 09:45.

| Window | N11T net | Gap repair net | Gap hold net |
|---|---:|---:|---:|
| Partial 2022 | −₹10,602.29 | −₹10,439.76 | −₹13,070.23 |
| 2023 | −₹11,536.98 | −₹11,536.98 | −₹17,752.42 |
| 2024 | +₹95,040.33 | +₹94,255.86 | +₹90,292.36 |
| 2025 | +₹63,478.57 | +₹63,478.57 | +₹60,785.40 |
| Available 2026 | +₹127,762.74 | +₹127,268.08 | +₹126,484.04 |
| Five fresh ₹250,000 wallets | +₹264,142.37 | +₹263,025.77 | +₹246,739.15 |

**Rejected.** Gap repair opened three trades. It left the subsequent native P&L unchanged to rounding precision and still cost ₹1,116.61. Gap hold opened 25. Its own trades lost about ₹1,813 and changes to the rest of the account cost about ₹15,591. In 2025 the early hold orders earned ₹2,259.79 while the later native path gave up ₹4,952.96. Moving the exit before 09:45 frees the open position slot, while settled P&L and risk usage carry forward. Removing the five best incremental dates left the arms down ₹1,279.14 and ₹25,610.41 respectively. Neither qualified for doubled costs or forward validation. [Gate calculations](round23-gates.json).

**November 5.** The Production read-only store at `398d44ad` contained 22 `15minute` cash `NIFTY 50` bars on the date and zero `minute` rows under the cash ticker or instrument token. The export includes minute futures bars. It cannot establish the opening cash close at 09:19 or 09:24. Candidate P&L is unavailable. The recorded comparison is ₹4,821.18 for NIFTY singles and ₹2,545.91 for the separately managed spread. [Recorded comparison](nov5-capital-results.json).

Re-run in Dev with `N12_YEAR` set to each value from 2022 through 2026 and the Windows engine Python, using `pytest -q test_round23.py` and `python round23.py`. The runner refuses to overwrite receipts. `round22_compare.compare` applies the frozen account gates to either named arm. No application source, settings, migrations, orders, push or deployment.
