# Primary-source review — November1,2026

- [Fidelity ADX/DMI](https://www.fidelity.com/viewpoints/active-investor/average-directional-index-adx):
  conventional25/20 trend/range readings and directional confirmation. These
  are heuristics, not a guaranteed day classifier or NIFTY-option profit proof.
- [Wood, Roberts, Zohren2021/2022](https://arxiv.org/abs/2105.13727): online
  changepoint features combined with slow momentum/fast reversal. Supports
  testing adaptation; their deep model is not reproduced or claimed here.
- [Shu, Yu, Mulvey2024](https://arxiv.org/abs/2402.05272): persistence/jump
  penalty and chronological cross-validation for regime switching, accounting
  for delays/costs. We test simple persistence, not their fitted jump model.
- [Adams/MacKay2007](https://arxiv.org/abs/0710.3742): online filtering of
  changepoints differs from retrospective segmentation. A full-sample smoothed
  label would not be a valid historical intraday decision.
- [Maitrier etal. order-flow research](https://arxiv.org/abs/2307.02375):
  real-time regimes of signed order flow. Our unsigned candle volume is not
  that evidence; no order-flow/news classifier is invented.

Prior local O30m day-router and O31h/O31i failures are retained controls and
methodological warnings. Neither foreign-market papers nor flexible routing
guarantee profit, avoid every losing day, or prove the experts have conditional
edge. The actual NIFTY option/cash replay decides this experiment's result.
