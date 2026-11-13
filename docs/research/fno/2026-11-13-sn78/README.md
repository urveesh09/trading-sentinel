# SN78: a 1-second book for Gold's empty days (Nov 13, 2026): NOT PROVEN, picks frozen for the next months

**Data:** the download agent's verified 1-second archive (`nifty-daily-1second-20261113.zip`, copied sealed into `_local/`, sha256 in `_local/zip.sha256`).
- NIFTY index plus the opening-ATM call and put, 77 sessions Apr 6 – Jul 27, 2026, including 16 expiry days. Apr 2 is partial and dropped.
- Gold (v5) traded on only 8 of these days; 71 are Gold-free by the rule known before the open (ADX < 30, or an expiry day).

**Book (`sn78.py`):**
- **Signals:** on 30-second index bars: opening-range break held 10–30 s, momentum burst, time-weighted average price break, stretched fade.
- **Fills:** buy the ATM call or put at that second's ask.
- **Exits:** checked every second (stop, target, trail, time); flat 15:00, or 13:30 on expiry days.
- **Money:** one lot, ₹30k day limit, charges + stress.
- **Selection:** choose on Apr–May (37 days), score once on Jun–Jul (40), against random entries with the same exits.

**Result:**

| Stress | Pick (chosen on Apr–May) | Apr–May | Jun–Jul | Jun–Jul, Gold's empty days | Random pick, Jun–Jul |
|---|---|---:|---:|---:|---:|
| +₹100 | TWAP break 1 ATR, stop 20%, target 30%, 45 min, 1 a day | +13,193 | **−4,096** | −6,583 | −7,905 |
| +₹0 | 2-bar momentum z 1.5, stop 20%, target 15%, 45 min, 3 a day | +17,100 | **−8,292** | −3,682 | −26,131 |

On Apr–May, random entries were as profitable as any rule (300–700 random configurations positive).

**What it teaches:**
- Second-level data gives exact fills and paths, but no edge on Gold's empty days within these costs.
- The momentum pick beat random out of sample at zero stress, so it may carry a small signal.

**Frozen for an unseen check:** both picks above, unchanged, are to be scored once on the next 1-second months the download agent finishes (sessions before Apr 2, 2026). That check is the only fair test left for them.
