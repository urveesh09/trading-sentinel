# F&O evolution round — 2026-10-27 (O27b)

The owner asked to breed the good strategies like genes: keep what worked on the winning days, drop the worst, mix and merge, add new parameters from the web plus a variation of our own, and test again.

This file and `freeze.json` were committed **before any genome was scored**. The results go below the line.

## What evolves

A genome has 17 genes. Each arm is still the whole NIFTY single-leg book in `fno_policy_replay` (entry plan, sizing, brakes, exit ladder at fast-exit cadence, bid/ask, real charges).

| Gene | Alleles (neighbour order) | Source |
| --- | --- | --- |
| Opening range length | 15, 20, 30, 45 min | O27 grid; 5–25 min tested in [the stocks-in-play ORB study](https://www.quantconnect.com/research/18444/opening-range-breakout-for-stocks-in-play/) |
| Freshness | crossing, first confirmation | O27 grid (continuation dropped) |
| Trend check | EMA 21/50 (shipped), **EMA 9/21 (our variation: turns faster)**, off | O27 grid: the slow check helped in Sep, blocked late-Oct trends |
| Break buffer | 0.10 / 0.25 / 0.40 ATR, Crabel "stretch" (mean open-to-nearer-extreme of the prior 10 sessions) | [NexusFi ORB notes](https://nexusfi.com/a/strategies/opening-range-breakout) |
| Relative volume minimum | 0.8, 1.0, 1.2, 1.5 | stocks-in-play study (RVOL > 1) |
| VWAP side | off, on | ORB indicator practice; every A entry was already on the VWAP side, so it is expected to be neutral |
| Opening-range bias | with, off, against | Window A: breaks *against* the opening range's own drift did better |
| Gap direction | off, with the gap (≥ 0.1%) | gap studies cited on NexusFi; window A: with-gap entries were better |
| Range width vs prior 10 sessions | off, ≤ 1.25×, ≤ 1.0×, ≤ 0.8× | Crabel-style compression |
| Previous-session narrow range | off, NR4, NR7 | [Crabel NR4/NR7](https://in.tradingview.com/script/sA6AFgk7-NR4-NR7-with-Breakouts-LuxAlgo) |
| Latest entry | 12:00, 13:30, 14:45 | time cutoff |
| Stop distance | 1.0, 1.5, 2.0 ATR | ATR stop (stocks-in-play study) |
| Target (arms the trail) | 1.2R, 1.8R, 2.5R | |
| Profit lock | TIGHT, LIVE, LATE, OFF | O27 grid |
| Time stop | 45, 60, 75, 90 min, off | O27 grid (30 min, the worst, dropped) |
| Time stop needs | 0.25R, 0.5R | |
| Trail | 0.6, 1.0, 1.5, 2.0 ATR | O27 grid |

**"What the winning days had in common"** was a descriptive look at window A only: 43 distinct entries from the O27 grid. It found:
- A few afternoon trend-day breakdowns in the direction of the morning gap made most of the money. Oct 1 at 12:21 was +₹7,108; Sep 28 and Sep 30 were also afternoons.
- Breaks against the opening range's own drift totalled +₹5,412; breaks with it, −₹7,692.
- With-gap entries were better than against-gap ones.
- A narrower range than usual was mildly better.
- A narrow previous session (NR4) was worse.

That look is why the bias gene has three alleles. It used no data from window B.

## How it evolves (frozen in `freeze.json`)

**Seeds.** The O27 grid's 32 eligible arms become genomes, with the new genes set to the shipped values. Arms with a 30-minute time stop or the continuation entry are dropped. Random genomes fill the population to 40.

**Breeding.** Each generation keeps 4 elites and adds 4 random immigrants. The rest are children: tournament-of-3 parents, uniform gene-by-gene crossover, then a 12% mutation rate per gene (70% of the time one step to a neighbouring allele, otherwise any allele). A child that was already evaluated is mutated again. The round runs 10 generations with fixed seed 20261027.

**Fitness** is measured on window A only (Sep 10 – Oct 9):
- (net − best day) ÷ max(max drawdown, ₹1,000), minus 0.5 for each half of A that lost money. The halves are Sep 10–24 and Sep 25 – Oct 9.
- A genome with fewer than 8 trades scores −5 + trades ÷ 8.

The fitness subtracts the best *day*, not just the best trade, so a strategy made by one lucky day scores low. The half penalty rewards earning in both halves.

**Finalists and plateau.** The 5 best genomes become finalists. Each is ranked by the median fitness of itself and all its one-step neighbours, so a lucky spike surrounded by losing settings scores low.

**Check on window B** (Oct 12 – 26, never seen by evolution). Each finalist, the shipped book and the O27 pick are replayed once over the whole window. A finalist passes only with:
- **at least 3 trades** in B (this closes the O27 rule's zero-trade gap);
- net ≥ 0;
- max drawdown ≤ max(1.5 × the shipped book's B drawdown, ₹5,000).

"B without Oct 21, 23 and 26" is also shown, for information only. Those are the days that prompted the no-EMA idea.

**Recommendation.** The first finalist, by plateau, that passes. Otherwise keep the shipped book.

**What a pass allows.** A forward-only replay from Oct 28 beside the shipped book. It does not allow:
- a paper or live change in the proving week;
- any change to the Nov 2 real-money test, which mirrors the paper book.

Promotion is the owner's call on forward evidence.

**Parity.** The shipped genome is replayed on A next to `CURRENT`, and the result must be identical.

## Honest limits

- All 29 sessions have been seen; B was seen in the O27 results.
- A genetic search on 19 sessions overfits by construction. The plateau, the best-day fitness and the B check are guards, not proof.
- The archive holds ATM±5 strikes only, so a deep in-the-money hold on a trend day can be unpriceable (Oct 21).
- Entries still start at 09:45 (the shipped entry window), so a 15- or 20-minute range cannot trade a 09:30–09:40 break.

## Run

```
python scripts/run_fno_evolution.py freeze --out docs/research/fno/2026-10-27-evolution
python scripts/run_fno_evolution.py run --out docs/research/fno/2026-10-27-evolution --jobs 10
```

The data is the O27 export (`docs/research/fno/2026-10-27-consistency-grid/_local/dataset`, bound by hash). Production stays up: the limit is the 6 CPU cores, and Production idles at under 1% CPU and 0.8 GB after hours.

---

## Results

Pending: filled in after `run`.
