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
