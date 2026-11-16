# SN331–SN350: trade the failed break, keep Gold's return through execution, and size the wage (plan, frozen before any number; Nov 16, 2026 ~14:45 IST)

**Owner (Nov 16):** the auditor's SN331–SN340 (`docs/SN331_SN340_RESEARCH_BRIEF.md` if supplied; the recommendation text in the conversation is the source) plus ten of my own. "Create the next SN strategies that can ensure that we are much more profitable than the current best Gold … so that the wage … can be achieved or at least reach close to that."

**Carried over:**
- Gold v5's ₹30,000 starting wallet, its priority, the 20% day room, growth and refills;
- the companion rule: premium ≤ wallet − ₹15,000, a ₹3,000 stop;
- bought options only, no margin;
- Production read only, no orders;
- forward P&L blind until its verdict.

## 0. Data honesty

- **Every historical window is now seen:** the one-second data (Apr–Nov 2026, and Jan–Apr 2026 since SN319's test), NIFTY 2019–2026 minutes, and the 41-day real-quote archive.
- **What remains genuinely unseen:** the tick recorder's forward sessions from Nov 17 (SN300a's window), and Gold on any year before 2023 (no N11 replay).
- **So:** every historical study below is a single rule frozen here before its own numbers are computed (no search), reported with that caveat. Any survivor goes to the forward packet block, scored once after Dec 23 with SN300a.

## 1. The auditor's slots (SN331–SN340)

- **SN331: why the breaks failed, and is the reversal tradable?**
  - **Data:** one-second, both windows.
  - **Events:** SN319's 30-second breaks of the 3-minute level.
  - **Failure:** the first completed 5-second bar closing back inside the level within 300 s of the break.
  - **Measured at the failure second f:**
    - the index's move in the reversal direction over +60 / +120 / +300 s;
    - buying the opposite-side opening-ATM option at f + 1 (modelled ask), held 300 s and 120 s, ₹3,000 stop;
    - net at ₹0 (gross), ₹205 and ₹400 stress, and the split into the index move, the option's move, spread and charges.
  - **The same on the real-quote archive** at minute resolution, with real asks and bids: a one-minute close outside the 3-minute level; failure = a later minute closing inside within 5 minutes; buy the opposite ATM option at the next minute's walked ask; sell at the walked bid 5 and 15 minutes later.
  - **Advance** to SN345 / SN349 only if the 300-s net per trade at ₹205 is > 0 on both one-second windows.
- **SN332: the reversal when liquidity rebuilds** (packets, forward; `fw4.py`).
  - **Event:** a failed upside break on the futures mid (a 30-second break of the 3-minute level, back inside within 120 s).
  - **Condition:** in the 10 s after the failure, at least 3 separate futures packets show five-level ask quantity ≥ 1.5 × its median over the 60 s before the break.
  - **Trade:** buy the front-weekly ATM put at fw2's execution, held 120 s. Mirror for downside breaks.
  - **Control:** the same failed breaks without the depth condition, bought 10 s after the failure.
- **SN333: the next futures month as a second opinion** (packets, forward).
  - **Event:** a burst is the front future's mid moving ≥ 0.05% in 10 s. It is "shared" when the next-month mid moved ≥ 70% as many points, "solo" when < 30%.
  - **Arms:**
    - SHARED-follow: buy the option in the burst's direction;
    - SOLO-fade: buy the opposite option;
    - each decided 1 s after the burst, held 60 s, fw2's execution.
  - **Control:** every burst followed.
- **SN334: SENSEX on NIFTY expiry days** for a surviving signal. **Conditional:** runs only if SN331 / SN344 / SN345 survives; otherwise recorded as not triggered.
- **SN335: index rebalance pressure.**
  - **Events:** the last trading session of March and of September, 2022–2026 (the NIFTY 50 semi-annual changes take effect after them).
  - **Measured:** the index's 14:00 → 15:10 return (before Gold's cutoff) against the same window on all other non-expiry sessions: rank and sign.
  - **Close the study** if the event days are not in the outer 20% of the distribution on average.
- **SN336: Gold v5 on 2022** (N11's frozen exam).
  - **Step 1:** reproduce a small known 2025 slice through the N08 → N11 pipeline (TEST2025 route), after the market closes, and only if free RAM allows.
  - Then 2022 in bounded batches.
  - If step 1 cannot finish this round, its blocker is recorded precisely; no result is inferred.
- **SN337: V8's shadow keeps its own inventory (Dev runtime fix).** The shadow records what V8 actually holds:
  - its entry lots (which can be fewer than paper);
  - adds computed on V8's holdings and cash;
  - exits that sell exactly what V8 holds;
  - a running V8 net beside paper.
  - **Test:** the auditor's case (paper 130 units, V8 65 → V8's exit sells 65).
- **SN338: V8's orders when the broker or market misbehaves** (`sn_gold_v8_orders.py`, a pure state machine for the live module).
  - **States:** OPEN / TRIGGER_PENDING / COMPLETE / CANCELLED / REJECTED, with partial fills.
  - **Rules:**
    - the sold quantity never exceeds the held quantity;
    - an exit first cancels the pending stop, then sells what is still held;
    - a stop that fills during the cancel reduces the exit;
    - a late fill after a cancel is reconciled;
    - a stop that triggers without filling becomes a market exit.
  - **Tests:** every case.
- **SN339: the finite refill reserve.** Gold v5 at ₹205 and ₹400, with spare cash R = ₹30,000 or ₹60,000 plus banked profits:
  - a losing day is refilled from that pool;
  - if the pool cannot cover a full day stop, Gold pauses until it can.
  - **Reported:** pauses, missed trades, net, and the withdrawals the pool could actually fund month by month.
- **SN340: survivors in one wallet on unopened sessions.** `fw4.py` scores SN332 / SN333 / SN349 with SN291 / SN293 / SN320 in Gold's wallet after Dec 23 (SN300a's sessions).
  - **Pass:** incremental net per FLAT session > 0 at both stresses, without the best day, with Gold first.
  - **Also reported:** skipped days, lost Gold trades, refills and fundable withdrawals.

## 2. My slots (SN341–SN350)

- **SN341: how much capital Gold can carry.**
  - On the real-quote archive: the walked round-trip cost per lot for 6, 8, 10, 12, 15 and 20 lots at ATM to 3 strikes in the money, against the model (extends SN312's 1–6 lots).
  - The first size where real − model > ₹100 a lot is Gold V8's lot ceiling.
- **SN342: the wage Gold V8 can pay.** From Gold v5's day log (₹205 and ₹400): at each month end, withdraw everything above the wallet + a reserve of one wallet.
  - **Reported:** average monthly withdrawal, months paid, the longest unpaid run, and the wage per session.
  - Plus the same with the growth cap at 4 and 5 steps (`GOLD_30K` stop 4 / 5) under SN341's cost ceiling.
- **SN343: the expiry-day book (E03.2) in Gold's wallet.** Gold never trades expiry days (202 of its 811 empty sessions).
  - If the shipped expiry-book replay (`expiry-v5`) can be run on the stored expiry-day chains, its trades are booked in Gold's wallet on those days. Otherwise the blocker is recorded.
- **SN344: the minute-level reversal, including 2019.**
  - **Rule:** SN318's held break; failure = a later minute within 10 minutes closing back inside the level; buy the opposite ATM option at the next minute (modelled ask); hold 15 minutes, ₹3,000 stop.
  - **Samples:** DEV, TEST, 2019 Q3 and 2019 Q4, against 200 random-clock books.
  - **Pass:** net > 0 at ₹205 and ₹400 in both 2019 quarters, above the random median.
- **SN345: the one-second reversal with the partner's confirmation.**
  - After SN331's failure, wait for the next completed 5-second bar that closes further in the reversal direction than the failure bar; enter at the next second.
  - SN331's exit and costs. Compared with entering at the failure.
  - **Pass (both windows):** net > 0 at ₹205 and ₹400, ≥ 30 trades.
- **SN346: V8 fill realism on packets.** For every V8 intent in the forward window: would the limit (ask + 2 ticks) have filled within 3 s, at what price, and against paper (from the tick recorder, read nightly). Frozen now; Gold trades rarely, so it reports at SN300a's date.
- **SN347: N11's stood-aside signals on Gold's empty days.** Gold v5 plus the NO_STAND book's extra signals, **at half size**, only on sessions with no Gold trade. Same replay.
  - **Pass:** at ₹205 and ₹400 and in both halves, net higher, refills no more than +10%, positive months not fewer, worst month not worse.
- **SN348: Gold with more growth steps** (4 and 5 instead of 3), with SN341's cost per lot above the ceiling added. The same pass rule as SN347, against Gold v5.
- **SN349: SN331's reversal on packets** (forward, `fw4.py`). The futures mid; the failure as in SN331; the opposite front-weekly ATM option; fw2's execution; 300 s.
- **SN350: the Gold V8 configuration.** One wallet replay of Gold v5 plus every historical survivor (SN347 / SN348), against Gold v5:
  - net, months, worst month, refills;
  - the wage (SN342's rule).
  - It writes the V8 configuration that goes to paper shadow.

## 3. Rollout

- **Research:** in `docs/research/fno/2026-11-16-sn331/`.
- **Runtime:** SN337 (and SN338's module, not wired to any broker) in Dev only; deploys only on the owner's word.
- **Results:** every result file is written once.
