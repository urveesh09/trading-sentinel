# SN131–SN140: the Smart Sentinel, phase D (Nov 13, 2026)

**Owner:** "I don't need rule-based or filtering systems. I need that smart Sentinel."

**What was built:** a learning system with no hand-written entry rule.
- **Inputs:** every minute of every sealed session (234,472 decisions, 2023 – Oct 28 2026), 44 measurements of the market.
- **Learning:** LightGBM models learn what buying the ATM call or put for 5 / 15 / 30 / 60 minutes is worth after real costs (ask in, bid out, Zerodha charges, ₹205 per lot).
- **Re-training:** every quarter on the past only (walk-forward, so 2024–2026 are true out-of-sample predictions).
- **Acting:** only when the learned expectation beats its own threshold, chosen inside the training window.
- **Further learners:**
  - a learned exit;
  - a learner on top of big-move events;
  - a monthly adaptive learner and an ensemble;
  - confidence sizing;
  - a 1-second learner (Apr–Nov 2026 seconds);
  - an order-book learner (real 5-level quotes).

**How it was tested:**
- Frozen at `1df2dd70` before any scoring. Numbers are in `results-*.json`.
- Research venv `C:\Users\Urveesh\sentinel-ml-venv` (numpy 1.26.4 = engine, scikit-learn 1.5.2, LightGBM 4.5.0).
- **One deviation:** SN136's test had 6 days, not 15. 9 of the archive's 40 days are NIFTY expiry days, which the frozen code skips.

**The answer:** the learners, left to themselves, decide that on NIFTY options at this resolution almost no moment is worth buying after costs. When they do trade, they do no better than random, and no better than a model trained on scrambled labels.

| SN | What | Result (2024–26, out of sample) | Verdict |
|---|---|---|---|
| 131 | Is there anything to learn? | Rank correlation of forecast vs realised net, per target: CE5 +0.014, CE15 −0.004, CE30 −0.015, CE60 −0.024, PE5 **+0.032** (+0.02 / +0.04 / +0.04 by year), PE15 +0.003, PE30 −0.009, PE60 −0.016. The **top 1%** of forecasts still lose ₹76–436 a trade (average trade ≈ −₹300) | Almost nothing |
| 132 | The learned policy (₹15k) | **−₹1,71,175**: 2024 −₹1,22,502, 2025 −₹56,799, **2026 +₹8,126** (654 trades). Random 95th −₹1,27,613 | NOT PROVEN |
| 133 | Learned exit | −₹1,97,988 vs fixed −₹1,71,175 (better only in 2026) | No |
| 134 | Learning which big moves to take | All 3,506 events −₹6,30,994; the learner takes 101: −₹8,270 (random 95th −₹6,747) | It learns to abstain |
| 135 | 1-second learner (train Apr–Jul, test Jul–Nov) | No validation threshold paid; 12 test trades −₹6,945 (random −₹3,299) | Nothing |
| 136 | Order-book learner (real depth) | No validation threshold paid; no test trades | Nothing |
| 137 | Adaptive (monthly, recent-weighted) | −₹3,12,558, every year negative | Worse: chases noise |
| 138 | Ensemble | −₹1,66,969 | No |
| 139 | Confidence sizing (₹30k) | Base −₹2,20,951 sized vs −₹2,17,139 one lot | Sizing amplifies losses |
| 140 | Honesty checks | ₹400: −₹2,97,212; 1 minute late −₹2,00,189; 3 of 12 quarters positive. **Shuffled-label control: −₹216 a trade vs the real learner's −₹262** | The learner's trades are no better than noise |

## What it teaches

1. **Learning confirms the friction wall.** With every measurement we hold, the expected value of buying a NIFTY option for 5–60 minutes sits ~₹300 below zero, about its cost, in every decile of the forecast. Smarter selection moves the mean only a few rupees.
2. **The one learnable signal is the 5-minute put:** small, consistent in every year, and far too small to pay costs.
3. **Data hunger, a hint:** 2026 is the only year in which every forecast correlation is positive and the policy made money; it is the year with the most history behind it. SN141 tests this.
4. **Faster data (1-second, order book) does not reveal hidden edges** in what we have: index plus the opening-ATM strike at 1 second, minute snapshots of depth.
