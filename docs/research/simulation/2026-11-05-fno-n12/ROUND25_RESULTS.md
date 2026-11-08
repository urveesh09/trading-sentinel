# Round 25 results. The futures substitute cost more

The diagnostic was frozen at `03c5adc`. All 209 N11T trades matched positive-volume dated futures marks at entry and exit. The unrestricted one-lot futures counterfactual showed ₹312,916.50 gross and approximately ₹77,502 net at two points per side, versus the options' ₹264,142 net. Futures fees, taxes and assumed fills consumed about ₹235,414. The result is a fixed-clock payoff attribution using today's cost schedule, with the option policy still defining the exit clocks. [Historical receipt](round25-results.json).

The risk screen accepted six positions at the 10% and 13% margin proxies. Replacing those positions reduced the five-window total by ₹3,855.06 at the original friction and ₹5,414.69 at four points per side. At the 16% proxy it accepted five and still cost ₹3,392.31. No margin or full-account performance claim follows. The test gives no reason to move paper capital into this futures substitute. [Cost model](ROUND25.md).

**November 5.** An unrestricted comparison on the three recorded admissions would have added ₹1,633.41 on that day's held prices and modeled fills. Zero trades met the entry screen. The screened diagnostic therefore leaves the recorded ₹4,821.18 of singles P&L alone. The one-day favorable unrestricted result differs from the five-window evidence. [November 5 receipt](round25-nov5.json).

In Dev, `pytest -q test_round23.py test_round24.py test_round25.py` passed eight tests, and `python round25.py` completed after validating the manifests, data and controls. Research files only. No settings, migration, account authority, expiry code, push or deployment changes.
