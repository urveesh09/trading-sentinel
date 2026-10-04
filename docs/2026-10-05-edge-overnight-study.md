# EDGE overnight: where the EDGE return really is (Dev, research)

Owner direction (October 4, 2026): improve EDGE if possible, test it properly,
and make the system smarter.

## Problem

The shipped EDGE loses heavily in the causal own-cash replay: −40% on Jan–Jun
2026 and −27% on Jul–Sep 2026 (`edge-trader-t1`). The thesis exits of
`EDGE_TRADER_V1` did not help.

## Finding (development: seen Jan–Sep 2026 only)

An event study of every shipped EDGE candidate (3,160 events) split each return
by time of day:

| Segment | Close → next open | Next open → next close | Close → close |
| --- | --- | --- | --- |
| All candidates | **+0.90%** | −0.38% | +0.49% |
| Strength ≥ 0.8 | **+1.98%** | −0.34% | +1.59% |

- The overnight move (close → next open) was positive in each of the nine months
  for strength ≥ 0.6.
- The shipped clock buys at the next open, so it misses the move and then holds
  the intraday fade. That alone explains most of the loss.
- The EDGE universe's unconditional overnight return was +0.56% (median +0.22%)
  over the same days. The selected candidates roughly double it.

Fidelity checks on 1-minute data (Sep 7–Oct 1, seen):

- **Entry price.** The 15:20 price averaged 0.07% under the daily close, with a
  mean absolute gap of 0.44%. The candidate charges 25 bps entry slippage.
- **Real fills.** Buying at the actual 15:20 minute price and selling at the
  actual 09:15 opening print gave +1.86% mean, +1.39% median and 77% winners on
  148 candidate events. The daily-bar estimate for the same events was +1.80%.
- **Liquidity.** Median traded value is ₹7.7 lakh in the 15:10–15:25 window and
  ₹2.7 lakh in the first two minutes after the open. The bottom 10% is very thin,
  hence the capacity cap.

## Candidate `EDGE_OVERNIGHT` (`edge_portfolio_replay.run_overnight_book`)

- **Signals:** the shipped `scan_today` ranking and sizing, unchanged.
- **Entry:** buy at the signal session's close (15:20 CNC proxy, +25 bps).
- **Exit:** sell at the next session's open (pre-open auction, −5 bps). A missing
  or zero-volume session delays the sale to that ticker's next open.
- **No stop:** nothing can execute overnight.
- **Capacity:** never more than 1% of the signal day's traded value. Fills under
  25% of plan are skipped.
- **Book:** own cash only, at most 3 entries per day.
- **Costs:** `penny_cnc_full_costs` for every arm, the baseline included (retired
  after scoring; see the correction below). This is
  the runtime schedule plus the buy-side delivery STT (0.1%) and the ₹15.93
  depository charge per sell, both of which the runtime model omits. Runtime
  delivery brokerage is kept although Zerodha charges none, so the model errs
  towards over-charging.

## Pre-registered study `edge-overnight-t1`

| Item | Value |
| --- | --- |
| Code | `2298e77` |
| Freeze | `1e5c904`, committed and pushed before scoring |
| Development window | Jan–Sep 2026 (seen) |
| Untouched window | Mar 2024–Dec 2025 daily, never examined by any EDGE study, scored once |
| Decision | `EDGE_OVERNIGHT` on the ₹25,000 book |
| Attribution arm | `EDGE_OVERNIGHT_S60` (minimum strength 0.6) |

| Untouched (Mar 2024–Dec 2025) | Trades | Net | Net excl. best | Max DD (vs start) | Max DD (from peak) | Win rate |
| --- | --- | --- | --- | --- | --- | --- |
| BASELINE ₹25k | 522 | −₹22,008 | −₹22,563 | 89.0% | 88.1% | 49.4% |
| **EDGE_OVERNIGHT ₹25k** | 829 | **+₹2,22,864** | +₹2,08,084 | 153.3% | **19.1%** | 55.1% |
| EDGE_OVERNIGHT_S60 ₹25k | 632 | +₹2,52,507 | +₹2,35,376 | 27.1% | 5.8% | 58.1% |
| BASELINE ₹1L | 521 | −₹84,534 | | 85.7% | 84.9% | 50.3% |
| EDGE_OVERNIGHT ₹1L | 757 | +₹5,95,871 | +₹5,49,774 | 108.4% | 17.3% | 55.5% |
| EDGE_OVERNIGHT_S60 ₹1L | 581 | +₹6,63,396 | | 22.6% | 4.9% | 56.8% |
| Any arm ₹3,000 | | ≈ −₹3,000 (ruined) | | | | |

**Frozen verdict: `NOT_SUPPORTED_STAYS_OFF`.** Three checks pass: net > 0, net
without the best winner > 0, and beating the baseline. The drawdown check fails:
153.3% > 1.5 × 89.0%.

The check measures drawdown in rupees against the *starting* bankroll. Sizing
compounds with equity, so after the book grew about ten times, a 19% fall from
the peak counts as 153% of the start. The rule was frozen and is honoured. Changing
it now would be re-tuning after seeing the result.

The attribution arm `EDGE_OVERNIGHT_S60` passes all four checks (27.1% ≤
133.4%), but it was not the declared decision candidate.

Distribution checks on the ₹25k decision arm:

- mean +1.02% per overnight, median +0.64%;
- the 11 trades beyond ±10% contribute ₹11,399 of ₹2,22,864;
- the worst trade (ALLCARGO −68.8%, Nov 2025) looks like an unadjusted demerger
  price, which counts against the candidate.

## What this does and does not show

- The overnight effect survived an untouched 22-month test, minute-level fill
  checks and conservative costs.
- The size of the returns (about +200% a year) is not a forecast. The replay
  assumes:
  - fills at the official close and the opening auction for every order;
  - a retrospective 2026 universe (survivorship);
  - no circuit lock, freeze or surveillance (ASM/GSM) restrictions;
  - Yahoo prices that are not adjusted for corporate actions.
- **Capital floor.** The DP charge is a flat fee per sell, so at ₹3,000 the costs
  ruin every arm. Below about ₹25,000 this idea does not work.
- **Runtime cost model.** `calc_penny_costs` under-charges delivery trades: buy
  STT and the DP charge are missing, while delivery brokerage is wrongly
  included. EDGE paper P&L was therefore optimistic. Fixed on October 5 (see
  below).

## Forward paper book (built after the owner's go-ahead, October 5)

The owner chose a broker-free forward paper book of ₹25,000.

- **Code:** `edge_overnight_paper.py`. Scheduler jobs `edge_overnight_entry`
  (Mon–Fri 15:20 IST) and `edge_overnight_exit` (Mon–Fri 09:17 IST).
- **Settings:** `EDGE_OVERNIGHT_PAPER_ENABLED=True`, `EDGE_OVERNIGHT_PAPER_BANKROLL=25000`.

How a day runs:

- **15:20 entry.** One quote batch builds today's provisional bar (session
  open/high/low, LTP as close, volume so far) for cached tickers whose latest
  close is ₹4–60.
  - The shipped `scan_today` ranks them on a temporary copy of the last 60 bars
    plus that bar.
  - Up to three picks are bought on paper at LTP +25 bps, capped at 1% of today's
    traded value and by own cash.
- **09:17 exit.** Each earlier position is sold at the quote's `ohlc.open` (the
  opening-auction print) −5 bps. Costs come from the corrected delivery schedule.
  A ticker with no trade today stays open and is retried (`OPEN_DELAYED`).
- **Store and restart safety.** Positions live in the separate store
  `<DB_PATH>.edge-overnight-paper.db`. Each phase runs once per day, so a restart
  is safe.
- **Reporting.** Telegram receives a summary at entry and at exit, with the book's
  running P&L and equity.
- **Safety.** No executor import, no `place_order` and no write to the
  operational ledger (enforced by a test).

## Delivery-cost correction (runtime, October 5)

`penny_risk.calc_penny_costs` with `is_intraday=False` now applies Zerodha
delivery charges:

- no brokerage;
- 0.1% STT on both buy and sell;
- 0.015% buy stamp duty (`PENNY_CNC_STAMP_DUTY_PCT`);
- a ₹15.93 DP charge per sell (`PENNY_CNC_DP_CHARGE`);
- exchange, SEBI and GST as before.

This applies to every Penny delivery path: EDGE paper and live, the CNC Connors
leg, and research replays. EDGE and CNC paper P&L were overstated before.

Intraday (MIS) costs are unchanged.

The research-only `CNC_FULL` model used to score `edge-overnight-t1` is retired.
It was the old runtime schedule plus buy STT and the DP charge, and it kept the
non-existent delivery brokerage, so it charged at least as much as the corrected
schedule. The frozen results remain conservative.

## Rollout

EDGE runtime still buys at 09:30 and stays paper-only; the overnight paper book
runs next to it.

- Rollback: `EDGE_OVERNIGHT_PAPER_ENABLED=false`. Open paper positions stay in
  the store and are sold by the exit job only while the setting is on.
- The frozen verdict still stands: this is forward evidence, not a promotion.
