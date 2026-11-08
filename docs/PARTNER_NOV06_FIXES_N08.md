# N08: the partner's November 6 morning, and what the Sentinel got wrong

Evidence was read only from Production (`398d44a`) on November 6 after the close, using `partner_watch_messages`, `partner_watch_trips`, `partner_watch_plan_versions`, `partner_orders`, `partner_stop_orders`, `partner_advisory_ideas`, `partner_advisory_updates`, `partner_hedge_messages`, `partner_messages` and `partner_trade_paths`. Nothing was written to Production.

## What the partner said

They followed the Sentinel and lost in the first half. One trade was sold by their stop, but the Sentinel did not notice and kept telling them to sell it.

## What happened

**The morning.** By 12:03 the day stood at −₹9,387 after charges, 11% of ₹82,612 cash. There were 24 trades: 7 won +₹15,799 and 17 lost −₹25,186.

**The card the partner followed.** At 09:50 the Sentinel's card said: buy SENSEX 79800 CE at ₹743.7, buy up to ₹759.75, skip after 10:00, **SL order at ₹636.85** (or exit on a 5-min close under SENSEX ≈79,460), target SENSEX ≈80,004.

- **09:50:29:** the partner bought 20 at ₹764.3.
- **09:50:31:** two seconds later the trade watch's PLAN said: **"Plan stop ₹671.1 (SENSEX future 79,724) ... Place an SL sell now: trigger ₹671.1"**. Two different stops for the same buy, both from the Sentinel.
- **Stop placed:** the partner placed their SL order at ₹680, close to the watch's stop.
- **10:54:48:** that stop sold for −₹1,765.
- **10:55:29:** they bought again at ₹706.75. Their SL at ₹670 sold at 11:00:25 for −₹813.
- **What the card's stop would have done:** the option's lowest 1-minute print between 09:51 and 13:20 was ₹648 at 11:00. That is under the watch's ₹671.1 but over the card's ₹636.85.
- **The card's outcome:** it reached its target at 13:20 with the option at ₹949.6, and the option was ₹1,482 at 15:12.

**The "sell it" messages after the stop had sold.**
- **13:20:** "🎯 SENSEX 79800 CE (09:50 card, bought by 10:00): target reached ... Book profit; on anything you keep, move SL to your entry price."
- **15:10:** "⏰ ... square off by 15:15."

Both went out although the trade watch had read, every few seconds since 11:00, that none of that option was held. The card's follow-ups were built never to read the partner's positions.

**The evening review.** It said "Sold before the card's exit ... exit on the card's message, not on a wobble". But the 10:54 sale was the partner's own SL order, placed where the watch's plan told them.

**Their own NIFTY trades.**
- 23 of the 24 morning trades closed before the Sentinel's plan stop was reached. The partner's stops were usually a few rupees under the buy price, against plan stops ₹15–37 under it.
- 9 of the day's 10 "you moved your stop down" messages were about stops still above the plan stop. Each said the move "adds to the loss you chose", so lowering a stop within the plan read as a mistake.
- Held from entry with the plan stop and target, the 1-minute prints show the plan stop hit on 7 of the day's 39 trades and the target reached on 32. Today rewarded holding. The trades overlapped, so that sum is not an achievable result. It shows only that the plan stops were not the cause of the morning losses.

## Mistakes and fixes

| | The mistake | The fix (Dev) |
|---|---|---|
| C1 | `_plan_job` looked up the card only `if size is None`, but `_start_plan` always passes a size. The N04-A "one plan for a carded buy" (Nov 2 audit) therefore never ran for a real buy. | The card is looked up for every buy. A buy inside the card's window gets the card's stop and target: "on the 09:50 card", "You paid ₹764.3; the card said buy up to ₹759.75", "🛑 The card's stop ₹636.85 ...". A later buy is told "Not the 09:50 card's trade". |
| C2 | Card follow-ups (target, stop, 15:10 square-off) ignored what the partner held. | At send time `partner_watch.held_units` reads the watch's latest reconciled book read (at most 60 s old). With none of the card's option held, a target or stop becomes one line: "... target reached (...). You hold none of it: nothing to sell." The square-off reminder is not sent and is recorded `EXPIRED_UNSENT` / `partner_holds_none`. If the watch cannot say (off, no read today, stale read), the message goes as before. |
| C3 | The review called a sale by the partner's own SL order "selling on a wobble". | A sale made by the partner's fired SL order (matched by order id, else fired within 60 s of the sale), with that stop closer than the card's, is flagged `STOP_TIGHTER_THAN_CARD`: "Your SL order at ₹680 sold at 10:54 for ₹680; the card's SL was ₹636.85 ...". The advice is to put the SL at the card's SL, not closer. A sale by hand is still `EARLY_EXIT`. A replayed hold still gets a held-back square-off reminder at its time. |
| L1 | A stop moved down but still above the plan stop was told as adding to the chosen loss. | Every move down is still told (owner, Oct 24). One still at or above the plan stop now ends "Still above the plan stop ₹82.05." A move under the plan stop, off the buy price or in profit keeps its wording. |
| C4 (Nov 8) | The pre-buy check (`check 79800 ce`) gave the watch's own stop inside a card's buy window, a second stop beside the card's. | `_check_reply` looks the card up as `_plan_job` does. Inside the window: "🃏 On the 09:50 card: buy up to ₹759.75." (and "₹764.3 is over it." for a dearer price), "🛑 If you buy: the card's stop ₹636.85 (or exit on a 5-min close under SENSEX ≈79,460) ...", "🎯 The card's target: option ≈₹776–913 ...". The size line uses the card's stop. After the window, after the card's close or at or under its stop: "• Not the 09:50 card's trade: ..." and the watch's own plan. A failed card read leaves the watch's plan. |

Still not checked: the eleven flow-pulse messages of Nov 6 ("OI flow leans ..."), whose text is not stored.

## Verification

- `tests/test_nov06_partner_fixes.py` has 14 checks, including the real Nov 6 card and both buys. The end-to-end card test fails on the old line and passes with the fix.
- **C4 (Nov 8):** one check-through-the-inbox test (inside the window, a price over the buy limit, after the window). All partner suites: 675 passed.
- Two older `test_partner_watch.py` wording checks were updated for L1.
- **Partner group:** the 24 partner, coach, advisory and watch suites passed, 591 checks before the two wording updates. After them, the watch group re-ran 161 passed and the advisory group 211 passed.
- **Whole engine suite:** 6,246 passed and 4 skipped, `pytest_exit=0`, in 11 min 19 s. That run left out the new file, which passed on its own.
- **Atlas:** regenerated, 304 modules.

## Rollout and rollback

Dev only, in `partner_watch.py`, `partner_manual_advisory.py`, `partner_buyer.py`, `partner_coach.py` and `partner_lessons.py`. There is no schema, configuration or scheduler change. The existing `status_reason` column records `partner_holds_none`. Messages only: nothing trades.

Rollback is to revert the commit through GitHub. Deploy needs the owner's word. The Dev branch also carries the other agent's unreleased Nov 5 profit protection (`5642781`) and research commits. That protection is on by default (`PARTNER_WATCH_PROFIT_PROTECTION_ENABLED`; set it to false to turn it off). An earlier version of this note said it was off; that was wrong.
