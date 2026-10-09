# Expiry-day paper book (`expiry-v1`), October 5, 2026

**Status:** Dev, paper only and broker-free. The owner asked for it on October 5 with
a ₹2,500 budget and plays A, B and C on Tuesdays (NIFTY) and Thursdays (SENSEX).
It goes live in Production only after the PR is merged and the images are rebuilt.
The live F&O book is unchanged: `FNO_EXPIRY_DAY_ENTRIES=False` and the 15:10 hard
flat still apply.

> **Owner's stop rule (set October 8, 2026, after two losing expiries).**
> October 6 (NIFTY, −₹3,224.47) and October 8 (SENSEX, −₹2,934.51) both lost.
> The owner will observe **8 more expiries, 10 in all**. If the main book (A, B
> and C, filled plus assumed) loses on **every one of the 10**, expiry-day F&O
> trading stops. Separately, **a play or section that keeps losing is dropped
> on its own**, even if the book as a whole does not meet the rule. This
> decision point comes before the 20-expiry scoring horizon: that horizon is
> only for choosing between plays if the book continues. Every day summary
> prints the tally ("owner rule … expiry N of 10, main book lost X of N,
> losing streak S" plus each play's losing/traded count;
> `expiry_paper.owner_rule_lines`). Each main play has its own ₹2,500 daily
> ceiling, so A, B and C together can lose up to ₹7,500 on one expiry.

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
  response, and the gateway answers 502 when Telegram refused it
  (`require_delivery`).

A second review of `4673105` found that sliced exits could exceed the reserve
(each slice was charged a full round trip). The buy is now charged once and one
sell-order fee per lot is reserved. No expiry had been traded, so the rules are
still `expiry-v1`.

**After the first expiry (October 6, NIFTY):** modeled loss ₹3,224.47 = filled
+₹25.53 and assumed −₹3,250.00 (B's put and C expired worthless by our sample).
The [first-day audit](../../Production_Trading-sentinel/docs/2026-10-06-expiry-system-deep-audit.md)
found execution and data defects, not rule defects. The strategy thresholds stay
frozen as `expiry-v1`; the corrected data/clock/fill contract is
`expiry-exec-v2`, recorded on every tick, day and position so later days are not
mixed with October 6:

- **Decision clock.** v1 judged freshness, windows and fill times at the
  request start, so a slow quote call refused new packets and accepted old
  ones. v2 reads the decision time after the quotes arrive. The tick row keeps
  the start and decision times and the client's limiter/transport timing.
- **Replayable evidence.** Each tick stores every leg's full five-level depth
  with its provider time, and the index/future packets with a status (`FRESH`,
  `STALE`, `AHEAD`, `NO_TIMESTAMP`, `NO_PRICE`, `MISSING`). The day state counts
  refusals by reason, entry refusals by play (spread, depth or budget, stale
  quote, max trades, and so on), the largest gap between ticks, gaps longer
  than 25 s, and the slowest decision.
- **Partial banks.** Reaching the bank level sets `bank_pending` to half the
  lots. Lots the bid depth could not take stay pending, survive a restart, and
  are sold while the bid holds the bank level. v1 forgot them.
- **No lost expiries.** An expiry whose index never answers still writes its
  day and ticks, so it stays in the 20-expiry denominator.
- **Exchange-bound charges.** SENSEX (BFO) uses BSE's 0.0325% transaction
  charge, against NSE's 0.03553%, from Zerodha's published list read on
  October 6. The schedule is frozen on the position at entry, and exits and
  settlement use it.
- **Outbox.** Flushes of one store are serialised. `sent_at` is the time of
  the acknowledgement. Delivery is at-least-once: a crash between Telegram
  accepting a notice and the mark sends it again. The flush runs in its own job,
  5 s after each tick, so a slow gateway no longer holds the tick. On October 6,
  90 of 966 slots were skipped while a tick was still running.
- **Messages.** A sell shows its gross, its sell fees, and the trade's net after
  all fees, including the buy. The summary shows fees, filled net, assumed and
  whole modeled per play and for the day, plus a data line.

## Shadow plays `expiry-shadow-v1` (frozen October 6, before October 8)

The owner approved these on October 6, after the first expiry. They test
lessons that come from market structure, not from fitting October 6. A, B and C
stay unchanged as `expiry-v1`. Each shadow play runs on the same quotes in the
same tick, keeps its own ₹2,500 ceiling (C500: ₹500), sends no per-trade
Telegram lines, and appears in a separate summary section. They are scored
beside `expiry-v1` after the same 20 expiries, by the same measures. October 6
is not part of their record.

| Play | Lesson tested | Rule |
|---|---|---|
| **BH** | After 15:15 the auction sets the price and option quotes are thin; a trailing stop may sell on noise. | B's strangle (same strikes, same entry), with no bank and no trail. Sold at 15:38, or settled if no bid. |
| **C500** | Lottery options are overpriced (lottery-preference research), so C deserves a small stake. | C's strike and timing, inside ₹500. |
| **D** | Expiry decay pays sellers. The owner asked for small but consistent profit. | Short iron condor, entered 14:30–14:45. Sell the strikes 2 steps either side of the money, and buy one step further out as protection. If that doesn't fit ₹2,500, try 1 step, then at the money (an iron butterfly). Held to cash settlement. |

D details:
- **Ceiling.** Held to cash settlement, only one side can finish in the money,
  and that side loses at most its strike gap. So the maximum loss is (gap −
  credit) × quantity, plus entry charges, plus exercise STT on a protective leg
  up to 5% of spot in the money. That sum must fit ₹2,500.
- **Credit rule.** The credit must cover at least twice the entry charges.
- **Settlement.** The result is our sampled settlement, labelled assumed like
  B's and C's leftovers. No closing orders or closing fees are modelled at
  settlement.
- **If quotes are lost** (an outage), each sold leg is valued at half the gap,
  so the whole condor books its maximum settlement loss.
- **Fit by index.** A condor 50 points wide on NIFTY risks ₹3,250 a lot before
  the credit, so on NIFTY D usually needs the nearer strikes or the butterfly.
  On SENSEX (20 units, 100-point steps) the 2-step condor fits.
- **Margin.** Selling an option blocks margin from the owner's own cash. There
  is no borrowing, but it is margin. That is why D stays paper only, with no
  live switch, until the owner decides on margin separately.

## Shadow plays `expiry-shadow-v2` (frozen October 8, scored from October 13)

Built after the first SENSEX expiry audit (Production
`docs/2026-10-08-expiry-system-deep-audit.md`). Both plays fix a structural
weakness the audit found, not a number fitted to the day. October 6 and
October 8 were both seen, so neither day counts for these plays. Their record
starts with the next expiry after the rebuild. BH, C500 and D carry on
unchanged. A, B and C stay `expiry-v1`.

| Play | Weakness found | Rule |
|---|---|---|
| **AL** | A buys one lot when the ceiling allows only one. One lot cannot bank half, so after a +40% bank the stop only rises to entry × 1.05. On October 8 the first A was +₹974 sellable at 14:22 and finished −₹115.69. | A's entry rules, sizing, stops and ceiling, applied to AL's own open position and budget. After a different exit, AL's later entries can differ from A's; compare matched entry paths for an exit-only view. Once banked, a one-lot AL keeps half of its peak gain as the stop (entry + 0.5 × (peak − entry)). It is a stop, not a sale, so a gap can fill below it. With two or more lots, AL is A. |
| **BP** | B manages its legs separately. The winning leg trails while the losing leg decays to no bid and settles at zero. On both expiries B's put was lost in full. October 8: the pair was +₹786.76 sellable at 15:26:10 and finished −₹720.75. | B's strangle (same strikes and entry), managed as one trade. On each tick before 15:38, if both legs sold now on the visible bids would net at least 20% of the premium paid, after every charge, both legs are sold (`PAIR_TARGET`). A leg the bids cannot fill stays latched and is retried. Otherwise both are sold at 15:38, like BH. |

Honesty notes:
- **The 20% target was chosen after seeing October 8**, where the pair peaked at
  35%. It answers the owner's goal of small, consistent profit. Any value below
  35% would have "worked" that day, so the day proves nothing about the number.
- **A Dev replay of the October 8 packets** (mechanics check only) gave AL
  +₹501.63 (the first A sold at 125.90 at 14:22:40) and BP +₹786.76. The same
  replay reproduced every Production result and path mark to the paise. These
  are in-sample figures, not evidence.
- **A context gate on D** (sell only when IV/RV is rich) needs no new play.
  Every D entry records its context, so after enough expiries the gate can be
  tested on D's own record and frozen as `expiry-context-v2` if it holds.

## October 8 audit corrections (Dev, no strategy change)

- **Slot count (audit T5).** `EXPECTED_SLOTS` is 966 (12:59:00–15:39:50). The
  tick guards use `< 15:40`.
- **Stale OI (T4), `expiry-context-v1.1`.** Walls, max pain, PCR and OI change
  read only fresh quotes. The context records `oi_fresh`/`oi_window`, and the
  summary prints "from N/M fresh quotes". The future's tick record keeps its OI.
- **Snapshot clocks.** The summary shows each snapshot's nominal time and the
  time it was actually read (for example "D entry 14:30:00, read 14:30:10").
  `SETTLE_AT` 15:35 is documented as our approximation, not a verified BFO
  settlement rule.
- **Quote cadence.** On October 8 the tick waited up to 28.9 s for the shared
  limiter (p99 18.3 s), while transport never exceeded 0.4 s. The tick's batch
  now waits in the limiter's management lane. That changes only the order of
  admission: the rate and burst are unchanged, and the lane's burst bound stops
  other modules from starving.
- **Whole-trade path.** Each open entry is marked every tick at its
  liquidation net on the visible depth, after fees (`liquidation_net`). The
  summary prints each entry's best and worst mark, the mark count, and its
  finish. Pairs and condors are marked as one trade at one moment. Marks are
  never fills.

## Notice delivery after the October 8 review (R1)

The expanded day summary reached 4,277 characters on the replayed October 8.
Telegram refuses anything over 4,096 (the gateway adds a prefix and does not
split), and the outbox then retried that one row forever, ahead of every later
trade notice. Two fixes:

- **Split into parts.** `notice_parts` splits any notice over 3,500
  characters at line ends into "[part i/n]" parts. Each part is its own outbox
  row with its own acknowledgement, so an accepted part is never resent. The
  replayed October 8 summary is two parts, 3,472 and 826 characters. A single
  over-long line is cut, never dropped.
- **No permanent block.** A row that has failed 3 times is stepped over. It
  stays stored and pending and is retried every flush, so later notices still
  go out. A second failure straight after a step-over means the transport is
  down, and the flush stops, keeping order. Delivery stays at-least-once.

**Superseded on October 9 (audit O9-E1).** The audit showed that two bad rows
in a row still looked like "gateway down" forever. `flush_notices` now uses
`notice_outbox`, like the overnight book. A 422 (Telegram refused this
message) is stepped over at once and retried on a backoff from 1 minute up to
30 minutes. A network failure or any other HTTP status stops the round in
order. An unknown failure keeps order for 3 tries, then backs off. Any number
of bad rows can no longer block a healthy one. Part lengths are measured in
UTF-16 units, Telegram's own measure, so emoji count double.

## Chain context `expiry-context-v1` (record-only, from October 7)

The owner asked whether the option chain, OI, change in OI and current IV can
improve the odds. The research ranking (October 7):

1. **Implied against realized volatility.** This is the strongest case.
   Options usually price in more movement than happens (the variance risk
   premium), even on the same day, but at that horizon the premium is small
   and fees can swallow it. It may serve as a regime filter for D (sell when
   rich) and B/C (buy when cheap).
2. **OI walls.** Gamma-hedging flows amplify moves when option sellers are
   short gamma (Baltussen et al., JFE 2021). Closes cluster at strikes for
   stocks (Ni, Pearson and Poteshman, JFE 2005); the evidence for indices is
   weaker. Public OI does not show who is short. This may serve as a label
   for A (breaking through or away from a wall) and as a placement guide
   for D.
3. **Change in OI and the future's build-up.** On the expiry afternoon this
   is mostly positions being closed, and index options show no sign of
   informed trading (Pan and Poteshman, 2006).
4. **Max pain.** The evidence is anecdotal. It is recorded only so the
   folklore can be checked.
5. **PCR.** It has no index-level predictive power. It is recorded only for
   the same check.

Nothing reads this context yet. Every tick records it under `context`, and
every leg records its `oi`. It costs no extra request, because Kite's full
quote already carries OI.

| Field | Meaning |
|---|---|
| `straddle`, `atm` | Mid of the fresh, two-sided ATM call and put: the expected absolute move to settlement |
| `iv` | Volatility the straddle implies, solved from straddle = √(2/π) × spot × iv × √T. T runs to the 15:35 auction close on a 252 × 375-minute session year |
| `rv`, `iv_rv` | Today's index volatility from returns at least 60 s apart, on the same clock (shown after 10 minutes of samples), and the ratio of implied to realized |
| `put_wall`, `call_wall` | Strike with the most put OI at or below spot, and with the most call OI at or above it |
| `max_pain`, `pcr` | Over the fetched ATM ± 8 strikes |
| `ce_oi_chg`, `pe_oi_chg`, `top_ce_add`, `top_pe_add` | OI change since each strike was first seen today. A strike entering the window is not counted as a change |
| `fut_oi_chg`, `fut_buildup` | The front future since the day's first fresh tick (long or short build-up, short covering, long unwinding) |

Snapshots are taken:
- in each A/C signal;
- at D's entry time, 14:30, under `state["context_at"]["d_entry"]`;
- at B's entry time, 15:13:30, under `state["context_at"]["b_entry"]`.

The summary prints both snapshots and how our sampled close met the 14:30 read:
- whether it closed inside the walls;
- its distance from max pain;
- how far it moved against the straddle.

**Next step:** after the first expiry, check that the fields fill and look
sensible on real data. After more expiries, propose the thresholds for a gate
on D and B and a label on A (`expiry-context-v2` or a shadow variant).
Freeze them before scoring, and score them only on later expiries. A filter
that halves the trades needs more than 20 expiries to prove itself.

**Dropped before freezing:** "A only when fees are under 2% of premium". A round
trip costs about ₹47 flat plus 0.24% of premium, so getting under 2% needs
about ₹2,700 of premium, more than A's ₹2,500 ceiling allows. The variant could
never trade. A's fee drag is a fixed property of its size.

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

**Loss ceiling (hard).** Every entry is sized so that its `max_loss` fits the
play's remaining ₹2,500 for the day. `max_loss` is the whole premium, the buy's
charges, and one sell-order fee per lot, because an exit can be split into at
most one order per lot. The buy is charged once at entry; each exit slice pays
only its own sell order.
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
  quote we sampled after 15:36, less 0.15% exercise STT (the buy was charged at
  entry). They are marked `SETTLED_ASSUMED`. This is our own sample, not the
  exchange's published settlement price.
- **Without such a quote**, a leg is marked `UNRESOLVED` at its remaining worst
  case (premium plus one order fee per open lot).
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

- **Telegram:** each buy (with buy fees and max loss) and each sell (with slice
  gross, sell fees and the trade's net after all fees), and one summary per
  expiry day. The summary shows:
  - the rules and execution versions, box status and signals;
  - a data line: ticks out of 967 slots, the largest gap, gaps over 25 s, the
    slowest decision, and index/future refusals by reason;
  - the record-only chain context at 14:30 and 15:13:30, and how the close
    met it;
  - per play: fees, filled net, assumed and whole modeled, or the entry
    refusals when there was no trade;
  - the day's filled + assumed = whole modeled;
  - per-underlying filled totals to date, assumed settlements on a separate
    line, and the whole modeled total.
- **Outbox:** `expiry_paper_notices`, flushed by the `expiry_paper_flush` job
  (5 s after each tick) and after each reconcile.
- **Store:** `<DB_PATH>.expiry-paper.db`, with tables
  - `expiry_paper_positions` (`max_loss`, `exit_pending`, `bank_pending`,
    `assumed_pnl`, `fee_snapshot`, `execution`, events carrying `fill_model`,
    and, on sells, `gross` and `charges`);
  - `expiry_paper_days` (state with counters and refusals);
  - `expiry_paper_ticks` (start and decision times, timing, full depth and OI
    per leg, index/future status, and the chain `context`).
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

- BFO live exits remain unsupported (SENSEX is paper anyway). BSE's
  transaction charge is bound. Its effective date is not published, and IPFT
  (₹0.01 per crore) is applied on both exchanges.
- **Settlement:** the official exchange settlement price is not fetched. The
  value is still our post-auction sample.
- **Queue position:** no queue position or order-book depletion is modelled.
- **Exactly-once delivery:** not guaranteed.
- **Shared limiter:** the expiry tick shares the Kite quote limiter with
  research collection. v2 measures the limiter wait per tick, but does not
  reserve capacity.
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
