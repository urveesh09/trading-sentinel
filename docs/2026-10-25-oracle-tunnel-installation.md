# October 25 — O25e Oracle tunnel installation and recovered access

## Outcome

The already pushed O25d tunnel is now installed on the existing Oracle VM.
It is active and enabled, and the VM firewall rule survives a reboot.
The application's Production working copy has not been changed or deployed.
External TCP 31528 still times out: cloud ingress and application adoption
remain incomplete. Keep real-money trading off; no order was placed.

## Access and identity

- The owner authorized searching the attached storage and completing the VM setup.
- Read the attached 128 GB USB's Linux partition through a read-only file
  handle; no mount, repair or write to that disk. Searched the Linux Desktop,
  then the normal `.ssh` and Downloads locations: 204 bounded candidate files,
  no read errors. Desktop notes did not contain an SSH private key.
- Found `/home/urveesh/.ssh/id_ed25519`. Its saved known-host records matched
  `161.118.160.180`. Strict host-key verification was enforced when connecting;
  no new host key was automatically accepted.
- SSH authenticated as `ubuntu`; host `trading-sentinel`, Ubuntu 22.04.5 LTS,
  Python 3.10.12. Oracle instance metadata independently reports the expected
  instance name, Mumbai `ap-mumbai-1`, `VM.Standard.E2.1.Micro`.
- Recovery material and client settings are in the explicitly protected
  local folder `C:\Users\Urveesh\sentinel-operations\oracle-access-20261025`,
  outside both repositories. Private keys/passwords were not printed, added
  to Git, or placed in these documents. Do not paste those files into chat.

## VM changes and rollback

- Installed the exact committed `scripts/kite_tunnel.py` from **`94a262a`**.
  Local, committed and installed SHA-256 agree:
  `362d52a73bdd054fad4fa8181a5c35bdad9c374ff6bf6e43c7fc2c119e8360a9`.
- Program: `/opt/kite-tunnel/kite_tunnel.py`.
- Settings: `/etc/kite-tunnel.env`, mode `0600`, newly generated password.
- Unit: `/etc/systemd/system/kite-tunnel.service`, active and enabled.
- Added INPUT TCP 31528 ACCEPT before Oracle Ubuntu's REJECT; persisted in
  `/etc/iptables/rules.v4` using existing `netfilter-persistent`. UFW was inactive.
- The prior 31527 relay remains listening under the same PID (4053). It is a
  Python process in an old login session, not an nginx service; do not assume
  a particular service name when eventually retiring it. No VM reboot occurred.
- Baseline firewall and installer receipt are saved root-only under
  `/var/backups/kite-tunnel/o25d-20261025/`. Installer output there contains
  the generated settings and must stay private (`0600`).
- Rollback if the new service fails: stop/disable only `kite-tunnel`; use the
  committed uninstall path to remove its own files and TCP 31528 rule. Keep
  the old relay and existing application route. The firewall snapshot is a
  recovery reference; do not blindly restore an entire firewall after other
  administrators have made later changes.

## Verification and limits

| Check | Observed result |
|---|---|
| Installer against the actual VM service | Missing password **407**; other destination **403**; verified TLS to Kite **HTTP 200** |
| `systemctl is-active / is-enabled kite-tunnel` | Both exit 0: active / enabled |
| `systemd-analyze verify` on the actual unit | Exit 0; unrelated installed `snapd.service` warns about unsupported `RestartMode` |
| Live and persisted VM firewall | TCP 31528 present in both |
| VM settings / installer log permissions | Both `0600` |
| External connection from this PC to 31528 | Timed out; cloud-side rule still needs verification |
| Actual Dev `KiteClient` through a temporary SSH forward to this service | Kite root **200**; fake token rejected **403**; no order call |
| Actual Dev gateway tunnel agent + Kite SDK, in a disposable existing Linux gateway image | Kite root **200**, certificate verified; fake token rejected as `TokenException`; no order call |
| Temporary SSH forward and test container | Closed/removed after checks; never substituted for the deployed application route |
| Production Git checkout | Still `582d7a5e3a72d5fc8d4b1a4cf719cbc347e26479`, no tracked diff |

The direct public path is **not verified**. The two client checks used SSH
to reach the actual VM listener while cloud TCP 31528 was unavailable. They
verify the service and client transports, not cloud ingress, a current broker
login, free cash, registered-IP order acceptance, or profitability.

The engine and gateway Production containers were already stopped when
inspected: exit 137, `OOMKilled=false`, at **11:11:48 / 11:11:51 IST** on
October 25. Both times precede this installation. No cause is established;
do not label this an OOM event. They were not restarted. Their proxy settings
are unset and the live-test switch is unset (default off).

## Remaining work, in order

1. Owner completes Oracle sign-in/password recovery in Chrome. The console
   is not authenticated and the VM has no OCI CLI configuration. Do not reset
   credentials, create paid infrastructure or replace this VM to avoid that step.
2. Inspect the existing subnet security list / NSG that permits 31527, and
   add the intended TCP 31528 ingress rule without removing existing rules.
   Recheck external 407 / 403 / verified TLS and both clients over the direct
   public route. Current timeout alone does not identify the exact cloud rule.
3. Promote [draft PR #115](https://github.com/urveesh09/trading-sentinel/pull/115)
   through GitHub and follow the application rollout with trading off. Resolve
   the stopped Production services as part of that authorized rollout; this
   installation did not edit their working copy or restart them.
4. Apply the protected client settings through the agreed operator
   configuration process after deployment; do not set both engine order-base
   and proxy settings. Verify the actual gateway login and engine route.
5. Later: fund the account, obtain a current broker session, pass the read-only
   preflight, perform the explicitly authorized real-order test and decide
   activation for **Nov 2–6**. No order test while unfunded.
6. Retire 31527 only after a clean application session over the replacement.

No application source changed in O25e; the previous O25d software-test receipt
remains applicable. This is an installation/transport receipt, not evidence
that the strategy can earn money or that real trading is ready.
