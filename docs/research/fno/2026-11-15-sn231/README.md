# SN231–SN250: Gold v6's bad months, and Gold v7 (Nov 15, 2026)

**Owner (Nov 15):** "comprehensively analyse the bad months … understand why it happened … something else that can help us make every single month positive … I have promised to refill every single penny that the system loses any day … give me a Gold V7 if possible."

**How it was tested**
- **Freezes:** plan `PLAN.md` at `5f67bb0b`, before any number; the diagnosis and amendment `DIAGNOSIS.md` and the `wk4.py` engine at `d87c0031`, before any candidate was scored.
- **Selection rule (frozen, Q1–Q5):**
  - more positive months than Gold v6;
  - ≥ 90% of its profit;
  - no worse worst month;
  - an added or changed WK leg positive on ≥ 4 of 5 WK samples with no fewer positive months;
  - threshold rules must beat a null.
- **The account:** SN Gold v5 (₹30k growing) + the WK leg, every day of Jan 2023 – Oct 2026 (46 months). That is the only window where Gold v5 can be replayed.
- **WK legs alone, five samples:** DEV, TEST, NIFTY Dec 2021 – Mar 2022, SENSEX Oct 2024 – Apr 2026, NIFTY Oct 2020 – Nov 2021.
- **Every sample on the PC is now seen.** The only unseen history, NIFTY Jan–Sep 2020, is still downloading; its crash test is pre-registered (`CRASH_TEST_2020.md`, `sn248.py`).

## Results

| SN | Study | Result |
|---|---|---|
| 231 | Gold v6 ledger | **31 of 46 months positive**, net +₹11,96,139, worst month −₹38,228 (May 2024). In the 15 bad months both legs lost in 8; WK-H's loss −₹1.54 lakh, Gold's −₹1.11 lakh. 8 of the 15 are in 2023 |
| 232 | Bad-month anatomy | Bad months are **quiet months**: realised volatility 10.6% vs 12.1% annualised, fewer 1% days and gaps. Gold trades 0–4 days in them; WK-H loses small amounts **although options were priced above the moves** (implied ÷ realised 1.2–1.5 in 2023) |
| 233 | WK-H's losing weeks (5 samples) | **Hedge charges ₹1.42 lakh per lot on DEV against a ₹2.12 lakh net.** The 14:30 expiry freeze cost −₹83k on DEV (May 16 2024: −₹24.6k). Gaps −₹1.47 lakh in 27 weeks; moves above implied −₹1.0 lakh in 32 weeks |
| 234 | Diagnosis and amendment | `DIAGNOSIS.md`: expiry-afternoon, hedge-cost and synthetic-hedge candidates added before any score |
| 235 | Expiry afternoon | Hedging through 15:15: worst month −₹27.7k but 31 months, −7% profit. Flattening at 14:30: 33 months but worst −₹45.2k. Every 5 minutes: like the first. **None qualifies** |
| 236 | Hedge cost; a second unit | **Band 0.8, every 15 minutes: 33 months, +₹13.71 lakh, worst −₹28,981, charges −38%: QUALIFIES.** Bands 1.0 / every 30 add months but break the tail or the WK samples. Synthetic options hedge alone: 5 of 5 WK samples positive but account worst −₹44.9k. A second hedged unit: worst month −₹48k to −₹54k |
| 237 | Daily hedged straddle | Fails: 25–26 months, rolling every day pays option costs every day |
| 238 | SENSEX WK-H as a second leg | +1 month, worst month −₹48k (band 0.8). Fails |
| 239 | Skip low-premium weeks | No more positive months than random skipping. Fails |
| 240 | More WK-H units | 2 units: 35 months but worst −₹51.6k (band 0.8). Fails the tail rule |
| 241 | Month profit-protection | No month turns positive; it only trims profit. Fails |
| 242 | Idle capital at 5% | +₹2,208 a month on ₹5.3 lakh: 34 months with band 0.8. Shown apart, not a strategy |
| 243 | Extra candidates | None |
| 244 | Combinations | Eligible: band 0.8. Information only: band 0.8 + synthetic hedge 34 months, +₹14.83 lakh, worst −₹30.7k (the best next idea) |
| **245** | **Gold v7 by the frozen rule** | **Gold v7 = SN Gold v5 + WK-H with hedge band 0.8** |
| 246 | Robustness | Bands 0.7 / 0.8 / 0.9 all beat 0.6 in the account (32–34 months, worst −₹23k to −₹35k). It survives option stress ₹200 / ₹300 and a 1.5-point futures half-spread. 2023: 7 positive months vs 4. Month bootstrap: band 0.8 more months 75% of the time, equal 14% |
| 247 | Gold v7 in money | See below |
| 248 | 2020 crash test | Pre-registered and sealed until the download completes |
| 249 | Runtime | `SN_WKH_BAND = 0.8` and `SN_WKH_LABEL = "Gold v7"` in Dev (`python-engine/sn_wkh.py`); Gold v6 is the same with 0.6 |
| 250 | Synthesis | below |

## Gold v6 vs Gold v7 (Jan 2023 – Oct 2026; Gold v5 ₹30k growing + one WK-H unit, 2 lots, ₹5 lakh)

| | Gold v6 (band 0.6) | **Gold v7 (band 0.8)** |
|---|---:|---:|
| Net | +11,96,139 | **+13,70,643** |
| Months positive | 31 of 46 | **33 of 46** (34 with idle-capital credit) |
| Worst month | −38,228 | **−28,981** |
| Mean month | 26,003 | 29,797 |
| 2023 / 2024 / 2025 / 2026 | −55,408 / +2,63,993 / +5,14,760 / +4,72,794 | **−26,648** / +3,43,667 / +5,68,064 / +4,85,561 |
| Owner's refills, total / worst month | 13.41 lakh / 71,314 | 13.40 lakh / 67,407 |

**Gold v7's 13 remaining bad months:**
- **9 from WK-H:** quiet 2023 months; May 2024's expiry-afternoon rally (−₹28,981); Feb 2026's gap (−₹5,175 net).
- **4 from Gold v5's own losing months:** Mar 2024, Oct 2024, Dec 2025, Apr 2026 (−₹38.5k Gold, softened to −₹15.7k by WK-H).

## SN250: synthesis

1. **Every month positive is not reachable with what the data supports today.**
   - The best rule-compliant version moves from 31 to 33 positive months of 46.
   - The remaining bad months are Gold v5's own losing months and sudden-move weeks that no hedge trades through.
2. **What helped was cost, not prediction.**
   - A wider hedge band trades the futures less (531 orders against 868 on DEV), so quiet months stop bleeding charges. 2023 went from −₹55k to −₹27k.
   - Filters, skips, extra legs and month rules did not help.
3. **The price of band 0.8.**
   - It earns less than 0.6 in fast markets: NIFTY 2021–22 −₹10k vs +₹10k per lot; SENSEX +₹78k vs +₹1.04 lakh. The 2020–21 exam is about equal (+₹59.6k vs +₹61.5k).
   - The 2020 crash test is the real check.
4. **The owner's refills:** about ₹29k a month on average (₹67k in the worst month), against ₹58k a month banked. The owner should plan for that cash flow.
5. **Best next idea (not yet eligible):**
   - band 0.8 with a synthetic options hedge, cheaper per order: 34 months, +₹14.8 lakh;
   - it needs option legs in the runtime and its own forward record.
6. **Not yet done:**
   - the 2020 crash test (data);
   - Gold v5's own unseen-year test, which needs an N11 replay for 2021 (separate job);
   - a Zerodha margin check;
   - a forward paper record of Gold v7.

## Files

- **Plan and diagnosis:** `PLAN.md`, `DIAGNOSIS.md`, `CRASH_TEST_2020.md`.
- **Code:** `led.py` (ledger), `ev.py` (scoring), `wk4.py` (hedge options; parity with `wk3` exact on all five samples).
- **Studies:** `sn231.py` … `sn248.py`, with `results-sn231.json` … `results-sn247.json`. `results-sn232-v1-entry-index-missing.json` is kept (a disclosed fix).
- **`logs/`:** git-ignored. Crash and print-fix logs are kept locally.
- **Post-run fixes (disclosed):**
  - SN231 and SN238 had print fixes (numpy integers): no number changed, rerun identical;
  - SN232's entry-index lookup was fixed, with the v1 result kept;
  - the SN243–SN246 stress test passes the option stress explicitly; fixed before it ran.
