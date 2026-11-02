# Expiry E01 successor entry point

Read [the plain-language report](../../../EXPIRY_RESEARCH_E01.md) first, then
PLAN.md, ROUND1.md, PREFLIGHT_CORRECTIONS.md, ROUND1_OUTCOME.md, VERIFICATION.md
and IDENTITY.json. This study is Dev only on the existing branch. No Production
restart, deployment, configuration or real-order change.

Selected CSTOP30 becomes **CE01**, an independent exact-entry C shadow, not a
new main strategy. PAIR30 failed. Main expiry-v3 and N11 remain unchanged.
Only eight seen expiry sessions exist; net without the best is still negative.

## Evidence and reproduction

- `freeze-round1-v2.json` is the active **pre-score** source/config/input
  contract (696 source/config entries; 30 inputs). `freeze-round1.json` is the
  retained superseded draft. Scores did not exist before the active freeze.
- `configuration.json`, `policies.py`, `round1.py`, `score_e01.py`: fixed
  hypotheses, populations, stress and all pass/fail conditions. Neighbours are
  diagnostics only. No second round was run.
- `control-parity.json`: 8 historical controls / 95 position legs. Original
  history versions are parity controls, not the candidate benchmark.
- `results-round1.json`: 80 declared baseline/primary/neighbour/stress cases.
- `native-parity*.json`: three successive 16-case integration validations,
  retaining the original and each binding hardening. They are not additional
  strategy trials or fresh data.
- `audit.py`, `audit-results.json`: independent recorded-depth, fee, full-risk,
  budget and settlement identity checks over the research/integration cases.
- `_local/export/expiry.sqlite`, `_local/source/`, `_local/evals/` and
  `_local/books/`: private consistent snapshot, exact historical source,
  individual events and scratch books. Never upload these broker archives.
- `_local/frozen-source/`: every original source byte at its pre-integration
  hash. Application integration intentionally changes the working tree;
  strict round1 source verification therefore fails on the integrated checkout.
  Do not weaken it. Use an isolated checkout of cbbdebb with the same frozen
  private inputs to reproduce research, or verify the complete archived tree.

Use `python-engine/winvenv/Scripts/python.exe`. Native replay uses the shipped
`_tick_underlying` against archived packets and disables external network after
Windows asyncio has created its self-pipe. Never start a scheduler or broker.
The existing raw case names are immutable: a new engineering validation needs
a new label and receipt. `verify_native.py` intentionally refuses to overwrite
its final cases. Keep actual errors and all earlier attempts.

The final `package_evidence.py <fixed-HEAD>` packet binds the integrated source,
archived original source, inputs and results after all commits. It is **post-run
consistency**, not retroactive preregistration or financial proof. Its generated
REPORT.md/REPORT.json live under `_local/evidence-report-final/`. Every missing
calendar date is unavailable, not an invented zero or guessed holiday.

## Remaining work and rollback

After a separately authorized GitHub deployment, collect the frozen 20-entry
forward sample, at least five per index, with exact C parent identity/economics,
coverage and quote/exit paths. No automatic promotion or new size. Full protocol
and acceptance routes are in the main report and ROUND1.md. Distinguish actual
fills, paper continuous/auction fills and assumed settlement.

Switch off **new** shadow entries with `EXPIRY_E01_SHADOW_ENABLED=false`; do not
remove management of existing CE01 legs. Old days are never retro-enrolled.
Future one-minute history alone cannot recreate 10-second depth or 25-second
confirmation behavior. No acquisition, 2022 test or new historical target was
authorized/performed by this study. Do not run another grid on these eight days.
