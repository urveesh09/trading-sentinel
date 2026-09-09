# Deployment verification runbook

This runbook prevents a healthy old container from being accepted as a newly
merged Sentinel release. It does not submit broker orders or send partner
messages.

## Promotion procedure

1. From the Production checkout, preserve the named data volume and record
   `git status --short`. Stop if tracked files are modified or history is not
   a fast-forward to the reviewed `evolve/smart-strategies` target. Do not
   reset, delete, or recreate the data volume.
2. Fetch and fast-forward that checkout to the reviewed target SHA. Do not
   pull `main` as a substitute for the release branch.
3. In PowerShell, stamp the exact checkout into the build, rebuild the three
   application services, and recreate them using the existing Compose
   procedure:

   ```powershell
   $sentinelReleaseSha = git rev-parse HEAD
   $env:SENTINEL_RELEASE_SHA = $sentinelReleaseSha
   $env:SENTINEL_BUILD_UTC = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
   docker compose build node-gateway python-engine agent
   docker compose up -d --no-deps --force-recreate node-gateway python-engine agent
   ```

4. Verify the live deployment and keep the receipt outside the repository
   (for example under the persistent operations archive):

   ```powershell
   python scripts/verify_deployment.py --expected-sha $sentinelReleaseSha --receipt C:\sentinel-operations\release-receipts\$sentinelReleaseSha.json
   ```

   This fails closed when any of node-gateway, python-engine, or agent is
   absent, stamped with a different SHA, stamped with no build UTC, or when
   the gateway and engine health payloads disagree. A green container status
   and image creation time alone are not acceptance evidence.
5. Then carry out the release plan's read-only health, scheduler, migration,
   authenticated quote, archive-manifest, and next-market-session observation
   checks. Verify NIFTY and SENSEX separately. A version receipt proves only
   source deployment; it does not prove input readiness or qualified advice.

## Failure handling

Do not restart to mask an identity failure. Preserve the receipt/error and
compare the checkout SHA, Compose build environment, image IDs, and runtime
`/api/health` payload. Rollbacks must retain new research archives and be
checked for database migration compatibility.
