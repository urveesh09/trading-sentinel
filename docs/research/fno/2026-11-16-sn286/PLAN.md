# SN286–SN300: the auditor's brief, tested (plan, frozen before any number; Nov 16, 2026 ~09:30 IST)

**Owner (Nov 16):** "You go ahead and test it out see if you can agree to it. If you don't fair enough, you can have your own ideas. You can improve on these recommendations … slots till 300."

**Source:** `docs/SN286_SN300_RESEARCH_BRIEF.md` (the auditor's brief, reviewed at `cd115aa7`).

**Verified before planning** (read from my own files, no new score):
- SN284's leg ledger: 38 calls, +₹14,970. One trade (Apr 2 2026) made +₹18,757; without it −₹3,787; without the best 5 −₹35,980.
- SN259's `pre_holiday` admitted four Saturday special sessions (2024-01-20, 2024-03-02, 2024-05-18, 2025-02-01).
- Two of them (Mar 2, May 18 2024) ended at 12:30 and booked a "time" exit from the last mark.
- **The auditor is right on all three.**

## What I agree with, what I change

**Agree:**
- fix the calendar and exits before any watch (SN286);
- replicate the partner's first minute against real quotes (SN288);
- qualify the tick recorder before using it (SN289);
- measure the real cost hurdle (SN290);
- two market candidates at most per scoring round (SN291, SN293);
- an exit challenger (SN296);
- a frozen forward verdict (SN300);
- the score is net ₹ per eligible gap session.

**Change:**
1. **The real-quote archive (Sep 10 – Nov 13) holds one snapshot a minute per contract** (checked: 386 NIFTY-future records on Nov 11, one a minute). SN288 and SN290 run at minute resolution: an as-of join of each fill to the next snapshot. SN291, SN293 and SN296 need packet data, which exists only from the tick recorder, live since **today, Nov 16 09:00**.
2. **Today is a development day.** It is used for plumbing, event counts and latency only, and never scored.
   - The forward window is the **next 20 full NIFTY sessions recorded after this plan's commit**, starting Nov 17.
   - Scoring happens once, after the 20th session.
3. **The partner:** research and coaching use only, on the frozen Nov 4 extract. Shapes and ratios only; no partner rupee totals in committed files. A live copy of the partner's entries is out of scope: it would need the partner's consent, and SN122's edge lasts about a minute.
4. **SN292, SN294, SN295 and SN297:**
   - SN294 (next expiry) and SN295 (SENSEX confirmation) become secondary diagnostics on SN291's events, reported without a verdict.
   - SN292 (replenishment fade) and SN297 (expiry mornings) are deferred: unused slots, to keep within the two-candidate limit.

## The slots

- **SN286: the corrected holiday replay** (seen data, a diagnosis).
  - A pre-holiday session is a Monday–Friday regular session with index prints through 15:10.
  - At least one Monday–Friday date between it and the next trading day must be a market holiday. The derived list is printed and checked against the engine's 2026 NSE list; any unexplained weekday is flagged.
  - Expiry days are excluded (they have no SN session).
  - Trade: the ITM call (one strike) at 09:20, exit at 15:10. **An executable 15:10 price is required, or the trade is "unresolved"** (listed, excluded from the net).
  - Report on all four samples: old vs corrected admissions, nets, the trade without its best day, and an ATM reference.
  - Matched control: the same trade on ordinary sessions of the same sample with the same weekday and sessions-to-expiry (all matches, the mean scaled to the count).
  - The corrected rule also goes into the one wallet (`ow.py`): Gold alone vs Gold + the call.
- **SN287: where the partner's green days were lost** (frozen Nov 4 extract, 7 sessions, real minute quotes).
  - Per session: the peak, and the first give-back alert (the rule in Production: a ≥ 5%-of-₹25k peak gives back 30%).
  - The change from the alert to the close is split into: marks on positions open at the alert, fees, and later entries.
  - Arms: (a) close everything at the alert; (b) no new entries after the alert, keep managing open ones; (c) actual.
  - Control: random alert clocks with similar open risk.
  - Session shares only.
- **SN288: the first-minute read with executable prices.**
  - Each partner buy fill is joined as-of to the first snapshot at or after the fill + 60 s; the executable result is (that snapshot's bid − the fill price) per unit.
  - Controls: the same contract, same day, same side, same clock bucket (30 minutes), within a premium band ±20%; minutes drawn from the archive.
  - Clustered by session: re-entries within 2 minutes of the same contract collapse into one.
  - Reported: executable lift vs control, and per lot after charges and ₹205.
- **SN289: qualify the tick recorder** (today's session, after 15:41):
  - decode every chunk;
  - per token, the first and last receipt and gaps > 5 s;
  - depth age; the events file; instruments; bytes;
  - futures and near-ATM coverage.
  - Also: a daily research extract (NIFTY front future + options within ±6 strikes, both expiries) into a compact research store, because the recorder keeps 35 days within a 12 GiB cap.
- **SN290: the executable hurdle** (minute archive, 41 sealed days). For one lot of the ATM CE, ATM PE and the straddle, bought at 09:20, 10:00, 11:00, 13:00 and 14:00 and sold 15 / 60 minutes later:
  - the real round-trip cost from the snapshots (ask in, bid out, depth for one lot);
  - against the model (half the P75 spread each side + charges);
  - the cost split into spread, charges and 1-minute delay movement.
  - This calibrates the hurdle that every bought-option rule must beat.
- **SN291: candidate A, futures pressure that persists** (forward, frozen here). See the specification below.
- **SN293: candidate B, the strike that lags the chain** (forward, frozen here). See below.
- **SN294 / SN295: secondary diagnostics** on SN291's events:
  - the next-expiry option of a similar delta vs the front option;
  - SENSEX future confirmation within 2 s.
  - Reported, no verdict.
- **SN296: the exit challenger** on SN291 / SN293 entries: exit when the supporting futures imbalance reverses sign after a positive net mark, vs the fixed hold. Identical fills.
- **SN298: the corrected holiday shadow.**
  - A frozen research ledger for future pre-holiday sessions under SN286's corrected rule.
  - In the 2026 list: Nov 23 (before Nov 24) is NIFTY's expiry-shifted day, so it is excluded by rule; Dec 24 (before Dec 25) qualifies.
  - The ledger is scored from the recorder's quotes; no runtime module.
- **SN299: the one-wallet contract for any forward survivor** (written here, run after SN300):
  - Gold first;
  - the candidate's debit plus fees within the ₹3,000 sub-budget inside the shared 20% room;
  - liquidation on Gold's signal;
  - Gold parity (`ow.py`).
- **SN300: the forward verdict.** See below.

## SN291: candidate A, futures pressure that persists (frozen)

**Data:** the NIFTY front-month future and the front weekly NIFTY options (full-mode packets), merged in receipt order (`recv_ns`).
- Mid = (best bid + best ask) / 2.
- Depth imbalance I = (Σ5 bid qty − Σ5 ask qty) / (Σ5 bid qty + Σ5 ask qty).

**Impulse:** the future's mid changes by ≥ 0.06% within 30 s (now vs the last packet at or before now − 30 s). One impulse per 120 s.

**Condition (the candidate):**
- the mean of I over the futures packets of the last 10 s has the impulse's sign;
- |mean I| ≥ 0.20;
- the mid 5 s after the impulse has not retraced more than half of it (pressure persists).
- The decision is at impulse + 5 s.

**Control:** the same impulses without the condition.

**Trade:**
- At the first option packet received ≥ 0.5 s after the decision, buy one lot of the ATM option of the impulse's side (call up, put down) at its best ask.
- Requirements: ask quantity ≥ one lot; quote age ≤ 2 s; premium ≤ ₹15,000.
- Exit at the first best bid ≥ 60 s after the fill. A ₹3,000 stop is checked on every packet.
- Window 09:30–14:30; at most 1 open position.
- Costs: Zerodha charges + ₹205 (and ₹400) per lot.

## SN293: candidate B, the strike that lags the chain (frozen)

**Hedge ratio:** for every option within ±3 strikes of ATM on the move's side, a local ratio β = the least-squares slope of the option mid's 5-second changes on the future mid's 5-second changes over the previous 10 minutes (≥ 30 pairs).

**Trigger:** the future's mid moves ≥ 0.04% within 5 s.

**Lag:** the target's expected change is β × ΔF. Its observed mid change since the trigger's start must be ≤ 40% of the expected change. At least two other strikes on the same side must have moved ≥ 70% of their expected changes. The target's quote age must be ≤ 1 s, so a stale quote is not counted as a lag.

**Room:** the remaining expected move (expected − observed) × one lot must be > the round-trip spread + charges + ₹205.

**Trade:**
- Buy one lot at the target's best ask on the first packet ≥ 0.5 s after the decision.
- Exit at the first best bid ≥ 15 s later.
- ₹3,000 stop. Window 09:30–14:30; one position at a time; one trade per trigger.

**Control:** the same triggers, buying the most-repriced strike instead.

## SN300: the forward verdict (frozen)

**Window:** the first 20 full NIFTY sessions recorded after this commit (from Nov 17). A session counts only if SN289's checks pass for it: futures and ATM coverage ≥ 95% of 09:30–14:30 with no gap > 60 s.

**Gold gap days** are read afterwards from Production's SN Gold paper ledger. The score is net ₹ per eligible gap session (zero-trade sessions count).

**A candidate passes only if all of these hold:**
- net > 0 at ₹205 and at ₹400;
- it beats its control;
- it is still positive without its best session;
- ≥ 30 trades on ≥ 10 sessions;
- the gap-session subset is positive.

**Otherwise:** "FAIL", or "insufficient evidence" when coverage or event counts miss these numbers. No reruns, and no threshold changes after this commit.

**After a pass:** SN299 (the one wallet), then a forward paper module on the owner's word.
