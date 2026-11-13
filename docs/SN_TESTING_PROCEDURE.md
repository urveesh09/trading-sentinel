# SN testing procedure: how every SN strategy was built, tested and judged (Nov 12–13, 2026)

This is the exact method behind SN01–SN90 and SN Gold v1–v5 (`docs/SN_STRATEGY_HISTORY.md`). An agent who follows it gets numbers comparable with every table in that file. The general house rules underneath are in `docs/RESEARCH_TESTING_METHOD.md` and `docs/FNO_YEAR_DATA_TESTING_METHOD.md`; this file is what SN added or fixed.

---

## 1. Ground rules (never broken)

1. **Research runs only in the Dev checkout** (`C:\Users\Urveesh\Desktop\trading-sentinel`). It never writes to Production, never calls Kite or ICICI for orders, never changes a runtime setting.
2. **Freeze before scoring.** The study script (grid, rule, scorer) is committed and pushed before the first run whose numbers decide anything. A scorer that writes `results.json` refuses to run twice.
3. **Seen data is seen.** NIFTY 2023, 2024, 2025, Jan–Oct 2026 (1-minute) are all seen, and so are both 1-second archives after SN79. In-sample results are description; only held-out years, the random NULL and forward or unseen sessions are evidence.
4. **Every SN at every wallet** (the owner's order, Nov 12). See section 6.
5. **Charges are real; slippage is stressed.** See section 4.
6. **Sealed data only.** A study copies its data into its own `_local/` (git-ignored), hashes it, and asserts the hash on load. It never reads the live Breeze download database. Every ICICI download goes through the `breeze-history-download` skill.
7. **Machine shared with Production.**
   - Market hours: at most 4 worker processes and ≥ 2 GB free RAM. Use one per year in the parallel searches.
   - Long jobs run as foreground slices of ≤ 9 minutes that resume from saved evaluations.
8. **Python:** `python-engine\winvenv\Scripts\python.exe` (a bare `python` is a Store stub). Cap pytest with `timeout`.

---

## 2. The data layers

| Layer | Built by | Grid | Fill model |
|---|---|---|---|
| 1-minute sessions (742 non-expiry sessions with options, 2023 – Oct 28 2026) | `docs/research/fno/2026-11-12-sn01/sn01_data.py` from the four sealed year datasets | 375 minutes, 09:15–15:29, index OHLC, front future OHLCV, nearest-weekly options OHLCV (ATM±4–8 strikes) | Each minute's close is an observation; options keep NaN when unprinted (a fill needs a printed minute, a mark carries forward) |
| Option OI | `2026-11-12-sn09/sn09_oi.py` | Same grid; OI snapshots every 3 minutes | – |
| Daily ADX/DMI | `2026-11-12-sn06/sn06.py daily` from every trading day (966) | Yesterday's reading gates today | – |
| N11's real entries | N11's stored replays (`docs/research/simulation/2026-11-02-fno-n11/_local/evals`), or re-run through N11's lab chain (`2026-11-12-sn07/sn07_lab.py`, `sn08_lab.py`) | Entry and exit minute, contract, strategy | Parity: SN's simulator reproduces N11's stored entry and exit prices to 0.00 (SN02) |
| 1-second archives | `2026-11-13-sn78/sec_data.py` from sealed copies of the download agent's zips | 22,500 seconds, index + opening-ATM CE/PE | A fill needs a printed second |
| 10-second expiry days | `2026-11-12-sn10/sn10.py build` | 2,250 ten-second bars | Opening-ATM CE/PE |

**Bid/ask model, everywhere:**
- bid = close − half, ask = close + half, where half = half the 75th-percentile spread the archive recorded at that premium (₹0.10 under ₹50 … ₹0.80 under ₹450), rounded to the ₹0.05 tick;
- buy at the ask, sell at the bid.

---

## 3. Causality and fill conventions (the simulator code enforces these)

- A signal at minute (or second) `i` reads only bars ≤ `i` of the session plus earlier sessions; the fill is at `i`'s close.
  - Tests prove it: `test_sn01.py::test_signals_are_causal` changes bars after a cut and asserts signals up to the cut are unchanged.
  - SN09's OI families were checked the same way.
- A 5-minute bar is known at its last minute's close. A 30-second bar is known at its last second.
- **Stops:** a stop-market on the option's low (at the bid). It fills at the stop, or at a gap-through open.
- **Targets:** a sell limit on the high.
- **Same-bar tie:** if a stop and a target both touch in one bar, **the stop is taken**.
- **Time stops and session end:** sell at the close bid. Flat by 15:15, 15:10 for SN Gold's extension, or 15:00 / 13:30 (expiry days) in the empty-day books.
- **Day loss limit** (20% of the wallet): a stop price on the option at the level where the day's remaining room is used up, after charges and stress. A gap can fill slightly beyond it; that is reported, never hidden.
- **Scale-in:** allowed only when the WHOLE position's stop still fits the day's room. SN28 found and fixed a version that broke the limit.
- **One position at a time** in all SN books. A signal that comes while a position is open is skipped.
- **Wallet affordability:** a lot must fit the wallet; else one strike further out of the money; else skip.

---

## 4. Money

- **Charges:** the shipped model `python-engine/fno_costs.py`, today's NFO rates, on every leg. Zerodha's page was checked on Nov 12 and is identical: brokerage ₹20/order, STT 0.15% on sells, NSE 0.03553%, SEBI ₹10/crore, stamp 0.003% on buys, GST 18% on brokerage+SEBI+transaction, IPFT.
- **Slippage stress:** +₹205 per lot per trade, the house standard; +₹100 per leg-lot for multi-leg structures.
- **Robustness levels:**
  - +₹0, +₹100, +₹300, +₹400;
  - 1% or 2% of premium per side (`STRESS_PCT` in the labs);
  - entries 1 or 2 minutes late;
  - partial fills (only one lot of two).
- **Net at the end** = won on winning days − refilled (the sum of losing days).

---

## 5. The selection procedures (how a "pick" was made without fooling ourselves)

1. **Leave one year out (LOYO)**, the main tool (`sn03_run.loyo`):
   - for each held-out year, choose the variant with the best total (or worst-year) result on the other three years, and record its result on the held-out year;
   - the held-out sum is the honest estimate of the procedure.
2. **The random NULL.** The same search, same budget and same exits, with random entry minutes and sides. A rule must beat the NULL's held-out result, or its edge is luck or a market effect.
3. **Genetic search** (SN01, SN04, SN06, SN09):
   - a seeded random pool;
   - then N generations of mutation and crossover per fold, selecting on training years only;
   - fitness = worst training year's net per session, valid only above an activity floor (trades per session);
   - evaluations are saved to `_local/evals.jsonl` (resumable).
4. **Chronological split** for short data (the 1-second books): choose on the earlier months, score once on the later ones (SN78).
5. **The one unseen test** (SN79): candidates frozen in a committed script; scored once on data no SN rule had opened (the Nov 12 1-second archive, Jul 28 – Nov 12); PASS = test net > 0 at +₹100 AND above the random pick.
6. **Small fair contests.** When several kept parts are combined (SN69), compare only those few candidates by LOYO, to limit selection luck.
7. **Tuning neighbours** (SN31–SN36). A kept setting's neighbours must be close (a plateau); a lone spike is rejected.

---

## 6. Wallet scoring (every SN)

`gold.py` / `lab.py` `run()` scores one variant on:

| Wallet | Meaning |
|---|---|
| A ₹15k 1 lot | Fixed wallet, one lot |
| B ₹20k 1 lot | Fixed wallet, one lot (buys N11's own contract more often) |
| C ₹30k sized | Fixed wallet, 2 lots on high-volatility days (yesterday's ATR% ≥ the median of prior sessions), else 1 |
| G0 / G2 / G3 (Gold) / G5 | Growing from ₹15k: +50% after net profit equal to the wallet, stopped after 0 / 2 / 3 / 5 steps; lots floor(W/15k), halved on low-volatility days |
| F (SN52) | A real account with no refills: equity carries losses; keeps 1 lot while ≥ ₹7,500; sizing equity capped |

**Output per variant and wallet:** per year (net, refilled, days won / lost / no trade, worst day); the four-year totals; net at the end. The held-out line prints the LOYO sum per wallet against the reference (v3, v4 or v5).

---

## 7. Frozen versions and verification

- Each SN Gold version is frozen as a copy of the exact harness (`docs/research/fno/sn-gold/gold_v3.py`, `gold_v4.py`, `gold_v5.py`) with:
  - its config (`SN_GOLD_V*.json`: the variant dict and the expected four-year totals per wallet);
  - a verifier (`verify_gold*.py`) that checks the harness hash, re-runs, and exits 1 on any difference;
  - a git tag (`sn-gold-v3` / `-v4` / `-v5`).
- **New experiments copy the latest frozen harness into a new lab;** the frozen copies are never edited.
- **Parity checks before trusting any harness:**
  - the reference variant must reproduce the previous version's numbers exactly (each lab's "SN Gold vN" row);
  - SN02 reproduced N11's stored trades;
  - SN07's lab chain reproduced N11's stored replays byte for byte.

---

## 8. The runtime module and its tests (how Production code was proven)

`python-engine/sn_gold.py` mirrors v5's rules on live quotes. `python-engine/tests/test_sn_gold.py` (20 tests) pins:
- the settings against `SN_GOLD_V5.json`;
- lots, ITM depth and contract choice;
- the day stop spending exactly the room;
- wallet growth capped at 3;
- ATR from completed 1-minute candles only;
- on a real temporary database:
  - entry from N11's paper record and snapshot;
  - the N11-synced exit with charges;
  - extension and its trail exit;
  - scale-in fitting or refusing;
  - the day stop;
  - skips (position open, stand-aside at 0.85 vs 0.9);
  - the day ledger with refill;
  - switched off;
  - the ₹30k production sizing;
- that the module imports no order path.

Before deploy: the full engine suite (6,385 passed, 4 skipped), a re-run of the module and N11 tests on the final config, `verify_deployment.py` (exit 0, receipt), and the settings read back from the running engine.

---

## 9. Pitfalls found and fixed during SN (do not repeat them)

| Pitfall | Where | Fix |
|---|---|---|
| Day target slightly missed by the exit's own STT | SN01 | Iterate the target price with the exit's charges; ceil to the tick |
| Scale-in let a day exceed the 20% limit | SN28 | Whole-position stop must fit the room, else no add |
| ATR inflated by sparse or late price samples | Runtime module tests | Read the 1-minute ATR from Kite futures candles (completed minutes); sampled bars only as a fallback |
| Daily ADX computed on non-expiry sessions only (20% of days missing) | SN06 | Build daily bars from every trading day of the sealed datasets |
| "2 minutes earlier" entry used an unfinished 5-minute bar (look-ahead) | SN07b | Declared invalid; only the bar's closing minute is allowed |
| Doc staging changed CRLF lines in shared docs | Docs ritual | Edit working copies as bytes; re-check each file's unstaged diff counts (50/42/40) |
| Selection luck mistaken for edge | SN06 combo (+₹2.0 lakh in-sample → +₹68k held out), SN78 (+₹13–17k → negative) | Always LOYO + NULL; one frozen unseen test |
| Test files reading wallet defaults after the production wallet changed | Runtime tests | Mechanics tests pin their own wallet; one separate test pins production |

---

## 10. Reporting format (what the owner gets)

For every SN:
- the idea;
- the result (in-sample and held out, against random);
- what it taught;
- kept or not.

The tables show per year profit / refill, won / lost / no-trade days, worst day, and net at the end, for every wallet. Results are always labelled in-sample or held-out; a pass only ever means "candidate for forward or paper", never real money without the owner's word.
