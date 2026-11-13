# SN141–SN150: the Smart Sentinel, phase E (frozen before any phase E scoring, Nov 13, 2026)

## What phase D found (`../2026-11-13-sn131`, scored so far)

- **SN131 (minute learner):** out-of-sample rank correlations −0.05 to +0.04. Even the most confident predictions lose about their costs (~₹300 a trade). The one consistent signal is the 5-minute put (+0.02 / +0.04 / +0.04 by year).
- **SN132 (policy):** −₹1,71,175 over 2024–26, no better than random. But 2026 is positive (+₹8,126), and 2026's correlations are positive for all 8 targets.
- **SN133 (learned exit):** worse overall; better in 2026.
- **SN134 (event model):** mostly abstains.
- **SN135 / SN136 (1-second, order book):** they find nothing that beats costs, so they choose not to trade.

**So the learners, on their own, conclude what Gold already does:** trade rarely. Two questions follow:
1. Does the learner get better with more history (2026 is the first year it had three years to learn from)? That decides whether the owner's offered resources (more data) can change the answer.
2. At what execution cost would it pay?

Phase E answers those, and tests the learner where phase A–C found real edges: holding to the close, hot days, Gold's own trades.

Same engine and rules as phase D (`sm.py`, fixed LightGBM parameters, executable labels, strict ₹205, nested thresholds, research venv).

## The studies

### SN141 — the learning curve (does more data help?)

| Test year | Training sets |
|---|---|
| 2026 | 2025 / 2024–25 / 2023–25 |
| 2025 | 2024 / 2023–24 |

- **Each run:** the 8 targets, rank correlation on the test year, and the policy's net (θ nested on the training window's last 125 sessions).
- **"More data helps"** if the correlation rises with every added training year in both test years, for at least 5 of 8 targets.

### SN142 — the cost curve

SN132's predictions re-simulated at stress ₹0 / 50 / 100 / 150 / 205 per lot (θ re-chosen nested under each cost). The break-even friction is where the 2024–26 net turns positive.

### SN143 — holding to the close as a learned action

New labels: the call / put bought now and sold at 15:10. With the 8 phase-D labels this gives 10 actions, all walk-forward. A close trade ends the day's trading. Policy and pass rule as SN132.

### SN144 — the hot-day specialist

- **Training data:** a walk-forward model trained only on hot-day rows from 10:00 (SN95's causal flag).
- **Actions:**
  - call / put × 15 / 30 / 60 minutes or to the close;
  - the straddle to the close (call + put labels).
- **Against:** SN95-L's fixed straddle on the same days.
- **Pass:** SN132's rule, on hot days.

### SN145 — a learned extension for Gold's trades (₹15k, 1 lot, description)

At each Gold v5 trade's N11 exit minute, hold on while the learned continuation (phase D's gross models) is positive. Compare the per-trade net against v5's own exit on identical trades; scale-ins are ignored (1-lot approximation).

### SN146 — the combined account

Gold v5 plus the best-evidenced learned gap-day policy (SN143 / SN144, whichever passed; if none, SN132 is shown as a description) at every wallet, against Gold alone.

### SN147 — the 1-second learner swapped

Train on archive B, test on archive A: is SN135's "nothing" stable in reverse?

### SN148 — what resources would change the answer

From SN141's curve, the existing download records and SN142's break-even, the exact data / execution resources ranked by expected value:
- more NIFTY option minute history;
- live second-level and depth capture;
- real broker fills.

### SN149 — the scoreboard for SN131–SN148

### SN150 — synthesis and the forward plan
