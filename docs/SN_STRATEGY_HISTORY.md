# SN strategy history: the owner's small-wallet F&O book, SN01 → SN90 and SN Gold v5 (complete record, Nov 12–13, 2026)

This is the one document to read to continue the SN work after a context reset. It records:
- what the owner asked for, in their words;
- every rule the owner set;
- every SN study, with its result and lesson;
- the SN Gold versions and their frozen configs;
- the Production deployment;
- where all data and code are;
- what is pending.

Everything is research in the Dev checkout (`C:\Users\Urveesh\Desktop\trading-sentinel`), branch `codex/production-correction-hedge-p0`, except the one Production deployment in section 7.

---

## 1. Current state, in one paragraph

**SN Gold v5 runs in Production on PAPER since Nov 13, 2026** (release `82b08371`, PR #137).
- It is `python-engine/sn_gold.py`: it follows N11's live paper record and places no orders.
- **Wallet:** starts at ₹30,000; 20% day loss limit; losing days refilled; +50% wallet after net profit equal to the wallet, at most 3 steps (₹1,01,250).
- **Research expectation (in-sample):** about +₹8.5 lakh over Jan 2023 – Oct 2026 from ₹30k, worst day about −₹21k, about 1 trade every 5–6 sessions.
- **The days Gold sits out:** about 84% of sessions. SN76–SN90 showed they have **no intraday edge** we could find (buying, selling, 1-minute, 1-second, web rules). **Recommendation: stay flat on them.**
- **Frozen, verifiable configs:** `docs/research/fno/sn-gold/` (v3, v4, v5), with git tags `sn-gold-v3`, `sn-gold-v4`, `sn-gold-v5`.

---

## 2. What the owner asked for (timeline, owner's words where quoted)

1. **Nov 12, SN01: the idea.**
   - "SN01 … specifically for the small amount … ₹15,000".
   - Earn "exactly 10% … post charges", then "we sell all … end the trading … for the day".
   - "Risk amount will be 20% of the total wallet". Profits never reused; losses refilled ("same consistent wallet").
   - After 100% profit the wallet grows 50%. The target grows 50% every 2 (or 3) wallet increases: "test both ways".
   - Idea: a lock at 10% instead of selling.
   - Runs beside N11/N012 (the ₹2.5 lakh paper book), never replacing it.
   - "Quick entry quick exit", "learn from N08 … N012", "genome … iterations", and report the total profit, losing days and wallet increases.
2. **Nov 12, SN02:** "not fixated on one minute data … 10 seconds whatever … get it profitable … learn from N012 … if we stop increasing the wallet … and just continuously farm" the minimum.
3. **Nov 12, SN03:** "now we have a benchmark … stop after 3rd, 4th, 5th … fewer losing days … tell me losing / winning / no-trading days … fast entry exit even if it earns less … latest Zerodha rates"; "how much I had to refill".
4. **Nov 12, SN04:** "why do we have so many none days? … not a filter system but a smart trading sentinel … more active … table for multiple stops for multiple strategies".
5. **Nov 12, SN05–SN07:** "SN04 … you don't have to follow all the rules of N11 … learn from it".
6. **Nov 12, SN06+:** "N11 entry was Gold not the exit … SN06 should be miles better … entry is the exact thing".
7. **Nov 12, SN09:** use the 10-second data; web allowed.
8. **Nov 12, SN10–SN15:** trade expiry days "only till 1 o'clock or 2 o'clock"; "six iterations".
9. **Nov 12, every wallet:** "the different wallet sizes should be done every time, not a different strategy … every SN strategy should teach you something".
10. **Nov 12, SN Gold:** "the best one … will be called SN Gold"; "do it till SN 30".
11. **Nov 12/13, SN31–SN50:** "store the Gold … to ensure that our experimentations do not change that and we are able to roll back"; "till SN 50".
12. **Nov 13, SN51–SN75:** "the starting amount I can change … 20,000 or even 30,000"; "is it because of the hard cap at profit"; "show me the net profit at the end"; "25 more … meaningful … quality".
13. **Nov 13, deploy:**
    - "whatever configuration … of the best Gold … set it up to run tomorrow as an independent module … push that merge that and deploy it in production … restart and rebuild everything right away";
    - "whatever the refill thing is, you have to tell me";
    - then "if you think 30,000 starting amount is better … fine with that".
14. **Nov 13, SN76–SN100:**
    - "clustering, identify the commonality of the days where Gold made profit … loss … why Gold did not trade";
    - "for those days … employ some other strategy … one second data";
    - "make profit in those days, not losses".
15. **Nov 13, the 1-second data:**
    - train on the **Nov 13 archive** (Apr–Jul 2026), test on the **Nov 12 archive** (Jul–Nov 2026).
    - "I don't mind the amount of time needed as long as correct good quality testing is done".
16. **Nov 13, SN80–SN90:** "search on the web … how do we earn money quick quick exit … why is it losing … learn from mistakes … SN80 to 90 … the last few based on the learnings".
17. **Nov 13:** "create a very very comprehensive big document" (this file).

---

## 3. The rules every SN study follows

- **Wallet:**
  - fixed, or growing by the owner's rule: +50% after net profit equal to the wallet; "stop after step k" caps size;
  - profits are banked; a losing day is refilled (refill = the sum of losing days);
  - net at the end = won on winning days − refilled.
- **Day loss limit:** 20% of the wallet. It is enforced as a stop price on the option, so a gap can fill slightly beyond it.
- **Costs:**
  - Zerodha's current F&O charges (checked against zerodha.com/charges on Nov 12, identical to `fno_costs`): ₹20/order, STT 0.15% sell, NSE 0.03553%, SEBI ₹10/crore, stamp 0.003% buy, GST 18%, IPFT;
  - plus a slippage stress of **+₹205 per lot per trade** (the house standard), with ₹0/₹100/₹300/₹400 or a % of premium as checks.
- **Fills:** bid/ask = close ± half the archive's 75th-percentile spread; stops win same-minute ties; executable prices only.
- **Every SN at every wallet** (owner's order, Nov 12):
  - A: ₹15k, 1 lot;
  - B: ₹20k, 1 lot;
  - C: ₹30k sized;
  - growth from ₹15k stopped after 0, 2, 3 or 5 steps;
  - per-year profit / refill, days won / lost / no trade, worst day, net at the end.
- **Honesty:**
  - freeze before scoring (commit the plan or script first);
  - choose on 3 years and score the 4th (leave one year out);
  - random-entry NULL;
  - all NIFTY years 2023 – Oct 2026 are seen, so in-sample results are description, not proof;
  - forward or unseen checks are the only real tests.
- **Data:**
  - never read Jan–May 2022 NIFTY (sealed exam) or NIFTY 2023 counts beyond what the skill prints;
  - every ICICI download goes through the `breeze-history-download` skill;
  - never touch the live download DB; research uses sealed copies.
- **Production:**
  - assess Production, change Dev, promote through GitHub; never edit Production directly;
  - no Production writes mid-day; real money only on the owner's word.
- **Docs ritual:** each study's README, plus sections in SYSTEM_GUIDE / NEXT_AGENT_PLAN / HANDOVER, staged byte-safely without touching the other agent's unstaged edits (50/42/40 lines).

---

## 4. Data and code inventory

| What | Where |
|---|---|
| NIFTY 1-minute sealed year datasets (2023, 2024, 2025, Jan–Oct 28 2026) | `docs/research/simulation/2026-11-01-fno-n08/_local/dataset-nifty-2023`, `docs/research/fno/2026-10-30-day-router/_local/dataset-nifty-2024`, `docs/research/fno/2026-10-30-nifty-2025-test/_local/dataset-nifty-2025`, `docs/research/fno/2026-10-29-year-genome/_local/dataset-nifty` |
| SN minute caches (742 non-expiry sessions with options) | `docs/research/fno/2026-11-12-sn01/_local/cache-<year>.pkl` (`sn01_data.py`) |
| Option OI caches | `docs/research/fno/2026-11-12-sn09/_local/oi-<year>.pkl` |
| Daily ADX/DMI (all 966 trading days) | `docs/research/fno/2026-11-12-sn06/_local/daily.json` |
| N11's stored replays (entries/exits per year) | `docs/research/simulation/2026-11-02-fno-n11/_local/evals`, keys in `keys-panel-<year>.json` |
| 136-strategy library replays (2024–2026) | `docs/research/fno/2026-10-30-day-router/_local/results-raw-*.json` |
| 10-second expiry-day data (56 NIFTY expiry days) | `docs/research/simulation/2026-11-03-expiry-year/_local/data` |
| **1-second archive A** (training): Apr 6 – Jul 27, 2026, 77 sessions, index + opening-ATM CE/PE | original `C:\Users\Urveesh\sentinel-operations\breeze-history-20261029\data\nifty-daily-1second-20261113.zip`; sealed copy `docs/research/fno/2026-11-13-sn78/_local/` (sha `6b5b68fb…`) |
| **1-second archive B** (test): Jul 27 – Nov 12, 2026, 76 sessions | original `...\data\nifty-daily-1second-20261112.zip`; sealed copy same folder (sha `95a29a54…`) |
| Run receipt of archive A | `...\run-logs\RUN_RECEIPT_NIFTY_DAILY_SECONDS_20261113.json` |
| Forward quote export (Oct 29–Nov 12, unseen for SN) | `C:\Users\Urveesh\sentinel-operations\fno-forward-panel-20261028\docs\research\fno\2026-10-28-forward-panel\_local\exports\20261112T103005Z` |
| Simulators and harnesses | `2026-11-12-sn01/sn01_sim.py` (minute sim), `2026-11-12-sn03/sn03.py` (N11 entries in a wallet), `2026-11-12-sn04/sn04.py` (index exits), `2026-11-12-sn19/gold.py` (Gold harness), `2026-11-13-sn51/lab.py` (latest lab), `2026-11-13-sn78/sn78.py` (1-second book) |
| Frozen Gold configs | `docs/research/fno/sn-gold/`: `gold_v3.py`/`gold_v4.py`/`gold_v5.py`, `SN_GOLD_V3.json`/`_V4`/`_V5`, `verify_gold.py`/`_v4`/`_v5` (all three reproduce), `FORWARD_V4.md`, `FORWARD_V5.md` |

---

## 5. Every SN study (folder `docs/research/fno/<folder>`)

### SN01–SN09: the small wallet and entries

| SN | Folder | Idea | Result | Lesson | Kept |
|---|---|---|---|---|---|
| 01 | 2026-11-12-sn01 | The owner's 10%-a-day book: 21,066 rule sets (ORB/MOMO/TPB/VWAPX/EMAX/FADE/PDX), premium exits, 10% target, 20% loss | **NOT PROVEN.** Held out 0/4 years positive, −₹1,22,146 vs random −₹1,35,115. Final pick (one trade a day + lock): +₹44,503 at +₹0, −₹13,803 at +₹100. Target days 69/742 | Entries ≈ random; costs ~₹85–120/lot/trade; more trades = more loss; a random side reaches +₹1,500 first 54% of days and still loses ₹1.79 lakh | Lock idea |
| 02 | 2026-11-12-sn02 | N11's own entries + exits inside the ₹15k wallet (parity exact) | **+₹1,06,990** (OTM substitute when unaffordable); the 10% cap cuts it to +₹11,240; long strangles dead (0/648) | N11's profit is in a few big days; never cap them | **Benchmark** |
| 03 | 2026-11-12-sn03 | 66 variants: filters, quick profit, breakeven, trails, sister books, no-new-trade at +10%, strike shifts, 2 lots, confirmation, leave-if-not-working | None beats the benchmark held out. Quick profit +₹500 = 73 winning days but −₹25,412 | Fast exits lose | Benchmark +₹1,11,995 (55/63/624 days, refill ₹91,635) |
| 04 | 2026-11-12-sn04 | Active entries with N11-style index exits (15,600 sets) | Held out −₹1,51,769 vs random −₹1,42,961 | The edge is N11's entry selection, not exits | No |
| 05 | 2026-11-12-sn05 | Fill empty days from the 136-strategy library | N11 alone +₹1,19,054 (2024–26); next best +₹20,426; mix held out +₹1,08,411 | Nothing adds | No |
| 06 | 2026-11-12-sn06 | N11's ingredients rebuilt (5-min setups, ADX gate, DMI) without big-money rules | Held out −₹62,251 (beats random −₹1,50,624 but loses); combo held out +₹68,243 | – | No |
| 07 | 2026-11-12-sn07 | The real N11 engine with big-money rules off | +₹90,287 vs +₹1,11,995 (extra trades are 2023 losers); zero-delay entry no gain | The stand-aside protects | No |
| 08 | 2026-11-12-sn08 | N11's quality rules relaxed (stretched, low-day direction, 14:00 cutoff) | All worse (all relaxed −₹23,477) | Quality rules are the gold | No |
| 09 | 2026-11-12-sn09 | Option OI entries; OI as a filter | Entries held out −₹1,80,378 vs random −₹1,57,721; filter held out +₹71,964 | OI is no edge | No |

### SN10–SN30: wallets, exits and SN Gold v3

| SN | Folder | Idea | Result | Lesson | Kept |
|---|---|---|---|---|---|
| 10 | 2026-11-12-sn10 | Expiry mornings on 10-second bars (56 days) | Pick +₹10,506 → −₹20,705 | – | No |
| 11 | 2026-11-12-sn11 | Exit before the dip | All worse; held out = benchmark | – | No |
| 12 | 2026-11-12-sn12 | Wallet sizes | ₹20k 1 lot +₹1,24,093 (buys N11's own contract) | – | Yes |
| 13 | 2026-11-12-sn13 | Second lot only on high-volatility days (₹30k) | +₹2,08,778, refill ₹1,55,737; 10% day limit worse | – | Yes |
| 14–15 | 2026-11-12-sn14 / sn15 | Growth caps per year; FORWARD A/B/C frozen | Tables in sn15/README | – | – |
| 16 | 2026-11-12-sn16 | Keep winners past N11's clock (3-ATR trail) | Growth held out +₹2,37,980 vs +₹2,01,565 | – | **SN Gold** |
| 17 | 2026-11-12-sn16 | Re-enter after winners | Loses | The move is done | No |
| 18 | 2026-11-12-sn16 | Size by days to expiry | Worse | Volatility is the size signal | No |
| 19 / 19b | 2026-11-12-sn19 | Strike by setup / **ITM when affordable** | 19b better at every wallet, held-out pick every fold | – | **v2** |
| 20–23 | 2026-11-12-sn19 | Second chance after a loss; time-of-day / recent-form / gap sizing | All worse | – | No |
| 24–25 | 2026-11-12-sn19 | Insurance hedge; debit spreads | Destroy profit | – | No |
| 26 | 2026-11-12-sn19 | Robustness (+₹300/400, 1-minute-late entries) | Survives | – | – |
| 27 | 2026-11-12-sn19 | Scale-out | Worse | – | No |
| 28 | 2026-11-12-sn19 | **Scale-in at +10%** (day-limit fix) | G3 +₹3,25,635, held out 4/4 | – | **v3** |
| 29–30 | 2026-11-12-sn19 | All lots every day (optional); v3 forward frozen | – | – | – |

### SN31–SN50: tuning and SN Gold v4 (2026-11-13-sn31)

| SN | Idea | Result | Lesson | Kept |
|---|---|---|---|---|
| 31–32 | Extension threshold and trail width | Plateaus at 25% and 3 ATR | v3 is not a knife-edge | – |
| 33, 38 | Deeper ITM | Deeper pays when money per lot allows | – | – |
| **43** | **ITM depth by money per lot** (<₹17.5k → 1, <₹20k → 2, else 3) | A unchanged; B +₹1,59,282 (held out 4/4) | – | **v4** |
| 34–37, 40–41 | More scale-ins, restricted scale-ins, volatility line, intraday-volatility sizing, day limit, trades/day caps | Not better | – | No |
| 39, 48 | Growth step ×2 / trigger 50% | Owner levers. Trigger 50%: G3 +₹3,53,995, same worst day | – | Lever |
| 42 | Start ₹20/25/30k | Scale | – | Lever |
| 44 | Bootstrap risk | ₹15k: 4.7% losing-year chance | – | – |
| 45 | Best days | 10 best days ≈ 77% of profit | Never cap winners | – |
| 46 | 2023 | 2023 = TPB's bad year | – | – |
| 47 | Robustness | Fine | – | – |
| 49–50 | v4 frozen | – | – | – |

### SN51–SN75: SN Gold v5 (2026-11-13-sn51)

| SN | Idea | Result | Lesson | Kept |
|---|---|---|---|---|
| 51 | "Is the cap costing profit?" | No profit cap exists; "stop after k" caps size; uncapped figures not achievable | – | – |
| 52 | Real account, no refills | ₹15k/20k die in a 2023 start; **₹30k survives** | – | Insight |
| 53–55 | OI / puts / ADX sizing | Lose or not stable | – | No |
| **56** | **N11 + R0.85 entries** | Held out 4/4 at A/B | – | **v5** |
| 57–60 | Day limit 30%; day profit lock; equity-curve sizing; deepest affordable strike | Worse | – | No |
| **61** | **Scale-in at a 1-ATR index move** | Better | – | **v5** |
| **62** | **Pyramid to full** | Better | – | **v5** |
| 63–64 | Hybrid trail; 15:20 hold | No change / worse | – | No |
| 65–66, 68 | Slippage 1–2% of premium, 2-minute delays, partial fills, 15 start quarters | Survives all | – | – |
| 69 | Fair contest | v5 wins held out (A 4/4, G3 4/4, B/C 3/4) | – | – |
| 70–73 | Start × trigger; risk; best days; stress | Below | – | – |
| 74–75 | v5 frozen, report | – | – | – |

### SN76–SN90: Gold's empty days

| SN | Folder | Idea | Result | Lesson | Kept |
|---|---|---|---|---|---|
| 76 | 2026-11-13-sn76 | Cluster Gold's win / loss / no-trade days | 609/620 empty days have no N11 setup; low-ADX days allow only TPB puts (low-ADX up days 0 wins / 179 empty); money = range ≥ 1.3% and down > 0.7% days; empty days = slow up-grinds / narrow ranges | – | – |
| 77 | 2026-11-13-sn77 | Defined-risk selling (iron condors and spreads) on quiet days | Loses even at zero stress (held out −₹51k) | Intraday premium ≈ fair | No |
| 78 | 2026-11-13-sn78 | 1-second book on Gold-free days (choose Apr–May, score Jun–Jul) | Pick +₹13,193 → −₹4,096 | – | No |
| 79 | 2026-11-13-sn78 | **The one unseen test** (train archive A, test archive B Jul 28 – Nov 12, 75 sessions) | All candidates worse than random (TWAP pick −₹28,579, momentum −₹51,078, random −₹7,745) | – | No |
| 80 | 2026-11-13-sn80 | Web claims: narrow CPR → trend day; tight opening range coils | **False on NIFTY.** A **wide** opening range predicts big days (34% vs 8%) | – | Insight |
| 81–84 | 2026-11-13-sn80 | Opening-range break on Gold-free days with web / wide gates | Held out −₹34–40k vs random −₹18–26k | Direction is a coin flip | No |
| 85 | 2026-11-13-sn80 | Gold's second lot by opening-range width | v5's volatility rule picked 15/16 folds | – | No |
| 86–88 | 2026-11-13-sn80 | Puts / opening drive on predicted big empty days | Plain puts +₹18,592 (all 2025); held out −₹38,179 vs random −₹16,292 | – | No |
| 89 | 2026-11-13-sn80 | v5 + best empty-day sleeve | Worse held out | – | No |
| 90 | 2026-11-13-sn80 | Conclusion | Stay flat on empty days; new work needs non-price information | – | – |

---

## 6. SN Gold, version by version (frozen in `docs/research/fno/sn-gold/`)

| Version | Rules (cumulative) | A ₹15k | B ₹20k | C ₹30k | Grow from ₹15k, stop after 3 | Stop after 5 |
|---|---|---:|---:|---:|---:|---:|
| Benchmark (SN02) | N11 entries/exits, 1 lot, OTM substitute, ₹3k day limit | 1,11,995 | 1,24,093 | 2,08,778* | 2,01,565 | 2,79,873 |
| SN Gold | + keep winners ≥ +25% at N11's exit on a 3-ATR index trail; lots floor(W/15k), halved on low-volatility days | 1,13,567 | 1,24,582 | 2,10,231 | 2,40,189 | 3,66,472 |
| v2 | + one strike ITM when every lot fits | 1,26,373 | 1,37,156 | 2,33,031 | 2,65,466 | 4,25,421 |
| **v3** (tag) | + scale-in 1 lot at +10% if the whole position fits the day room | 1,30,530 | 1,38,117 | 2,28,048 | 3,25,635 | 5,41,625 |
| **v4** (tag) | + ITM depth by money per lot (<17.5k 1, <20k 2, else 3) | 1,30,530 | 1,59,282 | 2,27,949 | 3,26,853 | 5,45,819 |
| **v5** (tag, **deployed**) | + R0.85 extra entries + scale-in at a 1-ATR move + pyramid to full | **1,51,155** | **1,76,846** | **2,80,508** | **3,99,906** | **7,41,675** |

\* C is 2 lots on high-volatility days (SN13 rule). All figures: Jan 2023 – Oct 2026, +₹205 per lot per trade, in-sample.

**v5 by year:**

| Wallet | 2023 | 2024 | 2025 | 2026 | Won | Refilled | **Net** | W/L/none | Worst |
|---|---|---|---|---|---:|---:|---:|---|---:|
| A ₹15k | 397 / 26,547 | 52,158 / 15,338 | 48,506 / 36,792 | 50,094 / 22,468 | 2,52,300 | 1,01,145 | **1,51,155** | 58/64/620 | −2,998 |
| B ₹20k | −1,305 / 29,321 | 72,538 / 14,234 | 43,957 / 50,531 | 61,656 / 32,810 | 3,03,742 | 1,26,896 | **1,76,846** | 64/69/609 | −3,997 |
| C ₹30k | −12,107 / 52,422 | 1,15,439 / 25,061 | 70,789 / 67,633 | 1,06,387 / 47,930 | 4,73,554 | 1,93,046 | **2,80,508** | 61/72/609 | −6,110 |
| Grow, stop 3 | 397 / 26,547 | 82,363 / 26,301 | 1,43,065 / 1,22,788 | 1,74,081 / 90,260 | 6,65,802 | 2,65,896 | **3,99,906** | 63/70/609 | −10,119 |
| Grow, stop 5 | 397 / 26,547 | 82,363 / 26,301 | 2,21,056 / 2,30,857 | 4,37,859 / 2,09,027 | 12,34,407 | 4,92,732 | **7,41,675** | 63/70/609 | −22,740 |

**v5 start amount × growth trigger** (net at the end; worst day in brackets):

| Start | Step after 100%, stop 3 | Step after 100%, stop 5 | Step after 50%, stop 3 | Step after 50%, stop 5 |
|---|---:|---:|---:|---:|
| ₹15k | 3,99,906 (−10,119) | 7,41,675 (−22,740) | 4,54,692 (−10,119) | 9,60,885 (−22,740) |
| ₹20k | 5,36,968 (−13,492) | 10,04,746 (−30,320) | 6,53,133 (−13,492) | 13,53,208 (−30,320) |
| **₹30k (deployed)** | **8,50,882 (−21,113)** | 15,51,780 (−45,464) | 9,47,841 (−21,113) | 20,24,800 (−45,469) |

**v5 risk:**
- One year at ₹15k: median +₹36,528, 5th percentile +₹2,690, a 3.5% chance of a losing year, refill median ₹25,053.
- Without the 10 best days: +₹45,239.
- Real account with no refills, over 15 start quarters: ₹15k died 3×, ₹20k 1×, **₹30k never** (ended ₹90k – ₹5.44 lakh).
- Survives +₹400 stress, 1–2% premium slippage, 2-minute delays and partial fills.

**Verify / roll back:**
- `python-engine/winvenv/Scripts/python.exe docs/research/fno/sn-gold/verify_gold_v5.py` (also `verify_gold_v4.py`, `verify_gold.py` for v3) re-runs from the frozen harness and fails on any difference.
- Tags `sn-gold-v3` / `-v4` / `-v5`.

---

## 7. Production deployment (Nov 13, 2026, night of Nov 12)

- **Authority:** the owner's words in section 2, item 13.
- **Release:**
  - `python-engine/sn_gold.py`, plus `SN_GOLD_*` settings in `config.py`;
  - two guarded hooks in `fno_orchestrator.py`, after `fno_n11.record_paper_signal` (entry, same chain snapshot) and after `fno_n11.tick` (management);
  - `docs/SN_GOLD.md` (owner rules), tests `python-engine/tests/test_sn_gold.py` (20).
  - Commit `bae3a524`, PR #137, merged `82b08371`, deployed by the runbook: built one service at a time, force-recreated, nginx restarted, autoheal restarted. `verify_deployment.py` exit 0; receipt `C:\Users\Urveesh\sentinel-operations\release-receipts\82b08371….json`. Docs commit `ebd6f23e`.
- **Tests:** full suite 6,385 passed, 4 skipped.
- **Settings read back in the engine:**
  - `SN_GOLD_ENABLED` True; start ₹30,000; 3 steps; day loss 0.20; stand-aside 0.85;
  - ITM thresholds 17,500 / 20,000; scale-in at 1 ATR; extend at +25% / 3 ATR;
  - `FNO_BOOK` N11; `FNO_LIVE_TEST_ENABLED` False.
- **Rules as run:**
  - **Entries:** N11 paper-record NIFTY signals plus those N11 stands aside on at 0.9 but R0.85 takes (wait only below 0.85 of usual volatility with a losing 20-trade paper record). One position. No expiry days.
  - **Size:** floor(W/15k) lots, halved on N11's low-volatility days. At ₹30k: 2 lots on lively days, 1 on quiet days.
  - **Strike:** the deepest ITM where every lot fits (by money per lot), else N11's strike, else one further out.
  - **Protection and scaling:** a 20% day stop on the option. A scale-in once at a 1-minute-ATR future move, to the full wallet, inside the day room.
  - **Exits:** with N11's paper lot; winners ≥ +25% kept on a 3-ATR trail to 15:10; failsafe 15:15.
  - **ATR:** from Kite 1-minute futures candles.
  - **The day:** booked after 15:20. Telegram on buys, sells and a day summary.
- **Tables:** `sn_gold_positions`, `sn_gold_days`, `sn_gold_wallet`, `sn_gold_skips`, `sn_gold_bars`.
- **Switch off:** `SN_GOLD_ENABLED=false` and recreate the engine. Rollback: redeploy `3ece6a8b`.
- **To check (from Nov 13):**
  - the first N11 paper signal → an `sn_gold_positions` row or an `sn_gold_skips` reason, plus the owner's buy message;
  - after 15:20 → `sn_gold_days` and the summary.

---

## 8. Forward and unseen checks

| Check | File | Status |
|---|---|---|
| SN02 benchmark at ₹15k | `2026-11-12-sn02/FORWARD.md` | From Nov 13, ≥ 20 trades, via `fno_n11_paper` |
| A / B / C wallets | `2026-11-12-sn15/FORWARD.md` | From Nov 13 |
| v3 | `2026-11-12-sn19/FORWARD.md` | From Nov 13 |
| v4 | `sn-gold/FORWARD_V4.md` | From Nov 13 |
| **v5 (deployed)** | `sn-gold/FORWARD_V5.md` | The live paper module is its forward check; R0.85 has no separate live record |
| 1-second empty-day book | `2026-11-13-sn78/sn79.py` | **Used up:** SN79 failed |

The pass rule everywhere: net > 0 after charges AND net without the single best trade > 0, at ≥ 20 counted trades. Real money only after a pass and on the owner's word.

---

## 9. The lessons, in order of importance

1. **N11's entries (its setups plus quality rules plus stand-aside) are the edge.** Exits are fine; more trades from anywhere else lose (SN04–SN09, SN17, SN20, SN77–SN88).
2. **Never cap winners.** About 77% of the profit is in 10 of 742 days (SN45). The 10% daily cap cut 70–90% (SN02). Quick exits add winning days but lose money (SN03, SN11, SN27).
3. **Costs decide small-target trading.** About ₹85–120 per lot per round trip. With a coin-flip direction, each trade loses about its cost.
4. **Money handling is where the improvements came from:**
   - enough wallet to buy N11's real contract;
   - ITM when affordable, deeper by money per lot;
   - a second lot on high-volatility days;
   - press winners (scale-in at a 1-ATR move, pyramid);
   - keep winners past N11's clock.
5. **Risk:**
   - "stop after k" growth caps the worst day;
   - ₹30k is self-sustaining without refills, ₹15k needs them;
   - a 20% day limit is right (15% and 30% worse).
6. **Day types:**
   - a wide 09:15–09:45 range predicts a big day (34% vs 8%);
   - narrow CPR and tight opening ranges do NOT predict trend days (web claims false);
   - yesterday's ADX < 30 limits N11 to puts, which explains most empty days.
7. **Gold's empty days have no intraday edge in price data** at 1-minute or 1-second resolution, for buyers or sellers (SN76–SN90). Stay flat; any new attempt needs non-price information.
8. **Method:** every surprising gain was checked held out and against random. Several in-sample winners (SN06 combo +₹2.0 lakh, SN78 +₹13–17k) collapsed out of sample.

---

## 10. Open items and next steps

- **SN91–SN100:** the owner will provide more data (evening or the next day). Promising directions only:
  - non-price information for empty days (RBI / budget / event calendar, pre-open global cues);
  - more months of 1-second data for a fresh unseen test;
  - Gold-day improvements scored at every wallet.
  - Do NOT re-search entry families on the two 1-second archives; they are seen.
- **Daily:** check SN Gold's paper module (section 7) and report its forward progress against `FORWARD_V5.md`.
- **Do not edit:** the frozen harnesses `sn-gold/gold_v*.py`. New experiments copy `gold_v5.py` into a new lab.
- **Earlier context (Nov 12):**
  - Production `3ece6a8b` (PR #136: N11 login reminders, N13 NIFTY-only main book), deployed without a backup on the owner's word;
  - disk cleanup freed 29 GB;
  - the owner's rule: no full backup before routine deploys.

---

## 11. Commit index (Dev branch `codex/production-correction-hedge-p0`)

| Step | Commits |
|---|---|
| SN01 | freeze `ca045b3c`, results `07e692bf`, docs `91501c3b` |
| SN02 | `4dbbc169`, docs `696743b7` |
| SN03 | `382ebcc5`, docs `66c9430e` |
| SN04 + SN05 | freeze `8bf68ae2`, results `1fc89f33`, docs `9bd05e9d` |
| SN06 | freeze `77c3c49b`, results `aaa21833`, docs `80c20e00` |
| SN07 | `a746c705`, docs `3ea95d48` |
| SN08 | `7c49b5b7`, docs `c9e67fa2` |
| SN09 | freeze `627d8af8`, results `b7224677`, docs `ecc172d4` |
| SN10 | freeze `e8ec1781` |
| SN14 / SN15 | `dc008ce4`, docs `cd64dee4` |
| SN16–SN18 | `c310912f`, docs `666d7842` |
| SN19–SN30 | `c3d0d767`, docs `7fa6b35a` |
| v3 freeze | `c6eefc68` (tag `sn-gold-v3`) |
| SN31–SN50 | `84930331` (tag `sn-gold-v4`), docs `f64b1e97` |
| SN51–SN75 | `d1d5f2ba` (tag `sn-gold-v5`), docs `c3eae8b8` |
| Deploy | `bae3a524` → PR #137 → `82b08371`, docs `ebd6f23e` |
| SN76 / SN77 | `a68f619a` |
| SN78 | `a6e5c53f` |
| SN79 | freeze `add4696e`, results `9ab9f0a8` |
| SN80–SN85 | `5e3aa825` |
| SN86–SN90 | `d0208fba` |
