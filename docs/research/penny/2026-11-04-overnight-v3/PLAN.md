# Penny overnight v3 — plan (November 4, 2026, written before any v3 arm is scored)

## Problem

The owner asked for a better result than Overnight v2 and the enrichment study (`982d587`).
What the evidence now says:

1. **Forward Production paper record** (read-only export in the enrichment study, Oct 22 – Nov 3,
   21 book closes): the overnight edge is there (official close to the modelled auction exit made
   +Rs 1,165), but 15:20 fills averaged about **1.35% above the official close** (Rs 2,044 on about
   Rs 1.52 lakh of tickets) and the 09:17 bid sat about **1.1% below** the modelled auction exit.
   Displayed 15:20 spreads averaged 1.3–1.4%.
2. **Iteration 1 (done, `_local/i1.json`)**: the enrichment's cost-aware route priced its regular
   sleeve at +36 bp. At the forward-measured 100–135 bp, its gain at poor fills disappears (older
   years, 50% winner fills: 19.4k vs v2 20.1k). Selling at the 09:17 bid instead of the auction
   (−110 bp) makes v2 lose (2015–18 −25.0k, 2019–22 −6.5k) or nearly vanish (2023–26 +16.4k).
   **Both ends must trade at the auction price: post-close entry and pre-open exit.**
3. **Diagnostics (done, `_local/diag.py`, `_local/diag2.py`)** on every eligible v2 pool member,
   in all four seen panels: the ranking EDGE uses adds nothing (top-2 vs rest equal), but the
   shrunk 60-night overnight mean is monotone within every liquidity bucket, and closing at a
   20-day high is consistently better. Pool members are usually thin on average days but in play
   on the signal day (median day value Rs 1.3–2.8 crore), so post-close capacity is plausible for
   most, not proven for any.
4. Closing Auction Session (from Aug 3, 2026) covers F&O stocks only (Zerodha bulletin 439989).
   Penny stocks still close on the last-30-minute VWAP, and the 15:50–16:00 post-close session is
   the only way to buy at that price. Pre-open market orders only until 09:05 (from Sep 7, 2026).

## Method

- Simulator `v3sim.py` (post-close entry, auction exit, enrichment accounting: fixed Rs 25,000,
  profits withheld, losses reduce own capital). Parity with the enrichment V2_NATIVE: 127,734.36
  vs 127,734.58 (2015–18, full fills) and 227,942.76 vs 227,941.77 (2023–26), within Rs 3 at
  50% winner fills (float rounding of the average entry price).
- **Development panels (all already seen):** Yahoo 2015–18 (enrichment older), 2019–22 (v2 exam),
  2023–Oct 2026, Kite Jul 2025 – Sep 2026. An arm must win **in each of the four panels**, not only
  in total, to go forward.
- **Seven frozen fill models** (assumptions, not evidence):
  M1 full; M2 adversarial 75% (a quarter of winning tickets denied); M3 adversarial 50%;
  M4 correlated 50% (one draw per night denies every winning ticket of that night);
  M5 capacity κ = 0.10% of the day's share volume (about a third of an assumed 0.3% post-close
  share); M6 = M5 + M3; M7 full fills with the exit at open −20 bp. Seed 20261104.
  **Robust net = the minimum over M1–M7.**
- At most three development rounds, at most four new arms each, every arm reported.

## Sealed final check (frozen now, before any 2010–2014 day is built)

- Data: the enrichment study's public acquisition `_local/older/yahoo.sqlite`
  (sha256 `de4b69312a0f663614b73af6ff10987d554c2908ce6d2a68933ff78346f98de8`), receipts
  `older-acquisition.json` (`e36be2a7…2032d1f`), split cuts `yahoo-split-cuts.json` (`003482e8…fd0e`),
  prepared with the enrichment's `prepare` rules (no repair). Rows 2010–2013 were acquired but no
  day table was ever built from them; 2014 was built only as warm-up and never scored.
- Window: **2011-01-01 to 2014-12-31**, warm-up from 2010-01-01, tail to 2015-01-10.
- At most two finalists, frozen with source hashes in `exam-freeze.json` before the build.
- **Pass (each finalist vs V2 on the exam):** (1) ≥ 100 closes at M1 and no unresolved exposure;
  (2) net > 0 under every model M1–M7; (3) robust net ≥ 1.10 × V2's robust net; (4) M1 net
  ≥ 0.95 × V2's M1 net; (5) M1 drawdown ≤ 1.5 × V2's; (6) positive in ≥ 3 of the 4 years at M1.
  Separately reported, not a pass condition: the ranking claim, i.e. the finalist above the 90th
  percentile of 200 random-order books drawn from its own pool at M1.
- Opened once. No change to an arm after the opening. Limits: current surviving membership,
  later-known split cuts, daily bars only (no fill can be proven), current fees for all years.

## Runtime (only if a finalist passes)

A new paper shadow beside ON_V2 with the same 15:20 inputs and its own Rs 25k; ON_V2, the book,
the Oct 21 shadows, the probe and the enrichment evidence path are unchanged. Rollback by flag.
No real orders. Docs ritual and full suite as AGENTS.md requires; Dev only; push and deploy are
the owner's.

## Round 2 arms (declared before scoring)

All: two equal halves, night screen ≥ 0.1%, realism refusals as v2, post-close entry, auction exit.
- **NIGHT10**: v2's top-10 pool, ranked by the shrunk 60-night mean instead of EDGE strength.
- **NIGHTALL**: every EDGE candidate of the day (no top-10 cut), screened, ranked by night mean.
- **NIGHTALL_HI**: as NIGHTALL, but names closing within 1% of their 20-day high first.
- **NIGHTALL_CAP**: as NIGHTALL, plus a decision-time capacity rule: reserve at most 0.10% of the
  day's share volume; a name that cannot take a quarter ticket is skipped and the slot kept.

## Round 2 result and the change to the random fill models (recorded before round 3 and before any exam build)

No round 2 arm won in all four panels. Night ranking helps 2015–22 and loses 2023–26 and Kite
under the capacity models: the 60-night mean leans to thin names, which the capacity models
partly fill. NIGHTALL_HI came closest (robust 11.2k vs 3.3k, 32.1k vs 20.3k, 47.1k vs 56.3k,
1.5k vs 4.6k). A single seed swung M4 by tens of thousands, so **M2, M3, M4 and M6 are now the mean
of ten seeds (20261104 … 20261113)** in development and in the sealed check. All else unchanged.

## Round 3 arms (declared before scoring)

- **V2_HI**: v2's top-10 pool in shipped strength order, names within 1% of their 20-day high first.
- **V2_Q4**: v2 with the night screen raised to 0.4% (fewer, stronger nights).
- **ALL_HI**: every candidate, shipped strength order, 20-day-high names first.
- **CAPRANK**: every candidate, ranked by night mean × the share of a half ticket that 0.1% of the
  day's share volume covers (a capacity-aware expected-rupee order).

## Round 3 result

**V2_HI** is the first arm better than v2 in all four panels on both full-fill and robust net,
by small margins (M1 +1 to +2%; robust 5.9k vs 3.3k, 20.4k vs 20.3k, 57.4k vs 56.3k, 5.7k vs 4.6k).
V2_Q4 trades ideal profit for robustness (M1 −5 to −15%, robust better in three of four).
ALL_HI and CAPRANK are not consistent. Lesson: ranking inside the pool moves results by a few
percent while the fill model moves them several-fold.

Utilisation check (`_local/slots.py`): v2 has zero or one position on 20–33% of nights and uses
73–84% of its capital. A plain overnight rule on all band stocks (`_local/fill_rules.py`;
F3 = up ≥ 5%, close in the upper half of the range, ≥ 2× the 20-day median volume, night mean ≥ 0.1%)
nets +1.22% / +0.87% / +0.79% per candidate (2019–22, 2023–26, Kite) and exists on ~95% of nights.

## Round 4 arms (declared before scoring; round 1 was re-pricing only, so this is the third arm round)

Fillers are band names (Rs 5–55) not already in the EDGE pool, with causal features rebuilt from
the day tables (`v3sim.filler_table`), the same realism refusal, and no stop/strength.
- **V2_HI_F3N**: V2_HI, then F3 fillers by night mean for any empty slot.
- **V2_HI_F3L**: V2_HI, then F3 fillers by today's traded value (liquidity first).
- **F3_ONLY_HI**: no EDGE pool; F3 names only, 20-day-high names first, then night mean.
- **V2_HI_F5L**: V2_HI, then F5 fillers (night mean ≥ 0.5% and up ≥ 2%) by traded value.

## Round 4 result and finalist freeze (before any 2010–2014 day table exists)

V2_HI_F3N beat v2 in all four panels at full fills (145.6k vs 127.7k, 214.6k vs 184.2k,
251.4k vs 227.9k, 59.8k vs 51.8k) and on robust net (5.7k vs 3.3k, 25.7k vs 20.3k, 60.1k vs
56.3k, 7.6k vs 4.6k); fillers add 170–200 trades per four-year panel at Rs 76–152 net each,
and every year is positive. V2_HI_F3L (fillers by traded value) also passes the four-panel rule
but by less. F3_ONLY_HI (no EDGE pool) is far better in 2015–22 but loses robust net in 2023–26.
V2_HI_F5L fails. Development stops here (three arm rounds, as planned).

Finalists frozen in `exam-freeze.json` by `scripts/exam.py freeze`: **V2_HI_F3N** (primary) and
**V2_HI_F3L**, against V2. The self-test on the Kite panel already shows random order inside the
same pool doing as well (65.6–67.7k vs 59.8k): the ranking claim is expected to fail; the
improvement, if any, is the fillers.

## Sealed check opened once (2011–2014): both finalists FAIL

246 tickers, 981 sessions (`exam-results.json`, `results/exam-run.log`). V2: M1 108.4k, robust 12.3k,
M1 drawdown 2,909. V2_HI_F3N: M1 **128.3k (+18%)**, every year better, M2 74.8k vs 65.5k, M5 72.4k vs
60.0k, M7 105.1k vs 90.2k, but M3 16.4k vs 21.2k and M4 17.6k vs 22.3k; robust 12.4k (needs ≥ 13.5k)
and M1 drawdown 4,624 (> 1.5 × 2,909). Checks 3 and 5 fail; 1, 2, 4 and 6 pass. V2_HI_F3L the same.
Ranking claim (reported only): V2_HI_F3N at the 96th percentile of 200 random-order books.

Reading: across all five periods the fillers add 10–18% whenever at least 75% of winning post-close
orders fill (M1, M2, M5, M7 better everywhere); their lower profit factor (2.46 vs 2.64 here) costs
money when half the winners are denied, which happened on the unseen years. Not qualified.

Decision recorded after the opening (owner precedent O31b/c: a candidate that fails narrowly goes on
paper, never real money): add V2_HI_F3N as a paper shadow **ON_V3** beside ON_V2, same 15:20 inputs,
own Rs 25k, no orders, so the forward record and the post-close probe decide between them. No
change to either finalist or to any rule.
