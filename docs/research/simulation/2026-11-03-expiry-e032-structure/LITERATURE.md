# Primary-source investigation, November 3, 2026

These sources motivate tests and establish data requirements. They do not
establish profitable NIFTY entries. No trader anecdote supplies a rule.

1. [Cont, Kukanov & Stoikov: The Price Impact of Order Book Events](https://arxiv.org/abs/1011.6402).
   Their U.S. stock study relates short-horizon price changes to imbalance of
   supply and demand at the best quotes; traded volume alone is a weaker proxy.
   Implication for us: minute volume is not a measurement of signed order flow.
   Even five-level snapshots every ten seconds miss intermediate book changes.
2. [Cont & Kukanov: Optimal Order Placement in Limit Order Markets](https://arxiv.org/abs/1210.1625).
   Order placement depends on fill risk, queue conditions and costs. A passive
   order's better price is not free if it misses the move. PATIENT tests this
   tradeoff without awarding intrabar touch fills or queue priority.
3. [Cboe: 0DTEs Decoded, May 2, 2025](https://www.cboe.com/insights/posts/0-dt-es-decoded-positioning-trends-and-market-impact).
   Cboe reports balanced customer SPX activity and small aggregate market-maker
   gamma hedging in its sample. That contradicts the assumption that high
   activity automatically means a one-way dealer squeeze. It is U.S. evidence,
   not a finding about India's market.
4. [Amaya et al.: 0DTE Index Options and Market Volatility](https://cdn.cboe.com/resources/education/research_publications/gammasqueezes.pdf), January 25, 2025.
   The authors reconstruct dealer positions from trade records identifying
   buyer/seller capacity. They find both gamma signs, generally positive in
   their sample, with different volatility effects. Our open-interest totals
   contain no equivalent dealer-position information. Therefore no signed
   "dealer GEX" signal is fabricated from those totals.
5. [NSE real-time data specification overview](https://www.nseindia.com/static/market-data/real-time-data-subscription).
   NSE distinguishes best quotes, deeper levels and full order-book feeds.
   A last-trade history is not any of those order-book histories.
6. [Kite WebSocket documentation](https://kite.trade/docs/connect/v3/websocket/).
   Its full quote packets include five bid/offer levels and exchange timestamps.
   Streaming these can improve observation granularity compared with polling;
   it does not provide our broker's queue priority, guaranteed execution or
   complete exchange order-event history. No new connection was opened here.
7. [Nifty Indices: index calculation FAQ](https://www.niftyindices.com/resources/index-concepts/faqs) and
   [NSE settlement prices](https://www.nseindia.com/static/products-services/equity-derivatives-settlement-price).
   The published index close uses constituent closing prices; the historical
   FAQ describes last-half-hour weighted closes. A simple average of index
   minute bars is not an official exercise settlement. Current specifications
   cannot be assumed to reconstruct every historical rule change. We neither
   price an end-of-day arbitrage nor invent settlement proceeds.

Search limitation: SSRN's `0DTE Trading Rules` landing page returned HTTP 403
when opened. No uninspected full-paper conclusion or trading rule is attributed
to it. Broker/blog claims of enormous one-day gains were not verified and do
not identify a repeatable, selectable opportunity.
