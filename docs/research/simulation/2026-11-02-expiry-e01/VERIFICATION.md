# E01 verification and limits

Use the Dev `python-engine/winvenv/Scripts/python.exe` (Python 3.11.9). This is
focused validation of expiry/config/isolation/cost changes, not a claim that the
entire engine suite or any live trading test was run for E01.

| Check | Actual result |
|---|---|
| Historical source controls | 8 sessions, 95 position legs; money/events exact after the explicitly declared old DEFAULT 0 column adaptation |
| Pre-change native expiry tests | 63 passed |
| Frozen research tests `test_e01.py` | 11 passed |
| Affected suite: expiry, E01, F&O isolation, cost schedules | 95 passed in 205.44s before final paired-term validation |
| Final E01 and existing paired/summary regressions | 28 passed, 59 deselected in 12.79s; includes all 24 E01 cases after final binding changes |
| Original strategy research | All 80 declared cases finished; 72 new executions 156.92s, exit 0 |
| Initial native integration | 16 ordinary/adverse comparisons, 14 paired entries; all pass |
| Saved-admission binding hardening | 16 comparisons, 14 paired entries; all pass |
| Final immutable paired-term hardening | 16 comparisons, 14 paired entries; all pass |
| Independent final audit | 128 research/integration cases, 506 primary/E01 position legs, 974 price/depth checks, 426 budget checks; pass |
| Auction observations in audit | 122 remain execution-unverified; 852 continuous observations checked |
| Native result invariants | Every main A/B/C outcome unchanged, CE01 equals frozen candidate C, no additional provider call |
| Code atlas | Regenerated; 292 Python modules indexed |

Commands (PowerShell, from Dev):

```powershell
& .\python-engine\winvenv\Scripts\python.exe -m pytest python-engine/tests/test_expiry_paper.py python-engine/tests/test_expiry_e01.py python-engine/tests/test_fno_isolation.py python-engine/tests/test_cost_schedules.py -q
& .\python-engine\winvenv\Scripts\python.exe -m pytest python-engine/tests/test_expiry_e01.py python-engine/tests/test_expiry_paper.py -q -k 'e01 or paired or summary'
& .\python-engine\winvenv\Scripts\python.exe docs/research/simulation/2026-11-02-expiry-e01/audit.py
& .\python-engine\winvenv\Scripts\python.exe scripts/build_system_code_atlas.py
```

`verify_native.py` ran the final 16 comparisons offline. Existing case names
are immutable; do not rerun it over its own output or weaken the overwrite
guard. For a new engineering change, preserve old cases and select a new
explicit label/receipt. The 48 integration executions test successive versions
of the same frozen strategy; they are not 48 independent observations or a new
parameter search. Two failed preflight replay attempts are separately retained.

Raw logs and scratch databases are private under `_local/`. The comprehensive
test process output was not recoverable after a context/tool-output truncation;
no result was invented. A captured affected-suite run produced the 95-pass
receipt above. A final changed binding path then received its own 28-pass run
and complete 16-case native financial/quote-call parity.

Research freeze: cbbdebb, 696 exact archived source/config entries and 30 inputs.
Scores: c6537c6. The final app's source changes are intentional and separately
verified. The strict research working-tree freeze is **not** claimed to match
the integrated application. Final fixed-SHA skill packaging verifies the old
full hash tree plus actual data, then binds the final integrated checkout. It
is post-run consistency, not new preregistration or proof of financial truth.

The first final-packaging attempt at handoff 7747344 exited 1 before copying
study files: it passed a relative Git filename to `relative_to` with an absolute
base. The exporter/strategy/candidate inputs and scores were unaffected. The
failed packet is preserved as `_local/evidence-report-failed-path/`; the tool
now resolves the repository path before making it study-relative. Its actual
successful receipt must be read from the fresh final packet, not assumed from
the presence of an initialized folder.

Production was checked read-only: d52642f5cbc973646a1bd9f8a1e207014d2985ee;
engine running with unchanged start 2026-11-02T03:29:35.254673416Z. No restart,
deployment, `.env`, capital, real-order, N11 or Production write. The source
snapshot used SQLite online backup from a read-only volume in a disposable
network-disabled, capped container, writing only Dev.

Limits: eight seen correlated sessions, retained gaps, legacy October 6 clocks,
reconstructed eligible catalogue rather than a full dated master, unverified
auction execution, assumed sampled-index settlement, no broker fill proof,
no finite shared account and no multiyear same-day expiry option history.
Neither tests nor the financial audit proves profitability. The unchanged
best-session exclusion still loses Rs 2,685.57 under E01.
