# F&O evidence foundation: verification and implementation handoff

## Latest release assessment — c0377a7, 8 September 2026

Supersedes prior completion summaries. Reviewed `c0377a7623d559c0c992ecc56d868ce2defcba15`. **No unconditional green light for unattended default-on deployment yet.** S1 is materially fixed; S2 improved; S3/S4 are partial. No new tests or implementation-note updates were included in this commit. Independently ran the seven-module suite: **92 passed**, one deprecation warning.

### Verified improvements

- Protected cleanup now compares row ID and all archived values, and the zero-eligible branch excludes protected indices. Repeating the export-then-update probe preserved OI=999: the prior evidence-loss bug is fixed.
- Missing-token runs are journalled. Invalid/nonfinite/mismatched future references are rejected; individual option normalisation/writes have exception handling.
- Active quote-file size is capped at a configured 256 MiB. Latest observation summaries persist across finalisation.

### Remaining release corrections, without expanding scope

1. **Finish S3 resource guarantees:** the 256 MiB cap covers the active quote file, not journals, summary writes, candidate/master/export data, quarantine or compression. Recovery/finalisation still bypass temporary-space checks. Implement the promised bounded first-session policy across producers, preserve the operational disk reserve during temporary writes and emit a distinct storage-stop reason. `max_queue` remains unused; either implement bounded admission or document/test the actual bounded sequential design and ensure other archive producers cannot saturate it. Offload/bound synchronous verification and readiness reads. Do not call the current cap a complete archive budget.
2. **Finish S4 truthful freshness:** age and provider-time validation remain absent. Offline probe: an August 1 quote with no provider timestamp, finalised before reading status, still reports `OBSERVED_USABLE`. This is historical observation, not current readiness. Add observed-but-stale/time-unknown states and preserve last-valid separately from last-seen. Stop rescanning the entire open quote file from the request path; the new summary currently coexists with that old scan.
3. **Finish the batch exception boundary:** initial reference and individual packet errors are caught, but strike selection and the second `_documented_quotes` request remain outside per-index handling. A raised exception there can prevent the other index from being collected and discard detailed partial results. Test the failure path and persist partial outcomes.
4. **Add regression evidence for this commit:** changed-row/zero-eligible cleanup races, session cap/restart, disk pressure during temporary writes, missing token, failed second batch with the other index succeeding, and stale/missing-time readiness. Existing passing tests alone do not exercise these new behaviours.

Once these narrowly defined checks pass, green-light a **passive observation deployment**, subject to the existing image/mount/access/export smoke checks. Do not hold that release for complete strategy research. This review does not authorise or execute a deployment.

### What the partner will actually receive

**Next session after deployment:** this increment gives the system better retained evidence and diagnostics. It adds no new qualified strategy and does not itself increase messages. Actionable NIFTY/SENSEX tips still require the explicit INTRADAY profile, genuine policy-specific qualification, a valid current opportunity and working delivery configuration. Do not promise tips or profits tomorrow solely from merging this code. Existing independently qualified policies, if present, remain governed by their own checks.

A limited read-only check of `/data/cache.db` in the running `python-engine` container found no tables matching the new partner profile/qualification/artifact table names. This does not establish the running application's actual configured DB path or all deployed state; it therefore does not prove absence globally. It does mean this review has not verified a saved production profile or qualified policy. Deployment acceptance must inspect the authoritative configured DB through the authenticated effective-settings/qualification interfaces. No secrets, profile payloads, orders or messages were accessed or changed.

**Following sessions:** retained quotes can support liquidity, costs and entry/exit research. Collection alone does not learn or qualify strategies automatically. Continue building the exact-policy replay/evaluator, active-leg coverage and reproducible comparisons in Dev immediately. Only after sufficient real evidence and separate qualification can improved selection, pricing limits and timing benefit actual tips. There is no honest fixed date or guaranteed return for that stage.

**Remaining product work:** exact NIFTY and SENSEX intraday policy studies; continued quote coverage of active legs; finer-frequency ingestion; realistic multi-leg/manual-delay replay; holdout strategy comparisons; reviewed qualification and profile setup; evidence-based ranking and management updates; optional AI explanations. Keep the partner independent of broker monitoring. A separately authorised fixed TEST message can check receipt before any strategy qualifies.

Owner's next action: return the four release corrections above to the coding agent, then merge the verified observation revision through GitHub. Do not wait idly for data before implementing the research pipeline. Production was not modified during this review; only this Dev plan was updated.

---

## Release decision — 2117715 review, 8 September 2026

This section supersedes earlier status summaries. Reviewed Dev HEAD `211771597aa8587459201892fb7ce74e73db543c`. Only three files changed since `72178fa`: archive, collector and archive tests. Production was not inspected or modified in this review; deployment, entitlement and performance remain unverified. No live messages or orders were sent.

**Recommendation: do not deploy this exact revision with all passive defaults unattended. Make the small safety checkpoint below, then deploy collection through GitHub for the next session. Do not wait for completed strategy research, and do not stop implementing while observations accumulate.** The claim that only post-deployment research remains is not supported by the diff.

### Verified in this increment

- Complete JSON without a trailing newline is repaired before appending; collection-run journals now use tail recovery too.
- Infinite integer depth values are caught rather than raising `OverflowError`.
- Option collection rejects explicit returned-token mismatches; per-index requested/received tokens are recorded.
- Readiness derives a displayed-book observation from active quote records and uses `NOT_EVALUATED_HERE` for qualification.
- Independently reran the seven-module suite documented below: **92 passed**, one Starlette deprecation warning. This is a different selected suite from the reported 114; no claim that all 114 were independently reproduced.

The earlier comment that malformed packets are fully isolated is too broad: no per-packet/per-index exception boundary was added. The initial futures price still passes through unchecked `float(...)`; malformed/nonfinite values can abort selection. Token validation is after that initial reference quote, so it does not protect the first futures-based universe selection.

### Minimum rollout-safety checkpoint (next commit)

**S1. Protect cleanup against unarchived changes.** `fno_oi_store.py` was untouched. An offline temporary-DB probe exported a NIFTY row with OI=100, updated it to OI=999 before deletion, and ran cleanup: **zero rows remained**, although the updated value had never been archived. Fix deletion to condition on exact exported logical identity plus values/revision within a short transaction. Fix the zero-eligible branch so a concurrently inserted protected row cannot be caught by broad cleanup. Tests must cover both races and row-ID reuse. A row-ID-only condition is insufficient. Do not disable `RESEARCH_ARCHIVE_REQUIRED_BEFORE_FNO_PURGE` as a workaround; that authorises ordinary deletion.

**S2. Make the collector survive individual bad inputs and report no access.** Validate the initial future's token, Mapping type and finite positive price before selecting strikes. Add per-index/per-packet error isolation with durable partial counts. Record the missing-token result exactly once; it still returns before journalling. Test bad NIFTY reference with valid SENSEX, malformed option data among valid packets, absent token and token mismatch in the reference request.

**S3. Bound first-session storage and work.** Cover finalisation, quarantine, append and journal payloads with temporary-space-aware capacity checks; current reserve protection does not cover every write. Add a hard per-session research byte budget and bounded background admission (the existing `max_queue` setting does not implement a queue). Stop intake with an operational diagnostic when the budget is reached; never silently delete referenced data. Keep slow research work off the event loop, including verification and readiness reads. Full multi-month catalogue/retention can follow after this bounded first-session release, but document and enforce the temporary retention/storage limit rather than leaving it implicit.

**S4. Make status safe to interpret.** Current `OBSERVED_USABLE` means a positive uncrossed displayed book in an open file, not a fresh, timestamp-valid quote. Show age, provider-time validity and per-index last success/error; use separate stale/unknown states. Finalisation removes the open file, causing the current view to forget observations. Persist a bounded latest-observation summary across finalisation/restart instead of repeatedly reading the whole active file synchronously. Test closed partitions, stale/missing provider time and malformed journal lines. Do not use the current readiness label to approve research or delivery.

Acceptance: rerun the existing suite plus these focused regressions, simulated low-disk/slow-storage checks and the documented HTTP response-contract tests for both exchanges. Update the implementation note with explicit outstanding work. The checkpoint is an observation-release requirement, not a strategy qualification test.

### Once that checkpoint passes: merge and deploy collection

1. Merge the corrected revision through GitHub and verify the running image revision, persistent `/data/research` mount, permissions, measured free space and configured session budget. Do not infer deployment from Dev HEAD or checkout alone.
2. Run the existing source-read-only export command below under the verified application user before scheduled cleanup. Verify hashes, row counts and NIFTY/SENSEX scope, and keep the manifest. No live DB copying or manual cleanup test.
3. Start passive research collection; confirm actual NFO and BFO master/quote responses and first archived packets during the open session. Check provider timestamp and contract identity, not just HTTP success or file existence.
4. Check after the first few collection intervals and near session end: both indices observed, gaps explained, disk budget respected, no material scheduler delay, active legs retained where supported, and archive finalisation/restart intact. Record actual results; no retrospective claims of continuous depth from minute snapshots.
5. Keep actionable partner delivery under its existing intraday profile/qualification guards. This data deployment does not authorise new strategies. A separately authorised fixed TEST Telegram diagnostic can verify routing independently of qualifications.
6. If intake fails or breaches its resource budget, pause it through the normal deployment/configuration path and investigate. Keep evidence preservation enabled. Turning off quote collection alone does not stop candidate/master/preservation writes; report each archive producer's effective state.

### Continue these implementation milestones immediately in Dev

| Can build now | Needs real observations to finish evaluation |
|---|---|
| Exact `partner-manual-intraday-v1` debit-spread evaluator for each index, with dated lot/expiry rules | Actual liquidity, missing-data patterns and practical price availability |
| Replay engine, strict datasets, reproducibility manifests and chronological holdout pipeline | Out-of-sample strategy results on collected observations |
| Active/evaluated-leg pinning through outcome horizon, input-bar archive, WebSocket ingestion and labelled REST fallback | Real reconnect/session coverage and finer-frequency execution evidence |
| Cost/manual-delay scenarios, no-fill/unknown outcomes, drawdown and opportunity diagnostics | Statistically adequate evidence to qualify each policy/index separately |
| Frozen strategy comparison, optional AI explanation boundary and reference-aware storage catalogue | Live usefulness and optional partner feedback |

Do not spend the next sessions merely waiting. The current modelled research wrapper is still the older NIFTY single-option strategy; building and testing the correct policy does not require waiting for live data. Synthetic fixtures validate software only; do not register them as genuine market research. Real evidence is needed for qualification, not for beginning implementation.

**Owner action:** have the coding agent complete S1–S4, then merge/deploy the corrected observation release. No new paid data purchase or partner strategy is required for this step. Risk-per-idea/lot preferences remain inputs for personalised sizing later. No guarantee of research completion or profitable tips after a fixed number of sessions is implied.

---

## Updated review — HEAD 72178fa, 8 September 2026

This status update supersedes the original completion/blocker assessment below. The original review and acceptance criteria remain as context; do not redo completed items. Reviewed commits `bc09cf3 fix: harden F&O evidence collection integrity` and `72178fa feat: expose per-index research readiness`, including their implementation comments. No tracked application changes were present. Production deployment/provider operation was not tested or changed in this review.

**Verdict: substantial integrity corrections completed, but Checkpoint A is not fully closed. B is partial; the actual strategy-research and advisory improvements in C/D remain outstanding.** Do not treat passing tests or readiness counts as qualification to send profitable tips.

Independent validation: the same seven-module suite listed below now passes **90 tests**, with one Starlette deprecation warning. Additional offline probes found the newline recovery and nonfinite-value defects described below. These are software checks, not live evidence or a profitability study.

### Completed since the original review

| Original item | Verified progress | Remaining scope |
|---|---|---|
| A1 packet integrity | REST timestamp correctly selected; raw packet retained; zero/nonpositive book values unusable; locked/crossed states distinguished; new documented exchange:symbol client method | Malformed-packet isolation, nonfinite integer handling, token mismatch validation and HTTP-boundary tests |
| A2 crash/gap evidence | Truncated JSON tail quarantined before a new writer appends; writer UUID and sequence; durable normal collection runs and several scheduler states | Valid JSON without newline; run-journal repair; missing token; per-index failure isolation and durable exact requested universe |
| A3 preservation | Both protected tables counted; cutoff-scoped export, hash verification and exported-row deletion; unprotected indices explicitly retain ordinary cleanup | Row-ID reuse/content mutation and zero-eligible race; streaming; unique capture publication |
| A4 runtime isolation | Export, quote/master/candidate writes and quote finalisation moved to worker threads; capacity prechecks added to export/master/candidate paths | Capacity coverage, bounded admission/retention, synchronous verification/readiness reads and whole-file memory use |
| B readiness | Per-index master metadata, recent gaps, latest run and free/total disk bytes exposed | Real per-index quote status, freshness, effective flags, verified source capabilities and bounded reads |
| C actual strategy studies | No new implementation in these two commits | Entire exact-policy research workstream remains; legacy model is unchanged |
| D partner improvements | No new implementation in these two commits | Evidence-backed ranking, research-driven promotion and operational acceptance remain |

### Next correction commit — precise remaining tasks

**R1 / P1 — finish archive-before-purge protection (`fno_oi_store.py`).**

- Exported `rowid` alone is not immutable identity. A row can be updated in place or removed/replaced between export and deletion; SQLite can reuse IDs. Current `DELETE ... WHERE rowid IN (...)` can erase content not represented by the archive. Compare immutable logical keys plus all exported values/revision under the deletion transaction, or use a persisted immutable row revision. Skip changed rows for the next export.
- If the initial count is zero, current code calls broad `purge_older_than`; a protected old row arriving between count and delete is still unprotected. In this branch delete only explicitly unprotected scopes, or recheck/protect within a safe transaction.
- Add race tests: insert after zero count; mutate same row after export; delete/reinsert with reused row ID; normal late insert; futures-only data. Preserve every changed/unexported protected row.
- Strengthen manifest validation with expected schema/files/counts/source/cutoff/scope. Keep export parsing outside the write transaction and use properly closed file handles. Avoid treating the unused last-timestamp verifier as valid coverage proof.

**R2 / P1 — close restart and malformed-packet edges (`research_archive.py`, `research_quote_collector.py`).**

- Reopening a file ending in complete JSON without a newline currently appends the next JSON directly to it. Probe: existing `{"id":1}` plus one new event finalises to **zero events**. Repair the missing delimiter before append; retain both records. Apply recovery to the collection-run journal too, whose damaged tail currently joins onto subsequent entries.
- `_finite_positive(float('inf'), int)` raises `OverflowError`; it is not caught. Catch overflow, validate field types and finite futures-reference price, and isolate each malformed packet and index so one bad NIFTY record cannot suppress SENSEX.
- Validate returned `instrument_token` against the requested dated contract; the new exchange:symbol method currently trusts the key while retaining the requested token even if the packet contradicts it. Record mismatches rather than archive mislabelled quotes.
- Acceptance includes missing newline, truncated newline-delimited records, malformed scalar/list packets, infinite quantity/price, NaN forward and wrong-token fixtures through the real HTTP adapter. Preserve valid events surrounding failures.

**R3 / P1 — complete trustworthy collection status (`research_quote_collector.py`, readiness API).**

- `no_market_data_token` returns before the journal write and the scheduler directly returns that result. Persist exactly one outcome for every attempted tick, including no token and partial progress before an exception. When storage itself fails, emit a separate operational failure; do not report durable journalling success.
- Record requested/received contract identities and per-index counts, elapsed time and timestamp-quality statistics, not just aggregate totals. Keep detailed partial outcomes when exceptions occur.
- Readiness currently hardcodes `quote_observation_status=NOT_YET_OBSERVED` and `qualification=NOT_QUALIFIED`, and assigns the same latest global run timestamp to each index. Probe confirmed the quote status stays unchanged after recorded successful collection. Derive index observation status from actual validated packets, not a run heartbeat. Represent qualification as `NOT_EVALUATED_HERE` or query the authoritative registry; never manufacture a negative or positive qualification status.
- Return last valid quote time, stale age, master freshness, expected versus received packets, index-specific last failure and actual effective enablement. Token presence remains unverified access. Capability/OI work from original B is still outstanding.
- Acceptance: NIFTY-only success never implies SENSEX success; no token visible; stale quotes visible; current observations not marked unobserved; one bad journal line does not discard later valid runs.

**R4 / P1 — bound storage and background work before unattended operation.**

- `asyncio.to_thread` removes event-loop blocking for several writes but is not a bounded queue/admission policy. `max_queue` remains unused. Add bounded research admission and measurable saturation with explicit operational priority.
- Quote compression/finalisation and tail quarantine still lack temporary-space reserve checks. Append/journal checks exclude the new payload size; concurrent checks do not reserve combined space. Cover these paths with a shared budget/reservation policy and count losses accurately (`_dropped` currently remains zero).
- Exports, finalisation/recovery and verification still read whole files into memory. Verification and exported-row parsing still run synchronously in the async purge path. Stream them and offload bounded filesystem work.
- New readiness scans full contract files and several full run journals on every request in the async route. Build a bounded materialised per-index summary; do not let archive growth increase request/event-loop latency indefinitely.
- Add catalogue/reference retention, disk-pressure alerting and a documented pause policy. Test low disk during compression/recovery and blocked disk I/O without missed advisory lifecycle deadlines.

### Work after the correction checkpoint — do not stop at another safety increment

1. **Deploy observation foundation:** after R1–R4 verification, use GitHub deployment and the export runbook below. Record deployed image, hashes and per-index coverage. Run a read-only actual provider check. A full session validates collection operation, not strategy profitability.
2. **Finish B collection coverage:** retain active/evaluated option legs outside the rolling ATM window through outcome expiry; archive actual strategy input bars and availability times; implement WebSocket full-mode ingestion with explicit REST fallback. This is essential to avoid losing exit data during large moves.
3. **Implement C in parallel with forward collection:** strict research inputs, reproducible retained datasets/code/effective defaults; evaluate the actual `partner-manual-intraday-v1` debit-spread logic separately for NIFTY and SENSEX. Legacy NIFTY FNO-MOM results cannot qualify it. Do not wait for weeks of collected quotes before building the offline evaluator.
4. **Run a small predeclared strategy comparison:** continuation, opening-range breakout and failed-breakout challenger; chronological holdout; costs, manual delay, unknown/no-fill outcomes, drawdown and opportunity frequency. Preserve evidence categories and avoid claiming short-delay fills from minute snapshots.
5. **Implement D only from measured results:** rank qualified timely ideas, compare entry/exit choices, suppress overlapping index risk, and prioritise invalidation/exit messages. Optional MiniMax explains and proposes research; deterministic code controls numerical terms and qualification.

### Required deliverable from the next coding agent

Deliver a correction commit with R1–R4 test evidence, then continue B/C as separately reviewable milestones. Update this table with exact completed acceptance criteria and remaining gaps. Do not claim the entire roadmap complete after infrastructure fixes. No new paid data source, partner broker connection, order authority or fake qualification is required. Any unresolved partner lot/risk preferences remain explicit inputs rather than inferred from the owner's testing capital.

This update changes the existing plan only. Application fixes above have **not** been implemented by this review.

---

Date: 8 September 2026. Reviewed Dev HEAD `f2df1e55c7289ce853142871dc81c940cf0c4a32`.

## Decision in plain language

The commit adds useful machinery to save data that previously disappeared and to begin collecting option prices/depth. It is a partial implementation of the free-data research plan, not completed strategy research or evidence that partner tips will be profitable.

Correct the collection and preservation defects below before enabling unattended research collection in Production. Do not delay these corrections for the larger strategy programme. Deploy the corrected observation foundation through GitHub, preserve the retained data, then build and evaluate the actual intraday advisory policy while forward collection runs.

No Production files, settings, databases, orders or messages were changed during this review. This is a Dev source review and offline verification; deployed operation and actual provider entitlement were not verified in this review. Earlier implementation claims are not treated as evidence of deployed behaviour.

## What is complete

| Area | Verified implementation | Important limit |
|---|---|---|
| Retained evidence export | SQLite read-only transaction; NIFTY/SENSEX selection; JSONL, schema, hashes and manifest | Captures retained LTP/OI, not past depth; purge coverage needs correction |
| Contract archive | Raw NFO/BFO CSV and canonical dated contract terms; content hashes | Runs when master refresh runs; no per-index freshness/failure dashboard |
| Forward collection | Independent minute scheduler; front future and nearby options across two expiries; five depth slots | REST snapshots, no integrated WebSocket collector; timestamp/gap/restart defects |
| Candidate audit | Saves candidates reaching `persist_candidate`, including invalid/rejected candidates | Does not prove every earlier scanner rejection is captured or retain continuing leg coverage |
| Research wrapper | NIFTY modelled report; optional chronological split; no automatic qualification | Uses older FNO-MOM single-option backtest, not partner debit-spread policy; SENSEX explicitly refused |
| Provider abstraction | Kite wrappers, capability structure, Breeze request shape | Token presence is not verified entitlement; Breeze transport absent |
| Readiness API | Internal-secret check, archive counts, collection switch | Counts do not establish usable data, freshness or research readiness |

The boundaries against placing orders and automatically qualifying strategies are appropriate. Preserve them.

## Independent verification

Executed from `python-engine` using `winvenv\Scripts\python.exe`:

```text
python -m pytest -q tests/test_research_archive.py tests/test_fno_oi_store.py tests/test_fno_instruments.py tests/test_partner_orchestrator.py tests/test_hedge_routes.py tests/test_scheduler_closures_invoke.py tests/test_main_surface_characterization.py
86 passed
```

Two warnings: Starlette lifespan deprecation and an unawaited Penny scheduler coroutine in the scheduler test. Neither failed this run; investigate the test warning separately without claiming runtime Penny failure from it. This review's selected set differs from the agent's reported 65 tests.

Additional temporary-directory probes:

1. Write valid quote, append truncated JSON, restart writer, append another valid quote, finalise: only **one** valid event survives; expected two.
2. Supply a REST packet with `timestamp`: normalised `exchange_timestamp` is **None**.
3. Supply zero-price/zero-quantity bid and ask: `missing_depth` is **False**.

These findings are independent of passing happy-path tests. No performance/profit backtest was independently run.

## Checkpoint A — correct evidence integrity before unattended rollout

### A1. Correct provider packet handling and verify the real API boundary

Files: `research_quote_collector.py`, `kite_client.py`, source-contract tests.

- For REST full quotes use provider `timestamp`; retain WebSocket `exchange_timestamp` separately by mode. Preserve original timestamp, parsed UTC, receipt UTC and explicit parse failure. Never substitute receipt time for an absent exchange time.
- Treat zero/nonfinite/nonpositive price or quantity as unusable depth. Preserve raw observations, distinguish missing/locked/crossed/malformed books, and validate finite numeric values without terminating the remaining batch.
- Persist raw payload or immutable raw-packet reference: the current raw hash alone cannot reconstruct fields discarded by normalisation.
- Verify both NFO and BFO through the actual HTTP response parser. Existing `KiteClient.get_quote` sends numeric identifiers and converts response keys using `int(k)`, whereas the documented full-quote interface uses exchange:symbol keys. Do not assume this inherited numeric route works merely because a stub returns integer keys. Use the documented exchange:symbol mapping and packet token where required, maintaining compatibility for existing consumers.
- Acceptance: representative documented REST fixtures for both indices, absent fields, invalid dates, stale/future timestamps, zero books and one malformed packet among good packets. After deployment perform an authorised read-only provider smoke check and record successful contract identity/timestamps, without secrets.

Official reference: [Kite full quotes and instruments](https://kite.trade/docs/connect/v3/market-quotes/). It documents `timestamp`, exchange:symbol lookup, missing keys and dated token reuse. This review does not claim the inherited numeric interface has been observed failing live.

### A2. Make crash recovery and missing-data evidence durable

Files: `research_archive.py`, `research_quote_collector.py`, `scheduler_setup.py`.

- On reopening a segment, repair/quarantine its incomplete tail before appending. Record discarded bytes and corruption reason. A later valid packet must never be concatenated onto damaged JSON and lost.
- Add boot/writer identity and monotonic sequence within that identity. Current sequence resets on restart; reconnect epoch remains zero. Do not imply a process-local monotonic clock orders multiple boots.
- Persist each scan's requested universe, returned universe, missing packets, errors, disabled/session states and elapsed time. Currently `gaps` is only returned and the scheduler discards the return value; ordinary missing-master/quote cases can leave no durable explanation.
- Track expected collection cadence and missed runs. Isolate one index/provider packet failure from the other index.
- Acceptance: interrupted append followed by same-day restart; repeated restart; missing entire batch; one missing leg; scheduler exception; stale master; partial segment corruption; measurable durable gap counts.

### A3. Make archive-before-purge coverage exact

Files: `fno_oi_store.py`, `research_archive.py`, preservation CLI/tests.

- Current guard counts only old chain rows. If only old `fno_fut_snap` rows exist, it purges them without export. Export selects configured indices, but purge deletes all indices. Explicitly define protected scope and preserve both tables within that scope before deleting them.
- Bind deletion to the exact exported row identities/cutoff and verified complete manifest. A separate export followed by broad time-based deletion can delete a concurrently inserted old row that the export never saw. Avoid a long write lock: use a bounded staged identity set and short conditional deletion transaction.
- Verify file hashes/counts and completion before destructive cleanup. `verify_fno_export_for_cutoff` is unused and its newest-timestamp check does not prove every earlier row is preserved; do not activate it as a shortcut.
- Stream/chunk export instead of loading all rows and JSON into memory. Use collision-resistant capture IDs and an explicit complete publication marker. Do not repeatedly export overlapping entire histories for every purge when incremental covered ranges suffice.
- Acceptance: futures-only history; mixed indices; filtered exports; late old-row insert; disk failure; incomplete/corrupt manifest; retry in same second; source DB unchanged during export. Protected rows remain until verified preservation.

### A4. Bound disk and event-loop impact

- The one-GiB check exists only in `QuoteArchive.append`. Export, master, candidate writes and compression bypass it. Apply a shared capacity policy to all writers, allowing for temporary compression/export space.
- `max_queue` is stored but unused; there is no bounded background writer. File writes/fsync and whole-file finalisation currently run synchronously inside async workflows, including candidate persistence. Move blocking research work off the operational event loop with bounded admission, timeouts and counters.
- Retention needs a catalogue of partitions and report/candidate references. Never delete inputs referenced by retained reports; expose disk pressure and stop new research intake predictably. Do not solve failed preservation by silently deleting protected evidence or allowing the operational DB to grow indefinitely without alert/escalation.
- Acceptance: all archive paths respect simulated low disk; writer saturation is visible; slow storage does not stall lifecycle deadlines; retention preserves referenced files. Record measured write volume, disk headroom and scheduler latency in the deployed environment.

## Checkpoint B — usable daily collection and operational acceptance

1. Keep the rolling ATM universe, but pin evaluated/active candidate legs until their management deadline and outcome horizon even when they leave that universe. Persist pin/release reasons. Otherwise moves that matter most may lose exit evidence.
2. Archive the underlying inputs needed to reproduce decisions, with candle close/availability times and dated contracts. Do not reconstruct history with today's instrument master.
3. Add full-mode WebSocket ingestion using available infrastructure, with bounded queue and reconnect/subscription journals. Preserve REST as an explicitly lower-frequency fallback; one-minute observations cannot demonstrate 15-second execution quality.
4. Expand readiness per index: effective enablement (both archive and collector), verified entitlement status/time, master date/hash, last valid quote, clock lag, requested/received counts, gaps, pinned-leg coverage, active/finalised partitions, bytes/free space, latest error and next action. Token presence must be `configured/unverified`, not `entitled=true`.
5. Historical OI capability must reflect implemented retrieval: the current historical wrapper calls a client method that does not request `oi=1`. Implement and test OI parsing or report it unavailable in this adapter. Separate provider-supported capabilities from implemented and successfully probed capabilities.

Acceptance: one full observed session for each index including restart/reconnect evidence and known missing-data intervals. This is an operational acceptance test, not statistical strategy qualification. Do not wait for this session to begin implementing Checkpoint C offline.

## Checkpoint C — research the actual tips, not a different strategy

The existing wrapper freezes a data fingerprint but not input files, effective defaults, source commit or dependency versions. It permits NaN/infinity and incoherent OHLC values. Its backtest hardcodes NIFTY lot size 75 and synthetic expiry assumptions. Label it legacy exploratory FNO-MOM research; do not register it as proof for `partner-manual-intraday-v1`.

Implement:

- Strict finite OHLCV validation, coherent ranges, timezone/session/bar-completion checks, missing-session report and chronological availability controls.
- Persist exact input partitions, hashes, code commit, effective parameters (resolve defaults), calendar/contract metadata and policy identity. A hash without retained inputs is insufficient for reproducibility.
- An evaluator calling the same deterministic candidate, payoff, cost, entry cutoff, invalidation and exit rules used by partner intraday advice. NIFTY/NFO and SENSEX/BFO remain separately calibrated, reported and qualified.
- Historical source acquisition using existing authorised Kite access first; optional Breeze only if authorised account access exists. The present Breeze request class is not a downloader. No paid vendor purchase is needed to start. Label underlying-only, modelled-option and observed-quote results separately.
- Start with a small frozen comparison: trend continuation debit spread, opening-range breakout debit spread, and a carefully filtered failed-breakout/mean-reversion challenger. These are hypotheses, not promised improvements. Conditional protection remains exposure-dependent and separate from directional spreads.
- Use chronological development, untouched evaluation and walk-forward windows; retain every eligible/rejected/no-fill/unknown-outcome candidate. Evaluate net expectancy after costs, drawdown, tail losses, opportunity frequency, stability by index/regime/time and practical displayed capacity.
- Compare manual response delays, spread-width choices and exit policies. Test 15/30/60-second delays only where observation frequency supports them; sparse data produces unknown/interval bounds, not invented fills. Price both legs conservatively and never assume simultaneous execution or guaranteed displayed liquidity.
- Predeclare sample adequacy, confidence/uncertainty treatment, maximum tolerable drawdown and promotion thresholds before inspecting holdout results. More calendar days alone do not qualify a strategy; avoid selecting the best of many trials without controlling selection bias.

Acceptance: reproducible reports for both indices, frozen strategy comparison and explicit evidence gaps. Produce a genuine immutable reviewed artifact for the exact policy before qualification. No dummy references, AI-generated prices or automatic promotion because a report exists.

## Checkpoint D — convert evidence into useful partner advice

- Rank qualified ideas by net opportunity, liquidity/capacity, regime fit and timeliness; suppress duplicated correlated NIFTY/SENSEX exposure. Treat activity diagnostics as a way to find broken scans, not a quota requiring trades.
- Cards give index/exchange, exact contracts, maximum entry debit, trigger, invalidation, target, full-lot estimated cost/risk and intraday deadline. Prioritise invalidation and exit management over new ideas.
- Make an execution window explicit: expired prices are not actionable. Publish conditional protection only with explicit exposure assumptions; a debit spread alone is not a personalised portfolio hedge.
- MiniMax may explain deterministic evidence, summarise research and propose challengers asynchronously. It cannot fabricate observations, change validated numerical terms, bypass gates or approve its own strategy.
- Collect optional Taken/Skipped/Closed feedback to measure usefulness and practical delay. Do not require partner broker access or imply simulated P&L is their actual earnings.
- Validate Telegram routing through the separate fixed TEST/no-advice diagnostic after explicit send authorisation. This can verify receipt before strategy qualifications exist. It must not enable actionable tips.

## Exact rollout sequence and responsibilities

1. Coding agent implements A1–A4 with regression evidence in Dev, then updates the implementation note accurately. Keep prior review artifacts intact. Commit/push through the existing branch workflow.
2. Owner merges through GitHub. Verify deployed image revision, persistent archive mount and disk headroom. Do not equate a changed checkout with a rebuilt running image.
3. Preserve retained records promptly after corrected deployment and before cleanup. In the current Dockerfile dependencies belong to `quantuser`; a default root `docker exec ... python` may not find them. Verify the running container/user/path first. Expected command after confirming this layout:

```powershell
docker exec --user quantuser --workdir /app python-engine python research_cli.py export-fno --source-db /data/cache.db --archive-root /data/research --underlyings NIFTY,SENSEX
```

4. Check completion, requested-index counts and every manifest file hash. Record capture path, deployed commit and coverage. Export command is an operational archive write with a read-only source; it was not executed during this audit. Do not run cleanup manually to test preservation on live data.
5. Enable corrected bounded collection; agent checks B acceptance and begins C. Continue existing actionable-delivery safeguards; data collection and tip permission are separate.
6. Agent prepares explicit INTRADAY profile and genuine policy-specific artifacts/qualification proposals from evidence. Owner supplies any unresolved risk/cost/capacity preferences; do not invent the partner's large-account sizing. Show remaining blockers with exact next actions.
7. Test receipt separately, then release only the index/policy combinations that meet the evidence requirements. NIFTY passing does not authorise SENSEX. Monitor stale quotes, missing exits, delivery ambiguity and effectiveness, with rollback of new collection/strategy flags through the normal deployment path.

### What is needed from the owner or partner

No partner strategy or broker credentials are required. Use the system's own researched strategies. The owner needs to merge/deploy when the correction checkpoint is complete, maintain authorised market-data access, and authorise the diagnostic if desired. The agent should discover existing nonsecret configuration and avoid asking for credentials already configured.

For practical advice sizing, the still-unresolved input is the partner's acceptable rupee risk/cost and typical lots per idea. Until supplied, use clearly labelled per-lot information and enforce explicit conservative profile limits; do not infer personalised large positions. The user's ₹8k Sentinel testing balance is separate from the partner's capital and must never size their advice.

The next deliverable is **reliable observations plus research of the exact advice policy**, not another broad set of unmeasured features. Better timing, executable prices and evidence-based selection can improve decision quality; this work cannot guarantee fast profits or eliminate trading losses.
