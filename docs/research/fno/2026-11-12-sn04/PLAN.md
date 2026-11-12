# SN04: an active ₹15,000 book with N11-style exits (frozen before scoring, Nov 12, 2026)

**The owner's question:** why so many no-trade days, and can the system trade actively and profitably? The SN02 benchmark traded on 118 of 742 sessions.

**Hypothesis:** SN01 lost on active entries partly because of its premium-percentage exits. Its entries with N11's kind of exits might earn:
- an index stop and target in ATR;
- an index trail;
- a time stop;
- the 15:10 flat;
- a premium backstop.

**Setup:**
- **Wallet:** fixed ₹15,000, one lot (the strike one step further out of the money if a lot costs more), one position, ₹3,000 day limit.
- **Costs:** Zerodha's charges (checked Nov 12) plus +₹205 per lot per trade.
- **Data:** the four seen NIFTY years (742 sessions).

**Search:**
- **Entries:** SN01's 7 entry families.
- **Exit genes:** `sn04.py` `EXIT_GENES`.
- **Day genes:** `DAY_GENES`.
- **NULL:** random entries with the same exit and day genes.
- **Budget:** a pool of 4,000 REAL and 2,000 NULL; then 8 generations × 120 per fold (4 held-out years, and ALL) and per kind.
- **Fitness:** the worst training year's net per session. Valid only when the book trades on ≥ 50% of the sessions in every training year.

**Rule, applied once by `score.py`:**
- **Held-out:** the REAL picks are positive in ≥ 3 of 4 held-out years, their sum is > 0, and the sum beats the NULL picks' held-out sum.
- **Final pick** (ALL fold): positive in every year at +₹205.
- **Both → PROMISING:** paper and forward only. Otherwise → NOT PROVEN.

**Also reported:** the days won, lost and empty, the refills, and the wallet stopped after steps 0–5 for:
- the SN02 benchmark;
- the SN04 pick;
- the two combined (N11's signals first; SN04 on days without an N11 signal).
