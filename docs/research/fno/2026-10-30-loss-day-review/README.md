# Why the F&O book loses, and what is worth researching next

October 30, 2026. **The losses have recurring characteristics. The most useful next research is better entry location and a confirmed response to failed breakouts.** A different strategy for every named type of day has already failed cross-year testing.

This report describes the **existing historical replays**, not actual money lost in Production. It uses 248 NIFTY sessions in 2025 and 203 in January-October 2026. The frozen live-policy book traded on 100 of those 451 sessions and lost on 57 of the active sessions. No new strategy was backtested or implemented here. No Production setting, order authority or real-money switch changed. The frozen 2024 exam was not touched.

**Evidence remains provisional:** 56 negative-volume candles occur in the sealed 2025 input. The original evidence is retained. We also show a sensitivity excluding all affected sessions and short index-data sessions; this is a diagnostic, not a corrected dataset.

## 1. What the losing days have in common

The comparison is with winning sessions of the same book, not merely a list of bad dates.

| Observed condition | 2025 | 2026 | When can we know it? |
|---|---|---|---|
| The day's range ends below 75% of the prior 20-session average range | 10 losses / 13 active days (77%); other days 23/41 (56%) | 10/13 (77%); other days 14/33 (42%) | Only after the day. A full-day description, never an advance trading signal. |
| Lots of back-and-forth movement with little net progress: front-future absolute first-to-last minute close move / sum of minute-to-minute absolute moves below 5% | 19 losses / 26 active days (73%); other days 14/28 (50%) | 16/23 (70%); other days 8/23 (35%) | Only after the day. It suggests what an intraday state detector should study, not a usable day label. |
| Yesterday had an above-usual range, using the old study's trailing-median side | 16 losses / 20 active days (80%); below usual 8/18 (44%) | 13/21 (62%); below usual 9/22 (41%) | Known before entry. A clue, with missing-feature days and small groups. |
| The entry is far from the current VWAP: last completed five-minute close is at least half the first 30-minute range from the futures-bar VWAP proxy | 40 losses / 63 trades (63%); nearer entries 40/75 (53%) | 33/55 (60%); nearer entries 26/51 (51%) | Known at entry using completed five-minute bars. An entry-location hypothesis. |

The last two associations hold in the same loss-rate direction in all four half-year slices. Some slices are small: for the prior-day-range comparison, one half has only six above-usual active days. These are exploratory associations, not statistically established predictors or calibrated probabilities.

In plain language: **a strong trend on yesterday's chart does not guarantee a useful move today. Buying after price has already travelled far can leave us paying for a move with too little left.** A large move yesterday can also precede a difficult next session. The data supports studying these mechanisms; it does not prove those explanations caused every loss.

### Checks against misleading explanations

- **Not every losing session was quiet.** There were losses on wide-range and apparently trending days too. Full-day endpoint-to-range labels were not consistently informative across both years.
- **Counting VWAP crosses before entry was not a useful warning by itself.** The 2+ cross group did not have a higher loss rate in either year. A simple 'crossed VWAP often, stop trading' rule is unsupported here.
- **Direction and clock-time effects changed between years.** Calls were negative in 2025 and positive in 2026. Day-before-expiry trades flipped from negative to positive. The 11:00/12:00 groups also changed sign. None supplies an automatic permanent veto.
- **Higher loss rate is not the same as negative expected return.** Extended 2026 entries still had positive total net. A replacement must account for large winners it misses, not just the losses it avoids.

### Sensitivity to known bad data

Excluding the five flagged 2025 dates and one short 2026 session leaves the main patterns in the same direction:

- Small-range active sessions: 10/12 losses in 2025 and 9/12 in 2026.
- Low-net-progress sessions: 19/26 and 15/22 losses respectively.
- Extended entry loss rates remain above nearer entries: 40/62 versus 40/74 in 2025; 31/53 versus 26/51 in 2026.

The live-policy 2025 total changes from about +271 to -2,958 in that sensitivity, because one removed active day was a winner. This illustrates fragility, not a licence to choose which days to keep.

## 2. What happened inside the losing trades

The live-policy paths contain **139 losing trades** across both years.

| Mechanism in the saved exit record | Losing trades |
|---|---:|
| Underlying stop | 70 |
| Time stop | 54 |
| Premium backstop | 11 |
| Hard-flat deadline | 4 |

This points first toward entry quality and failure to get sufficient follow-through. It does not establish that the existing stops are too tight.

- Only **5** losing trades had a positive gross result that turned negative after recorded charges. Charges matter, but recorded fees alone do not explain most losing trades. Spread effects already affect model prices, and true execution remains uncertain.
- In **23 of 139** losing trades, the future was farther in the intended direction at exit than at entry. Getting direction right can still produce a losing option trade. Time, volatility, spreads and small movement are possible contributors; we have not isolated their contributions with a Greek/IV attribution.
- On **48 of 139** losing trades, a later underlying excursion reached half an opening range in the original direction before 15:10. This is hindsight. It is not proof that the option recovered, that a fill was available, or that a wider stop would have made money.

The previous micro-exit study already found that an extra two-close VWAP exit reduced TPB profits. The evidence does not justify tightening every exit, removing stops or holding a losing position until it returns.

## 3. Are there strategies that already win on these bad days?

**Some existing countertrend variants did. The difficulty is selecting them without knowing the day's final result.** We matched identical variants across the two years, using the previously recorded 134-strategy library.

| Existing family | Variants positive on the live-policy losing-date subset in BOTH years | Variants positive on BOTH complete years |
|---|---:|---:|
| Failed opening-range breakout reversal (FADE) | 5 of 16 | 0 of 16 |
| VWAP mean reversion | 5 of 16 | 0 of 16 |
| RSI2 reversal | 1 of 8 | 0 of 8 |
| Previous-day-level fade | 0 of 8 | 0 of 8 |

For the FADE family, the median variant earned roughly +954 on the 2025 losing-date subset and +1,942 on the 2026 subset. On the live-policy winning-date subsets those medians were about -8,486 and -5,826. Those medians are summaries across variants, not one tradable strategy or portfolio.

This is a specific lead: **failed-breakout trading can capture some opposing moves, but always switching it on damages other sessions.** The earlier rule 'ADX low, use a fade' failed on 2025. The next hypothesis should identify an actual intraday failed break and its subsequent response, including on a day whose daily chart looks trending.

These are independent-book results conditioned on a label known after the close. They cannot be added to the original book's profits, and do not reproduce competition for cash, positions or the day's risk limits. 'Take the alternate strategy on the losing days' would be an impossible hindsight rule.

## 4. What the web research suggests

Primary sources, scope, access limits and cautions are recorded in [SOURCES.md](SOURCES.md). There is no published strategy we can safely assume will counter all these days.

### Priority 1: second-chance breakout/retest entry

**Problem addressed:** extended entries and quick reversals after entry.

Research a breakout that first establishes its level, then waits for a retest to hold and a completed candle to turn back in the breakout direction. Enter using a bounded price and a structural stop; expire the pending setup if it does not fill or breaks down. The [SMB range-trading guide](https://www.smbtraining.com/blog/wp-content/uploads/2024/03/Technical-Analysis-Range-Break-Trading-Cheat-Sheet.pdf) describes this second-chance mechanism.

This changes *where and how we enter*. It can improve price and risk placement, but strong moves may never retest. All missed winning trades must count in the comparison. It differs from the failed O30n VWAP-reclaim entry: this hypothesis uses a specific broken horizontal range level and a retest, rather than a touch of VWAP plus a break of the previous bar.

### Priority 2: confirmed failed-breakout reversal

**Problem addressed:** a break runs out of support and price returns to the old range.

Research a sequence: an observed break, a completed close back inside the range, then an attempted retest that fails to regain the outside level. Only then consider trading toward the range center, with a stop beyond the failed attempt. The [same primary practitioner guide](https://www.smbtraining.com/blog/wp-content/uploads/2024/03/Technical-Analysis-Range-Break-Trading-Cheat-Sheet.pdf) describes a failed-range-break setup.

The extra confirmation is a new hypothesis, not a proven repair to our failed FADE variants. Target distance must cover actual option spread, fees and time risk. If price regains the breakout level, the reversal thesis is invalid. Avoid automatic reversal immediately after every stop: that can double losses on an eventually successful trend.

### Priority 3: compression-to-expansion trading

**Problem addressed:** buying directional premium while the market remains confined, or missing a later release from balance.

Study a sequence in which a rolling completed-bar range contracts, then expands with a close outside and directional follow-through. [Schwab's TTM Squeeze documentation](https://toslc.thinkorswim.com/center/reference/Tech-Indicators/studies-library/T-U/TTM-Squeeze.html) gives one established compression representation. It is an indicator definition, not evidence that it profits in NIFTY.

The day can start balanced and develop a trend later. A prior full-day label must not decide its destiny. False releases, option carry while waiting and missed moves must all be charged. Entries stay inside 09:45-14:45, with 15:10 flattening.

### Priority 4: option-payoff-aware expression of a moderate move

**Problem addressed:** the 23 losing trades where underlying direction was favorable by exit, and slow moves that fail to pay for an outright option.

Research the executable value of the expected move against spread, time and volatility exposure. [OIC explains the erosion of short-dated time premium](https://www.optionseducation.org/optionsoverview/leaps-time-erosion-versus-delta-effect). Simply buying cheaper or deeper-in-the-money options was already tested in O30p and did not improve both years.

A separate defined-risk study could compare outright calls/puts with directional debit spreads for moderate moves. [Zerodha's spread lesson](https://zerodha.com/varsity/chapter/bull-call-spread-2/) describes the moderate-direction use case; [HKEX specifies the capped expiry payoff and net-debit loss](https://www.hkex.com.hk/eng/sorc/frontend/strategies_bullcall.htm). Actual intraday exits do not equal expiry payoff. Short legs, order sequence, hedge loss, costs and cash/margin must be modeled. [Zerodha's margin rules](https://support.zerodha.com/category/trading-and-markets/margins/margin-leverage-and-product-and-order-types/articles/hedged-position-margins) make this a separate authority/capital assessment, not a default for the Rs12,500 single-long-option trial.

### Lower priority: range-centered option structures

For genuine low-movement sessions, a defined-risk butterfly can have a different payoff from a directional long option. [OIC's butterfly explanation](https://prd-web.optionseducation.org/strategies/all-strategies/long-call-butterfly) makes clear that the position depends on location around its middle strike. It can lose when price escapes and introduces short legs and multiple execution costs. It needs a separate execution/affordability study and is outside the present single-leg mandate.

Unhedged short straddles, martingale additions, futures leverage and 'sell premium every quiet day' are not suitable substitutes under the owner's present constraints. A long straddle also needs enough movement to repay two premiums; it is not a cure for quiet-session losses. [CME's payoff guide](https://www.cmegroup.com/articles/files/2022/25-proven-strategies.pdf) is useful for comparing those exposures, not proof of profitability.

## 5. The practical design direction

The most useful working model is an **intraday state transition**, with explicit actions:

- Range breaks and retest holds: consider continuation at a better entry location.
- Range break fails and the attempted recovery fails: consider a bounded reversal toward the range.
- Range stays balanced: wait for a supported reversal or a real expansion with sufficient option payoff.
- A position's structural thesis fails: exit according to its explicit policy and risk limit.

This is a research proposal. It should be tested as one shared book rather than adding the best parts of separate backtests. The labels must use only completed observations available at the decision time. The [Bollinger creator's rules](https://www.bollingerbands.com/bollinger-band-rules) are a useful warning that touching an extreme is insufficient to declare a reversal.

## 6. Concrete next research, with boundaries

1. Verify/reacquire the bad volume and use a new sealed dataset version; preserve original studies and reproduce their references. Missing morning windows stay visible.
2. Freeze **two** next candidates: second-chance continuation and confirmed failed-break reversal. One fixed initial setting per mechanism, defined before scoring. Compare with unchanged live-policy, TPB and the existing blend on every eligible session in each year.
3. Score both separately and then together in the actual shared cash/slot/risk book. Report bad-day gains AND damage to good days, missed entries, holding time, unresolved exits, charges, slippage stress, downside and sample sizes. Any chosen parameter remains seen-data development.
4. Require an exact Rs12,500, one-lot cash path; no relaxation of stops, entry/exit deadlines, affordability, expiry or real-order permissions merely to get trades.
5. Validate on new prospective sessions. The existing 2024 exam remains fixed; do not tune these new hypotheses against it or silently append them to its frozen list.

## Evidence and reproduction

- `PLAN.md`: scope and feature definitions written before aggregation.
- `diagnose.py` / `diagnosis.json`: both years, three books, active-day and trade mechanisms, saved feature sides, family overlap and input hashes.
- `crosscheck.py` / `crosschecks.json`: four-half comparisons, quality sensitivity, matched identical variants, completed-bar future-perturbation check and outcome-partition check.
- `configuration.json`: research-only receipt and verified source identity.
- Ignored `_local/details-2025.json` and `details-2026.json`: per-day and per-trade attribution, including missing-feature labels.

Run the existing engine venv: `python-engine/winvenv/Scripts/python.exe diagnose.py`, then `crosscheck.py`, from this folder or with absolute script paths. The scripts read only existing sealed local data and replay records. No scheduler, network or live broker module is started. Original live normalized totals +271 / +80,912 are asserted; daily/trade/session identities reconcile; input database hashes match their manifests. These checks establish reproducibility, not a tradable edge.
