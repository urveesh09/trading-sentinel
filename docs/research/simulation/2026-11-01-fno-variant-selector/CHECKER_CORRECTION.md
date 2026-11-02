# Independent reporting checker correction — no strategy or score change

First statistics crosscheck failed at `np.allclose(halves,c['halves'])`.
All cash/weekly reconciliation checks before it had passed. Cause: the checker
assumed Jan–Jun/Jul–Dec for every year. The pre-score frozen analysis inherits
2024/25 Jan–Jun/Jul–Dec but splits the partial2026 sample into Jan–May and
Jun–Oct28 from the previous studies. Those constants were not changed.

Recorded MAIN_ANCHOR period totals:
11687.6975 / 2047.3735 / 3514.9714 / 294.0039 / 7332.7815 / 47958.6539.
Calendar-half diagnostic instead has2026 totals14877.4127 / 40414.0227.
STRUCT_ANCHOR recorded2026 totals32904.7340 / 28591.7004; calendar-half
diagnostic40449.3652 / 21047.0692. Both candidates have six positive blocks
under EITHER convention, so the acceptance flag and failed primary verdict do
not change. Calendar halves are not substituted for the registered periods.

Corrected only `reporting/verify_statistics.py` to independently reproduce the
frozen period definitions. No replay code, source freeze, models, decision
manifest, reference, strategy, quantity, cash path or results.json was changed.
Do not call this a strategy fix or conceal the failed verification attempt.
