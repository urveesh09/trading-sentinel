# SN366–SN380: find pressure before NIFTY moves, enter after the opening premium settles, and finish Gold's 2022 exam (plan, frozen before any number; Nov 16, 2026 ~19:40 IST)

**Owner (Nov 16):** the auditor's SN366–SN375 (`docs/SN366_SN375_RESEARCH_BRIEF.md`, committed as received in `e7f7aadf`) plus five own slots. "High quality is a mandatory need and you should be able to learn something new from every single test … the documentation is consistently updated."

**Agreed with the auditor:**
- **V8 headline:** counting only the 6 positions V8 fully closed, it is ₹1,15,088 against ₹92,270. My 7-trade figure included a remainder valued at the last bid.
- **fw6:** its expiry-day rows fall outside the owner's expiry-day clock, so they are research evidence, not wallet trades (amendment B1 below).
- **The target:** the number that matters is the extra net rupees per eligible gap day, skipped days included.

**How this round works (as before):**
- One slot at a time. Each script is committed before its own numbers; results are written once.
- Dated amendments are committed before the slot they change.
- Each slot ends with a written lesson, and the README is updated after every slot.

**Carried over:**
- Gold v5 at a ₹30,000 starting wallet: priority, growth and refills, the 20% shared day room;
- one fully paid long index option, whole lots, premium ≤ wallet − ₹15,000, a ₹3,000 planned stop;
- Zerodha charges + ₹205 / ₹400 stress, observed-quote numbers reported beside them;
- **expiry days:** flat by 13:30 (the owner's 13:00–14:00 window);
- Production is read only, and nothing places an order;
- SN300a, fw3 / fw4 / fw5 / fw6 and the 2022 exam stay unopened until their own runs.

## 0. Data (Nov 16)
- **TR01 recorder:**
  - NIFTY: 41 strikes (±1,000 points) × CE / PE × 3 weekly expiries, two futures;
  - SENSEX the same, plus INDIA VIX;
  - full packets with 5-level depth, from 09:00;
  - Nov 16 is development; Nov 17 onward is unseen forward.
- **Real-quote archive (minute snapshots, ~11 strikes × 2 expiries):** Sep 10 – Nov 13, 2026, seen.
- **Breeze 1-minute** (index, futures with pre-open rows from Dec 8, 2025, options with OI): seen.
- **N08 chain inputs for 2022:** SN186's `dataset-nifty-2022`, whose format must be checked against N08's year format.
- **Absent:**
  - NIFTYBEES quotes: not in the recorder, the archive or Breeze;
  - Hong Kong / London quotes;
  - GIFT NIFTY;
  - bank data.

## 1. The auditor's slots

### SN366: Gold / N11 on 2022 (frozen exam `EXAM_2022_N11.md`)
- **Gate W (wiring):** N08's own `TEST2025` repoint is replayed and must reproduce the stored 2025 receipts, the evaluation counts and nets, at each stage the chain uses (N08 → N09 → N10 → N101 → N11), with dated event / contract identities compared.
- **Gate D (2022 data):**
  - a 2022 point in N08's format: dataset with manifest, sessions and weekly expiry calendar; mirror; observation cache; evals; daily bars with ≥ 250 sessions of warm-up from 2021;
  - built only from data already on this PC;
  - option coverage per session is counted, and a session without options is a recorded gap.
- **Run:** the frozen exam once, in bounded batches after market hours, with free RAM ≥ 3 GiB. It answers questions A–D and reports the random-entry median.
- **Then Gold v5 on the 2022 N11 signal stream**, unchanged, at ₹30k: net at ₹205 / ₹400, months positive, worst day / month, refills.
- **If a gate fails,** the slot ends with the exact missing input and its effect. Nothing is inferred.

### SN367: from a visible peak to a paycheck
- **Data:** SN351's clocks and positions (DEV modelled; archive real quotes).
- **One bracket only:** target net +₹750 after charges and ₹205 stress (bid-side mark ≥ ₹955 before stress); the ₹3,000 stop at ₹205; a 60-minute deadline.
- **Fill rule:**
  - primary: the trigger is seen on minute m's quote and the fill comes at the next eligible quote (m + 1), at its bid;
  - diagnostic: a fill at the same minute.
- **Outcomes kept:** target, stop, timeout, unresolved, with realized size and frequency.
- **Controls:** cash (0), the same clock with a coin-flip side, and SN351's fixed 60-minute hold.
- **Diagnostics:** the largest bid before / after the trigger and before / after the stop.
- **Ends with:** which part loses (late fills, size of failures, or rarity of targets). It is never a new candidate.

### SN368: do the option wings move before the future?
- **Data:** the archive for development (seen); recorder packets forward (frozen as `fw7` only if development shows futures follow-through).
- **Each minute 09:30–14:30, front and next expiry:**
  - Black-76 IV per strike from usable mids;
  - the forward from the ATM pair's parity;
  - 25-delta put IV and call IV by delta interpolation;
  - RR = IV(25Δ P) − IV(25Δ C); ATM IV.
- **Event:**
  - the 10-minute ΔRR is the same sign in both tenors;
  - each is beyond 1.5 × the standard deviation of that tenor's ΔRR on earlier sessions only (≥ 5 earlier sessions);
  - the futures mid moved < 0.05% in those 10 minutes;
  - the ATM-IV change is removed by an earlier-sessions regression of ΔRR on ΔATM-IV and the futures return;
  - at most one event per 30 minutes.
- **Prediction:** puts richer means down.
- **Measured:**
  - the futures mid return over the next 15 / 30 minutes in the predicted direction, against all quiet minutes (matched clock) and ATM-IV-only events;
  - then the ATM option on that side bought at the next snapshot's walked ask, held 15 / 30 minutes.
- **Close if** fewer than 30 events, or follow-through < 1 basis point, or the option is negative at zero stress.

### SN369: NIFTYBEES as a sensor
- **Feasibility:** no timestamped NIFTYBEES data exists on the PC. The study is BLOCKED.
- **Recorded:** what the recorder would need. Subscribing the ETF token is an operational change, the owner's call.

### SN370: the Hong Kong afternoon reopen (10:30 IST)
- **No HK quotes exist here**, so the auditor's test is BLOCKED.
- **Feed-justification check (no HK data):**
  - NIFTY's |index return| and the ATM straddle's net over 10:28 → 10:45 and 10:28 → 11:00;
  - HKEX-open Indian sessions against Indian sessions when HKEX is closed (HKEX's dated holiday lists, recorded as fetched);
  - plus a clock-shift placebo (10:00 and 11:00).
- **If HK-open days don't move more,** a feed has little to explain and the slot closes. If they do, it is recorded as worth a feed.

### SN371: the opening forecast after the premium resets (10:15)
- **Data:** gl DEV + TEST (index gap, Apr 2022 – Oct 2026) and the auction gap (Breeze, Dec 2025 – Oct 2026), all seen; archive for real quotes.
- **Decision at 10:15** (minute 60). The direction is fixed from before 09:16:
  - AUCTION: the sign of SN353's g;
  - GAP: the sign of the index open / previous close − 1, for |gap| ≥ 0.10%.
- **Traveled:** T = the index return 09:16 → 10:15 in that direction. Buckets < −0.2%, −0.2..+0.2%, +0.2..+0.4%; **cap: abstain if T ≥ +0.4%.**
- **IV state:** NORMALIZED if the ATM straddle IV at 10:15 ≤ its IV at 09:16, else NOT.
- **Trade:** one lot of the front-weekly ATM option on the fixed side at 10:15, a ₹3,000 stop, held 60 minutes (primary; 20 minutes and to 14:30 are diagnostics).
- **Controls:**
  - a coin-flip side at 10:15;
  - the same path's 09:16 entry held to 11:15;
  - the opposite side.
- **Decomposition:** the after-10:15 index points in the direction, against the option's delta part and its theta / IV residual (SN361's method).
- **Advance** (to a forward freeze, never live) needs, at ₹205, a 60-minute net per trade > 0 on:
  - GAP (DEV + TEST, ≥ 200 trades, ≥ 3 of 5 years positive);
  - AUCTION (≥ 60 trades);
  - both above the coin flip;
  - the archive the same sign.

### SN372: expiry-morning pressure, traded in next week's contract
- **Mechanism (SN378's, on the expiring chain):** the expiring ATM pair's synthetic forward (K + C − P) against the futures mid; an event when its 10-minute change departs ≥ 2 earlier-only standard deviations from the futures' change while futures are quiet.
- **Trade:** the next-week ATM option on that side, entries 09:30–12:30, flat by 13:30.
- **Data:** archive expiry days (development); recorder forward.
- **Controls:** the same mechanism on non-expiry mornings, and a coin flip at the same clocks.
- **Close if** fewer than 20 events or no futures follow-through.

### SN373: what waiting at a limit really saves
- **Signal:** the development arm with the highest positive pre-stress room among SN353 (b) CONT, SN371 and SN376 (chosen by that rule, before SN373's numbers).
- **Arms:**
  - CROSS = buy at the ask now;
  - REST = one-lot buy limit at the mid, live 2 minutes, no chase.
- **Fill bounds (Breeze minute trade candles):**
  - conservative = a later minute's low < limit (a trade-through);
  - permissive = low ≤ limit;
  - no fill = no trade.
- **Report:** saving per filled trade; missed winners; the outcome after fills against after misses (adverse selection).
- **Retire it if** it only works on the permissive bound.

### SN374: withdrawals that survive bad starts
- **Journal:** `sn352.Journal`, ₹30k trading + ₹30k spare, starting every month from Jan 2023 to Apr 2026, each run to Oct 2026.
- **Policies:**
  - FIXED ₹X (X = SN363's S\* and ₹2,000);
  - PROFIT-ONLY (V1);
  - BASE+VAR = ₹1,000 base + 50% of spare above one wallet.
- **Report:**
  - median monthly payout;
  - months with nothing payable;
  - payments that dip into opening principal;
  - growth delays.
- **The gap:** the extra after-cost net per eligible gap session needed for ₹750 a session, without touching the cash Gold needs.

### SN375: survivors in the shared wallet
At most two candidates that pass their own slots go through `sn352.Journal` with Gold-first ordering, pre-emption and pending exits, on a fresh block. Otherwise the slot is recorded as not triggered.

## 2. Own slots (SN376–SN380)

### SN376: the auction direction through a vega-light option
- **Question:** SN361 says the opening premium is rich in volatility. A 1-strike in-the-money option carries more direction per rupee of volatility risk. Does the auction direction pay when expressed that way?
- **Arms:** on SN353 (b)'s 172 sessions and SN371's GAP sample, the auction / gap side bought 1 strike ITM (2 strikes when one lot ≤ ₹15,000) at 09:16 and at 10:15, held 20 / 60 minutes.
- **Compared with:** the ATM leg on the same sessions, plus a coin-flip ITM control.
- **Advance:** as SN371.

### SN377: is the opening premium always rich?
- **Measure:** IV(09:16) − IV(previous session 15:00) for the front ATM straddle (synthetic forward, as SN361), on gl DEV + TEST.
- **Buckets:** terciles from earlier sessions only.
- **Measured:**
  - the straddle's 09:16 → 10:15 residual R (SN361);
  - the auction / gap side's single leg at 09:16, 60-minute net.
- **Question:** does the cheapest-open tercile carry no richness and leave the direction profitable at ₹205?
- **Advance:** that tercile's 60-minute net at ₹205 > 0 with ≥ 100 trades and ≥ 3 of 5 years positive.

### SN378: does the option pair lead the future?
- **Signal:** b(t) = the ATM pair's synthetic forward − the futures mid (front expiry), on archive snapshots. z(t) = (b(t) − mean of b over the prior 30 minutes) / its std (prior 30 minutes).
- **Event:** |z| ≥ 2 while the futures mid moved < 0.05% over 10 minutes; one per 30 minutes.
- **Prediction:** the future moves toward the synthetic.
- **Measured / controls:** as SN368. A recorder version is frozen forward only if development shows follow-through.

### SN379: signed option flow
- **Signal:** on archive snapshots, for ATM ± 2 strikes, each minute's volume increment signed by the snapshot's last price against the previous snapshot's mid (Lee–Ready).
- **Event:** 10-minute net call-buy minus put-buy volume (lots) beyond 1.5 earlier-only std while futures are quiet.
- **Prediction:** call-buying means up.
- **Measured / controls:** as SN368.

### SN380: one follow-up, chosen by a rule frozen now
After SN366–SN379, the development arm with the highest gross (zero-stress) net per trade among those with ≥ 100 trades that are positive at ₹205 gets one combination test:
- its best mechanism expressed through SN376's ITM leg;
- entered after SN371's 10:15 reset when it is an opening signal;
- frozen forward on the recorder.

If no arm qualifies, the information measure with the strongest futures follow-through (SN368 / SN378 / SN379 / SN372) is frozen forward on the recorder as an information test, with the option trade reported beside it.

## 3. Order of work
1. SN366 (after hours, own round; gate W first).
2. SN371 → SN376 → SN377 (the opening family, same data).
3. SN368 → SN378 → SN379 → SN372 (pressure sensors on real quotes).
4. SN367 → SN373 → SN374.
5. SN370 / SN369 checks → SN380 → SN375.

## 4. Amendments
- **B1 (fw6, Nov 16, before any CAS session exists):** expiry-day rows are reported separately as research evidence and are excluded from the trade count, the pass rule and the controls, because they fall outside the owner's expiry-day clock. Code in `sn351/fw6.py`.
- **B2 (SN368, Nov 16, before any SN368 number):** the archive tracks about 11 strikes near the money. At 10:30 on Oct 1, OTM puts reach −0.27 delta and calls 0.18, so 25-delta wings are never bracketed (plumbing check, no outcome read). The archive development uses a **30-delta** risk reversal (`chainlib.RR_DELTA`). A recorder forward version (41 strikes) would use 25-delta.
- **B3 (SN368, Nov 16, before any SN368 number):** even at 30 delta the archive never brackets the next expiry's wings. The frozen two-tenor SN368 is therefore not computable on the archive and closes there for that reason. A front-only diagnostic (the same rule, one tenor) runs as development evidence. The two-tenor version needs the recorder.
