# O31h literature review, 31 October 2026

Primary sources; the entries below are hypotheses, not published NIFTY-option
backtests. No numerical return from another market is assumed transferable.

| Source | Useful finding / mechanism | What this study can test |
| --- | --- | --- |
| [Xiao, Yin & Zhao, JFR2020](https://onlinelibrary.wiley.com/doi/full/10.1111/jfir.12223) | US index-ETF jumps have different subsequent behaviour depending on news type; non-news and scheduled-news reversals differ from unscheduled-news continuation. | Shock size alone cannot identify a rebound. Test a price-based continuation confirmation; a true news-aware router needs an archived point-in-time news/calendar dataset that these candles do not provide. |
| [Osler, NYFed Staff Report125](https://www.newyorkfed.org/research/staff_reports/sr125.html) | FX stop-loss and take-profit orders cluster around levels, with different effects on continuation/reversal. | A held level followed by renewed movement is a plausible entry mechanism. Applying it to an intraday VWAP retest is our inference, not that paper's tested rule. |
| [CME: What is Volume?](https://www.cmegroup.com/education/courses/introduction-to-futures/what-is-volume) | Aggregate futures volume does not distinguish opening/closing or buying/selling motives. | Do not label a volume spike as buyer absorption or assume a bounce from volume alone. |
| [Heston, Korajczyk & Sadka, JF2010](https://doi.org/10.1111/j.1540-6261.2010.01573.x) | US stock return predictability separates recurring intraday continuation from short-lived reversal. | Supports treating continuation and reversal as distinct hypotheses; does not establish profitable long-option entry timing in India. |
| [Brogaard, Han & Kim, Intraday Price Pressures](https://papers.ssrn.com/sol3/Delivery.cfm/4731947.pdf?abstractid=4731947&mirid=1) | Their cross-sectional study finds stronger reversal in idiosyncratic residual returns than raw returns. | Deferred: a NIFTY index-only history has no point-in-time constituent panel/factor residuals. Do not manufacture residual signals from one index. |
| [Wood et al., Slow Momentum with Fast Reversion](https://arxiv.org/abs/2105.13727) | Online changepoint detection combined with a learned momentum model responds to changing regimes in their futures study. | Deferred: daily futures evidence is not our intraday option evidence. A learned router needs locked chronological training/validation, costs and additional fresh data; it cannot be honestly trained and claimed proven on these repeatedly mined years. |

Evidence strength differs: peer-reviewed studies / official exchange education
versus a working paper / preprint. None supplies the exact two entry rules.
Order-book imbalance and news labels are unavailable here. No candle volume is
presented as a substitute for true signed order flow or historical depth.

Follow-up mechanisms fixed before replay:

- **DMI_VWAP_RETEST:** after the original DMI break, wait for a later VWAP touch
  that holds, then another completed-bar continuation confirmation. Structural
  stop and bounded wait, rather than buying the first break.
- **SHOCK_FLAG:** after the same large shock, require at least two subsequent
  inside bars that hold its directional half, then a breakout of their range
  in the shock's direction. This tests continuation rather than automatically
  fading the shock. Both calls and puts are allowed.
