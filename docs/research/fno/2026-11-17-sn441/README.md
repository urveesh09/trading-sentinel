# SN441–SN455: the true direction hurdle, the value of waiting, discount and passive entries, honest fill persistence, Gold's cost at size, an affordable strike under a full-loss bound, bank results, the London clock, expiry-afternoon flows, a future-blind check of Gold, and what a development number is worth (Nov 17, 2026)

**Owner (Nov 17):** the auditor's SN441–SN450 (`docs/SN441_SN450_RESEARCH_BRIEF.md` and the 15-row filing CSV, committed as received in `6141c1df`) plus five own slots (SN451–SN455). Plan `f56f5807`, with amendments in its section 4. Every script was committed before it ran, and results were written once.

**Outside sources used for the method (never for parameters):**
- option-expiration pinning (Ni, Pearson & Poteshman 2005; Golez & Jackwerth 2012);
- hedging-demand intraday momentum (Baltussen, Da, Lammers & Martens, JFE 2021);
- hftbacktest's conservative queue model (a resting order fills only when price trades through it);
- freqtrade's lookahead analysis (recompute every decision with the future removed);
- dated STT (0.0625% → 0.1% from Oct 1, 2024; → 0.15% from Apr 1, 2026).

**Status:** research only. No runtime, broker, Production or order change. The forward verdicts stay unopened, and no recorder session from Nov 17 was read. The NIFTY 2023 expiry-day chains, the protected expiry exam, were not queried: SN451 asserts 2024–25. SN427's one 2023 expiry-morning read last round is disclosed in the plan.

## Results (in the order run)

| SN | Question | Result |
|---|---|---|
| **441** | The real directional hurdle (two-sided, legal exits) | **SN428 parity exact** (BASE −169, SIDE +1,269).<br>**Common cells:** 98 on 37 dates.<br>**Break-even direction for a one-hour 1-ITM trade:**<br>• overall: 49.7% gross, 51.7% with fees, **57.6% at ₹205**, **66.5% at ₹400**;<br>• **Gold-empty days: 52.7% / 55.0% / 61.8% (90% CI 57–68%) / 77.2% (68–91%)**;<br>• Gold days: 50.3% / 54.9%;<br>• expiry days: 60.0% / 65.0%.<br>**The coin side loses ₹264 / ₹538 a decision.**<br>SN428's late-exit flaw moved 7 rows and ₹1. The hurdle is the spread and time decay (the empty-day gross coin is already −82), then the stress |
| **442** | The value of waiting, contract locked | **Hindsight's best forward price within 30 minutes is worth +₹1,027 a decision over NOW** (Gold-empty +990).<br>**Fixed waits capture little:**<br>• WAIT-1 / 5 / 15: paired +42 / +54 / +76 at ₹205 (empty days +84 / +146 / +112);<br>• this is mostly a shorter decay exposure, not timing.<br>**SN428's TIMING headroom of +2,318 over NOW on the coin side splits into:**<br>• backward reach 658;<br>• strike re-choice 66;<br>• exit shift 479;<br>• **forward locked-price headroom 1,109** |
| **454** (own) | Passive entry at the touch, conservative fills | **FAIL.** A resting bid fills only when the ask falls through it, so it pays more than the new ask.<br>**Panel (180 decisions, ₹205):** PASSIVE −482 against NOW −361 and DELAY-1 −317 (89 limit fills saving ₹18 a lot against NOW).<br>**Nov 16 seconds (plumbing):** −17.4 against IMMEDIATE and −77.5 against DELAY-5 a lot.<br>**Closed** |
| **443** | A discount while the premise holds (Production's own signals, real quotes) | **FAIL.** 42 signals kept, 34 priced on 21 days.<br>**Per decision:** NOW −156 / −331 (₹205 / ₹400); **DISCOUNT −342 / −448**.<br>• Its 15 fills average −774: an option cheaper than its delta explains keeps falling.<br>• It missed 8 NOW winners.<br>PLAIN −160 / −247 (fewer trades, not better ones). Delays of 1–5 minutes: −34 to −76 paired.<br>**Closed** |
| **447** | The morning after bank results | **INSUFFICIENT:** 14 first releases, 8 independent reaction sessions.<br>**No stock drift beyond the first reaction:** abnormal 09:45–11:45 continuation +4.8 bp against −15.3 bp for matched controls (4 of 8 sessions above); 43% of issuers continue.<br>**The NIFTY mapping** hits 6 of 8 and prices +885 / +510 a session on 7, but one day (Apr 20, +6,655) is all of it: −77 without it |
| **448** | The London open as an outside clock | **No London clock.**<br>• The all-day DiD is +0.067 (90% CI 0.010–0.125).<br>• Within 4 weeks of each clock change it reverses to −0.057 (CI −0.19 to +0.06).<br>• LSE-closed days show +0.046, so the effect is seasonal, not London.<br>**13:30 IST is busier than 12:30 in both regimes.**<br>**After the first local bar the direction is a coin** (50.0% hit at the London clock, 51.6% at the other), though 30-minute moves (23 points) clear the 8 / 13-point option hurdle 74% / 60% of the time.<br>**The UK-surprise test is blocked** (no series) |
| **451** (own) | Expiry-afternoon flows: pin against momentum (105 expiries, 2024–25) | **No pin:** toward the largest OI hits 44% (13:00 → 15:00) and 35% from 14:00; only 24% of days end closer to it; max pain 42%.<br>**Momentum (Baltussen) is the round's one mechanism-consistent pattern:** 57.7% (CI 50–65%; 58.7% from 14:00) against **43.8% on the eve of expiry** (placebo).<br>**It does not pay:** the expiring ATM option makes +88 / −94 a trade (median −1,079; −92 without the best; 2024 −25, 2025 +199).<br>**No development pass; nothing nominated** |
| **446** | An affordable strike under the full-loss bound | **No workable bound at ₹30k.**<br>**BOUND-LADDER** (Gold's strike, then the signal strike, then one step OTM) trades 39 times in 2023–26 for **₹18,204 / ₹12,994** (26 OTM, 10 signal, 3 Gold strikes), against DEPLOYED ₹8.51 lakh. 2022: −4,071 (5 trades).<br>SN434's BOUND is reproduced exactly (0 / ₹11,799) |
| **452** (own) | Is Gold's replay future-blind? (freqtrade's lookahead analysis) | **PASS.**<br>• All 186 Gold decisions (30 in 2022, 156 in 2023–26) are identical with every option, index and future value after the entry minute removed (nets unchanged).<br>• The volatility table is unchanged on 40 seeded days with that day's own bars scaled.<br>• All 434 stream trades enter 59 s after their 5-minute signal bar closes |
| **453** (own) | SN443's discount on Gold's own stream, inside the wallet | **FAIL: Gold's entries should stay immediate.**<br>**2023–26 at ₹205:**<br>• DEPLOYED 8.51 lakh;<br>• DELAY-1 / 3 / 5: 7.77 / 8.24 / 7.45 lakh;<br>• PLAIN-5: 2.19 lakh (60 signals never dip);<br>• DISCOUNT-5: 5.80 lakh;<br>• DISCOUNT-OR-MARKET-5: 6.56 lakh.<br>2022: PLAIN-5 −14,669 against −15,281 (fewer trades in a losing year) |
| **445** | Gold's cost at its own clock and size | **₹205 still covers Gold's cost on average, with a wide spread.**<br>**Gold's 10 replay trades in the archive (all 6 lots):** 6 priced on real 5-level depth cost +120 a lot over the model (entry +50, exit +70; range −933 to +643); 4 are INSUFFICIENT (3 are 15:10 exits).<br>**The 41 paper rounds against the last complete bar:** mean +96.5, median +13, p90 +491 (24% above ₹205).<br>**Paper against the walked book at the snapshot before the fill:** entry +58.5 (41 s earlier), exit +114 (29 s), mostly market movement in the gap.<br>Fees: median ₹66.5 a lot. **Dated STT** would add only ₹5,199 to Gold's 2023–26 (0.6%) |
| **444** | An honest five-second companion | **`fx5.py` is frozen**, with 7 fixtures including the one-packet window failing.<br>**Mechanics (plumbing, Nov 16, 240 decisions, 300 s hold, ₹205):**<br>• IMMEDIATE −230;<br>• **DELAY-5 −161**;<br>• **CONFIRM-5 −67** (74 fills, 37 IMMEDIATE winners missed);<br>• PASSIVE-5 −243.<br>**The unconditional wait improves the fill as much as confirmation** (+53.3 against +54.5 a lot). Most of SN432's gain was the delay on a falling morning plus trading less.<br>**The prospective test** (fw7c + FNO_PAPER signals after the freeze, read once at 60 decisions) decides |
| **455** (own) | What a development number is worth here | **Of 19 development / unseen pairs (13 frozen rules), 5 kept their sign (26%).**<br>Unseen rate / development rate: **median −0.22** (IQR −0.61 to −0.07); 2 of 13 kept more than half.<br>**Only WK-H** (a hedged variance premium with a mechanism and 229 development weeks) kept its rate (1.11× / 1.18×).<br>Gold v5: −0.07× (2022); N11 −0.22×; N10 −0.07×; N08 −0.14× |
| **449** | Frequency, fill and the length of a verdict | **No lead can cover the gap or be verified in time.**<br>**SN451 momentum:** +83.6 per empty session at ₹205 (target 154; CI −490 to +735; SD 3,805 a trade) would need ~3,776 expiry sessions (72 years) to tell ₹154 from zero, and the SN455 shrinkage makes its expected unseen value negative.<br>**The bank mapping is capped by frequency** (5.7% of sessions): +44 a session (CI −36 to +149).<br>**Stopping rule published:** PASS / FAIL when the 90% block CI lies wholly above / below ₹154, else EVIDENCE_INSUFFICIENT at 3n |
| **450** | Gold-plus-candidate test | **NOT_TRIGGERED** (no survivor). The protocol is frozen.<br>**Gold-only all-session baseline, 2023–26 at ₹205:**<br>• 944 market sessions, **₹901 a session**;<br>• **without the best 5 days ₹5.00 lakh** (the best 5 = 41% of profit);<br>• payout months 25 of 46;<br>• **₹750+ days 59 (6.2%)**;<br>• **the longest stretch without a new high is 226 sessions**; the longest non-positive run 151;<br>• refills 5.62 lakh; worst day −21,113.<br>**At ₹400:** ₹525 a session, 1.96 lakh without the best 5.<br>**2022 at ₹205:** −62.9 a session, 4 of 12 months |

## Lessons
1. **The direction bar on Gold's empty days is about 62% at ₹205 and 77% at ₹400 for a one-hour ITM option,** and the gross coin is already negative there (spread plus decay). Every short-hold direction idea this round (bank results, the London clock, expiry momentum) fell below it once costs were counted.
2. **Timing headroom is real in hindsight, about ₹1,000 a decision, but no observable rule captures it.**
   - Fixed waits, a delta-adjusted discount, a plain limit and a resting bid all lose: the cheaper fills are the losing trades.
   - Inside Gold, every patient entry costs 3–74%. Gold's entries should stay immediate.
3. **Gold's replay is future-blind (SN452) and its cost allowance holds at its own size (SN445).** Its weakness is concentration, not leakage: 41% of four years' profit comes from 5 days, and the longest dry spell is 226 sessions.
4. **A full-loss bound cannot run Gold at ₹30k, even with a cheaper strike** (₹18k in four years).
5. **A development number has predicted almost nothing in this program** (median unseen / development −0.22). The single survivor had a mechanism and years of data. New ideas therefore go to frozen forward tests, and development results are read as hypotheses only.

## Forward queue (unchanged; scored once)
- fw5 / fw7 / fw7a / fw7b / fw7c and fw8 / fw8a after SN300a's 20 sessions;
- fw9 / fw9a / fw9b at 15 cheap fills or 60 sessions;
- fw6 from Dec 7;
- F1 after the recorder change is deployed;
- **new: fx5** (SN444), at 60 decisions on recorder sessions after `6d3b4d93`.

**Owner's decisions:**
- **The protected 2023 expiry exam** (48 full-chain expiries) is still unspent. Only the owner can assign it (to the E03 family, as frozen, or to a future expiry rule).
- **More bank filings** (the auditor's list, or an approved NSE fetch) would be needed before the bank route can be judged.

## Rule register
- **SN441:** `legal` (the stop on an observed mark; the first bid at or after the exit within 5 minutes, else UNRESOLVED); `test_sn441.py`.
- **SN442:** NOW / WAIT-k / BEST-PRICE-30 / FWD-LOCKED / FWD-RECHOSEN / TIMING-428, with exits A and B.
- **SN443:** NOW / DELAY-k / PLAIN / DISCOUNT, D = ₹1.
- **SN444:** `fx5.py` (frozen), `test_fx5.py`.
- **SN445:** A / B / C.
- **SN446:** BOUND-NORMAL / LADDER / LADDER-1 / SIGNAL / OTM1.
- **SN447:** R1 / R2a / R2b abnormal, matched controls.
- **SN448:** DiD and the residual.
- **SN449:** f × q × m and n.
- **SN450:** the baseline metrics and the companion protocol.
- **SN451:** PIN / PIN_PAIN / MOM.
- **SN452:** truncation, the volatility perturbation, signal clocks.
- **SN453:** DELAY-k / PLAIN-5 / DISCOUNT-5 / DISCOUNT-OR-MARKET-5.
- **SN454:** PASSIVE (panel and seconds).
- **SN455:** the pair table.
