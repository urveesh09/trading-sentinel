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
