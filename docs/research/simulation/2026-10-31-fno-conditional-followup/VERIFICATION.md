# O31h verification

Pre-replay source/diagnosis/config/data freeze: **a45eadd**, pushed first.
Results: **fe94d2f**. The documentation handoff identity is recorded in Git
history. All work is Dev research; no application, config, migration, order
authority, capital activation or Production changes.

Use `python-engine/winvenv/Scripts/python.exe` (Python3.11.9).

Completed commands:

```text
python -m pytest docs/research/simulation/2026-10-31-fno-conditional-followup/test_follow.py -q
# 15 passed on frozen source
python scripts/build_system_code_atlas.py
# 291 modules, no atlas diff
python docs/research/simulation/2026-10-31-fno-conditional-followup/lab_follow.py freeze
# committed/pushed as a45eadd before scoring
python docs/research/fno/run_slice.py --seconds 550 --env O30F_YEAR=2024 --log docs/research/simulation/2026-10-31-fno-conditional-followup/_local/run-2024.log -- docs/research/simulation/2026-10-31-fno-conditional-followup/lab_follow.py run --jobs 3
python docs/research/fno/run_slice.py --seconds 550 --env O30C_YEAR=2025 --log docs/research/simulation/2026-10-31-fno-conditional-followup/_local/run-2025.log -- docs/research/simulation/2026-10-31-fno-conditional-followup/lab_follow.py run --jobs 3
python docs/research/fno/run_slice.py --seconds 550 --env O30C_YEAR=2026 --log docs/research/simulation/2026-10-31-fno-conditional-followup/_local/run-2026.log -- docs/research/simulation/2026-10-31-fno-conditional-followup/lab_follow.py run --jobs 3
# each returncode0, DONE7; 108/104/86 seconds
python docs/research/simulation/2026-10-31-fno-conditional-followup/analyze_follow.py
# returncode0; passing=[]; problems={}; main and old raw trade-for-trade parity
python -m pytest docs/research/simulation/2026-10-31-fno-conditional-followup/test_follow.py docs/research/simulation/2026-10-31-fno-complements/test_gap.py docs/research/fno/2026-10-31-weak-spots/test_lab_w.py python-engine/tests/test_fno_book.py python-engine/tests/test_fno_policy_replay.py -q
# 77 passed in23.98s; no full engine-suite claim
```

Before the freeze: diagnostic runs over2024/25/26 reconstructed182 old raw
entries; `diagnose.py report` published all22 nonmissing bucket conditions per
family and the three two-year selection rotations. No eligible positive
condition with>=8 trades in each fitting year; no fresh holdout claim.

Post-run independent checks:

- All182 old diagnostic trades, annual/monthly/bucket sums and unique
  identities reconcile. Input mutation after the signal or on/after today's
  daily candle leaves every entry feature unchanged.
- Recomputed532 closed trade records across21 independent arms from quantity,
  premium difference, shipped fees and extra costs; max error <Rs0.00005.
- Actual datetime arithmetic verifies signal-bar start+5minutes<=entry,
  exit>=entry and hard-flat clock<=15:10; daily gate/member attribution,
  whole-lot bounds and day caps verified. No unresolved or memo conflicts.
- Rechecked all source/data/daily/memo/random-control fingerprints.
- **Reparsed699 sessions directly from raw candles**, comparing each complete
  observation/contract/quote/clock packet with its existing cache: all identical
  (248/248/203). Local program `_local/verify_inputs.py`, receipts
  `_local/input-check-2024.json` /2025/2026. No API/network calls.
- `crosschecks.json`, `diagnostic-crosschecks.json` are derived receipts. Raw
  trade/price evidence remains local; dedicated study `.gitignore` files
  protect it without staging the owner's unrelated root ignore changes.
- Documentation checked immediately after commits. Production availability
  read-only HTTP200. No live-order or profitability conclusion.

The helper packet under `_local/evidence-report/` is post-run consistency
packaging of the committed study, not a retrospective pre-registration. The
actual pre-run source and data contract is the a45eadd freeze. It separately
reports main and two combined shadow books; no sum of independent arms.

Remaining: reject these entries; preserve the original2023 exam; verified
acquisition/input repairs, real costs and fresh paper evidence; additional
news/constituent/order-flow inputs before their corresponding research. Any
funded-spread comparison needs a matched two-leg lifecycle and frozen plan.
