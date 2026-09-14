# Consistent data backup and code rollback

This procedure is a release prerequisite, not authorization to interrupt Production. Obtain an exclusive, explicitly authorized after-hours maintenance window. Do not stop services with open positions needing management, pending consequential dispatch, or unresolved protective exits. Resolve operator ownership first. Do not use `down -v`, delete volumes, copy only a live SQLite main file, or restore old data over newer history.

## Inventory and quiescence

1. Retain the reviewed old/new Git SHAs, image IDs/build metadata, container IDs and service health receipt outside the repository. Inspect the current application containers' `Mounts` (not complete environment/secret values) and resolve the exact existing Docker volume name mounted at `/data`. Compose's logical `trading_data` name is project-prefixed in practice; never guess a volume or use a Dev volume as a Production substitute.
2. Inspect effective non-secret storage paths. The source default is `/data/research`; an overridden external archive, bind mount, gateway DB, journal or provider cache needs its own inventoried capture in the same quiescent window. Include token/claim/reconciliation state, operational SQLite databases with WAL/SHM companions, public/candidate captures, quote segments/manifests, raw/canonical masters, attempt and selected-leg journals. Inventory is full-tree, not only files ending in `.db`.
3. Suspend restart automation/autoheal and any external writers or backup/cleanup jobs with authorization; retain their previous states. Stop application writers gracefully using the normal operator procedure. The agent's declared `/data` mount is read-only, but stop all consumers to remove uncertainty. Find *every* container using the resolved volume with `docker ps -a --filter volume=<exact-name>`; inspect their actual running state and mounts. Also account for host/bind/external writers. A stopped Compose trio does not prove no other writer exists.
4. Retain a quiescence receipt: UTC start, exact volume/source IDs, consumer IDs and states, external writer/restart controls, open-position/dispatch checks, responsible operator and original release identity. Exclusive ownership continues until inventory, archive and verification are complete. Recheck consumers and external writer controls afterward. If a writer returns, abandon the consistency claim, preserve the failed capture and obtain a new capture; do not make a raced inventory match by deleting evidence.

Source inventory checklist: gateway `signals.db`, `app.db`, `sessions.db` and their companions; engine effective `DB_PATH` (default `/data/cache.db`); research writer lease, selected-leg and per-attempt SQLite journals; `.open` quote streams and temporary files as well as finalized gzip/manifest pairs; masters, public/candidate captures; token/HALT/readiness/claim state, scheduler ticks, instrument/universe/event inputs, CSV logs and dead letters. Lazy migrations/retention exist across modules, not one migration ledger. Do not run EOD purge, direct F&O OI purge, selected-leg retention, telemetry cleanup, cache cleanup, repair or relabel scripts while capturing/rehearsing. Legacy repair scripts' single-main-file backup is not acceptable evidence of a consistent WAL backup.

## Capture and integrity verification

Use reviewed `scripts/verify_data_backup.py`. The helper does not stop services or establish quiescence. Use a new empty, access-restricted backup directory outside the repository and outside the source volume. Backups can contain persisted provider tokens and private account data: secure/encrypt them under the operator's approved storage policy; do not upload to GitHub or print file contents. Stop if secure storage is unavailable.

The following is a template for the authorized window, not an instruction to run now. Resolve values from actual mounts and reviewed tool/image identity; require cached approved helper images (no implicit pulling during maintenance). Every failed native command stops the procedure. `Invoke-SentinelStep` is defined in the deployment runbook.

```powershell
# Set these explicitly after actual-mount inventory; do not guess names.
# $sentinelDataVolume = exact existing volume name
# $sentinelBackupDirectory = new restricted empty absolute directory
# $sentinelBackupTool = absolute path to reviewed verify_data_backup.py
# $sentinelPythonImage / $sentinelTarImage = approved cached image IDs
Invoke-SentinelStep docker @('volume','inspect',$sentinelDataVolume,'--format','{{.Name}}')
Invoke-SentinelStep docker @('ps','-a','--filter',"volume=$sentinelDataVolume",'--format','{{.ID}} {{.Status}} {{.Names}}')
# Record and verify all consumers stopped and exclusive external ownership.
Invoke-SentinelStep docker @('run','--rm','--pull=never','--network','none','--entrypoint','python',
  '--mount',"type=volume,source=$sentinelDataVolume,target=/source,readonly",
  '--mount',"type=bind,source=$sentinelBackupDirectory,target=/backup",
  '--mount',"type=bind,source=$sentinelBackupTool,target=/tool.py,readonly",
  $sentinelPythonImage,'/tool.py','inventory','/source','--output','/backup/inventory.json')
Invoke-SentinelStep docker @('run','--rm','--pull=never','--network','none','--entrypoint','tar',
  '--mount',"type=volume,source=$sentinelDataVolume,target=/source,readonly",
  '--mount',"type=bind,source=$sentinelBackupDirectory,target=/backup",
  $sentinelTarImage,'-C','/source','-cf','/backup/data.tar','.')
Invoke-SentinelStep docker @('run','--rm','--pull=never','--network','none','--entrypoint','python',
  '--mount',"type=bind,source=$sentinelBackupDirectory,target=/backup",
  '--mount',"type=bind,source=$sentinelBackupTool,target=/tool.py,readonly",
  $sentinelPythonImage,'/tool.py','verify','/backup/data.tar',
  '--expected-inventory','/backup/inventory.json','--receipt','/backup/integrity-receipt.json')
# Reinspect exact consumer states/external controls and close quiescence receipt.
```

Do not reuse a backup directory: receipts are exclusive, and tar itself can overwrite a named output. Check the newly resolved output is absent before capture. Retain inventory, archive, integrity receipt, independent quiescence receipt and release/mount identities together. File/hash matching catches omission of a WAL present in inventory; SQLite `integrity_check` alone cannot detect that committed rows were lost by omitting WAL. Verification extracts into isolated scratch, never opens the original live DB. A receipt says `INTEGRITY_VERIFIED_CONSISTENCY_UNPROVEN`: only the independent operator receipt plus source scope/absence of writers can support consistency. Integrity checks cannot prove broker/account reconciliation or economic truth.

Defaults bound source/tar membership to 100,000 entries and expanded file data to 10 GiB; inventory JSON is limited to 64 MiB. Plan sufficient isolated scratch space before starting. If actual data exceeds limits, stop and review explicit `--max-members`/`--max-bytes` values and disk capacity rather than omit records or silently loosen bounds. Source enumeration failures and unsupported symlink/special/Windows-aliased paths fail closed. SQLite validation covers files with the SQLite header, regardless of extension; independently reconcile the intended database list with receipt observations. Non-SQLite files receive hash coverage, not a database-validity claim. Receipt `inventory_sha256` hashes the retained inventory file bytes, not a self-referential field.

## Restore rehearsal and rollback

Before release acceptance, rehearse restoration into a *new isolated volume* or directory with no network, no broker/Telegram credentials and no operational Compose services. Retain the original backup and source volume unchanged. Verify archive digest/inventory, every SQLite integrity observation, ledger row/economic identities and public/candidate/master/attempt/selected-leg relationships. Run old/new startup migrations against separate copies; prove row preservation, readable archive versions and claim/backoff/ambiguity retention. Do not accidentally start the application entrypoint against the restored fixture merely to test status.

Compatibility checklist includes ledger `origin_ref`; intraday-cache columns; attempt `public_observed_at_utc`; advisory `profile_id`; delivery `claim_token`; shadow `execution_json`; positions/signal-log additive columns; gateway protective-order/execution state columns. Inspect the actual reviewed release diff for more. Keep v1/v2/v3 research inputs and legacy reports readable but do not let legacy evidence grant qualification. Raw-master-digest enforcement can invalidate old instrument caches: prove normal provider refresh and clear unavailable reporting, not an unauthorized deletion of retained source evidence. No silent feature-default or risk-budget change is allowed during rollback.

Code rollback uses the reviewed previous GitHub release and stamped rebuild/recreate/identity verification. Test previous code against a copy of the *current post-migration data*, not just pre-release backup. Additive schema is not automatic compatibility: previous loaders may reject new source formats or ignore claim semantics. Preserve all post-backup cash, trades, positions, claims and evidence. A data rollback/restoration requires a separate reviewed reconciliation/merge plan and explicit authority; never replace the live volume with a pre-release snapshot to make checks pass.

Resume only the intended services and restore automation to its recorded state through the release procedure. Verify image and HTTP fingerprints, provider readiness and delivery/source switches; do not send advice or place an order as a backup test. Record failure/rollback and next-session observations separately from backup success. Actual Production backup, restore rehearsal and maintenance authorization remain outstanding until their receipts exist.
