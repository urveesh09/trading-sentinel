# Independent review of the October 13 fixes — October 15, 2026 IST

Scope: review Dev `433a81a` / documentation `8390c87`, compare with Production `4fd45f3`, and install the two explicitly requested reference-data files in the running engine's persistent `/data` volume. No source changes, strategy changes, deployment, notification sends or broker calls are authorized by this review.

## Data installation plan and acceptance

- Problem: `/data/nifty500.csv` and `/data/penny_company_data.json` are absent in the running engine.
- Sources/contracts: the Dev checkout's tracked `python-engine/data/nifty500.csv` (500 unique symbols; headers `tradingsymbol,exchange,sector`) and `python-engine/data/penny_company_data.json` (87 unique records; declared `as_of=2026-07-16`). These are supplied reference files, not freshly verified October fundamentals or constituents.
- Change: copy these two files into the existing `production_trading-sentinel_trading_data` volume only. Stage each file, verify its SHA-256 and parseability, then atomically rename it to the requested destination with read permission for `quantuser`. Do not edit Production source or rebuild/restart services.
- Acceptance: destination bytes/hashes match the Dev files, CSV/JSON validate, runtime user can read them, tracked Production files remain unchanged. Confirm the loader paths and disclose when files are only consumed on a later load/refresh.
- Rollout/rollback: this is the user's explicit runtime-data installation request, separate from GitHub code promotion. Both destinations were absent before installation; retain that fact and hashes for rollback. Do not overwrite any independently created file discovered during staging. Code promotion still requires the normal GitHub merge and rebuild.
- Remaining: finish installation and independent review, record verification results and any actionable defects below.

## Verdict

The release improves terminal buyer management, quote dispatch, costs and observability. No strategy-rule or threshold edits were found in this commit; fee correctness can still change modeled P&L and available risk reserve. It is not an unconditional approval: the recovery and reporting edge cases below remain. They were reproduced with fake providers and isolated stores, not inferred from test counts. No strategy profitability claim follows from this review.

## Independent verification

Run from Dev `python-engine`, using `winvenv/Scripts/python.exe`:

```text
-m pytest tests/test_oct13_audit_fixes.py tests/test_partner_buyer.py tests/test_partner_manual_advisory.py tests/test_kite_endpoint_budget.py tests/test_scheduler_tick.py tests/test_oct12_audit_fixes.py tests/test_fno_costs.py -q
120 passed; normal exit; 10.98s

-m pytest tests/test_partner_orchestrator.py tests/test_scheduler_closures_invoke.py tests/test_scheduler_h1_coroutine_guards.py tests/test_kite_client_methods.py tests/test_s5_provider_lanes.py tests/test_expiry_paper.py tests/test_research_quote_collection_deadline_p1.py tests/test_research_quote_runtime_cap_f2.py -q
183 passed; normal exit; 161.18s
```

Total **303 passed**, no failures or skips in these runs. Both emitted the existing Starlette async-generator lifespan deprecation warning. The full engine suite's reported 5,174 pass / 4 skip / one deselected test was not independently rerun; the excluded test therefore remains outside that claim. Initial collection using a nonexistent quote-test filename collected no tests; the corrected commands above completed successfully.

Expiry source is absent from the reviewed commit's changed-file list. Its tests pass, but shared quote changes still affect its runtime dependencies. No broker calls, real notifications or trading-job invocations were made by the isolated probes.

Verified improvements:

- Invalidation and terminal idea status commit together; old invalidations are reconciled; pending and final authorization layers refuse later target/reminder messages while permitting the fresh stop update.
- Buyer fallback renders one BUY option or keeps the idea undelivered; it does not deliver the old SELL-leg spread card.
- Failed flow pulses preserve the delivered-message cap and use bounded failure retry/backoff.
- The quote send gate covers numeric attempts, retries and keyed calls; late batch and dispatcher-cancellation tests pass. This is meaningful additional protection over admission-only spacing, not evidence of zero future provider errors or account-wide coordination.
- SENSEX routes to the BFO cost schedule for the changed call sites. The same-fill calculation reproduces ₹61.84206092416 rather than the NSE ₹62.28941497216. The rates match the broker's published charges: [Zerodha charges](https://zerodha.com/charges/).
- Daily Penny R and paper-exit provenance are corrected without altering the 1% paper model. Hourly single-position fixtures pass, with an identity-matching defect described below.

## Actionable findings and next Dev plan slice

### F1 — P2: login wait can cross EDGE's exit window

Files/contracts: `python-engine/scheduler_setup.py:642-658`; startup admission window ends at 15:15, the normal EDGE exit is scheduled at 15:15. The new ten-minute token wait does not recheck the window before invoking the scan. The safe scan wrapper checks calendar/token, not this cutoff.

Independent probe executed the actual nested function AST with fake clock, token, scanner and HTTP sender. A catch-up starting at 15:14:59, with token arriving at 15:20, invoked the scan at **15:20**. No real orders were placed in the probe. In operation, this can admit new exposure after the normal exit pass; live authority remains separately gated.

Correction: re-read the clock after token readiness and before scan/admission; refuse catch-up after its declared entry window. Use the same guard at the actual entry boundary if scanning can itself cross the cutoff. Do not change strategy thresholds.

Acceptance: before-cutoff token succeeds; token arriving at/after cutoff cannot enter; scan crossing cutoff cannot create a late fill; existing exits continue.

### F2 — P2: an EDGE error is persisted as a completed daily scan

Files/contracts: `scheduler_setup.py:606-607`; `penny_edge_orchestrator.py:598` returns a non-raising `regime='ERROR'` result after engine failure. The wrapper marks the day completed for every returned summary. A both-disabled result also returns normally.

Probe: scanner returned the actual error-result shape, `penny_edge_scan_state.json` was written, and the next catch-up skipped it. Total scan calls remained **1**, despite no successful scan.

Correction: persist explicit successful completion, distinguish unavailable/error/disabled from valid zero-signal completion, and use an atomic receipt. Recheck completion after token waiting; serialize cron/catch-up if they can overlap.

Acceptance: error then healthy restart retries; a valid zero-candidate scan does not repeat; completed day stays idempotent; interrupted receipt writes cannot suppress recovery.

### F3 — P2: target-first cards still include post-stop recovery as held performance

Files/contracts: `partner_orchestrator.py:294-308,1937-1947`. `_todays_card_outcomes` retains only the first event. The buyer wrap passes `stopped_at` only if that first event is INVALIDATION. A later stop is lost when a target occurred first.

Probe using real advisory queue functions: target at 11:40, invalidation at 11:45, later option recovery at 14:40. The wrap selected TARGET_ZONE and printed `option ₹97.35 → peak ₹200 (+105%), last ₹200 (+105%)`, without `after exit (not held)`, although the idea had stopped.

Correction: keep the first-event scoring contract, but separately carry the actual invalidation/closure timestamp into the premium path. Do not infer partner fills or alter target-first historical scoring.

Acceptance: target → stop → recovery labels recovery not held; stop-first remains correct; target with no later stop preserves the continuing path.

### F4 — P2: startup exposure and alert delivery are incomplete

Files/contracts: `main.py:2446-2490`. Counts cover only three tables in the main database. Overnight, expiry and Smart Penny have independent sibling stores. Any SQLite error becomes zero, including an unreadable store/table. This can falsely imply flatness. The alert's HTTP response is ignored and there is no durable retry.

Probes: with one OPEN overnight sibling-store holding and no main-book holdings, returned counts were all **0**. A fake gateway HTTP **503** returned normally; `raise_for_status` was never called and no retry record was persisted. Probe reruns exited cleanly; an initial scratch SQLite handle cleanup failure was corrected in the review harness, not product code.

Correction: read all operational books through read-only readers, distinguish UNKNOWN from zero, and describe these as observations at recovery rather than an atomic historical snapshot. Use acknowledged, durable delivery for the restart page, with bounded retry and deduplication.

Acceptance: each sibling-only exposure is visible; unreadable books say unknown; 503/refusal then recovery delivers once under acknowledged operation; lost acknowledgment is documented rather than promised exactly-once.

### F5 — P2: hourly Penny fills can be borrowed from another trade/book

Files/contracts: `penny_hourly_report.py:145-146`. The new lookup takes the latest position for the ticker anywhere in the report hour. It does not join by signal/position identity, source or product, or the particular signal's admission time.

Probe: actual Penny MIS fill **₹51.92** at 08:06 UTC, unrelated EDGE CNC position in the same ticker at **₹70** at 08:20 UTC. The report rendered `UNITEDPOLY MIS x9 @ 70.00 (signal 52.92)`.

Correction: use stable signal-to-position provenance. Where no stable identity exists, require an unambiguous source/product/time match; otherwise show the signal and unknown fill instead of guessing.

Acceptance: two same-ticker books, re-entry within one hour, paper/live separation and accepted-but-unfilled signal cases must not cross-match.

## Lifecycle evidence limitations

Wall time advancing ahead of monotonic time is consistent with suspend, but an adjustable realtime-clock step can also produce it. A heartbeat-thread stall does not uniquely prove the asyncio loop froze, and absence of such a stall does not prove the loop stayed responsive. Keep the new evidence, but use candidate-cause wording and correlate with host logs. [Linux clock documentation](https://man7.org/linux/man-pages/man2/clock_gettime.2.html) distinguishes adjustable realtime from monotonic and suspend-aware boottime clocks.

The code honestly retains `unclean_stop` when a restart's exact cause is unavailable. It cannot retroactively establish Oct 13 host sleep. No missed monitoring or fills are reconstructed.

## Requested data installation — completed

The two absent files were staged, parsed, hash-checked and atomically installed into the persistent engine volume, owner UID/GID 1000 and mode 0644. Runtime user `quantuser` successfully read both after installation:

| Destination | Bytes | Records | SHA-256 |
| --- | ---: | ---: | --- |
| `/data/nifty500.csv` | 10,529 | 500 unique symbols | `9df33043dbcd7c441b502503bc019fabc1ff002849a16e55da0999886571f493` |
| `/data/penny_company_data.json` | 8,999 | 87 unique company records | `d78dd2888b5bcf43c4ad06e0e1c5b3f6d82a52c884e9f420744471477d7dcb42` |

`settings.UNIVERSE_PATH` is `/data/nifty500.csv`; `_load_universe_with_fallback` reads it on a subsequent universe load. `main.PENNY_CORP_DATA_JSON_PATH` points to `/data/penny_company_data.json`, passed to the scheduled refresh. Copying does not retroactively replace an in-memory universe or force a refresh. No refresh was manually invoked. The company file declares **July 16, 2026**, 91 days before this review; its fundamentals were not reverified, and the CSV was not recertified as current exchange constituents. Installing supplied files is not a data-freshness upgrade.

Production tracked diff remains empty. Production checkout and runtime release SHA remain **4fd45f3**; engine stayed healthy. Dev HEAD and tracked remote both remain **8390c87**. The requested two reference files are installed, but the reviewed code remains **pushed, not deployed**. No migrations, configuration changes, rebuilds, restarts, commits or pushes were performed. This report is a new uncommitted Dev artifact.

## Promotion and first-day acceptance

Implement F1–F5 in Dev with the acceptance cases above, update the active plan/guide and atlas per AGENTS.md, then promote through GitHub and rebuild. Keep exit/risk policies and experiment boundaries unchanged. F1/F2 should be corrected before calling EDGE recovery finished; F3–F5 are remaining correctness work, not reasons to discard the core fixes.

After deployment, verify actual runtime release identity; no target/reminder after a stop for the same identity; post-stop recovery labels in both event orders; process-generation quote over-limit counters and actual HTTP429 counts; startup receipt plus acknowledged restart page with every book represented; EDGE success/error receipts; and the research collector's full-job runtime and completeness. Kite's quote contract is 1 request/second: [Kite limits](https://kite.trade/docs/connect/v3/exceptions/). Healthy counters and passing fake-provider tests do not replace first-day runtime evidence.

Rollback remains a reviewed GitHub source revert/rebuild. Preserve terminal idea rows and additive receipts/data; do not rewrite historical ledgers to make comparisons look better. The new runtime data can be rolled back independently because neither destination existed beforehand; only these exact files/hashes belong to this installation.

