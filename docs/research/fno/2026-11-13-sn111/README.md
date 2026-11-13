# SN111–SN115 (phase B): why the one real empty-day signal works, and what latency costs (Nov 13, 2026)

Frozen at `a45b401d` (`PLAN.md`) after phase A's results and before any phase B scoring. Numbers in `results-*.json`; logs local. Strict ₹205 per leg-lot.

**One line:** the straddle signal is a genuine *volatility-persistence* effect, and the ATM straddle is already its best form. Gold's edge is a different thing (direction), so volatility filters only hurt Gold. Real latency costs about what our ₹205 stress assumes.

| SN | Question | Result | Verdict |
|---|---|---|---|
| 111 | Where does the straddle's money come from? | **Movement persists.** The rest of the day's realised ÷ implied volatility rises from 0.63 (lowest R_today decile) to **0.96** (top decile); correlation with R_today **0.47**. Implied volatility does *not* catch up (1.01–1.09 in every decile; correlation −0.10). The top decile's |move| ÷ premium is 0.53 vs 0.35. Its profit came mostly from the **put** leg (+₹1,508 vs call −₹807 a day), but the winning leg followed the morning trend only **51%** of the time. By days to expiry the top decile made +₹2,273 at 2 days and −₹478 at 3 | Description: a gamma (movement) effect, not vega, not direction |
| 112 | Is the straddle a hidden direction trade? | With-trend leg only +₹5,559, against leg +₹9,425, straddle **+₹17,145** (SN95-L days). All signal days: with-trend +₹32,098 vs straddle +₹29,271 but negative in 2023 and 2025, −₹23,211 without best 5. A random leg's 95th percentile is +₹45k / +₹61k | Not preferred: keep both legs |
| 113 | Does Gold share the mechanism? | **No.** Gold's per-lot net by R_today at entry: low third ₹1,441, middle ₹1,013, high ₹1,539 (₹15k). Skipping low-R entries cuts the net at every wallet (₹15k: 1,51,155 → 1,39,000 / 1,05,867 / 90,627; ₹30k growing 8,50,882 → 7,17,576 at the mildest setting). The held-out pick is v5 in every year at every wallet | NOT PROVEN: never filter Gold by volatility |
| 114 | A cheaper structure? | ATM straddle +₹17,145 (premium ₹11.8k); 1-step strangle +₹16,485 (₹8.9k); 2-step strangle +₹14,656 (₹6.6k); 1-step ITM pair +₹1,043 (fits only 15 days) | Not preferred: ATM stays |
| 115 | What does latency really cost? (23 Production paper entries vs real quotes) | Fill **39 s** after the signal bar closes (median; mean 52 s). Fill vs the mid when the signal was decided: **₹57 per lot** (median; mean ₹109). Exit vs mid: ₹62 (mean ₹98). The option keeps moving our way after the fill (+₹98 per lot after 1 minute, +₹185 after 5, median); scheduled 10:00 buys show no such move (+₹16 / +₹25 mean) | **₹205 is about right:** real round trip vs mid ≈ ₹120 (median) – ₹207 (mean), against the simulator's ≈ ₹235 (model spread + ₹205) |

## What phase B adds to the lessons

1. **The empty-day signal is volatility persistence.** A morning that moves more than its options price keeps moving. Options do not reprice for it, so a long straddle held to the close collects the movement. It is two-sided and works best 1–2 days before expiry.
2. **Gold is a direction book.** Its winners do not depend on volatility. Every attempt to filter or size Gold by volatility (SN99 cheapness, SN113 skip) has failed.
3. **Our costs are realistic.** Signals are filled about 40 s late and pay about the ₹205 we assume. No headroom for "cheaper execution" without real broker fills.
