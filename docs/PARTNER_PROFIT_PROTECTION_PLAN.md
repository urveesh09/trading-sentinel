# Partner profit protection

Production 398d44a recorded a booked profit of Rs 45,487.86 on November 5 at 13:54. Its first giveback message arrived at 14:00 after Rs 5,954.36 had been surrendered. Two new calls opened in the meantime. Their separate plan losses totalled about Rs 4,964. The partner ended at Rs 29,025.18. The new advice should show how an entry or addition affects the profit the partner wants to keep.

Implement in Dev through the existing watch and authenticated chat. Suggest keeping 90% of the booked high after profit reaches the greater of Rs 5,000 or 20% of session cash. Accept `protect AMOUNT` for a fixed session floor and `protect auto` to restore the suggestion. Store the choice in the existing daily watch state. Provide a single milestone and a single floor-breach message per day. Add a compact combined-risk comparison to checks and to fills or additions that threaten the floor. Keep the existing loss warnings and later giveback updates.

Classify the relevant index future using three consecutive completed five-minute candles and a fresh last trade. Require aligned structure or a confirmed break of the preceding range. Interpret the direction for calls and puts separately. Missing or mixed evidence yields cautious wording. Use existing check inputs and quotes. Bound any additional market read at delivery and keep it off the polling path.

Use the same fee schedule and matched fill quantities as the watch. Sum planned losses for held positions and a proposed check. An estimate of open P&L requires fresh displayed bid depth for the entire holding and accounts for prior partial sales. Preserve unknown values when the holdings, plans or quotes are incomplete. Advice remains conditional on execution and requires no order permissions.

Verify persistence and day rollover, the November 5 arithmetic, grouped exposure, partial exits, stale and missing market data, current message validation, deduplication, and the existing partner paths. Update guide, plan, checklist and generated atlas. Rollback uses `PARTNER_WATCH_PROFIT_PROTECTION_ENABLED=false`. No migration or separate job. Keep the work local in Dev until a GitHub promotion is requested.

## Implemented behavior

The existing authenticated partner chat accepts `protect 40000` and `protect auto`. A fixed choice takes effect once booked profit reaches it. The suggested 90% floor trails the booked peak after the material-profit threshold. Both reset by session date. The switch defaults on and requires Sentinel partner advice to be enabled.

One milestone and the first floor breach use the existing DAY outbox. Further alerts fire as losses deepen by 10% of session cash below the floor. This replaces the overlapping legacy giveback steps while the floor is active. Existing loss alerts and legacy giveback alerts outside the active floor retain their behavior. CHECK shows the proposed trade alongside held exposure. PLAN and ADDED gain a short note when the combined plan loss threatens the floor or the futures direction is adverse. An eligible open mark can trigger the floor alert before any sale closes the trip.

The market check reads the relevant front future. The direction uses three consecutive completed five-minute candles and a fresh last trade. A completed break confirmed by the current price or consistent rising/falling structure gives a direction. Calls and puts are interpreted separately. The watch reuses current check data, caches candles by five-minute boundary and allows one second for any additional read during message building. Missing clocks, incomplete candles, and unavailable market data produce an unverified reading. The advice describes observed structure and has no established forward prediction accuracy.

Combined plan-loss estimates include partial sales and charges on the same basis as the watch. They depend on those exits being possible. Open marks require enough fresh displayed bids for every watched unit and reject duplicate use of the same depth across products. A floor is a preference for advice. The existing partner places and manages orders.

## Verification and rollout

Run in Dev with `python-engine/winvenv/Scripts/python.exe` and Python 3.11.9. The focused command `python -m pytest python-engine/tests/test_partner_profit_protection.py -q --tb=short` passed five tests after adding the fake partner account fixture. Its first run exposed two fixture setup failures. The complete partner test selection (`python-engine/tests/test_partner*.py`, supplied as explicit paths) plus `test_main_surface_characterization.py` initially passed 664 tests. After correcting the overlap with legacy giveback steps, the same command passed 665 tests in 61.21 seconds with six dependency deprecation warnings and exit zero. This is the partner and surface test group. The regenerated atlas indexes 304 modules.

The November 5 test uses the two actual post-peak position sizes and displayed plan stops. It reproduces approximately Rs 4,964 combined loss against a Rs 4,549 buffer. Synthetic trend cases validate the direction wording. This is an arithmetic and behavior check with no modeled partner compliance or forward profit result.

The implementation uses the existing watch-state table and DAY/CHECK transport. No new schema, service, dependencies or scheduler jobs. Production head was checked as 398d44a with a clean tracked tree. This commit is local Dev work. Forward checks after any GitHub rollout should measure message timing, display quality, actual partner choices and the later winners a pause might miss.
