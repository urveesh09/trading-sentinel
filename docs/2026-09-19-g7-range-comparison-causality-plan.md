# Workflow G.7 — range comparison causality correction

**Status:** TESTED_DEV. Commit/push receipt pending. Production is unchanged.

## Problem

`RANGE_REVERSION_V1` has a dedicated verifier, but its dispatcher selects the
last candidate bar up to the entry deadline and then lets the generic
confirmation simulator enter from the first candidate bar. A later bar can
therefore validate an earlier modeled fill. When history is insufficient or
malformed, the branch also falls through to generic completed-bar confirmation
instead of returning the range-specific fail-closed verdict documented by G.3.

The predeclared comparison protocol still describes every range profile as a
confirmation alias, attaches a semantic limitation, and forces it to
`UNCERTAIN`. Those rules were correct before the dedicated dispatcher existed
but now prevent genuine causal range evidence from reaching the ordinary
predeclared research gates.

## Files and contracts

- `python-engine/proactive_intelligence.py`: evaluate only the first completed
  candidate after the decision cutoff, require 14 prior history bars, return a
  named range-specific `NO_FILL` for insufficient/malformed history, and begin
  modeled execution strictly after the evaluated entry-decision bar.
- `python-engine/proactive_comparison_protocol.py`: remove only the obsolete
  alias limitation and forced-uncertain override. All completeness, economic,
  drawdown, paired uncertainty, immutable implementation identity and
  no-authority gates remain unchanged.
- Range dispatcher/comparison tests: prove that a later favorable bar cannot
  backdate an earlier fill, insufficient history cannot fall through, malformed
  bars fail closed, range and confirmation remain distinct, and a complete
  causal range profile is judged by the same predeclared gates as other
  profiles.
- Canonical guide, plan, checklist and generated atlas: replace stale alias
  claims with the corrected boundary and exact verification evidence.

Existing frozen comparison protocols bind the protocol and primary evaluator
source hashes. They must continue to fail identity validation after this source
change; operators must freeze a new protocol ID rather than reinterpret stored
results under corrected semantics.

## Acceptance checks

1. Pre-change range/comparison baseline remains recorded: 76 tests passed with
   warnings fatal.
2. The range verdict consumes exactly 14 bars at or before the causal cutoff
   plus the first eligible completed decision bar.
3. Execution begins strictly after that decision bar. Later bars cannot alter
   whether an earlier decision entered.
4. Missing history, no eligible decision bar, malformed/duplicate/nonfinite
   bars, and verifier exceptions return explicit fail-closed outcomes; none
   silently use generic confirmation.
5. Stable-range ENTER and strict-stop propagation still compose with all
   supported exit profiles without order, qualification or approval authority.
6. The comparison report no longer invents an alias limitation or forces range
   profiles uncertain, but ordinary completeness/economic/drawdown/paired gates
   still control disposition.
7. Focused and whole-engine tests, compilation, atlas and diff checks pass.

## Rollout and rollback

This changes offline research simulation and immutable comparison semantics
only. It adds no schema, migration, configuration/default, scheduler, broker
call, order path, partner delivery or capital authority. Promote through GitHub.
Rollback reverts source/tests/docs; stored protocols/results remain immutable
and are not rewritten. Any protocol frozen under a different implementation
hash requires its original code or a new protocol ID.

## Remaining work

This correction removes temporal leakage and stale gating; it does not create
held-out observations, prove positive expectancy, sign a BridgeDecision, prove
shared-book capacity, qualify a partner strategy, or deploy anything. Genuine
predeclared sessions, F/D evidence and operator review remain required.

## Verification receipt

- Pre-change focused range/comparison baseline: 76 passed, warnings fatal.
- Corrected focused range/comparison surface: 81 passed, warnings fatal.
- Broader proactive/G surface: 222 passed, warnings fatal.
- Whole engine: 4,095 passed, four skipped, 46 known Starlette/httpx
  deprecations in 204.44 seconds. JUnit:
  `C:/Users/Urveesh/AppData/Local/Temp/sentinel-g7-range-causality-20260919.xml`.
- Atlas regenerated and remains 203 Python modules. Changed-source compilation
  and `git diff --check` passed. The whole suite refreshed generated-at-only
  session golden files; those unrelated changes were removed without changing
  the vectors.

No schema/data migration, configuration/default change, network call, order,
capital/qualification authority, partner delivery or Production edit occurred.
Implementation, documentation receipt and push identities will be recorded
after each step is verified.
