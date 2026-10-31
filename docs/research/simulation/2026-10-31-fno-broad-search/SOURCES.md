# O31i primary-source research map

Read2026-10-31. Indicator definitions motivate hypotheses, not profit claims.
US equity/FX/futures studies do not establish NIFTY-option profitability.

- [Fidelity indicator guide](https://www.fidelity.com/learning-center/trading-investing/technical-analysis/technical-indicator-guide/overview)
  and [CCI](https://www.fidelity.com/learning-center/trading-investing/technical-analysis/technical-indicator-guide/cci):
  trend/oscillator/volatility families. Our exact parameters and entry rules are
  research hypotheses. No vendor return is accepted as evidence.
- [Moskowitz, Ooi & Pedersen, Time Series Momentum](https://fairmodel.econ.yale.edu/ec439/mosk.pdf):
  cross-asset longer-horizon momentum evidence; adapting it to intraday options
  is speculative. Adaptive/crossover/channel entries are tested, not assumed.
- [Heston, Korajczyk & Sadka, Intraday Patterns](https://doi.org/10.1111/j.1540-6261.2010.01573.x):
  recurring intraday return continuation and temporary reversals in US stocks.
  Same-clock NIFTY momentum is a different hypothesis with limited history.
- [Osler, NYFed125](https://www.newyorkfed.org/research/staff_reports/sr125.html):
  order clustering/levels in FX motivates testing failed-auction/reclaim logic.
- [Xiao etal., jumps and news](https://onlinelibrary.wiley.com/doi/full/10.1111/jfir.12223):
  continuation/reversal differs with information type. Deferred news router
  requires point-in-time news arrivals; no labels are invented from OHLC.
- [CME futures volume](https://www.cmegroup.com/education/courses/introduction-to-futures/what-is-volume):
  unsigned volume cannot distinguish opening/closing or buying/selling intent.
  OBV here is a signed-close proxy, not measured order flow.
- [OCC/OIC bull call debit spread](https://www.optionseducation.org/strategies/all-strategies/bull-call-spread-debit-call-spread),
  [vertical spreads](https://www.optionseducation.org/theoptionseducationcenter/learning-resources-by-topic/simple-spreads-and-verticals),
  [Cboe strategies](https://cdn.cboe.com/resources/options/Trading_Strategies.pdf):
  changing payoff trades premium cost against capped gains/defined structure
  risk. These are mechanics, not historical performance or Indian broker margin.
- [CMU genetic-programming validation research](https://publications.ri.cmu.edu/the-importance-of-simplicity-and-validation-in-genetic-programming-for-data-mining-in-financial-data)
  and [LBNL backtest-overfitting tutorial](https://datagrid.lbl.gov/backtest/Tutorial.pdf):
  a broad search needs a complete trial ledger, held-out/chronological checks
  and selection-bias accounting. We retain all48 genomes and max-t sensitivity;
  this cannot undo the many previous looks at these three years.

Not faithfully testable here: stock-relative-value/pairs (missing historical
constituent panel), news/order-flow/market making (missing arrival history,
signed trades and depth), calendars/diagonals (nearest-expiry-only scope),
cross-asset/SENSEX three-year strategies (missing comparable data), overnight
execution (no matching carry/admission adapter). Long straddles and fully
collateralized iron structures need a joint-leg lifecycle; vertical pairs in
this study are explicitly a matched-expression diagnostic only. Naked short
options/borrowed margin are outside the owner's constraints and are not tested.
