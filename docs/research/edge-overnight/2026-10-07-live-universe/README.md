# EDGE overnight on the live universe (October 7, 2026)

Development evidence. The rules were already known, and the window
(Jul 15, 2025 – Oct 6, 2026, about 310 sessions) overlaps windows seen by
earlier studies. Nothing here is a frozen, untouched score.

## Why

The live overnight paper book closed 6 trades for −₹916 in its first 3
sessions. The study behind it (`edge-overnight-t1`) tested about 95 Yahoo
tickers, but the live book ranks about 1,500 cached tickers in the price band.
Six of its first seven picks were never in the tested universe.

## Data and method (`backtest.py`)

- Data: a read-only copy of Production's Kite daily cache (5,701 tickers,
  Aug 2023 – Oct 2026). `NIFTYBEES` starts Jun 25, 2025, which sets the
  window start.
- Ranking: the shipped `penny_edge_live.scan_today`, ranked 10 deep. Each
  filter is applied, then the top N are kept. Sizing is risk-based per pick,
  so it does not depend on N.
- Book: the shipped `edge_portfolio_replay.run_overnight_book`:
  - buy at the close +25 bps, sell at the next open −5 bps;
  - capacity of 1% of traded value;
  - own cash of ₹25,000, compounding;
  - delivery costs from `penny_cnc_costs`.
- Check: the Oct 6 scan picked AAKASH and PRAENG, as the live book did.

## Results

| Arm | Trades | Net | Mean / median per trade | Max DD from peak |
| --- | --- | --- | --- | --- |
| LIVE_3 (raw fills, as the old model) | 579 | ₹7,34,824 | +1.68% / +0.73% | 133% of start |
| **REAL_3** (realistic fills) | 630 | ₹67,943 | +0.54% / +0.21% | 15.0% |
| REAL_2 | 531 | ₹56,553 | +0.58% / +0.26% | 12.7% |
| REAL_1 | 289 | ₹22,848 | +0.55% / +0.10% | 11.2% |
| REAL_LIQ25L_3 (20-day median traded value ≥ ₹25 lakh) | 434 | ₹22,808 | +0.32% / +0.12% | 12.7% |
| REAL_LIQ1CR_3 (≥ ₹1 crore) | 251 | ₹11,418 | +0.28% / +0.03% | 13.7% |
| REAL_TESTED95_3 | 609 | ₹37,698 | +0.37% / +0.15% | 14.4% |
| **REAL_NO_MR_MID_3 (shipped)** | 565 | **₹68,820** | **+0.62% / +0.27%** | **13.4%** |

Realistic fills mean the arm refuses three kinds of pick:
- a close at the day's high after a rise of 2% or more (usually locked at the
  upper band, with no sellers);
- a second series of a company already held (`CALSOFT` and `CALSOFT-BE`);
- SME series (`-SM` and `-ST`).

## Findings

1. **The old model's profit was mostly unbuyable.** On the live universe, 149
   trades that closed at the day's high after a rise made 75% of LIVE_3's
   net, with an 88% win rate. On the 95 tested tickers they made 54%. Those
   fills cannot happen at the close. The frozen `edge-overnight-t1` numbers
   (+₹2.2 lakh) are inflated the same way.
2. **A thin but steady edge remains.** For REAL_NO_MR_MID_3:
   - by quarter, per trade: 2025Q3 +0.06%, Q4 +0.56%; 2026Q1 +0.77%, Q2
     +0.92%, Q3 +0.69%;
   - with 0.25% extra entry slippage, the mean is still +0.37% (median
     +0.02%);
   - REAL_3 at 0.5% extra slippage falls to about zero.
3. **`MR_mid` is weak in every view.**
   - untouched Yahoo: −0.04%;
   - live universe with realistic fills: +0.16% (REAL_3) and +0.05%
     (REAL_2).
   - It is dropped. `MO_mid` is mixed and kept.
4. **A liquidity floor hurt.** The edge sits in the thinner names, which is
   where the 1% capacity cap and real fills matter most.
5. **Placeholder opens** (open equal to the previous close) were 8–10% of
   realistic trades and lost about −0.65% each. Live exits now record them.

## Shipped (`edge_overnight_paper.realism_refusal`)

- The book ranks 10 deep and fills up to `PENNY_EDGE_MAX_POSITIONS` slots.
  A refused pick is replaced by the next one.
- It refuses:
  - SME series;
  - a second series of a held or just-opened company;
  - the `MR_mid` kind;
  - an LTP within 0.5% of the quote's `upper_circuit_limit`;
  - sell depth with no quantity;
  - an LTP at the day's high after a rise of 1.9% or more (the proxy used
    when the band is unknown).

## What this does not show

- 15:20 is not the close, and the modeled entry is the close +25 bps.
  Live 15:20 entries were 0.4% worse on average over 8 trades.
- At the 2% proxy, the circuit rule is a heuristic: real band locks and
  near-band days with thin offers may differ.
- Thin names are where execution matters. If real entry slippage is 0.5%
  or more, this edge is gone.
- Judge the live book on 30+ forward trades, and compare its entry cost
  with the 25 bps assumption.
