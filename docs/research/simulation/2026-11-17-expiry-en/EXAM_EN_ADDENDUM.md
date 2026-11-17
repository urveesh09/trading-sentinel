# The EN round joins the E03-family exam: NIFTY 2023, scored once on the owner's word

Written November 17, 2026, after EN03–EN05 were scored on seen 2024/2025 (`results.json`) and before any
NIFTY 2023 price is read.
- The E03-family exam (`../2026-11-03-expiry-e032/EXAM_E03_FAMILY.md`) and its E03.2 addendum
  (`../2026-11-03-expiry-round8/EXAM_E032_ADDENDUM.md`) were frozen for "the next expiry download".
- The family exam says: "NIFTY 2023 stays protected unless the owner assigns it to this exam."
- The Breeze database already holds the NIFTY 2023 expiry-day chains: full one-minute chains, the
  same kind of data as 2024/2025. They sit in the sealed export `2026-11-02-expiry-e02/_local/data.sqlite`,
  which is hash-checked.
- Nothing in either earlier file changes. This addendum adds arms and tests, and fixes the route.

## Route

`exam2023.py score`:
- It refuses unless `OWNER_WORD.md` holds the owner's assignment and `freeze-exam.json` is committed.
- The tapes are built exactly as for 2024/2025. `exam2023.py check` proves the loader equals
  `data.load_year` on 2024.
- The labs are unchanged: E02 and E03 by `e03_lab`, E03.1 by `r8b_lab`, and E03.2 plus the EN arms by
  `en_lab`.
- Each arm runs a continuous Rs 25,000 book with its own brakes, at three fill levels: ordinary,
  adverse and severe.

**Coverage (the family exam's rule):**
- A decision is unavailable when any strike from the first OTM strike to 200 points on its side is
  missing from the day's chain.
- No arm trades an unavailable decision, and the count is reported per day.

## Arms

| Arm | Rule |
|---|---|
| `E02`, `E03`, `E031`, `E031_L8` | As frozen in `EXAM_E03_FAMILY.md` |
| `E032` | As frozen in `EXAM_E032_ADDENDUM.md` (`en_lab.E032`) |
| `EN04_put2.5x`, `EN04_put3x`, `EN04_put3.5x` | E03.2 with put tickets at 2.5, 3 and 3.5 times the call's Rs 1,250 |

Random control: 40 seeded random-entry books of E03.1, with the same signal count per day, the same
window and the same exits.

## Tests, once

Tests 1–6 are the family exam's and the addendum's, unchanged: E03.1 stands; E03.1 against E03; the 8%
limit; E03.2 against E03.1; and the put-over-call asymmetry. Two are added:

7. **`E032` stands.** All of these must hold:
   - net above zero at ordinary AND adverse fills;
   - net without the best day above zero;
   - no day worse than −Rs 2,500.

   If it fails, E03.2's edge is not confirmed on fresh data. It stays a paper strategy with no size
   increase.
8. **Puts at 3x.** They are adopted for paper only if all of these hold:
   - net at ordinary AND adverse ≥ E03.2's;
   - net without the best day ≥ E03.2's;
   - the 2023 book passes `RISK_PLAN.md`'s frozen limits:
     - skeptical losing-year chance ≤ 30%;
     - 95th-percentile drawdown ≤ Rs 5,000;
     - severe net ≥ −Rs 6,250;
   - both neighbours, 2.5x and 3.5x, are positive at ordinary and adverse.

   EN04 failed its stricter in-sample neighbour rule, so a pass here is the only route to 3x before the
   forward count.

Reported regardless:
- every ticket by side with its exit, and the unavailable counts;
- the EN03 lesson on fresh data: tickets added by a 0.65 put gate against E03.2's own put tickets, each
  ticket on a fresh day book.

A pass is one more modelled history, not a qualification for real money. Promotion still needs the
forward count of at least 20 new closed paper tickets.
