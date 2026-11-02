# N09.1 verification

Date: November1,2026, Asia/Kolkata. Python3.11.9; NumPy1.26.4;
pandas2.2.1; pytest8.0.0. Existing Dev winvenv; no installs.

## Source and boundaries

- Dev branch codex/production-correction-hedge-p0; basea63b32a.
- Original pre-score source4245670; exact controls/stressc5351a7.
- Post-score terminal-identity correctionc6bbcb9; original freeze and scores
  preserved, unchanged trading function ASTs,24 mandatory exact parity reruns.
- No app source/env/migration/risk authorization/order/message/capital/deploy
  change. Productionc97cb8c; engine start2026-11-01T01:41:39.3519856Z unchanged.
- Three replay workers maximum, inherited Windows memory guard, network-denied
  workers; all inputs local. No Breeze/Kite/Telegram calls or2022 access.

## Commands

Use python-engine/winvenv/Scripts/python.exe from Dev.

```powershell
python -m pytest docs/research/simulation/2026-11-01-fno-n091/test_n091.py docs/research/simulation/2026-11-01-fno-n091/test_state_identity.py docs/research/simulation/2026-11-01-fno-n09/test_n09.py docs/research/simulation/2026-11-01-fno-n09/test_n09_scoring.py -q --disable-warnings
python -m pytest python-engine/tests/test_fno_exit_rules.py python-engine/tests/test_fno_policy_replay.py -q --disable-warnings
python docs/research/simulation/2026-11-01-fno-n091/run_study.py controls
python docs/research/simulation/2026-11-01-fno-n091/audit.py controls
python docs/research/simulation/2026-11-01-fno-n091/run_study.py primary
python docs/research/simulation/2026-11-01-fno-n091/run_study.py costs
python docs/research/simulation/2026-11-01-fno-n091/run_study.py carry
# State repair: N08_YEAR=2023,2024,2025,2026, one at a time:
python docs/research/simulation/2026-11-01-fno-n091/repair_states.py
python docs/research/simulation/2026-11-01-fno-n091/audit.py full
# Quote audit: N08_YEAR=2023,2024,2025,2026, one at a time:
python docs/research/simulation/2026-11-01-fno-n091/audit_prices.py
python docs/research/simulation/2026-11-01-fno-n091/score.py
python docs/research/simulation/2026-11-01-fno-n091/stress.py
python docs/research/simulation/2026-11-01-fno-n091/make_report.py
python scripts/build_system_code_atlas.py
```

The recorded run is immutable: run_study guards existing logs and repair_states
requires a fresh repair namespace. These are exact recorded commands, not an
instruction to overwrite an archived study. Reproduction needs a new run/output
namespace and all retained private inputs. Direct driver.py may reuse evals;
that is not evidence of a fresh replay. Repair namespaces were fresh and installed
at module level in Windows children, preventing that earlier N08 failure mode.

## Measured durations

Every child returned0. Seconds in2023/2024/2025/2026 order:

| Phase | Seconds |
|---|---|
| controls | 68.12 / 67.39 / 55.67 / 48.45 |
| primary | 60.41 / 51.26 / 54.92 / 47.39 |
| costs | 100.3 / 85.05 / 90.06 / 76.95 |
| carry | 97.14 / 80.34 / 87.19 / 75.74 |
| repair | 102.89 / 84.48 / 91.05 / 77.61 |

60 declared unique annual books:12 controls,8 primary,24 cost diagnostics,
16 continuity.24 additional state-repair executions are exact repeats, not new
hypotheses. All24 economic trade lists and full admission/decision receipts
equal the archived originals. Independent60-book audits use the corrected
full-window fresh states and original distinct continuous carry states.

## Checks and limitations

- 55 focused checks:21 N09.1,23 N09 and11 native exit/replay. No full-suite claim.
- 12 exact controls reproduce675 prior trades. Cash, original admission terms,
  current fees/stress and all accepted/rejected budget decisions reconcile.
- Audit counts:{"annual_books": 60, "budget_decisions": 1904, "financial_lifecycles": 2798, "funded_full_premium_admissions": 846, "immutable_budget_admission_bindings": 1571, "independent_floor_clock_reconstructions": 1179, "persisted_cash_state_checks": 32}.
- 5596 entry/exit prices matched the archived
  modeled bid/ask observations. Native gates/closed-bar clocks retained.
- Original945 source/972 cached input/old receipt hashes bound pre-score;
  explicit correction binds947 source files with the same inputs plus correction
  identity. Original cached data reused, not claimed as new market acquisition.
- First audit failed on terminal snapshot identity. SOURCE_CORRECTION documents
  the defect, source comparison and post-score nature of repair. No threshold,
  trading rule, result or acceptance changed. No failed result discarded.
- A checker-only opening-display tolerance was corrected: native212025.95
  versus raw-close212025.9529 differed by0.0029rupees. Display comparisons use
  one paise; per-trade fee checks remain0.001rupees. CHECKER_CORRECTION.md.
- An exploratory PowerShell display tried string.Substring on JSON timestamps
  auto-converted to DateTime and failed. It supplied no scored metrics; Python
  score.py/audit.py independently read preserved ISO strings for all results.
- All years seen;2026 partial toOct28. Closed drawdown only,65 normalized lots,
  current fees/modeled spreads/assumed extra cost, clipped candles/gaps retained.
  No historical depth, actual fills or small-live-trial qualification.
- Atlas regenerated291 modules/no diff. Original N08/N09 studies and application
  source unchanged. Unrelated owner .gitignore/doc slices/untracked work retained.

The post-run skill packet follows at the final Git SHA. It checks evidence
consistency only, never profitability, preregistration or whole-system returns.
