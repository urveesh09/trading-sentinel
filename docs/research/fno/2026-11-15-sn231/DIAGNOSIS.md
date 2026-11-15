# SN234: why Gold v6 has bad months (from SN231–SN233), and the amendment (written before any SN235+ number)

## What the ledger shows (SN231, Jan 2023 – Oct 2026, 46 months; Gold v5 ₹30k growing + WK-H 2 lots)

| | Net | Months positive | Worst month | Mean month | SD month |
|---|---:|---:|---:|---:|---:|
| SN Gold v5 | +8,50,883 | 25 of 46 (7 with no trade) | −38,531 | 18,497 | 40,207 |
| WK-H | +3,45,256 | 29 of 46 | −31,830 | 7,506 | 19,975 |
| **Gold v6** | **+11,96,139** | **31 of 46** | **−38,228** | 26,003 | 45,650 |

**The 15 bad months:**
- 2023: Jan, Feb, Jun, Jul, Aug, Sep, Oct, Dec;
- 2024: Mar, May, Oct;
- 2025: Dec;
- 2026: Feb, Apr, Aug.

**What lost in them:**
- both legs lost in 8 of the 15;
- WK-H lost alone in 5, and Gold lost alone in 2;
- WK-H's share of the loss is −₹1.54 lakh, Gold's −₹1.11 lakh.

**The refill side.** The owner refills every red day, and even good months refill a lot: in May 2024, ₹71k was refilled against ₹33k banked.

## Why (SN232–SN233)

1. **Quiet months: costs, not direction.**
   - Bad months have lower realised volatility (10.6% against 12.1% annualised), fewer 1% days and fewer gaps.
   - Gold trades on 0–4 days in them and wins few.
   - WK-H loses small amounts even when options were priced above the moves that followed (implied ÷ realised 1.2–1.5 in Jun–Sep 2023). The cause is **₹5–8k a month of futures hedge charges** on a small premium (0.7–0.8% of the index).
   - Over DEV, **hedge charges were ₹1.42 lakh per option lot against a net of ₹2.12 lakh.**
2. **The last hour of expiry day.**
   - After the 14:30 freeze the hedge stands still. The 14:30 → settlement part of every week sums to **−₹83,224 per lot on DEV** (8 losing weeks decided by it).
   - May 16 2024, −₹24.6k per lot: the index fell below the strike, the hedge went short at 14:15, then the market rallied 340 points into the close.
3. **Gaps:** 27 losing weeks across the five samples (−₹1.47 lakh per lot). A futures hedge cannot trade through an overnight gap.
4. **Moves above what options priced:** 32 losing weeks (−₹1.0 lakh).
5. **Gold's own losing months** (14, plus 7 with no trade) are the trend book's lumps. Gold v5 stays unchanged, by the owner's word, so they can only be offset by other legs.

## Amendment (adds candidates; nothing above changes)

Added to SN235–SN243, scored under the frozen Q1–Q5 rule:
- **SN235, expiry afternoon:**
  - (a) keep the 15-minute checks through 15:15 on expiry day (no 14:30 freeze);
  - (b) flatten the futures at 14:30 and leave the straddle to settle;
  - (c) keep checking every 5 minutes from 14:30 to 15:15 on expiry day.
- **SN236, hedge cost** (on WK-H's 2 lots):
  - band 0.8 / 1.0 with checks every 15 / 30 minutes;
  - a **synthetic hedge**: an ATM call bought and put sold (or the reverse) of the same weekly expiry instead of futures. It is priced at the index plus carry; each lot-order is charged as two option legs (model spread at the ATM premium, ₹100 stress per leg-lot, option charges, STT on the sold leg's premium); remaining lots settle at intrinsic;
  - plus WK-H with a second hedged structure (the SN236 already in the plan).
- **SN237, the daily hedged straddle:** as planned (more, shorter positions: law of large numbers).
- The other studies are unchanged.

**Engine:** `wk4.py` re-implements `wk3.hedge_path` with these options. With the defaults it must reproduce `wk3` exactly (checked in SN235 before any variant is scored).
