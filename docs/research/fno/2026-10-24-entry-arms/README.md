# F&O single-leg entry arms at the live exits (October 24, 2026) — study `fno-entry-t2`

Frozen in commit `e37504f` (`study/freeze.json`, 17 sources and the dataset hashed) and pushed before
scoring; scored once (`study/results.json`). Research only: nothing here can place an order or change a live
decision.

## Question

The owner wants more profit and smaller losses without fitting the system to one thing. The F&O book's money
came from trends held with a trail (Sep 1 – Oct 23: three trail exits +₹13,767; every other exit −₹10,002), and
no F&O trade was taken on Oct 21–23 (most bars after a break were `not_fresh_break`). Do more entries on trend
days (a continuation after a pullback), or any of the recorded shadow entry variants, beat the shipped entries
when they are traded through the whole live book?

The shadow variants had only ever been given a target-hit scenario (FNO_BASE: 43 of 43 "wins", +₹85,689 on
Production), which replays no stop, time stop, trail or forced close. Here each arm trades its own entries through
`fno_policy_replay` (the shipped entry plan, sizing, brakes, the live exit ladder at fast-exit cadence, costs,
bid/ask fills); only the entry signal differs.

## Data

Read-only export of the Production research archive (`scripts/export_fno_replay_dataset.py`), 28 NIFTY sessions
Sep 10 – Oct 23 (Oct 23 unsealed), kept out of git under `_local/`. The replay is NIFTY only: SENSEX trades are
not replayed (3 of the 4 live trades in the decision window were SENSEX).

- Development: Sep 10 – Oct 9 (the sessions earlier F&O studies and the Oct 7 exit grid used).
- Decision ("untouched" for entry rules): Oct 12 – Oct 23.

## Arms

| Arm | Entry |
| --- | --- |
| BASELINE | the shipped entry (`CURRENT`: live switches, fast exit on) |
| FNO_SIG_CONTINUATION (candidate, new) | the base break, or after it a pullback to within 0.25 ATR of the break level since the latest extreme, then a bar resuming the trend |
| FNO_SIG_OR_20 / _OR_45 | a 20 / 45-minute opening range (recorded shadow variants) |
| FNO_SIG_CONFIRM_1 | one confirming bar after the cross, bounded extension (recorded shadow variant) |

## Results

| Window | Arm | Trades | Net | Net without the best winner | Max drawdown | Win rate | Exits |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Development | BASELINE | 12 | **+₹7,286** | +₹178 | ₹1,991 | 50% | time 7, trail 3, stop 2 |
| Development | CONTINUATION | 10 | **−₹4,846** | −₹5,429 | ₹5,124 | 30% | time 7, stop 3 |
| Development | OR_20 | 10 | +₹4,597 | −₹2,511 | ₹2,877 | 50% | lock 2, time 3, trail 2, stop 3 |
| Development | OR_45 | 13 | +₹5,655 | −₹1,453 | ₹2,769 | 46% | time 7, trail 3, stop 3 |
| Development | CONFIRM_1 | 3 | +₹3,921 | +₹316 | ₹0 | 100% | lock 1, time 1, trail 1 |
| Decision | BASELINE | 1 | +₹3,515 | ₹0 | ₹0 | 100% | trail 1 |
| Decision | CONTINUATION | 1 | +₹3,515 | ₹0 | ₹0 | 100% | trail 1 |
| Decision | OR_20 | 0 | ₹0 | ₹0 | ₹0 | – | – |
| Decision | OR_45 | 3 | +₹3,449 | +₹1,138 | ₹266 | 67% | lock 2, trail 1 |
| Decision | CONFIRM_1 | 0 | ₹0 | ₹0 | ₹0 | – | – |

Decision (the four pre-declared checks, candidate CONTINUATION on the decision window): net > 0 ✓; net without
the best winner > 0 ✗; beats BASELINE ✗; drawdown ✓ → **NOT SUPPORTED, stays off.**

Parity: on development the baseline replay matches 9 of the 12 live NIFTY trades by bar and contract. In the
decision window the one NIFTY trade (Oct 15) matches; live it exited on the profit lock at +₹663, the current
code (the lock's 8-second confirmation, SX-F1) holds it on the trail to +₹3,515.

## The drawdown halt (attribution, not the decision: `halt_attribution.py` / `.json`)

On development the continuation's early extra losses (Sep 10, 17, 23) put paper equity under the 15% drawdown
halt (₹2,12,500 on the ₹2.5L allocation). The halt then blocked the three trend-day winners the baseline took (Sep 28
13:30, Sep 30 14:20, Oct 1 12:15: +₹11,516 in the baseline). Rerun with the halt removed and everything else live:

| Window | Arm | Trades | Net | Net without the best winner | Max drawdown | Win rate |
| --- | --- | --- | --- | --- | --- | --- |
| Development | BASELINE | 13 | +₹6,922 | −₹186 | ₹1,991 | 46% |
| Development | CONTINUATION | 20 | −₹93 | −₹7,201 | ₹6,017 | 35% |
| Development | OR_45 | 14 | +₹5,291 | −₹1,817 | ₹2,769 | 43% |
| Development | OR_20 | 11 | +₹4,583 | −₹2,525 | ₹2,877 | 45% |
| Development | CONFIRM_1 | 3 | +₹3,921 | +₹316 | ₹0 | 100% |
| Decision | (every arm) | as above | unchanged | | | |

Without the halt the continuation gets the trend winners back, and its own extra entries still lose about ₹7,000:
the rule is the problem, the halt made it worse. The baseline barely changes (the halt did not bind for it here).

The live paper book (Production, read-only, Oct 24): ₹2,26,798, i.e. ₹14,298 above that halt. The halt counts
every loss since inception (the single-leg book is −₹23,012 over 45 closed trades since July). Two or three
ordinary losses would stop all F&O paper entries, trend days included. Changing the halt is the owner's decision.

## What it means

- **More entries on trend days did not pay.** The continuation's extra entries were mostly losers (time and
  stop exits, profit factor 0.18). They pushed the book under the drawdown halt, which then blocked the trend
  winners: −₹4,846 against +₹7,286 on the same sessions. Without the halt they still lose about ₹7,000. It stays off; it keeps being recorded in shadow (live, from
  deploy) for forward evidence, as the other variants are.
- **None of the recorded shadow variants beats the shipped entry.** OR_45 is the closest (positive in both
  windows) but loses without its best winner on development. The decision window is too thin (one NIFTY trade
  for the baseline) to promote anything; that is a fact about the sample, not a result.
- **The shipped entry rule is the best of the five tested here.** What made the difference in this archive is
  the exit side: trails on trend days, and holding through a brief dip (Oct 15).

## Limits

NIFTY only; ~60-second archive resolution (true fast-exit timing cannot be measured from it); 28 sessions, one
of them unsealed; paper fills at the archived bid/ask. "Promising" would only have meant more shadow; this
result authorises nothing either way beyond keeping the shipped entry.
