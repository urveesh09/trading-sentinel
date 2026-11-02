# E01.1: a stop 5 points tighter, the cost back at 3x, and a floor under the winner

November 2, 2026. **That night the owner made E01.1 the main expiry ticket on paper (expiry-v4), and the old C runs on as shadow `CL`.** This is the owner's choice before any forward result, not a result of the frozen tests: nothing here has run on a new expiry yet. A and B are unchanged, and no real order is involved.

**E01.1 earned more and lost less than E01 on every set it was tested on.** It keeps C's exact ticket and changes only what happens after buying it. It is still a lottery: it loses on most days and needs an occasional big winner, and it loses without one. The eight October sessions were seen before the rules were chosen, and September could only test a small part of it. So this is a better rule on what we have, not proof it will make money.

Technical record: [research/simulation/2026-11-02-expiry-e011/](research/simulation/2026-11-02-expiry-e011/README.md). The plan, frozen before September was read: [PLAN.md](research/simulation/2026-11-02-expiry-e011/PLAN.md).

## The rule

C's ticket is bought as before: the same break, strike, size, Rs 2,500 ceiling, failed-break exit and deadlines. Then:

| | C | E01 | **E01.1** |
|---|---|---|---|
| Premium stop | none | 30% | **25%** |
| At 3x | sell half | sell half | **sell just enough lots to take the ticket's whole cost back** |
| Floor | keep 60% of the peak, from 5x | same | **keep 60% of the peak, from 3x** |

## What went wrong before

Three tickets on these days reached 3x, and two of them collapsed:

- **Sep 22, Rs 5.50:** reached about Rs 26.90 and fell to Rs 3.45. That is 4.9x, just short of the 5x where the floor starts, so E01 had no protection. It banked half and rode the rest down to its stop.
- **Oct 29's second break, Rs 17:** reached about 3.2x and collapsed.
- **Oct 13, Rs 2.90:** ran to 17x. This is the one that carries the whole book.

So a ticket can reach 3x to 5x and still give almost all of it back. The floor closes that gap, and it does so with C's own 60%, not a new number.

**Selling less at 3x is unsafe on its own.** It leaves more lots to collapse. On September it was worse than E01 (-3,444 against -2,503). It only works with the floor.

## The result

**Eight archived sessions, the whole book (A + B + the ticket), real depth:**

| | C (main) | E01 | **E01.1** |
|---|---:|---:|---:|
| Net | +6,548 | +11,095 | **+12,918** |
| At worse fills | +6,362 | +10,994 | **+12,730** |
| Worst session | -1,427 | -1,000 | **-955** |
| Without the best session | -7,233 | -2,686 | **-2,176** |
| Biggest fall | 4,520 | 2,101 | **1,903** |
| NIFTY | +9,987 | +11,635 | **+13,250** |
| SENSEX | -3,439 | -540 | **-332** |
| Up / down sessions | 1 / 6 | 3 / 4 | **3 / 4** |

No session is worse than E01, and six are better.

**The same eight sessions, harder tests, ticket only:**

| | E01 | **E01.1** |
|---|---:|---:|
| Every break as its own ticket (18) | -150 | **+4,022** |
| ...at worse fills | -462 | **+3,627** |
| Entry 10 seconds late | +6,172 | **+8,134** |
| Entry 20 seconds late | +6,727 | **+8,442** |
| Entry 30 seconds late | +6,044 | **+8,261** |

**September, which no rule had seen, exits only, seven tickets:**

| | C | E01 | **E01.1** |
|---|---:|---:|---:|
| Ordinary fills | -7,850 | -2,503 | **-64** |
| Worse fills | -7,300 | -2,054 | **-17** |
| Worst ticket | -2,404 | -899 | **-899** |

All five frozen tests pass. These aren't money the book would have made: the seven tickets overlap, each has its own Rs 2,500, and the book wouldn't have bought them.

## September could not replay the book

The files hold one strike, chosen at the open. By the afternoon it is usually in the money or too dear for the ticket.

- **None of the 11 breaks had a ticket C could buy.** A and B can't run at all.
- **So September can't say whether the book makes money.** It can only say what different exits do to a ticket already bought. I bought seven tickets by a fixed rule and compared exits only.
- **They are all calls, on two of the four days.** Sep 15 and Sep 29 gave nothing.
- **One ticket makes most of it.** Sep 22's +2,057 is most of the +2,439 gain. The other six add +382, from the tighter stop.

It was a clean test: the rules were committed before any ticket's later price was read. But it's a small one.

## What the genome search taught

About 16,000 rule sets were bred across four starts, with the worst dropped each generation.

- **Its winners look wonderful and aren't usable.** Rs 18,000-20,000 on the ticket from about five tickets: rules that learned to buy Oct 13.
- **Rerun with each session hidden, it earned -2,564 on the hidden days, against E01's +6,394.** It lost less on the losing days, but it can't learn about a winner it can't see. So the genome pointed at ideas, and the rule was chosen by simple checks instead of by score.
- **About 140 single changes were tried against E01 first, session by session.** A and B had nothing to improve on these days.
- **Rejected:** buying again after a stop (-1,289, four days worse), waiting for the ticket to prove itself and scaling in (both break under worse fills or a small change), a 15% stop (Oct 13 is stopped under worse fills).

**A bug of mine, kept on record:** the first genome ran with no premium stop at all, because the engine reads a new position's first stop by play name and the candidate's name was unknown. Everything was rerun. A check and a test now pin it.

## How far to trust it

**In its favour.**
- The two main changes each have a plain reason, and the floor isn't a new number.
- The floor earned nothing on the eight sessions it was designed from, then earned on September. That's the best kind of evidence available here.
- Stops at 20% and 30% and a floor keeping 50% all still beat E01, so the result isn't balanced on one setting.
- No session got worse.

**Against it.**
- **All eight October sessions were seen.** Those figures show what the rule would have done, not what it will do.
- **The big result is still one day.** Without Oct 13 the book loses Rs 2,176 over seven sessions.
- **It wins rarely.** Up and down sessions are the same as E01's. Of the ticket's 14 trades (seven on the book's October sessions, seven on September), the 12 outside the two best average about -Rs 620.
- **September is thin:** seven call tickets on two days, one of them most of the gain.
- **Fills are modelled.** September has no bid or ask, and auction-window fills remain unverified.

## Open questions

**Sell at 3x, or let it all run?** Selling nothing (`E011R`) made +18,197 on the eight sessions, against +12,918, and all of that lead is Oct 13. On the two tickets that collapsed, E01.1 did better:

| Reached 3x | E01 | **E01.1** | Sell nothing |
|---|---:|---:|---:|
| Oct 13, ran to 17x | +10,289 | +11,602 | +16,881 |
| Oct 29, collapsed | +1,640 | +2,937 | +1,769 |
| Sep 22, collapsed | +1,948 | +4,005 | +3,646 |

The frozen rule picks E01.1, because selling nothing lost to it on September. Both go on paper, so new expiries can answer it.

**A 20% stop?** It looks better than 25% on all these tickets, and I only read that map after the score. The rule stays at 25%, and the 20% is named in the next exam.

**Skipping wide boxes and buying cheaper tickets** look good on the eight sessions (+14,204 and +13,764), but they change which ticket is bought and September can't test that. They wait.

## In the engine

**Main since expiry-v4:** `C` runs E01.1. **Shadows on the same ticket, shadow-v8, version `expiry-e011-v2`:** `CL` is the old C and `CE011R` sells nothing at 3x. `CE01` stays. The earlier shadow name `CE011` is gone: its rule is now C's, and it never ran in Production.

- **The swap did only what it says.** The real tick and store, all eight sessions, ordinary and worse fills: the new C equals the old `CE011`, the new `CL` equals the old C, and every other play and quote count is unchanged. 290 legs, zero mismatches: `native-parity-NATIVE_V4.json`.
- **The shadows copy only a saved C ticket,** and pairing needs the parent's ID and the same terms. A failed shadow save never costs C its ticket.
- **The evening summary** prints C's rule, the shadows beside it, and the day's box width as a reading only. C's record splits at v4.
- **Shadows off:** `EXPIRY_E011_SHADOW_ENABLED=false` and an engine restart. It blocks new copies, and open legs keep their exits. Going back to C's old exits needs a code revert and a deploy. No table and no `.env` change.

Before the swap, `CE011` and `CE011R` were shadows with 28 legs equal to the frozen lab's, field by field.

Tests: the whole engine suite, 6,034 passed and 4 skipped. Tests prove the code does what the rule says, not that the rule makes money.

## What's next

**The next real exam is the full-year data, and its rules are already frozen:** [EXAM_YEAR.md](research/simulation/2026-11-02-expiry-e011/EXAM_YEAR.md).

**The download's shape decides what that exam can say.** A year of opening-strike data repeats September's limit. The afternoon's strikes around the 13:00 price would let the whole book run, at about 180 requests an expiry, which is about two days for a year.

Primary sources behind the earlier rules are in E01's [SOURCES.md](research/simulation/2026-11-02-expiry-e01/SOURCES.md). The searches for this study found practitioner advice on expiry-day timing and on reading straddle premium, none of it tested, and nothing usable on stops against time stops. No rule here rests on them.
