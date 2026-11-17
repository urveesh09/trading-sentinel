# SN351–SN365: information before the option reprices, the corrected wage, and Gold's evidence (Nov 16, 2026)

**Owner (Nov 16):** the auditor's SN351–SN360 (`docs/SN351_SN360_RESEARCH_BRIEF.md`, `390fc644`) plus five own slots; "one strategy essence, slot, then give it time … what is tested has to be correctly tested".

**Method:**
- Plan frozen at `cbdbc54c` before any number.
- Amendments A1 (SN363), A2 (SN353 semantics) and A3 (SN361) were each committed before that slot's numbers.
- One slot at a time; each script is committed before it runs, and each result is written once.

**Status:** research only. No runtime, broker, Production or order change. SN300a / fw3 / fw4 stay unopened.

## Results so far (in the order run)

| SN | Question | Result |
|---|---|---|
| **352** | Does the wage ledger reconcile? (the auditor's finding) | **The auditor is right.** SN342 counted the growth cash twice: ₹15,000 + ₹22,500 + ₹33,750 = **₹71,250** paid out that never existed.<br>• The cash-funded journal reproduces both old numbers (₹6,54,004 / ₹3,07,103), matches Gold's day nets exactly, and the cash identity holds on every session.<br>• **Corrected (reserve = one wallet): ₹5,82,754 over 45 months = ₹785 a session at ₹205** (was ₹881); **₹318 at ₹400** (was ₹414).<br>• 14 of 45 months pay (8 at ₹400). **2023 pays nothing**; the longest dry spell is 12 months.<br>• Growth was never short of cash (0 deferred sessions).<br>• A fixed ₹60k reserve makes Gold sit out 107 sessions at ₹400.<br>• Extra opening spare cash only comes back as "wage": it is the owner's own money |
| **363** | What fixed monthly salary can Gold pay without ever sitting out? | **Small:**<br>• **₹500 a month** with the owner's ₹60,000 (₹30k wallet + ₹30k spare) at ₹205; ₹3,000 with ₹90k; ₹4,500 with ₹1.2 lakh;<br>• ₹0 / ₹2,500 / ₹3,500 at ₹400;<br>• a fresh start in Jan 2024 or Jan 2025 allows ₹5,500 / ₹4,500 (start-date luck).<br>**₹15,750 a month (₹750 a session) needs ₹3.4 lakh spare (₹3.7 lakh in total) at ₹205, and no capital sustains it at ₹400** (Gold's net is below 45 × ₹15,750).<br>22 of 45 months earn under ₹500. The binding stretches are Gold's drawdowns (Oct 2023, Oct 2024, Aug 2025) |
| **353 (a)** | What do the auction fields mean? | NSE's page (updated 04/09/2026): order entry 09:00–09:10 with a random close, matching 09:10–09:12. In the recording:<br>• the packet's `open` = the indicative price;<br>• `volume` = the indicative matched quantity;<br>• buy / sell = **total queued** quantities (not the unmatched imbalance);<br>• the match is visible as the last price / last-trade time jump (09:09:01 on Nov 16).<br>Breeze stores the match in the first pre-open row with open interest (09:07 in Jan–Feb, 09:09 by September). Amendment A2 |
| **353 (b)** | Does the auction gap's direction pay in options? | **Closed.** Buying the gap's side at 09:16 (172 sessions, Dec 2025 – Oct 2026):<br>• +₹183 a trade gross at 20 minutes, ₹326 above a coin flip and ₹550 above fading. **The direction is information.**<br>• But −₹30 at ₹205 and −₹215 at ₹400.<br>• On 21 real-quote sessions, −₹257 at ₹205.<br>• By 09:16 the future has already moved another 0.04% the gap's way.<br>A post-hoc subgroup (0.2–0.5% gaps, +₹176 at ₹205 over 64 trades) is registered as a forward watch only |
| **361** | Is an option bought at the open overpriced? | **Yes, and robustly.**<br>• An ATM straddle bought at 09:16 loses **₹226 a lot by 09:45 and ₹338 by 10:15** to volatility normalization (ATM IV −0.26 / −0.37 points).<br>• That is ₹156 / ₹255 more than the same hold from 11:00 (885 sessions; standard error ₹33 / ₹38).<br>• Negative in every year 2022–2026; worst the day before expiry (−₹387).<br>• Real-quote mids agree (−₹278 vs control).<br>**Any opening long-option entry starts about ₹80–130 a leg behind.** That is part of why SN353 (b) could not clear ₹205 |
| **365** | Does the auction say anything about Gold's own trades? | **No information.**<br>• 27 of Gold's 42 trades (Dec 2025 – Oct 2026) went the gap's way, making ₹1,549 a lot against ₹778 for the other 15.<br>• But the permutation p is 0.55.<br>• No size note |
| **353 (c)** | Queue pressure, forward | **Frozen** in `fw5.py` before Nov 17. It is scored once on SN300a's first 20 qualified sessions, with the 0.2–0.5% gap watch beside it. Nov 16 plumbing: queue pressure +3.4% / +1.3% (not persistent); indicative price 25,214.9 at 09:06; matched at 25,249 |
| **351** | Where is a bought option's move still available? | **No state has room at ₹205.**<br>• Across 8,488 DEV positions (5 clocks × CE / PE, 2022–2026), 65% touch an executable +₹300 within an hour, and the hindsight ceiling averages ₹1,048 a lot.<br>• Yet the payoff is −₹90 gross / −₹295 at ₹205 at 20 minutes.<br>• Buying with a just-finished 0.25% move is worst (−₹367 gross at 60 minutes); against it is best (+₹118 gross, −₹87 at ₹205).<br>• The real-quote archive (304 positions) agrees overall.<br>• One ATM lot's quoted cost is about ₹87 |
| **362** | Gold's signal in SENSEX options | **FAIL; Gold stays on NIFTY.**<br>• 66 budget-matched pairs (Oct 2024 – Apr 2026): +₹356 a trade at ₹205 only because of one trade (−₹186 without it; halves +₹1,230 / −₹518), and −₹292 at ₹400.<br>• SENSEX helps only with its expiry-eve options.<br>• Real per-lot spreads are nearly equal (₹16.25 / ₹17.0) |
| **359** | V8's orders on real depth | **Gold's return survives V8's execution.**<br>• 10 decisions (Sep 10 – Oct 28): 9 entered with every lot, 1 missed (a ₹11,094 loser).<br>• On the 7 exits the archive can price, V8 nets ₹1,25,866 against the replay's ₹99,262 at ₹205 (₹1,10,332 at zero stress), so the ₹205 stress is conservative at Gold's sizes.<br>• Two exits fall after the archive stopped quoting the strike (a data gap, disclosed in `results-sn359-coverage.json`) |
| **354** | GIFT NIFTY residual | **BLOCKED:** no timestamped GIFT data on the PC. The series needed is recorded; nothing was fetched |
| **355** | RBI surprise | **Untestable here.**<br>• No expectations, intraday rates or release times; about 6 decisions a year.<br>• Description only: on 2026's 4 decision days, 10:15 ATM buys made −₹303 gross against −₹183 on other days |
| **356** | The sector (Financials) | **BLOCKED for data, and mostly unaffordable.**<br>• No bank minutes or BANKNIFTY option quotes on the PC.<br>• BANKNIFTY lot 30 (NSE file) at 54,267: an ATM call costs ₹13.5k–32.4k a lot, inside the ₹15k room only in the last week at low volatility |
| **357 / 360** | Chain tails / shared wallet | **Not triggered** (no candidate reached a trade rule). SN352's `Journal` is the shared-wallet harness for a later survivor |
| **364** | CAS 2.0 closing window | **Frozen** in `fw6.py`, scored once after 15 CAS sessions from Dec 7. **Needs the recorder to run to 15:46** (SN329, Dev only). Plumbing checked |
| **358** | Gold on 2022 (N11 exam) | **Not run.** It is the next round's first slot: four chained engine replays (N08 → N09 → N10 → N101 → N11) with the TEST2025 wiring check first, after market hours |

## Forward items added to the after-Dec-23 queue
- `python fw5.py verdict`: after SN300a's 20 qualified sessions, from the nightly archive.
- `python fw6.py verdict`: after 15 CAS sessions, only if the recorder runs to 15:46.

## Lessons
- **The wage is capital-bound and lumpy.** Gold's profit arrives in a few big months. A promised fixed salary is limited by its worst early stretch, not by its average.
- **The opening auction tells the direction, but the price already carries it.** Opening option premium is rich by about ₹80–130 a leg. Buying at the open pays for both.
- **Selling that opening richness** would earn it, but selling is outside the no-margin wallet. That stays the owner's line.
- **Bought options have room only in hindsight.** The best exit in an hour averages about ₹1,050 a lot, but every entry state tested pays −₹90 to −₹370 gross at fixed horizons. A predictor has to clear ₹200–300 a trade before it earns.
- **Gold's execution is not the problem.** On real depth V8 keeps the modelled return, and the ₹205 stress is conservative at its sizes. SENSEX is no better a vehicle.
- **The ideas the auditor rated best after the auction** (GIFT, RBI, Financials) **need data this PC does not hold.** A download is the owner's decision.
