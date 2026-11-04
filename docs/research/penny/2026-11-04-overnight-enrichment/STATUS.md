# Overnight enrichment status

Research complete; engineering verification in progress. Dev only, no push
or deployment. Frozen rounds:4d95c71,a8976d1; older check:a4cf227.

Best conditional candidate is V3_COST_ROUTE, not a qualified replacement.
Older full-fill net124211 vs127735 V2; 50%-winning-close-fill net24366 vs20056.
Four-model arithmetic robustness passes; full-fill improvement fails.
Additional seeds/correlated fills and severe combined costs retain negative
cases, while daily final-candle candidates cannot justify early entry.
See REPORT.md and qualification.json. No native strategy/P&L book change.

New default-off EDGE_OVERNIGHT_EXECUTION_EVIDENCE_ENABLED archives actual
15:20 picks/quotes/night estimates and separate15:49,15:51,16:03 observations.
API execution_evidence adds strict capacity-only answers and retains missing
observations as UNKNOWN; never claims own fills. Old probe/book/ON_V2/shadows
remain unchanged. Independent sibling store, no existing-schema migration.

Mechanics:60 primary artifacts reconcile,30 actual-panel legacy parity
trades match. Focused final source+book+V2+surface tests pass (final count in
VERIFICATION.md). Full suite running; record exact result before completion.
Owner bytes preserved; Production tracked state remains unchanged at5e30ce0.
Zero Breeze/order/live quote calls during research.

Remaining research qualification: forward observed15:20 candidate comparison
with a frozen own-cash paper ledger and missing/partial fills; broker session
eligibility and separately authorized real fill proof. No claim these future
observations or real-money proof already exist.
