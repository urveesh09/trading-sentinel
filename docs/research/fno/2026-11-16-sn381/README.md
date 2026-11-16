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

## Rule register (every rule tried this round)
- SN382: the 09:16 auction-direction ITM leg (depth 2 → 1, ₹15k room), 20 / 60 minutes; the ATM and coin-ITM controls.
