# Primary-source research and transfer limits

Read 2026-11-18 through web tools. These sources motivate questions, not a claim
that any proposed policy is profitable in India. No strategy results borrowed.

1. Garleanu and Pedersen, *Dynamic Trading with Predictable Returns and
   Transaction Costs*, Journal of Finance 2013.
   https://w4.stern.nyu.edu/facdir/lpederse/papers/DynamicTrading.pdf
   Publisher-form paper read. Signal decay and trading costs affect desired
   positions/turnover. Supports EN112/114 action-horizon reasoning. Their linear
   commodity-futures setting does not establish an expiry-option edge or justify
   fractional lots, hidden leverage or copying its optimal portfolio formula.

2. Adams and MacKay, *Bayesian Online Changepoint Detection* (2007).
   https://arxiv.org/abs/0710.3742
   Primary author abstract read. Online posterior over time since a change uses
   sequential evidence, motivating causal inference rather than retrospective
   trend labels. EN116 proposes a different simpler HMM, not this algorithm.
   Detecting a state change is not predicting its direction or earning after fees.

3. Gibbs and Candes, *Conformal Inference for Online Prediction with Arbitrary
   Distribution Shifts*, JMLR 25(162), 2024.
   https://www.jmlr.org/papers/v25/22-1218.html
   Abstract read. Overweighting stale data can hurt changing forecasts; local
   adaptation matters. Motivates calibration/drift monitoring. Does not grant
   conditional coverage after choosing profitable-looking actions, nor make the
   bootstrap risk buffer in EN118 a certified confidence bound.

4. Lehalle and Mounjid, *Limit Order Strategic Placement with Adverse Selection
   Risk and the Role of Latency* (2018 revision).
   https://arxiv.org/abs/1610.00261
   Primary abstract read. Filled buy limits can select falling prices; latency
   erodes imbalance-based execution value. Supports EN119's conditional markout,
   cancel-race and missed-runaway controls. Not confirmation of paper queue fills.

5. Sachdeva, Su and Joachims, *Off-policy Bandits with Deficient Support*, KDD2020.
   https://arxiv.org/abs/2006.09438
   Primary abstract read. Unsupported historical actions undermine conventional
   IPS learning. EN118 must disclose simulator-dependent action labels; it cannot
   call nonexistent randomized trading propensities known or real causal effects.

6. Foster et al., *Offline Reinforcement Learning: Fundamental Barriers for
   Value Function Approximation*, COLT2022.
   https://proceedings.mlr.press/v178/foster22a.html
   Primary abstract read. Strong coverage/representation assumptions are needed
   for sample-efficient offline value learning. Supports small supported action
   sets before deep RL; does not imply every simulation model is invalid.

7. Cawley and Talbot, *On Over-fitting in Model Selection and Subsequent
   Selection Bias in Performance Evaluation*, JMLR2010.
   https://www.jmlr.org/papers/v11/cawley10a.html
   Primary abstract read. Noisy selection criteria themselves can be overfit.
   Supports bounded registered families, reported failures and new evidence.
   Chronological slicing of already-studied history does not undo prior exposure.

8. Options Industry Council: Gamma and Theta.
   https://www.optionseducation.org/advancedconcepts/gamma
   https://www.optionseducation.org/advancedconcepts/theta
   Explanatory bodies read. Local nonlinear response and accelerating time-value
   loss explain why a correct index direction may still lose option premium.
   Greeks are sensitivity approximations, not executable prices or forecasts.

9. Cboe, *Volatility Insights: Evaluating the Market Impact of SPX 0DTE Options*.
   https://www.cboe.com/insights/posts/volatility-insights-evaluating-the-market-impact-of-spx-0-dte-options/
   Article read. Its study distinguishes gross option activity from net market-
   maker positioning and uses exchange participant information. Supports refusing
   to infer a signed dealer-gamma regime from aggregate OI alone. Its US SPX
   averages/period are not estimates of NIFTY or SENSEX 2026 dealer positioning.

10. NSE F&O regulations (official archived PDF).
    https://nsearchives.nseindia.com/web/sites/default/files/inline-files/NSEFORegulations2025.pdf
    Official indexed definition: OI is outstanding unsettled contracts. Used only
    for the definition, not an assumption about minute update timing or which
    side initiated trades. Do not label public OI changes identified seller flow.

11. Kite Connect WebSocket documentation.
    https://kite.trade/docs/connect/v3/websocket/
    Documentation read: full-mode depth, quote timestamps/OI fields, subscription
    capability. Does not promise every exchange event, source refresh frequency,
    queue position or real order fills. Relevant to packet source capability and
    latency provenance; no runtime feed changes made by this review.

12. ICICI Direct official Breeze SDK README.
    https://github.com/Idirect-Tech/Breeze-Python-SDK/blob/main/README.md?plain=1
    Official historical-data examples inspected. Availability of an OI response
    field does not prove historical OI freshness, arrival time or older coverage.
    No API called. Acquisition must use the installed guarded download skill.

Not relied on: SSRN 5081696 (intraday option reversals) and 4881008 (0DTE market)
returned access errors. Search snippets alone are insufficient for transferring
their trade constructions. Reddit, trading vendors and performance anecdotes
were not used as strategy evidence. No provider-retention or dated exchange-rule
assertion was inferred from a forum.
