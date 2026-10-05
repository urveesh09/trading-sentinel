# Expiry-day paper book (`expiry-v1`), October 5, 2026

**Status:** Dev, paper only and broker-free. The owner asked for it on October 5 with
a ₹2,500 budget and plays A, B and C on Tuesdays (NIFTY) and Thursdays (SENSEX).
It goes live in Production only after the PR is merged and the images are rebuilt.
The live F&O book is unchanged: `FNO_EXPIRY_DAY_ENTRIES=False` and the 15:10 hard
flat still apply.

**Revised before its first expiry** (an independent review of `f000acb`):

- **The loss ceiling is now hard.** The earlier version sized A from its −30% stop,
  so a gap could lose about 3× the budget. It also left charges out of the B and
  C budgets.
- **Fills are executable or nothing.** Quotes must be fresh, buys and sells walk
  the visible depth, and the "98% of last price" fallback is gone. Exits that
  cannot fill stay latched and are retried every tick.
- **Futures confirmation can no longer be skipped.** Breakout confirmation also
  restarts after a missing observation or a gap.
- **Legs left open are settled.** After an outage, anything still open is settled
  as a labelled assumed valuation.
- **Telegram uses a durable outbox.** A notice is marked sent only after a 2xx
  response.

No expiry had been traded, so the rules are still `expiry-v1`.

## Why

The owner's goal is to profit on the expiry afternoon without big losses and
without wasting the opportunity. Small, steady wins are preferred to jackpots.

Research facts this design rests on (sources at the end):

- **Schedule:** NIFTY weeklies expire on Tuesday (NFO) and SENSEX on Thursday
  (BFO). Since September 2025 these are the only weekly index expiries.
- **Closing auction:** since August 3, 2026, F&O-eligible stocks stop continuous
  trading at 15:15. A closing auction runs 15:15–15:35 and F&O trades until
  15:40. The expiry settlement price is the auction close, not the old 30-minute
  average.
- **The index freezes from 15:15 to about 15:29.** Options keep trading against
  an indicative price. Observed effects:
  - ATM legs repriced 5× in one minute (8 Sep).
  - Puts rose 400–500% on a day the index fell only 0.55% (3 Sep, SENSEX).
  - The median closing move rose from 14.6 to 33.9 points.
  - The share of 50-point-plus closing moves rose from 6% to 32%.
- **The rule may change.** SEBI's consultation paper (Sep 12, comments closed
  Oct 3) proposes a blended-average settlement and new session times, so the
  auction window may change. SEBI's chair has said ending weekly expiries is not
  under consideration.
- **Most traders lose here.** 59% of index-option turnover happens on expiry
  day; about 88% of individual F&O traders lost money in FY26, 92% of it on
  options; cheap far out-of-the-money (OTM) options lose on average. Each play's
  results are kept separate so the evidence decides. A is the main candidate
  for repeatable trade management; B and C are speculative experiments.

## Rules (frozen as `expiry-v1`)

Module `python-engine/expiry_paper.py`; job `expiry_paper_tick` runs every 10 s,
12:59–15:40 IST, on trading days.

- **When it trades:** an underlying is traded only when today is its nearest
  option expiry in the instrument dump, so holiday shifts follow the exchange.
- **What each tick records:** one quote batch per underlying (index, front
  future, ATM ±8 strikes for today, open legs), logged to `expiry_paper_ticks`
  with bid and ask, their top-level quantities, the last price and the provider
  timestamp. The auction window is included.
- **Load on the shared Kite quote limiter:** about one request every 10 s.

**Loss ceiling (hard).** Every entry is sized so that the whole premium plus the
charges of a worthless expiry fits the play's remaining ₹2,500 for the day.
- The stops below are planned exits, not guarantees: a gap between ticks can
  fill below them.
- Raising a stop protects profit only as far as the next observed price allows.
  A gap after banking can still finish a trade below breakeven, but never below
  `max_loss`.

**Executable fills.**
- **Fresh quotes only:** a quote counts only if its provider timestamp is at
  most 20 s old (5 s of clock skew allowed).
- **Buys** walk the five-level ask depth and **sells** walk the bid depth, in
  whole lots, at the depth-weighted price. One-unit depth cannot fill a lot.
- **An exit that cannot fill** (no fresh quote, no bid, thin depth) stays latched
  in `exit_pending` and is retried every tick until 15:40.
- **Labels:** fills from 15:15 are marked `AUCTION_WINDOW`. Continuous-market
  fills during the closing auction are unverified (the CAS reachability gate is
  still UNREACHABLE), so they are reported separately.

**Settlement after the session** (`reconcile`):
- **When it runs:** on every tick for earlier days, and hourly at :45 from 09:45
  to 17:45 on trading days.
- **Legs still open after 15:40** are valued at intrinsic using the last index
  print logged after 15:36 (the post-auction close), less buy charges and 0.15%
  exercise STT. They are marked `SETTLED_ASSUMED`.
- **Without such a print**, a leg is marked `UNRESOLVED` at its full worst-case
  loss.
- **Separation:** both are stored in `assumed_pnl`, never mixed with filled P&L.

**Box.** The range of fresh index and futures samples between 13:00 and 13:30.
At least 30 samples are required; otherwise A and C stand down for the day.

**Breakout signal.**
- The index must be beyond the box by `max(15% of box width, 0.02% of spot)`,
  with the fresh future also beyond its own box.
- This must hold on 2 observations no more than 25 s apart. A missing or stale
  index or future restarts the count.
- The signal is valid 13:30–15:05.
- A direction re-arms only after the index returns inside the box.

**A — Gamma breakout.**
- **Entry:** the ATM option in the signal direction. If one ATM lot does not
  fit the ceiling, the next OTM strike is tried. The spread must be ≤6%.
- **Sizing:**
  - Up to 4 lots within the ceiling.
  - The ceiling is ₹2,500 less any A loss today; a profit does not raise it.
  - At most 2 trades a day, one open at a time.
- **Exits, in order of checking:**
  1. **Flat:** close everything from 15:13, before the index freezes.
  2. **Stop:** sell if the bid is at or below the stop. The stop starts at
     entry −30%. It moves up only:
     - after banking, to entry ×1.05;
     - at a peak of +100%, to 70% of peak;
     - at +200%, to 80% of peak;
     - from 15:00, once the peak reaches +40%, to 85% of peak.
  3. **Failed break:** sell if the index is back inside the box by a quarter of
     its width.
  4. **Time stop:** sell if 8 minutes have passed, nothing has been banked, and
     the peak never reached +15%.
  5. **Bank:** at a bid of +40%, sell half if there are 2 or more lots. A
     one-lot position only raises its stop.

**B — Auction strangle.**
- **Entry:** once, 15:13:30–15:15. Buy the CE at the strike at or above spot and
  the PE at the strike at or below spot. Spreads must be ≤10%.
- **Sizing:** both legs together within the ceiling, at most 4 lots. For NIFTY
  that means combined premiums of roughly ₹37 per unit or less for one lot.
- **Exits:**
  - There is no planned stop.
  - A leg at 2× its entry banks half and trails at 65% of peak.
  - From 15:30, a profitable peak keeps 80%.
  - Sold from 15:38.

**C — Lottery ticket.**
- **Entry:** on A's signal, once a day. Buy the strike nearest the money, in the
  signal direction, whose fresh ask is between 0.004% and 0.03% of spot (NIFTY
  about ₹1–7.5). The spread must be ≤10%.
- **Sizing:** within the ceiling, at most 10 lots.
- **Exits:**
  - There is no planned stop.
  - At 3× entry, sell half; from a 5× peak, the stop is 60% of peak.
  - It is held into the auction and sold from 15:38.

**Worst case per expiry day:** ₹2,500 per play, ₹7,500 for all three, on paper.

## Reading the results

- **Telegram:** each buy and sell, showing its max loss and any auction-window
  label, and one summary per expiry day. The summary shows:
  - box status, signals, and ticks with stale-quote counts;
  - filled and assumed P&L per play;
  - per-underlying totals to date.
- **Outbox:** `expiry_paper_notices`, flushed after each tick and each
  reconcile.
- **Store:** `<DB_PATH>.expiry-paper.db`, with tables
  - `expiry_paper_positions` (`max_loss`, `exit_pending`, `assumed_pnl`, events
    carrying `fill_model`);
  - `expiry_paper_days`;
  - `expiry_paper_ticks`.
- **Quote archive:** the research quote archive now records until 15:40.

## Evaluation (pre-registered)

- **When:** an initial review after 20 expiries, about 10 weeks with both
  indices. It is a review, not a verdict.
- **How:**
  - each play is judged on its own;
  - NIFTY and SENSEX are judged separately;
  - no-trade days count as zero days;
  - assumed settlements and `AUCTION_WINDOW` fills are reported separately from
    continuous fills.
- **Measures:**
  - net P&L > 0;
  - profit factor ≥ 1.2;
  - the share of winning days;
  - the worst day (no worse than −₹2,500 by construction);
  - net P&L without the single best day, which shows dependence on exceptional
    winners.
- **What it is not:** a pass is evidence for a paper-to-live discussion, not a
  live permission. B and C remain speculative until auction execution semantics
  are evidenced.
- **Rule changes:** any change becomes `expiry-v2` and is scored only on later
  expiries.
- **If SEBI changes the settlement or session times,** record the date and
  re-judge B and C from that point.

## Not done

- BFO live exits remain unsupported (SENSEX is paper anyway). BSE charges use
  the NSE schedule as an approximation.
- No replay of past expiries yet. The tick log builds that history from now on.
- No live switch exists for this book.

## Sources

- [Expiry schedule (Strota)](https://strota.in/india-expiry-schedule)
- [F&O hours to 15:40 (Multibagg)](https://www.multibagg.ai/market-pulse/articles/nse-fo-closing-auction-hours-cmscwd1a610h00zqox7g9fa3o)
- [What the auction did to expiry pricing (Tradetron)](https://tradetron.tech/closing-auction/)
- [SEBI review of auction settlement (MarketsEasy)](https://marketseasy.in/blog/sebi-expiry-settlement-price-cas-review-2026)
- [SEBI consultation paper (Business Standard)](https://www.business-standard.com/markets/news/sebi-derivatives-settlement-closing-auction-cas-market-timings-126091200337_1.html)
- [FY26 loss study (Open)](https://openthemagazine.com/business/sebi-fo-loss-study-explained-why-9-in-10-retail-traders-lost-91685-crore-in-fy26)
- [Lottery preference in options (CFR)](https://www.cfr-cologne.de/download/workingpaper/cfr-25-09.pdf)
- [SEBI chair on weekly expiries (IANS)](https://ianslive.in/cannot-just-shut-down-weekly-fo-expiries-tuhin-kanta-pandey--20251031130253)
