# N10: earn the second lot

November 1, 2026. Dev research only. No application, Production, money, order, broker, download or lot-limit change.

## Problem

The owner asks for N09.1's loss control with more profit than N08, without overfitting.

| Book | Fresh Rs 2.5 lakh, four-year sum | 2023 | Worst day | Worst annual fall | One account |
|---|---:|---:|---:|---:|---:|
| N08 | 2,02,284 | -37,581 | -9,720 | 15.08% | 2,12,419 |
| N09.1 CUSHION | 1,90,218 | -32,684 | -6,127 | 13.13% | 3,84,310 |

N09.1 gives up Rs 12,066 and is only a control on exposure. Everything N09 and N09.1 learned stands: no reading known at entry predicts direction, confirmation misses too many winners (Rs 1,48,895 of winners to avoid Rs 1,13,921 of losers), and switching strategies by market state has failed four times.

## The idea

N08 pays for its second lot at the entry, when nothing is known. N09's confirmation made every lot wait, so it missed the first leg of winners. The two can be separated: **keep the entry, and make only the second lot wait for proof.**

From the saved one-lot N08 trades, before any N10 replay:

- 91 of 99 winners reach +1R. 24 of 144 losers do.
- N08's entry-time second lots: 64 trades, -8,829 / +30,850 / +10,583 / +44,100. They double the loss on every wrong-direction trade.
- A rough sum of adding at +1R on every trade to the same exit: -4,758 / +27,478 / +35,176 / +36,616. Rough: fixed entry delta, no stop on the added lot, an estimated cost. It is why this is worth testing and proves nothing.

**The mechanism is not a forecast.** It is the owner's "smart, not blocking": no trade is refused, and size follows what the trade has already shown. All four years are seen, so this is discipline, not an exam.

## Earlier evidence, disclosed

Adding lots has been tried here twice and did not earn its place:

- **N08's screen:** the engine's add when the target arms the trail, on top of normal size: -12,549 over 2024-26 on N07.
- **O30s:** ADD1 at +1R with the stop moved to entry, on LIVE and TPB: "bigger both ways", falls 1.3 to 2 times larger.

N10 differs in four ways, each stated so it can fail on its own: the earned lot **replaces** the entry-time lot instead of adding to it; it is earlier than the target; the first lot's trade is **untouched** (its price, stop, trail, lock and clock all stay, where the earlier adds blended the entry price and moved the stop); and the earned lot has **its own stop** at the trade's entry level.

## The rule, written once

- **Entry:** every N08 signal enters at one lot through the unchanged planner.
- **Add:** when the future's move in the trade's favour first reaches +X R (X = 1.0, R = the distance from entry to the initial underlying stop), buy one lot of the same contract at the ask, once per step, before 14:45, the system's existing last-entry time.
- **Earned lot's exits:** it leaves when the future returns to the trade's entry level, or at a 25% premium backstop from its own price, whichever comes first, at the bid. It also leaves with the first lot, at the same price, for any reason. It is never added again once stopped.
- **Refused when:** any brake is active; the open premium cap would be broken; or planned risk exceeds the budget.
- **Planned risk:** first lot: entry premium x 25% x quantity, or nothing once its trail stop is beyond entry. Each earned lot: the smaller of its 25% backstop and (ask minus the premium at the previous step, plus the spread), times quantity.
- **Budget:** the planner's own: min(2% of equity, Rs 6,250), scaled by the risk multiplier. With a 25% backstop at Rs 2.5 lakh, that is Rs 5,000.
- **Accounting:** the earned lot's cash goes to equity when it closes, as a banked part of the same trade. The risk brakes see one trade. Extra cost (200 + 5 x lots) x lots applies to each lot's own round trip.

## Books, frozen before any is scored

Fresh Rs 2.5 lakh a year, today's brakes, extra cost in the money path. N08's signals and exits throughout.

| Name | Entry | Second lot | Reserve |
|---|---|---|---|
| EARN_N | one lot | earned only where the native plan allowed two | none |
| EARN_W | one lot | earned where planned risk fits | none |
| EARN_WV | one lot | as EARN_W, and yesterday's ATR% at or above its 250-session median (N09's reading) | none |
| EARN_WC | one lot | as EARN_W | N09.1's CUSHION, reserving the earned lot too |
| EARN_WVC | one lot | as EARN_WV | CUSHION |
| LADDER_WC | one lot | as EARN_W, plus a third lot at +2R whose stop is +1R | CUSHION |
| HYBRID_C | N09.1's CUSHION sizing, one or two lots | one more earned lot, up to three in all, where planned risk fits | CUSHION |

**Neighbours, for the plateau check:** X = 0.75 and 1.25 for each CUSHION book (LADDER's second step moves with it: 1.75, 2.25).

**Cost arms:** none and double extra cost for each CUSHION book. **One account from January 2023:** each CUSHION book, no reset, floor carried. **Brakes off, for the mechanism:** N08, one lot, EARN_W, EARN_WV. **Random-entry control:** 10 of the random books at one lot, brakes off, with and without the +1R add.

## Controls that must pass first

Every code path on with nothing changed:

- `NOOP` equals N08, trade for trade, on all four years.
- `NOOP_CUSHION` equals N09.1's saved CUSHION, trade for trade.
- `EARN_W` with X out of reach equals N08 at one lot, trade for trade.
- The first lot of each `EARN_W` trade uses the same exit logic as one-lot N08: checked on prices and exit reasons wherever the two books hold the same admission.

## Verdict, fixed now

**N10 passes** only if one CUSHION book meets all of these. If more than one does, the highest four-year sum is N10. If none does, N10 fails and stays on record as failed, with no change to any threshold.

1. Four-year sum above N08's 2,02,284.
2. Worst day no larger than N09.1's 6,127.
3. Worst annual closed-equity fall no larger than N09.1's 13.13%.
4. 2023 net no worse than N09.1's -32,684.
5. 2024, 2025 and 2026 each positive, and at least two of them at or above N09.1's (76,294 / 46,738 / 99,870).
6. One account from January 2023 ends at or above N09.1's 3,84,310.
7. Double extra cost: four-year sum at or above N09.1's 1,52,165.
8. Plateau: X = 0.75 and X = 1.25 each have a four-year sum above N09.1's 1,90,218.
9. Without its five largest winners, the four-year sum is at or above N09.1's without its own five largest.

**Reported, not gates:** paired weekly t against N08 and N09.1, block bootstrap of the difference, CSCV overfitting estimate across the panel, whole-year stress over 256 orderings, the random-entry control, how many trades earned a lot and what those lots made, and what each change cost.

**How to read the random control, written before it runs.** If the add helps random entries, trades that have already moved tend to keep moving, which supports the mechanism regardless of the entry. If it hurts them, the add is only as good as the entries it follows, and N10 is more exposed to another 2023.

Passing makes N10 a candidate on seen years. It doesn't make it proven and changes nothing live. The test that counts is unseen data: NIFTY 2022 and new sessions.

## Rollout and rollback

No deployment. N10 has no engine switch. The study sits in its own folder and imports the earlier studies without editing them. Rollback is deleting the folder. Monday's real-money test isn't affected: it stays at one lot.
