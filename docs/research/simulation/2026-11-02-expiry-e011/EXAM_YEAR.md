# E01.1's next exam: frozen before the data exists

Written November 2, 2026, before any of this data was downloaded or read. Whatever data arrives, these rules apply once, without changes. No study in this repository has scored an expiry-day option on those sessions.

## Why the data's shape decides everything

The owner plans to download more one-second expiry data. The job that produced September fetches the **opening at-the-money strike, call and put, for the whole day**. On September that shape could not test the book:

- **None of the 11 breaks had a ticket.** By the afternoon the opening strike was in the money or too dear for C's band.
- **A and B can't run,** because they need strikes near the afternoon's price.
- **Only seven tickets could be tested,** all calls, on two of the four days, and only for exits.

A year in that shape gives the same narrow test on more days. It would say something about exits, and nothing about whether the book makes money.

## The shape that would run the book

For each expiry day, instead of two legs all day:

| | Today's job | What the book needs |
|---|---|---|
| Hours | 09:15 to 15:30 | 13:00 to 15:30, and to 15:40 for expiries from Aug 3, 2026 if the source has it |
| Legs | opening ATM call and put | calls from 100 points below the 13:00 ATM to 300 above it, puts from 100 above to 300 below, 18 legs on NIFTY's 50-point strikes |
| Requests per expiry | 48 | about 180 (10 windows of 16 minutes per leg) |
| Expiries in a day's 4,800 | about 100 | about 26 |
| A year of about 50 expiries | under a day | about two days |
| Runs C's real ticket? | No | Yes, at nearly every break |
| Runs A? | No | Yes |
| Runs B? | No | Yes, unless the price has moved more than 100 points from 13:00 |

This needs no bid, ask or depth, and they don't exist in this history anyway. Ticks stay last-trade prices with the frozen spread model in `sept.py`, so it remains a modelled fill, and the ATM pair gives the index proxy.

This is the owner's decision. The seconds job is a dated exception and a wider target needs their word. It goes through the download skill and agent, not research.

## What is compared

All with C's entries, A and B unchanged where they can run:

| Name | Rule |
|---|---|
| **C** | the main book's ticket |
| **E01** | 30% stop |
| **E01.1** | `E011`: 25% stop, cost back at 3x, 60% floor from 3x |
| **E01.1 no bank** | `E011R`: 25% stop, no sale at 3x, 60% floor from 3x |
| Neighbour | `E011_S20`: E01.1 with a 20% stop |
| Entry reading | `E011_BOX35`: E01.1, no ticket when the box is wider than 35 bp |
| Entry reading | `E011_BAND50`: E01.1 with C's band's top halved |

`round2-map.json`, read after September, shows a 20% stop ahead on these tickets. That's why it's named here. It doesn't replace 25% unless this exam says so.

## The tests, once

1. **E01.1 against E01:** ticket net higher, worst session no worse, net without the best session no worse, on ordinary and adverse fills. Fail means E01 stays and E01.1 is dropped.
2. **No bank against E01.1:** replaces it only if at least as good on all three measures, ordinary and adverse.
3. **Stop 20% against 25%:** same bar.
4. **Each entry reading against E01.1:** same bar, one at a time, and each must keep at least 80% of E01.1's tickets that made Rs 1,000 or more.
5. **The whole book:** A + B + the winning ticket, against A + B + C and A + B + E01, on sessions where A and B can run.
6. **Report regardless:** tickets that reached 3x and what happened next, wins and losses by direction, each year apart, and every break whose ticket was unavailable. Unavailable is never zero.

A pass is a result on one more history, with modelled fills. It doesn't make E01.1 the main book or authorise real orders. Passing all six raises it for the owner to decide, beside the forward count: at least 20 new paired tickets, at least five per index.

## What this exam can't say

NIFTY only unless SENSEX is also downloaded. Expiry weekdays, lot sizes and the closing session changed across these years, so each year is reported apart. Regular F&O research has already read the non-expiry days of these years, so the market regime is known even though these option paths aren't.
