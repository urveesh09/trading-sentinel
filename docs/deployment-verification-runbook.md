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

## Review correction: immutable image identity

Compose no longer overrides baked release metadata at runtime. The verifier
compares the actual image's metadata with container metadata and rejects stopped
containers. Regression tests cover an old image relabelled with a new runtime SHA.

After merging the correction into evolve/smart-strategies, use PowerShell below.
Complete the consistent data backup described above first. Run after market hours.
Every native-command failure stops the procedure; do not continue manually past it.

```powershell
Set-Location 'C:\Users\Urveesh\Desktop\Production_Trading-sentinel'
function Invoke-SentinelStep {
    param([string]$Program, [string[]]$Arguments)
    & $Program @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Program failed; deployment stopped" }
}
if ((git branch --show-current) -ne 'evolve/smart-strategies') { throw 'Wrong release branch' }
if (git status --porcelain --untracked-files=no) { throw 'Tracked changes: preserve and resolve before deploying' }
Invoke-SentinelStep git @('fetch','origin','evolve/smart-strategies')
Invoke-SentinelStep git @('merge','--ff-only','origin/evolve/smart-strategies')
$sentinelReleaseSha = git rev-parse HEAD
$env:SENTINEL_RELEASE_SHA = $sentinelReleaseSha
$env:SENTINEL_BUILD_UTC = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
Invoke-SentinelStep docker @('compose','build','node-gateway','python-engine','agent')
Invoke-SentinelStep docker @('compose','up','-d','--no-deps','--force-recreate','node-gateway','python-engine','agent')
# Re-resolve the recreated gateway address in nginx's static upstream.
Invoke-SentinelStep docker @('compose','restart','nginx')
Start-Sleep -Seconds 30
Invoke-SentinelStep python @('scripts/verify_deployment.py','--expected-sha',$sentinelReleaseSha,'--receipt',"$env:USERPROFILE\sentinel-operations\release-receipts\$sentinelReleaseSha.json")
```

If startup is still in progress, inspect health/logs and rerun verification after
readiness; do not bypass it with --skip-health. No down -v, volume deletion or
reset is needed. A successful receipt verifies release identity, not broker/data
readiness or profitable strategies. Follow step 5 and the passive-release research
export runbook before accepting next-session collection.
