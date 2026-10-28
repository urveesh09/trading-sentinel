# O29b: why the strategies lost on Oct 28, how to tell such a day in time, and whether a fade pays on it

Research only, run on Oct 28 after the close. It used the forward panel's read-only export of Production's research archive (31 sessions, Sep 10 – Oct 28). Every replay ran through the shipped single-leg book unchanged. The study was frozen in `903f28f` before scoring. All 31 sessions had already been seen, and Oct 28 is the day that prompted the study, so a pick here is only a forward-test candidate (panel D, from Oct 29).

## Why Oct 28 went badly

Every breakout strategy took the same two trades:

| Time | What | Result (one book) |
| --- | --- | --- |
| 09:51 | a call on the break above the opening range (22,699) | stopped 10:01–10:05 (OR20 −₹2,287, EFF −₹2,890) |
| 10:21 | a put on the break below the opening range (22,610) | stopped 11:00–11:02 (SHIPPED −₹3,669, EFF −₹4,421) |

NIFTY went up, then down, then up to a new high: there was no trend. That is the day breakouts lose on.

Over the 31 sessions (hindsight labels, explanation only):

| Day type | Sessions | All four together | SHIPPED | OR20 | EFF | TPB |
| --- | --- | --- | --- | --- | --- | --- |
| Trend day (close–open ≥ half the range) | 18 | +₹40,695 | +₹5,955 | +₹21,141 | +₹27,596 | +₹16,808 |
| Not a trend day | 13 | −₹6,245 | +₹1,178 | +₹3,470 | −₹3,844 | +₹539 |

The money is made on trend days. On the other days, the breakouts mostly give it back.

## Telling it in time: the 09:45 opening drive

The opening drive is how one-way the first 30 minutes were: |price at 09:45 − open| ÷ the path of the 5-minute closes. It is HIGH when above the median of the previous 20 sessions. On Oct 28 it was 0.09, which is LOW.

Each filter on each strategy over all 31 sessions (in sample; each is one of eight filters tried):

| Strategy | Unfiltered: net / worst day / Oct 28 | Only on HIGH drive: net / worst day / Oct 28 |
| --- | --- | --- |
| SHIPPED | +₹7,132 / −₹3,669 / −₹3,669 | +₹4,988 / −₹440 / ₹0 |
| OR20 | +₹24,611 / −₹5,955 / −₹5,955 | +₹23,246 / −₹944 / ₹0 |
| EFF | +₹23,752 / −₹7,311 / −₹7,311 | +₹34,398 / −₹1,457 / ₹0 |
| TPB | +₹17,347 / −₹2,195 / ₹0 | +₹14,349 / ₹0 / ₹0 |

**Walk-forward** (each fold picks a filter on its training sessions; scored on the 19 sessions Oct 1 – Oct 28):

| | Picked filters, out of sample | Unfiltered, same sessions | Verdict (frozen) |
| --- | --- | --- | --- |
| EFF | +₹20,518, worst day −₹1,457 | +₹13,519, worst day −₹7,311 | **helps** (opening drive picked in every fold) |
| OR20 | +₹23,693, worst day −₹1,616 | +₹23,331, worst day −₹5,955 | helps, marginally |
| SHIPPED | +₹213 | +₹5,860 | does not help (the folds picked other filters) |
| TPB | +₹3,337 | +₹8,530 | does not help (TPB already waits for a trend) |
| All four, breakouts on HIGH drive (O28's fixed theory) | +₹33,828, worst day −₹2,500 | all four always: +₹27,706, worst day −₹5,955 | not selected here; shown for comparison |

The other filters mostly hurt. A minimum efficiency so far (`er`) turned OR20 and EFF negative. Fewer VWAP crosses as a condition cut profit, and "range already used" changed little. "No failed opening-range break so far" cut the worst day, but cost profit.

## A strategy for days like Oct 28: fades

These are 360 fades: buy the option against a failed opening-range break (288), or back toward VWAP after a band rejection (72).
- **On Oct 28,** all 141 fades that traded made money (median +₹7,241).
- **Over the 31 sessions,** 151 of the 360 were positive, against 25 of 48 random-entry controls.
- **Walk-forward:** the picked fades made **−₹6,684** out of sample, against −₹7,172 for the picked random entries. **Verdict: fades do not work.** They pay only on the days we cannot name in advance.

The **smart books** (breakouts behind one filter, TPB, plus one fade) made +₹47,766 out of sample. But the fold that tested Oct 28 picked a "range used" filter, and that lost **−₹10,434 that day**, which fails the no-day-worse-than-−₹5,000 rule. Verdict: they do not help.

The FINAL fold's smart book (breakouts on HIGH drive, TPB, a VWAP 2σ fade) made +₹64,546 over all 31 sessions, with a worst day of −₹2,349. That is in sample, and its fade family failed, so panel D observes it only.

## What it means

- **No strategy found here makes money on a two-way day that we could not have named in hindsight.**
- **The smart move on such a day is to sit out.** The only morning sign that held up is the 09:45 opening drive, now for the second time (O28 found it; on Oct 28 it was LOW and the drive-filtered books took no trade).
- The evidence is strongest for EFF, then OR20. It is weakest for the shipped strategy itself.

## Files and checks

- `study.py`: the day states, filters, fades, the book, the walk-forward and the freeze. `analyze.py` writes `results.json`.
- `test_study.py` passes 5 checks:
  - the filters read only closed bars (recomputing with later bars cut off gives the same states);
  - a fade's signal at a bar is the same with later bars cut off;
  - the front future is the November contract (expiry 23 Nov);
  - on O28's 29 sessions, this book reproduces O28's SHIPPED and UNION paths trade for trade, with 0 cache misses.
- 520 replays (32 filtered, 360 fades, 48 random, 2 baselines and 78 smart books) on 10 workers. Production was not stopped, because it was not needed.
- **Limit:** NIFTY only. The paper book also trades SENSEX, and SENSEX is not in the replay.
