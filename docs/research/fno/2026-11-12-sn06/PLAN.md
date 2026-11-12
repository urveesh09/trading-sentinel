# SN06: N11's entry ingredients without N11's big-money rules (frozen before scoring, Nov 12, 2026)

**The owner:** N11's entries are the gold. Make SN06 smarter and more active for the small wallet, learning from N08–N012. 10-second data is optional.

**Search** (`sn06.py`):
- **Setups:** the SN01 families, on closed 5-minute bars or on 1-minute bars.
- **Gates:** yesterday's daily ADX (none, ≥ 20, ≥ 25 or ≥ 30 HIGH; < 25 or < 30 LOW), computed from every trading day of the sealed datasets.
- **Direction:** optionally only in the daily DMI direction; bias none, puts or calls.
- **Exits:** N11-style index exits (SN04's genes).
- **No big-money rules:** no stand-aside, kill switches or premium cap. One position, ₹15,000, one lot with the out-of-the-money substitute, ₹3,000 day limit, Zerodha charges + ₹205 per lot per trade.
- **Activity floor:** trades on ≥ 25% of sessions in every training year. N11 trades on about 16%.
- **NULL:** random entries behind the same gates, direction and exits.
- **Budget:** a pool of 4,000 REAL and 2,000 NULL; then 6 generations × 120 per fold and kind.
- **Fitness:** the worst training year's net per session.

**Rule (`score.py`, applied once):**
- Held out, the REAL picks are positive in ≥ 3 of 4 years, their sum is > 0, and the sum is > the NULL's.
- The ALL-fold pick is positive in every year.
- Both → PROMISING (paper/forward only); otherwise NOT PROVEN.

**Reported either way:** per-year tables with the wallet stopped after steps 0–5 (profit and refills by year, days won, lost and empty) for:
- the SN02 benchmark;
- the SN06 pick;
- the two combined (N11's signals on its days, SN06 on the rest).
