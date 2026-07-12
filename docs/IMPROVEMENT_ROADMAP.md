# Trading Sentinel — Improvement Roadmap

_Compiled: 2026-07-11, from a three-track deep audit (architecture/reliability,
strategy/risk logic, code-quality/security/observability) of the dev checkout
at `~/trading-sentinel`, branch `feat/fno-module`._

_Cross-referenced against `FUTURE_UPGRADES.md` (April 2026 audit),
`docs/penny-prod-bugs-2026-07-10.md`, `docs/system_architecture.md`, and
`docs/superpowers/specs/fno-module.md`. Items already closed by those audits
are not repeated here; items from them that are **still open** are, with a
confirmation note._

Priority key: tiers are ordered by (risk of loss × effort). Do Tier 0 this
week; Tier 1 before scaling any bankroll; the rest as capacity allows.
Every item cites file:line in **this dev checkout** as of today.

---

## Tier 0 — Ship & protect what already exists (days, near-zero effort)

### 0.1 Commit the uncommitted working tree

> **Status: DONE 2026-07-12** — committed as `bc28e87` (F&O module),
> `dc868e8` (wiring + funnel fixes), `af2a880` (this doc); pushed to origin.

The **entire F&O module** (16 untracked `fno_*.py` files + specs + tests) and
the momentum-funnel fixes (`agent/agent.py`, `node-gateway/server/services/telegram.js`,
`python-engine/main.py`, plus 6 test files) sit uncommitted on
`feat/fno-module` — ~900 insertions. One careless `git checkout .` or disk
incident loses days of work. Nothing else on this list matters if the work
evaporates.

### 0.2 Deploy the momentum-funnel fixes to prod

Fixed in dev 2026-07-11, not yet in `~/Desktop/trading-sentinel`: cumulative
signals endpoint, 15-min agent polls, conviction-veto notices, `sendAlert`
retry. Until deployed, prod still has the hourly-poll-of-15-min-snapshot bug
that silently drops momentum alerts.

### 0.3 Rotate live credentials

`.env` holds **active** Zerodha API key/secret, Telegram bot token, Gemini
key, and both internal secrets in plaintext. It is correctly gitignored and
confirmed absent from git history — but the public IP is being actively
probed by internet scanners (see `gap.txt` itself: CFIDE/ISAPI/RCE probe
attempts), and the keys have now also passed through audit tooling. Rotate
all of them; longer-term, inject at deploy time or use a secrets manager.

### 0.4 Delete/untrack leaked and dead artifacts

> **Status: DONE 2026-07-12** — all artifacts below removed in `bf3af0f`
> (plus the duplicate `VIX_CB_THRESHOLD` and agent.py's commented-out
> old Gemini prompt).

| Artifact | Problem |
|---|---|
| `a.txt` (245 KB), `gap.txt` (130 KB) | Committed nginx log dumps; leak the server's public IP and access patterns; bloat the repo |
| `extra-docker-file-without-logging.txt` | Stale copy of docker-compose **without** log rotation — one accidental `cp` re-enables unbounded logs |
| `python-engine/main_bkp.py` | Pre-refactor `main.py` copy; imported nowhere; risk of editing the wrong file |
| `agent/agent_bkp.py`, `agent/Dockerfile_bkp` | Dead backups |
| `agent/agent.py:510,528,563` | **Three** `def main()` definitions — Python keeps only the last; ~90 lines of dead code in the live file |
| `python-engine/config.py:514,577` | `VIX_CB_THRESHOLD` defined twice; decommissioned `REGIME_VIX_*` settings |

---

## Tier 1 — Security P0 (before any bankroll scaling)

Several were flagged in the April audit (`FUTURE_UPGRADES.md`) and are
**confirmed still open** today.

### 1.1 Authenticate `/token` (HIGH-002 — worst open hole)

> **Status: DONE 2026-07-12** — `inject_token` now runs
> `_check_internal_secret`; node's provisioning call already sent the
> header, so the login flow is unchanged. Tests added.

`python-engine/main.py:3531` `inject_token()` has **no
`_check_internal_secret` call**. Anyone who can reach `python-engine:8000`
on the docker network can inject an arbitrary Kite access token — i.e. arm
or hijack trading. The sibling mutating endpoints (`/positions/manual`,
`/positions/close`) are gated; this one is not. One-line fix plus a test.

### 1.2 Enable nginx rate limiting (CRIT-004)

`limit_req_zone` is declared but the enforcement line is commented out
(`node-gateway/nginx/nginx.conf:37`). Given the live probe traffic in
`gap.txt`, uncomment it.

### 1.3 HTTPS (CRIT-005)

No 443 server block; everything including Telegram-relayed operator actions
transits plaintext. Certbot or GCP LB TLS termination.

### 1.4 Require `INTERNAL_API_SECRET` (HIGH-001)

> **Status: DONE 2026-07-12 (mandate-compatible form)** — whitespace-strip
> validator + boot-time Telegram alert instead of a hard-required field:
> the operator mandate 2026-06-25 (in `_check_internal_secret`'s docstring)
> forbids blocking boot during market hours.

Defaults to `""` (`python-engine/config.py:123`). The empty-secret 503
mitigation (AUDIT-FIX-2.2) helps, but a Pydantic required field + non-empty
validator makes misconfiguration impossible instead of merely detected.

### 1.5 Consider failing safe on `PENNY_LIVE_TRADING`

`config.py:337` defaults to `True` (deliberate opt-in, noted 2026-06-22, for
the Rs 2,500 test budget). A fresh checkout with a missing `.env` therefore
trades live by default. Recommended: default `False` in code, opt in via
`.env` — the safety-critical direction.

### 1.6 Sanitize `X-Internal-Secret` in node request logs (MED-011)

> **Status: DONE 2026-07-12** — verification showed the req serializer
> never logs headers (that's what protects the secret; now documented
> in-place), but it DID log `req.url` verbatim — including
> `request_token=…` on every daily Zerodha callback. Added
> `sanitiseUrl()` so sensitive query params are redacted. Residual
> (out of scope here): nginx's own access log still records the raw
> request line — covered when 1.2/1.3 touch nginx.conf.

`node-gateway/server/middleware/logger.js` — headers aren't run through
`sanitise()`; the shared secret can end up in pino logs.

---

## Tier 2 — Reliability & operations

### 2.1 Kite token lifecycle: one source of truth

> **Status: DONE 2026-07-12** — all three improvements shipped:
> (1) 15-min market-hours reconciliation cron in python-engine pages on
> scans-vs-execution token disagreement (deduped 1/hour);
> (2) the HTTP-400 InputException signature now fires a deduped Telegram
> alarm from `kite_client.get_quote`, not just a log line;
> (3) node re-arms at boot via authenticated `GET /token/current`
> (python serves its persisted same-IST-day token) — node still never
> writes tokens to disk. Discovered in passing: node's logout calls
> `POST /token/invalidate` on python, which **does not exist** (silent
> 404) — filed under the stub-endpoint items (3.x/MED-006/007/010).

Two independent token stores exist and can disagree:

- node-gateway: **in-memory only, by design** (`server/services/token-store.js`)
  — any mid-day node restart silently disarms *execution* while scans keep
  running.
- python-engine: persisted same-day to `/data` and restored on boot
  (`main.py` `_persist_kite_token` / `restore_kite_token_if_fresh`, the
  2026-07-09 fix).

Improvements, in order of value:
1. A **reconciliation probe**: `/health` (or the hourly heartbeat) checks
   "token armed on BOTH sides?" and alerts on disagreement.
2. Proactive expiry alarm keyed on the *correct* failure signature — Kite
   returns **HTTP 400 InputException** for expired tokens, not 401
   (`kite_client.py:448-457`), which has misdirected debugging twice.
3. Shared persisted store (node reads the same `/data` token file) so a node
   restart re-arms automatically.

### 2.2 Health checks that actually act

> **Status: DONE 2026-07-12** — verification: node/python image
> HEALTHCHECKs were already active (`docker ps` shows `(healthy)`); the
> real gaps were agent + nginx + "nothing acts". Shipped: agent
> heartbeat file + Dockerfile HEALTHCHECK (900s threshold, touched
> per-signal so long Gemini batches can't false-positive), nginx
> `/nginx-health` self-probe (answered by nginx itself so a node outage
> can't mislabel nginx), and a `willfarrell/autoheal` sidecar restarting
> any `autoheal=true` container that turns unhealthy. Deliberately NO
> `depends_on: condition: service_healthy` (operator mandate 2026-06-25:
> nothing may block startup during market hours).

- Dockerfiles define `HEALTHCHECK`s but `docker-compose.yml` has **no
  `healthcheck:` blocks and no `depends_on: condition: service_healthy`** —
  nothing restarts a wedged-but-alive process (the 2026-07-07 freeze ran
  6h32m; the Telegram bot once wedged ~5h).
- The **agent container has no healthcheck or heartbeat at all.** If it dies
  or hangs, momentum EXEC alerts stop with zero alarm. Add a healthcheck +
  a "last poll age" heartbeat visible in `/status`.
- Add an autoheal mechanism (e.g. `willfarrell/autoheal` or a host cron
  checking `docker inspect` health) since compose alone won't restart
  unhealthy containers.

### 2.3 CI and scripted deploy

There is **no `.github/workflows/`**. The ~95 python test files, jest
suites, and agent tests run only when a human remembers
(`imp_commands.txt`). Add:
1. GitHub Actions: pytest + jest + agent tests on every push/PR.
2. A `deploy.sh` that promotes dev → `~/Desktop/trading-sentinel` only after
   the suite passes (replacing the manual copy ritual), and tags the deployed
   commit.

### 2.4 Scheduler head-of-line blocking + liveness watchdog

> **Status: watchdog DONE 2026-07-12; scan offload deferred.**
> Shipped: a 60s `scheduler_tick` job runs ON the APScheduler loop and
> writes `/data/scheduler_tick.json` (the daemon-thread liveness
> heartbeat deliberately keeps ticking through a frozen loop, so it
> cannot detect this); the agent container (ro `/data` mount, separate
> process) checks it every 5 min and pages via direct Telegram when it
> goes stale >10 min during market hours (cooldown 30 min). This is the
> detector that would have caught 2026-07-07 in minutes. The
> heavy-scan offload is deferred: moving async scans to another
> thread/loop requires a second `KiteClient` (httpx client + rate
> limiter are loop-bound), which would double the effective Kite request
> rate unless the limiter is made cross-loop — too risky to bundle here;
> needs its own session.

One `AsyncIOScheduler` on one event loop runs penny + F&O + swing + momentum
+ reports + watchdogs (`main.py:181-207`). A slow Kite call stalls
*everything* — this is why `misfire_grace_time=600` and per-job
`max_instances=1` had to be retrofitted after real incidents.

- Move heavy scans to a worker thread/process so reports and watchdogs can't
  be starved by a scan.
- Add an **external loop-progress watchdog**: uvicorn answering `/health`
  does not prove the scheduler loop is alive. A "last scheduler tick age"
  metric checked from outside (host cron or the agent) would have caught the
  2026-07-07 freeze in minutes instead of hours.

### 2.5 Signal-delivery retry parity

> **Status: DONE 2026-07-12** — `sendSignalAlert` now uses the same
> detached 5s/15s/45s backoff, with one refinement: each retry rebuilds
> the message so the buttons carry a FRESH callback timestamp (the
> handler rejects presses >5 min after the embedded ts). A signal
> delivered on retry stores no `telegram_msg_id` (caller already
> returned) — acceptable, button handling uses the callback query's own
> message_id.

`sendAlert` gained 5s/15s/45s detached retries (2026-07-11 fix), but
**`sendSignalAlert` — the EXEC-button path, the one that matters most — is
still one-shot** (`server/services/telegram.js`): a transient Telegram error
silently drops a tradeable signal. Apply the same retry wrapper.

### 2.6 Monitor the OCI relay (single point of failure)

Every quote and order transits `161.118.160.180:31527`
(`SETUP_MANUAL.txt`, `config.py:579`). Today its liveness is a manual
morning `smoke_relay.sh`. Add an automated probe (every few minutes during
market hours) + Telegram alarm, and write down the failover procedure.

> **Status: DONE 2026-07-12.** `_kite_endpoint_probe_tick` (main.py):
> 3-min market-hours cron probing `settings.KITE_BASE_URL/` from inside
> the engine container (the real code path — also covers the direct-URL
> config). Pages on 2 consecutive failures (single blip = transient),
> deduped to 1/30 min while down, `✅ RECOVERED` notice once on heal.
> A 5xx from the relay counts as DOWN (relay up but path to Kite broken
> is still an outage for us). Pure state machine `_kite_probe_evaluate`
> fully covered in `tests/test_kite_endpoint_probe.py`. Failover
> procedure written to `docs/runbooks/relay-failover.md` (consolidates
> the SETUP_MANUAL troubleshooting entries: iptables ACCEPT rule loss,
> relay process death, reclaimed VM / changed IP + Kite re-whitelist).
> No automatic failover exists by design — the home ISP cannot reach
> api.kite.trade directly; that's why the relay exists.

### 2.7 Resource limits

No `mem_limit`/`cpus` anywhere in compose. One runaway pandas scan can OOM
the host and take down all four containers together.

> **Status: DONE 2026-07-12.** `mem_limit`/`cpus` on all 5 services:
> nginx 128m/1, node-gateway 768m/2, python-engine 3g/6, agent 768m/2,
> autoheal 64m/0.25. Host-protection caps with 5–20× headroom over
> observed steady state (nginx ~14M / node ~110M / python ~160M / agent
> ~100M on the 15G/12-cpu host), not tuning. With a cap the kernel
> OOM-kills only the offender; `restart:` + autoheal (2.2) + token
> re-arm (2.1) bring it back armed. Validated with
> `docker compose config`.

### 2.8 Log persistence & metrics

Logs live in Docker's 3×10 MB json-file ring per container — "what happened
last Tuesday" is often already deleted. Options in ascending effort: bigger
rotation caps on `/data`; `loki`/`promtail`; or at minimum persist the
funnel/watchdog counters (`analytics.gate_funnel_report`, accept-watchdog
daily rows) as time-series so the F&O `FNO_LIVENESS_30D_CLEAN` go-live gate
stops being a manual log grep.

> **Status: DONE 2026-07-12** (rotation caps + counters-as-time-series;
> loki/promtail deliberately skipped — host disk is 86% full and a log
> stack is out of proportion for a single-host system).
> Rotation: 10m×3 → 20m×10 + gzip on rotated files (~7× retention for
> ~40M real disk per container).
> New `ops_metrics.py` with two tables in the main DB (which lives on
> `/data`, already persistent): `ops_liveness_daily` — per-IST-day
> scheduler-tick count + worst gap (total AND market-hours columns),
> fed by the 2.4 `_scheduler_tick_job` (restart ⇒ gap=None, no
> fabricated gaps); `ops_funnel_daily` — per-day per-subsystem
> (momentum/penny/fno) evaluated/accepted/rejected + top-5 reject
> histogram (penny reasons collapsed via the accept-watchdog
> normaliser), snapshotted 15:50 IST on trading days, zero-eval days
> written explicitly. `GET /ops/metrics?days=30` (X-Internal-Secret
> gated) returns both; `liveness.market_gap_clean` is the queryable
> form of `fno_go_live_check` condition 4 (`FNO_LIVENESS_30D_CLEAN`) —
> the operator still attests via the env flag (going live stays a human
> decision), but the evidence is now SQL instead of the rule-62 grep
> over logs that had already rotated away. 32 new tests
> (`test_ops_metrics.py`, `test_kite_endpoint_probe.py`).

---

## Tier 3 — Strategy & risk correctness

_These change trading behaviour. Verify each against data first (the
audit-phase discipline), then fix behind a config flag where sensible._

### 3.1 F&O capital arithmetic may be a deadlock at Rs 1,00,000

`min_viable_pool = premium × lot × stop_pct / max_risk_pct`
(`fno_risk.py:107-120`). With the configured
`FNO_PAPER_BANKROLL=100000`, lot 75, `FNO_STOP_PREMIUM_PCT=0.25`,
`FNO_MAX_RISK_PCT=0.02` (`config.py:372,384-385`), only premiums
**≤ ~Rs 106.67** are admissible — and `FNO_MAX_STRUCTURAL_LOSS_PER_TRADE
= 12000` (`config.py:400`) separately rejects any lot with premium > 160.
The spec (§3) *anticipates* zero-trade days as healthy self-regulation, but
if 0.55-delta NIFTY weeklies routinely print 120–250, the feasible band is
nearly empty **every** day and the 60-trade/40-day go-live bar
(`fno_risk.py:263-266`) is unreachable.

**Action:** before changing anything, log a week of actual candidate
premiums vs the cap (the reject histogram already distinguishes
`pool_below_min_viable`). If confirmed, either raise the paper pool to
~Rs 200–250k or rework the stop/risk arithmetic — deliberately, since the
"premium cap = free volatility filter" property is worth preserving.

> **Status: DONE 2026-07-12** (operator waived the verification week and
> chose the pool raise directly). `FNO_PAPER_BANKROLL` 100k → 250k, and
> both rupee caps scaled ×2.5 with it (`FNO_MAX_LOSS_PER_TRADE` 2,500 →
> 6,250; `FNO_MAX_STRUCTURAL_LOSS_PER_TRADE` 12,000 → 30,000) — left at
> their old absolute values they would have re-created the deadlock at
> premium ≤ ₹133. Feasible premium band is now ≤ ~₹266.67 with the
> pool-derived `min_viable_pool` as the binding gate, i.e. the §3
> volatility-filter property is preserved and the typical 120–250
> weekly band is admissible. Sizing consequence: at ~₹100 premium the
> risk budget now admits 2 lots (capped by `FNO_MAX_LOTS=2`, was 1).
> Paper-only throughout (`FNO_LIVE_BANKROLL=0`, live leg disarmed).

### 3.2 R3 (crisis) regime contradicts its own design

The R3 branch says the RS filter *"replaces RSI + vol percentile filters"*
(`engine.py:282`) — but the **unconditional** `45 ≤ rsi14 ≤ 72` gate at
`engine.py:319` still applies to every regime. A genuine relative-strength
leader in a crisis (exactly what R3 wants to buy) usually has RSI > 72 and
is silently filtered. Combined with `RS ≥ 5%` single-day outperformance
(`config.py:570`) + `volZ ≥ 2.5` + `close > EMA200`, R3 is a near-impossible
conjunction — a candidate for the zero-accept watchdog treatment, and
possibly this codebase's next "unsatisfiable gate."

**Action:** make the RSI band regime-conditional; check the signal log for
lifetime R3 accepts (if zero, this is BUG-1's sibling).

> **Status: DONE 2026-07-12.** The 45–72 band in `evaluate_signal` now
> skips `REGIME_3_CRISIS` (the RS-vs-Nifty filter replaces it, as the
> R3 branch always claimed); R1/R2/UNKNOWN keep the band. Signal-log
> check: the prod log (2026-06-23 → 2026-07-10, 87k evaluations) holds
> **zero R3 evaluations** — the market never printed a crisis regime,
> so the dead gate could not be confirmed empirically; it was fixed
> statically before it could become BUG-1's sibling. Witness tests in
> `tests/test_swing_r3_rsi_gate.py` (verified to fail against the
> pre-fix code). The RS ≥ 5% single-day threshold itself was left
> untouched — no R3 data exists to justify tuning it.

### 3.3 Backtest gap-through-stop fills flatter every result

Both surviving backtests fill stop-outs **at the stop price** even when the
bar gapped through it: `backtest.py:64-67` (`curr_open <= stop →
exit_price = stop`) and `penny_edge_engine.py:472-475` (`low <= stop →
stop × (1 − 5bps)`). A real gap-down fills at the open, below the stop.
Systematic upward bias on win rate and average R in every historical sweep.

**Action:** `exit_price = min(stop, curr_open)` (keep edge's SL-before-TP
conservatism, which is already correct).

> **Status: DONE 2026-07-12.** `min(stop, open)` applied in all THREE
> fill sites: `backtest.py` `_simulate_trade`, `penny_edge_engine.py`
> `simulate_position` (slippage still applied, SL-before-TP unchanged),
> and — beyond the two the audit named — `penny_backtest_v2.py`'s
> `sl_hit` branch, so a future rerun of the sweep fills honestly too.
> Witness tests in `tests/test_backtest_gap_fills.py` (gap-through
> fills at the open; ordinary intraday breach still fills at the stop).
> Historical results produced before this date remain upward-biased —
> re-run before citing any of their numbers.

### 3.4 Swing book has no overnight gap protection

The chandelier stop is close-based and evaluated once daily EOD
(`chandelier_stop.py:152-166` + `position_tracker`). An overnight gap-down
realizes an unbounded loss relative to the stop distance. Consider a broker
GTT order as a catastrophic backstop, or size swing positions explicitly for
gap risk (e.g. assume 2× stop distance as true risk).

> **Status: DONE 2026-07-12** (gap-aware sizing route). New
> `SWING_GAP_RISK_MULT` (default 2.0): swing share counts are computed
> as if the true risk per share were stop_distance × 2 — halving
> position sizes; stop level and R targets unchanged. Set 1.0 in `.env`
> to restore old sizing. The GTT-order backstop was deliberately NOT
> built: it means placing real broker orders automatically — a new
> execution surface with its own failure modes — and stays available
> as a future opt-in if reduced sizing proves insufficient.
> Downstream (`portfolio.filter_and_allocate`) only ever shrinks
> shares further, so the multiplier cannot be bypassed.

### 3.5 `penny_backtest_v2` validated a different strategy than the one live

The sweep runs on **daily bars** (prev-day-high anchor, daily RSI(14), daily
volume vs 20-day median — `penny_backtest_v2.py:26-30,310-395`) while the
live MIS engine runs on **1-min intraday** bars with a prior-bars-high anchor
and 1-min RSI. Yet `VOL_MULT=1.8`, `buffer=0.3%`, and `RSI_MAX=70` were all
justified from that daily sweep. The parameters may still be fine — but the
derivation is invalid. Rebuild the sweep on 1-min data (Kite gives 60 days
of minute candles) or mark the params as unvalidated.

> **Status: DONE 2026-07-12** (marked-unvalidated route; the 1-min
> rebuild needs 60 days of Kite minute candles + a live token and is
> its own project). Findings against source: the audit's premise was
> only partly right — `PENNY_BREAKOUT_VOL_MULT=1.8` is justified from
> ORB literature and `PENNY_BREAKOUT_BUFFER_PCT=0.003` is a legacy
> hardcode-made-setting; **only `PENNY_BREAKOUT_RSI_MAX=70` actually
> rests on the daily sweep** (the "RSI 70–80 lost ₹13.5k" bucket
> comparison). Actions: a "PARAMETER DERIVATION IS INVALID" banner in
> `penny_backtest_v2.py`'s docstring (daily-vs-1-min mismatch on
> anchor, RSI resolution, volume basis — valid for activity/expectancy
> direction, invalid for parameter inference), and the
> `PENNY_BREAKOUT_RSI_MAX` config comment now flags the value as
> formally unvalidated (70 stays as the proven-shipped conservative
> default). No behaviour change to the live engine.

### 3.6 Penny regime is effectively single-signal

`compute_vol_rank` is documented for 5-min returns over a 60-day lookback
(`penny_regime.py:197-221`) but is fed **a single day's 1-min closes**
(`penny_scanner.py:474-478`). The stdev of 1-min returns vs a 0.10 soft cap
means `vol_rank ≈ 0` always — the 40%-weight input contributes nothing, so
the penny regime rides on the Nifty-vs-EMA50 VIX proxy alone.

Related (a *documented* fail-open, but worth revisiting): missing inputs →
`PR1_CALM` = full 5% sizing (`penny_regime.py:271-272`). A data outage
trades full size. Consider failing to PR2 sizing instead.

> **Status: DONE 2026-07-12.** Three fixes. (1) Scale:
> `compute_vol_rank` takes `bars_per_day` (scanner passes 375) and
> scales the per-bar stdev by √bars_per_day to a daily equivalent
> before the 0.10 cap — the raw 1-min stdev was ~0.001–0.005 vs the
> 0.10 cap, so vol_rank was ≈0 for every ticker and the 40%-weight
> input never influenced the regime. (Note: the sibling bug of the
> feed going to a throwaway instance was already fixed 2026-07-09 via
> the `__new__` singleton.) (2) Fail-open floor: missing inputs now
> classify to PR2_ELEVATED (2.5%), never PR1_CALM full 5%; all four
> fallback sites updated (classify(), main.py `_live_regime`, the
> hourly-report default, the scanner's no-regime constructor default).
> (3) Fail-open no longer masks severity: the input that IS present is
> still respected — vix_proxy ≥ 0.9 with vol_rank unfed classifies
> PR3_HOT (pre-fix, PR3 was unreachable every morning until the first
> scan fed vol_rank — the phase-2 audit finding, now closed at the
> classify() level).

### 3.7 Penny kill-switch rolls at the wrong midnight

`record_realized_pnl` / `kill_switch_active` key the "day" off
`when.date()` with UTC-flavored inputs (`penny_risk.py:114-134`), so the
daily-loss window resets at 05:30 IST — mid-morning-prep, not midnight. The
F&O kill-switch is IST-correct (`fno_risk.py`); align penny with it.

> **Status: DONE 2026-07-12.** New `PennyRiskEngine._trading_day()`
> converts to IST before taking the date (naive datetimes treated as
> UTC — every existing caller passes `utcnow()`); both kill-switch
> methods and the scanner's `daily_pnl_override` stamp use it. Witness:
> a switch tripped in-session now resets at IST midnight, not at 05:30
> IST (old code kept it active from 00:00–05:30 IST of the NEXT day).
> Real-world blast radius was small — the 00:05 IST `penny_daily_reset`
> job rebuilds the risk engine anyway — but the window and the reset
> job now agree on what "day" means.

### 3.8 `RiskEngine.calc_shares` floors to 1 share

`return max(1, shares)` (`risk_engine.py:122`) — when the capital cap
correctly computes 0 shares (expensive stock), it still buys 1, silently
violating the per-trade cap. The penny engine returns 0 in this case
(`penny_risk.py:110`); mirror that.

> **Status: DONE 2026-07-12.** Returns 0 with a
> `risk_engine_capital_capped_to_zero` log line, mirroring penny.
> Verified blast radius: `calc_shares` currently has NO production
> callers (swing sizing is inline in `engine.evaluate_signal`, which
> already rejects on 0 shares) — the fix removes a latent trap for the
> "share count recalculation if needed" use the RiskEngine singleton
> comment reserves.

### 3.9 Circuit-band inference is guesswork

`infer_band_pct_from_quote` (`penny_risk.py:250-280`) snaps to 5/10/20%
from today's high/low vs prev_close. A quiet day on a 20% ASM stock infers
a 5% band, mis-scaling the skip distance. Read the actual band (Kite quote
`lower_circuit_limit`/`upper_circuit_limit` gives the real thing directly).

### 3.10 Holiday & event hygiene

- `is_market_open` ignores holidays entirely (`market_calendar.py:14-22`) —
  weekday + time only.
- `is_trading_day` scrapes bot-blocked nseindia.com and **fail-opens to
  weekday-only with no alert** (HIGH-010, still open) — the system can run
  a full trading day on an NSE holiday and believe the market is open.
  Fix: maintained static holiday list (NSE publishes it yearly) + a loud
  Telegram warning on fallback.
- **No earnings/ex-dividend/event filter exists in any engine.** For Indian
  small-caps this is a top source of stop-jumping losses. Even a manual
  quarterly "results calendar" CSV consulted by the penny/edge gates would
  be a material improvement.

### 3.11 No F&O backtest exists

The newest, most complex strategy has zero historical validation — no
`fno_backtest*.py`. Build one reusing `fno_engine_mom` + `fno_gates` +
`fno_costs` directly (the penny-edge pattern, which shares
`scan_single_ticker`/`simulate_position` between live and backtest — the
trustworthy way this repo already knows how to do it).

---

## Tier 4 — Code health

### 4.1 Split `main.py` (3,833 lines)

Routes + scheduler wiring + auth + token persistence + breadth adapters +
per-strategy orchestration in one file. It is the largest and least-tested
file in the system. Natural seams: `routes_*.py` per subsystem, `scheduler_
setup.py`, `token_lifecycle.py`.

### 4.2 Unify the strategy-family triplication

`signal_log.py`/`penny_signal_log.py`/`fno_signal_log.py`,
`risk_engine.py`/`penny_risk.py`/`fno_risk.py`,
`penny_accept_watchdog.py`/`fno_accept_watchdog.py`,
`penny_hourly_report.py`/`fno_hourly_report.py` — each family reimplements
the same schema-write / kill-switch / zero-accept / report pattern (and the
kill-switch timezone bug in 3.7 exists precisely because they diverged).
Extract shared bases; **keep** the deliberate bankroll isolation.

### 4.3 Fix silent exception swallows in hot paths

`grep` finds ~15 `except ...: pass` sites; the dangerous ones:
`main.py:1068,1327,2092` (scan/serving paths), `penny_scanner.py:156`,
`position_tracker.py:44,48` (position bookkeeping — silent corruption of
exit logic), `penny_commands.py:178,189` (DB write failures vanish).
Replace with log-and-continue at minimum; alert where money is involved.

### 4.4 `retry.js`: backoff + error discrimination (MED-004)

Fixed-delay retries with no 4xx/5xx discrimination, used on the **order
placement** path (`executor.js`). Retrying a non-retryable 4xx on an order
is wasteful at best. Exponential backoff; retry only network errors + 5xx.

### 4.5 Consolidate the two signal pipelines

Pipeline A (agent polls `/signals` → Gemini → Telegram) and Pipeline B
(HMAC webhook → SQLite → Telegram) coexist, with two callback-ID formats
distinguished by regex (`index.js:47-53`). Related open item HIGH-007: the
momentum Execute handler **re-fetches live data** instead of executing the
approved snapshot — displayed price/shares/stop can differ from what
executes. Register the approved snapshot (Pipeline B's DB pattern) and make
it the single path.

### 4.6 Remaining `FUTURE_UPGRADES.md` odds and ends (confirmed open)

MED-002 dual Telegram alert sources (two messages per scan), MED-006
`/circuit-breaker/reset` proxied but unimplemented, MED-007 `/rejected`
always returns `[]`, MED-010 `/token/invalidate` 404s, LOW-003 minimal
`/health` payload, LOW-006 agent lacks an independent holiday check,
HIGH-008 `MomentumSignal.shares` missing `Field(ge=1)`.

### 4.7 Agent (Container C) hygiene

`logging.basicConfig` instead of the engine's structlog; unguarded
`json.loads(response.text)` on Gemini output (`agent.py:261`); `/signals`
GET carries no auth header; dedup state is an in-memory set lost on restart
(re-alerts after a bounce). Small fixes, one file.

---

## Tier 5 — Statistical rigor & future enhancements

### 5.1 Real edge statistics

`analytics.py` has honest sample-size gating (n ≥ 10, confidence tiers) but
only win_rate/avg_r. Add per-strategy **expectancy, profit factor, max
drawdown, and bootstrapped confidence intervals**; adopt a walk-forward /
out-of-sample split for every parameter sweep (none of the current sweeps
hold out data, so every tuned parameter is in-sample).

### 5.2 Paper-vs-live honesty checks

`PENNY_BROKERAGE_BYPASS` zeroes all penny costs in paper — any paper-vs-live
edge comparison with it on is meaningless; assert it off in reports. (F&O
already does this right: paper fills pay real bid/ask spread.)

### 5.3 From the repo's own backlog, sequenced after the above

- ML signal ranking once ≥ 90 days of outcome data exists (per
  `system_architecture.md` §13).
- FNO-VOL / FNO-THETA strategies (spec §13) — only after the liveness gate
  (`FNO_LIVENESS_30D_CLEAN`) is closed by the Tier 2 watchdog work.

---

## What is already good (preserve these)

- **Gate falsifiability tests** (witness + per-gate falsifier,
  `test_penny_gate_falsifiability.py`, `test_fno_gate_falsifiability.py`) and
  **zero-accept watchdogs** — the direct, correct answer to the 9-month
  dead-gate class of bug. Extend to every new gate as a merge rule.
- Per-incident **regression test suites** and the `docs/deviations/` +
  runbooks culture — rare discipline for a solo project.
- Centralized `config.py` with rationale comments on nearly every constant.
- Strict bankroll separation between pools, enforced by tests.
- The F&O `max_loss()` constitution + long-only-until-liveness-proven
  reasoning in the spec.
- structlog pipeline and the masked-token breadcrumb discipline.

## Suggested sequencing

```
Week 1  : Tier 0 (commit, deploy, rotate, delete)  +  1.1, 1.2, 1.4
Week 2  : 2.1 token probe, 2.2 healthchecks, 2.5 sendSignalAlert retry, 2.3 CI
Week 3-4: Tier 3 verifications (3.1 premium data, 3.2 R3 accept count),
          then the confirmed fixes behind flags; 3.3 backtest gap fills
Ongoing : Tier 4 refactors piecemeal (4.3 swallows first), Tier 5 with data
```
