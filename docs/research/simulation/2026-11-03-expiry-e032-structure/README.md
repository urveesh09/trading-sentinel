# E03.2 second investigation — information, execution and payoff

Plain report: [EXPIRY_RESEARCH_E032_STRUCTURE.md](../../../EXPIRY_RESEARCH_E032_STRUCTURE.md).
Frozen starting contract: [PLAN.md](PLAN.md). Current work/status: [STATUS.md](STATUS.md).

**No E03.2 replacement.** Six primary mechanisms failed; a new displayed-depth
pressure signal has a tiny 30-second midpoint effect that spread/fees consume.
No engine/config/flag/schema change; E03.1 remains off, Production untouched.
The owner explicitly reopened research after the first E03.2 search. Its
original report, failures and future exam remain immutable, as does 2023.

## Data and fidelity

- 105 NIFTY expiry-minute tapes, 52 in 2024 and 53 in 2025, inherited selected
  snapshots in `../2026-11-03-expiry-e02/_local/2024.sqlite` and `2025.sqlite`.
  SHA-256 in `initial.json`, reverified by `structure_checkpoint.py verify`.
  Both years seen before this study. Current 65-unit lots and native fees are
  normalized research, not historically realizable lot/tax returns.
- BAR_LIFECYCLE / PARTIAL, private Rs 25,000 own-cash books with continuous
  drawdown brakes, two sequential tickets, 1,250 per ticket / 2,500 original
  daily risk reserve, no refills. Reset-year results are separate experiments;
  they must never be added when continuous risk paths differ.
- Completed current-bar decisions, next-bar open/wider-cost/severe high-low
  execution, model spreads and 20% bar-volume proxy. No intrabar touch fills.
  Four-strike current-spot limit retained; no future-dependent selection.
- Round 3 explicitly generalizes single-long premium to bounded combination
  net debit plus charges, while all gross long-leg purchases fit own cash.
  Both new shapes are rejected. Butterfly's unresolved/full-premium written-off
  continuation is **invalid as a verified flat portfolio**; raw failed outputs
  preserved, no accepted money receipt. Severe zero may mean no entries.
- Quote evaluator reads only the five already-seen NIFTY dates from the two
  source DBs in `freeze-micro-v2.json`; four days have five-level evidence.
  October 6 unavailable (compact packets), not zero. Native timestamps, fees,
  next observed ask/bid depth, one-lot markouts. Overlapping conditional marks
  are **EVALUATOR**, never cumulative or independent portfolio profit.
- Full SENSEX-chain E03-family qualification is unavailable; no SENSEX score or
  theory-based option history invented. No new acquisition/API calls.

## Reproduction

Use Dev `python-engine/winvenv/Scripts/python.exe`; no credentials/scheduler.
The score scripts require committed freezes and refuse overwriting results.
The existing outputs are the original runs; inspect rather than blindly re-run.

```text
run_study.py verify       # round 1 freeze; baseline/E03/E031, patient, option-led
round2.py verify          # reclaim and value-check frozen sources
round3.py verify          # vertical and butterfly frozen sources
micro.py verify           # quote-evaluator v2; v1 is retained superseded draft
structure_checkpoint.py verify
python -m pytest <this-directory> python-engine/tests/test_expiry_e02.py python-engine/tests/test_expiry_e03.py python-engine/tests/test_expiry_e031.py -q
```

Original score commands (immutable files already exist):

```text
run_study.py score
round2.py score
round3.py score
micro.py score
audit.py
micro_diagnostics.py
finish.py
```

`build_loop.py` materializes one asserted order-state hook into the inherited
E03.1 loop; `mechanism_day.py` is inspectable. Round 2 uses the same loop with
different signal/pick functions. `payoff.py` is an explicitly separate pack
model, never an engine replacement. `micro.py` reuses native quote parsing,
freshness, depth walks, fees and risk reservation without native run_tick/DB
writes. `audit.py` blocks sockets before imports and reproduces all full
histories, checking native money independently of the research fee helper.

## Evidence map

| Artifact | Purpose |
|---|---|
| `initial.json` | Original owner/status/engine/research/data/Production fingerprints |
| `freeze-round1.json` | PATIENT / OPTION_LED, committed `120acde` before scoring |
| `freeze-round2.json`, `ROUND2.md` | Reclaim / valuation, `ee8b147` before scoring |
| `freeze-round3.json`, `ROUND3.md` | Payoff shapes, `bd3653b` before scoring |
| `freeze-micro-v2.json`, `MICRO.md` | Quote pressure, `15ed70b` before scoring |
| `round1-results.json` through `round3-results.json` | Every event, day and annual/continuous cash path, all three fills |
| `micro-results.json` | Every markout, refusal, daily coverage and timing |
| `micro-diagnostics.json` | Fixed two-second freshness and added-snapshot latency diagnostics |
| `audit-results.json` | 63 full-history replays, 1,287 repeated records, fees/reserves/causal reconciliation, failed acceptance and fixed added friction |
| `daily-results.csv` | 4,410 model day rows (annual experiments separate from continuous) |
| `verification.json` | 55 passing focused checks, original pre-score/tooling failures, no full-suite assertion |
| `LITERATURE.md` | Primary sources, applicable findings and unavailable facts |
| `NEXT_EXAM.md` | Original future exam protected; new microstructure evidence requirements |

The raw selected-year and quote DBs remain in ignored local Dev directories,
not committed broker data. Their full-file hashes were verified, not merely
copied from an old manifest. Reproduction on another machine needs those same
owner data bytes. Hashes and helper checks cannot establish financial truth.
Owner-original tails are held in `_local/*.initial` and selectively excluded
from our shared-doc commits; never stage those docs wholesale.

Audit's sampled mark statistic compares available model marks with realized
cash peaks. It is not a complete intrabar or mark-to-mark NAV drawdown; missing
liquidity/marks and pack capacity prevent that claim. Acceptance used realized
cash drawdown and explicit unresolved exposure, not that incomplete statistic.

No migration, rollback action, deployment or enable was needed. Stop this
research directory to roll back the experiment; existing strategies are intact.
