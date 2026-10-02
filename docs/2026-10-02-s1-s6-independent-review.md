# Independent S1–S6 review — October 2

## Correction slice before implementation

Review base: `9a26bd9`, including S2 `71061d3`, S3 `1d1dd1c`, S4
`9703f61`, S5 `f45ce43`/`18c7f2a`/`89a7595`, S6
`19a5471`/`02047d4`/`9a26bd9` and the previously reviewed S1.
Initial affected regression: 303 passed, one known skip and one Starlette
deprecation. Rendered Dev Compose verified `20m x 25` (500 MiB); eight
Compose-verifier tests passed. Production is not edited or restarted.

Small corrections: reject mismatched returned DR token and non-finite exit
prices; enforce provider/receipt clock order on passive evidence capture/export;
preserve the first futures reference paired with active research legs even if
the later ladder times out; inherit the ambient provider lane for ordinary
token quotes; deep-copy frozen candidate parameters and pin cost rates/source
in both S6 manifests. Tests must reproduce the old gaps before corrections,
then pass with unchanged exits, deadlines, rate and authority.

Files/contracts: `fno_dr_book.py`, `momentum_paper.py`,
`momentum_paper_path_adapter.py`, `research_quote_collector.py`,
`kite_client.py`, both exit-experiment modules and focused tests. No migration
or new provider request; no orders/messages or qualification changes. Fee/source
fingerprint changes intentionally invalidate old research freezes; retain them
as development evidence and freeze a new manifest before future sessions.
Rollout/rollback through GitHub only; preserve all evidence and active exposure.

## Larger remaining scope — guidance, not silently implemented

These are development/acceptance gaps, not a claim that all phases are ready
for production. Priority: source-bound S4/S6 evidence and crash-safe S3 receipts,
then the remaining DR research experiment and fresh qualification/pilot review.

- S3 crash/error recovery: test failures between CSV rename, manifest append,
  new-header creation and session-state replacement. Bytes are preserved but
  the present code can orphan an archive manifest or mislabel an empty new
  header with the prior session. Add a recoverable rotation journal and define
  off-path/bounded writer behavior. Current summaries retain outcomes/stages,
  not durable elapsed distributions or explicit market-hours segmentation.
  CSV archives also have no retention quota/free-space admission control of
  their own; define a bounded archive/backup policy without routine evidence
  deletion before enabling long-running collection.
  Keep disk/previous-boot/full-session operational acceptance open.
  A temporary-directory fault injection confirmed this gap: after a failed
  manifest append and next-write recovery, prior bytes were preserved but the
  manifest was not recovered (`True` / `False`, respectively).
- S4: wire an existing quote fanout with bounded non-blocking writes and no
  new request. Specify a typed, source-bound equity provider envelope and
  validate ticker/instrument, LTP and provider time against actual packet bytes
  at capture and export. Hash recomputation alone proves byte integrity, not
  that caller-supplied columns match those bytes. Retain exact keys, original
  quantity and post-close paths; incomplete paths must stay unavailable.
  Add corruption/saturation/retention tests and five reconciled fresh lifecycles.
- S5: complete frozen protocol and fresh independent-session holdout, reviewed
  qualification package and separately authorized delivery canary. A blocker
  diagnostic or test does not qualify a strategy or guarantee tips delivery.
- S6: defined-risk spread exit experiment remains missing source work. The
  single-leg archive adapter needs complete contract/raw-packet/provider-clock
  validation and conflict rejection (currently token/receipt pairing only),
  plus exact position-economic/cash binding before results inform promotion.
  Do not treat a generated `source_ref` as verified external provenance.
  F&O partial candidate fees currently call a round-trip cost per exit leg,
  including the flat entry commission more than once. Predeclare and implement
  one-entry/multiple-exit fee allocation for that candidate; retain baseline
  paper accounting unchanged and version the corrected candidate cost model.
  No source-bound future sample, qualified edge or runtime exit-policy promotion
  has been established by these commits.

## Verification receipt

Windows Dev runtime: `python-engine/winvenv/Scripts/python.exe`. Initial
cross-phase check passed 303 (one known skip); expanded selected F&O,
momentum, partner, research-quote/leg, session-CSV, scheduler, signal-log and
atomic-settlement suites passed **948, no deselections**, with two known
Starlette/HTTPX deprecations. Selected test paths were enumerated with `rg
--files tests` and matching `test_(fno|momentum|partner|research_quote|
research_leg|session_csv|scheduler|signal_log|penny_signal_log|s5_provider|
atomic_settlement)`; run with `python -m pytest <paths> -q`.

Isolated `-W error` checks: DR plus the two S6 experiment files **54 passed**;
S4 passive tests **7 passed** (29 unrelated tests deselected by `-k passive`);
S5 provider lanes **11 passed**. The combined five-file warnings-fatal run
still raised the previously documented unclosed Windows socket warning in
`test_paper_sizing_uses_the_live_regime_risk_schedule` (100 pass / one failure).
This is not represented as a clean full warnings-fatal receipt or hidden by
blanket suppression. Runtime hygiene remains a separate minimal-reproducer
follow-up.

Final expanded rerun also passed **948**, with the two deprecations plus an
intermittent `PytestUnhandledThreadExceptionWarning` from an aiosqlite worker
after its test event loop closed in a scheduler-closure test. That warning was
not diagnosed by this review; preserve it in the runtime-hygiene follow-up
instead of calling the final run warning-clean. Old-source in-memory freeze
reproducers separately confirmed that both prior S6 manifests accepted changed
fee settings and aliased their global candidate dictionaries; new regressions
reject drift and prove independent parameter copies.

Eight Compose-verifier tests passed; the actual Dev rendered contract is
`json-file`, `20m`, `25`, 500 MiB. Changed modules compiled; regenerated atlas
indexes 222 modules. No broker, provider network, qualification or notification
was exercised by the tests. Operational acceptance is not inferred from tests.
Only a read-only Production Git check was made: checkout HEAD is `d90c775`;
this does not confirm the running container's build. Dev remote-tracking head
is `19a5471`; S6b `02047d4`/`9a26bd9` and this correction are local-only at
review (no fetch/push/deployment performed).

Existing user golden-fixture edits and untracked documents are excluded.
The correction's commit identity is supplied with the handoff and can be
retrieved with `git log -- docs/2026-10-02-s1-s6-independent-review.md`.
