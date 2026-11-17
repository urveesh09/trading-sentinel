# SN366–SN380: pressure before NIFTY moves, entries after the opening premium settles, Gold's 2022 exam (Nov 16, 2026)

**Owner (Nov 16):** the auditor's SN366–SN375 (`docs/SN366_SN375_RESEARCH_BRIEF.md`, `e7f7aadf`) plus five own slots. "High quality is a mandatory need … learn something new from every single test … documentation consistently updated."

**Method:**
- Plan frozen at `3740b461` before any number. Amendments B1–B4 (and A1 in the data build) were each committed before the slot they change. Every script was committed before it ran.
- Mechanical crashes were fixed before any number and disclosed (logs kept).

**Status:** research only. No runtime, broker, Production or order change.

**Agreed with the auditor:**
- V8's fully closed subset is 6 positions, ₹1,15,088 against ₹92,270. My 7-trade figure valued one unsold remainder at the last bid.
- fw6's expiry-day rows are research evidence only (B1).

**Power cut (Nov 16, ~18:00–19:23):** Production restarted on its own. Containers are healthy, the database integrity check is ok, and the Gold close row and the open WK-H week are intact.

## Results (in the order run)

| SN | Question | Result |
|---|---|---|
| **371** | Does the opening direction still pay at 10:15, after the premium resets? | **No.**<br>• Gap direction at 10:15 (619 trades, 2022–26): 60-minute net −₹361 at ₹205, against a coin flip −₹386 and the opposite side −₹340. After 10:15 the index moves −0.2 points its way.<br>• Auction direction at 10:15 (153 trades): −₹619, against a coin flip −₹245. The early move reverses (09:16 → 11:15: −₹803).<br>**The opening forecast is a 20–30-minute effect** |
| **376** | The opening direction through a 1–2-strike ITM leg | **The ITM leg keeps ₹55–110 a trade more than ATM at the open.**<br>• Auction sessions (171, 2026): +₹31 (20 minutes) / +₹67 (60 minutes) a trade at ₹205, against ATM −₹25 / −₹44 and a coin-flip ITM −₹206 / −₹131. Negative at ₹400.<br>• The 2022–26 index-gap sample is negative at ₹205, so the frozen rule fails.<br>→ SN380's candidate |
| **377** | Is the opening premium always rich? | **Richness scales with the overnight IV jump.**<br>• By jump tercile (+0.4 / +2.5 / +5.2 vol points), the 09:16 straddle loses ₹226 / ₹282 / ₹550 a lot by 10:15, against ₹118 / ₹33 / ₹14 from 11:00.<br>• Cheapest tercile: the gap leg makes +₹71 gross but −₹148 at ₹205. Not advanced.<br>• Rich opens are a seller's edge, outside the wallet |
| **366** | Gold / N11 on unseen 2022 | **Exam run (second opening, after a disclosed source correction).** 242 sessions, 190 with options; fresh ₹2.5 lakh.<br>• **Nets:** N10 retry −₹3,803; CUSHION = N10 one try −₹4,363; N08 −₹6,874; NO_STAND −₹8,630; **N11 −₹14,079**; random-entry median −₹76,062.<br>• **N11 sheet:** A **no** (worst of the five); B **no** (the stand-aside held back 21 entries that were net winners); C / D "yes" only because the add and size by volatility never changed an N11 trade.<br>• **N10 sheet:** A, B, C **yes**; D (one account 2022–26) not run.<br>• **Gold v5 on 2022 (₹30k):** −₹15,281 at ₹205 (−₹23,511 at ₹400); 8 days won / 20 lost; 4 of 12 months positive; worst month −₹9,276; ₹53,896 refilled. Gold's first development year 2023 had the same profile (−₹12,107, 3 of 12 months) |
| **368** | Do the option wings move before the future? | **Frozen two-tenor test not computable on the archive** (the next expiry's wings are never bracketed; B2 / B3).<br>• Front-only diagnostic (88 events): when puts got rich while futures were quiet, the future then rose (−3.8 basis points the predicted way at 15 minutes, standard error 1.7).<br>• The option loses ₹352 gross. Closed |
| **378** | Does the ATM pair's synthetic forward lead the future? | **Closed.** 119 events: +3.2 basis points the predicted way in 15 minutes (64% hit), +1.1 by 30. The option loses ₹40 / ₹115 gross |
| **379** | Signed option flow (Lee–Ready) | **Closed on count:** only 15 events from minute snapshots (+8.9 basis points at 30 minutes, standard error 5.7). The recorder's packet trades are the natural forward test |
| **372** | Expiry-morning pressure via next week's option | **Closed on count:** 9 events on 9 expiry mornings. The future follows (+7.3 basis points at 30 minutes, 78% hit), but next week's option −₹64 gross. Non-expiry control arm +₹46 at ₹205 (53 events), recorded only |
| **374** | Withdrawals from every start month (Jan 2023 – Apr 2026) | **Profit-only** never touches principal but pays nothing in 63% of months (median start).<br>**Fixed ₹500** never pauses Gold, but 2/3 of starts pay at some point while funds are below the opening ₹60k.<br>**A payout that can drain spare cash to the day-stop cover traps the account** (base + variable from Jan 2023: 581 sessions sat out).<br>**The gap to ₹750 a session:** at ₹205 the average is already met (₹785, lumpy); at ₹400 it needs +₹527 per empty-Gold session |
| **373** | What a resting limit saves | **Retired.** A mid limit fills 90.6% and saves only ₹17.7 a trade, but the misses are the winners (crossing +₹235 on them vs +₹50 on fills). Per decision: rest +₹61 vs cross +₹67 at ₹205. Adverse selection measured |
| **367** | A visible ₹750 against a paycheck | **The timeouts lose it.** 37% of 8,488 positions reach +₹750 net and fill at +₹982. The 58% that don't, time out at −₹851. Bracket −₹313 a position = fixed hold −₹308 = coin flip −₹315. Break-even needs 52% targets |
| **370** | Hong Kong's 10:30 reopen | **Closed.** HK-open days move +1.35 basis points more at 10:30 than HK holidays after the 10:00 / 11:00 placebo (p 0.15). No feed is justified |
| **369** | NIFTYBEES as a sensor | **Blocked:** no ETF data on the PC; it needs a recorder subscription (the owner's call) |
| **380** | Follow-up by the frozen rule | **Frozen forward** (`fw7.py`): SN376's AUCTION ITM 60-minute arm, with ATM and coin-flip ITM controls, scored with fw5 on SN300a's first 20 sessions. B4 drops the 10:15 clause (measured negative) |
| **375** | Survivors in the shared wallet | **Not triggered** (no survivor) |

## SN366 evidence trail
- **Gate W:**
  - N08's TEST2025 repoint replayed from empty equals its receipt;
  - N11's chain on TEST2025 equals 2025 trade for trade;
  - `results-sn366-gateW-chain.json`'s `pass=false` comes from a mis-specified cross-lab key check (`results-sn366-gateW-note.json`).
- **Gate W2:** with the evidence readers replaced, 2025 is reproduced exactly; an empty paper stream turns N11 into exactly NO_STAND.
- **Gate D:**
  - 2022 Jan–Dec and 2021L Sep–Dec from data on this PC;
  - daily bars A1: Breeze's daily close is the 15:29 minute close; 6 grossly wrong 2022 rows corrected;
  - `n08_lab.py` stays byte-identical and the points live in `n08_shim.py`.
- **First opening:** a wiring fault. N09's volatility reading used fixed files with a 21-month hole (`SOURCE_CORRECTION_2022.md`; `results-sn366-exam-2022-WIRING-FAULT.json` kept). The correction was proven by `results-sn366-volcheck.json`, then the exam was replayed once more.

## Lessons
1. **The opening direction is real but short** (about 20–30 minutes). It is already in the price at 10:15, and the auction's early move reverses after it.
2. **Opening option premium is rich in proportion to the overnight IV jump.** An ITM leg loses less of it, which is the only thing that turned the auction direction positive at ₹205 (2026 only; forward test frozen).
3. **Pressure sensors on the option chain** (wings, synthetic forward, signed flow, expiry pairs) show small, short follow-through: 3–9 basis points, 15–30 minutes. That is below a bought option's hourly cost of about ₹300–850.
4. **The visible ₹750 is lost on the 58% that never get there,** not on late fills. Waiting at a limit loses the winners.
5. **Gold's first year from ₹30k lost in both 2022 (unseen) and 2023.** The ₹8.5 lakh comes from later growth years. A real-money plan must expect a ~₹15k losing year and ~₹54k of refills.
6. **Wage policy:** never pay spare cash down to the day-stop cover. A sitting-out Gold cannot earn its way back.
