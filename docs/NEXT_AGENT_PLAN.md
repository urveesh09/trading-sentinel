# Trading Sentinel — next-agent execution plan






## October 9 (evening) — open items closed (done, Dev, commit `68e965a`, pushed, not deployed)

- Problem: the Oct 9 audit's remaining items: F&O profit-lock floor missed by
  the 90 s sample; gateway 413 for any oversized notify; unexplained
  ledger/position gaps; two Smart positions OPEN.
- Files: `config.py`, `tests/test_fno_fast_exit.py`, `tests/main_surface_golden.json`,
  `node-gateway/server/app.js`, `routes/internal.js`, `utils/split-message.js`
  (new), gateway tests (2 new files, 2 new notify tests),
  `docs/2026-10-09-ledger-position-reconciliation.md` (new).
- Acceptance: fast exit registered by default (surface golden lists
  `fno_fast_exit` 10 s); 30 KB notify accepted and other routes still 413;
  long best-effort alert sent as parts, each ≤ 4,096 and rebuilt exactly;
  every ledger gap matched row by row (sums equal the audit deltas).
- Rollout: merge, rebuild the engine and the gateway. Rollback:
  `FNO_FAST_EXIT_ENABLED=false`; revert the gateway commit.
- Next: after deploy, watch `fno_fast_exit` telemetry, `fno_tick_skip
  reason=fno_pass_in_progress`, and quote `over_documented_limit` on
  `/ops/provider-budget`.

## October 9 — Production audit fixes O9-R1/S1/M1/O1/Q1-Q3/E1 (done, Dev, commit `959392a`, pushed, not deployed)

- Problem: a DNS failure on the 11:19 restart left the symbol cache empty
  all afternoon (no retry); Smart held exits, Momentum, Penny and the
  overnight entry went blind; Momentum heartbeats hit HTTP 413; quote sends
  could bunch past 1/s; instrument-keyed 429s were uncounted; >500-token
  requests were unchunked; two bad expiry notices could block a healthy one.
- Files: `kite_client.py`, `main.py`, `ops_watchdogs.py`, `routes_ops.py`,
  `penny_smart_shadow.py`, `penny_scanner.py`, `edge_overnight_paper.py`, `expiry_paper.py`,
  tests `test_oct9_audit_fixes.py` (new, 14), `test_expiry_paper.py`,
  `test_penny_cron_gating.py`, `test_scheduler_closures_invoke.py`.
- Acceptance (met in Dev tests): restart + DNS failure loads the snapshot and
  the recovery job restores a provider refresh, then no-ops; no snapshot ->
  unusable and the watchdog pages; Smart held symbols quoted by symbol with
  an empty cache; 497 unknown tickers give one family line under 10 KB and
  a 413 is logged; overnight with no quotes retries at 15:25 then records
  DATA_UNAVAILABLE; 1,100 symbols quoted in 500/500/100; a delayed shared
  limiter no longer lets two sends fall within 1/rate; 429 on the instrument
  path counted; 971 tokens chunked; two 422 expiry notices do not block a
  healthy third in the first round; Penny skips at once after a failed
  refresh. The 13 tests written first all fail on the old code.
- Config/migration: no new setting; new file `/data/nse_instrument_cache.json`;
  two nullable columns on `expiry_paper_notices`; new scheduler job
  `instrument_cache_recovery`.
- Rollout: merge, rebuild the engine. Rollback: revert (the snapshot file
  and columns are inert to the old code).
- Next:
  1. After deploy, check `/health.instrument_cache` (source PROVIDER, size
     ~9k) and that the snapshot file exists after 08:00.
  2. Two Smart positions (STEELXIND, TATSILV) are still OPEN in Production;
     they will be quoted by symbol and their pending deadline exits retried
     at the next session's first executable bid. Watch `smart_penny` on /health.
  3. `/ops/provider-budget`: quote `over_documented_limit` should be 0.
  4. Still open: gateway-side 413 handling for other senders; historical
     position-store mismatches (O9 #11); C4/C7 deferred items.

## October 8 (late night, 2) — follow-up review F1–F3 (done, Dev, commit `1f4321b`, pushed, not deployed)

- Problem: overnight admission used the pre-scan clock (could enter after
  15:29 and record 15:20) and had no snapshot TTL (F1); two permanently
  rejected notices blocked healthy ones (F2); the quote budget was only
  measured (F3).
- Files: `edge_overnight_paper.py`, `notice_outbox.py` (new),
  `kite_client.py`, `config.py` (`KITE_QUOTE_RATE_PER_SEC`), `routes_ops.py`,
  `node-gateway/server/routes/internal.js`, `services/telegram.js`, tests.
- Acceptance (met): scan crossing 15:29 refuses; actual decision time
  recorded; missing/stale/future snapshot refuses; two 422 notices and two
  unknown-failure notices do not block a healthy one over 8 rounds; outage
  retries only the first row; an acknowledged part is not resent;
  concurrent load stays within the quote budget with merged calls and
  bounded management wait.
- Config impact: new `KITE_QUOTE_RATE_PER_SEC=1.0`. Gateway contract: 422
  for rejected content (engine and gateway must be rebuilt together).
  Schema: two nullable columns on the overnight notice table (added on open).
- Rollout: merge, rebuild engine and gateway together. Rollback: revert;
  or set `KITE_QUOTE_RATE_PER_SEC=3` to match the old shared rate.
- Next:
  1. After a market day, read `/ops/provider-budget`: quote `over_documented_limit`
     should be 0, `http_429` 0, `quote_budget.max_wait_sec.management` small.
  2. Expiry agent: adopt `notice_outbox` in `expiry_paper.flush_notices`.
  3. Watch overnight 15:20 receipts for `decided_at` and the new refusals.

## October 8 (late night) — review R2–R6 (done, Dev, commit `fc58da3`, pushed, not deployed)

- Problem: independent review of the Oct 8 fixes: research arms inherited
  the changed default (R2); overnight cash-trim kept the larger order's
  price and stale quotes passed on date (R3); cohort report mislabelled
  unavailable paths (R4); agent guard could stay held (R5); provider limits
  differ by endpoint (R6). The expiry agent also flagged the overnight
  outbox blocking flaw.
- Files: `edge_overnight_paper.py`, `momentum_paper_path_adapter.py`,
  `momentum_admission_cohorts.py`, `agent/agent.py`, `kite_client.py`,
  `routes_ops.py`, tests, the research scripts and README.
- Acceptance (met): tests for the re-walked price, the stale last trade,
  the failed re-quote, outbox step-over / gateway down / long-notice parts,
  cohort unavailable attribution, guard release, budget counting; the
  research re-run reproduces both figures.
- Rollout: merge and rebuild. No schema/config change. Rollback: revert.
- Next:
  1. After a market day, read `GET /ops/provider-budget` (or the
     `kite_endpoint_over_documented_limit` lines). If quotes exceed 1/s,
     batch callers first (one `/quote` takes up to 500 instruments), then
     add a quote-specific limiter tested with Penny, expiry and F&O exits
     together.
  2. Overnight: count `stale_last_trade` and `no_fresh_quote` refusals.

## October 8 (night) — review R1: expiry summary over Telegram's limit (done, Dev, commit `c4329bc`, pushed, not deployed)

- Problem: the expanded summary (4,277 characters) would be refused by
  Telegram and block every later expiry notice.
- Files: `python-engine/expiry_paper.py` (`notice_parts`, `_notice`,
  `flush_notices`), `python-engine/tests/test_expiry_paper.py`, the design
  doc, the guide and the checklist.
- Acceptance (met): parts stay within 3,500 characters and are rebuilt with
  nothing lost; a full day is accepted under the Telegram limit with the
  prefix; a refused row is stepped over after 3 attempts and stays pending;
  with the gateway down, the flush stops after two failures; the Oct 8
  replay splits into 3,472 + 826 characters.
- Rollout: with the same merge and rebuild before October 13. Rollback:
  revert; part rows are ordinary outbox rows.
- Left to the developer agent (outside expiry): the review's R2–R6, the EDGE
  overnight outbox's same blocking pattern, and per-endpoint Kite budgets.

## October 8 (night) — Oct 8 production audit fixes (done, Dev, commit `7f028ed`, pushed, not deployed)

- Problem: the Oct 8 audit reproduced latent defects (F&O peak persistence
  without futures, inverted bought-put time-stop sign, overnight missing
  depth fails open), a scorecard wording/lookback issue, the Momentum
  cohort-pooling limit and agent status timeouts.
- Files: `fno_exit_rules.py`, `fno_orchestrator.py`, `fno_positions.py`,
  `config.py`, `edge_overnight_paper.py`, `partner_orchestrator.py`,
  `momentum_admission_cohorts.py` (new), `agent/agent.py`, tests, research
  `docs/research/fno/2026-10-08-time-stop-sign/`.
- Acceptance (met): peak kept on a no-futures tick and arms the lock on the
  next; bought CE and PE defer/exit symmetrically; live default banks at the
  time stop; missing/empty/zero depth refused; entry capped at visible asks
  with walked price; scorecard says "observed"; 30-date window; cohort split
  with the Oct 6 freeze verifying; status publish skip/streak tests.
- Config impact: `FNO_TIME_STOP_RESPECTS_PREMIUM` True → False (no `.env`
  override in Production). No schema migration (`best_premium` exists).
- Rollout: merge and rebuild. Rollback: revert the commit; to keep the sign
  fix but restore the deferral set `FNO_TIME_STOP_RESPECTS_PREMIUM=true`
  (replayed worse).
- Next:
  1. Watch the first single-leg F&O trades: `time_stop` exits in profit,
     `profit_lock`, no `fno_time_stop_deferred_in_profit` lines.
  2. Overnight 15:20: count `no_depth`, `no_sellers`, `thin_asks_*` refusals
     and compare walked entry prices with LTP + 25 bps.
  3. Owner decision pending: the F&O 15% drawdown halt sits ₹10.6k below
     current paper equity; replays show it can stop the book right before
     its trend winners. Do not change without the owner.
  4. Score selective Momentum only on `SELECTIVE_ADMISSION_V1`.

## October 8 (evening) — owner's expiry stop rule (done, Dev, commit `ab5e3a1`, pushed, not deployed)

- Owner decision: observe 8 more expiries (10 in all). If every one loses,
  stop expiry-day F&O. Drop any play or section that keeps losing on its own.
- Each day summary now prints the tally (`owner_rule_lines`). At expiry 10,
  report the verdict to the owner with the per-play counts, and recommend
  which plays to drop even if the rule is not met. The owner decides; nothing
  stops automatically.

## October 8 — first SENSEX expiry audit follow-up (done, Dev, commit `b7d3f4d`, pushed, not deployed)

- Problem: the owner asked what went wrong and right on October 8, for the
  fixes, and for better strategies, on the expiry module and report only.
  The audit found:
  - strategy losses, not data faults: a one-lot A gave back ₹1,090 from its
    best mark; B's losing put and C both settled at zero;
  - a 966 vs 967 slot count;
  - latent stale OI in the context;
  - nominal snapshot labels;
  - a shared-limiter wait tail of up to 28.9 s.
- Files:
  - `python-engine/expiry_paper.py`;
  - `python-engine/scheduler_setup.py` (tick guard);
  - `python-engine/tests/test_expiry_paper.py`;
  - the design doc, the guide, this plan, the checklist and the atlas.
- Acceptance (all met):
  - 966 slots, and no tick at exactly 15:40;
  - stale OI is excluded, with coverage recorded;
  - the batch runs in the management lane and the lane is restored afterwards;
  - `liquidation_net` walks the depth and returns None on stale, shallow or
    missing quotes;
  - AL's lock is half the peak gain for one lot and A's bank for two or more;
  - AL copies A's entries;
  - BP sells both legs on the first tick at target, BH is unchanged, and the
    BP mark equals its fills;
  - the summary shows the path lines and the "read" times;
  - the Oct 8 replay reproduces Production exactly.
- Rollout: merge and rebuild before the next expiry (Tuesday October 13, NIFTY, unless the calendar shifts it). That is the
  first scored day for AL and BP and the first `expiry-context-v1.1` day. No
  schema or config change. Rollback: revert; old day states are read as
  before.
- Next:
  1. Watch October 13. Expect the summary to read "ticks N of 966", the
     coverage "from N/M fresh quotes", and AL/BP rows. Max decision lag
     should drop if limiter queueing was the cause.
  2. Confirm the official SENSEX/NIFTY settlement price against our sampled
     index (still open since October 6).
  3. Isolated Dev tests from audit item 5 (send failure, a crash between ACK
     and commit, restart with open legs, an absent final sample) are still to
     be written.
  4. After 20 expiries, score `expiry-v1`, v1 shadows and v2 shadows on their
     own records (AL/BP from October 13). Test an IV/RV gate on D's recorded
     context; freeze it as `expiry-context-v2` only if it holds.

## October 7 (evening) — owner-requested profit keeping + Oct 7 audit fixes (done, Dev)

- Source: Production `docs/2026-10-07-production-deep-audit.md` (read-only),
  and the owner's question of how to keep small profits without pausing half
  the market.
- Done:
  - F&O profit lock and re-entry confirmation (paper, on by default). The
    flags `FNO_PROFIT_LOCK_ENABLED` and `FNO_REENTRY_REQUIRES_CONFIRMATION`
    turn them off.
  - Audit fixes: T1 overnight retry, T2 D reserve breach reporting, T3
    attribution date check.
  - Momentum selective entry turned on (owner decision; round-3 skipped,
    unscored). Penny noise stop was already on.
  - Overnight: an exit records `open_is_prev_close`; the forward fidelity
    check is in SYSTEM_GUIDE.
  - Overnight realistic-entry guards, from the live-universe replay
    (`docs/research/edge-overnight/2026-10-07-live-universe/README.md`).
    The old +₹2.2 lakh study was mostly unbuyable circuit closes. The
    realistic edge is about +0.6% a trade, positive every quarter, and very
    sensitive to slippage.
- Not done, by evidence:
  - an overnight liquidity floor (it cut the edge: the edge is in thinner
    names);
  - an overnight strength filter (all live picks were already 0.96–1.0);
  - a faster F&O management cadence (no gain in the replay);
  - an early profit lock (lost money).
- Still open from the audit:
  - T4: finite research-writer wait and the unbounded outer finalizer;
  - T7 / C7: late-bar shadow closure (frozen source);
  - T8: four historical position-store mismatches;
  - T9: DB size and bootstrap cost.
- Rollout: an engine rebuild. Additive column `fno_positions.best_premium`.
  Rollback: set the two flags off, or revert.
- Watch: the evidence is in-sample (12 trades, and the margin was picked
  after seeing 4 re-entry cases). Judge only on forward paper trades.

## October 7 — expiry chain context `expiry-context-v1` (done, Dev, record-only)

- Problem: the owner asked whether the option chain, OI, change in OI and IV
  can improve the odds. The research ranked implied against realized
  volatility first, OI walls second, and change in OI, max pain and PCR as
  weak. The owner chose to observe first, then integrate what proves useful.
- Files: `python-engine/expiry_paper.py`, `python-engine/tests/test_expiry_paper.py`
  and the design doc.
- Acceptance:
  - the max pain and realized-volatility math is checked;
  - the straddle-implied IV recovers a known volatility;
  - walls, PCR, OI change and futures build-up are read correctly;
  - a whole day gives identical positions with and without OI;
  - snapshots are taken at 14:30 and 15:13:30, and the summary shows the
    context block.
- Rollout: an engine rebuild (the October 8 SENSEX expiry is the first
  observation). No schema change: the context lives in the tick JSON and the
  day state. Rollback: revert; the stored context is ignored.
- Next:
  - after October 8, check that the fields fill and look sensible on real
    SENSEX data;
  - after more expiries, freeze thresholds for a D/B IV-against-RV gate and
    an A wall label as a new version, and score them only on later expiries.

## October 6 (night) — Production audit follow-up: O1 overnight fees, A1 partner updates (done, Dev)

- Source: Production `docs/2026-10-06-production-deep-audit.md` (read-only).
  The expiry findings E1–E5 were done in `db5153d`.
- Problem:
  - O1: overnight admission debited premium only. Oct 6 left −Rs 7.59 after
    buy charges.
  - A1: a partner target update was refused by the 30 s quote bound and
    stayed QUEUED with no retry and no reason.
- Files: `edge_overnight_paper.py`, `partner_manual_advisory.py`,
  `hedge_advisory.py`, `partner_orchestrator.py`, and tests.
- Acceptance: the tests listed in HANDOVER_CHECKLIST.
- Rollout: an engine rebuild. The schema change only adds a column.
  Rollback: revert; the column is ignored.
- R1 done (`5817263`): research writers wait up to 5 s and name the holder.
  Expiry-tick telemetry was decided against (see SYSTEM_GUIDE).
- C3 done: the classic Penny kill switch is fed from the durable ledger.
- Momentum allocation holdout frozen (S7a). Evaluate after about 10 sessions
  with capital skips.
- Still blocked by the round-3 frozen sources: C4 (DP once per scrip per day,
  in `penny_risk.py`) and C7 (`momentum_shadow.py` late bars).

## October 6 (evening) — expiry shadow plays (done, Dev)

- Problem: the owner asked for changes that could make expiry trading
  profitable after the October 6 loss, without fitting October 6.
- Files: `python-engine/expiry_paper.py`, `python-engine/tests/test_expiry_paper.py`
  and the design doc.
- Acceptance:
  - BH, C500 and D run beside A, B and C on the same ticks, with no Telegram
    trade lines;
  - D's settlement loss stays inside its ceiling on a runaway close;
  - an outage values D at its maximum loss;
  - a credit too small for its charges is refused.
- Rollout: an engine rebuild, ideally before October 8, the shadow plays'
  first expiry. The schema additions only add columns. Rollback: revert; the
  extra columns and rows are ignored.
- Still open:
  - score the shadow plays beside `expiry-v1` after 20 expiries;
  - D's live use needs the owner's separate margin decision.

## October 6 — expiry first-day audit remediation, `expiry-exec-v2` (done, Dev)

- Problem: the first-day audit found these defects:
  - freshness and windows were judged at the request start;
  - fills could not be replayed (only top of book was logged);
  - a partial bank lost its remainder;
  - concurrent flushes could send a notice twice;
  - an expiry with no index quote vanished from the record;
  - SENSEX used NSE charges, and fees were not frozen per position;
  - messages showed a slice net that excluded buy fees;
  - 90 of 966 slots were skipped.
- Files:
  - `python-engine/expiry_paper.py` and `python-engine/edge_overnight_paper.py`;
  - `python-engine/cost_schedules.py` and `python-engine/config.py`
    (`FNO_BSE_EXCHANGE_TXN_PCT`);
  - `python-engine/scheduler_setup.py` (`expiry_paper_flush` job);
  - tests and goldens.
- Acceptance:
  - the audit's clock probe (one packet 15 s ahead of the start, one 15 s
    behind it) is judged at receipt;
  - a B window crossing in transit is refused;
  - the 3-wanted/1-filled bank keeps 2 pending across a restart;
  - two concurrent flushes deliver once (both books);
  - a dark index day records 217 ticks and a summary;
  - BFO charges are frozen at entry;
  - a v1 store migrates and settles.
- Rollout:
  - one engine rebuild. The gateway is unchanged; Production `70a2256`
    (PR #103) already serves `require_delivery`.
  - Schema additions are additive.
  - Rollback: revert the commit. The extra columns are ignored by v1 code.
- Not changed: strategy thresholds, the ₹2,500 ceilings, the 20 s and 5 s
  freshness limits, paper-only authority, and the owner's live halt.
- Still open:
  1. Merge and rebuild before Thursday's SENSEX expiry (October 8), the first
     BFO day.
  2. After it, read the summary's data line and the tick timing. If limiter
     wait dominates, consider reserving quote capacity for the expiry tick
     during 13:00–15:40. That decision needs evidence first.
  3. Compare our settlement sample with the official settlement price, without
     overwriting assumed rows.
  4. Run the 20-expiry review on `expiry-exec-v2` days, with October 6 shown
     separately.

## October 5 (late night) — expiry book second review (done, Dev)

- Problem: partial exits could exceed the ₹2,500 reserve; the gateway reported
  success for Telegram sends that failed.
- Files: `python-engine/expiry_paper.py`, `python-engine/scheduler_setup.py`,
  `node-gateway/server/routes/internal.js`,
  `node-gateway/server/services/telegram.js`, and their tests.
- Acceptance: the review's repro stays inside `max_loss`; `require_delivery`
  answers 502 on a refusal without a gateway retry.
- Rollout: one rebuild of both containers. Rollback: revert the commit; no
  schema change (column meanings: `costs` and `net_pnl` include the buy's
  charges from entry; no Production rows exist yet).
- Still open: as in the section below (merge and rebuild, first-expiry
  freshness check, 20-expiry review). Do not loosen the 20 s freshness rule to
  get trades; first find out whether missing timestamps, provider lag or
  request timing caused any rejections.

## October 5 (night) — expiry-day book review fixes (done, Dev)

The independent review of `f000acb` was applied. The details are in the
[design doc](2026-10-05-expiry-day-paper-book.md) "Revised" note.

Still open:

1. **Merge and rebuild.** Production runs `acc7181` and lacks the module.
2. **First expiry:** check the summary's stale-index and stale-future counts. If
   Kite index timestamps lag, the box is unusable, A and C stand down, and the
   freshness rule for index quotes needs evidence-based adjustment as
   `expiry-v2`.
3. **Initial review after 20 expiries:**
   - per play and per underlying;
   - no-trade days count as zero;
   - report net without the best day;
   - keep assumed settlements and auction-window fills separate.

## October 5 (night) — Production audit remediation (owner-directed order)

Source: [Production audit](../../Production_Trading-sentinel/docs/2026-10-05-production-deep-audit.md)
(Production report; read-only).

Done in Dev (this slice): C1 Momentum post-dispatch lock; partner informational
surfaces restored while advisory is unqualified; partner RV datetime fix; Kite
acquisition retries.

**Round-3 Kite scoring is postponed (owner, Oct 5 22:45).** The data and freezes
are committed (`ae2b775`). The 21:12 scoring run was killed at about 22:40 for
low system memory and wrote no results, so the Kite Jan–Jul 2026 data is still
unseen.
- Do not rerun until the owner names a date. Then run only
  `scripts/run_preregistered_study.py run <study> --out <dir> --jobs 1` for
  momentum-smart-t3, then penny-noise-t3. No new acquisition.
- **Freeze drift (found Oct 6).** Later commits changed bound common files:
  - `config.py`, for both studies: `653560a` added
    `PARTNER_MANUAL_ADVISORY_SEND_UNQUALIFIED` and `db5153d` added
    `FNO_BSE_EXCHANGE_TXN_PCT`;
  - `cost_schedules.py`, for Penny: `db5153d` added the BSE options path.
  - `run` therefore refuses to score.
  - A bound diff shows only those file hashes moved. The Penny effective
    settings and execution-cost snapshot are identical, and the equity cost
    path is untouched.
  - Since nothing was ever scored, the fix is to freeze both studies again
    into new dated folders right before scoring, with the same study
    definitions, and to record this reason in the study docs.
- Until then, the frozen sources stay unedited. That blocks items 1 (replay arm),
  2, 3 and 5 below.

Next, in order:
1. **Penny profit protection: paper rule implemented** (`penny_profit_lock.py`,
   see SYSTEM_GUIDE). Remaining: once round-3 scoring has finished, add a
   labelled diagnostic arm to `penny_lifecycle_replay.py` (seen data); judge the
   rule by forward paper days. No untouched Penny data is left.
2. ~~Penny durable, settlement-fed daily brake~~ done Oct 6 (`main.sync_penny_daily_brake`, no frozen file edited).
3. C7: late Momentum shadow bars (15:15 EOD exits unresolved).
4. ~~C8~~ done (whole-trade analytics).
5. C2 BSE option schedule and C4 one DP per scrip per day remain; DP ₹15.34 done.
6. ~~C5/C6~~ done (overnight outbox and catch-up).
7. ~~Scheduler IN_FLIGHT telemetry; Penny funnel stages~~ done (retried and
   parked completion writes; `ops_funnel_daily.stages_json`). Swing heads-up and
   the heatmap log name are done.
8. ~~Owner halt~~ decided: `OWNER_LIVE_ENTRY_HALT=true` in Production `.env`
   with Momentum automatic, so it trades on paper until the owner lifts the halt.
9. ~~Partner cards~~ decided: unqualified cards go out labelled PURE ADVICE —
   NOT CHECKED.

## October 5 (evening) — expiry-day paper book

[Design and frozen rules](2026-10-05-expiry-day-paper-book.md). Paper only.

1. It needs the merge and rebuild before its first expiry. The same PR carries
   the gateway fix that Telegram needs.
2. After each expiry, check the Telegram summary or `expiry_paper_days` /
   `expiry_paper_positions`. Confirm the box was READY and the tick log reaches
   15:40.
3. Score each play after 20 expiries against the pre-registered measures. Any
   rule change is `expiry-v2`, scored only on later expiries.
4. Watch the SEBI settlement decision (consultation closed Oct 3). If the auction
   settlement or session times change, record the date; B and C must be
   re-judged from then.

## October 4 (late) — start here: successor inheritance and gateway fix

Read [the inheritance doc](2026-10-04-successor-inheritance.md) first.

1. Confirm Production was rebuilt with the container uid fix and the gateway is
   healthy (it crash-looped with `SQLITE_READONLY` on October 4).
2. Read and record the round-3 Kite scoring results from the October 5, 17:07
   Windows task. The in-chat reminder was cancelled; nothing else prompts it.
3. Then continue with the items below.

## October 5 — EDGE overnight result and next steps

`edge-overnight-t1` is complete ([study](2026-10-05-edge-overnight-study.md)).
The candidate failed only the frozen drawdown check (measured against starting
capital); the S60 attribution arm passed all four.

Next, if the owner approves:

1. **E1 (done):** the `edge_overnight_paper.py` ₹25k paper book. After 10 or more
   sessions, compare it with the EDGE_PAPER book on the corrected costs. Watch
   for exits waiting on circuit-locked names (`OPEN_DELAYED`).
2. **E2 (done):** delivery costs fixed in `calc_penny_costs`. EDGE_PAPER rows
   recorded before Oct 5 used the old schedule and were not migrated, so compare
   from Oct 5 onwards.
3. **E3:** a future study must declare a peak-relative drawdown metric before
   freezing. Do not re-score `edge-overnight-t1`.

Capital floor: at least about ₹25,000 for this idea, because of the DP charge.

## October 5 — forward paper evidence and the Kite untouched scoring

Read [the slice](2026-10-05-forward-paper-evidence.md). Every module runs on paper
with live money off. New forward evidence comes from the `MOM_SELECTIVE` shadow
variant and the smart-Penny paper shadow.

Next:
1. After the owner's same-day Kite login (owner authorised ~16:30–17:00 IST,
   October 5), acquire January–July 2026 history with
   `scripts/acquire_kite_history.py`, checking coverage only. Then freeze, commit,
   push and score `momentum-smart-t3` and `penny-noise-t3` once.
2. After 5 or more sessions, compare forward `MOM_SELECTIVE` against `MOM_BASE`
   (`/api/experiments/momentum`, decision-quality report), and the smart-Penny
   shadow against the Penny paper book. Read forward data only after a
   predeclared count of sessions; do not tune on it.
3. Open items carried forward: fix the three Penny paper `exit_price` blob rows;
   Penny D1 live-risk reconciliation; momentum auto-execute stays the owner's call.

## October 4 — smart Penny implementation and matched diagnostics

Read [the current implementation receipt](2026-10-04-penny-smart-trader-implementation.md)
first. R1 strength ranking and R2 stateful affordable entry / confirmed-close
management are implemented as default-OFF paper/replay variants. The separate
paper book also owns its simulated cash, fees, working risk and daily brake;
this completes paper accounting, not R3's actual live fill/settlement contract.
T4 compares five arms on the ₹2,000 budget over two already examined windows;
do not label either an untouched holdout or optimize exits until it looks good.
Keep all losing arms and execution stress results.

T4 is complete and `NOT_SUPPORTED_STAYS_OFF`: incumbent broader net +₹91.7169
(38 trades), combined −₹47.5019 (153), entry/risk −₹47.7479 (79), exit −₹2.2712
(48), ranking unchanged. Do not promote any new trading arm. Follow the explicit
D1–D4 material slices in the receipt: reconcile live risk; independent data and
decision context; small calibrated entry utility under matched risk; exit tests
on fixed cohorts before whole-book replay. No September outcome-driven retuning.

Remaining sequence:
1. Review the frozen T4 results and failure paths. Select further work from
   stable evidence; no activation from a positive seen-window PnL.
2. R0/T3 still needs absent January–July Kite history. Acquire only through the
   existing owner-login/data-contract process; commit the freeze before any
   actual untouched scoring. No present task generated or invented that data.
3. Develop a separate exit hypothesis only after isolating selection/entry
   economics. Preserve the incumbent exit policy if thesis exits do not help.
4. R3 must reconcile actual fills, costs, open risk and classic daily settlements
   before live activation/increased risk. Candle replay cannot prove depth,
   intraminute fills or runtime sampled-quote management.
5. R4 requires genuine point-in-time universe/regime/eligibility, continuous
   portfolio capital and untouched data, then prospective paper execution
   observations. GitHub promotion is separate; Production/F&O stay protected.

Current changes remain uncommitted Dev at `a674740`; no push/deployment, funding
change or broker order. The broad regression's unchanged F&O fixture failure is
recorded in the receipt; do not silently call that run completely green.

## October 4 — authorized corrections completed; next Penny hypotheses

[Implementation and verification receipt](2026-10-04-penny-corrections-and-relative-strength-slice.md)
closes the explicit stop-arm/effective-freeze and decision-stop rounding findings
from the earlier review below. Current cached instrument ticks now control
Penny execution; dated metadata is required for new live entries. Final fill
risk, complete settlement-driven daily brakes and marked exposure remain open.
830 selected tests and a final 55-test source check passed; atlas regenerated.
Changes are uncommitted in Dev at base `a674740`, not pushed/promoted. No new
live flags, funding, F&O operational or Production changes.

Read [the researched strategy and explicit R0–R4 slices](2026-10-04-penny-consistent-returns-strategy.md).
Next: finish R0 once independently validated untouched Kite history exists and
a corrected source freeze is committed before scoring; then R1 tests persistent
positive stock-specific strength ranking while keeping entries/exits fixed.
Test broader reclaim entries and winner trails separately after selection has
evidence. R3 reconciled owner risk/daily cash accounting is required before any
live activation or increased admitted risk. Preserve all failed hypotheses,
unknown/missing-data status, costs and F&O resource priority. A daily 1% goal is
measured on allocated equity and never becomes a mandatory entry quota.

Pending T3 now distinguishes BAR_LOW/NOISE_FLOOR and ₹100,000/₹2,000 books;
its January–July snapshot path is absent. The earlier review remains a historical
receipt; its statement that no source changes were made refers to that stage.

## October 4 — Penny independent-review findings before the next study

Read [Penny efficiency review and discussion](2026-10-04-penny-efficiency-independent-review.md)
before the older round-3 sequence below. Current `penny-noise-t3` BASELINE calls
the default-ON runtime noise stop, so it cannot isolate the old-to-new stop
hypothesis. Add explicit, exactly-once stop-policy inputs and bind effective
settings before freezing/scoring. Correct rounded-distance quantity arithmetic;
review actual-instrument tick and fill/protection risk before any live promotion.
Preserve previous frozen results; do not relabel them as current-policy results.

Then complete the untouched Kite comparison with distinct old/current policies,
owner-budget economics and daily marked returns. Further hypotheses should
isolate a stop or execution/selection change on shipped entries. Research a
larger admitted risk allocation only after an edge survives; this is a material
change, not a rounding fix. Existing caps/own cash/exit recovery and F&O capacity
remain protected. The owner's daily target is an aspiration, not a trade quota.

This task is review/discussion only: findings and proposals remain open, no
source/flag change or new scoring. 45 focused tests passed; reproductions reveal
gaps those tests do not cover. `a674740` is confirmed pushed; no merge/deployment
by this task. Review docs are Dev-local/uncommitted. Tomorrow's Production/paper
decision is separate; Penny live and Momentum auto-execute remain default OFF.

## October 4 — round 3: smarter Momentum/Penny candidates; Momentum direct trading built (OFF)

Development (seen windows):
- `MOM_SELECTIVE` sat out the falling Aug–Oct market (0 trades vs shipped −₹3,110).
- The runner exit was worse on shipped entries.
- `PEN_NOISE_STOP` beat the Penny baseline (+₹93 vs +₹78; DD ₹32 vs ₹45).

Next, in order:
1. With a same-day Kite session (owner login; run after 15:45 IST), acquire Kite
   history Jan–Jul 2026 for Momentum (15-minute + NIFTY 50) and Penny (minute)
   into `docs/research/kite/2026-10-05-*`. Check coverage only.
2. Freeze `momentum-smart-t3` and `penny-noise-t3`, commit, then
   `run --jobs 3`, once each. Record the verdicts.
3. Port only a promising candidate to the runtime (paper twin first).
4. Owner decides `MOMENTUM_AUTO_EXECUTE` after promotion; recommended together
   with a passing selective entry.
5. Fix the `PENNY_PAPER` exit_price blob rows (3 rows, Aug 31).

## October 4 — owner direction: Momentum, then Penny; F&O only records SENSEX history

F&O: no further development except SENSEX/NIFTY future-candle recording
(`research_future_candles`, from the first Production run after promotion).
Next: smarter Momentum entries/exits plus direct (no-approval) execution, then
Penny, each tested with the freeze-then-score method.

## October 4 — F&O growth slice implemented (paper, Dev only)

[Growth slice](2026-10-04-fno-growth-slice.md): adaptive risk (shrink in drawdown,
grow only when proven, two-strike day halt), tighter brakes (3/6/10/15%), cap
₹40k, multi-lot capped-loss book, SENSEX on the paper single-leg book with a
NIFTY-participation proxy and a correlation guard. Vehicle-by-IV ships OFF.

Owner test Sep 17–Oct 1 (see slice): found and fixed the drawdown-cut
"silent halt"; fresh ₹2L = +₹11,821 on 10 sessions; minimum live test revised to
₹2L. Since July the paper book is −₹22k; risk rules trim drawdown only.

Remaining, in order:
1. Promote through GitHub after owner review; watch paper logs for
   `fno_adaptive_risk`, `two_strike_day_halt`, `correlated_exposure_open` and
   SENSEX entries.
2. SENSEX replay: a second read-only export with SENSEX futures candles
   (leave the frozen `2026-10-04-archive/_local` untouched), underlying-aware
   replay, frozen round on sessions from October 5, 2026.
3. BFO support in `fno_exit_evidence`/`fno_exit_recovery` before any live SENSEX.
4. Score vehicle-by-IV and the fast exit loop as frozen candidates on forward data.
5. Redesign the stale `test_mark_to_market` DR writer-row test.
6. Entry quality in losing stretches (e.g. an equity-curve pause): freeze first,
   score only on sessions from October 5.

Do not loosen F&O hard limits beyond owner approval. Nothing pushed or deployed.

## October 4 — F&O replay built; shipped book still best; speed features OFF

[F&O replay and speed slice](2026-10-04-fno-replay-and-speed-slice.md): read-only
export of the archived NIFTY quote batches, a full-policy single-leg replay
(8 of 9 live paper trades reproduced), the pure entry planner / entry brakes
now shared by live and research, and two default-OFF speed features (fast exit
loop, bar-close trigger) under one F&O lock. Pre-registered `fno-trader-v1`:
shipped baseline +₹13,306 on Sep 24–Oct 1; FNO_TRADER_V1 +₹7,128 →
NOT_SUPPORTED_STAYS_OFF (pyramid blocked by the ₹30k structural cap, trend
filter skipped winners, partial/fast exit neutral).

Next: keep the archive growing and re-export weekly; score new frozen F&O
rounds only on sessions from Oct 5, 2026 (IV-aware vehicle, time-stop variant,
BANKNIFTY); paper-enable the fast exit loop for protection after promotion.
Do not loosen F&O hard limits. Dev only; nothing pushed/deployed.

## October 4 — T2 scored; improvement options and F&O review written

[T2 receipt](2026-10-04-t2-range-swing-momentum-slice.md): shared own-cash
`daily_portfolio` book (EDGE moved onto it, regression-identical), Range and
Swing portfolio replays, Momentum `NEXT_BAR_OPEN` clock + `THESIS_EXIT`, one
pre-registration tool (`scripts/run_preregistered_study.py`) and the
[testing method guide](RESEARCH_TESTING_METHOD.md). All T2 verdicts
**NOT_SUPPORTED_STAYS_OFF**; Range reclaim (−30% loss) and SWING_TRADER_V1
(−80% loss vs baseline) are the best leads. Penny CNC fired 0 times in 9
months (rule conjunction is effectively unsatisfiable).

Owner direction: running modules (including EDGE) stay on as they are.
Next per [improvement options and F&O review](2026-10-04-improvement-options-and-fno-review.md):
Swing round 2 (market-weather switch + affordable universe) on 2024–2025;
EDGE/Range geometry rounds; F&O chain-archive retention → F&O replay →
tick-driven exit monitor → frozen F&O candidates. Windows Jan–Jun 2026 (daily)
and Aug 10–Oct 1 (Momentum) are now seen. Dev only; nothing pushed/deployed.

## October 4 — T1 Penny/EDGE trader candidates scored; none beat baseline

[T1 slice receipt](2026-10-04-t1-penny-edge-trader-slice.md). The T0 prototype
was corrected (WATCH invalidation, expiry clock, volatility stop, participation)
and completed into `PEN_TRADER_V1/V2` with thesis exits, wired into the exact
Penny replay; EDGE gained a causal own-cash portfolio replay
(`penny_edge_portfolio_replay`) and `EDGE_TRADER_V1`. Freezes were committed
before untouched windows were scored. Verdicts: **NOT_SUPPORTED_STAYS_OFF** for
both. Penny untouched (13 sessions): shipped baseline +₹63.17, V2 −₹17.02.
EDGE untouched Jan–Jun, ₹100k own cash: shipped baseline −40.17% marked, V1
−44.78%; stop/target geometry (≈+2.8% targets vs −5.2% stops at ~50% hits) is
structurally negative.

Next: (1) owner decision on pausing EDGE paper and keeping EDGE live disabled;
(2) EDGE round 2 on geometry, judged on 2024–2025 untouched daily data;
(3) weekly Penny minute archive for future untouched windows; (4) T2 Range/
Swing/Momentum adapters. Do not re-tune on Sep 7–23/Oct 1 or Jan–Jun 2026; they
are now seen. Dev commits only; nothing pushed or deployed; F&O untouched.

## October 4 — active next direction: complete adaptive trader candidates

Follow the [revised adaptive non-F&O plan](2026-10-04-adaptive-non-fno-trader-development-plan.md).
The owner wants opportunity recognition and timely thesis-based management,
not another layer of subset-only filters. T0 couples candidate selection,
complete condition evidence, native warm-up and causal cash/clock fixes with
runnable Penny/EDGE stateful prototypes. T1 completes those policies; T2 adds
Range/Swing/Momentum using existing research and audits CNC; T3 qualifies on
untouched data at matched cash/risk and proves F&O noninterference.

Preserve R1–R5 acceptance and immutable earlier results. Strategy quality cues
may change only in explicitly named research versions; hard cash/risk/approval,
execution evidence, protective stops/recovery and deadlines remain constraints.
Keep baseline reproducible, all failed trials visible and new candidates OFF.
F&O is excluded and must remain unhindered, including shared cash/resources/exits.
No live activation or promotion follows from this plan revision.

Plan-only revision at `434c4cc`, Dev-local/uncommitted, preserving earlier dirty
source/evidence. No source/configuration/schema/dependency change, new test or
backtest, Production access, broker action, commit, push or deployment. Prior
130 test passes belong to the preceding review. All T0–T3 work remains open.

## October 4 — latest independent review; finish fidelity before tuning

The owner requested minor fixes, a plan for larger gaps and an identical-parameter
Yahoo comparison. [Review and R1–R5 follow-up](2026-10-04-non-fno-independent-review-and-repeat-plan.md)
is the active next slice. **The original plan is partial**, despite N1–N3 helpers
being present. Default policies did not change; first repeat matches all 16 prior
outcomes. Candidate filters/measurement cannot imply improved live performance.

Minor corrections cover Penny retest/profile validity and Momentum ATR/regime,
same-session positive-volume/deadline evidence and settings receipts. EDGE is
PROXY until causal holding/entry/cash semantics are established. 130 focused
tests passed; compilation/diff and 241-module atlas checks passed. Final repeat
and separately named candidate evidence remain distinct in the review receipt.

Next major work: explicit candidate interface and historical context/warm-up;
causal EDGE/Momentum lifecycle with marked/partial equity; real Range/Swing
adapters and bounded hypotheses; untouched trial qualification and F&O cash/
resource compatibility. Keep F&O excluded and unhindered. No new runtime gates,
funding, shared defaults, orders or canary are authorized by this review.
Baseline `434c4cc`; Dev-local uncommitted work, no Production access/edit,
configuration/schema/dependency change, push or deployment.

[Completed comparison](2026-10-04-non-fno-review-and-backtest-results.md): both
all-module repeats reproduce all 16 original outcomes; PEN_CONTEXT zero entries
with missing profiles, Momentum exit diagnostic −₹19.01 and EDGE independent-
trial PROXY sum −₹60,813.84. None proves improvement; R1–R5 stay open. Integrity
receipts bind snapshots/raw responses, current source/settings and trial freezes.

## October 4 — active N1–N3 implementation slice (Dev only)

The owner authorized N1, N2 and N3 from the researched non-F&O plan.  The
current implementation contract is [N1–N3 implementation slice](2026-10-04-n1-n3-implementation-slice.md): first replace known optimistic research
shortcuts with deterministic lifecycle measurement, then add named,
broker-free candidates.  F&O and shared live infrastructure remain out of
scope; baseline policy stays active unless a separate rollout is approved.

**Source completion boundary.** N1–N3 code is now present: Momentum has a
named shipped-exit lifecycle, EDGE has next-open lifecycle evidence, Penny has
default-off `PEN_CONTEXT`, and Range/Swing gates are pure research helpers.
No candidate has earned a policy change. Next: freeze candidate manifests,
compare equal cash/risk with coverage and all failures retained, then pursue N4
only if full-system context can be recorded. F&O operational compatibility and
any broker/paper observation remain separate, unapproved work.

Source implementation commit `65e050a`; 109 focused tests passed (one existing
HTTPX deprecation), affected modules compiled, `git diff --check` passed and
the atlas was regenerated to 241 Python modules. Dev only: no push, deployment,
Production edit, broker action, configuration or schema migration.

## October 3 — active next direction: smarter non-F&O entries/exits

The owner requested a researched development plan after the Yahoo results.
[Smart entry/exit plan](2026-10-03-non-fno-smart-entry-exit-development-plan.md)
is the latest direction: N0 baseline/F&O isolation and N1 lifecycle economics,
then Penny MIS/EDGE experiments, followed by Range/Swing and existing Momentum
research/parity. Activity counts are setup/selection/fill-specific; ₹15.18 is
five-session Penny sensitivity, not full-system/live earnings.

**F&O development is excluded and must not be hindered**, including shared cash,
regime/configuration, scheduler/DB/broker resources and exit authority. New
variants stay broker-free/default OFF until separate qualification and rollout.
No guaranteed daily profit, capital increase or gate weakening to force activity.
Reuse existing shipped VWAP/ATR/regime/ranking/exit and S7/proactive functions.

The plan is documentation only against Dev `4be033a`; all N0–N4 source work,
data coverage, qualification and promotion remain open. Required docs/source
and primary research reviewed; delivery link/scope/diff checks recorded in the
plan. Dev-local uncommitted documentation, no source/configuration/schema change,
Production access, broker actions, push or deployment in this planning task.
Earlier instructions to await this discussion are superseded by this plan;
older F&O/S6 priorities are historical for this non-F&O development request.

## October 3 — Yahoo interface delivered; historical fidelity limits remain

The owner superseded reliance on Sentinel's retained price history for these
non-F&O tests. [Yahoo plan](2026-10-03-yahoo-all-module-backtest-plan.md),
[usage](YAHOO_BACKTEST_GUIDE.md) and [real results](2026-10-03-yahoo-backtest-results.md)
record the delivered one-script date-argument interface. Native Yahoo OHLCV,
900-day daily warm-up, immutable raw/import/validated archives and current
shipped functions are used. No strategy tuning or F&O/broker/Production path.
70 focused tests passed; final offline repeats and documentation/atlas checks
are recorded with the source commit receipt.
Source/research commit `df0c379` is Dev-local; all 16 repeated outcomes agree,
and immediate documentation/atlas/clean-worktree checks passed.

Q3 daily evaluator outputs are available, including Swing's missing index warm-up.
Yahoo does not supply expired Q3 minute/15-minute history; primaries stay
unavailable and Sep 24–30 studies stay separate. Current Penny finds 18 closes
in that partial-session sensitivity, with fragile +₹15.18 and negative adverse
fill/winner-exclusion diagnostics. Do not relax entry gates simply to trade more.

Before full-system profit claims, bind real EDGE/Swing/Range execution/exit
lifecycles, live Momentum partial/trail behavior, historical context/admission
and marked shared portfolio equity. Current membership/adjusted prices and
prospective qualification remain limitations. Discuss improvements after the
owner reviews these new Yahoo results. Dev-only artifacts; no promotion.

## October 3 — testing finished; discuss improvements before implementing

The owner's latest request is tests first, improvement discussion afterward.
[Results](2026-10-03-current-system-backtest-results.md) and
[test plan / remaining evidence defects](2026-10-03-current-system-backtest-plan.md)
supersede a claim of complete multi-module profitability testing. All 19 archived
jobs finished, including preserved unavailable/failed attempts; 11 delivered
runs bind current source after the EDGE handle-only cleanup. No strategy tuning.
28 focused tests passed; immutable evidence/source checks, repeat outcomes,
compile/diff and atlas verification passed. Source/research commit `4929bea`;
immediate consistency, deterministic atlas and clean-worktree checks passed.
See [completion receipt](2026-10-03-current-system-test-completion.md).

The quarter is not fully covered. F&O full-policy/exit replay is unavailable;
recorded cash is distinct. Penny has actual historical activity, but complete
minute coverage is 189/6,500 stock-days. Its partial shared-cash sensitivity
locks four unresolved entries and cash-rejects seven candidates. Momentum has
16 later-day fallback closes, so its negative diagnostic cannot estimate live
intraday profitability. Swing lacks index warm-up; EDGE/Range remain evaluators.

Discuss evidence-led priorities with the owner before changing entries/exits:
historical coverage and context; Penny unresolved exits and CNC gate overlap;
EDGE/Range/Swing lifecycle contracts; exact Momentum partial/trail/EOD behavior;
verified executable F&O capture and winner concentration. Normalize mixed UTC/
IST ledger clocks and retain date-only CNC conservatism before broader portfolio
claims; independently normalized actual streams agree on this study's metrics.
No full-system qualification is available. P1/P2/P4 delivered source slices do
not remove P3 historical fidelity or operational acceptance requirements.

Production `044c016` is currently stopped and was only read/copied into Dev.
No restart, Production edit, orders, push or promotion occurred. Test artifacts
and correction are Dev-local; original large snapshots remain locally retained.

## October 3 — P1/P2/P4 delivered; P3 partial evidence boundary remains (Dev only)

P2 now recursively binds local transitive source dependencies in the policy
manifest and exclusively publishes completed snapshot/report artifacts without
an exists/write race. Focused CLI/Lab verification: 26 passed, one existing
httpx deprecation warning. Dev-only; no source data, runtime configuration,
broker, Production, push or deployment action occurred.

The owner approved P1 nominal book allocations: Swing ₹1,000, Penny ₹2,000,
Momentum ₹3,000 and EDGE ₹3,000. Unused allocation may transfer, so the ledger
must protect the account-wide own-cash limit and record book attribution; it
must not turn the four nominal allocations into isolated, stranded pools.

The owner delegated the outstanding contingency decision: P1 uses full bounded
entry exposure + calculated charges + a 1% executable-notional reserve. This
is recorded with P1–P4 contracts, acceptance and rollback in
[the completion slice](2026-10-03-p1-p4-completion-slice.md). P2 source commit
`28876be` is Dev-only; its focused CLI/Lab verification passed (26 passed,
one existing httpx deprecation warning). No source data, runtime configuration,
broker, Production, push or deployment action occurred.

P1 source admission is now shared across Python and Node through the durable
`account_cash_reservations` protocol. Its immediate source acceptance covers
concurrent snapshot overcommitment, visible broker pending-order
de-duplication, ambiguity/partial retention, zero-fill release and exit
exemption. The owner-approved book allocation is recorded as attribution and
the account-wide own-cash invariant supports allowed transfers. Paper
observation and owner-controlled promotion remain required.

P3 now includes a joint Penny MIS/CNC cash reconciler and a declared
`PORTFOLIO_PARTIAL` adapter. It improves shared-cash/fill/exit accounting but
cannot become FULL_PORTFOLIO until the runtime has archived point-in-time
universe, regime, event, broker and scheduler evidence; Momentum, Swing, EDGE
and Range have the same evidence boundary. P4 has an append-only prospective
registry and rejects qualification of this partial scope. Do not bypass that
block or relabel prior/historical date declarations as untouched holdouts.
P1/P3/P4 source commit `919e042` is Dev-local. No push, deployment or
Production runtime action occurred. The native Node SQLite ABI limitation is
recorded in the slice; run its real ledger protocol suite inside the matching
gateway container before paper observation/promotion.

## October 3 — authoritative post-implementation review (Dev only)

[Review, correction slice and follow-up acceptance plan](2026-10-03-post-implementation-independent-review.md)
supersedes the earlier blanket B0-B6 completion claims. The small correction
slice covers order-bound F0 reconciliation, unresolved occupancy, malformed
order-book evidence and truthful report/holdout semantics. No migration/config
change or Production/push/deployment action is authorized by this review.

Remaining implementation order: **P1 F1-B account-wide atomic own-cash admission**
and catastrophe acceptance; **P2 B0/B1 complete manifests and point-in-time
evidence**; **P3 B2/B3/B4 historical lifecycle/portfolio parity**; **P4 B6
prospective holdout and session-block uncertainty**. The linked slice defines
files/contracts, adversarial acceptance and rollout/rollback for each.
B5 remains excluded in the recorded current scope. CNC real-data collection
and Dev release operational acceptance remain pending. Production resumed after
the owner's power cut and reports the older declared engine `044c016`; this
review did not restart it. Final affected regression: 294 passed, two existing
deprecations; atlas/compile/diff checks passed.
Correction source commit `284bb4a` is Dev-local; immediate documentation/plan
consistency and atlas reproducibility passed. The authorized review is complete;
implement P1-P4 only in their defined follow-up slices.
Older receipts below describe delivery at their commit, not current completion
of the full original plan.

## October 3 — B3 evaluator slice delivered: shipped Swing/EDGE daily decision parity (Dev only)

**Problem.** The registered `swing_regime_daily` runner is explicitly a
single-ticker proxy (it substitutes the tested ticker for NIFTY and supplies
neutral market context). `penny_edge_backtest.py` has older hard-coded
thresholds, database and fill assumptions. Neither result may be relabelled as
a replay of the deployed daily decision path.

**Delivered.** Distinct research-only adapters call the shipped Swing evaluator
and EDGE scanner. They freeze current defaults, retain the old proxy adapter's
label, and fail unavailable when index/history evidence is absent. This is an
**EVALUATOR** replay: it reports decisions/candidates and rejects, not a live
portfolio, fill, broker admission or historical breadth/universe reconstruction.

**Files/contracts.** `python-engine/backtest_lab.py` registry/adapter contract;
new pure daily replay helper and unit/differential tests; `backtest_catalogue.py`
family declaration; this plan, the system guide and checklist. Inputs are a
frozen `ohlcv_cache` snapshot with explicit stock and index symbols; all source
reads remain read-only.

**Acceptance completed.** Fixtures call the same shipped functions and prove:
no bar dated D informs a Swing D decision; configured EDGE rank/strength values
reach the exact scanner through a temporary frozen cache; and the catalogue
states evaluator-only scope. Binding found and fixed the RSI-history delta
off-by-one which could abort live Swing scans. No strategy thresholds, capital,
broker, runtime scheduling or Production file changed. Focused verification:
149 passed, one existing httpx deprecation warning.

**Rollout/rollback/remaining work.** Offline Dev tests only; archive manifests
through the existing CLI. Rollback removes only the new research adapters and
does not alter archived runs. Next: B6 held-out reporting, then owner review of
the separately listed live cross-book allocation
decisions. GitHub push/promotion and Production read-only checks remain pending.

## October 3 — B4 evaluator slice delivered: Momentum and Range shipped-policy replays (Dev only)

**Problem.** The existing Momentum 15-minute adapter correctly reuses the
evaluator but models a shadow full-quantity target and has no evidence of the
manual EXEC/admission path. Range Reversion is a pure entry profile reached
through the proactive dispatcher and has no Backtest Lab adapter at all. A
daily Swing result must not be relabelled as Range performance.

**Delivered.** The Momentum replay retains its evaluator scope but defaults to
the shipped `MOM_BASE`; `MOM_RECENCY_5` is explicit research only. The Range
evaluator invokes `range_reversion_entry` on completed point-in-time bars,
records every verdict/reason and reports no P&L. Where
historical manual approval, archived advisory context, broker admission,
reservation or exit evidence is missing, declare it unavailable rather than
construct a counterfactual portfolio. If a pure exact Momentum admission/exit
kernel is already shared by runtime, bind it with parity tests; otherwise
document the boundary and do not claim lifecycle completion.

**Files/contracts.** `range_reversion.py`, its dispatcher call site,
`momentum_replay.py`, Backtest Lab/catalogue, existing B1 data contracts and
focused tests. Frozen snapshots are read-only; no live/order modules may be
called. Update guide/checklist/atlas on source changes.

**Acceptance completed.** Range decisions use only completed, prior-known bars and are
catalogued separately from Swing. Momentum retains its actual evaluator/exit
assumptions and rejects unverifiable interval/context input. Tests prove
decision parity/clock behavior and no adapter can place orders. No settings,
capital policy, Telegram action, broker call, Production edit or deployment.
Focused verification: 70 passed, one existing httpx deprecation warning.

**Rollout/rollback/remaining work.** Dev-only offline tests and archived
manifests. Rollback removes research code only. Next B6 adds holdout/report
requirements. B5 stays excluded by the owner; the unresolved cross-book live
allocation decisions remain owner decisions.

## October 3 — B6 reporting slice delivered: standard reports and date comparison guard (Dev only)

**Problem.** `backtest_cli report` currently only echoes a run's summary;
`compare` checks snapshot/window equality but does not protect an untouched
holdout boundary or explain whether a metric has an adequate equity clock.
This can encourage false comparability and selection leakage.

**Delivered.** A deterministic report formatter over archived Backtest Lab
reports retains policy/code/settings/data manifests,
separate unavailable/evaluator results from cash-return results, show the
metrics actually evidenced (gross/net/costs/exposure/turnover/distributions/
MFE-MAE/holding/drawdown only when present), and label every unavailable field.
adds an archived holdout date declaration with no overlap; comparisons require
identical snapshot, scope and holdout
declaration. Bootstrap uncertainty is allowed only for actual closed-trade
samples and must be deterministically seeded; it is never a profitability or
deployment verdict.

**Files/contracts.** `backtest_cli.py`, a pure reporting helper, CLI tests and
docs/catalogue as needed. Reports remain read-only JSON; secrets stay excluded.
No strategy adapter, broker, cache source, live setting or Production file is
changed.

**Acceptance completed for this slice.** Snapshot/window/scope/date-declaration
compatibility and non-overlap are enforced; missing/invalid equity clocks yield
`null` risk-adjusted fields. Tests cover overlap, incompatible comparison,
deterministic IID uncertainty and unavailable metrics. They do not establish
prospective policy freezing or reject repeated selection/prior holdout use.
New declarations explicitly say `DECLARED_UNVERIFIED`.

**Rollout/rollback/remaining work.** Dev-only generated reports; rollback
removes report helpers without deleting archived reports. The original B0-B6
plan remains incomplete as listed in the authoritative review above.
B5 remains excluded; Production recovery/read-only checks, GitHub push
and promotion remain separate authorized steps.

## October 3 — B0/B2 complete: exact classic Penny CNC Connors paper lifecycle (Dev only)

[B2 CNC slice](2026-10-03-b2-penny-cnc-connors-lifecycle.md).
- **Entry.** The replay reproduces the 09:30 scan with today's in-progress
  candle, rebuilt from minute bars, and calls the real
  `evaluate_connors_entry` with real sizing, caps and executor checks.
- **Exits.** It reproduces the 15:45 `update_daily_positions` tracker
  (stop, T1 50% to breakeven, T2, 15 days), proved equal to the real
  tracker and scanner by parity tests (14 tests).
- **Lab and CLI.** `penny_cnc_connors_lifecycle_1d` and `--strategy cnc`.

Runtime findings, not changed:
- `evaluate_connors_exit` has no caller.
- Live CNC rows have no exit management besides a broker SL-M.
- The 09:30 volume gate compares about 15 minutes of volume with a daily
  median.
- Partial day candles are cached until replaced.
- The entry-day stop uses the pre-entry low.

**Real-data run pending:** Production is stopped.

The CNC paper lifecycle slice is delivered under declared assumptions. The
original full-system plan is incomplete; see the authoritative review above.
B5 is excluded in the current recorded scope; promotion is separate.

## October 3 — F1-A owner rule "no extra margin" enforced at both broker boundaries (Dev only)

[F1-A slice](2026-10-03-f1a-own-cash-no-leverage-guard.md).

**Owner's definition:** invest only one's own money. No leverage, and
losses are bounded by the cash put in.

**What is now enforced (gateway Momentum/Swing EXEC, and Python
Penny/EDGE/F&O live).** Every BUY entry must satisfy:

> full order value ≤ broker `available.cash` − open long cost − pending buys − today's realised loss

- Missing evidence or short positions fail closed. Exits are never checked.
- Before this change, the gateway accepted leveraged MIS buys by comparing
  only the broker's roughly-20% MIS margin.

**Tests.** 58 gateway executor tests and 16 Python F1-A tests. The full
Python suite gave 4733 passed, plus 4 pre-existing baseline failures.

**Owner decisions on book-level over-allocation are listed in the slice.**
F1 is still open beyond this: broker statement authenticity, any short or
multi-leg live path, and catastrophe drills.

## October 3 — F0-R5 implemented in Dev; F0 R1–R5 source work complete

[R5 slice and verification](2026-10-03-fno-f0-r5-occupancy-and-clocks.md).
- **Occupancy at the claim.** The existing single-leg limits (concurrency,
  trades/day, open-premium cap, no-pyramid) and "one DR structure at a time"
  are enforced inside the claim transaction, counting in-flight claims.
- **Clocks after the claim.** Live callers re-check the cutoff and quote/
  chain freshness after the claim. A failure releases the entry auditably
  without dispatch.
- **Proof.** The review's DR race went from 2 open structures to 1.
- **Tests.** 12 new; 865 regression passed, plus the known unrelated
  mark-to-market failure.
- **Harness note.** A pre-existing pytest-asyncio/`asyncio.run` socket
  warning appears under `-W error`.

Remaining after F0:
1. Promote R1–R5 through GitHub.
2. Run the R3 Production SQL check once the stack is back up.
3. Observe paper claims and recoveries.
4. F1 (owner cash-only semantics plus broker margin preflight).
5. B2 CNC Connors adapter, then B0 and B3–B6.

Commit `6d41192` (Dev-local). Dev only, not pushed or deployed.

## October 3 — F0-R4 implemented in Dev (broker payload binding)

[R4 slice and verification](2026-10-03-fno-f0-r4-broker-payload-binding.md).
- **Shared check.** `fno_exit_evidence.derive_exit_facts` is now the single
  interpretation of an exit packet. The live verifier and the shared-risk
  reader both use it; the reader never calls the broker.
- **Binding.** Every open partial's receipt must match its retained packet:
  account, order, symbol, tag, status, quantities and weighted price. It
  must also match the position's immutable entry premium, and recompute its
  charges from the cost snapshot frozen at write time.
- **Fail closed.** Empty or forged payloads, consistent wrong prices, wrong
  costs and missing provenance all deny entry.
- **Proof.** All 15 corruption tests fail on the pre-R4 reader and pass on
  R4.
- **Tests.** 18 new; 781 regression passed, plus the known unrelated
  mark-to-market failure.

Commit `0bc8fa4` (Dev-local). Next: **R5**. Dev only, not pushed or deployed.

## October 3 — F0-R3 implemented in Dev (canonical cash, clock, completed trades)

[R3 slice and verification](2026-10-03-fno-f0-r3-cash-clock-completion.md).
- **One reader.** The shared view and policy read one validated cash
  ledger. `TRADE_PARTIAL` and `TRADE_CLOSED` are each counted once.
- **Fail closed.** Future, naive, non-finite, duplicate-exact and
  unclassified cash all deny entry; the observation clock defaults to the
  wall clock. Settled positions without their exact cash also deny entry.
- **Brakes.** Buckets are bounded by the policy day, and the six-loss pause
  counts completed trades.
- **Manual cash.** A positive manual deposit is never capacity.
- **Legacy rows** (generation 0, or no origin) are reported, not rejected.
- **Probe.** The pre-R3 code allowed the partial-loss and future-masking
  cases and falsely paused on six partial exits; R3 fixes all three.
- **Tests.** 20 new; 727 regression passed, plus the known unrelated
  mark-to-market failure.

Production's stack was found **stopped** at 12:22 IST on October 3; this
task did not touch it. Before promoting R3, run the slice's read-only SQL
check on Production.

Commit `5a3b978` (Dev-local). Next: **R4**, then R5. Dev only, not pushed or deployed.

## October 3 — F0-R2 implemented in Dev (one dispatch owner)

[R2 slice and verification](2026-10-03-fno-f0-r2-dispatch-ownership.md).
- **Claims.** A reservation is now only a receipt.
  `claim_shared_fno_entry_dispatch` re-reads the entry policy and grants
  exactly one `DISPATCHING` owner per reservation. Positions require the
  claim, and a halted retry is denied and released before dispatch.
- **Executor.** It re-reads the final order state after a cancel and returns
  typed outcomes with evidence. Only no-dispatch, explicit 4xx rejection and
  verified zero-fill outcomes release capital. Partial, unknown and
  unrecorded fills keep the full reservation (`UNRESOLVED`) until
  `reconcile_shared_fno_entry_dispatch` is given verified evidence.
- **Broker client.** `place_order` reports `dispatch_certainty`.
- **Tests.** 37 new; 666 F&O/broker/settlement passed, plus the known
  unrelated mark-to-market failure; 118 Penny order-path passed.

Commit `54c500e` (Dev-local). Next: **R3**, then R4 and R5. Dev only, not pushed or deployed.

**Operator note.** After any live F&O entry, check for `UNRESOLVED` or
orphaned `DISPATCHING` rows in `fno_entry_dispatches`
(`SharedFnoRiskView.unresolved_entry_dispatch_count`). They hold capital by
design until reconciled.

## October 3 — F0-R1 implemented in Dev (fee-inclusive exposure)

[R1 slice and verification](2026-10-03-fno-f0-r1-fee-inclusive-exposure.md).
- Single-leg rows freeze `risk_fee_reserve_rupees` from the actual fill and
  quantity; DR uses its frozen `entry_cost_rs`.
- The shared view counts loss plus fee for every OPEN/UNRESOLVED row. A
  partial keeps the full fee; a close hands over to exact ledger cash.
- Unbound fee economics, or a single-leg loss below its premium at risk,
  fail closed. Immutability triggers protect the evidence.
- The review's reproduction now holds capacity at ₹1, where it previously
  leaked ₹51.58.
- Tests: 11 new warnings-fatal; 530 F&O/settlement passed, plus 1
  pre-existing unrelated mark-to-market failure.

Commit `d4fd298` (Dev-local). Next: **R2** (single dispatch owner; halt-safe retry; ambiguous entries keep
capital), then R3–R5. Dev only, not pushed or deployed.

## October 3 — B1/B2 implemented in Dev (current state; read first)

[B1/B2 slice, results and verification](2026-10-03-b1-b2-data-contracts-and-penny-lifecycle.md). The owner directed this
task to treat the F&O half of the October 3 plan as done and to implement
B1/B2. For the record, the [independent F0 review](2026-10-03-fno-f0-independent-review.md)
still lists R1–R5; this slice changed no F&O code.

- **B1 `research_data_contracts.py`.**
  - One interval label per run; other labels are reported and never merged;
    `legacy_unknown` is never usable.
  - IST bar-start clock; an invalid row invalidates its ticker-day.
  - Zero-volume bars are marks, not fills.
  - Coverage statuses: COMPLETE, PARTIAL, INVALID, UNAVAILABLE.
  - The audited calendar has an explicit validity range.
  - Daily bars are point-in-time; suspected corporate actions and
    off-calendar dates are reported, never repaired.
  - Manifests carry hashes; loaders are read-only.
- **B2 `penny_lifecycle_replay.py`.** Replays the exact classic Penny MIS
  lifecycle (scope `LIFECYCLE`):
  - the live completed-bar clock;
  - real `PennyRiskEngine` sizing, the circuit filter, one position per
    ticker and at most 3 MIS positions;
  - executor drift and stop-breach checks;
  - the paper LTP stop or a broker stop, the 14:30 smart-EOD / 30-minute
    time stop, and the 15:00 force close, with no target exit.

  It passed a minute-by-minute parity test against the real
  `PennyScanner._evaluate_ticker_breakout`. It is registered in the Lab as
  `penny_breakout_mis_lifecycle_1m` and available through
  `scripts/run_penny_research.py --strategy lifecycle`.
- **Tests.**
  - B1 + B2 + CLI: 57 passed, warnings-fatal.
  - Broad Penny/Lab/research/calendar selection: 809 passed and 1 skipped;
    its warnings are the known Starlette/HTTPX deprecations.
- **Predeclared runs on Production data (read-only).**
  - Primary (`complete_only`): 3 trades, net +₹31.52; excluding the best
    winner, −₹5.91.
  - Sensitivity (`allow_gaps`): 5 trades, net +₹81.12.

  This shows rare entries and dependence on winners running to the 14:30
  rule. It establishes no profitability, holdout or funding authority.
- **Findings left for the owner.**
  - The classic Penny daily kill switch is never fed by runtime
    settlements, so it is inert.
  - Minute capture stops at about 14:29 after 2026-09-03, which leaves later
    sessions without exit evidence.
  - The bankroll is a fixed setting.
- **Next.**
  - CNC Connors exact adapter, then B3–B6.
  - Point-in-time universe and regime before any `FULL_PORTFOLIO` claim.
  - The F0 R1–R5 items and F1 remain open.

Dev only: implementation commit `9a18445`, local, not pushed or deployed; Production is unchanged at `044c016`.

## October 3 — independent F0 review: acceptance reopened

Read [the independent F0 review](2026-10-03-fno-f0-independent-review.md)
before acting on the earlier completion receipts. Reviewed Dev `2b106f7`;
Production remains `044c016` and lacks the shared-risk module. Existing F0
paper gates and atomic writes are implemented; source acceptance is open.

- R1: preserve fee-inclusive exposure through consumed/open/unresolved/partial
  states, with exact cash conservation across both books.
- R2: one durable dispatch owner, current-policy retry checks and evidence-backed
  handling of ambiguous entry/cancel/partial outcomes; no timeout release.
- R3: canonical partial/terminal cash, aware observation bounds and completed
  trade identity for the existing consecutive-loss brake.
- R4: re-derive retained broker payload facts and bind immutable entry/cost
  economics, beyond checking a digest and consistent scalar arithmetic.
- R5: enforce existing occupancy/premium/daily/no-pyramid limits atomically,
  then refresh real deadlines/freshness after the new admission DB waits.

Two bounded corrections are implemented here: shared read helpers do not
create missing databases, and verified zero-fill recovery retains all exposure
without false unavailability. Three new regressions pass warnings-fatal; final
verification is 114 passed with one existing Starlette warning and normal
exit; compilation/atlas/whitespace checks passed. Commit identity is in the
review. Implementation commit `a3f082f` is Dev-local, with immediate
post-commit source/atlas/docs/plan consistency verified. No schema/configuration
change, push or Production action. B1/B2 remains the next requested phase;
do not carry the superseded F0 source-complete claim into that work.

## October 3 — successor and shipped-module backtesting (current priority)

Start with [the successor inheritance](2026-10-03-successor-inheritance.md) and
[F&O safety / B0–B6 backtest plan](2026-10-03-backtesting-and-fno-safety-plan.md).
**Historical implemented slice — F0-D verified partial-exit residual exposure (October 3, Dev only).**
Problem: the existing, operator-authorised `FNO_LIVE` recovery can record a
broker-verified partial exit and proportionally lower `fno_positions.max_loss_rupees`,
but the shared F&O view currently trusts that scalar without tying it to the
recovery receipt and exact ledger cash. Contract: for every still-open
single-leg position with recovery evidence, validate the ordered filled/residual
quantities, settlement generations, retained `ledger_id`/source/origin cash,
and the pro-rata residual catastrophe loss against immutable initial quantity
and loss. Any missing, stale, duplicate or inconsistent partial evidence makes
new shared-risk admission unavailable; it never fabricates a release. Closed
history is not retroactively repaired, and no partial DR execution mechanism is
invented. Acceptance: a verified partial release exposes only its residual
worst-case cash; tampered/missing recovery or ledger evidence fails closed;
concurrent/restart resolution produces one cash row and one residual state;
unresolved/reserved exposure remains blocked. No signal, sizing, live-entry,
broker call, DR legging or exit authority change. Rollout: Dev tests and
additive read validation only, then local commit/review and paper observation;
rollback reverts the validation, preserving cash/recovery evidence.

Implementation result: residual FNO exposure is accepted only after the
shared view verifies ordered recovery quantities/generations, the unique
source/origin/generation ledger event and pro-rata remaining structural loss.
This covers actual operator-reconciled partial fills without inventing a paper
or DR partial fill path. A scalar/cash/receipt mismatch fails closed. Focused
shared-risk tests: 10 warnings-fatal; shared-risk plus recovery selection: 32
passed with the existing deprecated-ASGI route test deselected; broader F&O
risk/DR/orchestrator coverage: 80 passed normally. Source commit `7b77341`;
Dev only, not pushed or deployed.

**Completed implementation slice — F0-E receipt-backed partial cash integrity
(October 3, Dev only).** Problem: F0-D binds a residual to the identity of a
partial-exit ledger event but does not re-derive that event's P&L from the
retained fill receipt, and its declared entry quantity/loss baselines are not
write-protected. An altered fill price, cash value or baseline could therefore
make an invalid residual appear internally consistent. Contract: the shared
view must verify the canonical broker-evidence digest, filled receipt price and
cost-derived cash against the exact ledger row; `initial_qty`, `initial_lots`
and `initial_max_loss_rupees` become migration-safe immutable baselines once
populated. Any discrepancy denies new entry without changing existing
management, exits, broker calls, signal selection, sizing or thresholds.
Acceptance: real verified partial recovery still exposes its pro-rata residual
and exact cash; altered evidence, fill price, cash, generation or baseline
fails closed; legacy-null baselines can be populated once, while a populated
baseline cannot be rewritten; concurrent/restart recovery continues to yield
one receipt/cash transition. Rollout: additive Dev schema trigger and read
validation, local tests/commit, then GitHub promotion and paper observation.
Rollback: revert only the view validation and trigger migration, retaining all
settlement/recovery evidence. Implementation result: recovery rows now persist
the entry/fill/gross/cost/P&L values calculated in their atomic resolution
transaction, and immutable triggers protect recovery receipts plus populated
quantity/loss baselines. The shared view verifies the receipt hash, arithmetic,
ledger identity/cash, ordered generation and pro-rata residual before it grants
capacity. Existing partial rows lacking the new economic evidence fail closed;
they are never silently backfilled. Focused shared-risk/recovery tests: 32
passed warnings-fatal (two documented non-F0 test exclusions). Broader F&O
admission/lifecycle/DR/orchestrator selection: 150 passed normally; its
warnings-fatal form has one pre-existing socket-lifecycle warning in an
orchestrator timing test after 149 assertions. F0's Dev source contract is
complete pending post-promotion paper admission/recovery observation. F1
remains the separately authorised broker cash/margin preflight before any live
funding. Source commit `a9fef57`; Dev only, not pushed or deployed.

**Completed implementation slice — F0-C shared paper entry-policy receipt (October 3, Dev only).**
Problem: F0-B atomically reserves paper F&O catastrophe cash across the
single-leg and defined-risk books, but the legacy directional kill switches and
drawdown gate do not count defined-risk/partial ledger cash and DR admission
does not consult them. Contracts: add a typed, source-scoped, fail-closed
shared-entry-policy receipt in `fno_shared_risk.py`; derive day/week/month
losses from exact `TRADE_CLOSED` ledger rows (all F&O origins) using explicit
IST event dates, and derive drawdown from the same shared realised equity view.
Both new paper entry paths must consult that same receipt; existing position
management and exits must remain callable during a halt. Do not change signal,
quote, sizing, structural-limit, broker, live-spread, or settlement authority.
Acceptance checks: one DR or partial ledger loss halts either prospective book;
source isolation, malformed/naive clocks and missing required evidence reject
new entries; no halt is introduced for a profitable/within-limit fixture; the
drawdown threshold remains the existing 25% allocation policy; and a halted
tick still manages single-leg/DR exits. Rollout: additive code/tests and paper
receipt only in Dev, then a local commit and GitHub promotion/review before
paper observation; no Production configuration/data/process changes. Rollback:
revert only admission-policy wiring while preserving reservation/ledger
evidence; an emergency entry disable never removes exit authority. Remaining
F0 work after this slice: exact partial-settlement release/restart/race
reconciliation and F1 broker cash/margin preflight. Implementation result:
both paper admissions now read the typed receipt, and reservation re-checks it
inside `BEGIN IMMEDIATE`; exact DR/partial `TRADE_CLOSED` cash is common to
both books, while malformed/naive evidence denies new entries. Existing values
remain 6%/12%/20%, six losses and 25% drawdown—no new restriction was tuned in.
Focused `test_fno_shared_risk.py` plus `test_fno_risk_switches.py` passed 24
warnings-fatal; F&O shared-risk/risk-switch/DR/orchestrator selection passed
79 normally. The corresponding warnings-fatal wider run hit one documented
Windows socket-lifecycle warning after 47 assertions. Implementation commit
`bc666fe`; Dev only, not pushed or deployed.

**F0-A foundation is now in Dev:** `fno_shared_risk.py` provides a fail-closed,
source-scoped view of exact settlement cash plus single-leg/defined-risk
OPEN/UNRESOLVED losses and durable reservations. Its transactionally inserted
reservations cannot expire automatically and one-way resolution needs a receipt.
F0-B now binds both paper entries' fee-inclusive worst-case reservations to
their position insert atomically, preserving feasible fixture admissions while
preventing cross-book double spending. Next, make shared loss/drawdown decisions
apply to both books, then add partial-settlement/restart/race characterization. F1 verifies cash-only broker
margin/legging safety; no live spread authority is implied. Recent positive F&O
results do not prove improvement was caused at September 17 (that is also a
cash-key sample boundary). F0-B source commit: `0ba2d29` (Dev; pushed, not deployed).

Completed: existing Penny minute baseline via new inert Dev CLI; two unavailable
samples retained, valid two-stock August 11–20 diagnostic has 5,774 evaluations
and no entries (profitability unavailable). Small research-only SQLite handle
closure fixes Windows temp cleanup. CLI 4 and replay 11 warnings-fatal; combined
82 passed with one existing dependency warning. Full all-module CLI, provider
history, regime/lifecycle/capital parity are **planned**, not code-complete.
B1 data contracts/B2 classic Penny lifecycle follow F0. R6 operational acceptance
and independently authorized partner qualification/canary remain open.

## October 2 — current F&O profitability request

Read [the assessment and concrete replay/data plan](2026-10-02-fno-profitability-assessment.md).
The Dev-only `scripts/assess_fno_profitability.py` ran against Production
SQLite read-only. Recent linked paper outcomes are +₹10,755.67 single-leg (9)
and +₹3,187.60 spreads (7), but all retained July–October position rows report
-₹18,367.22 / -₹3,721.71 and older cash is not exactly reconciled. This is
operational history, **not a current-policy backtest or funding approval**.
Quote archive directories cover only September 10–October 1; obtain licensed
historical executable quotes/contract masters before implementing a full-policy
chronological replay. Existing constant-IV synthetic backtest is insufficient.
The report specifies source/settings freeze, shared policy parity, missing-data
handling, shared-capital portfolio, cost/fill stress and independent holdout.
No Production edits/restarts, provider calls or live-order authority changes.

## October 2 — release candidate; operational acceptance next (R6)

All review source items R1–R5 are in Dev and pushed. Promote through the GitHub
PR to Production, then perform post-deployment checks (read-only first):

1. Containers healthy; the engine runs startup migrations (additive columns only).
2. Collection runs show `momentum_paper_paths.write` after a paper admission, plus `provider_timing`. Research `runtime_capped` should fall after the screener bulk lane.
3. The scheduler daily summary shows the `elapsed_distribution` for market hours.
4. The gateway backlog `report` is reviewed by the operator; `apply` is run only with separate approval.
5. AI unavailable: alerts arrive with an AI-unavailable banner and paper trading continues; check that no classifier calls happen.
6. Then R6: three representative sessions, five reconciled paths, fresh S6/S7 freezes before future data, and partner qualification plus a delivery canary (separately authorised).

## October 2 review priorities — R1–R3 done; R4–R6 remain

R1 `af6f424`, R2 `dcc2f35`, R3 `1550886` in Dev. Next in priority order:
- R4: S3 CSV archive quota/free-space handling and durable market-hours elapsed distributions.
- R5: S7/S8 source-bound entry/thesis evidence, equity-constrained allocation and complete decision-quality analytics.
- R6: operational acceptance.

Deployment notes:
- Deploy the engine diagnostics allow-list before setting `OPTIONAL_AI_REPORT_DIAGNOSTICS=true` on the agent.
- Running the backlog `apply` against Production needs separate operator approval after reviewing its `report` output.
- Freeze fresh S6 manifests before future data.

## October 2 continuation review — authoritative current status

Start with [the independent S7–S10 review](2026-10-02-s7-s10-independent-review.md).
Its implementation contracts/status supersede historical completion and next-
priority statements below. **Not all remaining work is operational**: S6 spread
is an unbound prototype, and S8 is an initial composer, not complete learning.

Small Dev corrections: S10 original deadline forwarding, dispatch-time budget
and request-local zero retries; S8 ordered cash including earlier admissions
and honest drawdown/coverage; S7 settings/fees freeze; reproduced test-fixture
current-loop dependency removed. Agent 368 warnings-fatal; focused research 28
warnings-fatal; expanded engine 1016 passed with six recorded warnings; Node
health two; Compose eight, rendered 500 MiB. No Production/authority change.
The expanded process hung after its pass summary and was stopped by verified
Dev PID; its clean teardown is not established. Focused runs exited normally.

Next source queue, with files/tests/rollout/rollback in the review:

1. **R1 / S6:** typed DR source/leg/economics/cash and actual freeze binding;
   both single-leg raw provider clocks/tokens and position-economics/cash binding.
   Fix reproduced stale-future, modified-manifest and NaN-cost acceptance
   before research interpretation. Freeze anew, never rewrite old manifests.
2. **R2 / S9:** read-only proposed-action reconciliation report and separately
   reviewed idempotent expiry/resolution migration; preserve rows, verify races,
   no fabricated fills or historical trade-card resend.
3. **R3 / S10:** bounded expiry/source/stage counters, once-only still-valid
   original-alert annotation updates and strict transport/shutdown acceptance.
   Daemon-thread join is not forced socket cancellation.
4. **R4 / S3:** bounded/off-path CSV quota/free-space behavior and durable
   elapsed distributions/market-hours summaries before raw-tail eviction.
5. **R5 / S7–S8:** immutable completed-bar/thesis/eligibility adapters,
   separate realized-equity/correlation capacity research, full unique-opportunity
   learning analytics and genuinely versioned human-reviewed proposals.

After GitHub promotion: S1 keyed cash/schema verification; S2 recovery and three
market sessions; S3 peak-volume/prior-boot logs; S4 five reconciled paths;
S5 frozen future protocol, initial 20-session target with adequate closes/
coverage, authorized qualification and separate delivery canary. S6/S7 need
future paired HOLDOUT review before a paper-policy pilot. Paper remains
autonomous, real-money momentum needs owner EXEC, Jev stays deferred. No fixed
calendar-day promise for tips. This review does not push, deploy or send messages.

## October 2 independent S1–S6 review — active correction slice

See [the independent review](2026-10-02-s1-s6-independent-review.md) for
small correction contracts, verification and larger remaining implementation.
Earlier source-complete receipts do not close S3 crash-fault acceptance, S4
fanout/source-packet binding, S5 qualification/canary or the missing S6
defined-risk experiment and archive/economics binding. No Production mutation,
authority expansion or profitable-strategy claim follows from this review.

S7a (Dev): capital-skipped admissions now get candidate economics and a
passive path, and `momentum_allocation_research.py` replays first-arrival
against equal and risk-proportional allocation on one frozen common book.
1114 selected tests passed. After promotion: freeze a manifest before the
next session and evaluate only holdout batches. S7b is completed below;
the next source priority is the S6 defined-risk experiment.

S7b (Dev): frozen completed-bar continuation and bounded-pullback/no-chase
research is now implemented with new-thesis/state re-entry validation and a
bounded read-only view of existing rejected shadow receipts. Focused
warnings-fatal timing/shadow checks: 18 passed. It has no runtime caller.
Before learning from it, freeze the manifest before a new session and use only
signals after that freeze as HOLDOUT; no result authorizes a change to entry
timing. Next meaningful source work is S6's defined-risk experiment.

S8 initial Dev slice: `daily_decision_quality.py` composes isolated daily
book/policy facts from existing read-only audits and shadow receipts, retaining
partial versus terminal cash and rejected evidence. It is explicitly human
review only. Focused warnings-fatal tests: 2 passed. Future source-complete
sessions and reviewed versioned proposals remain required.

S6 defined-risk prototype exists, with its own max-loss R and entry/exit terms.
Independent review found its packet contents are not bound to economics,
manifest verification is incomplete and NaN costs pass. R1 above is required
source development before using its HOLDOUT labels or paired results.

S9 initial Dev slice: gateway health now labels Telegram bot presence as a
diagnostic rather than a transport-confirmed connection, surfaces any durable
dead-letter backlog, and releases its Python probe timer on every response
path. Penny health separates the legacy completed scan clock from a bounded
attempt/outcome state; operator status uses IST ledger-day attribution and
lists each paper book without folding it into live cash. Focused checks: 2
Node, 14 operator-status and 5 Penny-health tests passed. Remaining S9 work is
operationally sensitive: define a reviewed read-only report and supported
expiry/reconciliation migration for old pending requests, callbacks, unsynced
orders and historical dead letters; then collect fresh slow-provider and
no-trade evidence after GitHub promotion. Never use ad-hoc Production SQL.

S10 first Dev slice: stale, undated and timezone-unverifiable classified
sources are excluded from the optional-AI review context rather than poisoning
the annotation deadline. The source renderer emits an explicit
`NEWS_UNAVAILABLE` exclusion summary; deterministic facts may still receive an
advisory review under `proceed` policy. Fresh sources retain their true
validity. Focused agent/async-queue checks: 55 warnings-fatal passed. Next:
make provider transport/retry consume the task's remaining deadline and
surface completed annotations back to the original operator alert.

S4 runtime wiring (Dev): subscribed paper tickers ride the research
collector's existing first quote request into byte-bound envelopes via one
background writer. The deadline-close policy and per-entry adapter exclusion
correct two blockers. 1091 selected tests passed. No Production environment
change is required. Next: after promotion, verify `momentum_paper_paths`
telemetry and five reconciled lifecycles.

Review response (Dev): S6 partial fees and archive pairing (`ea8695d`), S3
crash-recoverable rotation (`c054bf3`) and the S4 typed byte-bound envelope
(`bfd343d`) are corrected; 1024 selected tests passed. Remaining: S4 fanout
wiring, S3 archive quota/elapsed distributions, S5 qualification/canary, S6
DR experiment and F&O position-economics binding.

Small corrections are implemented in Dev with expanded 948-test regression
and isolated warnings-fatal checks; see the receipt for commands and known
runtime-warning limits. Next development: S4 typed source binding and bounded
fanout capture, S3 rotation-journal recovery, then S6 strict archive/economic
binding and versioned partial fees/DR experiment. Existing qualification still
requires frozen future evidence and authorized canary. Do not relabel missing
source work as a deployed-session-only requirement or edit old freeze manifests.

## October 2 S5 partner research readiness — in progress (Dev)

S5a (partner action clock, commit `f45ce43`) is complete in Dev: persistence
and protection prechecks use the live action clock, so a late-received chain
is no longer misclassified as a future quote. S5b is complete in Dev: the
owner-approved bulk Kite lane admits normal research/F&O/penny/partner requests
ahead of the momentum screener's per-ticker fetches with bounded fairness, and
research observes exact active legs with the future reference before the
optional ladder. Expect the screener to take roughly 10–20% longer; verify it
on deployed sessions (commit `18c7f2a`). S5c is complete in Dev: the read-only
`research_cli partner-delivery-blockers` report explains each candidate's
blockers. S5 source work is complete; the frozen protocol, 20-session holdout,
qualification package and canary need fresh post-promotion sessions. S5c commit:
`89a7595`.

## October 2 S6 exit research — S6a complete; S6b in progress (Dev)

S6b step 1 (done): the live single-leg F&O exit ladder is now the pure
`fno_exit_rules.evaluate_single_leg_exit`, shared by the orchestrator and
research; behaviour proven identical (characterization + 20,000-case
differential; 397 suite tests; commit `02047d4`). Step 2 (done):
`fno_exit_experiment.py` freezes `fno_partial_at_target_v1` or
`fno_confirmed_time_extension_v1` and replays the shared ladder on paired
archive paths. Next operational step: export real single-leg positions as
entries, build packets from the research archive, freeze a candidate before
the next session and evaluate only HOLDOUT positions after R1's binding
correction. The defined-risk spread prototype also requires R1 before review.
S5a–S6a commits are pushed (`19a5471`); the PR toward Production must be
opened on GitHub (no `gh` CLI in this environment).


`momentum_exit_experiment.py` freezes one candidate exit policy before
evaluation and reports paired, cost-stressed, holdout-labelled results against
the live evaluator. No runtime caller; no live or paper exit changed. Next S6
work: once S4 paths are deployed and collecting, freeze
`thesis_confirmed_extension_v1` (and/or `target_hold_trail_v1`) before the
next session, then evaluate only HOLDOUT entries. F&O single-leg and
defined-risk exit experiments need their own path sources and R definitions.
A positive small sample authorizes nothing; promotion is versioned paper-only
management after review. Frozen protocol, 20-session holdout,
qualification package and delivery canary reuse existing tooling and need
fresh post-promotion sessions. See the consolidated plan's S5 slice for the
Production evidence. Production remains untouched.

## October 2 S4 equity-path evidence — Dev complete, operational acceptance open

S4 now provides bounded, additive paper evidence only. Every new opened
admission records immutable v1 entry economics, the explicit fixed configured
paper-pool capital snapshot, and canonical accepted-signal packet bytes with a
SHA-256 receipt. The audit recomputes the digest from stored bytes. Existing
`zero_shares` is retained, with a reason that distinguishes exhausted capital,
risk budget and invalid input. A passive exact-admission-key subscription keeps
original quantity through scale-outs. `record_momentum_paper_path_observations`
accepts caller-supplied provider packet bytes plus provider/receipt clocks only;
it has no network capability. The read-only path adapter validates packet bytes,
exact ticker/key, deadline, clock order and configured gaps before it emits a
study packet. Focused S4 evidence tests: 73 passed; compilation passed.

Dev-only source must be pushed/reviewed through GitHub; Production remains
untouched. Before any deployment/learning conclusion, configure bounded caps,
verify the implemented existing-request passive fanout (without a new provider
request), and collect five fresh reconciled lifecycles. Missing/forged/gapped
paths remain insufficient evidence. No test or deployment proves profitability,
strategy quality, partner qualification or live authority. Next priority is S5
or the separately scoped S10 work, not a silent sizing or exit-policy change.

## October 2 S3 evidence-retention — Dev complete, operational acceptance open

S2 source completion is committed in Dev and must be promoted only through
GitHub; Production remains untouched. Start S3 with an inventory of existing
engine/Compose log retention, CSV evidence rotation, scheduler summaries and
archive/restart behavior. Maintain a plan slice before edits: files/contracts,
peak-session retention calculation, tests, rollout/rollback and no-delete
archive rule. Do not change Production or delete retained evidence. S3 needs
rendered Compose verification, bounded writer/disk-failure behavior and
rotation/restart coverage before any deployment request. The optional AI path
must remain non-blocking when its API is unavailable.

S3 implementation slice (October 2) covered
`docker-compose.yml`, `scripts/verify_compose_logging.py` and its focused
tests. The Python engine currently renders `json-file` `20m x 10` (200 MiB),
below the planned `20m x 25` (500 MiB) retention floor. Raise only that engine
contract, render and validate it without printing environment values, and test
rejection of smaller/malformed policies. Rollback is a GitHub reversion of the
Compose/verifier change; never delete old container logs or research archives.
Effective recreation/free-space verification is an operator deployment step.

Completion: the rendered Python-engine contract is now 500 MiB; session CSV
rotation preserves header/rows and SHA-256 manifest evidence; daily scheduler
rollups retain final outcomes/stage statistics before raw-tail pruning. Verify
deployed free space, preserve prior-boot logs and measure complete-session
volume before claiming operational retention. Do not delete archives during
rollback. Next implementation priority is S4; optional AI remains non-blocking
if its API is unavailable.

## October 2 independent S1/S2 review — completed source correction

Review found small S2 gaps: action time was not refreshed after held-option/DR
reads or at final dispatch, quote-age parsing discarded time-zone offsets, and
the scheduler omitted management observations from its completion log. Correct
these in `fno_orchestrator.py` and `scheduler_setup.py`, with cutoff, hard-flat,
quote-age and replay-clock regressions. Preserve frozen signal evaluation time,
all authority gates and non-cancellable mutations. Verify the affected suite,
compile, regenerate the atlas and review the diff. Dev only; promotion/rollback
through GitHub, no Production edit/restart or migration. The original S2 scope
also includes provider queue priority/fairness, exact-leg management reads and
DB-wait timing; existing exit-before-entry ordering is not shared-queue priority.
These source corrections are now complete; stale-IN_FLIGHT recovery review and
three deployed-session observations remain operational acceptance, not proof of
profitability, partner qualification or deployment.

## October 1 consolidated smart-trader plan — active, planning only

Start with [the consolidated implementation plan](2026-10-01-smart-trader-consolidated-plan.md).
It incorporates September 28–October 1 Production evidence and corrects audit
book/time/count errors. First reproduce/fix defined-risk contract lot identity
and truthful atomic settlement, then bound management reads and action clocks.
Preserve complete equity/research paths, compare entry/exit/allocation policies
on frozen future evidence, and complete the existing partner qualification
workflow. This is a smart-trader roadmap, not a mandate to add entry filters.
Jev is deferred. No implementation, Production change or delivery follows from
this planning update; all development remains in Dev with GitHub promotion.
The September 26 admission/economics tools are deployed in PR #99 and four
fresh momentum closes match cash; older "not deployed" receipts below remain
historical. Full paired paths/held-out review are still required.
S10 now covers frequent AI_REVIEW_EXPIRED: stale/undated classified news can
expire the whole review before submission. Correct sanitized context/expiry,
propagate remaining deadlines and expose valid completed annotations without
changing paper autonomy or owner EXEC. See the plan's reproduced evidence and
regression/rollout contracts; this fix is planned, not implemented.

## October 1 S1 defined-risk contract/settlement correction — Dev complete, pending review

The first implementation slice from the consolidated plan is complete in Dev
only (GitHub review/push pending; not deployed at this receipt). New
defined-risk admissions bind every selected leg to its exact NFO identity and
derive quantity economics from the selected contract lot rather than the
configured fallback. The lifecycle refuses missing/inconsistent/replaced
contracts, leaves legacy rows explicitly unverified, preserves an unpriced
hard-flat as `UNRESOLVED` with no fabricated ledger cash, and blocks another
DR opening while unresolved exposure exists. New priced closes use the named
`ENTRY_MID_EXIT_BID_ASK_V1` policy: mid valuation and executable cash are
separate; the terminal row and uniquely generated ledger event are atomic and
idempotent. `fno_audit_report.py` exposes settled/unresolved/legacy evidence
and model-versus-cash totals without recalculating legacy cash.

Verification: 24 focused warnings-fatal DR/audit tests pass; the surrounding
suite passes 84 with one intentionally deselected timing-sensitive recovery
test and one existing Starlette lifespan deprecation. That recovery test passes
alone but fails only in the grouped run and is outside this slice. Additive database columns only; no config,
broker, entry logic, schedule, owner EXEC, partner authority or Production
change. Next: regenerate/review atlas and documentation, commit the scoped Dev
slice, then use GitHub promotion and inspect real schema/settlement receipts.
Source commit `9e26e1b` is local on `codex/production-correction-hedge-p0`;
it is not pushed or deployed.

## October 2 S2 management-read containment — initial Dev slice

The first S2 sub-slice bounds only cancellable management provider reads:
five seconds for futures/open-exit quotes and ten seconds for an existing DR
snapshot. Tick telemetry now exposes per-read completion, deadline or failure
state plus elapsed/cap seconds. A deadline cancels and joins its read, then
uses existing degraded/unpriced handling; it never wraps broker execution,
cash settlement, admission or a database write. Focused checks pass 34. The
warnings-fatal variant encounters an existing unclosed-socket ResourceWarning
in an unrelated stage-duration test, so it is not a clean warnings-fatal
receipt. Source commit `5ae54a8` is Dev-local, unpushed and not deployed;
complete the remaining S2 clock/priority instrumentation before treating the
slice done.

## October 2 S2 management clocks and timing — partial Dev scope, review corrected

S2 now records provider limiter wait, transport, parsing, attempt/retry data
where the real Kite client provides it; non-production adapters explicitly say
the fine timing is unavailable. It retains exact-leg oldest quote age and
refreshes the real action clock after reads and before entry admission, without
altering supplied replay clocks or completed-bar causality. Exits continue to
precede optional DR entry work, and no provider-rate/concurrency increase was
made. Focused coverage passes 59. Pending work is GitHub promotion and three
complete deployed-session receipts. This historical completion claim is
superseded by the independent review: exact-leg DR reads, queue priority/fairness
and DB-wait/timeout-stage attribution still require development. Source commit
`d2319e2` is local, unpushed and not deployed.

Correction slice verification and remaining acceptance are recorded in
[the independent S1/S2 review](2026-10-02-s1-s2-independent-review.md). Small
clock/age/logging corrections are in Dev; no migration, rate/cadence change,
authority expansion, Production edit or restart. Continue with bounded exact-leg
management and shared-request priority before declaring the full S2 complete.

## September 28 Jev decision-layer proposal — design only

The revised [Jev decision-layer draft](superpowers/specs/2026-09-27-jev-decision-layer-design.md)
proposes one disabled-by-default, shadow-only news-category experiment after
a frozen labelled evaluation contract. It does not authorize classifier
replacement, trade grading, signal filtering, M2/M3 promotion, live orders, or
partner advice. The Word/PDF copies remain the earlier draft until the Markdown
design is approved and regenerated. No Jev implementation or deployment has
been performed.

## September 26 P1 economic binding — corrected in Dev

Follow [the economic-binding correction plan](2026-09-26-economic-binding-correction-plan.md).
Replay quantity, time, price and all recorded exit inputs must match immutable
original admission evidence, not mutable remaining shares. Legacy entries are
unavailable. Next is GitHub-based reviewed deployment, fresh keyed admissions
with snapshots and preserved LTP paths, then a predeclared reconciled sample
review. Independently verify archive provenance; a formatted source hash alone
does not authenticate quotes. Do not expand strategy code or interpret held-out
results until this evidence exists. Partner qualification and an authorized
delivery canary remain separate; no automatic tips/live promotion follows.

## September 25 owner vision — autonomous paper, approved real money

The owner's [adaptive trader roadmap](2026-09-25-adaptive-trader-vision-plan.md)
supersedes any proposed default-veto response to a news-classifier timeout.
Paper momentum remains autonomous under deterministic sizing/exits; optional
AI is an annotation, not trade authority. Every **new real-money momentum
entry** still requires explicit owner EXEC approval and the existing hard
broker/session/risk gates. The strategy objective is proactive discovery,
thesis-based management, upside capture and evidence-led capital allocation,
not merely more entry filters. Start with a paper-only paired exit study and
no automatic live promotion. Partner general ideas remain manual intraday
advice with their own qualification and delivery gates.

## September 25 Production audit response and partner activation

Start with the [September 25 corrected audit response and ordered plan](2026-09-25-production-audit-response-plan.md).
Production merge `f52f4d5c` contains the previous Dev source. Read-only checks
correct the audit's claimed missing paper-admission migration and distinguish
post-close container replacement from unproved log rotation. The saved general
intraday profile and per-index collection attempts exist; general strategy
qualification is still absent, while the 0/7 staging-days gate belongs to a
separate personalized-hedge phase. First preserve release-spanning logs and
verify deployed safety/coverage; then produce predeclared, costed, held-out
general NIFTY/SENSEX research for human review. No advice, order or gate
relaxation follows automatically from this plan or three paper-ledger days.

## September 26 completed Dev slice — momentum-paper decision baseline

The [phase 2 plan](2026-09-26-adaptive-decision-baseline-plan.md) is now
implemented. Future momentum-paper opens persist their exact admission key in
the additive position column, partial/final paper cash retains it as
`origin_ref`, and the new read-only audit refuses ticker/date matching.
Legacy/unlinked evidence remains unavailable. No runtime strategy, authority,
broker, scheduler, AI or partner behavior changed. New audit/lifecycle tests:
9 warnings-fatal; affected momentum surface: 194 passed with one existing
Starlette lifespan deprecation warning.

Source commit `94871f2` is pushed on `codex/production-correction-hedge-p0`;
it is not deployed.

Next: promote through reviewed GitHub flow, then collect new keyed paper
lifecycle records and source-bound LTP packets. Run both audit tools on those
records before beginning the predeclared strategy basket; historical unlinked
rows are not a reason to backfill or infer performance.

## September 26 completed Dev slice — source-bound evidence review

The [Phase 3 evidence-binding slice](2026-09-26-adaptive-evidence-binding-plan.md)
is implemented. It joins a Phase-1 exit study to a Phase-2 paper lifecycle
only through a supplied exact admission key; ticker/time similarity is never a
fallback. It remains read-only and reports missing/duplicate/mismatched keys,
incomplete paths and unreconciled cash explicitly. Phase 1/3 focused checks:
20 passed warnings-fatal; the affected paper/replay surface: 214 passed with
one existing Starlette lifespan warning. No entry, exit, sizing, scheduler,
broker, EXEC, partner or delivery behavior changed.

Source commit `beb7e78` is pushed on `codex/production-correction-hedge-p0`;
it is not deployed.

Next: promote the reviewed evidence instrumentation, preserve fresh keyed
admissions and source-bound LTP paths, then run the Phase 3 review on a
predeclared bounded sample. Any missing path or non-matching lifecycle remains
unavailable. Only after independent future-held-out data exists should the
already-implemented frozen strategy-basket comparison be run; do not invent
or tune a result from the current sample.

## September 25 completed Dev slice — paper-only adaptive exit study

`momentum_exit_study.py` now provides the scoped no-runtime paired study in
[2026-09-25-adaptive-exit-study-plan.md](2026-09-25-adaptive-exit-study-plan.md).
It requires source-bound timezone-aware LTP input, rejects incomplete path
evidence, compares the current evaluator to one target-hold/0.5R-trail policy,
accounts for costs/partials, and cannot claim qualification.  It has no live
monitor, entry, EXEC, broker, database, scheduler or partner-delivery caller.
Focused validation: 13 new tests warnings-fatal; affected momentum surface:
109 passed with one existing Starlette lifespan deprecation warning.

Next only after retained quote packets exist: run the report over a predeclared
bounded set of real momentum-paper entries.  If any path is unavailable, retain
`INSUFFICIENT_EVIDENCE` and improve evidence collection rather than changing an
exit parameter.  Compare future held-out sessions before any human-reviewed
proposal; no study result grants live-exit authority.  Preserve unrelated
unstaged fixtures and independent audit documents.

## September 24 implementation update — P2 F&O audit evidence

The P2 F&O audit/financial-interpretation slice is complete in Dev.
`fno_signals` now records the exact passed-gate prefix and active switch
evidence in additive JSON fields; the stable first-reject reason and all
decision behavior are unchanged.  The new read-only
`fno_audit_report.py --db <existing-db> --date YYYY-MM-DD` groups repeated
leg evaluations into one bar/underlying/direction decision unit, so the 24 Sep
two-bar/six-row pattern cannot be described as six trade opportunities.  It
reports per-source FNO_PAPER/FNO_LIVE partial cash events and closed outcomes
separately, labels isolated costs unavailable, and deliberately issues no
expectancy or qualification verdict.  Legacy rows remain readable but state
that switch/gate evidence was not retained.

Focused report/gate/log/orchestrator/hourly tests passed 84; the broader
F&O/performance/division surface passed 376 (two existing framework warnings).
The retained Production audit has no local SQLite copy, so the historical six
rows cannot be retroactively enriched.  After reviewed promotion, run the
read-only report against a retained database and compare the two decision units
and switch evidence to the log before interpreting a block.  No remaining
source change is currently unblocked in this three-day plan; its remaining
items are production promotion and real-session evidence gates.

## September 24 implementation update — P2 classifier latency containment

The classifier latency correction is complete in Dev. Source analysis showed
that the one-second informational classifier reused the analyst client with
one SDK retry. It now uses a separate MiniMax/OpenAI client configured with
`CLASSIFIER_MAX_RETRIES=0`; all direct/fallback classifier calls select that
client. The analyst review client retains its original retry budget. A
wall-clock regression confirms a timeout failure is one bounded call and
returns `UNKNOWN`; no background or detached retry is introduced. The complete
agent test suite passed 361 tests. AI remains informational/non-authoritative.

Next is the separately scoped P2 F&O signal-row and financial interpretation
review: first inspect retained Production evidence read-only and verify the
actual switch/gate path before changing any code or financial presentation.

## September 24 implementation update — P1 momentum-paper admission evidence

The TATATECH acceptance slice is complete in Dev. The paper book now persists
a bounded, idempotent outcome only after its real decision/transaction:
`opened`, `already_held`, `zero_shares`, `disabled`,
`upstream_deduplicated`, or `transaction_failure`. Repeated accepted signals
are recorded at `main.py`'s alert-dedup boundary, so the paper opener is not
credited with a decision it never received. The table contains an opaque
digest/ticker/outcome/timestamp, not raw strategy payloads. A position insert
rollback cannot be marked opened; reopening a closed position preserves a new
immutable attempt. The paper-only/no-order boundary is unchanged.

Next development is P2 classifier latency diagnosis, only after reproducing
the owned retry/transport tail. Do not change AI authority, paper-entry
authority or schedule cadence from this evidence work.

## September 24 implementation update — P1 F&O tick-tail containment

The F&O tick-tail slice is complete in Dev. Read-only retained Production logs
showed 27 ticks at/over cadence (12 on 23 Sep and 15 on 24 Sep); all had zero
DR opens/exits and the repeatable tail was defined-risk entry preparation. Dev
therefore bounds only the cancellable market-data reads that prepare a new
paper DR entry to a shared 20 seconds. Active DR management, hard-flat
handling, single-leg exits and database admissions are deliberately outside
that deadline. A stalled-read regression proves cancellation is joined, the
skip is explicit and no order is created; F&O/DR/scheduler focused tests pass.

Next operationally, promote only through reviewed GitHub flow and collect
comparable session telemetry using `defined_risk_snapshot`,
`defined_risk_management`, `defined_risk_entry_inputs`,
`defined_risk_entry_admission` and `dr_entry_skip_reason`. Do not change the
90-second cadence to conceal a slow active-exit path. The next Dev slice in
the ordered plan is TATATECH accepted-signal admission evidence.

## September 24 implementation update — P1 research collection deadline

The first P1 collector slice is complete in Dev. Each provider quote operation
is cancellation-bounded by the remaining 48-second tick budget, while the
60-second schedule stays unchanged. Normal, capped and error results plus
their durable collection-run journal now carry cap/elapsed/partial telemetry
and truthful per-index coverage states; the first underlying rotates by UTC
scheduler slot so repeated caps do not starve one index. A stalled NIFTY provider is cancelled
and joined before return; its known active leg and skipped SENSEX coverage are
retained as gaps. Focused tests passed 54 and the complete research surface
passed 62. No Production change or strategy qualification occurred.

Next operationally, observe three logged-in sessions before making cadence or
evidence-quality claims. See [the active plan](2026-09-24-three-day-production-audit-plan.md).

## September 24 implementation update — P0 decision-forensics retention

P0 is complete as a measured no-value-change Dev slice. Read-only Production
inspection confirmed `python-engine` already has a 200 MiB `json-file` cap and
retained 35.897 hours/18.13 MiB at an observed 0.50 MiB/hour; no rotation was
present to justify a speculative Compose increase. Dev now pins that rendered
contract through `scripts/verify_compose_logging.py` and eight focused tests.
It prints no Compose environment values and fails closed on an absent,
malformed or non-`json-file` engine configuration. No Production container was
recreated. The remaining P0 operational acceptance is three logged-in
opening-to-close retrievals after reviewed promotion; see the
[P0 receipt](2026-09-24-three-day-production-audit-plan.md).

## September 24 three-day Production audit reconciliation

The 22–24 September deep audits were cross-checked against Production evidence
and current Dev source. The new [audit reconciliation and ordered plan](2026-09-24-three-day-production-audit-plan.md)
corrects several auditor inferences and identifies a confirmed research
collector cap/telemetry defect. It supersedes the September 24 release-slice
statement that no unblocked product-code issue remained: that statement was
correct for the six release gates, but the later Production audit exposed a
separate collection defect. Do not lengthen research/F&O schedules or change
paper/AI authority solely from the audit's recommendation. Production remains
read-only and no new Dev application change is implemented by this plan.

The user additionally queued three Dev slices in that document. The
full-session `python-engine` Compose-retention, research-collection deadline,
F&O tick-tail containment and TATATECH momentum-paper-admission slices are
complete in Dev. None is authorized for Production by this documentation
update; the next code investigation is the separately scoped P2 classifier
latency reproduction.

## September 24 implementation update — real research package boundary

The next Dev-implementable package boundary after F&O exit recovery is complete:
the bounded operator workflow assembles already replayed, reviewed full-policy
evidence into the existing authorization envelope. It cannot manufacture
evidence or approve/register/deliver advice. The exact contracts, acceptance
checks and rollout boundary are in
[the real-research package slice](2026-09-24-real-research-package-plan.md).
Real completed-bar/active-leg collection, future held-out evidence and an
operator review remain operational prerequisites, not test-fixture substitutes.

## September 24 implementation update — Dev release acceptance

Dev-side release acceptance is now recorded, including the repair for a
post-Jest background holiday-refresh log. The compatible Node 20 gateway
receipt naturally exits zero (461 passed / 4 skipped), scripts pass 226,
agent tests pass 357, and dashboard tests/build pass (46 / build). The full
engine process remains an environment-limited non-receipt because its
aiosqlite-worker teardown did not terminate; do not call it green. The exact
commands, boundary and source contract are in
[the release-acceptance slice](2026-09-24-dev-release-acceptance-plan.md).
This is Dev evidence only: it does not merge, deploy, qualify advice or send
Telegram/broker traffic.

### Remaining-gate classification

There is no further unblocked product-development task in the current release
slice. The clean full-engine process exit is a test-runtime/CI follow-up, not
an application-behaviour change: prior full receipts completed assertions but
retained aiosqlite workers. Diagnose only from a minimal reproducer; do not
weaken warnings, force an exit, or add broad shutdown code speculatively. The
other outstanding gates—GitHub promotion/release identity, session evidence,
real broker reconciliation, held-out research, saved profile/review and an
authorized Telegram canary—are operational or evidence tasks. See the
[acceptance receipt](2026-09-24-dev-release-acceptance-plan.md).

## September 24 implementation update — F&O exit recovery

Item 3 of the September 23 next-agent order is implemented in Dev for same-day
`FNO_LIVE` terminal zero, partial and full exits. The authenticated operator
route verifies the current broker order, executions and net position, retains
the bounded source snapshot, and atomically resolves the intent with a ledger
entry for actual fills. Ambiguous, older, unaccounted concurrent orders and
broker read failures remain blocked. Partial economics and residual risk carry
through the eventual final close. See
[the active recovery slice](2026-09-23-fno-exit-recovery-plan.md) for exact
tests, migration and rollout status. Production HEAD `782bbb7` contains the
earlier handover commit `f0e23b4`; this new recovery source is Dev only until
GitHub promotion. Items 1, 2 and 4–6 still require their own evidence/work.

## Current handover — September 23 remediation completion

Start with [the independent review and next-agent execution order](2026-09-21-independent-remediation-review.md).
This supersedes earlier claims that A1–A6 helper tests alone completed integration.
The corrected Dev implementation and tests are ready for review; actual deployed
identity, inputs and partner qualification must be checked separately.

Remaining priorities: (1) GitHub promotion and stamped-release verification with
backups; (2) real-session readiness/coverage/contention evidence; (3) authenticated
F&O ambiguous/partial/zero-fill recovery workflow before live single-leg activation;
(4) real source activation and held-out per-index research; (5) explicit profile,
reviewed qualification and authorized Telegram canary; (6) broker reconciliation
and Production dashboard scope verification. Do not loosen gates to produce tips.
Never erase an unresolved exit intent to force a retry. No guarantee of profitability.

## September 20 Workflow I.4.D provenance correction (Dev only)

Classification is now bound to the exact feed snapshot shown to the verdict
model. The requested ticker, bounded source URL/name, aware publication clock
and source digest survive in each result; invalid source evidence fails closed
without a model call. HTTP(S)+host validation and a seven-day source-validity
boundary are explicit. Optional-review keys bind the deterministic
classification-context digest when the feature is enabled and preserve the
legacy key when disabled; the queue also rejects context-mismatched cache hits
for direct callers. Typed reviews retain digest/count/structured source
references and actual expiry on available, unavailable and worker-exception
paths. Synchronous late results are discarded as unavailable; cached repeats
can shorten but cannot extend validity. Focused warning-fatal acceptance is
**185 passed**, full isolated agent is **357 passed**, compilation/diff checks
pass, and the atlas remains **203
modules** after regeneration. No schema/config default/authority/trading
behavior changed. Production evidence is still required; I.4.G remains
deferred. See the
[active plan](2026-09-20-i4d-classification-provenance-plan.md).
Implementation commit: **`3495ecb`**; promotion remains GitHub-only.

## September 19 Workflow I usefulness-contract correction (Dev only)

The optional-AI status bridge no longer rejects the real ten-field usefulness
snapshot while accepting only reduced test doubles. Engine validation now
covers all producer fields and their internal counter/rate consistency; the
agent's hourly contract-health check uses the real status shape and actually
runs its leakage/usefulness invariants. The dashboard renders p95 response time
and last completion without converting absent legacy fields to zero. No schema,
flag-default, authority, delivery, risk, capital, strategy, or order behavior
changes. Focused engine is **72 passed** with four known deprecations, full
agent is **340 passed** warning-fatal, and dashboard is **46 passed** plus build.
Whole-engine validation is **4,117 passed/four skipped/46 known deprecations**;
implementation commit `8dd2c41` was consistency-checked and pushed to
`origin/codex/production-correction-hedge-p0`. Real
Production observations and operator-labelled usefulness remain required;
per-ticker I.4.G is still deferred. See the
[active plan](2026-09-19-workflow-i-usefulness-contract-plan.md).
This correction supersedes the historical six-field I.A allow-list wording in
the long-form state table below; the current authoritative contract has ten
fields.

## September 19 Workflow C.C2.SOURCE completion (Dev only)

The remaining causal-pricing defect in the modeled-partial path is corrected:
every modeled leg is bound to its own verified asymmetric quote packet rather
than priced from the earlier decision book. Missing legacy source projections
now return `INSUFFICIENT_EVIDENCE / partial_fill_model_unavailable`, and
held-out admission independently cross-checks source attribution and recomputes
the model. Focused acceptance is **87 passed** with warnings fatal; broader C
coverage is **259 passed**; whole-engine acceptance is **4,070 passed/four
skipped/42 known deprecations**. Genuine retained sessions, adequate predeclared
holdout coverage, human qualification and release/Production observation are
still required. Details are in the
[completed slice](2026-09-19-workflow-c-asymmetric-source-binding-plan.md).
Implementation commit `e2212cb` and verification receipt `1a97932` were pushed
to `origin/codex/production-correction-hedge-p0`. Production is unchanged.

## September 19 Workflow C.C2.HOLDOUT completion (Dev only)

`C.C2.HOLDOUT` closes the modeled-partial review seam. The evaluator now emits
a separately identified `MODELED_PARTIAL_FILL_V1` replay, and held-out/review
outputs split `full_closes` from `modeled_partial_closes`. Adverse mid-plus-2bps
entry slippage is non-positive; a degenerate missing-leg quote fails closed.
Modeled outcomes remain outside `VERIFIED_FULL_POLICY_REPORTS` until honest
cost-stress and archived-public-scope evidence exists. Verification: 90
focused, 134 broader qualification/held-out, 226 Workflow C/research, and
4,069 whole-engine tests passed; four skipped and 42 known deprecations in the
whole run. Details and remaining runtime evidence are in
[the completed slice](2026-09-19-workflow-c-partial-holdout-plan.md).
Production is read-only.

## 1. Mission, scope and non-negotiable user intent

September16 square-off acceptance update: pushed Dev commit `ee0a300` moves live momentum EOD ownership to 15:13 IST with a strict 15:14:30 submission cutoff and one shared monitor/EOD lock. Deadline expiry after protective-stop cancellation re-arms and persists replacement protection when possible and always escalates; no late sell is submitted. Focused momentum/calendar/lifecycle/surface coverage is green (79 passed), the scheduler/calendar regression subset is green (25 passed), agent is green (338 passed), and final Python is3730 passed/four skipped/42 existing deprecation warnings in214.84s. The completed pytest receipt again retained aiosqlite worker processes; the exact processes were stopped. Merge/release observation remains required before Production acceptance. This removes the identified 15:15 CAS collision in Dev source; it does not supply staging CAS evidence, broker execution verification or partner strategy qualification.

September16 current acceptance override: Dev correction `97e62e7` and receipt `93efbe4` are pushed, while Production is merge `967e07a` with source parent `315fa72`. Production containers are healthy, but `trading_ready=false`/order execution UNVERIFIED. The new partner-card path has zero qualifications, research artifacts and ideas; two observed sessions produced no setup. The independent J correction HMAC-binds eligibility, strictly expires/validates calendars, removes operational-coverage SQLite initialization races and makes SUMMARY verification deterministic without changing JSON output. Final validation: Python 3725 passed/four skipped/42 existing deprecation warnings (complete receipt, but lingering aiosqlite workers prevented natural process teardown); runtime-matching native Node 424 passed/four skipped; dashboard 43 passed plus build; agent 338 passed. Until merged/released/observed, historical J/H/DONE labels below are source-history claims, not operational acceptance. A single paper close of+INR2,194.54 is not repeatable/live expectancy.

September14 overriding acceptance status: external F2–F6/H/I/J source is preserved but F/J complete labels below are not independently accepted. [Independent audit](2026-09-14-external-work-independent-audit.md) identifies writer-contract, account/capital and live session defects requiring correction. G/C predeclared protocol correction is Dev-tested in ten-file acceptance:156 passed/no warnings6.84s using winvenv `-q -W error`. Full-run JUnit `sentinel-g-protocol-reviewed-20260914.xml` records3304 cases, zero failures/errors, four skips,173.475s; pytest teardown remains alive at inspection, so clean process exit/warning count is NOT confirmed. Next: reconcile this protocol commit, correct F3/F4/F5 and fail-closed F6, then execution/calendar defects and independent I review. Real heldout inputs, faithful range semantics, operator risk input, F/D evidence and GitHub release/session observation remain open; no full-goal completion or live promotion inferred.

Current September13 verification: F inventory/provenance corrections, cache integrity and immutable approval-budget/validity source pass full Dev engine **2,703 tests/four skips/23 existing deprecations in126.20s**, receipt `sentinel-fg-provenance-baseline-20260913.xml` in user Temp. F historical warning evidence, genuine G/C predeclared comparisons/approval gates, D release/session proof and other matrix residuals remain unfinished. No deployment or qualification inferred.

Improve Sentinel into an active, intelligent, cost-aware trading system for the owner and a timely intraday NIFTY/SENSEX manual-advisory system for the partner. The owner wants substantial profit and proactive discovery with mitigated risk. Treat that as a product objective, not a guarantee or justification to loosen safeguards. The engineering target is positive, repeatable net expectancy demonstrated with appropriate evidence, reliable execution/management, truthful accounting and bounded losses.

Do not spend another sequence of commits solely making evidence machinery safer without getting to operational collection, research comparisons and useful product outcomes. Each work item below must produce an observable result, with an explicit decision about what to do next. Equally, do not skip missing evidence to claim progress toward income.

The final requested handover wraps the current code and documentation; this plan preserves the broader unfinished mission. Read SYSTEM_GUIDE.md, SYSTEM_CODE_ATLAS.md and HANDOVER_CHECKLIST.md before implementation. Then inspect the actual worktree, branch, open PR and Production status. Historical chat and these documents are pointers, not fresh runtime truth.

## 2. User constraints to carry forward

- Owner capital: about INR 8k now; possible staged increases to INR 20–50k, INR 1 lakh, then INR 5 lakh only after confidence. Do not silently change capital or treat added funds as returns.
- Partner: independent manual intraday trader in NIFTY and SENSEX, prioritizing hedging. No overnight recommendation under the current policy.
- General tips do not require their personal strategy or holdings. Personalized protection does require actual exposure; conditional protection needs explicit assumptions.
- The owner accepts some risk and wants frequent proactive scanning. A trade quota is not a substitute for an edge.
- AI may help; deterministic operation must continue without it. No AI risk override or fabricated qualification.
- Changes belong in Dev. Promotion is through GitHub. No direct Production edits, live order tests or unrequested partner messages.
- Existing intraday profile was previously saved. Revalidate it rather than asking again reflexively. Ask only for genuinely missing operational preferences or credentials, through appropriate secure configuration.

## 3. Starting state

Recent work added full-policy replay, independent public lifecycle events, delayed-entry capital/risk checks, archived public inputs, candidate capture, immutable CLI reports, and pre-decision-book support. Detailed changes and limitations are in the system guide and September 12 progress record.

Last inspected Production archive had quote journals and masters but zero captured public-input files. At that inspection the application containers were stopped. Do not assume this remains true or that restarting is authorized by a research task. The new Dev commits had not been deployed by this work.

No qualified NIFTY/SENSEX strategy or reliable date for partner tips has been established. The current report functions intentionally return no qualification/delivery/order authority. General Telegram connectivity can be tested separately with an explicitly authorized TEST message; that does not qualify trading advice.

## 4. First working session: establish a reproducible baseline

1. Read git status, current branch, last commits and remote tracking. Preserve untracked audits, evidence and unrelated edits. Do not squash earlier commits without authorization.
2. Read HANDOVER_CHECKLIST.md and rerun only checks invalidated by current changes/environment.
3. Inspect Production containers, release identity and archive root read-only. Record time, SHA, source paths and limitations. Do not print `.env` or tokens.
4. Locate current profile, qualification records, readiness reasons and per-index data timestamps using authenticated/read-only surfaces. Explain each missing gate in plain language.
5. Write the active plan slice with IDs from this document, success conditions and a bounded acceptance procedure. Begin the highest-priority unblocked slice.

Deliverable: an updated state table separating Dev-tested, release-tested, deployed, input-ready, strategy-qualified and delivery-tested. A single green label is insufficient.

## 5. Workstream A — finish causal acquisition and decision timing

**Priority:** P0 for usable research. **Files:** `fno_signal_scan.py`, `partner_orchestrator.py`, `partner_qualification.py`, `partner_research_capture.py`, `partner_full_policy_replay.py`, `research_cli.py`.

Problem: the original tick clock precedes network acquisition. Newly captured candidate receipts honestly occur later, so feeding them back at the old clock is correctly rejected. Merely setting a replay timestamp later can change bar eligibility/strategy meaning and must not masquerade as the original decision.

Implementation:

1. Define explicit tick-start, public-response receipt, chain-response receipt, evaluation cutoff, candidate construction and dispatch clocks. Use injected clocks in tests.
2. Choose and document the deployed policy: either evaluate on a declared frozen completed-bar cutoff with later availability, or recompute at a genuine post-acquisition decision clock. Do not silently mix both.
3. Carry the chosen clocks and source IDs into the captured bundle and frozen decision manifest. Bind candidate and public captures to the same decision/run/account/index.
4. Ensure crossing a five-minute boundary, entry cutoff or session boundary during a fetch cannot create a backdated idea.
5. Keep final dispatch revalidation independent: source availability does not grant transport authority.

Acceptance: reproduce an actual delayed-fetch case without timestamp fabrication; delayed source past entry deadline yields no advice; identical frozen inputs reproduce identity; a newly eligible bar has an explicit new decision. Quote provider timestamps remain untouched. Test both indices and timezone-aware UTC/IST input.

Expected benefit: collected sessions become replayable and recommendations use genuinely available inputs. Risk: changing clocks can alter signal frequency/identity. Version the policy and invalidate incompatible prior qualifications. Retain old captures and migration notes.

## 6. Workstream B — complete collection coverage, not just valid files

**Priority:** P0. **Files:** archive/capture/quote collector/leg subscription modules, scheduler telemetry, ops readiness routes and dashboard hooks.

1. Persist per-attempt records with expected schedule/cutoff, index, source, requested/received contracts, completion/error and references to immutable artifacts.
2. Record public and candidate capture outcomes independently, including no-setup, missing-chain, disk-full, busy writer and malformed packet cases.
3. Preserve all selected legs through the advice lifecycle and management horizon. Verify shared-token accounting, terminal registrations, restarts and expiry changes.
4. Compute session completeness from expected market-aware intervals and retained attempt records. Distinguish never attempted, attempted unavailable, partial, stale, and complete. A directory containing valid files alone is not sufficient.
5. Track quote and public-event gaps independently. Avoid pretending a stop between unobserved samples has a known fill.
6. Finish conditional-protection input capture and declare whether it can use the same replay schema or needs a separate evaluator.
7. Bound disk work. Current `to_thread` avoids event-loop blocking but awaiting it can still delay the advisory job. Introduce a bounded queue only with saturation/drop evidence, cancellation semantics and restart tests; never spawn unlimited writes.

Acceptance: interrupted/restarted session reports gaps; one index failure does not erase the other; missing selected leg prevents complete replay; archive budget failure remains observable while public updates continue; no operational cash or position mutation occurs. Review retention cleanup so capture files and referenced masters outlive qualification review.

Expected benefit: usable evidence and an honest explanation of why qualification is pending. Dependency: A's clock contract. Failure mode: collecting everything without a storage budget creates contention; measure overhead at representative load before release.

## 7. Workstream C — replay fidelity and review integration

**Priority:** P0 before qualification. **Files:** all `intraday_spread_*`, `partner_full_policy_replay.py`, `partner_qualification_review.py`, CLI and tests.

1. Verify public-source scope includes the intended underlying/futures contract and relevant roll/expiry context, not only a name string.
2. Bind raw/canonical master, candidate chain, public inputs, selected contracts, code/config/profile and cost schedule to immutable evidence IDs.
3. Review delayed execution beyond capital/risk: price spread limits, liquidity, current quantity, economic reward/risk, stale public observations and exact expiry boundaries.
4. Validate manual delay and cancellation behavior at entry and exit, including an invalidation on the fill timestamp, no later book, partial book and missed management deadline.
5. Align management deadline/reminder semantics with the deployed policy; do not force a fill at an unavailable exact-minute quote or retroactively close unresolved exposure.
6. Reject conflicting same-receipt quote packets rather than selecting a convenient first packet. Include failure evidence in the report.
7. Freeze review criteria before held-out sessions; connect full-policy outcomes to review without replacing the full evaluator with `orb_threshold_v1`.
8. Preserve zero-opportunity days, no-fills, unresolved exposure and rejected candidates. Account for overlapping ideas and repeated evaluations so sample size means independent opportunities.

Acceptance: unmocked multi-session archive fixture reaches both a costed close and unresolved outcome; tampered sources fail; cost stress uses identical observations; changed policy/profile cannot inherit qualification; complete CLI reports are reproducible and cannot overwrite earlier economics.

Expected benefit: a defensible decision to deliver a specific strategy. It may demonstrate that the current ORB policy lacks an edge; that is useful evidence and should lead to comparison, not suppressed losses.

## 8. Workstream D — release and genuine operational evidence

**Priority:** P0 after the passive collection slice is reviewed. Do not wait for an entire innovation roadmap before deploying useful, tested passive evidence collection.

1. Run full relevant Python acceptance, scheduler/API contracts, gateway native-SQLite-compatible tests, dashboard tests/build and affected agent tests. Record exact command, runtime and failures.
2. Review migrations, defaults, flags and Docker volumes. Establish consistent backup/rollback procedures without deleting data.
3. Prepare a PR describing behavior, tests and remaining operational prerequisites. User authorization is required for actions outside existing scope, including actual partner messages or live canary orders.
4. Promote via the release runbook: reviewed branch/SHA, stamped builds, recreate application services, resolve nginx upstream and verify live fingerprints. Never claim a merge alone deployed new code.
5. Observe one real market session for collection correctness and latency. This session proves operations, not strategy profitability. Fix deterministic gaps promptly.
6. Continue evidence until the predeclared review has an adequate independent sample. Report opportunity count, uncertainty and unresolved risk—not a countdown in arbitrary days.

Acceptance: receipt confirms correct live SHA; per-index inputs and coverage are observable; no unsolicited messages/orders; source and delivery switches match intended rollout. Roll back code only with schema/archive compatibility checked.

## 9. Workstream E — partner product activation and usefulness

**Priority:** P1, prepared in parallel with evidence collection.

Checklist for meaningful delivery: saved intraday profile, current index inputs, valid candidate, genuine compatible qualification, configured destination/token, transport test, final dispatch/session gates. Diagnose each separately. Never require partner positions for a general market setup.

Improve cards around decisions a manual trader can take: index/exchange, timestamp/validity, setup rationale, entry trigger and bounded price, exact contract legs/expiry/lot, total debit and modeled costs, maximum defined loss, invalidation/target and intraday deadline. Explain uncertainty and liquidity limits without overwhelming the message.

Hedge-first must have an explicit interpretation. Conditional protection states the exposure assumption and coverage; market directional spreads are not automatically personalized hedges. Ask for exposure details only if personalized protection is requested. Do not describe an unconfirmed action as taken/closed.

Prioritize invalidation and urgent management above new ideas; suppress overlapping NIFTY/SENSEX directional exposure as appropriate. Keep destination backoff, ambiguity and claim ownership intact. A two-idea cap, if effective, is a maximum rather than a quality target.

Acceptance: representative message previews are understandable, actionable and internally consistent; TEST delivery is distinguishable from advice; duplicate/recovery tests pass; strategy approval is scoped and revocable; every suppressed idea has an operator-visible reason.

Expected benefit: timely usable information, rather than hedge logs/status spam. Outcome evaluation should measure timeliness, executability and costed thesis performance. Partner feedback is helpful but not broker-confirmed P&L.

## 10. Workstream F — trading losses and accounting truth

**Priority:** P1, independent of partner qualification.

1. Reconstruct the previously reported ORB losses from actual entry/exit records, signal input, spread/leg identity, fees and market regime. Separate strategy failure, execution slippage, stale data and accounting defects.
2. Investigate each reconciliation warning with retained ledger/position records and broker statements when supplied. Produce discrepancy IDs and explanations; never mutate books merely to make the dashboard agree.
3. Audit true cost per trade relative to expected edge for INR 8k capital. Prevent a large configured paper bankroll from implying owner live affordability.
4. Audit funding, expenses, partial closes, rejected/cancelled orders and open mark-to-market independently.
5. Establish capital-increase criteria from externally reconciled net results, drawdown, execution quality and operational stability. Leave the user's loss tolerance as an explicit input if not supplied.

Acceptance: per-strategy/mode/account reports reconcile or show precise unresolved differences; deposits are not profit; no forced trade is used to verify a status flag. Expected benefit: stop allocating to misunderstood losses and make future scaling decisions evidence-based.

## 11. Workstream G — strategy basket and entry/exit intelligence

**Priority:** P1/P2 after data/accounting reliability. These are hypotheses, not proven improvements.

Predeclare a small basket rather than searching hundreds of variants until one looks profitable:

| Research hypothesis | Intended condition | Comparison | Main risk |
|---|---|---|---|
| Trend continuation after bounded pullback | Directional session with liquidity | Existing ORB vs pullback entry | Missed strong moves; hindsight support levels |
| Breakout with completed-bar confirmation | Expansion from compression | First break vs confirmation | Worse entry price offsets fewer false breaks |
| Range mean reversion with strict invalidation | Stable range/no expansion | No-trade baseline and existing range logic | Regime shift produces tail losses |
| Cost-aware abstention | Weak edge relative to spread/fees | Same setup before/after cost threshold | Overfitting threshold to recent trades |
| Exit profile comparison | Existing accepted entries | Fixed stop/target vs bounded time/trailing exit | Selecting best exit after seeing the path |
| Exposure-aware allocation | Multiple simultaneous ideas | Independent allocation vs shared risk cap | Correlation estimate unstable on short samples |

Use `proactive_*`, watchlists and run identities to compare candidates without creating an execution consumer implicitly. Freeze training/holdout and cost assumptions. Report net expectancy with uncertainty, drawdown, frequency, turnover, rejected/no-fill count and capacity. Control for repeated trials and overlapping signals.

Acceptance: one retained comparison report can explain why a strategy is promoted, rejected or still uncertain. Promotion to live requires a separate reviewed bridge and risk budget. Expected benefit is improved selection/management; no fixed profit uplift should be predicted without evidence.

## 12. Workstream H — scheduling, provider efficiency and dashboard

Measure p50/p95/p99/max execution time, queue wait, provider calls, cache hits/misses and database/writer contention during market hours. Prioritize order exits and public advice management, then candidate scans, then research. Cache only with explicit instrument, interval, completed-bar cutoff and freshness semantics.

The wrap-up scheduler-closure tests passed but emitted an unawaited `_run_penny_edge_scan_safe` coroutine warning at scheduler_setup.py:594. Determine whether the mocked scheduling path or a runtime rejection path leaks the coroutine, add a warning-sensitive regression, and correct it before describing scheduler validation as warning-free.

Investigate historical zero intraday-cache hit rates: find actual caller/key/window behavior before adding a cache. Do not mix mutable forming bars with completed historical bars or cross-account/exchange tokens.

Dashboard should show effective source/scope/window and readiness reason beside numbers. Distinguish disabled, unconfigured, no session, no setup, no evidence, stale and error. Wire real Production account/run sources rather than replacing unexplained zeros with synthetic results.

Acceptance: lower measured contention without missed exits or lost evidence; mocked slow-provider tests plus retained live-session measurements; UI fixture covers unavailable and zero distinctly. Be precise: reducing a job average does not prove tail latency is controlled.

## 13. Workstream I — optional AI and news

Use AI for bounded annotation: explain a deterministic setup, classify sourced events, summarize risk context, compare research findings and identify missing evidence. Store model/prompt/version, source references, response time and expiry. The typed result must not change capital limits, qualification or order/delivery authority.

Test disabled mode, timeout, stale response, queue saturation, budget exhaustion and restart. Deterministic paths must still operate. News must have publication/event timestamps and a reliable source; an unsupported model statement is not a market fact.

Expected benefit: better explanations and event-awareness. Main risk: plausible but wrong context arriving too late. Evaluate annotation usefulness separately from trading outcome and do not add synchronous model latency to exits.

## 14. Workstream J — CAS and market-session correctness

Read [the CAS inventory](2026-09-12-production-evidence-and-cas-findings.md) and verify current official NSE/BSE/SEBI sources before implementation. September 12 NSE information described cash CAS eligibility and different session timings from continuous cash and equity derivatives.

Inventory hard-coded clocks in market calendars, gateway market-hours, scheduler jobs, bars, expiry/square-off, UI and replay. Introduce an exchange/security/session-phase model only after verifying effective dates and broker behavior. Preserve earlier strategy deadlines unless explicitly revised and qualified.

Do not assume auction imbalance is available in Kite's current feed. Verify actual feed fields/rights first. If unavailable, label that limitation rather than infer imbalance from LTP. Any auction-based strategy is separate research with auction execution semantics, not an extension of a continuous-market fill model.

Acceptance: ordinary days, eligibility differences, holidays, shortened/special sessions and phase transitions have tests. No accidental extension of partner holding horizon. Expected benefit: correct session behavior; an auction profit edge remains hypothetical.

## 15. Suggested order and dependency graph

Start A and B, then finish C. Release a reviewed passive collection slice through D as soon as its operational acceptance is satisfied. Prepare E's message/setup UX in parallel; activate only after compatible qualification. Run F independently because capital truth and losses matter now. Use G to replace an unpromising baseline with tested alternatives. H supports every operational phase. I is optional, and J begins with session correctness before strategy innovation.

Do not claim A–J complete because files exist. Maintain a requirement matrix with statuses: NOT_STARTED, IMPLEMENTING, TESTED_DEV, RELEASE_VALIDATED, DEPLOYED_OBSERVED, EVIDENCE_PENDING, ACCEPTED or REJECTED. Include the precise evidence reference for each status.

### Current requirement matrix — September 12 A/B slice

| Requirement | Status | Evidence | Remaining transition |
|---|---|---|---|
| A — causal acquisition/decision timing | TESTED_DEV | `docs/2026-09-12-clock-and-coverage-plan.md`; focused Python timing/capture/orchestrator tests | Full release acceptance, promotion and one observed session |
| B — per-attempt collection completeness | TESTED_DEV | Archive-local SQLite attempt journal, readiness API/card and restart/partial/unavailable/timeout tests | Production load/retention measurement and observed schedule coverage |
| H — scheduler coroutine warning | TESTED_DEV | 41 scheduler/isolation tests with RuntimeWarning fatal | Release acceptance and deployed scheduler observation |
| C — replay fidelity/review integration | TESTED_DEV | Real evaluator/archive multi-session fixture uses master-proven v3 public futures/roll captures and reaches costed close/unresolved outcomes; conflicts and unrelated packets are distinguished; exact deadlines/strictly-future expiry and delayed liquidity/cancellation/public-age gates are tested; source-bound stress/drawdown and pre-holdout criteria remain enforced; modeled asymmetric legs are bound to their verified source packets and separately identified | Obtain adequate genuine held-out evidence; verify real collection/retention and exchange-specific settlement assumptions during D/J; actual broker fills are not asserted by the modeled-partial research contract |
| D — release/operational evidence | IMPLEMENTING | Baseline: full Python 2,545 passed/3 skipped, scheduler 41 passed, dashboard 25/build, agent 91; resource plan: gateway 324 passed/4 skipped/natural exit, Python warning-fatal 32 and resource-fatal 181; `docs/2026-09-13-consistent-backup-plan.md`: offline verifier/runbook and 117 warning-fatal backup/deployment/migration/journal tests, native dummy-data CLI/tar roundtrip | Actual authorized quiescence/backup/restore and old/new schema compatibility, reviewed GitHub PR/release and real-session observation; currently application containers stopped, not implicitly restarted |
| E — partner activation/usefulness | EVIDENCE_PENDING | Existing profile/delivery gates remain independent | Genuine compatible qualification and authorized transport validation |
| F — trading losses and accounting truth | TESTED_DEV through F.10A; operational evidence still pending | Existing F1-F6 evidence remains in `docs/2026-09-13-workflow-f-state-of-codebase-audit.md` and the independent correction plan. F.10A adds `broker_internal_reconciliation.py`, three durable discrepancy categories, additive CLI/HTTP output and regressions for account binding, statement selection, fill aggregation, both position books, missing/duplicate/paper references, quantity excess and idempotency; see `docs/2026-09-19-f10a-broker-internal-reference-plan.md`. Unsupported sources also fail closed by contract. It never upgrades a reference match into broker reconciliation or authority. Focused: 118 passed; whole engine: 4,090 passed/four skipped. | Obtain genuine broker statements and perform operator review. Full bidirectional economic reconciliation remains blocked on statement period bounds, account-scoped internal books, universal order IDs and richer immutable fill metadata. Signed loss tolerance/capital decision, D release validation and deployed observation remain separate. |
| G — strategy basket and entry/exit intelligence | TESTED_DEV through G.7; pushed, genuine evidence pending | Existing predeclared protocol, exit composition, immutable caches and signed bridge remain documented in the G audit/promotion plans. G.7 makes `RANGE_REVERSION_V1` causal: first completed post-cutoff decision bar, 14 prior bars, execution strictly later, explicit fail-closed outcomes, verifier-derived stop/mean target, and no fallback to generic confirmation. The comparison protocol removes the obsolete alias/forced-uncertain rule but preserves completeness, economics, drawdown, paired uncertainty, immutable implementation identity and all no-authority fields. Focused 81, broader G 222 warning-fatal, and whole engine 4,095/four skipped pass; commits `fefa5a3`/`bc79325` pushed; see `docs/2026-09-19-g7-range-comparison-causality-plan.md`. | Obtain genuine predeclared held-out sessions and F/D evidence. BridgeDecision signing, shared-book capacity, default-v1 migration, release/deployment and strategy qualification remain separate operator/evidence gates. |
| H — scheduling / provider efficiency / dashboard | DONE (H1 scheduler coroutine warning closed and PROD-ready; H2 priority-tier breakdown closed; H3 intraday-cache caller/key/window diagnostic closed `fead40c`; H4 cache-add for ``get_intraday`` closed `d1d6e15` with three operator-tunable knobs honouring §12 four explicit semantics; H4.B by-token cache closed `bfb42ac` extending H4 to the F&O/partner path; H5 dashboard readiness vocabulary closed `b9cfc44` with bounded state->descriptor mapping and self-validation) | H1 — `python-engine/scheduler_setup.py`: ``run_penny_hourly_report_safe`` wrapper + cron re-registered with ``max_instances=1, coalesce=True, misfire_grace_time=600``; ALL_CLOSURES extended. H2 — `python-engine/scheduler_telemetry.py`: `JOB_TIER_MAP` + `TIER_ORDER` + `_tier_for` + `_aggregate_by_tier` + `by_tier` key in `scheduler_timing_report`; `operational_coverage.py` extended with `scheduler_tier:{tier}` entries. H3 — `python-engine/intraday_cache_diagnostic.py`: read-only diagnostic with `CACHED_CALLER_SITES`/`BY_TOKEN_CALLER_SITES` inventories, `cache_row_counts`/`cache_interval_breakdown`/`cache_freshness_window`/`audit_key_shape` queries, `cache_by_token_row_counts`/`cache_by_token_interval_breakdown` for the new table, `run_diagnostic` + CLI; reuses `reconciliation_cli._write_output_atomic`. H4 — `python-engine/kite_client.py:454-575`: explicit §12 four-semantics enforcement in `get_intraday` HIT path (instrument + interval + completed-bar cutoff + freshness); three new operator-tunable knobs in `python-engine/config.py`: `INTRADAY_CACHE_FRESHNESS_SECONDS=0`, `INTRADAY_CACHE_INCLUDE_FORMING=False`, `INTRADAY_CACHE_MIN_CANDLES=4`. H4.B — `python-engine/kite_client.py`: same four semantics extended to `get_intraday_by_token` via shared `_intraday_cache_gate_evaluate` helper; new `intraday_cache_by_token` table; daily interval exempt from forming-bar filter; `_interval_minutes("day") = 1440` (was a latent PROD crash on partner_orchestrator's daily calls). H5 — `python-engine/coverage_vocabulary.py`: seven §12 descriptors (DISABLED/UNCONFIGURED/NO_SESSION/NO_SETUP/NO_EVIDENCE/STALE/ERROR), `STATE_TO_DESCRIPTOR` mapping for the eight states produced by `operational_coverage_report`, `validate_coverage_report` called at end of report; drift attached to report under `vocabulary_drift`, logged at WARNING. 7 + 22 + 26 + 13 + 13 + 22 = 103 new H-series tests pass. whole-engine 3,026 passed/4 skipped/39 warnings (~+22 vs previous 3,004 after H4.B). No regression to the previously closed baseline failures; no new warnings. | H-series complete. Production acceptance remains separate per plan §15 |
| I — optional AI and news | IMPLEMENTING (I1 model/prompt/version provenance + response time closed `4ea9b54`; I2 news provenance — publication timestamps + source URLs closed `33d780c`; I3 usefulness-instrumentation snapshot + bounded CLI closed `f35d859`; I.A bridge I3 usefulness metrics from agent to engine closed `980636e` + `65d4bfe`; I.B surface I1 provenance in operator alert closed `d1e7d4f` + `9bd5286`; I.C operational_coverage_report includes optional AI closed `89a9804` + `c47941e`; I.F cross-container contract test closed `a226ec3` + `0f7120b`; I.4 deep-research proposal closed `aaa15d6`; **I.4.D source-event classification closed `c80e3fa` + `d60073b` + `bc0a0a6` + `557de73`**; **I.4.E bounded contract-health self-evaluation closed (5 invariants: status_envelope_authority, no_prompt_leakage, usefulness_counters_only, classifier_fail_closed, review_non_authoritative) + `evaluate_contract()` aggregate + read-only CLI `tools/contract_health_check.py` with print-config/check/self-check subcommands**; remaining I.4 opportunity G (per-ticker breakdown) explicitly deferred to separate slices after A/B/C/F prove themselves in PROD) | I1 — `agent/advisory.py`: `Review` gains six provenance fields (model/base_url/prompt_version/started_at/completed_at/response_seconds), all default None for backwards compatibility. `agent/agent.py`: `MINIMAX_PROMPT_VERSION` env var (default "v1"); `_attach_provenance` helper using `dataclasses.replace`; every return site of `analyze_with_minimax` wrapped. I2 — `agent/agent.py`: `NewsItem` frozen dataclass with title/source_url/published_at_raw/published_at_parsed/source_name/age_label; `fetch_news_items` returns structured list; `_parse_rss_pubdate` handles RFC 822 and RFC 1123; `_age_label` produces `fresh`/`N hours ago`/`N days ago`/`stale_aged_Nd`/`stale_or_unknown`/`future_dated`; `fetch_rss_feed` legacy string format preserved; `scrape_sentiment` renders structured `[age] (source) title` + `url:` lines. I3 — `agent/async_reviews.py`: bounded counters (`_response_seconds` buffer, `_verdict_counts`, `_cache_hits`, `_cache_misses`, `_circuit_opens`, `_last_response_seconds`, `_last_completed_at`); `submit` tracks cache hits/misses; `_run` captures response_seconds + verdict counts + circuit-open transitions; new `usefulness_snapshot()` returns 10 bounded JSON-serialisable fields. I.A — `agent/agent.py::publish_optional_ai_status` includes `usefulness_snapshot()` in payload; `python-engine/optional_ai_status.py` extends `clean_queue` allow-list; new `usefulness` envelope with bounded field validator; dashboard `OptionalAiEvidence` renders the new fields. I.B — `agent/advisory.py::Review.banner()` renders model + prompt_version + response_seconds when present; backwards-compatible (provenance absent → banner unchanged). I.C — `python-engine/operational_coverage.py` gains `optional_ai` producer with the standard `{state, reason, observed_at, ...}` contract; H5 vocabulary extended to map optional AI states to descriptors. I.F — `python-engine/tests/test_optional_ai_cross_container_contract.py` + `agent/tests/test_optional_ai_cross_container_contract.py` round-trip the bounded envelope and reject unknown keys. I.4 — `docs/2026-09-13-i4-deep-research.md` proposes 7 bounded AI-enrichment opportunities (A–G). I.4.D — `agent/news_classifier.py` pure/total bounded 8-category classifier; `analyze_with_minimax(pre_classifications=None)` with backward-compatible prompt; `_fetch_news_items_for_ticker`/`_maybe_classify_news` env-flagged helpers; operator CLI `agent/tools/news_classify_cli.py` (--ticker/--input/--dry-run/--json); 76 tests (36 module + 10 helper + 9 integration + 21 CLI + 6 async-queue via `inspect.signature` review). I.4.E — `agent/contract_health.py` pure self-evaluation (5 bounded invariants + `evaluate_contract()` aggregate + `ContractReport` with `schema_version="i4e-v1"`); operator CLI `agent/tools/contract_health_check.py` (print-config/check/self-check, read-only, exit 0/1/2); 53 tests pin the contract; agent suite grew 259 → 312 (+53 net). See [I.4.E done-doc](2026-09-14-i4e-contract-health-done.md) |. `agent/optional_ai_metrics.py` NEW: bounded CLI with `print-config` and `read-snapshot` subcommands, documented `CONFIG_CONTRACT`. 15 + 21 + 15 = 51 new tests pass. **I.A** — NEW `_ALLOWED_USEFULNESS_KEYS` / `_ALLOWED_VERDICT_KEYS` allow-lists in `python-engine/optional_ai_status.py` (6 top-level bounded fields + 4 verdict buckets); new `_clean_usefulness(raw)` validator that rejects unknown keys, bad types, bool-for-int, negative numbers, non-dict envelopes. NEW `record_optional_ai_status` integrates the validator: clean usefulness persisted under `detail.usefulness` when envelope present; absent when not. `OPTIONAL_AI_REPORT_USEFULNESS` opt-in env var. `agent/agent.py::publish_optional_ai_status` includes `usefulness_snapshot()` in payload. NEW `tests/test_optional_ai_usefulness_bridge.py` (21 tests across 4 classes: bounded validator / persistence / route surface / bounded contract — explicitly rejects `pitch`/`rationale`/`prompt`/`api_key` leaks). Whole-engine: python-engine 3026 → 3047 (+21); agent 153 → 174 (+21). **I.B** — `agent/advisory.py::Review.banner()` extended with model/prompt_version/response_seconds (1 decimal); backwards-compat substring tests preserved. NEW `tests/test_review_banner_provenance.py` (300 lines, banner-format contract). Whole-engine: 3047 → 3072 (+25); agent 174 unchanged. **I.C** — `python-engine/operational_coverage.py` extended with `optional_ai` producer sourced from `load_optional_ai_status`; H5 `STATE_TO_DESCRIPTOR` mapping extended with optional-AI states (`READY`, `DISABLED_*`, `OUTAGE_CIRCUIT_OPEN`, `UNAVAILABLE`). NEW `tests/test_coverage_vocabulary_optional_ai.py` (140 lines) + `tests/test_operational_coverage_optional_ai.py` (436 lines). Whole-engine: 3072 → 3097 (+25); agent unchanged. **I.F** — Cross-container contract test pins the producer/consumer invariant: a known-bad envelope (leaked prompt, leaked credentials, wrong types) is rejected at the engine boundary; the producer's `usefulness_snapshot()` is bit-shaped-compatible with the consumer's `_clean_usefulness()`. NEW `tests/test_optional_ai_cross_container_contract.py` (488 lines). Plus 4-line optional_ai_status consistency fix. NEW `tests/test_optional_ai_status_usefulness.py` (132 lines) on the agent side. **I.4** — `docs/2026-09-13-i4-deep-research.md` (the research proposal): 7 enrichment opportunities ranked by value/cost; recommended A+B+C+F as the visibility-focused slice (already implemented above); D (source-event classification, the §13 explicit gap), E (periodic self-evaluation), G (per-ticker breakdown) deferred to separate slices after A/B/C/F prove themselves in PROD. **I.4.D** — NEW `agent/news_classifier.py`: bounded source-event classifier against the fixed 8-category taxonomy (`REGULATORY`, `EARNINGS`, `M_AND_A`, `GUIDANCE`, `MACRO`, `RUMOR`, `TECHNICAL`, `UNKNOWN`). `NewsCategory` enum (string-valued); `ClassificationResult` frozen dataclass (ticker, title_hash, category, confidence [0,1], bounded rationale ≤ 280 chars, prompt_version, classified_at). `CONFIDENCE_THRESHOLD = 0.6` (fail-closed: below threshold → UNKNOWN). `CLASSIFIER_TIMEOUT_SEC = 1.0` (per-item latency budget per the deep-research doc). Pure / total: never raises; on timeout / parse error / disabled / model-exception returns `UNKNOWN` with confidence=0.0 and a human-readable rationale. Fixed taxonomy — a category the model invents (outside the enum) is forced to `UNKNOWN`. `DISABLE_CLASSIFIER` env var forces every classification to UNKNOWN (offline / CI / sandbox). `_extract_json_object` parser tolerates `<think>...</think>` blocks (MiniMax-M3 reasoning), `\`\`\`json\`\`\`` fences, leading prose, malformed input. **`c80e3fa`** ships the module + 36 tests (taxonomy, JSON parser, output normaliser, threshold rule, frozen immutability, title hashing, disabled/no-client paths, end-to-end with mock client, batch API, to_dict JSON-safety, config sanity). **`d60073b`** wires `pre_classifications` into `analyze_with_minimax` as an OPTIONAL keyword parameter; the verdict prompt gains a `CLASSIFIED SENTIMENT DATA` section (rendered ABOVE the existing `MULTI-SOURCE SENTIMENT DATA` section) listing `title_hash + category + confidence + rationale` per headline. When `pre_classifications` is None (the default, every existing caller's path), the prompt renders a placeholder text and is byte-identical to its pre-I.4.D shape. The verdict pipeline's existing path is unchanged. **`bc0a0a6`** adds two env-flagged helpers (`_fetch_news_items_for_ticker`, `_maybe_classify_news`) so the operator can flip `ENABLE_NEWS_CLASSIFIER=1` to wire classification into the call sites — the async-queue extension is explicitly deferred (carrying `pre_classifications` through `_Task` is a separate slice). The helpers never raise; the verdict pipeline's failure modes are unchanged. **`557de73`** lands the operator CLI `python -m agent.tools.news_classify_cli --ticker TICKER | --input PATH [--dry-run] [--json] [--limit N]` — runs without touching the verdict pipeline, exits 0/1/2/3 with structured diagnostics. 21 CLI tests pin the contract. Agent suite grew 213 → 253 (+40 across the 4 commits); zero regressions. | Annotations surface in operator dashboards; usefulness evaluation requires operator-supplied ground truth (deferred per plan §13 explicit constraint). I.A/B/C/F and the I.4 deep-research proposal are CLOSED. **I.4.D source-event classification is CLOSED.** Remaining I-series work (opportunities E and G per the I.4 proposal — periodic self-evaluation, per-ticker breakdown) is explicitly deferred — separate slices only after the visibility-focused work proves itself in PROD. |
| J — CAS and market-session correctness | IMPLEMENTING (J.1 classifier closed `d82258f`/`63a98ab`; J.2.1 eligibility list closed `ba117fb`; J.2.2 broker-behaviour probe closed `f6e07da`; J.2 docs sweep closed `211fc58`; J.3.1 probe-quality + classifier `cas_eligible` kwarg closed `6019279`; J.3 capture-review tool + runbook + receipt-directory scaffold closed `9ab8ad1`; J.4 wire `stamp_session_phase` to real classifier closed `cb309a8`; J.5 holiday reconciliation Python↔Node closed `e0061a4` + `c3d1649`; **J.5 holiday divergence actually fixed (Node fallback updated to 20 dates matching Python, drift detector now reports ALIGNED) closed `00dffbd` via independent correction plan `64e22a9`**; J.6 Node sessionPhase mirror closed `1b007c6` + `d5ae6de`; J.7 CAS-aware execution gating closed `cf43df8` + `c0d5c79`; **J.7 CAS-eligibility resolver hardened (Python `routes_market_session.py` is the single authoritative projection; Node `services/cas-eligibility.js` fetches it; `entrySessionVerdict` blocks before broker/DB calls when resolver unavailable) closed `00dffbd`**; J.8 operator dashboard session-phase card closed `6ced829` + `d00f463`; J.9 CAS-aware signal handling closed `e18a160` + `cea1c26`; J.10 CAS-branch reachability gate closed `ba91dcc` + `414207e`; **J.10.CLOSURE operator-facing SUMMARY.md surface closed `c734e4c` + `b8a490e`**; **holiday calendar validity bound (`NSE_HOLIDAYS_VALID_THROUGH = 2026-12-31`, `isHolidayCalendarUsable()` fails closed after that date) closed `fd450a3`**; operator-supplied staging captures still pending for J.10 to flip from UNREACHABLE to REACHABLE) | J.1: `python-engine/market_calendar.py` central constants + 10-phase classifier + `is_cas_eligible` + 41 tests. J.2.1: `CAS_PHASE1_FNO_UNDERLYINGS` env var (CSV) → `is_cas_eligible`. J.2.2: staging-only `tools/j2_cas_probe.py`. J.3.1: probe bumped to `SCHEMA_VERSION: 2` with inline JSON Schema; new flags `--schema-print` / `--eligibility-list` / `--require-eligible` / `--validate`; strict ISO 8601 parser; explicit `cas_eligible: bool | None = None` kwarg on `classify_session_phase`. J.3: NEW `tools/j2_capture_review.py` (six-point checklist + opt-in OHLC-continuity cross-window check); NEW `docs/2026-09-13-j3-capture-protocol.md`; NEW `docs/j2_captures/README.md`. J.4: `python-engine/proactive_intelligence.py::stamp_session_phase` wired to `classify_session_phase` via lazy import. Signature gains three opt-in keyword-only kwargs (`symbol`, `is_derivative`, `cas_eligible`). 17 new J.4 tests across 5 classes. J.5: `python-engine/market_calendar.py` re-verified canonical 20-date NSE Equity 2026 holiday list against NSE source. NEW `python-engine/holiday_drift.py`: pure drift detector (Node source as text + canonical set; reports `ALIGNED` / `DRIFT`). NEW `python-engine/tools/holiday_drift_check.py`: CI/operator CLI (exit 1 on drift). NEW `python-engine/routes_holidays.py`: GET `/holidays` route returning the canonical list; the response now exposes `valid_through: NSE_HOLIDAYS_VALID_THROUGH` so consumers can see when the static set expires. `main.py` wires the new route (1 import + 1 `include_router`; main_surface_golden.json updated for the +1 endpoint). NEW `python-engine/tests/test_holiday_drift.py`: 18 tests — the pre-correction drift signature (Python=20 / Node=18) is documented as historical; the post-correction state (Python=20 / Node=20 / drift=0 / verdict=ALIGNED) is pinned. `node-gateway/server/utils/market-hours.js` rewritten: live `NSE_HOLIDAYS` Set mutated in-place by an engine fetch at boot (5s timeout); `MARKET_HOURS_HOLIDAYS_JSON` env override; **the pre-correction 18-date `NSE_HOLIDAYS_FALLBACK` is replaced by the exact ISO projection of `market_calendar.NSE_HOLIDAYS_STATIC` (20 dates); `isHolidayCalendarUsable()` fails closed after `NSE_HOLIDAYS_VALID_THROUGH = '2026-12-31'`**; `replaceHolidays` records the source validity date so a successful engine refresh can extend the live set's validity. 6 new Node tests in `tests/unit/market-hours.test.js` (was 19, +4 for stale-calendar fail-closed and `isCashCasEligibilityResolutionWindow` → 23 total). Full python-engine suite: **3245 pass / 4 skip / 0 fail** (vs J.4 baseline 3225 / 4 / 1; +20 net, 1 net regression eliminated — the previously-failing surface test was a documented golden refresh). **J.7**: NEW Python `execution_allowed(observation_at, *, symbol, is_derivative, cas_eligible, allow_pre_market) -> {allowed, phase, reason}` in `python-engine/market_calendar.py`. Bit-perfect mirror in Node: `isExecutionAllowed(opts)` in `node-gateway/server/utils/market-hours.js`. Translation table: `CONTINUOUS_TRADING` / `DERIVATIVES_CAS_ALIGNED` -> allowed; `PRE_MARKET` -> blocked unless `allow_pre_market=true`; `CLOSED` / all `CAS_*` / `UNKNOWN` -> blocked. NEW `node-gateway/server/utils/errors.js::CasPhaseError(phase, reason)` (status 422, code `cas_phase_blocked`). Wired into `services/executor.js` (replaces J.6 observability with a hard CAS-aware guard; preserves `MarketClosedError` for the `CLOSED` phase) and `index.js` telegram callback (shows `verdict.reason` for CAS-blocked phases). NEW `python-engine/tests/test_execution_allowed.py` (19 tests across 5 classes: CLOSED/PRE_MARKET, CONTINUOUS_TRADING, CAS sub-windows, DERIVATIVES_CAS_ALIGNED, purity). NEW `python-engine/tests/fixtures/regenerate_execution_allowed_golden.py` produces 3,525 vectors and dual-writes both fixtures. NEW `node-gateway/server/tests/unit/isExecutionAllowed.test.js` (20 tests including the **golden-vector parity test** that asserts zero mismatches across all 3,525 vectors). All 4 existing mocks of `market-hours.js` extended to expose `isExecutionAllowed`. Window boundary correction: the J.6 docs listed CAS sub-window widths that did not match the live Python constants (15:30 -> 15:40 for CAS_MATCHING vs actual 15:30 -> 15:35); J.7 corrects the docs and tests use the actual constants (CAS_REFERENCE_PRICE_WINDOW 15:15-15:20, CAS_ORDER_ENTRY 15:20-15:25, CAS_LIMIT_ENTRY_ONLY 15:25-15:30, CAS_MATCHING 15:30-15:35, CAS_POST cash 15:35-16:00, DERIVATIVES_CAS_ALIGNED 15:30-15:40). Net: Node full suite **380 pass / 4 skip / 0 fail** (was 360/4/0 at J.6 close; +20 new); python-engine full suite **3267 pass / 4 skip / 1 pre-existing failure** (the J.6-documented `test_coverage_vocabulary.py::test_unmapped_state_appears_in_drift` aiosqlite-threading flake, verified zero J.7 imports). **J.7 hardening (independent correction plan)**: NEW `python-engine/routes_market_session.py` exposes `GET /market-session/cas-eligibility?symbol=...` (authenticated via `X-Internal-Secret`, returns `{symbol, cas_eligible, source, source_version}` where `source_version` is a SHA-256 of the configured CSV — no CSV disclosure). NEW `node-gateway/server/services/cas-eligibility.js`: `resolveCasEligibility(symbol, observationAt)` short-circuits outside `isCashCasEligibilityResolutionWindow` (the 15:15-15:29 IST cash-CAS-affected interval) with `{required: false, resolved: true, casEligible: false}`; inside the window it fetches the Python projection with the configured timeout; failures return `{required: true, resolved: false, casEligible: null, reason: ...}`. NEW `entrySessionVerdict(symbol, observationAt)` chains eligibility with the existing `isExecutionAllowed` verdict: an unresolved eligibility returns `{allowed: false, phase: 'CAS_ELIGIBILITY_UNAVAILABLE', reason: ...}`. `services/executor.js` and `index.js` now call `entrySessionVerdict(signalData.ticker, new Date())` BEFORE any DB UPDATE / EXECUTING transition / answerCallbackQuery; a `CAS_ELIGIBILITY_UNAVAILABLE` failure short-circuits execution; operator sees `show_alert: true`. NEW `tests/test_market_session_route.py` (3 tests: 403 without secret, 200 projects config, 200 returns false for unconfigured). NEW `tests/unit/cas-eligibility.test.js` (3 tests: no-fetch outside window, fetch inside window with X-Internal-Secret, fails closed when resolver unavailable). Updated `tests/unit/executor.test.js` (2 new tests: blocks before broker calls, passes actual ticker), `tests/integration/telegram-callbacks.test.js` (1 new test: blocks callback), `tests/integration/approved-snapshot.test.js` (mock added so existing tests reach executor). `utils/errors.js` now exports `CasPhaseError`. **J.10.CLOSURE**: NEW `update_summary(report, summary_path, *, captures_dir=None)` in `python-engine/cas_reachability_gate.py` renders the gate's verdict into a deterministic markdown SUMMARY.md. **Critical bug fix**: `_safe_phase_from_capture` was reading `doc["classifier"]["phase"]` and `doc["phase"]` -- the J.3 schema actually stores the bounded phase at `rows[i].classifier_phase`. The gate now iterates `rows[]` and reads `rows[0].classifier_phase`. NEW `--update-summary` / `--summary-path` flags on `python-engine/tools/cas_reachability_check.py`. NEW auto-update hook on `python-engine/tools/j2_capture_review.py` happy-path: the SUMMARY regenerates automatically when a capture review passes; fail-path leaves the SUMMARY untouched (fail-closed). NEW `python-engine/tests/test_cas_reachability_summary.py` (10 tests) and `python-engine/tests/test_j10_closure_e2e.py` (3 tests); `python-engine/tests/test_cas_reachability_gate.py` fixtures updated to the J.3 schema shape. **J.10.CLOSURE holiday validity**: `python-engine/market_calendar.py::NSE_HOLIDAYS_VALID_THROUGH = '2026-12-31'` is the documented validity period for the static set; `routes_holidays.py` exposes `valid_through` in the response. Net (after independent correction plan): python-engine +19 new tests (5 F6, 7 F3/F4/F5, 3 market-session, 4 holiday_drift updated); Node full suite **394 pass / 4 skip / 0 fail** (was 385 at J.10.CLOSURE close; +9 new); client 40/0/0 (no client changes). | **Operator-supplied staging captures still pending in staging** (CAS broker-behaviour verification). Plan §14: any auction-aware code must pass `tools/cas_reachability_check.py` before shipping -- this is the gate. The J.10.CLOSURE SUMMARY.md surface is the audit trail. `fno_chain.py::EXPIRY_CUTOFF_HOUR/_MIN = 15, 30` and `hedge_strategies.py::_EXPIRY_CUTOFF = time(15, 30)` preserved unchanged. Holiday reconciliation Python↔Node **DONE in J.5 + actually fixed in the independent correction plan (Node fallback aligned to 20 dates, drift=ALIGNED, holiday validity bound fail-closed at 2026-12-31)**; the `NSE_HOLIDAYS_FALLBACK` divergence is no longer a divergent degraded-mode -- it is now the exact ISO projection of the canonical Python set. Node `sessionPhase()` parity mirror **DONE in J.6**; J.7's CAS-aware execution gating **DONE in J.7** (and now hardened by the independent correction plan's authoritative Python projection + Node resolver); J.8's operator dashboard session-phase card **DONE in J.8**; J.9's CAS-aware signal handling **DONE in J.9**; J.10's CAS-branch reachability gate **DONE in J.10**; J.10.CLOSURE's operator-facing SUMMARY.md surface is the last J-series slice -- once operator-supplied staging captures land, the gate flips to REACHABLE and the J-series is operationally closed. |

## 16. Mandatory documentation and plan ritual

September 13 independent F/G audit correction: `2026-09-13-fg-independent-correction-plan.md` supersedes any implication that the whole new bridge/strategy basket is accepted. Atomic terminal-state/append-order fix, faithful trailing composition and immutable exit-cache manifests are tested in Dev. Approval budget/expiry/version checks now require immutable predeclared amount/DD/expiry and retain the original-clock validity window; twelve-file F/G acceptance passes 180 tests with warnings fatal. Reads still report `approval_usable=False`: frozen held-out/account/F/D evidence validation, faithful range semantics and unsupported F schema/provenance/historical closures remain open. External F/G work is preserved. The earlier whole-engine receipt predates cache and budget changes; full rerun remains required.

This is a user requirement for every future agent, including an agent continuing its own work:

1. Before editing, reconcile current state and write/update a plan slice: problem, user impact, affected files, dependencies, assumptions, acceptance tests, rollback and what will remain.
2. During implementation, record material discoveries and revise the plan when scope changes. Do not keep obsolete tasks marked pending or pretend abandoned approaches were implemented.
3. With every implementation commit, update SYSTEM_GUIDE.md for changed behavior and regenerate SYSTEM_CODE_ATLAS.md when files/declarations change. Update the active plan and acceptance evidence in the same commit when practical.
4. Immediately after every commit, inspect the commit/status. Confirm documentation and plan match actual behavior. If documentation was missed, make a prompt docs-only correction before further implementation.
5. Record commit ID, exact verification command/result, environment, migration/config impact, release/deployment status, remaining risks and next action. Never mark Production changed just because Dev was pushed.
6. At every handover, provide a concise current-state ledger and one executable next action. Preserve the whole product objective across context compaction.

Use the following plan slice template:

```text
ID / title:
Problem and user-visible impact:
Current authoritative evidence:
Files and contracts affected:
Implementation steps and dependencies:
Acceptance / negative / restart / timing tests:
Data and configuration migration:
Rollout and rollback:
Status and verified commit:
Documentation updated:
Unresolved limits and exact next action:
```

## 17. Completion and communication rules

A feature is done only when its acceptance conditions are met; a release is done only when promoted and verified; a strategy is qualified only when genuine reviewed evidence supports it. These are different claims.

Report progress as behavior and user value first, then tests and limits. Avoid repeated vague declarations that 'only operational evidence remains' while acquisition, collection or review integration is still unfinished. Avoid predicting a date for tips from the number of elapsed sessions alone. Explain what is missing and what action produces the needed evidence.

The next agent should review the complete Dev release diff/defaults and prepare the GitHub PR, while resolving actual authorized quiescence/backup/restore and previous-code schema compatibility using the consistent-backup plan/runbook. Production application containers were observed stopped; user was asked whether this was deliberate, with no implicit restart. The 17 earlier Python failures and two detected gateway handles are corrected; full baseline acceptance is 2,545 passed/3 skipped. Genuine Production collection and adequate held-out evidence remain required. Preserve the working replay/CLI, legacy-read compatibility and all retained artifacts. Do not restart the architecture from scratch.

## 18. September 20 closeout — AI activation and staging evidence

Status: **IMPLEMENTED_DEV, PUSHED; NOT DEPLOYED**. Source commit `1a6e0d9` is
on `origin/codex/production-correction-hedge-p0`. Detailed plan and Production facts:
`docs/2026-09-20-ai-and-partner-readiness-gap-plan.md`.

Completed in Dev:

- Compose explicitly enables bounded optional-AI annotation, source-event
  classification and usefulness reporting with non-blocking safe policies.
- Manual partner advisory is explicit; advanced hedge shadow observation is
  enabled while Phase-2/3 delivery remains explicitly disabled.
- A staging date is recorded only after genuine reconciled-portfolio and fresh
  option-chain shadow processing. One date is idempotent across repeated ticks.
- The E.1 readiness diagnostic now queries the deployed runtime schemas and
  hardened transport ledger. It no longer mislabels advanced Phase-3 0/7 as a
  blocker for ordinary manual index advice.
- Seven Phase-3 dates, live-chain verification and per-kind sample reviews are
  still required. No threshold was lowered and no delivery/order authority was
  added.

Remaining work is operational/evidence work, not another threshold change:

1. Promote through GitHub and restore healthy Production application services.
2. Verify deployed release/config identities and effective flags.
3. Log in on each intended market day and provide a genuine, fresh reconciled
   partner-position snapshot if advanced personalized hedge staging is wanted.
4. Observe actual shadow receipts/evaluations; perform live-chain and sample
   reviews. Do not backfill missed days from container uptime.
5. Separately complete genuine manual-advisory strategy qualification. The
   advanced hedge 7/7 counter is not that qualification and does not control
   generic NIFTY/SENSEX advisory scanning.

Acceptance receipt: 4,122 Python-engine tests passed/four skipped; 357 agent
tests passed in the built image with networking disabled; 27 corrected E.1
tests passed with warnings fatal; both affected images built; rendered and
runtime Compose flag checks match the safe matrix. Existing deprecation and
Dockerfile casing warnings remain. These checks establish Dev regression
fitness, not deployment, strategy profitability or qualification.

### 2026-09-20 D.3 exact-range correction

The bounded Dev release-note generator now makes `--base-ref` authoritative:
it resolves both endpoints, includes every commit in `base..HEAD` without the
legacy 30-commit cap, reports the exact SHA range/ahead count, and fails closed
on an invalid or unreadable range. Regression coverage includes the observed
31-commit boundary and a valid zero-commit range. D.3 PR preparation is now
truthful at the tooling boundary; reviewer approval, merge, deployment,
backup/restore evidence and Production verification remain operator-owned.

The same acceptance run closed an adjacent F.7 operator-tool defect: text
broker-statement reports now use `INR`, remaining encodable by cp1252 Windows
consoles. The full warning-fatal scripts suite passes 225/225. No calculation,
database, delivery or Production behavior changed.

The operator-ready PR handoff is captured in
`docs/2026-09-20-release-pr-handoff.md` from immutable source head `2766b00`
and base `fef35e7` (32 commits). Because the handoff is itself a final
documentation-only commit, regenerate once immediately before opening the PR;
the exact-range tool makes that final receipt deterministic.

### 2026-09-20 J.6 reproducibility correction

The session-phase golden producer is now byte-reproducible for unchanged
classifier semantics. It preserves provenance time only for an equal semantic
payload, updates it on a real change, writes both consumers from one canonical
string and avoids no-op writes. Focused acceptance: seven Python contract tests
and all 43 Node mirror tests pass. The two already-present local timestamp-only
fixture edits remain deliberately unstaged; a clean checkout running the new
producer will no longer create them.
