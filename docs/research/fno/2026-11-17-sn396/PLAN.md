# SN396–SN410: put the opening trade on the real clock, isolate Gold's signal source, and test whether "cheap" is real (plan, frozen before any number; Nov 17, 2026 ~08:30 IST)

**Owner (Nov 17):** the auditor's SN396–SN405 (`docs/SN396_SN405_RESEARCH_BRIEF.md`, committed as received in `1f903980`) plus five own slots: "properly test the SN slots so we can get the new gold … tell me the returns … if we change any parameter".

**Agreed with the auditor, verified in the code before this plan:**
- **The 09:16 label.** In gl, minute index i is the bar starting at 09:15 + i minutes, and `gl.opx` returns its close. SN382 / SN394 decide, price the ATM strike, compute the straddle IV and fill at i = 1, the 09:16 bar's close (09:16:59). fw7a / fw9 decide at 09:16:00. The history therefore measured a 09:17:00 decision. (Gold's N11 stream is different: `entry_time` is the decision bar's close, e.g. 12:36:59, and Gold fills there, a zero-latency fill at the decision instant; SN409 measures its sensitivity.)
- **The limit.** `fw2.entry` compares the walked VWAP with the cap, so a lot can fill with units above the limit (64 at ₹100.00 + 1 at ₹100.15 against ₹100.10).
- **Quote age.** `fw9.straddle_iv` takes the last valid packet of each leg at or before the clock with no age or call / put skew bound. `fw9.verdict` takes the previous *archived* folder as the previous session, so a missing recording silently compares with an older day.
- **Also found:** `fw7a.session` sends an exact-zero auction gap to the PE side (`g > 0` → CE, else PE); `fw2.trade` records the exit status only for the first stress.

**Unchanged rules:** Gold v5 at ₹30,000; one bought index option, walked one-lot cost plus entry charges ≤ ₹15,000; ₹3,000 stop; ₹205 / ₹400 stress plus Zerodha charges; expiry days flat; Production read only; nothing places an order; fw5–fw9 and SN300a stay unopened until their verdicts; every script committed before it runs; results written once; crashes fixed before any number and disclosed.

## 0. Conventions fixed for this round

**Honest clock (gl minute data).** A decision at hh:mm:00 = minute index m uses bar closes up to m − 1 and is filled at the close of m − 1 (zero latency). Three variants are reported side by side wherever the opening trade is scored:
- **ORIGINAL:** SN382's convention (labels and fill at m).
- **HONEST:** labels (ATM strike, straddle IV, cheap label) and fill at m − 1; exits planned H minutes later at m − 1 + H; the previous session's 15:00 reading at index 344 (14:59:59).
- **LATE:** labels at m − 1, fill and exit as ORIGINAL (a 59-second latency). LATE − HONEST isolates fill timing; ORIGINAL − LATE isolates the label lead.

**Cheap label.** fw9's frozen fixed cutoff (1.2684 vol points) and, beside it, the causal moving tercile recomputed on the same clock. Both reported; neither re-tuned.

**Per-session reporting.** Skips, inadmissible and missed decisions score 0. Every result: per session at ₹205 / ₹400, fills, without the best day, by period (before / from Sep 7, 2026) and by auction source.

## 1. The auditor's slots

### SN396: reconcile the 09:16 signal, quotes and legal fills
- **A. History (gl):** SN382's AUCTION ITM arm and SN394's CHEAP split re-scored under ORIGINAL / HONEST / LATE; how many cheap labels, strikes and admissibility decisions change; per-session net.
- **B. Real quotes vs Breeze (overlap Sep 10 – Oct 28, 2026, non-expiry):** for the ATM and ITM contracts, the archive snapshot nearest before 09:16:00 (provider time) against the Breeze closes of 09:15 and 09:16: which minute the real 09:16:00 mid matches. The archive's walked one-lot ask against gl's modelled ask, and the 10:16 walked bid against gl's modelled bid: the real extra cost per lot at the open, against the ₹205 / ₹400 stresses.
- **C. Forward companions (frozen before any forward P&L):**
  - `fw7b.py` = fw7a + a limit-legal fill (only levels at or below the cap count; a full lot must be available at or below the cap in one packet inside the entry window, else MISSED; packets with a partial lot at or below the cap are counted as PENDING_PARTIAL) + exact-zero gap = NO_SIGNAL + the exit status per stress.
  - `fw9a.py` = fw9 on fw7b + fresh IV (each leg's packet ≤ MAX_AGE old at the clock, call / put receipt times ≤ MAX_SKEW apart, the index packet ≤ MAX_AGE) + the previous **exchange** session (NSE calendar: weekdays minus `market_calendar.NSE_HOLIDAYS_STATIC`); if that session's recording is missing, the baseline is MISSING, never an older day.
  - MAX_AGE / MAX_SKEW: from the Nov 16 recorder copy (plumbing only), the 99th percentile of the ATM CE / PE inter-packet gap 09:15–09:20, rounded up to a whole second, at least 2 s and at most 10 s; written into the file before any forward session is read.
  - Tests: the three reproduced fixtures (64 + 1 units; call at t = 59 / put at t = −50; the 90-second-old quote for fw8a in SN400), exact-zero gap, a pending partial, unresolved exits per stress; the nine fw7a tests still pass.
  - Verdicts: fw7b beside fw7a and fw9a beside fw9, published together.

### SN397: what does "cheap" detect?
- **Cohort:** HONEST auction rows with a reading.
- **Four cells:** CHEAP / OTHER × the auction side / the opposite side, ITM with the same cash rule, 60 minutes.
- **Strata:** sessions to expiry (1–2 vs ≥ 3), after a weekend or holiday vs not, auction source, |gap| below / above its median.
- **Separation:** signed futures follow-through (points, 09:16 → 10:16) by cell; the leg's mid change split into delta × ΔF, vega × ΔIV, theta and residual (SN383's Black-76 method); the admissible share; IV level and time value paid at entry.
- **Family:** every opening rule tried from SN376 to SN396 listed; a White reality check (stationary bootstrap, 2,000 draws, mean block 5 sessions) for the best rule's per-session net at ₹400 against the whole family.
- **Teaches:** whether a cheap open is a better direction, a smaller IV loss, or an affordability effect.

### SN398: weekly-roll days with the same contract
- **History:** Breeze's option downloads hold each weekly expiry only from the session after the previous expiry, so no next-week chain exists on expiry days: checked from the request keys and recorded.
- **Archive (Sep 10 – Nov 13):** on each session after a NIFTY expiry, the new front contract's ATM straddle IV at 09:16:00 against the same contract at the expiry day's 15:00 (it was the next week then). Also the total-variance version (IV² × T). The frozen cutoff applies to the vol-point jump.
- **Measured:** CHEAP labels; whether the auction-side ITM lot is affordable (walked ask, ₹15k room); the trade's net on real quotes (09:16:00 snapshot → 10:16:00 snapshot); the coverable share.
- **Forward:** fw9a records a ROLL reading (the next-week contract on the previous exchange session; the recorder holds three expiries), reported separately and never mixed into fw9a's verdict.

### SN399: a maximum price from the move the forecast can still deliver
- **Contracts:** ATM, 1-ITM, 2-ITM, each admissible under the cash rule (HONEST clock, 09:16).
- **Hurdle H (index points)** = [ask − mid + an exit half-spread (gl's model at the exit) + fees per unit + stress per unit + expected theta over 60 minutes + vega × E(ΔIV)] / |delta|, where E(ΔIV) = the mean 09:16 → 10:16 change of the ATM straddle IV over earlier sessions in the same cheap / other label.
- **Forecast F** = the mean signed futures move in the gap's direction over 09:16 → 10:16 on earlier sessions in the same |gap| half (the GAP sample from Apr 2022 to Dec 5, 2025, then expanding auction sessions).
- **Rule:** buy the admissible contract with the lowest H if F ≥ H; else skip.
- **Compared with fw9's fixed ITM** on the same days: per-session net at ₹205 / ₹400, missed winners, incremental net.

### SN400: does option flow lead futures or follow it?
- **`fw8a.py`** beside the frozen fw8. Strict signing: a trade is signed only if:
  - the prior quote is ≤ FRESH_Q old (fixed from the Nov 16 cadence by the same formula as SN396);
  - the prior quote is not crossed;
  - the volume increment equals the packet's last-traded quantity (one trade);
  - the exchange last-trade time is not before the prior quote's exchange time.
  Otherwise the trade is unsigned.
- **Plumbing (Nov 16):** the strict and original signable shares.
- **Forward judgement (frozen):** an OLS on events of the 15-minute futures return on signed flow, with the prior 10-minute futures return, the option mid revision and unsigned volume as controls. Plus fw8's option trade under strict signing.
- **Verdict:** at fw8's 20 sessions, published with fw8.

### SN401: a second instrument for dates NIFTY cannot serve
- **SENSEX** (gl EXAMS: Oct 2024 – Apr 2026; already seen for buyers), on (a) NIFTY expiry days, (b) days NIFTY's ITM leg is INADMISSIBLE, (c) common days for comparison.
- **Signal:** SENSEX's own index gap (09:15 open against the previous close, |gap| ≥ 0.10%); in the auction era, also NIFTY's futures auction direction.
- **Trade:** SENSEX ITM depth 2 then 1 (100-point steps), lot 20, ₹15k room, HONEST 09:16, 60 minutes, ₹3k stop.
- **Pass:** per-session net > 0 at ₹205 and ₹400 on NIFTY-skip days, and > 0 without the best day.
- **BANKNIFTY:** recorded as blocked if no history exists on this PC.

### SN402: late price discovery after a verified RBI release
- **Dates:** RBI MPC decision days from Apr 2022 to Oct 2026, from RBI's own archive (fetched and listed); release time 10:00 IST unless the archive says otherwise (e.g. the May 4, 2022 off-cycle).
- **Rule:** a decision at release + 6 min (bars to release + 5); direction = sign(NIFTY futures close at release + 5 − close at release − 1), |move| ≥ 0.15%.
- **Filter:** the ATM straddle IV at release + 5 ≤ its value at release − 1 (the event premium has been released).
- **Trade:** buy ITM (cash rule) at the honest fill; hold 30 / 60 min; ₹3k stop.
- **Compared with:** the unfiltered same-side entries, and ordinary days at the same clock with the same move threshold.
- **Bank agreement:** needs BANKNIFTY futures (absent: recorded). Fewer than 20 events = INSUFFICIENT.

### SN403: N10 against N11 inside the same Gold portfolio
- **Six arms** with Gold v5 unchanged at ₹30k:
  - with R0.85: N11 + R0.85 (deployed), NO_STAND + R0.85, N10 + R0.85;
  - without R0.85: N11, NO_STAND, N10.
- **Paths and stress:** 2022, 2023–26 and 2022–26, each at ₹205 / ₹400.
- **Per arm:** net, by year, months positive, worst month, refills.
- **Disagreement log:** the signal keys that differ, Gold's net on suppressed and added trades, and the retry fills (N10 entries not in NO_STAND).
- **Parity:** DEPLOYED 2023–26 at ₹205 must be ₹8,50,882 / 883.

### SN404: were the blocked recovery entries cheap?
- **Cohort:** the stand-aside's suppressions (NO_STAND entries absent from N11), 2022–26 (gl range Apr 2022 on).
- **Measured at the signal's honest clock:** the option ask, time-value share, the ATM straddle IV against the same session's 09:16 IV and the previous 15:00, sessions to expiry, and SN399's hurdle.
- **Compared:** blocked winners, blocked losers and accepted TPB entries.
- **Next step:** if SN399 gives a usable price criterion, one prospective arm is specified (forward only); otherwise this slot closes.

### SN405: one wallet by information time
- **Not triggered as a verdict:** no candidate has passed its own paper gate.
- **Run instead:**
  - (a) Gold-only coverage at ₹30k (2022–26): market sessions, sessions Gold trades, empty sessions, net per market session, and the net per empty session needed for ₹500 / ₹750 per market session;
  - (b) the shared-wallet harness, frozen, on the HONEST cheap-open history rows. Gold has priority; the opener is pre-empted at the model bid when Gold needs the cash; the 20% shared day stop applies; development illustration only.

## 2. Own slots (SN406–SN410)

### SN406: the opening trade's parameter map (HONEST clock)
- **Grid:**
  - entry clock 09:16 / 09:17 / 09:18 / 09:20 / 09:25 / 09:30;
  - hold 15 / 30 / 60 / 90 min;
  - contract ATM / 1-ITM / 2-ITM-then-1 (cash rule);
  - filter: all, CHEAP (frozen cutoff), or the jump's causal 20th / 40th / 50th percentile;
  - stop ₹2,000 / ₹3,000.
  That is 720 cells at ₹205 / ₹400.
- **Reported:**
  - the whole grid;
  - fw9's cell and its neighbours (one step in each dimension);
  - the share of cells > 0 at ₹400;
  - White's reality-check p for the best cell.
- **Learning only.** Only a contiguous region, not a single cell, positive at ₹400 would be named for a future forward test.

### SN407: fw9's frozen rule before the auction existed
- **Sessions:** Apr 2022 – Dec 5, 2025 (no auction rows), non-expiry.
- **Direction:** the index gap (09:15 open against the previous close, |gap| ≥ 0.10%, as SN376).
- **Trade:** HONEST 09:16, ITM 2 then 1 under the cash rule, 60 min, ₹3k stop. CHEAP by the frozen cutoff, and by the causal tercile.
- **Prior stated before running:** SN377's CHEAP gap-side ATM leg made −₹148 a trade at ₹205 over 2022–26.
- **Supports fw9 if:** CHEAP's per-session net is > 0 at ₹205 and ₹400 and > 0 without the best day, ≥ 3 of 4 years are positive, and CHEAP beats OTHER.

### SN408: does a rich option at Gold's entry explain Gold's losses?
- **Trades:** every Gold v5 trade on the 2022–26 path (DEPLOYED stream, ₹30k, ₹205), Apr 2022 on (gl range).
- **Measured at the entry bar:**
  - the ATM straddle IV, and its change from the same session's 09:16 and from the previous 15:00;
  - the time-value share of the bought option;
  - sessions to expiry;
  - SN399's hurdle in points against the ATR.
- **Outcome:** Gold's net per lot at entry (lots0).
- **Reported:** rank correlations, terciles and years.
- **Freeze a log-only forward field (no Gold change)** if the cheapest tercile beats the richest in ≥ 4 of 5 years with Spearman p < 0.05.

### SN409: Gold's clocks
- **Runs:** Gold v5 DEPLOYED (₹30k) on 2023–26 and on 2022, with every N11 entry and exit minute shifted by −1, 0, +1 and +2 minutes, through the stream only (Gold files untouched). 0 must reproduce ₹8,50,882.
- **Teaches:** how much of Gold's history depends on filling at the decision bar's close, and what a one- or two-minute live latency costs. The same for N10 + R0.85.

### SN410: did the September auction change remove the opening edge?
- **Breeze (Dec 8, 2025 – Oct 28, 2026):** the auction gap against the 09:16 → 10:16 futures follow-through (points and as a share of the gap); the match-to-09:16 drift; the ITM trade's delta part against its costs. Before Sep 7 against after.
- **Archive (Sep 10 – Nov 13):** opening spreads and one-lot walk costs at 09:16 against 10:16 and 11:00.
- **Teaches:** whether the post-September opening is priced more efficiently (gap fully in the auction), more expensive to trade, or both. That decides whether the opening family deserves more slots.

## 3. Order of work
1. SN396 → SN403 (the auditor's first two).
2. SN397 → SN399 → SN406 → SN407 → SN410 (the opening family, on SN396's HONEST rows).
3. SN398 → SN401 → SN402 (coverage).
4. SN404 → SN408 → SN409 (Gold).
5. SN400 → SN405 (forward design, then the wallet).

## 4. Amendments
(none yet)
