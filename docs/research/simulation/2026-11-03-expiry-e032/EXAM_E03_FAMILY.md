# The E03 family's exam on the next expiry download — frozen before the data exists

Written November 3, 2026, after the E03.2 search and before any of this data is downloaded or read. It adds
the E03 family to the exam already frozen for E01.1 (`2026-11-02-expiry-e011/EXAM_YEAR.md`), whose download
shape the owner approved on November 3. Whatever arrives is scored once under these rules, without changes.
No download is started here; that job goes through the download skill and agent.

## Data, as approved

NIFTY expiry days, options 13:00-15:30 (to 15:40 from August 3, 2026, if the source has it): calls from 100
points below the 13:00 at-the-money strike to 300 above it, puts from 100 above to 300 below (18 legs).
One-second last trades become minute bars (open, high, low, close, summed volume). Index and front-future
minutes come from the history database (it holds 2026 index and futures all day through October 28; later
expiries need them too), so E02's ten-minute signal has its full warm-up at 13:00. NIFTY 2023 stays protected unless the owner assigns it to this exam.

## Arms (each exactly as frozen in its own `candidate.json`)

| Arm | Rule |
|---|---|
| `E02` | E02 R3, one lot, four-strike cap |
| `E03` | `2026-11-03-expiry-e03/candidate.json` |
| `E031` | `2026-11-03-expiry-e031/candidate.json` |
| `E031_L8` | E03.1 with the buy limit at 8% above the decision ask instead of 10% |

Own Rs 25,000 book each, E02's reserves and brakes, ordinary / adverse / severe fills as in the labs, and
40 random-entry seeds for `E031` (same windows, same signal count per day, same exits).

## Coverage: unavailable is never zero

A decision is **available** only if every strike from the first out-of-the-money strike to 200 points away,
on the signal's side, is among the downloaded legs at that minute. Otherwise it is **unavailable**: the
arm does not trade it, and the count is reported per arm and per day. Days with any unavailable decision
are also reported apart, because a skipped decision changes the rest of that day's book. The usual
case is a day that has moved more than 100 points from its 13:00 level.

## The tests, once

1. **`E031` stands:** net above zero at ordinary AND adverse fills, net without the best day above zero
   (ordinary), no day worse than -Rs 1,250, and above the median random seed. Fail means the E03 family
   has no confirmed edge and stays paper-only.
2. **`E031` against `E03`:** E03.1 stays the lead only if at least as good at ordinary and adverse.
   Otherwise E03 is the lead.
3. **`E031_L8` against `E031`:** the 8% limit is adopted only if the severe result is better and
   ordinary and adverse are no worse.
4. **Report regardless:** each year apart, every ticket with its exit, tickets per hour, the unavailable
   counts, and E02 beside them all.

A pass is one more modelled history, not a qualification for real money. Promotion still needs the
forward count: at least 20 new closed paper tickets.
