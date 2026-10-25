# Kite tunnel through supervised SSH (O25h, October 25)

## Installed route

Oracle website credentials are separate from the VM's SSH key. The key
cannot reveal a Console password. A read-only check using official OCI SDK
2.189.0 authenticated the VM's instance principal, but reading its own VNIC
returned 404 `NotAuthorizedOrNotFound`. No cloud rule or IAM change was made.
The temporary SDK was removed; its metadata-only result is retained root-only
at `/var/backups/kite-tunnel/o25h-20261025/instance-permission-result.json`.

We use the existing SSH access instead. No Oracle Console login, paid service,
new application library, or change to the legacy relay is needed:

```text
Docker client -> host.docker.internal:31528
             -> Windows 127.0.0.1:31528
             -> authenticated SSH to VM port 22
             -> VM localhost:31528 (existing Kite CONNECT service)
             -> verified TLS to api.kite.trade:443
```

Kite still sees the VM's outbound IP. A fake-token transport test establishes
TLS reachability, not registered-IP order acceptance or trading profitability.
Broker credentials are inside TLS; SSH also encrypts the CONNECT exchange.
Direct public 31528 remains blocked and is not used by this route.

## Windows task

Name: **Trading Sentinel - Kite SSH Bridge**. Action is the already installed
`C:\Windows\System32\OpenSSH\ssh.exe`; no custom daemon/helper was installed.

- Current owner's Interactive token, limited privileges, no stored Windows
  password. S4U registration was denied; this task requires owner login.
- Owner-logon trigger and indefinite one-minute recurring trigger;
  `MultipleInstances=IgnoreNew`, unlimited execution, retry after one minute.
- `-F NUL`, strict saved host keys, `BatchMode=yes`, `IdentitiesOnly=yes`,
  `ExitOnForwardFailure=yes`, 15-second keepalives / three missed replies,
  10-second connect timeout and one attempt per run.
- `-N -T -L 127.0.0.1:31528:127.0.0.1:31528 ubuntu@161.118.160.180`.
- Key `candidate-key` and host file `known_hosts` in the protected directory
  below. Never replace host checking with automatic acceptance.
- Starts on batteries and is not stopped on battery power. No visible SSH
  window was observed. This is not an unattended machine-boot service.

Keep Windows logged in during trading; locking the screen is different from
logging off. Sleep, network loss, VM outage and Windows/Docker updates can
still interrupt the route. Keep broker stops and existing route monitoring.
Actual reboot and physical network-loss recovery were not tested.

## Private settings and receipts

`C:\Users\Urveesh\sentinel-operations\oracle-access-20261025`

- `tunnel-client.env` and `tunnel-client-ssh.env`: two operator settings
  selecting `host.docker.internal:31528`, protected to the Windows owner.
- `tunnel-client-direct.env`: prior public-endpoint copy, still blocked.
- `ssh-bridge-task.xml`: exact task definition for restoration on this PC.
- `ssh-bridge-verification.json`: transport/recovery results, no password.

The settings contain the existing tunnel password. Do not paste them into
chat, logs, Git or screenshots. VM `kite_tunnel.py print-env` prints the
**direct** endpoint; it is not the selected SSH settings file.

**Production clients have not adopted these settings.** Follow step 5 in
[the live-test checklist](fno-live-test.md), the approved operator rollout,
broker login and read-only preflight before any later real-order test. No
Production `.env` edit/image change/live activation occurred in O25h.

## Verification completed

- Missing CONNECT password 407; authenticated other destination 403.
- Actual Dev engine client: Kite root 200 and fake broker token rejected.
- Actual gateway agent/SDK in disposable Linux image: root 200, TLS certificate
  verified, fake token rejected. No Production data volume mounted.
- Disabling/stopping this task closed its listener; Production health stayed
  HTTP 200 on the unchanged legacy route. Re-enabled/started successfully.
- Forced termination of only the verified bridge SSH PID: scheduled recovery
  produced a different SSH process/listener in **58.8 seconds**. After recovery,
  both deployed engine/gateway images passed the TLS transport check again.
- No real orders, broker login, outbound test message, duplicate listener,
  new cloud port or Production restart for these checks.

## Check, restore or stop

Run these ordinary PowerShell checks:

```powershell
Get-ScheduledTask -TaskName 'Trading Sentinel - Kite SSH Bridge'
Get-ScheduledTaskInfo -TaskName 'Trading Sentinel - Kite SSH Bridge'
Get-NetTCPConnection -LocalAddress 127.0.0.1 -LocalPort 31528 -State Listen
```

Expect `Running`, one listener, and task result 267009 / `0x41301` while
running (not an error). The two triggers are intentionally redundant.
If needed, `Start-ScheduledTask` for this exact name starts the existing task.
For restoration on this same PC, inspect the protected XML before using
`Register-ScheduledTask -TaskName <same-name> -Xml <file-contents>`; do not
overwrite an unrelated task. Different PCs require updated owner/key paths.

To stop it deliberately, disable then stop (otherwise the recurring trigger
starts it again):

```powershell
Disable-ScheduledTask -TaskName 'Trading Sentinel - Kite SSH Bridge'
Stop-ScheduledTask -TaskName 'Trading Sentinel - Kite SSH Bridge'
```

Enable then start with the matching cmdlets to restore it. If application
clients have adopted it, first deliberately restore/verify their prior route
through the operator rollout with new entries off; do not disable an active
order route first. Do not kill arbitrary SSH processes or stop the old relay
until the replacement has completed its clean real session.
