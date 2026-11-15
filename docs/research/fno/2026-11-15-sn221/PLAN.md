# SN221–SN230: a robust gap-day leg, chosen on every seen sample and judged once on unseen NIFTY 2020–21 (Nov 15, 2026)

Frozen before any number of SN222–SN230 is computed. Research only, in Dev. No order, no runtime change, no Production change.

## The owner's ask (Nov 15)

"I remember SN204, SN208, SN207 which worked very well on those gap days and there were issues with them … we tried to create good exit strategies for them … but failed … improve the SN strategies to improve the gap days like the 204 and rest … improve them or make better ones … 10 more slots now till SN230 … make each SN slot count … try start wallets lot sizes different combinations … we are not replacing GOLD_V5 … another one that works in the gap days the GOLD does not work … full creative liberty … consistent daily earning."

## What SN201–SN220 taught, and what changes here

1. **The weekly seller (WK-S) was chosen on NIFTY 2022–26 alone** and then lost on all three other samples. Each sample liked a different version (SN219).
   - **Change 1:** choose on **all four seen samples at once** (NIFTY 2022–26 development, TEST, NIFTY Dec 2021 – Mar 2022, SENSEX Oct 2024 – Apr 2026). Use a **max-min rule**: the version whose worst sample is best.
2. **Exits cut tails but did not create an edge.** The losses are trend weeks, expiry-day moves and weekend gaps.
   - **Change 2:** three new mechanisms that act on those causes rather than exiting after the damage:
     - **futures delta hedging**, the way option market makers earn the premium without betting on direction;
     - **trend timing**, selling only after weak-trend days, the days Gold leaves empty (SN186);
     - **no-weekend entry**, never holding a weekend, the gap no exit can stop.
   - Far-wing insurance is tested only as far as the downloaded strikes allow.
3. **The judge.** The owner downloaded NIFTY 2020–21 on Nov 14–15. **NIFTY weekly expiries Oct 1 2020 – Nov 25 2021 (60 weeks) have never been read by any study:**
   - option prices: never read;
   - index: never read before Sep 2021; the Sep–Nov 2021 index minutes were read only as HAR warm-up in SN205/SN209, and no trade was scored on them.
   - The exam is scored **once**, in SN228, on the frozen picks of SN227.

## Data (SN221 seals it, counts only)

**Seen samples (selection), "the four":**
- **DEV:** NIFTY weeks with entries Apr 1 2022 – Aug 19 2026 (`wk.split(..., "dev")`, the year datasets);
- **TEST:** NIFTY entries from Aug 20 2026 (`wk.split(..., "test")`);
- **N2122:** NIFTY expiries Dec 2 2021 – Mar 24 2022 (SN201's lean mirror, SN211's full mirror);
- **SENSEX:** SENSEX expiries Oct 4 2024 – Apr 30 2026 (the same mirrors).

**Unseen exam, "EXAM":** NIFTY weekly expiries 2020-10-01 … 2021-11-25. SN221 builds read-only mirrors from `~/sentinel-operations/breeze-history-20261029/data/breeze-history.sqlite` (opened `mode=ro`, short queries; the downloader is not running):
- lean: index 1-minute Jun 1 2020 – Nov 30 2021, plus option rows 14:55–15:29 of those expiries;
- full: option rows at every minute of those expiries, sessions before expiry;
- futures: NIFTY 1-minute futures Jun 1 2020 – Nov 30 2021.

The audit prints counts and hashes only.
- **Sep 2020 expiries are excluded:** the Jul–Sep 2020 target is unfinished.
- **Expiry 2021-07-08 carries 8 sessions** because the 2021-07-01 expiry has no data. For the exam, a week whose session list holds more than 5 sessions drops the sessions on or before expiry − 7 calendar days.

**New futures mirrors (seen samples):**
- NIFTY futures Nov 20 2021 – Mar 31 2022;
- SENSEX futures Sep 25 2024 – Apr 30 2026.

DEV/TEST futures come from the year datasets.

## The engine (`wk3.py`, on `wk.py` / `wk2.py`, neither edited)

**Base positions.** `wk.trade` exactly:
- sell at the model bid, buy at the model ask;
- Zerodha charges, plus ₹100 per leg-lot stress;
- 15:15 lean marks; settlement at intrinsic on the expiry-day 15:00–15:29 index mean.

**Exits** (checked at each later 15:15 mark, in this order):
1. **stop:** total value ≤ −1.0 × credit;
2. **gate −0.25** (SN217): settle base, day before expiry, close unless the index is within 0.25·Q beyond both short strikes;
3. **pre:** close at the 15:15 before expiry.

With no hedge, `wk3` must reproduce `wk.trade` and `wk2.simulate(gate)` exactly (SN222 parity).

**Structures:**
- STRADDLE;
- STRANGLE 0.25 and STRANGLE 0.5;
- far-winged `IC 0.5/1.5` (shorts ±0.5·Q, wings 1.5·Q beyond);
- far-winged `IF 2.0` (straddle with wings ±2·Q).

Winged variants clamp missing wings inward (`wk.trade`). A winged variant is **eligible only if ≥ 80% of DEV weeks are unclamped**.

**Entry day k:**
- **1, 2, 3:** sessions before expiry;
- **F:** the week's first session;
- **M (new, "no weekend"):** the earliest session from which no calendar gap of more than one day remains before expiry. With no such session, there is no trade that week.

**Trend filters (new; causal, computed before entry):**
- **ADX:** yesterday's 14-day Wilder ADX on daily index bars (through the session before entry), < 25 or < 20;
- **ER:** the 10-session efficiency ratio of daily closes (entry day's 15:15 as today's close), < 0.4.

Daily bars come from each sample's own index minutes; DEV's first weeks use the N2122 index for warm-up, which is seen and causal. A filter only skips weeks.

**Futures delta hedge (new):**
- **Delta:** each leg's Black–Scholes delta, with σ fixed at entry from the ATM straddle (Q = 0.7979·S·σ·√T0).
- **Time:** in session units; the rest of today ÷ 375, plus each full session left, plus 360/375 for expiry day, plus 0.15 per night.
- **Rebalance:** the net delta is lots × option delta + h futures lots. When |net| > band, h is reset to −round(lots × option delta).
- **Checks:** every m minutes, from 15:16 on the entry day to 14:30 on expiry day, then frozen.
- **Execution:** at the next minute, at the futures close (missing → index + last basis, counted):
  - half-spread NIFTY 0.75 point, SENSEX 3 points;
  - Zerodha futures charges (Nov 2026 schedule: ₹20 or 0.03% per order, STT 0.02% sell, NSE 0.00173%, SEBI ₹10/crore, stamp 0.002% buy, GST 18%; NSE rate used for BSE too);
  - ₹100 per lot per order;
  - ₹100 per lot extra before 09:20.
- **Contract:** the first futures expiry on or after the option expiry.
- **Closing:**
  - the hedge closes with the options at a 15:15 exit;
  - at settlement it closes at the futures' 15:00–15:29 mean;
  - marks and the stop use options + hedge, both as if closed now.
- **Variants:**
  - `H1`: band 0.6, every minute, 1 option lot;
  - `H15`: band 0.6, every 15 minutes, 1 lot;
  - `H15x2`: band 0.6, every 15 minutes, 2 option lots (all rupees ÷ 2 for selection, reported raw too).

## Studies

| SN | Study | Samples |
|---|---|---|
| 221 | Seal the data (mirrors, counts, hashes, exam expiry list) | counts only |
| 222 | Engine parity (no-hedge `wk3` = `wk.trade` / `wk2` gate, every naked variant, the four), then **the four-sample board** of SN201–SN220's recipes: WK-S, runner-up (STRADDLE kF stop 0.5), WK-G, pre base, k1 ATM straddle, WK-A (IC 1.0/1.0 k1), breach 0.5 + gate | the four |
| 223 | Trend timing: filters × {WK-S, WK-G, k1 straddle, runner-up}; random-skip null (same skip rate, 500 draws, DEV) | the four |
| 224 | Exposure: k ∈ {1, 2, 3, F, M} × straddle / strangles × settle / gate; weekend-gap anatomy (P&L of weekend nights vs weekday nights for held positions) | the four |
| 225 | Far wings: IC 0.5/1.5 and IF 2.0 × k × exits; wing coverage per k | the four |
| 226 | Futures delta hedge: H1 / H15 / H15x2 × straddle / strangles × k × exits; hedge counts, costs paid | the four |
| 227 | **Robust selection** over the union of SN222–SN226 (every structure × k × exit × hedge × filter), then the freeze | the four |
| 228 | **The exam, once:** NIFTY Oct 2020 – Nov 2021 | EXAM |
| 229 | Wallets, lots and the account: margin need per lot, wallets ₹15k / ₹30k / ₹1 lakh / ₹2.5 lakh / ₹5 lakh; Gold v5 (₹30k growing) + pick on DEV 2023 – Aug 2026 (SN207's ledger); the exam per wallet | DEV, EXAM |
| 230 | Synthesis, docs | – |

## SN227's selection rule (frozen)

For each variant v and each of the four samples s:
- **Score:** `score_s = net_s / W_s`, where W_s is the number of weekly expiries in the sample, skipped weeks included, so standing aside scores 0. Lots-2 variants are divided by 2.

**Eligible** only if all of the following hold:
- **E1:** net > 0 on all four;
- **E2:** DEV years positive ≥ 4 of 5;
- **E3:** DEV worst month ≥ −₹34,163 (a third smaller than WK-S's −₹51,245);
- **E4:** trades in ≥ 50% of DEV weeks;
- **E5:** winged variants have ≥ 80% of DEV weeks unclamped.

**The picks:**
- **PICK** = the eligible variant with the largest min_s score_s; ties go to the larger summed net over the four.
- **RUNNERS** = the next two by the same order.
- **PLATEAU** = the per-week average of all eligible variants, a less tuned ensemble.

**If no variant is eligible:**
- no Gold v6 leg is proposed;
- the exam is still scored, once, on the max-min variant among all (labelled "least bad") and the references.

**Exam references (scored beside the picks):**
- WK-S, WK-G, breach 0.5 + gate (minute engine);
- the k1 ATM straddle;
- the best hedged version of WK-S (by min score).

The picks are written to `results-sn227.json` and committed before SN228 runs.

**Random-skip null (filters only):** a pick with a filter must beat the 95th percentile of 500 random skips of its unfiltered base at the same skip rate, on the min-score. If it does not, its unfiltered base replaces it.

## SN228's pass rule (frozen)

The PICK is a **forward-paper candidate** for a Gold v6 gap leg if both hold:
- **P1:** EXAM net > 0;
- **P2:** EXAM worst month ≥ −₹34,163.

Reported beside it:
- **P3**, the five-sample total;
- **P4**, whether it beats the k1 straddle reference on EXAM, which shows whether being smart adds anything over plain selling;
- each runner and the plateau.

**A pass is not proof:**
- it allows a Dev paper shadow and nothing more;
- going live needs the owner's word.

**A fail ends the family for this round.**

## Pre-registered later score (not in SN221–SN230)

When the NIFTY Jan–Sep 2020 options are downloaded (the COVID crash), the SN227 picks and references are scored **once**, unchanged, on its expiries.

## Wallet and margin conventions (SN229)

- **Naked short (straddle / strangle) or hedged:** ₹2.5 lakh per option lot, the SN204 proxy, not verified on Zerodha.
- **Winged:** the median max loss + ₹10,000.
- **Lots:** = floor(wallet ÷ margin).
- **Growing wallet:** +1 lot after net profit equal to one lot's margin (cap 3 lots).
- **Gold v5:** its own ₹30k wallet, unchanged.

## Integrity

- Each `snNNN.py` refuses to rerun once its `results-snNNN.json` exists.
- Crashes are logged in `logs/` (git-ignored) and disclosed.
- Post-freeze fixes are disclosed.
- No partner data. No Breeze call.
- The live download database is opened read-only only.
