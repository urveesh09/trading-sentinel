# SN231–SN250: Gold v6's bad months, and a Gold v7 that makes more months positive (Nov 15, 2026)

Frozen before any number of SN231–SN250 is computed. Research only, in Dev. No order, no runtime change in these studies; Production unchanged.

## The owner's ask (Nov 15)

"Gold v5 + wk-h is the new gold v6 … this will be our baseline … I will give you more slots till SN 250 … comprehensively analyse the bad months. Understand why it happened … add on one more … something else that can help us make every single month positive … since I have promised to refill every single penny that the system loses any day … if we have bad month … I will have to pay out the whole month … the good part of the strategy is maintained and the bad month is countered by something else … give me a Gold V7 if possible."

## Gold v6, the baseline (exactly as it runs in Dev)

- **SN Gold v5:** ₹30k growing (production), its day nets from SN161 `p4.gold("Rs 30k growing (production)")`, every day Jan 2 2023 – Oct 28 2026 (development and TEST).
- **WK-H:** `wk3.book3(sample, "STRADDLE", "M", "settle", "H15x2")`, 2 option lots (one ₹5 lakh unit). Daily marks come from `t["marks"]`, as in SN229.

**The account window:** Jan 2023 – Oct 2026, 46 months; the only window where Gold v5 can be replayed.

**WK-type legs alone** can also be read on five samples:
- DEV (Apr 2022 – Aug 2026);
- TEST;
- NIFTY Dec 2021 – Mar 2022;
- SENSEX Oct 2024 – Apr 2026;
- NIFTY Oct 2020 – Nov 2021 (seen since SN228).

**The owner's money rule:** every losing day is refilled.
- A month's **net** = what the winning days banked − what the losing days cost.
- A **bad month** is a month with net < 0.

## Data honesty

**Every sample on the PC is now seen.** The only unseen history is NIFTY Jan–Sep 2020, the COVID crash, which is still downloading (Jul–Sep 2020 options 318 of 857 on Nov 15).
- So Gold v7 is chosen on seen data by the rule below.
- Its first fair test is **pre-registered**: WK-type legs scored once on NIFTY Jan–Sep 2020 after the download, plus the forward paper record. Gold v5 cannot be replayed on 2020: its N11 parent book has no 2020 replay.

## Studies

| SN | Study |
|---|---|
| 231 | Gold v6's daily and monthly ledger (both legs); the list of bad months; the owner's refill cash flow per month |
| 232 | **Bad-month anatomy.** Per month, Gold's net, trades and wins, and WK-H's weeks, net, worst week and hedge cost. Per month, the market: realised volatility, implied premium (WK-H's Q ÷ index), implied ÷ realised, range, trend efficiency, gaps, trend days. Bad vs good months compared |
| 233 | WK-H's losing weeks on all five samples: gap, realised vs implied, expiry afternoon after the 14:30 freeze, hedge orders and their cost, weekday. Gold's losing months: trades, streaks, the kind of month |
| 234 | Diagnosis written down. **Amendment allowed here, before any SN235+ number:** new candidates suggested by SN231–SN233 may be added to the list below |
| 235 | **WK-H on expiry afternoon:** keep re-hedging until 15:15 on expiry day; or flatten the hedge at 14:30 |
| 236 | **A second hedged weekly structure:** WK-H + the best hedged WK-S (STRANGLE 0.5 k3 stop 1 H15x2); WK-H + the SN227 plateau members as separate units |
| 237 | **The daily hedged straddle (new engine path):** sell the ATM straddle at every 15:15 that is not followed by a weekend or holiday; hedge as WK-H; close at the next 15:15 (settle if the next session is expiry) |
| 238 | **SENSEX WK-H** as a second instrument (a different expiry day), on its months |
| 239 | **Cost-aware weeks:** skip WK-H when the straddle premium is below a frozen multiple of the week's expected hedge cost; random-skip null |
| 240 | **Leg mix:** WK-H units 1 / 2 / 3 against Gold's wallet, for monthly positivity and the worst month |
| 241 | **Month protection (profit, not loss):** once the month-to-date reaches X, the rest of the month runs smaller (WK-H 1 lot / Gold minimum). No rule reacts to a loss (the owner rejects loss-reaction blocks) |
| 242 | **Idle capital:** the ₹5.3 lakh wallet as pledged liquid-fund collateral (an assumed 5% a year after haircut), shown separately, never mixed into a strategy's result |
| 243 | Candidates from the SN234 amendment, if any |
| 244 | Combinations of what passed SN235–SN243 |
| 245 | **Gold v7 selection (frozen rule below)** |
| 246 | Robustness of the pick: costs ₹200 / ₹300 per leg-lot, futures half-spread 1.5 points, leave one year out, month bootstrap |
| 247 | Wallet table for Gold v7 (₹5.3 lakh / ₹10 lakh / ₹15 lakh) and the owner's refill cash flow |
| 248 | The pre-registered 2020 crash test (WK-type legs), frozen and written down; run only once the data is complete |
| 249 | If Gold v7 beats Gold v6 by the rule: its runtime design (Dev, on the owner's word) |
| 250 | Synthesis, docs |

## Gold v7's selection rule (frozen)

A candidate is Gold v6 plus or with changes from SN235–SN244. It qualifies only if all of these hold:
- **Q1:** its **months positive** in the account window are more than Gold v6's;
- **Q2:** its total net is ≥ 90% of Gold v6's;
- **Q3:** its worst month is no worse than Gold v6's;
- **Q4:** every WK-type leg it adds or changes is positive on ≥ 4 of the 5 WK samples, and its own months positive on those samples are no fewer than WK-H's;
- **Q5:** a rule with a threshold (SN239, SN241) beats its random or nearest-neighbour null.

**The pick and the fallback:**
- **Gold v7** = the qualifying candidate with the most positive months; ties go to the better worst month, then the larger total.
- **If none qualifies:** Gold v6 stays the baseline, and the result says so.

## Integrity

- Each `snNNN.py` refuses to rerun once its result file exists.
- Crashes are logged in `logs/` (git-ignored) and disclosed; post-freeze fixes are disclosed.
- No partner data, no Breeze call. The download database is not touched.
- The 2020 data stays sealed.
