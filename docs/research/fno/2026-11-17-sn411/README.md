# SN411–SN425: what was observable, what each day offered, whether another index can take the wallet, and how robust Gold is (Nov 17, 2026)

**Owner (Nov 17):** the auditor's SN411–SN420 (`docs/SN411_SN420_RESEARCH_BRIEF.md`, committed as received in `361f98ae`) plus five own slots. Plan `e5cc95b7`. Every script was committed before it ran; results were written once.

**Disclosed follow-ups** (run after the first numbers, published whole):
- SN413 A: MIDCPNIFTY's index name;
- SN414b: the threshold grid.

**Status:** research plus one Dev code change. The recorder change (BANKNIFTY futures and options, `1bfed1d0`) has tests and is **not deployed**: it awaits the owner's word. No broker, Production or order change. No forward session has been scored. fw7c / fw9b were frozen before any forward session.

## Results (in the order run)

| SN | Question | Result |
|---|---|---|
| **411 A** | Stale inputs at the decision | **`fw7c` frozen:**<br>• FIRST_TRADE needs today's continuous-session trade;<br>• the receipt offset comes from pre-decision packets only;<br>• the strike index and the admission / cap book must each be ≤ 2.0 s old.<br>`fw9b` = fw9a on fw7c. 25 tests pass. **Nov 16 plumbing: no decision changes** (book ages 0.12–0.38 s; offset 0.6305 against the whole day's 0.6332) |
| **411 B** | The live decision chain | **Production's paper entries** (64, Jul 16 – Nov 11; 5-minute bars) arrive a median **44 s after the bar end** (p90 88 s); **N11 entries (13) 53 s** (p90 88 s). The N11 replay assumes **59 s** (p90 119 s), always at second :59. **Live is no slower than the replay**, so SN409's one-minute penalty is not the live regime |
| **413 A** | Which index can take ₹15k (NSE end-of-day files, 71 sessions Aug 3 – Nov 13) | **NIFTY:** front ATM 98% affordable (both sides 97% of dates).<br>**BANKNIFTY** (lot 30): front ATM 30% (median ₹19,169): 93% in the last 5 sessions to its monthly expiry, 28% at 6–10, 6% at 11–20, 0% beyond; both sides 20% of dates; the next month never.<br>**FINNIFTY** (lot 60): 31%, and thin (a median **314 trades a day** per contract against BANKNIFTY's 42,570).<br>**MIDCPNIFTY** 21% (follow-up); **NIFTYNXT50** almost untraded.<br>**BANKNIFTY is the only workable venue, and mostly in its last week** |
| **413 B / C** | Depth | No intraday BANKNIFTY / FINNIFTY quotes on this PC. **Sample needed:** ≥ 20 recorder sessions with 5-level depth across a roll.<br>**Dev change `1bfed1d0`:** the recorder adds BANKNIFTY futures and options (2 expiries, ±10 strikes; ~+15% bytes; off with `TICK_RECORDER_EXTRA_UNDERLYINGS=""`). FINNIFTY is skipped (no instrument book; thin) |
| **414** | The bank-sector move NIFTY hides | **The basket proxy holds** (daily correlation 0.985 with BANKNIFTY).<br>**The move does not persist:** 15 triggers in 7 months; the next 45 min in the residual's direction **−4.4 bp** (t −0.89); the NIFTY-option version **−₹845 a trigger**.<br>**SN414b grid (27 cells):** 0 cells positive at 45 min, and **every cell negative at 15–30 min** (−5 to −14 bp, t down to −2.86): the residual **reverses**. Post hoc and small |
| **412** | What each day offered (hindsight) | **On every one of 42 real-quote days** one affordable lot could have made a median **₹9,376** (₹9,181 at ₹400). 100% of days reached ₹750 and ₹1,648; Gold-empty days had a median of ₹9,354.<br>**From fixed clocks** with a 60-min window, the best contract reached ₹750 in **83–97%** of cells.<br>**The gap is selection, not the instrument or the wallet** |
| **418** | The stand-aside across starts | **It fires only in 2022–23.**<br>**One lot, no growth:** −₹19,963 in 2022 and +₹41,864 in 2023–26 (+₹21,902 over 2022–26; +₹2,621 without R0.85); its 58 blocked trades net −₹11,232 at one lot.<br>**Quarterly starts:** 12 of 19 tie; the 2022 starts lose with it, and the late-2022 / 2023 starts gain. **Mildly positive, one regime: retained** |
| **419** | The cheap opener and Gold in one ledger | **Parity holds:** 8,50,883.<br>**The opener adds +₹22,849** at ₹205 (+₹12,240 at ₹400) over its 10-month window, about **₹133 / ₹71 a session**. Gold loses ₹1,233 from the reduced day room and never needed the cash first (0 forced exits).<br>**The costs:** all **12 opener stops slipped past ₹3,000** (worst −₹3,312 / −₹3,494); Gold's worst month −₹38,531 → −₹43,771. Development only |
| **421** | Gold's parameter map (one step at a time) | **Signal-side settings are flat:** the extension off −0.5%, ext_x / ext_k within 2%.<br>**Exposure settings are FRAGILE:**<br>• scale-in off −24% (2022 better);<br>• full-size adds off −29%;<br>• ITM choice off −28% (2022 worse too);<br>• day room 15% −24%;<br>• single lot −27%;<br>• growth cap 2 −27%, cap 4 +37%.<br>Gold's edge is its signals; sizing is leverage |
| **422** | Why Gold's days are empty | **Gold's replay never includes NIFTY expiry days:** 263 of 1,195 sessions.<br>Of the rest, **730 have no signal** and 41 are held back by the stand-aside (−₹23,924 if taken); **0 signals go untaken**.<br>**Per calendar session Gold makes ₹617 at ₹205 (₹319 at ₹400), not ₹791.** 86.5% of sessions have no Gold trade |
| **423** | Experts and sides | **EFF helps in both periods** (without it: 2022 −₹27,303, 2023–26 ₹5.70 lakh). OR20 and SHIPPED are mixed. TPB only and puts only are worse at ₹205. **In 2022 the 4 calls made +₹17,161 while the puts lost.** No dead weight: no change |
| **424** | Size ladder (2023–26 at ₹205) | **1 lot ₹2.14 lakh** (₹288 a session, worst month −₹9.6k); 2 lots ₹2.81 lakh.<br>**Growth caps 1 / 2 / 3 / 4 / 5:** ₹4.35 / 6.20 / **8.51** / 11.65 / 15.52 lakh, with worst months −12k / −24k / −39k / −55k / −84k (max lots 3 / 4 / 6 / 10 / 15).<br>**At ₹400 the gain flattens** (cap 5 ≈ cap 4); 2022 is unchanged by growth |
| **425** | Stop slippage and tail risk (2022–26) | **Stops:** 9 in 186 trades; 2 slipped past their room (worst +₹863).<br>**Bad days:** 2 lost more than 20% of the wallet (worst −₹21,113 = 20.9%).<br>**Worst trade** −₹20,203. **The no-bid bound is a full 6-lot debit (−₹1.00 lakh).**<br>**The extension** nets −₹6 over 18 trades |
| **415 / 416** | Company results; USDINR | **Closed at feasibility.** No filing timestamps, stock-option quotes or FX data on this PC (checked); the samples needed are listed |
| **417** | The partner's blind replay | **Protocol frozen** (`PROTOCOL_SN417.md`). Not run: it needs the owner's consent and the partner's time |
| **420** | The next paper decision | **Information route: none.**<br>**Instrument route:** one low-prior candidate, **F1, the BANKNIFTY residual fade** (`F1_SN420_SPEC.md`). It is judged only on recorder data after the owner deploys `1bfed1d0`, with 20 calibration sessions, then the verdict at 30 triggers or 120 sessions |

## Forward queue (scored once; no forward P&L opened)
- **After SN300a's 20 sessions:** fw5 / fw7 / fw7a / fw7b / **fw7c** together; fw8 / fw8a.
- **fw9 / fw9a / fw9b:** at 15 cheap fills or 60 sessions.
- **fw6:** from Dec 7.
- **F1:** after the recorder change is deployed, plus 20 calibration sessions.
- **2027:** add NSE's 2027 holidays to `fw9a.HOLIDAYS` before 2027.

## Lessons
1. **The opportunity is there every day; selection is the whole problem.** Hindsight offered ₹9k a day, and 90% of fixed-clock windows held a ₹750 trade. Every rule tested so far picks the right side and exit no better than chance.
2. **Gold's empty days are a signal shortage, not a permission problem.** Gold takes every signal it gets. Its replay also leaves out expiry days, a fifth of the market. Per real session it earns ₹617 (₹205) / ₹319 (₹400).
3. **Gold's robustness splits cleanly.** The signal side is flat to parameter changes. The exposure side (scale-in, ITM, room, lots, growth) moves the result by 25–37%, and it multiplies the bad months too. The size ladder is the owner's money decision, not a search result.
4. **Live clocks match the replay.** Live entries come about 44–53 s after the bar end against the replay's 59 s, so the replay's Gold timing is fair.
5. **Other indices fit a ₹15k wallet mainly in their last week.** BANKNIFTY has the liquidity, FINNIFTY doesn't. A sector residual reverses rather than persists, and that is a hypothesis, not a result.
6. **Stops slip.** The opener's stops overshot every time by up to ₹494. Gold's slip rarely, but a no-bid exit on a large Gold position could cost a full ₹1 lakh debit.

## Rule register
- **SN411:** fw7c / fw9b rules; the live chain.
- **SN412:** full-day and fixed-clock ceilings with and without the stop.
- **SN413:** the end-of-day screen (4 + 2 indices, front / next, ATM / 1 / 2-ITM).
- **SN414:** the residual trigger, plus a 27-cell grid × 4 horizons.
- **SN418:** one-lot and quarterly-start comparisons.
- **SN419:** the opener leg.
- **SN421:** 21 one-step variants.
- **SN422:** empty-day classes.
- **SN423:** 7 stream filters.
- **SN424:** 9 wallet ladders.
- **SN425:** stop / tail measures.
- **Forward:** fw7c, fw9b, F1 (spec).
