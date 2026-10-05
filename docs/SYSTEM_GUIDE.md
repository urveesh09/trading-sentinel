# Trading Sentinel — system guide and engineering handover










## October 5 (night) — scheduler completion telemetry and Penny funnel stages (actual behavior, Dev)

- **Scheduler telemetry (`scheduler_telemetry.py`).** The Production audit
  found 18 current-boot rows left IN_FLIGHT although the jobs finished. The
  final write had failed silently inside a 100 ms busy budget.
  - `instrument_async_job` now retries the final write with budgets of 100,
    250 and 500 ms (`COMPLETION_BUSY_BUDGETS_MS`).
  - If every attempt fails, it logs `scheduler_telemetry_completion_write_failed`
    and parks the final fact in memory (at most 200).
  - The next durable write replays parked facts, oldest first, at most 20
    each time, and logs `scheduler_telemetry_completion_replayed`.
  - `scheduler_timing_report` adds `pending_completion_writes` and gives each
    row its `run_id`. A current-boot `inflight_state` is now one of:
    - `CURRENT_PROCESS`: the callback is still being awaited.
    - `COMPLETION_WRITE_FAILED`: the job finished, but its final write is parked.
    - `CURRENT_PROCESS_STALE`: neither of the above is known.
  - The business callback never waits on telemetry for more than about 0.85 s
    in total, and never fails because of it.
- **Penny funnel stages (`ops_metrics.py`).**
  - `ops_funnel_daily` gains a `stages_json` column, added by
    `init_ops_metrics_db` at startup.
  - Every subsystem records `evaluated_rows`, `evaluator_accept_rows`,
    `evaluator_reject_rows` and `distinct_accepted`.
  - Penny also records distinct journal attempts for the IST day: `admitted`
    (CANDIDATE_ACCEPTED), `admission_refused` (VALIDATION_REJECTED),
    `entries_filled`, `positions_created`, `accept_rows_not_admitted` and
    `by_source`.
  - The existing `accepted` and `rejected` columns are unchanged.
  - `funnel_window` (and `/ops` `funnel`) returns `stages`.

## October 5 (night) — partner advisory cards delivered with advice labels (actual behavior, Dev)

- Owner direction: `PARTNER_MANUAL_ADVISORY_SEND_UNQUALIFIED=True`.
- `persist_candidate` queues every valid card, not only qualified ones. The
  card's first line is the label: `⚠️ 𝗣𝗨𝗥𝗘 𝗔𝗗𝗩𝗜𝗖𝗘 — 𝗡𝗢𝗧 𝗖𝗛𝗘𝗖𝗞𝗘𝗗` when
  no current qualification exists, `𝗣𝗨𝗥𝗘 𝗔𝗗𝗩𝗜𝗖𝗘` when one does. The text is
  Unicode bold, because the partner transport is plain text with no
  parse_mode. `payload.advice_label` records it.
- **`hedge_advisory._authorize_dispatch` (manual_v1):**
  - A qualified card still needs a current qualification at the transport
    boundary.
  - An unqualified card is sent only while the flag is on and its text starts
    with the NOT CHECKED label.
  - Every other gate is unchanged: validation reasons, profile version, session
    date, entry deadline, quote validity, claim token, the daily cap
    (`PARTNER_MANUAL_ADVISORY_DAILY_CAP=2`) and the one-minute gap.
- Qualification packages bind partner settings, so a package must be
  registered under the flag value in force.
- The informational surfaces (brief/EOD/analytics) still key off a *current
  qualification*, so the partner gets both the information messages and the
  labelled cards.

## October 5 (night) — Momentum automatic execution ON, owner halt ON (actual behavior, Dev + Prod .env)

- The gateway defaults to `MOMENTUM_AUTO_EXECUTE=true` (owner direction: automatic
  instead of manual approval). Every engine-accepted Momentum signal goes through
  `executeMomentum` with no tap.
- Production `.env` sets `OWNER_LIVE_ENTRY_HALT=true` (owner-authorised; the owner
  confirmed the edit). The executor refuses every real entry before dispatch, so
  automatic buys stay paper-only. The alert reads "Auto-execution did not run:
  Owner entry halted". Removing the halt makes Momentum fully automatic with real
  orders.

## October 5 (night) — EDGE overnight outbox and restart catch-up (actual behavior, Dev, paper only)

- **Outbox (audit C5).** Each phase writes its Telegram text to
  `edge_overnight_paper_notices` in the same transaction as its run receipt.
  - `flush_notices` sends pending notices oldest first and marks one sent only
    after a 2xx response (`raise_for_status`).
  - A failed send leaves the notice pending and stops that flush.
  - Flushes run after every phase and every catch-up tick.
- **Catch-up (audit C6).** Job `edge_overnight_catchup` (cron mon–fri 9–15,
  every 5 minutes, trading days) calls `catch_up`, which runs only a phase
  whose receipt is missing today:
  - **Exit**, 09:17–15:20. Up to 09:47 (the old misfire grace) it sells at the
    opening-auction price. Later it sells at the current LTP less 5 bps, with
    `exit_reason=CATCHUP_LTP` and `exit_open` still recording the real open.
    It never claims an auction fill it wasn't present for.
  - **Entry**, 15:21–15:29 only (pre-close); after that the day is not traded.
  - Receipts make every phase once-only per day.

## October 5 (night) — audit fixes: analytics, Swing heads-up, DP tariff (actual behavior, Dev)

- **Whole-trade analytics (audit C8).**
  - `performance_analytics._whole_trades` attaches each `TRADE_PARTIAL` leg to
    its position's final `TRADE_CLOSED`: the same `origin_ref` when recorded,
    otherwise the same ticker.
  - Profit factor, win rate and `trade_close_pnl` are now whole-trade figures.
  - Drawdown uses every ordered trade-cash leg; deposits and withdrawals stay
    excluded.
  - Partials without a final close appear as `unresolved_partial_pnl`, with a
    warning.
  - This clears Momentum paper's false +₹1,516 reconciliation mismatch.
- **Swing pre-market heads-up** reads the typed `Signal.ticker`; it crashed on
  `.get` and lost the heads-up.
- **Penny heatmap log.** `penny_heatmap_skipped` when nothing is open,
  `penny_heatmap_sending` before a send. The old `penny_heatmap_sent` line was
  logged even for empty heatmaps that were never sent.
- **DP charge** `PENNY_CNC_DP_CHARGE` = ₹15.34, Zerodha's published amount
  including GST (checked Oct 5). The earlier ₹15.93 was used by the already
  scored `edge-overnight-t1` study. That record is left as scored.

## October 5 (night) — classic Penny MIS paper profit lock (actual behavior, Dev, paper only)

- `penny_profit_lock.decide` (pure), applied by `main.run_penny_paper_stop_monitor`
  on every Penny scan (about 1 minute) when `PENNY_PROFIT_LOCK_ENABLED=True` (the
  default).
- **Rule** (owner-directed after SUTLEJTEX on Oct 5: entry 37.70, +4.1% at 11:18,
  stopped at 36.74 for −₹9; declared before any replay):
  1. LTP at or above the stored `target_1` (+2R) → exit, reason `target_paper`.
  2. Once the best LTP since entry reaches +1R, the stop rises to the larger of
     round-trip cost breakeven and entry + half the best gain. A hit exits with
     reason `profit_lock_paper`.
  3. The stop only rises. The peak and stop persist in
     `positions.highest_close_since_entry` / `trailing_stop_current`.
- A missing quote now skips the position. The earlier entry-price fallback
  would read as a breach once the stop sits above entry.
- Scope: `PENNY_PAPER` MIS rows only. Live Penny stops are broker SL orders and
  are not modified. Live parity needs broker `modify_order` wiring before any
  live Penny switch.
- The replay (`penny_lifecycle_replay.py`) still models the shipped book (no
  target exit). A labelled diagnostic arm comes after round-3 scoring, because
  that file is a frozen study source.

## October 5 (night) — audit fixes: Momentum dispatch lock, partner silence (actual behavior, Dev)

Source: the Production audit `Production_Trading-sentinel/docs/2026-10-05-production-deep-audit.md`.

- **Post-dispatch lock (audit C1).** `executor.executeSignal` now wraps the
  steps in `executeSignalSteps`, with a `dispatch.sent` flag set once a BUY may
  have reached the broker.
  - After that point, any error not marked `brokerFlat` is promoted to
    `positionHeld`/`outcomeUnknown`. `brokerFlat` marks broker-confirmed flat
    outcomes: rejected, cancelled unfilled, stop filled immediately, or unwind
    confirmed.
  - The three callers (`momentum-execution.js`, the Telegram EXEC handler in
    `index.js`, `POST /api/orders/execute`) record EXECUTED outside the
    `executeSignal` try. A failed record leaves the row `EXECUTING`, so the
    signal stays locked.
  - Previously a SQLITE_BUSY on that write reset the row to PENDING, and a retry
    bought again.
- **Partner informational surfaces (audit §7).** With
  `PARTNER_MANUAL_ADVISORY_DELIVERY_ENABLED=True` but no qualified advisory
  strategy, every partner surface was suppressed. Production's last partner
  message was on September 9.
  - `partner_orchestrator._legacy_info_retired` now retires these surfaces only
    when `_advisory_can_deliver` finds a current `QUALIFIED_FOR_ADVISORY` row
    (cached for 5 minutes): the morning brief, EOD wrap, analytics alerts
    (PCR/IV/OI walls/wall flow) and the expiry pin note.
  - The hedge pipeline's own suppress flags still apply when
    `PARTNER_HEDGE_ENABLED`.
  - Legacy directional trade calls (`partner_scan_tick`, Momentum stock-option
    cues) stay retired: they are unqualified trade instructions.
- **Partner RV refresh.** It passes full datetimes to `get_intraday_by_token`;
  date-only bounds failed every morning.
- **Kite history acquisition** retries timeouts, resets and 502/503/504, five
  attempts with backoff; history reads are idempotent. One 30 s timeout had
  aborted the round-3 download.

## October 5 — expiry-day paper book `expiry-v1` (actual behavior, Dev, paper only)

- `expiry_paper.py`, job `expiry_paper_tick`:
  - runs every 10 s, 12:59–15:40 IST, gated on trading days;
  - acts only when NIFTY (Tue) or SENSEX (Thu) expires today per the dump.
- **Plays:**
  - **A, gamma breakout:** a 13:00–13:30 box; −30% stop; failed-break and
    8-minute time stops; banks half at +40%, then trails; flat by 15:13.
  - **B, auction strangle:** bought 15:13:30–15:15 and held through the closing
    auction.
  - **C, lottery:** a cheap OTM option on A's signal, held into the auction.
- **Risk:** at most ₹2,500 (`EXPIRY_PAPER_BUDGET`) per play per expiry day.
  Broker-free; separate store `<DB_PATH>.expiry-paper.db`, which logs every tick
  including 15:15–15:40.
- The live F&O book is unchanged (`FNO_EXPIRY_DAY_ENTRIES=False`, 15:10 flat).
- The research quote archive now collects until 15:40 (F&O closes at 15:40 since
  the August 3 closing auction).
- Design and frozen rules: [expiry-day paper book](2026-10-05-expiry-day-paper-book.md).

## October 4 — container users share uid 1000 (actual behavior, Dev)

- `python-engine` (`quantuser`) and `node-gateway` (`appuser`) both run as
  uid/gid 1000. Both write the shared `cache.db`; the gateway has written it
  since the account cash reservations (`919e042`).
- Each entrypoint chowns its databases and their `-wal`/`-shm` files at start.
- Before this fix the gateway ran as uid 100 and crash-looped with
  `SQLITE_READONLY` on Production (October 4).
- Successor handover: [inheritance](2026-10-04-successor-inheritance.md).

## October 5 — EDGE overnight research candidate (actual behavior, Dev, research only)

[Study](2026-10-05-edge-overnight-study.md). `edge_portfolio_replay` adds:

- policy `EDGE_OVERNIGHT` (`run_overnight_book`): the shipped scan, ranking and
  sizing; buy at the signal close (+25 bps); sell at the next open; a 1% capacity
  cap on traded value; own cash only;
- `edge-overnight-t1` was scored with a research `CNC_FULL` cost model, since
  retired (see below).

Lab adapter `penny_edge_portfolio_replay` is now 1.2.0.

`edge-overnight-t1` scored once on untouched Mar 2024–Dec 2025: candidate
+₹2,22,864 versus baseline −₹22,008 on ₹25k. The verdict is
`NOT_SUPPORTED_STAYS_OFF`, on the drawdown check measured against starting
capital (19% from peak).

EDGE runtime still buys at 09:30 (paper only).

Added with the owner's go-ahead:

- the broker-free overnight paper book `edge_overnight_paper.py` (₹25,000), with
  jobs `edge_overnight_entry` (15:20) and `edge_overnight_exit` (09:17);
- the runtime delivery-cost fix in `calc_penny_costs`: no delivery brokerage,
  STT on both legs, 0.015% stamp duty and a ₹15.93 DP charge per sell. EDGE and
  CNC paper P&L was overstated before.

The research `cost_model`/`CNC_FULL` option is retired.
`scripts/run_round3_kite_scoring.ps1` is the one-shot Windows task (Oct 5, 17:07)
that acquires Kite Jan–Jul 2026 data and scores `momentum-smart-t3` and
`penny-noise-t3`.

## October 5 — everything on paper, forward evidence for new strategies (actual behavior, Dev)

[Slice](2026-10-05-forward-paper-evidence.md). The Momentum shadow book evaluates
a third broker-free variant, `MOM_SELECTIVE`: the shipped evaluator, then
`momentum_selective.selective_gate` (NIFTY up on the day, stock at least 0.3%
stronger, close above yesterday's high). With `MOMENTUM_SHADOW_ENABLED`, the scan
fetches NIFTY 50 15-minute bars once. A failed fetch makes only this variant
reject (`selective_index_bar_unavailable`); the funnel, the other variants and
their configs are unchanged. `PENNY_SMART_SHADOW_ENABLED` now defaults to `True`.
The owner's smart-Penny paper book collects forward evidence; it remains a failed
candidate (`penny-smart-t4`), not a trading policy. The owner's tick-size and
smart-controller changes below are committed unchanged. Automated live paths
stay off by default: `PENNY_LIVE_TRADING`, `PENNY_EDGE_DISABLE_LIVE`,
`FNO_LIVE_TRADING`/`FNO_DISABLE_LIVE` and `MOMENTUM_AUTO_EXECUTE`. Owner-tap EXEC
can still place an order unless `OWNER_LIVE_ENTRY_HALT=true`.

## October 4 — authorized smart Penny controller implemented (OFF)

[Implementation, verification and remaining contracts](2026-10-04-penny-smart-trader-implementation.md)
supersedes the earlier proposal-only status. New pure policy/book functions reuse
adaptive setup transitions, rank persistent positive stock strength, expire
overextended quotes and manage confirmed-close winners/failed setups. Durable
paper state has fee-inclusive cash/risk, a latched daily marked-loss brake,
restart/dedup and equity carry without daily top-ups. It does not fix the classic
live Penny settlement/daily-risk contract.

`PENNY_SMART_SHADOW_ENABLED=False` and virtual bankroll ₹2,000. No real orders or
capital reservations exist in this controller. Its sibling
`<DB_PATH>.penny-smart-paper.db` owns two additive state/event tables; the
operational ledger is not migrated or locked by shadow writes. Existing scanner
candles/quotes are reused; opt-in exit observation adds only one bounded batch
of at most three held symbols on the current cadence. Actual candles take
precedence over explicitly labelled archived bid samples. Processing moves off
the shared async loop, two-second timeout bounds shadow work, and incumbent
stop exits run first. F&O functions/adapters, broker clients and scheduler jobs
are unchanged; Production remains untouched.

Lifecycle v4 / Penny Lab 1.3.0 adds ranking, exit, entry/risk and combined ablations,
optional actual benchmark context, and daily returns including zero-trade days.
Runtime has no benchmark-history fetch: the frozen comparison also declares
benchmark absent. Replay fixed per-session capital, candle quote proxies and
constant PR1_CALM are diagnostics, not exact runtime/continuous cash performance.
Seen-window freeze and reports: [Penny T4](research/yahoo/2026-10-04-penny-smart-t4/freeze.json).
The runner checks source/settings/data both before and after scoring; a changing
input prevents a verdict. Completed broader T4: incumbent 38 closes / +₹91.7169;
full candidate 153 / −₹47.5019, drawdown ₹97.1379; ranking unchanged, entry and
exit variants also trail incumbent. All improvement checks fail: candidate OFF.
[Verdict](research/yahoo/2026-10-04-penny-smart-t4/results.json) and
[daily economics](research/yahoo/2026-10-04-penny-smart-t4/daily-economics.json)
preserve zero/losing days and negative execution stress. No untouched qualification or minimum daily income is
established. New code remains Dev-local/uncommitted at `a674740`, unpushed and
undeployed. Earlier sections below describe earlier source/evidence stages.

## October 4 — authorized Penny corrections and researched strategy proposal

[Correction receipt](2026-10-04-penny-corrections-and-relative-strength-slice.md)
supersedes the earlier review's open comparison/rounding/tick findings below.
Dev-local source changes at base `a674740` quantize the stop before sizing,
resolve current instrument ticks from refreshed Penny universe metadata and
require dated ticks before new live entries. Recovery/exits retain a fallback
when metadata is unavailable; this is an attempted exit, not a fill guarantee.
Runtime noise sizing preserves decision-price planned risk using the final tick
distance. It does not guarantee risk at later entry/exit fills.

Lifecycle v3 / Lab 1.2.0 adds explicit `stop_policy` and optional research
`bankroll`. T3's old-stop baseline is BAR_LOW, its noise arms NOISE_FLOOR,
applied once; effective settings/costs/helper sources bind its freeze. Paper
₹100,000 and owner ₹2,000 are distinct books. Stateful trader policies retain
their own structural stops. Historical tick/fill/regime/universe limitations
remain explicit. Old research receipts are preserved.

[Researched development proposal](2026-10-04-penny-consistent-returns-strategy.md)
prioritizes causal stock-specific strength ranking, affordable setup entries,
winner management and a reconciled owner-risk contract. These new strategies
are proposed, not implemented or proven. Runtime Penny's daily counter is not
fed by current settlements; resolving it is a material pre-live requirement.
No evidence proves a minimum 1–2% profit on every day.

Stable Sep 24–30 regression reproduced old baseline 18 / +₹15.1765 and gave
corrected noise 15 / +₹36.4486; removing its best winner leaves −₹4.8747.
These are seen-window ₹100,000 paper-book diagnostics, not owner/live proof.
830 selected tests passed (one skip, existing deprecation warnings), then 55
price/executor/lifecycle tests passed after final edits. Compilation and atlas
regeneration passed. Stable-source five-day baseline regression is recorded in
the correction receipt. Untouched January–July Kite data is unavailable locally.
No funding/strategy-live flag, DB migration or dependency change. No broker call,
push, merge, deployment or Production edit. F&O operational source and shared
scheduling remain unchanged. These corrections are uncommitted in Dev.

## October 4 — earlier independent Penny efficiency review

[Review and development discussion](2026-10-04-penny-efficiency-independent-review.md)
checks pushed Dev `a674740` against source and stored evidence. The stateful
Penny candidates are implemented but failed their untouched comparisons;
the owner-selected noise floor has a modest seen-window improvement and its
January–July test remains pending. 45 focused tests passed in this review.

Before the pending study/promotion review, address: its BASELINE now inherits
the default-ON noise stop, unrounded-distance sizing can violate preserved risk,
and the live executor's ₹0.10 snapping differs from intended research protection.
These are documented findings, not fixes performed in this task. Freeze explicit
stop policy/effective settings and final executable risk; then measure net daily
returns, cash utilization and marked exposure at the owner allocation.
No evidence establishes 1–2% profit every day or qualifies Penny live.

Remote branch HEAD was verified at `a674740`; Production Git HEAD is `044c016`
(metadata read only). Older 'not pushed' receipts below describe their original
task status; the reviewed branch is now pushed. This review changes documentation
only in Dev, uncommitted; no new source/configuration/schema/dependency change,
broker call, strategy scoring, merge or deployment. F&O development is excluded.

## October 4 — Penny noise-floor stop selected by the owner (actual behavior, Dev)

`penny_engine_breakout.evaluate_breakout_entry` widens the breakout-bar-low stop
with `noise_floor_stop`: the stop sits at least 1.5% and at least ₹0.03 under
entry, shares shrink at the same rupee risk, and the target stays at 2R from the
new stop. It is controlled by `PENNY_NOISE_STOP_ENABLED` (default **True**). The
owner selected it from development evidence (Sep 7–Oct 1: +₹93 vs +₹78, drawdown
₹32 vs ₹45); the untouched Kite test (`penny-noise-t3`) is still to be run.
Penny live trading stays off (`PENNY_LIVE_TRADING=False`), so this changes the
paper book. Momentum `MOM_SELECTIVE` was not profitable (0 trades) and is not
enabled; `MOMENTUM_AUTO_EXECUTE` stays false.

## October 4 — Momentum direct trading (OFF) and round-3 research candidates (actual behavior, Dev)

[Slice](2026-10-04-momentum-penny-smarter-slice.md).

- **Gateway:** `services/momentum-execution.js` is the only Momentum execution path
  (per-day lock, approved snapshot, `executor.executeSignal`, armed-fill persistence),
  used by the Telegram EM button and `POST /api/internal/momentum-auto-execute`.
  - The route returns `DISABLED` unless `MOMENTUM_AUTO_EXECUTE=true`
    (strict `true/false/1/0` parse; default false).
  - It executes registered snapshots only (no live engine re-fetch).
  - A `positionHeld` or `outcomeUnknown` failure stays locked (`HELD_UNPROTECTED` /
    `OUTCOME_UNKNOWN`) and pages. The EM button path now also locks
    `outcomeUnknown`; previously it reset to PENDING.
  - `services/approved-snapshots.js` holds `getApprovedSnapshot`.
- **Agent:** after registering the EM snapshot, `send_momentum_telegram_alert`
  calls the route. An executed alert carries no buttons; a flat refusal keeps the
  buttons with the reason; a held outcome warns "Do NOT retry". A non-JSON or
  failed reply falls back to the buttons, and only the exception type is logged.
- **Research only:**
  - `momentum_selective.selective_gate`;
  - `momentum_replay` variant `MOM_SELECTIVE` (needs `NIFTY 50` bars in the
    snapshot; `index_ticker`) and exit `RUNNER_EXIT`;
  - Penny `PEN_NOISE_STOP` / `PEN_NOISE_STOP_BE` (`noise_floored_decision`; the
    baseline trade dicts gain `initial_stop_price` with unchanged numbers);
  - `scripts/acquire_kite_history.py`;
  - `run_preregistered_study.py run --jobs N`;
  - studies `momentum-smart-t3` and `penny-noise-t3` (not yet frozen; they need
    Kite data).
- Runtime Momentum and Penny strategy code is unchanged.

## October 4 — index-future candle recording for research (actual behavior, Dev)

- New scheduler job `research_future_candles` (mon–fri 15:40 IST, trading-day and
  token gated) calls `research_future_candles.record_index_future_candles`: for each
  `RESEARCH_ARCHIVE_UNDERLYINGS` (NIFTY, SENSEX) front future it fetches the whole
  session's `5minute` and `minute` candles once; `kite_client.get_intraday_by_token`
  caches them in `intraday_cache_by_token` (never aged out). Market data only.
- `scripts/export_fno_replay_dataset.py` now exports NIFTY **and** SENSEX future
  candles (all cached intervals; the replay reads `5minute`).
- Owner direction: no further F&O development for now beyond this recording.

## October 4 — F&O growth slice: adaptive risk, SENSEX, multi-lot capped-loss book (actual behavior, Dev)

[Growth slice](2026-10-04-fno-growth-slice.md). Paper behaviour after this commit:

- **Brakes/caps:** daily 3%, weekly 6%, monthly 10%, drawdown halt 15%
  (`FNO_MAX_DRAWDOWN_PCT`, read by `fno_shared_risk` and the orchestrator);
  structural cap ₹40,000; `FNO_MAX_LOTS` 2, `FNO_MAX_LOTS_PROVEN` 3.
- **Adaptive risk** (`fno_adaptive_risk.risk_stance`, pure): 0.5× at 4% and 0.25×
  at 8% below the equity peak (anchored on the static allocation, both paper books'
  completed trades); 1.25×/1.5× only with ≥20/≥40 trades at PF ≥1.3/≥1.5 within 2%
  of the peak. It scales the single-leg risk budget and rupee ceiling and the
  capped-loss budget; a cut shrinks to one lot, never below (one lot must
  still fit the normal budget). Two losing single-leg closes in an IST day add the
  `two_strike_day_halt` switch (management continues).
- **Capped-loss book:** `dr_lots` sizes up to `FNO_DR_MAX_LOTS`=3 inside ₹10,000 ×
  multiplier and 40% of pool capital (condor margin reserved at ₹50,000/lot);
  `structure_round_trip_cost` charges each leg's full quantity.
- **SENSEX:** `run_fno_tick` evaluates every `FNO_TRADING_UNDERLYINGS` (NIFTY first,
  default `NIFTY,SENSEX`). SENSEX uses its own bars for range/ATR/EMA and NIFTY
  futures bars for RVOL (`rvol_bars`; missing aligned bar → reject). The
  correlation guard rejects `correlated_exposure_open` when the other index holds
  the same direction. Each position is managed against its own front future;
  executor orders carry the spec exchange. The live leg runs only on NFO.
  `refresh_all` refreshes traded books too.
- **Vehicle by IV:** implemented, `FNO_VEHICLE_BY_IV=False` (OFF).
- **Replay:** `fno_policy_replay` sizes through `risk_stance` and logs
  `risk_multiplier`/`risk_reason` per decision; NIFTY only.

## October 4 — F&O runtime and research changes (actual behavior, Dev)

- `_try_entry_for_leg` now delegates its pure decision to
  `fno_entry_plan.plan_single_leg_entry` (same order, reasons and log fields);
  `_read_entry_policy` delegates its arithmetic to `fno_shared_risk.entry_halts`.
- `run_fno_tick` manages single-leg positions through
  `_manage_single_leg_books`, also used by the new `run_fno_fast_exit`.
- `register_fno_scheduler_jobs` holds one asyncio lock for every F&O pass and
  registers `fno_fast_exit` (`FNO_FAST_EXIT_ENABLED`, default False, every
  `FNO_FAST_EXIT_INTERVAL_SEC`=10) and `fno_bar_close_tick`
  (`FNO_BAR_CLOSE_TRIGGER_ENABLED`, default False, `FNO_BAR_CLOSE_DELAY_SEC`=3)
  only when enabled. With both off, live behaviour is unchanged.
- Research: `fno_policy_replay.py` (inert) and
  `scripts/export_fno_replay_dataset.py`; see the
  [F&O slice](2026-10-04-fno-replay-and-speed-slice.md).

## October 4 — T2 research replays (actual behavior, Dev)

- `daily_portfolio.py` is the single own-cash daily book for EDGE, Range and
  Swing research replays (next-open/limit entries, stop-first ties, resting
  levels, close-time policy hooks, runtime cost schedules, marked equity).
- Lab adapters `penny_edge_portfolio_replay`, `range_reversion_portfolio_replay`
  and `swing_regime_portfolio_replay` share `DailyPortfolioAdapter`. The EDGE
  independent-trial proxy (`penny_edge_next_open_lifecycle`) was removed.
- `momentum_replay` accepts `entry_clock` (`ACCEPTED_CLOSE` legacy default,
  `NEXT_BAR_OPEN` executable) and `exit_model=THESIS_EXIT`.
- `scripts/run_preregistered_study.py` (list/freeze/run) replaces the per-module
  OOS scripts; `scripts/audit_penny_cnc_conjunction.py` is a CNC diagnostic.
- Measured: no T2 candidate is profitable; see the
  [T2 receipt](2026-10-04-t2-range-swing-momentum-slice.md). Runtime unchanged.

## October 4 — T1 research trader candidates (actual behavior, Dev)

Research-only modules, never imported by runtime Penny/EDGE/F&O code:

- `adaptive_penny_policy.py` — pure `PEN_TRADER_V1` / `V2_PARAMS` setup-state
  policy (context scoring, fast/retest/continuation entries, structural stop,
  cost-aware sizing, churn memory) and thesis exit manager.
- `penny_lifecycle_replay.py` — `candidate_policy` now accepts `PEN_TRADER_V1`,
  `PEN_TRADER_V1_THESIS`, `PEN_BASE_THESIS`, `PEN_TRADER_V2` (default
  `BASELINE`, unchanged output). Hard blocks are shared via `_hard_constraint`.
- `edge_portfolio_replay.py` / Lab `penny_edge_portfolio_replay` — causal
  own-cash EDGE portfolio (`BASELINE` live clocks or `EDGE_TRADER_V1`).
- `scripts/run_penny_trader_oos.py`, `scripts/run_edge_trader_oos.py` —
  freeze-then-run pre-registration.

Measured on untouched windows ([receipt](2026-10-04-t1-penny-edge-trader-slice.md)):
no candidate beat its baseline; the shipped Penny MIS baseline was +₹63.17 over
13 sessions; the shipped EDGE strategy lost 40.17% marked in Jan–Jun 2026 with
own cash. Runtime EDGE paper sizing does not check cash (per-day entry cap
only). No runtime, settings, schedule or F&O behavior changed.

## October 4 — latest direction: adaptive non-F&O trader policies

The owner requested a stronger plan after identifying excessive filter behavior.
[Adaptive trader development plan](2026-10-04-adaptive-non-fno-trader-development-plan.md)
is now the active design/order: T0 causal comparison plus runnable prototypes,
T1 complete Penny/EDGE policies, T2 Range/Swing/Momentum and limited CNC audit,
T3 untouched qualification and F&O compatibility. Replacement candidates may
recognize baseline-rejected setups; new subset-only gates are not completion.
Persistent setup/execution states, context-sensitive timing and thesis exits
are proposed, not implemented. Safety/cash/loss/protection contracts stay firm.

R1–R5 fidelity requirements and all adverse/unavailable receipts remain open.
Prior documentation below describes historical implementation and must not be
read as qualification. F&O remains excluded and must not be hindered through
cash, shared source/configuration, broker/quote capacity or scheduler/DB load.
This revision is documentation only; source HEAD `434c4cc` and existing
uncommitted review corrections/evidence are preserved. No new tests/backtest,
runtime/configuration/schema/dependency change, Production access, broker action,
commit, push or deployment occurred in this planning task.

## October 4 — independent review override and same-data repeat (Dev only)

[Independent review / larger follow-up plan](2026-10-04-non-fno-independent-review-and-repeat-plan.md)
supersedes a claim that N0–N4 or full N1–N3 lifecycle/candidate integration is
complete. New commits were research-only; the Yahoo runner and active policies
still select baseline defaults. Initial archived-Yahoo repeat reproduces all
16 prior states/windows/metrics, including Penny +₹15.1765 and Momentum −₹0.827101.

Bounded research corrections: Penny's retest anchors before its confirmation
candles and prior profiles require a complete same-minute prefix; Momentum's
named exit diagnostic forwards actual ATR/regime, refuses overnight, late
deadline and zero-volume fills, and binds exit settings/assumptions. EDGE's
new independent-trial adapter is correctly PROXY, not a verified LIFECYCLE;
holding-clock, sizing, slippage and persistent cash/position gaps remain planned.
Momentum intrabar ordering/completed-bar clock limits likewise remain explicit.

[Final comparison](2026-10-04-non-fno-review-and-backtest-results.md): both
16-outcome repeats agree exactly with the old defaults. PEN_CONTEXT finds zero
entries with insufficient prior profiles; Momentum exit diagnostic is −₹19.01;
EDGE PROXY has a −₹60,813.84 independent closed-trial sum, not account P&L.
No demonstrated improvement or qualification. All adverse diagnostics retained.

130 focused tests passed (one existing HTTPX deprecation); affected source
compiled, diff checks passed and atlas regenerated to 241 modules. Final repeat
and separately frozen candidate studies are recorded in the review receipt.
Source baseline `434c4cc`; corrections/results are Dev-local and uncommitted.
No shipped strategy, F&O, shared cash/scheduler, broker, runtime configuration,
dependency/schema or Production change; no push/deployment or qualification.

## October 4 — N1–N3 non-F&O research implementation (Dev only)

[N1–N3 implementation slice](2026-10-04-n1-n3-implementation-slice.md) is
implemented in Dev. It changes **research measurement and named offline
candidates**, not live strategy policy or any F&O component.

- N1: `LIVE_EXIT_LIFECYCLE` makes the Momentum replay call shipped
  `evaluate_momentum_exit`, including broker-stop-first OHLC ordering,
  scale-out/runner quantities, per-order costs, ratchets, hard square-off and
  unresolved exits. `TARGET_1_PROXY` remains the default. EDGE now has a Lab
  lifecycle adapter: shipped scan/ranker, next-daily-open fill only,
  geometry-invalid gap refusal and shipped exit simulator.
- N2: Penny MIS `PEN_CONTEXT` is optional research-only/default `BASELINE`.
  It preserves the baseline decision, requires five historical same-minute
  cumulative-volume profiles plus fresh breakout/bounded retest, and fails
  closed when evidence is absent. `penny_exit_thesis` is a non-widening,
  one-rearm-only diagnostic, not a runtime exit change.
- N3: broker-free Range net-room/thesis and Swing relative-strength/correlation
  gates are available for matched research; Momentum's real runner is now
  measurable. They are not wired to the live/shadow dispatcher.

No broker/order/API call, scheduler, DB schema, strategy setting, capital
reservation, F&O source/configuration or Production file changed. This is not
performance evidence or a rollout recommendation: manual approval,
point-in-time universe/event context, depth/fill receipts and shared stock
portfolio evidence remain absent. Verification: 109 focused tests passed (one
existing HTTPX deprecation), affected modules compiled and diff checks passed.
Dev only; no push or deployment. Source commit `65e050a`; atlas regenerated to
241 Python modules immediately before the commit.

## October 3 — non-F&O improvement direction (plan only)

[Researched smart-entry/exit plan](2026-10-03-non-fno-smart-entry-exit-development-plan.md)
prioritizes Penny MIS and EDGE, then Range/Swing, with Momentum's existing
partial/runner and S7 research reused. It first requires baseline isolation,
complete lifecycle economics and honest coverage, then bounded entry/exit
experiments at equal capital/risk and genuinely untouched holdouts.

F&O development is excluded. Its capital, decisions, exits and shared runtime
resources must remain protected; filename isolation alone is insufficient.
New non-F&O variants remain proposed, broker-free/default OFF; no strategy,
threshold, funding, dependency, runtime configuration or schema changed.
₹15.18 remains a five-session partial Penny sensitivity result, not live or
system profit. Source baseline `4be033a`; documentation-only, Dev-local and
uncommitted, no Production access, broker action, push or deployment this task.

## October 3 — Yahoo-only non-F&O backtest interface (Dev only)

`scripts/backtest_all_yahoo.py --start YYYY-MM-DD --end YYYY-MM-DD` supplies one
repeatable Yahoo-only research interface for the shipped non-F&O Lab paths.
See [usage](YAHOO_BACKTEST_GUIDE.md), [results](2026-10-03-yahoo-backtest-results.md)
and [plan](2026-10-03-yahoo-all-module-backtest-plan.md). It uses current universe
names/defaults and fresh Yahoo bars, not Sentinel prices/trades. Native interval,
identity/currency/clock, raw digest, B1 whole-day rejection, immutable publication
and source/settings/importer drift checks are preserved. All-null/known closed
session/metadata-bound final quote placeholders are archived as absent candles.
The original import and separately validated snapshots both remain available.

Yahoo retention leaves the requested quarter intraday study unavailable; a
separately declared Sep 24–30 diagnostic and Penny gap sensitivity are explicit.
Q3 EDGE has 1,142 candidate appearances/167 selections; Swing 171 entry decisions;
Range 1,097 ENTER verdicts. Recent Penny sensitivity has 18 closes/+₹15.18;
joint cash reuses them, not extra profit. Recent Momentum has two virtual time
exits/−₹0.83 with no later-day fallback. Effective daily names: 95/100 Penny and
499/500 stock; data exclusions remain visible. Scope is still evaluator,
lifecycle or partial portfolio, not full-system profit/qualification.

The checked-in Penny universe is empty, so the script prefers a nonempty current
file and otherwise uses an explicit symbol-only October 1 fallback. No live
universe, thresholds, capital, exits or runtime configuration changed. Downloads
use the standard library; no dependency added. 70 focused tests passed (one
existing HTTPX deprecation); final reproducibility/source/data checks and atlas
regeneration are recorded in the results receipt. Dev only, no Production edit,
broker action, push or deployment; F&O remains excluded.
Source/research commit `df0c379`; immediate guide/plan/results, deterministic
atlas and clean Dev worktree checks passed. The results document records the
documentation-only receipt update.

## October 3 — current-system real-data test receipt (Dev only)

[Current-system results](2026-10-03-current-system-backtest-results.md) and
[frozen execution plan](2026-10-03-current-system-backtest-plan.md) are the latest
research receipt. Current Dev `556209c` was exercised on retained Production
history: F&O September 17–October 1; stocks Q3. The only engine correction is
explicit EDGE SQLite handle closure, with return/exception regressions and the
first failed replay preserved. No numeric strategy/configuration/schema change.

Penny MIS's complete-session replay closes one trade (+₹37.43) on only 189 of
6,500 requested stock-days. Its gap sensitivity retains unresolved positions;
the joint ₹2,000 cash ledger admits seven, settles three and locks ₹1,961.56 in
four unresolved entries. Production records 84 accepted MIS signal observations
and 27 later-audited fill events; these are not quarter profitability evidence.
CNC has zero entries on its evidenced subset; EDGE has 1,242 candidate
appearances/168 selections; Range 1,095 ENTER verdicts. Swing lacks aligned
index warm-up. Momentum's quarter is unavailable; its Aug 11–Sep 30 diagnostic
is −₹89.13 on 18 virtual closes, 16 using later-day fallback exits because EOD
bars are absent. This cannot establish live MIS performance.

F&O current-policy/exit replay remains unavailable or insufficient. Retained
paper cash (+₹10,755.67 single-leg/+₹3,187.60 spreads) is operational history,
not a new policy backtest. Full historical context/lifecycle/portfolio fidelity,
complete executable F&O evidence and prospective qualification remain open.
The partial Penny ledger also needs UTC clock normalization before broader
parity claims; independently normalizing these actual streams leaves all cash
metrics unchanged. See results for explicit limitations and discussion order.

Verification: 28 focused tests passed (one existing HTTPX deprecation), raw
report/data/source integrity and unchanged repeat metrics checked; compilation,
diff and regenerated atlas checked. Large evidence stays locally retained under
the dated ignored `_local/`; tracked receipts bind it. Production release
`044c016` was stopped during collection/final read-only check; this task did not
restart or edit it. Dev only, no orders, push or deployment. Source/research
commit `4929bea`; immediate consistency, deterministic atlas and clean-worktree
checks passed. See [completion receipt](2026-10-03-current-system-test-completion.md).

## October 3 — P1/P3/P4 safety and research completion slice (Dev only)

P1 adds a cross-runtime durable account-cash reservation in the shared
`cache.db`. Python live BUY entries and gateway Momentum/Swing EXEC entries
reserve full bounded order value, calculated worst-case entry charges and a 1%
fill buffer before dispatch. Reservations retain ambiguous/partial outcomes,
release only known-not-sent or matching zero-fill terminal proof, and are not
applied to exits. Book attribution records the owner allocations (Swing
₹1,000, Penny ₹2,000, Momentum ₹3,000, EDGE ₹3,000); transfers are allowed, so
the account-wide own-cash limit—not stranded sleeve pools—remains the hard
constraint. The configured account ID is `kite-primary`.

P3 adds `penny_joint_lifecycle_portfolio`, which reconciles actual MIS/CNC
lifecycle streams against shared full-notional cash, preserves unresolved
exposure and explicitly orders known exits/entries. It is `PORTFOLIO_PARTIAL`,
not a fabricated full-system result: historical universe, regime, event,
scheduler and broker-fill evidence remains absent for Penny and the other
books.

P4 adds an append-only prospective qualification registry. A holdout may only
be frozen before it starts; snapshot/policy/config drift is rejected and every
evaluation is immutably recorded. The CLI refuses qualification for anything
below `FULL_PORTFOLIO` fidelity, so the new partial adapter cannot be marketed
as qualified. See [P1–P4 completion slice](2026-10-03-p1-p4-completion-slice.md).
Dev only; no configuration migration, Production edit, broker order, push or
deployment occurred. Source commit `919e042`; immediately after commit the
focused Python suite passed 90 tests (one existing HTTPX deprecation), the
gateway executor suite passed 59 tests, compilation/diff checks passed and the
atlas was regenerated (240 modules).

## October 3 — P2 reproducibility/publication (Dev only)

Backtest manifests now recursively bind local transitive Python dependencies.
Snapshots and report JSON are created as temporary sibling artifacts then
published exclusively, eliminating an exists/write overwrite race. Existing
artifacts remain readable. P2 focused CLI/Lab verification: 26 passed, one
existing httpx deprecation warning. Dev only, not pushed or deployed. See
[P2 slice](2026-10-03-p2-reproducibility-publication.md). Owner P1 budgets:
Swing ₹1,000; Penny ₹2,000; Momentum ₹3,000; EDGE ₹3,000; transfers allowed.
The outstanding P1 decision is the charge/gap contingency reserve; no live
reservation is activated until it is explicit.

## October 3 — independent review and bounded corrections (Dev only)

Current acceptance and remaining work are in the
[post-implementation review](2026-10-03-post-implementation-independent-review.md).
F0 R1-R5 source changes are present. Operator zero-fill reconciliation now must
match the claim's known order; unresolved single-leg positions continue to occupy
concurrency, no-pyramid and premium limits. Malformed/missing order-book evidence
is unavailable, so broker entry/retry checks cannot treat it as an empty book.
No schema, configuration or strategy-threshold change is involved.

The original plan remains incomplete: F1 account-wide cash reservations and
catastrophe acceptance; B0/B1 complete source/point-in-time manifests; B2 full
historical portfolio context; B3/B4 lifecycle/portfolio parity; and B6 prospective
holdout and session uncertainty. B5 stays excluded in the current recorded plan.
Production was stopped initially, then resumed after the owner's power cut.
Read-only identity reports declared engine `044c016` (healthy), matching the
Production checkout; this review did not restart/edit/promote it. Baseline
verification: 422 Python/58 gateway tests. Final affected regression: 294
passed, two existing deprecations; atlas, compile and diff checks passed.
No Dev runtime acceptance, push or deployment occurred.
Correction source commit `284bb4a`; immediately verified documentation/plan
consistency, deterministic atlas and clean Dev worktree. Review/correction work
is complete; the explicitly listed implementation and operational gaps remain.

## October 3 — B6 standard reporting and date declaration (Dev only)

`backtest_cli report` now emits evidence-only standard metrics and leaves
missing fields/risk-adjusted values null. `run --holdout-from/--holdout-to`
records a non-overlapping date declaration; `compare` requires the
same snapshot/window/scope/holdout. Trade-sample bootstrap intervals are
deterministic and explicitly not profitability evidence. New declarations are
`DECLARED_UNVERIFIED`, with `untouched_verified=false`: date ordering cannot
prove predeclaration or absence of prior use. Reports expose closed-field
coverage and leave partial/absent aggregates null; winner exclusion subtracts
only positive winners. Existing archived reports are preserved; `report`
clarifies legacy DECLARED_UNTOUCHED labels and includes their archived status.
Original focused B6 tests: 37
passed, one existing httpx deprecation warning. Dev only, not pushed/deployed.
Source commit `60bd989`; no configuration or migration impact. See
[B6 slice](2026-10-03-b6-standard-reports-holdouts.md).

## October 3 — B4 Momentum baseline and Range evaluator replay (Dev only)

The Momentum research default is now the shipped `MOM_BASE` evaluator;
`MOM_RECENCY_5` remains an explicit research comparison. It remains only an
`EVALUATOR`, because its full-T1 virtual shadow exit is not the live partial
runner/trail and the historical regime, Telegram, broker and shared-capital
evidence is not archived. `range_reversion_daily_evaluator` separately calls
the shipped `range_reversion_entry` on each completed validated daily bar and
records verdicts only, never invented P&L or orders. Focused B4 verification:
70 passed, one existing httpx deprecation warning. Dev only, not pushed or
deployed. Source commit `3e03916`; no configuration or migration impact. See
[B4 slice](2026-10-03-b4-momentum-range-evaluator.md).

## October 3 — B3 shipped Swing/EDGE daily evaluator replay (Dev only)

`backtest_lab.py` now has two distinct research-only `EVALUATOR` adapters:
`swing_regime_daily_evaluator` calls the current `engine.evaluate_signal` with
explicit NIFTY 50/NIFTY BANK history and a declared one-update-per-session
regime clock; `penny_edge_daily_evaluator` calls the current
`penny_edge_live.scan_today` on a frozen explicit-universe snapshot. The old
Swing runner remains a `PROXY` and is not relabelled. These adapters provide
decision/candidate evidence only: no Telegram approval, live admission,
historical scheduler state/breadth/event snapshot, fill, exit or shared cash
portfolio is reconstructed. Missing required evidence fails unavailable.

While binding the real Swing path, `engine.calc_rsi_series` was corrected to
use the matching close-to-close delta (`i - 1`) rather than indexing one past
the gain/loss arrays. That removes a live scanner `IndexError` once sufficient
RSI history exists; it does not change policy thresholds or sizing. B3 tests:
149 passed; one existing httpx deprecation warning. Dev only, not pushed or
deployed. Source commit `e349b0b`; no configuration or migration impact. See
[B3 slice](2026-10-03-b3-swing-edge-daily-evaluator.md).

## October 3 — B2 CNC Connors lifecycle replay (Dev only)

`research_penny_cnc_lifecycle.py` replays the shipped `PENNY_PAPER` CNC book
([B2 CNC](2026-10-03-b2-penny-cnc-connors-lifecycle.md)).

**Entry (09:30)**
- The scanner's `get_historical` fetches Kite day candles up to today, so
  its last bar is today's in-progress candle. The replay rebuilds that
  candle from the 09:15–09:29 minute bars.
- The real `evaluate_connors_entry` runs with `PennyRiskEngine` sizing, CNC
  caps (2 CNC, 5 total) and the executor drift/stop checks, and the entry
  fills at the 09:30 LTP.

**Exits (15:45)**
- The daily tracker applies: stop (only if no target was hit that day), T2,
  T1 (half the shares, stop to breakeven) and a 15-calendar-day time stop.
- The trail is disabled because Connors decisions carry no ATR.
- Costs use `engine.calc_zerodha_costs` for CNC.
- The Connors spec's `evaluate_connors_exit` is not used at runtime.

## October 3 — F1-A own-cash (no leverage) entry guard (Dev only)

Every live BUY entry now checks its notional against a snapshot of the owner's
own uncommitted cash ([F1-A](2026-10-03-f1a-own-cash-no-leverage-guard.md)):

> broker `equity.available.cash` (never collateral, adhoc margin or leverage)
> − open long position cost − pending BUY orders − today's realised loss

This is an individual preflight, without a common atomic Python/gateway cash
reservation or charge/contingency coverage. Concurrent entries can both use
the same snapshot; F1-B in the independent review is required before accepting
the owner's no-leverage rule as an account-wide invariant.

- **Gateway.** `node-gateway` `preflightEntryMargin` enforces it for
  Momentum/Swing EXEC, refusing with `OWN_CASH_INSUFFICIENT`.
- **Python.** `KiteClient.place_order` enforces it for Python live
  entries, refusing with `own_cash_refused` and `NOT_SENT`.
- **Fail closed.** Missing evidence, short positions and entries without a
  LIMIT price are refused.
- **Exits** are untouched.

## October 3 — F0-R5 occupancy in the claim and post-admission clocks (Dev only)

`claim_shared_fno_entry_dispatch(..., occupancy=EntryOccupancy(...))`
re-applies each book's existing occupancy limits inside its transaction,
counting positions plus in-flight `DISPATCHING`/`UNRESOLVED` claims
([R5](2026-10-03-fno-f0-r5-occupancy-and-clocks.md)):
- single-leg: `FNO_MAX_CONCURRENT`, `FNO_MAX_TRADES_PER_DAY`,
  `FNO_MAX_OPEN_PREMIUM_PCT × pool`, and no-pyramid on the contract;
- defined-risk: one structure.

A refusal releases the never-sent reservation
(`occupancy_denied_before_dispatch:<reason>`).

After the claim, live callers re-read the real clock:
`post_admission_entry_reject` (directional) and `dr_post_admission_reject`
(DR) re-check the entry window plus quote and chain freshness. A late entry
is resolved as `no_dispatch` and is never sent. Exits are untouched.

## October 3 — F0-R4 broker payload and entry/cost binding (Dev only)

`fno_exit_evidence.py` holds the one pure interpretation of a broker exit
packet (`derive_exit_facts`), used by the live recovery verifier and by the
shared F&O risk reader ([R4](2026-10-03-fno-f0-r4-broker-payload-binding.md)).

**What the reader binds**
- Each recovery receipt on an open position is re-derived from its stored
  packet: account, order, symbol, tag, terminal status, filled/remaining
  quantities, unique trade ids and weighted price.
- The receipt's entry premium must equal the position's. A trigger makes the
  position's `entry_premium`, `tradingsymbol` and `source` immutable.
- Charges are recomputed from the cost schedule snapshot that
  `resolve_exit_intent` now stores (`cost_snapshot_json`).

**Fail-closed reasons:** `recovery_payload_mismatch`,
`recovery_entry_economics_mismatch`, `recovery_cost_provenance_unavailable`
and `recovery_cost_mismatch`.

**Limitation.** A matching digest is local integrity, not broker
authenticity.

## October 3 — F0-R3 canonical F&O cash, observation clock and completed trades (Dev only)

The shared F&O view and policy now read one validated ledger ([R3](2026-10-03-fno-f0-r3-cash-clock-completion.md)).

**What counts as cash**
- `TRADE_PARTIAL` and `TRADE_CLOSED` are trade cash.
- `INITIAL` and `TRADE_OPENED` must be zero.
- Manual cash: a positive amount is excluded from capacity and reported; a
  negative amount reduces equity.
- Anything else fails closed.

**Validity checks.** Cash must be finite and timezone-aware, must not be
dated after `observed_at` (the wall clock unless injected), and must be
unique per origin and exact generation.

**Settlement completeness.** A settled single-leg row (generation ≥ 1) or a
`SETTLED` DR row must have its exact cash. Legacy closed rows are counted in
`legacy_unlinked_closed_positions`.

**Brakes.** Day, week and month totals stop at the policy day. The six-loss
pause counts completed trades: cash is grouped by origin, open trades are
excluded, and the order is completion time, then id.

## October 3 — F0-R2 single F&O dispatch owner and evidence-backed outcomes (Dev only)

Both F&O books now follow reserve → claim → act → resolve ([R2](2026-10-03-fno-f0-r2-dispatch-ownership.md)).

**Claiming**
- `claim_shared_fno_entry_dispatch` (one `BEGIN IMMEDIATE`) requires the
  `RESERVED` reservation and no prior claim, and re-reads the entry policy.
- It writes one `DISPATCHING` row (random owner token) in
  `fno_entry_dispatches`. Only that owner may call the executor.
- A policy denial releases the never-sent reservation. Claims never expire,
  and `FILLED`/`RELEASED` claims are immutable.

**Executor outcomes**
- The live `FnoExecutor.execute_entry` returns `filled`, `no_dispatch`,
  `rejected`, `zero_fill_verified`, `partial` or `unknown` with evidence. It
  re-reads the final order state after a cancel and keeps cancel errors.
- `KiteClient.place_order` adds `dispatch_certainty`: `NOT_SENT`,
  `BROKER_REJECTED`, `AMBIGUOUS` or `ACCEPTED`.

**What frees capital**
- `resolve_shared_fno_entry_dispatch` frees capital only for verified
  `no_dispatch`, `rejected` or `zero_fill_verified`. Anything unverifiable is
  stored as `unknown` and keeps the full reservation.
- A position insert consumes the reservation and fills the claim atomically.
- `reconcile_shared_fno_entry_dispatch` lets a named operator release an
  orphaned or unresolved claim, but only with `zero_fill_verified` or
  `no_order_verified` evidence.

## October 3 — F0-R1 fee-inclusive shared F&O exposure (Dev only)

The shared F&O view no longer releases the fee part of a reservation when a
position is inserted ([R1](2026-10-03-fno-f0-r1-fee-inclusive-exposure.md)).
- **What counts as exposure.** Each OPEN or UNRESOLVED single-leg row counts
  `max_loss_rupees + risk_fee_reserve_rupees`. The reserve is
  `calc_fno_costs(fill, 0, qty)`, frozen at insert, and is the exact
  worst-case charge for a bought option. Each DR row counts
  `max_loss_rs + entry_cost_rs`.
- **Partials and closes.** A verified partial keeps the full frozen fee. A
  terminal close leaves exposure, and its ledger cash carries the actual
  fees.
- **Fail closed.** Missing fee economics, or a single-leg structural loss
  below its premium at risk, make the view unavailable. Triggers make the
  reserves immutable.
- **Reporting.** `SharedFnoRiskView.open_fee_reserve_rs` reports the fee
  share.
- **Known limitation.** DR fees use the existing flat round-trip estimate.

Production has no open F&O rows, so this deploys without a stall.

## October 3 — research bar contracts and exact Penny lifecycle replay (Dev only)

This guide's research tooling now has two offline layers ([slice and evidence](2026-10-03-b1-b2-data-contracts-and-penny-lifecycle.md)).

**`research_data_contracts.py` (B1)** decides which cached bars a replay may
use.
- A run selects one registered interval label (`minute`, `3minute`,
  `5minute`, `15minute`). Other labels on the same ticker-day are counted,
  not merged; `legacy_unknown` is refused.
- Timestamps are IST wall-clock bar starts, visible at start + interval.
- One invalid row (off grid, outside 09:15–15:29, non-session date,
  impossible OHLC, negative volume, conflicting duplicate) invalidates that
  ticker-day.
- `TRADED` bars are the only executable evidence; zero-volume bars are
  marks.
- Each requested trading day is COMPLETE, PARTIAL (with reason codes),
  INVALID or UNAVAILABLE. Dates outside the audited static calendar are
  UNAVAILABLE.
- Daily bars are point-in-time with adjustment basis `UNKNOWN_AS_CACHED`.
  Moves above 40% and off-calendar daily dates (such as 2026-02-01) are
  reported, never repaired.
- Manifests carry an order-independent SHA-256. Loaders open SQLite with an
  encoded `mode=ro` URI and never create a database.

**`penny_lifecycle_replay.py` (B2)** replays the classic Penny MIS book with
the shipped functions in runtime order.
- At minute boundary *k* it evaluates bar *k−1* (the forming bar is dropped,
  as live does).
- Fills happen at the LTP: the open of bar *k* when it traded. A stale mark
  never proves a fill.
- Entry follows the runtime path: circuit filter, then
  `evaluate_breakout_entry` with real `PennyRiskEngine` sizing, then one
  position per ticker and at most 3 MIS positions, then the executor's 2%
  drift and stop-breach checks.
- Exits follow the runtime path: the paper LTP stop poll (`PENNY_PAPER`) or
  an approximate broker stop (`PENNY`), the 14:30 `run_penny_eod_check`
  branch order, and the 15:00 force close. There is no target exit.
- Costs use the frozen real equity MIS schedule; the brokerage bypass is
  never honoured.
- Scope is `LIFECYCLE`. Universe ranking, historical regime, the sector
  filter, the event calendar, broker rejections and partial fills, CNC
  occupancy and scheduler jitter are declared as not replayed.

It is exposed through the Backtest Lab (`penny_breakout_mis_lifecycle_1m`,
plus a new additive `scope` metadata field) and through
`scripts/run_penny_research.py --strategy lifecycle`. No runtime trading
path, schema, setting, broker, order or message behaviour changed.

Observed shipped behaviour, not changed:
- The classic Penny daily kill switch is never fed by runtime settlements
  (`record_close` has no caller), so it cannot fire.
- The Penny bankroll is a fixed setting.
- Minute bars stop at about 14:29 once the scanner's entry window closes, so
  sessions after 2026-09-03 lack 14:30/15:00 exit evidence.

Tests: 57 new or extended warnings-fatal tests; 809 passed and 1 skipped in
the broad Penny/Lab selection. Dev only; not pushed or deployed.

## October 3 — independent F0 acceptance review (Dev only)

[Independent review and correction plan](2026-10-03-fno-f0-independent-review.md)
supersedes the F0 source-complete claim below. Shared paper brakes and atomic
position/reservation writes are implemented, but open exposure loses its fee
reserve, identical reserved retries can dispatch after a halt, and simultaneous
DR callers can exceed the existing one-structure cap. Broker payload semantics,
cash event/clock/completion binding and ambiguous live-entry release also need
the planned R1–R5 corrections. These are code/isolated-fixture findings, not
claims of a Production loss or authorization to enter live spreads.

Two bounded reader corrections are implemented in this review: both shared
read helpers use encoded SQLite `mode=ro` URIs and never create a missing DB;
a real terminal zero-fill recovery may retain positive entry-premium context
without being mistaken for partial cash. It retains all open exposure and
books no cash. No schema, settings, broker call or exit authority changed.
Baseline review: 111 tests passed with one known Starlette deprecation; the
three new reader regressions passed warnings-fatal. The final six-file run
passed 114 tests with that existing deprecation and normal exit; compilation,
atlas regeneration (229 modules) and whitespace checks passed. Source commit
is recorded in the review. Production remains `044c016` with
no shared-risk module deployed; B1/B2 has not begun.

## October 3 — F0-D verified partial-exit residual exposure (Dev only; not deployed)

`fno_shared_risk.py` is an additive, source-scoped F&O evidence layer. It reads
one consistent view of exact source ledger settlement cash plus both books'
`OPEN`/`UNRESOLVED` structural losses and in-flight reservations. Missing
schemas, malformed/non-finite values and unpriced exposure are unavailable,
never capital. Its `BEGIN IMMEDIATE` reservation is idempotent only for the
same still-reserved request; resolution is one-way and needs a position or
failure receipt, so interrupted entries are never released by a timer. Focused
F0 tests: 4 new + 45 existing F&O risk/isolation checks passed warnings-fatal.
The broader F&O orchestrator/recovery selection passed 52 assertions without
warnings-as-errors but retains an existing Starlette lifespan deprecation; a
warnings-fatal combined run also surfaced the documented Windows socket warning.

F0-B binds each paper single-leg/DR admission to a fee-inclusive
worst-case-cash reservation and consumes it in the same transaction as its
position row. This preserves feasible paper trades while stopping the two books
from consuming the same capacity. Executor rejection releases a reservation;
an uncertain post-fill receipt retains it.

F0-C makes the existing 6% day, 12% week, 20% month, six-consecutive-loss and
25% drawdown entry brakes a typed, source-scoped shared policy receipt. It
uses every exact `TRADE_CLOSED` F&O ledger event—no single-leg origin prefix—so
defined-risk and partial cash affect both prospective paper books exactly once.
Naive/malformed terminal cash, missing evidence or invalid policy fails the
new entry closed. Both DR and directional paths read the receipt, and the
reservation transaction re-checks it immediately before capacity is consumed.
The change intentionally keeps sizing, signal/quote selection, structural caps,
exit management, settlement and live-spread authority unchanged; exits remain
available during entry halts. Focused shared-policy/risk-switch tests passed
24 warnings-fatal; the wider 79-test F&O selection passed normally. Its
warnings-fatal form has one pre-existing Windows socket-lifecycle warning, not
an assertion failure. Actual partial-settlement release/restart-race repair and
F1 broker cash/margin preflight remain open. Dev only: no Production database,
configuration, broker, order or authority change. Implementation commit:
`bc666fe` (local only; not pushed or deployed).

F0-D binds the already operator-authorised FNO live partial-exit recovery to
the shared-risk read model. An open residual position now supplies capacity only
when its ordered recovery receipts prove each filled/remaining quantity,
generation, exact linked ledger event and pro-rata loss against immutable entry
quantity/loss. A missing or tampered receipt, cash row, generation or residual
loss fails new shared admission closed; nothing automatically releases. This
does not create a partial paper/DR executor, change a broker call, or modify
exit authority. Focused shared-risk checks: 10 warnings-fatal passed; shared
risk plus partial-recovery selection: 32 passed (one ASGI route test excluded
because its existing dependency deprecation is warnings-fatal); broader F&O
risk/DR/orchestrator coverage: 80 passed normally. It is superseded for
partial-cash integrity by F0-E below.
Source commit `7b77341` is Dev-local, not pushed and not deployed.

F0-E completes the F0 **Dev source contract** without changing a threshold,
signal, sizing rule, broker call or exit authority. The atomic live-recovery
receipt now persists its entry/fill price and gross/cost/net cash. The shared
view verifies that immutable receipt's bounded broker-evidence digest,
fill-arithmetic, source/origin/generation ledger identity, exact net cash and
pro-rata residual loss before releasing capacity. A new additive migration
protects recovery rows from update/delete and populated quantity/loss baselines
from rewrite; legacy partial rows missing the new economic receipt deny entry
rather than being guessed/backfilled. Focused shared-risk/recovery tests: 32
passed warnings-fatal, excluding the pre-existing deprecated-ASGI route test
and an existing clock-precision test. Broader F&O admission/lifecycle/DR/
orchestrator coverage: 150 passed normally; its warnings-fatal form surfaced
one pre-existing socket-lifecycle warning in an orchestrator timing test after
149 assertions. F0 remains Dev-only pending GitHub promotion and real paper
admission/recovery observation; F1 cash/margin preflight remains required
before any live funding. Source commit `a9fef57` is Dev-local, not pushed or
deployed.

## October 3 — baseline research is not full portfolio backtesting

`scripts/run_penny_research.py` reuses Lab `penny_breakout_intraday_1m_replay`,
PEN_BASE, one share and prior daily volume. It collects bounded Production
evidence read-only over stdin and replays current Dev in isolated temp files;
outputs only new Dev documents. The reader now explicitly closes its SQLite
handle (Windows success/early-return cleanup regression). No trading rule changed.
Valid August 11–20 PCJEWELLER/SOUTHBANK sample: zero trades; no return claim.
Two rejected samples retain zero-volume/mixed-interval reasons; no silent data
repair. It is evaluator/shadow-lifecycle research, not complete scanner/regime/
capital/broker replay. [F0–F2 and B0–B6 plan](2026-10-03-backtesting-and-fno-safety-plan.md)
and [successor handover](2026-10-03-successor-inheritance.md) are authoritative.
Newly identified F0: DR paper entries lack common risk/capital brakes, while
single-leg kill-switch queries omit spread/partial cash. Do not claim whole-F&O
capital cannot be depleted or spread margin is zero; the safety work is planned.

## October 2 — F&O profit evidence is not qualification

`scripts/assess_fno_profitability.py` is an inert standard-library developer
CLI: SQLite read-only consistent snapshot, exact source/origin cash matching,
paper/live and single-leg/spread separation, IST monthly cash, winner-removal
and realized drawdown. It can stream into an existing container without writing
source there; output is restricted to new files under Dev docs. Missing,
duplicate, mismatched or nonfinite settlements remain unavailable. Stored
position totals are labelled NOT_FULLY_RECONCILED, not silently treated as cash.
See [October 2 results and replay plan](2026-10-02-fno-profitability-assessment.md).
Recent positive paper P&L does not prove current-policy multi-month profitability;
the old constant-IV `fno_backtest.py` is not a full current-policy replay.
No application behavior, authority, schema or Production configuration changed.

## October 2 source work complete for R1–R5; release and Production environment (Dev)

- **R4 (`c118598`).**
  - Scheduler summaries keep durable market-hours/off-hours elapsed histograms (p50/p95 bucket upper bounds).
  - Session CSVs refuse and count writes below a 1 GiB free-space reserve, flag over-quota archives (2 GiB, never pruned), isolate torn rows, and append off the event loop.
- **R5 (`addf46b`).**
  - Allocation research gains recorded batch identity, fixed-pool / realised-equity / real-budget bases, concentration metrics and a causal guarantee.
  - Timing research builds candidates only from verified admission evidence with a frozen zone rule.
  - The daily decision-quality report adds row-id ordering, unique opportunities, unavailable absent books, per-trade decomposition, lineage, missed allocation and best-winner exclusion.

**Production environment (owner-authorised, October 2).** The optional AI is temporarily unavailable. Production `.env` was backed up to the git-ignored `.env.bak-2026-10-02`, and these keys were appended:
- `MINIMAX_ASYNC_REVIEW_ENABLED=true` — must stay true; false forces synchronous AI calls inside the alert path.
- `MINIMAX_UNAVAILABLE_POLICY=proceed` and `MOMENTUM_MINIMAX_REJECT_POLICY=advisory` — AI never blocks.
- `ENABLE_NEWS_CLASSIFIER=0` — no per-headline classifier calls to a dead provider.
- `OPTIONAL_AI_REPORT_DIAGNOSTICS=false` — diagnostics stay off.

Dev Compose rendered with this file shows those agent values and engine logging `json-file 20m x 25`. No other Production file, service or data was changed. When the AI returns, set `ENABLE_NEWS_CLASSIFIER=1` and, after verifying engine status posts, optionally `OPTIONAL_AI_REPORT_DIAGNOSTICS=true`.

## October 2 review priorities R1–R3 completed (Dev)

Response to the S7–S10 independent review (details and receipts in
`2026-10-02-s7-s10-independent-review.md`):

- **R1 (`af6f424`).** S6 replays are bound to evidence.
  - The defined-risk experiment v2 derives entries from persisted rows with re-derived economics, uses same-receipt verified leg quotes, replays the live exit and settlement, and reconciles to the ledger.
  - The single-leg adapter verifies both packets from raw bytes, binds entries to `fno_positions` and the ledger, and counts paired deltas only for reconciled entries.
- **R2 (`dcc2f35`).** The gateway gains `scripts/backlog-reconciliation.js`.
  - `report` is a read-only classification of pending requests, interrupted executions, unsynced orders and dead letters.
  - `apply` takes an operator-reviewed plan, rechecks preconditions in one transaction and writes idempotent receipts. It never deletes, sends, orders or fabricates fills. Dead letters are acknowledged but never resent.
  - Health counts only unacknowledged dead letters.
  - Gateway suite (Node 20): 471 passed, 4 skipped.
- **R3 (`1550886`).** S10 completion.
  - Bounded diagnostics are published behind `OPTIONAL_AI_REPORT_DIAGNOSTICS` once the engine allow-list is deployed.
  - A completed review is posted once, as an edit to its original valid alert with the same buttons.
  - Worker shutdown fails pending reviews closed and discards late results. Socket cancellation is not claimed.

Production was not changed. Still open from the review: R4 (S3 CSV quota and
market-hours timing distributions), R5 (S7/S8 learning contracts) and every
operational acceptance gate.

## October 2 continuation review — current behavior and limits

See [the independent S7–S10 review](2026-10-02-s7-s10-independent-review.md)
and the top of NEXT_AGENT_PLAN.md. They supersede older source-complete claims.

Optional-AI reviewers now receive the original task expiry. Deadline-bound
MiniMax calls use request-local zero retries and deduct queue/prompt/setup
time before dispatch, limiting socket timeout and wall wait with cleanup
margin. Exact-deadline completion remains unavailable. Legacy no-deadline
calls keep configured retries. Daemon join is not transport cancellation;
strict shutdown, bounded cause/stage counters and original-alert completion
delivery remain development. Paper proceeds under its existing advisory policy.

S7 timing freezes snapshot exit settings and equity fees; allocation freezes
snapshot fees too. Runtime-only drift/unknown timing deadline policies are
refused. Earlier incomplete manifests must be replaced before new future data,
never retroactively edited. S8 cash uses event day (including earlier admissions)
and UTC chronology; legacy naive ledger clocks mean UTC. Linked-stream
`daily_cash_drawdown` is unknown for ambiguous equal clocks, and
`version_specific_cash_drawdown` is null without management-version lineage.
The report declares bounded linked cash coverage, not complete daily ledger
coverage. Full setup/regime/delay/hold/cost learning analytics remain source work.

S6 spread is an inert prototype, not an exact-economics-bound research pipeline.
R1 covers typed source/economics/cash binding, actual manifest validation and
finite observations, plus both raw clocks/tokens in the single-leg adapter.
S9 supported reconciliation/migration and S3 CSV capacity/durable elapsed
distributions also remain development. Partner qualification, future evidence
and an authorized delivery canary remain distinct gates. This correction is
Dev-only: no configuration, schema, broker, messaging, Production or authority
change. Agent 368 warnings-fatal; focused research 28; expanded engine 1016
passed with six documented warnings. Tests do not establish profits or delivery.
The broad Windows process hung after reporting its passes and was stopped;
that is not clean teardown verification. Focused runs exited normally.

## October 2 S7a allocation research (Dev)

The paper book admits accepted signals first-come from the fixed INR 50,000
pool (`MOMENTUM_PAPER_FIXED_POOL_V1`). Capital-skipped signals previously left
no price path, so no alternative allocation could be measured.

Capture (paper bookkeeping only): a `zero_shares` admission whose reason is
`capital_exhausted` or `allocation_rounding` now also records
`momentum_paper_candidate_economics_v1` (admitted shares 0, plus the shares the
fixed-pool rule would size with free capital). It subscribes a passive path
with `subscription_kind='CAPITAL_SKIPPED'` (additive column, default
`OPENED`) in the same admission transaction. S4 wiring collects it like any
other path. Nothing is opened, sized or exited differently, and the
exit-study adapter still uses opened admissions only.

`momentum_allocation_research.py` (inert; `freeze`, `evaluate`) reads opened
and capital-skipped candidates with complete verified paths
(`build_allocation_candidates`). It replays three frozen policies on one
common book:
- `FIRST_ARRIVAL_FIXED_POOL_V1`: the live rule via `paper_position_size`.
- `FIXED_EQUAL_V1`: equal notional per admission batch.
- `RISK_BUDGET_PROPORTIONAL_V1`: risk-sized shares scaled to fit.

Exits replay the live evaluator; notional and net cash are released leg by
leg. Outcomes are SELECTED, CAPITAL_UNAVAILABLE, ROUNDED_TO_ZERO,
TICKER_ALREADY_HELD, PATH_UNAVAILABLE or UNRESOLVED. Each policy reports net
P&L, costs, drawdown, peak deployed and turnover, with the delta versus
first-arrival, split HOLDOUT/DEVELOPMENT by a frozen manifest. The pool is
labelled fixed, not drawdown-adjusted. Overspend raises.

Tests (11, warnings-fatal): first-arrival reproduces live admission sizes
(BRIGADE 87 shares, matching October 1 Production); order-invariant
policies under every permutation; 90 random books per policy with no
overspend or duplicate; capital release enabling a later batch; duplicate
and incomplete candidates; manifest drift refusal and holdout split; and a
database run in which a capital-skipped candidate is captured, its path
collected, excluded from the exit study and selected by `FIXED_EQUAL_V1`.
Cross-phase selection: 1114 passed, one known skip. A synthetic concentration
example is a mechanism check, not evidence that any policy earns more.
S7b timing/near-miss research is recorded below; its future-holdout acceptance remains open.

## October 2 S7b frozen entry-timing research (Dev)

S7b adds the inert `momentum_entry_timing_research.py`, with no runtime caller,
broker, HTTP, database or order dependency. Its frozen report compares only
`COMPLETED_BAR_CONTINUATION_V1` (the explicitly supplied next completed-bar
clock and price) with `BOUNDED_PULLBACK_NO_CHASE_V1` (the first existing quote
inside the supplied pullback zone, never above the no-chase cap). It never
invents a fill: no entry, no-chase and incomplete path states remain explicit;
the shared gap/deadline validator and pure current exit evaluator run only
after entry. Re-entry must identify a newly different thesis/state, and a
duplicate ticker/thesis/state is not replayed. The existing isolated shadow
ledger now has a bounded near-miss view over rejected evaluator receipts,
retaining real reject reason/features/config rather than reconstructing an
opportunity. Focused timing/shadow tests: 18 warnings-fatal passed.

This is Dev-only research. Freeze terms before a future session and assess only
post-freeze HOLDOUT observations. No paper/live entry, allocation, sizing, exit,
AI, broker, Production environment or trading authority changed. A rollback is
a GitHub reversion and does not delete prior shadow evidence.

## October 2 S8 daily decision-quality reporting (Dev)

`daily_decision_quality.py` is a read-only daily evidence composer. It keeps
MOMENTUM_PAPER exact admissions/cash, F&O daily audit sources, and isolated
momentum/penny shadow evaluations in distinct book/mode/policy rows; it does
not sum incompatible R values or relabel partial cash as completed trades.
Daily linked cash drawdown requires proven order; version-specific cash drawdown
is unavailable without actual policy lineage. Rejected receipts retain an absence
state. Selection is always `HUMAN_REVIEW_REQUIRED` with no automatic change.
Focused tests: 2 warnings-fatal passed. Dev-only; no database mutation,
strategy retune, capital change, qualification, broker, AI or Production change.

## October 2 S9 operator-state truthfulness (Dev)

S9's first additive source slice makes existing operator surfaces say only what
their evidence supports. Gateway `/health` retains `telegram_status` for
clients, but no longer calls a constructed bot `connected`: its value is
`diagnostic_bot_instance_present` with an explicit
`telegram_status_basis`, or `delivery_backlog_present` when the durable local
dead-letter count is non-zero. The Python-engine probe deadline is released on
every response path. Health reads remain SELECT-only and do not queue, resend,
acknowledge or expire anything.

Penny scan health now preserves the legacy completed-success clock
(`last_scan_at`) and exposes additive `last_scan_attempted_at`, age and a
bounded outcome (`NEVER`, `IN_FLIGHT`, `COMPLETED`, `TIMED_OUT`, `FAILED`, or
`CANCELLED`). An attempt means `scanner.scan_once` was invoked; pre-gate
returns such as no token are not misrepresented as a scan. This lets a slow
provider call be distinguished from no completed scan without changing its
90-second deadline, cadence, provider load or entry behaviour. Operator status
groups realised ledger rows by IST day and reports Momentum, Penny, Edge and
F&O paper books separately as ledger facts, never as live cash/balance estimates;
legacy timezone-less ledger clocks remain UTC as all writers specify. Focused
checks: 2 Node health tests, 14 operator-status tests and 5 Penny-health tests
passed. The old Windows FastAPI import leaves an existing shutdown
event-loop/socket ResourceWarning after the Penny-health run; it is not hidden
as a product result. Dev only; no Production, broker, order, queue or database
migration change. Source commit: `5c9834a` on
`codex/production-correction-hedge-p0`; not deployed.

## October 2 S10 optional-AI source validity (Dev, first slice)

Optional AI is an annotation, never an authority change when the configured
unavailable policy is `proceed`/`advisory`. S10 now removes expired,
undated, or timezone-unverifiable classified sources from the review context
instead of allowing one to expire the entire review before queue admission.
The exact rendered/classified feed context now omits those items and states
`NEWS_UNAVAILABLE` with an exclusion count; a review with no usable news can
still assess deterministic market facts without inventing a catalyst. Fresh
included sources retain their genuine validity bound, and both direct review
and async queue paths receive only the usable classification list. Focused
agent/queue checks: 55 warnings-fatal passed. Dev-only; no API call is made by
the filtering itself, and no paper/live entry, approval, capital, broker or
Production behaviour changed. Remaining S10 work: forward remaining task
budget into provider transport/retry, surface completed annotation updates to
the original alert, and obtain post-promotion evidence.

## October 2 S6 defined-risk spread exit research (Dev)

`fno_dr_exit_experiment.py` is an inert structure-level prototype, separate
from the single-leg experiment. It hashes supplied bytes and checks supplied
leg identities but does not prove they describe the economics or observations.
Its declared target/stop/hard-flat and hold/giveback simulation uses max loss
for R and entry/exit cost terms. Independent review reproduced manifest drift
and NaN-cost acceptance. R1 in the continuation review is required before
interpreting its evidence. No runtime exit or authority behavior changed.

## October 2 S4 passive-path runtime wiring (Dev)

The paper monitor's gateway LTP has no provider timestamp or raw quote, so it
cannot feed source-bound paths. Instead, each research-collector tick attaches
the active subscribed paper tickers (`NSE:TICKER`, up to
`MOMENTUM_PAPER_PATH_MAX_TICKERS=20`) to its existing first quote request
(future plus exact legs). Kite accepts mixed exchanges in one call, so no
provider request is added; the ladder request is unchanged. Equity packets
are removed from the F&O data before any research logic runs and wrapped in
`kite_equity_quote_envelope_v1`. One background writer at a time stores them;
a busy writer drops the batch as a counted gap (`momentum_paper_paths` in the
collection result), and collection never waits on the trading database.
Gated by `MOMENTUM_PAPER_PATH_CAPTURE_ENABLED` (default true),
`MOMENTUM_PAPER_ENABLED` and research collection. Production `.env` overrides
none of these, so no environment change is needed.

Two S4 design defects that would have blocked every real path are corrected:
- Provider timestamps never equal exactly 15:15:00, so the exact-15:15 rule
  could not complete. Opt-in `deadline_quote_policy:
  first_at_or_after_1515_within_gap` (v1 study and S6a) closes at the first
  observation at or after 15:15 within the declared gap, with its real time.
  Capture keeps observations up to the gap past the deadline. Packets
  without the field keep the exact rule (unchanged reports).
- The adapter returned UNAVAILABLE for every path when any one admission was
  incomplete. It now packs complete entries and lists `unavailable_entries`
  with reasons; with no complete entry it returns the first reason as before.

Tests: an end-to-end wiring run (real collector, capture, background writer,
adapter and v1 study, closing at 15:15:25), no-attachment cases, busy-writer
gap, per-entry exclusion and deadline-policy study tests. Cross-phase
selection: 1091 passed, one known skip. Dev only. After promotion: confirm
`momentum_paper_paths` in collection runs and collect five reconciled fresh
lifecycles before any study is treated as evidence.

## October 2 review-response corrections (Dev)

- Session CSV rotation is crash-recoverable: unrecorded archives are
  reconciled into the manifest, torn lines isolated, state written before a
  new header, and header-only files never archived (fixes a permanent
  `FileExistsError` lockout).
- Passive momentum paths require `kite_equity_quote_envelope_v1` packets whose
  ticker, LTP and provider time equal the stored columns, both at capture and
  at export.
- The F&O exit experiment charges the entry order once, and its archive
  adapter verifies raw bytes, identity, duplicates and provider clocks.

See the review's response section. Commits `ea8695d`, `c054bf3`, `bfd343d`;
Dev-only, unpushed.

## October 2 independent S1–S6 review (Dev)

[The review](2026-10-02-s1-s6-independent-review.md) supersedes broad phase
completion claims. Small corrections reject foreign returned DR tokens and
non-finite exit prices, reject impossible/over-late passive receipt clocks and
corrupt scalar prices/economics, retain the first future receipt paired with
exact active research legs (even when the optional ladder times out), and let
ordinary token quotes inherit the screener's bulk lane. Collection counts now
include that additional retained reference observation; received-token coverage
remains unique, and no provider request was added. S6 freezes deep-copy policy
parameters and pin fee schedule/model/source; old manifests must be retained as
development artifacts and replaced by a fresh pre-session freeze, not edited.
The momentum fingerprint now includes `engine.py` and `cost_schedules.py`;
F&O includes `cost_schedules.py`, so fee implementation drift also invalidates
the freeze. No live exit policy, rate, order/AI/partner authority changed.

S1/S2 safeguards have passing affected regression coverage. S3 still needs
rotation crash-fault recovery and deployed session/previous-boot retention
acceptance. S4 is not wired to a runtime quote fanout and hashes establish byte
integrity, not quote-column/provider-packet binding. S5 still needs frozen fresh
evidence, qualification and an authorized delivery canary. S6 momentum and
single-leg tools remain research-only; full archive/economic binding, candidate
partial fee allocation and the defined-risk spread experiment remain open.
None of the new evidence or experiment tools proves profitability or enables
tips. Production was not edited/restarted; this correction is Dev-local.

## October 1 S1 defined-risk economics and truthful settlement (Dev)

New defined-risk paper admissions bind every selected option leg to bounded,
immutable NFO contract identity (underlying, expiry, token, symbol, lot and
leg ratio) and derive structure economics from those selected lots—not the
stale global fallback. Missing, inconsistent or subsequently replaced contract
identity is rejected/unpriceable; legacy rows remain readable but explicitly
unverified and are never reconstructed. At hard-flat, a missing exact-leg price
is recorded as `UNRESOLVED` with a reason and no fabricated zero-cash close;
the existing one-open-structure guard retains that exposure as unavailable
capital. For a fully priced exact close, `ENTRY_MID_EXIT_BID_ASK_V1` retains
model-mid valuation separately from executable bid/ask cash. The terminal DR
row and unique generated FNO ledger close share one SQLite transaction, so a
repeat, concurrent attempt or ledger-write failure cannot create duplicate or
orphaned cash. The read-only F&O daily audit now reports settled, unresolved
and legacy-unverified DR evidence with separate model/cash totals.

Focused warnings-fatal DR/audit checks passed 24. The affected defined-risk,
orchestrator and exit suite passed 84 with one deselected timing-sensitive
exit-recovery test and one existing Starlette lifespan deprecation warning.
The recovery test passes alone but fails only in its grouped run; it is outside
this slice and remains a test-hygiene follow-up. This migration is additive columns only; no configuration,
broker, entry-threshold, scheduler, EXEC, partner or Production behavior was
changed. Dev-local source is pending GitHub review/push and is not deployed;
inspect real post-promotion settlement receipts before making economic claims.
Source commit `9e26e1b` is local on `codex/production-correction-hedge-p0`.

## October 2 S2 initial management-read containment (Dev)

Existing F&O management now gives cancellable provider reads separate budgets:
five seconds for futures/open-exit quotes and ten seconds for an open DR chain
snapshot. The tick records bounded completion/deadline/failure state and
elapsed/cap seconds per read. A deadline cancels and joins the provider task,
then retains the existing unpriced/hard-flat handling; it never encloses a
broker dispatch, cash settlement, admission or SQLite mutation. Focused
orchestrator/recovery/audit checks passed 34. Warnings-fatal mode found an
existing unclosed-socket ResourceWarning in an unrelated stage-duration test,
so this is not claimed as a clean warnings-fatal suite. This is Dev-only and
unpushed/not deployed; source commit `5ae54a8` is local on
`codex/production-correction-hedge-p0`. The completion receipt below records
the subsequent action-clock and provider-timing work.

## October 2 S2 action clocks and provider timing (Dev; partial scope)

The real Kite quote client now returns limiter-wait, transport, parsing,
attempt and retry timing to F&O management; unsupported test/replay adapters
are explicitly marked unavailable. Management retains a conservative oldest
exact-leg quote age, refreshes live action time after provider waits and before
admission cutoffs, and keeps supplied replay clocks deterministic. Exit work
still precedes optional DR entry and no rate/concurrency setting changed.
Focused validation passed 59 with compilation and atlas regeneration. This is
Dev-only/unpushed/not deployed. The independent review below supersedes the
earlier claim that only deployed-session receipts remain. Source commit `d2319e2` is local on
`codex/production-correction-hedge-p0`.

Independent October 2 review corrected action time after held-option and DR
reads and at final directional/DR admission, including database reads before
DR admission. Existing chain/quote freshness thresholds are rechecked at live
admission; supplied replay clocks remain frozen. Signal evaluation retains its
own tick-start cutoff independently of refreshed action time. Quote-age evidence
preserves timezone offsets and reports unavailable when any held leg lacks a
valid timestamp. The scheduler completion/overrun structured logs now retain
management read outcomes, action time and management lag (not new scheduler DB
columns). No mutation is wrapped in a deadline. S1's focused exact-identity,
atomic/idempotent settlement and unresolved-state checks pass; no historical
cash is rewritten. Remaining S2 source scope: exact-held-leg DR read selection,
shared-provider priority with bounded fairness, and DB-wait/timeout-stage timing
attribution. Exit-before-entry ordering alone does not implement queue priority.
See [review and verification](2026-10-02-s1-s2-independent-review.md).

## October 2 S2 exact-leg, shared-priority and timing completion (Dev)

Open defined-risk management reads only the validated persisted leg tokens and
constructs an exact retained-contract snapshot; it never reconstructs a
nearest-expiry chain for legacy, missing or inconsistent identity. Those rows
remain unpriced/unresolved, including at hard-flat, with no fabricated cash.
The shared Kite token bucket now admits up to three management requests ahead
of queued normal work before one normal admission, preserving the original
3/s rate, burst-one capacity and concurrency. Cancelled waiters are removed.
Completed provider evidence separates limiter, transport, parse and retry
backoff; deadline cancellation is explicitly partial/unknown. Management DB
stage elapsed includes any SQLite lock wait and is labelled accordingly rather
than presented as a false lock-only measurement. Focused checks: 105 passed,
one known skip; isolated warnings-fatal DR/Kite checks: 53 passed, one known
skip. The broad warnings-fatal aggregate retains two unrelated socket warnings.
No migration, provider capacity, broker, policy, AI, Production or deployment
change occurred. Deployed recovery/session acceptance remains open.

## October 2 S3 evidence retention completion (Dev)

The Python engine Compose log contract is `json-file` `20m x 25` (500 MiB),
verified from rendered Compose without exposing environment values. Signal CSV
evidence now rotates by IST session: the existing configured path stays the
current-session file, the prior file is atomically preserved under a sibling
session archive with its header/rows intact, and a SHA-256 manifest records the
archive. Unknown legacy files are retained separately rather than misdated;
routine code does not delete archives. Scheduler telemetry keeps a durable
daily final-outcome rollup by market session/job/kind with outcome and stage
statistics before bounded raw events can be pruned. Unfinished crash markers
are not called successful. Research archive capacity/lease protections remain
unchanged. S3 tests passed 57, with 13 rotation/summary tests warnings-fatal
and 8 Compose-verifier tests. This is Dev-only configuration/evidence work;
Its only schema effect is the additive scheduler telemetry-summary table; it
does not migrate trading evidence.
deployment requires operator free-space, prior-boot preservation and full
market-session volume checks. Optional AI remains non-blocking when unavailable.

## October 2 S6b frozen single-leg F&O exit experiments (Dev)

`fno_exit_experiment.py` is an inert research CLI (`freeze`, `evaluate`,
`build-packet`). The baseline replays the live ladder
(`fno_exit_rules.evaluate_single_leg_exit`) over paired futures/option
observations and settles exactly as the paper path does: exit at the basis
(best bid, else LTP), `calc_fno_costs`, and R = net / (entry premium x
FNO_STOP_PREMIUM_PCT x quantity). An exit without a positive basis is
`UNRESOLVED`, never priced. Gaps above the declared maximum, a late first
observation or no observation at/after 15:10 are `INSUFFICIENT_EVIDENCE`.
Manifests pin the candidate, live ladder settings, hard-flat minute, backstop
percentage and a source fingerprint; mismatches are refused, and entries at or
before the freeze are `DEVELOPMENT`.

Candidates:
- `fno_partial_at_target_v1` banks floor(lots/2) lots at the bid when the
  target arms the trail; the rest follows the live ladder. A single lot is
  identical to the baseline.
- `fno_confirmed_time_extension_v1` defers a live time stop only while the
  underlying is not adverse, is within 0.5R of its best and the basis is at
  least 1.10x the premium stop. Every other exit and the hard flat are
  unchanged.

The read-only archive adapter pairs front-future and exact-option events only
when their `received_at_utc` is identical (no interpolation) and hashes the
archived raw-packet digests as provenance. Equity and F&O summary arithmetic
now lives in the shared pure `exit_experiment_metrics.py`, and both freeze
fingerprints include it. The no-runtime-caller guards now inspect actual
imports (AST) instead of text matches.

Tests: 15 F&O experiment tests (live-settlement parity, partial-lot
arithmetic, single-lot identity, confirmed and failed extensions, unresolved
basis, insufficient paths, no future leakage, tamper/setting drift,
development labelling, adapter pairing/provenance, end-to-end CLI, guards).
With the ladder and S6a tests, 30 passed warnings-fatal; related F&O/momentum
suites passed 110. On synthetic paths, partial-at-target slightly
underperformed and a confirmed extension outperformed; these are mechanism
checks, not evidence. Dev-only, not deployed.

## October 2 S6b shared single-leg F&O exit ladder (Dev; behaviour-preserving)

The live single-leg exit ladder that was inline in `fno_orchestrator.py` is now
the pure `fno_exit_rules.evaluate_single_leg_exit`, so paper/live management
and the forthcoming F&O exit experiments evaluate identical rules. Order and
semantics are unchanged: hard flat; then, with a futures quote, underlying
stop, trail stop (armed at target, ratcheting from the best underlying by
`FNO_TRAIL_ATR_MULT` x ATR), premium backstop, and the time stop (before the
trail only, deferred while premium is in profit when
`FNO_TIME_STOP_RESPECTS_PREMIUM`); without a futures quote only the backstop.
The orchestrator still logs trail arming, unparseable entry times and
deferrals, and persists trail state only when no exit fires with a futures
quote present.

Verification: new orchestrator characterization tests (underlying stop wins
over a crushed premium; target arms the trail and a retrace exits on
`trail_stop`; missing futures quote suppresses the time stop) passed against
the inline code before extraction and unchanged after it. A seeded
20,000-case differential test against a frozen transcription of the inline
block matched every exit reason and every persisted trail value. F&O,
scheduler and related suites: 397 passed. No configuration, threshold, order,
settlement or schema change. Dev-only; not deployed. Source commit: `02047d4`.

## October 2 S6a frozen momentum exit experiments (Dev)

`momentum_exit_experiment.py` is an inert, read-only research CLI. It leaves the
v1 study and its evidence-review consumer unchanged. `freeze` writes an
immutable manifest (candidate policy and parameters, live evaluator settings,
cost multipliers, a line-ending-neutral source fingerprint of the study,
experiment and evaluator modules, and freeze time). `evaluate` refuses any
mismatch (`FROZEN_POLICY_MISMATCH`), so a policy cannot be re-tuned after its
outcomes are seen. Entries at or before the freeze are `DEVELOPMENT`; only
later entries are `HOLDOUT`. September 28–October 1 can therefore never be
presented as holdout.

Candidates: `target_hold_trail_v1` (reproduces the v1 alternative exactly) and
`thesis_confirmed_extension_v1`. The latter replays the live pure evaluator and
replaces only its time-stop or target exit, and only while confirmation known
at that quote holds: LTP above VWAP-at-entry, not below entry, within 0.5R of
the running high, and a regime not marked REGIME_3/CRISIS. Volume is not in
the packet and is declared unused. Once a replacement is active, the
protective stop is still checked first, losing confirmation exits at that
observation, the stop only ratchets up (running high minus 1.0R) and 15:15
IST stays forced. The live +1R scale-out and existing fast-stop VWAP deferral
are untouched.

Reports add MFE/MAE in R over the exposure window, giveback, minutes exposed,
worst R, net at 1.0/1.5/2.0x costs, and paired deltas (better/worse/ties,
mean/median/worst, sum excluding the best, cost-stressed sums), split into
all/holdout/development. Qualification stays `NOT_ASSESSED`.

Tests: 13 passed warnings-fatal (continuation, bad continuation, gap through
stop, missing VWAP, crisis regime, target extension, no future leakage, v1
parity, tamper/stale-settings refusal, development labelling, incomplete path,
no-overwrite CLI, no runtime caller). Momentum exit/paper/review suites: 125
passed. No complete source-bound equity path exists yet (S4 collection is
not deployed), so no result is claimed. Equity only; F&O single-leg and
defined-risk experiments are separate future slices. Dev-only, not deployed.
Source commit: `19a5471` (pushed).

## October 2 S5c partner delivery-blocker diagnostic (Dev)

`research_cli.py partner-delivery-blockers --db <engine-db> [--attempts-db
<partner-collection-attempts.sqlite3>] [--session-from/--session-to YYYY-MM-DD]
--output <json>` writes an immutable report (byte-identical retries only).
For every persisted manual-advisory idea it lists ordered blockers:
validation reasons, evidence class, qualification-registry match at decision
time, delivery reasons and terminal status (`SUPERSEDED_*`, `RETIRED_*`,
`QUEUED_NOT_DISPATCHED`, unknown statuses, or `UNEXPLAINED_NOT_DELIVERED`).
Attempts and ideas share no exact identity, so the attempt journal is summarised
per IST session/index and an `attempt_idea_disagreement` is aggregate only; it
detects the S5a frozen-clock defect class. Qualification rows are registry
facts, not re-verified packages. Current delivery flags are labelled as today's
projection, not historical configuration. Databases open with SQLite
`mode=ro`; a missing file is reported and never created. There is no write,
registration, qualification, network, broker or message path.

S5c tests: 10 passed warnings-fatal. CLI/qualification/collection/partner
regression: 110 passed. A Production run was not performed in this session
(copying Production data was not permitted); run it read-only after promotion.
Expected first result from the earlier read-only queries: every September
28–October 1 idea is `EVIDENCE:RESEARCH_ONLY` / no qualification, and the
September 30 indices show attempt/idea disagreement. Dev-only, not deployed.
Source commit: `89a7595`.

## October 2 S5b shared-provider bulk lane and exact-leg-first research (Dev)

Root cause of the recurring 48-second research caps (read-only Production,
September 28–October 1): `run_momentum_screener` fetches about 500 tickers every
quarter hour with up to 50 concurrent waiters on the shared 3/s, burst-one
Kite limiter. A one-token research, F&O snapshot or penny request then waited
behind that backlog for roughly 40 seconds; no provider timeout or retry was
logged. With owner approval, `RateLimiter` now has a third `bulk` lane below
`normal`. Queued normal work is admitted first, but at most three consecutive
normal admissions occur while bulk waits, so the screener cannot starve. S2
management priority is unchanged and still yields to any lower lane after
its burst. The screener's per-ticker tasks are created inside
`provider_lane("bulk")` (a context variable inherited by those tasks only).
Rate, burst, concurrency, signal logic and every other caller are unchanged.

Research collection now requests the future reference and every exact active
selected leg in its first call, then requests only the remaining optional ATM
ladder (the future is re-read with the ladder as before). A ladder deadline
therefore no longer loses an exact retained leg. Each provider call records
bounded limiter-wait/transport/parse/outcome timing in `provider_timing`
(test doubles are labelled `UNAVAILABLE`; deadline splits `PARTIAL_UNKNOWN`).

Expected effect: the token bucket is work-conserving, so total throughput is
unchanged. The screener should take roughly 10–20% longer (about 243 s to an
estimated 270–285 s), because penny scans and F&O snapshots that previously
stretched, timed out or were skipped during its window now complete first.
This is an estimate from Production logs, not a measurement. Verify
`momentum_per_ticker_eval_done` elapsed, research `runtime_capped` counts,
`provider_timing` and penny skip counts on deployed sessions.

S5b/affected tests: 141 passed, one known skip; warnings-fatal S5b,
deadline and leg-subscription subset: 24 passed. The exact-leg regression
fails on the previous collector. A combined cross-module run shows the
`test_partner_orchestrator.py` `wired` fixture erroring after another module
closes the default event loop. A clean HEAD worktree reproduces the same 30
errors, so that ordering issue pre-dates S5b; the partner suites pass 91 alone.
HEAD's combined run also showed a timing flake in
`test_stalled_first_underlying_is_cancelled_and_reports_second_gap`. Both are
test-hygiene follow-ups. Dev-only; no schema/config migration and not deployed.
Source commit: `18c7f2a`.

## October 2 S5a partner candidate action clock (Dev)

Read-only Production evidence (September 30) showed seven partner ideas stored
`REJECTED` with `stale_or_future_leg_quote` while the collection-attempt
journal recorded the same ticks as `candidate_validated`. `persist_candidate`
re-validated at the frozen tick-start clock, so an option chain received more
than five seconds after the tick began looked like a quote from the future.
The manual-advisory tick now passes its live `stage_now()` action clock to
persistence and to conditional-protection construction/precheck. Explicit
replay/test calls without a clock remain frozen. Validation thresholds,
qualification, profile, delivery and message rules are unchanged; a genuinely
stale quote still rejects. Partner/hedge/scheduler suites: 373 passed; the
new late-chain regression fails on the previous source with the Production
reason. Dev-only; not deployed. This does not qualify any partner strategy:
every observed idea remains `RESEARCH_ONLY` and qualification-blocked.
Source commit: `f45ce43` (Dev, unpushed at receipt).

## October 2 S4 equity-path and admission-capital evidence completion (Dev)

New paper-admission outcomes retain an additive, bounded capital snapshot:
the configured fixed INR 50,000 benchmark is explicitly labelled as **not**
drawdown-adjusted, while realised paper cash basis, deployed/reserved/available
notional, risk budget, fee basis and allocation-policy version are recorded for
the decision. Existing `zero_shares` values remain compatible and now carry a
precise cause such as `capital_exhausted` or `risk_budget_below_one_share`.
Opened outcomes also seal the accepted decision inputs as canonical packet bytes
plus a SHA-256 receipt; the read-only audit recomputes the digest from those
bytes and reports a mismatch rather than trusting a formatted hash.

Each opened admission registers an exact-key passive path subscription with the
original share quantity and intraday deadline. The caller-fed collector accepts
only existing provider packet bytes with both provider-observation and receipt
clocks; it has no HTTP client or LTP callback and therefore cannot cause a
provider call on admission or exit. It is bounded by configurable packet and
row retention. The read-only path adapter rejects absent paths, tickers/keys,
clock order/gaps, missing exact 15:15 IST observation, altered original
quantity and forged packet bytes; only a complete path produces an S1 study
packet. Scale-outs cannot change that immutable study quantity. The adapter is
an instrumentation surface, not a strategy, sizing, broker, AI or execution
authority change. Focused S4 evidence tests: 73 passed; `py_compile` passed.

This is Dev-only, additive SQLite evidence. Historical rows remain available
but cannot become source-verified paths. Rollback is a GitHub reversion or
collector disablement; it must retain existing receipts/tables. Before any
operational claim, configure caps, wire an already-existing quote fanout to the
caller-fed collector, and obtain five fresh reconciled lifecycles. These are
instrumentation smoke checks, not profitability, qualification or deployment.

## October 1 Production assessment and smart-trader plan (documentation only)

The [consolidated plan](2026-10-01-smart-trader-consolidated-plan.md) records
verified September 28–October 1 evidence. PR #99 includes the September 26
admission/economics tools; four fresh momentum lifecycles reconcile to cash.
The latest INR 47,647.44 ledger balance belongs to MOMENTUM_PAPER, not penny.
General partner collection/profile exist, but qualifications remain absent;
personalized snapshot refresh is a separate disabled path. Market-hours F&O
management still has long read stages/overlap skips. DR planning currently
uses a configured lot fallback (75), inconsistent with the retained October 6
65-unit contracts, and unpriced/nonatomic settlement paths require correction.
These are assessed findings and planned changes, not implemented behavior.
The goal is timely thesis-based entry/management, capital allocation and
measured learning. Paper remains autonomous, new real-money momentum entries
retain owner EXEC approval, and qualified partner advice grants no order power.
Jev work is deferred. Production was inspected read-only and left untouched.
The optional-AI investigation reproduced pre-submission expiry when a fresh
review includes stale/undated news classification. Today's zero analyst-request
status is consistent with this path; exact historical headline causality is
not retained. The consolidated plan's S10 corrects source-context handling,
deadline propagation and visibility of completed reviews. No AI/runtime change
has been implemented; unavailable review remains informational under proceed.

## September 26 replay economics correction (Dev)

Exact admission identity alone is insufficient. New opened paper admissions
atomically retain a bounded (4096-character) immutable entry-economics snapshot:
UTC entry time, price, original shares, initial stop/risk, target, ATR, VWAP and
regime. The composite review requires all replay terms to match this snapshot
before counting a paired delta. Partial exits cannot redefine original shares.
Missing, legacy, corrupt or mismatched evidence stays unavailable/unresolved.
The additive nullable `entry_economics_json` column is initialized idempotently;
historical admissions are not backfilled. Invalid/oversized snapshots are
omitted without changing paper trading authority. This is Dev-only evidence
hardening, not live approval, partner qualification or profitability proof.
See [the correction and next-evidence plan](2026-09-26-economic-binding-correction-plan.md).

## September 26 source-bound momentum-paper evidence review (Dev)

`momentum_paper_evidence_review.py --db <existing-db> --input <packet>` joins
the Phase-1 paired exit study to the Phase-2 paper lifecycle audit only when
the input entry includes the exact opaque `admission_key`. The exit-study v1
packet remains backward-compatible, but its unkeyed entries are explicitly
unavailable to this composite review. Duplicate keys, same-ticker collisions,
missing/non-opened admissions, incomplete quote paths and unresolved cash all
remain visible rather than being joined or scored. It does not equate an
alternative simulated exit with actual ledger cash; it only reports a paired
research delta for exact, closed, cash-matched lifecycles.

The review is an inert, read-only CLI: no runtime caller, database write,
network, broker, order, scheduler, Telegram, EXEC, allocation, partner or
qualification behavior was added. Focused Phase 1/3 checks passed 20 tests
with warnings fatal; the affected suite passed 214 with one existing Starlette
lifespan deprecation warning. This is Dev-only and not deployed. See [the
Phase 3 implementation receipt](2026-09-26-adaptive-evidence-binding-plan.md).
Source commit `beb7e78` is pushed on `codex/production-correction-hedge-p0`.

## September 26 momentum-paper decision baseline (Dev)

Future `MOMENTUM_PAPER` lifecycles now retain the opaque admission identity
already generated at the real admission boundary. `init_positions_db` adds
nullable `positions.paper_admission_key` with a partial unique index; existing
and non-paper rows remain NULL. A paper open records that exact key, and paper
partial/final ledger events retain it as `origin_ref`. Existing minimal/legacy
schemas still perform their established paper bookkeeping, but evidence without
those keys is explicitly unlinked rather than guessed.

`momentum_paper_audit.py --db <existing-db>` is a read-only JSON audit of
admission → position → ledger evidence. It only makes exact-key joins, treats
the ledger as cash truth, separates partial from terminal cash, cross-checks
position P&L, and exposes missing/duplicate/unlinked lifecycle data as
unavailable or unresolved. It neither initializes a database nor emits a
qualification conclusion. It is not a runtime caller and adds no broker,
order, network, message, schedule, entry/exit or owner-EXEC authority.

Focused audit/lifecycle checks passed 9 tests with warnings fatal; the affected
surface passed 194 with one existing Starlette lifespan deprecation warning.
Compilation/diff checks passed and the atlas now lists 214 modules. This is
Dev-only and not deployed. Source commit `94871f2` is pushed on
`codex/production-correction-hedge-p0`. See [the Phase 2 implementation
receipt](2026-09-26-adaptive-decision-baseline-plan.md).

## September 25 adaptive momentum exit study (Dev)

`momentum_exit_study.py` is an inert, read-only paper-research builder for
paired momentum exit evidence.  It accepts only a bounded timestamped-LTP JSON
packet with a source archive fingerprint per entry and emits a deterministic
`momentum_exit_study_report_v1`.  The baseline reuses the current pure
`evaluate_momentum_exit` state machine and explicitly models the existing
broker SL-M at the first observed LTP trigger.  The only comparator is the
predeclared `target_hold_trail_v1`: after the baseline would close at an
observed target, it holds paper quantity behind a fixed 0.5R trail while
preserving initial stop, time stops and the 15:15 IST hard-flat deadline.

The module rejects a non-timezone-aware, non-chronological, cross-session,
pre-entry, conflicting, gapped or no-exact-15:15 quote path as
`INSUFFICIENT_EVIDENCE`; it never substitutes later quotes or fabricates an
exit.  It includes costs, partial legs, net cash/R, drawdown, observed capture
and unresolved counts, and permanently says qualification is `NOT_ASSESSED`.
It has no DB/broker/HTTP/scheduler/message imports or runtime caller.  Optional
report output is exclusive-create only; it cannot replace past evidence.

Focused exit-study validation passed 13 tests with warnings fatal.  Affected
momentum exit/paper/replay/shadow validation passed 109 tests with one
pre-existing Starlette lifespan deprecation warning.  Compilation and diff
checks passed and the atlas is now 213 Python modules.  This Dev-only research
instrumentation did not change a live/paper monitor, entry/EXEC authority,
risk/broker check, scheduler, database schema, Production service or partner
delivery.  Source commit `cbc5fca` is pushed on
`codex/production-correction-hedge-p0`; it is not deployed.  See [the active
implementation receipt](2026-09-25-adaptive-exit-study-plan.md).

## September 25 owner authority and adaptive-trader vision (plan only)

The current `momentum_paper.py` book automatically opens eligible accepted
deterministic signals and contains no order-placement path; the owner-facing
real momentum entry is a manual Telegram EXEC decision. The owner confirmed
this authority split: an informational news-classifier timeout is not a reason
to add a default paper veto, while each new real-money momentum entry requires
explicit approval and existing execution/risk checks. The next roadmap uses
paper/shadow evidence to compare full trade theses, adaptive exits and capital
allocation so Sentinel can pursue more upside without hiding downside or
loosening live authority. Longer owner holding horizons require a separate
product; partner advice remains manual intraday. See
[the adaptive trader roadmap](2026-09-25-adaptive-trader-vision-plan.md).
This is documentation only; no trading behavior was changed.

## September 25 Production audit interpretation (read-only)

Production merge `f52f4d5c` now includes the September 24 Dev improvements.
The new paper-admission table is already present as
`momentum_paper_admission_outcomes`; 25 September retained TENNIND `opened` and
PARADEEP `zero_shares`. The informational news-classifier timeout did not cause
the earlier TENNIND paper opening. A 16:15 IST post-close container replacement,
not confirmed 200 MiB rotation, explains the missing old-container log view;
the penny scan intentionally does not run after 15:30 IST, so post-restart
health stays stale until a genuine market-hours scan. The F&O parity warning
is diagnostic and does not itself veto a DR entry. General partner intraday
collection and a saved profile exist, but qualification/review are absent;
the hedge pathway's 0/7 operator staging counter is separate. Exact evidence,
limitations and the next plan are in
[the September 25 audit response](2026-09-25-production-audit-response-plan.md).
No source, configuration, broker or Telegram behavior changed in this update.

## September 24 P2 F&O audit evidence and financial interpretation (Dev)

`fno_signals` now retains two additive, JSON-encoded audit fields:
`passed_gates_json` is exactly the ordered prefix which passed before the
first rejection, and `active_kill_switches_json` is the switch evidence
returned for that same gate context.  The existing first reject reason,
gate order, thresholds, sizing and execution path are unchanged.  This means a
`kill_switches_clear` row can prove its preceding gates passed, but it never
claims later sizing, reward/risk, execution or admission would have succeeded.
Legacy rows remain readable and are explicitly labelled as lacking those later
audit fields.

`fno_audit_report.py` is a read-only daily CLI/builder.  It opens only an
existing SQLite file with SQLite read-only mode; a missing path is reported and
is never created.  It groups repeated signal rows by IST bar/underlying/
direction as a decision unit, records re-evaluation counts, projects the
current configured kill-switch policy next to retained switch evidence, and
separates `TRADE_PARTIAL` ledger cash from `TRADE_CLOSED` outcomes per
FNO_PAPER/FNO_LIVE source.  Isolated costs are shown as unavailable because the
ledger schema does not retain them.  It emits no expectancy score or
qualification verdict: a good day or small close sample is not an edge.

Focused report/gate/log/orchestrator/hourly checks passed **84 tests**; the
broader F&O/performance/division surface passed **376 tests**, with two
pre-existing framework deprecation warnings.  Compilation passed.  Production
was inspected read-only and has no recoverable local database copy for the
historical six-row switch identity; new Dev rows preserve it going forward.

## September 24 P2 classifier latency containment (Dev)

The news classifier previously reused the analyst verdict client, which is
configured with one SDK retry for a long reasoning review. That retry policy
made a one-second classifier request capable of making a second transport
attempt. The classifier now receives its own MiniMax/OpenAI client with
`CLASSIFIER_MAX_RETRIES=0`; it retains the per-item request timeout and has no
background thread or detached retry. The main analyst client remains at its
existing `MINIMAX_MAX_RETRIES` policy, so this correction does not change
review behavior.

Both the direct classifier fallback and `agent._maybe_classify_news` explicitly
select the no-retry client. A timeout/error still returns the existing bounded
`UNKNOWN` annotation with zero confidence; deterministic signal capture and
the configured advisory/block review policy are unchanged. Agent validation
passed **361 tests** and Python compilation/atlas generation passed. This is
Dev-only latency containment, not a claim that the external provider will meet
its service objective or that AI determines entry authority.

## September 24 P1 momentum-paper admission forensics (Dev)

Accepted momentum signals now receive durable, bounded paper-admission
evidence. `momentum_paper_admission_outcomes` retains only an opaque
deterministic signal digest, ticker, enumerated outcome and timestamp—never a
raw signal payload. The result is written in the same transaction as an
opening position: `opened`, `already_held`, or `zero_shares` is therefore not
reported before commit. A rolled-back position mutation is separately retained
as `transaction_failure` when SQLite is available; an unavailable database is
logged, never fabricated as durable evidence.

`main.py` now records repeat accepted signals at the alert-deduplication
boundary as `upstream_deduplicated`, rather than falsely saying the paper book
rejected them. A deliberately disabled paper book similarly records `disabled`.
Outcomes are idempotent, retention-bounded by
`MOMENTUM_PAPER_ADMISSION_RETENTION` (20,000), and reopening an already closed
paper position creates a separate immutable admission attempt. This remains a
paper-only bookkeeping path with no order capability or broker authority.

Focused paper/regime/shadow integration checks cover TATATECH-like repeats,
held and zero-share outcomes, disabled state, rollback receipt, retention and
the real upstream boundary (**159 passed**, with one existing Starlette
deprecation). Dev tests establish explainability, not a trading
edge or live/paper promotion. Production was not edited or deployed.

## September 24 P1 F&O tick-tail containment and exit-safe telemetry (Dev)

Read-only Production evidence across the retained 23–24 September window found
27 `fno_tick_complete` runs at or above the 90-second cadence (12 on the 23rd,
15 on the 24th). Their repeated tail was the defined-risk stage; all had zero
DR opens and exits. This identifies speculative paper DR entry preparation,
not ordinary single-leg exit management, as the demonstrated avoidable work.

`fno_orchestrator.py` now gives only the cancellable quote/history reads used
to prepare a *new* paper defined-risk structure one shared 20-second budget.
`asyncio.wait_for` cancels and joins a late input read. It never wraps existing
DR lifecycle management, hard-flat handling, broker-facing single-leg exits,
or a database admission write. Successful DR reads are still reused by the
directional path exactly as before. The tick now separately records
`defined_risk_snapshot`, `defined_risk_management`,
`defined_risk_entry_inputs`, and `defined_risk_entry_admission`; the scheduler
also logs an explicit `dr_entry_skip_reason`.

The stalled-entry test proves prompt cancellation/join, a named timeout, no
order and no detached request; existing F&O/DR/scheduler tests prove the
ordinary path remains intact. This is Dev-only containment, not a claim that
active-exit latency is solved: after reviewed promotion, collect comparable
session telemetry and inspect those new stage fields before any cadence change.
Production was inspected read-only; it was not edited, restarted or deployed.

## September 24 P1 research quote deadlines and coverage evidence (Dev)

The research scheduler now bounds every NIFTY/SENSEX provider await to the
remaining 48-second collection cap, rather than checking only between
underlyings. `asyncio.wait_for` cancels and joins the actual shared Kite
coroutine; it creates no replacement client or hidden late provider task. A
deadline is retained as evidence: current-index `provider_deadline_exceeded`,
exact active-leg tokens already known as unobserved, and later indices as
explicit skipped/unobserved coverage. Nothing is replaced with a stale quote.

Every scheduler result and persisted collection run carries `runtime_capped`,
`elapsed_sec`, `runtime_cap_sec`, `partial_collected` and `partial_count` for
normal, deadline and error paths. Per-index `collection_state` distinguishes
completed, empty, batch error, provider deadline, storage stop and skipped
deadline outcomes. The 60-second cadence and 48-second cap are unchanged.
The first underlying rotates deterministically by UTC scheduler slot and the
chosen order is retained, preventing repeated capped slots from permanently
favoring one index after a restart.
The scheduler regression proves cancellation of a stalled first operation and
complete NIFTY/SENSEX gap accounting; the normal path proves durable telemetry.
Focused coverage passed 54 tests, all research tests passed 62, the combined
collector/scheduler/Kite-client surface passed 173 with one skip and one
pre-existing Starlette lifespan deprecation, and compilation passed. This is
Dev-only evidence: three real logged-in sessions must still
show fairness/latency coverage before operational claims. See the
[P1 receipt](2026-09-24-three-day-production-audit-plan.md).

## September 24 P0 decision-forensics retention verification (Dev)

Read-only Production evidence showed that `python-engine` already uses
Docker `json-file` logging at `20m × 10` (200 MiB) and retained one 18.13 MiB
file across 35.897 hours, an observed 0.50 MiB/hour. Gateway used the same
configuration and retained 2.07 MiB over that interval. There was no rotation
to correct and the 104.42 GiB C: free-space observation did not justify an
unmeasured retention increase. Dev therefore preserves the existing Compose
values and adds `scripts/verify_compose_logging.py`: it renders Compose JSON,
checks only `python-engine`'s `json-file` driver, `max-size`, `max-file` and
the minimum 200 MiB ceiling, and never prints rendered environment values.
The focused unit suite passed 8 tests; direct rendered verification passed.

This is a configuration-regression guard, not proof of three-session
forensics retention: post-promotion acceptance is a read-only inspect and
opening-to-close retrieval for three logged-in sessions. Docker logging
options apply only after container recreation; no recreation was needed or
performed because no Compose value changed. Production was inspected read-only
and no service/data, order or message changed. Details and rollback criteria
are in [the P0 plan](2026-09-24-three-day-production-audit-plan.md).

## September 24 gateway test-lifecycle correction and Dev acceptance (Dev only)

`node-gateway/server/utils/market-hours.js` still refreshes the canonical
holiday calendar from the Python engine during normal module initialisation.
Only when the Jest worker marker and the test setup's explicit
`MARKET_HOURS_TEST_DISABLE_ENGINE_FETCH=1` flag are both present does it retain
the fail-closed fallback without beginning that background request. This avoids
post-test asynchronous logs while making it impossible for an accidental
production flag alone to disable the refresh. `tests/setup.js` preserves the
development-safe `.env.test` fixture and sets only the test-specific switch;
`market-hours.test.js` verifies the exact initialization result.

Dev receipt: Node 20 gateway 461 passed/4 skipped with exit 0; scripts 226
passed; agent 357 passed; dashboard 46 passed and builds. The full engine
runner remains inconclusive because its aiosqlite worker did not exit, so this
is not stated as a whole-engine pass. The code atlas was regenerated (211
Python modules). No Production file/service/data, Telegram delivery or broker
order changed. See
[the release-acceptance receipt](2026-09-24-dev-release-acceptance-plan.md).

The remaining six high-level gates are classified deliberately: no further
product source change is currently unblocked. The Python runner's retained
aiosqlite worker is test-runtime hygiene, to be fixed only after a minimal
owned-leak reproducer; the other gates depend on promotion, real observations,
broker records, held-out evidence and explicit operator approval. Test success
does not replace any of those requirements.

## September 24 real-research authorization package builder (Dev implementation)

`research_cli.py build-qualification-package` assembles the existing
`partner_advisory_authorization_v1` artifact only from bounded, root-confined
full-policy replay reports, a frozen criteria manifest, a reconstructed
held-out aggregate, and an externally created `APPROVED` human-review identity.
It reconstructs every held-out case and the review package before publishing
canonical immutable bytes; source-report policy identity, criteria identity,
scope, review/validity clocks and the 16 MiB authority limit all fail closed.
The output is then locally checked by the same current authority verifier used
at registration and final dispatch.

The command has no database parameter or side effect: it cannot save a profile,
register a qualification, approve evidence, alter configuration, send Telegram
or place an order.  The review identity and validity period must already exist
as separate operator records; `APPROVED` is an input, never inferred from P&L.
Inputs and output are relative to caller-declared roots to prevent traversal,
and a different existing output cannot be overwritten.  See
[the active package slice](2026-09-24-real-research-package-plan.md) for the
exact input layout and remaining real-market prerequisites.

Verification: the package/replay/held-out/review/authority/CLI acceptance group
passed 64 tests with warnings fatal. The wider research/advisory group passed
235 tests with one pre-existing Starlette async-generator-lifespan deprecation;
that legacy warning fails setup when warnings are deliberately made fatal.
The atlas was regenerated to 211 Python modules. Production was not read for
mutation, edited, deployed, or sent any broker/Telegram action.

## September 24 F&O exit recovery (Dev implementation)

An authenticated operator can list pending live single-leg F&O exit intents at
`GET /ops/fno-exit-intents` and reconcile one at
`POST /ops/fno-exit-intents/{position_id}/resolve`. The resolution requires a
named operator, account/order ID, exact intent timestamp and an explicit
confirmation. It reads the current day's broker order book, that order's trades
and net positions. Account, NFO/MIS symbol, SELL side, source tag, order and
trade quantities, terminal status, clocks and residual net quantity must agree.
An unavailable or ambiguous broker response leaves the intent untouched.

A verified terminal zero fill releases the intent with a retained broker
snapshot. A partial fill posts only realized economics to the ledger, scales
the open quantity/risk, preserves cumulative position P&L and permits only a
fresh later exit evaluation. A full fill closes the position and ledger in one
transaction. Each resolution retains bounded broker evidence and its SHA-256,
operator, account, order, and generation. Prior recovered orders are distinct
from unaccounted same-symbol orders. A tick that began before recovery cannot
immediately claim a replacement exit. The no-quote alert no longer suggests a
direct database status edit. Existing ambiguous exits still block automatically.
Daily/weekly/monthly F&O loss switches use each realized ledger event's IST
date, including partial fills; legacy closes without a tagged ledger entry
remain visible through position history.

The operator first reads the authenticated intent list to obtain the exact
`created_at`, then posts a JSON body containing `source: "FNO_LIVE"`,
`expected_created_at`, `account_id`, `order_id`, `operator`, and
`confirm: "RECONCILE_VERIFIED_BROKER_EXIT"`. Both routes require the existing
`X-Internal-Secret` header. A `409` means the evidence is insufficient or
changed; the intent remains for investigation. The stored snapshot is in
`fno_exit_recoveries`, alongside its digest and the linked ledger ID.

Kite's order/trade API is daily; an older unverified intent cannot be cleared
by this endpoint. It needs external statement-level reconciliation and review.
The internal secret authenticates the route; the operator name is an auditable
claim within that trust boundary. No broker order is sent by recovery itself.
Live single-leg activation still needs a supervised broker rehearsal.

## September 23 independent remediation review (Dev only)

The seven incoming audit-fix commits through `674a6fe` required corrections at
real entry, settlement and qualification boundaries. Owner-entry halts now reach
both gateway and direct Kite paths; unknown CAS fails closed. Single-leg F&O exits
retain durable dispatch intents and acknowledged-fill receipts, then atomically
settle position/ledger with source-scoped positive generations and allocated equity.
Ambiguous exits require reconciliation; they cannot automatically resubmit.

New entry advice requires a current `partner_advisory_authorization_v1` package,
recomputed held-out review, exact current code/config/profile, immutable bytes and
explicit dated human approval. Legacy status-only rows and the old bypass setting
cannot authorize delivery. Collection coverage is slot/account scoped; readiness
WARN is not green. Real token/archive freshness is on-demand observational evidence.

Read [the completion and recovery handover](2026-09-21-independent-remediation-review.md)
for contracts, migrations, rollout/rollback and remaining work. Production has not
been changed or re-certified by this Dev completion. Tests prove software behavior,
not strategy profitability or partner qualification.

## September 20 Workflow I.4.D evidence-provenance correction

The opt-in news classifier now renders and classifies one immutable Yahoo +
Google feed snapshot per signal rather than fetching the feeds twice. Each
frozen classification carries the requested ticker, bounded source name/URL,
an aware UTC publication time and a full source-evidence digest. Missing URLs,
missing/naive publication clocks, future-dated items, sources at or beyond the
declared seven-day freshness boundary, and non-HTTP(S)/hostless URLs fail
closed to `UNKNOWN` without a model call. The classification-context digest binds source,
publication time, category, confidence, rationale and prompt version while
deliberately excluding the completion clock.

Optional-review cache keys include that digest only when classification is
enabled, so the disabled-path key remains byte-compatible and changed
classifications cannot retrieve an older opinion. The queue independently
checks context even if a caller reuses an external key. Typed reviews retain
the classification digest/count and immutable `(source digest, URL,
publication clock)` references plus expiry. Sync late completions become
payload-free `REVIEW_UNAVAILABLE`; async unavailable/exception paths retain
their context and deadline. Async READY/CACHED reviews
expose the earlier of request deadline and cache TTL; a shorter repeat request
tightens, and can never extend, that deadline. This is evidence provenance
only: no strategy, threshold, risk, capital, qualification, delivery, broker or
order authority changed. CLI file input parses aware RFC/ISO clocks without
importing the full agent. Focused warning-fatal acceptance is **185 passed**;
the complete isolated network-disabled agent suite is **357 passed**. The
203-module atlas was regenerated. Production remains untouched. See the
[implementation plan](2026-09-20-i4d-classification-provenance-plan.md).
Implementation commit: **`3495ecb`**.

## September 19 Workflow I usefulness-contract correction

Dev now accepts the complete ten-field usefulness snapshot emitted by the
optional-AI worker. The engine strictly validates finite/non-negative latency,
cache-rate bounds and counter consistency, bounded verdicts, and an aware
completion clock while retaining partial legacy envelope compatibility. The
agent's contract-health allow-lists now match its real status producer, and the
hourly check evaluates leakage/usefulness invariants instead of inspecting only
the top-level authority shape. Real-producer boundary tests replace the former
six-field doubles. The dashboard adds p95 latency and last-completion evidence
and displays missing legacy values as unavailable, not observed zero.

This remains opt-in operational evidence under
`OPTIONAL_AI_REPORT_USEFULNESS`; it cannot alter a signal, qualification,
delivery, capital, risk, or order. No schema or default changes. Focused engine
acceptance is **72 passed** with four known framework deprecations; the complete
agent suite is **340 passed** warning-fatal; dashboard acceptance is **46
passed** plus a successful build. Whole-engine acceptance is **4,117 passed,
four skipped and 46 known framework deprecations in 209.34s**. See the
[implementation plan](2026-09-19-workflow-i-usefulness-contract-plan.md).
Production remains untouched.

## September 19 Workflow G.7 range-comparison causality correction

The dedicated `RANGE_REVERSION_V1` research path now evaluates the first
completed bar after its frozen decision cutoff, requires 14 prior bars, and
starts any modeled execution strictly after that decision bar. Later favorable
bars can no longer validate an earlier hypothetical fill. Missing history,
missing decision bars, malformed/duplicate bars, verifier failures and invalid
range geometry return named fail-closed outcomes rather than falling through to
generic completed-bar confirmation.

The predeclared comparison protocol no longer carries the obsolete statement
that range reversion is a confirmation alias or forces every range profile to
`UNCERTAIN`. Range evidence now faces the same completeness, baseline/stress
economics, drawdown and paired uncertainty gates as every other declared
profile. Protocol and evaluator source hashes remain frozen, so existing
protocols cannot be silently reinterpreted and require a new protocol ID under
the corrected implementation. This is offline research only: no qualification,
approval, order, capital or delivery authority. Production remains untouched.
Focused range/comparison acceptance is **81 passed** warning-fatal; the broader
G surface is **222 passed** warning-fatal; whole-engine acceptance is **4,095
passed/four skipped/46 known framework deprecations in 204.44s**.
See the [G.7 plan](2026-09-19-g7-range-comparison-causality-plan.md).

## September 19 Workflow F.10A broker/internal reference verification

Dev now compares each executed `FILLED`/`PARTIAL` broker order in an imported
statement with the retained live order references in `positions` and
`fno_positions`. The report aggregates fills by order, separates cancelled and
rejected evidence, and fails closed on missing schemas, incomplete table
coverage, account-binding gaps, paper/unsupported sources, duplicate
references, missing references and F&O quantity excess. Findings are persisted
idempotently under three additive discrepancy categories and are returned by
the reconciliation CLI and import route.

A unique reference is only `MATCHED_REFERENCE`: internal books still lack
broker `account_id`, statement period bounds are unavailable, and equity
`shares` is a mutable remaining quantity. Accordingly every report keeps
`account_attribution_verified=false`, `broker_reconciled=false`,
`can_place_orders=false`, `can_grow_live_capital=false` and
`authorization_effect=NONE`. This is a diagnostic bridge, not bidirectional
economic reconciliation, capital permission or evidence of profitability.
Focused reconciliation acceptance is **118 passed** with 21 known framework
deprecations; the final whole-engine run is **4,090 passed/four skipped/46
known deprecations in 204.15s**. Production remains untouched. See the
[F.10A plan and receipt](2026-09-19-f10a-broker-internal-reference-plan.md).

## September 19 Workflow C asymmetric source binding

`MODELED_PARTIAL_FILL_V1` now prices each missing leg from the exact verified
asymmetric archive packet that produced the execution-quality diagnostic. The
packet hash, quote clock, bid/ask and quantity flow into the modeled
attribution; the earlier complete decision book is never substituted. Legacy,
missing or malformed source projections fail closed, and held-out ingestion
recomputes the fill and P&L while cross-checking the retained source. Focused
acceptance is **87 passed** with warnings fatal; the broader C group is **259
passed**; the whole engine is **4,070 passed/four skipped/42 known
deprecations**. This remains modeled research evidence, not a broker fill,
qualification, delivery permission, or profitability claim. See the
[source-binding receipt](2026-09-19-workflow-c-asymmetric-source-binding-plan.md).
Production remains untouched.

## September 19 Workflow C partial-fill review correction

The asymmetric partial-fill path now binds its operator-selected CLOSED result
to a dedicated tamper-evident `MODELED_PARTIAL_FILL_V1` replay. Held-out groups
and qualification packages expose full closes separately from modeled partial
closes. The economic correction records mid-plus-2bps entry slippage as a cost,
never profit; missing/invalid top-of-book or naive receipt clocks cannot create
a modeled close. Because this path has no honest full cost-sensitivity artifact,
it remains outside `VERIFIED_FULL_POLICY_REPORTS` and cannot silently satisfy
that qualification gate. Full engine verification is 4,069 passed/four
skipped/42 known deprecations. See the
[C.C2.HOLDOUT receipt](2026-09-19-workflow-c-partial-holdout-plan.md).
Production remains untouched.

## 1. Read this first

September16 momentum/CAS correction: Dev now transfers exclusive live-momentum exit ownership from the intraday monitor to EOD at 15:13 IST and refuses every new square-off submission at or after 15:14:30, before the 15:15 CAS reference-price window. A shared lock prevents the monitor and EOD job from cancelling or selling the same position concurrently. The EOD path checks its deadline before cancelling a protective stop and immediately before submission; if the deadline or another pre-submit failure occurs after cancellation, it attempts to re-arm and durably persist replacement protection and pages the operator. The scheduler uses `max_instances=1`, coalescing and a bounded 60-second misfire window. Final Python receipt:3730 passed/four skipped/42 existing deprecation warnings in214.84s; agent:338 passed. As in the preceding baseline, aiosqlite workers retained the completed pytest processes after the receipt, so the exact test processes were stopped. This changes scheduling/control flow only: no schema, retained position, ledger, broker or configuration migration.

September16 independent post-commit review: the first J.7 resolver hardening was incomplete. The corrected Dev contract HMAC-binds the eligibility decision to the requested symbol, authoritative source label and configuration fingerprint; malformed responses fail closed before execution. Holiday refresh rejects an entire malformed/empty/out-of-validity payload rather than silently filtering it, and both fallback and engine-loaded calendars expire at declared `valid_through`. The audit also removed intermittent operational-coverage SQLite lock races and made J.10 SUMMARY verification deterministic without altering its public JSON shape. Final Dev Python receipt: 3725 passed/four skipped/42 existing deprecation warnings; native runtime-matching Node: 424 passed/four skipped; dashboard: 43 passed and build; agent: 338 passed. The completed Python run retained aiosqlite worker threads after printing the receipt, so clean interpreter teardown remains an environment/runtime follow-up. This is Dev source/test evidence only; Production remains at merge `967e07a`, and real CAS staging captures remain absent. See [independent correction plan](2026-09-14-independent-correction-plan.md).

September14 independent correction: the offline predeclared G/C comparison now freezes full cost metadata and code identity before holdout, supports identical late retries without backdating new protocols, preserves every session/state, reports actual turnover and opportunity-weighted session-cluster uncertainty, and applies baseline/stress gates to every declared profile. Missing declared coverage blocks support even when a lower minimum is met. Explicit CLI paths have no live DB default or backdating switch. Reports retain the complete frozen manifest and remain diagnostic research only: no winner selection, qualification, approval or order authority. See [protocol plan](2026-09-13-predeclared-strategy-comparison-plan.md). G.7 supersedes the historical RANGE alias limitation with a causal dedicated dispatcher; independent trials still are not shared-book capacity proof.

The [external-work audit](2026-09-14-external-work-independent-audit.md) supersedes F-series/J closure claims: actual F&O quantities, account evidence, capital defaults/failure handling, live CAS eligibility, square-off windows and holiday fallback need corrections. Passing synthetic tests are not acceptance of these contracts. Dev only; no push/deployment or operational data mutation.

This is the canonical architecture and feature guide. It is paired with [the code atlas](SYSTEM_CODE_ATLAS.md), [the next-agent plan](NEXT_AGENT_PLAN.md), and [the handover checklist](HANDOVER_CHECKLIST.md). Snapshot date: September 12, 2026. It describes the Dev source, not an assertion that all features are enabled or deployed.

The immediate handover is a bounded engineering deliverable. The broader objective—reliable, cost-aware trading income and valuable intraday partner advice—is not proven achieved. No documentation, test count, model score or green container demonstrates profitability.

**Environment rule:** assess Production at `C:\Users\Urveesh\Desktop\Production_Trading-sentinel`; change Dev at `C:\Users\Urveesh\Desktop\trading-sentinel`; promote through GitHub. Do not copy code directly into Production. Preserve persistent data volumes. Never run `down -v` as part of routine deployment.

Dev branch for this work: `codex/production-correction-hedge-p0`. The release runbook currently names `evolve/smart-strategies`; verify the actual PR target and checkout rather than assuming `main`. See [deployment verification](deployment-verification-runbook.md).

## 2. Product purpose and user constraints

There are two distinct products sharing infrastructure:

1. Sentinel trades/researches the owner's own strategies, with real, paper and shadow modes kept separate.
2. Sentinel provides useful manual intraday advice to an independent partner trading NIFTY and SENSEX. It does not execute that partner's orders.

The owner currently describes approximately INR 8,000 of test capital, originally INR 5,000, with possible progression to INR 20–50k, INR 1 lakh and eventually INR 5 lakh after confidence improves. Deposits are not trading income. No fixed withdrawal target or accepted drawdown percentage was agreed. The owner wants proactive opportunity discovery, not forced trades merely to achieve a daily quota.

The partner trades only intraday, prioritizes hedging, and uses larger capital independently. General market setup advice does not require their personal strategy, broker credentials or a fabricated portfolio. Personalized portfolio protection requires actual exposure evidence; conditional protection requires explicit coverage assumptions. These must not be confused.

An explicit intraday profile was previously observed in Production. The previously observed risk ceiling is configuration evidence, not an endorsement of that risk. Recheck effective settings and the saved profile; do not ask the user to repeat completed setup without evidence it is missing.

## 3. Runtime topology

Release safety now has an optional offline `scripts/verify_data_backup.py` source inventory/tar verifier and [consistent backup/rollback runbook](consistent-data-backup-runbook.md). It checks exact file hashes, bounded safe extraction and header-identified SQLite integrity with WAL recovery in scratch. Its receipt deliberately says consistency is unproven: independent live quiescence and actual source/mount coverage are operator responsibilities. Code rollback must preserve current post-backup books/evidence and prove previous-code compatibility on copies; it must not restore older cash/trade history over the live volume. Dev fixtures, not a Production backup, validate this tool.

| Layer | Entry points | Responsibility | Principal boundary |
|---|---|---|---|
| Reverse proxy | `node-gateway/nginx/nginx.conf`, `docker-compose.yml` | HTTP ingress, upstream routing, independent proxy health | Healthy proxy is not healthy trading |
| Gateway | `node-gateway/server/index.js`, `app.js` | Express app, authentication, broker API services, engine proxy | Order endpoints have real side effects |
| Engine | `python-engine/main.py`, `scheduler_setup.py` | FastAPI, scheduler, strategies, persistence and research | Feature flags and risk gates determine authority |
| Dashboard | `node-gateway/client/src/App.jsx`, `pages/Dashboard.jsx` | Operator views, source/readiness explanations, research UI | Display is not independent broker reconciliation |
| Optional agent | `agent/agent.py`, `advisory.py`, `async_reviews.py` | Typed AI review and asynchronous annotation | AI cannot grant order or delivery permission |
| Persistence | Compose named data volume, engine SQLite, gateway DB schema | Durable books, positions, claims, research journals | Account/mode/run scope is mandatory |
| Operations | release stamps, health, telemetry, watchdogs, autoheal | Detect liveness/deployment failures | Restart success is not correctness evidence |

The Compose stack includes the three application services, nginx, ngrok and autoheal. Dependencies start best-effort rather than requiring every service to be healthy first. Read the actual Compose resource limits and healthchecks before changing concurrency.

## 4. Authority and evidence types

| Type | Meaning | Must never be presented as |
|---|---|---|
| LIVE | Broker-facing trading path with its own controls | Guaranteed broker-reconciled profit merely because mode says LIVE |
| PAPER | Simulated execution/accounting | Real income |
| SHADOW | Proposal/evaluation/fixture evidence without execution authority | Actual fills or partner delivery |
| REPLAY | Historical or chronological study using declared assumptions | Live observations or held-out proof when tuned on the same data |
| Operational status | Jobs, heartbeats, retries, readiness | Trading opportunity or edge |
| Strategy qualification | Reviewed evidence for a specific policy/index/profile scope | Permission for every strategy or perpetual profitability |

The safe direction of dependency is market inputs → deterministic strategy → validation/risk → applicable execution/delivery authority. Research and AI annotate this process; neither bypasses it.

## 5. Trading feature map

### Core equity and momentum

`engine.py` supplies signal calculations; `regime.py` and `breadth.py` provide market context; `universe.py` supplies the candidate universe. `portfolio.py` and `risk_engine.py` filter/allocate, with `main.py` composing scheduled application behavior. `position_tracker.py`, `momentum_exits.py` and `chandelier_stop.py` participate in position/exit management. `momentum_paper.py`, `momentum_shadow.py`, `momentum_replay.py`, `backtest.py` and `walk_forward.py` provide separate simulation/research surfaces.

Do not infer live performance from a backtest or change a shared exit helper without checking its live and paper callers. A viable signal still needs executable pricing, sufficient capital, risk approval and current data.

### Penny and EDGE

`penny_scanner.py` and `penny_universe.py` handle scanning/universe preparation. Engines include `penny_engine_breakout.py`, `penny_engine_connors.py` and `penny_edge_engine.py`. `penny_edge_orchestrator.py`/`penny_edge_live.py` compose EDGE behavior. `penny_risk.py`, `penny_executor.py`, `penny_position_reservations.py` and `penny_execution_journal.py` cover risk, submission/reservations and durable execution evidence.

Related modules provide regime/sector filters, health, signal logs, attribution, heatmaps, static company data and backtests. See all `penny_*` entries in the atlas. These are a family of strategies, not one fungible P&L stream. Small expected gains are especially sensitive to costs and thin liquidity.

### F&O

`fno_models.py` defines contracts/quotes/directions. `fno_instruments.py` builds contract indexes, expiries, lots and strike metadata. `fno_underlyings.py` distinguishes index/exchange scope. `fno_chain.py` obtains chain snapshots and strike selection. `options_math.py` supplies options calculations.

`fno_engine_mom.py` evaluates the ORB/momentum policy: opening-range structure, volatility/trend/volume context and thesis levels. `fno_gates.py`, `fno_risk.py`, `fno_executor.py`, `fno_positions.py`, `fno_orchestrator.py` form the separate trading path. `fno_defined_risk.py` and `fno_dr_book.py` provide defined-risk spread logic/bookkeeping. Analytics, OI store, signal log, shadow and report modules retain separate evidence.

Earlier Production audits reported negative F&O performance. A dominance of `no_or_break` is not itself proof that a filter should be loosened. Reproduce losing trades and distinguish data/session defects from genuinely absent setups.

### CAS and market-session correctness (workstream J)

`market_calendar.py` is the single source of truth for session clocks. Beyond the historical `is_market_open` / `is_trading_day_sync` it now exposes a bounded session-phase classifier (`classify_session_phase(observation_at, *, symbol, is_derivative, cas_eligible)`) and a CAS-eligibility gate (`is_cas_eligible(symbol)`). The classifier returns exactly one of ten documented phases — `CLOSED`, `PRE_MARKET`, `CONTINUOUS_TRADING`, `CAS_REFERENCE_PRICE_WINDOW`, `CAS_ORDER_ENTRY`, `CAS_LIMIT_ENTRY_ONLY`, `CAS_MATCHING`, `CAS_POST`, `DERIVATIVES_CAS_ALIGNED`, `UNKNOWN` — for every (timestamp, symbol, is_derivative, cas_eligible) input. It never raises and never consults `NSE_HOLIDAYS_STATIC` (a deliberate separation of clock-only phase from holiday awareness).

The CAS-aware phases are gated on `is_cas_eligible`, which consults the operator-supplied list `settings.CAS_PHASE1_FNO_UNDERLYINGS` (env var, plain CSV string) at the moment it is asked. The list is operator-curated per NSE/CMTR/72394 — Dev ships an empty string so the classifier stays in non-CAS mode until the operator opts in. Config typing is deliberately a `str` (CSV at the wire layer) so pydantic-settings v2.2.1 does not JSON-decode the env var. `is_cas_eligible` does a lazy `from config import settings` so `market_calendar` stays importable in isolation, defends against import failures by returning False (the bounded default), and memoises the parsed set with `@functools.lru_cache(maxsize=1)`.

J.3.1 added a `cas_eligible: bool | None = None` keyword to `classify_session_phase` so callers can resolve eligibility upstream and bypass the settings lookup. Default `None` preserves the pre-J.3.1 byte-identity; explicit True/False forces the branch. This is the boundary that J.3's `--eligibility-list` and future staging captures depend on.

The G forward-compat seam `proactive_intelligence.py::stamp_session_phase` is now wired (J.4) to the real classifier. Contract: `observation_at=None` still returns `"UNKNOWN"` (preserves the `_ensure_shadow_run` manifest site); a real datetime returns the bounded phase from `classify_session_phase`. Optional kwargs `symbol` / `is_derivative` / `cas_eligible` mirror the classifier. Lazy import of `market_calendar` inside the function keeps `proactive_intelligence` policy-agnostic at module-import time.

Operator evidence collection during a real CAS window uses `python-engine/tools/j2_cas_probe.py` (staging-only CLI; `--dry-run` for Dev sanity checks). The probe captures the classifier verdict + eligibility verdict + Kite quote (cash fields + circuit limits + broker-side extras), with `--now` or `--observation-at`, `--output` JSON path, `--eligibility-list`, `--require-eligible`, `--validate`, and `--schema-print`. Inline JSON Schema (`SCHEMA_VERSION: 2`) pins the document shape. Strict ISO 8601 parser refuses naive timestamps. It is NOT exercised by pytest — see `docs/2026-09-13-j2-broker-behaviour-probe.md` for the operator procedure and six-point review checklist.

J.3 (this slice's J.3.1 + J.3.0) sharpens the probe (`SCHEMA_VERSION: 2`, inline JSON Schema, `--schema-print`, `--eligibility-list`, `--require-eligible`, `--validate`, strict ISO 8601) and adds the deterministic review tool `python-engine/tools/j2_capture_review.py`. The review tool runs the six-point checklist + an opt-in OHLC-continuity cross-window check against captured JSON and exits 0 only when every check passes. The operator protocol (`docs/2026-09-13-j3-capture-protocol.md`) prescribes a six-window capture grid (15:10 / 15:17 / 15:22 / 15:27 / 15:32 / 15:42 IST); the receipts land in `docs/j2_captures/YYYY-MM-DD/`. Until those receipts arrive, the broker-behaviour question remains open.

J.5 ends the Python↔Node holiday drift. The Python `NSE_HOLIDAYS_STATIC` (re-verified against NSE Equity 2026 trading-holiday list) is the canonical source of truth across the whole system. `python-engine/holiday_drift.py` is a pure drift detector that parses the Node source as text and emits `{verdict, drift_count, python_only, node_only, in_both}`. The CLI `python-engine/tools/holiday_drift_check.py` wraps it for CI / operators: exit 0 on `ALIGNED`, exit 1 on `DRIFT`. The Node gateway fetches `GET /holidays` from the engine at boot (5s timeout) and mutates `NSE_HOLIDAYS` in place on success. The Node `NSE_HOLIDAYS_FALLBACK` is now the **exact ISO projection** of `market_calendar.NSE_HOLIDAYS_STATIC` (20 dates) — the pre-J.5 18-date hand-maintained list has been retired by the independent correction plan; the fallback is now safe to use before the asynchronous engine refresh completes, overridable via `MARKET_HOURS_HOLIDAYS_JSON`. The static set has a documented validity period: `NSE_HOLIDAYS_VALID_THROUGH = '2026-12-31'`; once the embedded fallback passes this date, `isHolidayCalendarUsable()` returns `false` and `isMarketOpen()` / `isPreMarket()` fail closed rather than assuming a future weekday is open. `replaceHolidays` records the source validity date so a successful engine refresh can extend the live set's validity. `routes_holidays.py` exposes `valid_through` in the response so consumers can see when the static set expires. J.5 ships 18 new drift tests + 6 new Node holiday tests (the pre-correction drift signature Python=20/Node=18 is documented as historical; the post-correction state Python=20/Node=20/drift=0/verdict=ALIGNED is pinned); the python-engine suite is at 3245/4/0 with the previously-failing surface test resolved by the documented golden-refresh.

J.6 lands the Node session-phase mirror. Before J.6, every Node caller — `routes/health.js`, `services/executor.js`, `index.js` (the telegram callback handler) — could only see a binary `isMarketOpen()`; CAS sub-windows were structurally invisible on the Node side even though the J.1 Python classifier knew about them. J.6 ships `sessionPhase(observation_at, opts)` and `currentSessionPhase()` as Node-side mirrors of `python-engine/market_calendar.classify_session_phase`. The contract is bit-perfect: 10 documented phases (CLOSED, PRE_MARKET, CONTINUOUS_TRADING, CAS_REFERENCE_PRICE_WINDOW, CAS_ORDER_ENTRY, CAS_LIMIT_ENTRY_ONLY, CAS_MATCHING, DERIVATIVES_CAS_ALIGNED, CAS_POST, UNKNOWN), identical boundary semantics, IST-clock-aware via `Intl.DateTimeFormat({Asia/Kolkata})`. `sessionPhase()` accepts Date / millisecond-number / ISO-8601-string inputs; naive timestamps default to UTC (matching Python); invalid inputs return `UNKNOWN` without raising. The Phase-1 CAS eligibility probe is mirrored via `opts.cas_eligible` (caller-supplied override) with fallback to the J.2.1 list when absent. Wiring: `routes/health.js` exposes `session_phase: currentSessionPhase()` in `/` GET; `services/executor.js` logs `execution_phase_at_reject` whenever the `isMarketOpen()` guard fires; `index.js` telegram callback now reports "Market in {phase}. Cannot execute now." The invariant is pinned by a 2,355-vector golden regenerated by `python-engine/tests/fixtures/regenerate_session_phase_golden.py` from the live Python classifier and asserted bit-perfect by `node-gateway/server/tests/unit/sessionPhase.test.js`. The regenerator uses two sweeps: a wide minute-granularity sweep (8 days × 24 hours × 4 minutes × 3 option-combos = 2304 vectors) plus a focused second-granularity boundary pass (17 instants × 3 option-combos = 51 vectors) that hits `CAS_LIMIT_ENTRY_ONLY` (15:29:30 - 15:30 IST, ~30-second-wide sub-window) and `CAS_POST` (derivatives 15:40 - 16:00 IST) — both invisible to a minute-granularity sweep. Net: Node full suite 360/4/0 (was 317/4/0; +43 new tests in `sessionPhase.test.js`); python-engine full suite 3247/4/2 pre-existing failures (both unrelated to J.6 — verified by zero imports of any J.6 file). J.6 ships observability only; CAS-aware execution gating is the J.7 plan slice.

J.7 closes the loop on CAS awareness. J.6 gave the Node side visibility into the bounded phase; J.7 uses it to gate execution. Before J.7, an EXEC at 15:30 IST would be sent to Kite during `CAS_MATCHING` — NSE rejects, broker queues for post-CAS execution, or broker silently drops. Both outcomes are production hazards. J.7 ships `isExecutionAllowed(opts)` in `node-gateway/server/utils/market-hours.js` and `execution_allowed(...)` in `python-engine/market_calendar.py`. Both return `{allowed: bool, phase: str, reason: str|null}`. The translation table: `CONTINUOUS_TRADING` / `DERIVATIVES_CAS_ALIGNED` -> allowed; `PRE_MARKET` -> blocked unless `allow_pre_market=true`; `CLOSED` / all `CAS_*` / `UNKNOWN` -> blocked. NEW `node-gateway/server/utils/errors.js::CasPhaseError(phase, reason)` (status 422, code `cas_phase_blocked`) carries the phase + reason for the operator dashboard / telegram callback. Wiring: `services/executor.js` replaces J.6's `currentSessionPhase()` observability log with the J.7 verdict — throws `CasPhaseError` for CAS-blocked phases (preserves `MarketClosedError` for `CLOSED` so the existing error-code surface stays compatible); `index.js` telegram callback shows `verdict.reason` for CAS-blocked phases. The invariant is pinned by a 3,525-vector golden regenerated by `python-engine/tests/fixtures/regenerate_execution_allowed_golden.py` and asserted bit-perfect by `node-gateway/server/tests/unit/isExecutionAllowed.test.js`. Window boundary correction: J.6's docs listed CAS sub-window widths that did not match the live Python constants — the actual boundaries are `CAS_REFERENCE_PRICE_WINDOW` 15:15-15:20, `CAS_ORDER_ENTRY` 15:20-15:25, `CAS_LIMIT_ENTRY_ONLY` 15:25-15:30, `CAS_MATCHING` 15:30-15:35, `CAS_POST` (cash) 15:35-16:00, `DERIVATIVES_CAS_ALIGNED` 15:30-15:40. Net: Node full suite 380/4/0 (was 360/4/0; +20 new); python-engine full suite 3267/4/1 pre-existing failure (the J.6-documented `test_coverage_vocabulary.py` aiosqlite-threading flake).

J.7-HARDENING (independent correction plan) replaces the Node-carried CAS-eligibility list with an authoritative Python projection. Before this slice, `isExecutionAllowed` ran a pure check that consumed whatever CAS eligibility the Node supplied — in practice the Node carried a hardcoded `CAS_PHASE1_FNO_UNDERLYINGS` env list, creating a second, silently divergent eligibility surface. NEW `python-engine/routes_market_session.py::cas_eligibility` is the **single authoritative projection** of `market_calendar.is_cas_eligible`. The route is authenticated via `X-Internal-Secret` (returns 403 without the secret), returns `{symbol, cas_eligible, source, source_version}`, and the `source_version` is a SHA-256 hash of the configured CSV — the configured symbols are not disclosed over the wire. NEW `node-gateway/server/services/cas-eligibility.js` is the **only** path that fetches CAS eligibility. `resolveCasEligibility(symbol, observationAt)` short-circuits outside `isCashCasEligibilityResolutionWindow` (the 15:15-15:29 IST cash-CAS-affected interval) with `{required: false, resolved: true, casEligible: false}` so we never make an unnecessary HTTP call; inside the window it fetches the Python projection with the configured timeout. Failures return `{required: true, resolved: false, casEligible: null, reason: ...}` — the operator sees the human-readable reason and the system fails closed. NEW `entrySessionVerdict(symbol, observationAt)` chains eligibility resolution with the existing `isExecutionAllowed` verdict: an unresolved eligibility returns `{allowed: false, phase: 'CAS_ELIGIBILITY_UNAVAILABLE', reason: ...}`. Both `services/executor.js` and `index.js` (the telegram callback handler) now call `entrySessionVerdict(signalData.ticker, new Date())` **before** any DB UPDATE / EXECUTING transition / answerCallbackQuery — a `CAS_ELIGIBILITY_UNAVAILABLE` failure short-circuits execution; `executor.executeSignal` is never reached; no `EXECUTING` status is recorded; the operator sees `show_alert: true` with the phase-specific reason. NEW `tests/test_market_session_route.py` (3 tests: 403 without secret; 200 projects the configured CSV onto the supplied symbol; 200 returns `false` for unconfigured symbols). NEW `tests/unit/cas-eligibility.test.js` (3 tests: does not fetch outside the affected window; uses the authenticated Python projection inside the window with the `X-Internal-Secret` header; fails closed when the resolver is unavailable). Updated `tests/unit/executor.test.js` (2 new tests: blocks before broker calls when CAS eligibility cannot be resolved; passes the actual ticker to the authoritative resolver), `tests/integration/telegram-callbacks.test.js` (1 new test: blocks the EXEC callback when authoritative CAS eligibility is unavailable), `tests/integration/approved-snapshot.test.js` (mock added so existing tests reach the executor). `utils/errors.js` now exports `CasPhaseError`. The Node side is no longer a second source of eligibility truth — when the Python projection is unreachable, the Node side blocks entry rather than defaulting to continuous trading.

J.8 surfaces the bounded phase to the operator. J.6 made the bounded phase available via `health.session_phase`; J.8 makes the dashboard render it. NEW `node-gateway/client/src/utils/sessionPhase.js` is the pure single-source-of-truth utility: bounded phase -> colour class + display label + `isExecutionBlockedByPhase`. Fail-closed contract: any non-bounded input (null / undefined / garbage strings / numbers) returns `executionBlocked: true` so a misconfigured health payload never silently allows an order that the server would reject. NEW `SessionPhaseBadge` (compact chip with lock-icon when phase blocks) renders in `StatusBar.jsx` next to the binary "Open/Closed" indicator. NEW `SessionPhaseCard` (full card with phase label, broker-order verdict, and short description) renders on `Dashboard.jsx`. `SignalCard.jsx` gains a new `sessionPhase` prop and disables the EXEC button via `isExecutionBlockedByPhase` — the dashboard mirror matches the J.7 server gate so the operator's view matches what the server accepts. NEW `tests/sessionPhase.test.mjs` (15 tests via Node's built-in `node:test` runner): phase enumeration, label/color completeness (10/10), `coercePhase` null/undefined/garbage handling, `isExecutionBlockedByPhase` (8 blocking + 2 allowed + bad inputs), `describePhase` bundle, colour-bucket assertions (CAS=yellow, allowed=green, CLOSED/UNKNOWN=red). Net: client full unit suite 40/0/0 (was 25/0/0 at J.7 close; +15 new); Node full suite 380/4/0 unchanged (J.8 changed no Node code); python-engine J-slice 209/0 warnings-fatal (no regression). J.8 ships observation only; CAS-aware signal handling is the J.9 plan slice.

J.9 stamps the bounded phase at signal insertion. Before J.9, `received_signals` recorded `signal_time` (when the signal was generated) but not the phase at which it was received. Operators querying "how many signals arrived during `CAS_MATCHING`?" had no way to answer. NEW `received_signals.session_phase TEXT NOT NULL DEFAULT 'UNKNOWN' CHECK (session_phase IN (...10 phases...))` column in `node-gateway/server/db/schema.sql`. The `DEFAULT 'UNKNOWN'` covers existing rows (pre-J.9) so the additive migration does not break the production SQLite DB. NEW `stampSessionPhaseForSignal(ticker)` in `node-gateway/server/utils/market-hours.js` returns one of the 10 documented phases (never null, never an unrecognised string); non-string tickers (null, undefined, numbers, objects, arrays) route through `currentSessionPhase()` and the result is bounded by `STAMPABLE_PHASES` (the exported Node-side mirror of the DB CHECK constraint). Drift between `STAMPABLE_PHASES` (Node) and the DB CHECK (SQL) is a category-1 invariant failure. Wired into `routes/signals.js` (OpenClaw webhook insert) and `routes/internal.js` (Python engine callback insert) -- the phase recorded is the LIVE phase at the moment of arrival, not `signal_time`. NEW `tests/unit/sessionPhaseStamping.test.js` (5 tests): schema.sql CHECK constraint cardinality + `STAMPABLE_PHASES` cardinality pinned at 10; helper never throws on bad input; output always in the bounded set. Net: Node full suite 385/4/0 (was 380/4/0 at J.8 close; +5 new); python-engine J-slice 224/0 warnings-fatal (defensive regression only; J.9 made no Python changes).

J.10 ships the CAS-branch reachability gate, NOT an auction strategy. Plan §14 explicitly forbids auction-imbalance research and auction-based strategies: "any auction-based strategy is separate research with auction execution semantics, not an extension of a continuous-market fill model." The J.4 done-doc says "without `docs/j2_captures/YYYY-MM-DD/` receipt files passing `j2_capture_review.py`, the classifier's CAS branches are wired but unverified against real Kite." J.10 ships the **runtime gate** that enforces this boundary. NEW `python-engine/cas_reachability_gate.py`: pure / total module that walks `docs/j2_captures/`, reads each J.3 capture's `classifier.phase`, and emits `{verdict, captured_phases, missing_phases, coverage_pct, captures_scanned, captures_skipped}`. `CAS_BRANCHES_REQUIRING_EVIDENCE` is the 6 branches (5 CAS sub-windows + DERIVATIVES_CAS_ALIGNED). Defensive invariant: `CAS_BRANCHES_REQUIRING_EVIDENCE` is checked against `market_calendar._VALID_SESSION_PHASES` at import time -- drift between the gate's required set and the mirror's bounded set raises `RuntimeError` (category-1 invariant failure). NEW `python-engine/tools/cas_reachability_check.py`: operator-facing CLI with `--captures-dir`, `--json`, `--write`; exit 0 on REACHABLE, 1 on UNREACHABLE, 2 on missing directory. NEW `python-engine/tests/test_cas_reachability_gate.py` (9 tests): empty / partial / full coverage, extra-files tolerated (SUMMARY.md/README.md/review_log.md ignored), corrupt-capture skipped, non-bounded-phase ignored, format_report shape, write_report idempotency.

J.10.CLOSURE lands the operator-facing SUMMARY.md surface. **Critical bug fix discovered during J.10.CLOSURE**: `_safe_phase_from_capture` was reading `doc["classifier"]["phase"]` and `doc["phase"]` -- but the J.3 capture schema (per `tools/j2_cas_probe.py::CAPTURE_JSON_SCHEMA`) stores the bounded phase at `rows[i].classifier_phase`. The gate was silently counting every capture as "skipped". Fixed to iterate `rows[]` and read `rows[0].classifier_phase`. NEW `update_summary(report, summary_path, *, captures_dir=None)` in `cas_reachability_gate.py` renders the gate's verdict into a deterministic markdown SUMMARY.md. NEW `--update-summary` flag on `cas_reachability_check.py` CLI. NEW auto-update hook on `j2_capture_review.py` happy-path: SUMMARY regenerates automatically when a capture review passes; fail-path leaves the SUMMARY untouched (fail-closed). NEW `tests/test_cas_reachability_summary.py` (10 tests pinning the SUMMARY contract: verdict line shows bold REACHABLE/UNREACHABLE, missing-branches section, "Generated at" marker, captures_dir path, review-tool pointer, never raises on missing dir, fail-closed, idempotent). NEW `tests/test_j10_closure_e2e.py` (3 tests: happy-path review auto-updates SUMMARY, failed review does NOT auto-update, in-process `main()` helper path). `tests/test_cas_reachability_gate.py` fixtures updated to the J.3 schema shape. Net: python-engine +22 tests (was 3267/4/1 at J.7 close; now 3289/4/1 pre-baseline at this slice); Node full suite 385/4/0 (no Node changes); client 40/0/0 (no client changes). The SUMMARY.md is the persistent audit surface; the gate currently returns UNREACHABLE because `docs/j2_captures/` has no operator-supplied staging captures -- flipping to REACHABLE is operator work (run probe in staging, review captures), per plan §14. Net: Python `test_cas_reachability_gate.py` 9/9 PASS warnings-fatal; J-slice (16 files) 268/22 (the 22 are the J.6-documented `test_calendar_gates.py` cross-test isolation noise, verified by isolation re-run); Node full suite 385/4/0 unchanged (no Node changes in J.10); client full suite 40/0/0 unchanged. CLI invocation on the empty `docs/j2_captures/`: exit 1, UNREACHABLE, 0.0% coverage -- the **correct** state for J.10 (the operator-supplied captures are still pending; J.10 is the gate that waits for them). Closing this gap is the operator's responsibility, not a J.10 follow-up.

J.10.CLOSURE catalog enhancement: a follow-up slice (`12912b1`) adds a per-branch `captures_by_branch` field to the gate's report dict (per-branch list of relative paths) and renders it in three places: SUMMARY.md gains a `## Captures catalog` section listing each captured branch's captures as relative paths under a markdown sub-heading (branches with zero captures render `(no captures yet)`); the CLI's human-readable output gains a `captures catalog:` block; the CLI's `--json` output now includes the field. The catalog is purely informational -- the gate's verdict remains purely count-driven. NEW `tests/test_cas_reachability_check.py` (9 tests via subprocess) pins the CLI contract end-to-end: exit codes (0 REACHABLE / 1 UNREACHABLE / 2 missing-dir), `--json` shape stability (exactly 7 documented keys), `--update-summary` writes SUMMARY.md, `--summary-path` overrides, `--write` persists JSON report independent of `--update-summary`, human output renders the catalog. Net: python-engine +12 new tests (3 catalog + 9 CLI); 0 regressions; Node 394/4/0 + Client 40/0/0 unchanged.

J.10.CLOSURE runbook fix (`1c35633`): the SUMMARY's "How to add captures" section previously showed a probe command with the legacy `--observation-at 15:22:00 IST` syntax, which `tools/j2_cas_probe.py` does not accept (it takes ISO 8601 timestamps). Replaced with a per-branch IST-window cheat-sheet (CAS_REFERENCE_PRICE_WINDOW 15:15-15:19:59, CAS_ORDER_ENTRY 15:20-15:24:59, CAS_LIMIT_ENTRY_ONLY 15:25-15:29:59, CAS_MATCHING 15:30-15:34:59, CAS_POST 15:35-15:59:59 cash, DERIVATIVES_CAS_ALIGNED 15:30-15:39:59) and two ISO 8601 example commands. The runbook cross-references the "Captures catalog" section so a passing review surfaces in the same neighborhood without re-running the CLI. +3 new tests in `test_cas_reachability_check.py` (CLI subprocess): per-branch IST-window render, legacy-syntax rejection, catalog cross-reference.

J.10.CLOSURE `--status` flag (`2b7a670`): the CLI's multi-line human-readable output is awkward for shell prompts, monitoring agents, and CI summary lines. NEW `--status` flag emits a single-line summary: `J.10: <VERDICT> <coverage_pct>% (<captured>/<total> branches, <scanned> scanned, <skipped> skipped)`. Exit code follows the gate's verdict (0 REACHABLE / 1 UNREACHABLE / 2 missing-dir) so it composes with CI gates exactly like the multi-line mode. `<captured>` counts branches with >=1 capture (the gate's count-driven contract), NOT the total number of capture files. +3 new tests: single-line format on UNREACHABLE, REACHABLE 100.0% on all 6 branches, count-driven branch counting (5 captures on one branch = 1 branch). Net: python-engine +6 new tests since J.10.CLOSURE close (3 catalog + 9 CLI + 3 runbook + 3 status = 18 over two sessions); 380/380 PASS at this point.

The historical 15:30 → 15:40 expiry mismatch for derivatives (`fno_chain.EXPIRY_CUTOFF_HOUR/_MIN` and `hedge_strategies._EXPIRY_CUTOFF`) is documented but explicitly NOT fixed in J.1 through J.10 — plan §14 forbids changing strategy deadlines without operator sign-off.

## 6. Broker execution and accounting

The D release-baseline correction restores legacy test fixtures to the startup-migrated ledger contract without changing runtime accounting. A regression verifies repeated migration preserves old rows and accepts new close provenance (`origin_ref`). Windows source guards now read UTF-8 with closed handles; scheduler wrappers document actual delegated calendar gates and deliberate off-session cleanup/reconciliation exceptions. The existing partner-bot default remains `True`; explicitly disabling it still prevents network-client construction, and credentials/qualification/final dispatch remain separate gates. Full Dev Python acceptance now passes 2,545 tests (three skips, 23 existing deprecations); this is not deployment or strategy qualification. See `2026-09-13-release-baseline-plan.md` for the precise release status and warnings.

Gateway files `services/kite.js`, `executor.js`, `risk-geometry.js`, `halt-switch.js` and `routes/orders.js` deserve focused review before any execution change. `token-store.js`, `token-restore.js`, `routes/token.js`, engine `token_lifecycle.py` and `kite_client.py` handle the authentication/provider bridge. Do not log secrets or infer an authenticated broker session from a process heartbeat.

Token restoration now releases each abort timer in `finally`, including fetch failures, and keeps response-body parsing under the same three-second abort scope. Retries and internal authentication remain unchanged. Filesystem-only dead-letter tests stub Telegram rather than start fake-token polling. The current native gateway suite passes 324 tests (four skips) and exits naturally without forceExit or detected open handles. The Windows instrument-test socket warning was traced to a manual asyncio.run between pytest-managed async tests; that test now uses pytest's lifecycle. Original failing four-file warning-fatal acceptance passes 32 tests; broader resource-warning-fatal research acceptance passes 181 tests. This does not prove all operational resources are leak-free in Production.

`performance.py` owns ledger functions used by the application. `performance_analytics.py` and `performance.py` must be read with the relevant position stores. `broker_reconciliation.py` checks imported statement cash arithmetic, `reconciliation_evidence.py` checks internal ledger/position links, and `broker_internal_reconciliation.py` performs the narrower one-way executed-order reference check described above. None alone proves full broker reconciliation. `order_execution_readiness.py` reports order-path evidence; submitting a real order merely to turn UNVERIFIED green is not a valid test plan.

Five reconciliation warnings were previously observed in the UI. Historical screenshots are not current facts. Investigate by account, module, execution mode, close identity and fee treatment; do not overwrite one store to match another. Broker confirmation, net cash and gross position P&L can have different timing and cost conventions.

### F3/F4/F5/F6 — independent correction plan hardening

The independent correction plan (`docs/2026-09-14-independent-correction-plan.md`) tightens the F-substrate at the writer/account/output contract level. These are **fail-closed** changes — every one of them converts a previous "best-effort" or "fabricated default" behaviour into an explicit refusal, so the system cannot silently grant authority it does not actually possess.

**F3 mark_to_market**: `fno_positions.qty` is now contract units (the writer persists `lots * lot_size`; MTM does NOT multiply `lot_size` again). Legacy fno_dr_book rows without an immutable tradingsymbol/token return `QuoteStatus.UNSUPPORTED` with a dedicated note — the aggregate never guesses a symbol. `OpenMarkToMarket.total_unrealised_pnl` is preserved for backwards compatibility (partial subtotal only); a NEW `complete_unrealised_pnl` returns `None` when any mark is non-FRESH. Consumers must opt into the new field. `run_penny_hourly_report` now uses `complete_unrealised_pnl` and renders 'UNAVAILABLE (incomplete/stale quotes)' instead of a misleading `Rs +0`. NEW `tests/test_mtm_reporting_independent.py` (3 tests) pins the contract: incomplete aggregate returns `complete_unrealised_pnl=None` even when the legacy partial subtotal is zero; fresh flat book returns `complete_unrealised_pnl=0`; the active and no-action hourly reports label UNAVAILABLE rather than `Rs +0`.

**F4 discrepancies**: `record_from_evidence_report` writes internal ledger facts under `INTERNAL_UNSCOPED_ACCOUNT_ID` (one fact, one attribution — the same internal fact cannot be attached to two different broker accounts). `_row_to_record` reads `account_attribution` from the DB: `INTERNAL_UNSCOPED` for the dedicated sentinel, `UNVERIFIED_LEGACY_ACCOUNT_ATTRIBUTION` for pre-existing rows in INTERNAL_EVIDENCE_CATEGORIES, `ACCOUNT_SCOPED` for genuine broker-attributed rows. Pre-existing accountless history is preserved rather than silently rewritten to a broker account. NEW `test_legacy_internal_account_attribution_is_unverified` and `test_same_internal_fact_is_not_attached_to_each_broker_account` pin the contract.

**F5 reconciliation_cli**: `_payload_to_import_kwargs` rejects null/blank `account_id` or `statement_id` (previously they would coerce to `'None'` or `'   '`). The `_import_statement` response no longer carries an `imported` boolean — that was a behavioural claim the operator could not verify against the on-disk artifact. NEW `test_main_retry_writes_identical_immutable_output` pins byte-identical retry: two runs of the same immutable payload produce a byte-identical output file.

**F6 capital_policy**: `CapitalPolicyThresholds.loss_tolerance_pct` is now `Optional[float]` — the previous 25.0 default was a fabricated engineering default for the explicit user input plan §10.5 mandates. The config default flips to `None`. `live_current_inr`, `drawdown_pct`, `consecutive_losses` are now `Optional`; missing facts render as `None` in the human-readable summary rather than zero. The CLI never returns `can_grow_live_capital=True`; an explicit `authorization_effect: NONE` field documents that a completed evaluation is a diagnostic, never an executable promotion grant. NEW `tests/test_capital_policy_independent.py` (5 tests): `requested_delta_inr` strictly-positive-nonboolean, refuses `loss_tolerance_pct` until explicit input, missing execution quality as `INSUFFICIENT_EVIDENCE`, the accountless-wrapper refuses without creating a database, and rejects boolean numeric thresholds.

**Affordability**: `tests/test_affordability_integration.py` converted to `@pytest.mark.asyncio` (no more `asyncio.run` inside pytest's managed loop) — a Windows pytest-asyncio warning surfaced during the D-baseline was traced to this exact pattern.

Net: python-engine +12 new tests (5 F6 + 7 F3/F4/F5), 0 regressions. The F-substrate is now writer-faithful, account-authoritative, and CLI-immutable across retries.

## 7. Partner manual-advisory flow

1. `partner_orchestrator.py` selects NIFTY/SENSEX specifications and loads profile/effective settings.
2. `fno_signal_scan.observe_underlying` fetches futures bars and evaluates public conditions without an option-chain dependency.
3. Each completed public management path runs before optional new-entry chain work; this prevents a slow first-index chain from blocking the other index's lifecycle updates.
4. `attach_entry_chain` and expiry resolution obtain candidate inputs only where needed.
5. `partner_manual_advisory.build_directional_debit_spread` constructs a defined-risk directional candidate; conditional protection follows a distinct explicit-assumption path.
6. Candidate validation checks contract/exchange/lot consistency, two-leg economics, freshness, liquidity and profile constraints.
7. Qualification remains separate from input readiness and profile validity.
8. Persisted delivery claims, final authorization and Telegram transport govern an eligible card. Research evidence alone cannot deliver.
9. Public invalidation/target updates and clock-only intraday reminders manage published ideas; they do not claim the partner took or closed a position.

`partner_manual_advisory.py` centralizes profiles, candidates, research artifacts, qualifications, feedback and public updates. Read its schema/declarations in the atlas. `partner_thesis.py` shares pure invalidation/target rules with research. `partner_bot.py`, `partner_content.py` and legacy parts of `partner_orchestrator.py` also exist: do not accidentally re-enable old naked-option/status messages while enabling the new pathway.

Current policy remains INTRADAY, with an entry cutoff, reminder and management deadline represented in candidate data. Historically configured times were 14:45, 15:10 and 15:15 IST. Verify current settings; exchange closing hours are a different concept from Sentinel's deliberately earlier deadline.

## 8. Portfolio hedge pathway is separate

`hedge_advisory.py`, `hedge_strategies.py`, `hedge_analytics.py`, `hedge_formatters.py` and `hedge_readiness.py` provide portfolio-aware phases and evidence. `partner_source_adapter.py`, `partner_input_refresh.py` and `partner_fixture_adapter.py` handle source/snapshot inputs. `routes_hedge.py` exposes authenticated operator/API surfaces.

Prior hardening established single-account binding, complete snapshot acceptance, atomic reconciliation, consistent reads/revisions, stable economic identities and conservative delivery recovery. A missing portfolio adapter does not mean general market-setup tips require partner holdings. Conversely, the manual-advisory profile cannot prove personalized hedge coverage.

Timeout/disconnect after possible dispatch is ambiguous. Automatic resend can duplicate consequential advice. Inspect durable claim/transport evidence and manual-resolution requirements instead of deleting ledger rows or forcing status to queued.

## 9. Research and the improvements made in this work

### Earlier baseline versus present Dev

At takeover of the research pipeline (`de696f9`), a claimed pipeline existed, but code review exposed incomplete causal inputs, weak archive/identity boundaries and missing end-to-end alignment with the deployed strategy. Earlier hedge/delivery corrections were already substantial work by previous implementations; do not attribute all existing features to this increment.

| Earlier gap | Improvement now present | Practical benefit | Remaining limit |
|---|---|---|---|
| Weak complete-policy reproduction | `partner_qualification.py` composes actual evaluator, candidate and profile checks with `FROZEN_COMPLETED_BAR_CUTOFF_V1` clocks | Research asks the same entry question at an explicit frozen cutoff and later genuine construction time | Production session evidence and reviewed qualification remain absent |
| Missing exact public input | `partner_research_capture.py` saves fetched OHLCV and actual receipt | Reproduce inputs without inventing past availability | Latest inspected Production archive had none |
| Missing candidate input archive | Passive full map/chain/profile capture now includes requested/received tokens and conditional-protection inputs | Retain why particular contracts were considered and expose missing response contracts | Production load and retention behavior still require live-session observation |
| Threshold-only or spread-P&L exits | Full-policy connector and shared public thesis | Replay tracks the published invalidation/target | Public collection gaps are not reconstructed |
| Between-book breach lost | Independent public event stream with sticky breach | No optimistic exit omission after recovery | Sparse input still cannot prove uninterrupted coverage |
| Original price reused at delayed entry | Actual-book capital/risk and round-trip cost reserve | Reject fills that violate profile after price changes | Cost model and contemporary quality calibration remain |
| Timestamp equality requirement | Explicit tick/cutoff/request/receipt/construction clocks plus latest proven prior books | Later acquisition remains causal without changing provider timestamps or bar eligibility | Old v1 captures retain weaker legacy timing evidence |
| Mutable or mismapped evidence | Raw/master fingerprints, token/terms validation, immutable reports | Detect altered inputs and accidental result replacement | Hashes are integrity, not independent source authenticity |
| Ad hoc scripts needed | `research_cli replay-full-policy` | Repeatable offline diagnostic | It does not register qualifications |

### Module chain

`research_archive.py` owns preservation, writer admission/lease and storage limits. `research_quote_collector.py` collects quote evidence; `research_leg_subscriptions.py` pins needed contracts. `partner_collection_attempts.py` journals each scheduled NIFTY/SENSEX attempt independently and derives `NEVER_ATTEMPTED`, `ATTEMPTED_UNAVAILABLE`, `PARTIAL`, `STALE` or `COMPLETE` session state. `partner_decision_clock.py` defines the pure causal clock contract. `research_study.py` provides modelled studies. `partner_research_capture.py` retains public, directional and conditional-protection inputs and loads public lifecycle evidence.

The deployed advisory timing policy is `FROZEN_COMPLETED_BAR_CUTOFF_V1`. Tick start freezes completed-bar eligibility. Public and option-chain requests and receipts keep their actual clocks and source IDs; candidate construction/validation uses the genuine post-acquisition time. Crossing the session date or the exact 14:45 IST entry deadline suppresses the idea instead of backdating it. A five-minute boundary crossed during acquisition does not silently admit a bar that was outside the frozen request. The next scheduled tick is a new run and cutoff. Public and candidate v2 captures share the same run/account/index identity, while old v1 captures remain immutable and load as legacy evidence.

Archive persistence is still lower priority than public management and candidate evaluation. A nonblocking writer lease prevents concurrent active writers, and advisory waiting is bounded by `RESEARCH_CAPTURE_WAIT_TIMEOUT_SEC` (default two seconds). Since a Python worker thread cannot be killed safely, timeout is recorded as outcome-unknown and its eventual completion is consumed/logged; it is never automatically retried as a certain failure.

`intraday_spread_archive_adapter.py` checks master/packet evidence and builds paired books, retaining partial batches. `intraday_spread_signal_artifact.py` is a distinct signal-artifact path; its simple evaluator must not be passed off as the complete policy. `intraday_spread_replay.py` prices a bounded one-lot spread. `intraday_spread_chronological.py` chooses causal entry/exit sequences, supports manual delay, public events and cost stresses.

The proactive-ledger stack (`proactive_intelligence.py` plus five sibling modules, total 3,007 LoC; tests under `tests/test_proactive_*.py` total 891 LoC) is the substrate for plan §11's six hypotheses; it is offline-safe by docstring and every report payload returns `can_place_orders=False, authorization_effect=NONE`. An independent audit and the promotion-bridge contract that any future live promotion must obey are at `docs/2026-09-13-workflow-g-state-of-codebase-audit.md` and `docs/2026-09-13-workflow-g-promotion-bridge.md`.

`partner_full_policy_replay.py` binds the actual selected candidate to archived books, profile limits and public lifecycle events. The archive adapter rejects distinct valid packets for the same leg and receipt instead of selecting by input order; exact byte-identical retries are deduplicated. Conflicts remain explicit report evidence and can invalidate the decision book. Each accepted replay retains a fingerprinted baseline plus declared fee/slippage stresses computed from identical chronological observations; a thesis already crossed at decision remains a reviewable no-fill instead of disappearing. `intraday_spread_holdout.heldout_case_from_full_policy_report` verifies and retains the complete deployed-policy report, manifest, stress artifact and source identities before admission. Aggregation orders realised economics by timezone-aware close clocks and calculates sequential drawdown. `partner_qualification_review.py` requires an immutable criteria manifest frozen before holdout, evaluates its exact stress point and baseline/stressed drawdown limits, and rejects missing, duplicate, malformed or state-changing evidence. Legacy reports remain readable but blocked. This integration is not proof of a passing strategy, calibrated real costs or adequate real evidence.

### Important replay semantics

The tested source/execution-boundary slice adds v3 public captures with the exact futures symbol/token, exchange, expiry, lot/tick, dated raw-master digest, full eligible expiry list and next roll contract. Full-policy replay independently proves these identities and the front-contract selection against the retained master. Legacy v1/v2 captures remain readable but unscoped. Caller-supplied public dictionaries remain diagnostic and cannot establish verified held-out evidence. Finalized quote segments must match their retained segment manifest, not merely individual packet self-hashes.

Actual delayed-entry books reapply deployed spread, OI, volume and full-lot depth gates, public-observation age, current quantity, profile capital/risk and positive cost-inclusive expiry reward. Entry and management cutoffs use exact dated IST instants; same-day option expiry is excluded. Invalidation at the delayed fill cancels entry in either public-event representation. Delayed public-thesis exits require a genuine timely later book; recovery does not cancel the latched breach. Missing, partial or late books remain unresolved. Slippage is charged on gross executed leg notional and cannot become negative on a distressed net-debit close. Expiry reward/risk is a structural research bound, not a promised intraday target; asymmetric actual fills and exchange-specific settlement models remain outside this full-lot replay.

- A decision event can refer to a previously received complete book. Its constituent quote timestamps remain unchanged. Stale books or intervening partial observations are rejected.
- A public breach before delayed entry cancels it; after entry it remains pending through later price recovery.
- Exit delay starts at public event receipt, not the next option book. Missing executable exits remain UNRESOLVED.
- Capital and risk checks use execution debit plus declared costs, not original card prices.
- Reports retain insufficient evidence, no setup/no fill and unresolved outcomes. Excluding these creates selection bias.
- `can_qualify`, `can_deliver`, `can_place_orders` remain false in this connector.
- A CLI exit code 0 means diagnostic execution succeeded, including an insufficient-evidence result.

The exact command and policy format are in [replay progress](2026-09-12-full-policy-replay-progress.md). Every experiment needs its own immutable destination. Never reuse a report filename to hide changed assumptions.

## 10. Proactive research and optional AI

Independent F source review corrected materially inferred accounting schemas and unsupported historic closure claims in `2026-09-13-workflow-f-state-of-codebase-audit.md`: positions has no declared PK/id; outcomes has autoincrement id plus UNIQUE(ticker,closed_at); broker entries has the three-column account/statement/entry PK. Ledger has multiple writers and position/outbox lifecycle updates exist. A1–A5 warning identities/closures remain UNKNOWN without original records. Equity snapshot effective date is again null because verification date does not establish tariff effectiveness; numeric costs/version/as-of/options and old snapshots remain unchanged. Fresh isolated schema and funding-not-profit fixtures support these contracts, not actual Production reconciliation or loss reconstruction.

`proactive_intelligence.py` maintains activity stages, watchlists, synthetic capital/positions and outcome evidence by account/mode/run. Watchlist lifecycle includes watching, armed, triggered, selected/deferred/rejected, expiry and invalidation. Persisted assumptions prevent the same research run being reused with different economics.

Independent F/G review identified mislabeled trailing-exit dispatch and incomplete promotion approval validation despite passing focused tests. The first correction makes `promotion_bridge.py` transitions atomic and directed, reads the latest committed append state, and prevents a terminal refusal/approval from being amended. Signature timestamps cannot reorder that state. This preserves both tables and all rows. Its records remain non-authoritative (`can_place_orders=False`); approval budget/evidence/expiry validation and faithful entry/exit composition are still required, so neither a stored approval nor a green focused suite establishes live permission. See `2026-09-13-fg-independent-correction-plan.md`.

The trailing-composition follow-up now honors NEXT at-open, bounded pullback limit and completed-bar-confirmation entry behavior before applying the selected trailing exit. Intrabar limit fills don't ratchet from a possibly pre-fill entry-bar high; confirmation bars cannot fill or ratchet the position. Gap-invalid entries remain no-fill and nonfinite cost assumptions fail closed. Root's ten-file proactive/G suite passes 121 tests with warnings fatal; Terra independently reviewed causality and found no blocker. Existing primary comparison runs retain their implementation fingerprint and reject incompatible reuse. G.7 subsequently makes RANGE_REVERSION a causal dedicated hypothesis and removes the stale alias gate; old reports remain retained and cannot be reinterpreted because implementation hashes differ.

The exit-cache follow-up closes that proposal-clock/implementation identity gap: new `matched-exit-evidence-v3` manifests bind effective full proposal identities/timings, snapshotted bars, costs and both evaluator source hashes. A companion `proactive_exit_research_manifests` table retains canonical JSON without changing the original four-column results table. Legacy reports remain readable but cannot be reused as current-version runs; incompatible reuse fails rather than overwriting history. Atomic final recheck handles concurrent identical/conflicting requests, and duplicate opportunity IDs cannot inflate the sample. Root's current proactive/G suite passes 137 tests with warnings fatal. These are input/implementation integrity checks, not genuine held-out provenance, qualification or live authorization; approval validation/range semantics/F evidence remain open.

Approval-budget validation now requires the relevant retained amount, drawdown cap and integer expiry, rejecting booleans/nonfinite values before SQLite coercion. Approval transitions use budgets predeclared on the original unsigned record and a half-open validity window anchored to its original clock; signing later cannot extend expiry. Reads preserve recorded history and expose budget validity/expiry/version status, while `approval_usable=False` explicitly blocks missing frozen held-out/account/F/D evidence. This is budget validation, not full evidence approval or order authority. The twelve-file F/G suite passes 180 tests with warnings fatal; the previous whole-engine receipt predates this and the cache change.

`proactive_market_data.py`/`market_data_sources.py` address provider observations; `proactive_execution_research.py`, `proactive_exit_research.py` and `proactive_portfolio_research.py` compare choices. `proactive_diagnostics.py` and `operational_coverage.py` explain activity gaps. Demo modules exercise synthetic workflows. These components are useful foundations, not automatically broker-consuming strategy deployments.

Optional AI is represented by `optional_ai_status.py`, agent typed `advisory.py`, and `async_reviews.py`. A disabled or unavailable model should leave deterministic signal/risk/delivery functioning. Review timeout, budget, queue saturation, stale results and process restart before extending model use. The user's preference is assistance without absolute dependency.

I.4.D source-event classification (the only plan-§13 explicit gap that previously had no implementation) lands a bounded 8-category classifier against the J.2 sourced news. `agent/news_classifier.py` is pure / total: a fixed `NewsCategory` enum (`REGULATORY`, `EARNINGS`, `M_AND_A`, `GUIDANCE`, `MACRO`, `RUMOR`, `TECHNICAL`, `UNKNOWN`); a frozen `ClassificationResult` dataclass with `title_hash`, `category`, `confidence ∈ [0,1]`, bounded rationale (≤ 280 chars), `prompt_version`, `classified_at`; `CONFIDENCE_THRESHOLD = 0.6` forces low-confidence results to UNKNOWN (fail-closed); `CLASSIFIER_TIMEOUT_SEC = 1.0` per-item latency budget; never raises (timeout / parse error / disabled / model exception → UNKNOWN + confidence=0.0). The taxonomy is operator-defined — a category the model invents (outside the enum) is forced to UNKNOWN. The classifier never grants authority, never persists state, never executes. `DISABLE_CLASSIFIER` forces every result to UNKNOWN (offline / CI / sandbox). `analyze_with_minimax` accepts an optional `pre_classifications: Optional[List[ClassificationResult]] = None` parameter; when supplied, the prompt renders a "CLASSIFIED SENTIMENT DATA" section (above the existing "MULTI-SOURCE SENTIMENT DATA" section) listing `title_hash + category + confidence + rationale` per headline; when None (the default, every existing caller's path), the prompt renders a placeholder text and is byte-identical to its pre-I.4.D shape. Two env-flagged helpers (`_fetch_news_items_for_ticker`, `_maybe_classify_news`) wire the classifier into the verdict call sites when `ENABLE_NEWS_CLASSIFIER=1`; the helpers never raise. The operator CLI `python -m agent.tools.news_classify_cli --ticker TICKER | --input PATH [--dry-run] [--json]` runs without touching the verdict pipeline (lazy-imports `agent.fetch_news_items` only for `--ticker`); exits 0/1/2/3 with structured diagnostics. Agent suite grew 213 → 253 across the I.4.D commits (zero regressions); 36 module tests + 10 helper tests + 9 verdict-prompt integration tests + 21 CLI tests pin the contract.

I.4.E bounded contract-health self-evaluation (per the I.4 deep-research doc's "guard the guards" pattern) lands a pure self-evaluation module that asserts the bounded contract on the agent's own surfaces. `agent/contract_health.py` exposes five independent checks plus an aggregate `evaluate_contract(...)` that returns a `ContractReport` (`passed`, `checks[]`, `evaluated_at`, `schema_version="i4e-v1"`). The five invariants: (1) `status_envelope_authority` — the bounded health envelope carries no execution authority (rejects `can_place_orders != False`, `authorization_effect != "NONE"`, unknown top-level keys); (2) `no_prompt_leakage` — the bounded snapshot carries no prompt or reviewer content (rejects `prompt`, `rationale`, `pitch`, `risks`, `raw_response`, etc., at the top level and inside any `usefulness` sub-envelope); (3) `usefulness_counters_only` — every `usefulness` key is in the allow-list AND every value is a bounded primitive (`int`/`float`/`str`/`None`), with `verdict_counts` typed as `dict[str, int]` (bool values are rejected explicitly); (4) `classifier_fail_closed` — every `ClassificationResult` below `CONFIDENCE_THRESHOLD=0.6` must map to `UNKNOWN`, every category outside the bounded enum is a violation, every rationale > 280 chars is a violation; (5) `review_non_authoritative` — a `Review` must not carry any of `FORBIDDEN_REVIEW_DELTA_FIELDS` (`can_place_orders`, `authorization_effect`, `live_delta_inr`, `capital_delta`, `qualification`, `approved_live_budget`) — per plan §13 "the typed result must not change capital limits, qualification or order/delivery authority". All inputs are optional (`None` means "not inspected in this run", never a violation), letting the operator run the harness with only one surface available. The pure module imports `agent.news_classifier` lazily inside `check_classifier_fail_closed` so it stays importable in isolation (the `agent.py` import path triggers a Telegram env-var check at module load). The operator CLI `python -m tools.contract_health_check {print-config | check <path> | self-check}` is read-only; exit 0 iff every check passed, exit 1 on any violation, exit 2 on I/O/parse/shape error. Agent suite grew 259 → 312 (+53 net) across this slice. See [I.4.E done-doc](2026-09-14-i4e-contract-health-done.md).



The Dev optional-annotation queue now deep-snapshots nested signal inputs and bounds READY/CACHED validity by the original task deadline and cache TTL. A shorter cached-request deadline tightens validity; a later one cannot extend it. Completion exactly at expiry is discarded, and status returns EXPIRED without a review once validity elapses. This fixes a reproduced stale-cache defect without changing reviewer signatures, budgets or deterministic authority. The full isolated agent suite passes 98 tests with warnings fatal and networking disabled. Model/prompt/source provenance, sourced-news timestamps and annotation usefulness still require I acceptance; this lifecycle slice is not that proof.

## 11. Dashboard and API navigation

The gateway mounts routing/authentication in `server/app.js`. Engine routes are split among `routes_ops.py`, `routes_hedge.py`, `routes_portfolio.py`, `routes_promotion_readiness.py`, experiment routes and `main.py`. Use the atlas to find exact local handlers; a route's local path is not necessarily its externally mounted URL.

`pages/Dashboard.jsx` composes operational and performance views. `pages/ResearchCenter.jsx` and `BacktestLab.jsx` show research; `Positions.jsx` shows positions. Hooks include partner setup/cards/backlog and advisory collection readiness, reconciliation, scheduler timing, operational coverage, optional AI, proactive activity and session diagnostics. The advisory evidence card shows per-index expected/attempted/missing/incomplete counts and never turns an unavailable response into zero. Utility modules normalize display contracts.

Blank/zero cards can mean no configured account, no source observation, no evidence for the selected mode/run/window, feature disabled, API failure, or genuinely zero events. They are not interchangeable. Each UI surface should show source, scope, observed timestamp and missing-input reason. Reconciliation warnings must remain visible until explained.

## 12. Scheduler, lifecycle and operations

`scheduler_setup.py` registers trading scans, forced exits, partner entry/lifecycle jobs, research collection, input refresh and hedge recovery. `scheduler_telemetry.py` measures job runs. `ops_metrics.py`, `ops_watchdogs.py`, `memory_metrics.py`, `operator_status.py`, `operator_alert.py` and acceptance watchdogs support operations.

Startup catch-up registration resolves a running event loop before constructing `_run_penny_edge_scan_safe`. Synchronous registration/tests therefore defer the catch-up without leaking an unawaited coroutine; the ordinary async application startup path still schedules it.

Measure duration tails, queue delay, provider latency and lock contention separately. An 8-second average does not exceed a 60-second interval; a 115-second tail can overlap it. Prioritize exits and active-advice updates before optional research. Avoid solving lag merely by unbounded parallelism or deleting observations.

`release_identity.py`, gateway `release-identity.js`, Docker build stamps and `scripts/verify_deployment.py` tie a deployment to an actual source/image identity. A newly merged branch does not imply a rebuilt container. The verifier is a deployment identity check, not a profit verifier.

## 13. Last observed Production evidence, not a current health promise

On September 12 read-only inspection found application containers stopped; nginx was restarting. No application service was started. A disposable network-disabled helper mounted the existing data volume read-only. It found four master manifests, September 10/11 quote journals and zero public-input captures under `/data/research`.

Earlier September 11 assessment inspected 61,335 packets and found insufficient strategy evidence for both indices. Packet count is not trade sample size. That report also identified selected-leg retention gaps. Read [the original assessment](research-assessment-2026-09-11/qualification-readiness-report.md) and [the later inventory](2026-09-12-production-evidence-and-cas-findings.md). Reinspect state before acting; these observations expire.

## 14. Release and test discipline

Use the repository Python environment for tests. Avoid importing engine application modules just to generate docs: imports may initialize runtime resources. The atlas generator uses AST/text only.

For changed research/orchestration code, focused tests plus the combined research/orchestrator suite are required. Full release acceptance additionally includes gateway tests under a compatible Node/native SQLite runtime, dashboard tests/build, agent checks as applicable, scheduler/API contracts, migration review and deployment verification.

The historical Node 24 ABI/better-sqlite3 issue is an environment limitation, not permission to claim gateway green. Use the repository-compatible container/runtime rather than changing production dependencies to suit a test host. No broker order or partner message is required to run offline tests.

See HANDOVER_CHECKLIST.md for wrap-up validation and limits. The final handover commit closes this documentation task; it does not declare strategies qualified or promise tomorrow's tips.

## 15. Source navigation and maintenance

The atlas indexes all top-level engine/agent Python modules, declared symbols/line numbers, engine dependencies, related tests and declared tables, plus gateway/dashboard source dependencies and local routes. It is generated navigation, not a substitute for semantic review.

After every implementation commit, update affected sections here, regenerate the atlas, reconcile the active plan, and record checks/deployment state. Prefer doing those updates in the implementation commit; verify immediately afterwards. The mandatory ritual is specified in AGENTS.md and NEXT_AGENT_PLAN.md.

## 16. September 20 AI activation and truthful hedge staging

The Compose contract now explicitly enables the bounded optional-AI queue,
source-event classification and usefulness telemetry. Its safe policies remain
`proceed`/`advisory`: AI supplies non-authoritative context and cannot place an
order, change capital or silently become a hard veto. The manual partner
advisory switches are also explicit. `PARTNER_HEDGE_ENABLED=true` permits the
advanced Phase-2/3 shadow jobs to observe real inputs, while both advanced
delivery switches remain explicitly false and both shadow switches remain
true.

Phase-2/3 staging days are no longer expected to arise from elapsed uptime or
manual bookkeeping alone. `record_shadow_staging_day` writes one idempotent
system receipt per phase and IST date only after the shadow cycle processes at
least one reconciled underlying through a fresh option-chain context. Missing
login, missing positions, a closed market, stale/unavailable chains, stopped
services and scheduler invocation alone do not count. This system receipt does
not satisfy manual live-chain verification or per-kind Telegram sample review,
does not enable delivery and does not create qualification.

The read-only Production inspection behind this change found three manual
advisory ideas on 2026-09-17, no advanced hedge shadow evaluations, no hedge
gate evidence and no reconciled partner positions. Core application containers
were stopped with exit 137 and `OOMKilled=false`. Production flags were unset
despite a present MiniMax credential. These facts explain 0/7; they do not show
that the strategy gates rejected seven genuine staging sessions.

The partner-readiness CLI now reads the actual persisted profile, input-status,
idea, strategy-qualification and hardened `partner_hedge_messages` schemas.
The predecessor version used obsolete column/table names and treated advanced
Phase-3 readiness as the final gate for ordinary manual advice. The corrected
seventh check reports the manual-advisory enable/delivery configuration;
advanced 0/7 progress remains nested informational evidence with
`blocks_manual_advisory=false`. Database connections are read-only, and a
quiescent read-only Docker mount may use immutable SQLite mode only when no
non-empty WAL exists.

### Exact release-range notes (2026-09-20)

`scripts/build_release_notes.py --base-ref REF` now resolves `REF` and `HEAD`
to immutable commit SHAs and inventories the complete two-dot range. It no
longer labels a latest-30 snapshot as though it were the requested release
range. The generated header records the requested range, resolved base SHA,
resolved SHA range and ahead count. An invalid base or an uninspectable range
fails with exit code 2 before stdout or `--out` is written. Omitting
`--base-ref` intentionally retains the bounded latest-30 diagnostic view.

The tool never fetches, merges, deploys or edits Git state. Reviewers must
fetch explicitly before generation when they need a fresh remote-tracking
base, then verify the resolved base SHA against the intended PR target.

The broker-statement operator report uses the ASCII currency code `INR`
instead of the rupee glyph. Numeric reconciliation semantics are unchanged;
the representation prevents Windows cp1252 consoles from crashing before a
`MATCH` or `UNRESOLVED` result can be displayed.

### Reproducible session-phase goldens (2026-09-20)

The J.6 regenerator treats `generated_at_utc` as the time the semantic fixture
content last changed. If schema/classifier/vector content is identical, it
preserves that timestamp, emits canonical UTF-8 with a trailing newline and
skips writes whose bytes already match. If any semantic content changes, a new
timestamp is assigned and the exact same payload is dual-written to the Python
and Node consumers. No-op verification therefore leaves a clean checkout while
real phase changes remain visible and attributable.
