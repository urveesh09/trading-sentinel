# SN19–SN30 (Nov 12, 2026): SN Gold and twelve new perspectives, each at every wallet

`gold.py` is the harness. Every variant is scored at:
- **A:** ₹15k, 1 lot;
- **B:** ₹20k, 1 lot;
- **C:** ₹30k, second lot on high-volatility days;
- **growth from ₹15k:** stopped after 0, 2, 3 or 5 steps.

Per year it reports profit, refills, days won/lost/none and the worst day. Selection: chosen on three years and scored on the fourth, per wallet. Costs: current Zerodha charges + ₹205 per lot per trade, 20% day limit. Everything is in-sample for the entries (N11). The benchmark and SN Gold reproduce SN16 exactly.

**SN Gold (start):**
- N11's entries and exits;
- a winner up ≥ 25% at N11's exit is kept with a 3-ATR index trail;
- lots = floor(W / 15k), halved on low-volatility days;
- grow from ₹15k, stop after step 3.

| SN | Idea (new perspective) | Result (four years, G3 unless noted) | What it taught | Kept |
|---|---|---|---|---|
| 19 | Strike by setup (ITM/OTM per strategy) | ITM wins held out at B (all 4 folds) and C (all 4); hurts A (unaffordable) | The strike depends on the money per lot | → 19b |
| 19b | **One strike ITM when the wallet can pay** | A +₹1,26,373, B +₹1,37,156, C +₹2,33,031, G3 +₹2,65,466; held-out pick in every fold for A/B/C | More delta, less decay, when affordable | **Yes (v2)** |
| 20 | Second chance after a losing N11 trade | G3 about +₹1.25 lakh | A failed setup that comes back is a trap | No |
| 21 | Second lot by time of day | Worse than volatility; afternoon second lots are bad | – | No |
| 22 | Second lot by the strategy's recent form | Worse | Past wins don't predict the next trade | No |
| 23 | Second lot by the opening gap | Clearly worse | – | No |
| 24 | Insurance: buy the opposite option | Profit almost gone | Insurance costs more than it saves | No |
| 25 | Debit spreads | Losses at ₹15–20k | Capping the winners kills N11's edge | No |
| 26 | Reality: +₹300 / +₹400 stress, entries 1 minute late | v3 G3 +₹2,71,472 / +₹2,43,561 / +₹3,05,172; positive at every wallet | The gains survive realistic friction | – |
| 27 | Scale-out (sell one lot early) | Worse at C and G | Same lesson as SN11 | No |
| 28 | **Scale-in: add a lot at +10% while the whole position fits the day limit** | G3 +₹3,25,635 (held-out pick in all 4 folds); not reliably better at fixed wallets | Pressing winners helps a growing wallet | **Yes (v3, growth)** |
| 29 | v3 with all lots every day | G3 +₹3,41,758, same worst day; not reliably better held out | – | Optional, aggressive |
| 30 | Final package and forward freeze | Below | – | – |

**Fix found on the way:** the first scale-in let the added lot push a day past the 20% limit (B −₹5,761). It is now refused unless the whole position's stop fits the day's room.

## SN Gold v3, by year: profit / refilled

Rules: SN Gold + ITM when it fits + scale-in at +10%.

| Wallet | 2023 | 2024 | 2025 | 2026 | Total | Refilled | Won/lost/none | Worst day |
|---|---|---|---|---|---:|---:|---|---:|
| A ₹15k | −8,430 / 23,354 | 47,279 / 15,931 | 41,587 / 36,226 | 50,094 / 22,468 | 1,30,530 | 97,979 | 55/63/624 | −2,998 |
| B ₹20k | −22,981 / 33,526 | 61,097 / 13,420 | 43,485 / 48,895 | 56,516 / 31,135 | 1,38,117 | 1,26,976 | 59/70/613 | −3,995 |
| C ₹30k | −24,372 / 45,199 | 92,613 / 25,140 | 60,149 / 64,155 | 99,658 / 47,407 | 2,28,048 | 1,81,901 | 56/73/613 | −5,994 |
| Grow, stop after 2 | −8,430 / 23,354 | 67,869 / 18,631 | 74,508 / 67,802 | 1,09,920 / 51,602 | 2,43,867 | 1,61,389 | 58/71/613 | −6,740 |
| **Grow, stop after 3 (Gold)** | −8,430 / 23,354 | 67,869 / 18,631 | 90,898 / 93,811 | 1,75,298 / 76,425 | **3,25,635** | 2,12,221 | 58/71/613 | −10,119 |
| Grow, stop after 5 | −8,430 / 23,354 | 67,869 / 18,631 | 1,01,327 / 1,32,049 | 3,80,859 / 1,88,187 | 5,41,625 | 3,62,221 | 58/71/613 | −22,740 |

**Caveats:**
- 2023 is worse with v3 at B and C. The ITM strike and scale-in gain in 2024–2026.
- At the fixed wallets the held-out best is v2 (A +₹1,26,373, B +₹1,37,156, C +₹2,33,031).
- Forward check: `FORWARD.md`.
