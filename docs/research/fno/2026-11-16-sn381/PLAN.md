# SN381–SN395: make the opening trade honest, explain it, find a second opening witness, and close Gold's 2022 exam (plan, frozen before any number; Nov 16, 2026 ~21:20 IST)

**Owner (Nov 16):** the auditor's SN381–SN390 (`docs/SN381_SN390_RESEARCH_BRIEF.md`, committed as received in `c1f4fcbd`) plus five own slots; "high quality is a mandatory need … learn something new from every single test".

**Agreed with the auditor, verified in the code** (no forward session has been recorded yet: Nov 17 is the first):
- **Cash:** `sn376.leg` (line 39) and `fw7.leg` (line 51) accept the one-strike ITM fallback at any premium. The ₹15,000 room was enforced only on the two-strike leg. The forward order has no price cap.
- **Timing:** `fw5.session`'s fallback auction price is the first futures packet at or after 09:15:00, with no bound by the 09:16:00 decision (line 135). In history, SN353 (b) used the 09:15 open on 74 of 172 sessions.
- **Controls:** `fw5.judge` compares the candidate's mean over all its fills with each control's mean over the shared subset (line 190).

**How this round works (as before):** one slot at a time; scripts committed before their numbers; results written once; dated amendments before the slot they change; a README row after every slot. A register of every rule tried is kept in the README.

**Carried over:**
- Gold v5 at ₹30,000 and its rules; the 20% shared day room;
- one bought index option, premium plus entry charges ≤ wallet − ₹15,000 (₹15,000 at ₹30k), a ₹3,000 stop;
- ₹205 / ₹400 stress plus Zerodha charges;
- expiry days flat by 13:30;
- Production is read only, and nothing places an order;
- SN300a and fw3–fw7 stay unopened until their verdict.

## 0. Data
- **Seen:** gl DEV + TEST (2022–Oct 2026, modelled quotes); Breeze futures pre-open rows (Dec 8, 2025 on); the real-quote archive (Sep 10 – Nov 13); the 2022 exam stack (`sn366/_local`).
- **Unseen forward:** TR01 recorder sessions from Nov 17.
- **NSE's F&O pre-open changed on Sep 7, 2026** (order entry to 09:10; the Breeze match row moves from 09:07 to 09:09 and carries the indicative path). Every historical opening result is reported before / after Sep 7, 2026 separately, never pooled as one protocol.
- **Absent:** NIFTY constituent pre-open data; the NIFTY 50 index's own pre-open value is the weighted cash-auction basket.

## 1. The auditor's slots

### SN381: could the opening trade really be bought? (companion audit, `fw7a.py` + tests, before any forward P&L)
- **Strike rule:** both depths and the ATM control are admissible only if the walked one-lot ask plus entry charges ≤ ₹15,000. Otherwise the deeper one is tried, then the shallower; if neither fits the decision is INADMISSIBLE (scored 0, counted).
- **Order cap:** the buy order carries a limit = the 09:16:00 ask + 2 ticks; a walked fill above it is MISSED (capped).
- **Timestamps:** the auction price must come from a packet received before 09:16:00. MATCH (the pre-open match packet) and FIRST_TRADE (first continuous packet, received ≤ 09:16:00) are labelled; a later packet makes the decision NO_SIGNAL.
- **Ledger states:** INADMISSIBLE / NO_SIGNAL / MISSED / FILLED / UNRESOLVED, with receipt times, cash before / after, stop and exit times.
- **The coin control** uses the same depth and admissibility rules.
- **Synthetic tests:**
  - the ₹19,500 one-strike fallback;
  - a ₹15,000 top-of-book whose walk costs more;
  - a stale quote;
  - a fallback signal from a late packet;
  - an unresolved exit;
  - a one-matched-day control.
- **fw5 / fw7 originals stay as frozen** (their verdicts are still produced and published); fw7a is the corrected companion.

### SN382: replicate the opening lead honestly (history now; forward with fw7a)
- **History** (gl DEV + TEST, the same 171 auction sessions as SN376, plus the GAP sample):
  - SN376's arm re-scored under SN381's cash rule and source labels;
  - per-session net including skips (0) and inadmissible days;
  - paired differences against the ATM and coin controls on common sessions only;
  - ₹205 / ₹400; without the best day;
  - date-level and week-level standard errors;
  - split by source (MATCH vs FIRST_TRADE) and before / after Sep 7, 2026.
- **Forward:** fw7a's verdict on SN300a's 20 sessions, with the same paired rules.
- **Pass** for further consideration: incremental per-session net > 0 at ₹205 and ₹400, positive paired lift against both controls, > 0 without the best day.
- **Sizing:** the first window sizes a fresh validation block from its date-level variance.

### SN383: what the ITM option buys
- **Arms:** on SN382's admissible sessions, ATM, 1-ITM and 2-ITM on the same signal, clock, expiry and exit (60 minutes, ₹3,000 stop).
- **Decomposition:** each leg's mid change into delta × futures move, vega × IV change and theta, plus a residual (Black-76 on the synthetic forward, as SN361), against spread and charges paid.
- **Also reported:** time value paid as a share of the debit, and net per eligible day.
- **Maturity check:** next week's option at a similar entry delta, where affordable and quoted.
- **Diagnostic only.** A contract choice is promoted only on later paper dates.

### SN384: cut a failed opening thesis
- **Rule:** on the 09:16 fills (1–2 ITM, as SN382), at 09:36, exit if the latest received front-futures price has given back ≥ half of the move from its previous close to the auction price. Exit at the next minute's bid; the ₹3,000 stop is kept.
- **Comparison:** against the frozen 60-minute hold on the same fills, with winners cut short counted.
- **Stress:** applied both as fixed executed exits and through the stop-trigger simulation.

### SN385: does the cash auction confirm the futures auction?
- **Signal:** the NIFTY 50 index's pre-open value (Breeze index rows 09:0x, the weighted cash-auction basket, received before 09:15) against its previous close: a cash gap. AGREE = the same sign as the futures auction gap.
- **Arms:** SN382's trade split AGREE / DISAGREE, conditional on the gap's size bucket.
- **Roll dates** (both futures auctioned): the front and next gaps' agreement, logged.
- **Pre-check:** a timestamp and coverage manifest first; the slot needs ≥ 100 sessions with both gaps.
- **Constituent-weighted agreement** is not computable (no constituent pre-open data); recorded.
- **Advance:** AGREE's per-session net at ₹205 and ₹400 > 0, above DISAGREE and above the unconditional arm, in both protocol periods.

### SN386: signed option pressure from packets (forward design + plumbing)
- **Signing:** a recorder trade (volume increment with last price / quantity) is signed against the bid / ask in effect at its exchange time, else unsigned.
- **Event:** the first qualifying event per date; a 15-minute horizon.
- **Controls:** unsigned volume, same-clock same-futures-move, and a time-shifted placebo.
- **Frozen** as `fw8.py` and checked on Nov 16 for plumbing only. Scored after 20 sessions.
- **Timing sensitivity** of the one-second / ten-second archives as a diagnostic of available move size.

### SN387: close Gold's 2022 exam
- **Reconcile the dates:** 242 market dates against 190 option-usable dates, by reason (expiry day without the house's same-day options, missing strike or bar, warm-up), month and volatility.
- **N10 sheet D:** one account from the first 2022 session through 2026 for N09.1 CUSHION and N10 with WATCH, on the original ₹2.5 lakh terms. Yes if N10 never falls below 75% of its best closed equity and ends at or above CUSHION's end.
- **The ₹30,000 Gold** comparison follows in SN388 / SN392.

### SN388: where Gold's risk filter helped or hurt
- **Trace:** the 2022 stand-aside's fires, with the paper exits known at each, and the suppressed entries' outcomes by date and state.
- **Compare:** the unmodified N11 book, NO_STAND, and the N10 one try / retry on the same data.
- **Then:** a ₹30,000 Gold-sized book on each signal source (see SN392).

### SN389: cash needed to live through a bad start
- **Ledger:** an external-funding ledger (opening cash, withdrawals, stop room, P&L, internal transfers, external deposits).
- **Starts:** ₹30k + ₹30k from 2022 (Gold on the 2022 stream, then the development years), 2023 and every later month start, at ₹205 / ₹400.
- **Reported:**
  - maximum reserve depletion, gross transfers and external cash needed, as separate figures;
  - the share of market days paying ₹750; the longest dry spell.

### SN390: survivors through one wallet
- **Runs only for a candidate that passes SN382 / SN385 / SN386:** SN352's journal with Gold priority, pre-emption, the shared 20% room and candidate exit latency.
- **Otherwise** not triggered.

## 2. Own slots (SN391–SN395)

### SN391: the auction's indicative path
- **Source:** since Sep 7, 2026, Breeze's pre-open rows carry the indicative price minute by minute (09:00–09:09); the recorder carries it in `open`.
- **Signal:** late-auction drift = indicative(match) − indicative(09:05), relative to the gap.
- **Question:** does a drift in the gap's direction (building demand) strengthen SN382's trade, and does a drift against it weaken it?
- **Data:** development on Sep 7 – Oct 28, 2026 (Breeze); forward on the recorder (frozen in fw7a as a diagnostic field).

### SN392: Gold's signal source across five years
- **Arms:** Gold v5 (₹30k, unchanged sizing) fed by (a) N11 + R0.85 (as deployed), (b) NO_STAND (N11 without the stand-aside), (c) N10 retry.
- **Years:** each of 2022 (the exam stream) and 2023–26 (development streams), at ₹205 / ₹400.
- **Reported:** per-year nets, months positive, worst month, refills.
- **Learning only:** 2022 is seen now; no Gold change follows from this slot.

### SN393: auction conviction
- **Measure:** the matched quantity of the auction (Breeze match row volume; the recorder's indicative matched quantity) against its trailing 20-session median.
- **Question:** does SN382's trade do better on high-conviction auctions (above median) than low?
- **Data:** development on MATCH-source sessions.

### SN394: the opening trade on non-rich opens
- **Split:** SN382's trade by SN377's causal overnight-IV-jump tercile (from earlier sessions only).
- **Question:** does skipping RICH opens raise per-session net at ₹205 and ₹400?
- **Development only.**

### SN395: reserve sizing by block bootstrap
- **Method:** Gold's month sequences (₹30k start, the corrected journal) from 2022–2026 resampled in contiguous 3-month blocks, 10,000 paths of 24 months, at ₹205 / ₹400.
- **Reported:** the distribution of external cash needed, the longest dry spell, and the share of months paying ≥ ₹15,750.
- **Result:** the reserve covering 90% / 95% of paths.

## 3. Order of work
1. SN381 → SN382 (history) → SN387.
2. SN383 → SN384 → SN385 → SN391 → SN393 → SN394 (the opening family, on SN382's admissible set).
3. SN392 → SN388 → SN389 → SN395.
4. SN386 (forward design) → SN390.

## 4. Amendments
(none yet)
