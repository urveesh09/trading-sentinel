# Sources and boundaries

- N08/N09 reports, PLAN, source, freezes, and saved raw trade/evaluation receipts
  at this checkout are the primary evidence about Sentinel. Reproduced controls
  establish parity, not profitability.
- [NSE investor guidance](https://www.nseindia.com/static/invest/be-a-smart-investor)
  explains that an option holder may lose the entire amount paid. This motivates
  full-premium cash budgeting, not reliance on a requested stop price. Fees and
  operational/settlement constraints still matter.
- [NISM equity derivatives FAQ](https://www.nism.ac.in/wp-content/uploads/2021/02/Equity-Derivatives-FAQ-document-1.pdf)
  distinguishes the option buyer's premium exposure from the writer's exposure.
  N09.1 introduces no option selling, borrowing or margin assumption.
- [Moreira and Muir, Volatility Managed Portfolios](https://www.nber.org/papers/w22208)
  studies conditional exposure in different asset/factor settings. It does NOT
  validate N09's direction of volatility sizing for intraday bought options; that
  rule is inherited and tested directly here, not imported as a proven result.
- [Bailey et al., The Probability of Backtest Overfitting](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf)
  explains selection risk from repeated backtests. N09's corrected within-family
  PBO is not the posterior probability that N08 as a whole is overfit. All four
  years here were previously inspected; a frozen next experiment still does not
  make them unseen.

Web pages supplied mechanism/context only. No source promises N09.1 profitability
or a real-money capital guarantee. No additional market-data API calls were made.
