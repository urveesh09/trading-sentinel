# N11T: when the Rs 5,000 limit may stretch to Rs 7,500

**November 2, 2026. Research only.** This isn't deployed. N11 itself runs in Production on paper, and the real-money test isn't affected.

**A 50% tolerance raises profit by Rs 16,758 over four years, if it is used for one thing only: a second lot on a trade N11 already takes, when both of its readings are good.** The worst day stays inside the bar and the biggest fall doesn't change. But it rests on few trades, and it fails the test that matters most for a selection rule: a random pick of the same number of second lots beats it 23.8% of the time.

All four years were studied before and during its design, so none of this is proven. Technical record: [research/simulation/2026-11-02-fno-n11-tolerance/](research/simulation/2026-11-02-fno-n11-tolerance/).

## 1. The conditions

A trade may take a second lot, planning to lose up to Rs 7,500, only when **all** of these hold:

1. **N11 already takes this trade at one lot.** The tolerance lets in no new trade.
2. **Yesterday's volatility was at or above its usual level.**
3. **The last 20 paper trades made money.**
4. **No loss has been realised today.**
5. **The trade's own stop fits.** Its distance, valued at 1.75 x delta, has to fit inside the second lot's budget, so the strategy's stop acts first.
6. **The whole trade stays inside Rs 7,500,** fees and assumed cost included. The premium backstop tightens to keep that true. In a drawdown the limit shrinks with the stance. A winning streak never lifts it.

Never a third lot at entry, and the 15% open-premium cap stays. The earned lot keeps its Rs 5,000 charge: giving it this room earned less.

## 2. The result

Fresh Rs 2.5 lakh each year:

| | N11 | N11T |
|---|---:|---:|
| 2023 | -11,537 | -11,537 |
| 2024 | +93,256 | +95,040 |
| 2025 | +53,095 | +64,608 |
| 2026 (to Oct 28) | +1,20,551 | +1,24,011 |
| **Four years** | **+2,55,365** | **+2,72,123** |
| Worst day | -5,641 | -5,863 |
| Worst trade | -4,559 | -5,863 |
| Biggest fall in a year | 6.89% | 6.89% |
| At double the assumed cost | +1,99,622 | +2,11,623 |
| Without its top five winners | +1,25,490 | +1,41,374 |
| One account from Jan 2023 | Rs 5,18,305 | Rs 5,22,297 |

All 10 checks fixed in advance pass. Nearby settings hold: stop factor 1.5 earns 2,69,709 and 2.0 earns 2,75,036; a limit of Rs 6,250 earns 2,74,745 and Rs 7,000 earns 2,74,853. All have the same 6.89% fall and a worst day inside the bar. The account moves 0.43% across rupee-sized cost changes.

## 3. How far to trust it

**In its favour.**
- It only adds. It never fires in 2023, so it can't make that year worse.
- Hide any year and it would still have been chosen, and it earned in every hidden year where it fired.
- The paper reading matters: with it reversed, the same rule earns 2,49,462, below N11. Without it, 2,64,050 with a fall of 8.98%.

**Against it.**
- **The placebo fails.** Giving the same 16 second lots at random among N11's one-lot trades on above-usual days earns a median of +10,184, and beats the real +19,606 23.8% of the time. My limit was 10%. On those days a second lot tends to earn anyway, so my conditions can't be shown to pick better than chance.
- **Three trades supply it all.** They earned +21,772 of the second lots' +19,606. The other 13 lost a net 2,166. Seven of the 16 fall in January 2025.
- **It sits near a cliff.** At a stop factor of 1.25, the book earns 2,46,375, below N11, with a worst trade of -7,710. At 1.75 I'm in the middle of the part that holds, not far from the edge.
- **Overfitting estimate:** 0.619 on this study's 53 books. Pure chance averages about 0.53, give or take 0.18, so history can't choose among these variants.

**So: a modest, plausible gain, not a proven one.** The downside is small on these years. A single trade can now plan to lose Rs 7,500, though no trade lost more than Rs 5,863.

## 4. What this taught me

Four versions failed before this one, and each changed the design:

1. **A bigger budget on the 25% rule earned less than N11.** It still blocked every option above Rs 230.
2. **Charging a lot by its own stop helped,** but left a cliff below 1.5.
3. **My first cap lowered what the system already allows** when proven. That was a fault in my test, not a finding.
4. **A bigger budget also let in new one-lot trades on options up to Rs 420,** which made a -7,026 day. The fix was to let the tolerance add only a second lot.

**Something you should know about the limit:** the Rs 5,000 isn't a hard cap today. The live rules already allow up to Rs 7,500 on the 25% measure when the book is proven and near its peak. N11 has 23 such entries. So this tolerance extends something that exists, to a second set of conditions.

## 5. Errors disclosed

- **My code didn't match my plan on one point.** The plan says fees and assumed cost count inside Rs 7,500. On 5 of the 16 raised trades the frozen code let them sit on top, with planned loss up to Rs 8,010. A separate book follows the plan's wording (`n11t_strict.py`): 15 stops tightened, no exit changed, the same result to the rupee. An engine version must follow the plan.
- **The first four screens are kept** and counted, 74 books in all, plus 9 in the frozen panel.

## 6. What it would take

It needs a small engine change behind a switch, off by default. I haven't made it. Real money stays one lot with its own limits, whatever is decided here.
