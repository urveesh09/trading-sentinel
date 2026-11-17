# SN456–SN475: participant positioning, one pretrained model, filings, Gold's six-lot exits, decision-time capacity, calibration, a duplicate screen, F1's feasibility, the shared-wallet state machine, the power of our own verdicts, and the forecast skill an option buyer needs (Nov 17, 2026)

**Owner (Nov 17):** the auditor's SN456–SN470 handoff (`docs/SN456_SN470_AI_RESEARCH_BRIEF.md`, committed as received in `6f6d9d0f`), starting with SN456, SN464 and SN469, plus five own slots (SN471–SN475).

**How it was run:**
- Acquisition was committed and run before the plan: the participant-OI archive (`be1014a6`) and the sealed futures extract (`9cd1ab32`).
- Plan `83e1b444`, with amendments in its section 5.
- Every scoring script was committed before it ran, and results were written once.

**Status:** research only.
- No runtime, broker, Production or order change. Gold v5 is unchanged.
- The forward verdicts stay unopened, and no recorder session from Nov 17 was read.
- The NIFTY 2023 expiry-day chains (the protected exam) were not queried; ledger10 reads non-expiry sessions only.

**Outside sources used (method, never parameters):**
- NSE's participant-wise OI archive (1,897 daily files, 2019–2026);
- Clark & West (2007) for nested forecasts;
- Kronos-small (pinned code `67b630e6`, checkpoints `901c26c1` / `0e011738`) and the independent index-futures evaluation cited in the handoff;
- freqtrade's future-removal idea (reused from SN452);
- the SEC copy of HDFC Bank's exhibit for the filing fixture.

## Results (in the order run)

| SN | Question | Result |
|---|---|---|
| **464** | Why were 4 of Gold's 10 six-lot exits unpriced? | **None is an observed lack of bids.** At the exit's arrival, at the true held size (up to 11 lots):<br>• 6 FULL;<br>• 2 FEED_STOPPED: Oct 14 (the archive stopped at 10:48 for the day) and Sep 28 (a one-minute gap; full book one minute later);<br>• 2 INSTRUMENT_ABSENT: Oct 8 and Oct 21 at 15:10. Gold's winning puts were 6–7 strikes ITM, outside the archive's 11-strike window.<br>0 ZERO_BID, 0 PARTIAL.<br>**Within 5 minutes,** 7 resolve, at +₹89 a held lot over the model.<br>**Two corrections to SN445:**<br>• 4 of the 10 trades held more than their initial lots (SN445 walked the initial lots);<br>• the 15:10 exits are 3 of 10, and only 2 of them are unpriced (not "3 of the 4").<br>The two missing books are Gold's biggest winners (+₹57.9k, +₹71.7k), so their real cost needs the recorder's wider strike window |
| **469** | Can our scorer detect an edge of the size we need? | **The scorer is honest; the designs are underpowered.**<br>• It recovers what a rule actually earns. The ₹3,000 stop takes about 15% of a gradual edge (−₹15 to −21 a session at one clock, −₹60 at three).<br>• At a wage-level edge (about ₹134–157 a market session) the 90% CI clears zero in **10% of 60-session tests** and **32% at 500 sessions** (trading every session); **24% / 84%** when trading 30% of sessions with a larger edge per trade.<br>• SN449's CI-above-₹154 rule almost never passes at that edge (≤ 5%).<br>• **fw7a's point rule passes a zero-edge book 17–25% of the time** at 20–60 sessions.<br>• Stale quotes and a few large winners change little.<br>**Design check: FAIL** at every horizon except 30% coverage at 500 sessions |
| **472** (own) | How much can each scheduled forward verdict tell us? | **Very little, except fx5.**<br>**fw9a (the cheap opener):** PASS 19.8% at zero edge, 36.9% at its development claim (~₹109 a session), 45.3% at ₹154, 15.7% at the SN455-shrunk claim. These are upper bounds (no ATM control).<br>**SN300a:** INSUFFICIENT about 59%, PASS 4–8% at any edge.<br>**F1:** PASS 3.5% at zero, 6.5% at ₹154 a trade (the without-best-5 test dominates).<br>**fx5:** PASS 11.2% / 34.5% / 93.1% at 0 / 50 / 154 a decision. Its paired design is the only informative one |
| **456** | Does prior-session FII positioning add to a 10:00 → 11:00 NIFTY forecast? | **CLOSED.** 1,758 matched dates (2019–26), 1,508 out of sample in 13 anchored blocks.<br>• Clark–West −1.34 (p 0.62; 90% CI −9.2 to +6.0); permutation p 0.82.<br>• 7 of 13 blocks positive; −3.0 outside the roll window.<br>• MSPE 668.6 base against 679.8 with positioning (worse); hit 50.0% against 49.3%; partial correlation −0.012.<br>• The extra lag, alpha 1 / 100, and dropping month-ends and contract-mix breaks change nothing.<br>**Option stage not run.**<br>Data: 1,896 valid reports; for day t, the prior report was on time 1,806 times, late 25, re-uploaded (ASSUMED) 42 |
| **473** (own) | Where does the positioning information go? | **Nowhere visible.** z's correlation with:<br>• the overnight gap −0.030;<br>• open → 10:00 +0.002;<br>• 10:00 → 11:00 +0.031;<br>• 11:00 → 15:15 +0.013.<br>Every 90% CI spans 0.<br>**The popular contrarian "FII long ratio" rule is wrong-signed:**<br>• after a top-decile ratio the market rose the next day 65% of the time (contrarian SHORT hit 34.6%);<br>• 5-session contrarian −30.6 bp (CI −58 to −7) on 618 overlapping windows, half of them in 2025–26.<br>"Follow the extremes" is a hypothesis only, not an intraday option trade |
| **471** (own) | Does positioning separate Gold's good trades from bad? | **Fails its frozen rule (opposite signs).**<br>**2023–26:** agreeing trades +₹8,350 against +₹2,225 (+₹6,125; CI +810 to +11,589). Pooled +₹5,087, beyond the shift placebo (3%).<br>**2022:** −₹1,181 (30 trades).<br>**Post-hoc, disclosed:** without the 5 largest trades both periods are positive (2022 +₹650, 2023–26 +₹3,147).<br>**A hypothesis for a frozen forward diagnostic only; Gold unchanged** |
| **475** (own) | What forecast skill does a ₹30k option buyer need? | **On the 10:00 one-hour 1-ITM trade** (703 two-sided dates 2023–26; coin −₹316 / −₹510 a decision):<br>• **break-even needs a correlation of 0.215** with the next hour's move (0.364 at ₹400) trading every day;<br>• **0.104 / 0.164** on the top 30% of forecasts;<br>• **₹154 a market session needs 0.37 / 0.31** (≈ 0.80 at ₹400).<br>SN456's realised out-of-sample correlations here are 0.091 / 0.114; SN193's LSTM was near its base rate |
| **462** | Does forecast confidence map to cash? | **No.**<br>• Hit by |score| quintile: 57 / 47 / 48 / 42 / 59% with positioning.<br>• The 30% coverage point makes +₹67 / −₹111 a decision, i.e. **₹10.5 a market session at ₹205** (147 trades); price-only +₹31 / −₹135.<br>• A dumb days-to-expiry / spread ranking: −₹222 / −₹35.<br>• The most confident fifth is priced only 82–84% of the time (dear options).<br>• The 80% conformal interval covers 82% / 73% / 71% from low to high volatility |
| **458** | Kronos-small zero-shot against simple baselines | **STOP: no forecast value.** 551 dates after Kronos's June 2024 training boundary (Jul 2024 – Oct 2026), 8 seeded draws each, 10:00 → 10:30 future return.<br>• **MAE 37.8 bp against 13.2 for no change and 13.3 for a ridge** (Kronos − no change +24.6 bp, 90% CI +21.1 to +28.2).<br>• Correlation −0.064, sign hit 48.2%.<br>• Big-move event (|move| ≥ 13 points, base rate 70%): Brier 0.270 against 0.215 for a causal volatility baseline.<br>It forecasts large moves that do not come, which agrees with the independent index-futures evaluation. No architecture grid |
| **461** | How much of the gap is usable at decision time, with Gold's priority? | **Nearly all of it; capacity is not the constraint.**<br>• Gold is CLEAR at 10:00 on 918 of 929 replay days (77.5% of all 1,184 sessions; 251 expiry days and 4 others are outside the replay).<br>• Gold then enters inside 10:00–11:00 on 12 (1.3%), only later on 137, never on 768 (every hindsight gap day).<br>• Collision 6.7% at 11:00, 3.2% at 13:00 |
| **467** | Can BANKNIFTY F1 collect enough events? | **No.** 16 comparable triggers in 143 sessions (a lower bound) × 30% one-lot affordability (93% only in the last 5 days) × fill / recorder 0.9 / 0.95 = 0.029 qualified a session (0.6 a monthly cycle).<br>• 3.5 expected by the 120-session cap; P(≥ 15 fills) 4 × 10⁻⁶ (0.0016 at 1.5× triggers, everything optimistic).<br>• **30 triggers take about 4.1 years.** The recorder change is worth almost nothing for F1 itself |
| **468** | A Gold signal through the shared-wallet state machine | **`wallet_sm.py` + 8 fixtures (8 pass):**<br>• fills on fresh packets only;<br>• partial entry and exit;<br>• costs once per fill;<br>• Gold spends only free cash (DELAYED / MISSED);<br>• UNRESOLVED at the session end, never a sale at an invented bid;<br>• duplicate and simultaneous packets.<br>**SN419's opener days:** Gold traded on 12 of 68, every time after the opener had exited, so 0 delayed or missed |
| **474** (own) | Should Gold exit earlier for liquidity? | **No; 15:10 stays.**<br>**Depth:** ATM / 1-ITM books hold 6 lots on 100% of usable snapshots 15:00–15:20 (median 3,770–5,135 bid units, spread ₹0.25–0.30; 33 non-expiry days).<br>**Exit-clock returns, 2022 / 2023–26 at ₹205:**<br>• 15:00: −17,111 / 8,70,611;<br>• 15:05: −13,020 / 9,20,615;<br>• **15:10 deployed: −15,281 / 8,50,883**;<br>• extension to 15:15: −13,643 / 8,18,576.<br>**At ₹400:** −25,340 / 4,68,570; −21,250 / 5,23,364; **−23,511 / 4,95,597**; −21,873 / 4,70,895.<br>The curve zig-zags (a few trades' timing), so 15:05 is a sensitivity, not a proposal |
| **460** | Can usable exit depth be predicted at a stop? | **INSUFFICIENT** (18 stop dates; 30 needed).<br>• Production's paper book: 24 stops; 8 labelled on 5 dates inside the archive.<br>• The first full bid after the trigger is late on 7 (median 28 s at the minute grid) and unresolved on 1, at **+₹604 a lot against the trigger mark**. Six lots cost the same a lot, so it is market movement, not depth.<br>• Gold: 0 observed hard exits.<br>• Plumbing (Nov 16): packets see a full bid 0.8 s after the order, against 60 s on minute snapshots |
| **463** | Can a duplicate screen catch repeats before we simulate? | **Plain TF-IDF over the 350-row history finds 71% of the frozen check set's duplicates in the top 5** (8 of 12 queries fully).<br>• Missed: fx5 444, pin 451, the range rows LightGBM 131 and LSTM 193.<br>• My own check set held an invalid citation: "SN193", where the history records SN191–SN194 as a range.<br>• No false duplicate on the two new mechanisms.<br>• The mechanism lexicon adds nothing.<br>• LLM arm not run (the same model wrote the set) |
| **457** | Reading the filing itself | **The deterministic parser works on NSE's rendered filing** (the handoff's "iXBRL" link is a web view, not tags).<br>• Bank of India Q2 FY27, standalone, lakhs: interest earned 21,22,887 (the components sum exactly), interest expenses 14,22,166, **NII ₹7,007.21 crore** (H1 ₹13,839.76 crore).<br>• No year-ago column; board meeting ended 16:47; disseminated 20:13:32 IST.<br>• HDFC fixture: +6.4% and ₹326.2 / 306.5 bn match at half-up rounding; the consolidated figure is not in the SEC exhibit.<br>• Model-arm caveat with 3/3 verbatim quotes.<br>• **Forecast comparison INSUFFICIENT** |
| **466** | FII cash flow beside the futures position | **BLOCKED.** NSE's cash FII/DII series is only on the website API refused in SN430 (not worked around). NSDL's custodian series is two sessions stale and a different definition (owner's call) |
| **465** | Does the forward queue cover different gap days? | **DEFERRED** until the scheduled verdicts; the ledger's columns are frozen in the plan |
| **459** | Transfer to SENSEX | **NOT_RUN:** no informative feature to transfer (SN456 closed; SN457 has no tested feature) |
| **470** | Admit at most one candidate | **NOT_TRIGGERED.** No new mechanism passed its screen (SN456 closed, SN458 stopped, SN471 failed its frozen rule).<br>The already-frozen candidates continue on their own schedules: the cheap opener (fw9 / fw9a / fw9b), the packet candidates and fx5.<br>For reference, the best seen variant (SN462's positioning model at 30% coverage) would add ₹10.5 / −₹17.4 a market session at ₹205 / ₹400 |

## Lessons
1. **A pretrained market model does not help.** Kronos-small forecasts the next half hour worse than "no change" (SN458), as the independent study found.
2. **Positioning reports carry no intraday direction we can see.** That holds at every clock, through the gap, for the popular ratio rule (wrong-signed) and as a forecast feature (CW p 0.62). The one interesting reading is on Gold's own trades, and it flips sign in 2022.
3. **Skill, not capacity, is the gap.**
   - Gold leaves 77.5% of sessions clear at 10:00 and collides on 1.3%.
   - Filling them needs a forecast correlated about 0.2 with the next hour (0.1 when trading only the top 30%) just to break even.
   - The ₹154 a session the owner's goal needs takes about 0.3–0.37.
   - Nothing built here has exceeded about 0.1, and its confidence did not map to cash.
4. **Our forward verdicts are mostly unable to tell an edge from none.**
   - A point rule at 15–60 decisions passes a zero-edge book about 1 time in 5.
   - A real wage-level edge would pass only 1 time in 3 to 2.
   - fx5's paired design is the exception.
   - Read every scheduled verdict as a screen. Prefer paired designs and longer horizons.
5. **Gold's cost risk sits in deep-ITM winners the archive never recorded, not in thin books.** The 15:10 books are deep, so the cost check needs the recorder's wider window.

## Forward queue (unchanged; scored once)
- fw5 / fw7 / fw7a / fw7b / fw7c and fw8 / fw8a after SN300a's 20 sessions;
- fw9 / fw9a / fw9b at 15 cheap fills or 60 sessions;
- fw6 from Dec 7;
- F1 after the recorder change is deployed (SN467: it will end INSUFFICIENT);
- fx5 at 60 decisions.

SN472's power numbers should be read beside each verdict when it is issued.

## Owner's decisions
- **The protected 2023 expiry exam** (48 full-chain expiries) is still unspent.
- **SN466:** approve NSDL's custodian FPI series as a different, two-session-stale input, or leave the cash test blocked.
- **SN471:** optionally register "Gold trades agreeing with the prior-session FII change" as a frozen forward diagnostic (no Gold change; report only).
- **"Deploy"** is still pending for the recorder's BANKNIFTY chains (`1bfed1d0`; SN467: little value for F1), the SN329 hours and the V8 shadow.

## Rule register
- **Data and shared helpers:**
  - `poi_fetch.py`, `fut_extract.py` (acquisition);
  - `feat456.py` (features);
  - `ledger10.py` (the 10:00 two-sided Breeze ledger);
  - `wallet_sm.py` + `test_wallet_sm.py`.
- **Slots:**
  - SN456 BASE / AUG;
  - SN457 parser + model arm;
  - SN458 KRONOS / ZERO / RIDGE / VOL;
  - SN460 A / B / C;
  - SN461 states and attribution;
  - SN462 BINS / COVER30 / DUMB30 / CURVE / CONFORMAL;
  - SN463 PLAIN / STRUCTURED;
  - SN464 minute states and the partial exit;
  - SN467 cases;
  - SN468 the application;
  - SN469 12 scenarios × 3 rules;
  - SN471 AGREE − DISAGREE (+ post-hoc);
  - SN472 fw9a / SN300a / F1 / fx5;
  - SN473 correlations + the FII long-ratio rule;
  - SN474 depth + E345 / E350 / DEPLOYED / EXT360;
  - SN475 the ρ grid.
