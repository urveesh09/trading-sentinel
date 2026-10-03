# B1/B2 — bar data contracts and exact classic Penny MIS lifecycle replay (October 3, 2026)

## Status at slice start (inheritance, revalidated)

- Dev `codex/production-correction-hedge-p0` at `a5d81b2`, clean, 8 commits
  ahead of its cached upstream. Production checkout/engine release `044c016`.
- F0-A–E shared F&O paper risk is implemented in Dev. The owner has directed
  this task to treat the F&O half of the October 3 plan as done and move to
  B1/B2. For the record, the [independent F0 review](2026-10-03-fno-f0-independent-review.md)
  still lists R1–R5 as open source-acceptance items. This slice does not
  touch F&O code, and starting B1/B2 does not close those items.
- Production is assessed read-only. No Production file, configuration,
  schema, service, broker or message action is part of this slice.

## Problem

1. **No explicit data contract.** The existing Penny minute loader rejects a
   whole run when any requested ticker-day also has 15-minute rows, and
   when any minute row has zero volume. A read-only inventory of
   Production `/data/cache.db` (October 3) shows why that matters:
   - 781,275 `minute`, 370,039 `15minute` and 76,306 `legacy_unknown` rows;
     81 ticker-days carry both `minute` and `15minute` rows;
   - 192,400 minute rows (25%) have zero volume; 1,737 of them still show
     `high > low` (contradictory evidence);
   - only 318 of 2,755 minute ticker-days have all 375 bars; 1,796 have
     internal gaps;
   - minute data reaches 15:00 only through 2026-09-03; from then on the
     scanner stops fetching at about 14:29, so later sessions lack exit
     evidence;
   - timestamps are naive IST wall-clock bar starts (`YYYY-MM-DD HH:MM:SS`),
     with no off-grid seconds, no rows outside 09:15–15:29 and no weekend or
     holiday rows.
2. **The existing replay is not the shipped lifecycle.** Compared with the
   live classic Penny MIS code it:
   - exits at a +2R target, which the live book never does (the target is
     used only by the 14:30 smart-EOD rule);
   - evaluates bar *m* at clock *m*, whereas live sees a completed bar only
     in minute *m+1*, so the 10:30–14:30 window and pace-adjusted volume are
     shifted by one bar;
   - fills at the signal close instead of the executor's LTP after its 2%
     drift and stop-breach checks;
   - skips the circuit-band filter, the 14:30 smart-EOD / 30-minute time
     stop, the 60-second paper LTP stop monitor, `PennyRiskEngine` sizing and
     the one-per-ticker / three-MIS capacity reservations;
   - allows only one entry per ticker-day, whereas live allows re-entry after
     an exit.

## B1 contract — `python-engine/research_data_contracts.py` (new, pure, offline)

- **Intervals.** Registered `minute`, `3minute`, `5minute`, `15minute`.
  `legacy_unknown` and any unregistered label are never treated as another
  interval. A run selects exactly one label; other labels on the same
  ticker-day are counted and reported, not merged and not run-fatal.
- **Clock.** Values are IST wall-clock bar starts. A naive value is read as
  IST; an aware value is converted to IST; anything else is invalid. A bar is
  available at `start + interval`.
- **Row validation.** Each row is checked for:
  - a parseable timestamp, aligned to the interval grid from 09:15, with zero
    seconds;
  - a start inside 09:15 to the last session bar;
  - a weekday that is not a holiday;
  - finite, positive OHLC with `low <= min(open, close)` and
    `high >= max(open, close)`;
  - finite, non-negative volume;
  - no duplicate normalised timestamp with different values (identical
    duplicates are deduplicated and counted).

  An invalid row makes its whole ticker-day `INVALID`. The bad row is never
  silently dropped while the rest of the day is kept.
- **Bar kinds.**
  - `TRADED` (volume > 0) is the only executable evidence.
  - `NO_TRADE_MARK` (volume 0, `high == low`) and `ZERO_VOLUME_WITH_RANGE`
    (volume 0, `high > low`, an anomaly) can inform a mark or clock but never
    prove a fill.
- **Coverage per requested trading day.**
  - `COMPLETE`: every expected bar is present and there is no anomaly.
  - `PARTIAL`: rows exist, with reason codes `missing_bars`, `late_start`,
    `early_end` or `zero_volume_with_range`, plus counts and first/last bar.
  - `INVALID`: the day has at least one invalid row.
  - `UNAVAILABLE`: no rows of the selected label exist; other labels present
    are listed.

  Nothing is forward-filled.
- **Calendar.** The trading calendar comes from the audited
  `market_calendar.NSE_HOLIDAYS_STATIC` set and is valid only through its
  declared date. A requested intraday date outside that validity is
  `UNAVAILABLE` (`calendar_unavailable`), never assumed. Special sessions,
  such as Muhurat on a weekend, are unsupported and therefore unavailable.
- **Daily contract.**
  - Rows must have an ISO date, valid OHLC and volume ≥ 0. Zero-volume days
    are counted.
  - Point-in-time rule: a daily bar dated D is usable only for decisions on
    days after D.
  - Adjustment basis is declared `UNKNOWN_AS_CACHED`.
  - A move of more than 40% between consecutive closes, or between the prior
    close and the next open, is reported as `suspected_corporate_action`.
    Nothing is adjusted or repaired.
- **Manifest.** Each dataset carries a manifest containing:
  - contract version, interval, clock, source, request, calendar source and
    validity;
  - row counts by label and disposition;
  - per-day coverage and status counts;
  - a deterministic, order-independent SHA-256 over the canonical accepted
    rows.
- **I/O.** Loaders open SQLite only through an encoded `mode=ro` URI, use
  `contextlib.closing`, and never create a missing database. Pure validators
  accept collected rows, so the stdin collector path shares the same
  contract.
- **Strategy-specific requirement.** A `CoverageRequirement` declares which
  statuses a strategy can use. Generic code never assumes a session is
  complete.

## B2 contract — `python-engine/penny_lifecycle_replay.py` (new, offline)

Scope label: **`LIFECYCLE`** (not `FULL_PORTFOLIO`). The replay reuses the
shipped functions as-is: `evaluate_breakout_entry`, `_rsi_14_wilder`,
`PennyRiskEngine` sizing and `band_pct_from_quote`/`circuit_blocked`/`is_disabled`,
`smart_eod_check`, `time_stop_triggered`, `mis_time_stop_active` and
`calc_penny_costs`. No evaluator threshold changes.

Clock and order of events per minute boundary *k* (IST), mirroring the live
scheduler:

1. **Protective stop, by book.**
   - `PENNY_PAPER`, the book Production runs (`PENNY_LIVE_TRADING=False`):
     the 60-second paper monitor reads the LTP at *k*. If it is at or below
     the stop, the position exits at that reference price, as paper settles
     at the reference price.
   - `PENNY` (live): a broker stop triggers on a `TRADED` bar whose low
     reaches the stop. It fills at the stop, or at the bar's open on a gap.
     This is labelled an approximation, because the live stop-limit
     unfilled-gap path is not modelled.
2. **14:30 smart-EOD job.** This is the exact `run_penny_eod_check` branch
   order:
   - if `ltp < entry` and `time_stop_triggered`, exit with
     `time_stop_30min_in_loss`;
   - otherwise use `smart_eod_check`.
3. **15:00 force close** via `mis_time_stop_active`.
4. **Scan.** For every ticker, evaluate the last completed bar (*k−1*) at
   `as_of = k`. Inputs are built as `_evaluate_ticker_breakout` builds them:
   - prior-bars anchor, completed-bar RSI(14) and cumulative volume of the
     completed bars;
   - the 20-day median volume from daily rows dated in `[k−30 calendar
     days, D)`, with tail 20 and at least 5 rows;
   - the circuit-band check against the prior daily close and the current
     day high/low.

   Admission then follows the live order:
   - the regime (PR3 blocks every entry);
   - disabled tickers;
   - one active position per ticker, with at most 3 MIS positions;
   - executor checks against the LTP at *k*: drift above 2% is rejected, and
     a stop at or above the LTP is rejected.

   The fill is the LTP at *k*.

Execution evidence rules:
- The LTP at *k* is the open of bar *k* when that bar is `TRADED`, otherwise
  the last traded close before *k*, which is a mark only.
- An entry or exit fill requires a `TRADED` bar. An exit decided on a stale
  mark fills at the open of the first traded bar at or after *k*. If no such
  bar exists, the trade is `UNRESOLVED` and unscored.
- Entries without a traded bar *k* are counted as
  `NO_EXECUTABLE_EVIDENCE`. This deliberately diverges from paper's
  stale-LTP fill.

Re-entry after an exit is allowed, as live allows it. Sizing uses the book's
configured bankroll, which is fixed, as it is live. The shipped in-memory
daily kill switch is never fed by runtime settlements. It is therefore
replicated as inert, and a diagnostic reports days on which the declared 20%
threshold would have been breached.

**Not replayed, declared in every report:**
- point-in-time universe ranking (the explicit tickers and alphabetical
  order are declared);
- historical regime (one declared constant regime per run);
- the sector filter and the operator event calendar;
- broker MIS blocks and order rejections;
- partial fills;
- CNC positions occupying total capacity;
- scheduler jitter.

**Outputs:**
- Per trade: decision bar, `as_of`, fill and exit timestamps and prices,
  shares, the stop and target from the decision, exit reason, gross, costs,
  net, R, MFE/MAE in R, and holding minutes.
- Summary:
  - status `COMPLETE`/`PARTIAL`/`UNAVAILABLE`;
  - closed and unresolved counts, gross/costs/net, win rate, profit factor,
    expectancy, average R;
  - realised-cash drawdown, net excluding the best winner;
  - a per-day table and exit-reason counts;
  - a funnel with bounded reject codes and admission outcomes;
  - coverage exclusions;
  - an adverse-fill bound derived from the executor's own limit prices
    (entry limit at LTP × 1.005, stop/unwind limit at 1% below).

Metrics are `None` when there are no closed trades. A run with no trades is
reported as such, never as zero-risk success.

## Integration

- **Backtest Lab.** Register `penny_breakout_mis_lifecycle_1m`
  (`LIFECYCLE`) and add an additive `scope` metadata field, `EVALUATOR` for
  the existing minute replay. Existing adapters are unchanged.
- **Research CLI.** `scripts/run_penny_research.py` gains
  `--strategy lifecycle` (default `baseline` preserves the old behaviour),
  `--session-policy` and a coverage-only selection rule. The collector stays
  stdlib, read-only and bounded.

## Acceptance checks

- B1: interval selection with mixed labels; `legacy_unknown` unavailable;
  off-grid, outside-session, holiday, OHLC, negative-volume and
  conflicting-duplicate rows invalidate their day; identical duplicates are
  deduplicated; zero-volume kinds are classified; each coverage status is
  covered; missing requested days are `UNAVAILABLE`; outside-calendar dates
  are unavailable; the manifest hash is deterministic and independent of row
  order; daily point-in-time slicing and corporate-action suspicion work; a
  missing database is never created and its handle closes.
- B2:
  - **Live-scanner parity.** `PennyScanner._evaluate_ticker_breakout`, fed the
    same bars through a fake broker, returns the same decision as the replay
    for the same bar.
  - **Clocks.** Bar 10:29 is evaluated at 10:30 (in window); bar 14:29 is
    evaluated at 14:30 (out of window).
  - **No look-ahead.** Mutating bars after a decision leaves it unchanged.
  - **Fills.** The next-bar fill, the drift reject, the stop-breached reject
    and the zero-volume next bar each behave as specified.
  - **Stops.** A paper stop on the LTP poll differs from an intrabar wick on
    the live stop.
  - **Smart-EOD.** The within-0.5R exit, the 30-minute loss time stop, the
    fresh-loss hold and the 15:00 close each behave as specified.
  - **Capacity.** One position per ticker and at most 3 MIS positions;
    re-entry after an exit is allowed.
  - **Truncated day.** The trade is `UNRESOLVED` and the run status is
    `PARTIAL`.
  - **Determinism.** The run is deterministic and its fingerprint is stable.
- Existing Penny replay, Lab and CLI tests keep passing.

## Predeclared research run (fixed before any outcome is computed)

- Window: **2026-07-30 to 2026-09-03**. These are the only dates on which
  minute data reaches 15:00.
- Primary run:
  - book `PENNY_PAPER`, regime `PR1_CALM` (declared);
  - session policy `complete_only`;
  - universe: every ticker with at least one complete 375-bar minute day in
    the window and at least 20 daily rows before the window start, chosen
    from counts and timestamps only, alphabetically, capped at 40 tickers.
- Sensitivity run: the same universe with `allow_gaps`, labelled
  `MISSING_MINUTES_TREATED_AS_NO_TRADE_UNVERIFIED`.
- Both are retrospective, exploratory and coverage-selected (complete-session
  days favour liquid names). They are not a holdout, not a capital return and
  not a basis for tuning.

## Rollout and rollback

- **Rollout.** Dev only. The change adds new offline modules, an additive Lab
  registry entry and metadata field, and a backward-compatible CLI option. It
  has no runtime trading path, schema, settings, broker, order or message
  effect. Commit locally; promotion is through GitHub as usual.
- **Rollback.** Revert the two new modules, the registry entry and the CLI
  option. Archived reports are preserved.

## Implementation result (Dev only; not pushed, not deployed)

The slice above is implemented as specified, with one correction found
against real data before the research run.

- **Correction: off-calendar daily rows.** Production daily history has
  3,690 rows dated Sunday 2026-02-01, a broad session that the audited
  static calendar does not list (most likely an exchange special session;
  not independently verified here). Making such a row fatal would have
  invalidated every ticker's entire daily history.

  Off-calendar daily rows are therefore kept and reported:
  - in `DailyDataset.off_calendar`;
  - as per-date counts in the manifest (`off_calendar_dates`).

  The Penny replay excludes only ticker-days whose 30-day warm-up contains
  one (`off_calendar_daily_row_in_warmup`). Intraday rows on a non-session
  date still invalidate their ticker-day. No special session was added to
  the calendar.
- **`python-engine/research_data_contracts.py` (B1).** Intervals, the IST
  bar-start clock, row validation, bar kinds, coverage statuses, the
  calendar, the daily point-in-time rule, corporate-action suspicion,
  manifests with an order-independent SHA-256, and read-only loaders that
  never create a database.
- **`python-engine/penny_lifecycle_replay.py` (B2).** The exact classic
  Penny MIS lifecycle described above. A completed bar is evaluated once;
  gaps are never forward-filled.
- **`backtest_lab.py`.** A `PennyMisLifecycleAdapter`
  (`penny_breakout_mis_lifecycle_1m`, scope `LIFECYCLE`) is registered, and
  the additive `StrategyMetadata.scope` field is added. The minute evaluator
  replay is labelled `EVALUATOR`; other adapters are `UNSPECIFIED`.
- **`scripts/run_penny_research.py`.** Adds `--strategy lifecycle`,
  `--book`, `--regime` and `--session-policy`, plus a coverage-only
  selection rule with up to 40 tickers and 500k rows. The baseline path is
  unchanged.

### Shipped-behaviour findings recorded, not changed

- **Kill switch is inert.** `PennyRiskEngine.record_close` and
  `record_realized_pnl` have no runtime caller, so the classic Penny
  in-memory daily kill switch can never fire. The replay replicates it as
  inert and reports days on which the declared 20% threshold would have been
  breached. Wiring it is a separate, owner-reviewed runtime change.
- **Bankroll is fixed.** The classic Penny bankroll is a constant setting
  (`PENNY_PAPER_BANKROLL` / `PENNY_LIVE_BANKROLL`), not ledger-compounded,
  and `PENNY_PER_STOCK_CAP=500` keeps positions to about ₹500 of notional.
- **Minute evidence stops at about 14:29 after 2026-09-03.** The scanner
  stops fetching minute bars when the entry window closes. Later sessions
  therefore have no 14:30 or 15:00 exit evidence and cannot be replayed to
  completion. Capturing bars through 15:00 for tickers with open positions
  would be a separate runtime change to propose and review.

### Verification (Dev runtime `python-engine/winvenv/Scripts/python.exe`, Windows)

| Command | Result |
| --- | --- |
| `-m pytest tests/test_research_data_contracts.py -q -W error` | **29 passed** |
| `-m pytest tests/test_penny_lifecycle_replay.py -q -W error` | **22 passed** |
| `-m pytest scripts/tests/test_run_penny_research.py -q -W error` (from Dev root) | **6 passed** (4 existing, 2 new) |
| Combined B1 + B2 + CLI selection, warnings-fatal | **57 passed** |
| Penny / Backtest Lab / research / market-calendar / walk-forward / backtest-route selection | **809 passed, 1 skipped** |

The broad selection's warnings are the two pre-existing library
deprecations: the Starlette async-generator lifespan warning (repeated) and
the HTTPX `app` shortcut warning, one occurrence. No assertion failed.

- **Parity.** `test_replay_inputs_match_the_live_scanner_at_every_minute`
  drives the real `PennyScanner._evaluate_ticker_breakout` through a fake
  broker that serves the same bars. Over 324 minute boundaries, every
  accept/reject and every reject string matches, and accepted entry, stop,
  target, shares, RSI, anchor and buffer are identical.
- **Mutation check.** Temporarily shifting the replay clock back one minute
  (the old replay's convention) made that parity test and the time-window
  test fail. The module was restored afterwards.
- **Isolation.** `tests/test_penny_isolation.py` passes with the new
  `penny_lifecycle_replay.py`.

### Predeclared research run (executed after the code and tests above)

- **Collection.** A read-only stdlib collector was streamed to the
  `python-engine` container (`mode=ro`, one read transaction); there were no
  Production writes, restarts, provider calls or orders. Replay ran locally
  on current Dev code.
- **Primary run** (`docs/2026-10-03-penny-lifecycle-complete-sessions.json`):
  - parameters: 2026-07-30 to 2026-09-03, `PENNY_PAPER`, `PR1_CALM`,
    `complete_only`;
  - universe: 40 tickers selected by coverage alone, which includes some
    gold, silver and metal ETFs present in the minute cache;
  - coverage: 1,040 requested ticker-days, of which 161 were `COMPLETE` and
    usable, 296 `PARTIAL` (excluded) and 583 `UNAVAILABLE`;
  - funnel: 60,375 evaluations producing 3 accepted signals and 3 fills.
    The largest reject codes were volume below pace (22,461), time window
    (21,289), breakout not confirmed (15,560) and circuit blocked (863);
  - result: 3 closed trades and 0 unresolved, with a net of **+₹31.52**
    after ₹1.57 of costs;
  - exits: two paper LTP stops (−₹3.37 and −₹2.54), and one smart-EOD exit
    (SIGACHI, +₹37.43) after price ran from a 28.16 target to 29.69;
  - concentration: excluding the best winner, net is −₹5.91. The
    adverse-fill bound is +₹9.30.
- **Sensitivity run**
  (`docs/2026-10-03-penny-lifecycle-allow-gaps-sensitivity.json`):
  - same 40 tickers, `allow_gaps`, labelled
    `MISSING_MINUTES_TREATED_AS_NO_TRADE_UNVERIFIED`;
  - coverage: 457 usable ticker-days and 154,834 evaluations;
  - funnel: 7 accepted signals, giving 5 fills, 1 rejected as the same
    ticker already being occupied and 1 rejected as stop already breached;
  - result: 5 closed trades with a net of **+₹81.12**; the two smart-EOD
    runners (SIGACHI and KOHINOOR) produce +₹91.95;
  - concentration: excluding the best winner, net is +₹26.60. The
    adverse-fill bound is +₹43.64.
- **What this does and does not show.** It is the first exact-lifecycle
  evidence that the shipped book trades only rarely, and that its outcome
  depends on letting a few winners run to the 14:30 rule. Three to five
  trades cannot establish profitability, an expectancy or a capital return.
  These are retrospective, coverage-selected samples with no holdout, and
  are not grounds for tuning gates, funding or partner qualification.

### Remaining after B1/B2

- An exact CNC Connors adapter (the second half of the original B2 bullet),
  then B3–B6.
- Point-in-time universe, regime and sector inputs before any
  `FULL_PORTFOLIO` claim.
- Owner decisions on:
  - kill-switch wiring;
  - minute capture through 15:00;
  - whether to replay future sessions prospectively as a frozen holdout.
- Independently, the F&O F0 R1–R5 review items and F1.
