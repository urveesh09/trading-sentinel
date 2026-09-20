# Deterministic session-phase golden plan — 2026-09-20

## Problem

The J.6 session-phase regenerator writes `datetime.now()` into both committed
goldens on every test run. Even when all 2,355 vectors are identical, release
verification dirties two large files and removes their trailing newline. This
obscures meaningful classifier diffs and repeatedly leaves the Dev worktree
unclean.

## Contract and files

- `python-engine/tests/fixtures/regenerate_session_phase_golden.py`: preserve
  the existing `generated_at_utc` only when every semantic field/vector is
  unchanged; assign a new timestamp when content changes; serialize one
  canonical payload with a trailing newline to both consumers; avoid writes
  when bytes already match.
- `python-engine/tests/test_session_phase_golden.py`: prove repeated generation
  is byte-identical and both copies remain identical/canonical.
- Canonical guide, atlas, active plan and checklist: record the behavior and
  exact acceptance receipt.

`generated_at_utc` therefore means “when this semantic fixture content last
changed,” not “when a no-op verification happened.” It remains audit-useful
without creating meaningless diffs.

## Acceptance

- Two consecutive generations from unchanged classifier code are byte-equal.
- Python and Node goldens are byte-equal, include 2,355 vectors and end with a
  newline.
- A semantic payload change cannot retain the old timestamp.
- Focused Python golden tests and Node mirror test pass.
- The generator/source checks do not alter Production or execute broker,
  delivery or strategy paths.

## Rollout and rollback

This is Dev-only test tooling. Rollback is the prior Git commit. The two
pre-existing timestamp-only local fixture edits remain outside this task and
will not be staged without explicit ownership; this slice prevents future
no-op runs from changing them again.

## Verification receipt

- `python-engine`: `winvenv` Python, seven focused tests passed with warnings
  fatal in 1.95 seconds. The seventh pins raw-byte CRLF normalization so
  Windows text-mode translation cannot mask non-canonical content.
- `node-gateway/server`: Jest explicit-path run passed all 43 mirror tests and
  exited naturally in 1.56 seconds. The offline holiday fetch logged its
  expected warning and did not affect parity.
- Two consecutive Python generations produced byte-identical Python and Node
  files, with the second reporting both locations `unchanged`.
- Configuration/migration impact: none. Dev source only; Production untouched.
