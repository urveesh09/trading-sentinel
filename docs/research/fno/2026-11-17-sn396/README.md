# SN396–SN410: put the opening trade on the real clock, isolate Gold's signal source, test whether "cheap" is real (Nov 17, 2026)

**Owner (Nov 17):** the auditor's SN396–SN405 (`docs/SN396_SN405_RESEARCH_BRIEF.md`, committed as received in `1f903980`) plus five own slots. Plan `00693405` (amendment A1 and one disclosed fix in its section 4). Every script was committed before it ran; results were written once.

**Status:** research only. No runtime, broker, Production or order change. No forward session has been scored. The new forward companions (fw7b, fw9a, fw8a) were frozen before any forward session was read.

**The auditor's findings: all confirmed in the code.**
- **The 09:16 label.** gl's index i is the bar starting at 09:15 + i, and its close falls at that bar's last second. SN382 / SN394 decided, labelled and filled at the 09:16 bar's close (09:16:59). The history therefore measured a 09:17:00 decision, while fw7a / fw9 decide at 09:16:00.
- **The limit.** fw2 compared the walked VWAP with the cap (64 + 1 units filled against a ₹100.10 limit).
- **Quote age.** fw9's straddle IV had no age or call / put skew bound, and it used the previous *archived* folder as the previous session.
- **Also found:** an exact-zero auction gap went to PE, and the exit status was recorded for one stress only.

## Results (in the order run)

| SN | Question | Result |
|---|---|---|
| **396** | The opening trade on the real clock | **The clock lead was the whole edge.** Per session (60 min) at ₹205 / ₹400:<br>• ORIGINAL (SN382 parity) +45.6 / −137.5.<br>• **HONEST** (labels and fill at the 09:15 close = 09:16:00) **−80.7 / −234.6**.<br>• LATE (59 s latency, capped) −252.8 / −348.6: fills fall from 146 to 82, and the capped order fills mostly when the price falls.<br>**CHEAP survives the clock:** HONEST frozen cutoff +334.5 / +181.5 per cheap session (72 sessions; +189.5 at ₹205 without the best day). Labels changed on 5 of 124.<br>**Archive against model at the open (24 days):** the median extra round trip per lot is −36 / −42 / +39 (ATM / 1-ITM / 2-ITM). Real spreads are ₹16–26 a lot against the model's ₹23–33. The large means (+237 to +395) are the first-minute price change, not spread.<br>**Forward companions frozen:**<br>• `fw7b`: limit-legal fill, zero gap = NO_SIGNAL, status per stress.<br>• `fw9a`: legs ≤ 2.0 s old and ≤ 2.0 s apart; previous exchange session by NSE's calendar; ROLL block.<br>16 tests pass. On Nov 16, 0 of 348,359 ask levels were not lot multiples, so a one-lot partial fill cannot occur |
| **403** | N10 against N11 in the same Gold portfolio (₹30k, six feeds) | **2022:** DEPLOYED −15,281; N11 alone −7,242 (R0.85 cost 8,039); NO_STAND = N10 = **+4,681**, with or without R0.85.<br>**N10's retry never fired in 2022:** the whole N10-versus-N11 gap is the stand-aside (+₹19,962).<br>**2023–26 (in sample):** DEPLOYED ₹8,50,883; NO_STAND + R0.85 ₹7,00,026 (the stand-aside's in-sample gain is +₹1,50,857); N10 + R0.85 ₹7,11,386 (the retry adds +₹11k at ₹205 and −₹287 at ₹400).<br>**2022–26:** DEPLOYED leads (₹7,36,894; N10 ₹7,16,165; N11 ₹7,14,972).<br>The 65 blocked signals produced 58 Gold trades netting **−₹822 over five years**: at trade level the stand-aside is a wash, and its lead is a compounding path effect. **No change** |
| **397** | What does "cheap" detect? | **Mostly direction:**<br>• follow-through +12.7 index points against +2.4 (delta part +₹734 against −₹495 a lot);<br>• a smaller IV / decay loss (vega −64 against −160, theta −37 against −88);<br>• affordability 94% against 83%;<br>• the opposite side loses −₹811 on cheap mornings (the mirror image).<br>**Calendar-tangled:** 42 of 44 after-weekend / holiday mornings are not cheap; 30 of 33 mornings ≥ 3 sessions from expiry are cheap (and they lose −₹405). The binary label has t 3.6, but **the continuous jump has no slope (t −0.9)**.<br>**White reality check, 24-rule family at ₹400:** best = CHEAP (₹84.9 a session), **p 0.80**; on the HONEST clock p 0.76. Studentized (SN397b): t 0.81 / 1.02, p 0.90 / 0.84 |
| **399** | A price ceiling from the remaining move | **The forecast never clears the hurdle.** The cheapest break-even contract (2-ITM on 99 of 117 sessions) needs a median **13.4 index points** in the hour (18.2 at ₹400); the causal forecast of the gap direction's follow-through is **1.3–1.6 points**. 0 trades |
| **406** | Parameter map (720 cells, HONEST) | **Without a filter, all 144 cells lose at ₹400** (mean −₹287 a session). Only 16.5% of all cells are positive at ₹400 (4.7% in both periods).<br>**With CHEAP:** a contiguous patch at ₹205 (entries 09:16–09:25, holds 30–90 min, every contract, +30 to +189 a session). At ₹400 it rests mainly on the ten post-Sep 7 cheap days.<br>**A stricter cut (20th percentile) is worse:** no dose-response.<br>**Best cell:** 09:25 / 30 m / 2-ITM / CHEAP, +₹112.6 at ₹400 with 8 of 11 neighbours positive; **reality-check p 0.83** (studentized 0.80).<br>**fw9's cell:** +140.8 / +76.4 a session (pre-period +6.5 at ₹400) |
| **407** | fw9's frozen rule before the auction (2022 – Dec 2025, gap direction) | **Does not support fw9.** CHEAP +₹18.8 a cheap session at ₹205 (−71.9 without the best day), −₹147 at ₹400; by year +555 / +107 / −261 / −237.<br>The relative effect holds (OTHER −211, ALL −146): cheap mornings are less bad, but not profitable |
| **410** | Did the Sep 7 auction change remove the edge? | **Before Sep 7** the auction direction kept going for the hour after 09:16:00 (+14.5 points, t 2.65, 60% positive).<br>**From Sep 7** the move is spent by 09:16:00 (first-minute drift +23 points, t 3.3) and the hour after is flat to negative (−13.2 mean, −1.6 median, 27 sessions).<br>**Cost is not the problem:** real spreads are ₹22.75 a lot at 09:16 against ₹19.50 at 10:16 / 11:00 |
| **398** | Weekly-roll days with the same contract | **Breeze:** 0 of 43 expiries have option requests on or before the previous expiry day (no next-week chain in history).<br>**Archive:** 9 roll days, 7 with a same-contract reading (5 CHEAP). The next-week ITM lot was affordable on **3 of 7**: +1,342 / +1,700 (cheap), −3,116 (stop). Little extra coverage; recorded forward in fw9a's ROLL block |
| **401** | SENSEX for days NIFTY cannot trade | **Fails.**<br>• **81 NIFTY expiry days:** SENSEX gap ITM −₹547 / −₹668 a session.<br>• **26 NIFTY-unaffordable days:** +252 / +87, but negative without the best day.<br>• **NIFTY's auction direction on SENSEX:** −341 / −407.<br>A disclosed fix: the first run's expiry class was empty (receipt kept). BANKNIFTY has daily bars only |
| **402** | RBI release days | **INSUFFICIENT.** Of 29 MPC decision days (dates confirmed from RBI pages and schedules), 23 had a session; only 3 moved ≥ 0.15% in the five minutes after release, and all 3 hit the ₹3,000 stop.<br>Bank agreement untestable |
| **404** | Were the stand-aside's blocked winners cheap? | **No.** The 14 blocked winners had a higher ask (117 against 97), higher IV and a higher hurdle than the 43 blocked losers. No price measure correlates with Gold's net per lot (blocked \|t\| ≤ 1.31; accepted TPB n = 112, \|t\| ≤ 1.52). Closed |
| **408** | Does option richness explain Gold's losses? | **No.** 176 Gold trades: every measure \|t\| ≤ 1.03. The overnight-richness terciles look monotone pooled (+1,863 / +1,312 / +704 a lot) but the cheap third wins in only 2 of 4 years. No forward field. Gold's losses are signal losses |
| **409** | Gold's clocks (stream minutes shifted) | **Gold is not a clock artefact.** 2023–26 at ₹205:<br>• 0 = ₹8,50,883 (parity);<br>• **+1 min latency ₹7,85,632 (−7.7%)**;<br>• +2 min ₹8,55,097 (path noise);<br>• −1 min (lookahead) ₹10,98,614.<br>**Gold buys into moves already running:** fill speed matters, but a minute of latency leaves it intact |
| **400** | Does option flow lead futures? | **`fw8a` frozen.** Strict signing needs a fresh, uncrossed, single-trade, causal prior quote.<br>**Nov 16 plumbing:** each Kite volume increment bundles a median of **~198 trades** (only 0.4% are single trades), so strict signing labels **0.0%**. fw8's 91.7% is the sign of each bundle's *last print*.<br>**Amendment A1:** the forward OLS tests that last-print flow against the futures return, option mid revision and unsigned volume. 4 new fixtures; 20 tests pass |
| **405** | One wallet (not a verdict) | **Gold alone from ₹30k, 2022–26:**<br>• trades on 161 of 932 sessions (17%);<br>• **₹791 a market session at ₹205, ₹409 at ₹400**; 6.9% of sessions reach ₹750;<br>• the longest stretch to a new high is 352 sessions (516 at ₹400).<br>**For ₹750 a session at ₹400,** each empty session would need +₹412.<br>**The cheap opener in the shared wallet (development):** 68 fills, **0 conflicts with Gold** (Gold never entered before 10:16 those days), +₹140 / +₹76 a session |

## Forward queue (scored once; no forward P&L opened)
- **After SN300a's first 20 qualified sessions (about Dec 23):**
  - `sn351/fw5.py` beside `sn381/fw7a.py`, `sn396/fw7b.py` and `sn366/fw7.py`, all published together;
  - `sn381/fw8.py` and `sn396/fw8a.py` (20 sessions, 5 to calibrate).
- `sn381/fw9.py` and `sn396/fw9a.py`: at 15 cheap fills or 60 sessions, published together. fw9a's ROLL block is reported separately.
- **2027 holidays:** NSE's 2027 list must be added to `fw9a.HOLIDAYS` before any 2027 session is scored.
- `sn351/fw6.py`: from Dec 7. It needs the recorder to run to 15:46.

## Lessons
1. **The clock decides opening research.** One minute of label lead turned −₹81 into +₹46 a session. A 59-second latency with a capped order selects the losing fills. Any history that labels a bar by its start and trades its close is a minute ahead of a live decision.
2. **"Cheap" is real as a sorting variable but not proven as an edge.** Cheap mornings follow through more and lose less IV, so they are better than other mornings in every period. Yet the continuous measure has no slope, the effect is tangled with the calendar, it fails on 2022–2025 gap days, and after the search it is p ≈ 0.8. fw9 / fw9a are the only fair judges now.
3. **The opening gap carries no expected move that pays for an option.** Break-even needs about 13 points in the hour; the average follow-through is about 1.3. Since Sep 7 the follow-through is spent before 09:16:00.
4. **Gold's stand-aside is a path effect.** Its blocked trades net −₹822 over five years. In 2022 the N10 / N11 gap is entirely the stand-aside, since the retry never fired. N10 earns a paper comparison, not a switch.
5. **Gold's losses are not price losses.** No measure of option richness at entry predicts its trades. Gold survives a minute of latency, but it buys into moves already running.
6. **Kite packets cannot sign trades.** One packet bundles about 200 trades. Any "order flow" from this feed is last-print flow.
7. **Coverage routes are closed:** roll days (affordability), SENSEX on NIFTY's skip days, RBI events (too few, and they reverse).

## Rule register (every rule tried this round)
- **SN396:**
  - ORIGINAL / HONEST / LATE clocks × ITM / ATM / coin;
  - CHEAP by the fixed cutoff and the moving tercile;
  - archive-versus-model cost at 09:16 / 10:16.
- **SN397:** four cells (CHEAP / OTHER × SAME / OPP); strata (DTE, after-break, source, gap size); OLS on CHEAP and on the jump; White and studentized reality checks over 24 rules.
- **SN399:** a hurdle against a causal forecast across ATM / 1-ITM / 2-ITM.
- **SN406:** 6 clocks × 4 holds × 3 contracts × 5 filters × 2 stops.
- **SN407:** fw9 on gap days, 2022 – Dec 2025.
- **SN410:** gap / drift / follow-through before and after Sep 7; spreads by window.
- **SN398:** same-contract roll IV and the roll-day ITM trade.
- **SN401:** SENSEX gap and NIFTY-auction ITM on NIFTY expiry / unaffordable / common days.
- **SN402:** RBI release + 6 min, 0.15% move, IV-released filter.
- **SN403:** six Gold feeds × three paths × two stresses.
- **SN404 / SN408:** richness measures against Gold's per-lot net.
- **SN409:** stream shifts −1 / 0 / +1 / +2.
- **SN405:** Gold coverage; the shared-wallet illustration.
- **Forward:** fw7b, fw9a, fw8a.
