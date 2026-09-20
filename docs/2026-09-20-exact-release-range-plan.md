# Exact release-range and PR handoff plan — 2026-09-20

## Problem

`scripts/build_release_notes.py` exposes `--base-ref`, but `get_git_state`
always reads `git log --oneline -30`. The current Dev branch is 31 commits
ahead of `origin/evolve/smart-strategies`, so a generated PR body can silently
omit a release commit and is not actually bound to the declared target.

## Files and contracts

- `scripts/build_release_notes.py`: resolve and validate the requested base,
  collect the exact `base..HEAD` commit range, report the resolved base SHA and
  ahead count, and retain the bounded latest-30 behavior only when no base is
  supplied.
- `scripts/tests/test_build_release_notes.py`: pin exact-range selection,
  invalid-base failure, and CLI forwarding.
- Release handoff documentation: record target/head, exact scope, verification,
  rollout/rollback, Production state and evidence-only prerequisites.

## Acceptance

- `--base-ref origin/evolve/smart-strategies` contains every and only commit in
  `origin/evolve/smart-strategies..HEAD`.
- The rendered count matches `git rev-list --count` for the same range.
- Invalid base refs exit nonzero and do not emit plausible release notes.
- Legacy no-base calls remain deterministic and limited to the latest 30.
- Script suite, syntax checks and generated handoff review pass.

## Rollout and rollback

This is Dev-only release tooling/documentation. It does not merge, deploy,
restart services, send messages, touch broker state or modify Production data.
Rollback is the prior Git commit. The generated handoff is advisory until a
reviewer opens/approves the GitHub PR and follows the deployment runbook.

## Remaining work

An authorized reviewer still owns PR approval/merge and Production deployment.
After deployment, release identity, configuration, container health, backup
and market-session evidence must be verified separately.

## Adjacent release-suite blocker discovered during acceptance

The full scripts suite exposed a Windows operator-path failure in
`scripts/import_broker_statement.py`: its human report emitted the Unicode
rupee glyph, which raises `UnicodeEncodeError` on the normal cp1252 console.
The bounded correction is to render the unambiguous ASCII currency code
`INR`, preserve all numeric values/status/exit codes, pin the output contract,
and rerun the complete scripts suite. This does not touch reconciliation data
or calculation behavior.
