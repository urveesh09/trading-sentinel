# N01-F: stale closed-bar state guard — input-contract repair

During independent gap/decision audit, before reviewing adaptive performance,
the original adapter's latest-closed-bar lookup can return a pre-gap bar on
the first resumed observation. The state-series gap check only takes effect
when the first post-gap bar closes. This violates the intended missing-data
fail-closed contract for those intervening minutes.

Fix ONLY that information boundary: a state is UNAVAILABLE if its latest
closed bar's END is5 minutes old or more (one complete native interval). Return
empty state history for regime exits too; do not invent a fresh bar or bypass
ordinary price/stop/hard-flat management. Test normal4:59 versus stale5:00,
long break and no-bar cases. No threshold/rank/expert/stop/cost tuning.

Preserve all original source, freezes, models and45 replays. Reuse27 base
books/economics by exact hashes: STATIC decisions never use state, so their
trades/cash cannot change under a pure state annotation repair. For learning,
derive a separate label view of those unchanged expert trades, relabeling only
stale entries UNAVAILABLE; retain global outcomes and sample/exit/as-of rules.
Rebuild all34 monthly models and commit their hashes before18 corrected
candidate replays. No training outcome, quantity, price or net is altered.
Copy base evidence unchanged into the corrected packet; disclose reuse rather
than claiming another27 fresh scores. Original parity/attribution is retained;
entry-state attribution by signal bar remains distinct from stale entry-time
availability.

Files: fresh_lab.py, analyze_fresh.py, test_freshness.py, freeze.json,
training manifest/derived labels/models, results/receipts in this nested folder.
Source freeze before correction scores; training manifest before child scores.
Same acceptance/risk/source/data/2023-exam contracts as parent; all years seen.
No application/config/migration/deployment/Production/order changes. Rollback:
stop corrected worker and keep both complete versions. Reports use corrected
outputs and record any differences. Tests cannot establish profitable execution.
