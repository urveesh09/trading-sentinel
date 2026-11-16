# SN251–SN275: Gold's gap days from Gold's own wallet, without margin (plan, frozen before any number)

**Owner (Nov 16, 2026):**
- "why not consider hedging and only option selling in wk-H is that less profitable, but I think it should be much less risk … and the deposit needed will be also much less";
- "instead of that separate five lakh rupees, I want you to use the same wallet that the Gold V5 is using and create some strategy out of it to trade on the Gold gap days … I don't want to use margin because there is potential of unlimited loss … the amount we can refill [is] by max the wallet's full amount … in those gap days, please earn me the money possible … try to make it so that the system is active … option buying every day has a potential to earn more than 10%";
- "25 slots till SN 275 … new perspective. New strategy, new model, whatever you want".

## 0. The owner's constraints, as rules

1. **One wallet.** A gap-day leg uses SN Gold v5's wallet (₹30,000, +50% after net profit equal to the wallet, at most 3 steps). No other money.
2. **No margin, no unlimited loss.** **Tier A** (the default): bought options only, so the most a position can lose is the premium paid. **Tier B** (information only; the owner decides): defined-risk spreads whose largest possible loss is fixed at entry, paid from the same wallet. No naked short options and no futures in either tier.
3. **Day risk.** The SN110 one-wallet contract:
   - the leg opens only when no Gold position is open;
   - its premium leaves at least ₹15,000 of the wallet free for Gold;
   - its own stop is 10% of the wallet, inside the shared 20% day room;
   - a Gold signal while the leg is open sells the leg that minute, then Gold enters.
   - A position held overnight is booked on the day it closes, inside that day's room.
   - The premium of one position is never more than the wallet, so the largest possible refill is below the wallet (the owner's ceiling).
4. **Gold v5 is never changed.** The never-admitted leg must reproduce Gold v5 exactly (parity, SN252).
5. **Production:** WK-H (Gold v7) stays on Production paper as it is, placing no orders, unless the owner says otherwise. Nothing here touches Production. Deploys only on the owner's word.

## 1. Samples (non-expiry NIFTY sessions have full-day options of the current weekly contract; no sample holds expiry-day option minutes or next-week contracts)

| Name | What | Status |
|---|---|---|
| DEV | NIFTY Apr 1 2022 – Aug 19 2026 (SN186's 2022 dataset + SN01's 2023–2026 caches) | Seen |
| TEST | NIFTY Aug 20 – Oct 28 2026 (37 sessions) | Seen (SN181/SN198) |
| **EXAM-N** | NIFTY Oct 2020 – Mar 2022, non-expiry sessions with full-day options (SN221's and SN211's full mirrors; futures from SN221's mirrors) | Seen only for weekly-seller paths at 15:15 and WK-H; **never used for any intraday or overnight buyer rule** |
| **EXAM-S** | SENSEX Oct 2024 – Apr 2026, the same (SN211's full mirror; index from SN201's lean mirror; futures from SN221's) | The same |
| WK samples | DEV, TEST, N2122, SENSEX, EXAM of SN221–SN250 | All seen; used only by SN251 |

- EXAM-N and EXAM-S are scored **once per slot**, for that slot's single pick, after the pick is committed. They are used up after this round.
- NIFTY Jan–Sep 2020 stays sealed for the WK-H crash test (`sn248.py`).

## 2. The engine and costs (`gl.py`, written in SN253 before any buyer rule is scored)

- **Sessions:** SN01's session format (index and front future 1-minute OHLCV, current-week options per strike, previous days). The instrument is NIFTY (lot 65, strike step 50) or SENSEX (lot 20, step 100).
- **Prices:**
  - a buy fills at the minute's close plus half the 75th-percentile spread (`wk` table, SENSEX scaled ×3.25);
  - a sale fills at the close minus half;
  - an option close older than 10 minutes is not a price.
- **Costs:** Zerodha's current F&O charges (`wk.charges`), plus a **stress of ₹205 per lot per leg per round trip** (the SN house standard). Robustness at ₹400.
- **Stops:** checked at every minute's close mark; they fill at that minute's bid. An overnight gap fills wherever the market opens.
- **Sizes:** one lot per position for the per-lot results; the wallet sizes appear in SN266–SN267.

## 3. The pass rule (frozen)

For a leg's single pick in a slot:
- **G1 (DEV):** net > 0 at ₹205, and at least 3 of the 5 DEV years (2022 from April, 2023, 2024, 2025, 2026 to Aug 19) positive.
- **G2 (null):** the pick's DEV max-min score beats the 95th percentile of a null with the **same search budget**. Each null draw replaces every variant of the slot with a random version that has the same trade count, on random eligible days or with a random side, and takes the max-min pick among them. 200 draws.
- **G3 (exams):** net > 0 on **both** EXAM-N and EXAM-S at ₹205.
- **G4 (robust, DEV):** net > 0 at ₹400 and with entries one minute late.
- **PASS** = G1–G4. **WATCH** = G1–G3 only. **FAIL** otherwise. TEST is reported, not a gate (37 sessions).
- **In the wallet (SN266):** a PASS leg goes into the Gold account (Jan 2023 – Oct 2026). It must not lower Gold's net and must not reduce the number of positive months.

**Choosing inside a slot:**
- each slot lists **at most 12 variants**, written below before its run;
- the pick is the variant with the best worst DEV year (max-min), ties broken by DEV net;
- only the pick goes to TEST and the exams.

## 4. The slots

### A. The owner's questions

- **SN251: options-only WK-H (the owner's first question).**
  - Setup: WK-H's timing (the first 15:15 after the last weekend or holiday before expiry, held to settlement), with bought wings instead of the futures hedge.
  - Structures: iron fly with wings 0.5 / 1.0 / 2.0 × the straddle; iron condor 0.5/0.5, 0.5/1.0, 0.5/1.5. References: the same straddle unhedged, and WK-H itself.
  - Samples: all 5 WK samples (`wk3` / `wk4`, no change).
  - Reported per lot: net, positive months, worst month, worst week, the largest possible loss (structure), and whether one lot's largest loss fits 20% of ₹30,000.
  - A winged structure is a candidate for Gold's wallet only if positive on ≥ 4 of 5 samples.
  - Earlier evidence, quoted and not re-searched: SN203 (0 of 78 protected sellers positive) and SN225 (every winged version lost on all four samples).
- **SN252: the gap-day census and the one-wallet player.**
  - Per year: sessions, Gold trade days, gap days (non-expiry no-trade days, expiry days), Gold's wallet on gap days.
  - What a leg must earn per gap day for ₹750, ₹1,500, or 10% of the wallet.
  - The one-wallet player (SN110's contract, any leg, overnight carry) and its parity: the never-admitted leg = Gold v5 exactly.

### B. New unseen data and the controls

- **SN253: seal EXAM-N and EXAM-S** as session caches. Write `gl.py`.
  - Recorded: counts, hashes, ATM coverage and spreads.
  - No strategy price is read into any result.
- **SN254: the old gap-day buyers, frozen, on both exams, once.**
  - The leg: **SN95-L**, the 10:00 ATM straddle on hot mornings (realised ÷ implied in the top fifth by SN95's causal rule), held to 15:10.
  - It is ported to `gl.py`, with parity on DEV against SN95's stored trades before the exams are read.
  - SN126-L and SN171 are added only if they port with the same parity; otherwise recorded as "not portable".
- **SN255: the literal ask, a buyer active every gap day** (the cost of activity, not a candidate).
  - Variants:
    - (a) ATM option at 09:20 in the 09:15–09:20 direction;
    - (b) ATM option at 09:45 in the 09:15–09:45 drive direction;
    - (c) a random side at 09:20 (200 seeds);
    - (d) the 10:00 ATM straddle every day.
  - Each has a 10%-of-₹30,000 stop and exits at 15:10.
  - Samples: DEV, TEST and both exams.

### C. New perspectives (each: ≤ 12 variants on DEV, max-min pick, null, then TEST + EXAM-N + EXAM-S once)

- **SN256: weekend and holiday long volatility.**
  - SN224 found that sellers lose over weekend intervals on every sample. A buyer may get the weekend's moves without paying the weekend's decay.
  - Entry: the ATM straddle or the 0.25-straddle strangle, bought at 15:15 or 15:25 on the last session before a weekend or holiday.
  - Exits on the next session: 09:20, 09:45, 10:15, or 15:10.
- **SN257: weekday overnight longs.**
  - Entry: 15:20 on a weekday whose next session is a weekday and not an expiry day.
  - Positions: an ATM straddle, an ATM call, or an ITM call (one strike in the money); calls also only after a down day.
  - Exit: 09:20 or 09:45 on the next session.
  - The index's close-to-open drift per year (2020–2026) is reported first.
- **SN258: multi-session swing (fewer, bigger trades).**
  - Signal, read at 15:15: the close beyond the 10-day high or low, or a 3-day move > 1 daily ATR.
  - Position: an ATM option in the signal's direction.
  - Hold: to 15:15 of the 1st or 2nd next session, or of the last session before expiry.
  - Stop: an adverse index move of 1 daily ATR, checked on 15-minute marks.
- **SN259: the calendar and scheduled events (non-price information).**
  - Turn of the month (last session and first 3 sessions): an ATM call 09:20 → 15:10.
  - The session before a market holiday: an ATM call 09:20 → 15:10.
  - RBI policy days: the ATM straddle 09:50 → 15:10. Dates: `wk2.RBI`, plus 2020–21 dates from RBI press releases, listed in `events.json` before the run.
  - Union Budget days: the ATM straddle 09:20 → 15:10.
- **SN260: big opening gaps (overnight shocks).**
  - Trigger: |open ÷ previous close − 1| ≥ 0.5% or ≥ 0.8%.
  - Plays: (a) the ATM straddle 09:20 → 15:10; (b) the gap's direction 09:20 → 11:00 or → 15:10; (c) the fade, 09:30 → 15:10.
- **SN261: the weekly straddle bought when it is cheap (WK-H's mirror).**
  - Entry: at WK-H's entry, buy the ATM straddle when its implied move is below the last 5 sessions' realised move × {0.8, 1.0}.
  - Exit: the next session's 15:15, or 09:20 two sessions later where the contract allows. Expiry-day minutes do not exist, so nothing is held to settlement.
- **SN262: a learned move-size model.**
  - Model: LightGBM, walk-forward by year on DEV.
  - Target: "the rest of the day from 10:00 moves more than the 10:00 straddle costs".
  - Features: realised ÷ implied since 09:20, the 30-minute opening range, the gap, yesterday's range, the VIX ratio, sessions to expiry, the weekday.
  - Trade: buy the straddle when the probability is in the top 10% or 20% of the training year's.
  - For the exams, the model is trained on all of DEV and the threshold is fixed from DEV.
- **SN263: confirmed gap-day afternoons.**
  - On a session with no Gold trade by 14:00 (Gold's low-ADX entries stop at 14:00), at 14:00:
    - (a) the direction of 13:00–14:00;
    - (b) the ATM straddle.
  - Exit: 15:10 or 15:25.
  - On the exams (no Gold), every session is used.
- **SN264: expiry days, Gold's certain gap days (description only).**
  - What the ₹2.5 lakh book's expiry engine (E03.2) has shown in research and on Production paper since Nov 3, read-only.
  - What the owner's "only till 1–2 pm" SN rule allows.
  - No unseen expiry-day minutes exist on this PC, so there is no exam and no verdict.

### D. Survivors and the wage (run on whatever PASSES or WATCHES; "none" is a valid answer)

- **SN265: robustness:** ₹0 / ₹205 / ₹400 stress, one minute late, without the best 5 days, a month bootstrap.
- **SN266: in the one wallet with Gold** (Jan 2023 – Oct 2026, ₹30k growing): net, positive months, worst day and month, refills, green days on gap days.
- **SN267: every wallet:** ₹15k 1 lot, ₹20k 1 lot, ₹30k sized, ₹30k growing (stop 0 / 2 / 3 / 5).
- **SN268: combinations** of survivors in one wallet (only if ≥ 2 survive).
- **SN269: the daily wage from one wallet, without new money.**
  - A wage pot inside Gold's own wallet (Gold v5, plus survivors if any) pays a fixed amount every session, gap days included, from banked profit.
  - The owner refills losing days as promised.
  - Answers: which wage is sustainable from each starting month, the deepest dip, and when the pot pays for itself.
- **SN270: synthesis and the forward plan.**

### E. Reserve (SN271–SN275)

- Five reserved slots for hypotheses that SN251–SN264 suggest.
- Each is written into this file as a dated amendment, with its variants and the same pass rule, **before** it runs.
- Unused slots are reported as unused, not filled.

## 5. Not repeated (documented failures on the same data)

The 13 approaches of `docs/SN_PROBLEM_STATEMENT_EMPTY_DAYS.md` section 3, and everything in sections 9–14 of it:
- OI walls;
- the last half-hour;
- the partner-style scalper;
- the Smart Sentinel learners;
- the wage traders;
- intraday iron flies and condors;
- the weekly unprotected and protected sellers and their exits.

SN255 re-runs the literal "active every day" buyer only as the cost of activity, on new samples.
