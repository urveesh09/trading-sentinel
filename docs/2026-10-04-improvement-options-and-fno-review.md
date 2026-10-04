# Improvement options after T1/T2, and an F&O review (October 4, 2026)

Status: **analysis and recommendations only.** No runtime, settings or F&O code
was changed for this document; Production was only read (it is currently not
running, so the latest F&O evidence is the October 2 read-only assessment).
Evidence: [T1 receipt](2026-10-04-t1-penny-edge-trader-slice.md),
[T2 receipt](2026-10-04-t2-range-swing-momentum-slice.md),
[F&O profitability assessment](2026-10-02-fno-profitability-assessment.md),
method in [RESEARCH_TESTING_METHOD.md](RESEARCH_TESTING_METHOD.md).

## Part A — where the non-F&O modules stand

| Module | Shipped baseline on untouched data (own cash) | Best candidate | What the evidence says is wrong |
| --- | --- | --- | --- |
| Penny MIS | **+₹63.17**, 24 trades, 13 sessions | none beat it | Works on this sample; too few sessions to trust. |
| EDGE | −40.17% marked (Jan–Jun, ₹1 lakh) | none | Targets ≈ +2.8% vs stops ≈ −5.2% at ~50% hits; MR is most of the loss; half of signals can't be bought at 09:30 (2% drift). |
| Range | −₹9,024 (−9%) | Reclaim entry −₹6,275 | Stop only 0.8% below entry → noise stops (120 stops vs 50 targets); delivery costs ≈ ⅓ of the loss. |
| Swing | −28.6% of ₹4,500 | **SWING_TRADER_V1 −5.7%** | Halving winners at T1 and holding broken trends; ₹4,500 cannot fund most signals (wide 7.5% stops on expensive stocks). |
| Momentum | −₹120.87 (54 trades) | none | Entry rarely follows through (5/54 targets). |
| Penny CNC | **0 signals in 9 months** | — | "RSI(2) < 10" and "RSI rising two bars" almost never coexist. |

Every daily module also lost in Jan–Jun 2026, which suggests a weak or choppy
market for long-only daily trading, so part of the problem is *when* they trade.

### Suggested next rounds (normal)

Each needs a new freeze and a still-untouched window (2024–2025 daily data
exists for all daily modules; forward data for intraday ones).

1. **Swing round 2:** keep SWING_TRADER_V1's exits (the −80% loss reduction is
   the strongest signal found), add a market-weather switch (no new longs when
   NIFTY < its 50-day average or breadth is weak), and size to what the pool can
   afford (an affordable-universe filter instead of 197 dust skips).
2. **EDGE round 2 (geometry, not timing):** ATR-based stops with targets ≥ 1.5×
   the stop, test MO-only versus MR-only, and replace the 2% gap reject with a
   limit order at the signal close for the first hour.
3. **Range round 2:** stop at range-low minus 0.5×ATR (not 0.1%), keep the
   reclaim entry, and require reward-after-costs ≥ 2× costs, or move Range to an
   intraday MIS version (cheaper costs, matching its live 30-minute/4-hour design).
4. **Momentum:** stop tuning exits; the entry needs a new hypothesis (for
   example only the first breakout after a tight morning range, or only stocks
   with relative strength above NIFTY on the day).
5. **Penny CNC:** either retire the leg (it cannot fire) or replace the rising-
   RSI clause with an armed reclaim, tested properly. The quick audit gave no
   clear edge either way, so retiring is the honest default.
6. **Penny MIS:** keep it; archive minute data weekly so a larger forward sample
   can confirm or refute the +₹63.

### Creative / drastic options (owner asked; still tested the same way)

- **Capital follows evidence (meta-allocator).** Run all modules in shadow and
  give real capital only to modules whose *rolling forward shadow* result
  passes the decision rule; cut a module to zero automatically after a drawdown
  limit. This turns "which module is good?" into a measured, automatic answer.
- **One market-regime switch for every long-only module.** Today each module
  has its own partial regime logic. A single portfolio-level "risk-on/off" state
  (trend, breadth, India VIX) that blocks new long entries in risk-off would
  have avoided much of the Jan–Jun losses — to be tested on 2024–2025.
- **Learned ranking from our own ledgers.** The replays now record every
  candidate signal, its features and its outcome. Train a small, calibrated
  model (logistic regression or gradient boosting) on 2024–2025 to rank or
  veto signals, then judge it on 2026. Only feasible now that outcomes are
  causal and cost-inclusive; keep it out of the order path until it qualifies.
- **Retire or merge weak modules.** Penny CNC (dead), Momentum (no follow-
  through) and EDGE (structurally negative) could be paused in favour of
  concentrating capital on the two modules with the best evidence (Penny MIS,
  F&O trend) plus Swing round 2.
- **Intraday conversion to cut costs.** Short-hold daily ideas (EDGE 1–3 days,
  Range) pay delivery STT on both legs; intraday versions pay far less. Where the
  idea is really an intraday move, run it as MIS.
- Not recommended: leverage, margin, averaging down or martingale sizing —
  all ruled out by the owner and none would fix a negative expectancy.

## Part B — how the F&O module works today

**Book:** paper (`FNO_PAPER`, ₹2,50,000), NIFTY only. The live leg is disarmed
three ways and also needs `fno_go_live_check()` to pass (≥40 trading days, ≥60
trades, profit factor ≥1.2, clean liveness).

**Every 90 seconds** (`run_fno_tick`, 09:15–15:30):

1. **Manage open positions first** (so a stop and a new signal can't double up).
   The single-leg exit ladder (`fno_exit_rules.py`), checked on NIFTY futures:
   - 15:10 hard flat (unconditional);
   - underlying stop;
   - after the target (1.8R) is reached, a trail of 1×ATR from the best price;
   - premium backstop at −25% of premium;
   - 45-minute time stop if the move has not made 0.5R — deferred while the
     option itself is in profit.
2. **Entry signal** (`fno_engine_mom.py`), computed on **NIFTY futures 5-minute
   bars, never on option prices** (premium is distorted by time decay and IV):
   - opening range = 09:15–09:45 high/low;
   - LONG (buy CE) when a closed bar *freshly* breaks above OR-high +
     0.25×ATR, EMA21 > EMA50 and time-of-day relative volume ≥ 1.2, outside
     the crisis regime; SHORT (buy PE) is the mirror;
   - stop = the tighter of the opposite OR edge or 1.5×ATR; target = 1.8R.
3. **Gates with witnesses** (`fno_gates.py`): a fixed order of checks (entry
   window 09:45–14:45, no expiry-day entries, kill switches, liquidity — OI
   ≥5,000, volume ≥1,000, spread ≤1.5%, fresh quotes/chain, IV sanity, minimum
   viable pool, reward/risk ≥1.3). Every gate ships a test input that passes it,
   so a gate can never silently block everything (the Penny lesson).
4. **Contract choice** (`fno_chain.py`): one batched quote for ATM±5 strikes
   plus the future; IV and delta use the futures price as the forward; choose
   the ~0.55-delta (ATM or one ITM) option, never OTM.
5. **Risk** (`fno_risk.py`, `fno_shared_risk.py`): no order path exists for a
   position with unbounded loss; 2% of pool risked per trade, ≤₹6,250 stop
   risk, ≤2 lots, ≤2 concurrent, ≤3 trades/day, ≤15% of pool in premium;
   kill switches at −6% day, −12% week, −20% month or 6 straight losses. Both
   books share one fail-closed reservation ledger.
6. **Execution** (`fno_executor.py`): LIMIT only — buy at the ask with a 30-second
   timeout (never chase), sell at the bid then bid−3 ticks after 15 s, and a
   marketable limit at the 15:10 hard flat. Paper fills at the real ask/bid, so
   paper pays the spread honestly. Options cannot carry an exchange stop-loss
   order, so stops are enforced by this 90-second loop.
7. **Defined-risk book** (`fno_defined_risk.py`, `fno_dr_book.py`), riding the
   same tick: with a directional signal and enough expected move it opens a
   **debit spread** (buy ATM, sell 2 strikes out); with no signal, rich IV and a
   contained expected move, an **iron condor**; otherwise it stands aside. One
   structure at a time, 1 lot, exits at fractions of max profit/loss or square-off.

## Part C — is ₹10,000 in two weeks good enough?

Evidence (Production paper DB, Sep 17–Oct 1): single-leg **+₹10,755.67 from 9
closes**, defined-risk **+₹3,187.60 from 7 closes**, on **7 session dates**.

- The shape is what a trend-follower should look like: three trail-stop exits
  made **+₹13,767** (+₹4,711, +₹1,622, +₹7,435); five 45-minute time stops lost
  only −₹954 net; one stop lost −₹2,056. Small losers and a few big winners are
  the right *shape*.
- But it is not yet evidence of an edge: remove the two biggest winners and the
  single-leg book is about −₹1,389. The same book lost −₹26,777 in July–August
  (older policy versions, partly unreconciled). Nine trades from seven days
  cannot separate skill from two lucky trend days. It is paper, not live fills.
- On a ₹2.5 lakh paper pool, ₹10.8k is ~4.3% in two weeks — excellent *if* it
  repeats, which is exactly what is unknown.

**Verdict:** encouraging, not proven. There is real potential in the design
(honest fills, good risk architecture, a trend-capture exit ladder that lets
winners run), but the next step is evidence, then careful scaling — not more
size now.

## Part D — what is needed to get more out of F&O

### Requirements (in priority order)

1. **A real replay of today's policy.** The archive already stores NIFTY futures
   bars and chain snapshots since ~September 10. Build an F&O replay on the same
   pre-registered method: decisions from archived futures bars, fills from
   archived bid/ask, the shipped gates/exit ladder/spread pricing, a shared cash
   book. Without this, every change is a guess.
2. **Keep the chain archive complete and permanent.** OI snapshots are purged
   after 7 days (disk at 86%). Move chain/futures snapshots to cheap compressed
   storage (Parquet) before purge, so the history grows daily. Optionally buy
   licensed historical option quotes to test July–September and 2025.
3. **More independent trading days.** The go-live bar (40 days, 60 trades,
   PF ≥ 1.2) is sensible; at ~1 trade/day that is ~3 months of paper. Do not
   shortcut it.
4. **A small, separately authorised live pilot** (1 lot, defined-risk only)
   after the bar is met, so real broker fills replace paper assumptions.

### How to make it faster

- **Exits on live ticks, not 90-second polling.** Subscribe the held option and
  NIFTY future on Kite's WebSocket and evaluate the stop/trail on every tick (or
  every 1–2 s). With no exchange stop order available for options, a 90-second
  gap can let a stop slip by tens of NIFTY points on a fast day. This is the
  single biggest risk-reduction lever.
- **Fire entries at the 5-minute bar close.** Schedule the entry evaluation a
  second after each bar closes instead of on a free-running 90-second clock;
  today a signal can wait up to 90 s after its bar closes before the order goes.
- **Pre-compute the chain.** Keep ATM±5 quotes warm between bars so the strike
  pick and gates run instantly when the bar closes.
- **Measure it.** Record bar-close → decision → order → fill latency (p50/p95)
  in paper before and after, as the plan already requires.

### How to raise profit while lowering risk

1. **Pyramid only with house money.** When the target arms the trail, the trade's
   initial risk is effectively gone; add one lot with a stop that keeps the
   combined position's worst case at or below the original risk. That increases
   trend-day profit (where all the money is made) without raising worst-case risk.
2. **Take part, trail the rest.** Sell half at the 1.8R target and trail the rest:
   less give-back on reversal days, while still catching the big runs.
3. **Choose the vehicle by IV.** Buy the naked option when IV is low (cheap
   convexity); use the debit spread when IV is high (sell expensive premium
   against it). Today the two books run side by side on the same signal, which
   doubles exposure to one idea instead of picking the better structure.
4. **Trade only trend-prone days.** The ORB edge lives on trend days. Test a day-
   type filter: opening range narrow versus ATR, gap behaviour, India VIX band,
   prior-day narrow range (NR7). Skipping chop days cuts the losing streaks that
   hurt July–August.
5. **Add BANKNIFTY (and later SENSEX) as separate opportunities.** The signal
   code already runs for them in the partner-tips scan. More underlyings means
   more trend days to catch, but they are correlated, so keep one shared risk
   budget across them.
6. **Keep the hard rules.** Defined loss on every order, kill switches, no
   expiry-day entries, the 15:10 flat, LIMIT-only orders and the go-live bar
   are what make the upside safe to pursue. None should be loosened to trade more.

### How to make earnings more consistent

- Pair the **trend book** (wins on trend days) with the **range book** (iron
  condors on rich-IV quiet days); their good days are different days, so the
  combined equity curve is smoother. Measure them as one portfolio.
- Size by volatility: risk a fixed rupee amount per trade measured in ATR, so
  quiet and wild days carry similar risk.
- Judge by monthly profit factor and drawdown, not by single great weeks.

### Suggested F&O order of work

1. Chain/futures archive retention (prerequisite for everything).
2. F&O replay of the current policy on the archive (pre-registered method).
3. Tick-driven exit monitor (paper first, latency measured).
4. Candidates, each frozen and scored on untouched archive days: partial-plus-
   trail, house-money pyramiding, IV-based vehicle choice, day-type filter.
5. Continue paper to the go-live bar; then a separately authorised 1-lot
   defined-risk live pilot via the normal GitHub promotion.

All F&O work must follow the existing noninterference rules: F&O decisions,
reservations and exit authority are protected, and nothing in this document has
changed them.
