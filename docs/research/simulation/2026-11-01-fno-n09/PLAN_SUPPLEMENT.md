# N09 supplement: what the first round pointed to

**Status of this file:** written after the first round was scored and before anything below is replayed. The first round's rule stands and its result isn't changed: every challenger failed, and the book it composed, called **N09A** from here on, failed its verdict. This supplement doesn't rescue N09A. It asks new questions, and it is post-hoc: I chose them after seeing the first round, and that is stated wherever they are reported.

## First-round results that led here

- **N09A** (N08 without the morning two-lot rule): 2023 -38,667, 2024 +65,214, 2025 +46,823, 2026 +85,576, total +1,58,946 against N08's +2,02,284. Verdict checks 1, 2 and 3 fail.
- **S_VOL** missed its 2023 check by Rs 393, but its fresh-year total is +1,91,428 and its worst day -6,127 against N08's -9,720. Its last 2023 trade is Dec 26 against N08's Oct 3. With the brake on, a 2023 net is mostly where the floor happens to stop the book, so that check was a poor way to judge it. That is my judgement, made after seeing the number, so it doesn't overturn the check.
- **One account from January 2023:** N08 unchanged ends at Rs 2,12,419 with no trade after Oct 3, 2023. With a restart, ANNUAL ends at Rs 4,41,234 and SHADOW at Rs 4,36,635.
- **The overfitting estimate of 0.031 is not trustworthy.** Frozen code let the cost-stress books into the search. `COST|none` isn't a strategy, it is N08 with no assumed cost, so it won in-sample in 12,201 of 12,870 splits and flattered the score. It stays on record in `pbo.json`.

## The questions, all fixed now

**N09B = N08's entries and exits, S_VOL for size, SHADOW for the account.** At one lot it makes the same decisions as N08, so it adds no entry or exit filter.

| Run | What it answers |
|---|---|
| S_VOL brakes off, each year, against N08 brakes off | Does the size rule cost less in a bad year when the brake isn't setting the number? |
| S_VOL with no extra cost and double, against N08 | Does it depend on the assumed cost? |
| One account from Jan 2023: S_VOL, S_VOL with ANNUAL, S_VOL with SHADOW | Does size plus restart hold up in the account an owner would really have? |
| Corrected overfitting estimate | The 84 books without the four cost-stress books and exact duplicates. Same method, same blocks |
| Random reshuffle of months, one lot, 10,000 paths, 46 months each | What does a restart do when bad stretches come at other times, or twice? No restart, ANNUAL and SHADOW on the same paths |
| 48 broad-search books, plus Intraday DMI and Shock Recovery, on 2023 | None was chosen using 2023, so this is new evidence on them. Is there a complement that earns where N08 struggles? |

## Rules, fixed now

**N09B replaces N08 as the research lead only if all pass:**

1. One account with SHADOW ends at 95% or more of N08 with SHADOW.
2. That account's largest closed fall and worst day are no larger than N08 with SHADOW's.
3. Brakes off, its 2023 loss is at least 10% smaller than N08's.
4. Its fresh-year four-year total is at least 90% of N08's.
5. Its four-year total stays above zero at double the assumed cost.

**The restart rule is worth keeping only if all pass, on N08:**

1. In the real replay, SHADOW's one-account end is above the unchanged account's.
2. In the reshuffle, SHADOW's median end is above no restart's.
3. In the reshuffle, SHADOW's 5th-percentile end is no more than 10% below no restart's. A restart can lose a second 15%, and this bounds that risk.

SHADOW is the rule tested here because it waits for evidence. ANNUAL is reported beside it and can't be chosen on its result.

**A complement goes forward only if all pass:** at one lot after Rs 200 a trade, positive in 2023; at least 3 of 4 years positive; four-year net above zero; and, added to N08 at one lot, 2023 and the four-year total both higher. Fifty candidates on one year will show some positives by chance, so the best 2023 result proves nothing by itself. It would go to a later frozen test, not into N09B.

**Nothing changes in the system on any of this.** N09B would still be a seen-year lead: NIFTY 2022 on the owner's login, then a forward shadow, then real fills. A change to the live 15% halt is the owner's decision alone.
