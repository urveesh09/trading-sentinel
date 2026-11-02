# E01.1 outcome: E011 accepted, E011R kept as a paper comparison

Scored once at freeze commit f457d9b. No rule or test changed after the result. `results.json` holds every figure; `view.py` prints them.

Both primaries pass T1-T5. By the frozen decision rule E011 is E01.1, because E011R isn't at least as good on T5: -423 against -64 on ordinary quotes and -840 against -17 on adverse.

## Eight archived sessions, A + B + the ticket

| | C (main book) | E01 | **E01.1** | No-bank arm |
|---|---:|---:|---:|---:|
| Net | +6,548.10 | +11,095.17 | **+12,918.15** | +18,196.64 |
| Adverse quotes | +6,361.82 | +10,994.22 | **+12,729.64** | +17,943.25 |
| Worst session | -1,427.00 | -1,000.15 | **-954.88** | -954.88 |
| Without the best session | -7,232.64 | -2,685.57 | **-2,176.31** | -2,176.31 |
| Fall in running P&L | 4,520.04 | 2,100.73 | **1,902.87** | 1,902.87 |
| Up / down sessions | 1 / 6 | 3 / 4 | **3 / 4** | 3 / 4 |
| Ticket alone | +1,847.40 | +6,394.47 | **+8,217.45** | +13,495.94 |

Sessions, E01 to E01.1: Oct 6 -1,000 to -896; Oct 8 +24 to +121; Oct 13 +13,781 to +15,094; Oct 15 -955 unchanged; Oct 19 -904 to -836; Oct 22 no trade; Oct 27 -242 to -112; Oct 29 +392 to +501.

## Stress on the same sessions

- **Late entry (T3), ticket alone.** 10 seconds: E01 6,172, E01.1 8,134. 20 seconds: 6,727, 8,442. 30 seconds: 6,044, 8,261.
- **Every break as its own ticket (T4), 18 tickets.** E01 -150, E01.1 +4,022, no-bank +8,132. Adverse: -462, +3,627, +7,673.
- **Neighbours (T2).** Stop 20%: +13,369. Stop 30%: +12,409. Floor keeping 50%: +12,918. All beat E01 with a worst session no worse.

## September, seven tickets, exits only

| Seven tickets, two days | C | E01 | **E01.1** | No-bank arm |
|---|---:|---:|---:|---:|
| Ordinary | -7,849.84 | -2,503.01 | **-63.69** | -422.85 |
| Adverse | -7,300.27 | -2,053.99 | **-16.92** | -839.94 |
| Worst ticket | -2,403.67 | -899.46 | **-899.46** | -899.46 |

One change at a time, ordinary: stop 25% alone -2,023. Cost-recovery bank alone **-3,444, worse than E01.** Floor from 3x alone -255.

**One ticket makes most of this.** Sep 22 at 14:06:50, a call at Rs 5.50, reached about Rs 26.90 and fell to Rs 3.45. E01 banked half at 17.95, then the rest rode down to its stop: +1,948. E01.1 banked two lots at 17.95 and sold the other four at 15.00: +4,005. That's 2,057 of the 2,439 gain. The other six tickets gain 382 between them, from the tighter stop: three improve, three don't change.

**What it taught.** The bank alone is worse: selling less at 3x without a floor just leaves more to collapse. The floor is what protects the runner. C's own trail starts at 5x, and this ticket reached 4.9x, so it never armed.

## Which of the two

Three tickets on these days reached 3x:

| Ticket | E01 | E01.1 | No bank |
|---|---:|---:|---:|
| Oct 13, ran to 17x | +10,289 | +11,602 | +16,881 |
| Oct 29 second break, reached 3x and collapsed | +1,640 | +2,937 | +1,769 |
| Sep 22, reached 4.9x and collapsed | +1,948 | +4,005 | +3,646 |

E01.1 is ahead when a ticket collapses. Selling nothing is ahead when a ticket runs, and in the total, on that one Oct 13 run. Three tickets can't settle it, so both go on paper.

## How far to trust this

- **All eight October sessions are seen,** and the rules were chosen after studying them. They're evidence of nothing new on their own.
- **September is a clean test of a narrow thing.** No ticket's later price was read before the freeze. But it holds seven call tickets on two days, one ticket makes most of the gain, and these aren't tickets the book would have bought: none of its 11 breaks has a ticket in the files.
- **It's still a lottery.** Sessions up and down are the same as E01's, 3 and 4. Without Oct 13 the book still loses Rs 2,176 over seven sessions. On the ticket alone, leaving out the two best of the 14, the other 12 average about -Rs 620.
- **A, B and SENSEX aren't tested by September at all.**
- **Not carried.** Skipping wide boxes (+14,204, without the best -891) and cheaper tickets (+13,764) look good on the seen days. They change which ticket is bought, and September can't test that, so they wait for data that can.

The next real exam is the full-year data, with the strikes the ticket would buy: `EXAM_YEAR.md`.
