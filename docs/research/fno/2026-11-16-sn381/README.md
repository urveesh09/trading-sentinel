# SN381–SN395: make the opening trade honest, explain it, look for a second opening witness, close Gold's 2022 exam (Nov 16, 2026)

**Owner (Nov 16):** the auditor's SN381–SN390 (`docs/SN381_SN390_RESEARCH_BRIEF.md`, `c1f4fcbd`) plus five own slots. Plan `c6e99cee`. Each script was committed before it ran; crashes were fixed before any number and disclosed (logs kept).

**Status:** research only. No runtime, broker, Production or order change. No forward session has been scored; the first is Nov 17.

**The auditor's three flaws: all confirmed in the code.**
- **Cash:** the one-strike fallback was accepted at any premium.
- **Timing:** a fallback signal could use a packet received after 09:16:00.
- **Controls:** the candidate's mean over all fills was compared with the controls' shared subset.

All three are fixed in `fw7a.py`, and fw5 / fw7 are kept as frozen.

## Results (in the order run)

| SN | Question | Result |
|---|---|---|
| **381** | Could the opening trade really be bought? | **Companion audit `fw7a.py`, with 9 synthetic tests passing:**<br>• walked one-lot cost plus charges ≤ ₹15,000;<br>• a buy limit at ask + 2 ticks, never above the room;<br>• the signal only from packets received before 09:16:00;<br>• ledger states;<br>• a paired judge with skips scored as 0.<br>Nov 16: the capped order misses as the ask runs up |
| **382** | SN376's opening lead under honest rules | **Fragile.**<br>• The cash rule removes 25 of 171 trades (SN376 had traded them over the room).<br>• Per session **+₹45.6 at ₹205 (−₹7 without the best day), −₹137.5 at ₹400.**<br>• Match-row days −₹14; fallback days +₹124.<br>• Before NSE's Sep 7 change +₹138, **after it −₹447** (27 sessions).<br>• **Robust: ITM beats ATM by +₹122 a trade on the same days (standard error 39) in every split** |
| **387** | Close Gold's 2022 exam | **Closed.**<br>• Of the 52 sessions without options, 51 are expiry days and 1 a data gap.<br>• **N10 sheet D yes:** one ₹2.5 lakh account 2022–26, with carry wiring checked against N10's stored account. N10 with WATCH ends **₹4,41,853** against CUSHION ₹4,15,120, never below 86.9% of its best.<br>• **N10's 2022 sheet passes A–D; N11's fails A and B: by the sheets, N10 retry is the lead paper candidate** (owner's call) |
| **392** | Gold's signal source over five years (₹30k) | **2022 (out of sample):** deployed N11 + R0.85 −₹15,281; NO_STAND = N10 +₹4,681.<br>**2023–26 (in sample):** deployed ₹8,50,883; N10 ₹7,16,978.<br>**2022–26:** deployed ₹7,36,894; N10 ₹7,16,165 (₹3,81,297 against ₹2,93,055 at ₹400).<br>The stand-aside's gain is in-sample; its one unseen year cost ₹20k. **No change** |
| **388** | Where the stand-aside helped or hurt | 21 fires; 15 skipped losers, but **6 big winners skipped** (net cost ₹5,449). It helped on EFF and hurt on TPB / SHIPPED; it stayed on up to 11 sessions in a row. A trend book's filter misses the recovery winner |
| **383** | What the ITM option buys | **Mostly a bigger directional bet.** 2-ITM against ATM: +₹95 before stress = delta +₹77 + vega +₹23 + theta +₹3 − costs ₹7. Per rupee of debit 2.07% against 1.84%. Gamma residual about +₹160 |
| **384** | Cut a failed opening at 09:36 | **No.** −₹14 against the hold (standard error 61); 7 of 29 exits were winners |
| **385** | Cash-auction agreement | **Closed on coverage** (84 index pre-open sessions, below the 100 needed). 9 roll dates, anecdotal |
| **391** | The indicative path (after Sep 7) | 9 sessions (building +₹1,006 / fading −₹729): too few. Recorded forward in fw7a |
| **393** | Auction conviction | **The opposite:** large auctions −₹446 against small +₹102 |
| **394** | Cheap vs rich opens | **The strongest development result.** On causally cheap opens (overnight IV jump below the lower tercile): **+₹396 / +₹199 per session at ₹205 / ₹400** (73 sessions); rich −₹90 / −₹362.<br>Robustness gate passed: permutation p 0.031 at both stresses; without the best day +₹277 / +₹80; positive in both protocol periods and both signal sources.<br>Caveat: the best of ~10 splits (adjusted p ~0.3).<br>→ **frozen forward as `fw9.py`** |
| **389** | Cash through a bad start | **Profit-only from Jan 2022:** ₹525 a session at ₹205 (₹163 at ₹400), a **21-month dry spell**, ₹20,539 of outside money.<br>**A paid ₹15,750 a month:** ₹5.31 lakh of outside money from Jan 2022 (₹7.90 lakh at ₹400); a median ₹1.97 lakh over 52 starts; no start needs none.<br>Gross internal refills (₹5–6 lakh) recycle the same cash |
| **395** | Reserve by block bootstrap (10,000 two-year paths) | **Profit-only:** outside cash 90th percentile ₹18,790 / 95th ₹28,554 (₹205); 64.5% of paths need none; dry spells median 10 / 90th percentile 17 months; median 2-year payout ₹55,995.<br>**A ₹15,750 salary:** outside cash median ₹2.87 lakh, roughly ¾ of it the owner's own money in the first two years |
| **386** | Signed option pressure from packets | **Frozen forward as `fw8.py`:** packet-level signing (91.7% of volume signable on Nov 16), earlier-only calibration, unsigned / shifted / coin controls |
| **390** | Survivors through one wallet | **Not triggered:** no development survivor as a trade; fw7a / fw8 / fw9 must pass forward first |

## Forward queue (scored once, after SN300a's window; no forward P&L opened)
- `sn351/fw5.py` and `sn381/fw7a.py` (the companion with paired controls), on SN300a's first 20 sessions.
- `sn366/fw7.py`, the frozen original, beside them.
- `sn381/fw9.py`: cheap-open auction ITM; at 15 cheap fills or 60 sessions.
- `sn381/fw8.py`: signed flow; 20 sessions (5 calibrate).
- `sn351/fw6.py`: from Dec 7; needs the recorder to 15:46.

## Lessons
1. **Honest execution rules cut the opening edge to break-even.** The cash rule, a price cap, receipt-time signals and paired controls together turn +₹67 into +₹46 a session (−₹7 without the best day), and it is negative after NSE's September auction change. **The ITM-versus-ATM edge is the robust part,** and it is mostly a larger delta.
2. **The one promising combination is direction + ITM + a cheap open** (no overnight volatility jump). It passes its permutation gate but is the best of about ten splits, so it is a forward test.
3. **Gold's stand-aside filter is unproven out of sample.** It cost ₹20k in 2022 by skipping the few big winners. **N10 retry is the 2022 sheets' lead**; Gold's deployed signals still lead over 2022–26 on in-sample years.
4. **The wage needs capital, not cleverness.** From ₹60k, profit-only pays about ₹525 a session on a bad start with dry spells up to 21 months. A fixed ₹750 a session needs ₹2–5 lakh of the owner's own money in the first years.
5. **Packet-level data makes flow measurable** (92% signable, against minute snapshots' crude signs). The forward recorder is now the main research asset.

## Rule register (every rule tried this round)
- SN382: the 09:16 auction ITM leg (depth 2 → 1, ₹15k room), 20 / 60 minutes; ATM and coin-ITM controls.
- SN383: ATM / 1-ITM / 2-ITM decomposition (diagnostic).
- SN384: the 09:36 half-gap give-back exit.
- SN385: cash-auction agreement (closed on coverage).
- SN391: indicative drift.
- SN393: auction volume above / below its trailing median.
- SN394: cheap / middle / rich overnight-IV-jump terciles, and skipping rich.
- SN387: N10 sheet D carry.
- SN392: Gold fed by NO_STAND or N10 retry.
- SN389: profit-only vs a ₹15,750 salary with outside deposits.
- SN395: the same under a block bootstrap.
- Forward: fw7a, fw8, fw9.
