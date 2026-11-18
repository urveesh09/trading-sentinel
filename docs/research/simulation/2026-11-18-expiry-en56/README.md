# EN56–EN70 (Nov 18, 2026): the auditor's ten slots plus five of mine

| File | What it is |
|---|---|
| `PLAN6.md` | The plan, frozen before any score |
| `en_lab6.py` | `run_day6`, a hooked copy of the immutable `run_day4`, proven equal on 15,600 arm-days; new setups (EN60/62/64), EN63's contract, EN65's bank and child, the pair engine (EN59), the EN56 library, EN69's decomposition |
| `en_ml6.py` | EN61: observable candidates, aligned labels, the shallow boosting model, ridge controls |
| `pk6.py` | Recorder packets: EN70's minute builder and parity, EN58's entry policies, EN56 on depth |
| `en_score6.py` | Selftest, freeze, start receipt, the single score and verdicts |

**Run with** `C:\Users\Urveesh\sentinel-ml-venv\Scripts\python.exe` (scikit-learn 1.5.2, numpy 1.26.4).

| Command | What it does |
|---|---|
| `python en_lab6.py` | Parity, causal and mechanical checks, then counts |
| `python en_score6.py selftest` | Runs the whole pipeline on truncated books |
| `python en_score6.py freeze` | Writes `freeze6.json` |
| `python en_score6.py score` | Scores once |

**State:** Dev research only. No engine, configuration, `.env` or Production change. EN55's forward test is untouched.
