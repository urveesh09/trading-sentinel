# E01.1 new-history exam and bounded improvement

Owner request November 3, 2026: understand the inherited tests, test E01.1 on
new NIFTY/SENSEX expiry history, diagnose losses and missed upside, and improve
only with evidence that survives an untouched test. Dev starts at 65a11f1 on
codex/production-correction-hedge-p0. Existing owner changes are preserved.
Production checkout is 06bed07, which already includes expiry-v4 on paper;
the older handover's not-deployed status is superseded. No deployment here.

## Contracts and files

- Read-only local history and authoritative exported coverage, no API calls,
  downloader changes, repair, secrets, Production writes or N11 changes.
- New scripts, frozen snapshots/configuration/hashes, tests and results live in
  this directory. Reuse expiry_paper money/exits and the E01.1 lab, verify against
  archived October receipts before interpreting new results.
- Opening-ATM ten-second OHLC supports a PARTIAL paired-exit panel and only the
  entry opportunities actually present. Missing strikes are unavailable, never
  zero. A/B or an entire book must not be inferred from that panel. Minute
  history coverage is inspected separately; any minute adaptation is a distinct
  model, never native ten-second parity or a combined profit claim.
- Exclude all pre-2025 prices from this job, especially sealed NIFTY 2023.
- Rs 2,500 independent full-premium ceiling, whole lots, native fees, no
  leverage or averaging. Historical lot changes require verified dated evidence
  or an explicit constant-size research normalization, never invented history.
- No tick/depth or 15:38 execution can be recovered from OHLC ending 15:30.
  Endpoint sale models and unresolved remainder must be explicit. Assumed
  worthless marks are never reported as actual zero-price sales.

## Sequence and protection against fitting

1. Coverage only, no strategy outcomes. Seal authoritative selected inputs and
   source/assumption hashes. Reproduce archived baseline/exit mechanics.
2. Development: new January-June 2026 sessions only. Inspect frozen E01/E01.1
   controls, causal loss reasons and upside concentration. Existing October and
   four September NIFTY sessions are already seen and remain diagnostics.
3. Before any other new outcomes: register at most TWO novel, simple candidates
   from the development diagnosis, freeze their source, execution assumptions
   and acceptance tests in a commit. No genome or threshold optimization.
4. Validation: July-October 1, 2026 excluding already-seen September 8/15/22/29
   NIFTY. Test: available 2025. Score once, do not adjust candidates afterward.
   The old EXAM_YEAR arms (old C, E01, E011, E011R, S20, BOX35, BAND50) remain
   frozen and are scored on every eligible new session; the two entry readings
   are unavailable where strikes prevent a fair admission test.
5. Report each index/year/window/scenario, paired entry identity, missing
   coverage, fees, net/ex-best/worst/drawdown, losing streak, 3x outcomes,
   direction and opportunity cost. Preserve every rejected result.

Novel-candidate acceptance on BOTH validation and 2025, ordinary and adverse:
net positive, net without best session positive, net higher than E011, worst
session no worse, daily realized drawdown no worse, no greater full-premium
budget; require support on both indices where samples permit. Insufficient
coverage/sample is inconclusive, not a pass. Prior EXAM_YEAR uses its original
relative net/worst/ex-best tests and winner retention for entry variants.

## Verification, rollout and rollback

Tests cover completed-bar causality, missing observations, pending exits,
whole-lot fee-inclusive ceilings, initial stops, identical entries for exit
arms, and financial/event identities. Freeze guard refuses changed bound
inputs/code. Record real commands/results and environment limits. Regenerate
atlas when source declarations change; update guide/active plan/checklist with
each implementation commit, immediately verify consistency afterward.

Research-only outcomes cannot authorize promotion. A supported change can be
implemented as a separately versioned Dev paper shadow with exact native parity;
deployment flows through GitHub on separate authorization. A negative result
retains E01.1 and delivers specific evidence/data improvements. Rollback of this
study is to stop its isolated process; no operational state/config/migration is
changed. Remaining: coverage, snapshots/parity, development, freeze, untouched
scores, independent audit, detailed report and Dev commit/status receipt.

## Development receipt and freeze scope

100 of 110 exported dates have all paired afternoon observations and valid rows
(51 development, 23 validation, 22 test2025, four already seen). Ten remain
unavailable. Inherited October E01/E011/E011R economics/events reproduce 42 legs
with zero mismatches. Initial six event discrepancies were record-only index /
failed-break-line annotations, preserved in parity-initial-context-mismatch.json;
all money and clocks already matched. Development was run while diagnosing those
annotations; no validation/test outcomes were opened.

Development panel: E011 -16,828.51 ordinary, -30,731.84 adverse, against E01
-22,397.75 / -35,892.55. 92 of 101 ordinary tickets lose, nine reach 3x; most
losers barely advance. Two candidates, exactly one setting each:
E012_IDLE8 copies A's eight-minute / +40% idle rule; E012_LOCK40 copies AL's
half-peak-gain floor, armed at A's +40%. IDLE8 improves development loss to
-10,607.35 / -23,960.21; LOCK40 worsens total to -23,897.58 / -38,489.49.
Both are retained for the registered test, with no tuning or winner substitution.

The distinct NIFTY 2025 minute C proxy is also frozen before any 2025 result:
53 expiry sessions, actual independent index/front-future bars, recorded chain,
two completed minute confirmations (65 s gap limit), next-bar fills, scheduled
exit from 15:28. It tests only C, not A/B or a unified book. Current normalized
lots/fees, modelled liquidity, partial chain and coarse clocks remain explicit.
Raw selection SQL reads only 2025; pre-2025 evidence remains unseen. Tests and
snapshot/freeze hashes bind the model, candidates and acceptance rules before
the validation, 2025 panel and minute proxy are scored once.
