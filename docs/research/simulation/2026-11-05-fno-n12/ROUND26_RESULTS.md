# Round 26 results. Midday rotation failed the directional screen

Frozen at `1136144`. The five dated windows produced ten signals, two in each window. Every signaled outcome had both required futures marks. The mean signed move was −5.90 points and the median was −12.05 points before applying the cost hurdle. After 15 points per trade, the total was −209.05 points, and only 2026 was positive. The result fell to −290.75 without the strongest contributions. No option pricing or account replay follows from this screen. [Frozen evidence](round26-results.json).

November 5 supplied all 301 futures minute rows from 09:15 to 14:15 under the dated `NIFTY26NOVFUT` contract in the read-only Production export. The move had not stretched far enough from morning value, so the rule signaled nothing. This is a decision check, with no candidate option return assigned.

Run `pytest -q test_round26.py` and `python round26.py` under Dev's Windows engine interpreter. The combined Round 23–26 study suite passed ten tests. No changes to application source, settings, migration, account authority or deployment. Future work should use a distinct, independently plausible mechanism before adding more filters to this window.
