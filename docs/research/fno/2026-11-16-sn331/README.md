# SN331–SN350: trade the failed break, keep Gold's return through execution, size the wage (Nov 16, 2026)

**Owner (Nov 16):** the auditor's SN331–SN340 (`docs/SN331_SN340_RESEARCH_BRIEF.md`) plus ten of my own: "much more profitable than the current best Gold … so that the wage … can be achieved or at least reach close to that."

**Plan:** `PLAN.md`, frozen at `95287d3f`. Every script was frozen before it ran. Every historical window is seen; each study is one rule, frozen before its numbers.

## Results

| SN | Study | Result |
|---|---|---|
| **331** | Why the breaks failed, and is the reversal tradable? (one-second data, both windows; and the real-quote archive) | **No room.** 2,523 + 784 failed breaks.<br>• **The move:** after the failure, the index reverses a mean of **0.5–2.1 points** in 5 minutes (median 0.4–1.8); only 7–32% move more than 9 points.<br>• **Buying the opposite option:** loses **₹70–89 a trade even with zero stress**, and ₹275–295 at ₹205.<br>• **Per lot,** the option's mid moved +₹2 to +₹35 against ₹24–31 of spread and ₹68–74 of charges.<br>• **At real archive prices** (minute level): −₹131 to −₹169 a trade gross.<br>**Breakouts lose because the price churns after them and the round trip costs more than the churn; there is no profitable reversal to catch.** Not advanced |
| **345** | The reversal with the partner's 5-second confirmation | **FAIL:** −₹278 to −₹294 a trade at ₹205 on both windows |
| **335** | Index rebalance days (last session of March and September, 2022–26) | **Closed.** The 14:00–15:10 move ranks 0.76 on average among 881 sessions; signs mixed (1 of 3 up). No pressure before Gold's cutoff |
| **334** | SENSEX on NIFTY expiry days for a surviving signal | **Not triggered:** no signal survived |
| **343** | The expiry-day book in Gold's wallet | **Already answered by SN264:** E03.2's in-sample profit comes mostly after 14:00 (outside the owner's SN rule), and it has placed 0 paper tickets since Nov 5. Not re-run |
| **341** | How much capital Gold can carry (real-quote archive, 6–20 lots) | Real costs stay at or under the model up to **12 lots** (e.g. PE 3-ITM ×12: +₹4.3 a lot). At 15 lots, visible depth is missing in 8% of PE 3-ITM cases. **Gold V8's lot ceiling = 12 lots** (a wallet of about ₹1.8 lakh) |
| **339** | The finite refill reserve (Gold v5, ₹205 / ₹400) | **A fixed ₹30,000 reserve is not enough once the wallet grows.** When everything above it is withdrawn monthly, a ₹1 lakh wallet's 20% stop (₹20k) soon exceeds the pool: Gold sits out 386 sessions (89 with signals) and nets only ₹65k. With ₹60,000: no pause at ₹205 (net ₹8.51 lakh), but 107 pauses at ₹400. **The reserve must scale with the wallet** |
| **342** | The wage Gold V8 can pay (reserve = one wallet; everything above withdrawn at month end) | At ₹205:<br>• **₹6.54 lakh withdrawn over 45 months: ₹14,533 a month on average, ₹881 a session**;<br>• the last 12 months average ₹24,659 a month;<br>• but only **14 of 45 months pay**, and the longest dry spell is 12 months.<br>At ₹400: ₹3.07 lakh (₹414 a session). **The ₹750-a-session wage is reached on average at ₹205 stress, not at ₹400, and it arrives in lumps** |
| **347** | N11's stood-aside (NO_STAND) signals at half size on Gold's empty days | **FAIL:** 34 extra trades take the net from ₹8.51 lakh to **₹6.98 lakh** (₹400: ₹4.96 → ₹2.91 lakh). The stand-aside rule is earning its keep |
| **348** | More growth steps (4 and 5 instead of 3), with SN341's ceiling cost | More money, more risk:<br>• **4 steps: ₹11.65 lakh** (₹400: ₹6.51 lakh), worst month −₹54,771;<br>• **5 steps: ₹15.51 lakh** (₹400: ₹7.74 lakh), worst month −₹83,621.<br>The ceiling costs only ₹51–1,168. Against 3 steps (₹8.51 lakh, worst month −₹38,531), positive months fall by one and the worst month deepens. **FAIL** by the frozen rule; it remains a risk choice for the owner |
| **350** | The V8 configuration | No change passed, so **Gold V8 = Gold v5** (3 steps, its signals), executed by the V8 module. The wage is SN342's |

| **344** | The minute-level reversal (buy against a held break that fails within 10 minutes), DEV / TEST / 2019 | **FAIL, and below every random book again** (percentile 0.0–0.005). Per trade at ₹205: DEV −₹302 (10,030 trades), TEST −₹284, **2019 Q3 −₹304, 2019 Q4 −₹270**, against random entries at about −₹204. **Lesson: any entry right after a fast 1–3-minute move, with it or against it, costs about ₹95 a lot more than a random entry.** The option has already priced the move, and the move then fades. Random entries themselves are about break-even before the ₹205 stress. Short-horizon option buying has no edge on NIFTY at any clock we can trade |
| **336** | Gold v5 on unseen 2022 (N11's frozen exam) | **Not run; blocker made precise.** The route is:<br>• N08's repointing (`n08_lab.POINTS`, today only 2023 / TEST2025);<br>• then N09, N10, N101 and N11's own labs, each needing that year's evals (N101's paper evidence reads `keys-diag-<year>`);<br>• a 2022 dataset in the year format, with its manifest, observation cache and daily-bar file.<br>That is four chained engine replays of a year, competing with Production for RAM. It needs its own round, started after market hours, with the TEST2025 wiring check first |
| **337** | V8's shadow keeps its own inventory (Dev runtime) | **Fixed.** `sn_gold_v8_positions` holds what V8 actually bought. Adds are evaluated on V8's holdings and cash (Gold's rule + SN311's G1 cash check + the whole-position stop), and exits sell exactly V8's holding, with a running V8 net beside paper. **The auditor's case is a test:** paper holds 130 units, V8 enters 65, and V8's exit sells 65 |
| **338** | V8's orders when the broker or market misbehaves | `python-engine/sn_gold_v8_orders.py`: a pure order-lifecycle state machine for the future live module (no broker). Tested cases:<br>• a partial entry fill sizes the stop;<br>• an exit waits for the stop's cancel, and a stop that fills during the cancel shrinks the exit (to zero);<br>• a stop that triggers without filling becomes a MARKET exit;<br>• an add replaces the stop for the whole holding;<br>• a SELL can never exceed the holding;<br>• a late fill after a confirmed cancel is booked and flagged OVERSOLD;<br>• a rejection is flagged.<br>8 tests |
| **332 / 333 / 349 / 340 / 346** | Forward packet candidates and the one-wallet score (`fw4.py`) | **Frozen:**<br>• SN349, the reversal on the futures mid;<br>• SN332, the reversal after the rejected side's depth rebuilds;<br>• SN333, next-month confirmation (shared bursts followed, solo bursts faded);<br>• SN340, in Gold's wallet;<br>• SN346, whether each V8 intent would have filled within 3 s.<br>Scored once after SN300a (Dec 23): `python fw4.py verdict`. After SN331 / SN344, SN349 and SN332 are expected to fail; SN333 is the one untested mechanism |

## What this round teaches

1. **Short-horizon NIFTY option buying has no edge at any clock we can trade:**
   - one-second, five-second, thirty-second and one-minute rules all lose;
   - so do breaks, holds, pullbacks and reversals;
   - entries right after fast moves are *worse* than random by about ₹95 a lot, because the premium already contains the move.
2. **Gold V8 = Gold v5.** No filter, gap-fill or sizing change passed. The real-money work is execution: the V8 shadow with its own inventory, and the order lifecycle.
3. **The wage comes from Gold's capital:**
   - with a reserve equal to the wallet, Gold v5 pays about ₹881 a session (₹14.5k a month) at ₹205 stress, in lumps;
   - 4 growth steps pay about ₹1,121 a session, 5 steps about ₹1,398, with deeper bad months (−₹55k / −₹84k);
   - **depth carries Gold up to 12 lots** (a wallet of about ₹1.8 lakh).
4. **A fixed spare reserve stalls Gold once its wallet grows.** Keep one wallet of spare cash beside the wallet.

## Files

- **Plan:** `PLAN.md`.
- **Code:** `sn331_345.py`, `sn335.py`, `sn339_350.py`, `sn341.py`, `sn344.py`, `fw4.py`.
- **Results:** `results-*.json`.
- **Logs:** `logs/` (git-ignored).
- **Runtime (Dev only, not deployed):** `python-engine/sn_gold_v8.py` (SN337), `python-engine/sn_gold_v8_orders.py` (SN338), the `sn_gold.py` hooks, and tests.
