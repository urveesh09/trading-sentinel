# N10.1: what improved, and what did not

**The account-control correction is built and tested. The price-backed third
lot did not establish an economic improvement over N10 retry.** All four years
were already studied; none of these results proves future profitability.

WATCH_FLAT lowers the floor only when the account is flat and genuinely cannot
fund a typical lot. PREMIUM_LOCK also requires the option's own price to fund
the added lot's protective stop; an underlying trail alone is insufficient.
Stops can still gap. The changes concern recovery, sizing and exits.

Fresh Rs 250,000 EACH year, after modeled costs:

| Book | 2023 | 2024 | 2025 | 2026 to Oct 28 | Total |
|---|---:|---:|---:|---:|---:|
| N08 | -37,581 | 76,294 | 58,647 | 104,924 | 202,284 |
| N09.1 | -32,684 | 76,294 | 46,738 | 99,870 | 190,218 |
| N10 one try | -32,898 | 79,334 | 46,738 | 105,311 | 198,484 |
| N10 retry | -32,898 | 88,805 | 51,583 | 125,786 | 233,275 |
| N10.1 WATCH_FLAT | -32,898 | 88,805 | 51,583 | 125,786 | 233,275 |
| N10.1 PREMIUM_LOCK | -32,684 | 80,030 | 54,122 | 100,120 | 201,588 |

| Book | Worst day | Worst annual closed drawdown | Double-cost total | Without own top five winners |
|---|---:|---:|---:|---:|
| N10 retry | -6,127 | 13.21% | 168,672 | 106,281 |
| N10.1 WATCH_FLAT | -6,127 | 13.21% | 165,934 | 106,281 |
| N10.1 PREMIUM_LOCK | -6,127 | 13.13% | 128,938 | 62,059 |

One continuous Rs 250,000 account, no resets/deposits:

| One continuous Rs 250,000 account | Cost 199 | Cost 200 | Cost 202 | Cost 400 |
|---|---:|---:|---:|---:|
| N10 retry | 427,697 | 427,440 | 427,111 | 410,161 |
| N10.1 WATCH_FLAT | 427,712 | 427,452 | 425,872 | 400,420 |
| N10.1 PREMIUM_LOCK | 429,214 | 401,475 | 428,392 | 361,046 |

- **N10.1 WATCH_FLAT:** does NOT pass economic superiority. Failed checks: higher four-year profit, profit under doubled extra costs, account value at every tested cost.
- **N10.1 PREMIUM_LOCK:** does NOT pass economic superiority. Failed checks: higher four-year profit, profit under doubled extra costs, profit excluding the five best winners, account value at every tested cost.

The distinction matters: a more accurate risk rule can give up profitable
pullbacks, and a tighter recovery rule can change later admissions. Both costs
are reported. 2023 remains a loss; this did not discover a way to predict every
bad market day or know that an extra lot will win.

**Recommendation:** keep N10 retry as the research profit reference, with its
unproven retry rule clearly labelled. Keep WATCH_FLAT for prospective comparison;
do not promote PREMIUM_LOCK. Its tighter stops gave up too much of the original
positions' earnings. No new live strategy is recommended from this round.

80 annual executions and 100 focused tests; independent cash/fees/prices/stops/
floor/state checks passed. Production and real-money settings unchanged.
Source `c567f8e`; exact controls `f4f92f2`.

Next: prospective keyed shadows and actual execution-cost evidence, or the
separately frozen 2022 exam when the owner acquires it. 2022 was untouched here.
Keep the original N10 exam; do not silently add/tune candidates after reading it.

Full methods, tradeoffs, attribution and uncertainty:
[N10.1 study](research/simulation/2026-11-02-fno-n101/README.md).
