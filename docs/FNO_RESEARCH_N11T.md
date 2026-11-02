# N11T: a second lot inside a Rs 6,250 limit

**November 2, 2026. Deployed on paper that night on the owner's order, with a fresh Rs 2,50,000 for the paper book.** The real-money test isn't affected either way.

**The owner allowed a tolerance on the Rs 5,000 per-trade plan, and left the conditions and the amount to me. I chose Rs 6,250, not the Rs 7,500 I first tested.** It adds Rs 19,380 to N11 over four years. Its worst day and worst trade on these years are no larger than N11's, and it plans to lose Rs 1,250 less per raised trade than the Rs 7,500 version, which earned less.

All four years were studied before and during its design, so none of this is proven. Technical record: [research/simulation/2026-11-02-fno-n11-tolerance/](research/simulation/2026-11-02-fno-n11-tolerance/). The final plan, written before its run: [PLAN_FINAL.md](research/simulation/2026-11-02-fno-n11-tolerance/PLAN_FINAL.md).

## 1. The rule

A NIFTY paper trade that N11 already takes at one lot may take a second lot, when **all** of these hold, each known at entry:

1. **N11 allows two lots on this trade:** yesterday's volatility at or above usual, no realised loss today, and the low-day morning clock.
2. **The last 20 paper trades made money.**
3. **It fits, one of two ways:** two lots at the normal 25% backstop fit the budget, or the trade's own stop, valued at 1.75 x delta x its distance, fits the premium points the limit allows.
4. **The 15% open-premium cap and the structural cap still pass** at two lots.

The whole trade then stays inside **Rs 6,250, fees and assumed cost included.** The premium backstop tightens to keep that true, and is never lower than the normal 25%. In a drawdown the limit shrinks with the stance. A winning streak never lifts it.

It lets in no new trade, and never takes a third lot at entry. The earned lot keeps its Rs 5,000 charge. A planned loss isn't a promise: stops can gap.

## 2. The result

Fresh Rs 2.5 lakh each year:

| | N11 | First test: Rs 7,500 | **Final: Rs 6,250** |
|---|---:|---:|---:|
| 2023 | -11,537 | -11,537 | -11,537 |
| 2024 | +93,256 | +95,040 | +95,040 |
| 2025 | +53,095 | +64,608 | +63,479 |
| 2026 (to Oct 28) | +1,20,551 | +1,24,011 | +1,27,763 |
| **Four years** | **+2,55,365** | **+2,72,123** | **+2,74,745** |
| Worst day | -5,641 | -5,863 | -5,641 |
| Worst trade | -4,559 | -5,863 | -4,559 |
| Biggest fall in a year | 6.89% | 6.89% | 6.89% |
| At double the assumed cost | +1,99,622 | +2,11,623 | +2,09,513 |
| Without its top five winners | +1,25,490 | +1,41,374 | +1,43,996 |
| One account from Jan 2023 | Rs 5,18,305 | Rs 5,22,297 | Rs 5,22,297 |

All 11 checks fixed in advance pass. The one-account figure is the same for both amounts because both take identical trades there: a larger account already has room for them.

## 3. Why Rs 6,250

The map, four-year totals, before the plan-wording fix (Rs 6,250's own total didn't change under it):

| Limit | k 1.5 | k 1.75 | k 2.0 |
|---|---:|---:|---:|
| 5,500 | 2,69,503 | 2,57,663 | 2,53,749 |
| 6,250 | 2,68,749 | **2,74,745** | 2,63,741 |
| 7,000 | 2,71,674 | 2,74,853 | 2,78,787 |
| 7,500 | 2,69,709 | 2,72,123 | 2,75,036 |

- **The limit is the one hard fact about risk here.** Which trades fall inside a cell is hindsight. A smaller limit plans to lose less on every raised trade, whatever the market does.
- **It gives up nothing for that.** Rs 6,250 earns the same as Rs 7,000 and more than Rs 7,500.
- **It isn't a number off the map.** It is the book's existing rupee limit, and was a neighbour fixed in the first freeze.

**Why not the highest cell,** Rs 7,000 at k 2.0: it plans Rs 750 more per trade, for a Rs 4,042 lead that comes from which of about 15 trades qualify, at the edge of the tested range. That is choosing the peak.

## 4. How far to trust it

**In its favour.**
- **It only adds.** It never fires in 2023, so it can't make that year worse.
- **Hide any year and it would still have been chosen,** and it earned in each hidden year where it fired: +1,784, +9,710, +10,734.
- **The paper reading matters.** Without it: 2,67,022, with a fall of 8.84%. Reversed: 2,49,812, below N11.
- **The neighbours hold.** k 1.5 earns 2,68,749, k 2.0 earns 2,63,741, a limit of 5,500 earns 2,57,663, and a limit of 7,000 earns 2,74,853. All are above N11, with the worst day inside the bar.

**Against it.**
- **The matching worst day is partly luck.** This amount happens to leave out losing second lots of -2,062, -2,913 and -1,021, and also a +6,105 winner. I chose it after seeing that.
- **The random test passes only in a way I can't count.** Giving the same 11 second lots at random beats it 9.7% of the time, against my 10% limit. The Rs 7,500 version failed at 23.8%. The difference is those few trades, chosen knowing how they turned out, so this pass isn't evidence that the conditions pick well.
- **Few trades carry it.** Eleven trades got a second lot. The top three earned +18,633 of the +22,228, and the other eight +3,595. Six of the 11 fall in January 2025.
- **The result moves with the settings.** k 2.0 keeps only +8,376 of the gain, and a limit of 5,500 only +2,298. At Rs 7,500 a stop factor of 1.25 falls below N11.
- **Overfitting estimate:** 0.615 on this study's 55 books. Pure chance averages about 0.53, give or take 0.18, so history can't choose among these variants.

**So: a modest, plausible gain, not a proven one.** The downside looks small on these years: the worst second lot lost 2,060, and the worst raised trade lost 4,157 in all.

Of the 11, **nine are the tolerance's own second lots** (+21,267). **Two came from the existing stance:** earlier gains made the book "proven" sooner, and those trades took two lots under its existing rule, with their normal 25% stop, which can plan past Rs 6,250. The tolerance's knock-on on later trades is +674 in 2025 and -3,522 in 2026.

## 5. In the engine

Behind `FNO_N11_TOLERANCE_ENABLED`, on by default, as the owner asked for it on paper. Deployed the night of Nov 2.

- **Same decisions as the tested book.** `parity_final.py` asks the engine's own `fno_n11.second_lot` the same question at every planned entry: 696 decisions over four years and all nine backstops, zero mismatches. The replay's yearly results equal the frozen panel's to the paisa.
- **Paper and NIFTY only.** The real-money test reads only the contract from the paper entry, buys one lot and sets its own 25% stop. SENSEX was never tested, so it stays at N11's size.
- **One indirect effect on real money, if it is turned on:** a second lot uses paper's open-premium room, so a later paper entry can be refused that day, and the real test wouldn't mirror it.
- **A second lot never costs the trade its first.** If the shared reservation refuses two lots, the entry asks again for one.
- **Evidence for the forward test.** Each second lot is recorded in `fno_n11_second_lot`, and the evening report says how many there were, about what they made, and about what plain N11 would have made.
- **What the replay can't show:** the live path hasn't met a real signal. Unit tests drive it through the real entry path on a temporary database.

**Off:** `FNO_N11_TOLERANCE_ENABLED=false` and an engine restart. It adds one table and no other migration.

## 6. Production today can't use this

Read on Nov 2, about 14:15 IST:

- **The paper book is far below where research starts.** Both paper books' closes total -33,844 since July, nearly all before N11. Equity is about Rs 2,16,156, 13.54% below its peak, so the stance is 0.25x. Research starts each year from a fresh Rs 2.5 lakh at full size.
- **At 0.25x this rule can hardly fire.** The limit becomes Rs 1,562.50. A second lot then needs an option at or under about Rs 48, or a stop within about 9 points at delta 0.5. N11's own two lots and its earned lot are just as rare.
- **The floor is close.** Equity is about Rs 3,656 above the 15% floor of Rs 2,12,500. Under it, paper entries stop and paper can't trade back. The real-money test only buys what paper just bought, so it would stop too.
- **N11's first live day:** three signals, each at one lot because of the stance, all stopped, -4,298 before the assumed extra cost, two-strike halt at 12:32, no errors. None qualified for a second lot at 0.25x. At full size the first (Rs 161.90) would have, adding about -2,474 for a loss of about 4,995 on that trade.

**The owner ordered the fresh start the same night.** `FNO_PAPER_BOOK_START` (`python-engine/fno_book_start.py`) starts the book's money, peak, stance and brakes at Rs 2,50,000 from Nov 3, with every old trade kept. So the figures above describe the book before it.

## 7. What the first study taught me

Four versions failed before the first Rs 7,500 book, and each changed the design:

1. **A bigger budget on the 25% rule earned less than N11.** It still blocked every option above Rs 230.
2. **Charging a lot by its own stop helped,** but left a cliff below 1.5.
3. **My first cap lowered what the system already allows** when proven. That was a fault in my test, not a finding.
4. **A bigger budget also let in new one-lot trades on options up to Rs 420,** which made a -7,026 day. The fix was to let the tolerance add only a second lot.

**Something you should know about the limit:** the Rs 5,000 isn't a hard cap today. The live rules already allow up to Rs 7,500 on the 25% measure when the book is proven and near its peak. N11 has 23 such entries. So this tolerance extends something that exists, to a second set of conditions.

## 8. Errors disclosed

- **My first plan's code didn't match its words, in two ways.** The words said fees and assumed cost count inside the limit, but on 5 of 16 raised trades the code let them sit on top. A separate book followed the words, with the same result to the rupee. The words also said every second lot needs the stop check, but the tested code only asks it when two lots at 25% don't already fit. The final plan and the engine say what was tested, with fees inside.
- **The final audit first counted the two stance trades as the tolerance's.** They reached two lots by the existing rule, with a 25% stop. It now separates them, using the parity run's record of which trades the tolerance raised.
- **The first study's screens are kept** and counted: 74 books, plus 9 in its frozen panel and 9 in the final one.

The first study's Rs 7,500 figures are in `results.json` and the final's in `results-final.json`. Its files weren't edited.
