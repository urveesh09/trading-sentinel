# EN01–EN05: what improved E03.2 and what did not

November 17, 2026.
- **Two fixes make the paper book honest and make live E03.2 trade the window it was tested on.**
- **The three strategy ideas all failed their frozen tests**, so the E03.2 rule stays exactly as it is.
- All of this is Dev only; nothing is deployed. Paper only, no real orders.

## Why E03.2 has not traded yet

In four live sessions (Nov 5, 9, 12, 17) it opened no ticket:
- Its trend-strength check said no 404 times out of 480.
- That is by design. In 2024–2025 it traded on about one expiry in three.
- EN03 below shows that loosening that check loses money.

## The five slots

| Slot | What | Result |
|---|---|---|
| **EN01** | Honest exits (the audit's three items) | **Done in Dev**, 8 tests |
| **EN02** | Start recording at 12:47, so E03.2 can decide from 13:00 | **Done in Dev** |
| EN03 | More put tickets (a looser trend check for puts) | **Failed**: the extra tickets lose |
| EN04 | Bigger puts (2.5x, 3x, 3.5x) | **Failed as frozen**: 3x passed, its neighbours did not; now an exam arm |
| EN05 | Keep part of a winning put after the 8-minute clock | **Failed**: worse in both years |

**EN01, honest exits:**
- A single displayed bid can no longer be sold twice in one quote snapshot.
- Every sale now gets its own message.
- A ticket that cannot be sold before the close is valued at settlement: intrinsic value from our
  sampled index, or its worst case if there is none. It is marked "assumed, not a fill" and you get a
  message. It no longer blocks the next expiry.
- From December 7, no paper sale is booked after the expiring contracts' 15:30 close. The old A/B/C
  book's 15:38 sale moves to 15:28.

**EN02, 13:00 start:**
- E03.2 needs twelve one-minute bars. Recording began at 12:59, so it could not decide before about 13:11.
- In testing, 2 of its 39 tickets came in 13:00–13:10 (+Rs 1,715).

## The numbers

NIFTY 2024 + 2025, one Rs 25,000 book. In-sample, because E03.2 was built on these years.

| | E03.2 | Puts 2.5x | **Puts 3x** | Puts 3.5x | Looser put check (0.65) | Put runner (1.2) |
|---|---:|---:|---:|---:|---:|---:|
| Normal fills | +21,518 | +23,846 | **+34,165** | +39,240 | +10,367 | +18,351 |
| Worse fills | +20,001 | +22,102 | **+31,341** | +34,933 | +7,367 | +17,166 |
| Very bad fills | −2,438 | −3,343 | **−3,277** | −4,232 | −4,070 | −3,046 |
| Worst day | −647 | −1,247 | **−1,247** | −1,847 | −1,117 | −647 |
| 2025 alone | +5,937 | +7,853 | **+9,363** | +9,575 | −4,026 | +3,719 |

**What we learned:**
- **The trend check is load-bearing.** Put signals just below its threshold lost money in both years.
  At 0.60, the extra put tickets were 16 in 2024 (4 winners) and 14 in 2025 (3 winners). The edge exists
  only in the strongest moves. Loosening the check to get more trades is the wrong way to make E03.2
  busier.
- **More money on puts is the only lever that kept working.**
  - 3x puts passed every test, including the risk limits frozen on Nov 3.
  - The rule written for this round also required 2.5x and 3.5x to pass. 2.5x fell short of E03.2 without
    its best day (lot rounding), and 3.5x lost more on very bad fills.
  - So 3x is not adopted. It goes to the 2023 exam as an arm.
- **The 8-minute sale is right for puts too.** Keeping a runner after it gave money back in both years.

## What would settle it: NIFTY 2023

The history database already holds NIFTY 2023's full expiry chains, 48 expiries. They are kept sealed as
the one fresh test for this strategy family.
- The exam is written and frozen in advance (`EXAM_E03_FAMILY.md`, `EXAM_E032_ADDENDUM.md`,
  `EXAM_EN_ADDENDUM.md`).
- It tests whether E03.2 earns on a year it has never seen, whether puts still beat calls, and whether 3x
  puts are safe.
- It runs once, only on your word.

## Data that would help next

All of it through the download skill.
1. **NIFTY 2026 expiry afternoons.** This year's market, including the closing-auction months.
2. **SENSEX expiry afternoons, Oct 2024 – Nov 2026.** E03.2 has never been tested on SENSEX history.
3. **NIFTY 2020–2022 expiry afternoons.**

Our database has the index and futures for these days. It has no options on the expiry afternoon
itself, and that is what E03.2 buys.

Technical record: [research/simulation/2026-11-17-expiry-en/README.md](research/simulation/2026-11-17-expiry-en/README.md).
