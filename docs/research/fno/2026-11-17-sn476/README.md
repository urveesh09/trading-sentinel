# SN476–SN490: Gold v5 against its own weaknesses (Nov 17, 2026)

**Owner (Nov 17):** the auditor's ten Gold slots (`BRIEF.md`, a byte-exact copy of `2026-11-17-gold-v5-next-ten/HANDOFF.md`) plus five
own slots: "thorough testing, no half work". Plan `bf895633`, amendments A1–A4 in its section 5. Every script was committed before
it ran; results were written once (crashes before any output are disclosed in the commit log).

## Headline

- **Nothing beats Gold v5 on the dates we have, and Gold itself is weaker than its benchmark said.** Run unchanged on a sample it
  had never seen, NIFTY Jan 2020 – Aug 2021 (SN482), Gold **loses ₹64,783 at ₹205 and ₹93,971 at ₹400** from ₹30k (one lot: −₹35,767 /
  −₹52,884), with 5 of 20 months positive. With 2022 (−₹15,281) and 2023 (−₹12,107) it has now lost in **four of seven years**; all
  its money was made in 2024–26.
- Over every replayed session 2020–26, Gold's ₹30k book averages **₹612 a replay session at ₹205 and ₹300 at ₹400**; one lot averages
  ₹84 / **₹11**. Confirming the edge forward needs **585 market sessions (~2.4 years)** at ₹205 (SN485, frozen in `fw10.py`).
- **No challenger survives** (SN490): selling failed adds, a faster entry, expert-specific adds and an oil / rupee add filter all fail
  somewhere; the 2020–21 holdout confirms none of them.
- **Useful engineering, in Dev:** the live engine can take every trade the benchmark credits (SN476); its rules match the replay to the
  paisa; the held-contract pin closes the archive gap that hid Gold's two biggest winners (SN477, tests pass, not deployed); a
  packet-triggered stop-limit would recover about ₹140–160 a lot per stop on the same touch (SN479, mechanism only).

## Results

| Slot | Question | Result |
|---|---|---|
| **476** | Runtime Gold vs replay Gold | **Live:** Gold started Nov 13 with **0 eligible decisions** (no NIFTY N11 signal Nov 13 / 16; Nov 17 was expiry day, refused by the planner as in the replay); day rows reconcile; 0 divergences.<br>**Signal set:** the paper record gated at 0.85 contains **every benchmark trade** (156 of 156 in 2023–26, 30 of 30 in 2022) plus 7 / 2 trades the books' brakes blocked; on ₹30k they lose ₹18,925 / ₹5,309 (runtime-equivalent benchmark ₹8,31,958 @205, ₹4,73,030 @400), on one lot −₹34 / −₹867 (the gap is compounding).<br>**Pure rules:** lots, contract, charges and net identical **to the paisa on all 186 trades**.<br>**Three reproducible divergences:** the runtime stop leaves out the ₹205 reserve (≈ ₹3.15 lower per unit); growth and refills run on unstressed nets (2024's steps 1–13 days earlier); sampled-bid stops (the live tick) worsen the worst day (−₹21,113 → −₹26,908 @205; ~₹1,100 a lot) while avoiding 5 of 11 stops at ₹400.<br>**Structure:** the replay triggers adds and the trail on the NIFTY **index**, the runtime on the **future**; the replay requires a traded minute for a quote |
| **477** | Record the held contract to its exit | **PASS (Dev).** The tick recorder already keeps every contract all day (its set only grows; resubscribes after a drop). The gap was the **minute archive** (±5 strikes, recentred): Oct 8 22600 PE sat outside 22050–22550, Oct 21 23100 PE outside 22500–23000 at exit. New `research_pins.py`: each Gold entry and N11 paper record pins its exact contract in the collector's selected-leg store until 15:20; both traces stay in the collector's request; 9 new tests, 99 related pass |
| **478** | The same entry, sooner | **FAIL.** Live acts a median **40 s** after the 5-minute bar (8 paper rows; evaluations median 45 s). The replay enters at the first minute close after the bar for 63% of signals and one minute later for 30%; the stream contract traded at the earlier minute in every later case (a replay rule, not missing data). One minute sooner: ₹30k 2023–26 +₹15,397 @205 (CI −7,153 to +39,860), 2022 −₹1,380, one lot −₹13,339; 2020–21 one lot −₹990 |
| **479** | Recoverable stop slippage | **Planned sample INCONCLUSIVE:** 29 paper stops, none on a recorder day (the archive samples futures every ~40–50 s and options once a minute). **Mechanism on Nov 16–17 packets** (340 synthetic one-lot stops): on the same touch a packet-triggered stop-limit sells **1 s** after the trigger against the 55-s tick's ~50 s and recovers **₹160 a lot** (underlying stops; 90% CI 126–194) and **₹140** (premium; 100–180) against ₹56–63 of unavoidable move; worst-5% exit −₹168 / −₹229 against −₹749 / −₹612; over all events +₹56 / +₹28 a lot (CIs span zero: some touches the tick never acts on recover) |
| **480** | Sell a failed add, keep the original lots | **FAIL on every ledger.** ₹30k 2023–26 **−₹1,56,875 @205** (CI −2,59,785 to −62,392), −₹11,674 @400; 2022 +₹1,015 / +₹1,443. The 34 sold adds netted −₹61,557; held in Gold the same pieces made **+₹62,398** (dipped adds recover). Worst day unchanged. 2020–21: +₹2,886 / +₹5,163 (CIs span zero) |
| **481** | Same signal in next week's option | **INSUFFICIENT.** Trades 1–2 sessions before expiry are 59% of Gold's one-lot trades and **72% of its net**, but the Breeze history never holds the next weekly then (0 of 400 expiry pairs). On the archive, the 5 delta-matched pairs **all favour the front contract** (−₹1,759 a lot in total: dearer premium, smaller gain) |
| **482** | Unchanged Gold through 2020–21 | **Gold loses.** NIFTY Jan 2020 – Aug 2021 (327 Gold sessions of 414; N11 56 + 38 signals; route of SN366, receipts hashed): ₹30k **−₹64,783 @205** (2020 −50,837; 2021 −13,946), **−₹93,971 @400**, 5 / 20 months positive, refills ₹1,36,305, worst month −₹18,870; one lot −₹35,767 / −₹52,884; dated lots (75 then 50) −₹44,564 / −₹68,892. Puts −₹45,753, calls −₹19,030; TPB −₹45,320; **EFF the only component not losing** (+₹333; +₹2,309 one lot) |
| **483** | Oil + rupee as a risk input | **FAIL.** FRED Brent and USD/INR under honest publication lags (median 6–7 days stale): the joint stress lowers held-out next-hour adverse-excursion error in 4 of 5 years, but correlations are −0.04 to +0.19; stops (9) and add nets show nothing. The planned reduction (no add when stress ≥ 1) costs ₹30k 2023–26 −₹59,032 @205 / −₹59,610 @400 with the same worst day |
| **484** | A slower ETF trend benchmark | **FAIL.** NIFTYBEES month-end 12-month trend vs buy-and-hold, delivery costs + spread, whole shares: 2020–26 CAGR **1.7% vs 10.7%** (both −36% in the 2020 crash: a monthly rule cannot dodge a one-month fall), 2022–26 2.9% vs 6.5%, 2023–26 4.6% vs 7.1%. Funded like Gold 2023–26 (₹5.92 lakh in): trend −₹33,104, buy-and-hold +₹2,208. Yahoo's 2010–19 series has bad prints (A4), so the long window's drawdowns are unreliable |
| **485** | One funded forward contest | **Gold alone** (no survivor), from **2026-11-18 for 585 market sessions** (~2.4 years: n* for a 90% CI to exclude zero on the ₹30k book @205 from the 2020–26 prior; 1,450 @400). `fw10.py` scores once (EDGE_CONFIRMED / EDGE_REJECTED / INCONCLUSIVE) on read-only Production receipts and refuses to score early |
| **486** (own) | The failed-add rule's neighbours | **No threshold works.** θ = +0.5 / 0 / −0.5 / −1.0 ATR all help 2022 slightly (+₹992 to +₹2,369) and hurt 2023–26 (−₹68,588 to −₹1,71,810 @205); same-minute execution no better. **SN480b:** self-funded ₹30k capped at Gold's ceiling makes ₹8,89,565 on 2023–26 @205 **without deposits**, but **at ₹400 falls below ₹7,500 on 2023-12-22 and never trades again** |
| **487** (own) | Where Gold's money comes from | 2023–26 @205: **first lots 79%** (₹6,73,629), adds 21% (₹1,77,254, 48% of 62 adds won), extension **+₹230**; **puts +₹7,81,332** on 121 trades, calls +₹69,551 (−₹19,134 @400); TPB 65% of profit; EFF +₹78,715 but +₹8,445 @400. 2022: TPB −₹24,151 on 27 of 30 trades, all 4 adds lost |
| **488** (own) | Gold's uncertainty, contest length | From 2022–26 alone: P(losing year) 5.6% (₹30k @205) to 27.5% (one lot @400); median drawdown ~₹70k. Every candidate's paired difference needs **2 to 667 years** to confirm. (SN485 redoes the length with 2020–21 included) |
| **489** (own) | Adds by expert, chosen honestly | Leave-one-year-out estimate +₹83,855 @205 / +₹1,31,178 @400 → qualified; frozen rule = adds only on TPB / SHIPPED. Then **fails**: 2023–26 −₹25,045 @205 (+₹1,45,081 @400), 2022 0, 2020–21 +₹136 / +₹1,111 |
| **490** (own) | Frozen holdout on 2020–21 | **No survivor.** SN480 fails 2023–26, FAST fails 2022, SN489's rule fails 2023–26 @205 |

## Lessons

1. **Gold's edge is a 2024–26 phenomenon on the evidence we have.** Four of seven years lose (2020, 2021, 2022, 2023), losses spread
   over most months and every expert but EFF. A benchmark judged on 2023–26 is mostly judged on its best regime.
2. **The engine is faithful to the replay where it matters.** Same contract, lots, charges and net to the paisa; the paper record
   offers every benchmark trade. The remaining differences (stop reserve, growth on unstressed nets, sampled stops, index vs future)
   are small next to the regime problem, but they are reproducible and listed for a fix decision.
3. **Gold's adds are trend bets that recover from dips.** Cutting them on a reversal, on a stress reading, or by expert costs more
   than it saves; the tail does not shrink because Gold's worst days are not add days.
4. **Funding is part of the strategy.** Without deposits, ₹30k at ₹400 stress is gone by Dec 2023; the refills are the reserve.
5. **Execution has a cheap, real improvement:** a packet-triggered stop-limit recovers ~₹150 a lot per stop on the same touch
   (mechanism evidence); fresh real stops on recorder days are needed for a verdict.
6. **Forward verdicts take years.** Gold vs zero needs ~2.4 years at ₹205; any small improvement needs far longer.

## Owner decisions

1. **Deploy the SN477 pin** (Dev, tested; research-only, no order path). It lets the archive price every Gold / N11 exit.
2. **Runtime divergences (SN476):** keep as is and restate the benchmark (recommended for now), or change the runtime stop to reserve
   the ₹205 stress and grow on stressed nets (exact parity with the replay; changes paper behaviour).
3. **Build the packet-driven stop-limit path** for paper (SN479), then judge it on real recorder-day stops.
4. **Next-week data (SN481):** a Breeze download of the next weekly for the two sessions before each expiry (owner's call; the skill's
   targets do not include it).
5. **Real money:** this round argues against moving Gold to real money on 2023–26 evidence alone; the forward record (fw10) decides.
6. Unchanged: the 2023 expiry exam (sealed), deploy of earlier Dev items, NSE 2027 holidays before 2027.

## Data and receipts

- Production (read-only, throwaway container, `mode=ro`): `_local/prod-gold-20261117T113959Z.json` (sha256 60e487f9…); recorder copies
  Nov 16–17 in the scratchpad.
- 2020–21: mirrors `results-sn482-mirror-*.json` (sha256 a29b74da… / 417419e5…), daily, bind receipts; N09 DIAG and N11 exam replays in
  `_local` (git-ignored).
- External: Yahoo NIFTYBEES (sha256 in `results-sn484.json`), FRED DCOILBRENTEU / DEXINUS (sha256 in `results-sn483.json`), NSE circular
  FAOP70616 (lot 75 → 65, 2025; the 2020–21 dated lots are an assumption).
- Shared: `goldx.py` (Gold v5's walk with the round's switches; parity 8,50,883 / −15,281), `test_goldx.py` (6 fixtures).

Nothing deployed, nothing pushed. Production `0b645d77` was only read.
