# SN01: a small fixed wallet trading NIFTY options for a 10% day (plan, frozen before scoring)

**Status:** research only, in Dev. No runtime change, no Production write, no order, no real money.

## The owner's idea (Nov 12, 2026)

- The wallet is **₹15,000** and stays fixed. Profit is banked and never traded, and a losing day is refilled by the owner.
- **Day target:** 10% of the wallet (**₹1,500**), net of charges. When it is reached, sell everything and stop F&O for the day.
- **Day loss limit:** 20% of the current wallet (**₹3,000**).
- **Active trading:** quick entries and exits on all three kinds of day (trending up, sideways, trending down). The target can come from several small wins.
- **Wallet growth:** each time the profit adds up to 100% of the wallet, the wallet grows by 50%.
  - The day target grows by 50% once every **2** wallet steps, or once every **3** (test both).
  - The target never falls below 10% of the wallet before the step.
  - The loss limit is always 20% of the current wallet.
- **Owner's improvement idea:** once the day passes 10%, lock 10% with a stop instead of selling, and let the trade run.
- SN01 runs alongside the N11/N012 paper main book (₹2,50,000) and never replaces it.

## Readings I chose (stated so the owner can correct them)

1. **"100% in total in profit"** is read as the **net** banked since the last step (winning days minus refilled losing days), because a refill is the owner's own money. The gross reading (winning days only) is reported beside it.
2. **At a step,** the step's profit is used up, and anything above it carries to the next step.
3. **Target modes:**
   - `every2`: ₹1,500 × 1.5^(steps // 2), the owner's first choice;
   - `every3`: the same, every 3 steps;
   - for comparison, `prop` (10% of the current wallet) and `flat` (always ₹1,500).
4. **Instruments:**
   - Options are bought only: ₹15,000 cannot carry futures or option selling.
   - NIFTY nearest weekly, one position at a time, lots = what the wallet buys (gene `cash` × W), capped by gene `max_lots`.
   - A trade is taken only if its own stop fits the day's remaining loss room.
5. **No expiry-day trading.** The year data has no same-day options, and expiry days are already off limits for the real-money test.
6. **The lock idea** is the gene `lock`:
   - when a trade would bring the day to its target, the trade is not sold;
   - a floor sits at the price where the day is exactly at its target;
   - the floor trails the best price by `lock` × target (in rupees), never below the target;
   - when that trade ends, the day ends.

## Data

- The four sealed NIFTY year datasets: 2023, 2024, 2025 and Jan 1 – Oct 28, 2026, ICICI Breeze 1-minute candles.
  - 742 non-expiry sessions with options, about 190 a year.
  - `sn01_data.py` copies them read-only into `_local/cache-<year>.pkl`, bound to each dataset's manifest hash.
- **All four years are already seen** for F&O single-leg rules (method ledger, section 11). So this search is in-sample by construction. The only honest checks:
  - leave-one-year-out selection;
  - a random-entry NULL searched with the same budget;
  - cost stress;
  - forward sessions.
- **Forward check (unseen for strategy work):** non-expiry sessions Oct 29 – Nov 12, 2026, from Production's quote archive. These are real bid/ask, about once a minute, read-only from the forward panel's export `20261112T103005Z`.
  - The converter is written and checked first on the seen overlap (Sep 10 – Oct 28, quotes against candles).
  - Only then is the final pick scored once on Oct 29 – Nov 12.
  - About 9 sessions cannot prove anything. The check can only show that the result is not wildly different.

## Fill model and costs (`sn01_sim.py`)

- **Entry:** at the signal minute's close ask. The ask is the close plus half the archive's 75th-percentile spread.
- **Stop:** a stop-market on the minute's low bid, filled at the stop or at a gap-through open.
- **Target:** a sell limit on the minute's high bid.
- **Same-minute touch:** if a stop and a target are both touched in one minute, the stop is taken.
- **Time stop and 15:15 exit:** at the close bid.
- **Charges:** the shipped round-trip charges (`fno_costs`, today's NFO rates) on every trade.
- **Extra cost stress:** +₹0, +₹100 and +₹200 per lot per trade.
  - **The search and the verdict use +₹100.**
  - Candles flattered fills by ₹100–200 per trade per lot in earlier studies, and a quick-trade strategy pays it on every trade.

## What luck alone gives (so a hit rate is not mistaken for skill)

For a price with no drift and no costs, the chance of reaching +₹1,500 before −₹3,000 is 3,000 / 4,500 ≈ **67%**.
- So a high share of target days is expected from luck. Only the **rupee total after costs** shows skill.
- The random-entry NULL measures exactly this.

## Search (`sn01_search.py`), budget fixed now

- **Entry families** (from the earlier F&O studies):
  - ORB (opening-range break);
  - MOMO (a 1–10-minute burst against 1-minute ATR, with an optional VWAP side);
  - TPB (trend pullback);
  - VWAPX (VWAP side with EMA slope);
  - EMAX (EMA cross);
  - FADE (stretch from VWAP plus a reversal bar);
  - PDX (prior-day high or low break).
- **Genome:** one or two families, plus these day and exit genes:
  - bias: none, with or against the daily EMA, puts only, calls only;
  - strike: ITM1, ATM, OTM1 or OTM2;
  - lots cap and cash share;
  - stop of 5–30% of premium;
  - target of 4–100%;
  - time stop of 2–120 minutes;
  - trail;
  - trades a day: 1–20;
  - entry window;
  - lock.
- **NULL:** RANDOM entries (probability per minute 0.5–10%, random side) with the same day and exit genes.
- **Budget:**
  - a pool of 6,000 REAL and 3,000 NULL genomes;
  - then per fold (each held-out year, plus ALL for the final pick) and per kind, 10 generations × 150 children.
- **Fitness** (training years only): the worst training year's net per session at +₹100.
  - It is valid only with ≥ 0.75 trades a session in every training year, because the owner wants an active strategy.

## The rule (`sn01_analyze.py` `RULE`, applied once)

- **The search generalises** if all of these hold:
  - the 4 held-out-year picks are positive at +₹100 in at least 3 of 4 years;
  - their sum is positive;
  - their sum beats the NULL picks' held-out sum.
- **The final pick is robust** if both hold:
  - it is positive at +₹100 in every year;
  - its four-year net is positive at +₹200.
- **Verdict:**
  - both → **PROMISING (paper shadow only)**;
  - otherwise → **NOT PROVEN**.
- Either way, the final pick's wallet ledger (Jan 2023 → Oct 2026, every2 / every3 / prop / flat, net and gross, at +₹0 / 100 / 200) is reported. It is a description of seen data, never a promise.

## After the verdict

- A pass can only become a paper shadow in Dev, which is the owner's call. Real money needs the owner's own decision and its own runbook (`docs/runbooks/fno-live-test.md`).
- A failure is reported plainly, with what it would take instead.
