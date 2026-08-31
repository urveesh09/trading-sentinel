# Runbook: OCI relay (Kite endpoint) outage

_Last updated: 2026-07-12 (ROADMAP-2.6). Companion to the automated
probe in `python-engine/main.py` (`_kite_endpoint_probe_tick`)._

## What the relay is

Every quote and order the system makes transits `settings.KITE_BASE_URL`.
On the home desktop that is a path-preserving forward proxy on a free
Oracle Cloud Always-Free VM:

- **Relay host:** `161.118.160.180`
- **Relay port:** `31527`
- **Why it exists:** the home ISP cannot reach `api.kite.trade`
  directly; the desktop → relay hop works and the VM's IP is
  whitelisted in the Kite developer console (`SETUP_MANUAL.txt`).

There is **no automatic failover**: pointing `KITE_BASE_URL` straight at
`https://api.kite.trade` does not work from the home network — that is
the reason the relay exists. Recovery means fixing the relay (or moving
the stack to a network that can reach Kite directly).

## How you find out

- **Automated (2.6):** python-engine probes `KITE_BASE_URL/` every
  3 minutes during market hours. Two consecutive failures page
  Telegram (`📡 KITE ENDPOINT DOWN`), re-paged at most every 30 min
  while down, with a `✅ KITE ENDPOINT RECOVERED` notice when it heals.
  A 5xx answer counts as down (the relay answered but the path to Kite
  is broken).
- **Manual:** `bash python-engine/smoke_relay.sh` — expect
  `status=200` on both the host and in-container legs.

## Triage, in order

1. **Confirm from the host** (separates relay problems from container
   problems):

       curl -v -m 5 http://161.118.160.180:31527/

   - `200` here but the alert fired → problem is inside the container
     or its network; check `docker exec python-engine env | grep
     KITE_BASE_URL` and container DNS/network.
   - Timeout / connection refused / no route → continue below.

2. **"No route to host"** → the VM's iptables lost the 31527 ACCEPT
   rule (has happened before). SSH to the VM and:

       sudo iptables -I INPUT 5 -p tcp --dport 31527 -j ACCEPT
       sudo netfilter-persistent save

3. **Connection refused** → the relay process on the VM is not
   listening. SSH to the VM, check/restart the relay process, then
   re-run step 1.

4. **VM unreachable entirely** → check the Oracle Cloud console:
   instance state (Always-Free instances can be reclaimed/stopped),
   public IP unchanged, security list still allows 31527. If the
   public IP changed: update `KITE_BASE_URL` in both `.env` files
   AND whitelist the new IP in the Kite developer console
   (Kite errors such as "IP address is not allowed to place orders" are
   the symptom of forgetting the second half). Quote/token health does
   not prove order authorization.

   Sentinel records broker-order readiness separately as `UNVERIFIED`,
   `AUTHORIZED`, or `BLOCKED`. A real accepted order is the only positive
   evidence. A static-IP/permission rejection writes the shared global
   `HALT`, blocks every new live entry, and pages the operator; exits remain
   enabled so existing positions can still be reduced.

5. **Relay up, Kite itself down** (probe sees 5xx; Kite status page /
   broker outage) → nothing to fix on our side; positions may need
   manual management via the Kite app, which does not use the relay.

After correcting the relay/IP registration, reconcile all `UNKNOWN`/open orders
and broker positions and verify the registered egress IP before manually
clearing the global halt. If an existing position needs an exit, its accepted
exit provides direct authorization evidence. Never clear the halt merely
because quotes recovered.

## While the relay is down

- Scans produce no signals (quotes fail with connect errors, logged as
  `kite_endpoint_probe_failed` + per-call errors) and EXEC orders will
  fail. The system fails idle, not wrong — no stale-data trading.
- **Open positions are NOT managed** (no quotes → no stop checks).
  If you hold positions, manage them directly in the Kite app until
  recovery.

## Last resort

Run the stack from a network that can reach `api.kite.trade` directly
(e.g. a VPS or phone hotspot): set `KITE_BASE_URL=https://api.kite.trade`
in both `.env` files, restart containers, and make sure that network's
IP situation satisfies Kite's whitelist requirements.
