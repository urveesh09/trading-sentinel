# SN426–SN440: Gold's missing expiry mornings, which decision makes the hindsight money, exits, fills, a hard loss bound, and Gold's feed / clock / cost (plan, frozen before any number; Nov 17, 2026 ~10:20 IST)

**Owner (Nov 17):** the auditor's SN426–SN435 (`docs/SN426_SN435_RESEARCH_BRIEF.md`, committed as received in `f3c4fc1d`) plus five own slots, "properly test … tell me the returns … if we change any parameter".

**Agreed with the auditor, checked before this plan:**
- **Production logs expiry-day candidates.** Its `fno_signals` export logs N11 candidates on expiry days as `expiry_day_block`, with a direction (3 a day on Oct 27 and Nov 3).
- **The replay meets them too.** N11 meets expiry days and drops its candidates at `chain_unavailable:calendar_expiry_not_archived`: 139 such funnel counts in 2024, from the base lab's `_entry`.
- **Breeze's expiry-day data:**
  - the expiring contract's opening-ATM strike, CE and PE, at 1-second and 10-second resolution all day, on 87 NIFTY expiries (Jun 2023 – Sep 2026);
  - no next-week chain on expiry days (SN398).
  - The real-quote archive holds both tenors on its expiry days.
- **SN422 checked untaken signals on zero-trade days only.**
- **SN412 labelled the archive's expiry days EMPTY.**
- **`sn01_data._ffill` back-fills a missing leading bar** from a later candle.

**Unchanged rules:** Gold v5 at ₹30,000; one bought index option; ₹3,000 intended stop for challengers; ₹205 / ₹400 stress plus Zerodha charges; Production read only; nothing places an order. The forward verdicts (fw5–fw9 + companions, SN300a, F1) stay unopened. Every script is committed before it runs; results are written once; crashes are fixed before any number and disclosed. Frozen evaluations are never overwritten: reruns write to this round's `_local`.

## 1. The auditor's slots

### SN426: reconcile the dates and every entry decision
- **Dates:**
  - one row per NIFTY session in Breeze's daily bars (Jan 2022 – Oct 28, 2026);
  - labels: GOLD_SESSION, EXPIRY (the session date equals a front-weekly expiry in Gold's sessions or Breeze's option request keys), SPECIAL (a muhurat evening: no regular 09:15 index bar), DATA_HOLE (regular index minutes but no option session in Gold's data), UNRESOLVED;
  - the 12 unmatched dates each get their evidence (index minutes, option request keys, weekday).
- **Signals:** every N11 / R0.85 stream signal 2022–26 is joined to Gold's log (day, entry minute) and classed:
  - TAKEN;
  - DUPLICATE (the same day and minute as a taken signal from the other book);
  - BUSY (a Gold position was open at its minute);
  - LATE (at or after Gold's last entry minute);
  - EXPIRY_MISMATCH;
  - DAY_STOP (the day's room was spent);
  - OTHER.
- **Reported:** counts by year, and per-market-session net with all dates in the denominator.

### SN427: Gold's signal on expiry mornings
- **A. Candidates.** A rerun of N11 and R0.85 (2023–26, `driver`-style, into `_local`) with one in-memory hook. Each time the base lab counts `chain_unavailable:calendar_expiry_not_archived` on an expiry day, the candidate's clock, bar, direction, futures price, stop level and book are recorded. The trades must equal the saved evaluations' economics (wiring check).
- **B. Screen, the expiring contract** (Breeze 1-second data, 87 expiries):
  - the first candidate per expiry morning (09:20–12:30) per book, deduplicated across books;
  - priced on the opening-ATM strike on the signal's side, only if that strike is within 50 points of the futures price at the candidate's clock (else UNPRICED);
  - entry at the first 1-second trade ≥ 1 s after the decision + a 0.5-tick half spread + charges;
  - exit at the index crossing N11's stop level, a ₹3,000 premium stop, or 13:30 (first trade at or after), less a half spread;
  - ₹205 / ₹400 stress;
  - control: a seeded random side at the same clock.
- **C. Paired tenors on real quotes** (archive expiry days with an N11 candidate, Sep 10 – Oct 28): the expiring and the next-week ATM on the same decision, walked asks and bids, the same exits.
- **Learning:** whether the missing coverage is worth anything at executable prices. A pass would be a forward arm, never a runtime change.

### SN428: which decision makes the hindsight money
- **Panel:** the archive panel (SN412's 42 days; expiry days labelled).
- **Fixed clocks** 10:00 / 11:00 / 13:00. **Base rule:** a seeded side, the 1-ITM front contract (affordable), held 60 minutes or to the ₹3,000 stop, walked prices.
- **Hindsight over one decision at a time:**
  - SIDE (the better of CE / PE);
  - CONTRACT (the best affordable strike / expiry in the recorded universe, same side and exit);
  - EXIT (the best exit minute before the stop within 60 minutes);
  - TIMING (the best entry minute within ±30 minutes);
  - SIDE + EXIT jointly.
- **Reported:** mean net and the share ≥ ₹750 per cell (₹205 / ₹400), the capture fraction of the full SN412 ceiling, and unpriced cells.

### SN429: does the trade still deserve its time (Gold's entries)
- **Rule:** at a checkpoint K minutes after entry (K = 30 / 60 / 90), exit if the index has not moved in the trade's direction since entry (cut losers); else hold to Gold's exit. Applied through the stream: N11's exit minute is set to the checkpoint when the rule fires, using gl's index closes.
- **Paths and gate:** fit on 2023–26, judge on 2022 (Gold's unseen year).
- **Reported:** losses saved, winners cut, and net at ₹205 / ₹400.
- **The branch stops** if the rule removes the large winners.

### SN430: the morning after a bank's results
- **Source:** NSE's corporate-announcements API (public, the auditor's query) for the 12 BANKNIFTY constituents, Jan – Jul 2026; the first financial-results filing per issuer-quarter with its `exchdisstime`.
- **Event:** the next session's first two completed 15-minute bars (to 09:45).
- **Measured:** the stock's market- and peer-adjusted move from 09:45 to 11:15 and to the close, signed by its 09:15–09:45 residual, against matched non-filing sessions of the same stock with a similar opening residual.
- **Cash level only.** It stops before any option if events are < 15 or the move is spent by 09:45.

### SN431: F1 on native BANKNIFTY books
- **Blocked:** F1's data requires the recorder change `1bfed1d0`, which is not deployed (Production is checked read only).
- **Reported:** the status and the calibration checks to run once data exists.

### SN432: 5 and 30 seconds of fill persistence (development recorder slice)
- **Decisions:** on the Nov 16 recorder copy (plumbing only, 09:16–10:19), every whole minute is a decision time for the ATM and 1-ITM CE / PE.
- **Measured:**
  - how long the inside ask and full-lot depth persist;
  - IMMEDIATE (the first fresh packet ≥ 0.5 s, capped) against CONFIRM-5 (enter only if the ask has not risen and full-lot depth persisted for 5 s) and CONFIRM-30;
  - each with its bid 60 s and 300 s later;
  - a time-matched random wait as control.
- **Reported:** missed entries and their later bids.
- **One morning is plumbing evidence only;** the prospective test is specified.

### SN433: Gold's own clock once it trades
- **Production check (read only):** the Gold ledger's trades so far.
- **The adapter defect:** the sessions whose first index or futures minute is missing (`_ffill` back-fill), and whether any Gold decision falls inside a back-filled stretch.

### SN434: the opportunity cost of a hard loss bound
- **BOUND arm:** a Gold entry (and every add) is admitted only if its full debit plus charges fits the day room left (20% of the wallet + the day's realized net − open debits); lots are reduced to fit, else skipped. Adds are off (they cannot fit a full-loss bound alongside the parent).
- **Paths:** 2022 and 2023–26, at ₹205 / ₹400.
- **Reported:** trades kept, signals lost by strike / expert, net, worst month, and the worst no-bid exposure.

### SN435: the wage test for any survivor
- **Runs only for a candidate passing** SN427 B / C or SN430 at its stage gate. Otherwise not triggered.

## 2. Own slots (SN436–SN440)

### SN436: widen Gold's feed with one more panel book
- **Runs:** DEPLOYED (N11 + R0.85) plus each of R0.95, N15, N25, X0.75, X1.25, NO_STAND, NO_LOSS, NO_ADD, NO_VOL, DOUBLE, N08, N10 one at a time.
- **Paths:** 2022 (the exam's own panel evaluations) and 2023–26, at ₹205 / ₹400.
- **Reported:** extra signals, extra trading days, net.
- **Labels:** HELPS only if both 2022 and 2023–26 improve at ₹205.

### SN437: where Gold's edge lives (entry hour, weekday, sessions to expiry, year)
- **Data:** Gold's DEPLOYED trades 2022–26 (₹205), net per lot.
- **Buckets:** entry hour (≤ 10:30, 10:30–12:00, 12:00–13:30, > 13:30), weekday, sessions to expiry (1, 2, 3+), year.
- **A cutoff is named** only if a bucket is negative in both 2022 and 2023–26, with ≥ 10 trades each.

### SN438: size by expert
- **Gold's size rule "setup":** full lots only for the named experts on volatility days, half otherwise.
- **Arms:** {EFF}, {EFF, TPB}, {TPB}, against the deployed "vol".
- **Paths:** 2022 and 2023–26, at ₹205 / ₹400.

### SN439: Gold's exit headroom
- **Per Gold trade** (2022 Apr – 2026, gl's modelled bids), on the chosen contract:
  - the best exit bid before its stop within the trade's own window (entry to N11's exit + extension);
  - the bid at a 30 / 60-minute checkpoint;
  - against the realized exit.
- **Reported:** headroom per lot, the share of trades whose best exit came in the first hour, and whether the cut losers of SN429 were recoverable.

### SN440: Gold's real cost per lot
- **Data:** Production's paper fills (`fno_positions` in the sealed export, Jul 16 – Nov 11).
- **Measured:** entry and exit premium against gl's modelled ask / bid at the same minute and contract (Breeze closes, Jul 16 – Oct 28). The real minus modelled round-trip cost per lot, against the ₹205 / ₹400 stress.
- **Teaches:** which of Gold's ₹617 / ₹319 a real session applies.

## 3. Order of work
SN426 → SN427 → SN428 → SN429 → SN434 → SN436 → SN437 → SN438 → SN439 → SN440 → SN430 → SN432 → SN433 → SN431 → SN435.

## 4. Amendments
(none yet)
