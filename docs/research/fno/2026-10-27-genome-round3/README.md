# O27f: genome round 3. New entry families, option-contract genes, a walk-forward of the search itself, and a random-entry null

**Verdict: the search does not work on this data. The frozen walk-forward rule fails, so keep the shipped book.** The most consistent-looking new strategy, a trend-day VWAP pullback, now goes into a forward test (panel B, O27g). It gets no promotion on seen data.

- Freeze: `3b8f9ef`, committed before any scoring.
- Run: 2,217 full replays, 8 workers, 21:52–22:52 IST, Oct 27.
- Research only. Production was only read, and no paper, live or forward-panel A rule changed.

## What this round asked

The earlier rounds searched the same 29 sessions: O27 (360-arm grid), O27b (17-gene ORB evolution) and O27e (efficiency, compression and failed-auction families). Each found arms that made more money than the shipped book *on those sessions*. None measured the question that decides everything:

> When the search picks a strategy from the past, does that pick make money on the sessions that come after?

This round measured it in two ways:

1. **An anchored walk-forward of the whole search procedure.** The pool, a 6-generation evolution with cross-family crossover, and the plateau pick ran separately for each fold, each seeing only sessions before its test block:

   | Fold | Training sessions | Test sessions |
   | --- | --- | --- |
   | F1 | Sep 10 – Sep 30 | Oct 1 – Oct 9 |
   | F2 | Sep 10 – Oct 9 | Oct 12 – Oct 16 |
   | F3 | Sep 10 – Oct 16 | Oct 19 – Oct 26 |

   This gives 16 test sessions, each one unseen by the pick that traded it.
2. **A random-entry NULL family searched with the same budget, genes and exits.** Its entries come from a seeded coin flip. Anything the NULL track achieves is what search produces on pure noise.

## What was new in the genome

- **Entry families** (none were in O27, O27b or O27e):
  - TREND_PULLBACK: on a trend day, a pullback to VWAP or EMA20 and a resumption bar;
  - PDL_BREAK: a close through the prior day's high or low;
  - VWAP_BAND: a close through VWAP ± k session σ, with VWAP sloping the same way;
  - MOMO_BURST: an N-bar move of at least m ATR, all bars the same colour;
  - ENSEMBLE: votes over six sub-signals (OR20, the O27e efficiency break, PDL, VWB, TPB, MOMO).
- **New genes:**
  - SENSEX cross-index confirmation;
  - multi-day trend alignment;
  - AM or PM entry windows;
  - a VWAP-lost exit;
  - option strike depth (delta 0.55 or 0.65);
  - expiry week (nearest or next).
- **Crossover across families:** shared genes mix between families.
- **The book is unchanged.** Every genome went through the shipped single-leg book: planner, sizing, brakes, exit ladder at about 60 s, costs, ask entry and bid exit.
  - The lab's copy of the entry path has three marked changes.
  - A run-time gate proved the copy reproduces the shipped book exactly (13 trades, ₹10,801.09).
  - A test proved every family is free of look-ahead.

## Result 1: the walk-forward (frozen rule: fails)

| On the 16 test sessions | Trades | Net ₹ | Max DD ₹ | Folds > 0 |
| --- | ---: | ---: | ---: | ---: |
| **REAL search, picked per fold** | 6 | **+1,011** | 1,525 | 1 of 3 |
| NULL search (random entries) | 9 | +3,682 | 9,233 | 1 of 3 |
| Shipped book, same sessions | 4 | +9,528 | 1,461 | — |
| O27e efficiency break (picked on Sep 10 – Oct 9) | 19 | +20,831 | 6,749 | — |
| O27 OR20 no-EMA (picked after seeing all 29 sessions) | 10 | +29,287 | 3,423 | — |

| Fold | REAL pick (training) | Training | Test |
| --- | --- | --- | --- |
| F1 | TREND_PULLBACK, PM, RVOL ≥ 1.2, stop 1 ATR, 2.4R, VWAP-lost exit, delta 0.65 | 6 trades, +₹9,142, no drawdown | 1 trade, −₹1,525 |
| F2 | TREND_PULLBACK, PM, stop 2 ATR, LATE exit, VWAP-lost exit, delta 0.65 | 9 trades, +₹8,657 | 0 trades |
| F3 | TREND_PULLBACK from 10:30, 3R, LATE exit, delta 0.65 | 11 trades, +₹18,063 | 5 trades, +₹2,535 |

The frozen rule required the REAL result to be above zero, beat the shipped book, beat NULL, and have at least 2 of 3 folds above zero. It only managed the first.

The two reference rows are not fair competitors: each was picked with knowledge of some of these sessions. On Oct 12–26 alone, which the O27e selection never used, its efficiency break made +₹18,871 on 13 trades. That is the best genuinely held-out number any study has produced so far. Its drawdown on that period still broke the ₹5,000 cap.

## Result 2: past rank does not predict future rank on this data

| Measure (REAL pool, uniformly sampled genomes) | Value |
| --- | --- |
| Rank correlation of net, Sep 10 – Oct 9 against Oct 12 – Oct 26 | **−0.23** (125 genomes; same sign 47 times, below a coin's 50%) |
| Rank correlation, week to week (mean of 7 week pairs) | **+0.08** (range −0.49 to +0.38) |
| Top 10 genomes on Sep 10 – Oct 9, mean result on Oct 12 – 26 | REAL **−₹1,200** (3 of 10 positive); NULL −₹3,083 (1 of 10) |
| Rank correlation of training fitness against later net | −0.02 |
| Genomes with a positive full-window net | REAL 64% of 1,378; NULL (random entries) 66% of 839 |
| Best full-window net found | REAL +₹65,955 (VWAP band); NULL **+₹28,265** (13 trades, positive in both halves) |

The best genome of each family on Sep 10 – Oct 9 then lost or went flat on Oct 12–26:

| Family | Sep 10 – Oct 9 | Oct 12 – 26 |
| --- | ---: | ---: |
| TREND_PULLBACK | +₹19,991 | −₹4,947 |
| ENSEMBLE | +₹14,781 | −₹7,435 |
| MOMO_BURST | +₹11,945 | −₹709 |
| VWAP_BAND | +₹7,052 | 0 |
| NULL | +₹8,755 | −₹3,029 |

## Result 3: what the genes say (main effects over 600 uniformly sampled genomes, full window, seen data)

| Gene | Better allele | Mean net ₹ (better vs worse) | Note |
| --- | --- | --- | --- |
| Strike depth | delta 0.55 | +1,303 vs −251 (0.65) | Deeper ITM costs more premium. The shipped risk cap shrinks or refuses it: 5.4 vs 7.4 trades. |
| Expiry week | nearest | +585 vs +475 (next) | The next week's premium is often unaffordable under the cap: 4.0 vs 8.9 trades. |
| Entry window | AM (before 12:30) | +1,935 vs −644 (PM) | This flips with the regime: PM was better on Sep 10 – Oct 9 (−201 vs −1,443), AM on Oct 12 – 26 (+3,378 vs −443). |
| Target | 3.0R | +1,797 vs −232 (1.5R) | Letting winners run is the most stable gene across the rounds. |
| Exit | LOOSE (60 min, trail 1.5, no lock) | +1,254 vs +253 (live ladder) | The same lesson: the live profit lock and 45-min time stop cut winners. |
| VWAP-lost exit | on | +813 vs +243 | A small help. |
| RVOL | ≥ 0.8 | +1,615 vs −71 (off) | Noisy: 1.0 and 1.2 are no better than off. |
| Multi-day trend | with | +707 vs +333 | Mostly fewer trades: 4.7 vs 8.3. |
| SENSEX confirmation | off | +761 vs +303 (on) | Confirmation removed trades without improving them. |

Exit reasons over the whole pool: time stop 1,105, underlying stop 1,096, trail 512, hard flat at 15:10 372, VWAP lost 366, profit lock 338, premium backstop 61.

## The most consistent strategy found (forward-test candidate, not a promotion)

**TREND_PULLBACK** is the FINAL fold's frozen pick: the best plateau among the five best-fitness genomes over all 29 sessions.

- **Rules:**
  - From 11:30, the day must be a trend day: price at least 1.5 ATR from the day's open, with at least 75% of the day's 5-minute closes on the trend side of VWAP.
  - Wait for a pullback that comes within 0.5 ATR of VWAP. Enter on the first bar that closes back in the trend direction above the prior bar's high (below its low for a short).
  - Stop at 1.5 ATR, target 3R. Exit: 120-minute time stop, 2-ATR trail, no profit lock.
  - Shipped sizing, brakes and costs; ATM-or-ITM strike at delta 0.55; nearest expiry.

| Full window (seen) | Trades | Net ₹ | Net without best day ₹ | Max DD ₹ | Win rate | PF | Green / red days | Green / red weeks | Worst day ₹ | Stressed net ₹ |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Shipped book | 13 | 10,801 | 3,693 | 1,991 | 54% | 2.99 | 6 / 4 | 3 / 3 | −1,461 | 8,878 |
| **TREND_PULLBACK (O27f)** | 14 | **17,347** | **11,627** | 3,418 | **71%** | **4.09** | **8 / 1** | **6 / 0** | −2,195 | 15,287 |
| ENSEMBLE EFF+MOMO (O27f best fitness) | 16 | 24,531 | 14,997 | 2,994 | 56% | 5.07 | 7 / 4 | 5 / 2 | −2,994 | 22,152 |
| O27e efficiency break | 38 | 31,063 | 22,656 | 6,749 | 55% | 2.28 | 12 / 7 | 4 / 4 | −2,307 | 25,035 |
| O27 OR20 no-EMA (post hoc) | 19 | 30,567 | 21,117 | 3,423 | 63% | 3.90 | 10 / 5 | 5 / 2 | −3,423 | 27,605 |

- **Why it is the "most consistent" on seen data:**
  - 8 green days against 1 red, and no red week.
  - It was positive in both halves: +₹11,615 on Sep 10 – Oct 9 and +₹5,732 on Oct 12–26.
  - **All 23 one-step neighbours are profitable** (median +₹12,019, minimum +₹3,281). That is a broad plateau, unlike O27e's region, where one step flipped +₹12k to −₹8k.
  - **Reversing its direction loses ₹11,761**, so its direction call carries information, not just its exits.
  - 9 of 14 trades rode to the 15:10 hard flat: it makes money by holding trend days to the close.
- **Why that is still not proof:**
  - It traded on only 9 of 29 sessions.
  - Its walk-forward relatives (the F1–F3 picks are the same family) made +₹1,011 on 6 test trades.
  - A random-entry genome found by the same search also made money in both halves (+₹17,825 and +₹10,440).
  - 14 trades cannot separate skill from luck. At this frequency, about 50 trades (3–4 months) are needed before any verdict.

## Learning

1. **On this data, the past does not rank the future.** In this sample the market changed character between Sep 10 – Oct 9 and Oct 12–26 (PM breaks worked first, then AM). The best strategies of one period were, on average, worse than others in the next. Rank correlation was −0.23, and week to week it was about zero. Every "best on the past" pick made in O27, O27b, O27e and this round was mostly picking the past regime. **Retuning on the last few days is chasing noise.** Do not switch strategies on a few days' results.
2. **Random entries with good exits made money in this period.** Two-thirds of the random-entry genomes ended positive, and the best made +₹28,265. Sep–Oct had enough trending days that the exit design alone produces profit:
   - let winners run (3R targets, a looser trail, no early lock);
   - cut losers at the stop.

   So in-sample profit from any entry rule overstates its skill. The fair yardstick is a random-entry arm, which panel B now carries.
3. **The exit lesson is the one that keeps repeating.** It held across O27, O27b, O27e and this round: the live ladder's 45-minute time stop and early profit lock give up the trend days that pay for everything. A 3R target, a looser trail and holding a trend day to the close were the most consistently positive genes. That is the strongest candidate for a future *exit* change. It needs its own frozen forward test, and it cannot happen during a proving week.
4. **Deeper strikes and next-week options lose to the risk cap.** At delta 0.65 or the next expiry, the shipped per-trade risk cap shrinks or refuses the position, so they mostly cut the number of trades. Delta 0.55 at the nearest expiry stays best inside the current risk rules.
5. **More filters are not more consistency.** SENSEX confirmation, the multi-day trend filter and higher RVOL bars mostly removed trades. O27b found the same.
6. **Evolution barely improved on the first random draw.** In three of four folds, the best fitness after six generations equalled the best in the starting pool or rose only slightly. The landscape is noise-dominated: crossover cannot climb a hill that is not there.
7. **The fitness favoured strategies that trade rarely.** Picks with 6–11 training trades and almost no drawdown scored best, then traded 0–5 times per test block. A future search should require at least about 1 trade per 2 sessions, or score per trade, to avoid lucky sparse picks.

## What happens next

- **Forward panel B (O27g)** runs from Oct 28 to Nov 27, frozen before the first forward session:
  - SHIPPED (control);
  - O27F_TREND_PULLBACK;
  - O27F_ENSEMBLE_EFF_MOMO;
  - O27E_EFFICIENCY_BREAK (never forward-tested before);
  - NULL_CONTROL (the NULL track's frozen pick).

  It uses panel A's rule, and a candidate must also beat the random-entry control. See `docs/research/fno/2026-10-28-forward-panel-b/README.md`.
- No paper, live or proving-week change.
- Nothing here justifies more capital.

## Files and reproduction

- Files:
  - `lab.py` and `test_lab.py` (7 tests);
  - `freeze.json` (committed in `3b8f9ef` before the run);
  - `analyze.py` and `results.json`.
- Raw replays are in the ignored `_local/evals/` (one JSON per genome) and `_local/results-raw.json`.
- To reproduce: `python-engine\winvenv\Scripts\python.exe docs\research\fno\2026-10-27-genome-round3\lab.py run --jobs 8`, then `analyze.py`. The run refuses to start if any bound source, setting or dataset file changed. It also needs the read-only export at `docs/research/fno/2026-10-27-consistency-grid/_local/dataset` (see `docs/FNO_STRATEGY_TESTING_PLAYBOOK.md` §3).
- Disclosure: every session was already seen by earlier rounds.
  - A 12-genome timing smoke test ran before the freeze; it removed only the unaffordable delta 0.75 allele.
  - `analyze.py` was written during the run and adds the persistence measure. No frozen selection depends on it.
