# A two-sided expiry book: the trend decides who you are — frozen before scoring

Written November 3, 2026, after the seller study (`176e7b5`) and before any day of it is split by trend.

## Why

- E03/E03.1 earn on trend afternoons: their entry needs a strong ten-minute trend.
- The seller study's results swung with the year's afternoons (2024 rewarded selling from 13:15 to 14:15,
  2025 punished it except at 14:00). A seller is short the very moves E03 is long.
- If the seller's losses sit on trend afternoons, selling only on afternoons **without** a trend should be
  steady at every entry time, and the two books should cover each other's bad days.

## The rule

The seller of `SELLER_PLAN.md` (iron butterfly, one lot, NIFTY 2024/2025 chains, same fills and
charges), traded only when its day is **quiet** at the decision. Two definitions, both scored:

- `NOSIG`: E03.1's own entry signal (E02 R3's ten-minute trend pullback) has not fired on any completed
  minute from 13:00 up to the decision;
- `LOWEFF`: the index's thirty-minute directional efficiency at the decision is below 0.3 in size.

## The plateau test (strict, so that one lucky minute cannot pass)

Each definition is scored on 20 arms: entry 13:30, 13:45, 14:00, 14:15, 14:30 x cover 2 or 4 strikes x
stop at 2x credit or held to 15:28. A definition **passes** only if all of these hold:

1. At least 16 of its 20 arms are positive in both years at ordinary AND adverse fills.
2. In at least 16 of its 20 arms, it beats the unconditional seller in both years (ordinary).
3. The central arm (14:00, 4 strikes, stop) is positive without its best day in both years.
4. The complement (the same arms on trend days only) loses in total in both years.

Reported regardless: the severe-fill results, and a combined book of E03.1 plus the central quiet-day
seller (daily sums, correlation, worst day, drawdown). Margin is not modelled; one iron butterfly needs far
more than Rs 25,000 at a broker.

Both years are seen. A pass is a structural learning and a forward-paper candidate, never qualification.
