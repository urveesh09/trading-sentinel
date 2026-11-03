# E03.2 joins the E03-family exam — written before the exam's data exists

November 3, 2026. Adds one arm and two tests to `../2026-11-03-expiry-e032/EXAM_E03_FAMILY.md`, the
frozen exam on the expiry download the owner approved (`EXAM_YEAR.md` shape). Nothing in that file
changes; its coverage rule (unavailable is never zero) applies to this arm too.

| Arm | Rule |
|---|---|
| `E032` | `candidate.json` here: E03.1 with put tickets at twice the reserve, an 8% buy limit, sold from 15:14 |

Tests, once, ordinary and adverse fills, each year apart and together:

5. **`E032` against `E031`:** E03.2 replaces E03.1 as the lead only if its net is higher at ordinary AND
   adverse fills, its net without the best day is higher, and its worst day is no worse than twice E03.1's.
6. **The asymmetry itself:** E03.1's put tickets earn more per ticket than its call tickets. If they do
   not, E03.2's premise fails on fresh data whatever its total, and the lead stays E03.1.

Reported regardless: every E03.2 ticket by side with its exit, and the severe-fill result.
