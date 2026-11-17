# EN11–EN25 plan (frozen before any score)

Nov 17, 2026, owner's instruction: run the auditor's ten slots (`docs/EXPIRY_RESEARCH_EN11_EN20.md`) plus five slots of my own (EN21–EN25). Every slot must either improve E03.2 or teach something specific. The benchmark is **E03.2 unchanged**.

## Ground rules

- **One primary arm per slot.** The numbers below are fixed now. Diagnostic arms are named as such; they are never candidates.
- **Development data only.** NIFTY 2023, 2024 and 2025 expiry chains are all seen, so nothing here is an exam.
  - A slot that passes becomes a candidate for a **disabled paper shadow** and for fresh data.
  - No slot changes Production in this round.
- **Same lab and coverage rule as EN07–EN10:**
  - minute bars, a decision on the completed bar, a fill on the next bar's open ± half the spread;
  - fill scenarios: ordinary, adverse and severe;
  - 20% of the minute's volume per fill;
  - every new signal must pass `exam2023b.available_at` (the strike coverage rule).
- **`check()` must prove:**
  - `en_lab3` with every hook off reproduces E03.2 day by day in all three years at all three fill levels;
  - each recorded-data loader runs.
  - `check()` prints counts only, never rupees.
- **Funding:**
  - every ticket is fully cash-funded: premium plus fees reserved before entry;
  - long options only, no margin;
  - the book's drawdown brakes stay as they are;
  - new setups use symmetric sizing: Rs 1,250 per ticket for calls and puts alike, up to 3 lots, 2 tickets a day, a Rs 2,500 day reserve. That is inside E03.2's own Rs 5,000 day ceiling.
- **Ledgers:** each new setup runs in its own Rs 25,000 ledger, so nothing crowds out E03.2. Standalone totals are never added together.
- **Anatomy (owner's rule):** every arm reports, per year:
  - its results by side, by exit path and by entry window;
  - the tickets it added, removed or changed against E03.2, with their rupee effect;
  - its best and worst tickets.
  - Slot-specific diagnostics are listed under each slot.
- **Indices:** only NIFTY has expiry-afternoon history.
  - SENSEX appears only in the 2026 recorded-quote studies (EN16, EN18); SENSEX history is a standing data request.
  - Dec 7 (NSE CAS 2.0) does not apply to 2023–25 history. The deployability notes say which arms depend on it.

## Pass rules (applied mechanically by `en_score3.py`)

**R-EXIT** applies to changes to E03.2's own tickets: EN11, EN12, EN20, EN21, EN22, EN24 and EN25. All of these must hold:
1. In each year (2023, 2024 and 2025), the arm is at or above E03.2 on ordinary net, adverse net, and net without the best day.
2. Severe-fill net summed over the three years ≥ E03.2's − Rs 1,000.
3. Worst day ≥ −Rs 2,500.
4. Adverse net summed over the three years > 0.
5. **Informative:** at least 6 tickets added, removed or changed over the three years; otherwise the slot is INCONCLUSIVE.

**R-NEW** applies to new entry setups in their own ledger: EN13, EN14, EN17, EN19 and EN23. All of these must hold:
1. Ordinary net > 0 in each year, so E03.2 plus the setup in its own budget beats E03.2 every year.
2. Adverse net summed over the three years > 0.
3. Net without the best day ≥ 0 in each year.
4. Ordinary net above the median of its **matched null** in each year. There are 40 seeded runs:
   - EN13, EN14, EN19, EN23: the same decision minutes with a random side, and the same exits mirrored about the decision close.
   - EN17: the same number of pairs bought at random eligible minutes.
5. Worst day ≥ −Rs 2,500.
6. **Informative:** at least 10 tickets over the three years; otherwise INCONCLUSIVE.

EN14 must also beat its matched **immediate-impulse** arm on summed ordinary net.

The recorded-data and signal slots (EN15, EN16, EN18) have the rules stated under each slot. The EN11 1-second measurement is descriptive only, with no pass or fail.

## The fifteen slots

### Auditor's ten

**EN11 · Fast exit when the trade breaks** (matched entries; R-EXIT)
- **Fast stop:** E03.2's entries and every exit stay as they are, plus two intrabar triggers on non-runner tickets. The first is the current premium stop, hard or trailing:
  - **Trigger:** when the bar's lowest bid, `down(low − half(low))`, reaches the stop and the bar has at least one whole lot of capacity, the ticket sells in that same bar.
  - **Ordinary fill:** the open bid if the bar opened through the stop, else the stop rounded down to a tick.
  - **Adverse fill:** the ordinary price less half the spread and less max(0.05, 1%), never below the bar's lowest bid.
  - **Severe fill:** the bar's lowest bid.
- **Fast structure:**
  - **Trigger:** the index bar's low (calls) or high (puts) crosses E03.2's 2-ATR structure level, and the future's bar extreme crosses the same distance from the future's decision price.
  - **Fills:** the bar's closing bid (ordinary), that bid less max(0.05, 1%) (adverse), the lowest bid (severe).
- Anything not filled carries on through E03.2's normal exit path.
- **Diagnostics:**
  - **Stops that would have recovered:** among tickets whose exit changed, the control ticket's later exit was profitable while EN11 sold at a loss. Their count and rupees are reported against the losses saved.
- **Separate 1-second measurement** (`en11_seconds.py`). Data: NIFTY 1-second trades, Jan 16 – Apr 2 2026, 11 expiries, the open's ATM call and put.
  - Every 5 minutes from 13:00 to 14:55, when a contract trades within Rs 5–20, a synthetic entry is made at that second with a stop at 0.65 × entry.
  - At the first trade at or below the stop, the measurement reports the price 1, 3, 10 and 60 seconds later. It also reports the minute-cadence price: the next minute's first trade after the minute that crossed.
  - The share stopped out that trades back above the stop within 60 seconds is reported too.
  - Descriptive only.

**EN12 · Pay for the runner before letting it run** (matched entries; R-EXIT)
- **At E03.2's 2x trigger, for tickets of 2 or more lots:**
  - sell the smallest number of whole lots whose fee-net proceeds, less the remaining lots' exit order fees, cover the whole ticket debit including entry fees (`e03_lab.recover_lots`);
  - if no smaller sale covers it, sell everything.
- **The rest is the runner:**
  - E03.2's runner trail is unchanged: floor at entry, half the peak kept, sold at 10x;
  - plus a structural exit: the index closes back through its price at the decision.
- One-lot tickets are unchanged.
- **Diagnostics:**
  - whether the actual partial fills covered the debit;
  - a **full-sale-at-2x** arm (diagnostic only) that shows what E03.2's runner is worth at all.

**EN13 · Range rotation** (new setup; R-NEW)
- **Frozen range:** at the first completed bar from 13:00 whose previous 60 bars meet all of these:
  - efficiency ≤ 0.25;
  - closes cross the range midpoint at least 4 times (two rotations);
  - half-width ≥ 0.06% of the index;
  - the current close is inside the range.
- **Range fixed:** once frozen, high H, low Lo and mid stay fixed. The range is dead for the day at the first close outside [Lo, H].
- **Call entry:**
  - the low of the previous or current bar touches the lower quarter without going below Lo;
  - the index and future close up on the bar;
  - at least 40% of the distance from Lo to mid is still left to the midpoint.
- **Put entry:** the mirror image.
- **Exits:**
  - the midpoint (index close at or beyond mid) is the target;
  - the boundary break (close beyond Lo or H) is the structure exit;
  - plus E03.2's 35% stop, 8-minute clock, 2x management and 15:14 flat.
- Entries run 13:00–15:00, using E03.2's strike choice and 8% buy limit.

**EN14 · Second wave of a real impulse** (new setup; R-NEW + beats immediate)
- **Impulse at bar k** (13:00–14:45):
  - the index moves ≥ 2.5 × ATR10 over 3 bars;
  - the future moves the same way by at least 0.6 × the index's points.
- **Midpoint:** half way between the impulse's start close and its extreme.
- **Pause:** at least 1 bar after k that does not close beyond the extreme, with all of these:
  - both the index and the future stay beyond their impulse midpoints;
  - average futures volume over the pause bars ≥ the median futures volume of the 30 bars before the impulse.
- **Entry:** the first bar within k+1..k+6 whose index and future both close beyond their impulse extremes after the pause.
- **Exits:** a close back through the impulse midpoint (structure), plus E03.2's stop, clock, 2x management and flat.
- **Immediate control (diagnostic):** buy at bar k with the same exits.

**EN15 · Constituent breadth** (signal study; Kite 15-minute bars, Jan–Jul 2026)
- **Why this shape:** no minute-level constituent data exists. 15-minute bars are the finest we hold, so this is a signal-quality study, not a trade.
- **Data:**
  - the 50 NIFTY constituents in the frozen list in `en15_breadth.py`, whichever are present;
  - the `NIFTY 50` index series;
  - 15-minute bars starting 12:45 to 14:30 on every session.
- **Breadth:** B = (number of constituents up − number down) / number present.
- **Event:** |B| ≥ 0.6.
- **Measures:**
  - the breadth hit rate: the next bar's index return has the sign of B;
  - the index-only hit rate: the next bar's return has the sign of the index's own return on the event bar;
  - both rates again on disagreement events, where the index's own return has the opposite sign to B.
- **PASS (worth buying minute-level constituent data):** all of these:
  - n ≥ 100;
  - breadth hit rate ≥ 56%;
  - breadth hit rate − index-only hit rate ≥ 3 points;
  - breadth hit rate on disagreements > 50%, with n ≥ 30.
- Expiry days are reported separately.

**EN16 · Next-expiry confirmation** (2026 recorded quotes; 9 NIFTY and 10 SENSEX sealed expiry sessions, Sep 10 – Nov 13)
- **Trigger:**
  - minute m in 13:00–14:52 where the front future's mid moved ≥ 0.04% over 3 minutes;
  - at least 10 minutes after the previous trigger.
- **Confirmation:**
  - the next weekly expiry's near-ATM synthetic forward (K + mid(call) − mid(put), at the strike nearest the future) moved the same way over the same 3 minutes;
  - by at least half the future's move;
  - with usable quotes at both ends.
- **Outcomes:**
  - the future's move over the next 8 minutes (hit rate and mean signed change);
  - a one-lot trade: E03.2's band pick in today's expiry (NIFTY Rs 5–20 within 200 points, SENSEX Rs 16.25–65 within 400) is bought at the real ask at m+1. It is sold at the real bid at m+9, or earlier at the first bid ≤ 0.65 × entry. Real fees apply.
- **PASS:** all of these:
  - at least 30 confirmed triggers;
  - the confirmed hit rate beats the unconfirmed by at least 5 points;
  - confirmed one-lot P&L has a positive mean that beats the unconfirmed mean.
- Fewer than 30 confirmed triggers means INCONCLUSIVE.

**EN17 · Paired call+put on a volatility burst** (new setup, own pair ledger; R-NEW against random-minute pairs)
- **Burst at bar i** (13:00–14:45):
  - the index's 5-bar sum of true ranges ≥ 2 × its median 5-bar sum since 09:45 (at least 30 values);
  - |efficiency10| < 0.5, so no direction is established yet;
  - the nearest affordable OTM call and put in the band, together, are at or above their combined price 5 bars earlier (expansion at least offsets five minutes of decay);
  - both sides available.
- **Pre-freeze activity check** (counts only, no rupees seen): the brief's literal "both premiums up ≥ 10% over 5 bars" fired on 0, 1 and 0 days in 2023, 2024 and 2025, and "combined up ≥ 10%" on 0, 2 and 3. Expiry-afternoon decay makes both untestable, so the frozen condition is the combined price holding its value (3, 5 and 7 days).
- **Sizing:** equal lots (up to 3) per leg; both legs' full reserves fit Rs 2,500; up to 2 pairs a day; Rs 5,000 a day.
- **Fills:** both legs fill at the next bar.
  - If only one leg fills, it is sold on the following bar and its real result is booked.
- **Pair exits:**
  - combined fee-net bid value ≥ 1.5 × the debit;
  - ≤ 0.70 × the debit;
  - at age ≥ 4 bars, below the debit (the burst faded);
  - at age ≥ 10 bars;
  - 15:14 flat.

**EN18 · Strike by executable cost** (2026 recorded quotes, same sessions as EN16)
- **When:** every minute 13:00–14:52, for each side.
- **Base:** E03.2's band pick (the nearest OTM strike in the band with a usable quote).
- **Alternative:** the next strike further OTM, also in the band and inside the distance limit, with a usable quote.
- **The rule:** pick the alternative when its one-lot round trip, (ask − bid) × lot plus both fees, is a smaller share of its premium and its best ask covers one lot. Otherwise keep the base.
- **Outcome:** buy at the ask at m+1, sell at the bid at m+9 (stop 0.65 × entry), in two ways:
  - one lot;
  - a funded ticket (Rs 1,250 call, Rs 2,500 put, whole lots, up to 3 or 6).
- **PASS:** all of these:
  - the rule's mean funded-ticket P&L beats the base in both indices;
  - the rule is at or above the base in at least 60% of sessions;
  - the rule's mean one-lot round-trip cost share is lower.
- Otherwise it fails.

**EN19 · One small shot at a late release from a strike** (new setup; R-NEW)
- **Pin:** a bar between 14:15 and 15:00 where at least 80% of the previous 30 closes sit within ±0.10% of K, the 50-point strike nearest their mean.
- **Release:**
  - the close is ≥ 0.15% beyond K;
  - the previous close is ≥ 0.05% beyond K on the same side;
  - the future is up (or down) over the last 2 bars, in the same direction.
- **Limits:** one attempt a day (the first release, taken or not).
- **Ticket:**
  - one lot, Rs 2–19, inside Rs 1,250, using E03.2's strike rules.
- **Exits:**
  - a close back through K;
  - the 35% stop;
  - a tighter trail: gain ≥ 50% keeps 75% of the peak;
  - at 2x the single lot becomes a runner (floor at entry, 70% of the peak kept, 10x target);
  - no 8-minute clock;
  - 15:14 flat (the exchange buffer).

**EN20 · Re-enter only after a failed signal proves itself** (E03.2 base; R-EXIT)
- **When it applies:** after a ticket closes at a loss whose first sale was STOP or STRUCTURE.
- **Same-side rule:** a later same-side E03.2 signal that day is taken only if all of these hold:
  - the index close and the future are both beyond their prices at the first decision (reclaimed);
  - the pullback's extreme (the low of the last 2 bars for calls) is beyond the first decision price (a new higher low or lower high);
  - lots are at most the first ticket's.
- **Retry exits:** a close back through that new low or high (structure), plus E03.2's other exits.
- Opposite-side tickets are unchanged.
- **Diagnostic:** no second ticket after a losing stop at all. This is a block the owner rejects, so it is never a candidate; it is reported only to price E03.2's second tickets.

### My five (EN21–EN25)

Each answers a finding in `ANATOMY.md`:
- **EN21, EN22:** stop exits lose Rs 6,885.
- **EN23:** a late window with a cited mechanism.
- **EN24, EN25:** how much of a signal's value is entry quality and cost.

**EN21 · Scale in only when right** (E03.2 base; R-EXIT)
- **Scope:** tickets of 2 or more lots; one-lot tickets are unchanged.
- **First order:** ceil(planned/2) lots.
- **The add:** once, the remaining planned lots, if within 3 bars of the fill:
  - the bid reaches ≥ 1.20 × the first fill;
  - the 2-ATR structure still holds;
  - no exit is pending.
- **Add order:**
  - at most an 8% limit over the decision bar's ask;
  - reduced to fit the ticket's unused reserve.
- **After the add:** stop, lock, trail and target use the average price, and the hard stop resets to 0.65 × the average.
- **Why:** when the signal is wrong, only half the size is lost; when it is right, most of the size is carried.
- **Diagnostics:** the number of adds, their fills, and the rupees on tickets that were and were not added to.

**EN22 · The premium is the stop** (E03.2 base; R-EXIT)
- **Change:** the 35% hard premium stop is removed.
- **Unchanged:** the full premium is already reserved; the structure stop, 1.5x lock, trail, clock, 2x management and flat all stay.
- **Why:** this tests whether the hard stop is the leak (cheap 0DTE noise stopping out trades that recover) or the protection. With EN11 it brackets the stop question from both sides.

**EN23 · Last-half-hour intraday momentum** (new setup; R-NEW)
- **Source:** Gao, Han, Li & Zhou, *Market intraday momentum*, JFE 2018: the first half-hour return predicts the last half-hour return.
- **Decision** (on the completed 14:59 bar):
  - r1 = the 09:45 close over the 09:15 open, intraday only (the tape has no previous close);
  - r12 = the 15:00 close over the 14:30 close;
  - trade only when r1 and r12 have the same sign.
- **Ticket:** buy that side at 15:01, one ticket.
- **Exits:**
  - E03.2's 35% stop, lock, trail and 2x management;
  - no 8-minute clock, no structure exit;
  - sold from 15:28.
- **Deployability note:** 15:28 is executable only under NSE CAS 2.0 (continuous trading to 15:30 from Dec 7); today's CAS phase 1 auction starts at 15:15.

**EN24 · Participation behind the resume** (E03.2 base; R-EXIT)
- **Filter:** an E03.2 signal is kept only if the futures volume on the resume (decision) bar ≥ the median futures volume of the previous 30 bars (at least 20 present).
- **Why:** tests whether the pullback-resume works only when volume is behind it.
- **Data:** futures volume comes from the sealed export.

**EN25 · Patient entry** (E03.2 base; R-EXIT)
- **Order:** instead of buying at the ask, rest a buy limit at the decision bar's bid, `down(close − half(close))`, for 2 bars.
- **Fill:**
  - only when a later bar trades **through** the limit: its low ≤ limit − 0.05 (ordinary), or ≤ limit − 0.10 (adverse and severe);
  - filled at the limit, up to the bar's capacity.
- **Unfilled:** cancelled and counted as MISSED, without using a slot.
- **Why:** this measures adverse selection against the half-spread saved: do patient fills keep the losers and miss the winners?
- **Diagnostics:** missed tickets and what the control ticket made on them.

## Files and order

- **Files:**
  - `en_lab3.py`: hooks, setups, the pair loop, futures volume and `check()`;
  - `rec2026.py`: EN16 and EN18 (forward-panel export `20261117T103003Z`, sealed days only, every file hash-checked by the loader);
  - `en15_breadth.py`: EN15;
  - `en11_seconds.py`: EN11's 1-second measurement;
  - `en_score3.py`: freeze and score.
- **Order:**
  1. `python en_lab3.py` (CHECK_OK, counts only).
  2. `python en_score3.py freeze`, then commit.
  3. `python en_score3.py score` once → `results3.json`, `anatomy3.json`.
  4. Write-up in `ANATOMY3.md` and the plain report.
- Nothing is re-tuned after the score.
- Diagnostics are never promoted.
- A passing slot is written up as a disabled-shadow proposal for the owner.
