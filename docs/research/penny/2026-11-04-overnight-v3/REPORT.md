# Penny overnight v3 — report (November 4, 2026)

## Result in plain words

1. **The other agent's improvement does not survive real costs.** Its cost-aware route bought half
   a ticket at 15:20, priced at +0.36% over the close. Production's own paper record (Oct 22 –
   Nov 3, 21 closes) shows 15:20 fills averaging **about 1.35% above the official close**. At that
   cost the route falls back to plain v2 (2015–18 at 50% winner fills: 19.4k vs v2 20.1k).
2. **Both ends must trade at the auction price.** Selling at the 09:17 bid (about −1.1% vs the auction
   in Production's record) instead of in the 09:00–09:05 pre-open auction turns v2 negative in
   2015–18 (−25.0k) and 2019–22 (−6.5k). Buy in the post-close session, sell in the pre-open auction.
3. **New and consistent: fill v2's empty slots.** v2 has zero or one position on 21–33% of nights.
   A plain overnight rule (up ≥ 5%, closing in the upper half of the range, ≥ 2× normal volume,
   positive overnight history) nets +0.8% to +1.2% a trade, about as much as EDGE's own picks.
   v2 + those fillers + 20-day-high picks first (**V2_HI_F3N**) made **10–18% more than v2 in all
   five periods** at full fills, including the 2011–2014 years nobody had scored.
4. **But it failed its sealed check.** When half of the winning post-close orders are assumed
   not to fill, the fillers' lower win/loss ratio cost money on 2011–14 (16.4k vs v2 21.2k), and its
   drawdown was 1.59× v2's (limit 1.5×). By the rule frozen before the opening: **FAIL**.
5. So it runs as a **paper shadow, ON_V3, next to ON_V2**. The forward record and the post-close
   probe decide between them. No orders, no real money.

## Fixed Rs 25,000, post-close entry, auction exit −5 bp

| Period | v2, all fill | V2_HI_F3N, all fill | v2, 75% winners fill | V2_HI_F3N, 75% | v2, 50% | V2_HI_F3N, 50% |
|---|---:|---:|---:|---:|---:|---:|
| 2011–14 (sealed, opened once) | 108,445 | **128,281** | 65,497 | **74,764** | **21,192** | 16,380 |
| 2015–18 | 127,734 | **145,610** | 68,868 | **78,906** | 10,721 | **13,316** |
| 2019–22 | 184,222 | **214,596** | 112,130 | **132,846** | 38,229 | **49,638** |
| 2023–Oct 2026 | 227,943 | **251,360** | 152,470 | **167,085** | 73,831 | **80,944** |
| Kite Jul 2025–Sep 2026 | 51,836 | **59,833** | 31,978 | **37,509** | 11,014 | **13,833** |

The 75% and 50% columns are the mean of ten random draws. A drawn share of *winning* tickets
does not fill; every losing ticket fills. Every year of every period was positive for both books at
full fills. Other models (`results/round4.json`, `exam-results.json`): a capacity limit of 0.1% of
the day's volume, a −20 bp exit, and capacity + 50% denial favour V2_HI_F3N in every period (the
last by only Rs 144 on 2011–14). Correlated denial (all of a night's winners at once) favours it in
four of five; on 2011–14 it loses there (17.6k vs 22.3k).

## What was tried, in order

| Round | Idea | Result |
|---|---|---|
| 1 | Re-price v2 and the cost route with the forward costs | Cost route = v2 at real costs; missing the auction exit loses |
| diag | Per-candidate outcomes by feature, four periods | EDGE's ranking adds nothing; night history and 20-day highs help; thin names pay more but fill less |
| 2 | Rank by night history; take every candidate; 20-day high first; capacity sizing | None consistent: night ranking leans to thin names that the capacity model cuts |
| 3 | v2 order with 20-day high first; higher night screen; capacity-aware ranking | V2_HI consistent but only +1–2%; the fill model moves results several-fold, ranking a few % |
| 4 | Fill empty slots with plain overnight names | V2_HI_F3N +10–16% in all four seen periods; finalists frozen |
| exam | Sealed 2011–14 (built only after the freeze, opened once) | +18% at full fills, but FAIL on the 50%-denial robustness and drawdown checks |

Also measured: the Closing Auction Session (since Aug 3, 2026) covers F&O stocks only, so penny
stocks still close on the last-30-minute average and the 15:50–16:00 post-close session is the only
way to buy at that price. Pre-open market orders are accepted only until 09:05 (from Sep 7, 2026).

## Honest limits

- Daily bars only. No historical data shows whether a post-close buy fills; the denial and capacity
  models are assumptions. Production's forward record is 21 closes, a small sample.
- The Kite period ends with positions still open at the data boundary (1 for v2, 3 for V2_HI_F3N),
  so its totals are partial.
- All four development periods were already seen. Only the 2011–14 check was fresh, and it is a
  surviving-universe backward check (246 names), not a forward test.
- Order inside the pool: the frozen V2_HI_F3N order beat 96% of random-order books on 2011–14 but
  lost to random order on the Kite self-test. Treat ordering as unproven; the gain is the fillers.
- In the runtime, ON_V3's fillers are judged on 15:20 quotes (LTP and volume so far), not the final
  bar: the volume test reads lower at 15:20, so slightly fewer fillers qualify than in the replays.

## Built in Dev (paper only)

- `edge_overnight_paper.ON_V3`: ON_V2's rules (two halves, night screen ≥ 0.1%, P&L from the official
  close, auction exit) plus ranked picks within 1% of their 20-session high first, plus F3 fillers
  (best night mean first, one per company, at most 10 re-quoted once before the decision clock) for
  slots the EDGE picks leave empty. Fillers go through the same realism refusals and sizing as every
  pick. The extra cache read and quote move the 15:20 decision about a second later (1.2 s for 3,800
  names on the Kite cache copy; the live universe is about 1,100).
- `overnight_features` (one cache read, causal), `filler_rule`, `filler_picks`; the ENTRY receipt
  gains `v3_inputs`. ON_V2's night screen moved into a shared helper, same output.
- Filler parity with the research table (`scripts/filler_parity.py`, `results/filler-parity.json`):
  0 rule mismatches in 5,912 stock-days. Night means are identical except a few thinly traded
  trade-to-trade names (BE/BZ) where the research table skipped off-calendar sessions.
  The runtime keeps ON_V2's rule.
- Switch `EDGE_OVERNIGHT_V3_SHADOW_ENABLED` (default true; rollback false). The book, ON_V2, the Oct 21
  shadows, the post-close probe and the enrichment evidence path are unchanged.

## How to judge it forward

After 20+ ON_V3 closes, `GET /experiments/edge-overnight`: ON_V3 vs ON_V2 net on the same nights,
`postclose_probe.covers_ticket_share` (does the post-close session trade a half-ticket?), and
`entry_basis_counts`. If post-close capacity proves good, ON_V3 is the better design; if fills look
poor, ON_V2 is. A real post-close order test remains the only proof of fills and is the owner's call.

## Reproduce

`scripts/parity.py`, `scripts/i1.py`, `scripts/diag.py`, `scripts/diag2.py`, `scripts/slots.py`,
`scripts/fill_rules.py`, `scripts/rounds.py 2|3|4`, `scripts/check4.py`, `scripts/exam.py freeze|run`
(run refuses a second opening), `scripts/filler_parity.py`. Engine Python: `python-engine/winvenv`.
