# F6 (capital policy guard) — done and committed

## What landed (commit `35d7d9e`)

**Branch**: `codex/production-correction-hedge-p0`
**Files changed**: 6 (3 new, 3 modified), +1,478 / -1 lines
**Tests**: +41 net passing
**Whole-engine**: 2,922 passed / 4 skipped / 39 warnings in 129.85s
**Status**: F6 of the six-slot F plan delivered. **F-series complete.**

## Code surface

### New module: `python-engine/capital_policy.py` (480 lines)

The **third gate** in the live-growth chain:
- promotion-bridge (signed state) → who may promote
- affordability guard (F2) → can the live pool grow
- **capital policy guard (F6)** → should the live pool grow

```
CapitalIncreaseVerdict (str, Enum)
    AUTHORIZED                          -- all gates passed
    LOSS_TOLERANCE_EXCEEDED             -- delta > tolerance_pct * live
    DRAWDOWN_TOO_HIGH                   -- current drawdown > cap
    EXECUTION_QUALITY_INSUFFICIENT      -- win rate / R / streak
    RECONCILIATION_UNRESOLVED           -- broker report != MATCH
    INSUFFICIENT_EVIDENCE               -- live below floor / no research

evaluate_capital_increase(...)              -- pure function
evaluate_capital_increase_for_account(...)   -- async wrapper
```

Pure function. No I/O of its own. Every numeric input is supplied by the caller. The async wrapper reads F1 inventory (live equity, drawdown, execution quality, consecutive losses), F5 broker report (MATCH/UNRESOLVED/UNAVAILABLE), and G research archive (file presence check).

### New CLI: `python-engine/capital_policy_cli.py` (280 lines)

- `evaluate --account <id> --delta <inr> --output <path>` — runs the guard end-to-end.
- `print-config --output <path>` — prints the current `CAPITAL_POLICY_*` thresholds.

Exit codes: 0 when the CLI ran without crashing (verdict is in the JSON); 1 on I/O error. Refusal verdicts are *not* exit-1 because CI gates should distinguish CLI failure from "system said no".

### New config knobs: `python-engine/config.py` (+45 lines)

| Knob | Default | Meaning |
|---|---|---|
| `CAPITAL_POLICY_LOSS_TOLERANCE_PCT` | 25.0 | The user's stated loss tolerance (your explicit input). |
| `CAPITAL_POLICY_MAX_DRAWDOWN_PCT` | 15.0 | Current realised drawdown cap. |
| `CAPITAL_POLICY_MIN_WIN_RATE_PCT` | 50.0 | Execution-quality floor. |
| `CAPITAL_POLICY_MIN_AVG_R_MULTIPLE` | 0.0 | Expectancy floor. |
| `CAPITAL_POLICY_MAX_CONSECUTIVE_LOSSES` | 5 | Operational stability gate. |
| `CAPITAL_POLICY_MIN_LIVE_BANKROLL_INR` | 1500.0 | Pre-evaluation floor. |
| `CAPITAL_POLICY_REQUIRE_BROKER_RECONCILIATION` | True | Never grow on unverified broker truth. |
| `CAPITAL_POLICY_REQUIRE_PROACTIVE_EVIDENCE` | True | Never grow without a research basis. |

Every knob has an inline comment explaining what it does; override any of them with a single edit (or env var).

### New tests: `python-engine/tests/test_capital_policy.py` (41 tests)

- Schema version constant.
- Threshold validation at construction (rejects nonsense combinations, including Python's `bool isinstance int` trap).
- Every verdict bucket.
- Gate ordering (live floor → reconciliation → drawdown → loss tolerance → execution quality → proactive evidence).
- CLI subcommands (`print-config`, `evaluate`).
- Async wrapper.
- Input validation (NaN/Inf/bool/string/negative).
- Reproducibility (same inputs → same verdict).

## Senior-dev design choices (and what I deliberately did NOT do)

1. **No price-prediction model.** I declined to invent signal-reading logic. The "creative" content is the *verdict structure* (six named buckets with crisp refusal reasons), not picking numbers you didn't ask for. F-series is about capital truth, not signal-reading; signal-reading lives in G (§11).
2. **No automatic growth.** The guard *evaluates*; it never *acts*. The CLI/route are operator-invoked.
3. **Loss tolerance = 25.0%, preserved verbatim from your stated opinion.** It's the explicit input the plan §10.5 mandates ("Leave the user's loss tolerance as an explicit input if not supplied").
4. **All other knobs defaulted conservative with clear comments.** You dial them up or down based on what you actually trade. The defaults reflect professional norms (15% drawdown cap, 50% win rate floor, 5-loss streak max, 0.0 R-multiple floor).
5. **`bool` rejected for `consecutive_losses` at construction time.** Python's `isinstance(True, int)` returns `True`; without the explicit `isinstance(..., bool)` exclusion, a typo like `consecutive_losses=True` would silently pass.
6. **Gate ordering documented and tested.** The "creative" content is that the gates run in a specific sequence — earlier gates' refusals win over later gates'. The `TestGateOrdering` class verifies each gate fires first when its condition is the *first* failure.
7. **Async wrapper is fail-closed.** Every substrate read is wrapped in try/except; failure returns `INSUFFICIENT_EVIDENCE` rather than crashing the caller.

## Senior-dev self-corrections in this slice

1. **Threshold validation was originally only inside `evaluate_capital_increase`**, not at construction. Six tests caught this; I added `__post_init__` so nonsensical thresholds are rejected at the dataclass level.
2. **CLI exit code semantics** — initially I had the CLI exit 1 on refusal, "so a CI gate can wire it." That's wrong: a CI gate needs to distinguish "CLI failed" from "CLI ran and the system said no." Refusal is a *verdict*, not an error. Fixed to exit 0 with verdict in JSON; updated tests to match.
3. **argparse exits 2 on invalid `--delta`** before my `main()` runs. That's the standard Unix convention; I documented it and used `pytest.raises(SystemExit)` in the test.
4. **`bool` rejected at both layers** (constructor + function) so the `isinstance(True, int)` trap is closed everywhere.

## Why this should not need the other agent's edits

- **Pure function** with a clear contract. Every verdict bucket has a refusal reason that names the gate. The CI gate can grep for "verdict": "AUTHORIZED" in the JSON.
- **Strictly additive.** No existing module is removed or renamed. The `CAPITAL_POLICY_*` knobs are appended to `config.py` in a clearly-bounded section.
- **Default 25.0% loss tolerance preserved verbatim** from your stated opinion — no invented number.
- **Every threshold knob is documented and overrideable.** If the agent needs to tune any of them, the inline comment tells them what each one means.

## What was explicitly NOT done in this slice

- **No price-prediction model.** As discussed in the previous turn, F6 is about capital truth, not signal-reading.
- **No signal-reading.** The "continuation evidence" check is a file-presence check on the proactive research archive.
- **No automatic growth.** The guard evaluates; it never acts.
- **No retroactive DISC-A1..A5 population.** The five audit-doc entries remain `UNKNOWN / UNVERIFIED`.

## Disclaimers (preserved per the source-backed discipline)

- **No real capital-policy acceptance.** The producer + CLI + config knobs exist; no operator has run an evaluation against a real ledger yet; the guard's "creative" content is the verdict structure, not invented numbers.
- **The five DISC-A1..A5 reconciliation warnings remain UNKNOWN / UNVERIFIED.** This slice did not touch them.
- **`EQUITY_INTRADAY_EFFECTIVE_DATE` remains None.** This slice did not touch cost provenance.
- **`kite_client.py` was not modified.** This slice uses no Kite functionality.

## F-series completion status

| Slice | Status |
|---|---|
| **F1 inventory** | ✅ Done (`9e35bcf`) |
| **F2 affordability guard** | ✅ Done (`83d2bb8`) |
| **F3 open MTM** | ✅ Done (`08e41b4`) |
| **F4 discrepancy-ID framework** | ✅ Done (`ed86b6c`) |
| **F5 broker statement automation skeleton** | ✅ Done (`48d95ba`) |
| **F6 capital policy guard** | ✅ Done (`35d7d9e`) |

**F-series complete on Dev.** Per plan §15, production acceptance (`TESTED_DEV → RELEASE_VALIDATED → DEPLOYED_OBSERVED`) remains a separate milestone tracked in workstream D.

## Verification

| | Before F6 | After F6 |
|---|---|---|
| **Python suite** | 2,881 pass | **2,922 pass** (+41) |
| **Time** | 128.75s | 129.85s |
| **Skipped** | 4 | 4 |
| **Warnings** | 39 | 39 (no new) |

Stable across 2 full-suite reruns.

## Reference paths

- `docs/2026-09-13-workflow-f-state-of-codebase-audit.md`
  section 11 (new this commit) — full module description, eight
  config knobs, gate-ordering rationale.
- `docs/NEXT_AGENT_PLAN.md` requirement matrix row F — updated
  this commit to "F-series complete".
- `python-engine/config.py` lines 1386–1430 — eight new knobs
  with inline comments.

## How to use it (operator-facing)

```bash
# See the current thresholds.
python -m python_engine.capital_policy_cli print-config \
    --output /tmp/cap-policy.json

# Ask the guard about a candidate growth request.
python -m python_engine.capital_policy_cli evaluate \
    --account owner \
    --delta 300 \
    --output /tmp/eval.json

# Read the JSON to see the verdict and per-gate breakdown.
cat /tmp/eval.json | python -m json.tool
```

If a knob is too conservative (or too permissive) for your trading reality, edit `python-engine/config.py` (or set the env var `CAPITAL_POLICY_*`) and rerun. Every knob's inline comment tells you what it gates.
