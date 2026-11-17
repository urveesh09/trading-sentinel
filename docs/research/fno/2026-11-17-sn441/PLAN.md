# SN441–SN455: the true direction hurdle, the value of waiting, discount and passive entries, honest fill persistence, Gold's real cost at size, an affordable strike under a full-loss bound, bank results, the London clock, expiry-afternoon hedging flows, a future-blind check of Gold, and how much a development number is worth (plan, frozen before any number; Nov 17, 2026 ~12:00 IST)

**Owner (Nov 17):** the auditor's SN441–SN450 (`docs/SN441_SN450_RESEARCH_BRIEF.md` and the 15-row filing CSV, committed as received in `6141c1df`) plus five own slots. The owner's words: "use the learnings … the web, the famous GitHub repos … properly test the SN slots so we can get the new gold … tell me the returns … if we change any parameter".

**Checked before this plan:**
- **The NIFTY 2023 expiry-day chains are a protected exam.** The history database holds full 1-minute chains with OI on 48 NIFTY 2023 expiry days (49 with OI), next to 52 (2024) and 53 (2025). The testing method keeps "the 2023 expiry exam" protected for the expiry book (`EXAM_E03_FAMILY.md`). Only counts were read here. No slot in this round reads 2023 expiry-day option prices.
- **Disclosure from SN427 (last round).** SN427 B priced one 2023 expiry morning on Breeze's 1-second opening-ATM data: 2023-12-28, one strike, 11:22–13:30. That touched the protected 2023 expiry window for one session's morning. It is recorded here; the afternoon full-chain exam shape (13:00–15:30) was not read.
- **Production's signal log** (`fno_signals` in the sealed export, Sep 10 – Nov 13) holds about 100 NIFTY directional FNO_PAPER decisions with time, side, strike, expiry, premium and delta: 23 accepted plus rejects after the signal formed (expiry_day_block 32, trades_per_day 17, kill_switches_clear 10, concurrency 8, reward_risk 6 and others).
- **The replay's fees** use the 2026-04-01 schedule (0.15% STT on option sales) for every year, so pre-April-2026 replays are charged slightly more than the dated schedule.
- **Outside sources read for the own slots** (method, never parameters):
  - option-expiration pinning (Ni, Pearson & Poteshman 2005; Golez & Jackwerth 2012);
  - hedging-demand intraday momentum (Baltussen, Da, Lammers & Martens, JFE 2021);
  - hftbacktest's conservative queue model (a resting order fills only when price trades through it);
  - freqtrade's lookahead analysis (recompute each decision with the future removed);
  - the SN history itself (development against held-out results).

**Unchanged rules:**
- Gold v5 at ₹30,000.
- One bought index option; nothing is sold or margined.
- ₹3,000 intended stop for challengers.
- Stress of ₹205 / ₹400 a lot plus Zerodha charges.
- Production read only; nothing places an order.
- The forward verdicts (fw5–fw9 and companions, SN300a, F1) stay unopened, and recorder sessions from Nov 17 stay unread.
- Every script is committed before it runs; results are written once; crashes are fixed before any number and disclosed.
- Frozen evaluations are never overwritten.

**Shared panel (SN441 / SN442 / SN454):** SN412's 42 sealed archive days (export `20261116T103002Z`, one snapshot a minute, walked one-lot prices, lot 65, entry ≤ ₹15,000). Clocks 10:00 / 11:00 / 13:00 (minute index 45 / 105 / 225; an expiring contract only to 13:30). Labels EXPIRY / GOLD / EMPTY / NO_REPLAY as in SN428.

**Legal exit rule (all panel slots):** a scheduled exit at minute x takes the walked bid at the first usable snapshot at or after x, within 5 minutes. If none exists, the row is UNRESOLVED and is reported, never priced from an earlier mark. A stop exits at the first usable snapshot whose mark is ≤ −₹3,000, at that snapshot's walked bid.

## 1. The auditor's slots

### SN441: a common two-sided decision ledger for direction
- **Rows:** every day × clock, both 1-ITM sides (CE and PE) on the front expiry, contract fixed at the clock.
  - Each row is ENTERED, UNAFFORDABLE, NO_QUOTE or UNRESOLVED.
- **Common cells:** both sides priced at both stresses.
  - Per cell: better, worse and coin = their mean.
  - Implied threshold p* = −worse / (better − worse).
  - Reported overall and by label (EMPTY = Gold-empty).
- **Where the hurdle comes from:**
  - p* gross (no fees or stress), with fees only, with fees + ₹205, and with fees + ₹400;
  - the coin mean under SN428's old exit rule against the legal rule on the same cells (alignment);
  - the coin mean on all priced cells against common cells (affordability and missing quotes).
- **Uncertainty:** 2,000 date-block bootstrap resamples for coin and p*.
- **Parity:** SN428's own `trade()` reproduces its receipt's BASE and SIDE means.
- **Fixture:** a synthetic contract with a bid only at minute 5 must give UNRESOLVED under the new rule. The old rule gives the minute-5 mark.

### SN442: the value of waiting once a signal exists (contract locked)
- **Locked at the clock:** each side's 1-ITM contract and expiry, with a maximum debit of ₹15,000.
- **Arms:**
  - NOW;
  - WAIT-1 / WAIT-5 / WAIT-15 (unconditional, at that snapshot's walked ask);
  - BEST-30, the hindsight lowest walked ask in the next 30 minutes, same contract.
- **Exits:**
  - A: a common deadline at clock + 60 (main);
  - B: each arm holds 60 minutes from its own entry (diagnostic).
- **SN428 decomposition on the same cells:**
  - TIMING as SN428 ran it (±30 minutes, re-chosen strike, shifted exit);
  - FWD-RECHOSEN (0 to +30, re-chosen strike, shifted exit);
  - FWD-LOCKED (BEST-30 with exit B).
- **Reported:** paired means against NOW per side, label and clock; no-fills.

### SN443: a discount while the directional premise holds (Production's signal stream, real quotes)
- **Decisions:** Production's NIFTY FNO_PAPER directional rows (accepted, or a post-signal reject), Sep 10 – Nov 13.
  - The first per (day, side), then at least 15 minutes apart.
  - Contract: the signal's own strike, type and expiry if the archive recorded it, else UNRECORDED (counted).
  - Decision minute: the first snapshot after `evaluated_at`.
- **Premise:** the break holds.
  - A long fails if the front future trades back below `or_high`; a short fails above `or_low`.
  - Without those levels, it fails on a 0.15% adverse futures move.
- **Delta:** Δ = (V_K − K × (V_{K+50} − V_{K−50}) / 100) / F, from same-snapshot mids (the homogeneous-option identity). Fallback: the signal's recorded delta.
- **Arms, all with a 5-snapshot window:**
  - NOW;
  - DELAY-1 / 2 / 3 / 5 (unconditional);
  - PLAIN: buy if ask ≤ ask₀ − D;
  - DISCOUNT: buy if ask ≤ ask₀ + Δ(F_t − F₀) − D.
  - PLAIN and DISCOUNT cancel when the premise fails or the window ends.
  - D = ₹1.00 a unit (₹65 a lot).
- **Exit:** the same for every arm: decision + 60 minutes, or the ₹3,000 stop.
- **Reported:**
  - per original decision: fills, misses, and net with misses at zero;
  - missed NOW winners;
  - paired fill improvements.
- **The branch closes** if DISCOUNT does not beat NOW and PLAIN at both stresses.

### SN444: an honest five-second execution companion (built and frozen now, scored on future recorder data)
- **Module `fx5.py`**, on one decision (contract, side, cap = decision ask + 2 ticks, per-level cap as in fw7c, the same exit rule).
- **Arms:**
  - IMMEDIATE: legal capped arrival;
  - DELAY-5: an unconditional 5-second wait, then capped arrival;
  - CONFIRM-5: needs observed persistence.
    - Every valid packet in (t, t + 5] has inside ask ≤ ask₀ and five-level depth ≥ one lot.
    - The first valid packet is within 2.0 s of t; the last is at or after t + 3.0.
    - No two valid packets are more than 2.0 s apart (the house freshness rule).
    - Otherwise NOT_CONFIRMED.
  - PASSIVE-5 (from SN454): rest a buy at bid + 1 tick for 5 s.
    - It fills only if a packet shows ask ≤ the limit, or a trade prints strictly below it (trade-through).
    - Otherwise it crosses with the cap.
- **Charges:** commissions on all fills; stops and the unresolved exit rule apply.
- **Reported:**
  - paired fill improvement against IMMEDIATE;
  - the missed-trade opportunity cost per original decision.
- **Tests:**
  - a synthetic window with a single packet at 0.9 s must give NOT_CONFIRMED;
  - a gap of more than 2 s must fail;
  - a full window must pass.
- **Mechanics run:** the Nov 16 plumbing copy only (labelled plumbing).
- **Prospective score:** on fw7c's decisions from the recorder sessions after the freeze, once 60 decisions exist, read once.

### SN445: Gold's cost at its own clock and size
- **A. SN440's 41 paper rounds, re-referenced:**
  - the model price from the last *complete* minute bar before the fill;
  - the archive snapshot nearest before the fill, with its provider timestamp read from the raw files and the displacement in seconds;
  - the full-lot walk;
  - fees by order;
  - the futures move between the two timestamps × delta, reported apart.
- **B. Gold's own replay trades inside the archive window** (2026 path, Sep 10 – Oct 28, at the replay's entry and exit minutes and lots):
  - the archive's walked ask and bid for the trade's full quantity against the replay's model prices;
  - real minus model per lot, by lot bucket (1 / 2–3 / 4+);
  - INSUFFICIENT rows kept.
- **C. Fees:** the effect of the dated STT (0.1% before Apr 1, 2026) against the replay's 0.15% on Gold's 2023–26 trades.

### SN446: an affordable strike under the full-loss bound
- **Gold v5 at ₹30k, no adds.** At each signal, try in order:
  - Gold's normal strike (its own ITM cascade);
  - ATM;
  - one step OTM.
- **Take the first (highest delta) where at least one lot fits:**
  - lots ≤ Gold's lots;
  - lots × ask × 65 + entry and exit fees at the entry price + stress × lots ≤ the remaining day room (20% of the wallet + the day's realized net).
  - Otherwise skip.
- **Arms:**
  - BOUND-NORMAL, SN434's BOUND (parity);
  - BOUND-LADDER (the order above);
  - BOUND-LADDER-1LOT;
  - BOUND-ATM-ONLY;
  - BOUND-OTM-ONLY.
- **Paths and stresses:** 2022 and 2023–26, at ₹205 / ₹400.
- **Reported:**
  - trades, skips and the strike used;
  - net, worst month, worst day and refills;
  - the mean per-lot result by strike class;
  - the largest debit at risk.

### SN447: the bank-results screen from the supplied timestamps
- **Events:** the CSV.
  - Duplicate issuer-dates keep the first release (Kotak Jul 18 18:43 is dropped as SAME_ISSUER_DATE_REVIEW).
  - The reaction session is the first session opening after the filing; an in-session filing is flagged IN_SESSION.
  - Overlap is counted by reaction session.
- **Stock bars:** Kite 15-minute and daily, Jan–Jul 2026.
  - Abnormal return = stock − β × NIFTY 50, with β from the prior 60 daily returns.
  - First reaction R1: previous close → 09:45 (the gap and two completed bars).
  - Residuals R2 from 09:45 to 11:45 and from 09:45 to the close.
- **Control:** the same stock's 10 ordinary sessions (no filing within ±1 session) nearest in |abnormal R1|.
- **Statistic:** continuation = sign(R1) × R2.
  - Event mean against matched-control mean, block by reaction session.
- **NIFTY mapping:** on reaction sessions, sign(weighted filer R1) against NIFTY's R2.
  - Priced on gl's NIFTY minutes: a 1-ITM front weekly bought at 09:45, out at 11:45 or the ₹3,000 stop, ₹205 / ₹400.
- **Verdict:** INSUFFICIENT below 20 independent sessions, whatever the sign.

### SN448: the London open as an outside clock
- **Clock:** LSE 08:00 London = 13:30 IST on GMT and 12:30 IST on BST.
  - BST runs from the last Sunday of March to the last Sunday of October, computed.
  - LSE-closed days use England's bank holidays, coded with their dated exceptions.
- **Data:** NIFTY index 1-minute bars, Jan 2020 – Oct 2026 (Breeze, read only).
- **Activity:** the mean |5-minute return| in each 5-minute window, 11:30–14:30 IST.
  - Difference-in-differences: (12:30 – 13:30 window activity) on BST days minus the same on GMT days.
  - Also the four weeks either side of each clock change.
  - LSE-closed days as the placebo.
- **Residual:** after the first completed 5-minute bar from the London open, the continuation hit rate and mean signed move to +30 minutes.
  - The 30-minute |move| against the option-cost hurdle in points.
- **No direction from the calendar.**
- **The signed UK-surprise test is BLOCKED:** no eligible timestamped UK futures or opening-basket series in hand.

### SN449: achievable frequency and how long a verdict needs
- **For each arm with a positive development mean in this round** (and, illustratively, bank-results sessions and the BANKNIFTY last-week cluster):
  - signal share of empty sessions, the executable fill share and the net per fill;
  - the implied per-empty-session gain against the ₹154 / ₹498 targets.
- **Sample size:** block-bootstrap SD per session → sessions needed to detect ₹154 a session (80% power, one-sided 5%).
- **Published:**
  - a stopping rule: stop when the 90% block CI lies wholly above or below ₹154, or at N_max = 3 × the needed sessions → EVIDENCE_INSUFFICIENT;
  - same-date and same-catalyst clustering.

### SN450: the Gold-plus-candidate chronological test
- **Gold-only baseline now** (2022 and 2023–26, at ₹205 / ₹400):
  - all-session net and net without the top 5 dates;
  - payout months;
  - ₹750 days;
  - the longest dry spell (sessions between new equity highs, and the longest run of non-positive sessions);
  - refills.
- **Only a survivor of this round** (at most two independent mechanisms) is frozen into a Gold-plus ledger with Gold priority, charged for blocked cash, day room and missed Gold trades.
- **Otherwise:** NOT_TRIGGERED, with the protocol written.
- **The existing forward tests keep their own verdict dates.**

## 2. Own slots

### SN451: expiry-afternoon hedging flows, pin against momentum (2024–25 only; 2023 protected)
- **Sample:** NIFTY weekly expiry days 2024–25 with ≥ 9 strikes of 1-minute data and OI (105).
- **At 13:00** (closes through 12:59):
  - K_OI = the strike with the largest CE + PE OI;
  - K_pain = max pain over the strikes present;
  - S₀ = the index.
- **Predictions, both from the literature:**
  - PIN: the side toward K_OI when |K_OI − S₀| ≥ 25;
  - MOMENTUM: the sign of the return from the previous close to 13:00 (Baltussen et al.).
- **Outcome:** the index move 13:00 → 15:00 and → 15:25.
- **Reported:**
  - hit rates and the mean signed move with date-block bootstrap;
  - agreement of the two predictions;
  - sensitivity at 12:00 and 14:00;
  - a placebo on the session before each expiry (same expiry chain).
- **Priced:** the expiring ATM option on each prediction's side at 13:00 (model fills as Gold's, charges, ₹205 / ₹400), out at 15:00 or the ₹3,000 stop.
  - This is outside Gold's 13:30 expiring-contract cutoff and is marked so.
- **Exam:** a development pass (hit ≥ 58% with a positive priced mean at both stresses) can only nominate the rule for the protected 2023 expiry exam, on the owner's word.

### SN452: a future-blind check of Gold (freqtrade's lookahead analysis)
- **Method:** for every Gold trade (2022 and 2023–26, at ₹205), recompute Gold's entry decision (strike, lots, ask) on a copy of the session with every option, index and future value after the entry minute removed.
  - Also with the entry day's own daily bar removed from the volatility table.
- **Pass:** zero mismatches.
  - Also: each signal's engine bar time is before the replay's entry minute, from the evaluations' records.

### SN453: SN443's discount rule on Gold's own stream, inside the wallet (Breeze minutes)
- **Arms** (Gold v5, ₹30k, 2022 and 2023–26, ₹205 / ₹400):
  - DEPLOYED;
  - DELAY-1 / 3 / 5;
  - PLAIN-5: ask ≤ ask₀ − D;
  - DISCOUNT-5: ask ≤ ask₀ + Δ(F_t − F₀) − D;
  - DISCOUNT-OR-MARKET-5: DISCOUNT-5, buying at minute 5 if the premise still holds.
- **Definitions:**
  - asks are the replay's model ask of each minute's close;
  - Δ comes from the same identity on the neighbours' closes;
  - the premise fails on a 0.10% adverse futures move;
  - D = 1.5 × the model spread at ask₀, so a bid-ask bounce alone cannot trigger it;
  - Gold's exit minute is unchanged.
- **Reported:** net, trades, misses, and the paired entry improvement.
- **Pass:** better than DEPLOYED in both periods at both stresses.

### SN454: passive entry at the touch, with a conservative fill model (hftbacktest)
- **Panel, minute version:** both 1-ITM sides at each clock.
  - Rest a buy at the decision bid + 1 tick, one lot, for one minute.
  - FILL only if the next usable snapshot's best ask ≤ the limit with ≥ one lot at or under it.
  - Else cross at that snapshot's walked ask (no miss).
- **Panel arms:** NOW and DELAY-1 beside it. The exit is the common deadline clock + 60.
- **Seconds version (Nov 16 plumbing):** SN432's decisions.
  - Rest for 5 s; fill on ask ≤ limit or a trade strictly below it.
  - Else cross with the cap.
- **Reported:** the fill share, the paired price improvement, and the outcome difference of passive fills against NOW (adverse selection).

### SN455: what a development number is worth (the SN program's own record)
- **Pairs:** every frozen candidate in `docs/SN_STRATEGY_HISTORY.md` and the research READMEs it cites that reports both a development (in-sample) result and a later unseen / held-out result for the same rule, extracted with the line reference.
  - Normalized to the per-session or per-lot unit the source uses.
- **Reported:**
  - the share that kept their sign;
  - the median held-out / development ratio;
  - the development level that historically preceded a held-out pass.
- **Its use:** the minimum development effect SN449 should demand.

## 3. Order
SN441 → SN442 → SN454 → SN443 → SN447 → SN448 → SN451 → SN446 → SN452 → SN453 → SN445 → SN444 → SN455 → SN449 → SN450.

## 4. Amendments (added after freezing; disclosed)

- **A1 (details fixed in scripts before their runs; no crash in this round):**
  - **SN441:** the gross and fees-only views reuse the ₹205 exit price.
  - **SN443:** the decision snapshot is the evaluated minute + 1.
  - **SN445:** a junk line was removed before the first run.
  - **SN449:** n is computed for a ₹154 effect at both stresses.
  - **SN450:** Gold sessions without a 15:29 index bar join the calendar (8 dates).
  - **SN453:** NO_DELTA signals enter at the decision as deployed.
  - **SN455:** SN78's "+₹13–17k" development figure enters as its midpoint, ₹15,000.
- **A2 (outcomes):**
  - **SN443 / SN453 / SN454:** closed.
  - **SN447:** INSUFFICIENT.
  - **SN448:** no London clock; the surprise test is blocked.
  - **SN451:** no development pass, nothing nominated.
  - **SN450:** NOT_TRIGGERED.
  - **SN444:** `fx5` is frozen at `6d3b4d93` for its prospective test.
