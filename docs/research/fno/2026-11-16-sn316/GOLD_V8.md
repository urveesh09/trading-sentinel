# Gold V8: the real-money Gold (SN328 draft, Nov 16, 2026; results sections are filled in from SN323–SN327)

**Owner (Nov 16):** "Gold V8 … should be something that we are focusing to develop in real life."

**Why not v6 / v7:** WK-H sells a straddle and hedges with futures, which needs about ₹5 lakh of margin. They stay on Production paper.

## 1. What Gold V8 is

- **Gold v5's rules, unchanged**, as the core. This is the only edge 330 slots have found:
  - N11 / R0.85 entries, the deepest in-the-money strike that fits, lots = ⌊wallet / ₹15,000⌋ (halved on low-volatility days);
  - the 20% day stop, one scale-in at 1 ATR, the 3-ATR keep-a-winner trail;
  - flat at 15:10, failsafe 15:15;
  - wallet ₹30,000 growing 50% after net profit equal to the wallet, at most 3 steps;
  - losing days refilled.
- **Plus only what passes a frozen test.** Candidates this round:
  - SN324 (cancel a pending TPB entry whose setup fails within a minute): result in section 3;
  - SN320 / SN321 (a gap-day chart-sequence leg): one-second test in section 3, packet test after Dec 23.
- **No margin, ever:** bought options only. The most a day can lose is the 20% stop plus slippage; a bought option can never lose more than its premium.

## 2. The real-money execution contract (what the live module must do)

| Step | Paper module today (`sn_gold.py`) | Real-money V8 |
|---|---|---|
| Entry | records the snapshot ask | marketable **limit** order at the ask + 2 ticks, valid 3 s; if unfilled, cancel and record "missed" (never chase) |
| Lots | ⌊wallet / ₹15,000⌋ | the same, and the **cash actually paid** for every lot plus charges must fit the wallet (SN311's G1 rule: the same as v5 in every replayed trade, but safe in the synthetic edge case) |
| Day stop | a price check each tick | a **stop-loss order** at Zerodha at the day-stop price (SL with a limit 5% below the trigger), replaced on the scale-in |
| Scale-in | when the future has moved 1 ATR | the same trigger; a limit order at the ask + 2 ticks; the stop order is re-placed for the whole position first |
| Exits | N11's paper exit / trail / 15:10 / 15:15 | a limit order at the bid − 2 ticks, retried each second for 10 s, then a market order; the failsafe at 15:15 is a market order |
| Reconciliation | none (paper) | after every order and every minute: Kite positions and orders vs the module's book. A mismatch stops new entries and tells the owner |
| Kill switches | — | the owner's `/stop` command; the day stop; a stale-quote stop (no fresh chain for 30 s, so no new entry); a broker-error stop (2 rejected orders, so no new entry that day) |
| Clock | 15:40 close | the date-aware session facts (SN329): 15:45 close from Dec 7, 2026, and 15:30 for expiring index contracts |

## 3. Results this round (filled from the scored files)

- **SN323 (when Gold's entries fail): they don't fail early.**
  - 0 of 86 losing trades broke N11's own setup level in the first minute; 62 never broke it before exiting.
  - A bad first minute is as common among winners (5.7%) as among losers (4.7%).
  - Gold's losses are trades that drift to N11's exit, so no early filter can separate them.
- **SN324 (cancel a failing TPB entry): fails.** It avoids ₹15,670 of losses but misses ₹36,114 of winners (₹205 stress). Not adopted.
  - **Lesson for the live module:** a one-minute-late TPB entry costs ₹29,312 over the replay, so V8 must enter as fast as the paper module.
- **SN327 (real-money risk): within the owner's limit.**
  - No calendar month ever needed refills above the wallet (most: 63% at ₹205 stress, 81% at ₹400).
  - Any 20 sessions needed up to 96% (123% under ₹400 stress).
  - The worst month was −38% of the wallet; the longest losing run was 7 sessions.
  - **Hold about one extra wallet of cash for refills** (₹30,000 at the start).
- **SN319–SN322 (the chart sequence as a gap-day leg): no edge.** Every clock loses about the option round trip on every trade (−₹277 to −₹299 a trade at ₹205); only 12% of breaks ever offered ₹750 even in hindsight. The unused Jan–Apr 2026 window, scored once, **failed**: the five-second pullback entry lost ₹357 a trade against ₹337 for entering on the break.
- **SN317 (the 2020 crash):** Gold v7's WK-H leg passed (+₹42,570 per lot, March −₹23,171). It stays margin-funded paper; it is not part of V8 (no margin).
- **V8's rules are therefore Gold v5's rules.** The work for real money is the execution module and its gates (sections 2 and 4), not a new signal.

## 4. Gates from paper to real money (proposed; the owner decides)

1. **SN329 deployed before Dec 7** (session facts by date).
2. **The live V8 module built in Dev** behind a flag, default off. Tests cover every row of section 2 against a fake broker. It is reviewed, then deployed with the flag **off**.
3. **A shadow week:** the module runs against live quotes, places no orders, and logs the orders it would have sent. Its fills must match Gold v5's paper record within the spread on every trade.
4. **First real money:** one lot, ₹30,000 wallet, no growth steps for the first 10 real trades. The owner's word is needed for that switch.
5. **Growth:** after 10 real trades whose fills match paper within ₹100 a lot on average, the normal growth rules apply.

Gold v5 trades about once every 5–6 sessions, so 10 real trades take about two to three months.
