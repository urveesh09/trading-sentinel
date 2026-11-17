# SN476–SN490: Gold v5 against its own weaknesses (plan, frozen before any number)

**Owner (Nov 17, 2026):** the auditor's ten slots (`BRIEF.md`, a byte-exact copy of the untracked
`docs/research/fno/2026-11-17-gold-v5-next-ten/HANDOFF.md`, sha256 `c4b13a03…a28deb1`) plus five own slots, "thorough testing, no half
work". Slot numbers: the auditor's 1–10 are **SN476–SN485**; own slots **SN486–SN490**.

## 0. Baseline, ledgers, discipline

- **Baseline = Gold v5 unchanged** (`sn-gold/SN_GOLD_V5.json`; runner `2026-11-17-sn411/gold.py`, wiring sn403 → sn392 → sn366_gold → gw/ow;
  parity DEPLOYED 2023–26 @₹205 = ₹8,50,882 / 883). Known: 2022 −15,281 / 2023–26 +8,50,883 @205; −23,511 / +4,95,597 @400 (₹30k start).
- **Ledgers** (each candidate gets its own verdict in each):
  - `GOLD_30K` = Gold's growth wallet from ₹30k, losing days refilled; total refills reported as deposits ("funded reserve");
  - `SELF_30K` = the same wallet without deposits: W += day net, lots = floor(W / 15k) (≥ 1 while W ≥ ₹7,500, else flat) — the lab's
    `float` kind, ₹30k start, no growth steps (declared here as the "without funded reserve" ledger);
  - `ONE_15K` = ₹15k one lot (the lab's `A 15k 1 lot`).
- **Paths:** 2022 (SN366 data), 2023–26 (development); 2020–21 only in SN482 / SN490. **Stress:** ₹205 and ₹400 per lot per trade.
- **Every date here is seen** (2022–26 by Gold's own research; 2020–21 by SN251–SN272's option-buyer studies, but Gold itself has never
  been run there). Nothing in this round can qualify live; a passing change goes to the forward contest (SN485) only.
- Freeze-then-score: this plan is committed before any number; every script is committed before it runs; results are written once;
  details fixed later go in section 5 (amendments) before the number they affect.
- Untouched: Gold's frozen files, `n08_lab.py` (byte-identical), hashed policy files, the NIFTY 2023 expiry-chain exam (no price
  query), the sealed forward verdicts (fw5–fw9b, fx5, F1, SN300a), Production (read-only through a throwaway container with the data
  volume mounted read-only, as `export_fno_replay_dataset.py` does), Breeze (read-only counts of the history database, no downloads).

## 1. The auditor's slots

### SN476 — Runtime Gold against replay Gold (brief slot 1; first)
- **A. Live join.** Production `cache.db` (read-only): every `fno_n11_paper` row (source `N11_PAPER`) from `sn_gold_wallet.started`
  onward → its `sn_gold_positions` row, its `sn_gold_skips` row, or a documented reason (not recorded by N11's paper planner, expiry
  day, engine off); every NIFTY N11 evaluation in `fno_signals` for those sessions tabulated by reason. A paper row with neither a Gold
  row nor a skip is a DIVERGENCE. Wallet / day rows must reconcile (day net = Σ position nets; refills; steps).
- **B. Pre-start shadow.** The N11_PAPER rows before Gold's start (Nov 2–11) through the runtime's pure rules (`sn_gold.pick_contract`,
  `lots_for`, `day_stop`) on the quote archive's snapshot nearest the paper entry: contract, lots, stop, affordability. Shadow only.
- **C. Signal sets.** RUNTIME stream = N09's one-lot brakes-off paper twin (DIAG evals; the historical analogue of `fno_n11_paper`)
  with the runtime gate on each signal: stand = not vol_up(atr, usual, 0.85) and ≥ 20 earlier paper exits and their last-20 sum ≤ 0
  (`fno_n11.stand_aside`; paper history = the DIAG trades the research's own R0.85 read for that path: 2023–26 DIAG for 2023–26,
  2021L + 2022 DIAG for 2022; exits strictly before the signal); N11's exit minute from the DIAG trade. Keys (entry minute, strike,
  call) against DEPLOYED (N11 ∪ R0.85): both / union-only / runtime-only, by year; then Gold v5 on RUNTIME vs DEPLOYED, both paths,
  both stresses, GOLD_30K.
- **D. Runtime-faithful execution.** DEPLOYED stream; the stop triggers only on a minute's close bid (bc[j] on a traded minute, else
  the mark) and fills at that bid (the live tick samples the bid about once a minute and books the sale there), instead of the bar's
  bid low with a fill at min(stop, open bid). Everything else unchanged.
- **E. Pure-rule parity.** On every Gold replay trade's logged inputs: `lots_for` vs the lab's size rule, `itm_depth` vs itm_auto,
  `day_stop` vs the lab's first stop, `scale_in_stop` vs the lab's add stop, `position_net` vs the lab's per-piece net (shipped charges +
  ₹205), `grow` vs the lab's growth. Differences > ₹0.01 listed. Plus a code-reading table of the structural differences.
- **Pass:** every eligible live decision matched or documented; E reconciles or each mismatch is explained; C / D quantified; a fix
  proposal (Dev only) for any reproducible divergence.

### SN477 — Record the held contract until it is closed (brief slot 2)
- Dev change to the tick recorder: subscriptions = its rolling ATM window ∪ the tokens of every OPEN Gold / N11-paper / F&O paper
  position (and a pending entry), kept until the row is CLOSED or UNRESOLVED; pinned tokens count against the existing cap and are never
  the ones dropped; re-subscribed after a reconnect; a pinned contract survives the expiry roll until its exit.
- Tests: reconnect, roll, cap, a feed outage stays an outage. Trace check on SN464's two deep-ITM exits (Oct 8 22600 PE, Oct 21
  23100 PE): the window at exit excluded the strike; the pinned set includes it. **Pass:** both selection gaps recovered on the traces,
  all tests pass, cap respected. Deployment is the owner's word.

### SN478 — The same entry, sooner (brief slot 3)
- Live latency: per N11 paper row, entry time − (bar_ts + 5 min); per NIFTY N11 evaluation, `evaluated_at` − bar end.
- Replay latency: Gold stream entry minute − the bar-end minute (+59 s = the first minute close after the bar completes; the replay's
  observations are minute closes). Diagnostic for each later entry: was the stream contract's minute candle at the bar-end minute
  without volume (a stale quote in a minute archive, not a live delay)?
- **FAST arm:** every stream entry later than the bar-end minute moves to the bar-end minute (same contract, side and N11 exit); kept
  where that minute has no quote (counted). Causal: the bar is complete at bar end and live acts in about 31 s (median of the live rows).
- Archive check: the live paper rows' asks against the archive's minute asks at +59 s / +119 s.
- **Pass:** paired net higher at both stresses in both paths, no extra missed winner (trades lost or changed are listed).

### SN479 — The recoverable part of stop slippage (brief slot 4)
- Sample: Production F&O paper stop exits (underlying_stop, premium_backstop, trail_stop; Gold has none yet) on days with packet-level
  data (the quote archive's raw records, the recorder copies). Trigger clock T = the order time; trigger level = the position's stop
  level in premium terms where stored, else the trigger snapshot's bid.
- CURRENT = the first usable full bid after T + 0.5 s (fw2's rule); STOP_LIMIT = a packet-driven sell limit at trigger − max(₹0.50, 1%)
  placed at the first packet whose bid ≤ trigger, filled when a later packet's bid ≥ limit with depth for the quantity; after 5 s a
  market fallback walks the book. Decomposition: (i) the move from trigger to the earliest allowed bid; (ii) the delay cost the
  current path adds beyond (i). Cancel races, partial fills and trigger-without-fill counted; sold quantity never exceeds held.
- **Pass:** positive paired net on the triggered cases with a 90% CI above zero and no larger loss tail; otherwise INCONCLUSIVE.

### SN480 — Sell a failed add, keep the original lots (brief slot 5; first)
- **Rule (one challenger).** Gold v5 unchanged, plus: after an add fills at minute j_a, if at a later minute's close (j > j_a) the
  future has closed through the original entry level against the trade, (c[j] − c[i])·d < 0, and the whole position does not exit at
  j, then the added lots are sold at minute j + 1's executable bid (close bid if traded, else the mark), unless the whole position
  exits at j + 1 (stop, N11 exit or the extension's trail take precedence). The original lots keep Gold's exits; their stop becomes
  max(original stop, ceil_tick(e0 − (room + realized − fees0) / q0)) so the day's loss room still holds after the add's result is
  booked. No second add. The challenger pays an extra ₹23.60 a failed-add sale (₹20 brokerage + GST): the replay already charges each
  piece its own sale, so this makes the separate order explicit.
- Ledgers GOLD_30K / SELF_30K / ONE_15K; paths 2022, 2023–26; ₹205 / ₹400.
- Reported: net, by year, paired daily difference (90% circular block bootstrap CI, block 20 sessions, 10,000 draws, seed 476), worst
  day, sum of losing days, worst month, refills, the top-5 Gold days under both, failed-add sales (count, add net under both), the
  difference without the single most affected session, sold quantity ≤ held quantity and cash ≤ wallet (asserted).
- **Pass (return):** paired net > 0 at both stresses in both paths on GOLD_30K and still > 0 without the most affected session.
  **Pass (risk):** worst day and losing-day sum smaller at both stresses in both paths while keeping ≥ 90% of Gold's 2023–26 net at
  both stresses. Else FAIL. A pass is development evidence and goes to SN490 / SN485.

### SN481 — The same signal in next week's option (brief slot 6)
- Frequency: Gold's trades on non-expiry days with one or two sessions to the front expiry, 2022–26 (count, share of net, by stress).
- Coverage: whether the next weekly exists in the Gold datasets / the Breeze history (counts only).
- Pricing where both expiries are recorded (the quote archive, Sep 10 – Nov 16 2026): same side; next-week strike with |Δ_next − Δ_front|
  ≤ 0.05 (Black-76 deltas from the archive mids, the front future, ACT/365 to 15:30 on expiry); one lot, affordable under the same cash;
  same exit minute; walked asks / bids. **Pass:** better net at both stresses counting unavailable pairs, no worse tail; with < 20 pairs
  it is INSUFFICIENT and the acquisition need is stated.

### SN482 — Unchanged Gold through 2020–21 (brief slot 7)
- Inventory (read-only counts of the Breeze history): NIFTY index / future / option coverage by month, Jan 2020 – Aug 2021.
- Build the covered months through SN366's route (`n08_shim` points added in memory, `n08_lab.py` untouched, N09's `vol_table`
  repointed to the new daily bars — the SN366 trap): mirror, daily, export, warm, N09 DIAG paper twin, the N11 and R0.85 panel books.
- Gold v5 unchanged: `ONE_15K` first, then `GOLD_30K` from ₹30k at the window start, ₹205 / ₹400; current-lot (65) view as the
  primary (Gold's harness rule for every year so far) and a dated-lot view (NSE's lot of the day) beside it; coverage and exclusions
  disclosed. **Pass:** an interpretable comparison with high coverage and lower-tail numbers at ₹400.
- Every candidate scored on these dates is frozen before this run (SN490).

### SN483 — Oil and the rupee as Gold's risk input (brief slot 8)
- Data: Brent (FRED DCOILBRENTEU; ALFRED first-release dates if obtainable) and USD/INR (FRED DEXINUS, or FBIL's reference rate if a
  static archive is obtainable), fetched once with a generic client, hashed. Availability: by first-release date where known; else a
  conservative lag declared before joining (Brent from the IST session after the Thursday following the observation; DEXINUS from the
  IST session after the Tuesday following its week; FBIL from the next IST session).
- Joint stress = z(|Δlog Brent|) + z(|Δlog USD/INR|) on the latest available day (z over the previous 60 values).
- Targets on Gold's 2022–26 replay trades: stop exit (yes / no) and the next-60-minute adverse excursion of the future in entry-ATR
  units; for trades with an add, the add's net. Baseline: gap, volatility ratio, expert, side. Leave-one-year-out logistic / ridge;
  increment = AUC / MSE change, per year.
- Only if the increment is positive in ≥ 4 of 5 years: one reduction, skip the add when joint stress ≥ 1.0, scored as a Gold variant.

### SN484 — A slower, cash-funded trend benchmark (brief slot 9)
- NIFTYBEES long-or-cash: at each month end, hold next month if the 12-month total return of NIFTY 50 (TRI if obtainable, else
  NIFTYBEES's own price as the proxy, declared) is > 0, else cash (0% in the primary, 5% a year as a sensitivity); trades at the next
  session's close; whole shares; Zerodha delivery charges (₹0 brokerage, STT 0.1% each side, stamp 0.015% buy, exchange, SEBI, GST,
  DP ₹15.34 + GST a sell day) and 0.05% spread a side.
- Against buy-and-hold NIFTYBEES and cash; ₹30k start, and separately with Gold's own deposit schedule (2023–26 @205 refills on
  their dates); compounded return, spendable P&L, drawdown, over 2022–26 and the longest available history.
- **Pass:** better return for its drawdown than both simple benchmarks after costs.

### SN485 — One funded forward contest (brief slot 10)
- Contestants: Gold v5 and the strongest survivor of this round (SN490's rule), else Gold alone. Fresh sessions from the first session
  after the scorer is committed; same ₹30k, ledgers GOLD_30K / SELF_30K and a fixed one-lot view; one ledger per contestant, paired by
  day; prices from the recorder / archive; missing prices counted.
- Duration set before looking from SN488's paired variance and Gold's trade frequency; verdict once at that count: **return upgrade**
  if the 90% CI of the paired daily difference lies above zero at ₹205 and ₹400 with no worse worst day / drawdown / funding; **risk
  upgrade** if the stressed loss tail is smaller at the declared 90% retention; else INCONCLUSIVE / FAIL.

## 2. Own slots

### SN486 — The failed-add rule's neighbours
- θ ∈ {+0.5, 0, −0.5, −1.0}: the adds are sold when the future closes through c[i] + d·θ·atr[i] against the trade (θ = 0 is SN480);
  plus SN480 with the same-minute bid (Gold's own exit convention) as an execution sensitivity. **Plateau-stable** only if all four
  θ have the same sign of paired difference in both paths at both stresses (GOLD_30K).

### SN487 — Where Gold's money comes from
- Gold's trade log, 2022 and 2023–26 at ₹205 / ₹400: first-lot pieces, added pieces, the extension's contribution, fees and stress; by
  expert, side and year; the top-5 days' composition; add count and add win rate. Learning only.

### SN488 — Gold's uncertainty and the forward contest's length
- Circular block bootstrap (block 20 sessions, 10,000 draws, seed 488) of Gold's daily P&L over every replay session (zeros included),
  2022–26, ₹205 / ₹400: annual net distribution, P(year < 0), longest stretch without a new high, worst drawdown from ₹30k.
- For each candidate's paired daily difference (SN478, SN480, SN489): mean, SD, lag-1..5 autocorrelation and the sessions needed for a
  90% CI to exclude zero at the observed mean (block-adjusted). Feeds SN485.

### SN489 — Adds by expert, chosen honestly
- Per expert in Gold's stream: Gold with that expert's adds switched off, paired with Gold, per year, ₹205 / ₹400.
- Rule chosen by leave-one-year-out over 2022–26: on four years keep adds only for experts whose add contribution is positive in total
  at ₹400; apply to the held-out year; the honest estimate = the sum of held-out paired differences. If positive at both stresses, the
  rule chosen on all five years is frozen for SN490; else the slot ends there.

### SN490 — The round's candidates on 2020–21 (frozen holdout)
- On SN482's data, once: SN480's challenger, SN478's FAST and SN489's rule (if it qualified), each paired with Gold v5, ₹205 / ₹400,
  ONE_15K and GOLD_30K. **Strongest survivor** = the largest ₹400 paired gain on 2020–21 among candidates positive in 2022, 2023–26
  and 2020–21 at both stresses (GOLD_30K); at most one advances to SN485.

## 3. Order of work

SN476 → SN480 → SN486 → SN487 → SN489 → SN478 → SN488 (development numbers; candidates frozen) → SN482 + SN490 (one run) → SN481 →
SN479 → SN477 → SN483 → SN484 → SN485.

## 4. Outputs

`results-sn4NN.json` per slot (written once), `README.md` (results, lessons, owner decisions), shared docs and the history updated with
the commits. Nothing deployed; nothing pushed without the owner.

## 5. Amendments

- **A1 (SN476, after its run, before SN476b):** the Production tables were first read (exploratory, read-only) before this plan was
  written, which is how the plan knew Gold had no eligible decision yet; the scored receipt is the committed `sn476_pull.py` run
  (`prod-gold-20261117T113959Z.json`, sha256 60e487f9…). The first `sn476.py` run crashed in part E on a wrong module reference
  (`gold.M` for `goldx.M`) before printing or writing anything; fixed and rerun. SN476 D on GOLD_30K moved −4,941 at ₹205 but +1,77,306
  at ₹400 through the growth wallet's path; supplementary `sn476b.py` repeats C and D on the fixed ONE_15K ledger to show the
  trade-level effect without compounding (added after seeing D, disclosed here; it does not change SN476's verdicts).
