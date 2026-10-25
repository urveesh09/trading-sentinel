# Runbook: the ₹12,500 real-money F&O test (O25–O25d)

_O25g operational update, October 25: **Production is recovered and PR #115
is merged/deployed at `0aa629a`**. Engine, gateway, agent and nginx are healthy;
the public dashboard and release identity checks passed. Automatic restart
and the engine's 20m x 25 log retention are effective. Steps 0/2 are done for
this release. Keep the real-money switch false. Oracle cloud TCP 31528 still
times out, so finish Console sign-in and step 4's cloud rule before adopting
the tunnel. Log in to Kite Monday morning before 09:15; the broker token is
currently expired. Partner watch requires the partner's separate login.
Telegram polling/API authentication passed, but outbound delivery was not
tested. See the [release receipt](../2026-10-25-production-recovery-and-release.md).
This supersedes the older stopped/not-deployed statements below._

_O25e actual setup, October 25: the tunnel is now installed and verified on
the existing Oracle VM, with its VM firewall rule persisted. SSH access was
recovered from the owner's attached Linux disk. External TCP 31528 still
times out, so step 4's Oracle cloud rule and the direct public route remain
pending; the owner is completing Oracle sign-in. Both client transports
passed against the actual service through a temporary SSH forward, which
is now closed. Steps 5 onward are not completed; no application configuration,
Production restart or real order occurred. See the
[installation receipt](../2026-10-25-oracle-tunnel-installation.md), including
the observation that the Production engine/gateway were already stopped._

_Written 2026-10-25, revised the same day after the audit-agent review (O25b) and
for the owner's dates and the encrypted tunnel (O25c). Code:
`python-engine/fno_live_test.py`, `fno_executor.py`, `fno_orchestrator.py`,
`fno_proving_week.py`, `fno_live_preflight.py`; the tunnel `scripts/kite_tunnel.py`
and `node-gateway/server/services/kite-tunnel.js`._

_O25d (code `94a262a`, pushed, not deployed) corrects all five findings in
[the review](../2026-10-25-independent-live-tunnel-review.md). Promote the
verified code through GitHub before using it operationally. Local tunnel
tests passed; actual VM installation/client routes must still be verified.
The account is unfunded: keep the trading switch false and do not place a
test order yet. The Python commands specify the application user because
the image installs its dependencies for `quantuser`._

## The dates (the owner's decision, Oct 25)

| When | What |
|---|---|
| Sun Oct 25 onward | VM/tunnel preparation may be done now, with the real-money switch false. |
| Mon Oct 26 – Fri Oct 30 | The proving week. Paper only: you watch the F&O book. No change to its rules. |
| Sat Oct 31 – Sun Nov 1 | You do the checklist below. Every step works on a weekend. |
| Mon Nov 2 – Fri Nov 6 | The real-money run: five sessions, then it stops by itself. |

Nothing here costs money. The Oracle VM is the Always-Free one you already
have, the tunnel uses only the Python that is already on it, and opening a
port in Oracle's console is free. The Kite Connect plan is unchanged.

## The checklist (once, in this order)

Work from the Production folder (`C:\Users\Urveesh\Desktop\Production_Trading-sentinel`)
once it has been updated from GitHub. Every command below runs from that folder.

### Before anything: is Production running?

    docker ps --format "{{.Names}} {{.Status}}"

`python-engine`, `node-gateway` and `agent` must show `Up`. On Oct 25 a Docker
Desktop update (11:12–11:15 IST) restarted Docker, and those three stayed
down: their restart policy did not survive it. While the gateway is down there
is no Telegram either. If any is not `Up`, from the Production folder, one at a time:

    docker start python-engine
    docker start node-gateway
    docker start agent

`quant_nginx` recovers by itself once the gateway is up. O25f sets
`restart: always` for the three, so after the next deploy a Docker restart
brings them back. Even so, do not update Docker Desktop or Windows during
market hours, above all Nov 2–6. An update in the session stops the engine;
an open real position then has only the broker's resting stop.

### 0. Optional, before Mon Oct 26 09:15: deploy now

If you merge and deploy before Monday's open, the engine sends the proving
week's progress at 15:50 every day and the verdict on Friday at 15:50. The
week then also proves the code that will trade. Nothing trades for real: the
switch stays off. If you deploy only at the weekend, step 1 gives you the
verdict then.

Merge the PR (`codex/production-correction-hedge-p0` → `evolve/smart-strategies`),
then rebuild one service at a time: the engine, then the gateway.

### 1. Read the verdict

It comes on Telegram on Fri Oct 30 at 15:50 if you deployed in step 0.
Otherwise read it now:

If step 0 was not completed, perform step 2 first, then return here. The
new module must be present in the deployed image before this command runs:

    docker exec --user quantuser python-engine python -m fno_proving_week

The rules were fixed on Oct 25:

- PROVED: at least one trade, no loss at one lot after one lot's own charges,
  nothing broken, and no drawdown halt;
- NOT PROVED: otherwise;
- NO EVIDENCE: no trade;
- UNAVAILABLE: the halt state could not be read.

Five sessions cannot prove an edge. Going ahead is your decision.

### 2. Deploy (if not done in step 0)

Merge the PR, then rebuild one service at a time: the engine, then the gateway.
The switch is still off, so nothing trades for real.

### 3. Cash

Have at least ₹12,500 of free cash in the Zerodha account. Pledged holdings
and margin do not count. A typical lot has cost about ₹8–9k; the morning
check compares the two.

### 4. The tunnel on the Oracle VM

Today all of the gateway's Kite traffic goes through the relay on port 31527
in plain HTTP. That includes the login exchange and the day's access token.
The tunnel replaces it: the token is inside TLS all the way to Kite, orders
still leave from the VM's registered IP, and it serves nothing else.

**[O25f] State on Oct 25: items 1 and 2 are done.** The tunnel was installed on
the VM on Oct 25 (O25e). A read-only check the same day showed the service
`kite-tunnel` active and enabled at boot, listening on 31528, with the VM's
own firewall accepting it. Its two `.env` lines are in
`C:\Users\Urveesh\sentinel-operations\oracle-access-20261025\tunnel-client.env`.
**Only item 3, the Oracle console rule, is left.** From this PC, 31528 does
not answer until that rule exists, while 31527 does. Items 1–2 remain below
for a reinstall.

1. Copy the program to the VM, from a PowerShell window in the Production folder:

       scp -i <your VM key> scripts\kite_tunnel.py ubuntu@161.118.160.180:~/

   (`ubuntu` is the usual user on Oracle's Ubuntu images; use yours if it differs.)
2. On the VM (`ssh -i <your VM key> ubuntu@161.118.160.180`):

       sudo python3 kite_tunnel.py install

   It installs a service called `kite-tunnel` on port 31528 and opens the
   VM's own firewall for that port. Then it tests itself: no password is
   refused, any other host is refused, and Kite is reached over verified TLS.
   Expect three `PASS` lines, then two `.env` lines. Copy those two lines
   somewhere private. Do not paste them into a chat or a screenshot: they
   hold the tunnel's password. If you lose them, `sudo python3 kite_tunnel.py print-env`
   prints them again. Running `install` again keeps the same password.
3. In the Oracle console, open the port (the VM firewall is not enough). Do
   it in the same place that allows 31527 today: usually Compute → Instances →
   your VM → its subnet → Security Lists → the list → **Add Ingress Rules**
   (or the VM's Network Security Group, if it uses one):
   - Source CIDR `0.0.0.0/0` (the password protects it). Or use your home
     IP `/32`, but then a change of home IP blocks orders until you update it.
   - IP Protocol: TCP.
   - Destination Port Range: `31528`.

Leave the old relay (31527) running for now: it is the fallback (step 10).

### 5. The two `.env` lines, with the switch still off

Take them from `tunnel-client.env` (step 4), or from `sudo python3 kite_tunnel.py print-env`
on the VM.

- `node-gateway\.env`: add the `KITE_PROXY_URL=…` line. Leave `KITE_BASE_URL`
  as it is: while `KITE_PROXY_URL` is set it is ignored, and deleting
  `KITE_PROXY_URL` takes the gateway back to the relay.
- `.env` (the root one, beside `docker-compose.yml`): add the
  `KITE_ORDER_PROXY_URL=…` line. Do not also set `KITE_ORDER_BASE_URL`.

Recreate the two services, one at a time:

    docker compose up -d --force-recreate python-engine
    docker compose up -d --force-recreate node-gateway

Check that the gateway took the tunnel. Expect `"encrypted":true` and no password:

    docker logs node-gateway 2>&1 | findstr kite_route

### 6. Log in to Kite on the dashboard

Do the usual login (it works on a weekend). The gateway's login exchange now
goes through the tunnel, so a successful login proves the gateway's route.

### 7. Check the engine's route (reads only)

    docker exec --user quantuser python-engine python -m fno_live_preflight

Expect:

- `Order route: https://api.kite.trade through the CONNECT proxy http://kite:***@161.118.160.180:31528 (TLS end to end)`;
- `Order route answers: yes`;
- your free cash, and no problem lines.

### 8. One test order (a real order, cancelled)

    docker exec --user quantuser -it python-engine python -m fno_live_preflight --test-order

Do not run this real-order command after any failed read-only preflight check.
Do not run it between 01:00 and 05:30 IST: Zerodha disables AMO placement,
modification and cancellation then, including on weekends. O25d enforces
that maintenance interval and refuses the order when required preflight
checks failed. While unfunded, stop at the read-only route checks in step 7;
the cash failure is expected and does not authorize a test order.

At a weekend this is an **after-market order** (AMO): a BUY of one lot of a
NIFTY call, 20% under its last price. Kite holds F&O AMOs until 09:15 on the
next trading day. The tool cancels it within seconds, so it never reaches the
exchange. In market hours it would be a regular order 20% under the bid,
cancelled at once. It refuses to run from 09:00 to 09:15 and from 15:25 to
15:45.

- Expect `PASS`. That proves Kite accepts orders from the tunnel's IP (the
  static-IP rule).
- A static-IP refusal trips the order-authorization halt. Fix the route,
  then clear the halt.
- `UNCLEAR`: open Kite → Orders and cancel the order yourself. For an AMO
  this must happen before 09:11 on the next trading day. Do not switch on
  until it is cancelled.
- In market hours it could fill in the very unlikely case the option falls
  20% in two seconds. It is then recorded as a real position, the engine
  sells it at once and you are paged.

### 9. Switch on (Sun Nov 1 evening, after funding, verification and owner decision)

In the root `.env`, add `FNO_LIVE_TEST_ENABLED=true`. Optionally also set
`FNO_LIVE_TEST_RUN=1`, `FNO_LIVE_TEST_SESSIONS=5`, `FNO_LIVE_TEST_CAPITAL=12500`
and `FNO_LIVE_TEST_FLOOR=7000`. Then:

    docker compose up -d --force-recreate python-engine

Do this before 09:15 or after the 15:40 close, never in the session.

The authorized entry dates default to `FNO_LIVE_TEST_START_DATE=2026-11-02`
and `FNO_LIVE_TEST_END_DATE=2026-11-06`. The start, end and five-session
limit are frozen in that run's record. Early activation cannot buy before
Nov 2; delayed startup cannot extend Nov 6. Changing the dates or session
limit in the environment cannot extend an existing name. A later run needs
a new name and explicitly authorized dates. Legacy rows without an end date
cannot admit entries; use a new authorized run name. Exits remain active
after the entry window ends.

**Monday Nov 2.** Do the usual morning login before 09:25. At 09:25 the engine
sends `✅ REAL-money F&O test ready today`, or `⚠️ NOT ready` with the reason.

### 10. After Monday's session: retire the old relay

After a clean session on the tunnel (logins, quotes and any real orders
working), stop the plain-HTTP relay so nothing can ever use it again:

1. On the VM, `sudo python3 kite_tunnel.py status` shows what listens on 31527.
   Stop and disable that program.
2. In the Oracle console, delete the ingress rule for port 31527.

Until then it is the fallback. If the tunnel fails:

- gateway: delete `KITE_PROXY_URL` from `node-gateway\.env` and recreate the gateway;
- engine: replace `KITE_ORDER_PROXY_URL` with `KITE_ORDER_BASE_URL=http://161.118.160.180:31527`
  and recreate the engine.

That is plain HTTP again, so use it only to get through the day.

**Run the preflight once.** Repeat steps 7–8 only after something in the order
path changes: the tunnel, the VM or its IP, the Zerodha API key or app, or a
new static IP. Nothing is run daily. While the test is on, the engine checks
every trading day by itself (below).

## What it is

The paper F&O single-leg book gets five sessions to prove itself (Oct 26–30).
If you go ahead, ₹12,500 of real money goes on it for one bounded run, five
sessions by default, with the sizing guardrails relaxed, to see how the system
trades with real fills. It is the pure intraday single-leg book only: no expiry
book, no spreads, no expiry-day trades.

One switch, `FNO_LIVE_TEST_ENABLED=true`, in the root `.env` that the
python-engine reads. It is off unless you set it.

The test **never decides a trade**. When the paper book buys a NIFTY option,
the test buys **one lot of the same contract** on the same signal bar. The
signal, strike, gates, reward/risk, the paper book's size tiers, loss brakes
and 15% drawdown halt decide for both. Exits use the same rules on the real
fill:

- the stop and target on NIFTY from the same signal;
- the 25% premium stop, the trail, the profit lock and the time stop;
- the 15:10 hard flat;
- a resting broker stop-loss order as a backstop.

| | Relaxed for this test only | Kept |
|---|---|---|
| Sizing | 2%-of-pool risk per trade: one lot instead; one stop-out risks about ₹1.5k–3.7k, 12–30% of ₹12,500 | own cash only: Kite refuses a buy the account's free cash cannot pay; no margin, no leverage |
| Pool gates | minimum-viable-pool and open-premium gates | the shared F&O ledger reserves the whole premium against the test's own equity |
| Go-live bar | PF ≥ 1.2, 60 trades, 40 days (`fno_go_live_check`) | NIFTY only (enforced in the buy itself), never on its expiry day, one position at a time, at most 3 entries a day |
| Run length | — | `FNO_LIVE_TEST_RUN` names it; its authorized start/end and `FNO_LIVE_TEST_SESSIONS` (default 5) are frozen. Defaults Nov 2–6; no delayed-start extension. Then no new entry and you are told |
| Floor | — | no new entry while test equity (capital plus realised real P&L) is under `FNO_LIVE_TEST_FLOOR`, ₹7,000 by default |
| Orders | — | LIMIT orders only, MIS (intraday) |

**The floor stops new entries; it does not guarantee ₹7,000 remains.** A
position already open can lose its whole premium if its exits cannot execute.
A five-session result also cannot establish profitability.

**Entry.** The buy is a LIMIT at the fresh ask plus two ticks, so it trades at
the ask or better. It is skipped when:

- that ask is more than 2% above the paper price (`FNO_LIVE_TEST_MAX_CHASE_PCT`);
- the quote is stale or one-sided;
- the spread is over 1.5%.

An unfilled buy is cancelled after 30 s and never chased.

**Exit.** One SELL LIMIT just under the bid, moved lower in steps until it
fills: 0.5%, then 3%, then 10% (or ₹5) under the bid, about 30 s in all.

- **Before it is sent:** the exit's own broker tag is recorded.
- **Once Kite gives an order id:** the id is recorded, before any wait. After
  a restart the engine follows the same order. A send whose reply was lost is
  found in Kite's order book by its tag. One that never reached Kite is sent
  again.
- **Price changes:** only those Kite accepts count. A refused change is
  retried on the next pass.
- **There is never a second SELL order.** The engine also never sells more
  than the broker shows it holding as MIS on NFO: an NRML holding of the same
  contract is not the system's to sell.

## What you will see

- **09:25 each trading day (while on):** `✅ REAL-money F&O test ready today`,
  or `⚠️ NOT ready` with the reason:
  - the route is not set, or does not answer (the tunnel);
  - no login yet;
  - free cash against a typical lot;
  - F&O positions held at the broker;
  - the run's session ("session 2 of 5") or that it has ended;
  - equity against the floor;
  - anything left from earlier.
- **Each real trade:** a `💰 REAL MONEY ENTRY [FNO_LIVE]` line with the paper
  price beside it, then a `💰 REAL MONEY EXIT` line.
- **15:50 each trading day:** the proving week's status (Oct 26–30), then each
  real trade beside its paper twin, with:
  - one lot each, after its own charges;
  - the decision-to-fill delay;
  - entry and exit slippage against paper;
  - how many times the exit price was moved, and how many changes were refused;
  - the state of the broker stop;
  - the paper trades not bought for real, and why;
  - anything outstanding (open positions, claimed exits, held reservations);
  - test equity.
- **Alerts:**
  - `📡 KITE ORDER ROUTE DOWN`: the tunnel failed two probes in a row (every
    3 min in market hours), with `✅ … RECOVERED` when it answers again;
  - the floor was reached, or the run ended;
  - a real exit was not placed (it is retried), is still working, or is
    unclear;
  - the broker does not hold (or only partly holds) a position;
  - a backstop was not placed;
  - order authorization was blocked;
  - the preflight test buy filled.

## What protects an open position

1. The engine's own exits, every 10 s (fast exit) and every 90 s (tick).
2. A resting SL order at the broker, 35% under the fill (limit 10% under
   that). It is for when the engine (or the tunnel) is down: the loss can then
   reach about 35–45% of the premium, ₹2.5k–5k on a typical lot, not 25%. A
   gap through the limit can leave it unfilled.
3. The 15:10 hard flat. Behind it, Zerodha squares off MIS positions itself
   in the afternoon (with its own charge).

## To stop

- **New entries:** set `FNO_LIVE_TEST_ENABLED=false` and recreate the engine.
  An open real position is still managed to its exit. When the run's sessions
  are used up, entries stop by themselves. A new run needs a new
  `FNO_LIVE_TEST_RUN` name and explicitly authorized start/end dates.
- **Now:** sell in Kite. The engine checks the broker's MIS positions before
  any real sell, so it will not sell it again. It pages you to record the exit
  with F&O exit recovery: `POST /ops/fno-exit-intents/{id}/resolve` with the
  Kite order id of your sale (`GET /ops/fno-exit-intents` lists it).

## The relay and the tunnel

| | The old relay (31527) | The tunnel (31528, O25c) |
|---|---|---|
| Kite's access token on the internet | readable (plain HTTP) | inside TLS from home to Kite |
| Who can use it | anyone who finds the port | only with the tunnel password |
| What it serves | any request, forwarded | CONNECT to `api.kite.trade:443` only |
| Orders leave from | the VM (registered IP) | the VM (registered IP) |
| Watched | no (the engine's own probe watches its direct link) | every 3 min in market hours |
| Cost | free | free (Python already on the VM) |

The tunnel password travels outside TLS, in the request that opens the tunnel.
Someone who captured it could reach `api.kite.trade` from the VM's IP, but
without your access token, which is always inside TLS, Kite gives them nothing.
On the VM: `sudo python3 kite_tunnel.py status` (state, listeners, last log
lines), `sudo python3 kite_tunnel.py uninstall`. The service restarts itself
and starts at boot.

## Known limits

- One lot only. A partial fill of one lot cannot happen on NSE (lots trade whole).
- Five sessions are a small sample. Paper and real will differ by fills and
  timing; the 15:50 report shows the gap per trade.
- The tunnel is one VM. If it is down, real orders and exits cannot be sent;
  the broker's resting stop and Zerodha's own MIS square-off remain.
