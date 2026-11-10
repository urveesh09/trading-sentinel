# N09c results: the card rule FAILED its frozen test (November 9, 2026)

Freeze `c2b3adb5` (`freeze.json`) came before any replay. `analyze_x.py` applied the frozen rule and wrote `results.json`. The raw replays are in `_local/`.

## Verdict

**`card_passes: false`.** Three of the six checks failed:

| Check (per lot, after the replay's costs) | Result | Pass |
| --- | --- | --- |
| net > 0 in each year | 2024 +13,700 · 2025 +2,168 · 2026 **−8,036** | no |
| net > 0 over three years at +₹200 per trade | **−56,568** (322 trades) | no |
| net > 0 without its best day | **−4,841** | no |
| at most 1 red half-year of 6 | 1 (2026 Jun–Oct −8,122) | yes |
| at least 40 trades a year | 120 · 114 · 88 | yes |
| above the median random-entry book each year | random median −31,242 · −29,126 · −29,335 | yes |

**Over the three years:**
- The card made +₹7,832 per lot on 322 trades, about ₹24 a trade.
- Worst day −6,327, largest fall 42,214, months 17 green and 17 red.
- It won 34–40% of trades, with average wins of about ₹2,800 a lot against average losses of about ₹1,650. Break-even for that payoff is a win rate of about 37%, and the card sits right on it.

**Informational, decided in advance.** The card's exits did not beat the book's own exits in every year. On the same signal:

| Year | Card exits | Book exits |
| --- | --- | --- |
| 2024 | +13,700 | −11,381 |
| 2025 | +2,168 | +6,521 |
| 2026 | −8,036 | +7,699 |

Holding after the target with a 1.5 ATR trail made +9,844 over the three years, and −54,556 at +₹200.

**Consistency.** `INFO|live_union_adx` reproduced the O30c case study's `BASE|UNION_ADX` exactly: 2025 +271 and 2026 +80,912 per lot. The replay stack on today's engine files gives the earlier results.

## Reading

- **The forward record was a good month, not an edge.** The 18 forward cards (9 at target, Oct–Nov) came in a strong rise. Over 2.8 years the same rule is about break-even before extra costs and loses once realistic slippage is added. It lost in 2026, and Jun–Oct 2026 was its worst half-year.
- **Beating random entries says little here.** The random books trade more and lose to costs. This is the method's luck yardstick, not evidence of an edge.
- **Found by looking, not a rule.** Under the card's exits, calls made money in all three years (+12,367 · +8,021 · +1,494) and puts lost in two. Under the book's exits it is the other way round: puts earned in 2025 and 2026 and calls lost. The direction effect flips with the exit, so it is path, not edge. It is not used.
- **One trade per SHIPPED book has no exit reason or result.** It was still open at the end of the data and is excluded from the nets.

## What follows (as frozen)

- **The partner is not coached to lean on the card.** The card-led watch (N09c-W) is not built.
- **The card stays as it is.** It is labelled research-only, and its forward record keeps counting in the wrap.
- **No change** to the runtime, settings, orders or deployment.
- **Jan – May 2022 was not read.** It stays the N012 exam.
