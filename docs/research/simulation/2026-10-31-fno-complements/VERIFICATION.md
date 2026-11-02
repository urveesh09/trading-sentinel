# O31g verification and handoff

- Pre-run source/config/data contract: **86a4fd0**, pushed before scoring.
- Results and documentation: **e6bb57d**, Dev only. This handoff records those
  identities; its own identity is in Git history. Production read-only checkout
  still `c97cb8c3ba0eeb4ac8e9966135b07034d760b40d`.
- All application source, settings, order authority and migrations unchanged.
- Owner's pre-existing dirty files and document slices preserved. Only this
  study and its three documentation sections are committed.

Interpreter: `python-engine/winvenv/Scripts/python.exe` (Python3.11.9).

Commands actually completed:

```text
python -m pytest docs/research/simulation/2026-10-31-fno-complements/test_gap.py -q
# 13 passed
python scripts/build_system_code_atlas.py
# 291 modules, no atlas diff
python docs/research/simulation/2026-10-31-fno-complements/lab_gap.py freeze
# three-year datasets, daily snapshots, source, settings, memos and controls bound
# freeze committed/pushed as 86a4fd0 before the following runs
python docs/research/fno/run_slice.py --seconds 550 --env O30F_YEAR=2024 --log docs/research/simulation/2026-10-31-fno-complements/_local/run-2024.log -- docs/research/simulation/2026-10-31-fno-complements/lab_gap.py run --jobs 3
python docs/research/fno/run_slice.py --seconds 550 --env O30C_YEAR=2025 --log docs/research/simulation/2026-10-31-fno-complements/_local/run-2025.log -- docs/research/simulation/2026-10-31-fno-complements/lab_gap.py run --jobs 3
python docs/research/fno/run_slice.py --seconds 550 --env O30C_YEAR=2026 --log docs/research/simulation/2026-10-31-fno-complements/_local/run-2026.log -- docs/research/simulation/2026-10-31-fno-complements/lab_gap.py run --jobs 3
# all returncode0, DONE8; 112/120/98 seconds
python docs/research/simulation/2026-10-31-fno-complements/analyze_gap.py
# returncode0; passing=[]; financial/memo problems={}; parity exact
python -m pytest docs/research/simulation/2026-10-31-fno-complements/test_gap.py docs/research/fno/2026-10-31-weak-spots/test_lab_w.py python-engine/tests/test_fno_book.py python-engine/tests/test_fno_policy_replay.py -q
# 62 passed in22.74s
```

Independent checks (separate inline calculation; outputs in `crosschecks.json`):
1. 1,087 closed records, all24 independent replay arms; zero unresolved.
2. Trade net independently recomputed from entry/exit price × quantity, shipped
   brokerage/taxes, and the declared extra cost. Max discrepancy <Rs0.00005.
3. Whole lots, day caps, entry/exit timing, closed-signal clocks and daily
   ADX/member attribution verified for every stored trade.
4. Every frozen source, sealed dataset, daily snapshot and reused random file
   hash rechecked. No strategy-score threshold changed after the freeze.
5. Read-only sealed-data quality scan: 2025 has56 negative-volume bars on four
   dates; 2024/2026 have0. No repairs or favourable exclusions.
6. Main exact and raw parity, existing TPB-put control parity; actual combined
   books evaluated rather than summing separate strategies.
7. Documentation consistency checked immediately after source/results commits.
   Unrelated dirty source/document slices retained. No raw evidence tracked.

The local post-run helper report (`_local/evidence-report/REPORT.md`) packages
the finished study with verified private inputs and daily attribution. It does
not establish executable fills, strategy profitability or fresh qualification.
The root helper inventory predates the source freeze commit and is retained as
preliminary metadata, not represented as a successful final helper report.

Remaining: reject both additions; unchanged 2023 exam after verified acquisition;
input repair, real cost evidence and prospective paper evaluation for any
surviving candidate. Any new debit-spread study needs a separate frozen plan
and lifecycle adapter. No deployment or real-money action is part of this work.
