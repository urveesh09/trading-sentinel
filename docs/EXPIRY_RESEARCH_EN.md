# EN01–EN05: what improved E03.2 and what did not

November 17, 2026.
- **Two fixes make the paper book honest and make live E03.2 trade the window it was tested on.**
- **The three strategy ideas all failed their frozen tests**, so the E03.2 rule stays exactly as it is.
- **On NIFTY 2023, the one year it had never seen, E03.2 and its whole family lost money.**
- Paper only, no real orders.

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
| EN04 | Bigger puts (2.5x, 3x, 3.5x) | **Failed as frozen**: 3x passed, its neighbours did not. It also lost on 2023 |
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
  - So 3x was not adopted. It went to the 2023 exam as an arm and lost there too.
- **The 8-minute sale is right for puts too.** Keeping a runner after it gave money back in both years.

## NIFTY 2023: the fresh test, and it failed

You said open it, so it was scored once, exactly as frozen. It covered 49 of 2023's 52 expiries; the
first three January ones were never downloaded.

| | E02 | E03 | E03.1 | **E03.2** | Puts 3x |
|---|---:|---:|---:|---:|---:|
| Normal fills | −2,416 | −3,222 | −3,132 | **−3,645** | −4,215 |
| Worse fills | −2,764 | −3,167 | −3,076 | **−4,036** | −4,319 |
| Tickets (winning days) | 17 (3) | 17 (3) | 17 (3) | **17 (3)** | 14 (4) |

**What this means, plainly:**
- **Every version loses in 2023, in every quarter.** E03.1's signal did worse than 39 of 40 books that
  bought at random minutes.
- **The put advantage did not hold.** E03.2's puts lost Rs 1,982 over 7 tickets and its calls Rs 1,663
  over 10. Bigger puts lose more.
- 2023 is also the year every option-buying strategy in this system lost, including the F&O books on
  Nov 1. That year was calm and grinding, a hard market for option buyers.
- So E03.2's profit is a 2024–2025 result, not a proven edge.

**What changes:**
- E03.2 stays on paper only. No size increase, nothing toward real money.
- Its forward paper tickets (0 of 20 so far) are now the main evidence.
- The fixes (EN01, EN02) still matter: they make that paper record honest and complete.

## The five extra slots (EN06–EN10)

| Slot | What | Result |
|---|---|---|
| **EN06** | Paper sales can no longer reuse the same quote twice, even across restarts. The evening report shows real fills and assumed values apart. Messages can't be lost in a crash. December 7 rules are applied. | **Done in Dev**, shipping in tonight's release |
| **EN07** | Re-checked the 2023 test with the stricter "strikes present at that minute" rule the auditor asked for | Same result to the paisa. The 2023 loss is real. |
| EN08 | Skip calm mornings (the quietest third of days) | Failed. It halves the 2023 loss but ruins 2025, whose calm days were E03.2's best. No "type of day" explains when it earns. |
| EN09 | A different entry: breakout after a quiet spell | Failed. It lost every year, worse than picking the side at random. |
| EN10 | A one-lot ticket banks its gain earlier | Failed. Only 6 tickets in 3 years changed, mixed. |

**Bottom line:**
- E03.2 is unchanged and nothing tested beats it.
- 2024 earned, mostly from one day. 2025 earned a little. 2023 lost.
- The system now records paper results honestly, so each new expiry adds real evidence.
- What can genuinely move this forward is new data (below) and forward paper tickets.

## Data that would help next

All of it through the download skill.
1. **NIFTY 2026 expiry afternoons.** This year's market, including the closing-auction months.
2. **SENSEX expiry afternoons, Oct 2024 – Nov 2026.** E03.2 has never been tested on SENSEX history.
3. **NIFTY 2020–2022 expiry afternoons.**

Our database has the index and futures for these days. It has no options on the expiry afternoon
itself, and that is what E03.2 buys.

Technical record: [research/simulation/2026-11-17-expiry-en/README.md](research/simulation/2026-11-17-expiry-en/README.md).
