# EN41–EN55 (Nov 18, 2026): ten auditor slots plus five of mine

| File | What it is |
|---|---|
| `PLAN5.md` | The plan, frozen at `4376ba80` before any score |
| `en_lab5.py` | Builds on the immutable round-4 lab through four dispatchers that stay inert when off; the straddle loop; the walk-forward ridge models |
| `en_score5.py` | Scored once: `results5.json`, `anatomy5.json`, `results5-started.json` |
| `render5.py` | Renders `ANATOMY5-tables.md` |
| `ANATOMY5.md` | The write-up: where each slot won and lost |
| `FORWARD5.md` | EN55's registered forward test |
| `PLAN5B.md`, `tr01.py`, `en5b.py` | Round 5b: EN41/EN42 on exported TR01 packets plus the Q28 resting-bid fill check, frozen `8737707a`, scored once into `results5b.json` |

**Verification** (`python en_lab5.py`, counts only):
- results4 reproduced through the dispatchers for E032, EN40, EN35_diag, EN32, EN28 and EN36, on 5 books × 3 fill levels;
- ridge sufficient statistics equal a direct fit, including session-block weights;
- the auditor's retention example;
- straddle target, stop, leg-out and cheapness refusal on synthetic tapes;
- 285 decisions unchanged when every later bar is erased.

**The selftest:** `python en_score5.py selftest` passes.

**Result:** nothing passes.
- EN41, EN42 and EN43 are DATA_UNAVAILABLE. EN48 and EN49 are INCONCLUSIVE; EN49 abstained everywhere.
- EN44, EN45, EN46, EN47, EN51, EN52, EN53 and EN54 FAIL. EN50 is INCONCLUSIVE.
- EN55, the learned E03.2, is FORWARD-ONLY. It is the only version whose continuous NIFTY wallet never halts: +3,445, against E03.2's −4,123 with a halt from Jan 18, 2024.
- Holm-adjusted p = 1.0 for every primary.

**State:** Dev research only. No engine, configuration, `.env` or Production change.

**Round 5b:**
- EN41 fired twice on the one eligible session and lost both; EN42 never fired. Both are INCONCLUSIVE.
- Order flow on 1-second snapshots shows no continuation.
- Q28: resting bids fill 72% within 10 s and 89% within 60 s; the minute-candle proxy agrees on 97.5% of orders; fills are adversely selected (−2.1% after a fill against +17.6% after a miss).
