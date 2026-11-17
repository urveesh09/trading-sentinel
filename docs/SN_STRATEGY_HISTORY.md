# SN strategy history: the owner's small-wallet F&O book, SN01 → SN90 and SN Gold v5 (complete record, Nov 12–13, 2026)

This is the one document to read to continue the SN work after a context reset. It records:
- what the owner asked for, in their words;
- every rule the owner set;
- every SN study, with its result and lesson;
- the SN Gold versions and their frozen configs;
- the Production deployment;
- where all data and code are;
- what is pending.

Companion documents:
- `docs/SN_TESTING_PROCEDURE.md`: exactly how every SN test was built, run and judged;
- `docs/SN_PROBLEM_STATEMENT_EMPTY_DAYS.md`: the open problem (Gold's ~84% no-trade days) for a research agent.
- `docs/SN_WEEKLY_SELLER_AND_GOLD_V6.md`: the weekly option seller (SN201–SN220), every recipe and number, and the road to Gold v6.

Everything is research in the Dev checkout (`C:\Users\Urveesh\Desktop\trading-sentinel`), branch `codex/production-correction-hedge-p0`, except the one Production deployment in section 7.

---

## 1. Current state (updated Nov 16, 2026 morning, after SN275: Gold v7 on Production paper; no margin-free gap-day leg) — read this first

**In Production (`052a6d6e`, PR #139, deployed Nov 15 night, verified): Gold v7 on paper (SN Gold v5 + WK-H band 0.8, `sn_wkh.py`), plus everything below from `826f0727` (PR #138, Nov 13 evening):**
- **SN Gold v5 on PAPER** (`python-engine/sn_gold.py`, since Nov 13, release `82b08371`):
  - follows N11's live paper record and places no orders;
  - wallet starts at ₹30,000, 20% day loss limit, losing days refilled, +50% after net profit equal to the wallet (at most 3 steps).
- **Partner give-back stop** (`partner_profit_protection.giveback_stop`, flag `PARTNER_WATCH_GIVEBACK_STOP_ENABLED`): "🛑 Stop for today and keep your profit" once a day that reached ≥ 5% of cash gives back 30% of its best. Messages only.
- **TR01 live tick recorder** (`python-engine/tick_recorder.py`, flag `TICK_RECORDER_ENABLED`):
  - records every NIFTY/SENSEX chain change with 5-level depth to `/data/research/ticks/<day>/`;
  - limits: 600 MiB a day, 12 GiB in all, 35-day retention;
  - **first live session Mon Nov 16**: check `events.jsonl`, the chunks and the owner line "📼 Tick recorder …" after 15:41.

**What the research says (SN01–SN220, all in this file):**
- **Gold v5 is the edge.** It earns in lumps: about 1 trade every 5–6 sessions, about half the months positive, +₹6.4 lakh from ₹30k growing over Jan 2023 – Aug 2026 (development), +₹2.09 lakh on the latest-5% TEST.
- **Gold's empty days (~84% of sessions)** are weak-trend, calm, flat-closing days (SN186).
- **Nothing tried makes money on them reliably:**
  - one-day and one-night ideas: rules, cheaper contracts, fixed ₹1,000 / ₹1,500 targets, sellers, LightGBM, LSTM, a bandit, 1-second scalping;
  - the volatility-persistence watches (SN95-L, SN171): earned a little in 2023–26 but **failed the unseen NIFTY 2022 exam (SN196)**;
  - **weekly option selling (SN201–SN210):** the unprotected weekly seller WK-S earned in every development year (+₹3.14 lakh per lot, NIFTY 2022–26). It **lost on all three unseen samples** (TEST −₹23k; NIFTY Dec 2021 – Mar 2022 −₹57k; SENSEX Oct 2024 – Apr 2026 −₹42k). Protected (winged) sellers lose everywhere.
  - **smart fail-safe exits for the weekly seller (SN211–SN220):** the best exit (the expiry-day gate) kept 97% of the development profit and cut the worst month by 37%, but no exit made the seller profitable on the three samples where it lost (−₹71k to −₹1.57 lakh over 96 weeks). **No Gold v6;** Gold v5 stays as it is.
- **SN221–SN230 (Nov 15): the first gap-day leg to pass an unseen exam, WK-H** (ATM straddle sold after the last weekend before expiry, delta-hedged with NIFTY futures in half-lot steps, held to settlement): **+₹61,511 per lot on unseen NIFTY Oct 2020 – Nov 2021 (worst month −₹6,251)**, where every unhedged seller lost; Gold + WK-H per lot +₹8.17 lakh vs Gold +₹6.42 lakh, 282 green days vs 55. Forward-paper candidate only; about ₹5 lakh margin; not deployed.
- **Gold v6 and Gold v7 (Nov 15 evening):**
  - the owner made Gold v5 + WK-H the baseline Gold v6; it is built in Dev as `python-engine/sn_wkh.py` (paper, `1690bb71`, not deployed);
  - SN231–SN250 chose **Gold v7 = the same leg with hedge band 0.8**: over Jan 2023 – Oct 2026, 33 of 46 months positive against 31, worst month −₹28,981 against −₹38,228, net +₹13.71 lakh against +₹11.96 lakh. It is the Dev default;
  - every month positive was not reached. The remaining bad months come from WK-H's quiet or sudden-move weeks and Gold v5's own losing months.
- **SN251–SN275 (Nov 16): Gold's gap days from Gold's own wallet, without margin: nothing passed.** Options-only WK-H (wings instead of futures) loses on 4–5 of 5 samples (−₹2.1 to −₹2.7 lakh per lot); the hot-day watches fail two new unseen buyer exams (NIFTY Oct 2020 – Mar 2022, SENSEX Oct 2024 – Apr 2026); buying every day loses ₹150–660 per lot per day; 13 new studies fail. A wage pot from Gold pays ₹500–750 a session over years, with ₹0.5–3.1 lakh advanced first (SN269). See the SN251–SN275 section at the end.
- **SN276–SN285 (Nov 16): every earlier gap-day signal combined on 1,465 pooled sessions: nothing passed** (walk-forward learners −₹1.3–1.8 lakh, the vote −₹973 pooled). Pre-holiday calls are positive on all four samples (post-hoc, ~10 a year): a forward watch candidate. See the SN276–SN285 section at the end.
- **SN286–SN300 (Nov 16): the auditor's brief.** Corrected holiday calls are carried by their best day (forward ledger only); the partner's first minute is not tradable at real prices; two tick-recorder candidates (futures pressure, lagging strike) are frozen for a 20-session forward verdict (`fwd.py`, about Dec 17–19). See the SN286–SN300 section at the end.
- **SN301–SN315 (Nov 16): the forward test protected and Gold v5's own losses audited.** Amended scorer and verified archive (`sn301/fwd2.py`; verdict after session 20, Dec 23). Gold's losses are signal losses (stops, adds, costs and cash checks sound; extension neutral); no Gold change. From Dec 7 F&O closes at 15:45 (engine assumes 15:40). See the SN301–SN315 section at the end.
- **SN316–SN330 (Nov 16): the partner's chart sequence fails on one-second data; Gold's losses have no early signature; WK-H passes the 2020 crash exam; Gold V8 = Gold v5 executed for real money** (`sn316/GOLD_V8.md`). Dec 7 CAS 2.0 hours fixed in Dev (`52a77adf`, not deployed). See the SN316–SN330 section at the end.
- **SN331–SN350 (Nov 16): no short-horizon option edge at any clock** (failed-break reversals have no room; entries after fast moves are worse than random). **Gold V8 = Gold v5**; the wage comes from Gold's capital (₹881 a session at ₹205 with a one-wallet reserve). See the SN331–SN350 section at the end.
- **SN351–SN365 (Nov 16): the wage corrected to ₹785 a session (SN342 double-counted ₹71,250 of growth cash); the auction's direction is information already priced; opening premium is rich; no entry state has room at ₹205.** Forward scorers fw5 / fw6 frozen. See the SN351–SN365 section at the end.
- **SN366–SN380 (Nov 16): Gold v5 on unseen 2022 lost ₹15,281 from ₹30k (4 of 12 months positive, like 2023); the opening direction is a 20–30-minute effect; chain pressure sensors are too small for a bought option.** Forward fw7 frozen. See the SN366–SN380 section at the end.
- **SN381–SN395 (Nov 16): under honest rules the opening ITM trade is break-even (+₹46 a session, −₹447 after Sep 7); the robust part is ITM over ATM; Gold's 2022 exam closed (N10 sheet D yes, N10 retry the sheets' lead); the wage is a capital question.** Forward fw7a / fw8 / fw9 frozen. See the SN381–SN395 section at the end.
- **SN396–SN410 (Nov 17): on the real 09:16:00 clock the opening trade loses (−₹81 a session; the +₹46 was a one-minute label lead); "cheap" sorts mornings but fails its search-corrected (p 0.80) and pre-auction checks; the 2022 N10–N11 gap is the stand-aside alone; Gold survives a minute of latency.** Forward fw7b / fw9a / fw8a frozen. See the SN396–SN410 section at the end.
- **SN411–SN425 (Nov 17): every day offered ₹750 in hindsight (the gap is selection); Gold takes every signal but its replay excludes expiry days (₹617 a real session at ₹205); Gold's exposure settings are leverage; BANKNIFTY is the only other venue (last week of the month).** Recorder BANKNIFTY change in Dev (not deployed); fw7c / fw9b frozen; F1 pre-registered. See the SN411–SN425 section at the end.
- **SN426–SN440 (Nov 17): break-even needs ~56% / ~68% direction (₹205 / ₹400) for a one-hour ITM trade; Gold's expiry mornings hold ~7 signals a year; Gold's exit headroom (₹2,085 a lot) resists every simple rule; ₹205 is the realistic Gold cost (₹617 a real session).** See the SN426–SN440 section at the end.
- **A daily wage comes from paying out Gold, not from daily trades (SN177):** an account of ~₹3.15 lakh pays ₹750 every session, ~₹8.45 lakh pays ₹1,500 (Gold ₹30k fixed + watches, in-sample).

**Data inventory (what is seen):**
- **NIFTY 2023, 2024, 2025, Jan–Oct 2026:** seen.
- **NIFTY Apr–Dec 2022:** seen since SN196 (sealed copy in `docs/research/fno/2026-11-13-sn186/_local`).
- **NIFTY Sep 2021 – Mar 2022:** seen since SN209 (the index at every minute, options 14:55–15:29; lean sealed mirror in `docs/research/fno/2026-11-14-sn201/_local`).
- **SENSEX May 2024 – Apr 2026:** seen since SN209 (the same lean mirror).
- **1-second archives Apr–Nov 2026:** seen. **NIFTY 1-second Jan 16 – Apr 2 2026:** downloaded Nov 14, not used yet.
- **Real-quote archive Sep 10 – Nov 12 2026:** seen.
- **NIFTY Oct 2020 – Nov 2021:** seen since SN228 (the WK-H exam, Nov 15; mirrors in `docs/research/fno/2026-11-15-sn221/_local`).
- **Unseen / not fully downloaded:** NIFTY Jan–Sep 2020 (Jul–Sep 2020 options 318 of 857; the pre-registered crash test). ICICI does not serve SENSEX Jan–Sep 2024 (the probe failed).

**Paper watches:**
- SN95-L, SN126-L and SN171 (forward ≥ 20 trades; weak after SN196);
- SN Gold v5 `FORWARD_V5.md`.

**Waiting on the owner:**
- **Gold v7 is on Production paper since Nov 15 night (`052a6d6e`):** real money only after the gates in `docs/SN_GOLD.md` (8 settled WK-H weeks, the 2020 crash test, a Kite margin check, a real-money WK-H module with a week stop) and the owner's word;
- the rest of NIFTY Jul–Sep 2020 options and Jan–Jun 2020 (the owner's downloader continues), then the pre-registered crash test;
- (done Nov 15: `nifty-2021-q4-fno` options and all of 2021.)

**How to resume:**
- **For Gold v6 or the weekly seller, read `docs/SN_WEEKLY_SELLER_AND_GOLD_V6.md` first; its section 0 is WK-H (SN221–SN230)** (every recipe, number, data path and rerun command for SN201–SN230).
- Read this section and the last sections of this file: SN161–SN185, SN186–SN200, SN201–SN210, SN211–SN220, SN221–SN230 and SN231–SN250 (with "Open items, Nov 15, 2026, after SN250").
- Then read `docs/SN_TESTING_PROCEDURE.md`, sections 1–15 (tools, venvs, pitfalls).
- Then read the folder READMEs:
  - `docs/research/fno/2026-11-13-sn161/README.md`
  - `docs/research/fno/2026-11-13-sn186/README.md`
  - `docs/research/fno/2026-11-14-sn201/README.md`
  - `docs/research/fno/2026-11-14-sn211/README.md`
  - `docs/research/fno/2026-11-15-sn221/README.md`
  - `docs/research/fno/2026-11-15-sn231/README.md`
- Research Python: `C:\Users\Urveesh\sentinel-ml-venv` (LightGBM, PyTorch CPU); the engine uses `python-engine\winvenv`.

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


## SN91–SN100 (Nov 13, 2026; research only, Dev)

The owner asked for the other agent's SN92–SN100 proposal and component review (`docs/SN92_SN100_RESEARCH_PROPOSAL.md`, `docs/SN_COMPONENT_RESEARCH_REVIEW.md`, local files of that agent) to be built and tested at every wallet, cap and start, "and let's see if it improves drastically the current Gold". Folder `docs/research/fno/2026-11-13-sn92` (plan + scripts frozen at `b4295b1c` before scoring; README has every number).

| SN | Idea | Held out | Verdict |
|---|---|---:|---|
| 91 | Rupees of wallet per lot (10k / 12.5k / 15k / 20k) | 10–15k equal, 20k worse | v5's 15k stays |
| 92 | Where the money goes | ₹205/lot stress is Gold's biggest cost (₹28.7k at ₹15k); TPB puts carry the book; on empty days the index moves 3–10× the ~9-point cost hurdle but the direction is a coin flip | Description |
| 93 | Slow up-drift calls | −₹49,898 (random days at the same clock −₹10,599) | NOT PROVEN |
| 94 | Confirmed failed breakout | −₹86,916 (unconditional fade −₹1,69,200) | NOT PROVEN |
| 95 | Cheap straddle (realised vs implied at 10:00) / rich iron fly | Straddle **+₹23,518** (35 trades; 2/4 years; −₹16,930 without best 5); fly −₹1,15,649 | NOT PROVEN; straddle = forward watch `SN95-L` |
| 96 | NIFTY 50 components (15-minute Kite + Production bars, Feb–Oct 2026) | No information (forecast 0.43% worse; residual breadth correlation +0.009, interval −0.04 to +0.06) | NOT PROVEN |
| 97 | Futures volume (Gold lots, companion confirmation), events | Trades less, still loses; Gold on RBI days +₹2,297 (4 trades) | NOT PROVEN |
| 98 | Expiry mornings priced | −₹16,757 | NOT PROVEN |
| 99 | Gold's lots by setup / cheapness / VIX / volume / one deep lot | +₹3.5k (₹30k fixed) and +₹6.2k (growth) over v5, reversed at +₹400 and 1-minute-late | NOT PROVEN; v5 sizing stays |
| 100 | Gold + companion in one account | ₹30k growing: Gold alone ₹8,50,882; + SN93 −₹2.21 lakh; + SN94 −₹5.28 lakh | Gold alone best |

**Money levers for Gold v5 (in-sample, `levers.py`):**
- ₹30k start, stop after 3: ₹8,50,882 (worst day −₹21,113); stepping after 50% profit gives ₹9,47,841 with the same worst day.
- Stop after 5: ₹15,51,780 (−₹45,464).
- ₹50k start: ₹14,70,693 (−₹33,689).
- A 15% day limit costs about a quarter. 25–30% raises the worst day for little gain at small wallets, and SN57 already found 30% worse held out, so 20% stays.

**Conclusion:** Gold v5 is unchanged and stays deployed on paper. Empty days stay flat. New information (BANKNIFTY option minutes, 1-minute constituents, GIFT Nifty, order book) needs a download on the owner's word. Commits: freeze `b4295b1c`, results in the commit that adds this section.


## SN101–SN120 (Nov 13, 2026; research only, Dev)

The owner asked for the other agent's SN101–SN110 (`docs/SN101_SN110_RESEARCH_REVIEW.md`, that agent's local file), then SN111–SN115 (better permutations) and SN116–SN120 (the combined learning). "Correct testing is the need."

Three phases, each frozen before scoring:
- A `docs/research/fno/2026-11-13-sn101` (`728f15f8` / results `24e769bc`);
- B `…-sn111` (`a45b401d` / `21f2bba8`);
- C `…-sn116` (`2a3683bd` / results commit that adds this section).

Each folder's README has every number.

**New data used for the first time:**
- **Production's quote archive:** real bid/ask with 5-level depth, both weekly expiries, 40 sealed days Sep 10 – Nov 11 2026.
- **Its paper-position replay:** 23 NIFTY entries.
- **N012's Round 36 SENSEX panel.**

All were read in place and hash-checked.

| SN | Finding | Verdict |
|---|---|---|
| 101 | SN95's 10:00 straddle signal vs matched random days: **p = 0.002**. Only the top decile pays; the ₹15k premium cap is part of it | Information real |
| 102 | Remaining-value model: correlation 0.19; held out +₹19,686 (3/4 years) but −₹12,702 without its best 5 days | NOT PROVEN |
| 103 | Real quotes: next-week straddle loses half as much per rupee (−₹24.9 vs −₹53.3 per ₹1,000) | Description |
| 104 | Taking straddle profit early destroys it (−₹7,959 vs hold +₹17,145) | NOT PROVEN |
| 105 / 106 / 108 | Bank cancellation, SENSEX, order-book absorption: no information | NOT PROVEN |
| 107 | RBI days: implied volatility −4.7% by 10:30 (17 events) | Description |
| 109 | Real spreads match the model below ₹300 premium (1.46× at ₹300–450); 1–6 lots fill at the best price; Gold's simulated fills are conservative | Costs honest |
| 110 | Gold + straddle in one wallet: +4.6–4.9% at ₹30k, worse drawdown, negative at ₹400/leg | Fails the Gold v6 bar |
| 111 | The straddle's edge is **volatility persistence** (later realised ÷ implied 0.63 → 0.96 across deciles, correlation 0.47); implied does not catch up; not a direction trade | Mechanism |
| 112 / 114 | One leg, strangles, ITM pair: none better than the ATM straddle | ATM stays |
| 113 | Gold's per-lot net is flat across volatility terciles; skipping low-volatility entries hurts every wallet | Never filter Gold by volatility |
| 115 | Production paper entries fill **39 s** after the signal and pay ₹57–109 per lot in, ₹62–98 out vs mid | ₹205 stress about right |
| 116 | ₹45k growing (stop 3): Gold ₹45k **₹13.21 lakh** vs Gold ₹30k + straddle sleeve ₹8.68 lakh | Extra money belongs in Gold |
| 117 | Measured costs ≈ ₹175 per lot; Gold v5 ₹30k growing 5th / 50th / 95th: ₹7.95 / 8.75 / 9.80 lakh (house ₹8.51 lakh) | Research realistic |
| 118 | No refills, every monthly start, ₹30k capped sizing: 0 of 42 starts ended below the start, none dead, median 24.6×. But the **Jan 2023 start fell to ₹14,782 (−51%)** first | Survival with deep drawdowns |
| 119 | Gold v5 beats **all 400** random-entry Golds with the same machinery (random entries lose ~₹1 lakh on average) | Gold's entries are a genuine edge |
| 120 | Scoreboard (`sn116/results-sn120.json`) and the frozen forward plan (`sn116/README.md`) | – |

**Conclusion:**
- Gold v5 stays unchanged.
- Empty days stay flat; SN95-L stays a forward watch, and if it ever passes it goes in a separate sleeve.
- The owner's levers are capital, the 50% growth trigger and the cap.
- The only data worth buying next is small real broker fills (cost calibration), then NIFTY next-week expiry minutes (for the straddle watch).


## SN121–SN130 (Nov 13, 2026): gap days freed from Gold's rules, and the partner

**The request:** the owner wanted the gap days used ("the partner trades every day and is up ₹6–7k on ₹25k at some moment; why can't the system"), with autonomy over gap-day rules. Folder `docs/research/fno/2026-11-13-sn121` (frozen `cecf2f8a`; the README has every number and the sources).

**The partner data and its privacy rule:** the frozen Nov 4 extract is used, with shapes and ratios only and no partner rupee totals.

| SN | Finding | Verdict |
|---|---|---|
| 121 | The partner's peak was ≥ +20% of ₹25k on 5 of 7 days, but only 3 ended green, with a median of 22 trips after the peak. A 30% give-back stop on their own sequence cuts the 7-day loss by ~71% | Coaching lesson |
| 122 | Their entries catch the next minute (+1.51% vs +0.12% random, p = 0.0015), gone by 5 minutes; their exits are well timed; machine exits on their entries are worse | Skill is real but tiny vs costs |
| 123 | A partner-like machine scalper loses ₹2,950–8,295 a day; locks only shrink losses | NOT PROVEN |
| 124 | Overnight fly / condor selling (Muravyev–Ni): the effect exists, but 4 legs of costs swamp it (−₹850–1,040 a night) | NOT PROVEN |
| 125 | The last half-hour to 15:25: −₹1,10,959 held out | NOT PROVEN |
| 126 | Hot-day big-burst scalping: +₹4,414 on 35 trades, −₹2,362 at ₹400 | Forward watch SN126-L |
| 127 | A 15-minute option buy costs ₹285–340 per lot at every clock | Map |
| 128 | Morning IV-crush selling: no better than midday | NOT PROVEN |
| 129 | Nothing passed. Trading every candidate every gap day: −₹17.6 lakh. Gold ₹55k alone: ₹16.16 lakh | Do not trade every day |
| 130 | Synthesis: copy the partner's missing discipline (give-back alert, friction counter, edge clock) as coach messages, the owner's call; their tape-reading cannot be copied from minute data | – |


## SN131–SN150 (Nov 13, 2026): the Smart Sentinel, learned decisions instead of rules

**The request:** "I don't need rule-based or filtering systems. I need that smart Sentinel ... if you need resources, tell me."

**Folders:** `docs/research/fno/2026-11-13-sn131` (phase D, frozen `1df2dd70`) and `…-sn141` (phase E, frozen `f63a658e`). Each README has every number.

**What was built:** LightGBM learners over 234,472 minute decisions (2023 – Oct 2026, 44 measurements, CE / PE × 5–60 minutes, executable labels), retrained quarterly walk-forward; plus learned exits, event selection, adaptive retraining, ensembles, confidence sizing, a 1-second learner and an order-book learner. Research venv `C:\Users\Urveesh\sentinel-ml-venv`.

| SN | Finding |
|---|---|
| 131 | Out-of-sample rank correlations −0.02 to +0.03. Even the top 1% of forecasts lose about their cost (~₹300 a trade). The only consistent signal is the 5-minute put, too small to pay |
| 132–140 | Learned policy −₹1,71,175 (2024–26; 2026 +₹8,126), no better than random. Adaptive is worse, the ensemble the same, sizing amplifies losses. A shuffled-label control does as well per trade (−₹216 vs −₹262). The 1-second and order-book learners choose not to trade |
| 141 | More history helps in 2026 (correlation +0.006 → +0.019, policy −₹63,723 → −₹4,572) but not in 2025: not established |
| 142 | Even at zero slippage it loses (−₹29,503); costs decide |
| 143–147 | Holding to the close is never chosen. The hot-day learner (−₹18,467) loses to SN95-L's fixed straddle (+₹36,541) on the same days. A learned extension for Gold is worse than v5's exit. Adding the learner to Gold cuts ₹8.63 lakh to ₹6.92 lakh. The reversed 1-second test also finds nothing |
| 148 | Resources, ranked: (1) live full-chain tick capture (the partner's eyes; free with Kite; a Dev build + deploy); (2) NIFTY 2019 – 2022 minute history (~4 days of Breeze allowance; a probe first); (3) small real broker fills (real money, the owner's decision) |
| 150 | The learner, given full freedom, chose not to trade gap days: the smart decision at this information and cost level. Edges that pay are mechanism-based (Gold's entries, hot-day volatility persistence) |


## SN151–SN160 (Nov 13, 2026): the hot-day program

The work dug where the one gap-day edge lives (volatility persistence, the 10:00 straddle), mixing rules and learning. Folder `docs/research/fno/2026-11-13-sn151` (frozen `5f42b20e`).

| SN | Finding |
|---|---|
| 151 | Rolling "hot right now" entries every 30 minutes lose (−₹46,028 held out): later entries have too little day left |
| 152 | Yesterday-hot → straddle today: +₹4,008 held out but 2/4 years and negative at ₹400 (a faint echo) |
| 153 | Expiry-day hot straddle loses (0 days to expiry decay) |
| 154–155 | A learned probability loses (−₹15,898); rule + model agreeing gives 4 trades vs the plain rule's +₹17,144 |
| 156 | Legging out of a winner is worse than holding both legs |
| 157 | 1-second hot-day momentum = random side |
| 158–159 | The hot-day book (SN95-L + SN126-L) +₹19,794 in four years on a ₹15k sleeve, intervals include zero; the same ₹15k inside Gold earns ~₹4.5 lakh more |

**Lesson:** the edge is precise (10:00, hold both legs to the close, hot days only), and the simple mechanism rule beats every model on so few hot days. Gap days stay a paper forward watch (SN95-L + SN126-L). Gold's capital remains the profit lever.

## SN161–SN185: the daily wage (Nov 13, 2026 night; folder `docs/research/fno/2026-11-13-sn161`)

**Owner:** the SN goal was always "a daily 10% target … a daily wage", with ₹15,000 and ₹1,500 a day. Gold v5 "gives insane returns" but trades too rarely for a wage-earner. Train on the data, keep the latest 3–5% for testing, try cheaper contracts, ML, any mix.

- **Method:** the plan was frozen (`8d91837d`) and every phase frozen before it ran. TEST = the latest 5% (37 sessions, 2026-08-20 … 10-28), scored once by SN181.
- **Development (705 sessions):**
  - Gold v5 at ₹15k gives 0.8 wage days a month.
  - Hindsight shows +₹1,500 on 91% of days; a random side keeps it on 25%.
  - A coin-flip wage trader reaches its wage on up to 58% of days and loses ₹4.1 lakh (₹1.23 lakh even with zero slippage). Cheaper contracts and more attempts lose more.
  - Triple-barrier ML (SN166–SN168) is worse than random, or learns not to trade. A learned exit trims losses by about 10%. The online bandit learns "no trade".
  - Only SN171 passes development: a HAR volatility forecast for the 10:00 strangle / straddle (+₹23,087 / +₹56,653 held out, 6–12 trades a year). It is the SN95-L mechanism.
- **TEST:** nothing passes.
  - Gold v5 reference: +₹29,628 at ₹15k and +₹2.09 lakh at ₹30k production, 2.0–2.3 wage days a month.
  - The coin-flip trader: −₹19,511.
  - SN171: 0 trades at ₹15k, −₹2,901 on 2 trades at ₹30k.
- **Real quotes (SN182):** the coin-flip trade loses ₹171 a trade, against the model's ₹465. The ₹205 a lot slippage allowance is the measured reaction delay.
- **The usable answer (SN177):** a salary account pays a fixed wage from Gold's lumpy profit. Paying ₹750 every session needs about ₹3.15 lakh, and ₹1,500 about ₹8.45 lakh (Gold ₹30k fixed + watches, in-sample).
- **Lesson:** a wage is easy to see and hard to keep. On gap days the smart answer is to sit out. A daily income comes from paying out Gold's edge, not from forcing trades.
- **Forward:** SN95-L, SN126-L and SN171 stay paper watches, with tick-recorder data from Nov 16. One sealed SENSEX (Oct 2024 – Dec 2025) test of the hot-day trades needs the owner's word.

## SN186–SN200 (Nov 13–14, 2026 night): an extra leg for Gold's empty days (folder `docs/research/fno/2026-11-13-sn186`)

**Owner:** "We don't want to replace Gold … an additional leg for the empty days … the commonality of those days … remove the rule of 10% … a fixed amount of ₹1000 or ₹1500 … whatever the wallet size … maybe try LSTM … use whatever data we have on the device … till SN 200."

**Method:**
- Plan frozen at `4462f86f`; every phase frozen before it ran.
- Development = 705 sessions; TEST = the latest 5% (Gold's 26 empty days of Aug 20 – Oct 28, 2026).
- NIFTY Apr–Dec 2022 (unseen, on disk) sealed and scored once.
- Fixed goal ₹1,000 / ₹1,500, lots fixed, ₹205 per leg.

| SN | Result |
|---|---|
| 186 Commonality | Empty days: yesterday's ADX 20.8 vs 28.3, OR30 0.37% vs 0.43%, VIX ratio 0.98 vs 1.02, range 0.77% vs 0.85%, open→close +0.03% vs −0.32% (Gold earns on falls). No cluster pays a simple play; 09:45 tells Gold vs empty days at AUC 0.66–0.72 |
| 187 The 91% trade on both sides | −₹3.94 lakh held out (random minute −₹3.63 lakh) |
| 188 Hot empty days, small target | −₹86,715 |
| 189 Iron-fly seller on calm forecasts | −₹1.51 lakh; the fly reaches +₹1,000 on 6 of 590 empty days |
| 190 Volatility-regime leg | −₹1.10 lakh |
| 191 LSTM entry | AUC 0.53 / 0.50, no trades; LightGBM AUC 0.51 |
| 192 LSTM volatility | R² below HAR in all three years |
| 193 LSTM 15-min direction | 51.1% / 52.0% / 49.9% accuracy = base rate; −₹71,667 |
| 194 Stack | No trades |
| 195 NIFTY 2022 sealed | 145 lab sessions (Apr 1 – Dec 30, 2022) |
| **196 NIFTY 2022 exam** | **SN95-L −₹4,490 (10 trades), SN171 −₹1,740 / −₹1,657 (2 each): the watches fail the unseen year** |
| 197 Leg beside Gold | Leg +₹39,086 in development (in-sample); Gold + leg 1.3 goal days a month vs 0.84 |
| 198 TEST | Leg +₹2,407 on 2 trades at ₹15k |
| 199 Leg wallet | Scales linearly, losing years included |

**Lesson:** empty days are calm, two-way days; no buyer, seller or learner earns on them after costs, and the only 2023–26 edge failed 2022. Stay flat on empty days; take a daily income from Gold through the salary account (SN177).

### Open items, Nov 14, 2026 (superseded)

See "Open items, Nov 14, 2026, after SN210" at the end of this file.

### Commit index, SN161–SN200

- **SN161–SN185:** `8d91837d` (plan), `b813219b`, `f2d8de08`, `0be4c0cb`, `62186118`, `777b1182`, `e63fd462`, `b38b606c`, `73af1f1b`; docs `946a9692`.
- **SN186–SN200:** `4462f86f` (plan), `1f60f9df`, `09714777`, `5deb4c7f`, `d08e02fd`.
- **Production:** `826f0727` (PR #138); docs `43634552`.

## SN201–SN210 (Nov 14, 2026): selling weekly options for Gold's quiet days (folder `docs/research/fno/2026-11-14-sn201`)

**Owner:** "instead of staying flat … how do the real traders earn that money on every day … different perspective, different instruments, different systems … the system should become smarter and smarter … make little profit money first." Also: use the new data and try ML / LSTM.

**Method:**
- **Plan:** frozen `00564b6b`; amended after SN203, before SN204 was written.
- **Engine (`wk.py`):** one position per weekly expiry, entered at 15:15 and held to the expiry settlement (or a stop at a 15:15 mark). 1 lot, Zerodha charges, ₹100 per leg-lot.
- **Development:** NIFTY Apr 2022 – Aug 2026, 229 weeks, held out by year (LOYO).
- **TEST:** the latest 9 weeks.
- **Two unseen exams, scored once:** NIFTY Dec 2021 – Mar 2022 (17 weeks; the owner's new download) and SENSEX Oct 2024 – Apr 2026 (83 weeks).

| SN | Result |
|---|---|
| 201 | New data sealed: 17 NIFTY + 83 SENSEX weekly expiries (lean read-only mirrors, hashed) |
| 202 | The weekly premium exists only **unprotected**: the short ATM straddle held to expiry made +₹1.40–2.44 lakh per lot, with sellers keeping 4–10% of the premium. Every protected structure loses |
| 203 | 0 of 78 protected (defined-risk) weekly sellers are positive (best −₹75,662) |
| 204 | 38 of 38 unprotected sellers are positive. **WK-S** (strangle at ±0.5 straddle, 3 sessions before expiry, stop at 1× the credit): +₹3,13,523, every year positive, LOYO +₹1,49,729. Worst month −₹51,245. An 8% crash week would lose about ₹1.09 lakh per lot |
| 205 | HAR timing fails (LOYO +₹1.46 lakh vs +₹3.14 lakh unfiltered). Sizing beats the plain seller in only 2 of 5 years |
| 206 | LightGBM / LSTM risk model: AUC 0.56 / 0.49. Every filter earns less than not filtering |
| 207 | Gold + WK-S (2023 – Aug 2026): +₹8.76 lakh, 380 green days vs Gold's 55, every year positive (in-sample) |
| 208 | Robust in development to entry time, 2–4× slippage, width, stop and entry day |
| **209** | **Fails every unseen sample:** TEST −₹23,348; NIFTY 2021–22 −₹56,743 (the Russia week, Feb 21–24, 2022, alone −₹40,884); SENSEX 2024–26 −₹42,022. Real quotes match the cost model |
| 210 | Synthesis: stay flat on empty days; WK-S is paper-only if the owner wants it |

**Lessons:**
- The weekly seller looked like the missing piece in development, but its edge (4–10% of the premium) is smaller than one shock week. HAR, LightGBM and LSTM cannot see the shock weeks coming. The unseen data decided.
- **How real traders earn every day:**
  - about 9 in 10 individual F&O traders lose (SEBI studies, FY22–FY25);
  - the steady earners are firms that make markets (spread, speed, scale) or sell options with large capital and accept heavy weeks.

### Open items, Nov 14, 2026, after SN210 (superseded)

See "Open items, Nov 14, 2026, after SN220" at the end of this file.

### Commit index, SN201–SN210

- `00564b6b` (plan and engine, before any score), `6847a924` (SN201–SN203 + amendment, SN204 frozen), `7bdc7e73` (SN204, SN205–SN208 frozen), `4852fc05` (SN205–SN208, SN209 frozen), `8192ccf5` (SN209–SN210 and the README).
- The docs commit adds this section.
- **Production:** unchanged at `826f0727`.

## SN211–SN220 (Nov 14, 2026): a smart fail-safe exit for the weekly seller (folder `docs/research/fno/2026-11-14-sn211`)

**Owner:** "certain days wiped it all off … a smart fail safe mechanism … master the exit … slice down the losses … while ensuring that the profit is maintained … a gold V6 which includes gold V5 and the gap covering strategy."

**Correction given to the owner:** WK-S is not a better entry. It sells options and is paid on quiet days. On unseen data it lost beyond its single worst week, so the test was whether an exit can cut the big losses and still leave a profit.

**Method:**
- **Plan:** frozen `2c2d1b66`, with an amendment after SN212 (development only).
- **Engine:** `wk2.py` replays each week minute by minute (reaction delay, fresh prices only, opening penalty). With no rule it matches WK-S exactly on all four samples.
- **Development:** NIFTY 2022–26, held out by year.
- **Second look:** the three samples where WK-S lost. Their paths had never been studied; every exit was frozen first, then each sample was run once.

| SN | Result |
|---|---|
| 211 | Full-minute exam mirrors; exact parity |
| 212 | Overnight gaps earn (+₹1.62 lakh). Losing weeks lose on expiry day (−₹4.17 lakh) and intraday (−₹2.99 lakh). After a strike touch, holding was better 60% of the time |
| 213 | Exit on a strike break: near the strike destroys the profit; far past it (0.5 straddle) is harmless (+₹2.94 lakh) |
| 214 | Minute loss stops and profit takes: no tail cut |
| 215 | Crash-speed exit: FAIL |
| 216 | Buy protection when threatened: FAIL |
| 217 | **Expiry-day gate** (hold into expiry only while the index is inside the strikes): +₹3.05 lakh (97%), worst month −₹32,138 (−37%), worst week −18%, every year positive. Calendar skip: −33% profit |
| 218 | Combined exit (30 candidates): the strict screen fails; the April 2025 weekend gap cannot be exited |
| **219** | **Second look (96 weeks):** WK-S −₹1,22,113; gate −₹1,56,870; breach + gate −₹1,14,945; never through expiry day −₹71,141. Development, Gold + gate: +₹8.65 lakh with a −₹31,981 worst month. **FAIL** |
| 220 | **No Gold v6.** An exit can cut the tail once an edge exists; it cannot create one |

### Open items, Nov 14, 2026, after SN220 (superseded; see "Open items, Nov 15, 2026, after SN230" at the end)

1. **Mon Nov 16 checks:**
   - the tick recorder's first live day (`events.jsonl`, chunks, the owner line);
   - SN Gold v5 paper progress;
   - the partner give-back stop.
2. **ICICI:**
   - `nifty-2021-q4-fno` options are left (410 of 957);
   - `sensex-2024-jan-sep-fno` is not served (do not retry);
   - a NIFTY 2020 / Jan–Sep 2021 target is the only true crash test left for any seller: the owner's word and a probe first.
3. **Weekly seller:** closed. No Gold v6 and no paper watch recommended.
4. **Forward watches:** SN95-L, SN126-L and SN171 stay paper-only.
5. **Do not repeat on NIFTY 2021–2026 or SENSEX 2024–2026:**
   - everything in the SN210 list;
   - weekly-seller exits: strike breach, minute loss stop, profit take, crash speed, protect-on-breach, the event calendar, the expiry-day gate.
6. **The next real lever is new information:** order flow from the tick recorder.

### Commit index, SN211–SN220

- `2c2d1b66` (plan, engine, SN211–SN212 before any score)
- `2693893f` (SN211–SN212 and the amendment; SN213–SN218 frozen)
- `f8a5b533` (SN213–SN218; SN219 frozen)
- `436295ca` (SN219–SN220 and the README)
- The docs commit adds this section. **Production:** unchanged at `826f0727`.

## SN221–SN230 (Nov 15, 2026): the hedged weekly straddle WK-H passes an unseen exam (folder `docs/research/fno/2026-11-15-sn221`)

**Owner:** "SN204, SN208, SN207 … worked very well on those gap days and there were issues with them … improve them or make better ones … till SN230 … try start wallets lot sizes different combinations … we are not replacing GOLD_V5 … another one that works in the gap days."

**Method:**
- plan frozen at `ec76f220`, before any number;
- versions chosen on **all four seen samples at once** (DEV, TEST, NIFTY Dec 2021 – Mar 2022, SENSEX 2024–26) by a max-min rule;
- picks frozen at `dbbf9086`;
- one exam on **unseen NIFTY Oct 1 2020 – Nov 25 2021** (60 weekly expiries, downloaded by the owner Nov 14–15).

| SN | Study | Result |
|---|---|---|
| 221 | Seal the exam and futures mirrors | 60 expiries, counts and hashes only |
| 222 | Parity + the four-sample board | Exact parity; every SN201–SN220 recipe loses on ≥ 2 samples |
| 223 | Trend timing (ADX, efficiency ratio) | Skips weeks, not the bad ones; no better than random skipping |
| 224 | Entry day and weekends | **Weekend intervals lose for sellers on every sample**; no-weekend entry helps DEV only |
| 225 | Far wings | Strikes rarely reach ±2 Q; every winged version loses |
| 226 | **Futures delta hedge** | 2 option lots hedged in half-lot steps every 15 minutes lift the four-sample worst score in **78 of 78** versions |
| 227 | Robust selection, 2,080 versions | 20 eligible (all filtered); the filtered picks fail the random-skip null, so **PICK = WK-H, STRADDLE kM settle H15x2** |
| **228** | **The exam (once)** | **WK-H +₹61,511 per lot, worst month −₹6,251, 59% of weeks, both years +.** Same weeks: WK-S −41,621, the same straddle unhedged −43,526. **PASS** (forward-paper candidate) |
| 229 | Wallets and Gold + WK-H | One unit = 2 option lots ≈ ₹5 lakh. Gold + WK-H per lot (2023 – Aug 2026) **+₹8.17 lakh vs +₹6.42 lakh, 282 green days vs 55, worst month −₹28k vs −₹38.5k** |
| 230 | Synthesis | `README.md` of the folder |

**WK-H:**
- sell the ATM straddle, 2 lots, at 15:15 of the first session after the last weekend or holiday before expiry;
- every 15 minutes, reset NIFTY futures to −round(2 × Black–Scholes delta) whenever the net delta exceeds 0.6 lot (none after 14:30 on expiry day);
- hold to settlement.
- Per lot: DEV +₹2,11,957 (worst month −15,915), TEST −2,414, NIFTY 2021–22 +10,308, SENSEX +1,04,354, exam +61,511; **five samples +₹3,85,716**.

**Not proven yet:**
- one unseen sample (a bull market);
- margin unverified;
- about 4.7 futures orders a week;
- the expiry-afternoon hedge freeze is its weakest point (May 16 2024, −₹24.6k per lot).

**Full record:** `docs/SN_WEEKLY_SELLER_AND_GOLD_V6.md` section 0.

### Open items, Nov 15, 2026, after SN230 (superseded; see "Open items, Nov 15, 2026, after SN250" at the end)

- **Mon Nov 16:**
  - check the tick recorder's first live day (`events.jsonl`, chunks, the "Tick recorder" owner line after 15:41);
  - check SN Gold v5 paper progress;
  - check the give-back stop.
- **Owner's word needed for WK-H:**
  1. build a Dev paper shadow of the Gold v6 candidate (Gold v5 + WK-H; live option and futures quotes, the hedge loop, Telegram lines, no orders), then deploy;
  2. a Kite basket-margin check for 2 short NIFTY ATM straddle lots + 2 futures lots.
- **The pre-registered crash test:** once NIFTY Jul–Sep 2020 (options 318 of 857) and Jan–Jun 2020 are downloaded, score WK-H, the runners, the references and the plateau once, unchanged.
- **Later SN idea (untested):** flatten the hedge at the 14:30 expiry-day freeze; information only on the crash sample.
- **Downloads:** the owner's downloader continues back through 2020, then SENSEX.
  - The Oct–Dec 2020 full check is unfinished (the PC ran low on memory).
  - The Jan–Mar 2021 check lists 3 unexplained items.

### Commit index, SN221–SN230

- `ec76f220`: plan, engine, SN221 seal.
- `dbbf9086`: SN222–SN227, picks frozen.
- `bb7370c2`: SN228 exam, SN229, README.

## SN231–SN250 (Nov 15, 2026 evening): Gold v6's bad months, and Gold v7 (folder `docs/research/fno/2026-11-15-sn231`)

**Owner:** "this will be our baseline, and we will be calling this Gold V6 … comprehensively analyse the bad months … make every single month positive … I have promised to refill every single penny … give me a Gold V7 if possible."

**Gold v6 built in Dev first:** `python-engine/sn_wkh.py` (commit `1690bb71`), paper, not deployed. SN Gold v5 is unchanged.

**Method:**
- plan frozen at `5f67bb0b`; diagnosis and amendment at `d87c0031`;
- the account is SN Gold v5 (₹30k growing) + the WK leg, Jan 2023 – Oct 2026 (46 months);
- the frozen rule Q1–Q5: more positive months, ≥ 90% of the profit, no worse worst month, the WK leg holding up on the five WK samples, nulls for thresholds.

| SN | Result |
|---|---|
| 231 | Gold v6: 31 of 46 months positive, +₹11,96,139, worst −₹38,228; 15 bad months, 8 of them in 2023 |
| 232–233 | Bad months are quiet months. **Futures hedge charges (₹1.42 lakh per lot on DEV vs a ₹2.12 lakh net)** eat WK-H's small premium. The 14:30 expiry freeze cost −₹83k; gaps; Gold v5's own losing months |
| 235 | Expiry-afternoon variants: none qualifies |
| 236 | **Hedge band 0.8: qualifies** (33 months, +₹13.71 lakh, worst −₹28,981, charges −38%); the rest of the cost grid, the synthetic hedge alone and a second unit fail |
| 237–241 | Daily hedged straddle, SENSEX second leg, low-premium skips, more units, month profit-protection: all fail |
| 242 | Idle capital at 5%: +1 month, shown apart |
| 244 | Information: band 0.8 + synthetic options hedge, 34 months, +₹14.83 lakh (the best next idea) |
| **245** | **Gold v7 = SN Gold v5 + WK-H with hedge band 0.8** |
| 246 | Robust: bands 0.7–0.9 beat 0.6; it survives cost stress; 2023 has 7 positive months vs 4; bootstrap 75%. Weaker on fast samples (NIFTY 2021–22, SENSEX) |
| 247 | Gold v7 has 13 bad months left (9 WK-H, 4 Gold). Owner's refills about ₹29k a month (worst ₹67k) vs about ₹58k banked |
| 248 | NIFTY Jan–Sep 2020 crash test pre-registered (`CRASH_TEST_2020.md`), sealed |
| 249 | Dev default `SN_WKH_BAND = 0.8`, `SN_WKH_LABEL = "Gold v7"` |
| 250 | Synthesis: folder README |

### Open items, Nov 15, 2026, after SN250 (the current list)

- **Mon Nov 16 checks:**
  - the tick recorder's first live day;
  - SN Gold v5 paper;
  - the give-back stop.
- **Owner's word:**
  1. deploy Gold v7 to Production (paper; WK-H's first entry is the Monday 15:15 after the deploy);
  2. Kite basket margin for 2 short NIFTY ATM straddle lots + 2 futures lots.
- **The crash test:** `docs/research/fno/2026-11-15-sn231/sn248.py --data-complete`, once NIFTY Jul–Sep 2020 (options 318 of 857 on Nov 15) and Jan–Jun 2020 are downloaded. Score once, unchanged.
- **Next ideas:**
  - band 0.8 + a synthetic options hedge (needs option legs in the runtime);
  - Gold v5's own unseen-year test (an N11 replay for 2021: a separate job).
- **Downloads:** the downloading agent continues back through 2020, then SENSEX.

### Commit index, SN231–SN250 and Gold v6 / v7

- `1690bb71`: Gold v6 runtime (`sn_wkh.py`).
- `5f67bb0b`: plan.
- `d87c0031`: SN231–SN234 and the amendment.
- `13850b41`: SN235–SN248.
- The Gold v7 runtime and docs commit follows.

## SN251–SN275 (Nov 16, 2026): Gold's gap days from Gold's own wallet, without margin (folder `docs/research/fno/2026-11-16-sn251`)

**Owner:**
- "use the same wallet that the Gold V5 is using … to trade on the Gold gap days … I don't want to use margin because there is potential of unlimited loss … the amount we can refill [is] by max the wallet's full amount … option buying every day has a potential to earn more than 10% … 25 slots till SN 275";
- and: why not hedge WK-H with options only.

**Method:**
- **Freezes:** plan `fb7e7523` (amendment `c22d0b0f` before SN271–SN272); engine `gl.py` / `ow.py` at `0555a559`; each Block C slot frozen before its run.
- **Tier A:** bought options only. **Tier B:** defined-risk spreads, as information.
- **One wallet:** SN110's contract. With no leg, `ow.py` reproduces Gold v5 exactly (₹8,50,882).
- **Samples:**
  - DEV: NIFTY Apr 2022 – Aug 2026;
  - TEST: Aug 20 – Oct 28 2026;
  - **two new buyer exams**, scored once per slot: EXAM-N (NIFTY Oct 2020 – Mar 2022, 286 sessions) and EXAM-S (SENSEX Oct 2024 – Apr 2026, 306 sessions).
- **Pass rule:**
  - G1: DEV net > 0 and ≥ 3 of 5 years positive;
  - G2: a same-budget random null;
  - G3: both exams positive;
  - G4: DEV positive at ₹400 and one minute late.
  - The pick is the max-min variant of ≤ 12.

| SN | Result | Verdict |
|---|---|---|
| 251 | Options-only WK-H: iron flies (wings 0.5 / 1.0 / 2.0) and condors, per lot over 5 samples −₹2.13 to −₹2.72 lakh (0–1 of 5 positive); largest loss per lot ₹1.1k–11k. WK-H with futures +₹3.86 / +₹4.19 lakh | Wings lose the profit |
| 252 | 944 sessions, 811 gap days (609 non-expiry + 202 expiry); Gold v5 +₹8,50,883, 25 of 46 months positive. ₹1,500 a session needs ₹697 more per gap day | Census |
| 253 | Exams sealed; ATM legs priced on ≥ 99.7% of sessions | Data |
| 254 | SN95-L: EXAM-N −₹17,654 (19 trades), EXAM-S −₹8,541 (21); SN171 lost every EXAM-N trade | FAIL |
| 255 | Buying every day: −₹150 to −₹660 per lot per day on every sample; random side 0 of 200 seeds positive on DEV | Cost of activity |
| 256–263 | Weekend straddles (−₹2.3 lakh DEV), weekday overnights, swing (exams + but DEV −₹70k), events (Budget pick, RBI straddles −₹20.9k), opening gaps, the cheap weekly straddle, LightGBM (exams −₹11.7k / +₹13.5k), gap-day afternoons | All FAIL |
| 264 | Expiry days: no unseen data; E03.2 in-sample only, 0 tickets on Production paper since Nov 5 | No verdict |
| 265–268 | No survivor | Not run |
| 269 | Wage pot from Gold v5 alone: ₹500–750 every session is affordable over years; the owner advances ₹0.5–3.1 lakh first (₹1.16 lakh from Jan 2024, ₹3.13 lakh from Jan 2023 at ₹750) | – |
| 271 | Overnight index ETF (cash): the tradeable 15:20 → 09:16–09:30 drift is about zero after charges and the ₹15.34 DP fee | FAIL |
| 272 | Pre-holiday calls (post-hoc): DEV +₹13,331, EXAM-N +₹25,327, EXAM-S +₹8,884, ~10 trades a year; fails G2 | FAIL by rule |
| 273–275 | – | Unused |

**Lessons:**
1. A defined-risk (winged) seller has a small deposit and a fixed worst case, but the wings cost as much as the weekly edge. What made WK-H work is the futures hedge, which needs margin.
2. With bought options only, Gold's gap days have no edge after costs, on two more unseen samples. The one real effect, NIFTY's overnight drift, sits in the closing and opening prints and cannot be collected with options or an ETF.
3. A daily income comes from Gold's profit through a wage pot, with money advanced at the start.

### Open items, Nov 16, 2026, after SN275 (the current list)

1. **Mon Nov 16 15:15:**
   - the first Gold v7 WK-H paper entry ("🥇 Gold v7 · WK-H (paper): sold …", a `gold_v6_wkh_weeks` row);
   - Tue Nov 17 hedges and the 15:24 close; Wed Nov 18 09:15 settlement.
2. **The 2020 crash test** (`sn248.py --data-complete`) after the download.
3. **Owner's decisions:**
   - a pre-holiday call forward paper watch (~10 a year);
   - a wage pot amount;
   - WK-H with real money only after the `SN_GOLD.md` gates and with margin.
4. **Do not repeat** on these samples:
   - everything in SN251–SN272;
   - options-only WK-H structures;
   - every-day buyers.

### Commit index, SN251–SN275

- Plan `fb7e7523`.
- Results: `0555a559`, `f781a9fa`, `fbc949aa`, `e60e28ba`, `24ca38b2`, `c22d0b0f`, `4773927b`, `4f91377e`.
- The docs commit adds this section.
- **Production:** `c6cbceb1` (PR #140, another release) carries SN251–SN257's research files; no runtime change from SN251–SN275.

## SN276–SN285 (Nov 16, 2026): every earlier gap-day signal combined, on all the data (folder `docs/research/fno/2026-11-16-sn276`)

**Owner:** "10 slots more. Try some other perspective … same wallet … learn from the good points of strategies … use whatever you want."

**Method:**
- Plan `c300be88` before any number.
- SN251's engine, unchanged.
- 1,465 pooled sessions (NIFTY Oct 2020 – Oct 2026, SENSEX Oct 2024 – Apr 2026), 21 features at 10:00.
- Learners walk-forward by half-year, 2022 H1 – 2026 H2, each trained only on earlier sessions.

| SN | Result | Verdict |
|---|---|---|
| 276 | Every plain 10:00 action loses on average on every sample (straddle −₹580 to −₹1,015, call −₹224 to −₹1,194, put −₹212 to −₹481) | Base rates |
| 277 | Action-value LightGBM: −₹1,28,556, 4 of 10 half-years positive | FAIL |
| 278 | Two-stage classifier: −₹1,34,370, 2 of 10 | FAIL |
| 279 | Vote of seven frozen signals: k = 3 DEV +₹13,988, EXAM-N −₹11,040, EXAM-S −₹28,680 | FAIL |
| 280 | Controls for the vote: pooled −₹973 (null −₹62.8k), ₹400 −₹53.9k | FAIL |
| 281 | Pre-holiday call positive on all four samples (ITM +₹46,674 over 73 trades); debit spreads and the breakout swing lose | Description |
| 282 | SN126-L: EXAM-N +₹132 (12 trades), ₹400 negative | FAIL |
| 283 | Cash-equity paper books: 4–5 forward sessions, slightly negative, cash conflict with Gold | Not a fit |
| 284 | The pre-holiday ITM call in Gold's wallet (information, in-sample): +₹14,970, positive months 25 → 28, worst month −₹38.5k → −₹20.5k | Watch candidate |
| 285 | Synthesis | – |

**Lessons:**
1. Weak signals combined stay weak. The 10:00 option's cost (₹200–650 a day) exceeds what any gap-day information predicts.
2. The pre-holiday calendar effect is the only buyer signal positive everywhere. It is post-hoc and rare (about 10 a year).
3. WK-H (Gold v7) won 57.6% of weeks over 368 weeks; it is not a partner strategy (margin, selling, automation).

**Open items** (added to the SN275 list):
- a pre-holiday ITM call forward paper watch on the owner's word;
- the next weekday NSE holiday is its first forward test.

**Commits:** `c300be88`, `c0521449`, `0dc1d2dc`, `d53009ee`, and the docs commit that adds this section.

## SN286–SN300 (Nov 16, 2026): the auditor's brief tested (folder `docs/research/fno/2026-11-16-sn286`)

**Owner:** "test it out see if you can agree to it … improve it … slots till 300." Brief: `docs/SN286_SN300_RESEARCH_BRIEF.md`.

**The auditor was right on SN284:**
- one call carried the in-wallet gain;
- Saturday special sessions were admitted;
- two 12:30 sessions booked 15:10 exits.

| SN | Result |
|---|---|
| 286 | Corrected holiday rule: ITM call DEV +₹22,932 (40), TEST +₹5,464, EXAM-N +₹10,050, EXAM-S +₹12,010; without the best day +₹4.2k / −₹3.0k / −₹5.1k / −₹14.4k; in Gold's wallet +₹18,016, −₹741 without the best. Forward ledger only |
| 287 | Partner: after the give-back alert, later entries made 145% of the change; "no new entries after the alert" better in 3 of 4 |
| 288 | Partner first minute at executable prices: −0.22% vs +0.09% control; not tradable |
| 289 | Recorder qualification built; the Nov 16 development day is clean |
| 290 | Real one-lot ATM round trip ₹90–100 (straddle ₹190); the model is ₹4–9 conservative; delay is noise |
| 291 / 293 | Packet candidates (futures pressure; lagging strike) frozen; forward verdict on the first 20 qualified sessions from Nov 17 |
| 294–296, 298 | Diagnostics, exit challenger and holiday shadow frozen on the same window |
| 292, 297 | Deferred |
| 299–300 | One-wallet contract written; verdict code frozen (`fwd.py`) |

**Open items:**
- `python fwd.py collect` before ~Dec 20; `python fwd.py verdict` once 20 sessions qualify (about Dec 17–19).
- Coaching idea (owner's call): after the give-back alert, a "stop adding trades" line.

**Commits:** `d5cfb8f1`, `9153f68b`, `64cfa082`, `d5168b0f`, and the docs commit.

## SN301–SN315 (Nov 16, 2026): the forward test protected, Gold v5's own losses audited (folder `docs/research/fno/2026-11-16-sn301`)

**Owner:** "use these 15 slots to make me a better strategy … losses are cut and nothing unreasonable is happening." Review: `docs/SN301_SN315_RESEARCH_AUDIT.md`. Plan `94c772cd`.

**Agreed with the auditor, fixed:**
- the verdict could pass on missing evidence (unknown Gold days, an empty control);
- `fw.hold` filled into a zero-quantity bid and booked missing exits early;
- the collector could freeze a partial copy;
- raw totals were compared against a control at a different frequency.

**Not agreed:**
- SN299's "debit within ₹3,000" was a wording error; the one-wallet rule (premium ≤ wallet − ₹15,000, ₹3,000 stop) decides, and the strict share is reported;
- the original freeze is kept and reported as superseded;
- SN312 was a cost audit first.

| SN | Result |
|---|---|
| 301–305, 300a, 315 | Verified archive, executable contract, Gold labels, matched controls, affordability, amended verdict and replication block (`fw2.py`, `fwd2.py`; 12 tests). Session 20 = Dec 23 |
| 306 | One-minute delay on 748 real-quote cases: entry late PE −₹50–56, CE +₹10–19, straddle −₹37–39; exit late −₹19 to +₹37. The cost is at the entry |
| 307–309 | Price cap, order-flow change, premise-fail exit: frozen forward comparisons |
| 310 | Gold v5 waterfall (156 trades): losers −₹6.00 lakh (first piece −₹5.01 lakh, adds −₹0.99 lakh; 78 at N11's exit, 8 stops; overshoot ₹988); winners +₹14.51 lakh (adds +₹2.77 lakh); extension +₹232 over 16 trades; fees + stress ₹1.98 lakh; the best 10 trades are 71% |
| 311 | Scale-in cash: Gold v5 never over-commits (G1 = G0); "true cash" +₹62.6k at ₹205 but +₹5.7k at ₹400 and less in 2023–24, so it fails the frozen rule; no change |
| 312 | Real in-the-money costs (ATM to 3 ITM, 1–6 lots): the model is ₹0.6–6.5 a lot conservative; depth ample; no challenger |
| 313 | Partner, order by order: new trades after the alert lost in 3 of 4 sessions; "no new trades" better in 3 of 4 |
| 314 | Dec 7 (NSE CAS 2.0): F&O to 15:45, expiring index contracts stop at 15:30; about 15 engine files assume 15:40 (`SN314_CLOCKS.md`); runtime slice on the owner's word |

**Lesson:** Gold's losses are signal losses, not execution losses. Its cost model, stops, adds and cash checks are sound at its sizes, so the remaining lever is which entries it takes, and every frozen attempt there has failed (SN92–SN285).

**Open items:**
- `python fwd2.py collect` evenings until Dec 23;
- `python fwd2.py verdict` once;
- the Dec 7 clock slice (owner's word);
- the partner coaching line (owner's call).

## SN316–SN330 (Nov 16, 2026): the partner's chart sequence, Gold's entry failures, 2019–2020 history, Gold V8 (folder `docs/research/fno/2026-11-16-sn316`)

**Owner:** the auditor's SN316–SN325 plus five own slots, toward a real-money Gold V8. Plan `657b74b9`. **Correction given to the owner:** SN301–SN315 found no Gold improvement ("true cash" adds failed the frozen ₹400 test).

| SN | Result |
|---|---|
| 316 | Seal: 2019 H2 122 sessions (options on the days before each expiry; Jul 30 and Nov 6 without the ATM pair); 2020 Q1–Q3 all 39 expiries with legs and hedge marks (Mar 13 halt: no 09:30 bar); Jan 16 – Apr 2 2026 52 one-second days |
| 317 | Frozen crash exam: Gold v7's WK-H leg PASS (+₹42,570 per lot, Mar 2020 −₹23,171); band 0.6 +₹64,999; unhedged March −₹69,274 |
| 318 | One-minute break-and-hold, unseen 2019: FAIL (Q3 −₹2.10 lakh, Q4 −₹2.25 lakh), below every random book on every sample |
| 319–322 | The partner's 1m / 30s / 5s sequence: dev −₹277 to −₹299 a trade on every clock; test (Jan–Apr 2026, once) break −₹337, five-second pullback −₹357, gate −₹353; ceiling ≥ ₹750 on only 12–20% of breaks. FAIL |
| 78 | SN78's picks on their reserved window: −₹6,015 / −₹44,576. Retired |
| 323 | Gold's losers do not fail early: 0 of 86 broke N11's level in the first minute; 62 never did |
| 324 | Cancel failing TPB entries: avoided ₹15.7k, missed ₹36.1k. Not adopted; a one-minute-late TPB entry costs ₹29k |
| 325 | `fw3.py` (the chart sequence on packets + the wallet) frozen; scored with SN300a after Dec 23 |
| 326 | Gold v5 on 2022: blocked by the N08 → N11 stack; step plan written |
| 327 | Real-money risk: month refills ≤ 63% of the wallet (81% at ₹400); 20-session ≤ 96% (123%); worst month −38% |
| 328 | `GOLD_V8.md`: Gold v5's rules plus a real-money execution contract and gates |
| 329 | Dec 7 NSE CAS 2.0 hours in Dev (`52a77adf`), full suite passes; not deployed |
| 330 | Nightly verified collection task registered |

**Lessons:**
- The seconds clocks add no edge for a bought ATM option: the round trip costs more than the moves the breaks offer.
- One- to three-minute breaks in NIFTY tend to revert (worse than random).
- Gold's losses are not failed setups.
- The futures hedge is what carries WK-H through a crash.
- **Gold V8 = Gold v5, executed for real money.**

**Open items:**
- deploy SN329 before Dec 7 (the owner's word);
- the Gold V8 live module (the owner's word);
- `fwd2.py` / `fw3.py` verdicts after Dec 23;
- SN326's 2022 replay as its own round.

## SN331–SN350 (Nov 16, 2026): the failed break, Gold's execution and the wage (folder `docs/research/fno/2026-11-16-sn331`)

**Owner:** the auditor's SN331–SN340 plus ten own slots; "much more profitable than the current best Gold … the wage". Plan `95287d3f`.

| SN | Result |
|---|---|
| 331 | Failed breaks reverse only 0.5–2.1 index points in 5 min; buying the reversal −₹70–89 a trade at zero stress, −₹275–295 at ₹205; archive real prices −₹131 to −₹169 gross. No room |
| 345 | Reversal + 5-second confirmation: FAIL (−₹278 to −₹294 a trade) |
| 344 | Minute reversal (DEV, TEST, 2019 Q3 / Q4): FAIL, below every random book; entries after fast moves cost about ₹95 a lot more than random |
| 335 | Rebalance days: closed (mean rank 0.76, mixed signs) |
| 334 / 343 | Not triggered / already answered by SN264 |
| 341 | Gold's lot ceiling on real depth: 12 lots |
| 339 | A fixed ₹30k reserve stalls Gold once the wallet grows (386 paused sessions); ₹60k holds at ₹205 |
| 342 | Wage with reserve = one wallet: ₹881 a session at ₹205 (₹14.5k a month; 14 of 45 months pay), ₹414 at ₹400 |
| 347 | NO_STAND half-size gap fill: FAIL (₹8.51 → ₹6.98 lakh) |
| 348 | 4 / 5 growth steps: ₹11.65 / ₹15.51 lakh, worst month −₹54.8k / −₹83.6k; FAIL the frozen rule (risk choice) |
| 350 | V8 configuration = Gold v5 |
| 336 | Gold on 2022: route recorded (N08 POINTS → N09 / N10 / N101 / N11 replays); its own round |
| 337 / 338 | V8 shadow own inventory; order-lifecycle state machine (Dev, tests) |
| 332 / 333 / 340 / 346 / 349 | Frozen in `fw4.py`; scored once after Dec 23 |

**Lessons:**
- NIFTY's short-horizon option market prices fast moves instantly. At any tradable clock, buying after a move (with or against it) is worse than random, and random is about break-even before the stress.
- Gold's return depends on its entries' timing (a late entry costs) and on capital.
- The wage scales with the capital the owner can keep beside Gold.

## SN351–SN365 (Nov 16, 2026): information before the option reprices, the corrected wage, Gold's execution (folder `docs/research/fno/2026-11-16-sn351`)

**Owner:** the auditor's SN351–SN360 plus five own slots, one slot at a time. Plan `cbdbc54c`, amendments A1–A6.

| SN | Result |
|---|---|
| 352 | SN342's wage counted ₹71,250 of growth cash twice. Corrected journal: ₹5,82,754 over 45 months = ₹785 a session at ₹205 (₹318 at ₹400); 14 / 45 months pay; 2023 pays nothing; growth never short of cash |
| 363 | Never-failing fixed salary: ₹500 a month (owner ₹60k), ₹3,000 (₹90k), ₹4,500 (₹1.2 lakh) at ₹205; ₹0 / 2,500 / 3,500 at ₹400. ₹15,750 a month needs ₹3.7 lakh at ₹205, impossible at ₹400 |
| 353 | Auction fields decoded (A2). Price-only gap: +₹183 gross, −₹30 at ₹205 (172 sessions), −₹257 on real quotes: CLOSED. Queue-pressure arm and a post-hoc 0.2–0.5% gap watch frozen forward (`fw5.py`, SN300a's window) |
| 361 | Opening premium rich: ATM straddle at 09:16 −₹226 by 09:45, −₹338 by 10:15 (−₹156 / −₹255 against 11:00; 885 sessions; every year) |
| 365 | Auction agreement with Gold's trades: p = 0.55, no information |
| 351 | No state has room at ₹205 (8,488 positions; hindsight ceiling ₹1,048 a lot; −₹295 at 20 minutes; buying with a just-finished move worst) |
| 362 | Gold via SENSEX options: FAIL (one-trade mean; −₹292 at ₹400). Real per-lot spreads are equal (₹16 / ₹17) |
| 359 | V8 lifecycle on real depth: 9 / 10 decisions entered with every lot; on priced exits V8 ₹1,25,866 vs replay ₹99,262 at ₹205 |
| 354 / 355 / 356 | Blocked / untestable here / blocked and mostly unaffordable (BANKNIFTY lot 30) |
| 357 / 360 | Not triggered |
| 364 | CAS 2.0 closing window frozen forward (`fw6.py`, needs the recorder to 15:46) |
| 358 | Not run: the next round's first slot (N08 → N11 route on 2022) |

**Lessons:**
- The opening auction's direction is real information, already in the price to within the costs. Opening option premium is rich.
- No entry state for a bought option has room after ₹205. The room is in the path (hindsight), which no tested predictor reaches.
- Gold's wage is capital-bound and lumpy. A promised salary is set by the worst early stretch, not the average.

## SN366–SN380 (Nov 16, 2026): Gold's unseen 2022 exam, the opening family, chain pressure sensors (folder `docs/research/fno/2026-11-16-sn366`)

**Owner:** the auditor's SN366–SN375 plus five own slots, one at a time with quality. Plan `3740b461`, amendments B1–B4.

| SN | Result |
|---|---|
| 366 | NIFTY 2022 exam (second opening after a disclosed volatility-source correction): N10 retry −₹3,803, CUSHION −₹4,363, N08 −₹6,874, NO_STAND −₹8,630, N11 −₹14,079, random median −₹76,062. N11 sheet A no, B no; N10 sheet A–C yes, D not run. **Gold v5 from ₹30k: −₹15,281 at ₹205 (−₹23,511 at ₹400), 4 of 12 months positive** (2023: −₹12,107, 3 of 12) |
| 371 | Opening direction at 10:15: no value left (gap −₹361 at ₹205 vs coin −₹386); auction direction reverses (−₹619 vs −₹245) |
| 376 | ITM leg at 09:16 keeps ₹55–110 more: auction +₹67 at ₹205 (171, 2026); 2022–26 gap negative → SN380's forward candidate |
| 377 | Opening richness ∝ overnight IV jump (straddle −₹226 / −₹282 / −₹550 by 10:15 by tercile); cheap opens still −₹148 at ₹205 |
| 368 / 378 / 379 / 372 | Wings (two tenors not computable on the archive; the front tenor points the other way), synthetic-forward lead (+3.2 bp / 15 min), signed flow (15 events), expiry pressure (9 events): all closed |
| 367 | ₹750 bracket: 37% reach it (fills +₹982), 58% time out at −₹851; bracket = fixed hold = coin |
| 373 | Resting mid limit: saves ₹17.7, misses the winners; retired |
| 374 | Withdrawals: profit-only pays nothing in 63% of months; a payout down to the day-stop cover traps the account |
| 370 / 369 | Hong Kong reopen (+1.35 bp DiD, p 0.15) closed; NIFTYBEES blocked (no data) |
| 380 / 375 | fw7 frozen forward (AUCTION ITM); SN375 not triggered |

**Lessons:**
- Direction at the open is real for 20–30 minutes and already priced at 10:15.
- Chain pressure precedes 3–9 bp moves, too small for a bought option's hourly cost (₹300–850).
- Gold's first year from ₹30k lost in both 2022 and 2023: a real-money plan must expect it.

## SN381–SN395 (Nov 16, 2026): the opening trade made honest, Gold's 2022 exam closed, the wage's capital (folder `docs/research/fno/2026-11-16-sn381`)

**Owner:** the auditor's SN381–SN390 plus five own slots. Plan `c6e99cee`.

| SN | Result |
|---|---|
| 381 | fw7a companion audit (cash room, price cap, receipt-time signal, paired judge), 9 synthetic tests |
| 382 | Opening ITM under honest rules: +₹46 a session at ₹205 (−₹7 without the best day), −₹137 at ₹400; −₹447 after Sep 7. ITM beats ATM +₹122 a trade (se 39) everywhere |
| 383 / 384 | ITM = mostly a larger delta; the 09:36 exit does not help |
| 385 / 391 / 393 | Cash agreement (coverage), indicative drift (9 sessions), auction size (the opposite): closed |
| 394 | Cheap opens +₹396 / +₹199 per session (73), p 0.031, best of ~10 splits → fw9 forward |
| 387 | 2022: 51 of 52 option-less days are expiries; N10 sheet D yes (₹4,41,853 vs CUSHION ₹4,15,120); N10 retry is the sheets' lead |
| 392 / 388 | Gold v5 2022: N11 signals −₹15,281 vs N10 +₹4,681; the stand-aside skipped 6 big winners (cost ₹5,449); 2022–26 deployed still leads in sample |
| 389 / 395 | Profit-only from ₹60k: ~₹525 a session on a bad start, 21-month dry spell; ₹750 a session needs ₹2–5 lakh outside |
| 386 | fw8 packet-level signed flow, forward (92% signable) |
| 390 | Not triggered |

**Lessons:**
- Honest execution rules turn the opening edge into break-even; the robust part is choosing ITM over ATM.
- A filter that sits out bad stretches misses the trend book's big winners.
- The daily wage is a capital question.

## SN396–SN410 (Nov 17, 2026): the opening trade on the real clock, "cheap" tested four ways, N10 vs N11 inside Gold, Gold's clocks (folder `docs/research/fno/2026-11-17-sn396`)

**Owner:** the auditor's SN396–SN405 plus five own slots. Plan `00693405`.

| SN | Result |
|---|---|
| 396 | HONEST 09:16:00 clock: −₹81 / −₹235 a session (ORIGINAL +₹46 was a one-minute lead); LATE −₹253; CHEAP +₹335 / +₹182; archive costs ≈ model in the median; fw7b / fw9a frozen (16 tests) |
| 397 | Cheap = mostly direction (+12.7 vs +2.4 points), calendar-tangled, no slope in the jump; reality check p 0.80 / studentized 0.90 |
| 399 | Hurdle about 13 index points against a forecast of 1.3: never trades |
| 406 | 720 cells: no unfiltered cell positive at ₹400; CHEAP patch at ₹205; best cell p 0.83 |
| 407 | fw9's rule on 2022 – Dec 2025 gap days: +₹19 / −₹147; does not support fw9 |
| 410 | Before Sep 7, +14.5 points follow-through after 09:16; from Sep 7, spent before 09:16 (−13) |
| 398 / 401 / 402 | Roll days 3 of 7 affordable; SENSEX on NIFTY expiry days −₹547; RBI 3 events all stopped: closed |
| 403 | 2022 N10–N11 gap = the stand-aside only; blocked trades −₹822 over five years; DEPLOYED leads 2022–26 |
| 404 / 408 | Option richness at entry predicts no Gold outcome |
| 409 | Gold +1 min latency −7.7%; −1 min (lookahead) +₹2.48L; intact |
| 400 | Kite bundles about 198 trades per packet: strict signing 0%; fw8a frozen on last-print flow |
| 405 | Gold ₹791 / ₹409 a session, trades 17% of sessions; the opener never conflicts with Gold |

**Lessons:**
- A bar labelled by its start and traded at its close is a minute ahead of a live decision.
- "Cheap" sorts opening mornings but has not shown an edge after the search.
- Gold's stand-aside is a path effect; its losses are signal losses, not price losses.

## SN411–SN425 (Nov 17, 2026): observability, the hindsight ceiling, other indices, the bank residual, Gold's robustness (folder `docs/research/fno/2026-11-17-sn411`)

**Owner:** the auditor's SN411–SN420 plus five own slots. Plan `e5cc95b7`.

| SN | Result |
|---|---|
| 411 | fw7c / fw9b frozen (today's trade, pre-decision offset, 2 s strike / book); live entries 44–53 s after the bar end against the replay's 59 s |
| 412 | Hindsight: median ₹9,376 a day, every day ≥ ₹750; fixed-clock windows 83–97% ≥ ₹750 |
| 413 | BANKNIFTY front ATM affordable 30% (93% in its last week); FINNIFTY thin; recorder Dev change `1bfed1d0` (not deployed) |
| 414 | The bank residual does not persist (−4.4 bp at 45 min); it reverses at 15–30 min (post hoc grid) |
| 418 / 419 | Stand-aside: one regime, mildly positive at one lot; opener + Gold in one ledger +₹22.8k / +₹12.2k |
| 421–425 | Gold: signal side flat, exposure side leverage; the replay excludes expiry days (₹617 a real session); no expert is dead weight; size ladder 1 lot ₹2.14L → cap 5 ₹15.5L; tail: no-bid bound ₹1L |
| 415 / 416 / 417 / 420 | Closed at feasibility / protocol only / F1 pre-registered (BANKNIFTY residual fade) |

**Lessons:**
- The opportunity exists every day; selection is the problem.
- Gold's empty days are a signal shortage.
- Gold's size is the owner's leverage decision.

## SN426–SN440 (Nov 17, 2026): expiry mornings, the hindsight decomposition, exits, the loss bound, Gold's feed / edge / cost (folder `docs/research/fno/2026-11-17-sn426`)

**Owner:** the auditor's SN426–SN435 plus five own slots. Plan `123301ac`.

| SN | Result |
|---|---|
| 426 | 263 non-Gold dates = 251 expiries + 4 special + 8 data holes; 66 signals skipped while Gold held a position |
| 427 | Hooked N11 rerun (parity); expiry-morning candidates on 27 of ~200 expiry days; 5 priced, all net losers; insufficient |
| 428 | Hindsight per decision: side +1,269, exit +1,240, entry minute +2,126, coin −169 (₹205); break-even direction ~56% (₹205) / ~68% (₹400) |
| 429 / 439 / 439b | Checkpoints, no-progress cuts and breakeven locks all cut Gold's winners; headroom ₹2,085 a lot |
| 434 | A full-loss bound leaves Gold 4 trades; the trigger stop's worst debit at risk is ₹1 lakh |
| 436–438 | No extra feed book, size-by-expert rule or entry-hour cutoff helps both periods |
| 440 | Paper fills vs model: median +₹6.5 a lot; ₹205 is the realistic Gold cost (₹617 a real session) |
| 430 / 431 / 432 / 433 / 435 | Blocked (NSE access) / blocked (recorder) / plumbing (CONFIRM-5) / back-fill 1 trade / not triggered |

**Lessons:**
- Selection needs ~56–68% direction accuracy for a one-hour ITM trade.
- Gold's exits cannot be improved by simple rules.
- Gold's realistic income is ₹617 a real session at ₹30k.
