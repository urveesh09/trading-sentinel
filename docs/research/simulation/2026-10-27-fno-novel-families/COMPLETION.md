# Completion and audit notes

## Outcome

Frozen search and reporting are complete. No candidate qualifies. The efficiency
candidate is the highest-profit exploratory result; the shipped control has a
better net/closed-drawdown ratio and remains the control. Production, paper rules,
the pinned O27c panel and application sources are unchanged. No push/deployment.

- Pre-score freeze commit: `3e2bcfe9d70f6bd338f047ab989958b0b69a4015`.
- 121 distinct genomes / 115 A trade histories; all attempted genomes in results.json.
- 29 archived sessions / 30 expected; September 18 unavailable. All dates seen.
- Final focused regression: **57 passed**, two existing dependency warnings,
  `regression-final.log` (37.18 seconds).
- Independent audit: 128 closed trade checks and 121 arm metric reconciliations.
- Three partial/proxy receipts account for all 47 calendar dates, including null
  metrics for weekends, holidays and the missing archive. Recorded daily cash and
  trade counts reconcile. `signals` counts emitted candidate decisions, including
  rejected admissions; it does not mean filled trades. No actual-execution profit
  is asserted: modeled quote-touch cash is entirely in `assumed_pnl`.

## Preserved reporting failure

`REPORT.md` / `REPORT.json` were produced by the unmodified simulation skill helper.
They are **INVALID**, with exactly `Policy source or Git SHA changed after freeze`.
The helper records the initial source HEAD (`07abebd`); committing the mandatory
pre-score freeze changes HEAD to `3e2bcfe` even though all application source hashes
are identical. Its `verify` also reports the inherited invalid-report flag. Neither
failure was erased, bypassed or relabelled as a helper pass.

`verify_study.py` is a separate, explicit audit. It requires the original helper's
exact failures, unchanged helper/source/input hashes, original and freeze commits
as ancestors, frozen lab/tests/configuration content, original dataset bindings,
unchanged Production, preserved unrelated Dev edits, financial reconciliation and
all generated report artifact hashes. Git-normalized LF/CRLF is allowed only when
comparing repository blobs; sealed working-tree bytes retain their original hash
checks. Its result is in `verification.json`. This adds evidence; it does not
qualify a strategy or repair the helper's metadata contract.

A future helper improvement should distinguish a committed source identity from
later report-only commits. That change needs its own tests and must not rewrite
this experiment's historical freeze.

## Recheck with the original private archive

From Dev, using its existing Python environment:

```powershell
python-engine/winvenv/Scripts/python.exe -m pytest docs/research/simulation/2026-10-27-fno-novel-families/test_lab.py python-engine/tests/test_fno_policy_replay.py python-engine/tests/test_fno_shadow.py python-engine/tests/test_fno_consistency_grid.py python-engine/tests/test_fno_evolution.py python-engine/tests/test_fno_forward_panel.py -q
python-engine/winvenv/Scripts/python.exe docs/research/simulation/2026-10-27-fno-novel-families/verify_study.py verification-recheck.json
```

The verifier refuses overwriting previous receipts. Raw packet files, parse caches,
per-arm detailed reports, original dirty-file backups and private coverage evidence
stay ignored under `_local`; a public checkout without these cannot revalidate the
raw replay. `analyze.py` intentionally refuses to overwrite existing audit/summary
outputs. Do not rerun the frozen search in place or re-seal inputs after scoring.

Matplotlib 3.10.7 and its dependencies were installed only under this study's ignored
`_local/plot-packages`. Its isolated chart process uses that path; the shared replay
venv/Production were not changed. The installer warns about NumPy/pandas compatibility
in that isolated target; the chart imports no pandas or replay code. The strategy
tests and ledger audit run with the unchanged shared scientific environment.

## Remaining research

No untouched forward evidence exists for these new candidates. A separately approved,
pre-registered prospective experiment and improved quote coverage are required before
considering any rule change. The existing O27c panel and proving-week restrictions
remain in force. No guarantee of consistent profit is supported by this study.
