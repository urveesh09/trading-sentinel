# N09 partner: a coach, not a caution machine (plan, November 9, 2026)

## Problem

On Nov 9 the partner made 31 option buys between 09:15 and 12:04 (NIFTY's weekly expiry moved to Monday because of Tuesday's holiday), and 25 of the first 30 closed trades lost. The owner: "Failure of theirs is our failure ... not just a caution machine, but something that can help them grow almost every day."

What the Production record showed (read-only, `partner_watch_trips` and `partner_watch_messages`, 351 closed trades over 10 sessions from Oct 27):

- **Nov 9:** 9 switches between calls and puts while NIFTY stayed in a ~200-point band; 10 buys in the same minute a losing trade closed; at 09:27, after four losses, about 70% of the cash in one call (more than a quarter of the day's loss); after the best trade (+65% in 5 min) an immediate buy-back at a 70% higher price; 8 stops moved down, 3 adds to falling options, 8 refused orders.
- **What Sentinel sent:** 59 messages by noon, mostly 6–8 line PLAN messages after each buy. "The Sentinel takes 1 lot after a loss" about 25 times. Six identical DAY updates. The 09:50 plan arrived after 11 trades and said "expiry today, scalp only" and "take profits quickly". Nothing said what the market was doing or what to wait for.
- **10-day record:** mornings (entries before 12:00) ended down on 8 of 10 days. Trades closed within 2 minutes won 14% (n=35); trades held 15–60 minutes won 49% (n=104) and carried most of the profit. The average win was +21% of premium, the average loss −14%; the win rate is 36%, where that payoff needs about 40%.
- **Not supported, so not used:** trades inside the opening range and expiry-day options were not worse in their record; buys 0–2 minutes after a loss were mixed. The frozen `partner_watch_score` verdicts on UNUSUAL_SIZE and AFTER_LOSS were not SUPPORTED either.

## What changes (behind `PARTNER_WATCH_COACH_ENABLED`, default on; off = N08 behaviour)

1. **Game plan, 09:00** (GAMEPLAN, once a day): from the 09:00 `partner_watch_prompt` job whether or not the partner is logged in (the watch's ticks only start at 09:15, too late), or after a login before 11:00, or from the first ticks if both were missed. It says which index expires today (from today's instrument book only), gives one line of the partner's own record (`partner_habits.record_line`, only parts that meet the frozen sample rule), and offers four buttons for today's own rule: "3 trades before 10:00", "Stop at −10% today", "Both", "No rule today". Typed `rule 3`, `rule 10%`, `rule 3 10%`, `rule none` do the same. The choice is confirmed in one line.
2. **Their own rule, reminded once** (RULE): at the Nth buy before 10:00, and when the day's result reaches the chosen share of cash. Nothing is blocked.
3. **Short buy messages** (PLAN): the buy and its stop with the loss, one warning at most (twice the trade just lost or more, size against their usual, minutes after a loss), and the stop-order action. With nothing protecting the trade yet and a fresh price, the stop and the action are one line, so the message is two or three lines. The card's target stays for card buys. `more` sends the full plan of the latest buy.
4. **One losing-run message** (STREAK) at 2 losses in a row, and at 4 only when the 4th came at least 10 minutes after the 2nd (on Nov 9 they were one minute apart). It gives the times, the last 30 minutes' 5-minute range of that index's future, "I'll message you when a 5-min bar closes outside", and their hold-time record when supported.
5. **Break alert** (BREAK): once, on the first completed 5-minute close outside that range, only if the STREAK message was sent; expires at 15:15.
6. **Fewer, shorter DAY loss messages:** two lines, at 20% and 40% of cash only (the first warnings are the STREAK and the partner's own rule). Give-back and profit-floor messages (N04-B, N07) unchanged.
6b. **A patient win, said as it happens** (GOOD, once a day): the first trade closed in profit after 15 minutes or more, with their own 15–60 minute win rate when the record supports it. The coach praises the pattern that works, not only warning.
7. **Evening habits** in the coach note (`partner_habits.evening_lines`): buys and buys before 10:00, median hold, quick re-buys after a loss, stops moved down; the best trade; one thing to try tomorrow, picked by a fixed rule from the costliest habit. On the week's last session, this week against last week.
8. **Brief wording:** "expiry today, scalp only" and "premium rich, take profits quickly" contradicted the coach's own lesson (sold before the card's exit, Nov 5 and Nov 6). Now "expiry today: time value melts fast" and "premium rich (options cost more than usual)".
8b. **N09b, the owner's heads-up** (`PARTNER_WATCH_OWNER_HEADSUP_ENABLED`, its own switch): once a day, to the owner's own chat (`operator_alert`), when the partner has 4 losses in a row or the day is past −20% of their cash. It gives counts and times only, with no money figures. The owner: "keep a heads up to me, though I doubt every time I can help it's important". On Nov 9, after the owner's call, the buying slowed from about 11 an hour to 5, the sizes fell to 4–7% of the cash and the pre-buy check was used.
9. **Scorecard, frozen before any forward day** (`SCORECARD.md`, `partner_habits.scorecard`): the 10-session baseline against the first 10 sessions after deployment.

Not changed: LOWERED, ADDED, REFUSED and the protection messages (owner, Oct 24: every stop moved down is told); the Sentinel's own trades (item 6 of the proposal is the owner's call); the cards; nothing places or blocks an order.

## Files and contracts

- `python-engine/partner_habits.py` (new): pure record/habit functions and read-only loaders over `partner_watch_trips` and `partner_watch_messages`; `scorecard` CLI.
- `python-engine/partner_watch.py`: GAMEPLAN, RULE, STREAK, BREAK kinds; `short_plan_text`, `short_day_text`; the `rule`/`more` replies; `handle_button` for `watch:rule:YYYYMMDD:<choice>`.
- `python-engine/partner_coach.py`: habits appended to the evening note.
- `python-engine/partner_buyer.py`: the two wordings.
- `python-engine/config.py`: `PARTNER_WATCH_COACH_ENABLED`.
- Tests: `tests/test_partner_coach_n09.py`; conftest turns the flag off for the older pinned-text tests (as with `PARTNER_SENTINEL_ADVICE_ENABLED`).

## Acceptance checks

- Nov 9's sequence replayed through the tick: one GAMEPLAN, STREAK at the 2nd and 4th straight loss, the RULE line at the chosen share, DAY only at 20% and 40%, PLAN texts at most 4 lines.
- BREAK only after a sent STREAK, once, on a completed bar close outside the range.
- A rule tap for another day changes nothing; typed rules parse; `more` returns the latest full plan.
- With the flag off, every existing partner test passes unchanged.
- No order path, no block, no new Kite call outside the existing `Market` reads (the 5-minute candles the profit floor already reads).

## Rollout and rollback

Dev, then GitHub, then Production only on the owner's word. Rollback: `PARTNER_WATCH_COACH_ENABLED=false` (N08 behaviour), or revert the commit. No migration: new rows in existing tables only (`partner_watch_state` keys `gameplan:`, `rule:`, `break:`, `plan_long:`).

## Remaining after this slice

Judge on the frozen scorecard after 10 forward sessions. Profit is not promised. Moving the Sentinel's own trades to the evening is the owner's call.
