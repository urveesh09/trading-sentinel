# Expiry-day paper book (`expiry-v1`), October 5, 2026

**Status:** Dev, paper only and broker-free. The owner asked for it on October 5 with
a ₹2,500 budget and plays A, B and C on Tuesdays (NIFTY) and Thursdays (SENSEX).
It goes live in Production only after the PR is merged and the images are rebuilt.
The live F&O book is unchanged: `FNO_EXPIRY_DAY_ENTRIES=False` and the 15:10 hard
flat still apply.

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
  options; cheap far out-of-the-money (OTM) options lose on average. A steady
  profit therefore cannot come from lottery buying alone. It has to come from
  tight risk control and banking gains early. Each play's results are kept
  separate so the evidence decides.

## Rules (frozen as `expiry-v1`)

Module `python-engine/expiry_paper.py`; job `expiry_paper_tick` runs every 10 s,
12:59–15:40 IST, on trading days.

- **When it trades:** an underlying is traded only when today is its nearest
  option expiry in the instrument dump, so holiday shifts follow the exchange.
- **What each tick records:** one quote batch per underlying (index, front
  future, ATM ±8 strikes for today, open legs), logged in full to
  `expiry_paper_ticks`, including the auction window.
- **Fills:** buys fill at the best ask and sells at the best bid. If there is no
  bid, the sell price is 98% of the last traded price.
- **Costs:** each exit slice pays a full round trip through `calc_fno_costs`, a
  slight overstatement. BSE (SENSEX) uses the NSE rate schedule as an
  approximation.

**Box.** The range of index samples between 13:00 and 13:30 (and of the front
future). At least 30 samples are required; otherwise A and C stand down for
the day.

**Breakout signal.**
- The index must close beyond the box by `max(15% of box width, 0.02% of spot)`
  on 2 consecutive ticks, and the future must also be beyond its own box.
- The signal is valid 13:30–15:05.
- A direction re-arms only after the index returns inside the box.

**A — Gamma breakout.**
- **Entry:** buy the ATM option in the signal direction (CE up, PE down). The
  spread must be ≤6% of the ask.
- **Sizing:**
  - Lots = the remaining budget ÷ (ask × 30% × lot size).
  - The remaining budget is ₹2,500 less any A loss today; a profit does not
    raise it.
  - Caps: at most 4 lots and at most ₹20,000 premium.
  - At most 2 trades a day, one open at a time.
- **Exits, in order of checking:**
  1. **Flat:** close everything at 15:13, before the index freezes.
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
  5. **Bank:** at a bid of +40%, sell half (if there are 2 or more lots) and
     move the stop to entry ×1.05.

**B — Auction strangle.**
- **Entry:** once, 15:13:30–15:15. Buy the CE at the strike at or above spot and
  the PE at the strike at or below spot. Spreads must be ≤10%.
- **Sizing:** whole premium ≤ ₹2,500, at most 4 lots.
- **Exits:**
  - There is no stop: the premium is the risk.
  - A leg at 2× its entry sells half; at a 2× peak the stop is 65% of peak.
  - From 15:30, a profitable peak keeps 80%.
  - Everything is sold at 15:38, so nothing is left to exercise.

**C — Lottery ticket.**
- **Entry:** on A's signal, once a day. Buy the strike nearest the money, in the
  signal direction, whose ask is between 0.004% and 0.03% of spot (NIFTY about
  ₹1–7.5). The spread must be ≤10%.
- **Sizing:** whole premium ≤ ₹2,500, at most 10 lots.
- **Exits:**
  - There is no stop.
  - At 3× entry, sell half; from a 5× peak, the stop is 60% of peak.
  - It is held into the auction and sold at 15:38.

**Worst case per expiry day:** ₹2,500 per play, ₹7,500 for all three, on paper.

## Reading the results

- **Telegram:** a message for each buy and sell, and a summary per expiry day
  with running totals per play. This needs the gateway (fixed in `79b1333`).
- **Store:** `<DB_PATH>.expiry-paper.db`, with tables
  - `expiry_paper_positions` (each event in `events`);
  - `expiry_paper_days` (box, signals, trade counts);
  - `expiry_paper_ticks`.
- **Quote archive:** the research quote archive now records until 15:40 (was
  15:30).

## Evaluation (pre-registered)

- **When:** after 20 expiries, about 10 weeks with both indices. Each play is
  judged on its own.
- **Measures:** net P&L > 0; profit factor ≥ 1.2; the share of winning days; and
  the worst day, which is no worse than −₹2,500 by construction.
- **What it is not:** a pass is evidence for a paper-to-live discussion, not a
  live permission.
- **Rule changes:** any change becomes `expiry-v2` and is scored only on later
  expiries.
- **If SEBI changes the settlement or session times,** B and C rest on the
  current auction. Record the date and re-judge them from that point.

## Not done

- BFO live exits remain unsupported (SENSEX is paper anyway).
- No replay of past expiries yet. The archive has ±5 strikes until 15:30 and
  misses the auction tail. The tick log fills that gap from now on.
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
