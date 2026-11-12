# SN09: option open-interest entries on N11's empty days (frozen before scoring, Nov 12, 2026)

**Why:** SN04–SN08 show that N11's entries and quality rules are its edge, and that every price-only way of filling its empty days loses. Option OI, where writers add positions strike by strike, is information no SN or N book has used. The candles carry it as a snapshot every 3 minutes.

**Search** (`sn09.py`):
- **Families:** PCRD, FLOW, WALLB and WALLR (genes in `OI_GENES`).
- **Setup:** SN06's ADX/DMI gate options, SN04's index exits, bias none/puts/calls.
- **Days:** only sessions without an N11 signal.
- **Wallet:** ₹15,000, one lot, the out-of-the-money substitute, ₹3,000 day limit, Zerodha charges + ₹205.
- **Activity floor:** ≥ 20% of those sessions in every training year.
- **NULL:** random entries behind the same gates and exits.
- **Budget:** a pool of 3,000 REAL and 1,500 NULL; 6 generations × 100 per fold and kind.
- **Fitness:** the worst training year's net per session.
- **Causality:** checked by perturbing OI and price after a cut.

**Rule (`score.py`, once):**
- Held out, the REAL picks are positive in ≥ 3 of 4 years, their sum is > 0, and the sum is > the NULL's.
- The ALL pick is positive in every year.
- Both → PROMISING (paper/forward only). Otherwise NOT PROVEN.

**Reported either way:**
- the combination (N11 on its days, the held-out SN09 pick on the others) per year;
- the per-year wallet-stop table.

**Also after the verdict** (`confirm.py`): OI flow as a confirmation filter on N11's own trades, chosen on three years and scored on the fourth.
