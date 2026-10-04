# Penny: capture stronger opportunities with controlled risk — October 4, 2026

This is a researched development proposal, not a demonstrated profitable policy
or authorization to activate live trading. The owner approved the preceding
comparison/rounding/tick corrections. Those changes are tracked separately in
[the implementation slice](2026-10-04-penny-corrections-and-relative-strength-slice.md).
Dev base is `a674740`; Production remains untouched. F&O source, capital,
subscriptions, request capacity, scheduling and exits must remain protected in
every subsequent slice. No Penny experiment may borrow from another division.

## The return objective

Yes: a 1–2% Penny-book gain can occur on an individual day. A declining index
does not establish that every stock declines. The challenge is selecting an
affordable opportunity before its outcome is known and actually executing both
sides. A stock discovered after it rose, or locked at its upper circuit, is not
an executable opportunity available to the strategy.

Measure net return on beginning-of-day Penny allocated equity, including idle
cash, costs and marked open exposure. At ₹2,000, 1% means ₹20 net and 2% means
₹40 net. Three ₹500 positions each gaining 2% earn ₹30 gross, or 1.5% of the
book. Conversely, one ₹500 position gaining 3% and another losing 1% net ₹10
gross, only 0.5% of the book. These arithmetic examples assume fillable moves
and are not forecasts, signals or a capital-allocation change.

Daily expected return depends on the number of executable trades, risk per
trade and net expectancy in units of planned risk. Four trades risking 0.25%
of the book each would require an average **net** expectancy of 1R per trade
to average 1% per day. This is a strong, unproved edge. Even a positive mean
would still permit losing and flat days. Stop risk is planned risk, not a
guaranteed loss ceiling. No quota should force an entry when the observed edge
does not cover costs.

The existing ₹100,000 paper book, ₹500 per-stock cap and three MIS slots can
deploy at most ₹1,500 concurrently before stop-based shrinkage. That utilization
is quite different from a ₹2,000 book. Widening a tiny candle stop while
preserving its original rupee risk reduces shares further: entry ₹20, candle
stop ₹19.95 and 25 shares become a ₹19.70 stop with four shares, only ₹80
notional. This explains part of the small rupee results; it does not establish
that increasing exposure would be profitable.

## What the local evidence says

The stateful trader variants already implemented were more active and failed
their untouched comparisons. T1 baseline closed 24 trades for +₹63.17; V1
closed 91 for −₹102.94, thesis V1 closed 283 for −₹104.89, and V2 closed 80 for
−₹17.02. The thesis policy had positive gross P&L but larger costs. These are
stored lifecycle simulations, not Production performance or owner-sized returns.
See [the independent review](2026-10-04-penny-efficiency-independent-review.md).

The previously reported noise-stop improvement is seen-window evidence. The
automatic +1R breakeven variant lost money in that comparison. Neither fact
supports adding more setups indiscriminately or mechanically cutting winners
earlier. Newly corrected stop arithmetic requires new receipts; archived
amounts describe their original source version.

Authorized corrections were then checked on the same seen Sep 24–30 window:
BAR_LOW reproduced 18 closes / +₹15.1765 exactly; corrected NOISE_FLOOR had
15 closes / +₹36.4486, realized drawdown ₹30.8560. Its net after removing the
best winner was −₹4.8747 and adverse-fill bound −₹41.0747. The source/data
manifest stayed fixed in the valid run. This is encouraging development
evidence with clear concentration/execution weaknesses, not a new untouched
test or a ₹2,000-book result. See [stable receipts](research/yahoo/2026-10-04-penny-correction-parity-stable/results.json).

## Recommended first hypothesis: persistent stock-specific strength

Reuse the existing setup-state engine and lifecycle, adding a causal selection
layer rather than another collection of universal entry gates. Hard cash,
protection, valid-data, executable-price and broker restrictions remain hard
constraints. Ranking features choose between affordable eligible opportunities.

1. **Observe and rank the opportunity.** Use completed bars only. Rank positive
   absolute stock momentum, excess return over its sector/index, same-time
   relative traded value, persistence across successive completed intervals,
   and remaining range relative to observed noise. A ticker losing less than
   the index does not satisfy positive absolute momentum. ETF/commodity units
   in today's low-price universe should be classified separately from operating
   company shares, not treated as company catalysts. Missing benchmark/sector
   histories must be explicit unavailable features, never fabricated strength.
2. **Watch a specific setup, then enter within a price budget.** Start observing
   earlier than the current 10:30 entry window, without buying the first opening
   spike. Test one continuation/retest trigger first, reusing shipped functions
   wherever available. Require a completed pullback/reclaim or breakout retest
   while strength persists. Record setup identity, reference level and maximum
   affordable entry. If the quote runs beyond that price, expire the setup.
   Do not require a fresh all-day high for every possible future reclaim setup.
   Keep this broader entry family as a separate later experiment if changing
   selection alone is supported; the generic early ORB copy has already failed
   locally and is not a new hypothesis merely under another name.
3. **Evaluate execution before spending risk.** Timestamped quotes, spread,
   actual ticks, band headroom, broker eligibility and depth determine whether
   the apparent move is affordable. A catalyst may improve ranking only when
   its verified publication timestamp precedes the decision. Volume is not a
   substitute for available bid/ask liquidity. Initially use depth for execution
   observation and stress bounds, not a supposed predictive signal from one
   snapshot. Historical candles cannot validate this part; collect shadow quotes.
4. **Manage the thesis, preserve the winner.** Keep existing exit policy for the
   first selection comparison. Subsequently test a completed-bar structural or
   volatility trail: protect below confirmed swing support, tighten when progress
   and relative strength fade, and exit failed setups or the mandatory session
   deadline. Never widen admitted risk, average down or automatically move to
   breakeven at +1R. Partial profit-taking needs a separate test of costs and
   lost right-tail gains; integer quantities often make it impractical here.
5. **Choose deployment from the stop, not from desired income.** A later risk
   policy should select a structural/noise stop first, then size from an explicit
   rupee budget including executable entry/stop prices and cost/slippage reserve,
   capped by free own cash, the existing stock cap and total/correlated risk.
   An illustrative research budget is 0.25% of a ₹2,000 book, ₹5 per trade;
   this is not enabled and is not necessarily lower than today's tiny admitted
   candle-risk amount. Raising that amount is a material policy change. Freeze
   the budget before scoring; do not increase it to compensate for losses.

In a falling market, this hypothesis can consider a stock with positive
absolute returns and sustained independent demand. Index weakness becomes a
ranking/risk context feature, not a blanket red-market veto. Preserve existing
market/regime risk brakes until that proposed change has its own controlled
test. This long-only approach remains exposed to a market reversal; it is not
a market-neutral implementation of academic residual momentum.

## Primary research and the limits of applying it

| Source | Useful finding/design implication | Transfer limit |
| --- | --- | --- |
| [Blitz, Huij and Martens, Residual Momentum](https://repub.eur.nl/pub/22252/ResidualMomentum-2011.pdf) | Separate company-specific momentum from changing common-factor exposures. Motives the stock/sector/index comparison. | Monthly, long/short academic portfolios; simple intraday excess return is not their fitted factor-residual strategy or evidence of NSE Penny profit. |
| [Zarattini, Barbon and Aziz, Stocks in Play/ORB](https://www.alexandria.unisg.ch/server/api/core/bitstreams/3c2989c4-688d-4d78-8a71-f02690990d51/content) | Concentrating on unusual-volume opportunities can matter more than trading all breakouts. | US sample excludes shares below $5 and uses different liquidity, leverage and costs. The PDF was inspected in the preceding review; fresh retrieval timed out, while the primary search index remained available. Our local ORB-style candidates did not establish the advertised edge. |
| [Gao et al., Market Intraday Momentum](https://www.researchwithrutgers.org/en/publications/market-intraday-momentum/) | Opening returns predicted late-session returns in the studied ETFs, with variation by volume/volatility context. Time-of-day matters. | US ETF evidence and a specific late-session horizon. It does not justify arbitrary mid-morning entries or extending Penny past its required exit time. University publication abstract inspected. |
| [Gârleanu and Pedersen, Dynamic Trading with Transaction Costs](https://archive.nyu.edu/bitstream/2451/28346/2/DynamicTrading.pdf) | Persistence and turnover costs belong in the trading decision. Supports setup memory and avoiding repeated fleeting signals. | Optimization model with commodity-futures illustration; not a fitted Penny entry/exit rule. |
| [Cont, Kukanov and Stoikov, Order Book Events](https://arxiv.org/abs/1011.6402) | Short-horizon price changes relate to order-flow imbalance and depth in their US-stock sample. | Five-level periodic Kite snapshots cannot reproduce full order-event data; displayed depth may vanish. |
| [Barber et al., Cross-section of Speculator Skill](https://faculty.haas.berkeley.edu/odean/papers/day%20traders/The%20Cross-Section%20of%20Speculator%20Skill.pdf) | A small group showed persistent skill after fees in Taiwan. Repeatable trading skill is possible. | Their averages, population and capital definition do not prove 1% daily allocated-equity returns for our system or profitable every day. |
| [SEBI equity-cash intraday study release](https://www.sebi.gov.in/sebi_data/attachdocs/jul-2024/1721818619980.pdf) | Costs materially affected both winners and losers; frequent trading correlated with more loss-making accounts. | Historical retail population statistics, not a causal verdict on our algorithm. Use as a reason to count costs and test turnover. |
| [NSE price bands](https://www.nseindia.com/static/products-services/equity-market-price-bands) and [Kite quotes/instruments](https://kite.trade/docs/connect/v3/market-quotes/) | Exchange bands and actual instrument ticks/quotes constrain achievable fills. | Today's metadata cannot be substituted for historical band/tick evidence. |
| [Kite streaming](https://kite.trade/docs/connect/v3/websocket/) | Provides quote/depth timestamps and order updates for future execution observation. | Adding subscriptions consumes shared capacity; F&O must retain priority and exits must remain timely. No new connection/subscription here. |
| [Bailey et al., Statistical Overfitting and Backtest Performance](https://sdm.lbl.gov/oapapers/ssrn-id2507040-bailey.pdf) | Trying many variants on the same window can create impressive in-sample results without predictive edge. | Freeze a small set of hypotheses and preserve all trials; adding more indicators is not evidence of intelligence. |

## Development contracts and acceptance sequence

| Slice | Files/contracts | Acceptance | Rollout/rollback |
| --- | --- | --- | --- |
| C0, authorized corrections | `penny_prices`, breakout, executor, universe metadata, lifecycle/Lab and study runner | Exact rounded planned-risk bound; dated instrument ticks; unknown metadata blocks new live entries while recovery remains available; explicit old/new policies and effective-setting/cost binding | Dev only; existing flags/caps unchanged; full receipt in correction slice. |
| R0, independent stop decision | Corrected T3 definition plus independently validated available Kite data | Committed freeze before once-only scoring; separate paper and owner-budget books; old-baseline parity; no selected invalid bars or reused holdout | Continue paper observation only if supported; no live/funding authority from results. Missing history yields unavailable. |
| R1, selection ablation | Existing `adaptive_penny_policy`, Penny universe/scanner, lifecycle adapter; timestamped index/sector feature contract | Current setup/stop/exit unchanged; new ranking versus original admission order; causal same-time volume and point-in-time eligibility; red/green sessions reported separately | Research flag OFF; retain incumbent and all failed trials. No broad live entry-gate relaxation. |
| R2, management ablation | Existing exit functions and replay adapter, persisted setup memory | One independent trail/thesis hypothesis versus incumbent exits on matched entries; include churn, winner giveback and missed runners | Research flag OFF; mandatory exits and protection remain active. No deployment from seen-window gain. |
| R3, owner risk/execution contract | `penny_risk`, scanner/executor/position tracker and Penny-only settlement/read models | Reconcile fills/partial cash/open marked risk after restart; settlement-driven daily brake; pre-order limit/stop budget reserve; own-cash and existing caps; exits during entry halt; explicit gap/non-fill stress | Material plan required before implementation; no live until reconciled risk authority works. Do not alter shared F&O accounting. |
| R4, observation and promotion | Penny-only quote/execution telemetry and GitHub release receipt | Paper/shadow execution evidence; stale/partial/reject/stop-failure drills; measured provider and scheduler budget with F&O priority; compare simulated and observed costs | Promote only through GitHub after separately requested release; live remains OFF until a separate owner decision. Roll back candidate selection while preserving exits. |

Current replay explicitly reports that runtime settlements do not feed the
PennyRiskEngine daily counter. Its advertised daily switch therefore must not
be treated as validated live protection. Existing source default is 20% of
bankroll, not a new conservative daily-risk policy. R3 must resolve accounting
and predeclare a much smaller research loss budget before increasing admitted
risk; neither a reliable daily brake nor tight gap-loss bound is claimed here.

Every experiment must report net allocated-equity return on all covered
sessions, including zero-trade sessions; median and lower-tail day, frequency
of ≥1%/≥2% days, loss/flat days, drawdown and recovery, cash utilization, net
expectancy, turnover costs, concentration after removing best winners and
adverse fills. Missing sessions are unavailable, not zero return. Current-symbol
selection, fixed historical regime, missing depth and approximate fills must
remain visible. Use marked-equity drawdown, not only closed-trade drawdown.

An opportunity audit should record every causal watched setup, admission/rank,
expiry, skip reason and subsequent path. It can reveal late scans, capacity
lost to weak incumbents and inaccessible circuit moves. A hindsight oracle is
only an upper bound on available opportunities, never strategy P&L. With enough
clean training data, calibrate net-edge estimates by setup/context using only
past observations and shrink sparse estimates toward zero. Do not display
invented win probabilities or fit to the next test window.

The next development priority is R0 and R1, with R3 a prerequisite for live
activation or larger admitted risk. This gives the 1% aspiration an explicit
measurement path while retaining the right to stay flat when opportunities
are not executable.
