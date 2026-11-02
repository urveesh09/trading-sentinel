# N11T: when may a trade plan to lose up to Rs 7,500? Plan, written before the frozen run

November 2, 2026. Research only, in Dev. Not deployed. The owner: "under certain specific circumstances I allow a 50% tolerance ... I will allow you to decide to ensure our profit is increased."

## Where this plan came from

Five development screens (`screen` to `screen5`, 74 books, all kept) on the four seen years, read before this was written. So this freeze is discipline, not an exam.

- **Screen 1: a bigger budget on the 25% rule.** Lower than N11 everywhere: the rule still blocks every option above Rs 230.
- **Screen 2: charge a lot by its own stop.** Better, up to about Rs 2.70 lakh, with a cliff below k = 1.5.
- **Screen 3: the map.** Bumpy, for a reason in my test: the cap also lowered what the proven stance already allows.
- **Screen 4: raise only.** A clean plateau, but the bigger budget also admitted new one-lot trades on options up to Rs 420, which made the -7,026 day.
- **Screen 5: a second lot only.** Every setting from k = 1.5 and a cap of Rs 6,250 up beats N11, and no year gets worse.

## The rule

N11, unchanged, plus one thing. **A trade N11 already takes at one lot may take a second lot**, when all of these hold, each known at entry:

1. Yesterday's volatility is at or above its usual level (N11's two-lot reading).
2. The last 20 closed paper trades, exits strictly before now, made money (the stand-aside's own reading, on its good side).
3. No realised loss today (N11's one-lot-after-a-loss rule still applies).
4. The trade's own stop, valued at 1.75 x delta x its distance, fits inside the second lot's budget, so the strategy's stop acts first.
5. Planned loss for both lots, fees and declared stress included, is at most Rs 7,500, scaled down in a drawdown and never up. The premium backstop tightens to keep that true. The underlying stop, target, trail and clocks don't change.
6. N11's own limits stay: two lots at entry, the 15% open-premium cap, the morning clock for the low-day pullback.

It admits no new trade, never lowers a trade's limit, and takes no third lot at entry. The earned lot's own Rs 5,000 charge doesn't change: giving it this room earned less in screen 1.

**Rs 7,500 is the owner's number, not read off the map.** k = 1.75 is the middle of the 1.5 to 2.0 range that holds, chosen away from the cliff at 1.25. It isn't the best point on the map.

## Checks, fixed before the frozen run

**A. Is it better, and inside the bar?** All must hold:

1. Four-year sum above N11's 2,55,365.
2. Worst day no larger than 6,127, the bar set for N11.
3. Biggest yearly fall no larger than N11's 6.89%.
4. Worst trade no larger than 7,500.
5. Every year at or above N11's, within Rs 500.

**B. Is it sturdy?** All must hold:

6. Double cost above N11's 1,99,622.
7. Without its own top five above N11's 1,25,490.
8. Plateau: k 1.5 and 2.0, cap 6,250 and 7,000: each above 2,55,365, worst day no larger than 6,127.
9. One account at extra cost 195, 198, 199, 200, 201, 202, 205 (per-lot term 5), 180, 220 and 400: each at or above N11 at the same cost, within 5% of each other from 195 to 205, never near the stop.
10. The audit: on every raised trade, volatility at or above usual, the paper record positive, no realised loss earlier today, planned loss at most 7,500, and the backstop where the rule puts it.

**C. Honest about overfitting.** Reported whatever they say:

11. Placebo: the same number of second lots given at random among one-lot trades on above-usual days. Check: chance of beating the real choice at or below 0.10.
12. Hide each year in turn: would the rule be chosen on the other three, and what does it do on the hidden year?
13. Without the paper reading, and with the reading reversed (second lots only on a losing record).
14. Top three raised trades' share of the gain.
15. The overfitting estimate over this study's books and N11's family.

**Verdict words.** A and B all true: "meets the bar on the seen years". That isn't "proven". Anything false is reported as failed, by name, and the book isn't rescued by changing a check.

## Files and contracts

Only `docs/research/simulation/2026-11-02-fno-n11-tolerance/`, its report, and the ritual sections. No application change: this isn't deployed unless the owner says so.

**If the owner approves it,** the engine change is small: `fno_n11` gains the condition and the stop-based charge, behind a setting, off by default.

**Rollout and rollback.** None now. Real money isn't touched: it stays one lot, with its own limits.
