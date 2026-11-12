# SN Gold v3 forward check (frozen Nov 12, 2026, before Nov 13)

**What is scored:**
- **Entries:** N11's live paper entries from `fno_n11_paper` (NIFTY), sessions from 2026-11-13.
- **Prices:** the research quote archive, read-only, about one look a minute.
- **The v3 rules played on them:**
  - one strike in the money when one lot (at C/G, every lot) fits the wallet, else N11's strike, else one strike further out;
  - a winner up ≥ 25% at N11's exit kept with a 3 × 1-minute-ATR index trail until 15:10;
  - one lot added at +10% when the whole position's stop fits the day's room;
  - 20% day loss limit, current charges, no extra stress (live quotes).
- **Wallets:** A, B, C and growth from ₹15k stopped after step 3, as in `README.md`.

**Rule, once per wallet at ≥ 20 counted trades:** PASS when net > 0 and net without the single best trade > 0. Report the days won, lost and empty, the refills and the worst day.

**What a PASS means:** offered for real money only on the owner's word, by its own runbook. Until then nothing in Production changes.
