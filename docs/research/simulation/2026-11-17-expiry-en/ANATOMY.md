# Where each EN arm won and lost (owner's rule, Nov 17)

`anatomy.py` replays every frozen arm with the same labs and coverage rule, and asserts each year's
ordinary net against the scored results (`ANATOMY_OK`); the full tables are in `anatomy.json`. These are
descriptions of seen data, not new scores. Nothing is re-tuned from them; the "worth keeping" items are
hypotheses for new data or forward paper only.

Rupees are the ordinary-fill net after fees, on one Rs 25,000 book per year. "t" means tickets and "w"
means winners.

## E03.2 itself (the benchmark)

| Year | Net | Tickets (winners) | Calls | Puts | Stop exits | 8-minute clock exits | 14:30–15:00 entries |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2023 | −3,645 | 17 (4) | 10t 2w −1,663 | 7t 2w −1,982 | 5t −3,709 | 11t +26 | 2t 0w −1,587 |
| 2024 | +15,581 | 19 (8) | 11t 3w +1,086 | 8t 5w +14,495 | 6t −2,207 | 5t +877 | 5t 3w +13,069 (hero +11,771) |
| 2025 | +5,937 | 20 (13) | 11t 6w +965 | 9t 7w +4,972 | 2t −969 | 15t +5,373 | 3t 0w −916 |

**Good parts:**
- **The 8-minute clock exit is the steady earner.** It made +5,373 in 2025, +877 in 2024 and +26 in 2023.
  It never lost a year.
- **2x split + runner** catches the rare big put: 2024-03-28 made +11,771.
- **14:00–14:30 entries** are positive in all three years: +740, +1,741 and +2,847.

**Bad parts:**
- **Stop exits are where the money goes:** −3,709 (2023), −2,207 (2024) and −969 (2025), −6,885 over
  three years. In 2023 they are the whole loss.
- **Late entries (14:30–15:00)** lost in 2023 and 2025 with 0 winners from 5 tickets. Only 2024's single
  hero makes the window positive; without it 2024's late tickets made +1,298.
- **13:00–13:30 entries in 2023** lost −1,913.
- **Calls** are near zero in 2024 and 2025 (+1,086, +965) and lose in 2023.

**Worth keeping:** the clock exit and the 14:00–14:30 window. **Worth examining on new data:** whether
late entries without a hero are a drag, and why stops in 2023 fell through (6-lot put −1,162 on
2023-06-15).

## EN03: looser put gate

**What happened:** every extra put ticket loses.
- 2024 at 0.60: 16 added, 4 winners, −4,183. Stop exits rose from −2,207 to −5,469.
- 2025 at 0.65: 5 added, 0 winners, −3,981.
- Those 2025 losses tripped the drawdown brake, which **removed 12 later E03.2 tickets worth +5,905.**
  That is why 2025 collapses to −4,026.

**Good parts:** none economically.

**Lessons:**
- The 0.70 gate is load-bearing.
- A bad filter is amplified by the brakes: early losses stop the book before its good trades.

## EN04: bigger puts (2.5x / 3x / 3.5x)

**Where 3x's money comes from:**
- 2024: +9,221 more from the same 8 tickets, of which **+6,649 is the one hero day.**
- 2025: +4,013 more from 9 tickets, spread across ordinary put winners (2025-08-07 +1,300 more,
  2025-09-02 +1,019 more), less one added loser (−587).

**Where it loses:**
- 2023: every bigger put just loses more. 2023-06-15 went from −1,162 to −1,719, and 2023-03-16 from −889
  to −1,310.
- The worst day roughly doubles (−647 → −1,247).
- 2.5x and 3.5x hit lot rounding and brake effects. At 3.5x, 2023 dropped 8 tickets through the brake.

**Good part:** in 2025 the extra profit is not one day; several normal put winners grow.

**Bad part:**
- In a losing year (2023) size only enlarges the losses.
- 2024's gain is mostly the hero.

**Keep as:** an idea for after a fresh-year pass, never before.

## EN05: put runner at the 8-minute clock

**What happened:** every changed ticket earned less.
- 2024: 2 tickets, −949 (2024-08-22: +953 → +287).
- 2025: 6 tickets, −2,218 (2025-08-07: +1,253 → +730).
- The runners all end on the runner trail.

**Lesson:** puts that are up at 8 minutes have usually done their move. Banking at the clock is right, which
matches the clock being E03.2's steady earner.

## EN08: no entries on calm mornings

| Year | Tickets removed | Their net | Effect |
|---|---:|---:|---|
| 2023 | 9 | −1,869 | good: losers removed |
| 2024 | 4 | −292 | good: losers removed |
| 2025 | 5 | +3,538 | **bad: winners removed**, 5 of 5 had won |

**Good part:** in 2 of 3 years calm mornings held E03.2's losers. The 2023 loss would halve.

**Bad part:** 2025's calm mornings were its best days, so the gate is not a stable rule.

**Worth examining on new data:** the calm-morning tickets' side and time, to see whether a narrower version
holds (hypothesis only).

## EN09: breakout after a quiet spell

| | 2023 | 2024 | 2025 |
|---|---:|---:|---:|
| Alone | 13t 3w −2,920 | 13t 1w −4,200 | 7t 0w −4,197 |
| Matched random-side null | −2,293 | −3,281 | −3,900 |

- Stops and index-structure exits dominate, and 13:00–14:00 is the worst.
- **Crowding, a key lesson:** added to E03.2 in 2024, a breakout ticket on 2024-03-28 used the day's slot
  and budget first. E03.2's hero shrank from +11,771 to +681 (−11,302 on that day alone).
- A weaker second setup that shares the ticket limit can cost the main setup its best trade.

**Good part:** none.

**Lesson:** any future second setup needs its own budget and slot, never E03.2's, and the
crowding must be measured.

## EN10: one-lot bank

It touched only one-lot tickets, which are all calls (puts get two or more lots).

| Year | Saved (fading calls) | Cut (calls that would have run) |
|---|---|---|
| 2023 | 2023-03-16, +38 → +638 | — |
| 2024 | 2024-07-18, −183 → +427 | 2024-02-22, +1,313 → +340 (a 2x winner cut) |
| 2025 | 2025-10-14, +258 → +473 | 2025-04-17, +761 → +544; 2025-12-16, +321 → +240 |

**Good part:** it rescues one-lot calls that rise and then fade: 3 tickets, +1,424 more.

**Bad part:** it truncates calls that kept rising: 3 tickets, −1,271, including a 2x winner cut by −973.
The net effect is +153 over three years, and there are too few tickets.

## EN07 and the 2023 exam

The repaired coverage rule changed nothing. The 2023 anatomy is the E03.2 row above: the loss is stops
(−3,709), early entries (13:00–13:30, −1,913) and late entries (14:30–15:00, −1,587). The clock exit and
the 14:00–14:30 window were the only positive parts (+26 and +740).
