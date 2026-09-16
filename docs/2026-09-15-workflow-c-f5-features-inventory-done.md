# Workflow C.F5 — J.10 features inventory CLI (F-5 from prod audit)

## Source

Per the 2026-09-15 production deep audit F-5:
> 🟡 F-5 (MED, infra): New PR #89-#92 features deployed but invisible in production runtime. Need to verify they're wired correctly.

The audit observed:
- 0 log lines for `cas_eligibility` Python projection.
- 0 log lines for `cas_reachability` gate.
- 0 log lines for `mark_to_market`, `discrepancies`, `reconciliation_cli`, `capital_policy` fixes (F3/F4/F5/F6 from PR #88).
- 0 log lines for J.10 capture gate features.
- 0 log lines for `WRITE_ATOMIC` JSON writes.
- 0 log lines for I.4.D agent classifiers.
- **0 log lines for I.4.E bounded contract-health self-evaluation** (MED — not yet in prod).
- 0 log lines for `summary.md` auto-generation.

The audit's ask: **"verify they're wired correctly"**.

## What landed

| File | Type | Purpose |
|---|---|---|
| `python-engine/cas_reachability_features.py` | module (new) | `FEATURES_INVENTORY` constant + `format_features_inventory` / `features_inventory_as_json` helpers |
| `python-engine/tools/cas_reachability_check.py` | CLI (extended) | New `--features-inventory` flag (composes with `--json`) |
| `python-engine/tests/test_cas_reachability_features.py` | test (new) | 13 tests pinning the inventory contract |
| `docs/2026-09-15-workflow-c-f5-features-inventory-done.md` | doc (new) | This file |

## The shift in defensive posture

Before this slice, the only way to confirm J.10 wiring was to:
1. Inspect each module's source for the documented feature.
2. Wait for captures to happen (some features only fire on capture events).
3. Run individual unit tests (which exercise one feature at a time).

After this slice, an operator can run a single command:

```
python tools/cas_reachability_check.py --features-inventory
```

And immediately see every J.10 feature wired into the engine version, the date it was added, its description, and the CLI flags that activate it. The output is sorted by `feature_id` for stable display and exits 0 regardless of captures-dir state.

The audit's next iteration can grep `J.10.GATE` / `J.10.DEDUP` / etc. in the operator's run output to confirm wiring without needing a capture event.

## Why this is the right bounded improvement

The audit's concern is **wiring visibility**, not new feature implementation. Adding heartbeat logs to every J.10 feature would scatter observability across many places. A single inventory command:

- Centralizes the "what's wired here?" question to one place.
- Is side-effect free (no captures-dir reads).
- Composes with `--json` for machine-readable aggregation.
- Has a single source of truth (`FEATURES_INVENTORY` constant) that future feature additions must extend.

## Key design choices

- **Constant table, not introspection.** The inventory is a hand-curated tuple of dicts — a single source of truth. New features are added by appending a row, not by magic detection. This avoids the "feature exists in code but wasn't introspectable" problem.
- **Sorted by feature_id** for stable display. Operators can diff two inventories across versions.
- **ISO date format** (`YYYY-MM-DD`) for `added_at` so the column is parseable.
- **Reference back to the audit** in the `J.10.FEATURES_INVENTORY` row's description, so an operator reading the inventory understands why the slice exists.
- **Mutually exclusive with verdict flags** — the inventory short-circuits before the captures-dir check, so it's safe to run in any deployment state.
- **No new dependencies.** Stdlib only (`json` for JSON output).

## Defensive regression

| Test file | Tests | Δ |
|---|---|---|
| `test_cas_reachability_features.py` | 13 | +13 (new file) |
| Full cas_reachability surface (12 test files) | 248 | +13 |
| Full python-engine narrow regression surface (33 test files) | 519 | +13 |

Zero regressions in any prior test.

## What this does NOT solve

- The audit's F-5 finding is fundamentally about **PROD-side wiring verification**. The bounded dev-side improvement here gives operators a way to confirm wiring locally; the actual PROD deployment hygiene (verifying after each deploy that the inventory matches the expected) is operator-owned.
- I.4.E bounded contract-health self-evaluation is still dev-only (not yet in prod, per the audit). When it ships to prod, the `--features-inventory` style will need extending to cover agent-side features too.

## Critical invariants preserved

- No change to existing J.10 gate semantics.
- No change to existing J.10 flags (`--json`, `--write`, `--status`, `--update-summary`, `--summary-path`, `--captures-since`, `--min-unique-per-branch`, `--list-captures`, `--show-branch-histogram`, `--verify-summary`).
- The inventory is purely additive: a NEW flag, not a behavior change.

## Operator runbook

After deploy to PROD, the audit's next run can ask:

```
$ python tools/cas_reachability_check.py --features-inventory
# J.10 features inventory
# ------------------------
# ...
J.10.GATE                                  2026-09-13  --
J.10.SUMMARY                               2026-09-13  --update-summary
J.10.DEDUP                                 2026-09-14  --
J.10.FRESHNESS                             2026-09-14  --captures-since
...
```

And immediately see whether all expected features are present, what they do, and when each was added. If the audit observes a feature missing from this list, that's a real signal that a deploy was rolled back or never happened.

## What's still open on the audit

- **F-4** (penny stale warning flood) — DONE in `0ba14a9` (C.B.3).
- **F-7** (agent dedup file observability) — DONE in `04aa166` (C.B.2).
- **F-3** (concurrent finalize_prior_days race) — DONE in `7cf87c3` (C.B.1).
- **F-1** (dashboard bootstrap race) — DONE in `f186a22` + `5265c73`.
- **F-2** (Kite LTP fanout) — DONE in `729f7f1` (C.F2).
- **F-5** (features invisible) — DONE in this slice (`<next-commit>`).
- **F-8** (GRAVISSHO not booked) — OPEN, next slice.
