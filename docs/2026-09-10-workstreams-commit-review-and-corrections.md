# Review of workstreams 2–5 through 12acfcd

## Verdict

Partial foundations implemented, not completion of the handoff. Reviewed dde8616, d1f6467 and 12acfcd against the implementation record, real client contract and earlier specification. No Production changes, orders, messages or qualifications. Selected tests pass but missed integration contracts remain.

## Corrections made in this review

Replay now rejects stale provider observations even if recently received, negative fee assumptions, and exit contract/side/lot identities different from entry. Three regression cases added. 23 tests passed across replay, research artifact, telemetry, coverage, reconciliation and completed-bar modules. This does not establish full application or production correctness.

## Completion matrix

- Scheduling: bounded timing journal/listener and dashboard implemented. Actual contention diagnosis and fixes, provider/DB/archive stage attribution, exit-capacity isolation and Production before/after measurements remain. Recording after completion does not expose a currently hung invocation. Confirm penny/bootstrap coverage explicitly; the record primarily lists other jobs. Do not call this contention resolved.
- Reconciliation: future FNO origin references and limited internal matcher implemented. The five requested sheets for MOMENTUM, EDGE_LIVE, MOMENTUM_PAPER, PENNY_PAPER, EDGE_PAPER are not delivered. These are different sources from the new FNO linkage. Missing historical IDs do not prevent read-only amount/count/window/partial-close investigation. Broker evidence may remain unavailable without blocking internal diagnosis.
- Dashboard: new coverage/timing/reconciliation panels implemented. Legacy strategy event integration, primary-view simplification and meaningful real completed-bar progression remain unproven.
- Research: supplied-entry/exit two-leg pricing helper and summary artifact implemented. It is not the exact deployed strategy evaluator, chronological event replay, active-leg collector, forensic case pack, frozen basket comparison or qualification evidence.
- Earlier partner review: remaining independent management, conditional protection, read-time freshness and qualification visibility work was not changed by these three commits.

## P0 next: repair completed-bar adapter contract

kite_client.get_intraday_by_token returns a DataFrame with a timezone-naive IST DatetimeIndex named datetime; the adapter searches timestamp columns and then requires aware timestamps. It will reject the actual client response. Existing test stubs return a different shape.

Implement a narrow normalization boundary matching the actual client contract: explicitly localize naive client index as IST, preserve aware offsets correctly, reject mixed/ambiguous input, use correct interval-close convention and cutoff. Test through a realistic client-shaped fixture, including delayed response. Record actual completion/receipt time instead of copying as_of; an evaluation clock before the network request is not receipt evidence.

Validate instrument token mapping against the archived current master and declared spot/futures basis. A positive integer is not proof of NIFTY/SENSEX identity. Assess index zero-volume semantics versus the existing positive-volume equity strategy builders: do not relabel an index as tradable equity or treat legitimate zero volume as generic corrupt OHLCV. Use a compatible research policy/source contract. Test both indices, partial failure, current bar exclusion, stale bar, wrong token, restart and Monday history requirements. Missing one index must remain visible independently.

## P0 next: constrain replay claims and repair structural validation

LegQuote has no structured strike, option type, token or per-leg expiry. The helper cannot establish a valid same-expiry vertical or validate declared expiry against both contracts. Add explicit immutable contract metadata and master provenance, strict quantities, finite integer depth, non-boolean inputs, distinct legs, strike ordering, spread width and economic bounds. Validate entry session start/calendar and expiry; current code checks only the upper entry cutoff.

Freeze all decision assumptions in the evidence hash: age/sync thresholds, entry and management windows, cost/slippage/delay policy and contract provenance are currently incomplete. Two runs with different assumptions must not share an evidence identity.

Then implement policy-driven chronological signal/entry/exit selection. Caller-selected entry and exit times can cherry-pick outcomes. Retain active-leg quotes, no-fills, receipt availability, interval uncertainty, partial-leg execution exposure and late-exit unresolved risk. Do not classify a missing timely exit as harmless pre-entry rejection and omit its risk. Add adversarial tests before describing it as exact-policy research.

## P1 next: research report integrity

session_dates is caller supplied; duplicated result objects can count as independent closed trades. Validate real dates/session provenance, deduplicate stable opportunity identities, preserve per-index/policy groups and all rejected/unresolved results. Record predeclared thresholds in a frozen run manifest before producing outcomes, rather than just labelling caller parameters predeclared. Separate deterministic dataset/results/config hash from report creation timestamp. Quantify costs, drawdown, unseen-session behavior and uncertainty; threshold counts alone cannot establish reliable research readiness. No auto-qualification.

## P1 next: finish actual warning investigation

Create the five read-consistent evidence sheets from retained Production snapshots. Include amount/count differences, time ranges, costs, funding/adjustments, partial exits and missing coverage. Stable matching may be unresolved; show why and quantify it. Extend forward linkage to relevant sources only after understanding their lifecycle. The matcher must detect multiple ledger rows sharing one origin, missing position-to-ledger records and non-finite amounts; a matching amount on each of two duplicate rows must not report both clean. Show pagination/truncation and scope so a latest-200-row report is not mistaken for complete reconciliation.

## P1 next: finish scheduling/coverage integration

Add bounded start/in-flight evidence and market-session filtering, measure relevant stages, and distinguish callback success from underlying no-op/handled failure. Aggregate event totals separately from executed run counts (current runs includes scheduler rejections). Add slow provider/locked DB/archive saturation integration tests. Measure rather than infer capacity from healthy containers. Readiness must age at read time and preserve source coverage; quote receipt is not qualification.

## Implementation sequence and acceptance

1. Fix real Kite DataFrame/clock/token/policy integration with realistic fixtures; keep adapter inactive until verified.
2. Implement strict spread contract validation and complete evidence identity; keep reports research-only.
3. Produce five forensic reconciliation sheets and scheduler timing baseline in parallel.
4. Complete legacy activity integration and active-bar/leg research pipeline.
5. Produce chronological held-out comparison artifacts; report insufficient data where applicable rather than stopping independent code work.

Acceptance requires real contract-shaped integration tests, deterministic replay, no future information, no duplicate outcomes, truthful missing inputs and concrete per-source warning explanations. Update the implementation record so earlier still-pending sections and later claims do not contradict each other. Separate implemented, tested, deployed and observed status. Market-session performance needs observation after GitHub deployment; code contract bugs can and should be fixed now.
