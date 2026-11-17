# SN411–SN425: what was observable, what the day offered, whether another index can take the wallet, and how robust Gold is (plan, frozen before any number; Nov 17, 2026 ~09:10 IST)

**Owner (Nov 17):** the auditor's SN411–SN420 (`docs/SN411_SN420_RESEARCH_BRIEF.md`, committed as received in `361f98ae`) plus five own slots: "properly test the SN slots so we can get the new gold … tell me the returns … if we change any parameter".

**Agreed with the auditor, checked before this plan:**
- **Stale first trade.** `fw7a.auction_price` takes the first packet received at or after 09:15:00 as FIRST_TRADE without checking that its last trade happened today in the continuous session.
- **Stale order inputs.** `fw7b.session.book_at` takes the last valid packet at or before 09:16:00 at any age for the strike's admission and the cap.
- **The offset.** `fw2.Day`'s receipt-minus-exchange offset is the median over the whole day's front-future packets (later packets set an earlier freshness flag).

**Data on this PC, inventoried before this plan:**
- **Breeze:** NIFTY / SENSEX minutes; BANKNIFTY daily bars only.
- **Archive and recorder:** NIFTY / SENSEX.
- **Kite 15-minute bars** for 498 stocks (Jan 1 – Jul 31, 2026), including BANKNIFTY's constituents.
- **Production's export:** `fno_positions` (64 paper entries, Jul 16 – Nov 11) and `fno_signals` (6,336 scans).
- **Absent:** no intraday BANKNIFTY / FINNIFTY index, futures or option data; no USDINR; no company-filing timestamps; no stock-option quotes.
- **NSE's public end-of-day F&O bhavcopies and index closes** download from `nsearchives.nseindia.com` (checked on one file).

**Unchanged rules:** Gold v5 at ₹30,000; one bought index option, walked one-lot cost plus entry charges ≤ ₹15,000; ₹3,000 stop; ₹205 / ₹400 stress plus Zerodha charges; expiry days flat; Production read only; nothing places an order. fw5–fw9, fw7b / fw9a / fw8a and SN300a stay unopened until their verdicts. Every script is committed before it runs; results are written once; crashes are fixed before any number and disclosed; the HONEST clock (`sn396/op.py`) is used for every minute-data entry.

## 1. The auditor's slots

### SN411: what was actually observable at the decision
- **A. `fw7c.py` (companion of fw7b; frozen before any forward P&L):**
  - FIRST_TRADE needs the packet's last-trade time ≥ today's 09:15:00 (else QUOTE_ONLY: skipped, the search continues to 09:16:00);
  - the receipt-minus-exchange offset comes from front-future packets received in [08:58:00, 09:16:00) only, and every freshness flag is recomputed with it;
  - the index packet that sets the strike must be ≤ 2.0 s old at 09:16:00 (else STALE_INDEX, scored 0);
  - the book used for admission and the cap must be received ≤ 2.0 s before 09:16:00 (else STALE_BOOK, scored 0).
  - Everything else is fw7b.
  - `fw9b.py` = fw9a on fw7c, published with fw9 / fw9a.
  - **Tests:** an old trade in a new packet; a 55-second-old book; the pre-decision offset; and all existing fixtures.
  - **Nov 16 plumbing:** decisions whose state changes from fw7b to fw7c.
- **B. The live decision chain (Production export, read only):**
  - for every paper position: signal bar end (bar_ts + the bar length), the scan's `evaluated_at`, and `entry_time`;
  - the latency distribution;
  - the share of entries more than 60 s after the bar end;
  - the cost in Gold terms from SN409's per-minute figure.

### SN412: how much of the wage the day physically offered (hindsight, no portfolio P&L)
- **Data:** the real-quote archive, sealed days (Sep 10 – Nov 13), NIFTY's recorded universe (about 11 strikes × 2 expiries × CE / PE, one snapshot a minute).
- **Trade:** one lot entered at any usable snapshot 09:16–14:59 at the walked ask (cost + charges ≤ ₹15,000); exit at any later usable snapshot to 15:10 at the walked bid (an expiring contract by 13:30). Net after charges and ₹205 / ₹400.
- **Per day:** the ceiling without a stop, and with the ₹3,000 stop (every mark before the exit > −₹3,000); its contract and clock; whether it reaches ₹750.
- **Denominators:** observed days, and Gold-empty days (Gold's replay log, Sep 10 – Oct 28).
- **Fixed clocks (09:30, 10:00, 11:00, 12:00, 13:00, 14:00):** the best contract with exit within 60 minutes. Measured: the share of day × clock cells where ₹750 was reachable before the stop, and the share where every contract loses (abstain best).

### SN413: which other index can take the wallet
- **A. End-of-day screen** (NSE bhavcopies + official index closes, every session Aug 3 – Nov 13, 2026, saved under `_local`):
  - indices BANKNIFTY, FINNIFTY, MIDCPNIFTY, with NIFTY as reference;
  - front expiry (first strictly after the date) and the next;
  - ATM (nearest the official close), 1-ITM and 2-ITM, CE / PE.
  - An observation passes if contracts traded > 0 and close × lot ≤ ₹15,000 (before fees).
  - Reported: by sessions-to-expiry bucket (1–5, 6–10, 11–20, > 20), before / after each monthly roll, and on NIFTY's expiry days.
- **B. Depth:** no intraday quotes exist on this PC. The exact sample needed: ≥ 20 recorder sessions with BANKNIFTY / FINNIFTY front and next month, ±10 strikes, 5-level depth, spanning a monthly roll.
- **C. Dev change** (deploy only on the owner's word): the recorder records BANKNIFTY / FINNIFTY futures and options (front + next month, ±10 strikes), with a FINNIFTY instrument book that never feeds partner messages, tests, and a byte-budget estimate.

### SN414: the sector move NIFTY hides (stage 1, cash-level and NIFTY expression)
- **Data:** Kite 15-minute bars Jan 1 – Jul 31, 2026 (seen for momentum; new question).
- **Basket:** BANKNIFTY's 12 constituents with frozen approximate weights:
  - HDFCBANK 0.28, ICICIBANK 0.25, SBIN 0.09, KOTAKBANK 0.08, AXISBANK 0.08;
  - CANBK 0.04, INDUSINDBK / BANKBARODA / FEDERALBNK / IDFCFIRSTB / AUBANK / PNB 0.03 each.
- **Proxy gate:** the basket's daily close-to-close return against Breeze's BANKNIFTY daily bars, correlation ≥ 0.95, else the slot stops.
- **Decision** at bar boundaries 10:30, 11:00, 11:30, 12:00, 12:30, 13:00, using completed bars only:
  - residual = basket 30-minute return − β × NIFTY's 30-minute return (β from OLS of 15-minute returns over the previous 20 sessions);
  - z = residual / its standard deviation over the previous 20 sessions;
  - trigger if |z| ≥ 2, |NIFTY 30 min| ≤ 0.15%, ≥ 70% of basket weight moving with the residual's sign, and Gold flat (no Gold position open at the clock, per Gold's replay log). First trigger per day.
- **Outcomes:**
  - (a) the basket's next 45 minutes (3 bars) in the residual's direction, in bp;
  - (b) the residual's 45-minute continuation;
  - (c) the same signal on NIFTY: HONEST ITM 2 then 1 in the residual direction, 45 minutes, ₹3k stop, ₹205 / ₹400 (gl);
  - controls: a seeded coin direction at the same clocks, and untriggered sessions at the same clocks.
- **Hurdle:** a BANKNIFTY option's break-even in bp of the index, from the bhavcopies' typical ATM premium (spread allowance, fees, stress, an hour's theta at delta 0.5).
- **Advance to quotes only if:** ≥ 30 triggers, mean (a) > 0 with t > 2, and the mean (a) exceeds the hurdle.

### SN415: company results
- **Feasibility only:** exchange dissemination timestamps for a roster, intraday stock data across those dates, and stock-option quotes are not on this PC; stock options settle physically.
- **Reported:** the exact sample needed. Closed until the owner approves a filings and option-quote source.

### SN416: USDINR as a sensor
- **Feasibility only:** no USDINR data on this PC (Breeze, archive and recorder hold none).
- **Reported:** the sample needed (≥ 40 sessions of front-future ticks with exchange times, and NIFTY on the same clock).

### SN417: the partner's decision in a blind replay
- **Design only:** a frozen protocol (clips ending before the decision, ordinary pass sessions mixed in, outcomes hidden; buy / pass, side, maximum ask, invalidation, reason; scoring against random entries and passes at realistic latency).
- **Not run:** it needs the owner's consent and the partner's time; the clips create no signals and no orders.

### SN418: does Gold's stand-aside help across starting points?
- **A. One lot, no growth** (wallet kind "one"): DEPLOYED against NO_STAND + R0.85, and N11 against NO_STAND; 2022, 2023–26, 2022–26; ₹205 / ₹400.
- **B. Quarterly starts:** Gold's ₹30k growth wallet from each quarter start Jan 2022 – Jul 2026 (from_day). DEPLOYED against NO_STAND + R0.85: the net over the next four quarters (or to the end of data) and to the end.
- **Reported:** starts where DEPLOYED leads, the median difference, and growth-step dates.
- **Closes on a wash;** the current source is retained unless the matched comparison shows value.

### SN419: the cheap opener and Gold in one ledger
- **Ledger:** `ow.run_wallet` with a leg (SN252's contract) on the 2023–26 path.
- **The leg:** fw9's rule on the HONEST clock, only on CHEAP auction sessions (Dec 2025 – Oct 2026), at the session's start:
  - 2-ITM then 1-ITM within the spendable cash (wallet − ₹15,000) and ≤ ₹15,000;
  - stop = min(the shared room, ₹3,000);
  - 60 minutes;
  - sold at Gold's first signal minute if Gold signals first.
- **How the ledger links them:** an opener loss reduces Gold's day room (`loss + realized`).
- **Parity:** a leg that never enters must give ₹8,50,883 at ₹205.
- **Reported:**
  - the incremental net and Gold's own net change;
  - forced exits;
  - the opener's stop overshoot;
  - days with total loss > 20% of the wallet;
  - the no-bid bound (paid premium + fees) per opener trade, at ₹205 / ₹400.

### SN420: pre-register the next paper decision
- **At most two** new candidates (one instrument route, one information route), and only if SN411–SN419 justify them.
- **Otherwise none,** and the existing forward tests continue.

## 2. Own slots (SN421–SN425): how robust is Gold, the one thing that works?

### SN421: Gold's parameter map (one step at a time)
- **Changes:**
  - extension: off, ext_x 0.15 / 0.35, ext_k 2 / 4;
  - scale-in: in_atr off / 0.5 / 1.5, in_full off;
  - ITM: itm_if_fits off, itm_auto (15k, 17.5k) / (20k, 25k);
  - day room: loss_share 0.15 / 0.25;
  - size rule: all / single;
  - growth: g_trig 0.75 / 1.5, growth cap 2 / 4 steps.
- **Runs:** each against Gold v5 as deployed, on 2022 (out of sample) and 2023–26, at ₹205 / ₹400.
- **Labels:**
  - FRAGILE if a one-step change moves the 2023–26 net by > 20%;
  - CONSISTENT if 2022 moves the same way.
- **Learning only.** No Gold change follows from this slot.

### SN422: why Gold's sessions are empty
- **Sessions:** 2022–26, DEPLOYED, ₹205; each market session without a Gold trade.
- **Reasons:**
  - NO_SIGNAL (no N11 / R0.85 signal that day);
  - SIGNAL_NOT_TAKEN (a signal existed; Gold's own rules did not enter: expiry mismatch, after the exit minute, day stop, one position);
  - STAND_ASIDE (NO_STAND or N10 had a signal and N11 did not).
- **Reported:** counts by year, and the Gold net those days would have had in the NO_STAND arm (SN403's log).

### SN423: which of Gold's experts and sides carry it
- **Streams:** DEPLOYED, filtered: without EFF, without OR20, without SHIPPED, TPB only, puts only, calls only.
- **Runs:** 2022 and 2023–26, at ₹205 / ₹400.
- **Teaches:** whether one part is dead weight out of sample.
- **Learning only.**

### SN424: Gold's size ladder
- **Wallets:** 1 lot fixed; 2 lots (sized); the growth wallet with caps 0 / 1 / 2 / 3 (deployed) / 4 / 5 steps; size rule "all" under cap 3.
- **Paths:** 2022, 2023–26 and 2022–26 (₹30k from Jan 2022), at ₹205 / ₹400.
- **Reported:** net, net per session, worst month, months positive, refills.
- **Teaches:** the money question the owner decides.

### SN425: Gold's stop slippage and tail risk
- **Run:** DEPLOYED 2022–26 at ₹205 / ₹400 with Gold's full trade log (gw.LOG).
- **Stops:** each stop exit's realized loss against its intended room, and the overshoot in rupees (share, median, worst).
- **Tail:** days whose loss exceeds 20% of the wallet; the no-bid bound per trade (paid premium + fees) against the worst actual loss.
- **Extension:** the extension's contribution.
- **Teaches:** the honest risk figure before real money (V8).

## 3. Order of work
SN411 → SN413 → SN414 → SN412 → SN418 → SN419 → SN421 → SN422 → SN423 → SN424 → SN425 → SN415 / SN416 / SN417 → SN420.

## 4. Amendments
- **SN413 A (disclosed follow-up after the first scoring).** MIDCPNIFTY had no observations: the official index file names it "Nifty Midcap Select". It was re-scored with the right name, adding NIFTYNXT50, in `results-sn413a-followup.json`. The first results are unchanged.
- **SN414b (disclosed follow-up after SN414's numbers).** The full 27-cell threshold grid × 4 horizons, cash level only, published whole.
- **SN413 C (Dev change `1bfed1d0`).** BANKNIFTY only. FINNIFTY has no instrument book, and adding one would touch the partner-tips analytics path; SN413 A also shows it thin.
