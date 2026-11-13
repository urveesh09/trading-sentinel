# SN141–SN150: the Smart Sentinel, phase E — what would change the answer (Nov 13, 2026)

- **Frozen** at `f63a658e` (`PLAN.md`) after phase D's results, before any phase E scoring. Numbers are in `results-*.json`.
- **One post-freeze crash fix (SN144):** its first run crashed because 2023 has too few hot days to train before validating (the hot-day flag needs 60 earlier sessions). Quarters with fewer than 50 hot training days are now skipped with no trades. The crash log is kept local.

| SN | Question | Result | Verdict |
|---|---|---|---|
| 141 | Does the learner improve with more history? | Test 2026: mean correlation **+0.006 → +0.013 → +0.019** with 1 / 2 / 3 training years; policy −₹63,723 → −₹11,483 → **−₹4,572**. Test 2025: +0.017 → +0.003 (worse), policy −₹1,44,855 → −₹48,834 | Mixed: 2026 says yes, 2025 says no. By the frozen rule (every added year, both test years, ≥ 5 of 8 targets) **not established** |
| 142 | At what cost would it pay? | 2024–26 total at stress ₹0 / 50 / 100 / 150 / 205: **−₹29,503** / −₹1,61,313 / −₹1,45,039 / −₹1,29,194 / −₹1,71,175. 2026 is positive at every cost | Even free slippage does not rescue it; break-even needs fills better than the mid |
| 143 | Holding to the close as a learned action | The learner never chose it (0 trades); results identical to SN132 | Holding to the close is not learnable from these features on average |
| 144 | Hot-day specialist (learned, hot days only) | Learned **−₹18,467** (2025–26) vs SN95-L's fixed 10:00 straddle on the same hot days **+₹36,541** (2024 +₹29,842, 2025 −₹12,241, 2026 +₹18,940) | **The mechanism-based rule beats the learner** (93 hot days is too little to learn from) |
| 145 | A learned extension for Gold's trades | ₹1,19,104 vs v5's own exits ₹1,36,393 on 112 trades (worse every year) | Keep v5's exit |
| 146 | Combined account | Nothing passed. As a description, Gold ₹30k growing 2024–26 ₹8,62,989 → **₹6,91,814** with the learned sleeve | Do not add it |
| 147 | 1-second learner trained the other way (B → A) | −₹16,304 on 48 trades, worse than random (−₹13,709) | "Nothing" is stable |
| 148 | Resources | Below | – |
| 149 | Scoreboard | `results-sn149.json` | – |
| 150 | Synthesis | Below | – |

## SN148 — the resources that could change the answer, ranked

1. **Live full-chain tick capture.** Give the system the eyes a human scalper has.
   - **The gap:** your partner's entries carry a real 1-minute edge (SN122, p = 0.0015). Our 1-second archive has only the index and *one* opening-ATM strike, and the order-book archive is one snapshot a minute. The partner watches the live chain.
   - **The fix:** a Production recorder of Kite WebSocket ticks (full depth) for NIFTY and SENSEX futures and ±10 strikes of both weekly expiries, saved daily. Free with the existing Kite account; a Dev build plus a deploy on your word.
   - **Timing:** after ~3 months it gives an honest, never-seen forward set for a sub-minute learner.
2. **More history.** NIFTY minute options 2019–2021 and Jun–Dec 2022 (Jan–May 2022 stays the sealed exam).
   - **Cost:** about 4,140 Breeze requests per year (2024's download), under one day of the 4,800 daily allowance each, so ~4 days in all.
   - **Unknown:** ICICI's coverage before 2023 needs the skill's probe first (your login).
   - **Value:** SN141 is mixed, so this is a fair experiment, not a sure win.
3. **Real broker fills.** A small real-money test (Gold's own signals, 1 lot) is the only way to know true slippage.
   - **Why it matters:** SN142 shows costs decide everything. SN115 / SN117 measured paper fills at about ₹175 a lot, near our ₹205.
   - Your decision; real money.
4. **Not worth buying now:** BANKNIFTY option history (SN105 found no information), 1-minute constituents (SN96), or more NIFTY-only seconds (SN135 / SN147).

## SN150 — synthesis: why the human can sometimes, and what the Smart Sentinel did

- **The system was given full freedom:**
  - learned decisions, not rules: 234,472 minute decisions, 44 measurements, 8 actions;
  - second-level data and real order-book depth;
  - adaptive retraining, ensembles, confidence sizing and learned exits.
- **What it decided, entirely on its own:**
  - almost every gap-day moment is worth less than it costs, so it barely traded;
  - when it did trade, it did no better than chance or a model fed noise.

  That is the smart decision. A system that trades every day here would lose about ₹300 a trade, like 9 in 10 retail traders (SEBI).
- **Humans are not smarter, they are lucky and selective.**
  - Your partner's 1-minute entry edge is real.
  - But it is smaller than the cost of acting on it: per lot, their trades are about +₹80 before slippage, against ₹140–175 of measured friction.
  - The peaks you see are volatility, not kept profit. The one human habit the machine can fix is giving the peak back, and that message is built (the partner give-back stop, Dev `cba0519d`).
- **Where the system does make money, the edge has a reason behind it:**
  - Gold's entries beat 400 random versions of itself (SN119);
  - the hot-day straddle exploits volatility persistence (SN101 / SN111).

  Both are mechanism-based, and the learner did not beat either.
- **To make it smarter, give it new eyes, not more freedom:** the live full-chain tick recorder (item 1 above) is the single most valuable resource, then more history, then real fills.
