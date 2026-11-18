# EN56–EN70 (Nov 18, 2026): the auditor's ten slots plus five of mine

> **Erratum (Nov 18, published before round 7):** [`ERRATA-20261118b.md`](ERRATA-20261118b.md).
> - **F1.** EN58's price-through estimator accepted pre-arrival last trades. It is repaired as version 2 in round 7's `pk7.py`, reported as lower, queue and upper bounds. Nov 17's fill counts and conclusion are unchanged.
> - **F2.** The 49.5% "direction right" figure was 50% by construction.
> - **F3.** Live paper cannot confirm queue fills.
> - **F4.** EN60, EN61, EN68, EN69 and EN70 now carry narrower statements.
> - Original results are unchanged.

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

**Scored once** (`results6.json`, `anatomy6.json`, `results6-started.json`). The write-up is `ANATOMY6.md`; the tables are `ANATOMY6-tables.md` (rendered by `render6.py`). After the score, `post6_en58.py` → `post6-en58.json` is a reporting fix only: the same frozen code, with missing quotes skipped in EN58's markouts.

**Result: no strategy passes; all 18 Holm-adjusted p = 1.0.**

| Verdict | Slots |
|---|---|
| FAIL | EN60, EN61 (NIFTY), EN62 (NIFTY), EN63 (NIFTY), EN64 (NIFTY), EN67 |
| INCONCLUSIVE | EN58, EN59, EN65, and SENSEX for EN61–EN64 |
| ANSWERED | EN56, EN57, EN66, EN68, EN69 |
| PARITY NOT ESTABLISHED | EN70 |

**Main lessons:**
- **Hindsight shows opportunity on almost every expiry:** ≥ Rs 1,250 available on 181 of 197 NIFTY afternoons. But the average decision loses.
- **More activity loses money:** Rs 149 per added EN55 ticket.
- **EN55's wallet survival:** it comes from the half-first scout, and depends on minute-bar resting fills that real depth shows are adversely selected.
- **The put edge** is the index move on a few days, not volatility.
