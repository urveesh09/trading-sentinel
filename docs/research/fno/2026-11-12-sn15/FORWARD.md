# SN15 forward check: three wallet versions of N11's entries (frozen Nov 12, 2026, before the Nov 13 session)

This sits beside `../2026-11-12-sn02/FORWARD.md` (version A) and uses the same source, rule and limits.

- **Source:** Production's one-lot paper record `fno_n11_paper` (NIFTY), closed rows from 2026-11-13, exported read-only. Lots and substitutes are priced from the research quote archive, read-only.
- **Versions:**
  - **A:** ₹15,000, 1 lot, the strike one step out of the money when a lot costs more than ₹15,000.
  - **B:** ₹20,000, 1 lot, the same substitute rule at ₹20,000.
  - **C:** ₹30,000; 2 lots when yesterday's daily ATR% is at or above its median of the prior sessions (SN13's rule), else 1; the substitute rule at the wallet's limit.
- **For every version:** one position at a time, a day loss limit of 20% of the wallet (later trades that day skipped), no 10% cap, the wallet fixed and refilled.
- **Charges:** the shipped model (current Zerodha rates), no extra stress, because these are live quotes.
- **Rule, scored once per version at ≥ 20 counted trades:** PASS when net > 0 and net without the single best trade > 0.
- Also reported: skipped trades by reason, the days won, lost and empty, the refills and the worst day.
- **What a PASS means:** a version may be offered for real money on the owner's word, by its own runbook. Every number in SN12–SN14 is in-sample.
