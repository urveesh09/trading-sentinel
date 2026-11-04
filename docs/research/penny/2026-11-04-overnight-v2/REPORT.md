# Penny overnight v2 — report (November 4, 2026)

## Result in plain words

Penny stocks make their money **overnight** and lose it **during the day**. Across
1,000+ penny-band stocks and eight years (2019–2026), the average stock gained
about +0.5% from the official close to the next opening auction and lost about
−0.5% from the open to the close. The stocks EDGE picks gained **+1.3% overnight**
on average, then fell **−1.0% to −1.2%** the next day.

That one fact explains the whole Penny family:
- The **EDGE overnight book** is on the right side. It earns little only because of
  how it trades: it pays the ask at 15:20 (~0.36% measured), splits ₹25k into three
  small tickets (the fixed ₹15.34 DP charge costs 0.18% each). Its exit job runs at
  09:17: the paper model prices the auction open, but a real order sent then would
  sell after the auction, when prices have faded ~0.5%.
- **EDGE daytime, Smart V1 and Smart V2** buy during the day. They fight a −0.5%-a-day
  drift before any fee. No filter or genome fixes that, which is why the earlier
  search found Smart losing before costs.

**Overnight v2** keeps EDGE's own signals and changes how they are traded:

1. **Buy at the official close** in the NSE post-close session (15:40–16:00).
   Zerodha fills CNC market orders there at the closing price, so there is no ask to pay.
2. **Sell in the 09:00–09:08 pre-open auction**, at the opening price, not at 09:17.
3. **Two equal halves** of the book instead of three risk-sized tickets.
4. **Overnight-history screen**: a pick's shrunk 60-night overnight mean must be ≥ 0.1%
   (the earlier agent's G05 idea; the only selection rule that held out of sample).

At a fixed ₹25,000 (no compounding), against today's book at its measured entry cost:

| Window | Today's book | v2 rules only | v2 + post-close entry |
|---|---:|---:|---:|
| Kite cache, Jul 2025 – Sep 2026 | +23,158 | +30,623 (+32%) | **+52,654 (+127%)** |
| Yahoo, Jan 2023 – Oct 2026 | +116,027 | +158,807 (+37%) | **+231,005 (+99%)** |
| Yahoo, Apr 2019 – Dec 2022 (exam) | +100,175 | +123,886 (+24%) | **+188,667 (+88%)** |

Every book was positive in every year. Peak drawdown fell (exam 27.7% → 18.6%).

**What this is not.** These are daily-bar replays, not fills. Under my own frozen exam
rule **every finalist failed** (see below). The biggest gain depends on post-close
orders actually filling, and **no historical data can show that**. Production's own
forward record so far (20 closes to Oct 21) was −₹991, with the costs taking the edge.
Hence the next step is a declared forward shadow plus a read-only post-close probe.
Nothing here is live trading.

## What I learned from the earlier search (e0ad826) and did differently

| Earlier search | Here |
|---|---|
| Fixed 108-stock cohort | Broad band universe: 1,535 Kite tickers, 874 Yahoo names (the live book ranks ~1,100) |
| Execution fixed; costs only stressed upward | Execution treated as the design variable: post-close entry, auction exit, ticket size |
| "Two slots" read as new alpha | Shown to be fee economics (DP is per scrip) and kept as such |
| Genome search judged in-sample | Search walk-forward (pick on one block of years, score on the other) plus a null |
| — | A per-stock return model, rejected after it was caught trading spread bounce |
| — | The intraday drift that makes Smart lose, measured |

## Data and parity

- **K**: stopped-Production Kite daily cache copy (Oct 3): 1,535 band tickers, Jul 2025 – Oct 1 2026
  (broad only from Jun 2025). Already seen by the Oct 7 live-universe study.
- **Y**: public Yahoo daily, 874 requested, 872 returned, 2019 – Nov 3 2026. Zero Breeze,
  broker or Production calls. Split tickers are cut before their last split; zero-volume rows dropped.
- **Exam**: Y from Apr 2019 to Dec 2022, sealed in `PLAN.md` (commit `6532f15`) before any
  arm was scored. Opened once, after the finalist freeze (`f11a16a`). Caveats: 144 of the 874
  names were in the earlier study's universe, which trained on those years; survivorship
  (the universe is 2025–26 band membership).
- **Minute data** (Production exports, Jul 30 – Nov 3 2026) only for microstructure checks.
  The reserved Jan–Jul 2026 `penny-h1` archive was **not opened**.
- **Parity**: the lab reproduces the shipped `run_overnight_book` exactly: 175 closes,
  0 mismatches, net equal to 4 decimals, costs identical to `calc_penny_costs`
  (`parity-2025-07-15-2025-10-31.json`). The runtime night screen equals the research
  feature on 400 real cases (`night-parity.json`, max difference 7e-18).

## Iterations

**Round 1, execution and fees** (`results/round1.json`). Shipped picks, fixed ₹25k:

| | Kite (+0.36%) | Kite post-close | Yahoo 2023–26 (+0.36%) | Yahoo post-close |
|---|---:|---:|---:|---:|
| Shipped (3 slots) | 23,158 | 43,899 | 116,027 | 183,094 |
| Two equal slots | 30,810 | 52,792 | 151,419 | 224,393 |
| One slot | 35,561 | 55,638 | 180,410 | 256,631 |

At +0.60% entry / −0.20% exit, every arm is near zero. Lesson: execution decides it.

**Surface** (`surface.py`, `allsurface.py`). The EDGE candidate edge is broad: no feature bucket
dominates. Overnight return rises with the day's return for **all** stocks (up 8–12%: about +1%;
up 12%+ and closing near the high: +1.7% to +1.9%).

**Round 2, a learned trader** (`ev.py`, `results/round2-*.json`). A numpy ridge model of the next
overnight return, refit every 21 sessions on past data only, trading the best positive
expected-net bets. Kite 2026: +35.6k vs +20.4k for two shipped slots. Yahoo: +149.5k vs +141.1k.
The catch: its picks had a median day traded value of ₹36 lakh (shipped ₹2.24 crore) and closed
7.7% under the high. Its strongest weights were "thin is better" and "fell during the day is
better", which is bid–ask bounce (close on the bid, auction near the mid). A flat cost cannot price that.

**Round 3, the same model inside shipped-like liquidity** (`results/round3-*.json`). Yahoo, +0.36%:
+117.4k (≥ ₹50 lakh) and +100.1k (≥ ₹1 crore), vs +141.1k shipped. **Rejected.** The shipped
EDGE ranking is as good once liquidity is held equal. A liquidity floor on the shipped book
also hurts (+109.8k), as the Oct 7 study found.

**Round 4, genome search** (`genome.py`, `results/genome-*.json`). 60 genomes over slots, sizing,
night screen, close location, kinds, depth, near-high, volume and price cap. Picked on 2023-07..2024
and scored on 2025-26, then the reverse. Out of sample: +50.7k vs +51.3k (two shipped slots), and
+73.5k vs +89.8k. Training rank anti-predicts test rank (Spearman −0.20 to −0.71). **Fails**, as the
F&O searches did. Lesson: do not tune filters on a broad edge.

## The exam (2019–2022, opened once)

Frozen finalists: TWO (two equal slots), TWO_NIGHT (two slots + night screen), ONE (one slot), against
BASE (the shipped book). Rule: closes ≥ 100, net and net-ex-best > 0, beats BASE, drawdown ≤
max(1.5×BASE, 15%), ≥ 3 positive years, and above the 90th percentile of 200 random-order books
from the same candidates (`exam-results.json`).

**Verdict: all three FAIL**, under both the +0.36% and post-close models:
- **Check 5 failed for all.** Random picks among the shipped top-10 did as well as the shipped
  ranking. The edge is in the EDGE candidate pool and in execution, not in the ordering.
- **My mistake:** I made compounding the primary metric. A ₹25k penny book compounding to
  ₹11–44 lakh is unrealistic, and it widens the null band. Under compounding, TWO and ONE did not beat BASE.

Seen afterwards (`after-exam.json`, diagnosis only, not a pass): at fixed size, TWO_NIGHT sits at the
92nd percentile of the random books and TWO at the 49th–55th. All books were positive in all four
years. Under the +0.60%/−0.20% stress, TWO_NIGHT made +56.0k vs +31.8k for BASE.

## Execution facts (minute data, small samples)

- Official close vs the 15:20 price: mean −0.32%, median −0.04% (n = 1,153). Buying at the close is
  no dearer than at 15:20, before the spread is even counted.
- After the auction, candidates fade: 09:17 median −0.49%, 09:20 −0.81% (n = 70 exits).
- "Placeholder" opens (open = previous close, 13% of mornings): a 09:17 sale got +0.26% on average
  (n = 489). The current exit model is mildly conservative there, not flattering.
- Volume outside 09:15–15:29 is a median 0.6% of daily volume (pre-open plus post-close, n = 396).
  Post-close liquidity exists but may be thin: **unknown at our ticket size**.
- Adverse-fill stress for post-close: if only 75% of winning nights fill and every losing night does,
  v2 still makes +144.9k on the exam years (today's book: +100.2k). At 50% it falls to +75.1k.

## Built in Dev (paper only, no orders)

- `edge_overnight_paper.ON_V2` shadow, declared 2026-11-04 before scoring. Same 15:20 picks and quotes
  as the book, own ₹25k. Two equal halves; `night_means` screen (shrunk 60-night mean ≥ 0.1%, parity-checked).
  Its P&L uses the entry day's **official close** (`entry_basis="official_close"`), proven from the exit
  quote's `ohlc.close` only when the entry day is the session before. Otherwise it keeps its 15:20 fill
  (`fill_fallback`). Exit at the auction open, as the book.
- `run_postclose_probe` at 15:32 (CLOSE) and 16:03 (POST): read-only quotes of the day's ranked picks.
  POST volume − CLOSE volume = post-close session quantity. `GET /experiments/edge-overnight` now shows
  `postclose_probe` (pairs, traded share, median ₹ value, share covering a half-book ticket) and, per
  shadow, `since`, `book_same_nights` and `entry_basis_counts`.
- Rollback: `EDGE_OVERNIGHT_POSTCLOSE_PROBE_ENABLED=false` stops the probe;
  `EDGE_OVERNIGHT_SHADOWS_ENABLED=false` stops all shadows. The book is unchanged.

## How to judge it forward

After 20+ ON_V2 closes, read `GET /experiments/edge-overnight`:
1. ON_V2 net vs `book_same_nights` net (the book at its real 15:20 fills);
2. `postclose_probe.covers_ticket_share`: how often the post-close session traded at least a half-book
   ticket. If it is low, the post-close gain is not available at this size;
3. `entry_basis_counts`: fallbacks should be rare.

A real-money check of post-close fills (one small CNC market order at 15:50 on a pick) is the only way
to prove fills. That is the owner's call and is not built.

## Smart V1/V2 and EDGE daytime

Penny stocks fall from open to close by about 0.5% a day on average (Kite −0.50%, Yahoo 2023–26 −0.53%),
and EDGE-type movers by −1.0% to −1.2% the day after. An intraday long book needs to beat that drift before
fees. Tuning Smart's entries (the earlier search's best: −₹52 vs −₹85) only trades less. My
recommendation is to **stop investing in intraday-long penny strategies**, and to aim Penny capital and
effort at the overnight book's execution. This is a recommendation; Smart and EDGE were not changed.

## Reproduce

`build.py kite|yahoo` → `_local/days-*.pkl`; `allrows.py`; `round1.py`; `round2.py`; `round3.py`;
`genome.py E36|PC`; `exam.py run` (freeze verified by hash); `after_exam.py`; `headline.py`;
`night_parity.py`; `parity.py 2025-07-15 2025-10-31`. Engine Python: `python-engine/winvenv`.
