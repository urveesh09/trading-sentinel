# E03 — E02's entry, with a free runner for the zero-to-hero move

November 3, 2026. **E03 is built in Dev as a disabled paper shadow beside E02. It is
not deployed, and both test years were already seen, so its figures are in-sample.**

## The answer to "how do we catch zero to hero"

**Buying cheap options and waiting for the hero move loses money.** On 105 NIFTY expiry
afternoons (2024 and 2025):

- Half the days had *some* cheap option that went 5x or more. But only 6-9% of all cheap
  tickets did, and nothing readable in advance picks which one.
- A ticket of about Rs 1,000 held to the close lost Rs 139 on average in 2024 and Rs 473
  in 2025. The cheapest (Rs 1-2) lost the most: they are priced as lottery tickets.
- Morning movement does predict afternoon movement in both years. But the option price
  already pays for most of it, and no volatility or "option is cheap" reading made money
  in both years without its best day.

So every hero idea that **chose when to buy** failed:

| Tried | What happened |
|---|---|
| E02.1: keep E02's ticket instead of selling at 2x | 2025 turned to a loss |
| An extra cheap "kicker" ticket further out | Made money only on one day; lost without it |
| The "gamma blast" (index breaks the biggest open-interest strike) | Looked good in a quick estimate; in the real book 2025 lost Rs 4,328 |
| One bigger Rs 2,500 ticket a day | More money, but the worst day doubled and 2024 lost without its best day |
| A volatility filter on E02's entries | Fewer trades, less money |

**What works is changing what a winner does, not when to buy.** E02's entry already
beats 97.5% of random entries in both years. Its weakness is that it sells everything at
2x, so it can never catch a hero move.

## The rule

E02's entry, strike band, stops and cash limits, unchanged. Then:

1. **Up to three lots** in the same Rs 1,250 ticket (E02 buys one). A cheap ticket buys
   two or three lots; a dear one still buys one.
2. **At 2x, sell all but half the lots.** That locks E02's profit.
3. **The rest run free:** the floor is the ticket's cost, it keeps half its peak, and it
   is sold at 10x or at 15:28. No 8-minute clock and no index stop on the runner.

The runner can only give back its own lot's gain. The worst day, the Rs 1,250 per ticket
and the Rs 2,500 per day are E02's.

## The result (NIFTY, today's lot size and fees, Rs 25,000 paper cash)

| | E02 | **E03** |
|---|---:|---:|
| 2024 | +3,514 | **+8,567** |
| 2025 | +3,387 | **+3,389** |
| Both years, ordinary fills | +6,901 | **+11,956** |
| Both years, worse fills | +6,260 | **+11,115** |
| Both years, severe fills | -3,766 | **-3,273** |
| Worst day | -568 | **-568** |
| Without the best day (2024 / 2025) | +2,201 / +2,184 | **+2,717 / +2,187** |

E02's figures here use the four-strike pick (see below); as E02 reported them they were
+6,329 / +5,669.

**How far to trust it:**

- **The extra is one hero, so far.** On March 28, 2024 two lots were bought at Rs 7.60;
  one sold at 18.85 and the runner at 87.65 (11.5x): +Rs 5,850. In 2025 no two-lot ticket
  reached 2x, so the runner never fired and E03 equals E02. That is how hero trades
  behave: rare, but here they cost nothing when they don't come.
- **The runner's settings don't matter much.** Every neighbour (keep 40-60%, floor 1-2x,
  5x, 10x or no target) is at or above E02 in both years.
- **Random entries with E03's exits lose** (about -Rs 800 to -1,000 a year), so the
  entry matters as much as the exits.
- **Both years were seen** when E02 was fitted and when this was built. Severe fills
  lose money. Production's own five recorded NIFTY expiries (October 6 to November 3) gave
  one trade (+Rs 94), far too few to judge.

**A defect fixed on the way:** E02's lab could pick a strike up to 8 steps away, but the
history holds every strike only within 4 steps of the day's range. A farther strike
exists only if the index later moved toward it (look-ahead). It happened once, on a
losing 2024 trade. E03 never goes beyond 4 steps.

## E01.1 on the new data

E01.1 (the main paper C since November 2) was tested on NIFTY 2024, the year it had
never been run on: **-Rs 9,012 over 46 tickets** (old C -8,441, E01 -18,669). With
2025's -Rs 20,638 it lost about Rs 29,650 over 99 NIFTY expiries. E01.1 is the best of
the lottery exits, but C's entry (any break of the 13:00-13:30 box) has no edge: most
tickets never move. On November 3, its first Production day as C, its ticket hit the 25%
stop in ten minutes (-Rs 701); the main book lost Rs 901 that day (A -663, B +462).

E03 is E01.1's own idea (take the cost back, let the rest run on a floor) applied to
E02's much better entry. **Making E03 (or E02) the expiry book's main ticket instead of
C is your decision, after forward paper evidence.**

## In the engine

- `python-engine/expiry_e02.py` now runs two variants. E02 is unchanged. E03 has its own
  paper cash (Rs 25,000), its own database (`<DB_PATH>.expiry-e03.db`) and its own flag,
  `EXPIRY_E03_SHADOW_ENABLED`, false by default.
- No real orders, messages or ledger writes. A switched-off variant still exits an open
  leg. NIFTY only; SENSEX is not qualified.
- The paper code matches the research lab on all 82 positions (both years, both fill
  levels): zero mismatches. Tests show the code does what the rule says, not that the
  rule makes money.

Technical record: [research/simulation/2026-11-03-expiry-e03/README.md](research/simulation/2026-11-03-expiry-e03/README.md).

## What happens next

1. **Your call:** merge and rebuild, then switch on `EXPIRY_E03_SHADOW_ENABLED` and
   `EXPIRY_E02_SHADOW_ENABLED` together, so every E03 ticket is compared with E02's on
   the same entry.
2. **Forward evidence:** at least 20 closed E03 tickets before any promotion.
3. **An untouched test:** a full afternoon chain on new expiries. SENSEX needs its own
   full-chain study. NIFTY 2023 stays protected until you assign it.
