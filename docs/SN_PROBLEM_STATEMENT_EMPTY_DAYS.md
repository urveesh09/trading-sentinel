# Problem statement: profitable trading on the days SN Gold does not trade (for a research agent)

**Owner's goal:** a small-wallet NIFTY options book that earns more consistently. Today's best book, SN Gold v5, trades on only about **16% of sessions**. The owner wants a profitable strategy for the other ~84% ("make profit in those days, not losses"), without copying Gold. This document states the problem, the evidence, every approach that failed and why, the constraints, the data, and what a valid solution must show.

Read with:
- `docs/SN_STRATEGY_HISTORY.md` (the full record);
- `docs/SN_TESTING_PROCEDURE.md` (the exact testing method; any solution must be judged by it).

---

## 1. The system as it is

**SN Gold v5** (frozen: `docs/research/fno/sn-gold/SN_GOLD_V5.json`, `gold_v5.py`, tag `sn-gold-v5`; running on paper in Production as `python-engine/sn_gold.py` since Nov 13, 2026, ₹30,000 start):
- **Entries:** the signals of the N11 F&O book (four setups on NIFTY futures: SHIPPED break, OR20 opening range, EFF efficiency, TPB trend pullback), plus its sister book R0.85.
- **Day gate:** yesterday's daily ADX(14):
  - **ADX ≥ 30:** all four setups may fire;
  - **ADX < 30:** only TPB, and only **puts**, and only before 14:00;
  - plus a stand-aside rule (low volatility and a losing 20-trade paper record).
- **Instruments:** NIFTY weekly options, bought only. In the money when affordable.
- **Exits:** N11's own exits, plus winners kept on a trail. One position at a time.
- **Money:** a 20% day loss limit; a wallet that grows 50% after net profit equal to the wallet (at most 3 times).
- **Result (in-sample, 2023 – Oct 2026, 742 non-expiry sessions):** from ₹30k with refills, +₹8.5 lakh. From ₹15k: 58 winning days, 64 losing, **620 no-trade days**.

---

## 2. The gap, measured (SN76, `docs/research/fno/2026-11-13-sn76/`)

- **Why Gold doesn't trade:** of the 620 no-trade days, **609 had no N11 / R0.85 setup at all**; 11 had a signal Gold could not take (position already open, or unaffordable).
- **Gate × day outcome** (won / lost / none; "up/down/flat" = open-to-close beyond ±0.25%):

  | | Up day | Flat day | Down day |
  |---|---|---|---|
  | ADX < 30 | **0 / 2 / 179** | 2 / 12 / 208 | 28 / 21 / 130 |
  | ADX ≥ 30 | 8 / 11 / 23 | 7 / 6 / 39 | 12 / 12 / 36 |

- **Low-ADX days are 582 of the 742.** On them N11 can only buy puts, so low-ADX up days and flat days are almost never traded.
- **Where Gold's money is:**
  - days with range ≥ 1.3% (+₹1.25 lakh, 18% win vs 5% loss);
  - down days worse than −0.7% (+₹1.14 lakh, 24% vs 7%).
  - Narrow days (< 0.6%) lose.
- **What empty days look like** (k-means on range, move, efficiency, first hour, gap, close position):
  - the largest no-trade cluster (192 days) is a **slow up-grind**: range 0.76%, move +0.36%, path efficiency 0.06, close near the high;
  - the rest are narrow or flat days.

---

## 3. Why the obvious answers fail (every approach tried, with numbers)

All results use real charges + ₹205 per lot per trade, choose-on-3-years / score-on-the-4th (LOYO), and a random-entry NULL with the same search budget.

| # | Approach on Gold's empty or Gold-free days | Result | Failure reason |
|---|---|---|---|
| 1 | Active intraday option buying, 7 entry families, premium exits (SN01, 21k rule sets) | Held out −₹1,22,146 vs random −₹1,35,115 | Entries ≈ random; costs per trade ≈ the expected gain |
| 2 | The same entries with N11-style index exits (SN04, 15.6k sets, trading ≥ 50% of days) | Held out −₹1,51,769 vs random −₹1,42,961 | Exits don't create edge; N11's edge is its entry selection |
| 3 | N11's ingredients rebuilt (5-minute setups, ADX gate, DMI direction) without its big-money rules (SN06) | Held out −₹62,251 (beats random −₹1,50,624, still loses) | Gates help, but not enough to pay costs |
| 4 | Fill empty days from 136 house strategies (SN05) | Held out +₹1,08,411 vs N11 alone +₹1,19,054 | Added trades lose |
| 5 | Relax N11's own rules: big-money rules (SN07), quality rules (SN08) | Every relaxation worse; all relaxed −₹23,477 | The rules that block trading on empty days are the edge |
| 6 | Option open-interest signals (PCR shift, writer flow, OI walls) (SN09) | Held out −₹1,80,378 vs random −₹1,57,721 | OI adds no direction |
| 7 | Expiry-day mornings on 10-second bars (SN10) | Pick +₹10,506 → −₹20,705 | – |
| 8 | Selling time value with defined risk (iron condors, credit spreads) (SN77) | Loses even with zero slippage (held out −₹51,496) | Intraday premium on quiet non-expiry days is about fair; 2–4 legs of charges and spreads |
| 9 | 1-second book (30-second signals, per-second exits) (SN78 → SN79 unseen test Jul 28 – Nov 12) | TWAP pick −₹28,579, momentum −₹51,078, **random −₹7,745** | Training profits were selection luck |
| 10 | Web day-type rules (narrow CPR → trend; tight opening range coils) (SN80–SN83) | The claims are false on NIFTY; breaks lose (held out −₹39,536 vs random −₹26,233) | – |
| 11 | Opening-range break on predicted big days (wide opening range) (SN84) | About break-even at best; held out −₹34,697 vs random −₹17,712 | **Big days are predictable, direction is not** |
| 12 | Puts / opening drive on predicted big days (SN86–SN88) | Plain puts +₹18,592 (all 2025); held out −₹38,179 vs random −₹16,292 | Not robust across years |
| 13 | Quick exits with a small profit cap (SN01, SN03, SN11, SN27) | More winning days, net losses (quick profit +₹500: 73 winning days, −₹25,412) | Cost ~₹85–120/lot/round trip vs a coin-flip direction; the cap removes the fat right tail |

**The core diagnosis:**
- On Gold's empty days, **price data at 1-minute and 1-second resolution carries no exploitable direction**, and intraday option premium is about fairly priced.
- With a round-trip cost of about ₹85–120 per lot (about 1.4 premium points), any rule without real direction skill loses about its cost per trade. Both buyers and sellers lose.
- **What IS predictable:**
  - the size of the day: a wide 09:15–09:45 range → 34% of days reach a 1.3% range vs 8% after a tight one; yesterday's volatility also helps;
  - Gold's own setups' direction on its own days.

---

## 4. What a solution needs that past attempts lacked

A valid approach almost certainly needs **information that the NIFTY price series alone does not contain**, or a **cost structure** that changes the arithmetic. Candidate directions not yet tested:

1. **Event and calendar information:** RBI policy days, budget, US CPI/FOMC nights, index rebalancing, large-cap results days, expiry-week position effects. Gate or direction from scheduled events.
2. **Pre-open global cues:**
   - GIFT Nifty / SGX overnight move;
   - US index close and futures;
   - Asian open, USD-INR, crude.
   - Overnight information may give the morning direction on days N11 has no setup.
3. **Cross-index lead-lag:**
   - Bank Nifty / Fin Nifty / SENSEX versus NIFTY, at 1-second resolution;
   - futures basis and option skew shifts.
   - Only NIFTY index plus opening-ATM options exist in the 1-second archives; other series would need new downloads.
4. **Breadth and constituents:** advance/decline, heavyweights (HDFC Bank, Reliance, ICICI) leading the index intraday.
5. **Cost structure:**
   - fewer, larger expected moves per trade (hold rather than scalp);
   - instruments with lower relative cost (index futures need ~₹1.5L+ margin, beyond the wallet);
   - expiry-day gamma within the owner's "only till 1–2 pm" rule (SN10 was a single small test).
6. **Accepting flat days:** a valid answer may be that the best action on most empty days is no trade. It must still be proven against a candidate that loses less than its costs.

---

## 5. Constraints a solution must respect

- **Money:**
  - wallet ₹30,000 (₹15–20k variants for comparison);
  - options only (no futures; option selling only with defined risk and real Zerodha margin checked);
  - one position at a time, shared with SN Gold (Gold has priority when it signals);
  - a 20% day loss limit.
- **Trading window:** non-expiry days 09:15–15:15; expiry days only until 13:00–14:00 (the owner's rule).
- **Costs:** Zerodha's current charges + ₹205 per lot per trade stress (multi-leg: per leg); results also at +₹0 and +₹400.
- **No loss-reaction blocks** (the owner rejects "stop trading after a loss" rules). Risk is limited by size and the day limit only.
- **Paper first:** nothing goes to real money without a forward pass and the owner's word.

---

## 6. Data available (all sealed, git-ignored, under each study's `_local/`)

| Data | Span | Notes |
|---|---|---|
| NIFTY 1-minute: index, front future, nearest-weekly options ATM±4–8 | Jan 2023 – Oct 28 2026 (742 non-expiry sessions with options; expiry days have no same-day options) | All seen |
| Option OI per strike-minute | Same | Seen (SN09) |
| Daily ADX / DMI / ATR% | All 966 trading days | – |
| N11's real entries and exits | 2023 – Oct 2026 | N11 lab chain reproducible |
| 1-second NIFTY index + opening-ATM CE/PE | Apr 6 – Jul 27, 2026 (archive A) and Jul 28 – Nov 12, 2026 (archive B) | Both now SEEN for empty-day entry rules (SN78/SN79). The download continues before Apr 2, 2026: the next months are the only unseen 1-second test set |
| 10-second expiry days | 56 NIFTY expiry days, Sep 2025 – Sep 2026 | Opening-ATM CE/PE |
| Forward live quotes (Production archive export) | Oct 29 – Nov 12, 2026 | Unseen for SN rules |
| SN76 day labels (Gold outcome, features) | All 742 sessions | `docs/research/fno/2026-11-13-sn76/_local/days.json` |

New series (GIFT Nifty, global indices, Bank Nifty seconds, events calendar) are not in the repo; adding them needs the owner's word and, for ICICI, the download skill.

---

## 7. What a solution must show (acceptance)

1. **A frozen, committed plan before scoring:** hypothesis, rule, grid size, scorer.
2. **Held-out evidence:** LOYO across the four 1-minute years, or a chronological unseen split for 1-second data. Positive held-out net at +₹205, and at least 3 of 4 held-out years positive.
3. **It beats the random NULL** run with the same budget.
4. **It works at every wallet** (A ₹15k, B ₹20k, C ₹30k sized, growth caps), reported with per-year profit, refill, days won / lost / no trade, worst day, and net at the end.
5. **Combined with SN Gold v5,** it adds to v5's held-out results at the deployed ₹30k wallet and does not raise the worst day beyond the 20% limit.
6. **Robust:** positive at +₹400 stress and with entries 1 minute late; not dependent on its best 5 days.
7. **A forward check written in advance,** scored at ≥ 20 trades on sessions after the freeze.

---

## 8. Starting points for the next agent

- **Harness:** copy `docs/research/fno/sn-gold/gold_v5.py` into a new study folder as the lab. Never edit the frozen copies. Run `verify_gold_v5.py` first.
- **Day labels and features:** `2026-11-13-sn76/_local/days.json` (outcome, ADX, DMI, volatility ratio, gap, DTE, range, move, efficiency, first-hour range).
- **The empty-day test harness (1-minute):** `2026-11-13-sn80/sn80.py` (`day_table()`, `or_break_sig()`; exits via `2026-11-12-sn04/sn04.py run_day`).
- **The 1-second harness:** `2026-11-13-sn78/sn78.py` + `sec_data.py` (sealed archives; `sn79.py` is the one-shot unseen scorer pattern).
- **Do not repeat:** any of the 13 approaches in section 3 on the same data. They are documented failures, and re-searching seen data only produces selection luck.

---

## 9. Status after SN92–SN120 (Nov 13, 2026)

Read first: `docs/research/fno/2026-11-13-sn92/README.md`, `…-sn101/README.md`, `…-sn111/README.md`, `…-sn116/README.md`.

**Approaches now also tested and failed** (do not repeat on the same data):
- slow up-drift calls (SN93);
- confirmed failed breakouts (SN94);
- rich iron flies (SN95);
- NIFTY 50 constituent breadth and agreement at 15 minutes (SN96);
- futures-volume confirmation (SN97);
- priced expiry mornings (SN98);
- straddle giveback exits (SN104);
- BANKNIFTY-proxy cancellation (SN105);
- SENSEX transplant (SN106);
- order-book absorption from minute depth snapshots (SN108);
- one-leg and strangle expressions (SN112, SN114);
- volatility filters on Gold (SN113).

**The one real piece of empty-day information:** at 10:00, when realised 1-minute volatility since 09:20 is in the top fifth relative to the ATM straddle's implied volatility, movement persists for the rest of the day.
- The rest of the day's realised ÷ implied is 0.96 vs 0.63 in the lowest decile; correlation 0.47 (SN111).
- A long ATM straddle held to 15:10 beats matched random days, p = 0.002 (SN101).
- It is thin (≈ +₹17k in four years at ₹15k, strict costs) and lumpy (negative without its best 5 days).
- It is the frozen forward watch **SN95-L**. In Gold's wallet it adds +4.6–4.9% at ₹30k and fails the Gold v6 bar (SN110).

**What the evidence now says about the problem itself:**
- **Gold's edge is its entries:** v5 beats all 400 random-entry versions of itself (SN119).
- **Extra capital earns about 27× more inside Gold** than in the best empty-day companion (SN116).
- **Costs are realistic:** real spreads match the model, and paper fills pay about the ₹205 stress (SN109, SN115, SN117).
- **Conclusion:** the empty-day problem is not solvable with NIFTY price, volume, depth, constituents or SENSEX at the resolutions available. The best empty-day action remains no trade, keeping capital ready for Gold.

**Still open:**
1. the straddle watch with next-week expiries (SN103: half the decay per rupee; needs NIFTY next-week minute history);
2. real broker fills, for cost calibration.

Both need the owner's word.

## 10. Status after SN121–SN200 (Nov 13–14, 2026)

**What the empty days are** (SN186, 594 empty vs 111 Gold days, development):
- weak-trend days: yesterday's ADX 20.8 vs 28.3;
- quieter openings: OR30 0.37% vs 0.43%;
- calmer VIX: 0.98 vs 1.02 of its median;
- smaller ranges: 0.77% vs 0.85%;
- they end flat: open → close +0.03% vs −0.32% on Gold days;
- they still move about 0.5% after 10:00, in both directions.

**Everything tried since SN121, all held out against random nulls:**
- partner-style scalping, overnight and last-half-hour plays, morning crush;
- the Smart Sentinel learners (LightGBM over 234k minute decisions, 1-second and order-book learners);
- the hot-day program;
- the daily-wage program (wage lock, cheap contracts, capital ladders, triple-barrier ML, learned exits, an online bandit);
- the empty-day leg program: both sides at 09:20, small fixed targets, an iron-fly seller, a volatility-regime leg, LSTM entry / volatility / direction, a stack.
- **None is profitable held out.** The learners' honest answer is to sit out.

**The one 2023–26 edge failed the unseen year:** volatility persistence (SN95-L, SN171: a busy morning keeps the day busy) lost on NIFTY Apr–Dec 2022 (SN196).

**What could still change the answer** (new information, not new searches):
1. order-book flow from the tick recorder (from Nov 16);
2. SENSEX as a second index (a SENSEX lab on the unseen Oct 2024 – Apr 2026 data);
3. event days (RBI, budget, global cues) as non-price information;
4. older NIFTY history (2020–2022) for more hot days.

Until then the best empty-day action remains no trade. A daily income comes from paying out Gold's lumpy profit (SN177's salary account).

## 11. Status after SN201–SN210 (Nov 14, 2026)

- **New perspective tried:** hold an option *sale* for the whole weekly expiry, so costs are paid once a week. Calm days are when sellers get paid.
- **Development (NIFTY 2022–26):**
  - protected sellers lose (0 of 78);
  - the unprotected seller earns in every year (+₹3.14 lakh per lot) and turns Gold's 55 green days into 380.
- **Unseen data:** it lost on TEST and on both new exams (NIFTY Dec 2021 – Mar 2022, SENSEX Oct 2024 – Apr 2026): −₹1.22 lakh in 96 weeks. Shock weeks decide, and no forecast (HAR, LightGBM, LSTM) sees them coming.
- **Still open:**
  1. order flow from the tick recorder (from Nov 16);
  2. full option chains far from the money (cheap far wings were not in the downloads);
  3. event days as non-price information;
  4. NIFTY 2020–2021 history (probe first).
- Until then, no trade remains the best empty-day action. A daily income comes from Gold's profits (SN177).

## 12. Status after SN211–SN220 (Nov 14, 2026)

- **Smart fail-safe exits for the weekly seller,** each checked minute by minute: strike-break, loss stop, profit take, crash speed, buying protection, the event calendar, and an expiry-day gate.
- **Development:** the gate keeps 97% of the profit and cuts the worst month by 37%.
- **The three samples where the seller lost:** no exit makes it profitable (−₹71k to −₹1.57 lakh over 96 weeks). Gaps at the open cannot be exited, and exits cannot create an edge.
- **No Gold v6.** Empty days stay flat; a daily income comes from Gold's profits (SN177).
- **What is left:** new information (order flow from the tick recorder) and a true crash test (NIFTY 2020) for any future seller.

## 13. Status after SN221–SN230 (Nov 15, 2026)

- **A candidate exists for the first time: WK-H, the hedged weekly straddle.**
  - It sells the ATM straddle (2 lots) at the first 15:15 after the last weekend before expiry.
  - It delta-hedges with NIFTY futures in half-lot steps every 15 minutes.
  - It holds to settlement.
- **Results:**
  - positive on three of the four seen samples (TEST −₹2.4k over 7 weeks);
  - on the **unseen NIFTY Oct 2020 – Nov 2021 exam: +₹61,511 per lot, worst month −₹6,251**, where every unhedged seller lost.
- **On Gold's empty days** it averages ₹386 a day for the ₹5 lakh unit, paid in weeks rather than days (about 59% of weeks win).
- **With Gold** (2023 – Aug 2026, per option lot): +₹8.17 lakh vs +₹6.42 lakh, 282 green days vs 55, worst month −₹28k vs −₹38.5k.
- **Limits:**
  - about ₹5 lakh margin (unverified);
  - about 4.7 futures orders a week;
  - one unseen sample in a bull market;
  - the crash test (Jan–Sep 2020) is pre-registered;
  - forward paper is the next step, on the owner's word.
- Full record: `docs/SN_WEEKLY_SELLER_AND_GOLD_V6.md` section 0.

## 14. Status after SN231–SN250 (Nov 15, 2026)

- **Gold v6 (Gold v5 + WK-H) is built in Dev** (`python-engine/sn_wkh.py`, paper). **Gold v7** is the same leg with hedge band 0.8: 33 of 46 months positive against 31, worst month −₹28,981 against −₹38,228.
- **The empty days now carry WK-H.**
  - Gold v7's remaining bad months come from WK-H's quiet or sudden-move weeks (9) and Gold v5's own losing months (4).
  - Every month positive was not reached; trend filters, skips, more legs and month rules did not help.
- **Open:**
  - the 2020 crash test (pre-registered);
  - a forward paper record;
  - a cheaper synthetic options hedge, the best next idea;
  - Gold v5's own unseen-year test.
- Record: `docs/research/fno/2026-11-15-sn231/README.md`, `docs/SN_WEEKLY_SELLER_AND_GOLD_V6.md` section 00.

## 15. Status after SN251–SN275 (Nov 16, 2026)

- **The owner's new constraint:** a gap-day leg must use Gold v5's own wallet, with no margin and no unlimited loss: bought options, or defined-risk spreads as information.
- **Two new unseen buyer exams:** NIFTY Oct 2020 – Mar 2022 (286 sessions) and SENSEX Oct 2024 – Apr 2026 (306). Neither had been used for any intraday or overnight buyer rule.
- **Nothing passed:**
  - options-only WK-H (wings instead of futures) loses on 4–5 of 5 samples in every structure;
  - SN95-L / SN171 fail both exams;
  - buying every day loses ₹150–660 per lot per day;
  - weekend and overnight holds, multi-session swing, calendar and events, opening gaps, the cheap weekly straddle, a LightGBM move-size model, gap-day afternoons and an overnight cash ETF all fail their frozen rule;
  - pre-holiday calls were positive on all four samples but failed the null as a post-hoc pick (about 10 trades a year).
- **NIFTY's overnight drift is real** (close to open, t up to 6), but it sits in the closing and opening prints. Options (decay) and an ETF (charges, the DP fee) cannot collect it at the tradeable 15:20 and 09:16+ prices.
- **Do not repeat** any SN251–SN272 rule on these samples.
- **Still open:**
  1. order flow from the tick recorder (live from Nov 16);
  2. the 2020 crash test for WK-H;
  3. a wage pot paid from Gold's profit (SN269: ₹500–750 a session over years, with ₹0.5–3.1 lakh advanced first).
- Record: `docs/research/fno/2026-11-16-sn251/README.md`.

## 16. Status after SN276–SN285 (Nov 16, 2026)

- **Every earlier gap-day signal, combined on 1,465 pooled sessions** (NIFTY Oct 2020 – Oct 2026 + SENSEX Oct 2024 – Apr 2026), does not make a buyer profitable:
  - walk-forward LightGBM learners: −₹1.3 to −₹1.8 lakh, 2–4 of 10 half-years positive;
  - a seven-signal vote: −₹973 pooled, negative at ₹400.
- **The 10:00 option's cost** (₹200–650 a day on average) exceeds what the information predicts.
- **The one buyer signal positive on all four samples:** calls on the session before a weekday market holiday (ITM +₹46.7k over 73 trades). It is post-hoc, fails the null, and trades about 10 times a year.
- Record: `docs/research/fno/2026-11-16-sn276/README.md`.

## 17. Status after SN286–SN300 (Nov 16, 2026)

- **The corrected holiday-call rule** (weekday full sessions only, executable exits) is positive on all four samples, but each is carried by its best day. It is a forward ledger (SN298), not a strategy.
- **The partner's first minute** does not survive executable prices (SN288). Their green days were lost to trades added after the give-back alert (SN287).
- **The real cost of one ATM lot round trip** is ₹90–100 (SN290).
- **The remaining untested information is packet-level order flow** from the tick recorder (live from Nov 16). Two candidates (SN291 futures pressure, SN293 lagging strike) are frozen for a 20-session forward verdict (`docs/research/fno/2026-11-16-sn286/fwd.py`, about Dec 17–19).

## 18. Status after SN301–SN315 (Nov 16, 2026)

- **The forward test is protected:** verified archive, executable fills and stops, provable Gold day labels, matched controls and an amended verdict that cannot pass on missing evidence (`docs/research/fno/2026-11-16-sn301/fwd2.py`). Session 20 is Dec 23.
- **Gold v5's own losses are signal losses**, capped at the day room (SN310). Stops, adds, costs at real prices and the scale-in cash check are sound at its sizes (SN311, SN312), so no execution fix can cut them. A gap-day leg must add new information, not better plumbing.
- **A one-minute delay costs at the entry, not the exit** (SN306). Any gap-day buyer needs a price-protected entry.
- **From Dec 7** F&O trades to 15:45 and expiring index contracts stop at 15:30 (SN314). Any rule using the last minutes must be date-aware.

## 19. Status after SN316–SN330 (Nov 16, 2026)

- **Seconds clocks add no edge.** The partner's 1-minute level, 30-second hold and 5-second pullback were tested on one-second data (development Apr–Nov 2026; the unused Jan–Apr 2026 window scored once). Every arm lost about the option round trip on every trade, and the five-second pullback was slightly worse than entering on the break. Only 12–20% of breaks ever offered ₹750 net even in hindsight.
- **Short breaks revert.** A one-minute break-and-hold lost on unseen 2019 as on 2022–26, below every random book.
- **WK-H survived the 2020 crash** (+₹42,570 per lot; March −₹23,171), but it needs margin.
- **For a no-margin gap-day leg the remaining open question** is the packet-level forward test (SN300a / `fw3.py`, after Dec 23).

## 20. Status after SN331–SN365 (Nov 16, 2026)

- **After-move entries are worse than random at every clock** (SN331 / SN344). Failed breaks reverse only 0.5–2.1 index points.
- **The opening auction's direction is information, but it is already in the price** (SN353 (b): +₹183 gross a trade, −₹30 at ₹205). Opening premium is rich by about ₹80–130 a leg by 10:15 (SN361).
- **No entry state for a bought option has room at ₹205** (SN351). The hindsight best exit averages about ₹1,050 a lot, but fixed-horizon payoffs are −₹90 to −₹370 gross.
- **Ideas needing data this PC lacks:** GIFT NIFTY residuals, RBI surprises, BANKNIFTY / bank constituents (SN354–SN356). BANKNIFTY's ATM lot (30) fits the ₹15k room only in its last week. A download is the owner's call.
- **Still open, forward only:**
  - the auction queue pressure and a mid-gap watch (`sn351/fw5.py`, with SN300a after Dec 23);
  - the CAS 2.0 closing window from Dec 7 (`sn351/fw6.py`; needs the recorder to 15:46, SN329 not deployed).
- **The wage comes from Gold's capital** (SN352 / SN363): ₹785 a session on average at ₹205, in lumps. A never-failing ₹750 a session needs about ₹3.7 lakh.

## 21. Status after SN366–SN380 (Nov 16, 2026)

- **Opening entries:** the opening direction is real for 20–30 minutes and has no value left at 10:15 (SN371). An in-the-money leg keeps ₹55–110 more of it at 09:16: +₹67 at ₹205 on 171 auction sessions, 2026 only, frozen forward in `sn366/fw7.py` (SN376 / SN380). Opening premium richness grows with the overnight IV jump (SN377).
- **Chain pressure:** wings, synthetic forward, signed flow and expiry pairs are followed by only 3–9 bp over 15–30 minutes (SN368 / SN372 / SN378 / SN379). That is below a bought option's hourly cost of ₹300–850.
- **Bracket and limit:** a visible ₹750 is lost on the 58% of positions that time out at −₹851 (SN367). A resting limit order saves ₹18 but misses the winners (SN373).
- **Gold on unseen 2022:** −₹15,281 from ₹30k (4 of 12 months positive), like its first development year 2023 (SN366). A losing first year must be expected.
- **Blocked or closed by the data:** Hong Kong's 10:30 reopen shows no extra NIFTY move (SN370). NIFTYBEES needs a recorder subscription (SN369).

## 22. Status after SN381–SN395 (Nov 16, 2026)

- **The opening trade, made honest** (the walked cost within ₹15,000, a capped limit, a signal received before 09:16, paired controls), is break-even: +₹46 a session at ₹205, −₹7 without the best day, −₹137 at ₹400, and −₹447 after NSE's Sep 7 auction change (SN382). Choosing an in-the-money option over ATM is the robust part (+₹122 a trade, mostly a larger delta; SN383).
- **One promising combination:** the auction direction, ITM, on cheap overnight opens (+₹396 / +₹199 per session over 73 sessions, permutation p 0.031, the best of ~10 splits). Frozen forward in `sn381/fw9.py` (SN394).
- **Closed:** the 09:36 exit, cash-auction agreement (coverage), auction size, indicative drift (too few).
- **Signed option flow** is now measurable from tick packets (92% of volume signable), forward in `sn381/fw8.py`.
- **The wage:** from ₹60k, profit-only pays about ₹525 a session on a bad start, with dry spells up to 21 months. A fixed ₹750 a session needs ₹2–5 lakh of the owner's own money in the first years (SN389 / SN395). Gap-day trading would have to earn at least the shortfall after costs on every empty day; nothing so far comes close.

## 23. Status after SN396–SN410 (Nov 17, 2026)

- **The opening trade, on the real clock** (a 09:16:00 decision at the 09:15 bar's close), loses −₹81 a session at ₹205 and −₹235 at ₹400 (SN396). The earlier +₹46 came from a one-minute label lead in the minute data.
- **No affordable option breaks even on the opening move.** It needs about 13 index points within the hour; the gap direction's expected follow-through is about 1.3 (SN399). Since NSE's Sep 7 change, the follow-through is spent before 09:16:00 (SN410).
- **"Cheap" overnight opens are better mornings than the rest,** but the edge isn't proven:
  - the White reality check over the 24-rule family gives p 0.80;
  - the continuous measure has no slope, and the label is tangled with the calendar;
  - it fails on 2022–2025 gap days (SN397 / SN406 / SN407).
  It stays a forward test only (fw9 / fw9a).
- **Coverage routes are closed:** roll days (the lot is rarely affordable), SENSEX on NIFTY's skip days (−₹547 a session on NIFTY expiry days), RBI release days (3 events, all stopped) (SN398 / SN401 / SN402).
- **Gold covers 17% of sessions** and pays ₹791 a market session at ₹205 (₹409 at ₹400) from ₹30k (SN405). Empty days would need +₹412 each at ₹400 to reach ₹750 a session. Nothing found in 410 slots comes close.

## 24. Status after SN411–SN425 (Nov 17, 2026)

- **The days are not empty of opportunity.** With hindsight, one affordable NIFTY lot could have made a median ₹9,376 on every one of 42 real-quote days. From fixed clocks with a 60-minute window, the best contract reached ₹750 in 83–97% of cases (SN412). The open problem is selection (side and exit), not instrument or wallet.
- **Gold's empty days are a signal shortage.** Gold takes every N11 / R0.85 signal it gets. 730 of its 932 replay sessions have none, and its replay leaves out NIFTY's expiry days, 263 of 1,195 sessions (SN422).
- **Per real market session Gold makes ₹617 at ₹205 and ₹319 at ₹400** from ₹30k. To reach ₹750 a session at ₹400, each of the 1,034 non-Gold sessions would need about +₹498.
- **Other venues:** BANKNIFTY's ATM fits ₹15k mainly in its last five sessions before monthly expiry (93%; 30% of all sessions). FINNIFTY is thin and NIFTYNXT50 is untraded (SN413).
- **A bank-sector residual reverses rather than persists** (SN414). It is pre-registered forward as F1 once BANKNIFTY quotes are recorded.
- **Still closed:** company results and USDINR lack data on this PC (SN415 / SN416); RBI days are too few (SN402).

## 25. Status after SN426–SN440 (Nov 17, 2026)

- **What a signal must do.** With hindsight over one decision at a time (SN428), a one-hour 1-ITM trade from a coin-flip side loses ₹169 a decision at ₹205. It needs about 56% directional accuracy at ₹205, and about 68% at ₹400, to break even. The best entry minute within ±30 minutes is the single most valuable decision.
- **NIFTY's expiry mornings, a fifth of all sessions, are not a hidden Gold opportunity.** Gold's own signal fires on about 7 of them a year, and the few priced cases lose (SN427).
- **Gold's realistic income is about ₹617 a real market session at ₹30k (₹205 stress).** Production's paper fills cost only a median ₹6.5 a lot more than the model (SN440). The gap to ₹750 is about ₹154 per non-Gold session.
- **No simple exit, feed or size rule improves Gold in both its unseen year and its development years** (SN429 / SN434 / SN436–SN439b).

## 26. Status after SN441–SN455 (Nov 17, 2026)

- **The direction bar on Gold's empty days is about 62% at ₹205 and 77% at ₹400** for a one-hour 1-ITM option (SN441). The gross coin is already negative there (spread plus decay).
- **Timing headroom exists only in hindsight** (about ₹1,000 a decision). Waits, discounts, limits and resting bids all lose (SN442 / SN443 / SN453 / SN454). Gold's own entries must stay immediate.
- **No outside information clock was found.** Bank results are insufficient, there is no London clock and no expiry pin. Expiry-afternoon momentum is real-looking but does not pay (SN447 / SN448 / SN451).
- **Gold is honest but lumpy.** Its replay is future-blind (SN452), and ₹205 covers its cost at 6 lots (SN445). In 2023–26 it pays ₹750+ on 6.2% of sessions, its best 5 days are 41% of profit, and it went 226 sessions without a new high (SN450).
- **Development results have predicted almost nothing** (SN455: 5 of 19 pairs kept their sign). New ideas go to frozen forward tests, such as `fx5` (SN444).

## 27. Status after SN456–SN475 (Nov 17, 2026)

- **Capacity is not the constraint.** Gold is clear at 10:00 on 98.8% of its replay days and enters inside the next hour on 1.3% (SN461).
- **Skill is the constraint.** A 10:00 one-hour 1-ITM buyer needs a forecast correlated about 0.2 with the next hour's move to break even at ₹205 (0.1 trading only the top 30%), and about 0.31–0.37 for ₹154 a market session (SN475). Nothing built so far exceeds about 0.1, and its confidence did not map to cash (SN462).
- **No new information source helped.** Participant positioning (SN456 / SN473) and Kronos (SN458: Kronos-small zero-shot forecasts the next half hour worse than no change (MAE 37.8 against 13.2 bp)) add nothing. FII cash is blocked (SN466) and bank filings are too few (SN457).
- **The forward verdicts are low-power screens** (SN469 / SN472). Only paired designs such as fx5 separate an edge from none at their horizons.

## 28. Status after SN476–SN490 (Nov 17, 2026)

Gold v5, the benchmark the gap is measured against, loses on its never-run sample (NIFTY Jan 2020 – Aug 2021: −₹64,783 @205 from ₹30k) and has lost in four of seven years; across 2020–26 its ₹30k book averages ₹612 a replay session @205 and one lot ₹11 @400. The ₹154-a-non-Gold-day hurdle assumed Gold's 2023–26 rate; on all years Gold itself is far from ₹750 a session. No challenger beat Gold on any of the round's ten mechanisms. Gold's forward record (`fw10.py`, 585 market sessions from 2026-11-18) decides whether the edge is real. See `docs/research/fno/2026-11-17-sn476/README.md`.
