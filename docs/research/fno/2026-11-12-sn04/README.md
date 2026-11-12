# SN04: active entries with N11-style exits (Nov 12, 2026): NOT PROVEN

**The question:** the owner asked why the SN02 benchmark has 624 no-trade days out of 742, and wanted an active, profitable book. The plan was frozen at `8bf68ae2`.

**What was searched:**
- SN01's 7 entry families, trading on at least 50% of sessions;
- with N11-style exits: index stop and target in ATR, index trail, time stop, 15:10 flat, premium backstop;
- in the ₹15,000 wallet, one lot, Zerodha charges + ₹205 per lot per trade;
- 15,600 rule sets, chosen on three years and scored on the fourth, against random entries with the same exits.

**Result (`results.json`):**

| | Held-out years positive | Held-out sum |
|---|---:|---:|
| Active entries | 0 of 4 | **−₹1,51,769** |
| Random entries, same exits | – | −₹1,42,961 |

- **Final pick:** negative in all four years (−₹13k to −₹20k a year), trading on about 55% of sessions.
- Of 4,000 random REAL rule sets, none was positive in every year.

**What it means:** N11's edge is in **which trades it takes** (rare, gated setups), not in its exits. Filling the no-trade days with active entries loses about what random entries lose.
