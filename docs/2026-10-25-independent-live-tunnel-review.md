# Independent O25b/O25c review — 25 October 2026

**Resolution update (O25d):** the owner subsequently authorized direct Dev
remediation. All five code comments below are now implemented locally with
regression coverage; the original observations remain historical evidence.
See the current O25d receipt in `NEXT_AGENT_PLAN.md` for verification and
commit/promotion state. VM setup still requires usable SSH/Oracle access.
No real order or trading activation forms part of this unfunded setup.

Reviewed Dev commits `abbe073` and `cff5036`, through documentation HEAD
`d67caad55b14319e84f292b979c469e506cecc8d`. A read-only `git ls-remote`
confirmed that exact head on `origin/codex/production-correction-hedge-p0`.

**Verdict: useful improvements, but do not enable real-money trading yet.**
The nine previous review items have corresponding changes and regression
coverage. The new tunnel passed an independent local test against real Kite.
The checks below found additional entry-boundary and operational gaps.

This is an audit, not a deployment. Only this review, the active plan, guide,
handover note and small runbook corrections were edited in Dev. No application
source, strategy, dependency, database schema or trading configuration was
changed. These documentation changes are local, uncommitted and not pushed.
Existing unrelated working-copy changes were preserved.

## Verified operational state

- Production checkout and running engine release:
  `582d7a5e3a72d5fc8d4b1a4cf719cbc347e26479`.
- Production engine and gateway were healthy when inspected. No services were
  restarted or recreated.
- Engine environment: test switch false; neither order proxy nor order-base
  override configured. Gateway proxy unset. No secret values were printed.
- Production database, read through SQLite `mode=ro`: zero open FNO_LIVE
  positions and zero FNO_LIVE exit intents.
- The cached Kite login was dated October 23, not October 25. Its token was
  rejected locally as stale; **no authenticated broker requests were sent**.
  Today's cash cannot therefore be confirmed. Do not reuse this check as
  evidence of available cash on November 2.
- A TCP connection to the VM's old port 31527 succeeded. Port 31528 timed out
  from this PC. This does not identify whether the service, VM firewall or
  Oracle rule is missing; it means the deployed tunnel is not verified.
- No local `.ssh`/`.oci` configuration or SSH/OCI environment configuration
  was available for this task. No VM login, install or firewall change was
  attempted.
- No open PR was returned for the specified head branch. No PR was created or
  merged during this review.
- The paper observation week, October 26–30, has not started at review time.
  There is no valid five-session verdict to act on yet.

## Findings and acceptance checks

### 1. P1 — an existing run's session limit is not frozen

`python-engine/fno_live_test.py:104–132` stores `sessions`, but does not read it
back. It uses the current environment setting instead. An already ended run
can resume without a new run name.

Isolated temporary-database reproduction:

```text
stored_sessions: 5
run label: audit
ended before changing environment: true
ended after setting sessions to 10: false
```

Required: use the persisted session count for that run. Test that changing
the environment cannot extend an ended run. Apply a deliberate, explicit
contract for changes to its recorded capital/floor/release too; recording
these fields alone does not freeze the runtime values.

### 2. P2 — November 2–6 is a checklist assumption, not an enforced window

`current_run` starts on the first date it is asked about while armed. There
is no earliest or latest calendar-date gate for the owner's intended run.
The reproduction accepts October 26 as session 1. A delayed first startup
can shift the five-session window beyond November 6.

Required: enforce the authorized start and final entry date independently
of first observation and session counting. Keep managing an open position
after the entry window ends. Test early activation, delayed startup,
restart, holidays and the final date. Keep dates explicit in a new run's
authorization rather than silently moving them.

### 3. P1 — failed preflight still invokes the real-order test

`python-engine/fno_live_preflight.py:157` always invokes `_test_order` when
the command-line flag is present, even after the route or evidence checks
have failed. A broker-double reproduction with an unavailable route returned
failure but still invoked the test-order function once.

Required: stop before the test-order function when required preflight checks
fail. Assert zero order calls for failed route, invalid configuration,
unavailable cash/positions/orders and insufficient required cash. Distinguish
an accepted/cancelled route test from overall readiness.

### 4. P1 — conflicting route settings can send credentials in plaintext

`python-engine/kite_client.py:804–808` accepts an HTTP order base together
with a proxy. HTTPX then sends a regular plaintext HTTP proxy request, not
CONNECT plus TLS. The preflight describes the conflict but does not prevent
the client making authenticated reads; the live entry path does not consult
that description either.

An isolated loopback proxy with **fake credentials only** observed:

```text
absolute_http_target: true
token_visible_in_cleartext: true
```

Required: validate the combination before constructing/using the authenticated
order client. The runbook's supported proxy configuration must always target
Kite through verified HTTPS. An invalid combination must send no authenticated
bytes. The deliberately insecure, operator-selected legacy fallback must not
be confused with the encrypted mode.

### 5. P2 — AMO maintenance window is missing

`variety_for` returns `amo` at 02:00 on a Sunday and a trading day.
Zerodha documents that AMOs cannot be placed, modified or cancelled between
01:00 and 05:30, including the cancellation operation this check relies on.

Required: refuse that interval before any order call and test exact boundaries
on trading and closed days. The runbook now warns the operator, but the code
guard remains pending.

Source checked on October 25:
[Zerodha AMO timings and maintenance](https://support.zerodha.com/category/trading-and-markets/charts-and-orders/order/articles/auto-amo).
The same source supports F&O AMO submission to the exchange at 09:15. That
does not guarantee cancellation: the tool must still verify the terminal
cancelled, zero-fill state.

### 6. P2 — a restricted installer blocks its own self-test

`scripts/kite_tunnel.py:132` rejects loopback if `--allow` contains only the
home address. `install` then invokes `self_test`, whose default host is
127.0.0.1. Reproduction: configured home address allowed, installer loopback
denied. The unrestricted default is unaffected.

Required: support a narrowly scoped authenticated loopback self-test while
retaining the external allow-list. Test the real installer/self-test path
with a restrictive list, plus denial of an unrelated external address.

### 7. P2 — container CLI instructions need the application user (corrected)

The running image installs Python dependencies in
`/home/quantuser/.local`; its entrypoint drops privileges for the application,
but `docker exec` defaults to root. The original command failed at import
with `ModuleNotFoundError: pydantic`. The same read-only check worked with
`docker exec --user quantuser`.

The Dev runbook's three engine commands now specify that user. The current
Dev Dockerfile uses the same dependency layout. This is a documentation fix;
no image or Production configuration was modified.

### 8. Checklist ordering correction

If optional step 0 was skipped, step 1 tried to invoke a new module before
step 2 deployed it. The runbook now explicitly sends the operator to step 2
first, then back to step 1. It also flags that application fixes and actual
VM/client-route verification remain prerequisites.

## Independent checks performed

1. Dev engine environment, Windows Python 3.11:

   ```text
   winvenv/Scripts/python.exe -m pytest
     tests/test_fno_live_test.py tests/test_fno_live_preflight.py
     tests/test_fno_proving_week.py tests/test_kite_endpoint_probe.py
     tests/test_fno_broker_backstop.py tests/test_fno_exit_recovery_boundary.py
     tests/test_fno_fast_exit.py ../scripts/tests/test_kite_tunnel.py
     -q -p no:cacheprovider
     -W error::pytest.PytestUnhandledThreadExceptionWarning
     -W error::pytest.PytestUnraisableExceptionWarning
   ```

   Result: **116 passed**, one existing Starlette deprecation warning.

2. Dev gateway:

   ```text
   npm test -- --runInBand tests/unit/kite-tunnel.test.js
     tests/unit/kite.test.js tests/unit/executor.test.js
   ```

   Result: **97 passed**.

3. The two native-SQLite gateway files on Windows:
   **18 failed, 2 passed**, all failures unable to load the native binding.
   This is not an all-green full gateway result. A separate disposable Linux
   run uses Dev source, the existing gateway image's Linux native libraries,
   no network and temporary files only: **20 passed**, both files, exit 0.
   Dev source was mounted read-only and copied into a temporary filesystem;
   the test process used the image's native SQLite dependencies and the
   existing Jest JavaScript packages. No Production volume or secret was
   mounted and the normal gateway entrypoint/application was not started.

4. A fresh, ephemeral local instance of the actual tunnel, bound only to
   loopback, with a randomly generated test password that was not printed:
   missing credentials → **407**, other destination → **403**, real
   `api.kite.trade` over verified TLS → **HTTP 200**. Only an unauthenticated
   GET of Kite's root was used; no broker login token or order was involved.

5. Additional isolated reproductions above used temporary databases,
   broker doubles and fake credentials. No application source was changed.

The full engine and full gateway suites were not independently rerun here.
Passing tests establish software behavior only, not trading profitability or
production deployment.

## What can be done now, and what remains

Completed here: review, focused checks, real local TLS self-test, safe
Production state inspection, VM-port reachability checks, remote Git identity
check, PR inventory and runbook corrections. No passwords were generated for
the real VM, printed or copied into configuration.

Next developer slice: close findings 1–6 with the acceptance checks above,
update the four system documents/atlas as required, and promote through GitHub
with the test switch false. Do not merge the current head as an assertion of
real-money readiness. Review the paper week under the intended code/version;
old-code paper evidence is not automatically proof of the newly deployed code.

Operator-dependent: current Kite login and free-cash evidence; VM SSH/install;
Oracle ingress rule; private configuration lines; actual service route checks;
explicit real-order test; owner activation for the intended dates. Do not
enable the switch in advance merely to exercise diagnostics. Restricting the
source address is useful after the allow-list/self-test issue is fixed; the
CONNECT password itself is documented to travel outside TLS.

Rollback remains entry-only disarming with open-position management retained.
Keep the legacy relay until the replacement is verified, then retire it via
the documented operator process. It remains plaintext while used.
