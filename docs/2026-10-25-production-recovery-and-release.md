# October 25 Production recovery and independent O25f review (O25g)

## Result and scope

Production is running at **`0aa629a32f1ee714eb898fb790cf50e4ca06fc43`**,
the merge of [PR #115](https://github.com/urveesh09/trading-sentinel/pull/115).
Engine, gateway, agent and nginx are healthy; public dashboard and health
requests return HTTP 200. Real-money trading remains off. No new source
change was necessary in the reviewed O25f fixes. This is operational and
software evidence, not proof of strategy profitability or live execution.

The owner requested immediate recovery, independent review of the other
agent's three fixes and completion of the remaining authorized setup.
Production initially contained `582d7a5`; all three application containers
were stopped with `unless-stopped`. The prior O25f investigation attributes
the outage to Docker Desktop's update. This slice verified recovery rather
than repeating that updater-log investigation.

## Recovery and release

1. Started existing `python-engine`, `node-gateway`, `agent` separately,
   around 13:32 IST. nginx recovered without a separate restart. Confirmed
   each application's health and the public dashboard before deployment.
2. Reviewed O25f code `e9645de` / docs `ecd1a18`: route conflicts refuse
   place/modify/cancel/probe without order HTTP; malformed dates remain
   unavailable while reports continue; rendered Compose uses `always`.
3. Retained the previous image IDs and rollback tags outside the repositories.
   Backed up eight SQLite databases with the online backup API and checked
   each with `PRAGMA quick_check=ok`. The largest, cache.db, was about 3.15 GB.
4. Marked PR #115 ready and merged its exact checked head `ecd1a18` through
   GitHub. Production `git pull --ff-only origin evolve/smart-strategies`
   fast-forwarded to the merge SHA. Untracked Production audits were kept.
5. Built engine, gateway and agent one at a time with the exact merged SHA
   and UTC build time. Recreated them in that order using
   `docker compose up -d --no-deps --no-build --force-recreate <service>`.
   No ad-hoc source/configuration copy or Production `.env` edit.
6. `python scripts/verify_deployment.py --expected-sha
   0aa629a32f1ee714eb898fb790cf50e4ca06fc43` passed all three baked-image and
   runtime identities plus HTTP gateway/engine identities at **13:42:35 IST**.

## Validation and observed limits

- Dev local: `python -m pytest tests/test_fno_live_test.py
  tests/test_fno_live_preflight.py tests/test_kite_endpoint_probe.py -q
  -p no:cacheprovider`: **66 passed**.
- Newly built engine image, isolated container, no network/Production volume:
  those suites plus `tests/test_fno_proving_week.py`: **74 passed**.
  One existing Starlette lifespan deprecation warning in each run.
- New gateway image: native `better-sqlite3` in-memory `quick_check=ok`,
  tunnel module loads, release matches. Its normal image build also builds
  the React dashboard. These are smoke checks, not a new full gateway suite.
- Previous full engine/scripts **6,010 passed / 4 skipped** is the other
  developer's O25f receipt; this slice did not repeat that full suite.
- Docker health: engine, gateway, agent and nginx healthy. All application
  restart policies `always`. Engine `json-file`, `max-size=20m`, `max-file=25`.
- Scheduler startup: running, **88 jobs**; partner registration **18 jobs**.
  No new startup traceback observed. The engine reached HTTP readiness
  before Docker's first health interval; final Docker health passed too.
- Effective settings: `FNO_LIVE_TEST_ENABLED=false`, live bankroll 0,
  proving start Oct 26 / five sessions, evening report enabled, real entry
  authorization Nov 2–6. Deployed `python -m fno_proving_week` reads Oct 26–30,
  no paper trades yet, verdict after Friday close. It sends no message.
- Local and public `/api/health` report `ok` and exact merged release.
  Broker token expired; historical stale Telegram backlog remains visible.
  Polling restarted; Telegram's read-only `getMe` authenticated the bot.
  No outbound test message, broker order, live activation or stream enablement.
- Engine `/health` separately reports `DEGRADED`, scheduler running,
  `trading_ready=false`: `no_kite_token`, `instrument_cache_unavailable`,
  `order_execution_unverified`. Container health/HTTP readiness is established;
  broker login, instrument refresh and later order-path verification are not.

## Protected evidence and rollback

`C:\Users\Urveesh\sentinel-operations\production-rollout-20261025`
contains `previous-release.json`, `database-backup/`, gateway/agent build logs
and `deployment-receipt.json`. Access is restricted to the owner, SYSTEM and
Administrators. Backups contain account/trade data; do not commit them.

Previous images are tagged
`sentinel-rollback/<service>:582d7a5-20261025`. Roll back through the normal
GitHub release path and these retained images, with trading off. Do not
blindly overwrite the current database after schema changes: retain the
failed state and choose an explicit compatible recovery.

## Remaining work

1. Owner finishes Oracle password recovery/sign-in. At this check, 31527
   answers externally and 31528 times out. VM tunnel installation and its
   firewall are already done; cloud ingress/direct TLS validation and client
   adoption are pending. Protected settings are not applied to Production.
2. Owner logs in to Kite **Monday morning before 09:15**. A Sunday login
   does not establish Monday's token freshness. Partner logs in separately
   for the advisory watch. Observe actual message delivery and alert latency.
3. Observe the fixed Oct 26–30 paper sample and 15:50 reports; Friday verdict
   does not itself authorize live orders or establish an edge.
4. Oct 31–Nov 1: funding, current broker login, read-only preflight, explicit
   real-order test and owner activation decision for Nov 2–6. None performed
   while the account is unfunded. Keep the old relay until the replacement
   completes a clean real session; avoid updates during market hours.

The only repository changes made by this slice are Dev documentation.
Existing unrelated dirty Dev files/document tails remain excluded.
