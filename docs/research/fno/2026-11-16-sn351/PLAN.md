# SN351–SN365: information before the option reprices, the corrected wage ledger, and Gold's independent evidence (plan, frozen before any number; Nov 16, 2026 ~16:15 IST)

**Owner (Nov 16):** the auditor's SN351–SN360 (`docs/SN351_SN360_RESEARCH_BRIEF.md`, committed as received in `390fc644`) plus five own slots. "Take one strategy essence, slot, then give it time … what is tested has to be correctly tested … even if all of these once again fail … we still gain something out of it."

**How this round works (the owner's instruction):**
- **One slot at a time, in the order of section 3.** Each slot gets its own script, committed before its own numbers are computed.
- **This plan freezes each slot's question, data, arms, controls and pass rule.** Where a slot's code needs a detail the plan cannot fix today (a field name, a file format), a dated amendment is added to this file and committed before that slot's own numbers. An amendment may never use that slot's results.
- **Each slot ends with a written lesson,** pass or fail.

**Carried over:**
- Gold v5 at a ₹30,000 starting wallet, with its priority, growth trigger (net profit = wallet), ×1.5 steps, cap of 3, and the 20% day room shared with any leg;
- the companion rule for a candidate: one bought index option, premium ≤ wallet − ₹15,000, a ₹3,000 planned stop inside the remaining day room, existing deadlines and the early expiry cutoff;
- no margin and no selling;
- costs: Zerodha's charges + ₹205 and ₹400 stress per lot per round trip, with the observed-quote difference reported beside them;
- Production is read only, and nothing places an order;
- the SN300a / fw3 / fw4 forward results stay unopened until their verdict.

## 0. Data honesty (what exists on this PC on Nov 16)

| Data | Window | Status |
|---|---|---|
| NIFTY 1-minute index / futures / options (Breeze) | 2019–Oct 2026 (with gaps) | seen |
| Futures **pre-open rows 09:00–09:07** (Breeze 1-minute, near and next month) | Dec 8, 2025 – Oct 2026 (143 day-contract pairs) | in the seen years, but **never used as a signal**. Development use only |
| NIFTY one-second (index + options) | Jan 16 – Apr 2 and Apr 6 – Nov 12, 2026 | seen |
| Real-quote archive (bid / ask, 5 levels, minute snapshots, NIFTY + SENSEX) | Sep 10 – Nov 13, 2026, sealed (42 days); Nov 16 unsealed | seen |
| TR01 tick recorder (full packets with total buy / sell quantity, 09:00 on) | Nov 16 (development); Nov 17 onward is **unseen forward** | Nov 16 dev |
| BANKNIFTY | 4 daily-bar requests only; no minutes, no options, no constituents | **absent** |
| GIFT NIFTY, rate-market intraday data, RBI expectation surveys | none | **absent** |
| Gold v5 / N11 on 2022 | no N11 replay of 2022 exists | **unopened** for Gold (the 2022 tape is seen by other buyer studies) |

**Consequences:**
- every historical result here is a single frozen rule on seen data: development evidence only;
- the auction **imbalance** can be scored only forward, on recorder sessions from Nov 17;
- SN354 / SN355 / SN356 are availability and affordability checks unless their data appear. Nothing is fetched or bought for them (the auditor's condition; a download needs the owner's word).

## 1. The auditor's slots (SN351–SN360)

### SN352: the cash-funded wage and refill ledger (first)
- **Reproduce first:**
  - SN342's old pool (`sn331/sn339_350.pooled`, reserve = one wallet) must give ₹6,54,004 withdrawn and ₹881 a session at ₹205;
  - the auditor's fixture (₹30k trading + ₹30k spare, +₹30k profit, growth to ₹45k): the old equations must pay ₹15,000 and the corrected ones ₹0, leaving ₹45k trading and ₹45k spare.
- **Corrected journal** (a copy of `lab.run`'s growth loop for Gold's wallet, with Gold's day unchanged):
  - **State:** trading cash T (= Gold's sizing wallet W at every session start), spare cash P, owner deposits D, withdrawals X. Margin is zero; Gold holds no position overnight.
  - **Each session:**
    1. At the first session of a new month, apply the withdrawal policy to the previous month-end state.
    2. Session gate: if P < 20% of W (a full day stop cannot be refilled), Gold pauses (policy PAUSE), or the owner deposits the shortfall into P (policy DEPOSIT).
    3. Gold plays. Its day net x settles into P: a loss refills T from P, a profit moves from T to P.
    4. **Growth (Gold's priority):** Gold's trigger is unchanged (progress since the last step ≥ W, cap 3). The step moves ΔW = 0.5 W from P to T only if P − ΔW ≥ 20% of the new wallet. Otherwise the step is **deferred**: the progress is kept, and funding is tried again after each later session.
  - **Daily identity, asserted to ₹0.01 every session:** opening funds + Σ net + D − X = T + P.
  - **Parity:** with unlimited spare cash and no withdrawal, Gold's net must be ₹8,50,882 at ₹205, with day nets identical to `ow.run_wallet`.
- **Withdrawal policies** (monthly):
  - **V1:** everything in P above one wallet (SN342's rule, corrected). In the growth-first form (V1-G), if a step is deferred the keep is W + ΔW. V1-W ignores the pending step.
  - **V2:** everything above a fixed ₹60,000 (SN339's surviving reserve).
  - **F10 / F15:** a fixed salary of ₹10,000 or ₹15,000, paid only from P above one wallet; a month that cannot pay in full pays what it can, and the shortfall is not carried.
- **Funding:** spare P0 = ₹30,000 (owner's total ₹60,000) and ₹60,000 (total ₹90,000); PAUSE and DEPOSIT; ₹205 and ₹400.
- **Report per run:**
  - withdrawn total, a session, a month, and the last 12 months;
  - months paid; longest dry spell;
  - growth steps, their dates and deferred sessions;
  - paused sessions (with signals);
  - deposits (total and worst month);
  - minimum P; final T + P;
  - the identity check withdrawn + final funds − opening funds − deposits = Gold's net.
- **Pass:** this is accounting. It passes when the reproduction, fixture, parity and every daily identity hold. The corrected V1-G at ₹205 replaces ₹881 as the published wage.

### SN353: the futures opening auction (the lead hypothesis)
- **(a) Semantics, before any outcome:**
  - **Sources:** NSE's futures pre-open rules (order entry, random close, matching, buffer); Kite's packet specification.
  - **On the Nov 16 recording,** for the near NIFTY future 09:00–09:15: which fields change (last price, total buy / sell quantity, depth, volume, OI, exchange time); the time of the last changing packet before the order-entry close; whether the 09:08–09:15 price equals the 09:15 open.
  - **On Breeze's pre-open rows:** the price on 09:00–09:06 against the previous close, the 09:07 row's close and volume against the first 09:15 trade, and the signed "volume" against the recorder's quantities on any overlapping day.
  - **Gate G1:** if total buy / sell quantity cannot be identified as the auction's queued (unmatched) demand, the imbalance arm is closed and recorded; the price-only arm continues.
  - **Gate G2:** the auction price is the 09:07 row's close only if (a) shows it is the matched price; otherwise it is the 09:15 open.
- **(b) Price-only development arm** (Breeze, Dec 8, 2025 – Oct 28, 2026, non-expiry sessions, seen data):
  - **Signal:** auction gap g = auction price / the previous session's last futures close − 1. Buckets |g| < 0.2%, 0.2–0.5%, > 0.5%.
  - **Entry:** the first tradable decision is 09:16 (minute index 1), via gl's executable model. One lot of the front-weekly ATM option.
  - **Arms:** CONT buys the side of g's sign, FADE the opposite side. Each is held 5 / 20 / 60 minutes with a ₹3,000 stop on minute closes.
  - **Control:** a seeded coin-flip side on the same sessions at the same clock.
  - **Report:** net at ₹0 / ₹205 / ₹400 by bucket; the index move from the auction price to 09:16 (how much is already priced); and the same on the real-quote archive (Sep 10 – Nov 13, walked ask / bid at the first snapshot ≥ 09:16).
  - **Advance:** the price-only rule needs, at ₹205, a 20-minute net per trade > 0 on Breeze with ≥ 60 trades, above the coin flip, and the same sign on the archive. Otherwise it is closed. The imbalance arm runs forward regardless of (b), because its information is different.
- **(c) Imbalance arm, forward** (`sn351/fw5.py`, frozen with this plan's amendment before Nov 17's session is scored):
  - **Signal:** I(t) = (buy − sell) / (buy + sell) of the near future's last packet at or before 09:05:00 and 09:06:00.
  - **Persistent:** the same sign at both clocks and |I| ≥ 0.20 at both.
  - **Acceptance:** the futures mid at 09:16:00 is on I's side of the auction price.
  - **Price cap:** abstain if the mid has already moved ≥ 0.15% from the auction price in I's direction.
  - **Trade:** buy the front-weekly ATM option on I's side at fw2's execution contract (first valid ask 0.5–2.5 s after 09:16:00, walked through five levels). Hold 20 minutes, with a ₹3,000 stop; 5 and 60 minutes are diagnostics only.
  - **Controls:** the opposite side at the same clock, and the price-only CONT rule on the same sessions.
  - **Scored once** after the 20th qualified session (with SN300a's window), counting every decision, abstention, miss and stale packet.
  - **Pass:** ≥ 15 trades; net at ₹205 and ₹400 > 0; above both controls; and > 0 without the best day. Fewer trades: INSUFFICIENT, and the arm keeps collecting.
- **Nov 16** is a development session for plumbing only: no tuning.

### SN351: where a profitable option move is still available (opportunity map)
- **Data:** gl's DEV sample (NIFTY Apr 2022 – Aug 2026, modelled quotes) for breadth; the real-quote archive (Sep 10 – Nov 13) for executable checks.
- **Decisions:** fixed, non-overlapping clocks (09:30, 10:30, 11:30, 12:30, 13:30); the front-weekly ATM CE and PE, one lot each; non-expiry sessions.
- **State at the decision** (the prior 15 minutes of the index):
  - QUIET: |move| < 0.10%;
  - JUST-MOVED: |move| ≥ 0.25%, ending at the decision;
  - SETTLED: a ≥ 0.25% move that ended 15–30 minutes earlier, and the option spread back at or below its session median (archive only);
  - with the side WITH or AGAINST the move.
- **Measured:**
  - quoted cost of one lot;
  - time to the first executable gain of ₹300 and ₹750 (bid-side, after charges) within 60 minutes;
  - the share stopped at −₹3,000 first;
  - the residual payoff at 5 / 20 / 60 minutes;
  - the hindsight ceiling (best executable bid in the horizon), kept apart from realized returns.
- **Room:** a state has room if its mean 20- or 60-minute net at ₹205 is > 0 with ≥ 100 decisions on DEV and the same sign on the archive. A state with room is only a target for a future predictor, never a strategy.

### SN354: GIFT NIFTY residual
- **Availability check:** search the PC for timestamped GIFT NIFTY data. None is expected.
- **Record** the exact series needed: per-minute NSE IX GIFT NIFTY futures, 15:30 (previous day) to 09:15, with exchange timestamps and contract months.
- **Then close as BLOCKED,** with no fetch. If such data appear, the frozen test is the auditor's: the overnight residual against the local indicative open, with SN353 as the baseline.

### SN355: RBI surprise transmission
- **Feasibility:**
  - list the scheduled MPC decision days inside the seen option windows from RBI's own press-release record (dates only);
  - count them;
  - state what is missing: pre-event expectations, intraday OIS / G-sec reaction and release timestamps.
- **Without a surprise measure, the hypothesis is untestable here.** A calendar-only option map on those days (SN351's measures at 10:15 / 10:30 / 11:30 against matched non-event days) is reported as a description, never as a signal.

### SN356: the sector that moved (Financials)
- **Blocked:** no bank-constituent minutes or BANKNIFTY option quotes are on the PC.
- **Record affordability arithmetic** from published contract facts (BANKNIFTY monthly lot and a typical ATM premium against the ₹15,000 debit room of a ₹30,000 wallet), with sources and dates.
- **Catalogue** what a download would need (`docs/SN_PROBLEM_STATEMENT_EMPTY_DAYS.md`), for the owner's decision.

### SN357: what the chain already charges
- **Runs only on a candidate event** that reaches a trade rule (SN353 (b) advancing, or SN353 (c) / SN361 giving an opening decision).
- **Diagnostic:** on the real-quote archive's synchronized snapshots at that decision clock, the call / put vertical-spread-implied probabilities across neighbouring strikes, with monotonic / convexity checks and bid / ask bounds.
- **Compared:** premium-only, ATM-IV-only and strike-based information, against the realized intraday path to break-even. No maturity probability is read as a 20-minute probability.
- **If no candidate exists,** it is recorded as not triggered.

### SN358: Gold on 2022 (N11's frozen exam, `simulation/2026-11-02-fno-n11/EXAM_2022_N11.md`)
- **Route:** SN336's recorded route, in its own round after market hours, only while free RAM stays above 3 GiB:
  1. reproduce a known TEST2025 slice through N08 → N09 → N10 → N101 → N11 and compare event and contract identities at each stage;
  2. build the 2022 year dataset;
  3. run the frozen exam once;
  4. run Gold v5 unchanged on the resulting 2022 stream.
- **Report:** reason codes, costs, drawdown and missing data, against the sheet's questions A–D.
- **If the wiring check cannot be completed,** the blocker is recorded and nothing is inferred.

### SN359: V8 lifecycle on real depth
- **Data:** Gold v5's replay decisions inside the real-quote archive window (Sep 10 – Oct 28, 2026), and Gold's paper decisions on recorder days later.
- **The SN337 / SN338 lifecycle on the snapshot depth:**
  - entry LIMIT at ask + 2 ticks, filling only the quantity at the levels ≤ the limit;
  - a partial fill keeps what filled, and the rest is cancelled at the next snapshot;
  - adds by the same rule;
  - the stop and exits are LIMIT_THEN_MARKET at bid − 2 ticks, walking the bid levels; whatever is unfilled sells at the next snapshot;
  - every original Gold decision is counted (missed winners included).
- **Report:** V8 net against the replay's modelled net on the same decisions (retained share), partial fills and misses. `fw4`'s SN346 is left frozen and reported under its own definition.

### SN360: survivors in the shared wallet
- **Runs only for a candidate passing its own slot:** at most two.
- **Replay:** SN352's journal with Gold-first ordering, pending exits charged against cash, and the candidate blocking a later Gold fill when cash is tied up.
- **If none survives,** it is recorded as not triggered, and SN352's journal is the harness left for later.

## 2. Own slots (SN361–SN365)

### SN361: opening premium richness (the hurdle for any opening entry)
- **Question:** does an option bought at the first tradable minute (09:16) carry extra price that bleeds out over the first hour, beyond the underlying's move? SN353 trades exactly then.
- **Data:** the real-quote archive (non-expiry sessions; mids of the front-weekly ATM straddle and single legs); gl's DEV sample (modelled, longer).
- **Measured:** Black-76 implied volatility from the mid (the future as forward, the chain's expiry at 15:30) at 09:16, 09:45 and 10:15; the change; and the rupee cost per lot of that change at the 09:16 vega.
- **Control:** the same change measured 11:00 → 11:30 → 12:00.
- **Result:** "an ATM option bought at 09:16 loses ₹X a lot to volatility normalization by 09:45". It is a hurdle number for SN353 (and any opening rule), with no pass / fail.

### SN362: Gold's signal through SENSEX options
- **Question:** the same Gold decision bought in SENSEX options instead of NIFTY: does the different instrument (another expiry weekday, other premiums and spreads) keep more rupees?
- **Data:** Gold v5's replay trades inside the SENSEX minute window (May 2024 – Apr 2026, seen); SENSEX options from gl's EXAMS mirror (now seen), with prices on gl's model and SENSEX spreads from the real-quote archive.
- **Pairing:**
  - the SENSEX front-weekly option at the same moneyness step, bought at Gold's entry minute and sold at Gold's exit minute;
  - with the same rupee premium budget, so lots = floor(Gold's paid premium / SENSEX premium per lot), ≥ 1;
  - SENSEX stress = ₹205 × (SENSEX real spread per ₹ of premium ÷ NIFTY's), measured on the archive at Gold's clocks.
- **Pass (a routing candidate):** the mean paired difference (SENSEX − NIFTY) > 0 at both stresses, in both halves of the window, and > 0 without the best trade. Otherwise Gold stays on NIFTY, with the measured gap recorded.

### SN363: the owner's salary on the corrected ledger
- **Fixed salary:** on SN352's journal (V1-G keep, PAUSE policy), the largest fixed monthly salary S\* (₹500 steps) such that over Jan 2023 – Oct 2026:
  - Gold never pauses and needs no deposit;
  - every triggered growth step is funded within 21 sessions;
  - computed at ₹205 and ₹400, for spare P0 = ₹30k / ₹60k / ₹90k.
- **Start-date luck:** S\* again starting Jan 2024 and Jan 2025 (each with a fresh ₹30k wallet).
- **Capital for the wage:** the smallest P0 (₹10k steps) at which ₹15,750 a month (₹750 × 21 sessions) is sustainable by the same test.
- **Report:** S\* and its per-session equivalent; months below S\* if it were paid anyway; final funds.

### SN364: the new closing window from Dec 7 (CAS 2.0), frozen forward observation
- **Question:** from Dec 7, the cash market runs a closing auction 15:30–15:45 while F&O trades on. Do NIFTY futures and next-week options in 15:30–15:45 drift toward the auction's indicative close, and does a one-lot option bought at 15:31 and sold at 15:44 have room after costs? New rules can leave a gap before participants adapt.
- **Data:** recorder sessions from Dec 7. This **needs** the recorder to run to 15:46 (SN329's `tick_recorder` change, in Dev, not deployed).
- **Measured per session:**
  - the futures mid at 15:30:30 / 15:35 / 15:40 / 15:44:30;
  - the index's official close;
  - the direction of the 15:30 → 15:44 futures move against the 15:00–15:30 move;
  - a one-lot next-week ATM option on the 15:00–15:30 direction, bought at fw2's execution at 15:31:00 and sold at 15:44:00. This sits after Gold's last exit, so there is no wallet conflict.
- **Scored once after 15 qualified CAS sessions.**
  - **Pass:** net at ₹205 and ₹400 > 0, above the opposite-direction control, and > 0 without the best day.

### SN365: the auction's information on Gold's own decisions
- **Question:** does the auction say anything about the one strategy that earns?
- **Data:** Gold v5's replay trades Dec 8, 2025 – Oct 28, 2026, labelled by whether the trade's side agrees with the price-only auction gap sign (g, SN353 (b)).
- **Measured:**
  - net per lot and win rate for agree against disagree, at ₹205;
  - a 10,000-shuffle permutation p-value of the difference.
- **Freeze a size note only if** p < 0.10 and the agree group's net per lot is ≥ 2 × the disagree group's. The note would be a forward-only observation on recorder days with I, never a Gold rule change from this sample.
- **Otherwise it is recorded as "no information".**

## 3. Order of work
1. SN352 → SN363 (accounting; the owner's wage).
2. SN353 (a) / (b) → SN361 → SN365 → SN353 (c) freeze (before Nov 17 is scored).
3. SN351.
4. SN362.
5. SN359.
6. SN358 (own round, after hours).
7. SN357 (if triggered), SN354 / SN355 / SN356 checks, SN364 freeze, SN360 (if triggered).

Each slot's script and log go in this folder (`results-<slot>.json` written once; a rerun refuses). The README collects the results and the lesson of each slot.
