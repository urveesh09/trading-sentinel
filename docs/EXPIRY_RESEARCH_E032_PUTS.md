# E03.2 — the edge is in the puts

November 3, 2026. **Built in Dev as a disabled paper variant beside E03.1. Not deployed. Both test years
were already seen, so the figures are in-sample.**

## What we found

E03.1's money comes almost entirely from its put tickets:

| E03.1's tickets, 2024 + 2025 | Tickets | Net | 2024 | 2025 |
|---|---:|---:|---:|---:|
| Calls | 23 | +Rs 1,800 | +835 | +965 |
| **Puts** | **18** | **+Rs 10,627** | **+8,063** | **+2,564** |

- Puts made money in **all eight quarters**; calls lost in three.
- It is the same in E02 and E03, so it is not the runner.
- Random entries show **no** such gap. It belongs to the signal: when E02 sees a downtrend pause and
  resume on an expiry afternoon, the fall usually keeps going. Rallies are slower. The F&O strategy found
  the same thing on other days: its calls lost and its puts earned in all three years.
- Honest limit: without the one big day (a put), the difference is suggestive but not proven
  statistically (p = 0.13). That is why it goes to paper first.

## E03.2: put more money where the edge is

E03.1, with three changes:

1. **A put ticket gets twice the money:** Rs 2,500 and up to six lots. Calls stay Rs 1,250.
2. **Never pay more than 8% above the price seen at the decision** (it was 10%). This only refuses
   fills that jump; it cuts the bad-fill loss.
3. **Sell everything by 15:14**, before the closing auction freezes the index. Long options held through
   the auction lost value on 6 of 8 recorded days. In 2024-2025 it changes nothing.

| 2024 + 2025, Rs 25,000 | E03.1 | **E03.2** |
|---|---:|---:|
| Normal fills | +Rs 12,427 | **+Rs 21,518** (+73%) |
| Worse fills | +Rs 11,498 | **+Rs 20,001** |
| Very bad fills | -Rs 3,234 | **-Rs 2,438** |
| Worst day | -Rs 478 | -Rs 647 |
| Largest fall from a peak | Rs 1,374 | **Rs 754** |

More risk is taken only on the side that earns, so the extra money more than pays for it: the
drawdown is smaller and bad fills cost less. The most it can reserve in one day doubles to Rs 5,000.

## What else this round tested (all failed)

- Trading only with the week's or the day's direction: cut good trades.
- Choosing the strike by delta instead of price: worse in every setting.
- The volatility explanation was half right: option prices rose on falls in 2024 but not in 2025.

## In the engine

A fourth variant beside E02, E03 and E03.1: its own cash, database and switch,
`EXPIRY_E032_SHADOW_ENABLED`, off. E02, E03 and E03.1 behave exactly as before. The engine matches the
research lab on all 78 positions and 78 entry sizes, zero mismatches.

## What happens next (your decisions)

1. Merge, rebuild, and switch on E03.2 beside E03.1, so every ticket is compared on paper.
2. The frozen exam on the approved download now includes E03.2 and a direct test of the put advantage.
3. After 20 forward tickets and the exam: the calculation says puts could go to 3x within the same risk
   limits (+Rs 34,165 in the model). That is a later decision, on fresh data only.

Technical record: [research/simulation/2026-11-03-expiry-round8/README.md](research/simulation/2026-11-03-expiry-round8/README.md).
