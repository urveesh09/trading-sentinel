# EN71–EN85 (Nov 18, 2026): the auditor's ten slots plus five of mine

**State:** research only, in Dev. There is no engine, configuration, `.env`, scheduler or Production change. EN55's registered forward comparison and E03.2 on paper are unchanged.

**Result, on seen sessions (a development screen):** no strategy qualifies; all 19 testable Holm-adjusted p-values are 1.0.

| Verdict | Cells |
|---|---|
| PROTECTION-LIKE | NIFTY EN72, EN81 and EN84 (none is new alpha) |
| FAIL | EN73 (both indices); EN75 (both); EN76 (NIFTY); EN83 (NIFTY) |
| INCONCLUSIVE (support) | EN78, EN79, EN82; the SENSEX cells of EN72, EN76, EN81 and EN84 |
| DATA UNAVAILABLE | EN74, EN77, and EN83 on SENSEX |

The one new lead is that option-market flow (EN75, EN83) picks the side better than chance on NIFTY, but not enough to pay.

## Files

| File | What it is |
|---|---|
| `PLAN7.md` | The plan, frozen at `47a29999` before any score |
| `en_lab7.py` | `run_day7`, a hooked copy of the frozen `run_day6` (equal on 24,180 arm-days); the matched envelope; the arms |
| `prep7.py` | Causal setups: EN73 ridge, EN75 synthetic forward, EN78 basis, EN83 OI, and the N11 mapping and gates |
| `fut7.py` | All-session index and front-future minutes, read-only from Breeze |
| `n11x.py` | The pinned Production N11 dispatcher (`55b5e942`) in an isolated process |
| `frontier7.py` | EN71's canonical decision table, ceilings and synthetic predictors |
| `alloc7.py` | EN79's selector and EN80's shared wallet |
| `pk7.py` | Fill estimator v2 (the EN58 erratum), packet pilots and pre-registration facts |
| `check7.py` | Parity, causality, mechanics and known-signal checks |
| `score7.py` | Selftest, freeze, the single score |
| `fwd7.py` | EN85: the forward cohort machine |
| `registration/` | One registration per slot, written by the freeze |
| `results7.json`, `anatomy7.json` | The score |
| `ANATOMY7.md`, `ANATOMY7-tables.md` | The write-up and all tables (`render7.py`) |
| `post7.py` → `post7-fixes.json` | Post-score reporting fixes: EN82's SENSEX gate routing, EN71's paired-side share per session, the EN75/EN83 overlap |
| `fwd-dryrun.json` | EN85's dry run and idempotence receipt |
| `erratum-en58-v2.json`, `facts7.json`, `n11-days.json`, `n11-signals.json` | Bound inputs |

## Commands

Run everything with `C:\Users\Urveesh\sentinel-ml-venv\Scripts\python.exe -B` (`-I` for `n11x.py`).

| Command | What it does |
|---|---|
| `pk7.py` | Estimator v2 and the EN58 erratum |
| `check7.py` | Parity, causality, mechanics and known-signal checks |
| `score7.py selftest` | The whole pipeline on truncated books |
| `score7.py freeze` | Writes `freeze7.json` and `registration/` |
| `score7.py score` | Scores once |
| `fwd7.py status` | The forward cohort's registry, calendar and coverage |
| `fwd7.py run` | Scores each new eligible expiry once into `forward7/ledger.jsonl` (needs the Breeze downloads in request 7) |
| `fwd7.py dryrun` | The rehearsal on historical sessions |

## How the score was run

The background shell running the score was reaped by Claude Code under system memory pressure after about 260 s. The Python process itself kept running and finished normally: `results7.json` was written at 15:21 with its STATUS line. It was not restarted, and nothing was scored twice.
