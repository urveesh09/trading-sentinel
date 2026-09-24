# Dev release-acceptance slice — 24 September 2026

## Problem

The F&O recovery and real-research package commits are pushed, but each was
validated primarily with focused suites. Before a reviewer can promote the
branch, the plan requires a current cross-component Dev receipt. This is an
acceptance task, not permission to merge, deploy, edit Production, send a
message, or place an order.

## Scope

- Run the full Python engine and script test suites with the repository runtime.
- Run the gateway suite in its supported local/runtime-compatible form and the
  dashboard and agent test/build checks where dependencies are available.
- Run syntax, staged/worktree diff, and documentation/atlas consistency checks.
- Record exact commands, results and environmental limitations. Preserve
  unrelated session-golden fixture changes and independent audit artifacts.

## Acceptance

All selected suites must pass, or any failure must be reproduced and repaired
within the relevant source boundary. Existing framework deprecations are
reported, not silently treated as new correctness failures. The receipt names
the tested commit and explicitly says Dev-tested, not deployed or profitable.

## Rollout and remaining work

GitHub review/merge, backup, rebuild/stamped-release verification, real-session
collection, broker reconciliation, partner qualification and any Telegram
canary remain separate operator actions. Rollback is GitHub-based and must keep
existing databases and research archives intact.

## Implementation receipt — 24 September 2026 (Dev only)

The gateway's holiday-calendar bootstrap previously started a production
engine fetch in every Jest worker. In a compatible Node runtime the request
could reject after Jest had completed, turning otherwise passing assertions
into a failing process. `tests/setup.js` now sets
`MARKET_HOURS_TEST_DISABLE_ENGINE_FETCH=1`, and `market-hours.js` honours that
switch only when Jest supplies `JEST_WORKER_ID`. Production processes therefore
retain the default engine refresh even if the test switch is present by
mistake. The test fixture deliberately retains its `NODE_ENV=development`
configuration; changing it would invalidate gateway configuration coverage.

The module reports `fallback:test-network-suppressed` only for the explicit
Jest path, and `tests/unit/market-hours.test.js` pins that contract. The unused
duplicate initializer was removed so the single module-load path is auditable.

Verification on this Dev checkout:

- `python-engine/winvenv/Scripts/python.exe -m pytest scripts/tests -q -W error`:
  226 passed.
- From `agent`, `../python-engine/winvenv/Scripts/python.exe -m pytest tests -q
  -W error`: 357 passed.
- Compatible Node 20 Docker receipt (read-only source mount, fresh dependencies,
  natural process exit): 30 suites passed, 1 skipped; 461 tests passed, 4
  skipped; exit 0. The gateway host's Node 24 runtime cannot load its locally
  installed `better-sqlite3` native binary, so that host run is diagnostic only,
  not the release receipt.
- From `node-gateway/client`, `npm run test:unit`: 46 passed; `npm run build`:
  passed. Vite reported the pre-existing stale Browserslist-data advisory.
- `python-engine/winvenv/Scripts/python.exe scripts/build_system_code_atlas.py`:
  regenerated the atlas (211 Python modules).

An attempted full `python-engine/tests` process did not terminate after showing
early progress because of the documented aiosqlite-worker teardown issue; it
was stopped without reporting a pass result. It is not represented as a green
full-engine receipt. The current source change is isolated to the gateway test
bootstrap; previously recorded focused engine evidence remains in the package
and recovery receipts. No Production source, data, service, Telegram message or
broker order was changed.

## Gate classification correction — 24 September 2026

The six remaining high-level items are **not six pending product-development
packages**. F&O exit recovery, bounded qualification-package construction and
gateway test-lifecycle isolation are complete Dev implementations. The
remaining full-engine natural-exit receipt is test-runtime/CI hygiene only:
earlier full runs completed their test assertions and then retained aiosqlite
worker threads. Do not change application teardown or add global warning
suppression without a minimal reproducer that identifies an owned connection
leak. The remaining rollout, session-evidence, reconciliation, held-out
research, profile/review and Telegram-canary gates require GitHub promotion,
real retained data, or explicit operator authority—not more code.
