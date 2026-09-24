# Real research authorization-package implementation slice — 24 September 2026

## Problem

The Dev checkout can replay the deployed intraday policy and build a
non-authoritative held-out review.  It did not yet provide the documented,
bounded operator workflow that assembles those immutable artifacts into the
`partner_advisory_authorization_v1` envelope consumed by the existing
authority verifier.  Hand-built JSON creates avoidable scope and fingerprint
errors; an automatic approval command would be unsafe.

## Scope and contracts

- Add `partner_qualification_package.py`: validate bounded, finite JSON inputs;
  reconstruct every `HeldOutCase` from complete full-policy replay reports;
  rebuild the held-out and review results; and create a canonical immutable
  authorization package only when an *externally supplied* review identity
  already says `APPROVED`.
- Add `research_cli.py build-qualification-package`: require explicit report
  manifest, frozen criteria manifest, review-identity file, readiness file and
  output path.  It never writes a registry, dispatches Telegram, sends advice,
  changes settings, or creates an approval identity.  The command uses no
  operational database default.
- Package scope, policy identity, criterion identity, declared coverage and
  human review clocks are checked before output.  Output is bounded (the same
  16 MiB authority ceiling), canonical JSON, atomic and only idempotent for
  byte-identical retries.  Existing `verify_authorization_package` remains the
  final authority boundary.

## Acceptance checks

1. A valid, independently reviewed fixture produces a package that the real
   authority verifier accepts for the exact current profile and scope.
2. Tampered replay/criteria/held-out bytes, mismatched source reports, a
   non-approved or malformed review identity, oversize inputs and incompatible
   scope fail without output or registry mutation.
3. A different existing output is never overwritten; identical retry is safe.
4. Focused package, replay, held-out, review, authority and CLI tests pass;
   relevant broader research/advisory tests, syntax and diff checks pass.

## Rollout and remaining evidence

This is Dev-only and GitHub-promoted only.  It does not create real data,
qualify a strategy, enable partner advice, send a message, or alter Production.
Operators still need retained dated masters, real completed-bar and active-leg
captures, a frozen future hold-out, costed outcomes, a saved profile, a genuine
human review and separately authorized delivery validation.

## Implementation receipt

Implemented in Dev: `partner_qualification_package.py` provides bounded,
root-confined loading; exact held-out reconstruction; immutable assembly; and
same-contract authority verification. `research_cli.py` now exposes
`build-qualification-package`. The command deliberately has no registry or
transport call and labels its result with `authorization_effect=NONE`.

Focused package/replay/held-out/review/authority/CLI acceptance passed **64
tests** with warnings treated as errors. The wider research/advisory group
passed **235 tests** with one existing Starlette async-generator-lifespan
deprecation. Under warning-fatal mode that framework warning fails setup before
the orchestrator tests run; it is unrelated to this offline CLI and is retained
as an explicit environment limit rather than hidden. Atlas regeneration reached
**211 Python modules**. Final staged-scope verification is recorded with the
implementation commit. Production remains untouched.
