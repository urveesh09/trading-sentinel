# SN221–SN230: the hedged weekly straddle (WK-H), the first gap-day leg to pass an unseen exam (Nov 15, 2026)

**Full record for Gold v6 work:** `docs/SN_WEEKLY_SELLER_AND_GOLD_V6.md` (section 0 holds SN221–SN230).

**Owner (Nov 15):** "SN204, SN208, SN207 … worked very well on those gap days and there were issues with them … improve them or make better ones … till SN230 … try start wallets lot sizes different combinations … we are not replacing GOLD_V5 … another one that works in the gap days."

## How it was tested

- **Plan:** `PLAN.md`, frozen at `ec76f220` before any number. The exam picks were frozen at `dbbf9086` before the exam was opened.
- **What changed from SN201–SN220:**
  - versions are chosen on **all four seen samples at once**, by a max-min rule: the version whose worst sample is best;
  - **three new mechanisms:** a futures delta hedge, trend timing, and no-weekend entry.
- **The four seen samples:**
  - NIFTY Apr 2022 – Aug 2026 (DEV);
  - TEST (Aug 20 – Oct 27 2026);
  - NIFTY Dec 2021 – Mar 2022 (N2122);
  - SENSEX Oct 2024 – Apr 2026.
- **The exam (once):** NIFTY weekly expiries **Oct 1 2020 – Nov 25 2021**, 60 weeks of data nobody had read, downloaded by the owner Nov 14–15.
- **Costs:**
  - options exactly as in SN204;
  - futures: Zerodha's current schedule (STT 0.02% on sell, NSE 0.00173%, ₹20 per order, stamp, GST), plus a 0.75-point half-spread, plus ₹100 per lot per order, plus ₹100 per lot before 09:20, executed one minute after the signal.

## Results

| SN | Study | Result | Verdict |
|---|---|---|---|
| 221 | Seal the data | Exam mirrors: 60 expiries, all with an expiry-day index, 375 index sessions from Jun 2020; futures for every sample. Counts and hashes only | Data sealed |
| 222 | Parity and the four-sample board | `wk3` = `wk.trade` and `wk2` gate exactly (0.0 rupee, 26 variants, all four samples). Every SN201–SN220 recipe loses on at least two samples (WK-S: DEV +3,13,523 / TEST −23,348 / N2122 −56,743 / SENSEX −42,022) | Engine proven; old recipes not robust |
| 223 | Trend timing (yesterday's ADX < 25 / < 20, efficiency ratio < 0.4) | Removes weeks, not the bad ones. No filtered base is positive on all four; random skipping does as well | FAIL alone |
| 224 | Exposure and the weekend | **Weekend intervals lose for sellers on every sample.** No-weekend entry (k = M, the Monday 15:15 for a Thursday expiry) lifts DEV, but N2122's Russia week is mid-week | Weekends are pure risk |
| 225 | Far wings (±2 Q) | Downloaded strikes rarely reach 2 Q (unclamped < 80% everywhere). Every winged version loses on all four (wings cost about ₹960 a week) | FAIL (needs wider strikes) |
| 226 | **Futures delta hedge** | Hedging 2 option lots in half-lot steps every 15 minutes (H15x2) **lifts the four-sample worst score in 78 of 78 versions.** Cost: about 4.5 futures orders a week, ₹640–760 a week per lot (mostly STT). One-lot hedges help about half the time | **The mechanism that works** |
| 227 | Robust selection (2,080 versions) | 65 positive on all four; 20 eligible, all filtered. The filtered picks fail the random-skip null, so by the frozen rule **PICK = STRADDLE kM settle H15x2 ("WK-H")**: DEV +2,11,957 per lot (worst month −15,915), N2122 +10,308, SENSEX +1,04,354, TEST −2,414 | Frozen before the exam |
| **228** | **THE EXAM, NIFTY Oct 2020 – Nov 2021 (60 weeks, once)** | **WK-H +₹61,511 per lot, 59% of weeks won, worst week −8,980, worst month −6,251, 9 of 14 months positive, 2020 +13,285 / 2021 +48,225.** Same weeks: WK-S −41,621; the same straddle unhedged −43,526; k1 straddle −12,009; WK-G −6,734; breach + gate −14,662. Best hedged WK-S (STRANGLE 0.5 k3 stop 1, H15x2) +78,395; plateau of the 20 eligible +37,670 | **PASS (P1–P4).** Forward-paper candidate |
| 229 | Wallets, lots, Gold + WK-H | One WK-H unit = 2 option lots ≈ ₹5 lakh margin (proxy). ₹15k / ₹30k / ₹1 lakh / ₹2.5 lakh cannot run it. ₹5 lakh: DEV +4.24 lakh (19.3% a year), exam +1.23 lakh (21.3% a year). **Gold + WK-H per option lot, 2023 – Aug 2026: +8,17,214 (Gold alone +6,42,173), 282 green days (55), worst month −28,184 (Gold alone −38,531)** | See below |
| 230 | Synthesis | below | – |

## SN230: synthesis

1. **What finally worked is not an exit; it is a hedge.**
   - WK-S was paid for quiet days and lost on trend weeks and gaps.
   - WK-H sells the same premium but **neutralises direction with NIFTY futures as the index moves**, the way option market makers earn.
   - It keeps the difference between the premium and the moves actually realised.
   - On the exam's weeks every unhedged seller lost (−₹12k to −₹44k per lot), and WK-H made +₹61.5k.
2. **Never hold a weekend.** Weekend intervals lose on every sample: the weekend decay is already priced in by Friday's close. WK-H enters at the 15:15 of the first session after the last weekend or holiday before expiry.
3. **Tails are small everywhere:**
   - the worst month per lot is −₹15.9k (DEV), −₹3.0k (TEST), −₹8.6k (N2122), −₹8.9k (SENSEX) and −₹6.3k (exam);
   - WK-S's was −₹51k / −₹19k / −₹36k / −₹70k / −₹19k.
   - The worst single weeks were −₹24.6k (May 16 2024: the hedge stops trading at 14:30 on expiry day, and the index then rallied 340 points into the close) and −₹18.3k (Feb 3 2026's +2.7% gap; the hedge cut it from −₹42k).
4. **Five samples, +₹3.86 lakh per lot in total.** The weekly average is about ₹1,000 per lot. It is not a daily wage: about 59% of weeks win, and the money comes mostly at expiry. On Gold's empty days it averages ₹386 a day for the ₹5 lakh unit.
5. **With Gold it is the first true complement:**
   - per lot, 2023 – Aug 2026: +₹1.75 lakh more profit;
   - 5× the green days;
   - a **smaller** worst month than Gold alone;
   - correlation −0.17 on Gold's trade days.
6. **What filters and wings taught:**
   - Trend filters only skip weeks; random skipping does as well.
   - Far wings cannot be tested on the downloaded strikes, and near wings cost more than they save.
7. **Not proven yet:**
   - one unseen sample (a bull market);
   - margin not verified on Zerodha;
   - about 4.7 futures orders a week (it must be automated);
   - the expiry-afternoon freeze is its weakest point.

## Next steps (each on the owner's word)

- **Crash test (pre-registered, PLAN.md):** once the NIFTY Jan–Sep 2020 options are downloaded, score WK-H, the runners, the references and the plateau **once**, unchanged.
- **Gold v6 candidate on paper:** Gold v5 + WK-H as a forward paper shadow, placing no orders.
  - It needs a Dev module (live option and futures quotes, the hedge loop, Telegram lines) and a deploy on the owner's word.
  - Every live week is new unseen data.
- **Zerodha margin check** for 2 short NIFTY straddle lots + 0–2 futures lots, which the owner can check in Kite's basket margin.
- **A research idea for a later slot, not tested:** close the hedge at the 14:30 freeze instead of holding it to settlement. It would be scored on the crash test as information only.

## Files

- **Plan and engine:** `PLAN.md`, `wk3.py`, `grid.py`.
- **Studies:** `sn221.py` … `sn229.py`, with `results-sn221.json` … `results-sn229.json`.
- **Exam ledger:** `results-sn228.json` → `pick_ledger_per_lot`.
- **`_local` (git-ignored):**
  - exam mirrors `mirror-nifty-2021-lean.sqlite` (sha `7ec3e483…`) and `mirror-nifty-2021-full.sqlite` (`10d9d542…`);
  - futures `fut-nifty-2021.sqlite` (`d623beb9…`), `fut-nifty-2122.sqlite` (`8e5df633…`), `fut-sensex.sqlite` (`64f8a451…`);
  - the grid caches `grid-*.pkl`.
- **`logs/`:** git-ignored. Crash logs are kept locally.
- **Post-freeze fixes (disclosed):**
  - `wk3.hedge_path` falls back to the ATM strike when the entry index print is missing (a DEV crash before any number);
  - SN226 and SN227 had JSON save fixes (numpy integers) and were rerun unchanged, with identical printed output.
  - SN227 also added an information-only field (the best eligible unfiltered version: none).
