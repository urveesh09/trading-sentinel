# F&O successor handover — November 2, 2026

> **Update, November 2 night.** On the owner's order N11T is deployed on paper, and the paper book has a fresh Rs 2,50,000 from Nov 3 (`FNO_PAPER_BOOK_START`, `python-engine/fno_book_start.py`). Every old trade is kept. Where this document says N11T is Dev-only or the book is at 0.25x, read that as history.

This is the inheritance document for **regular F&O, through N11/N11T**. The
separate [expiry handover](EXPIRY_SUCCESSOR_HANDOVER_2026-11-02.md) covers
expiry-v3, E01, the new September data and unfinished E01.1 work. Do not treat
regular F&O results as evidence for the expiry module.

## 1. Read this first

The owner wants a trader that can choose suitable entries, manage winners and
exit intelligently. They welcome lower losses and higher profits, but do not
want endless rejection filters or a historical winner presented as proven.
Preserve cash funding, bounded exposure, truthful evidence and explicit
real-money authorization. Paper improvements are not authority to enable or
enlarge a real-money experiment.

The immediate request that produced this document was **handover only**.
No strategy, setting, data download, order, service restart or deployment was
performed while writing it. Further research was stopped at that boundary.

| Item | State at handover |
|---|---|
| Dev checkout | `C:/Users/Urveesh/Desktop/trading-sentinel` |
| Branch | `codex/production-correction-hedge-p0` |
| Reviewed Dev source | `7711521f14cd0f044b9d2c68c9f33d8f6c4c841e` |
| Production checkout | `C:/Users/Urveesh/Desktop/Production_Trading-sentinel` |
| Production Git HEAD, read-only recheck | `d52642f5cbc973646a1bd9f8a1e207014d2985ee` |
| Engine, read-only recheck | Running; started `2026-11-02T03:29:35.254673416Z` |
| Regular F&O main book | N11 deployed **on paper**, per deployment record |
| N11T tolerance | Built and pushed in Dev; not in the Production HEAD above |
| Real-money switch | Last recorded off; source default is false. This handover did not reread runtime secrets/config or authorize enabling it |

The Git and container-state checks do not independently prove the running
image's source identity. Consult the release receipt/runtime identity before
claiming a future deployment is verified. All runtime observations are dated,
not a promise about the next session.

Read `AGENTS.md`, [system guide](SYSTEM_GUIDE.md), [atlas](SYSTEM_CODE_ATLAS.md),
[active plan](NEXT_AGENT_PLAN.md) and [checklist](HANDOVER_CHECKLIST.md) before
resuming. These documents contain chronological snapshots; newer deployment
entries supersede older statements such as "N11 is research only."

## 2. The authoritative reading order

1. [N11 report](FNO_RESEARCH_N11.md), then
   [N11T report](FNO_RESEARCH_N11T.md). The latter includes the current Production
   paper-equity problem and the final Rs 6,250 rule.
2. [Year-data testing method](FNO_YEAR_DATA_TESTING_METHOD.md),
   [general research rules](RESEARCH_TESTING_METHOD.md), and
   [archive-quote playbook](FNO_STRATEGY_TESTING_PLAYBOOK.md).
3. [N11 research directory](research/simulation/2026-11-02-fno-n11/README.md):
   plan, freeze, exact rules, annual results, independent audits, engine parity,
   failures and the prewritten 2022 exam.
4. [N11T final plan](research/simulation/2026-11-02-fno-n11-tolerance/PLAN_FINAL.md),
   `freeze-final.json`, `results-final.json`, `parity-final-2023.json` through
   `parity-final-2026.json`, and `audit-final-*.json` in that directory.
5. Earlier comparisons only when needed:
   [N08](FNO_RESEARCH_N08.md), [N09](FNO_RESEARCH_N09.md),
   [N09.1](FNO_RESEARCH_N091.md), [N10](FNO_RESEARCH_N10.md),
   [N10.1](FNO_RESEARCH_N101.md), and the
   [Oct 29–30 history](FNO_RESEARCH_2026-10-30_SUMMARY.md).

## 3. What is actually implemented

### N11 main paper book

`python-engine/fno_book.py::n11_signal` routes by yesterday's NIFTY ADX, using
closed-bar information. At ADX at least 30, it uses SHIPPED, OR20, EFF with its
retest, and TPB. On low-trend days it uses only the put pullback, with no new
such entry from 14:00. The stretched-entry check remains. EFF/OR20 use their
2-ATR trails; stalled losing EFF options have the shorter soft clock.

`python-engine/fno_n11.py` adds:

- Two entry lots only when volatility is at or above its usual level, subject
  to the existing planner and other sizing/capital restrictions. Low-trend
  two-lot entries also have the morning clock.
- One lot after a realized loss that day. This changes size rather than
  refusing that individual signal.
- Stand-aside only when volatility is below 0.9 of usual **and** the last 20
  one-lot paper outcomes sum to zero or less. The independent paper record
  continues, so eligibility can recover without live trades.
- An earned third lot, `N11_ADD`, as a separate paper position after a
  qualifying two-lot parent reaches the required gain. Parent loss at its
  existing stop plus the child's full planned backstop exposure must fit the
  Rs 5,000 budget. It never tightens the parent's stop to manufacture room.

The N11 deployment adds `fno_n11_paper` and `fno_n11_gate`; the initial paper
history was seeded with 22 research outcomes through October 23. This is a
declared seed, not 22 fresh prospective trades. Source default `FNO_BOOK=N11`.
Rollback mode is `FNO_BOOK=UNION_ADX`, while existing N11 positions keep exits.

### N11T optional second lot

Code **9931c15**, documentation **6d6caf7**, both ancestors of reviewed Dev HEAD.
This is the final **Rs 6,250 / stop factor 1.75** version, not the earlier
Rs 7,500 study. `FNO_N11_TOLERANCE_ENABLED` defaults true in Dev.

A NIFTY paper entry that N11 already admits at one lot may become two only
when the N11 ceiling permits it, the last 20 paper trades are profitable, and
the declared native-backstop or structural-stop funding condition passes.
Fees and declared stress are inside the tolerance's limit. The limit shrinks
with drawdown stance, and open-premium/structural caps still apply. It does
not admit a new signal or give three lots at entry. Reservation failure at two
falls back to the original one-lot request.

Important integration points: `second_lot`, `second_lot_stop`,
`record_second_lot`, and `send_shadow_report_once` in `fno_n11.py`, plus the
entry path in `fno_engine.py`. Evidence table: `fno_n11_second_lot`.
Disable new tolerance use with `FNO_N11_TOLERANCE_ENABLED=false` through an
authorized deployment/config workflow; preserve management of open positions.

SENSEX is outside this tolerance's tested scope. A real-money mirror still
buys one lot with its own stop. Indirectly, an extra paper lot can occupy
premium room and prevent a later paper admission that real money would have
copied. Include that admission feedback in comparisons.

## 4. Results to retain, with their meaning

Fresh Rs 250,000 at the beginning of **each** year; costs included; 2026 ends
October 28. These are modeled research results on already studied years.

| Version | 2023 | 2024 | 2025 | 2026 | Sum of annual profits | Worst day | Largest yearly drawdown |
|---|---:|---:|---:|---:|---:|---:|---:|
| N08 | -37,581 | 76,294 | 58,647 | 104,924 | 202,284 | -9,720 | 15.08% |
| N09.1 | -32,684 | 76,294 | 46,738 | 99,870 | 190,218 | -6,127 | 13.13% |
| N10 retry | -32,898 | 88,805 | 51,583 | 125,786 | 233,275 | -6,127 | 13.21% |
| N11 | -11,537 | 93,256 | 53,095 | 120,551 | 255,365 | -5,641 | 6.89% |
| N11T final | -11,537 | 95,040 | 63,479 | 127,763 | 274,745 | -5,641 | 6.89% |

N11 is the current paper reference. N11T is a promising unqualified sizing
candidate. N08 remains a useful simpler reference. None is a proven future
winner. N11's advantage over N10 is essentially the 2023 improvement;
2024–26 totals are 266,902 versus 266,174. Every version still loses in 2023.

The one-continuous-account endings are separate experiments: N11 Rs 518,305;
N11T Rs 522,297. Never obtain these by adding independently reset annual
profits. N09.1's Rs 384,310 is unstable: rupee-sized cost changes can leave it
stuck near Rs 217,000 instead. Funding eligibility created an account cliff.

Research limitations that must survive every new report:

- All 2023–26 years have been used for selection. Relabeling a later variant
  does not make them held out again.
- N11's close-variant overfitting estimate failed its fixed 0.5 bar at 0.893.
  Its stand-aside improvement depends heavily on 2023; without that year it
  would not have been selected. Nearby volatility thresholds can miss recovery.
- N11T's estimate is 0.615 over 55 books. Its 9.7% random-selection result is
  post-selection and is **not** independent proof. Three trades contribute
  Rs 18,633 of Rs 22,228 in extra-lot earnings; six of eleven extra-lot
  trades are in January 2025. Net improvement is Rs 19,380 after feedback.
- N10's retry was absent from its original written plan; N10.1 exposed
  understated option risk in its proxy. Keep both failures on record.
- N10.1 WATCH_FLAT and PREMIUM_LOCK did not establish economic superiority.
  Do not revive the floor-release mechanism merely because it enables trades.

## 5. Data, models and reproducibility

The sealed regular-F&O datasets are listed in section 2 of
[FNO_YEAR_DATA_TESTING_METHOD.md](FNO_YEAR_DATA_TESTING_METHOD.md). Local roots:

| Year | Repository-relative private dataset |
|---|---|
| 2026 | `docs/research/fno/2026-10-29-year-genome/_local/dataset-nifty` |
| 2025 | `docs/research/fno/2026-10-30-nifty-2025-test/_local/dataset-nifty-2025` |
| 2024 | `docs/research/fno/2026-10-30-day-router/_local/dataset-nifty-2024` |
| 2023 | `docs/research/simulation/2026-11-01-fno-n08/_local/dataset-nifty-2023` |

These use minute observations and an explicitly modeled bid/ask spread. The
overlap comparison found candles about Rs 100–200 per trade per lot better
than archived quotes. Keep the declared extra cost and doubled-cost stress.
The current-lot normalization is 65 units across years; these are current-rule
counterfactuals, not literal historic broker-contract statements.

The regular exports deliberately lack same-day-expiry options. Separate expiry
downloads do not retroactively change a sealed regular-F&O dataset. Preserve
the documented half-days, unavailable candles and UNRESOLVED outcomes; do not
fill gaps, invent marks or silently repair source rows.

2022 has not been used by this work. The owner said they will download it
later. Keep the prewritten N10/N11 exam sheets; freeze a separate N11T supplement
before reading its prices. Availability is not guaranteed. Do not spend API
allowance or download on the strength of this handover alone.

Use the `sentinel-trading-simulation` skill for replays and the relevant guarded
download skill for acquisition. Never bypass writer locks, call ledgers or
owner-only login. Never copy secrets, account data or whole operational ledgers
into research. Research uses sealed selected evidence, not a changing shared DB.

## 6. Production capital mismatch and real-money boundaries

The latest **reported** paper-capital read, November 2 about 14:15 IST, was
equity Rs 216,156, with Rs 33,844 cumulative losses since July, a 0.25x stance
and only about Rs 3,656 above the fixed Rs 212,500 floor. Most losses predate
N11. Three first-day one-lot signals lost about Rs 4,298; the two-loss rule
halted entries at 12:32. These are historical observations from the N11T
report, not a new end-of-day account reconciliation by this handover.

At quarter stance, N11T's nominal limit is only Rs 1,562.50. Research starts
with fresh full-size accounts, so it does **not** describe this deployed book's
starting conditions. Under the floor paper cannot trade back, and a real-money
mirror dependent on fresh paper admissions would also stop receiving entries.

A fresh paper start was suggested but **not built or authorized as an action
in this handover**. Preserve old history. Any reset must have an explicit new
run identity, accounting boundary and the owner's decision; never delete losses
or silently move the 15% floor. The fixed floor also protects a smaller fraction
of equity as a winning account grows. That unresolved policy trade-off is not
permission to change it.

Real-money implementation is separate: `fno_live_test.py`,
`fno_live_preflight.py`, `fno_proving_week.py`, and
[live-test runbook](runbooks/fno-live-test.md). Source defaults include switch
off, capital Rs 12,500 and Nov 2–6 window. Earlier discussion mentioned
Rs 15,000; do not assume that suggestion became effective configuration.
Persisted run limits and fixed dates matter. Never run `--test-order` during
research: even its preflight order is real. An open live position must retain
exit management when new entries are disabled.

Cash-funded long options avoid an uncovered short-option margin liability,
but an option can lose its entire paid premium plus costs. A stop or account
halt is not a guarantee against gaps, non-fills, outages or larger realized
drawdown. Do not say a bad market cannot consume all allocated trading cash.

## 7. Checks already performed versus checks still required

Recorded previous verification, not rerun for this documentation-only task:

- N11 engine/research parity: 188,455 ticks, 1,505 signal ticks and 696 lot
  ceilings; zero mismatches. The 460 stand-aside ticks intentionally refuse
  later in the entry path. This does not prove every earned-lot lifecycle.
- N11T final parity: 696 decisions, all nine tolerance backstops, zero
  mismatches; annual nets agree with the frozen panel. Independent annual
  financial audits and focused entry-path tests are in the study.
- Deployment verification for N11 was recorded by the deploying agent. Its
  after-hours data backup was not taken; do not invent a backup receipt.

Useful focused checks after an actual code change, from Dev:

```powershell
& .\python-engine\winvenv\Scripts\python.exe -m pytest python-engine/tests/test_fno_book.py python-engine/tests/test_fno_n11.py python-engine/tests/test_fno_n11_second_lot.py -q
```

Do not run old research scripts blindly: some write fixed result filenames,
depend on archived source, environment-selected years and private datasets.
Inspect guards, freeze and output identity; use a new labeled output for a new
experiment. Software parity is not evidence of profitability.

## 8. Concrete next-agent queue

1. Revalidate checkout, running-image identity, current paper equity/floor,
   stance, open legs and last signal evidence read-only. Separate new facts
   from the dated observations above.
2. Await the owner's capital/reset and deployment decisions. N11T/E01 have
   not been deployed by this work. Do not turn research into real-order
   authority or bundle an unrequested capital change into a release.
3. After an authorized N11T deployment, verify the first genuine qualifying
   second lot, stop, reservation fallback and `fno_n11_second_lot` record.
   Reconcile the evening comparison against actual position/cash lifecycle.
4. Build a genuinely comparable forward N08/N10/N11 shadow if requested.
   The current daily shadow line is **size-only**: it does not implement each
   counterfactual reserve, floor, earned lot and resulting admission feedback.
5. Run the predeclared 2022 exam when acquisition is separately authorized and
   complete. Missing or unexercised mechanisms mean unavailable/not tested.
6. Prefer new forward evidence and operational corrections to another genome
   search on 2023–26. New hypotheses need a small explicit plan, frozen
   acceptance checks and source/data/config identity before scores.

## 9. Workspace and resumption instructions

Owner changes already existed in `.gitignore`, three ritual documents and
several untracked directories. Preserve them; never bulk stage the checkout.
The untracked expiry-E02 preparation is this research session's unfinished
work, documented in the separate handover. It must not disappear in a cleanup.

Python: `python-engine/winvenv/Scripts/python.exe` (3.11.9). Production shares
the machine: respect the research method's CPU/RAM limits and never stop it to
free resources. Do all changes in Dev, promote through GitHub. Keep using the
same branch unless the owner changes that instruction.

This handover changes Markdown only. No atlas regeneration, migration or
application regression run is warranted. Check local document links and
`git diff --check`; preserve the owner's dirty slices. The handover commit is
discoverable with `git log -1 -- docs/FNO_SUCCESSOR_HANDOVER_2026-11-02.md`.

Handover verification completed: both documents' local Markdown links resolve;
`git diff --check` passes; the original owner diff matches the preserved
baseline. The E01 packet receipt and the four new CSVs' row counts, fixed
strikes and 3,347 missing-source-second total were checked read-only. No new
strategy score or application-suite result is claimed.

Suggested next prompt:

> Read the FNO_SUCCESSOR_HANDOVER_2026-11-02.md and the four ritual documents.
> Revalidate N11/N11T status and current paper capital without changing
> Production. Preserve all existing work. Resume only the explicitly selected
> next item; keep 2022 untouched until its separately authorized exam.
