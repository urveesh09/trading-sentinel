# Primary research used for EN96-EN105

Read on 2026-11-18. These support research questions/methods, not proof that a
particular NIFTY/SENSEX expiry rule is profitable. No social-media P&L claims
were used to set strategy parameters.

1. [OIC, General Information](https://www.optionseducation.org/referencelibrary/faq/general-information).
   OI counts outstanding contracts, each with long/short sides. Its sign/change
   alone cannot identify bullishness, an informed buyer or a covering seller.
   Application: EN96/97 representations, with neutral names and source receipts.
   The FAQ's US end-of-day reporting convention is not an assertion about the
   timestamp/update frequency of Indian exchange intraday OI.
2. [Pan/Poteshman, The Information in Option Volume for Future Stock Prices](https://www.mit.edu/~junpan/volume.pdf).
   Information was found in specially identified opening-buyer equity-option
   transactions. Application: option activity can contain information, but our
   aggregate OI is not that dataset; no transfer of their effect size, horizon
   or stock-level result to intraday index expiry. It motivates testing, not a
   claim that 'writers' reveal the right side.
3. [Garleanu/Pedersen, Dynamic Trading with Predictable Returns and Transaction Costs](https://w4.stern.nyu.edu/facdir/lpederse/papers/DynamicTrading.pdf).
   Signal persistence and trading costs affect trading intensity and desired
   positions in their model. Application: EN101 permission to continue and
   EN103 staged commitment. The paper's commodity-futures model is not a
   whole-lot expiry-option implementation or validation of our thresholds.
4. [Lehalle/Mounjid, Limit Order Strategic Placement with Adverse Selection Risk and the Role of Latency](https://arxiv.org/abs/1610.00261).
   Limit-order fills expose a participant to adverse selection; latency reduces
   ability to act on liquidity information. Application: EN99 includes missed
   runaways, conditional post-fill markouts, TTL/cancellation and receive clocks.
   It does not validate our queue position or establish simulated fills as real.
5. [Muravyev/Pearson, Option Trading Costs Are Lower Than You Think](https://www.cicfconf.org/sites/default/files/paper_745.pdf).
   Author working paper, 2015; journal version published in RFS 2020. High-frequency
   equity-option execution timing can change measured effective trading costs.
   Application: test executable timing and ask caps rather than declaring all
   spread costs unavoidable or crediting arbitrary price improvement. Its US
   equity-option data are not our expired Indian index chains.
6. [Cawley/Talbot, On Over-fitting in Model Selection and Subsequent Selection Bias in Performance Evaluation](https://www.jmlr.org/beta/papers/v11/cawley10a.html).
   Selecting hyperparameters can overfit an evaluation criterion. Application:
   chronological inner selection and separate prospective comparison of the
   selected procedure. Nesting on previously inspected dates is still development.
7. [Novy-Marx, Backtesting Strategies Based on Multiple Signals](https://www.nber.org/system/files/working_papers/w21329/w21329.pdf).
   Combining chosen signals greatly increases selection bias. Application:
   EN105 finite genotype registry, all ablations/trials and full-selector nulls.
   NBER full PDF fetch returned 403; the indexed NBER abstract and author record
   were accessible. No inaccessible detailed theorem is claimed to be implemented.
8. [Bailey/Lopez de Prado, The Deflated Sharpe Ratio](https://davidhbailey.com/dhbpapers/deflated-sharpe.pdf).
   Selection and nonnormal returns inflate apparent performance. Application:
   disclose full trial count, skew/tail concentration and selection uncertainty;
   DSR alone cannot qualify sparse serially dependent expiry tickets.
9. [OIC gamma](https://www.optionseducation.org/advancedconcepts/gamma) and
   [theta](https://www.optionseducation.org/advancedconcepts/theta).
   Near expiry, ATM gamma is large and time decay matters. Application: tail
   opportunity is plausible but price direction alone need not pay a long option.
   These are sensitivity concepts, not a tradable entry signal.
10. [Kite streaming documentation](https://kite.trade/docs/connect/v3/websocket/).
    Packet modes contain different price/depth/timestamp fields. Application:
    validate received fields, depth and event clocks for EN99 packet research.
    A documented field is not a guaranteed update frequency or known order queue.
11. [Lin/Luo/Shao, When Does Intraday Options Trading Predict Stock Returns?](https://shidongshao.github.io/assets/files/Lin_Luo_Shao_OOI.pdf).
    Author working paper, August 2026. Signed opening-volume and liquidity timing
    relate to next-day US stock returns. Its horizon and identified flow differ
    from our minute OI/index-expiry task. It reinforces the information-availability
    gap; no new feature requiring these unavailable labels is fabricated here.
12. [scikit-learn TimeSeriesSplit documentation](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html).
    Chronological splits avoid training on future records. Its equally spaced
    observation assumptions do not justify randomly treating irregular expiry
    minutes as samples. Proposed folds use dated expiry calendars and preserve
    missing sessions. No particular library version is required by this proposal.

All grid values in the proposal are **new engineering hypotheses**, selected to
span simple economically distinct alternatives. None is represented as a
published profitable parameter, a fitted optimum or an already-scored result.
