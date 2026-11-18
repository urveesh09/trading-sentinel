# Round 9 — EN96–EN110 (each slot a family of variations)

**State:**
- Research only, in Dev. No engine, configuration, `.env`, scheduler, broker or Production change.
- E03.2 on paper and EN55's forward registration are unchanged.

**Result (development screen on studied sessions):**
- No strategy qualifies and no champion is nominated.
- The chronological selection fell back to EN87 in most folds: EN87 funds only 7–10 parents per 60 sessions, below the registered floor of 10.

Read in this order:

| File | What it is |
|---|---|
| `../../../EXPIRY_RESEARCH_EN96_EN105.md` | The auditor's family specification (EN96–EN105) |
| `IMPL9.md` | Implementation plan and every pre-score resolution, including my families EN106–EN110 |
| `ANATOMY9.md` | Family-by-family results: where each won and lost, neighbours, support, next decisions |
| `COMPONENTS9.md` | Good part / harmful part / removal / interactions for every component |
| `ANATOMY9-tables.md` | Every cell, control and reference (rendered by `render9.py`) |
| `post9.json` (`post9.py`) | Labelled post-score diagnostics: exit-target transfer, EN98/EN102/EN99 explanatory receipts |

## Code

Run with `C:\Users\Urveesh\sentinel-ml-venv\Scripts\python.exe -B`.

| File | Role |
|---|---|
| `round8.py` | Imports round 8/7 read-only, network denied |
| `signals9.py` | Causal OI series (4 lookbacks, 18 baskets), thresholds, context, synthetic forward, basis, arms |
| `lab9.py` | `run_day9` (a hooked copy of `run_day8`; 15,342 arm-days identical with hooks off), choosers, continuation, damage exit, staged adds, wallets |
| `families9.py` | Grid expansion of `families9.json` + `families9-own.json`, specs, rules, builders, controls, references |
| `search9.py` | Stage B selection and EN105 composition |
| `stats9.py` | Descriptive long-group t; uncalibrated family max-t |
| `score9.py` | `selftest`, `freeze`, `score` (one shot) |
| `test9.py`, `test9_unit.py` | `parity`, `reproduce`, `causal`, `unit` |
| `verify9.py` | Post-score reconciliation (fresh-process reruns, identities, Stage B re-derivation) |
| `render9.py` | Writes `ANATOMY9-tables.md` |

## Receipts

| Stage | Files |
|---|---|
| Before the freeze | `parity9.json`, `reproduce9.json`, `causal9.json`, `unit9.json`, `selftest9.json`, `calibration9.json`, `calibration9-holm.json` |
| Freeze | `freeze9.json`, committed `99958d97` |
| Score | `results9-started.json`, `results9.json`, `anatomy9.json`, `trials9.jsonl` |
| After the score | `verification9.json` (PASS), `post9.json` |

`registration9/` is empty: no family met the frozen DEVELOPMENT CANDIDATE rule, so nothing was nominated.
