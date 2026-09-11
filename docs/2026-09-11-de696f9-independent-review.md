# Independent review of de696f9 — in progress

This is a Dev correction checkpoint, not a completed qualification or production approval. Production was not modified. The implementation contains useful components, but its claim that the code portion is complete is not yet supported by the end-to-end paths inspected.

## Corrections implemented in this review

- Normalize research decision clocks to IST before calling the deployed evaluator, which strips timezone information and expects IST. Normalize timezone-aware bar indices to the same exchange-local convention. UTC and IST representations of the same evidence now produce identical decisions.
- Reject duplicate, unordered, non-finite and inconsistent OHLCV inputs before evaluation. Previously the fingerprint sorted bars while evaluation consumed original ordering.
- Count distinct exchange/token identities against selected-leg capacity rather than counting decision owners. Multiple decisions sharing a leg no longer crowd out another contract unnecessarily.
- Record missing selected-leg coverage on empty provider responses, which previously continued before the durable gap update.

Validation: 83 tests passed across qualification, subscriptions, archives, release safety, CLI, manual advisory, chronological replay, signal artifacts and held-out reporting. This is targeted evidence, not a rerun of the claimed 301-test suite.

## Remaining work to inspect and complete

1. The full-policy diagnostic CLI supplies bars only: it has no chain/book/profile input path. A fired signal therefore returns candidate_input_missing. Add a reproducible complete-input diagnostic path and actual accepted/rejected candidate integration coverage.
2. The research adapter is invoked by the diagnostic CLI, not the production observation path. Define and implement contemporaneous bar/baseline/regime capture and persisted decision provenance; waiting for more quote packets alone cannot supply this evidence.
3. The policy manifest includes each decision timestamp and bars digest. Separate stable strategy identity from per-decision evidence before using a frozen policy identity across multiple held-out sessions. Bind all relevant evaluator dependencies, configuration and profile assumptions.
4. Review-package code compares claimed manifest digests without recomputing them, and does not yet bind each held-out group to verified full-policy decisions. Cost criteria accept non-finite multipliers; drawdown and stress remain deferred to human review. Inspect and implement evidence validation rather than treating aggregate counts as sufficient.
5. Connect exact selected full-policy decisions to chronological replay. The current replay CLI still consumes the separate signal-artifact path; verify full-policy identity survives end to end without downgrading to a threshold-only artifact.
6. Audit subscription re-registration identity and terminal behavior, deadline coverage, durable recovery after registration failure, and collector latency/isolation. Existing restart/capacity tests do not prove all these invariants.
7. Produce the retained two-session diagnostic and explicit readiness report after the integration is functional. Missing historical inputs must remain marked unavailable/retrospective; no fabricated trades, prices, qualifications or outcomes.

The work remains active. Genuine held-out evidence and reviewed qualification are separate from passing code tests. No partner message or order was sent.

## Second correction checkpoint

- Subscription registration now verifies immutable exchange, contract, master and deadline identity under a write transaction. Exact retries cannot revive terminal rows. Scope and finite price increments are checked.
- The public scanner now retains the actual fetched frame, futures token and receipt clock in its scan result. After both indices finish urgent public management, the advisory workflow persists content-addressed bar/regime/signal evidence. Receipt time is preserved even when later than the scan's original clock; this is not relabelled pre-decision evidence.
- Public-input writes share the existing archive writer lease, free-space reserve and persistent daily write budget. Capture failure is isolated and logged/counted. This adds input capture, not complete qualification, chain evidence or replay linkage.
- Fixed the shared archive guard treating pathlib.Path.root as the archive directory. Existing export source/destination behavior remains covered by tests.

Validation for this checkpoint: 84 tests passed across public input capture, scanner, orchestrator, subscriptions, research adapter, archive and release safety. Remaining integration work above remains open, including public-input retention/readiness presentation and complete-input replay.

## Review artifact integrity checkpoint

The review builder now recomputes manifest and held-out-report fingerprints instead of trusting supplied digest labels. Sample criteria require actual integers; risk/cost criteria reject booleans, non-finite numbers and malformed numeric types. Eleven review/held-out tests pass, including altered artifacts and NaN/infinite criteria. Fingerprint integrity is not source authenticity or full-policy outcome linkage: those remaining requirements above are still open.

## Offline complete-input diagnostic checkpoint

`full-policy-diagnostic` now accepts optional `--candidate-evidence <JSON>`. The bundle supplies underlying, segment, received_at, contracts (Contract fields with ISO expiry), snapshot (taken_at, expiry, forward, lot_size, quotes keyed by token with ContractQuote fields), and explicit profile. It is decoded entirely offline; no instruments cache or broker state is written. Index/segment, unique contracts/quotes and receipt-time boundaries are checked. This is operator-supplied research evidence, not independently authenticated archive provenance or qualification.

Missing profile is now an explicit candidate rejection. Decision identity includes the full candidate and profile rather than just the thesis label. Fourteen research-adapter/CLI tests passed, including actual spread construction/validation with an injected fired signal and malformed bundle rejection. Full unmocked policy-to-replay integration and verified archive-origin bundles remain outstanding.

## Frozen policy identity checkpoint

Decision manifests now carry a separate `frozen_policy` and `policy_sha256`. This identity binds the index/structure, profile, FNO/advisory configuration and relevant module fingerprints while keeping observation time, bars and dated master identity in the per-decision manifest. Helper-module edits are included. The configuration binding is deliberately conservative and can invalidate research after an operational FNO setting changes; it does not establish authenticity or promotion eligibility. Review callers must use the frozen policy when declaring multi-session criteria; end-to-end replay binding remains open. Twenty-five adapter/CLI/review/capture tests passed, including stable identity across observation times and changed identity after a rule change.

## Public-thesis replay checkpoint — not qualification-ready

An unmocked full signal-to-candidate fixture now passes. Review identified that generic chronological replay used spread-P&L exits, whereas published partner advice uses underlying invalidation/target levels. A pure shared `public_thesis_event` now serves advisory management and an explicit `PUBLIC_THESIS` replay mode. The default research exit mode is preserved. Public input clocks are fingerprinted and future receipt evidence rejected. Regression verifies spread profit alone cannot close a public-thesis simulation; 79 advisory/orchestrator/qualification/thesis tests and 10 chronological tests passed.

This is an integration checkpoint: archive-derived public-price timestamps/freshness, persistent trigger handling across missing executable books, manual exit delay, and exact reminder/deadline treatment still require completion before this mode can qualify partner advice. No production qualification is granted by these helpers.

Follow-up: public exit triggers now latch before executable-book validation and survive a later underlying-price recovery. A declared execution delay requires a later eligible observation; unresolved output preserves the trigger. Fourteen chronological/held-out tests passed, including an invalidation with insufficient depth followed by a usable book after price recovery. Archive linkage, event freshness, deadline semantics and complete delayed-exit regression coverage remain open.

## Consolidated verification

Public-price observations now require separate event and receipt clocks; future events and events beyond the declared maximum age are rejected. The age bound is part of replay evidence. Unresolved replay hashes include any pending public exit trigger. The combined 15-module regression run passed **152 tests** (one existing Starlette lifespan deprecation warning). This verifies the current correction checkpoint, not overall qualification or deployment readiness. Remaining major work is the archive-to-full-policy replay integration, review outcome binding, operational diagnostics and the retained-data report.

## Retained public-input diagnostic

Added `python research_cli.py captured-policy-diagnostic --public-input <hash-named-json> --underlying NIFTY --output <diagnostic-json>` (also SENSEX). It verifies the file fingerprint, scope and timezone, reconstructs the retained frame/regime, and evaluates at the original clock. Late receipt remains retrospective; the command never shifts the clock to manufacture causal availability. It is a signal diagnostic; selected chain/profile and replay linkage remain separate unfinished work. Eighteen capture/CLI/adapter tests pass, including capture-to-command execution.

The retained-input command now also accepts `--candidate-evidence` and `--contract-master-sha256`. An unmocked capture-to-CLI-to-accepted-spread fixture passes; the decision remains non-qualifying. Decision evidence now fingerprints the complete supplied snapshot quote set, not only selected legs. Nineteen capture/adapter/CLI tests pass. The supplied chain bundle still needs archive-origin proof; a declared master digest alone does not provide it. End-to-end real-data replay and reviewed qualification remain outstanding.

Archive reader correction: contract lookup now recomputes both raw.csv and contracts.jsonl fingerprints rather than trusting the raw digest label in a manifest. Six archive-adapter/CLI tests pass, including raw and canonical file tampering. This detects file corruption against the referenced manifest; independent raw-to-canonical term reproduction and source authenticity remain distinct requirements. Candidate-bundle linkage to verified archive observations remains unfinished.

Contract verification now additionally matches the unique raw CSV token row's symbol, index, exchange, option type, expiry, strike and lot size. Rehashed false normalized lot sizes are rejected. Both diagnostic commands accept `--archive-root` with `--contract-master-sha256` to enforce this check on supplied contracts. Quote-packet origin and full decision/replay binding remain unfinished. Twenty-four combined adapter/capture/CLI tests passed, followed by six master-reader tests including the raw-to-normalized inconsistency case.

Quote replay now requires a matching raw-packet hash/token, normalized top-book prices/quantities matching the raw response, and a provider observation clock. Missing provider time is not replaced with receipt time. Nine archive-adapter tests pass, including altered price/hash and absent clock becoming explicit partial evidence. Raw timestamp reproduction and end-to-end full-policy binding remain open; these checks are integrity checks, not proof of source authenticity.

Raw timestamp reproduction is now checked, including naive IST provider timestamps converted to UTC. Altered normalized timestamps and provider times after receipt cannot produce executable observations. Fourteen archive/capture/CLI tests passed. This closes that timestamp-integrity gap; it does not complete full-policy replay linkage or held-out qualification.

Decision outputs now use unique temporary files, fsync and atomic create-if-absent linking. Identical concurrent retries are idempotent; a different decision cannot overwrite an existing output. Twenty adapter/capture/CLI tests pass, including eight concurrent writes and conflicting reuse. Operators must use a new output path for a revised diagnostic rather than replacing evidence. Filesystems without hard-link support fail explicitly rather than falling back to unsafe overwrite.

Review scope checks now reject cross-index groups, duplicate policy groups and negative/noninteger outcome counts even when the altered report is rehashed. Forty-three review/adapter/capture/archive/held-out tests pass. This remains insufficient to establish per-outcome full-policy provenance or reviewed strategy qualification.
