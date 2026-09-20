# Plan — A6: Readiness CLI accuracy

Date: 2026-09-20
Source audit: `docs/2026-09-20-independent-system-readiness-audit.md` §3-A6

## Problem

The deployed-schema diagnostic correctly describes no qualifications
but assigns WARN. Its exit contract returns success for WARN-only
results. An automation could interpret exit 0 as delivery-ready.

The audit's words:

> The profile and config PASS results are useful, but the overall
> exit is not a partner-delivery certificate.

The audit's required acceptance:

> No qualifications + valid token/profile yields diagnostic-success
> but delivery-not-ready; deployment automation cannot confuse
> them.

Additionally the audit requires:

- Missing qualification must remain a delivery blocker.
- Treat off-session stale quotes separately from a broken
  in-session provider; do not make Sunday look like a failed
  trading session.

## Fix

1. **Add `delivery_ready` to the output schema.** The diagnostic
   continues to emit per-check items (PASS / WARN / FAIL /
   BLOCKER), but the top-level response gains an explicit
   `delivery_ready: bool` that is `False` whenever any delivery
   blocker is present. The exit code is updated so that
   diagnostic execution success (no BLOCKER / FAIL) with
   `delivery_ready=False` returns exit code 1, NOT exit code 0.

2. **Missing qualification is a delivery blocker.** Change the
   `compatible_qualification` check from WARN to BLOCKER when
   no compatible row exists. WARN stays only for the
   "DB not provided" diagnostic case (where we cannot read).

3. **Off-session provider freshness is its own state.** A new
   check `provider_freshness` distinguishes:
   - `IN_SESSION` (market open + fresh public quote) → PASS
   - `OFF_SESSION` (Sunday / outside market hours + last
     fresh quote < max age) → PASS (intentional quiet state)
   - `STALE_IN_SESSION` (market open + public quote stale) →
     BLOCKER (real provider failure)
   - `NO_PROVIDER_INPUT` (no quote ever) → BLOCKER

4. **CLI flag for delivery gate.** `--delivery-ready-only` exits
   0 only when `delivery_ready=True`; otherwise exit 1. This is
   the operator-friendly surface.

## Files affected

  - `scripts/check_partner_readiness.py` — top-level
    `delivery_ready`; `compatible_qualification` blocker;
    provider freshness check.
  - `scripts/tests/test_check_partner_readiness.py` — pin the
    audit's acceptance: no qualifications + valid token/profile
    yields `delivery_ready=False` and exit code 1.
  - `docs/2026-09-20-workflow-a6-readiness-cli-accuracy-done.md`.

## Acceptance

| Acceptance check | Expected outcome |
|---|---|
| No qualifications + valid token/profile | `delivery_ready=False`, exit 1 |
| All PASS but no qualification | `delivery_ready=False`, exit 1 |
| All PASS including a qualification | `delivery_ready=True`, exit 0 |
| Off-session Sunday with stale last quote | `provider_freshness=PASS` (off-session) |
| In-session with stale public quote | `provider_freshness=BLOCKER` |
| `--delivery-ready-only` flag suppresses diagnostic detail | exit 0 / 1 only |

## Data and configuration migration

  - No schema changes.
  - One new CLI flag: `--delivery-ready-only`.

## Rollout and rollback

  - Dev only.
  - Backward-compatible: existing consumers reading the
    per-check items continue to work; `delivery_ready` is an
    additional key.

## Status

  - Plan committed before implementation: this doc.

## Documentation updated

  - `docs/2026-09-20-workflow-a6-readiness-cli-accuracy-done.md` (new).
  - `scripts/check_partner_readiness.py` docstring: enumerate the
    new `delivery_ready` semantics.
