# SN381–SN395: make the opening trade honest, explain it, look for a second opening witness, close Gold's 2022 exam (Nov 16, 2026)

**Owner (Nov 16):** the auditor's SN381–SN390 (`docs/SN381_SN390_RESEARCH_BRIEF.md`, `c1f4fcbd`) plus five own slots. Plan `c6e99cee`.

**Status:** research only. No runtime, broker, Production or order change. No forward session has been scored.

**The auditor's three flaws: all confirmed in the code and fixed in the companion `fw7a.py`.**
- **Cash:** the one-strike fallback was accepted at any premium.
- **Timing:** a fallback signal could come from a packet received after 09:16:00.
- **Controls:** the candidate's mean over all fills was compared with the controls' shared subset.

## Results (in the order run)

| SN | Question | Result |
|---|---|---|
| **381** | Could the opening trade really be bought? | **Companion audit `fw7a.py` frozen, with 9 synthetic tests passing.** It adds:<br>• the walked one-lot cost plus charges ≤ ₹15,000;<br>• a buy limit at ask + 2 ticks, never above the room;<br>• the signal only from packets received before 09:16:00 (MATCH / FIRST_TRADE);<br>• ledger states;<br>• a paired judge with skips scored as 0.<br>Nov 16 plumbing: the capped 2-ITM order misses as the ask runs up (uncapped fw7 had filled higher). fw5 / fw7's frozen verdicts are still produced beside it |
| **382** | Does SN376's opening lead survive honest rules? | **No, it is fragile.**<br>• The cash rule removes 25 of 171 trades: SN376 had traded all 25 above the ₹15,000 room.<br>• Per session: **+₹45.6 at ₹205 (−₹7 without the best day), −₹137.5 at ₹400**.<br>• Match-row days: −₹14.1. 09:15-open fallback days: +₹123.7.<br>• Before NSE's Sep 7 change +₹137.9; **after it −₹447.1** (27 sessions).<br>• Weekly: 20 of 43 weeks positive (mean +₹181, standard error ₹621).<br>• **Robust part: ITM beats ATM by +₹122 a trade on the same days (standard error 39) in every source and period.**<br>The expression is real; the direction is not reliable |
| **387** | Close Gold's 2022 exam | **Closed.**<br>• **Dates:** of the 52 sessions without options, 51 are weekly expiry days (the house format) and 1 is a data gap (Jan 12, 2022).<br>• **N10 sheet D YES:** one ₹2.5 lakh account Jan 2022 – Oct 2026 (carry wiring checked first: N10's stored 2023-start account reproduced trade for trade). N10 with WATCH ends **₹4,41,853** against CUSHION ₹4,15,120, and never closes below 86.9% of its best.<br>• **N10's 2022 sheet passes A–D; N11's fails A and B.** By the sheets' own words N10 retry, not N11, is the lead paper candidate (one more year; the owner's decision) |
| **392** | Gold's signal source over five years (₹30k) | Gold v5 by source, ₹205 (₹400):<br>• **2022 alone (the only out-of-sample year):** deployed N11 + R0.85 **−₹15,281** (−₹23,511); NO_STAND = N10 retry **+₹4,681** (−₹6,863).<br>• **2023–26 (in sample):** deployed ₹8,50,883; NO_STAND ₹7,08,148; N10 ₹7,16,978.<br>• **2022–26 path:** deployed ₹7,36,894 (₹3,81,297); N10 ₹7,16,165 (₹2,93,055).<br>The stand-aside's in-sample gain (~₹1.35 lakh) is biased; its one unseen year cost ₹20k. **No Gold change; unproven out of sample** |
| **388** | Where the stand-aside helped or hurt (2022) | 21 fires on 16 sessions; **15 of the skipped trades lost, but the 6 winners were big** (SHIPPED +₹8,224; December +₹6,148). Net cost ₹5,449, which equals N11 − NO_STAND.<br>• It helped on EFF (−₹6,385 avoided) and hurt on TPB / SHIPPED.<br>• Once on, it stayed on up to 11 sessions running; 5 fires came with the paper record within ₹2,000 of zero.<br>On a book that earns from rare big winners, sitting out a bad stretch tends to miss the recovery winner |

## Rule register (every rule tried this round)
- SN382: the 09:16 auction-direction ITM leg (depth 2 → 1, ₹15k room), 20 / 60 minutes; the ATM and coin-ITM controls.
- SN387: N10 sheet D one-account carry (frozen books, unchanged).
- SN392: Gold v5 fed by NO_STAND or N10 retry instead of N11 + R0.85 (learning only).
