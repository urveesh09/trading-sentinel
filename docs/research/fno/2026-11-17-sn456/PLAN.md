# SN456–SN475: participant positioning, filings, one pretrained model, transfer, exit depth, real-time capacity, calibration, a duplicate screen, Gold's six-lot exits, forward coverage, FII cash, BANKNIFTY F1 feasibility, the shared-wallet state machine, scorer power, one admission, plus five own slots (plan, frozen before any outcome; Nov 17, 2026 ~15:00 IST)

**Owner (Nov 17):** the auditor's SN456–SN470 handoff (`docs/SN456_SN470_AI_RESEARCH_BRIEF.md`, committed as received in `6f6d9d0f`), with the instruction to start with SN456, SN464 and SN469. Also: "take five more slots for yourself … all the gaps that you can exploit, all the good parts you can extract from our prior strategies … get back to me with the good results."

**Checked before this plan (acquisition and setup only; no outcome computed):**
- **Participant OI archive (SN456 / SN471 / SN473).** `poi_fetch.py` (committed `be1014a6` before running) requested every weekday 2019-02-18 – 2026-10-28 from `nsearchives.nseindia.com/content/nsccl/fao_participant_oi_DDMMYYYY.csv` (public static files, generic client, no cookies; the route SN413 A used for bhavcopies).
  - 2,008 receipts: 1,897 files, 111 × 404.
  - Last-Modified relative to the report date: same day 1,757, next day 75, 2–7 days 16, more than 7 days 49 (re-uploads; availability unknown).
  - 127 titles use date formats my first check did not accept ("Aug 05 2019", `Aug 20,"2019"`); one file (2019-12-12) writes the FII row with Indian thousands separators. The scorer re-parses both (below).
- **NIFTY futures (SN456 / SN458 / SN473 / SN475).** `fut_extract.py` (committed `9cd1ab32` before running) sealed every contract's 1-minute bars to `_local/fut.npz` (sha256 `d61db757…d24845`): 1,888 sessions, 2019-03-01 – 2026-10-28; the source was last modified Nov 16 (no download running). Each contract is stored for about 34 sessions (from about 7 weeks before its expiry), so a 480-bar window on the near contract never needs a roll. March 2022's contract is absent.
- **Kronos (SN458).** Repository `shiyu-coder/Kronos` at `67b630e6` in `C:\Users\Urveesh\sentinel-ml-models\Kronos`; checkpoints `NeoQuasar/Kronos-small` rev `901c26c1` (model.safetensors `b082dfcb…`) and `NeoQuasar/Kronos-Tokenizer-base` rev `0e011738` (`59d85f6a…`), pins in `sentinel-ml-models\hf_pins.json`. einops 0.8.1, huggingface_hub 0.33.1 and safetensors 0.6.2 were added to the research venv only. Speed on synthetic noise: about 1 s per sampled path on 4 threads.
- **SN445's unpriced Gold trades, a correction.** Of the 4 INSUFFICIENT rows, **2** are 15:10 exits (Oct 8, Oct 21; exit index 355). Sep 28 exits at index 135 (11:30) and Oct 14 lacks its entry book as well. The SN441 README's "3 are 15:10 exits" (repeated in the handoff) counted the three 15:10 exits among all ten trades, one of which (Oct 23) priced. SN445 also walked the **initial** lots at the exit, though 3 of the 10 trades had added lots. SN464 resolves both.
- **SN466's source.** NSE's provisional FII/DII cash series is served only through the website API that refused automated access in SN430 (not worked around). NSDL's FPI archive is reachable but is custodian-reported, published about one session late (so two sessions stale at 10:00), through form postbacks, and is not a venue aggregate.
- **Duplicate check on my own slots.** The cheap opener inside Gold's ledger is SN419; I do not repeat it.

**Unchanged rules:**
- Gold v5 at ₹30,000 with immediate entries, signal source, scaling and exits as deployed. Nothing here changes it.
- One bought, fully paid index option; nothing sold or margined; ₹3,000 challenger stop as a trigger; Gold's priority.
- Stress ₹205 / ₹400 a lot plus Zerodha charges.
- Production read only; nothing places an order.
- The forward verdicts (fw5–fw9, fw7c, fx5, SN300a, F1) stay unopened; recorder sessions from Nov 17 stay unread.
- **The NIFTY 2023 expiry-day option chains (the protected expiry exam) are not queried.** Any expiry-day option script asserts its years. SN427's one 2023-12-28 read stays disclosed.
- Every script is committed before it runs; results are written once; crashes are fixed before any number and disclosed in section 4.

**Shared helpers:**
- `ledger10.py`: the two-sided 10:00 ledger on Breeze minutes (gl's sealed `ALL` sample, non-expiry sessions 2023 – Oct 2026). For each date, the CE and PE 1-ITM (else ATM) front-weekly option through `op.leg` on the HONEST clock at m = 45 (label and fill at the 09:59 bar's close), entry ≤ ₹15,000. Exit **legal**: a stop at the first priced minute whose net mark ≤ −₹3,000, else the first priced minute at or after index 104 (the 11:00:00 close) within 5 minutes, else UNRESOLVED. Nets at ₹205 and ₹400. Cached in `_local`.
- `poi.py`: the participant-OI reader (tolerant title date, thousands separators stripped, recomputed sum and balance checks, Last-Modified in IST).
- `fut.py`: the futures reader (asserts the npz hash; near contract = the smallest expiry ≥ the day with ≥ 300 bars that day).

## 1. The auditor's slots

### SN456: new information from participant positioning (first)
- **Report validity:** HTTP 200, the title date (tolerant) equals the requested date, Client + DII + FII + Pro = TOTAL in both Future Index columns, TOTAL long = TOTAL short.
- **Feature:** share(d) = (FII Future Index Long − FII Future Index Short) / TOTAL Future Index Long. x_t = share(t−1) − share(t−2), the two exchange sessions before t, both valid.
  - **Availability:** report t−1 counts at t's 10:00 if its Last-Modified (IST) is no later than t 10:00:00. Last-Modified more than 7 days after the report date is a re-upload and is treated as available (labelled ASSUMED, counted). A late report removes the date from the primary sample (counted LATE).
  - z_t = (x_t − mean) / sd over the previous 60 usable x values (excluding x_t).
  - **Extra-lag sensitivity:** x'_t = share(t−2) − share(t−3), standardised the same way.
- **Target:** y_t = 10,000 × ln(F₁₀₄ / F₄₄) on the near future (the 09:59 bar's close to the 10:59 bar's close: 10:00:00 → 11:00:00). A missing close takes the last close within 3 bars before; otherwise the date drops.
- **Baseline features (known at 10:00):**
  - gap = ln(open₀ / previous close), on the same contract;
  - opening return = ln(F₄₄ / open₀);
  - range = ln(max high₀..₄₄ / min low₀..₄₄);
  - previous session return = ln(prev close / prev-prev close);
  - monthly expiry day, roll window (the last 3 sessions to the monthly expiry) and weekly expiry day flags (weekly expiry dates from the history's distinct NIFTY option expiries, metadata only);
  - vol20 = the standard deviation of the previous 20 close-to-close returns.
- **Models:** ridge, alpha 10, on features standardised with training statistics, plus an intercept. BASE has the baseline features; AUG adds z_t.
  - **Anchored blocks:** the first 250 usable dates train; out-of-sample blocks of 125 usable dates; refit at each block start on every earlier usable date.
- **Primary statistic:** Clark–West f_t = (y − ŷ_B)² − [(y − ŷ_A)² − (ŷ_B − ŷ_A)²] over every out-of-sample date. One-sided p from 2,000 circular block-bootstrap resamples (block 20, seed 456) of the recentred mean.
- **Improvement holds (all four):**
  1. CW p < 0.05;
  2. a within-quarter permutation of z (500 permutations, seed 4560, full refit) gives p_perm < 0.05;
  3. the CW mean is > 0 in at least two thirds of the out-of-sample blocks;
  4. the CW mean is > 0 on dates outside the roll window.
- **Reported regardless:**
  - eligible, late, assumed and missing files; matched dates;
  - MSPE of both models; sign hit of both;
  - the out-of-sample partial correlation of z with y beyond gap and opening return;
  - the extra-lag result;
  - results without month-end ±2 sessions and without contract-mix break dates (TOTAL Future Index Long changing more than 30% from the previous valid report);
  - alpha 1 and 100.
- **Option stage (only if the improvement holds):** on ledger10's dates with out-of-sample forecasts, trade sign(ŷ_A) when |ŷ_A| ≥ the 70th percentile of that block's in-sample |fitted ŷ_A|, at the ledger's side price.
  - **Same rule on ŷ_B,** and a seeded coin (seed 4561) on the same dates.
  - **Per decision and per market session,** both stresses, without the best day.
  - **Promising** only if AUG is positive at both stresses, beats BASE and the coin at ₹205, and stays positive without the best day. Otherwise the slot closes.

### SN457: what changed in the filing (the deterministic parser first; the model arm bounded)
- **Parser:** a standard-library iXBRL reader (`ix:nonFraction`: name, contextRef, unitRef, decimals, scale, sign; contexts give period and standalone / consolidated) on the handoff's Banking Integrated Filing example (fetched once from nsearchives, hashed).
  - **Report:** issuer, period, entity scope, unit and scale, interest earned, interest expended, NII, and the year-ago comparison when the filing carries it.
- **HDFC Bank December 2025 fixture:** ₹32,615.00 crore standalone NII against ₹30,653.25 crore (+6.40%), consolidated ₹41,245.52 crore. Checked against the SEC exhibit if it can be fetched with a generic client; otherwise BLOCKED for that fixture (no contact details are sent).
- **Model arm:** the session's model (this agent) reads the same bounded parsed text and writes one cited comparability caveat about the interest components, or UNKNOWN. The citation is checked mechanically: the quoted span must occur verbatim in the document. Latency is not meaningful for an in-session reader and is reported as such.
- **Forecast comparison:** INSUFFICIENT by construction (SN447's 8 reaction sessions are development fixtures; no new session has accrued).

### SN458: one fair test of a pretrained market model (Kronos-small, zero-shot)
- **Dates:** futures sessions 2024-07-01 – 2026-10-28 (after Kronos's June 2024 training boundary) whose near contract has every 1-minute bar in each of the last 480 five-minute bars to 10:00 and in today's bars to 10:30.
- **Input:** five-minute bars aggregated from 1-minute bars (bar k = minutes 5k..5k+4, 09:15–15:30 only, 75 a session; the post-15:30 bars from Oct 6, 2026 excluded).
  - Columns: open, high, low, close, volume (summed); amount = volume × mean(OHLC), Kronos's own proxy, recorded.
  - Timestamps: bar starts.
  - The context is the 480 bars ending with today's 09:55 bar.
- **Forecast:** 6 steps (10:00–10:25 bars). 8 draws per date with the reference sampler (T = 1.0, top_p = 0.9, top_k = 0), the draws kept individually by a wrapper that copies `auto_regressive_inference` and stops before its average, torch seed 458000 + the date's ordinal, 4 threads.
  - r̂_K = the mean over draws of ln(pred close₅ / last context close).
  - P̂_K = the share of draws with |r| ≥ θ.
- **Target:** r = ln(F₇₄ / F₄₄) (10:00:00 → 10:30:00). Event: |r| ≥ θ = 13 index points / F₄₄ (SN448's ₹400 one-lot hurdle for a 30-minute ATM move).
- **Arms:**
  - ZERO (r̂ = 0);
  - RIDGE: ridge, alpha 10, on the same context (the last 1 / 3 / 6 / 12 bar returns, today's open-to-10:00 return, gap, the context's 5-minute return SD), anchored and trained on 2019-07 – 2024-06, refit every 60 test dates;
  - VOL: P(|r| ≥ θ) under N(0, σ̂²), σ̂ = the SD of the previous 60 sessions' 10:00 → 10:30 returns; RIDGE's own event probability under N(r̂, σ̂²).
- **Metrics:** paired by day with 2,000 block-bootstrap resamples (block 20, seed 458):
  - return MAE (primary; MSE reported);
  - event Brier;
  - sign hit;
  - correlation.
- **Adds forecast value only if:** Kronos's MAE beats both ZERO and RIDGE AND its Brier beats VOL, each with the 90% CI of the difference wholly favourable. Otherwise STOP (no architecture grid). A pass nominates only a forward comparison on dates after this freeze.

### SN459: transfer to SENSEX (conditional)
Runs only if SN456's improvement holds (or SN457 yields a tested feature). Otherwise NOT_RUN, with the reason.

### SN460: usable exit depth on qualified entries
- **Events:**
  - every FNO_PAPER NIFTY position in the sealed export (Sep 10 – Nov 13) that closed on a stop, with its trigger time;
  - Gold's 6-lot replay stops inside the archive.
- **State at the trigger (the archive's one-a-minute snapshots, causal):** spread, best-level and 5-level bid quantity, quote age (seconds since that contract's previous usable snapshot) and the volume change over the previous 5 snapshots.
- **Labels:**
  - the time to the first usable snapshot after the trigger whose 5-level bid holds the requested quantity;
  - the extra loss of that walked bid against the trigger mark;
  - fw2's buckets (on time / late / unresolved).
- **Classifier:** a first-snapshot rule, a depth rule and a small logistic model are compared **only with ≥ 30 independent stop dates**. Otherwise INSUFFICIENT with the label table, one lot against the scaled request, and the Nov 16 packets against its minute snapshots (plumbing only).

### SN461: decision-time capacity under Gold's priority (no candidate P&L)
- **Sessions:** every NIFTY futures session 2022-01-03 – 2026-10-28.
- **Gold:** its replay path (DEPLOYED, ₹205; 2022 and 2023–26 runs).
- **At the 10:00 clock (11:00 and 13:00 also):**
  - OPEN: a Gold position filled at index ≤ m − 1 and exits at ≥ m;
  - PENDING: a Gold fill at index m (its signal bar closed at the clock, filled 59 s later);
  - CLEAR: otherwise;
  - OUTSIDE: not in Gold's replay (expiry days, specials, data holes).
- **Attribution over the 10:00–11:00 interval:**
  - a Gold entry during it;
  - a Gold entry only after it;
  - Gold entered and closed before it;
  - no Gold entry all day.
- **Reported:** decision-time capacity (CLEAR) against the hindsight gap days (no Gold entry all day), by year, with expiry eligibility and missing quote windows (ledger10 coverage) as their own blocks.

### SN462: score calibration against cash
- **Scores:** SN456's out-of-sample ŷ_A and ŷ_B (filed chronologically before each outcome).
- **Bins:** quintiles of |ŷ| from each block's in-sample fitted values. Per bin on ledger10's dates:
  - directional hit;
  - mean y;
  - after-cost net of trading sign(ŷ) at both stresses;
  - priced share, unresolved share, worst decile.
- **Coverage point:** 30%.
- **Comparator ranking (same side choice, same count):** the nearest expiry first, then the lowest modelled spread share of premium.
- **Also:** the net-per-market-session curve for coverage 10–100%; a split-conformal 80% interval's coverage by vol20 tercile (diagnostic, no guarantee claimed).
- **No threshold is chosen from these results.**

### SN463: a duplicate screen before simulation
- **Registry:** one row per SN result in `docs/SN_STRATEGY_HISTORY.md` (number, text, the section's folder).
- **Plain search:** TF-IDF cosine, top 5.
- **Check set** (committed in `sn463.py` before scoring): 14 queries with their expected matches, including the handoff's four pairs (SN443 / SN453 discount; SN444 / SN454 fills; SN09 option OI against the participant reports, expected NOT a duplicate; SN447 timing against structured filing content, expected a partial match).
- **Structured pass:** the session's model fills mechanism fields for the check set in the same commit, before scoring.
- **Reported:** recall@5, wrong and missed duplicates, invalid citations (a cited SN whose folder or history row does not exist). The structured pass is not independent of the check set (the same model wrote both), and is reported as such.

## 2. The follow-ups

### SN464: why Gold's six-lot exits were missing (first)
- **Rows:** all 10 SN445 trades, re-derived through SN445's hooked run (parity: ₹8,50,882 / 883).
  - Per trade: instrument, dated lot (65), the initial and the held lots at the exit (adds and pieces from Gold's log), the scheduled exit index j, the arrival at snapshot j + 1.
- **States per snapshot (raw archive records), j + 1 to j + 6:**
  - FEED_STOPPED: no record for any contract that minute;
  - INSTRUMENT_ABSENT: others recorded, this contract not;
  - NOT_USABLE: depth state ≠ USABLE, crossed or locked;
  - ZERO_BID;
  - PARTIAL: 5-level bid < the held quantity;
  - FULL.
  The entry side gets the same treatment.
- **For captured books:**
  - requested against available units; the walked cost of what is available;
  - the time to the first FULL snapshot within 5 minutes and to the session's end;
  - a partial-exit lifecycle (V8 style: sell what the 5 levels hold at each usable snapshot until done), with the quantity still open at 5 minutes and at the session's end.
- **Reported:**
  - the original 6 of 10, kept;
  - the observed cost against the model;
  - a no-recovery scenario (unsold units lose their premium).
- **SN460's predictive work** applies only if this audit finds ≥ 30 observed hard exits.

### SN465: does the forward queue cover different gap days (after the verdicts)
DEFERRED until each frozen scorer has issued its scheduled verdict. The ledger's columns are fixed here:
- date and scorer;
- eligible / observable / captured / traded;
- unique sessions added to Gold;
- non-qualifying versus unobserved;
- pairwise date overlap;
- shared move / contract / clock;
- for fx5, both original controls and the missed winners.

No score threshold and no live arm.

### SN466: foreign cash flow beside the futures position
BLOCKED as specified (no consistent venue aggregate is publicly obtainable before 10:00 without the refused NSE API). The NSDL substitute's lag and definition are recorded for the owner. Nothing is joined to prices.

### SN467: can BANKNIFTY F1 collect enough events
- **Development fixtures only (F1 stays frozen, no P&L):**
  - BANKNIFTY's dated lot and monthly expiry calendar;
  - SN413 A's affordability by days to expiry;
  - F1's trigger rate from SN414b's comparable cell;
  - Gold's OPEN share at F1's clocks (SN461);
  - the recorder budget.
- **Expected verdict:**
  - sessions after deployment to 30 qualified triggers;
  - the chance of INSUFFICIENT (< 15 fills) at the 120-session cap (Poisson);
  - qualified triggers per monthly expiry cycle.

### SN468: a competing Gold signal through the shared-wallet state machine
- **What:** `wallet_sm.py`, an event-driven ledger with the companion's order states (PENDING_ENTRY, OPEN, PENDING_EXIT, PARTIAL, CLOSED, UNRESOLVED).
  - Cash leaves at a fill and returns only at a simulated exit completion, with costs booked once.
  - A Gold intent spends only free cash (no simultaneous reuse of proceeds).
  - A blocked Gold intent waits for the companion's exit (DELAYED) or lapses after 60 s (MISSED).
  - No forced sale at an invented bid; the session's end leaves an open lot UNRESOLVED.
- **Fixtures (`test_wallet_sm.py`):**
  - a Gold intent during a pending exit;
  - a partial fill;
  - a stale or absent bid;
  - duplicate packets;
  - simultaneous timestamps;
  - the session boundary.
  - Invariants: cash never negative, never double-counted, costs once.
- **Application (development):** SN419's opener days replayed through the machine for the count of Gold intents that would have been DELAYED or MISSED by cash, against SN419's assumption of selling at that minute's bar.

### SN469: can the test detect an edge of the intended size (first)
- **Books:** SN441's common two-sided cells (SN412 archive, real walked books, legal exits). Synthetic sessions resample the 37 dates.
- **Generator:**
  - an observable predictor fixes the favoured side before the decision;
  - the favoured side's ask and bid after entry are raised by δ × (t − e) / (x − e) up to the exit (δ after it);
  - the scorer (`sn441.legal`, then per-session sums) never sees δ or the label.
- **Truth:** each scenario's mean net per market session from 100,000 generator draws.
- **Scenarios:**
  - μ = 0 (null), +₹50 (a small supplement), +₹154 (the wage gap) per market session at ₹205;
  - coverage 30% or 100%;
  - one clock, or 3 clocks a day sharing the day's side (within-day dependence);
  - stresses: 20% of snapshots blanked after entry (stale or absent quotes; unresolved = premium lost), and the edge in 5% of trades at 20× size (a few large winners).
- **Horizons:** 20 / 60 / 120 / 250 / 500 sessions, 1,000 replications each (seed 469).
- **Rules:**
  - (i) the 90% block-bootstrap CI wholly above 0;
  - (ii) SN449's rule (CI wholly above ₹154);
  - (iii) fw7a's point rule (≥ 15 fills, positive at both stresses, positive without the best day).
- **Reported:** false positives, recovered mean against the truth, and the detection rate.
- **Design check:** a horizon whose detection is below 80%, or whose recovery bias exceeds 20%, needs a different verdict design before any reserved sample is opened.

### SN470: admit at most one candidate
- **New mechanisms:** a candidate advances only if it passed its data and forecast screen this round (SN456's option stage, SN458, SN471). It is frozen with signal, universe, one-lot capped order, exit, costs, expiry rules, fills and verdict horizon (from SN469's power), then run through SN450's protocol.
- **If no screen passes:** NOT_TRIGGERED.
- **Already-frozen candidates:** the cheap opener (fw9 / fw9a / fw9b), the packet candidates and fx5 continue on their own schedules.

## 3. Own slots

### SN471: positioning and Gold's own trades (a better decision on an identified opportunity)
- **Data:** Gold's replay trades in 2022 and 2023–26 (DEPLOYED, ₹205), each with its side and net.
  - z_d: SN456's primary feature for the trade's day (the prior-session report, known all day).
  - AGREE = (CE and z > 0) or (PE and z < 0).
- **Statistic:** the mean net per trade AGREE − DISAGREE, by period.
  - **CI:** 2,000 date-block resamples (seed 471).
  - **Placebo:** 200 circular shifts of the z series by 20–219 sessions.
- **Worth a forward look only if all hold:**
  - the same sign in 2022 and 2023–26;
  - the pooled CI excludes 0;
  - above the placebo's 95th percentile.
- **Gold is not changed either way.**

### SN472: the power of every scheduled forward verdict
- **Method:** SN469's machinery at each verdict's own horizon and point rule.
  - **fw9a:** 15 fills or 60 sessions; fw7a's judge without the ATM control, so the pass rates are upper bounds.
  - **SN300a:** 20 sessions with ≥ 30 trades; net > 0 at both stresses, positive without the best session, the pair difference > 0.
  - **fx5:** 60 decisions; the candidate's paired difference against both controls > 0 at both stresses.
  - **F1:** 30 triggers; positive at both stresses and without the best 5 days.
- **Outcome distributions:** resampled from real legal nets (SN441's one-hour cells; SN444's paired mechanics for fx5), recentred to the true per-trade edge.
- **Reported:** P(PASS) at a zero true edge, at the edge the candidate's development claimed, and at the wage level.

### SN473: where the positioning information goes
- **Correlations of z_t** (90% block CI) with:
  - the overnight gap (previous close → open);
  - open → 10:00;
  - 10:00 → 11:00;
  - 11:00 → 15:15 (F₁₀₄ → F₃₅₉).
- **The popular "FII long ratio" rule:**
  - L = FII Future Index Long / (Long + Short); its causal expanding percentile (≥ 250 prior reports);
  - LONG at ≤ 10%, SHORT at ≥ 90%;
  - hit and mean of the next session's open → close and of the next 5 sessions' open → close.
- **A mechanism check, not a trade.**

### SN474: Gold's exit clock against liquidity
- **(a) Archive depth:** on the 42 sealed days, for the front-weekly ATM and 1-ITM CE / PE at 15:00 / 15:05 / 15:10 / 15:15 / 15:20, the share of usable snapshots whose 5-level bid holds 65 units and 390 units, the median bid depth and the spread.
- **(b) Gold replay:** Gold's time exit moved from index 355 (deployed) to 345 / 350 / 360, in 2022 and 2023–26 at ₹205 and ₹400 (the module constant patched for the run, Gold's files untouched).
- **An earlier exit is worth proposing only if:**
  - it costs < 2% of Gold's net in both periods; and
  - its full-depth share is ≥ 10 points better.
  Otherwise 15:10 stays.

### SN475: the forecast skill a ₹30k option buyer needs
- **Data:** ledger10's priced dates (both sides), with y_t from SN456's target.
- **Synthetic forecasts:** f = ρ z(y) + √(1 − ρ²) ε, with:
  - ρ ∈ {0, 0.02, 0.05, 0.08, 0.10, 0.15, 0.20, 0.30};
  - 200 noise seeds each (seed 475).
- **Trade sign(f):** on every date, and on the top 30% of |f|.
- **Reported:**
  - net per decision and per market session at both stresses;
  - the ρ where net crosses 0 and where it reaches ₹154 per market session.
- **Against:** SN456's and SN458's realised out-of-sample correlations, and SN193's LSTM.
- **A design tool:** f uses the realised y by construction; it is never a strategy.

## 4. Order
SN464 → SN469 / SN472 → SN456 (with SN473 / SN471) → ledger10 → SN475 / SN462 → SN458 → SN461 → SN467 → SN468 → SN460 → SN463 → SN457 → SN466 / SN465 / SN459 → SN470.

## 5. Amendments (added after freezing; disclosed)

### A1. Details fixed in the scripts before their runs (each script committed before it ran)
- **SN464:** the raw-record minute states; the HELD quantity at the exit (Gold's entry pieces), with SN445's initial-lots result recomputed beside it. An unused helper was removed before the first run.
- **SN469:** the 98 common cells are rebuilt and asserted (98 on 37 dates). "Truth" is the label-based scheduled-exit net plus the injected drift. Because days carry different numbers of cells, the realised truth differs slightly from the nominal μ (reported beside it). The bootstrap uses 300 resamples per replication.
- **SN472:** COIN is the only modelled control (ATM, the two other F1 controls and F1's reversal t are not modelled), so the pass rates are upper bounds. SN300a's FLAT test uses the archive's EMPTY label; fx5 uses SN444's one-morning rows.
- **SN456:** the scorer re-parses titles tolerantly and strips thousands separators. One title remained invalid.
- **SN458:** 8 draws a date (CPU: about 1 s a path), one date per call so each date has its own seed. A bar needs all five 1-minute bars. A junk line was removed before the first run.
- **SN473:** two junk lines were removed before the first run.
- **SN463:** the table-row SN parser was simplified before the first run. The LLM arm was not run, because the same model wrote the check set.
- **SN474:** the 15:15 arm moves only the extension's end (N11's own 15:10 time exits are unchanged). Depth uses non-expiry archive days only.
- **SN457:** the handoff's "iXBRL" example is NSE's rendered web view, so the parser reads its rows. The SEC request used a generic placeholder client with no personal details.
- **SN460:** the trigger time is the position's exit_time (no separate trigger clock is stored). The labels sit on the archive's one-a-minute raw records.
- **SN466:** recorded from the pre-plan probe; no script.

### A2. Disclosures
- **SN471 post-hoc:** `sn471_posthoc.py` (the split without the largest trades) was added after SN471's verdict. It cannot change that verdict.
- **SN474 commit message:** the message for `results-sn474.json` says "38 archive days". The depth sample is **33** non-expiry days (116–120 contract snapshots per clock). The result file is correct.
- **SN457:** `matches_32615 = false` is an artefact of Python's float rounding (round(326.15, 1) = 326.1). Half-up rounding gives the exhibit's 326.2, so the fixture matches. Not rerun.
- **Stray command:** a stray `python -` in an exploratory shell command waited on stdin and was stopped. No file was touched.
