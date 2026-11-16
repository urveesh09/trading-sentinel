# SN276–SN285: learn from every earlier strategy, on all the data at once (Nov 16, 2026)

**Owner (Nov 16):** "10 slots more. Try some other perspective … that same wallet, size … specific for gap days … learn from the good points of strategies … use whatever you want."

**Answer in one line:** combining every earlier gap-day signal on the largest sample ever used here does not create an edge.
- Learners and a vote fail strictly walk-forward.
- The one consistent signal is calls on the session before a weekday market holiday: positive on all four samples, about 10 trades a year, found after the fact. In Gold's wallet it added +₹15k and 3 positive months over 2023–26 (in-sample). A forward paper watch at most.

## How it was tested

- **Freezes:**
  - plan `PLAN.md` at `c300be88` before any number;
  - dataset and scripts at `c0521449`;
  - SN280–SN282 at `0dc1d2dc`;
  - the SN284 amendment at `d53009ee`.
- **Engine and constraints:** SN251's `gl.py` / `legs.py` unchanged. One lot; a ₹3,000 stop; Zerodha charges + ₹205 per lot per leg.
- **Pooled sample:** 1,465 sessions, NIFTY Oct 2020 – Oct 2026 plus SENSEX Oct 2024 – Apr 2026.
- **Learners:** walk-forward by half-year, 2022 H1 – 2026 H2. Each model is trained only on earlier sessions of both indices.
- **Disclosure:** all sessions were seen by earlier studies, and the features came from them.

## Results

| SN | Study | Result | Verdict |
|---|---|---|---|
| 276 | Pooled dataset: 21 features at 10:00; straddle / call / put outcomes to 15:10 | Every plain action loses on average on every sample: straddle −₹580 to −₹1,015 a session, call −₹224 to −₹1,194, put −₹212 to −₹481 (TEST puts +₹416) | Base rates |
| 277 | Walk-forward LightGBM action-value learner | τ = 0: −₹1,28,556 over 865 trades, 4 of 10 half-years positive, NIFTY −89k, SENSEX −39k. τ = 300: −₹1,81,979 | **FAIL** |
| 278 | Walk-forward two-stage classifier (direction + big move) | δ = 0.12: −₹1,34,370, 2 of 10 half-years positive; δ = 0.08: −₹1,64,016 | **FAIL** |
| 279 | Vote of seven frozen signals → the 10:00 straddle | k = 2 loses on all four samples. k = 3: DEV +13,988 (62), TEST +3,834 (4), EXAM-N −11,040 (39), EXAM-S −28,680 (28) | **FAIL** |
| 280 | Controls for the best (SN279 k = 3, pooled from 2022) | −₹973 over 105 trades: better than random days (null −₹62.8k), but ₹400 −₹53.9k, late −₹7.7k, without the best 10 −₹1.01 lakh | **FAIL** |
| 281 | Cheaper expressions of the two exam-positive signals | **Pre-holiday call:** ATM +52,185 / ITM +46,674 in total, **positive on all four samples** (ITM: DEV +20,266, TEST +5,464, EXAM-N +10,050, EXAM-S +10,894; 73 trades); the debit spread loses (−41,160). **Breakout swing:** all expressions lose on DEV | Description (post-hoc) |
| 282 | SN126-L (hot-day bursts), the original code | EXAM-N +₹132 on 12 trades (₹400 −₹2,208); 2022 −2,544; TEST −1,714; 2023–26 in-sample +4,037. EXAM-S not ported | **FAIL** |
| 283 | Cash-equity paper books on Production (read-only) | Penny Smart V3: 4 trades, −₹95 on ₹2,000. Momentum ORB shadow: 4 days, −₹111. Both hold cash in Gold's trading window | Not a fit |
| 284 | Information only: the pre-holiday ITM call inside Gold's one wallet (2023 – Oct 2026) | Gold +₹8,50,883 → +₹8,65,853 (+₹14,970 from 38 calls); positive months 25 → 28; worst month −₹38,531 → −₹20,498; worst day −₹21,113 unchanged; green days 62 → 75. **In-sample** | Watch candidate |
| 285 | Synthesis | Below | – |

## SN285: synthesis

1. **"Learn from all the strategies" was the right idea to test, and it failed.**
   - Signals that are each almost noise stay noise when combined.
   - The walk-forward learners lost ₹1.3–1.8 lakh and were positive in only 2–4 of 10 half-years.
   - The vote picked better days than chance but still lost after costs.
   - The cost of each 10:00 option (₹200–650 a day) is larger than anything the data can predict on gap days.
2. **Calls on the session before a weekday holiday.**
   - It is a known calendar effect (markets tend to rise before holidays), and it was positive on DEV, TEST and both unseen exams.
   - Against it: it was found after the fact, it fails the random-null test (its bad year is as bad as chance), and it trades about 10 times a year.
   - Inside Gold's wallet it would have added about ₹4k a year (in-sample).
   - Worth a forward paper watch, not money.
3. **Expressions:** an ITM call is at least as good as ATM; debit spreads lose (two legs of costs, capped winners).
4. **For the record:** the cash-equity books, the burst scalper (SN126-L) and the hot-day straddle do not carry over.

## Files

- **Plan:** `PLAN.md` (with the SN284 amendment).
- **Code:** `ds.py` (SN276 dataset), `wf.py` (walk-forward), `sn277_278.py`, `sn279.py` … `sn282.py`, `sn284.py`.
- **Results:** `results-sn276.json` … `results-sn284.json`.
- **Local and logs:** `_local/ds.pkl` (git-ignored), `logs/`.
