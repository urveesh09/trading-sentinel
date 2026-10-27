# Trading Sentinel — system guide and engineering handover

## October 27 — O27b Research genes on the F&O shadow variant and the evolution runner (actual behavior, Dev, freeze `3f97f2c`, results commit `080330d`)

- **`fno_shadow.FnoShadowVariant` gains optional research genes**, each a no-op at its default. `_variant_signal` reads them; no recorded live shadow sets one.
  - Before the break test:
    - `latest_entry_min`;
    - `ema_spans`, which replaces `FNO_EMA_FAST`/`SLOW` for the trend check and its minimum-bar count;
    - `buffer_atr` or `stretch_buffer`, which sets the break level.
  - On a fresh break, `_gene_reject` applies, in order: `vwap_side`, `or_bias` (`with`/`against`: the opening range's last close vs the day's open), `gap_align` (gaps ≥ `GAP_MIN_FRACTION` 0.1%), `max_or_width_ratio` (vs the prior 10 sessions' mean range width) and `narrow_prior_days` (NR-n).
  - Later checks: `min_rvol` replaces `FNO_MIN_RVOL`; `stop_atr_mult` and `target_r` replace `FNO_STOP_ATR_MULT` and `FNO_TARGET_R`.
  - `_prior_sessions(closed, day, or_minutes)` returns the daily OHLC and range width of earlier sessions in the frame. It is cached per frame window, in a module dict cleared at 256 entries.
- **`scripts/run_fno_evolution.py`:**
  - The genome is 17 genes (`GENES`); `SHIPPED` is the live book.
  - `freeze`/`run`. Evaluations are cached under `_local/A` and `_local/FULL`, with the O27 dataset's parse cache under `_local/observations`.
  - `results.json` holds the generation history, every evaluation's fitness, the plateau, the B checks, the holdout metrics and the allele effects.

## October 27 — O27 F&O consistency grid tooling (actual behavior, Dev, freeze `d4cfb7e`, results commit `32f4271`)

- **`fno_shadow.FnoShadowVariant.ema_filter`** (default True): False skips the multi-day EMA(21/50) agreement in `_variant_signal`. Every live shadow keeps True, so recorded rows gain only `"ema_filter": true` in `config_json`.
- **`fno_policy_replay`**:
  - `ReplayPolicy.signal_variant` is a `VARIANTS` name or an `FnoShadowVariant`.
  - `run_replay(root, start=, end=, policy=<name | CURRENT | ReplayPolicy>, data=<ReplayData | None>)`.
  - Still research only, with no runtime caller.
- **`scripts/run_fno_consistency_grid.py`**:
  - `freeze` binds the 361 arms, windows, rule, source and dataset hashes, and the effective `FNO_*` settings hash; `run --jobs N` scores each arm once.
  - `CachedReplayData` pickles parsed sessions under the study's `_local/observations/<manifest>/`.
  - Window metrics: net, net excluding the best winner, max drawdown, CS, per-lot net, green/red days, green weeks.
- The Oct 27 run's results are in `docs/research/fno/2026-10-27-consistency-grid/README.md`. They change no runtime behavior: the paper and live books still run CURRENT.

## October 26 — O26e Terminal pass per saved execution; minute path must be the whole session (actual behavior, commit `1d99c12`, deployed by PR #119 (`3b945eb`, Oct 26))

- **`momentum_shadow`**:
  - `_saved_execution(trade)`, `_time_exit_of(execution)`; `_exit_for_bar` uses the trade's saved `exit_slippage_bps` and time exit;
  - `_terminal_bars(ticker, day, bars, execution)` decides each trade's bars, terminal and derived bar;
  - `cas_time_exit_evidence` requires the declared 15:15 exit.
- **`position_tracker`**:
  - `minute_path(minutes, day_bar, entered_at=)` returns `(path, coverage)` (rules in its docstring; constants `MINUTE_PATH_FIRST` 09:16, `MINUTE_PATH_LAST` 15:25, `MINUTE_PATH_MAX_GAP` 5, `MINUTE_PATH_TOLERANCE` 0.1%);
  - `day_exits` results carry `coverage` and `rule` (`DAY_EXITS_RULE`), and the tracker logs both;
  - the research lifecycle is v3.

## October 26 — O26d Daily exits ordered (minute bars when needed), partner trade evidence and frozen score v2, closing-auction exit on dated evidence, test network guard, F&O pass counter (actual behavior, commit `4205eef`, deployed by PR #119 (`3b945eb`, Oct 26))

- **Production** runs `f9547c5` (PR #118); everything from O26 on is Dev only.
- **`position_tracker.day_exits(status, stop, entry, t1, t2, bar, entered_at=, minutes=)`**:
  - returns `t1` (the half's price), `close` (status, price), `stop` and `basis` (`DAILY`, `DAILY_STOP_FIRST`, `DAILY_ENTRY_DAY` or `MINUTES`);
  - `update_daily_positions` fetches the day's minute bars only when the basis is not `DAILY`; a T1 half and a close on one day are written as two updates;
  - `research_penny_cnc_lifecycle.tracker_step(pos, bar, day, minutes=)` returns its events as a list; the lifecycle is v2.
- **`partner_watch_trips`**:
  - new columns `prior_exit`, `cash`, `opening_order`, `opening_qty`, `opening_value`, `opening_final`, `opening_exact`;
  - `run_pct`, `usual` and `cash` are first known; everything else is rewritten;
  - `paid_share = ROUND(opening_value / first-known cash, 4)`;
  - `_store_trips(..., orders)` reads the opening order's status.
- **`partner_watch_score`**:
  - `SPEC` v2 and `SPEC_ID`; `evidence_of(trip)` gives POSITIVE/NEGATIVE/UNKNOWN per warning;
  - `score` compares POSITIVE with NEGATIVE and counts UNKNOWN; `_side` counts `from_orders`;
  - `partner_watch_report` marks an after-loss buy by the same rule.
- **`momentum_shadow`**:
  - `EXECUTION.cas_time_exit`; `cas_time_exit_evidence(ticker, day)`;
  - the terminal pass sorts bars, derives the 15:15 bar only when that is ELIGIBLE, and otherwise records `no_terminal_bar:cas_<reason>`;
  - the derived bar carries `modelled`; the comparison adds `modelled_time_exit_closes` and `modelled_time_exit_net_pnl`.
- **`market_calendar`**: `CAS_PHASE1_FROM` (2026-08-03), `CAS_PHASE1_UNTIL` (2026-12-07, exclusive), `cas_phase1_in_force(day)`.
- **`research_archive.contract_master_underlyings(root, provider=, segment=, day=)`**: the underlyings with FUT contracts in that day's archived masters, or None.
- **`scheduler_setup`**: a tick that waited for the lock skips when `fno_pass["ticks"]` moved meanwhile (no clock comparison).
- **Tests**: `tests/netguard/sitecustomize.py` blocks non-local lookups and connections (sockets and asyncio) in the test process and in Python children; `SENTINEL_TEST_NETWORK=1` opts out.
- **DAY**: "That includes about ₹X of charges (estimated) on N orders."

## October 26 — O26c Audit fixes: last halt check before a buy, check expiry at send, future clocks, closing-auction time exits, daily stop-first, F&O to 15:39, no network in tests; DAY charges, refusal size (actual behavior, commit `a848bcb`, deployed by PR #119 (`3b945eb`, Oct 26))

- **Production** runs `f9547c5` (PR #118); everything from O26 on is Dev only.
- **`kite_client.place_order`**: after `_own_cash_refusal` and `_reserve_account_cash`, `entry_blocker()` runs again before the POST. A halt then releases the hold (`release_not_sent`, reason `halted_before_dispatch`) and returns its NOT_SENT refusal.
- **`partner_watch._deliver`**: for a CHECK, after the build/claim loop, `_outdated_check(entry, _now())`. Past `valid_until`: `_unmark`, close REFRESHING, `_refresh_later` (log `partner_watch_check_outdated … at_send=1`).
- **`quote_freshness`**: INVALID when the read or the receipt is more than QUOTE_FRESH after `now`; `level_state` then says UNVERIFIED.
- **`momentum_shadow.resolve_momentum_shadow_day`**: no bar at/after 15:15 but the 15:00 bar → `_last_continuous_at_time_exit` adds a 15:15 bar priced at the 15:00 close; a close on it has receipt detail `LAST_CONTINUOUS` (`time_exit_last_continuous`). `momentum_replay._with_last_continuous` does the same for `_simulate`.
- **`position_tracker.update_daily_positions`** (and `research_penny_cnc_lifecycle.tracker_step`): `target1_hit` only while OPEN; a bar touching the stop and a target takes the stop unless it opened at a target (log `daily_bar_stop_and_target_touched`).
- **`scheduler_setup`**: `_fno_open_after_cutoff(nm)`: 15:26–15:39, true while `fast_exit_has_work()` or `fno_dr_book.open_structures` (paper). The regular F&O tick runs then; the fast exit's window is 09:15–15:39 (still work-gated).
- **`tests/conftest.py`**: `socket.getaddrinfo` refuses non-local hosts; `patch_settings` sets fake `TELEGRAM_BOT_TOKEN`, `PARTNER_TELEGRAM_BOT_TOKEN`, chat ids and partner Kite key/secret.
- **Partner messages**:
  - `day_so_far` adds `charges` and `orders`; `day_text` says "That includes ₹X of charges on N orders."
  - `refused_text(row, rows, still_open, cash=, usual=)`: a BUY refused for funds adds its share of the day's cash and the usual share. `_b_refused` gets the usual from `_usual_share(..., before=placed_at)`.

## October 26 — O26b A far bigger buy still warns on a quiet day; the day's trades stored; the check's warnings scored by a frozen rule (actual behavior, commit `cf6befc`, deployed by PR #119 (`3b945eb`, Oct 26))

- **SIZE.** `_deliver`, on muting a PLAN or ADDED for Quiet, calls `_size_through_quiet`. When `size_reasons(kind, context, cash)` finds a size warning, a `size:<message key>` row (kind SIZE) goes to the outbox.
  - The reasons: PLAN's `bought_px × bought`, or ADDED's `held_value`, over `USUAL_SIZE_MULT` × `usual` of the day's cash; or PLAN's `after_loss` with `bigger`.
  - `_b_size` builds it only while the trade is held: `size_text`, the reasons plus `plan_summary`, then `QUIET_SIZE_NOTE`.
  - SIZE is in QUIET_KEEPS and `_QUOTED`; PRIORITY 2; LIFETIME 180 s. `_revise` now takes `trips` and puts `held_value` and `usual` in ADDED's context.
- **`partner_watch_trips`** (key: session_date, position_key). Written by `_store_trips` in `_events` (step 6) for each trip whose signature changed. The signature: bought, sold, buy and sell values, closed_at, exact, the plan's run, the day's cash.
  - `trip_row` gives the fills, `realised`, `orders`, `exact` and `carried`.
  - It also gives the buy-time `run_pct`, `after_loss` (JSON), `usual` and `paid_share` (the opening order's value over the day's cash). These are kept as first known (`_TRIP_UPSERT`, COALESCE).
  - A failed write is logged (`partner_watch_trips_write_failed`) and tried on the next tick.
- **`partner_watch_report`**: `report()` adds `trades` (by day); `day_totals`; `render` lists "Trades <day>" and each trade.
- **`partner_watch_score`** (`load`, `warnings_of`, `score`, `render`; `python -m partner_watch_score [FIRST [LAST]]`). It reads the database read-only, applies the rule frozen in its module docstring (FROZEN_FROM 2026-10-27, MIN_WARNED 20, four checks), and reports checked and unchecked trades apart.

## October 26 — O26 The trade watch's day so far (DAY) and run figures rounded down (actual behavior, commit `6ec5ce1`, deployed by PR #119 (`3b945eb`, Oct 26))

- **DAY** (`partner_watch.day_so_far(trips, cash)`, `day_text`, `_b_day`), from each book read in `_events`:
  - Today's closed trips (`Trip.realised()`, after charges; carried trips left out) are summed. `step` = how many DAY_STEP (0.10) shares of the day's cash (`_state.cash`: opening balance plus intraday pay-in) the loss is.
  - With `step > 0` the outbox gets `day:<day>:<step>` (INSERT OR IGNORE: once a day per step, restart-safe). Only the step reached now is queued.
  - At send time the text is built from the latest view. The step must be exactly the one queued, else `superseded`: back above it, or past the next, whose own message tells it.
  - The text: result and share of the cash (rounded down); trades closed, won and lost; those bought within `partner_coach.REENTRY_WINDOW_MIN` (30) of a losing exit (`_after_loss`) with their sum; trades still open; the check for the latest trade's option (`_check_example`); `DAY_NOTE`.
  - DAY is in QUIET_KEEPS (PRIORITY 2, LIFETIME 600 s). No cash read: no DAY.
- **Run figures** (`_pct_down`): the 15-minute run in the check and the PLAN message is in whole percent rounded down, so a figure shown as 20% always has the check's chased-spike warning (`partner_insights.SPIKE_RUN_PCT`).
- `WATCH_ON_TEXT` and `QUIET_TOAST` name the DAY step.

## October 25 — O25N Once-a-day partner messages: retried only when provably unsent (actual behavior, commit `967c2d6`)

- **`partner_orchestrator.send_daily(db, kind, day, text, now, reply_markup, until)`** is used by the brief, the wrap, the coach note, the review prompt and the 07:00 reminder.
  - Each send is claimed (`<kind>_try`, `<day>:<n>`, with its text and button) before it goes, and settled after.
  - The answers are:
    - `sent`;
    - `failed` (provably unsent, will be retried);
    - `retry_later`;
    - `in_progress` (claimed under 60 s ago);
    - `uncertain` (a timeout after the request left, or a send cut off by a restart: never resent);
    - `refused` (a 4xx);
    - `undelivered` (4 sends, or the window's end);
    - `already_sent`.
  - The day's `(kind, day)` row is written once nothing more will be sent.
- **`partner_daily_retry`** runs every 5 minutes, at :40 seconds. It resends the brief, the wrap, the coach note and the review prompt from the first send's text, with "⏱ Written at HH:MM; it could not be sent then."
  - The waits are 5, 10 and 20 minutes, with 4 sends at most, within 60 minutes of the first send.
  - Nothing happens for a message the job never sent today.
- **The 07:00 reminder** uses the same ledger. Its own tick rebuilds the text and also sends it when the 07:00 run was missed (07:00–08:30).
- **CHECK work-out.** The outdated row stays due as `refreshing` until its replacement is in the outbox. A restart during the work-out works it out again; the replacement's fixed key prevents doubles.

## October 25 — O25M Partner delivery: current prices, verified quote clocks, a safe reminder retry (actual behavior, commit `07e22da`)

- **Quote freshness (`partner_watch.quote_freshness`).** A quote is FRESH only when all of these hold:
  - our read is within QUOTE_FRESH (15 s);
  - the exchange's quote time and our receipt time are both present, readable and zoned;
  - the exchange time is at most QUOTE_CLOCK_SKEW (5 s) after receipt and at most QUOTE_MAX_AGE (15 s) before it.

  Otherwise it is STALE, UNVERIFIED (unknown), INVALID (a future exchange time) or MISSING.
  - Only a FRESH quote checks a level (`level_state`: VALID or CROSSED). Anything else is "check first". UNVERIFIED texts say the time could not be verified and never print a future time.
  - Plans use the option's mid and the future's price only when FRESH, typed price or not. Without a current future, the levels come from the last closed 5-minute bar.
  - The fired-stop alarm says the bid only from a FRESH quote.
- **"check 22300 pe" replies.** The outbox row keeps the request, the exact option and expiry, and `valid_until` (15 s after the prices were read).
  - A reply not sent by then is never sent: the row is closed `outdated`, and the reply is worked out again once for the same option and expiry, beside the sender, saying "Prices read again at …".
  - Otherwise the partner gets a no-numbers note to send the check again.
  - With a typed price and no current quote, the reply says why ("its last price update was 10:50:02, too old to use, so the levels are worked from your price"). It never says "the ask now" or gives a bid-ask gap.
- **The partner's 07:00 reminder.** Each send is claimed in `partner_messages` (`login_reminder_try`, `<day>:<n>`) before it goes, and settled after.
  - A send that provably did not leave (no connection, 429, Telegram 5xx) is retried by `partner_login_reminder_retry`, which runs every 5 minutes. The waits are 5, 10 and 20 minutes, 4 sends at most, and only 07:00–08:30.
  - Nothing is resent after a timeout after the request left, a send cut off by a restart, a 4xx, or a login.
  - The same tick sends a reminder the 07:00 run missed. The day's `login_reminder` row records the result: reminded, uncertain, refused or undelivered.
- **Owner alerts.** `operator_alert_queued` (warning) means the gateway accepted an alert that Telegram did not take on the first try; the gateway keeps retrying it.

## October 25 — O25L independently verified state and remaining partner delivery gaps

Production runs `7468853`, with matching Dev application source and matching installed Mumbai tunnel source. Both application tunnel settings are now applied. The full application runs on the owner's Windows/Docker host; Oracle hosts the routing service. Real trading remains off. Sunday readiness still requires a current owner login, instruments and order-execution verification.

The partner can request a hypothetical nearest-expiry option plan in Telegram with `check 22300 pe` or `check sensex 81000 ce 120 2 lots`. It never records a buy or authorizes/places an order. Actual post-buy monitoring, protection alerts and evening broker-based review are separate. Order-update streaming is implemented but off; price/depth streaming and scored adaptive exit judgments are not active. Production has zero watch-message/quote-path rows, so live watch delivery has not yet been demonstrated.

Three reproduced gaps were in the code reviewed (fixed in Dev by O25M, above; Production keeps them until it is deployed): CHECK is fixed text and can be retried stale; incomplete/future quote clocks pass freshness and a supplied price bypasses stale-input rejection; failed morning reminders are deduplicated as already reminded. These require Dev fixes, not Production edits. The unqualified-card option is currently enabled, so an empty qualification registry alone does not block properly labelled NOT CHECKED cards. [Verified feature inventory, findings, evidence and implementation plan](2026-10-25-independent-production-partner-review.md).

## October 25 — O25k The morning login reminder (actual behavior, commit `1d40091`)

- **Job `premarket_login_nudge`.** Cron LOGIN_REMINDER_HOUR:LOGIN_REMINDER_MINUTE (07:00 IST), misfire grace 30 min, NSE trading days only.
  1. **Owner:** unless `token_is_fresh_today()`, `notify_operator(login_nudge_text(…, owner_login_url()))`. The plain text holds `https://kite.zerodha.com/connect/login?v=3&api_key=<ZERODHA_API_KEY>`, then the last refresh time and the pending bootstrap tasks.
  2. **Partner:** `partner_broker_sync.morning_login_reminder(now)`. It is skipped when the app is not configured, the partner bot is disabled, `connected(now)`, or a `login_reminder` row exists for the day. Otherwise it sends `login_reminder_text` with the URL button `🔑 Log in to Zerodha` (their app's login, ending on their review page; the login also starts the trade watch).
  - Any exception in step 2 is logged (`partner_login_reminder_failed`) and never affects step 1.
- **Production root `.env`:** OWNER_LIVE_ENTRY_HALT=true and OWNER_LIVE_ENTRY_HALT_CHANNELS=momentum,penny,edge.

## October 25 — O25j Production's Kite routes and the owner's entry halt (operations; commit `0cc0edc`)

- No source change. Production's `node-gateway/.env` gets `KITE_PROXY_URL` and the root `.env` gets `KITE_ORDER_PROXY_URL`, both the direct tunnel `161.118.160.180:31528`. So:
  - the gateway's Kite calls go HTTPS inside the tunnel (its KITE_BASE_URL, the plain relay, is ignored);
  - the engine's place/modify/cancel go through the tunnel; its quotes stay direct (KITE_BASE_URL https://api.kite.trade);
  - the engine's 3-minute market-hours probe watches the tunnel.
- `OWNER_LIVE_ENTRY_HALT=true` (Production root `.env`) refuses every real entry on every channel before any order is sent, including FNO_LIVE buys and the preflight test order. Exits are never halted. For the Nov 2 run: OWNER_LIVE_ENTRY_HALT=false plus OWNER_LIVE_ENTRY_HALT_CHANNELS=momentum,penny,edge (runbook step 9).

## October 25 — O25i direct Oracle tunnel verified; application adoption still pending

- Owner saved stateful TCP 31528 ingress in the attached `ig-quick-action-NSG` (`0.0.0.0/0`, source ports All). Console read-back and direct public tests confirm it; no existing rule was removed. Missing password 407, wrong destination 403. Both deployed application images reached Kite HTTP 200 directly with verified TLS and rejected fake broker tokens; no real orders/credentials or Production data mounts.
- Protected `tunnel-client.env` now selects public `161.118.160.180:31528`, with direct/SSH copies retained separately. The SSH bridge remains running as deliberate fallback; the preferred direct route does not depend on that Windows task. **Production clients still use the previous relay** until operator adoption in checklist step 5. Production remains healthy at `0aa629a`, trading switch off. No source/configuration change or restart in this slice; older timeout/SSH-preferred notes below are historical.

## October 25 — O25h supervised SSH access to the Kite tunnel

- Oracle website credentials cannot be derived from the SSH key. The VM's instance principal authenticated but its network read returned `NotAuthorizedOrNotFound`; no cloud security/IAM change was made. A temporary official SDK was removed after the check.
- Installed **Trading Sentinel - Kite SSH Bridge**, an owner-level Windows Scheduled Task using the existing OpenSSH client/key and strict saved host keys. Loopback 127.0.0.1:31528 forwards over SSH port 22 to the existing VM CONNECT service on localhost:31528. The task retries and starts at owner logon; it requires the owner to stay logged in. Docker clients use `host.docker.internal:31528`. No cloud port opening is required for this route.
- Both actual client transports passed, including both deployed images after a forced bridge-process loss. Missing password 407, other destination 403, verified Kite TLS HTTP 200; fake broker tokens rejected. Automatic process recovery took 58.8 s. Reboot/physical network-loss recovery was not exercised. Stop/start testing did not affect Production.
- Protected operator settings now select this SSH route, with a separate direct-route copy. **Production clients still use their previous route**, pending step 5 adoption; no Production config edit, image change or live enablement in O25h. The previous cloud-ingress blocker remains only for direct public 31528. [Operation, limitations and rollback](runbooks/kite-ssh-bridge.md).

## October 25 — O25g Production recovered and PR #115 deployed

- Production was started at 13:32 IST, then updated exclusively through merged PR #115 / fast-forward to `0aa629a32f1ee714eb898fb790cf50e4ca06fc43`. Engine, gateway, agent and nginx are healthy; the public dashboard and health endpoint return HTTP 200. All three application images and runtime health passed release-identity verification at 13:42:35 IST. Automatic restart and engine logging 20m x 25 are now effective, rather than only Dev settings.
- Independent verification: 66 focused local tests; 74 tests in the newly built Linux engine image; native SQLite/tunnel-module checks in the gateway image. The previous full-suite 6,010/4 result remains the developer's receipt, not a new full-suite run. No additional source defect established in the reviewed O25f changes; no source/strategy change in this slice.
- Scheduler startup attests 88 jobs (partner registration 18); deployed proving-week CLI reads Oct 26–30. Evening reporting is enabled; real-money test remains false and live bankroll 0. A fresh owner Kite login is needed Monday morning. Telegram polling resumed and a read-only bot API authentication passed; outbound delivery was not exercised. Historical stale backlog remains visible.
- Oracle TCP 31528 still times out; Console sign-in/cloud ingress and client adoption remain incomplete. No tunnel credentials were applied to Production, no broker order placed, and no trading switch enabled. Earlier entries describing Production as stopped/unmerged are superseded by this receipt. See [verification, rollback and remaining operator work](2026-10-25-production-recovery-and-release.md).

## October 25 — O25f Route conflicts, run authorization and restart policy (actual behavior, Dev, commit `e9645de`)

- **`KiteClient.__init__`.** When KITE_ORDER_PROXY_URL and KITE_ORDER_BASE_URL are both set, `order_route_error` is set, `order_client` is None and `kite_order_route_invalid` is logged (critical). It never raises.
  - `place_order` (any intent), `modify_order` and `cancel_order` return `order_route_invalid` (place: `dispatch_certainty` NOT_SENT) before the limiter or any HTTP.
  - `probe_order_route` returns the reason.
- **`ops_watchdogs._kite_endpoint_probe_tick`.** With both set, the order-route probe counts as failed (no GET through the pair) and pages through the usual 2-failure state machine.
- **`fno_live_test.current_run`.** An unreadable or disordered FNO_LIVE_TEST_START_DATE/END_DATE, or SESSIONS < 1, returns `{window_available: False, invalid: "…", sessions: 0, …}` without touching the database (it logs `fno_live_test_run_authorization_invalid`).
  - `mirror_entry` refuses with `live_test_run_window_unavailable`.
  - `morning_check` names `invalid`, and also catches a failing run read.
  - `day_report` catches a failing run read, and heads "run … cannot buy: …" for an invalid one.
- **`docker-compose.yml`.** `node-gateway`, `python-engine` and `agent` use `restart: always`, like nginx, ngrok and autoheal: a Docker daemon restart (a Docker Desktop update) brings them back. Stop the stack with `docker compose down`.

## October 25 — O25e actual Oracle tunnel installation; application adoption pending

- Recovered the owner's SSH key from the attached Linux USB without writing to that disk or exposing key contents. Strict saved-host-key verification authenticated the existing Mumbai `trading-sentinel` VM as `ubuntu`; the earlier missing-key blocker is resolved.
- The exact pushed O25d tunnel (`94a262a`) is installed on the VM, active/enabled on 31528, with a persisted VM firewall rule and root-only settings. Actual service self-test passed **407 / 403 / verified TLS HTTP 200**. Both Dev client transports passed against that service through a temporary SSH forward; the gateway test used a disposable Linux image. No real credentials/orders were used and the temporary forward is closed.
- External 31528 still times out. Oracle Console remains at owner password recovery; cloud ingress and direct client verification are incomplete. The old 31527 relay stays running. Protected client settings are outside both repositories and have not been applied to Production. The application remains at `582d7a5`, live-test switch default off, PR #115 unmerged.
- A read-only inspection found the Production engine/gateway already stopped at 11:11:48 / 11:11:51 IST (exit 137, OOMKilled false), before this setup. No cause is established and no restart was performed. Resolve during the authorized rollout before expecting proving-week messages. See [the installation receipt](2026-10-25-oracle-tunnel-installation.md) for verification, rollback and remaining steps. No application source changed in this slice.

## October 25 — O25d live-test admission and tunnel setup corrections (Dev, code `94a262a`, pushed, not deployed)

- `fno_live_test.current_run` stores the authorized start (`FNO_LIVE_TEST_START_DATE`, default `2026-11-02`), end (`FNO_LIVE_TEST_END_DATE`, default `2026-11-06`) and session limit (5). Existing names use their stored dates/length, never a later environment value. Delayed first startup consumes the earlier sessions; it does not shift the window. A pre-start or ended run cannot buy. Open-position exit management is independent and remains active.
- Run schema: nullable `fno_live_test_runs.ends_on`, added under a serialized transaction. Legacy rows without an end date remain unavailable for entries; authorize a new run name with explicit dates instead of silently rewriting them. Invalid dates/length fail closed. Capital/floor/release remain recorded metadata; this change freezes the entry window and session count, not those other environment settings.
- `fno_live_preflight.run` rejects invalid route configuration before creating a client or sending authenticated reads. Failed route/cash/evidence checks return before the real-order test. `variety_for` also refuses 01:00–05:30 IST on every day. No order test is authorized while the account is unfunded.
- `KiteClient` rejects simultaneous `KITE_ORDER_BASE_URL` and `KITE_ORDER_PROXY_URL` before creating any HTTP client. Proxy mode therefore targets verified HTTPS to Kite, with no accidental plaintext-forward request caused by an old HTTP base.
- The tunnel's external allow-list permits loopback for installer diagnostics, but loopback still requires the password, CONNECT and the exact Kite destination. Unrelated external addresses remain denied. The test-owned server loop now joins live handlers before shutdown.
- Verification: full engine/scripts suite **6,008 passed, 4 skipped**, exit 0 (702.68 s); affected suite **314 passed, 1 existing INDICES-plan skip**. Existing deprecation warnings and an unrelated injected penny-writer teardown diagnostic are recorded in the plan, not omitted. A fresh real-Kite TLS self-test with a restrictive allow-list also passed. Source/strategy switches remain off; no broker order was placed. Owner confirmed an Oracle account, but VM installation still needs an authenticated Console/SSH session; the sign-in page is left available.
- Rollout remains GitHub promotion with trading off. The [runbook](runbooks/fno-live-test.md) separates today's setup from later funding, broker login, explicitly authorized order test and activation. The earlier review below is historical; its five code findings are addressed by O25d, not by the earlier pushed `d67caad`.

## October 25 — Independent O25b/O25c readiness review

See [the independent review](2026-10-25-independent-live-tunnel-review.md) and
the active plan's pending implementation slice. The actual tunnel passed a
local real-Kite TLS self-test; 116 focused Python and 97 gateway tests passed.
Those checks do not verify VM installation, deployment or trading readiness.
The named run currently reads its session limit from the environment rather
than its stored row, and the Nov 2–6 window is not enforced. Failed preflight
checks still reach the test-order function; a conflicting HTTP order base
and proxy can send credentials in plaintext. AMO maintenance and restrictive
allow-list self-testing also need guards. The Dev runbook's CLI user and
deploy-before-new-module instructions were corrected; application behavior
was not changed by this audit. Production release remains `582d7a5`, switch
off; this review's documentation edits are local and uncommitted.

## October 25 (3) — O25c The Kite tunnel, the weekend test order and the order-route probe (actual behavior, Dev, commit `cff5036`)

- **`scripts/kite_tunnel.py` (on the Oracle VM).**
  - `Tunnel.handle` reads one request head (8 KiB within 10 s) and checks, in order:
    1. the client allow list (empty: anyone);
    2. that the method is CONNECT (else 405);
    3. the Basic password, by `hmac.compare_digest` (wrong or missing: 1 s delay, then 407);
    4. that the target is exactly `api.kite.trade:443` (else 403).
  - Then it connects to Kite within 10 s (else 502) and pipes bytes both ways until either side closes, or after 300 s of silence in both directions.
  - More than 128 connections at once get 503. Each connection logs one line: client, outcome and byte counts.
  - `install`:
    - copies itself to `/opt/kite-tunnel`;
    - writes `/etc/kite-tunnel.env` (mode 600, password kept on a re-run);
    - writes the systemd unit (DynamicUser and sandboxing), then enables and restarts it;
    - inserts the iptables ACCEPT before the first REJECT/DROP, saved with netfilter-persistent; ufw too if it is active;
    - runs `self_test` and prints the gateway and engine `.env` lines only when every check passes.
- **Gateway `services/kite-tunnel.js`.**
  - `kiteTransport(env)`:
    - without KITE_PROXY_URL: the root is KITE_BASE_URL, with no agent;
    - with it: the root is https://api.kite.trade with a `ConnectTunnelAgent` (keep-alive, 30 s idle, 10 s CONNECT timeout), and `requestOptions` `{httpsAgent, proxy: false}`.
    - A malformed KITE_PROXY_URL throws at start-up.
  - `kiteConnectThrough` sets the SDK's axios `defaults.httpsAgent` and `proxy=false` only around `new KiteConnect`, then restores them.
  - `kite.js` logs `kite_route` (route, encrypted), plus `kite_base_url_ignored` when both are set.
- **Engine.**
  - `KiteClient.probe_order_route()`: GET /user/profile on `_orders_http`. It returns None on 200, else `HTTP n: message` or the exception, credentials redacted.
  - `kite_client.redact_url_credentials`.
  - `fno_live_preflight`:
    - `order_route()` redacts the proxy;
    - `run` prints "Order route answers: yes/NO" (NO counts as a problem);
    - `variety_for(now, trading_day)` chooses the test order type; AMO price: 80% of the last price, floored to the tick, at least the lower circuit (ceiled to the tick);
    - `_instrument_book` uses the engine's book if it is today's, else a private temp-file book refreshed from Kite.
  - `FnoExecutor.cancel_and_read(order_id, variety="regular")`: "CANCELLED AMO" is terminal.
  - `fno_live_test.morning_check` adds "the order route does not answer (…)" when the probe fails.
  - `ops_watchdogs._kite_endpoint_probe_tick`:
    - after the KITE_BASE_URL probe, `_order_route_probe_target()` (the proxy, or a distinct KITE_ORDER_BASE_URL) is fetched by `_kite_probe_get`;
    - it is folded into `_kite_order_route_probe_state` by `_kite_probe_evaluate(…, route=…)` and paged by `_kite_probe_notify`.

## October 25 (2) — O25b The live exit's identity, restart recovery, bounded runs and readiness (actual behavior, Dev, commit `abbe073`)

- **`FnoExecutor` (live).**
  - `execute_exit(…, tag=None, on_event=None)` sends the SELL with the exit's own tag. It calls `on_event("placed", order_id, price)` before any wait.
  - Each step's modification counts only when Kite accepts it: `_reprice` returns a bool and emits `modified` or `modify_refused`.
  - The returned `limit` is the broker-shown resting price (`_resting_price`: Kite's `price`, else the last accepted).
  - `follow_exit(…, on_event)` re-prices to the fresh bid − max(10%, 100 ticks) only when that is under the resting price, and returns the resting price.
- **`fno_orchestrator._manage_open_positions` (live positions).**
  - First, its claimed exit (`fno_positions.exit_intent`):
    - with an order id → `_follow_working_exit`;
    - with only a tag → `_recover_tagged_exit`: `_find_tagged_order` requires exactly one SELL of this contract and quantity under the tag. Found → adopted; absent after PLACING_GRACE_SEC → freed; otherwise held and paged.
    - with neither (held for recovery: not held at the broker, or the engine stopped between claim and name) → nothing sold; paged once as `claimed_unsent` unless its reason is not_held/partly_held.
  - A FNO_LIVE position with bar `PREFLIGHT-…` exits at once, reason `preflight_flatten`, hard-flat depth.
  - After the claim, `_broker_mis_held` gives MIS on the contract's exchange; less than the quantity to sell → nothing sold (claim kept, paged).
  - Then `record_exit_tag` writes a tag `FX`+17 hex and the reason; if it cannot be written, the claim is freed and nothing is sent.
  - `_exit_event_recorder` records the working order on placed/modified and every step in `fno_live_execution_events`.
- **`fno_live_test`.**
  - `mirror_entry` refuses non-NIFTY (`live_test_not_nifty`) and an ended run (`live_test_run_ended`, `current_run`: `fno_live_test_runs`, sessions counted with `is_trading_day_sync`).
  - It records `entry_filled` (decision-to-fill delay, slippage) and `backstop_armed`.
  - `one_lot_pnl` uses the two fills and one lot's own `calc_fno_costs`.
  - `day_report`: one lot each, execution quality per trade, refusals by reason, outstanding work, the floor caveat.
  - `morning_check` gives route, login, own cash against `typical_lot_cost`, broker F&O positions, run, equity and leftovers. It runs from job `fno_live_readiness` at 09:25 while armed.
  - `hand_off_preflight_fill` records a filled preflight buy as a FNO_LIVE position and pages.
- **`fno_proving_week`.** One-lot P&L comes from fills (`one_lot_pnl`). The verdict is UNAVAILABLE when the drawdown-halt read is unavailable.
- **`kite_client`.** With KITE_ORDER_PROXY_URL, `order_client` is `https://api.kite.trade` (or KITE_ORDER_BASE_URL) through that HTTP CONNECT proxy.
- **`fno_live_preflight`.** `order_route()` describes the route (encrypted or not) and flags none or both set. A fill is handed to the engine; the tool never sells.
- **Gateway `executeSignal`.** A failed `releaseFilled` is logged and the hold kept; protection continues.

## October 25 — O25 The real-money F&O test, the live exit and the proving week (actual behavior, Dev, commit `ca12934`)

- **`fno_live_test` (off unless FNO_LIVE_TEST_ENABLED).** After a paper single-leg entry on an NFO underlying, `fno_orchestrator._single_leg_entries` calls `mirror_entry`.
  - It refuses (as FNO_LIVE signal rows `live_test_*`):
    - an expiry day;
    - a missing paper row;
    - an open FNO_LIVE position, or FNO_MAX_TRADES_PER_DAY reached;
    - an unreadable or under-floor equity (one owner notice a day);
    - a stale, one-sided or wide fresh quote;
    - an ask over the paper price × (1 + FNO_LIVE_TEST_MAX_CHASE_PCT).
  - It then buys ONE lot: a LIMIT at the ask on the tick grid plus FNO_LIVE_TEST_ENTRY_BUFFER_TICKS.
    - It runs through `reserve_shared_fno_risk` (pool = `live_pool()` = FNO_LIVE_TEST_CAPITAL), `claim_shared_fno_entry_dispatch` (max_open 1) and `FnoExecutor.execute_entry`.
    - On a fill it inserts the FNO_LIVE row with the paper row's stops, target, direction and bar, then arms `fno_broker_backstop`.
  - `live_equity` = capital + the FNO_LIVE ledger sum (fail closed). `day_report` puts the day's real trades beside their paper twins.
  - The legacy live entry block (go-live bar) does not run while the test is on.
- **Live exit (`FnoExecutor.execute_exit`, live only).**
  - One SELL LIMIT along `exit_ladder_prices` (EXIT_LADDER: 0.5%/2 ticks for 4 s, 3%/10 ticks for 6 s, 10%/100 ticks for 20 s under the bid), modified with `modify_order`. The hard flat starts at the last step.
  - Statuses: filled, not_sent, rejected_verified, unfilled (with `limit`), unknown.
  - `follow_exit` reads a working order and moves it to the fresh bid − max(10%, 100 ticks), never up.
  - Paper fills are unchanged (entry at the ask, exit at the bid).
- **`fno_orchestrator._manage_open_positions`.**
  - The executor is per position (`_executor_for_position`): a FNO_LIVE row with a PAPER-... entry id is closed on paper; one with a broker id by real orders, whatever the switches.
  - Live positions first follow a recorded working exit (`fno_exit_intents.order_id`, `_follow_working_exit`).
  - After the claim, a real sell is skipped when the broker's positions hold none of the contract (`_broker_holds_none`): the claim stays and the owner is paged.
  - Unfilled outcomes (`_live_exit_not_filled`):
    - not_sent / rejected_verified: `release_exit_intent`, then a retry;
    - unfilled: `record_working_exit`;
    - anything else stays claimed.
  - Owner pages are deduplicated only once delivered.
  - `_live_leg_managed`: the live leg's exits run while it is enabled, and always while a FNO_LIVE position is open. `fast_exit_has_work` always looks at FNO_LIVE.
- **Own-cash holds.**
  - `FnoExecutor` calls `KiteClient.settle_entry_reservation` after a fill, a fill during cancel, or a verified zero fill.
  - That calls `AccountCashReservations.release_filled` / `release_zero_fill`, looked up with `reservation_for_order`.
  - The gateway's momentum entry calls `releaseFilled` after a confirmed fill.
- **Order route.** `KiteClient.order_client` (KITE_ORDER_BASE_URL, when set and different) carries `place_order`, `modify_order` and `cancel_order` (`_orders_http`). `set_token` sets both clients' headers.
- **`fno_proving_week`.**
  - `window_days` uses the sync holiday cache, never the network.
  - `score` and `render` implement the verdict rules frozen in the module docstring.
  - `evening_report` runs from the 15:50 job `fno_evening_report` (trading days, FNO_EVENING_REPORT_ENABLED). It is sent once a day (`fno_evening_report_told`).
- **`fno_live_preflight`**: an owner-run CLI. Reads: the route, own free cash, open F&O positions, the order book. `--test-order`: one BUY 20% under the bid, cancelled and read back.

## October 24 (night, 4) — O24i F&O paper risk messages (actual behavior, Dev, commit `0b7d7b9`)

- **`fno_risk_alert.check_paper(db_path, now, notify=None)`**, called by `fno_orchestrator.run_fno_tick` right after `_manage_single_leg_books`, unless FNO_DISABLE_PAPER.
  - It reads `fno_shared_risk.shared_fno_entry_policy` (FNO_PAPER, pool FNO_PAPER_BANKROLL) and `fno_adaptive_risk.risk_stance` over `read_book_closes`.
  - State: `{"tier": stance.reason, "halts": [halt kinds, most serious first, plus two_strike_day_halt]}`.
  - Unchanged from `fno_risk_alert_state` → nothing. The first look at a calm book (base, no halt) is saved silently.
  - Otherwise `risk_text` goes to `operator_alert.notify_operator` (event `fno_paper_risk_state`); the state is saved only when it was accepted.
  - With the ledger unavailable, nothing is claimed. Any exception is logged as `fno_risk_alert_failed`.
- **`risk_text`.** It gives the tier (base / 0.5x / 0.25x / proven), the drawdown from the peak, and the halts started and cleared. Then the paper equity and its distance to `FNO_PAPER_BANKROLL × (1 − FNO_MAX_DRAWDOWN_PCT)`; a new drawdown halt adds that the decision is the owner's.
- The halt itself is unchanged (`fno_shared_risk.entry_halts`, `FNO_MAX_DRAWDOWN_PCT` 0.15).

## October 24 (night, 3) — O24h F&O entry-signal arms; exit slippage report; "check before you buy" (actual behavior, Dev, commit `b8cf7a8`)

- **`fno_shadow.VARIANTS`** gains `FNO_CONTINUATION` (`FnoShadowVariant.pullback_atr` 0.25, freshness `crossing_or_pullback`).
  - `_variant_signal` accepts a fresh break as the base does. Otherwise it needs `pullback_resumed(today_bars, long, level, atr, 0.25)`, else `no_pullback_resumption`:
    - closes beyond the level exist before the last bar;
    - after the run's extreme, a bar came within 0.25 ATR of the level;
    - the last bar closes beyond the level and the previous bar's extreme.
  - The regime, EMA and RVOL checks, the stop and the target are the base's. The freshness branches are explicit; an unknown one raises. The live shadow evaluates all five variants each F&O tick (research only).
- **`fno_policy_replay.ReplayPolicy.signal_variant`.** `_entry` calls `fno_shadow._variant_signal` with that variant instead of `evaluate_fno_mom`. FNO_SIG_CONFIRM_1, _OR_20, _OR_45 and _CONTINUATION all manage at the live fast-exit cadence.
- **`scripts/run_preregistered_study.py`** study `fno-entry-t2`: development Sep 10 – Oct 9, untouched Oct 12 – Oct 23; candidate FNO_SIG_CONTINUATION vs BASELINE (`CURRENT`). Results are in `docs/research/fno/2026-10-24-entry-arms/`.
- **`fno_exit_report.py`** (read-only sqlite URI; `python -m fno_exit_report [FIRST [LAST]]`).
  - `exit_slippage` takes the closed FNO_PAPER single-leg positions with a level (`stop_underlying`, `trail_stop_underlying`, `premium_stop`).
  - "past" is points beyond the level (positive is worse; the premium stop in premium). The rupee estimate is past × |delta_at_entry| × qty.
  - Time stops, the lock, targets and the forced close are counted as without a level. `render` prints them.
- **"Check before you buy".**
  - `partner_fill_capture.handle_update` calls `partner_watch.answer_check` before `parse_report_text`; anything else returns "not_check" and continues as before.
  - `parse_check`: the words `check` or `chk` (or `/check`); then the underlying (default NIFTY), the strike and CE/PE (or "22300pe"), an optional price, and lots ("x2", "2 lots", at most 50). Commas inside numbers are allowed. An unclear word gives `CHECK_HELP`.
  - `check_message` finds the contract (`get_instruments_for(name).nearest_option_expiry`, `.option`) and builds a synthetic `Trip`. `_market_plan(size=(qty, price or None))` takes the fresh ask when no price is given, else returns no plan.
  - The day's context comes from `_state.view` when it is today's: `_after_loss`, `_day_line` (as "This would be trade N"), `_usual_share`, the cash.
  - `check_text` builds the reply. `answer_check` sends it via `_say(kind CHECK, event_at=the message time)`, keyed `check:<update_id>` (a repeated update is not answered twice). The deadline is `CHECK_DEADLINE_SEC` (12 s).
  - CHECK is in ALWAYS_SENT (never muted), LIFETIME 120 s, PRIORITY 1.
- **WATCH_ON** ends with "Before a buy you can send me, for example: check 22300 pe."

## October 24 (night, 2) — O24g stops moved together; claims from a fresh GTT list; the order stream and delivery measurement (actual behavior, Dev, commit `797d69b`)

- **Stops moved together (`_lowered(moves)`).**
  - A move is {"id", "old", "new", "units", "at"}. `_events` step 1 collects each holding's SL orders modified down. `_guard(moves)` adds the GTTs modified down (`_track_stops`) and a single replacement (`_replacement` → ("MOVE", move)); several replaced stay ("CHANGED", gone, added) → `_changed`.
  - One read is one message, keyed `lowered:<id>@<new>+…`, with "first" taken once for the read.
  - `moves_reason` is the most serious of the read's reasons. `moved_text` gives each move "₹70 → ₹69 for 65" and the result at the units' weighted triggers, on the units held (`_held_moves` caps them). `_moves_why` names the moves the reason is about.
  - `_b_lowered` tells only the moves whose stop still waits at its new level, with the units capped as in O24f, and judges the reason again. One left uses `lowered_text`.
  - With the GTTs UNKNOWN, the SL moves are still told.
- **Claims from a fresh GTT list.**
  - `_cover_claim` builds REMOVED, NO_STOP or PARTIAL. When a claim is not yet in the outbox and the GTT list was not read this tick, the guard reads it (once a tick) and recomputes the cover. A changed state gives no claim this tick; without a read, the claim waits.
  - For EXCESS, ORPHAN and PRODUCT that count a GTT (`_counts_gtt`), `_events` reads the list and runs `_exits` again with it. Without a read, those claims are dropped for this tick.
- **The tick and the stream.**
  - `watch_tick(woken=)` holds `_tick_lock` around `_watch_tick`. A scheduled tick returns SKIPPED busy while another runs. `wake()` starts `_woken`: woken ticks run while wakes keep coming, WAKE_GAP_SEC (1 s) apart, at `_now()`, with the last tick's market.
  - `_state.detected_by` (poll | stream) goes to `_insert_outbox(by=)`, also through `_start_plan` → `_plan_job(by=)` → `_store_plan(by=)` and `_revise`.
  - `partner_watch_stream.ensure()` runs each tick and starts `run()` while the stream should run (`_should_run`: enabled with a key, the login held, 09:00 to 15:40).
  - `run(connect, clock)`: CONNECTING → LIVE. Frames go to `_frame`: binary is counted; an "order" text frame counts an update, records its lag and calls `partner_watch.wake("order")`; "error" is counted, not logged.
  - Recovery: 401, 403 or no library → REFUSED and a 30 min wait; anything else → DOWN with a 1 s backoff doubling to 60 s; no frame for 10 s → reconnect; a changed token → reconnect; the end → OFF.
  - `_code(exc)` logs only the HTTP status or the type.
- **Measurement.**
  - `partner_watch_messages.detected_by`.
  - `_TickStats` (module `_ticks`) counts ticks by status:reason (and "woken"), tick_ms and read_ms (the /orders read), up to TICK_SAMPLES each. It is saved every TICK_STATS_EVERY (60 s) for the watch's current day as `ticks:<day>:<process start>`, with `partner_watch_stream.stats()`.
  - `partner_watch_report.report(db, first, last)` reads it (sqlite read-only URI); `spread` is nearest-rank p50, p95 and max; `render` prints plain text; `main` is the CLI.
  - `watch_status()["stream"]` gives the stream's state, or None when off.

## October 24 (night) — O24f the watch's sell-order and replacement boundaries; watch health (actual behavior, Dev, commit `320fe20`)

- **"None held" (`none_held`).** For an option, or a product, with no holding, the evidence is:
  - ZERODHA: `View.positions`, Zerodha's positions read within POSITIONS_MAX_AGE, show none;
  - ORDERS: no positions now, but the overnight list was read today (`View.carried_known`);
  - UNREAD: the positions were not read today.
  - ORPHAN says "Zerodha shows you hold none now … Cancel it if the trade is over" only on ZERODHA. Otherwise: "… I could not check whether you hold this option: … If you hold it, this order is its protection: keep it. If you don't, it would sell N you do not have: a short sale."
- **Sell orders by product (`_sell_products`, `_exits`).**
  - Every waiting sell (an SL, an open sell, a GTT sell leg) is keyed by exchange, option and product; each exit carries its `product`.
  - EXCESS: per holding, as before.
  - ORPHAN: an option held in no product, one message for all its sells.
  - PRODUCT: a product not held, on an option held as another. Keyed `product:<day>:<exchange>:<symbol>:<product>:<ids>`; built by `_b_product` while still so.
  - `product_text`: "this sell order is MIS: …, but your 65 are NRML. It would not sell them: if it triggers, it opens a new MIS short of 65 …". It hedges the same way when the positions are not ZERODHA.
  - PRODUCT is in QUIET_KEEPS, PRIORITY 1, LIFETIME 900.
- **Replacements (`_track_stops`, `_all_stops`, `_replaced_lower`).**
  - Each tick (not UNKNOWN), the guard compares the stops now with `seen`. `_all_stops` gives the holding's SL orders plus the GTT stop legs of a GTT list within GTT_REFRESH; without one, the GTTs as last seen.
  - A stop gone and `_withdrawn` goes to `withdrawn`; a new one goes to `fresh`. Both carry "at" and are kept for REPLACE_WINDOW (120 s).
  - When both lists have entries, they are matched and cleared:
    - lower on average and one each: `_lowered` for the new stop, units = min(new, old, held);
    - several: `_lowered(changed=(gone, added))` at the average triggers. `_b_lowered` checks that every new stop still waits; the text is `changed_text`: "your stops changed: ₹95 and ₹92 cancelled, new ones at ₹88 and ₹70. If they are hit, on your 130: about … instead of about …".
  - A GTT with the same id and a lower trigger is a move.
  - `baseline` (a new guard, or the first read after a restart) only remembers. The memory (`seen`, `withdrawn`, `fresh`, `tracked`) is kept in partner_watch_state.
- **A fired GTT (`_lost_why(gtts=)`).** A GTT now "triggered" is judged by the order it placed:
  - sold part: SOLD via GTT, "your GTT at ₹60 fired and sold 30; the other 35 have no stop now";
  - cancelled unsold: FIRED_CANCELLED;
  - no order found: GTT_GONE.
- **Watch health (`_health`, `_read_failed`).**
  - `_State.unread`: read → its first failure since it last worked. Reads: orders, positions, gtts, quotes. Failures for the budget, TokenException and not_connected are not counted.
  - BLIND (fixed text, ALWAYS_SENT, PRIORITY 1, LIFETIME 600) is sent once the failure lasts BLIND_AFTER:
    - orders: 60 s, from the failed-read path;
    - positions: 120 s, only while the overnight list is unknown;
    - gtts: 120 s, only while a holding's cover is UNKNOWN, naming those holdings.
  - BACK (PRIORITY 4) is sent when that read works again, if its BLIND was sent.
  - The failed-read tick waits for its message within the budget.
  - `watch_status()["unread"]`: the reads failing now. The page appends "Right now it cannot read …".
  - `_read_gtts` keeps the last list on a budget skip.
- **Names and counts.**
  - `Holding.twin`: the option is held as two products; texts use `_name` ("NIFTY 22300 PE MIS").
  - `Holding.converted`: units Zerodha shows in a product today's orders did not buy, while the orders' own product shows fewer. `_count_note`: "Zerodha's positions show 65 held as NRML; your orders today bought them as MIS, so they look converted."
  - EXCESS adds `_count_note`.
  - WATCH_ON and QUIET_TOAST name the sell-order alarms (and, in WATCH_ON, BLIND).

## October 24 (late) — O24e the watch's last races closed; sell orders that could sell short (actual behavior, Dev, commit `79629e5`)

- **Send only from the latest read (`_deliver`).** Each try, up to `BUILD_TRIES` (3):
  - takes `view = _state.view` and builds from it (`_build(…, view)`; builders await `_plan_for` and `_price_now`);
  - if `_state.view is not view` after the build (`_still`), builds again from the newer view;
  - None from the build → `superseded`;
  - otherwise `_mark` (attempting, attempts + 1, the text), then checks again. A newer view there → `_unmark` (attempts, outcome and last_attempt_at as read) and builds again.
  - After 3 tries it is WAIT and the next tick tries again. Fixed texts (WATCH_ON, PROMPT, RECONNECT) need no view.
- **Plans and their messages, atomically.**
  - `_store_plan(…, announce=item, day=)` inserts the version (version 1 is still never replaced) and the outbox row (`_insert_outbox` on the same connection) in one transaction. `_noted` updates `_state.enqueued` and wakes the sender only after the commit.
  - `_plan_job` builds the PLAN item (lots from `trip.bought`, `_after_loss`, `_day_line`, `_usual_share`) before storing. `_revise` does the same for ADDED.
  - A failed write raises: in the plan job, the task fails and is started again (`PLAN_TRIES`); in `_revise`, `_events` logs `partner_watch_revise_failed` and the change is seen again on the next tick. `_load_meta` failures log `partner_watch_plan_read_failed`.
- **A moved stop (`lowered_text`, `_b_lowered`).**
  - The context carries `stop_id` and `units`:
    - a modify: `kite:<order>`, its pending units;
    - a replacement: the new top stop's id and units.
  - The builder needs that same stop waiting at the new trigger. The units are capped at the held count.
  - With units under the held count: "you moved your stop for U of your N down … on those U: … instead of …", plus `_rest_note`: the other units' stops, part covered, or none. GUARD says "those U can end in a loss". `_result_for(holding, price, qty)` is the result for part of a holding.
- **No plan stop (`_no_level_line`).** The PREMIUM and NONE stop lines start from the cover:
  - FULL: "Your SL at ₹X covers all N." + why there is no level + the result at the stops + "in a fast fall an SL order can trigger and still not fill";
  - PARTIAL: the units without a stop and their premium at risk;
  - UNKNOWN: "unless a GTT covers it";
  - ABSENT: as before.
  - `plan_summary`: "no plan stop; your SL at … covered all N". `added_text` without a level and FULL: the result at the stops.
- **Freshness.** `QUOTE_MAX_AGE` = 15 s (was 60 s), the same as `QUOTE_FRESH`; `stale()` unchanged otherwise.
- **Sell orders that could sell short (`_exits`, `exits_of`).**
  - `exits_of(rows, gtts, exchange, symbol, product|None)` lists:
    - SL orders waiting (SL);
    - open, or waiting without a trigger (SELL);
    - active GTT sells (GTT); a two-leg OCO once, for its bigger leg (OCO).
  - Every tick, after the guards, `_exits`:
    - EXCESS: a holding's exits add up to more than it holds, keyed `excess:<ep>:<held>:<exit ids>`;
    - ORPHAN: an option with sells waiting and no holding of any product, keyed `orphan:<day>:<exchange>:<symbol>:<exit ids>`.
  - Each is told after `COVER_GRACE` (20 s; `exit_seen`). The builders recount from the view and wait while a counted GTT is not in a fresh list (`View.gtts`, within `GTT_REFRESH` 60 s).
  - `_events` reads the GTT list when it is older than `GTT_REFRESH`. Both kinds are in `QUIET_KEEPS`, `PRIORITY` 1, `LIFETIME_SEC` 900.
- **Stop advice.** FULL with a stop under the plan stop gives the comparison only (no "Raising its trigger").

## October 24 (night) — O24d the watch's advice stays with the partner's position (actual behavior, Dev, commit `677c630`)

- **Outbox (`partner_watch_messages`).** The tick's `_events` collects (key, kind, subject, context, event_at, episode). It builds `View` (rows, trips, holdings, covers) and writes the messages as `queued` (`_enqueue_many`, INSERT OR IGNORE: a key goes in once). Then it starts the sender (`_kick` → `_drain`, one at a time, via `background_tasks.spawn`).
  - `_drain` takes today's `queued` rows and provably unsent ones with tries left, by `priority` (UNFILLED 0; REMOVED, LOWERED, REFUSED 1; NO_STOP, PARTIAL 2; ADDED, PLAN 3; CLOSE 4; fixed texts 5).
  - `_deliver` handles each row in this order:
    - past `LIFETIME_SEC` → `expired`;
    - quiet → `muted` (not the loss alarms);
    - otherwise `_build`:
      - from `_state.view` only when it is today's, within `VIEW_FRESH` (15 s), and from the latest tick (`tick_at`), else WAIT;
      - the builder returns None when the message is no longer true → `superseded`.
  - The send records Telegram's state. `unsent_connect`, `rate_limited` or `telegram_http_5xx` are tried again `RETRY_GAP` later, up to `MAX_ATTEMPTS`; anything else is final; a row left `attempting` is never repeated.
  - A tick that reads no book (outside the session, no login, a failed read) calls `_flush`, so fixed texts still go; messages about a trade wait for a read.
  - WATCH_ON, PROMPT and RECONNECT go through `_say` (the outbox, waiting up to `DELIVERY_INLINE_SEC`).
- **Builders (`_BUILDERS`).**
  - PLAN: the trade still held (else superseded), its plan for the held count (`_current`), its cover and a fresh quote.
  - ADDED: the trade still held.
  - NO_STOP / PARTIAL / REMOVED: the trade still held, the cover still ABSENT / PARTIAL (UNKNOWN waits), NO_STOP / PARTIAL for the same size.
  - UNFILLED: the fired order still OPEN and unsold.
  - LOWERED: a stop still waiting at the new trigger.
  - REFUSED: the order from the view; "still open" from the held count then.
  - CLOSE: the trade still held.
- **Episodes.** `_episode(day, holding)` = `<day>:<trip key>` (`<day>:zerodha:<holding key>` without a trip). `_Guard` is per episode. `covered_once`, `full_once`, `stops`, `full_ids` and `lowered_told` are saved as `guard:<episode>` in `partner_watch_state` and loaded by `_guard_for`. Keys:
  - `nostop:<ep>:<held>`;
  - `partial:<ep>:<held>:<protected | lost:<ids>>`;
  - `removed:<ep>:<lost ids>`;
  - `unfilled:<order>`, `lowered:<order>:<new>`, `refused:<order>`;
  - `plan:<ep>`, `added:<ep>:<order>`, `close:<ep>`.
  - `_replaced_lower` runs only on a tick after the first of a login (seen happening).
- **Stop advice (`stop_advice`).**
  - It uses the plan stop's `level_state(..., now)`; CROSSED adds nothing (the stop line says it).
  - FULL:
    - stops ≥ the plan stop: "already covers all N … no second SL is needed";
    - lower: the result at the stops (`_result_at_stops`) against the plan stop, and "Raising its trigger to ₹X" with a fresh price.
  - PARTIAL: "For the other N:" an SL.
  - UNKNOWN: "Your GTTs could not be read. If you have no stop yet:".
  - ABSENT: "Place an SL sell now" (VALID only).
  - STALE / UNCHECKED give `_unchecked`: the plan stop with its time, and "check the option is still above ₹X before placing an SL there".
- **Freshness (`stale`).** STALE when `looked_at` is older than `QUOTE_FRESH` (15 s), or `quote_at` is more than `QUOTE_MAX_AGE` (60 s) before `received_at`. `plan_stop_line` says "the last price update was HH:MM:SS".
- **Exit price (`exit_fill`, `_sell_now`).** `_top` keeps `bids` ([price, qty], best first). Selling the whole holding walks them: the best bid; else "into the bids (A down to B)"; else "the bids shown take only N of your Q … or worse" (the rest priced at the lowest bid shown). Without sizes it is the bid as before.
- **One count.**
  - `_start_plan(…, holding)` sizes version 1 from the reconciled holding (`_plan_of(size=)`). `_revise` stores the holding's quantity and average; `bought` / `sold` are the orders'.
  - PLAN's header is the buy (the context's `bought`, `bought_px`). `_held_line` adds "N still held: you sold … with charges", "N held now, with your later buys", or Zerodha's count note.
  - `added_text(cover=)` adds how much of the new size a stop covers.
- **Budget.**
  - `watch_tick` sets `deadline = start + TICK_BUDGET_SEC` (4 s). `_book(path, deadline)` raises `budget` with less than `MIN_READ_SEC` (0.5 s) left.
  - `_refresh_book` keeps the last trade book and the last positions on a failed or budget-skipped read. Positions older than `POSITIONS_MAX_AGE` (2 min) are dropped.
  - `_seed_cash` runs after the book, up to `CASH_TRIES`.
  - `_wait_within` bounds the waits for plans (`PLAN_INLINE_SEC`), the sender (`DELIVERY_INLINE_SEC`) and the looks (spawned).
- **Review (`partner_coach._off_card_plan`).** OFF_CARD's why says what Zerodha shows: the partner's own SL or GTT and when ("The card rule is about which trades to take, not about whether your stop was good"), no stop order placed, or stops not known.

## October 24 (evening) — O24c the trade watch made trustworthy; a fired backstop recognised; a stable usual size (actual behavior, Dev, commit `7d0cb6f`)

- **What is held (`partner_watch.fills_of`, `trips_from_fills`, `holdings_of`).**
  - Fills come from GET /trades. It is read when a fill is new, and again while it shows fewer units than the orders' filled quantities. An order's unshown part is one fill at its last update, priced to keep its average.
  - Round trips are per exchange, option and product. A trip reopened by the same order's later fill is `<id>#2`.
  - A carried position starts at `overnight_quantity`, at the position's average price.
  - `Holding.basis` compares the trips with Zerodha's positions (GET /portfolio/positions: after a new fill, every 30 s, each tick while any differ):
    - CONFIRMED: they agree;
    - ORDERS: no positions were read, or the trip's last fill is within POSITIONS_LAG (10 s) of the read;
    - ZERODHA: they differ; the messages then use Zerodha's count and `_count_note` says so.
- **What protects it (`cover_of`, `gtt_legs`).**
  - `Cover.state` is FULL / PARTIAL / ABSENT / UNKNOWN, with `covered` and `exiting` units:
    - waiting SL orders (`WAITING`: TRIGGER PENDING, a modify or AMO in flight) and active GTT stop legs, of the holding's product only, count for their pending units;
    - other products go in `other_product`;
    - a fired stop is `fired`: a SELL with its trigger in OPEN, or a triggered GTT's placed order still OPEN.
  - GTTs are read only when the SL orders leave units uncovered, at most once a tick, and reused for 20 s. Unread GTTs make the state UNKNOWN.
  - `_guard` keeps one `_Guard` per holding and sends:
    - NO_STOP: never covered, 120 s after the newest buy order's first fill;
    - PARTIAL: for 20 s;
    - REMOVED: covered, then ABSENT for 20 s; `_lost_why` gives CANCELLED / SOLD / GTT_GONE / GONE;
    - UNFILLED: a fired stop unsold for 10 s; it is never muted;
    - LOWERED: on a modify (per order, while waiting), or when a stop is withdrawn (`_withdrawn`: cancelled unsold, or a GTT gone) and the highest remaining trigger is lower.
- **Delivery (`_send`).**
  - The row is written as "attempting" before the send; Telegram's state, error, ack time and message id after.
  - `_retryable`: `unsent_connect`, `rate_limited`, or a `telegram_http_5xx`. Those are sent again, 10 s apart, at most 4 times, within `LIFETIME_SEC[kind]`, with the text rebuilt:
    - level-triggered kinds by the next `_guard`;
    - one-off kinds (PLAN, ADDED, LOWERED, REFUSED) by `_retry_pending`;
    - WATCH_ON / PROMPT by `_send_until_done`.
  - Everything else is final. Quiet mutes PLAN, ADDED, NO_STOP, PARTIAL and CLOSE.
- **Levels (`level_state`).**
  - A stop at or above the LTP is CROSSED. PLAN and the stop line then say the price is already under the plan stop, and give the result of selling at the bid; there is no SL instruction.
  - A target at or under the LTP is "already above the target zone".
  - Unchecked levels say when they were set.
  - Futures levels read "<UNDERLYING> future".
- **Plans (`partner_watch_plan_versions`).**
  - `_store_plan` never replaces version 1 ("BUY").
  - `_revise` adds ADDED (a new buy order; a message while fresh), FILLED and TRIMMED versions, with the same levels and the loss for the new size and average (`revised`).
  - A restart loads the latest version (`_load_meta`).
- **Timing.**
  - `_book` bounds each read at 4 s. The tick runs the protection alarms before plans.
  - `_start_plan` runs `_plan_job` as a task: the tick waits up to `PLAN_INLINE_SEC`; past `PLAN_DEADLINE_SEC` the plan is the premium at risk.
  - A failed plan task is started again, up to `PLAN_TRIES` (3).
  - `watch_tick` returns `ms` and logs `partner_watch_tick_slow` over 4 s.
  - `_top` keeps `bid_qty`, `ask_qty`, `quote_at`, `trade_at` and `received_at`; looks store them.
- **Backstop (`fno_broker_backstop._sl_shape`).** SL, or LIMIT with a trigger > 0 (a fired SL), in both the tagged and the legacy lookup.
- **Review (`partner_coach.size_history`, `partner_insights.trade_share`).**
  - `load_partner_coach` passes the shares of the trades in the 45 days before the window as `earlier_sizes`; `usual_size_flags(..., earlier=...)` starts from them. The watch's `_usual_share` uses the same history.
  - `score["rules_version"]` is `partner_lessons.RULES_VERSION` (2026-10-24); the page and the PDF print "Rules of 24 Oct 2026".

## October 24 (afternoon) — O24b partner size against their own habit; the system on the 15:40 F&O close (actual behavior, Dev, commit `3c6523e`)

- **O24-SZ size (`partner_insights.py`, `partner_coach.py`, `partner_lessons.py`, `partner_watch.py`).**
  - `_risk` keeps the money at risk (to the stop, the card's SL, or the premium) as `insight["risk"]`. It adds `insight["size"]`: the premium paid and its share of the day's cash. Neither is a limit.
  - `usual_size(shares)` is the median of the last `USUAL_SIZE_LOOKBACK` (20) shares, once there are `USUAL_SIZE_MIN_TRADES` (5).
  - `usual_size_flags(items)` runs after the sequence flags over every traded item in the loaded window, in time order. A share above `USUAL_SIZE_MULT` (1.5) times the usual gets UNUSUAL_SIZE:
    - "You usually put about N% into one trade";
    - the better line is the usual lots, with the result when the trade closed.
  - The rule "size" is named "Usual size": UNUSUAL_SIZE or AVERAGED_DOWN break it.
  - BIG_RISK and `RISK_OF_CASH_PCT` are gone.
  - Watch PLAN:
    - the loss at the stop is shown as a share of cash, without a threshold;
    - "⚠️ ₹X in this trade, N% of your cash: much bigger than your usual M%" when the buy is more than 1.5 times the usual. `_usual_share` builds the usual from earlier days' ZERODHA BUY reports against `partner_account_days`, then today's trips.
- **O24-MC2 the 15:40 close.**
  - `market_calendar.DERIVATIVES_CLOSE_TIME` (15:40) is the F&O session end; `MARKET_CLOSE_TIME` (15:30) stays the cash end.
  - At 15:40:
    - `fno_chain.EXPIRY_CUTOFF` and `hedge_strategies._EXPIRY_CUTOFF` (time to expiry for every option price and greek);
    - `hedge_advisory`'s gamma-alert hours;
    - `research_future_candles` (fetch to 15:40, job at 15:45);
    - `partner_orchestrator.partner_analytics_tick` (gate 09:20–15:40);
    - `standard_capital._expiry` exits;
    - the activity and health windows in `lifecycle_receipts`, `ops_metrics`, `ops_watchdogs`, `token_lifecycle`, `daily_bootstrap`, `scheduler_telemetry` and `tools/runtime_audit`.
  - At 15:30, the cash segment:
    - the penny and momentum market-hours gates (`main.py`) and `market_calendar.is_market_open`;
    - `PENNY_DAILY_ATTRIBUTION_TIME`, `penny_lifecycle_replay` and `standard_capital._close_time`;
    - the gateway's `backlog-reconciliation` stock signals.
  - Strategy times unchanged: FNO entry end 14:45, hard flat and DR square-off 15:10, the expiry book's A flat 15:13, FINAL_FLAT 15:38, BL late 15:30.

## October 24 — O24 partner: stops as Zerodha shows them, the 15:40 close, refusals in plain words, the trade watch (actual behavior, Dev, commit `53280d9`)

- **O24-SR stops (`partner_broker_sync.py`).**
  - A stop is any option SELL order that carried a trigger:
    - `carries_trigger` (any order type with a trigger above 0);
    - the history's first trigger, through `history_facts`, for orders read after O24.
  - Kite shows a fired SL as LIMIT and a fired SL-M as MARKET, both with the trigger kept.
  - A stop the partner turns into a market or limit sale loses its trigger in the book. Its status is CONVERTED, and it counts as protecting the trade until that sale.
  - `_read_details` reads the history of every stop and every modified order, sell orders first, at most 40. It stores:
    - the price and trigger changes (`partner_order_changes`);
    - `history_read`, `stop_trigger` and `stop_since` on `partner_orders` (the columns are added in place by `init_partner_broker_db`; a re-read of the book never erases them).
  - `order_stop(order, changes)` gives a stop row, None, or `UNKNOWN`:
    - with a history: its first trigger and the time it appeared (`placed_exact`);
    - before O24: a trigger now or a trigger change makes it a stop. The first trigger is the first change's old value, and the earliest stamp is "in place by" (`placed_exact` False);
    - a modified sale with neither: UNKNOWN.
  - `merge_stops(stop_rows, orders, changes)`: SL stops come from the stored book on days it was stored, else from the fills read's `partner_stop_orders`. GTT stops always come from `partner_stop_orders`. It returns the UNKNOWN sales.
  - `partner_coach.analyse(unknown_stops=…)`: a trade with an UNKNOWN sale and no confirmed stop has unknown stops (no stop checks). `PROTECTING` = PENDING, TRIGGERED, CONVERTED.
  - `partner_insights._stop_orders_of` uses `order_stop`, so stop moves on fired and converted stops are seen.
  - STOP_TRAILED is also given after a trim down, when the stop ended above where it started and its last move was up.
  - The timeline says "You placed an SL order at ₹X" when the time is exact, else "By this time you had an SL order at ₹X".
  - Effect on Oct 23: the stop rule read 1/12 and now reads 1/10. Stops moved down went from 1 to 9 trades, and that is now the lesson (−₹1,706). "Size within the account" went from 0/12 to 6/12, since risk is now measured to the real stop.
- **O24-RF refusals (`partner_insights.refusal_plain`).**
  - A refusal for margin reads in plain words:
    - a buy: "the buy needed ₹X and your account had ₹Y";
    - a sale is counted as a new short sale, for one of four reasons, tested in order: the option was not held at that moment, the buy and sale products differ, the sale was for more than was held, or (the rest) another sell order was already waiting for the lot.
  - Shown on the trade timeline and in the day's orders. The page and the PDF show the plain reason with "Zerodha: …" under it.
- **O24-MC the close.**
  - `partner_broker_sync.CLOSE_MIN` and `partner_trade_paths.CLOSE_MIN` come from `market_calendar.DERIVATIVES_CLOSE_TIME` (15:40). They set the day's completeness and the candles to 15:40.
  - `partner_coach._day_close`, the insights holding window and the chart end are 15:40.
  - Taps are accepted to 15:40. The last time bucket is "13:30–15:40".
  - `PARTNER_EOD_MIN` is 50: the evening wrap and the hedge EOD summary run at 15:50.
  - The rest of the system still uses 15:30 in places; NEXT_AGENT_PLAN lists them.
- **O24-PW the trade watch (`partner_watch.py`).**
  - Messages only. Its Kite calls go through the read-only allowlist, which now also allows GET `/quote` and GET `/instruments/historical/{token}/(minute|5minute)` on the partner's key.
  - Jobs:
    - `partner_watch_prompt` at 09:00: the login button, unless a login is held;
    - `partner_watch_tick` every `PARTNER_WATCH_POLL_SEC` (5 s): self-gated on enabled, 09:15–15:40, `is_trading_day` and the partner's login.
  - `on_login` runs in the background from `partner_broker_sync.on_login`. It stores `login:<day>` and, before the close, sends "Trade watch on until 15:40".
  - On a lost login during the session it sends one reconnect button per login.
  - Each tick reads `/orders` (`option_orders` rows). The first read after a login also reads the positions held overnight and the day's cash.
  - Messages are claimed by key in `partner_watch_messages` before sending, so a restart never repeats one. Events from before the first read are never told.
  - The messages:
    - PLAN: the first fill of a round trip, if seen within 5 minutes. `build_plan` sets:
      - the index stop as the F&O engine sets it: the opposite opening-range edge once the 09:15–09:45 range is complete and on the losing side, else 1.5 × ATR(14) of 5-minute futures bars over 21 days, the tighter;
      - that stop priced by Black-76 at the option's implied volatility (`fno_chain.years_to_expiry`), tick-floored;
      - if it is inside the option's swing W (the median 5-minute high–low over the 30 minutes before the buy, from at least 10 one-minute bars), or the index could not be read, the stop is P − W instead;
      - the loss at the stop with charges (`round_trip_costs`) against the day's cash, flagged above a tenth;
      - the target at 1.8 R, priced the same way;
      - facts: W, the rise from the 15-minute low, and the 5-minute EMA 21/50 trend;
      - when they apply: a buy within 30 minutes of a losing exit (and a bigger size), and from the 5th trade the day's count and charges;
      - without market data: the premium at risk and "decide your stop".
    - NO_STOP: 120 s after the buy with no resting SL. A pending sell GTT counts as a stop, and an unreadable GTT list means nothing is claimed.
    - LOWERED: a resting stop's trigger moved down, or cancelled and replaced lower within 20 s. Told the first time in the trip, then only under the plan stop or when it stops guarding the buy price (within 0.5%).
    - REMOVED: a resting stop cancelled with no stop 20 s later.
    - REFUSED: a new rejection, explained by `refusal_plain`.
    - CLOSE: 15:20 with an option held. It says what happens: expiry settlement, MIS square-off, or NRML overnight with theta per day.
  - "Quiet today" (callback `watch:quiet:YYYYMMDD`, handled in `partner_fill_capture.handle_update`) mutes PLAN, NO_STOP and CLOSE for the day.
  - Market data: the partner's own key (`Market`, tried once a day; PermissionException means fallback), else `main.kite` (quotes in the management lane, `get_intraday_by_token`).
  - Every 15 s each open trip's bid, ask, LTP and front future go to `partner_watch_looks` (shadow). Plans are stored in `partner_watch_plans`.
  - The review: `messages_between` puts the sent messages on the matching trade's timeline as "Assistant: …" (who `assistant`; teal on the page and in the PDF). `/partner/review` returns `watch` {on, until, quiet}, and the page shows "Trade watch on until 15:40 …".

## October 23 (evening) — O23 partner review: earlier days, a PDF of the day, what each rule means (actual behavior, Dev, commit `66cfb7c`)

- **O23-PH earlier days.**
  - **Engine `routes_partner_coach.py`.** `_review(day, days)` serves both
    the page and the PDF.
    - The window loaded is the larger of `days` (14–120, default 30) and the
      span back to the asked day.
    - `progress` uses only the last `days` days whichever day is open
      (before, an old day widened it).
    - The response adds `today` (IST date) and `newest`: the open day is
      today or the latest day with a review.
    - `GET /partner/review/days` returns every day with a card or a trade in
      the last 120 days (`REVIEW_HISTORY_DAYS`), newest first.
  - **Wording.**
    - `partner_insights.when(ctx, day)` gives "today" for the analysis
      date's session and "that day" for an earlier one. It is used in
      BIG_RISK ("cash in your account …"), HELD_OVERNIGHT ("It expired …"),
      INSUFFICIENT_FUNDS ("(n refusals …)") and OVERTRADING ("today's" /
      "that day's trades paid").
    - `partner_lessons.day_review(view, day, today=None)` words the headline
      ("No trades that day."), the clean-day line, "At risk … of your cash
      that day" and the read-before-close note ("trades after that are not
      in this review").
    - Without `today` (the evening note) everything reads as before.
  - **Page `PartnerReview.jsx`.**
    - `DayBar`: Earlier / select / Later over `dayList(review days, 120-day
      list, open day)`.
    - The "Today" tab shows the date on an earlier day, and section titles
      come from `dayWords(past)`.
    - Focus shows only when `newest`.
    - Progress "Day by day" rows are buttons that open the day.
  - **What a past day can show.**
    - Zerodha trades exist only for days Zerodha was read (Kite returns only
      the current day's orders).
    - Card paths are frozen at the 15:40 wrap and traded options' 1-minute
      paths are stored, so an old review does not change with the 7-day OI
      purge.
- **O23-PD the day's review as a PDF.**
  - **Engine `partner_review_pdf.py`.**
    - `render_review_pdf(document)` prints, in the page's order:
      - the title and the made-at time;
      - the headline box: P&L, rules kept, the stats line;
      - tomorrow's focus, only when `newest`;
      - the lesson (what / why / better, "Also on this trade", next time);
      - what went well;
      - every other lesson with all its examples;
      - the rules with their meanings;
      - each trade with its check chips, a vector price chart, the option
        lines, the timeline, the result and its mistakes and habits;
      - the orders with their refusals, the cards not taken and the notes.
    - The footer reads "Coaching only. Nothing here places an order." and
      "Page n of m".
    - Number formats match the page: Indian grouping, a true minus,
      `formatRs`, `formatPrice`, `signedPercent` and `minutesLabel`.
    - The chart follows the page's `chartGeometry`: a far level is listed as
      off the chart. Labels sit on small panels and are placed clear of each
      other and of the dots.
    - Fonts: DejaVu Sans from `/usr/share/fonts/truetype/dejavu`
      (fonts-dejavu-core in the image), embedded and subset. Without it the
      built-in Helvetica is used, and `plain()` replaces each character the
      font lacks (₹ → "Rs ", − → "-"), never dropping one.
    - Renders run in a worker thread under one lock (reportlab keeps module
      state). About 0.25 s for the 12-trade Oct 23 day, 11 pages.
  - **Engine route `GET /partner/review/pdf?day=`.**
    - Returns `application/pdf` with `Content-Disposition: attachment;
      filename="trading-review-YYYY-MM-DD.pdf"` and `Cache-Control:
      no-store`.
    - Errors: 422 for a bad day; 503 `pdf_unavailable` when reportlab is
      missing (an image built before O23); 500 `pdf_failed` with a log line.
  - **Gateway `/api/partner-kite/review/pdf`.**
    - Needs a partner or owner session and accepts a day of YYYY-MM-DD only.
      Limiter `reviewPdf` allows 20 a minute; the timeout is 30 s.
    - Only a 200 `application/pdf` is passed on. The file name is used only
      if it matches the fixed pattern, else `trading-review.pdf`.
    - Anything else becomes a fixed JSON error (422 → 400, other → 502).
  - **Gateway `/api/partner-kite/review/days`** has a 20 s timeout.
  - **Page.** "Download PDF" is a same-origin link with `download`. While
    today's Zerodha read is still running it shows "PDF after the update".
- **O23-PM what each rule means.**
  - `partner_lessons.RULE_MEANINGS` gives one plain line per rule. It
    matches the flags that break the rule and their thresholds: 30 minutes,
    5 minutes, a tenth of the cash, 20%, and cards + 1 with three buys.
  - `score()["rules"][i]["means"]` carries the line; the page shows it under
    each rule and so does the PDF.
  - "Traded a card" means the trade was on a card the system sent on
    Telegram that day: the same exchange and symbol, bought at or after the
    card arrived (60 s slack), the same session. A trade on any other option
    is "without a card" (OFF_CARD).

## October 23 — S23 Oct 23 audit fixes: broker-stop identity, one equity charge contract, clean shutdown, terminal retry, iNAV screen, health backlog, telemetry identity, honest reporting (actual behavior, Dev, commit `7e2a2b9`)

- **S23-BS1 a broker stop is found by identity, not shape (live F&O only).**
  - Each backstop intent records its own broker tag (`BSL` + 17 hex, within
    Kite's 20 characters) before the send, and the SL order carries it.
  - When a receipt is lost (`PLACING`/`PLACE_UNKNOWN` without an order id),
    `_find_in_order_book` accepts only the order with that tag and the row's
    symbol, exchange and quantity. If more than one order has the tag, or it
    no longer matches, the lookup is `ambiguous`.
  - With the tag absent from a readable book:
    - another backstop's tag (`BSL…`) belongs to another position;
    - a same-shape order that finished before the intent (2 min clock skew
      allowed) belongs to an earlier position;
    - a same-shape order still working from before the intent, or untagged
      since it, or without a timestamp, is `ambiguous`;
    - otherwise the order is `absent`.
  - Rows written before tags match shape, exchange and quantity, and only
    orders placed after the intent; the same doubt rules apply.
  - `ambiguous` holds the exit and pages once, as before.
  - The Oct 23 audit's reproducer now ends in `proceed`, not `filled`:
    an earlier position's 10:01 COMPLETE stop beside an 11:01 lost send.
- **S23-COST1 one equity charge contract.**
  `equity_charges.charged_as_intraday(product, entry, exit)`:
  - MIS (or none, legacy) is intraday;
  - CNC is intraday when sold in the IST session it was bought, as Zerodha
    charges a same-day CNC round trip;
  - CNC held overnight pays delivery charges.

  The pieces that use it:
  - `engine.calc_zerodha_costs` charges delivery as `calc_penny_costs` does:
    no brokerage, 0.1% STT on both legs, 0.015% buy stamp duty and the
    ₹15.34 DP charge. It used to charge intraday brokerage and stamp, STT on
    the sell only, and no DP.
  - The tracker (`position_tracker.settlement_costs`) settles its
    Penny/EDGE paper books with `calc_penny_costs` and this rule; the
    confirmed EDGE exit and the CNC lifecycle replay use the same rule.
  - Momentum closes use `main._charged_as_intraday(pos)`.

  Example, Oct 22 DCMSRIND (873 shares, 54.30 → 51.5424, same day): ₹48.84;
  booked ₹82.58. On Production's 21 fully closed EDGE/Penny paper positions
  the old tracker over-charged ₹127.79 in all; the ledger is kept as booked.
- **S23-G1 entry gates price full costs.** The `for_gate` bypass is removed;
  it zeroed brokerage, STT and GST in Momentum's `is_cost_viable` and
  `net_ev`, and in the daily swing screener's EV gate (`evaluate_signal`,
  which sends signals to the gateway).
  - Momentum's accepted set does not change: its cost-per-R gate (full
    costs, ≤ 0.12 R) is stricter and already binding.
  - The swing screener now needs its target profit to cover real delivery
    costs (both-leg STT, delivery stamp duty, DP), so marginal small signals
    are no longer emitted.
- **Frozen research and these changes.** The Oct 6 Momentum allocation
  freeze fingerprints `engine.py` and `momentum_exits.py`.
  - It is verified, and its holdout evaluated, at `b03afa5`: the last commit
    whose fingerprint matches.
  - Its intraday costs are unchanged by S23 (a test compares 500 cases with
    the pinned engine).
- **S23-SG clean engine shutdown.**
  - Compose gives the engine `stop_grace_period: 45s`.
  - uvicorn runs with `--timeout-graceful-shutdown 10`.
  - The lifespan shutdown then completes inside the grace: liveness join
    ≤ 10 s, background drain ≤ 5 s, exit-path writer ≤ 5 s, then the
    `clean_shutdown` receipt.
  - A host or VM shutdown is outside this.
- **S23-R1 a second Momentum terminal pass.**
  - `momentum_shadow_terminal_retry` (16:05 Mon–Fri) re-runs the resolver
    with `pass_name=retry` for trades still without a CLOSED event.
  - The intraday cache treats a cache ending before 15:15 as stale, so the
    retry refetches.
  - A CENSORED receipt may become CLOSED, never the reverse.
- **S23-U1 ETF iNAVs are not equities.** `INAV` joins the non-equity
  suffixes, at the refresh screen and at scan time.
- **S23-H1 gateway health and old backlog.**
  - `status` is `degraded` for:
    - an unreachable engine;
    - an open dead letter from the last `HEALTH_BACKLOG_RECENT_HOURS`
      (default 24);
    - an unsynced order from that window;
    - an unsynced order of any age that is not CANCELLED/REJECTED.
  - Older, settled items are reported under `stale_backlog`, with
    `telegram_status=stale_delivery_backlog_present`, until the reviewed
    backlog reconciliation resolves them. The total counts are unchanged.
- **S23-T1 scheduler telemetry identity.**
  - Each wrapped run gets its id before its in-flight marker.
  - If the marker write loses the lock, the completion is inserted under that
    id with the same growing budgets (100/250/500 ms).
  - `INSERT OR IGNORE` plus a summary update only on insert make a replay
    idempotent.
- **S23-M1 login nudge.** The 07:50 message quotes the last successful
  refresh (`/data/daily_bootstrap_timing.json`, written by
  `run_penny_universe_refresh`). Its ask is unchanged.
- **S23-M2 all books in the 16:00 digest.** `day_books.all_books_day` reads
  each book's own store read-only:
  - main ledger settlements by IST date;
  - Smart `EXIT_FILLED` per policy;
  - overnight closes and holdings at entry value.

  The digest labels "Classic Penny" and adds:
  - main, Smart V1 and overnight;
  - their closed subtotal (separate books, not an account or NAV);
  - Smart V2 as a parallel experiment that is never added.

  An unreadable book shows as unavailable, never zero.
- **S23-S1 overnight realism measures.**
  - Book and shadow rows record `entry_bid`/`entry_ask` (displayed) and, at
    the exit, the quote's best bid plus the net had it been sold there
    (`exit_bid`, `exit_bid_net`).
  - The overnight comparison's `realism` reports:
    - `entry_spread_pct`, the displayed spread;
    - `exit_at_bid`, including how far the modelled open-auction exit sits
      above the bid;
    - `entry_at_close`, the same shares bought at the entry day's close.
  - Counterfactuals only. ON_TIGHT_SPREAD is unchanged and is documented as
    a fill-over-LTP limit.
- **S23-Q1** `kite_quote_instrument_partial` names up to 20 missing keys.

## October 22 (evening) — T22-BG background work is held and drained; T22-U the universe refresh reads only usable history (actual behavior, commit `3a9f674`, deployed 2026-10-22 by PR #114)

- **T22-BG fire-and-forget work is held until done.**
  - Found while verifying A22: the full suite passed (5,451) and then the
    process never exited (3.5 h). The cause was a registration-time startup
    catch-up: the EDGE scan between 09:30 and 15:15 IST, the EDGE exit after
    15:15, the accept watchdog after 15:45. It was started with a bare
    `create_task`, and the test's loop closed while the task was inside
    `aiosqlite.connect()`. aiosqlite 0.20's connection worker is a
    non-daemon thread that waits for `close()`, so the interpreter could
    never exit.
  - The same pattern was a Production risk. asyncio holds only a weak
    reference to a task, so an unreferenced one can be collected mid-run.
    Fourteen sites spawned work that way, among them the Penny ledger write
    of realised P&L, `post_login_initialization` (which runs the morning
    bootstrap), the startup catch-ups and the operator alerts.
  - New `background_tasks.spawn(coro, name=, loop=)` holds each task until
    it is done and logs a failure as `background_task_failed name=…`.
    Before, a failed ledger write vanished unlogged. All fourteen sites use
    it. Each site still resolves its loop before it builds the coroutine.
  - Shutdown gives background tasks 2 s to finish, then cancels them and
    waits up to 3 s for them to unwind, before the exit-path writer drains.
    That is at most 5 s, inside Docker's default 10 s stop grace.
    Cancelled names are logged as `background_tasks_cancelled`.
  - Tests: conftest cancels a test's background tasks while its loop is
    still open. At session end it stops any leaked aiosqlite worker and
    prints the count, so a leak can no longer hang a run.
  - **aiosqlite 0.20.0 → 0.21.0.** In 0.20 `_connect` caught only
    `Exception`, so a cancellation while a connection was opening left its
    worker thread waiting forever. Such a cancellation can come from a
    drain or a `wait_for` deadline. 0.21.0 is the maintenance release with
    exactly that fix (#317), and `Connection` is unchanged otherwise.
  - Production showed 17 engine threads after 12 h, so the leak was rare
    there. The pin closes it.
- **T22-U the universe refresh reads daily history only for symbols that can
  enter the universe.**
  - Production 2026-10-22: `penny_universe_refresh` ran 07:51–08:51
    (3,611 s). It read 10,235 histories, of which 6,085 were skipped:
    5,351 empty and 734 short, mostly state-government bonds (`…-SG`).
  - History only fills candidates. So it is now read only for quoted EQ
    symbols inside `PENNY_PRICE_MIN`–`PENNY_PRICE_MAX` that are not
    bonds/ETFs or non-EQ series (`_quote_screen`). The candidate loop uses
    the same screen, so the two cannot drift.
  - New log line `penny_universe_history_scope fetch=… instruments=…`.
  - The written universe is unchanged: it was identical to the previous
    code over 40 randomised instrument sets with bonds, ETFs, SME/BE,
    unquoted symbols, band edges, and empty or short histories.
  - About 956 symbols in Production's daily cache closed inside ₹1–₹55, so
    the refresh should take minutes instead of an hour. That also frees
    Kite's shared 3 req/s history limit before the open, and after it on a
    late-login day.
  - Symbols outside the band are no longer pre-warmed in the daily cache.
    No caller depended on that: a request ending today misses the cache
    until today's candle exists.

## October 22 — A22 audit follow-up: broker-stop safety, short write locks, bounded exit evidence, honest research and partner timing (actual behavior, commit `ffa979c`, deployed 2026-10-22 by PR #114)

The Oct 22 audit of PRs #112–113 (Production 33065ed) reported two order-safety
defects and five follow-ups. Each was reproduced in Dev before the fix, and each
new regression test fails on the previous code:

- **A22-BS broker backstop never allows a second SELL on an uncertain record
  (P1, live only).** `fno_broker_backstop.arm` writes the placement intent
  (`state=PLACING`, trigger, limit; `INSERT OR IGNORE`, so one order per
  position) *before* the SL is sent. If that write fails, nothing is sent:
  the result is `ARM_FAILED`, the operator is paged, and the engine stop still
  acts. If the receipt write fails after the send, the row stays `PLACING`
  without an order id and the operator is paged (`fno_backstop_unrecorded`).
  `load_backstop` now raises `BackstopUnreadable` for any unreadable ledger.
  Only "no such table" (nothing ever recorded) means absent.
  `before_exit` handles uncertain rows as follows:
  - an unreadable ledger holds the exit (paged once);
  - a `PLACING` row younger than 30 s holds (the send may still be in
    flight);
  - an older `PLACING` or `PLACE_UNKNOWN` row is looked up in the order
    book: found means cancel it and read its state; absent means none rests,
    so proceed; an unreadable book holds.

  The passive check adopts a lost order id once the book shows it. Live F&O
  is still off, so this changes no paper behaviour. The unused
  `init_backstop_db` is removed.
- **A22-M2 Momentum terminal pass holds no write lock while fetching.**
  `resolve_momentum_shadow_day` reads the open trades, closes that
  connection, then fetches each ticker's bars with no connection open.
  Each ticker is applied in its own short transaction. A rerun resumes,
  because only trades without a CLOSED event are selected. The audit's
  "database is locked" reproducer is now a test.
- **A22-R6 exit-path recorder is bounded and off the shared executor.**
  - `record()` puts the line on a bounded queue (2,000) and returns
    True/False; it never awaits and never raises.
  - One daemon thread appends batches (≤ 500) through the research archive's
    `guarded_write`: free-space reserve, daily byte budget, cross-process
    lease. The per-session file cap is 32 MiB.
  - Drops are counted by reason: `queue_full`, `day_cap`, `storage`,
    `write_error`. The counts appear in `fno_exit_paths.stats()` and the ops
    snapshot `fno_exit_paths`.
  - Shutdown drains the writer (`close`).
  - Each line now carries `params_sha`, a digest of the live exit settings
    plus `FNO_HARD_FLAT_MIN`. A position's first look of the session also
    carries the full `params`.
- **A22-R3 exit-arm evaluator scores only whole, reconciled evidence.**
  - Arms are overrides on the settings recorded with the looks. CURRENT is
    what was live then, not this process's settings. `LOCK_CONFIRMED` (8 s)
    is added, amended 2026-10-22 before any session was scored.
  - A position is skipped, and counted, when it has no recorded path, a
    contract mismatch, no recorded settings, a settings change mid-trade, a
    path that ends before the live exit, or an observation gap. Gaps mean the
    first look more than 120 s after entry, or more than 120 s between looks.
  - It is also skipped on a `baseline_mismatch`: CURRENT must reproduce the
    stored exit reason, within 20 s, at a premium within 1% or ₹0.10. These
    are listed under `mismatches`; this is the audit's ₹0 underlying_stop
    counterexample.
  - Archive quotes after the live exit are used only up to the first gap
    over 180 s, with a future price no older than 180 s.
  - Totals and `paired.delta_vs_current` count scored positions only. The
    output reports `coverage` and `scope` (exit-only).
  - Lines recorded before this change carry no settings and are reported as
    `settings_unbound`.
- **A22-P4 partner login answers inside the gateway deadline.**
  - `on_login` uses one 35 s deadline: the session exchange (≤ 25 s), then
    the fills.
  - Order histories, positions, cash, option prices and, after the close,
    the coach note continue in a background task with a 120 s budget.
    Overrunning it gives the `partial` state.
  - A fills read that fails inside the deadline is still the login's error.
  - `review_sync()` reports `reading` / `enriching` / `done` / `partial` /
    `failed`, with no token and no broker data. `GET /partner/review` returns
    it as `sync`.
  - The review page shows a one-line status and refreshes every 4 s until
    the state is final.
  - The 15:40 wrap and the owner's sync button still run the whole read
    (`sync_book`).
- **A22-P5 partner coaching never borrows prices from outside the holding.**
  - "Best/worst while you held" uses only 1-minute candles wholly inside the
    holding; for prints, a print time inside it.
  - The buy and sale minutes are reported apart as `edge` (uncertain):
    "In the minute you bought or sold it also traded at …; that may have
    been before your buy or after your sale".
  - A lowered stop's later touch must start after the change and end before
    the sale.
  - The audit's 10-second hold no longer gets the whole minute's range.
- **A22-E1 Smart V1/V2 comparison compares opportunities, not just totals.**
  - `smart_policy_comparison` pairs entries with exits into round trips.
  - Per book it reports fees, median hold, average deployed and rupee-hours
    (capital occupancy).
  - `versus[PEN_SMART_V2]` compares same-day, same-ticker opportunities:
    matched count and net difference, V1 stop-outs where V2 did better, V2
    wider-stop losses, opportunities only one book took, and the winners each
    missed.
  - It is reporting only; no threshold reads it.
- **A22-E2 scope labels.** Standard capital's `method.scope`, shown first on
  the page, says it scales closed trades: open positions are not included,
  and it is neither a whole-portfolio replay nor an exit experiment. The exit
  evaluator states that it is exit-only.
- **A22-E3 version separation (verified, no change).**
  - The expiry book keeps each day's rules version (`day_rules`), and its
    paired comparisons total pre-`RULE_SINCE` entries apart.
  - Smart V2 is scored from 2026-10-22 on its own events.
  - Neither pools an older rule's winners into the new version.

## October 21 (night, 3) — SX-F1 confirmed F&O profit lock + live-clock exit evidence; SX-P2 PEN_SMART_V2 (actual behavior, commit `ace52ab`, deployed: merged by PR #113, running at `582d7a5`)

Owner (Oct 21 night): "take the relevant calls … make it smart, not a
blocking and filtering system". Calls taken, each with its evidence, a
shadow of the old behaviour and a one-line rollback:

- **SX-F1 F&O profit lock waits for a second look (live paper change).** The
  lock (arm 0.4 premium-R, keep half the best gain) was validated on 90 s
  samples (Oct 7 replay, ₹6,041 vs ₹5,323) but live checks the bid every
  10 s. Production since Oct 9: four lock exits at +₹288 to +₹663 (0.1–0.3 R),
  while the two best trades before the lock trailed out at +₹4,711 and
  +₹7,435; Oct 15 live sold at 10:03 for +₹663 where the 90 s replay of the
  same trade trailed out at +₹3,515. `FNO_PROFIT_LOCK_CONFIRM_SEC = 8`: the
  price must still be at/under the floor at a look ≥ 8 s after the first
  (`lock_breach_since`, kept per position in `fno_orchestrator`; a restart
  forgets it, so never an earlier exit). Underlying stop, trail, premium
  backstop and hard flat stay immediate. Thresholds unchanged. Rollback:
  `FNO_PROFIT_LOCK_CONFIRM_SEC=0`.
- **SX-F1 live-clock evidence.** `fno_exit_paths.py` appends every exit look
  of a held option (bid/ask/LTP, future, decision, lock state) to
  `<RESEARCH_ARCHIVE_PATH>/fno_exit_paths/<day>.jsonl` off the exit path
  (never awaited, never raises; `FNO_EXIT_PATH_RECORDING`; since A22-R6 one
  bounded, guarded writer thread with counted drops). The export copies
  finished sessions. `fno_exit_cadence.py` replays declared arms (CURRENT,
  LOCK_FIRST_LOOK = the old lock, FNO_LOCK_OFF, FNO_LOCK_LATE_ARM,
  FNO_LOCK_LOOSE_KEEP) from each live entry on the recorded looks, then on
  the archive's verified quotes after the live exit; still open at the end =
  unresolved. Declared 2026-10-21; judge after ≥ 20 matched trades (since
  A22-R3: scored trades only, see the Oct 22 section). The
  post-Oct-5 archive replay of the lock arms was inconclusive (3 NIFTY
  trades; arms differ on one trade by ≤ ₹400).
- **SX-P2 PEN_SMART_V2 beside V1.** V1's Production record Oct 5–21: 68 closes,
  9 wins, 59 losses, −₹163 on ₹2,000; median stop 0.86% under entry (inside
  a ₹3–50 stock's spread/tick noise), many exits within 0.4–2 min, 33 thesis
  failures after two 1-minute closes; wins only from trails. V2
  (`penny_smart_v2.py`) changes three numbers: `noise_atr_mult` 1.0→1.5,
  `min_noise_pct` 0.004→0.012, `failed_breakout_closes` 2→3 (same code,
  inputs, caps, costs; fewer shares for a wider stop). Own state row,
  events, ₹2,000 paper bankroll and binding (V1's four hashed files plus
  `penny_smart_v2.py`); V1's binding is byte-identical, so V1 sees no
  configuration drift. Scanner and stop monitor run each book in turn with
  its own time budget (V1 first); held names are the union; `/health`-style
  snapshot adds `smart_penny_v2`; `GET /experiments/penny-smart` compares
  closes from 2026-10-22. Setting `PENNY_SMART_V2_ENABLED` (True).
- **Partner cards: no change (call taken).** Five buyer cards since Oct 12
  (all low-end premium reward/risk < 1, a range that is the premium
  estimate's uncertainty, not two targets); the card already warns and its
  target update says book profit and move the SL to entry. Too few cards to
  change a real-money card; the owner reported the partner is happy with
  them; the coach (O21-PX) teaches the management.
- **Expiry book: no promotion yet.** Five expiries; A (+₹3,560) and C (+₹9,004)
  are carried by Oct 13; the owner's 10-expiry review stands.
## October 21 (night, 2) — SX-M1 Momentum shadow scoring excludes missed-exit closes (actual behavior, commit `27ee87b`, deployed: merged by PR #113, running at `582d7a5`)

- Production read-only (Oct 21): 72 of MOM_BASE's 92 virtual closes (88 of
  MOM_RECENCY_5's 108) were `overnight_gap_exit`: the declared 15:15 exit bar
  was never read (fixed forward by S21-R1's terminal pass), so the close
  measured the overnight gap, not the variant.
- `momentum_shadow_comparison` now scores only rule exits; it adds
  `scored_closes`, `missed_time_exit_closes`, `missed_time_exit_net_pnl` and a
  warning. `promotion_readiness` counts `scored_closes` (when present) for its
  closed-trades sample gate. `closed_trades` keeps its meaning (all closes).
## October 21 (night) — O21-PX the partner's deeper review (actual behavior, commit `68eec28`, deployed: merged by PR #113, running at `582d7a5`)

Owner (Oct 21 night, after merging PR #112): after the day's ending brief the
partner gets one message with the review link, the link goes to the Zerodha
login and the login lands on the review; "improve the feedback ... from
whatever available resources the API can provide ... ensure that the review
dashboard becomes even better". Coaching only: nothing places an order,
blocks a card or changes card text.

- **One review link every trading day.** `partner_eod_wrap` (15:40): the brief,
  then `partner_broker_eod` (read the book if a login is held, else the
  prompt), then `partner_coach_eod`, then `ensure_review_message`: when the
  coach note (whose button is the same login) was not delivered, the prompt
  "📒 Review your day (Mon 19 Oct)" goes out (once a day). Before, a login held
  since the morning on a day without trades meant no link at all.
- **More from the partner's Zerodha app (read-only).** The allowlist adds GET
  `/portfolio/positions`, GET `/user/margins/equity` and GET `/orders/<numeric
  id>` (one order's history). Placing (POST /orders/{variety}), modifying
  (PUT) and cancelling (DELETE /orders/{variety}/{id}) still cannot match.
  `sync_book` keeps, best effort (a failed part never fails the read):
  `partner_orders` (every option order, status, Zerodha's rejection text),
  `partner_order_changes` (price/trigger changes of orders Kite marks
  `modified`, from confirmed history states; at most 40 per read),
  `partner_broker_positions` and `partner_account_days` (opening balance +
  intraday pay-in = the day's cash; read only from the open).
- **The traded options' prices (`partner_trade_paths.py`).** After a read of a
  finished day, each option the partner bought or sold gets the session's
  1-minute candles from the owner's market data
  (`get_intraday_by_token(..., "minute")`, token from the morning books),
  else the analytics tick's 5-minute prints (`5MIN_PRINTS`, retried on the
  next read). At most 12 contracts, 8 s each, 20 s a day. Table
  `partner_trade_paths`. The gateway's login wait is 45 s (was 30 s).
- **Round trips (`partner_coach.round_trips`).** One option's fills split where
  the position is flat again. Before, a stop-out and a re-buy of the same
  option was one trade ("added to a losing option") and the re-entry was
  invisible. A card's later round trip is its own item (`reentry`,
  checked against the same card); an off-card one is its own trade. Summary
  `card_reentries`; "only the card trades" excludes re-entries.
- **New lessons (`partner_insights.py`, each with what/why/better/rule):**
  `CHASED_SPIKE` (off-card, 1-minute candles: up ≥ 20% in the 15 minutes
  before the buy and within 5% of the day's high so far; told, not priced),
  `GAVE_BACK_PROFIT` (off-card: up ≥ 20% while held, closed under the entry;
  priced with the stop moved to the entry, 3% slippage), `STOP_LOWERED` (an
  SL order moved down while held; priced at the original level when the
  option traded there), `PRICE_RAISED_TO_FILL` (≥ 2 raises or ≥ 5%; on a card
  only past its buy-up-to), `BIG_RISK` (> 10% of the day's cash at risk: to
  the partner's stop; the premium without one; the card's SL when stops are
  unknown on a card trade; priced with the lots that fit), `HELD_OVERNIGHT`
  (off-card, open at the close, confirmed by positions when read),
  `INSUFFICIENT_FUNDS` (day: a buy refused for money), `ENTRY_UNDER_STOP` (a
  card trade bought at or under the card's SL: the card's idea had failed,
  plan = skip, and no "sell at the SL" advice). Positives `CUT_LOSS_SAVED`
  (30 minutes after a losing exit the option was ≥ 15% lower) and
  `STOP_TRAILED`. Hindsight only shows what happened and praises a
  disciplined exit; it never says to hold a loser.
- **Per trade (`insight`):** hold time, best and worst price while held (open
  ₹), the run before the buy, the price 30 minutes after the sale, money at
  risk against the day's cash, gross move and charges, order changes and
  refusals in the timeline (ordered to the second), and a chart (1-minute
  closes, buys/sells, card buy-up-to/SL/target and the partner's stop).
- **The review (`partner_lessons.py`).** Rules kept: each trade checked on six
  rules (card, entry, stop — only when stops are known or a stop moved —
  exit, calm after a loss, size) plus the day's own (only the cards; orders
  within the cash when the book was read); the score counts process, not
  money. Day numbers (wins, losses, charges, time in the market, the day as a
  share of the cash). The lesson of the day folds at most 3 other mistakes
  on its trades; the rest stay as their own lessons. Progress adds the window
  statistics (win rate, average win/loss, per trade, charges, card against
  no-card, within 30 minutes of a loss, median hold of winners against
  losers, four time-of-day buckets) with one plain line per pattern (≥ 3
  trades a side) and "Tomorrow, focus on one thing": the rule broken most in
  the last 7 days. The Telegram note's headline adds "rules kept k/n".
- **Dashboard (`PartnerReview.jsx`).** Today: headline with rules kept,
  wins/losses, charges, time in the market and the share of the account;
  the focus card; the lesson; rules kept; each trade with its rule checks, an
  SVG price chart (`chartGeometry`; a far level is listed, not drawn) and
  "what the option did" lines; the day's orders with refusals. Progress: the
  statistics, "what your numbers say", where the results came from, and
  rules kept per day.
## October 21 (late) — Oct 21 audit fixes and the overnight book's forward shadows (actual behavior, commit `462d28f`, deployed: merged by PR #112, running at `582d7a5`)

Owner (Oct 21): act on the Oct 21 Production audit
(`Production_Trading-sentinel/docs/2026-10-21-production-deep-audit.md`):
fix what it found, and add shadows where a better approach is supported.
No live strategy rule, sizing, Smart policy file, expiry rule or live
switch changed; everything below is a bug fix, telemetry, or research.

- **S21-R1 Momentum shadow terminal pass.** Virtual trades advanced only on
  a later scan's bars; scans run 10:15–14:45, so the declared 15:15 time
  exit never arrived (Oct 21: 9 of 13 MOM_RS_PULLBACK trades unresolved).
  Job `momentum_shadow_terminal` (15:32 IST, Mon–Fri, trading days,
  `MOMENTUM_SHADOW_ENABLED`) fetches each open ticker's completed 15-minute
  bars for the session and calls `resolve_momentum_shadow_day`. Bars after
  the 15:15 bar are not passed; the usual stop/target/time-exit rules decide
  (the time exit uses only the 15:15 open). Table
  `momentum_shadow_terminal_receipts`: CLOSED or CENSORED with why
  (`fetch_failed:<Class>`, `no_terminal_bar`); a later pass may close a
  censored trade, never the reverse. The comparison adds `censored_trades`.
- **S21-R2 RS_PULLBACK identity.** The RS variant's config now carries
  `rules` (`rs_pullback_rules()`: every constant and sizing setting, version
  `rs_pullback_v1`) and `momentum_pool`; its fingerprint also hashes the
  index bars the rule could see (`rs_index_known`) and the daily bars (ATR
  floor). A different index or constant gives a different identity. The
  other variants' configs and fingerprints are byte-identical.
- **S21-R3 Overnight replay parity.** On the `EDGE_OVERNIGHT_RUNTIME` arm the
  replay now measures the quarter-of-plan dust floor against the plan capped
  at an equal share of equity, with the pick's share of free cash, as the
  runtime does (`edge_overnight_paper`). The audit's counterexample (₹25,000,
  3 slots, plan 2,000 at 20.05) now fills 414 (runtime 415; the 0.2% buffer).
  Other replay arms are unchanged.
- **S21-E1 EDGE entry-day event check.** `_run_one_leg` re-checks
  `event_block(ticker, entry date)` before each admission (skip reason
  `entry_day_event_window: ...`). The scan's signal-date check stays.
- **S21-L1 Restart overlap.** `startup_receipt` writes `market_overlap_sec`
  over trading sessions only (`is_trading_day_sync` per day; an unreadable
  calendar counts the weekday) and keeps the raw weekday figure as
  `weekday_overlap_sec`. Oct 19 night → Oct 21 pre-market: 0 (was 22,500 s).
- **R21-M1 EDGE signal rows and the zero-accept alarm.** Candidates were
  logged against the live leg, which is off by design, so all 96 read
  `not_selected_by_live_leg` and the alarm said "unsatisfiable gate". Each
  row now carries the real outcome (`edge_candidate_outcome`): accepted if
  either leg entered it; else the per-ticker refusal (paper first), or
  `rank_not_selected`. The watchdog leaves `rank_not_selected` out of the
  dead-gate test (`NOT_A_GATE`, shown as "Not a gate (selection by design)"),
  says "the last N evaluation day(s)" (not "consecutive"), and words a
  dominant gate as a check to make, not a verdict.
- **R21-M2 F&O hourly.** `allocation=` and `equity=` (`division_equity`:
  allocation + realised P&L) replace `pool=`.
- **O19-M1 follow-up.** `_notify_momentum_heartbeat` returns whether the
  gateway accepted it; the hour's slot is set only then, so a failed send is
  retried by the next silent scan that hour.
- **T21-X Transport kinds.** `transport_error_kind` adds `pool_timeout` (this
  process's own pool, not the provider), `read`, `write`, `protocol`, and
  `other:<ExceptionClass>` instead of a bare `other`.
- **O21-ON Overnight forward shadows (`edge_overnight_paper.py`).** From
  Production's own record (16 trades with a recorded split): close→open
  +₹986.97 (about +0.77% a trade), entry spread paid at the ask −₹462.11
  (about 0.36%; 15:20→close drift only −₹108.41 with mixed signs), delivery
  charges about ₹33 a trade (about 0.42% at ₹8k; the DP charge is fixed per
  scrip): the edge is real and the costs take it. Two shadows were declared
  on 2026-10-21 before any scoring (`OVERNIGHT_SHADOWS`):
  - `ON_TWO_LARGER`: two equal positions of half the book each
    (`fill_cash_share`), so the fixed DP charge weighs less per rupee;
  - `ON_TIGHT_SPREAD`: the book's sizing, but a pick filled more than 0.35%
    above LTP is refused (`entry_cost_above_limit`, no slot used).
  The admission loop moved into `_admit` (the book calls it with its exact
  previous behaviour); each shadow calls it with its declared fields on the
  same ranked picks, re-quote and decision time, with its own cash
  (`EDGE_OVERNIGHT_PAPER_BANKROLL` + its realised P&L, `shadow_state`).
  Exits use the same quotes and `_price_exit` (EXIT phase and same-day
  retries). Table `edge_overnight_shadow_trades`; the ENTRY summary gains a
  compact `shadows` key; the book's notices are unchanged. Read-only
  `GET /experiments/edge-overnight` compares each shadow with the book on
  the same nights (closed, net, PF, average net, charges, average entry cost
  %, average position value). Setting `EDGE_OVERNIGHT_SHADOWS_ENABLED`
  (True).

## October 21 (night) — the partner's own review page; lessons that explain each mistake (actual behavior, commit `6f882f0`, deployed: merged by PR #112, running at `582d7a5`)

Owner (Oct 21): the partner logs in from the Telegram button and lands on
their own dashboard, a branch of the main one, opening on the day's
learnings; more is there if they want it. The lessons must be top quality,
comprehensive, correct and well tested, so the partner understands each
mistake and what would have been better. Owner's decision (Oct 21 night): the
partner's app is a separate app in the owner's developer account with the
partner's client ID; the partner is the owner's parent, immediate family
under Zerodha's static-IP rule (spouse, dependent children, dependent
parents), declared when the IPs were whitelisted. Reads do not need the IP. Built on O21-PK below. No strategy rule, card
text or gate, sizing, Smart policy file or live switch changed.

- **Each mistake explained (`partner_coach.py`, O21-PL).** Every flag now
  carries `reason` (what happened, times and prices), `why` (why it matters,
  with this trade's numbers), `better` + `better_pnl` (the better action and
  what it would have paid after charges) and `advice` (the rule).
  `impact_rs` = actual − better (was mixed; ENTRY_ABOVE_LIMIT was the extra
  premium paid). What-ifs on the same position are charged for the same
  number of orders (`_pnl(..., orders)`), so an extra order's brokerage never
  shows up as a behaviour cost. Examples:
  - chased entry: the stop-out loss from the partner's price against the
    card's limit (e.g. ₹1,506 instead of ₹1,153 on 20 qty, 31% more) and the
    room left to the first target; "skip it: ₹0 instead of −₹2,268"; when a
    5-minute print came back inside the limit before the skip-after time, "or
    wait with a limit order at ₹522.35: it traded at ₹518 at 12:15";
  - held past the stop: when the option first printed under the SL, and the
    result of an SL order at the card's price;
  - revenge re-entry: the earlier loss, the minutes between, the two trades
    together; size-up: per-₹1 exposure and the same trade at the old size;
    averaged down: the result with only the first buy; early exit, gave back
    after target, held past square-off: the card's exit priced on the
    partner's entry; overtrading: the day's charges and the cards-only day.
  - A rule-break that made money says "It made +₹X this time; the rule is
    about the risk taken, not about this result" and stays a lesson.
- **Stop discipline (Zerodha days).** The read now also takes GET
  `/gtt/triggers` (allowlisted; no GTT or order write path).
  `partner_stop_orders` keeps every SL / SL-M SELL order on an option and
  every sell GTT that protects (an OCO's lower leg; a single trigger set
  below the price at creation; a single one above it is a target).
  `partner_broker_days.stops_known` is set only when the GTT list was read.
  On complete days with stops known: NO_STOP_ORDER (held ≥ 5 min with no SL
  order or GTT placed from 60 s before the buy), STOP_WIDER_THAN_CARD (> 3%
  under the card SL; priced when it fired), STOP_CANCELLED (cancelled before
  the exit and before 15:15, no new stop after it, sold > 1% under it).
  Positives: STOP_PLACED (within 5 min of the buy, not later cancelled),
  EXITED_BEFORE_STOP, PAUSED_AFTER_LOSS (> 30 min after a loss, then a card).
  Unknown stops: nothing is said about stops.
- **Card plan fix.** A card whose first print after delivery was already at
  or under its SL is "card said skip" (₹0), not an entry under its own stop.
- **The day review (`partner_lessons.py`).** `day_review(view, day)`:
  headline ("2 trades · −₹5,345 after charges · following the cards exactly:
  ₹0 · 1 without a card"); the lesson of the day = the costliest group of
  the same mistake, ties by `LESSON_PRIORITY` (revenge and size first, then
  entries breaking the card, then stops); mistakes on the same trade fold
  into it as "also on this trade" (one revenge trade is one story); up to 4
  more lessons; what went well (CLEAN_DAY when every trade followed its
  card); each trade as a time-ordered story (card, buys, stops placed and
  cancelled, the card's SL being reached, card messages, sells, result);
  cards not taken, neutrally ("Not taking a card is always allowed"); data
  notes (taps are estimates; a read before the close; stops unknown; 5-minute
  prices). `progress(view, today)`: per pattern this week against last week
  with a trend, trades that followed their card, clean-day streak, per-day
  rows. `render_note` writes the evening Telegram note from the same review:
  headline, "Lesson:", "Better:", "Next time:", ✅ habits, at most six lines.
- **Route and pages.** Engine GET `/partner/review?day=&days=` (internal
  secret; default today, else the latest day with a card or trade; window
  14–120 days). Gateway GET `/api/partner-kite/review` (partner or owner
  session; day YYYY-MM-DD only). The Zerodha login now lands on
  `/?view=review`. Client `PartnerReview.jsx` is the partner's dashboard:
  "Today" (headline, lesson of the day with what/why/better/rule, what went
  well, more to learn, trades step by step, cards not taken, notes), then
  "Progress" and "All details" (the coach page, read-only). The owner opens
  it from the Coach page ("Partner's view"); the owner's flags also show the
  why and better lines.

## October 21 (evening) — the partner's Zerodha fills read once a day, coach-only review page (actual behavior, commit `9648f95`, deployed: merged by PR #112, running at `582d7a5`)

Owner (Oct 21): the partner will not log entries during the day; fetch their
orders from the free API and let them open the dashboard only at the end of
the day for the learnings. Built on O21-PC (afternoon section below). No
strategy rule, card text, card gate, book sizing, Smart policy file or live
switch changed; nothing places, modifies or cancels an order.

- **The partner's own app.** Kite Connect "Personal" (free) gives order and
  portfolio APIs but no market data; the order book can be read from any IP
  (the exchange static-IP rule covers API order endpoints only). The partner
  app is a separate app in the owner's developer account with the partner's
  client ID (owner's decision; the partner is the owner's parent) and
  redirect URL `<public URL>/api/partner-kite/callback`. Reads need no
  static IP; the code has no order path. Settings (root `.env`, read by the engine): `PARTNER_KITE_API_KEY`,
  `PARTNER_KITE_API_SECRET`, `PARTNER_KITE_USER_ID` (all three, else off),
  `PARTNER_KITE_BASE_URL` (`https://api.kite.trade`, direct, not the relay),
  `PARTNER_ZERODHA_SYNC_ENABLED` (True). Tests pin the three keys empty
  (`tests/conftest.py`) so real keys in the repo `.env` change nothing.
- **Evening flow (`partner_broker_sync.py`, O21-PK).**
  - `partner_eod_wrap` (15:40) calls `partner_broker_eod` before the coach:
    with a login held it reads the book; otherwise it sends one message per
    day (`partner_messages` kind `zerodha_prompt`) with a URL button
    "📒 Open today's review" = the Kite login link
    (`https://kite.zerodha.com/connect/login?v=3&api_key=...`).
  - Kite redirects to the gateway callback with a one-time `request_token`;
    the gateway POSTs it to `/partner/broker/session`. `create_session`
    exchanges it (checksum SHA-256 of key + token + secret), refuses any
    `user_id` other than `PARTNER_KITE_USER_ID` (and logs that token out),
    and keeps the access token in memory only until 06:00 IST (Kite's
    expiry). It never reaches a log line, the DB or a response; accounts are
    shown masked (`AB***34`).
  - `sync_book` reads GET `/orders` and `/trades` (if `/trades` is refused,
    each order's own average price and exchange time are used). `_kite_call`
    allows only POST/DELETE `/session/token`, GET `/orders`, GET `/trades`;
    anything else raises `not_allowed` before a request is built. A
    `TokenException` drops the session.
  - One report per filled NFO/BFO option order into `partner_trade_reports`:
    `source` ZERODHA, `price_basis` BROKER_FILL (quantity-weighted average of
    the order's trades), `trade_at` the first fill's exchange time
    (EXCHANGE_FILL), lots = quantity / lot size (instrument book, else the
    card; a quantity that is not whole lots is scored as units with a note).
    Partly filled then cancelled orders count their filled part. Rejected or
    unfilled orders, equity and futures are counted, not stored.
    `dedup_key` `kite:<order_id>`; a re-read refreshes the same row (an order
    that filled more); a row the owner voided stays voided.
  - Card matching: a BUY belongs to the latest card for the same Kite symbol
    and exchange sent before it (60 s clock slack); a SELL to the latest such
    card still holding quantity, else the latest such card; anything else is
    off-card (contract read from the symbol, e.g. `NIFTY25O2122950PE`).
  - `partner_broker_days` records each read: `complete` once a read happened
    at or after 15:30 IST that day. An empty book before 09:15 records
    nothing.
  - `on_login`: session, read, and after the close the coach note
    (`partner_coach_eod`). A login before the close is kept, and the 15:40
    wrap reads the final book with no tap.
- **Coach on Zerodha days (`partner_coach.py`).** On a day read from
  Zerodha, Telegram and dashboard BUY/SELL reports up to the read time (the
  whole day once complete) are ignored (`zerodha_first`;
  `data_quality.superseded_by_zerodha`). SKIP taps stay. On a complete day
  a card with no order is NOT_TRADED (counted in `cards_not_traded`, earns
  "Skipping saved money" when the card lost); before a complete read it
  stays NOT_REPORTED. With Zerodha configured the evening note waits for a
  complete read (`awaiting_zerodha`), says "(from Zerodha)", and carries an
  "📒 Open full review" button. The view carries `zerodha` (configured,
  connected, masked account, per-day reads; never the token).
- **Card buttons.** With Zerodha configured, cards and exit updates go out
  without the Bought/Skipped/Sold buttons (`PARTNER_FILL_BUTTONS_WITH_ZERODHA`
  False); typed replies still record. Without Zerodha nothing changes.
- **Gateway and review page.** `server/routes/partner-kite.js`: GET
  `/api/partner-kite/callback` (callback rate limiter; fixed-text pages
  only; success sets `req.session.partner_view`, never `authenticated`, and
  redirects to `/?view=coach`); GET `/api/partner-kite/coach?days=` (1–120,
  partner or owner session; the only route a partner session opens). Every
  `/api/proxy`, `/api/orders`, `/api/token` route still needs
  `authenticated`. `/api/auth/status` adds `partner_view`. Owner proxy: POST
  `/api/proxy/partner/broker/sync` (re-read while a login is held). Engine
  routes: POST `/partner/broker/session`, GET `/partner/broker/status`, POST
  `/partner/broker/sync` (internal secret; errors are a `code` only). The
  client opens `PartnerCoach partnerView` for a partner-only session: title
  "Your trading review", default Today, no report form, no remove, no
  navigation; Zerodha fills show "from Zerodha" and cannot be removed. The
  owner's page shows a Zerodha status line and "Re-read Zerodha".
- **Owner login guard (gateway `routes/auth.js`).** The owner's
  `/api/auth/callback` never checked which Zerodha account logged in. Now
  that the partner opens the dashboard URL, a partner whose review session
  expired could press the Login page's Zerodha button. If Zerodha allowed
  that account on the owner's app, its token would have become the system
  token with an owner session. The callback now reads the account
  (`generateSessionWithUser`) and refuses `PARTNER_KITE_USER_ID`, or every
  account but `ZERODHA_USER_ID` when that is set. Both are in
  `node-gateway/.env`, which is separate from the engine's root `.env`. A
  refused login stores, provisions and authenticates nothing and redirects
  to `/login?error=wrong_account`. With neither set the callback is
  unchanged.

## October 21 (afternoon) — partner fill capture and coach, standard-capital view, F&O broker backstop (actual behavior, commit `b580af2`, deployed: merged by PR #112, running at `582d7a5`)

Owner (Oct 21): before real money, standardise every book on one capital
(₹2L / ₹5L) and scale down later; a broker-side stop for live F&O; capture
the partner's real fills and add a coaching dashboard so the manual partner
can learn from FOMO and revenge trades. Host reliability (UPS or cloud VM)
is the owner's call and is not done. No strategy rule, card text, card gate,
book sizing, Smart policy file or live switch changed.

- **Partner fill capture (O21-PC, `partner_fill_capture.py`).** Until now
  `partner_positions` and `partner_advisory_feedback` had 0 rows.
  - Entry cards (`manual_market_advisory`) carry inline buttons Bought 1 lot
    / 2 lots / Skipped; exit-type updates (INVALIDATION, TARGET_ZONE,
    SESSION_EXIT_REMINDER) carry Sold all / Sold 1 lot. `keyboard_for(kind,
    detail)` is called in `hedge_advisory._send_claimed_review`; the text and
    every gate are unchanged. `send_partner_result(..., reply_markup=)`.
  - Job `partner_inbox_tick` (interval `PARTNER_INBOX_POLL_SEC` 20 s,
    09:00–21:00 IST any day) long-polls `getUpdates`
    (`PARTNER_INBOX_LONG_POLL_SEC` 15) on the partner bot, offset in
    `partner_inbox_state`; a failed poll (409 webhook, network) backs off 10
    min. Only `PARTNER_TELEGRAM_CHAT_ID` is read.
  - A tap records the option's ask (buy) / bid (sell) from one
    management-lane quote (`ASK_AT_TAP` / `BID_AT_TAP`, shown "≈"), market
    hours only; a double tap within 10 s is one tap. The card's buttons then
    show the recorded state, with Undo.
  - A reply to a card or update records or corrects in the partner's words:
    "518.5", "b 518.5 x2", "s 560 @14:42", "skip", "undo"
    (`parse_report_text`). A bare price within 30 min of a Bought/Sold tap
    replaces the estimate (`PARTNER_STATED`, the old row VOIDED). Off-card:
    "b NIFTY 22950 PE 120 x2" (or "/b ..." in a group). Bad input gets one
    help line per 10 minutes; ordinary chat is ignored. Reactions (👍)
    acknowledge typed reports.
  - Table `partner_trade_reports` (append-only, `dedup_key` per Telegram
    update, status ACTIVE/VOIDED). No price is ever taken from the card.
- **Partner coach (`partner_coach.py`).** Per delivered buyer card: the
  partner's fills and P&L after charges; "card exits on your entry" (premium
  SL order, the 5-minute print `PARTNER_COACH_REACTION_SEC` = 120 s after an
  exit/target/square-off message, else the exit-by print); the card plan
  (a chased, late or after-close entry was a skip on the card: ₹0). Flags
  with the numbers that fired them and a fixed "next time" line:
  ENTRY_ABOVE_LIMIT (FOMO), LATE_ENTRY, AFTER_CARD_CLOSED, OFF_CARD,
  QUICK_REENTRY_AFTER_LOSS (≤ 30 min, revenge pattern), SIZE_UP_AFTER_LOSS,
  AVERAGED_DOWN, HELD_PAST_STOP (> 3% under the SL, or > 10 min after the
  exit message), EARLY_EXIT, GAVE_BACK_AFTER_TARGET, HELD_PAST_SQUARE_OFF,
  OVERTRADING (day). Positives: bought inside the limit, exited with the
  card, a skip that saved money. Leaks are ranked by rupee effect (they
  overlap). `partner_eod_wrap` calls `partner_coach_eod`: it freezes the
  day's card price paths (`partner_coach_card_paths`, past the 7-day OI
  purge) and, when the partner reported a trade, sends a note of at most six
  lines (`PARTNER_COACH_NOTE_ENABLED`, dedup `partner_messages` kind
  `coach`). Coaching never blocks a card or a trade.
- **Standard capital (O21-SC, `standard_capital.py`).** Replays each book's
  own closed paper trades on one capital S (default `STANDARD_CAPITAL_INR`
  ₹2L, any ₹1k–₹1cr): units = round(book units × S / reference) in whole
  lots/shares (0 = too small, skipped and counted); own cash only (sized
  down or skipped); charges recomputed at the new size (real F&O/equity
  schedules where prices are stored, else flat ₹20/order kept fixed);
  `since` scores the current version of a book. References: F&O single and
  spreads `FNO_PAPER_BANKROLL`; expiry 3 × `EXPIRY_PAPER_BUDGET` /
  `FNO_MAX_RISK_PCT` = ₹3.75L (its peak cash, ~₹9k, would scale it 22×);
  overnight, Momentum, Penny, EDGE morning their paper bankrolls. Identity:
  at its own reference a book's replay equals its own net P&L unless it held
  more than its pool at once (flagged; Momentum MIS). Penny rows closed
  since September store shares=0: sized from `PENNY_PER_STOCK_CAP` (noted).
  EDGE morning positions hold 9 of the ledger's 19 closes (noted). An 8-byte
  blob price (numpy int64, VPRPL Aug 11) is decoded. Production trial
  (read-only, Oct 21): at own references F&O single −₹23,012.32, spreads
  −₹189.95, expiry +₹2,567.95, overnight −₹991.05 reproduce the books; since
  Sep 1 at ₹2L each: spreads +₹7,238.41 (3.62%, DD 0.52%), single
  +₹3,764.84 (1.88%), Momentum +₹702.81, overnight −₹5,780.76 (×8 flagged);
  at ₹10k/₹12.5k every F&O trade is too small.
- **F&O broker backstop (O21-BS, `fno_broker_backstop.py`).** After a LIVE
  single-leg fill the orchestrator calls `arm()`: one SELL SL (stop-limit,
  MIS, `intent="exit"`, never halt-blocked) at trigger = fill × (1 −
  `FNO_STOP_PREMIUM_PCT` − `FNO_BACKSTOP_EXTRA_PCT` 0.10), limit 10% under
  (`FNO_BACKSTOP_LIMIT_GAP_PCT`, clamped to NSE circular 54/2023 OPTIDX
  range: ₹10 up to a ₹50 trigger, else 20%). Table `fno_broker_backstops`.
  Before any engine exit `before_exit()` cancels and re-reads it: cancelled
  unfilled → exit as before; fully filled → booked as the exit
  (`broker_backstop`, no order sent); part-filled → sells only the rest;
  unprovable → nothing sold, paged once (no exit intent claimed). While no
  exit is due `check_filled()` re-reads each minute, every tick within 2% of
  the trigger. PLACE_UNKNOWN (since A22-BS also a lost-receipt PLACING row) is resolved
  from `orders_snapshot`. Paper never
  places one; `REENTRY_STOP_REASONS` includes `broker_backstop`. The live
  leg is still behind `FNO_DISABLE_LIVE` and the go-live bar.
- **Routes and dashboard.** Engine `routes_partner_coach.py`: GET
  `/partner/coach?days=`, POST `/partner/coach/reports`, POST
  `/partner/coach/reports/{id}/void`, GET
  `/performance/standard-capital?capital=&since=` (internal secret). Gateway
  proxies them under `/api/proxy/` (void id digits only). Client pages
  Partner Coach and Standard Capital, buttons on the dashboard.
- **Deployment drift corrected.** `d12bb1d` and its docs commit `e5621f7`
  were deployed by PR #111 (merge `2fc12ee`, Oct 20 22:56 IST; engine image
  built 22:59 IST; the running container has the `before_date` scan fix,
  checked Oct 21). `a88da98` (expiry-v3) was not merged: the container runs
  `RULES_VERSION = "expiry-v2"`.

## October 21 — expiry-v3: B takes BP's pair target; expiry-shadow-v5 (BL, CI) and Oct 19 expiry-audit fixes (actual behavior, commit `a88da98`, deployed: merged by PR #112, running at `582d7a5`)

Audit: Production `docs/2026-10-19-expiry-system-deep-audit.md` (first expiry
on v2). Owner order: apply the fixes, keep observing, and promote a shadow that
keeps beating its main (the main becomes a shadow). Design, the five-expiry
evidence table and honesty notes are in
`docs/2026-10-05-expiry-day-paper-book.md`, section "expiry-v3". Execution
(`expiry-exec-v2`), A, C, D, the budgets and the owner's 10-expiry rule are
unchanged.

- **B (main, `RULES_VERSION = expiry-v3`).** `POLICIES["B"]` is the hold
  policy and `PAIR_PLAYS = (B, BP)`: both legs are sold together
  (`PAIR_TARGET`, 0.20) once the pair's liquidation net after all charges
  reaches 20% of the premium paid; else held into the auction and sold from
  15:38 if bid. Why: BP − B was +₹768.77, +₹1,507.51 (replays), ₹0.00 and
  +₹722.46 (forward) on the four expiries B traded, never worse. B's buy
  notice says "both sold once the pair nets 20% after fees, else held into the
  auction".
- **Shadows (`SHADOW_VERSION = expiry-shadow-v5`).** `SHADOW_PLAYS = BH, C500,
  D, AL, BR, CH, BL, CI`; `RETIRED_PLAYS = CX, BP` (no new entries, history
  prints).
  - **BL** = v2's B (`POLICIES["BL"]`: bank half at ×2, trail 65%, 80% from
    15:30), paired with B. **BR** = BL plus its 50% leg stop.
  - **CI** = C sold once the index is back inside the box at all
    (`STRUCTURE_BACK["CI"] = 0.0`; A, AL, C and CX keep 0.25), paired with C.
    In-sample CI − C +₹2,429.99 over five expiries; scored only forward.
  - AE (A after a second buffer) was replayed and not added (−₹167.32 against
    A in-sample).
- **Fixes (Oct 19 audit X-1–X-5).**
  - X-1: the 15:38 sale does fill a leg with a bid (ITM legs were bid to
    15:39:50 on all five expiries); worthless legs have no bids and settle at
    zero. Settlement events store `intrinsic`; the summary labels settled legs
    "(worthless)" or "(intrinsic x)".
  - X-2: `_record_tick` counts a fresh index equal to the previous one in
    `state["index_unchanged"]` (before/from 15:15, longest run before 15:15,
    last change) and as a third `window_ticks` element. The summary prints
    "index unchanged from the previous tick: …". `update_realized` stops at
    15:15 (`CONTEXT_VERSION = expiry-context-v1.2`).
  - X-3: `RULE_SINCE = {A: 1, B: 3, C: 2}` and `day_rules()`. The owner
    per-play tally adds "since expiry-vN a/b Rs x" when a record spans a rule
    change. Paired lines total entries from before the primary's rule apart
    ("before B's expiry-v3 rule …"). A mixed day counts as the version it
    began under.
  - X-4: sell lines are composed after every leg has moved; a strangle leg
    says "leg closed", names the open partner and gives the whole trade's net.
  - X-5: a `FAILED_BREAK` event stores `index` and `line`; the sell line
    prints both.
- **Rules version per day.** A day begun under older rules is marked
  "expiry-v2+expiry-v3 from mid-day" (B's open legs would then switch to the
  pair rule; deploy after the session).
- **Verification.** A replay of the five retained Production expiries through
  Dev (scratch `xv5/replay_all.py`, `compare.py`):
  - before the change, 0 row mismatches on Oct 8, 13 and 19 (Oct 6 and 15
    differ only where v2's C replaced v1's);
  - after it, every existing row and event is identical except that B's rows
    equal the old BP rows and BL's equal the old B rows; the only new rows
    are CI's.
  - main book in-sample under v3: −₹1,285.60 / −₹1,427.00 / +₹13,780.74 /
    −₹954.88 / −₹1,357.93 = +₹8,755.33 (v2 +₹5,756.59; as run +₹2,567.95).
    Still 4 losing expiries of 5. In-sample, not evidence of profit.

## October 19 — Oct 19 audit fixes: EDGE morning scan, partner pacing, Smart marks, overnight split, Momentum/F&O shadows (actual behavior, Dev, commit `d12bb1d`)

Source: `Production_Trading-sentinel/docs/2026-10-19-production-deep-audit.md`
(first full session on PR #110). Expiry items are not in this slice.

- **EDGE morning scan scored today's unfinished bar (O19-E1).** The 09:20
  `run_screener` daily fetch caches today's partial candle for ~500 NIFTY 500
  names, so `penny_edge_live.scan_today` ("newest cached date") scored date =
  today with only those names (Oct 16/19 logs: `date=<today> universe=499`,
  482 `price_out_of_range`): zero EDGE candidates since late September. The
  orchestrator now passes `before_date=<IST today>` and the scan scores the
  newest date strictly before it (the last completed session, ~940 band names
  refreshed by the pre-open penny-universe fetch). `as_of_date` callers and
  the 15:20 overnight scan are unchanged.
- **Partner update pacing (O19-P1).** `dispatch_queued_management_update`
  spaced every card's updates by one shared 1-minute gap on a 1-minute tick,
  so tick jitter allowed one update per 2 minutes across all cards (Oct 19:
  15:10/15:12/15:14). Now `MANAGEMENT_UPDATE_GAP` = 45 s per card
  (`gap_counts` by `advisory_id`); the daily cap (4) counts target/
  invalidation updates only and the `SESSION_EXIT_REMINDER` (one per card) is
  never refused by it (`cap_counts`). `hedge_advisory._claim` /
  `_send_claimed_review` gained the optional `gap_counts`/`cap_counts`
  selectors (default: every delivered row of the kind, as before). Pending
  updates are dispatched oldest observation first. Message wording unchanged.
- **Unsendable cards expire (O19-P2).** `run_intraday_session_lifecycle`
  marks a QUEUED card past its entry deadline (or from an earlier session)
  `EXPIRED_UNSENT`, so the dashboard stops offering it (`can_send`).
- **Smart Penny held marks and halt reasons (O19-S1/S2).** The frozen book
  halts all entries while a held position has no executable quote, and the
  scanner quoted only the surviving universe. The scanner now adds Smart's
  held names (`penny_smart_shadow.smart_held_tickers`) to its one quote batch.
  `_explain_halts` replaces the merged `regime_or_missing_marks_or_daily_loss`
  with the condition(s) (`configuration_drift`, `entries_not_allowed`,
  `held_mark_unavailable` + `unmarked`, `daily_loss_latched`) and drops the
  halt from exit-only stop-monitor batches (most of Oct 19's 235). The hashed
  Smart policy files (`penny_smart_policy/book.py`, `adaptive_penny_policy.py`,
  `penny_prices.py`) are untouched: editing them is binding drift that stops
  Smart entries for good (test guards it).
- **Overnight cash split (O19-O1).** `edge_overnight_paper.run_overnight_entry`
  caps each pick at the free cash / open slots (cash a smaller pick leaves
  passes on); the quarter-of-plan dust floor is measured against the plan
  capped at equity / slots, so the cap never refuses a pick. Oct 19 KMSUGAR
  took 50% of the book. `edge_portfolio_replay` EDGE_OVERNIGHT_RUNTIME mirrors
  it (`split_cash`).
- **F&O profit-lock shadow arms (O19-F1).** `fno_policy_replay` arms
  `FNO_LOCK_LATE_ARM` (arm 0.8R), `FNO_LOCK_LOOSE_KEEP` (keep 25%),
  `FNO_LOCK_OFF`, each the live ladder at fast-exit cadence with one lock
  change; compare with `CURRENT`. Frozen before scoring. On the seen Sep 10 –
  Oct 7 archive all four equal CURRENT (11 closes, +Rs 6,919.53): the lock
  armed on 4 legs but never fired. Scoring needs post-Oct-7 NIFTY sessions
  (Oct 15 lock exit); SENSEX single-leg (Oct 19) is not replayable. No live
  change.
- **MOM_RS_PULLBACK shadow (O19-M2).** `momentum_rs_pullback.rs_pullback_signal`:
  stock up on the session and >= 0.75% above NIFTY's session return, >= 60%
  of earlier bars closed above VWAP, a dip to VWAP (0.3%) reclaimed on the
  last bar (close > VWAP and prior close, upper-half close, volume >= 1.2x the
  prior 8 bars), 10:15-14:15; shipped stop floors, regime R target/risk and
  pool cap. Registered in `momentum_shadow.VARIANTS` (old variants' configs
  and fingerprints unchanged) and `momentum_replay.VARIANTS`; lab adapter
  1.2.0. Simulation runner job `momentum-pullback`. Shadow evidence only.
- **Smaller.** Bootstrap runs `fno_instruments` before `penny_universe`
  (O19-B1: Oct 19 F&O readiness waited to 08:51). Momentum's silent-scan
  heartbeat goes out on the first silent scan of each clock hour (O19-M1: 19
  of 46 owner messages). Plan/checklist receipts for `a6d820d`/`5458d2d` now
  read "deployed by PR #110".
- **Not changed.** No threshold of a live strategy; the Smart −1% daily
  latch and F&O quarter sizing stay. Same-day-expiry DR spreads (T-3) are the
  owner's decision. The telemetry writer already retries and replays (4
  locked writes, none lost).

## October 18 — simulation-report fixes: replays answer like the runtime (actual behavior, Dev, commit `a0a3fd8`)

Source: the Oct 13 current-strategy simulation
(`docs/research/simulation/2026-10-18-oct13-current-7238676/REPORT.md`).
Research tooling only; no runtime strategy, threshold or config changed.

- **F&O replay expiry calendar (O18-F1).** `fno_policy_replay` asked the
  series one quote batch carried; a batch without the 0DTE series turned
  Oct 13 into a regular day and bought the next series (the simulation's
  INVALID -Rs 2,269.70). The replay now uses a dated calendar, as the runtime
  asks `FnoInstruments`: every NIFTY option expiry the archive ever quoted
  (`ReplayData.option_expiries()`: the export manifest's `option_expiries`,
  else one archive scan). `is_expiry_day` and the traded expiry come from it;
  a batch without that expiry's quotes is
  `chain_unavailable:calendar_expiry_not_archived` (never a substitute
  series). Results carry `expiry_calendar` (source, expiry days in window).
  `scripts/export_fno_replay_dataset.py` writes `option_expiries` per
  underlying. New arm `CURRENT` (`resolve_policy`) follows the live switches
  (`FNO_FAST_EXIT_ENABLED` → ~60 s management; research-only arms off).
  Real archive: Oct 13 CURRENT → 0 trades, the 3 fired candidates refused
  (2 calendar series not archived in that batch, 1 `expiry_day_block`);
  Oct 14 → 0 signals (only 94 archived batches that day).
- **Classic Penny paper-exit parity (O18-P1).** Runtime PENNY_PAPER exits
  fill at reference × (1 − 1%), tick-floored (`PennyExecutor.execute_exit`,
  PAPER_LIMIT_FLOOR_V1); the replay filled at the reference. Lifecycle v5:
  `PennyLifecycleConfig.paper_exit_fill="RUNTIME_LIMIT_FLOOR"` (default) floors
  every PENNY_PAPER market exit to INR 0.01 and records
  `exit_reference_price`; resting partial legs and the PENNY broker book are
  unchanged; `REFERENCE` reproduces pre-v5 receipts. Lab adapter 1.4.0
  exposes it. Oct 13 UNITEDPOLY: REFERENCE −Rs 10.5226 (the simulation's
  figure, reproduced); runtime fill 51.56 → 51.04, −Rs 14.68 (Production's
  own fill was 50.97 from LTP 51.49).
- **EDGE overnight runtime arm (O18-E1).** `EDGE_OVERNIGHT` was the Oct 5
  study arm (3-deep scan, no realism rules). `EDGE_OVERNIGHT_RUNTIME` ranks
  `RANK_DEPTH` (10) deep, fills `PENNY_EDGE_MAX_POSITIONS` slots in rank
  order and replaces a pick the runtime would refuse on its daily bar.
  `edge_overnight_paper.realism_refusal` is split into `series_refusal`
  (SME / duplicate series / weak kind) and `day_high_refusal` (close at the
  high after ≥ 1.9%), called by both runtime and replay; runtime reasons and
  order are unchanged. Quote-only refusals (circuit, depth, staleness) are
  not visible in daily bars. Lab adapter 1.3.0. Oct 13: 4 `MR_mid` picks
  refused, OPTIFIN bought.
- **Simulation runner (O18-R1..R3).** `scripts/backtest_all_yahoo.py`:
  - new lifecycle jobs `edge-portfolio` (BASELINE at
    `PENNY_EDGE_PAPER_BANKROLL`), `edge-overnight` (EDGE_OVERNIGHT_RUNTIME at
    `EDGE_OVERNIGHT_PAPER_BANKROLL`), `swing-portfolio`, `range-portfolio`
    (declared research defaults): entry-to-exit P&L with marked equity,
    beside the entry-only evaluators;
  - daily bars are fetched for a bounded tail after `--end`
    (`daily_tail_end`: the job's `tail_days`, never an unfinished session)
    into `validated-yahoo-tail.sqlite`, read only by these jobs; every other
    job keeps the bounded snapshot;
  - reports are entry-dated: next-open books start one session early
    (`signal_window`, `entry_window` in the receipt); open positions at the
    tail end are `open_marked`, not sold;
  - `penny-smart` runs PEN_SMART_TRADER at `PENNY_SMART_SHADOW_BANKROLL`
    (with the gap-sensitivity diagnostic); `momentum` runs the configured
    gate (MOM_SELECTIVE while `MOMENTUM_SELECTIVE_ENTRY_ENABLED`),
    LIVE_EXIT_LIFECYCLE, NEXT_BAR_OPEN and reuses the 15-minute NIFTY 50
    probe as its index context (validated apart: `intraday_context`).
  The simulation needed hand-written scripts for both.
  Oct 13 smoke on the simulation's snapshot (no tail yet): Swing fired 9
  (= evaluator), filled 1 (Rs 4,500 book); Range 4 closed −Rs 309.86; EDGE
  baseline 1 closed +Rs 220.44, 1 open.
- **Not changed.** No strategy threshold was tuned on Oct 13: it is a seen
  day, Penny minute data was partial and Smart Penny's 5 trades total
  −Rs 8.74. The replays now measure what the runtime would do, so the Oct 13
  rerun and the Oct 14 run can show which modules earn.

## October 15 — expiry-v2: C takes CX's failed-break exit; expiry-shadow-v4 and Oct 15 expiry-audit fixes (actual behavior, commit `5458d2d`, deployed by PR #110)

Audit: Production `docs/2026-10-15-expiry-system-deep-audit.md`. The owner
ordered that a shadow which worked should replace its main play. Design, the
per-shadow evidence table and honesty notes are in
`docs/2026-10-05-expiry-day-paper-book.md`, section "expiry-v2". Execution
(`expiry-exec-v2`), context (`expiry-context-v1.1`), A, B, the budgets and
the owner's 10-expiry rule are unchanged.

- **C (main, `RULES_VERSION = expiry-v2`).** C is now in `STRUCTURE_PLAYS`
  (A, AL, C, CX). Its ticket is sold (`FAILED_BREAK`) when A's frozen
  failed-break test fires; otherwise C's v1 entry, sizing, bank, trail and
  15:38 flat apply. Why: CX − C was +₹1,170.10, ₹0, ₹0 on the seen Oct 6/8/13
  replays and +₹2,018.54 on the first forward expiry (Oct 15). It was never
  worse. C's buy notice says "sold if the break fails, else held into the
  auction". Its failed-break sell is a main-book Telegram line.
- **CH (shadow, `SHADOW_VERSION = expiry-shadow-v4`).** expiry-v1's C (held,
  no failed-break exit), on C's entry, with `POLICIES["CH"] = POLICIES["C"]`.
  CH − C keeps scoring the promotion. **CX** is in `RETIRED_PLAYS`: no new
  entries, but its rows still print in the shadow section (when present), the
  to-date line and the owner tally. Not promoted: AL (−₹4,914.29 against A on
  Oct 13), BP and BR (no forward entry yet; Oct 15's outage emptied the B
  window).
- **Rules version per day.** `_load_state` marks a day begun under older rules
  as "expiry-v1+expiry-v2 from mid-day", once. The summary header prints the
  day's own rules (it used to print the module constant).
- **Entry-window coverage.** `ENTRY_WINDOWS` (box 13:00–13:30, A/C
  13:30–15:05, D 14:30–14:45, B 15:13:30–15:15). `_record_tick` keeps
  `state["window_ticks"][name] = [fresh index, ticks]`. The summary prints
  "window ticks with a fresh index: box n of N, A/C …, D …, B …" (absent on
  older days).
- **Paired comparisons bound per entry.** `paired_lines` groups legs by
  (day, play, entry_ts). A shadow entry pairs only with the primary entry
  with the same clock and the same legs (symbol, side, lots, entry price).
  It prints "over n entries on m expiries", plus "k not the same entry" and
  "k still open" when they occur. C500 stays excluded.
- **Context labels.** `_moment` prints "D window 14:30:00, read …" and "B
  window 15:13:30, read …"; the label never implies a trade.
- **Verification.** A scratch replay of the four retained Production expiries
  (Oct 6/8/13/15) through Dev produced:
  - before the change, 0 row mismatches on all four days;
  - after it, the only differences are C's rows. C now finishes as CX did:
    −₹986.46 / −₹2,138.48 / +₹10,288.54 / −₹281.00, total +₹6,882.60.
    CH reproduces v1 C: −₹2,156.56 / −₹2,138.48 / +₹10,288.54 / −₹2,299.54,
    total +₹3,693.96. Oct 15 has no CX row (retired).
  - main book, in-sample: +₹7,836.98 under v2 against +₹4,648.34 under v1.
    Still 3 losing expiries of 4.
  - the Oct 15 summary prints "B 0 of 9" and CH−C −₹2,018.54, in 2 parts of
    3,416 and 1,145 UTF-16 units.

## October 15 (evening) — Oct 15 audit fixes: outage pages, unsent-retry, held restart page, historical gate (actual behavior, Dev, commit `a6d820d`)

Audit: `Production_Trading-sentinel/docs/2026-10-15-production-deep-audit.md`
(Production on PR #109 / `4e5836e`). Expiry findings belong to the expiry
book and are not touched here.

- **Provider outage visibility (O15-N1).** `EndpointBudget` now counts calls
  that got no HTTP answer per endpoint and kind (`dns`, `connect`,
  `connect_timeout`, `timeout`, `other`; `transport_error_kind`), shown as
  `transport_errors` beside `http_errors` on `/ops/provider-budget`. The
  first such failure opens an outage; the next provider answer (any status)
  closes it (`connectivity()`: current + last 20). Quote and historical
  paths feed it. Oct 15 14:57–15:15 had 154 quote failures while
  `http_errors` read `{}`.
- **Outage pages.** The 60 s scheduler tick calls
  `lifecycle_receipts.provider_outage_alerts` on trading days. An outage with
  ≥ 5 failures and ≥ 120 s of market-hours overlap queues one "Market data
  down since HH:MM" page (with open exposure per book, unknown ≠ flat) and,
  when it ends, one "Market data back" page with the window and counts. The
  end page retires an undelivered start page (`SUPERSEDED`). Both go
  through the acknowledged restart-alert outbox (same retries/backoff).
  Nothing is priced or filled from data seen after the window.
- **Restart page for a held book (O15-R1).** A market-hours restart now
  pages from 60 s of overlap when any book is open or unreadable; a flat
  book keeps the 300 s bar. Oct 15's 168 s host restart with a NIFTY spread
  held paged nobody. Gaps under 10 min are shown with one decimal.
- **Historical send gate (O15-H1).** `SendWindowGate(limit=3,
  window_sec=1.05)` sits right before every historical HTTP send (three call
  sites), after the shared limiter, like the quote `before_send` gate. Oct
  15 recorded a historical peak of 4/s (documented 3/s) and one 504. Waits
  show as `historical_gate_waits`.
- **Partner sends that never connected (O15-M1).** `partner_bot` returns
  `unsent_connect` for `httpx.ConnectError` / `ConnectTimeout` (DNS,
  refused, connect timeout): no byte left the process. `_fail_claim` makes
  that an ordinary `retry_scheduled` (+30 s, `unsent_proven`), still bounded
  by the claim's validity, the management observation age (360 s) and
  `PARTNER_HEDGE_DELIVERY_MAX_ATTEMPTS`. Read timeouts and other transport
  errors stay ambiguous → manual recovery (no duplicate). Oct 15's 15:10
  square-off reminder failed this way and expired unsent.
- **Buyer wrap honesty (O15-B2 and the 15:15 residual).**
  `partner_buyer.premium_path(..., exit_by=)`: the held path ends at the
  card's management deadline (payload `management_deadline`, else the
  configured 15:15), so later prints are not the card's result; the last
  held print carries its own time ("₹177.25 at 14:57 before the 15:15
  exit"). Before a stop, a sample within 10 min reads "₹X at HH:MM, just
  before the stop"; an older one reads "last seen ₹X at HH:MM; no price seen
  near the stop". No exit price is made up.
- **EDGE catch-up wait (S15-R1).** `run_edge_catchup` bounds the token wait
  in elapsed time on `now_fn` (a late wake no longer stretches it), and
  still stops after the nominal poll count if the clock does not move. The
  15:15 cutoff checks are unchanged.
- **Late notices dated (O15-D2).** An overnight notice delivered on a later
  day is sent as "[Wed 14 Oct, delivered late] …"; the stored row is
  unchanged.

## October 15 — expiry-shadow-v3 (CX, BR) and Oct 13 expiry-audit diagnostics (actual behavior, commit `db6e028`, deployed by PR #109)

Audit: Production `docs/2026-10-13-expiry-system-deep-audit.md`. Design and
honesty notes: `docs/2026-10-05-expiry-day-paper-book.md`, section
"expiry-shadow-v3". Primary rules (`expiry-v1`), the execution contract
(`expiry-exec-v2`), the context (`expiry-context-v1.1`), Telegram trade
lines and the owner's 10-expiry rule are unchanged.

- **CX (shadow).** CX takes C's entry, sizing, ceiling, bank and trail. Its
  ticket is also sold (`FAILED_BREAK`) when A's frozen failed-break test fires
  (`STRUCTURE_PLAYS = A, AL, CX`). It buys one ticket a day.
- **BR (shadow).** BR takes B's strangle, bank and trail. Each leg is also
  sold once its bid is down `BR_LEG_STOP = 0.50` of entry: `POLICIES["BR"]`
  is B with `hard_stop=0.50`, and it exits through `manage_position`'s STOP.
  Stops inside 15:15–15:40 are AUCTION_WINDOW fills (unverified).
- **Paired comparison.** `PAIRED_WITH` maps each shadow to its primary.
  `paired_lines` prints shadow − primary whole modeled, today and to date for
  this underlying, over expiries where both traded. C500 is excluded (its
  difference is size, not management).
- **Mark denominators.** `_mark_paths` keeps `held` and `unmarked` (per-leg
  reasons from `unmarkable_legs`: `NO_QUOTE`, `STALE`/`AHEAD`/`NO_TIMESTAMP`,
  `NO_BID`/`NO_ASK`, `THIN`). The summary prints "n of N held ticks marked;
  unmarked legs: …", or "never marked". Day states from before this change
  print the old "(n marks)".
- **Context availability.** `count_context_fields` keeps per-field tick
  counts in `state["context_fields"]`. The context block prints "available on
  ticks (of N): OK, straddle, IV, realized, IV/RV, PCR, future build-up,
  every OI quote fresh".
- **Owner tally.** Each play shows whole modeled rupees to date beside its
  losing/traded count. The rule and verdict are unchanged.
- **Verification.** A scratch replay of the retained Production packets for
  Oct 6, 8 and 13 through Dev reproduced every Production row with zero
  mismatches. The new diagnostics equal the audit's independent counts
  (B 95/159 marked, NO_BID 64/63; D 352/420; context 903/900/837 of 966).
  In-sample shadow results, not evidence: CX −₹986.46 / −₹2,138.48 /
  +₹10,288.54 against C −₹2,156.56 / −₹2,138.48 / +₹10,288.54; BR −₹396.84 /
  −₹1,242.41 / −₹1,097.85 against B −₹846.83 / −₹720.75 / −₹1,894.03. The
  Oct 13 summary grows to 5,374 UTF-16 units, which is 2 acknowledged parts.

## October 15 — second review R1/R2 (actual behavior, Dev, commit `934aa2c`)

Review: `docs/2026-10-15-oct13-fixes-second-review.md` (on the F1–F5 tree).

- **EDGE cutoff inside the batch (R1).** `_run_one_leg(…, entry_cutoff=,
  now_fn=)` re-checks the 15:15 cutoff before every admission. A slow
  earlier fill can no longer carry the batch past 15:15: the remaining
  candidates are skipped `after-entry-cutoff`. A fill already accepted is
  recorded and managed as usual. Live EDGE entries stay fail-closed, so the
  per-admission check is the last gate before the paper fill. Manual and
  replay callers pass no cutoff.
- **Restart outbox race (R2).** Every outbox change is reload → change one
  row → save, with no await in between (`_update_alert`), and queuing is a
  synchronous append. A page queued while another page's send is in flight
  is kept and sent by the next tick. Before, the stale whole-list save
  dropped it. Delivery stays at-least-once.

## October 15 — independent review F1–F5 of the Oct 13 fixes (actual behavior, Dev, commit `ec1d5a2`)

Review: `docs/2026-10-15-oct13-fixes-independent-review.md` (on `433a81a`).

- **EDGE cutoff (F1).** `penny_edge_orchestrator.run_edge_catchup` waits
  (bounded) for the restored token, but re-reads the clock after the wait:
  at or after `EDGE_ENTRY_CUTOFF` (15:15 IST, the exit pass) it does not
  scan. Scheduled scans call `run_penny_edge_scan(…, entry_cutoff=15:15)`,
  which checks the cutoff before the signal pass and again at the entry
  boundary, so a scan that crosses 15:15 enters nothing (`AFTER_CUTOFF`).
  Manual and replay callers pass no cutoff, so their behaviour is unchanged.
- **EDGE completion (F2).** Every scan result now has a `status`:
  `COMPLETED`, `ERROR`, `DISABLED` or `AFTER_CUTOFF`. Only `COMPLETED` writes
  the atomic receipt `penny_edge_scan_state.json` ({date, status,
  completed_at, counts}); a valid zero-candidate day counts as completed.
  The cron and the catch-up share one `asyncio.Lock`, and both check the
  receipt under it. An error, disabled legs or the cutoff leave the day
  recoverable; a torn or old-format receipt reads as not completed.
- **Wrap after a later stop (F3).** `_todays_card_outcomes` keeps
  first-event scoring and also carries `stop_at`, the first INVALIDATION. A
  card that went target → stop → recovery reads "🎯 target hit 11:40, 🛑
  stopped 11:45", and its held premium path ends at the stop.
- **Restart page (F4).**
  - `lifecycle_receipts.open_exposure_counts` reads every book read-only:
    F&O singles and spreads, equity/Penny/EDGE, overnight, expiry and
    Smart. A missing store or table counts 0; any other read failure is
    `None` and shows as "unknown", never flat.
  - The page goes into `restart_alert_outbox.json`, one id per boot. It is
    sent with `require_delivery` and counts only when the gateway confirms
    `delivered: true`. A 422 is final; anything else retries (30 s
    doubling to 10 min, 20 attempts, 6 h max) from the 60 s scheduler tick
    under one lock. The attempt is persisted before each send.
  - Delivery is at-least-once: a lost acknowledgement can repeat a page.
  - The wording names a *likely* cause, since a clock step can look like a
    host sleep.
- **Hourly Penny fill (F5).** The fill is joined by identity: signal
  (scan_id, ticker, leg) → `penny_execution_events` `CANDIDATE_ACCEPTED`
  attempt → `positions.penny_attempt_id`. With no attempt, several
  attempts, or no position, the line reads "signal 52.92, fill n/a"; a fill
  is never guessed from ticker and hour. Checked on Production (read-only):
  Oct 13 UNITEDPOLY signal `penny-01ac0535` → attempt `pen-ae2e…` → 51.92.
  Exit events reuse the scan id under `-exit-N` attempt ids, so only the
  entry attempt is matched.

## October 13 — Oct 13 audit fixes: terminal buyer ideas, quote send gate, exchange fees, restart receipts (actual behavior, Dev, commit `433a81a`)

Source: `Production_Trading-sentinel/docs/2026-10-13-production-deep-audit.md`
(Oct 13 clean session, PR #108). Expiry items are owned by the expiry agent
and are not touched here.

- **Buyer ideas end at their stop (O13-B1, P1).** Oct 13: both delivered
  cards got "EXIT … Idea closed" at 11:45, then "Book profit; move SL to your
  entry price" for the same ideas at 14:40/14:50. Now:
  - queuing an `INVALIDATION` sets the idea to `CLOSED_INVALIDATED` in the
    same transaction;
  - `queue_management_updates` and `run_intraday_session_lifecycle` only
    work on `DELIVERED_ACKNOWLEDGED` ideas, so no later target or reminder;
  - `_close_invalidated_ideas` closes older rows that already have a stop;
  - `pending_management_updates` still sends the stop itself, and expires a
    queued target as `idea_closed_invalidated`;
  - the final authorizer (`hedge_advisory._authorize_dispatch`, phase
    `manual_update_v1`) refuses any non-stop update once a stop is
    recorded for the idea.
  A fresh setup after a stop is a new card with a new identity (re-entry
  levels unchanged). Diagnostics and the blocker report count
  `CLOSED_INVALIDATED` and `RETIRED_SESSION_END` as delivered.
- **Wrap after a stop (O13-B1/B4).** `partner_buyer.premium_path(…,
  stopped_at=)` ends the held path at the stop and shows the later peak as
  "after exit (not held)". No event reads "no level seen (5-min samples)",
  not "no level hit".
- **Buyer fallback.** If the priced view is missing or will not render, the
  card is `BUYER_VIEW_FALLBACK_V1`: the same BUY leg, levels on the future,
  limit ask + 2 %, "premium stop not priced, size small". The two-leg card,
  which has a SELL leg, is never sent to the buyer. If even that fails, the
  idea stays a shadow (`buyer_view_unavailable`).
- **Flow pulse failures (O13-B2).** `partner_messages(flow_pulse)` detail
  now holds `count` (delivered), `failed` and `last_delivered_at`. The
  30-minute gap and the 6-a-day cap count delivered pulses only. A failed
  send retries after `PULSE_RETRY_MIN` = 5 minutes, at most
  `PULSE_MAX_FAILED_ATTEMPTS` = 12 failures a day. Facts still commit only
  on delivery.
- **Exchange fees (O13-B3).** `fno_costs.calc_fno_costs(…, exchange=)` and
  `options_exchange_for(underlying)` (SENSEX → BFO). Used by the single-leg
  exit cost and admission reserve (`fno_orchestrator`), the position fee
  reserve (`fno_positions._with_entry_baselines`), the buyer loss-at-SL and
  `fee_segment`, the protection card estimate and the F&O shadow scenario.
  Oct 13 same-fill check: call 42 ₹62.2894 (NSE) vs ₹61.8421 (BSE); card
  ₹1,691.07 vs ₹1,690.74. Recorded ledger rows are not repriced.
- **Quote send gate (O13-Q1).** `QuoteBudget.before_send()` runs right
  before the endpoint counter and the HTTP call, on every attempt (merged
  batches, retries, keyed calls), and holds a send until ≥ 1/rate + 2 ms
  after the previous send. Admission also waits for the last real send.
  The Oct 13 over-limit came from a batch task that started late after
  admission. New counter: `send_gate_waits`.
- **Dispatcher cancellation (O13-Q2).** `_dispatch` wraps the loop: if it is
  cancelled or fails while waiting for admission, every queued caller gets
  `QuoteBatchCancelled` (or the error). Counter: `cancelled_queued`. One
  caller cancelling does not affect others.
- **Restart receipts (O13-R1).** New `lifecycle_receipts.py`, writing to
  `lifecycle_events.jsonl` beside the DB:
  - the heartbeat thread records `host_suspend` (wall clock ran ahead of
    monotonic) and `thread_stall`;
  - a graceful shutdown flags `scheduler_tick.json` with `clean_shutdown`;
  - startup writes a receipt: gap, market-hours overlap, prior shutdown
    flag, host/VM uptime, cause (`clean_shutdown`,
    `host_or_vm_restarted`, `unclean_stop`);
  - a gap over 5 market minutes on a trading day pages the operator with
    the open positions per book.
  Nothing is backfilled or traded for the gap.
- **Penny reports.**
  - Daily attribution reads R from the settled position row (ledger notes
    never carry `r=`). Oct 13 printed "Avg R: 0.0" for a −3.72R stop; a day
    with no known R now prints "n/a".
  - The hourly report shows the paper fill, plus the signal close when they
    differ (Oct 13 showed 52.92 for a 51.92 fill).
- **Penny paper exit provenance (O13-P1).** The paper exit result and the
  `EXIT_SIMULATED` event carry `reference_price`, `fill_model`
  (`PAPER_LIMIT_FLOOR_V1`), `slip_pct` and `model_decrement_per_share`. The
  fill model itself is unchanged: ref × 0.99, tick-floored. Changing it
  would need a frozen comparison.
- **EDGE startup catch-up.** Jobs register before the token is restored, so
  the Oct 13 11:40 catch-up skipped (`no_access_token`). It now waits up to
  10 minutes for the token. It also does nothing when today's scan already
  completed: `penny_edge_scan_state.json` is written after a scan returns.
- **Liquidity filter.** Universe names missing from a usable (≥ 1,000
  symbol) catalogue drop in one `liquidity_filter_unlisted_symbols` line, not
  one warning each. Oct 13 had 54 warnings: HEG, HFCL (now `HFCL-BE`) and
  JBCHEPHARM.

## October 12 (night) — option-buyer card numbers verified on Production data (O12-PB2, actual behavior, Dev, commit `feed23e`)

Owner: the partner trades real money, so the card's numbers must be the most
correct the system can produce. Every number was checked read-only against
Production records. The changes in `partner_buyer.py` (`BUYER_VIEW_V2`):

- **Index conversion confirmed, and essential.** Oct 8 SENSEX futures traded
  330–430 points over the index. The parity-forward estimate against the
  real index (184 tick samples): median error +0.4 points, mean absolute
  16 points, p90 31. Averaging 3 or 5 strikes did not help: the scatter is
  index-print timing.
- **Premium model calibrated.** Black-76 at the entry implied volatility was
  replayed on 41,950 later NIFTY/SENSEX snapshot pairs (Oct 5–12). Real
  premiums ran below the model, more so with time (median −7% after 3 h).
  With `PREMIUM_DECAY_MINUTES` = 60 priced in:
  - target-like moves: median 0.0% (NIFTY) and −1.7% (SENSEX);
  - stop-like moves: −3.4% and −4.1%, so the premium stop fires slightly
    early (toward a smaller loss).
- **Target is a range** (`TARGET_PREMIUM_LOW_FACTOR` 0.85). Bulk p10 was
  −13.6% / −11.9%. When the index reached target, the Oct 6/8/9 cards'
  options were 10%, 14% and 15% under the model; each got there later.
  "Reward < risk" is judged on the low end.
- **"Loss at SL ≈₹X/lot"** runs from the buy-up-to limit down to the premium
  stop, plus one current spread and round-trip charges (`fno_costs`). It
  replaces "Risk ≈" from the ask, and is shown at the exact stop price
  (`₹73.25`, not a rounded `₹73`). It is not called a maximum, because fast
  falls fill below the trigger (Oct 7: ₹166 → ₹158 between 5-minute prints).
- **The stop line now reads "SL order at ₹X right after buying (or exit if
  <index> ≈Y breaks)".** On the Oct 7 14:00 card the premium stop (₹158.4)
  traded at 14:02. The index stop was confirmed on the 14:30 bar, with the
  put at ₹117 (about ₹3,700 a lot worse).
- **A stop within `NEAR_STOP_PCT` (5%) of the ask is flagged** "skip or tiny
  size". The Oct 7 13:11 card had its stop ₹3.25 under ₹169.65.
- **Target update:** "move SL to your entry price" (the partner's own fill),
  not the card's ask. The brief and pulse say "near-money PCR": it is
  computed over ±15 strikes, not NSE's whole chain.
- **Replay of the five delivered Oct 6–9 cards:**
  - every published level matched what happened;
  - the premium stop protected each losing card;
  - 4 of 5 cards now carry "reward < risk". The signals' 1.5R index targets
    are often under 1R in premium at the low end. That is a property of
    the signal, now shown to the partner, not hidden.

## October 12 (evening) — partner messages for an option buyer (`PARTNER_BUYER_MESSAGES`, on) (actual behavior, Dev, commit `304ad70`)

Owner: the partner no longer hedges and only buys options, and the messages
could not be read in market time. Production (read-only, Oct 6–12):
- each advice card was a 1,646–1,676 character debit-spread card with a
  30-second "Valid until";
- updates were 283–295 characters about "the paired structure";
- intraday OI alerts were suppressed by the dormant hedge bot. Earlier they
  arrived as separate lines, up to five in one minute (two the same PCR read).

The advice pipeline is unchanged: signal, validation, economic identity,
caps (2 cards, 4 updates a day), dispatch gates, re-entry rule, lifecycle,
research capture and the 2-minute cadence. Only the text differs.

- **Entry card (`partner_buyer.buyer_plan` / `render_buyer_card`).**
  - It names the spread's BUY leg as a single option to buy.
  - Lines: the PURE ADVICE label (still required by `_authorize_dispatch`);
    `BUY NIFTY 22550 CE (13 Oct) @ ₹97.35`; a buy-up-to limit; the skip time;
    stop and target; risk per lot; the exit time; one line of why. About 300
    characters.
  - Buy limit: ask + 15% of the premium stop distance, capped at ask + 4%,
    rounded up to the tick (+2% when no premium stop could be modelled).
  - Skip after quote time + `PARTNER_BUYER_ENTRY_WINDOW_MIN` (10), capped at
    the entry deadline.
  - Premiums at the stop and target are Black-76 estimates at the option's
    mid implied volatility, shown in whole rupees with "≈" on the target.
    On Oct 9 the constant-volatility target estimate was about ₹147 against
    an actual ₹125.
  - The card warns "reward < risk in premium" when the modelled reward is
    smaller than the modelled risk.
  - `payload.buyer_view` stores every number. `advisory_id` and
    `economic_version` are unchanged (a test proves it).
- **Levels on the index.**
  - The signal reads front-month futures bars. On Oct 9 the future was about
    60 points over the index, more than that card's 47-point stop.
  - Levels shift by future − spot, where spot is the chain's parity forward
    discounted by `RISK_FREE_RATE`. They are shown as `NIFTY ≈22,417`.
  - With no parity forward, or a gap above 2%, levels stay on the future and
    say `fut`.
- **Updates (one line each).**
  - `🛑 EXIT NIFTY 22550 CE now: stop level hit (NIFTY ≈22,412 at 13:50).`
  - `🎯 … target reached (…). Book profit; on anything you keep, move SL to
    ₹97.35 (cost).`
  - `⏰ … square off by 15:15. No overnight hold.`
  - Ideas without a `buyer_view` keep the old wording.
- **Morning brief (09:50).**
  - `PARTNER_BUYER_INDICES` (NIFTY, SENSEX) only.
  - Per index: index level, CE-above and PE-below break levels (index terms),
    then premium read, expiry note, OI walls and PCR.
  - It also carries the crisis line and the event calendar note.
- **OI flow pulse (analytics tick, buyer indices).**
  - One message per index replaces the separate PCR, IV, wall and wall-flow
    alerts. It uses the same thresholds and is sent when a fact is new,
    at most every `PARTNER_EVENT_MIN_GAP_MIN` (30) and
    `PARTNER_FLOW_PULSE_DAILY_CAP` (6) times a day.
  - Line 1 says whether the open-relative OI flow leans to CALLS or PUTS.
    The PCR shift, each wall build or unwind, and the futures build-up cast
    one vote each; two net votes name a side. This is a read of writer
    positioning, not a validated signal.
  - Fact state is committed only after a delivered pulse.
  - The expiry pin note is kept. Regime notices go out only on entering or
    leaving crisis. The "risk limits flagging caution" notice is off, because
    it describes our own book.
  - Snapshots for all analytics underlyings are still stored.
- **Close wrap (15:40).**
  - Per index: the futures range and where it closed.
  - For each card: the first level reached, and what its option did, from
    the 5-minute snapshot LTPs, e.g.
    `option ₹97.35 → peak ₹140.6 (+44%), last ₹109.25 (+12%)`.
  - The tomorrow-expiry note and a 30-day tally:
    `NIFTY n (🎯t 🛑s)`.
- Rollback: `PARTNER_BUYER_MESSAGES=false` restores the previous text.
- Not changed, noted:
  - The card's strike is the ATM of the *future* (about one strike OTM for
    calls and ITM for puts when the future trades 60 over).
  - Cards arrive 50–110 s after a bar closes. The collection-completeness
    journal assumes 2-minute slots at :50, so the cadence was left alone.

## October 12 — Oct 12 audit fixes: F&O lock and read deadlines, quote fairness, cache validation, tilt identity (actual behavior, Dev)

Source: `Production_Trading-sentinel/docs/2026-10-12-production-deep-audit.md`
(PR #107 deployed; no F&O trade; Smart −₹11.44 and Penny −₹6.98 by exit date;
3 overnight positions OPEN). Expiry code untouched (expiry agent).

- **F&O lock (O12-F1).** `fno_orchestrator.fast_exit_has_work()` checks for an
  OPEN single leg. The 10 s fast-exit job checks it **without** the F&O lock
  and without durable telemetry; only a pass with an open leg runs the
  telemetered `_fno_fast_exit_pass` under the lock. A regular tick that finds
  the lock held by a fast pass now **waits** (≤ `FNO_TICK_FAST_EXIT_WAIT_SEC`,
  20 s) instead of skipping; it still skips behind another regular pass
  (bar-close trigger). `fno_tick_complete` logs `lock_wait_sec`. Oct 12 lost
  4/247 entry passes this way, and flat fast passes filled 3,101 of the 5,000
  retained telemetry rows.
- **Defined-risk read deadlines (O12-R1).** Oct 12: 10 DR passes ended at the
  20 s budget (8 chain, 2 futures history); the entry-read median was 5.4 s,
  p90 15 s, two quote calls queued on the 1/s quote budget. Now:
  `take_chain_snapshot(anchor_price=...)` centres the strike window on the
  tick's own futures quote, which saves one request (the fresh future is still
  quoted with the ladder, and a move of more than half the window retakes it
  the old way). DR entry reads and the single-leg chain read after a fired
  signal run in the **management** lane (bounded at 3 consecutive grants).
  Each tick records `defined_risk_entry_read_sec` {chain_snapshot,
  futures_history}, and the skip warning carries it.
- **Quote budget (O12-Q1/Q2).** Admission is shared limiter → 1/s quote
  bucket (priority lanes) → send, with nothing awaited in between (the FIFO
  dispatch gate is gone; a strict spacing check keeps sends ≥ 1/rate + 2 ms
  apart). The merged batch is built after admission, and its lane is the best
  lane in it (`quote_batch_lane`). After 3 batches led by a higher lane while
  a lower-lane request waits, the oldest lower request leads
  (`fairness_promotions`). In-flight batches are tracked; a cancelled batch
  raises `QuoteBatchCancelled` to every caller. `quote_batch_wait_sec` is now
  queue wait to admission only; `quote_batch_elapsed_sec` runs to the
  response. Instrument-keyed requests over 500 keys are chunked like tokens.
  Chunk timing sums waits and attempts, and reports the largest request
  size, not a sum. `/ops/provider-budget` quote budget shows
  `spacing_waits`, `fairness_promotions`, `cancelled_batches` and `in_flight`
  (`dispatch_gate_waits` removed).
- **Instrument cache (O12-C1/C2).** A dump under 1,000 symbols is a failed
  refresh (`_TruncatedInstrumentDump`, `last_dump_size`). It is not merged or
  saved, and the recovery job keeps retrying. `ensure_instrument_cache` is
  done for the day only when refreshed today **and** usable. A full dump
  replaces the catalogue in place, dropping symbols the provider no longer
  lists. Snapshot `saved_at` must be timezone-aware and not more than 300 s
  in the future; bad clocks are refused inside the handler (no TypeError).
- **Spread tilt (O12-T1/T2/T3).**
  - Pairs need the same underlying, option type and expiry (when both sides
    record one) within 120 s; the nearest entry wins. An ambiguous spread is
    `UNAVAILABLE`, never a wildcard.
  - Pre-binding spread rows are NIFTY with an unknown expiry
    (`identity: legacy`).
  - `MANIFEST` (lot cap 3, window, rules) and `manifest_fingerprint` freeze
    the terms; runtime `FNO_DR_MAX_LOTS` is shown but no longer used.
  - OPEN sides make a signal OPEN.
  - The summary adds `open`, `unavailable` and chronological
    `paired_*_max_drawdown`.
  - The hourly report reads it in a worker thread with a 10 s deadline
    ("report unavailable this hour" on timeout).
  - Forward sample was 0, so no score changed. Checked on a read-only copy
    of Production's F&O rows: the same 22 in-sample pairs and the same nets
    (31 spreads, 28 legacy and 3 contract-bound; 41 NIFTY singles). New
    in-sample drawdown: paired actual ₹16,331 vs variant ₹16,416. The tilt
    does not lower drawdown in-sample.
- **Smart exit-date total (O12-S1).** `/health.smart_penny.exit_date` =
  {date, closes, net, carried_closes, book_day_realized}, joined from today's
  durable `EXIT_FILLED` events. Oct 12 would read 12 closes / −₹11.44 (2
  carried) beside `marked_pnl` −₹18.01.
- **Overnight receipt (rec 10).** Each opened entry also stores `ask_levels`
  (the visible ladder), `walked_avg`, `price_basis` (ask_walk or
  slippage_floor) and `capacity`. Fill contract unchanged (`visible-asks-v3`).
- **Wording (O12-D1).** The cache watchdog says new-entry scans cannot resolve
  symbols while Smart held exits fall back to symbol quotes.

## October 9 (night) — frozen F&O shadow `FNO_SPREAD_TILT_V1` (actual behavior, Dev)

- **What it is.** `fno_spread_tilt.py`, read-only. For each signal where the
  paper book opened both a naked option and a debit spread (entries within
  120 s, matching option type), the variant drops the naked option and spends
  its max-loss budget on extra spread lots, capped at `FNO_DR_MAX_LOTS` (3).
  Formula: lots = min(actual + floor(naked max loss / spread max loss per lot), 3);
  variant net = spread cash net per lot × lots. Signals with one vehicle keep
  their actual result. It never trades or changes the real book.
- **Why.** Since Sep 1 the spread made +₹4,756 over 15 trades (worst −₹851)
  and naked options +₹3,080 over 14 (worst −₹3,228). Every spread was 1 lot,
  because the drawdown multiplier shrinks it (unchanged; it is a safety limit).
  The owner approved testing the tilt as a shadow and refused loss-reaction
  rules such as a re-entry ban.
- **Scoring.** Forward only, from signals on 2026-10-12. Earlier pairs are
  shown as in-sample context and never used to qualify it. Context on
  Production (read-only):
  - 22 lifetime pairs: actual −₹9,240 vs variant −₹5,109, worst trade
    −₹4,088 vs −₹6,061;
  - 10 pairs since Sep 1: +₹1,934 vs +₹6,300.
  The lifetime signal total reconciles to the F&O ledger (−₹26,369.94).
- **Where.** One line in the F&O hourly report; `GET /ops/fno-spread-tilt`
  (internal secret). Approximations: scaling realised net per lot overcounts
  flat brokerage (against the variant); three-lot depth is assumed.

## October 9 (evening) — open items closed: F&O fast exit ON, gateway notify parts, ledger gaps explained (actual behavior, Dev)

- **F&O fast exit ON** (`config.FNO_FAST_EXIT_ENABLED=True`). Single-leg
  management (no entries) runs every 10 s through `run_fno_fast_exit`,
  serialised with the 90 s tick by the F&O lock. One DB read when flat, and
  about 2 management-lane quotes per 10 s while a leg is open. Reason: Oct 9's
  NIFTY call armed a profit-lock floor of 123.875, and the next 90 s sample
  was 115.65 (net −₹22.75, roughly ₹534 gross below the floor). The Oct 4
  replay could not show this at 60 s resolution and recommended paper-enabling
  it. The bar-close entry trigger stays OFF. Roll back with
  `FNO_FAST_EXIT_ENABLED=false`.
- **Gateway `/api/internal/notify`.**
  - It takes bodies up to 64 KB through a route-specific parser registered
    before the general 10 KB one; other routes keep 10 KB.
  - `message` is capped at 60,000 characters.
  - A best-effort (non-`require_delivery`) alert over 4,000 UTF-16 units is
    sent as "[part i/n]" parts (`utils/split-message.js`), and `delivered` is
    false if any part failed.
  - Durable outboxes already split before sending.
- **Ledger versus positions (audit item 11).** All four gaps are historical
  and explained row by row in `docs/2026-10-09-ledger-position-reconciliation.md`:
  - Momentum Jul 20 double close;
  - Penny AMDIND Aug 31 double close;
  - EDGE paper/live Jul 1–20 closes from before EDGE wrote `positions` rows.
  No gap after Sep 1. Ledger left as written.
- **Smart stuck positions.** No code needed beyond `959392a`: on a new session
  `step_book` exits any prior-day position at the first executable bid
  (`SMART_SESSION_DEADLINE`) before rolling the book over. The symbol-key
  quote makes that bid reachable without the token cache.

## October 9 — Production audit fixes: lost symbol cache recovery and the paths it broke (actual behavior, Dev)

Source: `Production_Trading-sentinel/docs/2026-10-09-production-deep-audit.md`
and `2026-10-09-expiry-followup-audit.md`. After the 11:19 restart a DNS
failure left the NSE symbol->token cache empty for the rest of the session:
Momentum (14 scans, 6,958 "Unknown ticker" rows), Penny, Smart exits (two
positions OPEN and unpriced past the deadline) and the 15:20 overnight entry
(0 of 971 quoted, stored as a completed day) were all blind.

- **Symbol cache recovery (O9-R1, `kite_client.py`).**
  - A provider refresh writes `nse_instrument_cache.json` beside the DB
    (only when the dump has at least 1,000 symbols).
  - A failed refresh with an empty cache loads that snapshot if it is at most
    7 days old and has at least 1,000 symbols (in place, so universes that
    hold the dict see it).
  - `ensure_instrument_cache()` runs every 2 min, weekdays 07:00-15:58
    (`instrument_cache_recovery` job): one provider attempt until today's
    refresh succeeds, then a no-op.
  - `instrument_cache_status()` (source PROVIDER/SNAPSHOT/EMPTY, size,
    usable, failures, last error type) is on `/health` as `instrument_cache`;
    an unusable cache adds `instrument_cache_unavailable` to
    `not_trading_reasons` and makes the readiness watchdog page.
  - Penny's startup cache wait returns at once when the refresh already
    failed (source EMPTY, failures > 0) instead of stalling 60 s past its
    own 60 s trigger (95 max-instance skips on Oct 9).
- **Smart held exits (O9-S1, `penny_smart_shadow.py`).** A held symbol with
  no token is quoted by `NSE:<SYMBOL>` through `get_quote_by_instruments`;
  a missing answer stays unavailable (no stale fill). Monitor timeout 2 s ->
  5 s. `smart_exposure_snapshot()` is on `/health` as `smart_penny`
  (FLAT/OPEN/ATTENTION with exit_pending, minutes since managed, mark status)
  so the classic Penny "open 0" cannot hide Smart exposure.
- **Momentum (O9-M1, `main.py`).** A scan with an unusable cache tries one
  recovery, else skips with `momentum_screener_skipped
  reason=instrument_cache_unavailable` (no error rows). The heartbeat groups
  reasons by family (`exception: Unknown ticker: X` -> `exception: Unknown
  ticker`), shows the top 12 plus an "other reasons" line, caps the body at
  3,500 characters, and logs `momentum_heartbeat_rejected status=...` on a
  non-2xx answer. Entry gates, selective entry, sizing and exits are unchanged.
- **Overnight entry (O9-O1, `edge_overnight_paper.py`).** Names the cache
  cannot resolve are quoted by symbol in 500-key chunks. With quotes for
  fewer than half the universe the scan does not run: no receipt while a
  later catch-up slot (every 5 min) fits before 15:29, else a
  `status: DATA_UNAVAILABLE` receipt and the notice "NO ENTRY - quotes
  unavailable ... Not a no-signal day".
- **Quote budget (O9-Q1/Q2/Q3, `kite_client.py`).** `QuoteBudget.dispatch_gate()`
  runs after the shared limiter, right before each `/quote` HTTP call, so
  sends stay at least `1/rate` apart (`dispatch_gate_waits` in the snapshot).
  Instrument-keyed non-2xx answers (429 included) are counted. Token requests
  over 500 are split into 500-key chunks.
- **Expiry outbox (O9-E1, `expiry_paper.py`).** `flush_notices` uses
  `notice_outbox` like the overnight book: a 422 steps over at once with
  backoff, a transport failure stops in order, an unknown failure keeps order
  for 3 tries. Two new nullable columns on `expiry_paper_notices`
  (`next_attempt_at`, `last_error`), added on open. `notice_parts` measures
  UTF-16 units (Telegram's measure). `NOTICE_STEP_OVER_AFTER` is removed.
- **Not changed:** strategy thresholds, sizing, F&O, the frozen expiry plays,
  the gateway 10 KB body limit.

## October 8 (late night, 2) — follow-up review F1–F3: entry clock, outbox classification, quote budget (actual behavior, Dev)

- **Overnight entry `visible-asks-v3` (F1).**
  - The admission decision uses a clock read after the scan and the
    shortlist re-quote. Past 15:29 (or another date) every pick refuses
    `past_entry_cutoff`. Entries and the receipt are recorded at that
    decision time; the summary keeps `started_at` and `decided_at`.
  - The live catch-up passes the wall clock (it used to freeze its start).
  - Snapshot freshness is its own rule: the quote `timestamp` must exist
    (`no_quote_timestamp`), be at most 120 s old (`stale_quote_snapshot`)
    and not more than 5 s ahead (`quote_time_ahead`). The 30-minute
    last-trade rule stays as the separate activity policy.
- **Outbox delivery classification (F2).**
  - Gateway: `require_delivery` answers 422 when Telegram rejected the
    message itself (HTTP 400), 502 for anything else
    (`telegram.sendAlertOnceDetailed`).
  - `notice_outbox.py`: 422 = content (step over at once, back off 1 min
    doubling to 30 min); network/timeout/other HTTP = transport (stop the
    round, keep order); other exceptions = unknown (keep order for 3
    tries, then step over with backoff). Rows backing off are skipped until
    due; `last_error` and `next_attempt_at` are stored.
  - The overnight outbox uses it: any number of rejected notices no longer
    block healthy ones, and an outage retries only the first row. Delivery
    is at-least-once (a lost acknowledgement resends).
  - The expiry outbox (expiry agent's code) still has the older step-over
    rule; adopting `notice_outbox` there is a small change for that agent.
    The new 422 status does not change its current behaviour.
- **Quote budget enforced (F3, `kite_client.QuoteBudget`).**
  - Every `/quote` HTTP attempt takes a slot at `KITE_QUOTE_RATE_PER_SEC`
    (1.0, Kite's documented limit), management lane first; the shared 3/s
    limiter still applies on top.
  - Concurrent token requests waiting for a slot are merged into one call
    (up to 500 instruments) and each caller gets only its own tokens.
    Instrument-keyed calls (expiry, research collection) share the budget
    unmerged.
  - Load test (scaled 10x): 36 concurrent Penny/F&O-exit/expiry requests
    needed 4 HTTP calls; F&O exits waited one slot (about 1.1 s at the real
    rate), bulk Penny at most about 3.3 s.
  - Counters now include instrument refresh and funds/margins; orders count
    at HTTP dispatch only; non-2xx statuses (including 429) are counted per
    endpoint. `/ops/provider-budget` shows scope (this engine process since
    `started_at`; Node gateway traffic excluded) and the quote-budget
    batches and maximum waits per lane.

## October 8 (late night) — independent review R2–R6 and overnight outbox (actual behavior, Dev)

- **Overnight entry `visible-asks-v2` (R3).**
  - After the scan, the shortlist is re-quoted in one call. A failed
    re-quote refuses (`no_fresh_quote`); it never prices from the old batch.
  - A pick whose last trade is more than 30 minutes old at admission refuses
    `stale_last_trade` (a 09:00 trade used to pass a 15:20 entry on date).
  - `price_for_cash` re-walks the asks for the final, cash-trimmed share
    count, so price and buy charges match what is bought (the reviewer's
    probe overpaid ₹14.10 on 295 shares).
- **Overnight outbox.** Over-long notices are stored as acknowledged
  `[part i/n]` rows (`expiry_paper.notice_parts`, read-only reuse). A notice
  refused 3 times is stepped over, kept and retried; a second failure in a
  row means the gateway is down and the flush stops.
- **Momentum cohorts (R4).** Unavailable paths carry `recorded_at` and are
  reported in their own admission population; store-level gaps go to
  `unattributed_unavailable`. Each population lists its admission keys.
- **Agent status guard (R5).** A snapshot or thread-start failure releases
  `in_flight`.
- **Provider budgets (R6), measurement first.** `kite_client.EndpointBudget`
  counts admitted calls per endpoint class (quote 1/s, historical 3/s,
  order and other 10/s, as documented by Kite), with the per-second peak
  and over-limit count. `kite_endpoint_over_documented_limit` is logged at
  most once a minute per class; `GET /ops/provider-budget` returns the
  snapshot. The shared limiter stays at 3/s. Oct 8 logs had no 429
  rejection, and a blind 1/s quote cap would triple quote queueing; set a
  per-endpoint cap from this data.
- **Research scripts (R2).** Every arm in
  `docs/research/fno/2026-10-08-time-stop-sign/` now sets the deferral
  explicitly; a re-run reproduces −₹5,267 / +₹6,968. The shipped row is
  −₹139 without its best winner (Oct 1), so the sample cannot show steady
  profits.
- Kept: the F&O 15% drawdown halt (agreed with the reviewer; a weekly reset
  could repeatedly forgive losses).

## October 8 (night) — expiry notices split into parts; a refused row no longer blocks (actual behavior, Dev, review R1)

- **Problem (independent review R1, valid).** The expanded day summary was
  4,277 characters on the replayed Oct 8. Telegram's limit is 4,096; the
  gateway adds a "🚨 [SYSTEM ALERT]" prefix line and does not split. `flush_notices`
  broke on the first failure, so that row blocked every later notice across
  days.
- **`notice_parts` / `_notice`.** A notice over `NOTICE_MAX_CHARS` (3,500) is
  split at line ends into "[part i/n]" parts, stored as
  `<key>:partNNofMM` rows, each acknowledged separately. A notice that fits
  keeps its key.
- **`flush_notices`.** A row with `attempts >= NOTICE_STEP_OVER_AFTER` (3) is
  stepped over, logged as `expiry_paper_notice_stepped_over` with key,
  attempts and length (no text). It stays pending. A second consecutive
  failure stops the flush.
- **Checked.** The Oct 8 replay summary splits into 3,472 + 826 characters.
  A full simulated day is delivered through a fake sender that enforces
  Telegram's UTF-16 limit with the gateway prefix. A refused row is stepped
  over after 3 attempts. With the gateway down, the flush stops after two
  failures.
- **Not changed here:** the EDGE overnight outbox has the same break-on-first
  pattern (not expiry; left to the developer agent). Review R6 (per-endpoint
  Kite budgets: full quote is 1 request/s versus the shared 3/s limiter)
  belongs to the shared `kite_client`, also the developer agent's area.

## October 8 (night) — Oct 8 audit fixes: F&O peak and put sign, overnight depth, card wording, Momentum cohorts, status publish (actual behavior, Dev)

- **F&O profit-lock peak without futures (O8-F1).** A new option peak seen on
  a tick with no futures quote is now stored (`fpos.update_best_premium`,
  monotonic `MAX`, open rows only). Before, it was computed but dropped, so
  the lock could not arm from it. Trail state is still only written when a
  futures quote exists.
- **Bought-put time-stop sign (O8-F2).** Single-leg positions always buy the
  option and settle as `(exit - entry) x qty`. The time-stop deferral negated
  premium P&L for SHORT (bought puts), so it deferred losing puts and cut
  winning ones. The negation is removed.
- **Time-stop deferral OFF (`FNO_TIME_STOP_RESPECTS_PREMIUM=False`).** With
  the sign corrected, the 18 archived sessions replay at −₹5,267 with the
  deferral and +₹6,968 banking at the time stop (max DD ₹1,991, PF 2.26).
  The Oct 7 ₹8,411 figure depended on the bug holding three losing puts that
  recovered. Evidence: `docs/research/fno/2026-10-08-time-stop-sign/`
  (in-sample development evidence). So at 45 minutes without 0.5 R of
  underlying progress the trade now closes, profitable or not; the profit
  lock and trail still manage winners before that.
- **Drawdown-halt cliff (finding, unchanged).** The F&O paper book halts all
  entries below 85% of the ₹2.5 L pool (₹212,500); Production equity on
  Oct 8 was ₹223,087, already at 0.25x size (more than 8% below peak).
  Replays starting near the line are dominated by it.
- **Overnight entry fills against visible asks (O8-O1, `visible-asks-v1`).**
  - Missing depth refuses `no_depth`; empty, zero or malformed asks refuse
    `no_sellers`.
  - Shares are capped at the displayed ask quantity, and the price is the
    walked average ask, never below LTP + 25 bps.
  - Fewer visible shares than a quarter of the plan refuses
    `thin_asks_below_quarter_of_plan`.
  - Each entry keeps `planned`, `visible_ask_qty`, `best_ask`, `best_bid`
    and `quote_ts`; the summary carries `fill_contract`.
- **Equal open (audit 3.4).** `open_is_prev_close` is an equality flag only;
  a discovered open can equal the previous close.
- **Partner EOD card scorecard (O8-P1).** No retained target/invalidation
  event now reads "no target/invalidation observed" (not "neither level
  reached"). The record covers 30 calendar dates including today (was 31).
- **Momentum allocation cohorts (T6).** `momentum_admission_cohorts.py` runs
  the unchanged frozen allocation report per admission population
  (`BASELINE_ADMISSION`, `SELECTIVE_ADMISSION_V1` from 09:00 IST Oct 8). It
  lives outside the fingerprinted modules, so the Oct 6 freeze still
  verifies. CLI: `python momentum_admission_cohorts.py --db … --manifest …
  --output …`.
- **Agent status publish (O8-A1).** Timeout (2 s connect, 10 s read); a post
  still in flight makes the next minute skip; failures log `streak` and
  `last_ok`, with a `recovered` line. Status only; no trading path.
- Already done by the expiry follow-up (`b7d3f4d`): audit T4 stale OI, T5
  966 slots, limiter management lane.
- Not changed: T7 settlement-horizon labels (documented already), C4/C7, R1,
  T8/T9 historical mismatches.

## October 8 (evening) — owner's expiry stop rule, tallied in the summary (actual behavior, Dev)

- **The rule.** The owner set it after two losing expiries (Oct 6 NIFTY
  −₹3,224.47, Oct 8 SENSEX −₹2,934.51). Observe 10 expiries in all. If the main
  book (A+B+C whole modeled) loses on every one, stop expiry-day F&O trading.
  A play or section that keeps losing is dropped on its own. This decision
  point comes before the 20-expiry scoring horizon.
- **Code.** `OWNER_RULE_SET`/`OWNER_REVIEW_EXPIRIES` (10). `owner_rule_lines`
  covers every expiry day in the store up to the summary's day, all
  underlyings. It counts how many lost, the current losing streak (a day
  without a main loss resets it) and per play the expiries lost/traded. At 10
  expiries, all of them lost, it prints "RULE MET: … stop expiry-day F&O".
  `format_day_summary` appends both lines. The rule is reporting only: nothing
  stops automatically; the owner decides.
- **Checked on a read-only copy of the Production store:** "expiry 2 of 10,
  main book lost 2 of 2, losing streak 2; 8 expiries left to observe". Per
  play: A 2/2, B 2/2, C 2/2, BH 1/1, C500 1/1, D 0/1.

## October 8 — expiry book after the first SENSEX audit: shadow-v2 (AL, BP), path marks, T4/T5 fixes (actual behavior, Dev, paper only)

Source: Production `docs/2026-10-08-expiry-system-deep-audit.md` (read-only).
That day was primary −₹2,934.51 (filled +₹508.49, assumed −₹3,443.00) and
shadows −₹184.19. All 16 fills and fees replayed exactly, and every quote was
fresh. The losses were strategy outcomes, not data faults. The thresholds of A,
B and C (`expiry-v1`) are unchanged.

- **Shadow plays `expiry-shadow-v2`** (`SHADOW_PLAYS` = BH, C500, D, AL, BP;
  no Telegram trade lines; summary only):
  - **AL** uses A's entry rules under its own ₹2,500 ceiling, trade count
    and open-position check, so its entries can diverge from A's after a
    different exit. Its lock is a stop and can gap. Its policy is `replace(POLICIES["A"],
    lock_gain=0.5)`: `_bank_floor` keeps a banked one-lot position at
    entry + 0.5 × (peak − entry). With two or more lots it behaves as A.
  - **BP** takes B's strangle. Its legs have BH's policy (no bank, no trail,
    flat at 15:38). Before the per-leg loop, `_pair_target` sets
    `exit_pending="PAIR_TARGET"` on both legs once `liquidation_net` of the
    pair is at least `BP_TARGET` (0.20) × the premium paid. Only when both legs
    are open and neither is pending, and only before 15:38.
  - A day begun under v1 reads `expiry-shadow-v1+expiry-shadow-v2 joined
    mid-day`.
- **Path marks:** `liquidation_net(legs, quotes, now)` gives the net of selling
  every open leg on the fresh visible depth now. Long legs walk the bids; D's
  sold legs buy back on the asks. Each pays its own order charges, plus what
  the legs already booked. It is None when any open leg lacks fresh, deep
  enough depth. `_mark_paths` stores the best and worst mark and the count per
  entry (`state["marks"]["<play> <entry_ts>"]`). An entry that closes during a
  tick is marked at its fills. The summary adds a line under each play
  ("entry HH:MM:SS: best … worst … (n marks), finished …").
- **T5:** `EXPECTED_SLOTS` = 966. `run_expiry_tick` and the scheduler wrapper
  run only while `TICK_START <= t < SESSION_END`.
- **T4, `expiry-context-v1.1`:** OI-based context reads fresh quotes only. It
  adds `oi_fresh`/`oi_window`, and the text prints "from N/M fresh quotes".
  `_observe` logs the future's `oi`.
- **Labels:** `_moment` prints "D entry 14:30:00, read 14:30:10". `SETTLE_AT`
  is commented as an approximation.
- **Limiter:** `_fetch` runs inside `kite_client.provider_lane("management")`.
  The rate and burst are unchanged; `management_burst` bounds starvation of
  the other lanes.
  - Cause found on the Oct 8 packets: 95 ticks waited over 3 s. Nearly all
    were the first tick of a minute, between 13:00 and 14:30, and none came
    after 14:30. That matches the per-minute Penny breakout scan
    (`penny_scan_interval`, 60 s, breakout window to 14:30, normal lane).
  - Check: the real `RateLimiter` (3/s, burst 1) with 60 queued normal
    requests gives an expiry wait of 13.78 s in the normal lane and 0.28 s in
    the management lane.
  - Owner question (Oct 8): pause Swing or other modules on expiry
    afternoons? No. The lane removes the contention while Penny keeps
    running, and pausing would cost Penny its trades. Swing makes no intraday
    quote calls, so pausing it frees nothing. Revisit only if the first v2
    expiry still shows waits over 3 s.
- **Replay check:** the retained Oct 8 Production packets replayed through Dev
  (scratch script, read-only copy of the store). Every primary and v1-shadow
  result, and the audit's path figures, matched to the paise. AL came to
  +₹501.63 and BP to +₹786.76. These are in-sample, not evidence.
- **Unchanged:** `expiry-v1` thresholds, ceilings, freshness limits, fill
  model, fee snapshots, the outbox, reconcile and D's sizing. Schema: none
  (the marks live in the day state).

## October 7 (evening) — F&O profit lock and re-entry confirmation; Oct 7 audit fixes T1–T3 (actual behavior, Dev)

- **F&O single-leg profit lock (`fno_exit_rules.profit_lock_floor`, on by default).**
  - Once the option's best exit basis (bid, else LTP) has been
    `FNO_PROFIT_LOCK_ARM_R` = 0.4 premium-R above entry, the position exits
    (`profit_lock`) if the basis falls to the floor. Premium-R is entry
    premium x `FNO_STOP_PREMIUM_PCT`.
  - The floor is the larger of entry + 0.1 R and entry + half the best gain
    (`FNO_PROFIT_LOCK_KEEP_FRACTION` = 0.5).
  - The floor uses the best seen before the current sample, so one sample
    cannot both arm and fire it.
  - The ladder order is: underlying stop, trail, premium backstop, profit
    lock, then the time stop. The lock also works without a futures quote.
  - `fno_positions.best_premium` is a new additive column, written with the
    trail.
- **F&O re-entry confirmation (`fno_entry_plan.reentry_confirmed`, on by default).**
  - After a same-day `underlying_stop` or `premium_backstop` on an
    underlying, a new single-leg entry in that direction must be beyond the
    stopped trade's entry by `FNO_REENTRY_MARGIN_R` (0.25) x its stop
    distance. Otherwise it is refused as `reentry_not_confirmed`, and the log
    carries the level.
  - The opposite direction and other underlyings are never blocked.
  - Levels come from `fno_positions.stopped_entry_levels_today`.
- **Evidence (development only, every session already seen).**
  - The replay covered 18 archived NIFTY sessions:
    `docs/research/fno/2026-10-07-exit-and-reentry/README.md`.
  - Results:
    - baseline: ₹5,323 net, drawdown ₹3,831;
    - re-entry gate alone: ₹7,693, drawdown ₹1,991;
    - both features: ₹8,411, drawdown ₹1,991. Without the best trade,
      the result goes from −₹1,784 to +₹1,303.
    - Superseded Oct 8: these used the inverted put sign; corrected with
      the deferral off, +₹6,968 (see the Oct 8 night section).
  - Rejected settings:
    - an early lock (0.2–0.25 R) lost money, because exits fell through a
      thin floor between samples;
    - faster management did not help on this data.
  - Oct 7's two puts never went meaningfully green, so no exit rule could
    have saved them. The re-entry gate blocks the second one.
- **Partner context restored: morning brief and EOD wrap (`PARTNER_CONTEXT_WITH_ADVISORY`, on).**
  - Production's compose file defaults `PARTNER_HEDGE_ENABLED=true`, with no
    bound partner portfolio. The hedge bot therefore sent nothing, but
    `_legacy_info_retired` silenced the 09:50 brief and the 15:40 EOD wrap.
  - Both are now context surfaces (`context=True`). They run beside advice
    cards and the hedge bot.
  - The 09:50 brief covers, per index:
    - opening-range breakout levels;
    - IV against RV, with a buyer's-day verdict;
    - skew, PCR, max pain and the OI support/resistance walls;
    - expiry and event-calendar notes.
  - The 15:40 EOD wrap now lists each delivered advice card with its
    outcome (invalidated, target reached, or neither with the close against
    the trigger). It adds a 30-day card record and a tomorrow-expiry
    warning.
  - Intraday analytics alerts keep the suppression rule, because about 100
    events a day would be noise.
  - Turn it off with `PARTNER_CONTEXT_WITH_ADVISORY=false`.
- **Partner cards follow the same re-entry rule (`partner_manual_advisory.invalidated_reentry_levels`).**
  - After a same-day partner idea on an underlying reaches its published
    invalidation, a new card in that direction is suppressed
    (`reentry_not_confirmed`). It is allowed once the forward price passes
    the failed idea's trigger by `FNO_REENTRY_MARGIN_R` x its
    trigger-to-invalidation distance.
  - The other direction is never blocked. The gate is controlled by the
    same flag as the paper book.
  - On Oct 7 the partner received the 13:11 card and the 14:00 repeat. Both
    were invalidated; the second is the kind this gate suppresses.
  - Partner traffic is unchanged otherwise. It stays event-driven:
    - at most 2 cards and 4 updates a day;
    - cards 09:45–14:45;
    - invalidation or target updates, and a 15:10 exit reminder;
    - PURE ADVICE (NOT CHECKED) labels;
    - no orders.
    The hedge bot (`PARTNER_HEDGE_ENABLED`) is off, and analytics messages
    are suppressed.
- **`mark_to_market` defined-risk marks.**
  - The marker now reads `fno_dr_book`'s contract-bound legs (signed
    `quantity`, `premium`, `contract.token` / `tradingsymbol`), using the
    row's `lot_size`.
  - Structure P&L is the sum of the legs' (mark − entry) values.
    `net_premium_rs` is the entry cost and is no longer subtracted a second
    time.
  - Legacy legs with no identity stay UNSUPPORTED. No runtime caller passes
    DR rows yet.
- **Momentum selective entry (`MOMENTUM_SELECTIVE_ENTRY_ENABLED`, on).**
  - This was an owner decision on Oct 7. The round-3 scoring on untouched
    data was skipped, so this is unscored and paper forward evidence only.
  - A shipped Momentum signal now also needs all three of
    `momentum_selective.selective_gate`:
    - NIFTY 50 above its session open;
    - the stock at least 0.3% ahead of NIFTY;
    - the close above yesterday's high.
  - A refusal is recorded as `selective_<reason>`.
  - The one NIFTY 50 intraday fetch per scan now also runs when the shadow
    is off. A missing index fails closed: no entry in that scan.
  - It applies to the shared scanner, so it also gates the live Momentum
    path, which remains halted by the owner.
  - The frozen Momentum allocation holdout's candidate population is now
    selective-only from Oct 8. Record that when evaluating it.
  - Penny's matching candidate `PEN_NOISE_STOP` was already on in the runtime
    (`PENNY_NOISE_STOP_ENABLED`).
- **Overnight forward check (Oct 7).**
  - Official Yahoo daily bars for the 8 live picks give these 15:20 entries
    against the official close: −0.4, −1.1, −0.7, −0.3, −2.6, +1.0, +2.1
    and −1.1%.
  - The close → next open moves were −4.6, 0, +0.7, 0, 0 and +3.6%. The
    +3.6% is PRAENG, the winner the T1 bug never sold.
  - All 8 picks had strength 0.96–1.0, so a stricter strength filter
    (S60) would have changed nothing.
  - Three exits had open exactly equal to the previous close. That may mean
    the pre-open auction found no equilibrium price, but a real discovered
    open can also equal the previous close (Oct 8 audit, NSE pre-open rules).
    `open_is_prev_close` is an equality flag only; it does not prove the open
    was untraded.
- **Overnight realistic-entry guards (`edge_overnight_paper.realism_refusal`, Oct 7 night).**
  - The live-universe replay
    (`docs/research/edge-overnight/2026-10-07-live-universe/`) used Kite
    daily data, about 1,500 band tickers and Jul 2025 – Oct 2026. It found
    that 75% of the old model's profit came from closes locked at the day's
    high, which cannot be bought at the close. The frozen `edge-overnight-t1`
    result is inflated the same way.
  - With realistic fills the edge is thin but positive in every quarter:
    - +₹68,820 on ₹25k;
    - +0.62% per trade (median +0.27%);
    - 13.4% drawdown from peak.
  - The 15:20 entry now ranks 10 deep and fills the
    `PENNY_EDGE_MAX_POSITIONS` slots, replacing each refused pick with the
    next one. It refuses:
    - SME series (`-SM`, `-ST`);
    - a second series of a held company;
    - the `MR_mid` kind;
    - an LTP within 0.5% of `upper_circuit_limit`;
    - empty sell depth;
    - an LTP at the day's high after a rise of 1.9% or more.
  - Refusals appear in the entry summary's `skipped` list.
- **Overnight waiting-leg retry (audit T1, `edge_overnight_paper.retry_waiting_exits`).**
  - After today's EXIT receipt, `catch_up` (every 5 min) retries legs that
    had no trade at 09:17, until 15:20:
    - inside the 09:47 auction grace it sells at `ohlc.open` (`OPEN_RETRY`);
    - after that it sells at LTP (`CATCHUP_LTP`).
  - Each retry that closes something queues its own notice
    (`EXIT_RETRY_HHMM`).
  - Refusals keep their exact predicate: `no_quote`, `no_open_price`,
    `no_basis_price`, or `no_trade_today` with the quote's last trade time.
  - A leg still untraded at 15:20 is carried, as before.
- **Overnight attribution date check (audit T3).**
  - The entry-vs-close / overnight split is recorded only when the entry day
    is the session right before today (`prior_session`, from the cached
    holiday list; never the network).
  - A wholly missed session now exits as `OPEN_DELAYED` without a split,
    even with zero attempts.
  - LTP exits add `after_open_rs`.
- **Expiry D reserve (audit T2).**
  - D's sizing is unchanged (frozen `expiry-shadow-v1`). Its `max_loss` is
    a bound only within the 5% exercise-STT reserve domain.
  - Settlement now records a `reserve_breach` event on a long wing whose
    intrinsic is beyond the reserve stored at entry
    (`reserve_intrinsic`), and logs `expiry_d_reserve_breach`.
  - The day summary prints `RESERVE BREACH` with the STT beyond the
    reserve. The loss is never capped.

## October 6 (night) — EDGE overnight result split into entry and overnight parts (actual behavior, Dev)

- `edge_overnight_paper.run_overnight_exit` reads `ohlc.close` from the
  09:17 quote. On the first exit session that is the entry day's official
  close. It records three values:
  - `entry_day_close` (a new column, added at open);
  - `entry_vs_close_rs`: close minus the paper entry price, times shares. This
    is the cost of buying at 15:20 LTP + 25 bps instead of at the close.
  - `overnight_rs`: open minus close, times shares. This is the move the
    study measured.
- The exit message shows both parts per trade.
- A delayed exit (`OPEN_DELAYED`, or a catch-up on a later session) does not
  record them, because that quote's close belongs to a different day.
- Why: the study's edge is close → next open. The Oct 6 audit noted that IWP
  opened above its reference and still lost, to slippage and costs. After
  10+ sessions these fields show whether losses come from the overnight
  thesis or from the 15:20 entry, before anyone changes the entry clock. This
  is measurement only; no rule changed.

## October 6 (night) — classic Penny durable daily brake; Momentum allocation holdout frozen (actual behavior, Dev)

- **Classic Penny kill switch is now settlement-fed (`main.sync_penny_daily_brake`, audit C3).**
  - Before: the runtime never called `PennyRiskEngine.record_close`, so
    `daily_pnl` stayed 0 and `kill_switch_active` could never trip. A restart
    or the 00:05 reset also cleared it.
  - Now, before each 30 s scan, the engine sums the IST day's `TRADE_CLOSED`
    and `TRADE_PARTIAL` ledger rows for the scanner's own source and sets
    `daily_pnl` from that sum. The source is `PENNY_PAPER` or `PENNY`; other
    books are excluded.
  - The trip threshold is unchanged: `PENNY_DAILY_KILL_SWITCH_PCT` (20%) of
    the configured bankroll, so ₹20,000 on the ₹1L paper book and ₹400 on a
    ₹2,000 live book.
  - If the ledger cannot be read, a live scanner is blocked (fail closed) and
    a paper scanner keeps its last value.
  - No frozen study source was edited: `penny_risk.py` and
    `penny_scanner.py` are unchanged.
- **Momentum allocation holdout (S7a).**
  - `docs/research/momentum-allocation/2026-10-06-allocation-freeze.json`
    freezes the comparison of first-arrival, equal-split and risk-proportional
    allocation on identical candidates (`momentum_allocation_research.py`).
    It also covers the capital-skipped NUVOCO and SUNTV kind.
  - Frozen at 2026-10-06 15:33 UTC; every batch after that is holdout.
  - Evaluate later, in Dev, against a read-only copy of the Production
    engine DB:
    `python momentum_allocation_research.py evaluate --db <copy> --manifest <freeze> --output <report>`.
  - The source fingerprint covers `cost_schedules.py` and `engine.py`, so
    evaluate on a checkout whose fingerprint matches.
  - Nothing in runtime changes until a reviewed holdout and a versioned
    paper pilot.

## October 6 (night) — research archive writers wait briefly instead of dropping (actual behavior, Dev)

- **`research_archive.guarded_write` (audit R1).**
  - Before: admission refused immediately when another archive write held
    the process lock or the cross-process `writer-lease.sqlite3`. On Oct 6
    this dropped seven quote collections and four partner input captures.
  - Now: the writer waits up to `WRITER_ADMISSION_WAIT_SEC` (5 s) for the
    lock and lease together. All callers run in worker threads, so the event
    loop is not blocked.
  - A wait of 0.5 s or more logs `research_writer_waited`.
  - A refusal reads `research writer busy holder=<operation|other_process>
    held_ms=… waited_ms=…`. `finalize_prior_days` registers itself as the
    holder for its whole loop.
  - The collector's failure handling is unchanged. A refused observation is
    still a recorded gap; it is never re-fetched later and passed off as the
    missed one.
- **Telemetry scope.** The 10 s expiry tick gets no scheduler-telemetry
  wrapper on purpose. Its ticks already store start and decision times, and
  two telemetry writes every 10 s would add load to the database that hit a
  lock on Oct 6.

## October 6 (night) — overnight buy charges reserved; partner management updates retried (actual behavior, Dev)

- **EDGE overnight admission (`edge_overnight_paper.py`, audit O1).**
  - `buy_charges(price, shares)` gives the delivery buy-side charges:
    `calc_penny_costs` with a zero sell leg, minus the DP charge (DP belongs to
    the sell).
  - `book_state` cash now subtracts each open position's premium and its buy
    charges (`reserved_buy_charges`). After a restart the reservation is
    rebuilt the same way.
  - At 15:20, each pick's shares are cut until premium plus its own buy
    charges fit the cash left after earlier picks. The entry summary records
    `buy_charges` per pick and `cash_after`.
  - The full round trip is still booked once, at exit. Equity and realized
    P&L are unchanged.
  - Oct 6 reproduction: the three picks would have reserved Rs 28.93 against
    Rs 21.34 of cash (−Rs 7.59).
- **Partner management updates (`partner_manual_advisory.py`, audit A1).**
  - A TARGET_ZONE, INVALIDATION or SESSION_EXIT_REMINDER update reports a
    completed public bar, not an executable quote.
  - Dispatch and authorization now use
    `PARTNER_MANUAL_ADVISORY_MANAGEMENT_MAX_OBSERVATION_AGE_SEC` (360 s) through
    `management_observation_fresh`. Before, they used the 30 s option-quote
    bound, which refused the Oct 6 12:40 SENSEX TARGET_ZONE 50 s later and
    left it QUEUED.
  - `pending_management_updates` runs on each scan and lifecycle tick. Every
    QUEUED row is either dispatched again or closed with a recorded reason:
    - `DELIVERED_ACKNOWLEDGED` (`acknowledged_claim_reconciled`) when its
      claim was already acknowledged;
    - `EXPIRED_UNSENT` (`observation_older_than_management_bound`,
      `idea_<status>`, or `idea_payload_unusable`).
  - A stale observation is never resent as current.
  - `partner_advisory_updates` gains a `status_reason` column, added at init.

## October 7 — expiry chain context `expiry-context-v1` (actual behavior, Dev, record-only)

See the [design doc](2026-10-05-expiry-day-paper-book.md), section "Chain
context", for the research ranking and the field table.

- **Recording:**
  - `chain_context` runs on every expiry tick after the quotes arrive and is
    stored under `context` in the tick row.
  - `Quote` now parses Kite's `oi`, so every logged leg carries it.
  - The day state keeps the realized-volatility samples (`rv`), each strike's
    first OI today (`oi_base`), the future's first price and OI
    (`fut_base`), and snapshots at 14:30 and 15:13:30 (`context_at`). Each A/C
    signal carries the context of its tick.
- **Summary:** a context block with both snapshots and how our sampled close
  met the 14:30 read (inside the walls, distance from max pain, move against
  the straddle).
- **Authority:** no rule reads the context. A whole simulated day gives
  identical positions with and without OI (test). If the context computation
  fails, the tick stores `{"status": "ERROR", "error": <type>}` and carries on
  (test).
- **Limits:**
  - max pain, walls and PCR cover only the ATM ± 8 strikes fetched;
  - IV comes from the straddle approximation, not a solver;
  - after 15:15 the index is frozen, so the 15:13:30 snapshot is the last
    meaningful one.

## October 6 (evening) — expiry shadow plays `expiry-shadow-v1` (actual behavior, Dev, paper only)

The owner approved them. See the
[design doc](2026-10-05-expiry-day-paper-book.md) section "Shadow plays".

- **Plays:**
  - `BH`: B's strangle with no bank or trail, sold at 15:38.
  - `C500`: C inside ₹500.
  - `D`: short iron condor, 14:30–14:45. Sold strikes are tried at 2, then 1,
    then 0 steps from the money; the protective legs sit one step further out.
    Sized by `condor_fill`. Held to cash settlement, so `reconcile` values it.
- **Isolation:** shadow plays share the tick's quotes. Each has its own trade
  counter in `state["trades"]` and sends no Telegram trade lines (`notify`
  filters to `MAIN_PLAYS`). The summary has a separate section and a shadow
  to-date line.
- **Schema:** `expiry_paper_positions` gains `side` (SHORT only for D's sold
  legs) and `width`, added in place. `reconcile` values a sold leg at
  (entry − intrinsic) × qty. If there is no settlement sample, it uses
  (entry − width/2) × qty.
- **Unchanged:** A, B and C (`expiry-v1`), the ceilings, the freshness limits,
  and paper-only authority. D has no live path. Selling options needs margin,
  and that is the owner's decision.

## October 6 — expiry book execution contract `expiry-exec-v2` after the first-day audit (actual behavior, Dev, paper only)

Source: the [first-day expiry audit](../../Production_Trading-sentinel/docs/2026-10-06-expiry-system-deep-audit.md)
(Production, read-only). On October 6 the NIFTY book lost ₹3,224.47 modeled:
filled +₹25.53, assumed −₹3,250.00. The strategy thresholds stay `expiry-v1`.
Only the data, clock and fill contract changed. Ticks, day state and positions
record `expiry-exec-v2`; a day begun under v1 reads
`expiry-exec-v1+expiry-exec-v2`.

- **Decision clock:** `run_expiry_tick(..., clock=)`. The start time only
  decides whether to run. Freshness (`Quote.age_status`), entry windows, fill
  labels and event times use `clock()` read after the quotes arrive.
- **Tick evidence:** each tick stores
  - the start and decision times;
  - `get_quote_by_instruments_with_timing` limiter and transport seconds;
  - every leg's full depth with its provider time;
  - index and future status: `FRESH`, `STALE`, `AHEAD`, `NO_TIMESTAMP`,
    `NO_PRICE` or `MISSING`.
- **Day-state counters:** refusals by reason, entry refusals by play, maximum
  gap, gaps over 25 s, and the slowest decision.
- **Partial bank:** the `bank_pending` column keeps the unfilled lots of a
  half-bank. They are retried while the bid holds the bank level and survive
  a restart.
- **No-quote expiry:** the expiry still writes its day and ticks. The box goes
  to `UNUSABLE_0_SAMPLES`, and a summary is queued.
- **Charges:** `options_cost_snapshot(exchange)`. BFO uses
  `FNO_BSE_EXCHANGE_TXN_PCT=0.000325` (BSE 0.0325%, Zerodha's list read on
  October 6). The schedule is frozen in `fee_snapshot` at entry; rows without
  a snapshot use the exchange's current schedule.
- **Outbox:**
  - per-store `asyncio.Lock` in the expiry and EDGE overnight `flush_notices`;
  - `sent_at` is the acknowledgement time;
  - delivery is at-least-once;
  - new job `expiry_paper_flush` (Mon–Fri, 12–15 h, second `5-55/10`); the
    tick callback no longer flushes.
- **Messages:**
  - buys show buy fees;
  - sells show slice gross, sell fees and the trade's net after all fees;
  - the summary has a data line;
  - per play: fees, filled net, assumed and whole modeled;
  - day and to-date whole modeled totals.
- **Schema:** `expiry_paper_positions` gains `bank_pending`, `fee_snapshot`
  and `execution` through `ALTER TABLE` when a store is first opened. Existing
  rows are kept.

## October 5 (late night) — expiry book: exit-fee reserve and acknowledged Telegram (actual behavior, Dev, paper only)

A second review of `4673105` found two gaps; both are closed.

- **Exit fees are reserved.** `max_loss` is now the whole premium, the buy's
  charges, and one sell-order fee per lot (an exit is at most one slice per
  lot). The buy is charged once at entry (`buy_charges`); each exit slice pays
  only its own sell order (`sell_charges`). Before, each slice charged a full
  round trip, so 2 lots at ₹18.80 sold one lot at a time at ₹0.05 lost ₹2,533
  against a ₹2,492 reserve. Sizing now gives 1 lot there, and ₹6 premiums give
  5 lots, not 6.
- **Telegram delivery is acknowledged.** `/api/internal/notify` accepts
  `require_delivery: true`: one send through `sendAlertOnce`, no gateway retry
  or dead letter, and **502** if Telegram refused it. `_send_paper_notice`
  (expiry and EDGE overnight outboxes) sends it, so only the outbox retries.
  Other callers keep the old always-200 contract with gateway retries; the
  response now also says `delivered`.
- **Settlement wording:** `SETTLED_ASSUMED` uses our own sampled post-auction
  index quote (`settlement_source: SAMPLED_INDEX_QUOTE`), not the exchange's
  published settlement price, and the summary says so.
- **Totals:** the running per-underlying line is filled P&L only; assumed
  settlements get their own line.
- **Deploy order:** gateway and engine ship together in one rebuild. An old
  gateway ignores the flag and answers 200, the previous behaviour.

## October 5 (night) — expiry-day paper book hardened after review (actual behavior, Dev, paper only)

Supersedes the risk and fill description in the `expiry-v1` section below. See
the [design doc](2026-10-05-expiry-day-paper-book.md).

- **Hard ceiling:** each entry's whole premium plus worthless-expiry charges
  (`max_loss`) fits the play's remaining ₹2,500 for the day. Stops are planned
  exits only; a gap can fill below them, never below `max_loss`.
- **A's strike:** ATM, or the next OTM strike if one ATM lot does not fit.
- **Fills:**
  - Fresh quotes only: the provider timestamp must be at most 20 s old.
  - Buys and sells walk the five-level depth in whole lots.
  - An unfillable exit latches `exit_pending` and is retried each tick.
  - Fills from 15:15 are labelled `AUCTION_WINDOW` (unverified).
- **Breakout:** needs fresh index and futures on 2 observations no more than
  25 s apart. A missing observation or a gap restarts the count.
- **`reconcile` settlement:** runs on each tick for earlier days and hourly
  09:45–17:45 (`expiry_paper_reconcile`).
  - It settles legs left open after 15:40 as `SETTLED_ASSUMED`: intrinsic at the
    post-15:36 index print, less charges and exercise STT.
  - Without that print a leg is `UNRESOLVED` at its worst-case loss.
  - Both go in `assumed_pnl`, separate from fills.
- **Telegram:** a durable outbox, `expiry_paper_notices`. A notice is marked
  sent only after a 2xx response. The sender `_send_paper_notice` is shared
  with EDGE overnight.

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
