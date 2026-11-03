# Round 8 — four mechanisms no study here has tested, frozen before scoring (November 3, 2026)

Owner (November 3, after seven rounds and the other agent's capital-reuse / protected-selling / hybrid
round, `b5e83e4`): take time, run several genuinely new experiments, and report whether anything gives
an explosive result. Starting checkout `b5e83e4`. Both NIFTY years (2024/2025) are seen; every afternoon
result is in-sample. Nothing here changes the runtime. NIFTY 2023 stays protected; no download.

## What has been tested before (so this round does not repeat it)

Entry signals, windows, option-led and auction-drift timing, 16-feature forecasts, OI walls, volatility
filters; exits (runners, locks, clocks, rolls); instruments (near-the-money, debit verticals, butterflies,
iron butterflies, protected directional selling, hybrids); sizing (earned tickets, extra lots, capital
reuse, the risk dial). **Never tested:** whether puts and calls behave differently; whether the week's or
the day's direction matters; choosing the strike by its delta; and what the live engine's 15:28 exit does
now that 15:15-15:29 is the closing auction.

## X1 — put/call asymmetry (the volatility smile moves with the market)

Mechanism: when the index falls, implied volatility usually rises, so a put gains from both the move and
the volatility; when it rises, volatility usually falls, and a call's gain is damped. The repo's F&O study
found its main strategy's calls lost and puts earned in all three years (`docs/FNO_WEAK_SPOTS_2026-10-31.md`).

- **X1a, the mechanism (diagnostic with fixed signs):** (i) each afternoon minute 13:00-15:00, the change
  in at-the-money implied volatility against the index's change: the slope is **negative in both years**;
  (ii) every non-overlapping ten-minute window 13:00-15:00 whose index move is at least 0.15%: the return
  of the nearest out-of-the-money option priced 5-20 in the move's direction (bought at the window's
  start ask, valued at its end bid): **puts on falls beat calls on rises in both years**. Both use realized
  windows: they describe the mechanism, not a trade.
- **X1b, the trade:** E03.1's own tickets split by side; `PUT2`, E03.1 with put tickets at twice the
  reserve (Rs 2,500, up to 6 lots; calls unchanged, day reserve up to Rs 5,000, E03.1's brakes); `PE_ONLY`
  reported. **PUT2 passes** if it beats E03.1 in each year at ordinary and adverse fills **and** its ordinary
  net per rupee of worst day and per rupee of drawdown are at least E03.1's (more risk must pay for itself).

## X2 — does the bigger picture's direction matter?

- `WEEK`: the sign of the index's last five completed sessions (previous close against the close five
  sessions before; daily closes from the history database). `DAY`: the sign of the index at the decision
  against the day's 09:15 open.
- Arms: `ALIGN_WEEK`, `ALIGN_DAY` (take only signals in that direction); `ALIGN_WEEK2`, `ALIGN_DAY2`
  (aligned tickets at twice the reserve, others unchanged).
- A filter passes if it beats E03.1 in each year at ordinary and adverse fills; a 2x arm passes by PUT2's rule.

## X3 — the strike by delta, not by price

E03.1's Rs 5-20 band picks different leverage in different years and hours. Arms `DELTA15`, `DELTA25`,
`DELTA35`: the out-of-the-money strike (within four steps, price at least Rs 2, affordable inside Rs 1,250,
up to 3 lots) whose Black-Scholes delta at the at-the-money implied volatility (read at the decision) is
nearest the target; everything else E03.1. **Passes** if at least two of the three beat E03.1 in each year
at ordinary and adverse fills.

## X4 — the live engine's exit inside the closing auction

The live E02/E03/E03.1 paper code sells at 15:28 (`expiry_e02.py`); since August 3 that is inside the
auction. On the nine Production recordings (Oct 6 - Nov 3), every leg with a mid of at least Rs 1 at the
15:14:50 snapshot: sell one lot on the bids at that snapshot, against selling on the bids of the first
snapshot from 15:28:00. **Holding to 15:28 loses** if the average difference is negative in total and on
at least 7 of the 9 days. If so, an exit before the auction is recommended for any E-variant going live.

## Rules for every arm

E03.1's lab and fills (`2026-11-03-expiry-e031/lab.py`, reproduced day by day first), continuous
2024-2025 cash and each year independently, ordinary / adverse / severe fills; severe reported, not a test.
Every arm and every failure is written to the results file. Passing is a learning and a forward-paper
candidate, never a qualification for real money.
