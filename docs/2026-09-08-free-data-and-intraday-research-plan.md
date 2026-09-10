# NIFTY/SENSEX research using existing resources and free data

Date: 8 September 2026. Dev inspected HEAD: `8693ecc` (safe Telegram diagnostic addition). This is a data/research implementation plan, not a new acceptance audit of that commit. Builds on `2026-09-08-fast-production-rollout-checklist.md`.

## 1. Decision and owner-readable answer

**Do not buy a specialist dataset yet.** First preserve Sentinel's existing market records, use its existing Kite subscription for historical candles and live quotes, add official daily reference reports, and build a forward option-depth archive. Investigate ICICIdirect Breeze as an optional no-additional-API-fee historical source if account access is available.

Yahoo/yfinance can help cross-check index history and broad context. It is not a verified replacement for NIFTY/SENSEX historical option quotes/depth. I did not find and verify a dependable unrestricted free historical depth archive covering both markets. That is a limit of this search, not proof none exists.

The important distinction is **free API access**, **zero incremental cost with an existing subscription**, and **free historical execution-quality data**. They are different. No additional purchase, account opening or data subscription is authorised by this plan.

The coding agent performs ingestion, research, report generation and technical registration. MiniMax may help interpret results and write explanations from verified facts. It must not invent prices, depth, option contracts, missing observations or qualifying evidence. The partner need not provide their strategy, holdings or broker access.

## 2. What Sentinel already has: read-only Production findings

Inspected the running Production `python-engine` SQLite database using `file:/data/cache.db?mode=ro`, on 8 September, around the 12:17 IST snapshot. Counts can change during the session.

| Existing table | Observed coverage | Useful for | Missing for execution research |
|---|---|---|---|
| `fno_chain_oi` | 89,652 rows, 31 August 09:22 through 8 September 12:17; 29,884 each for NIFTY, SENSEX and BANKNIFTY | Observed option LTP/OI/volume and broad intraday chain context | No bid/ask prices, quantities, full depth or individual exchange quote timestamps in this schema |
| `fno_fut_snap` | 1,446 rows; 482 per underlying over the same range | Futures LTP/OI and stored PCR/max-pain/ATM-IV context | Not a depth archive or full timestamped execution path |

Do not interpret equal row counts as complete quality-checked data. Validate gaps, duplicate/zero fields and session coverage. BANKNIFTY is existing evidence; the partner release remains NIFTY/SENSEX only.

Source inspection: `fno_oi_store.py` persists roughly five-minute analytics snapshots. `FNO_OI_RETENTION_DAYS` defaults to **7** and the EOD purge is wired. Its schema's primary key omits expiry even though expiry is a column; reusing it for multiple expiries at one timestamp could overwrite contracts. Introduce a separate correctly keyed research archive rather than widening this cache blindly.

The inspected database had no table names matching instrument/quote/candle archive patterns. This is not an exhaustive disk/container-volume inventory; filesystem caches and other databases may exist. Inventory them before claiming historical data is absent. Old comments mention disk pressure; current free space was not measured in this research turn.

**First implementation task:** export the available evidence safely before normal retention removes it. Do not simply disable Production cleanup or put unlimited ticks into the trading database.

## 3. Source research and recommended order

### A. Kite: primary existing source, not a completely free data service

Zerodha currently lists live and historical data in its ₹500/month-per-key paid Connect plan; its free Personal API excludes those data services. If Sentinel already has paid access, collection has no separate vendor fee, but subscription and storage costs still exist. Verify entitlement without printing keys. [Zerodha data-plan explanation](https://support.zerodha.com/category/trading-and-markets/general-kite/kite-api/articles/historical-data-and-live-market-data-payment-plan).

Historical endpoints supply candles and optional OI, not past bid/ask depth. Instrument masters contain live contracts; save mappings proactively. Continuous history is limited to daily futures history for supported NFO/MCX contracts, not an expired-option-chain backfill. Saving a token is necessary for identification but is not a guarantee the provider will retain accessible option history after expiry. Harvest available contract candles before they disappear and record access results. [Kite historical data](https://kite.trade/docs/connect/v3/historical/).

Live full-mode WebSocket messages contain five bid/offer levels, OI and separate trade/exchange timestamps. Index packets differ from tradable-contract packets. Published limits include 3,000 instruments per connection and up to three connections per API key; our narrow universe should be much smaller. This is a broker stream, not a guarantee of every exchange event or future fills. [Kite WebSocket documentation](https://kite.trade/docs/connect/v3/websocket/).

Kite's full-quote REST endpoint supports up to 500 instruments per request, including depth. Instrument tokens may be reused; archive daily masters and identify contracts by exchange plus full contract identity, retaining dated token mappings. Master-file last prices are not live quotes. [Kite quotes and instruments](https://kite.trade/docs/connect/v3/market-quotes/).

### B. ICICIdirect Breeze: strongest free-API candidate found

ICICIdirect advertises free API/historical access for its customers, historical derivatives and three years of second-level LTP data. This does not promise historical order-book depth or cost-free brokerage/account ownership. Check the applicable account plan and access terms before opening anything. [Official Breeze offering](https://www.icicidirect.com/futures-and-options/api/breeze).

Its documentation provides historical option requests for NIFTY/NFO and a SENSEX request using BFO and provider symbol `BSESEN`. This supports a concrete two-index access probe, not an assumption that every date/strike exists. Test representative expired contracts, both legs, expiry types, timestamps and intervals. Preserve provider-specific mapping; do not use `BSESEN` as a Kite symbol. [Breeze API reference](https://api.icicidirect.com/breezeapi/documents/index.html), [official NIFTY historical-download example](https://www.icicidirect.com/futures-and-options/api/breeze/article/how-to-download-historical-data-using-breezeapi-python-sdk).

Decision: if the owner already has suitable ICICIdirect access, test this in parallel. Otherwise deliver the adapter/fixtures and a precise access request; do not block Kite collection or open an account automatically. Successful option-candle history improves the study but remains candle-based evidence unless actual depth is supplied.

### C. Official exchange reports: reference and daily context

NSE provides daily derivatives reports, including bhavcopy and historical report listings; use published downloadable files under applicable access/use terms. They support contract/date identity, daily prices, volumes, OI and reconciliation—not an intraday entry/exit order book. [NSE derivatives reports](https://www.nseindia.com/all-reports-derivatives), [historical report directory](https://www.nseindia.com/static/resources/historical-reports-capital-market-daily-monthly-archives).

For BSE use official derivatives report/contract links from the regulator's directory, validate current file format and availability and retain raw downloads. The BSE report page did not successfully open with the research browser this turn; automated download feasibility was not established. Do not assume NSE file names, schemas or historical coverage apply to BSE. [SEBI exchange-information directory](https://www.sebi.gov.in/curation/equity_derivatives.html).

Use download/import adapters that can also accept a manually obtained authorised file. Do not build the collector around reverse-engineering public option-chain endpoints, bypassing anti-bot controls or assuming visible website data grants bulk redistribution rights. The earlier blanket claim about the exact NSE option-chain terms was not independently confirmed in the retrieved page; check applicable terms directly rather than repeating an unsupported legal quote. A chain page is not an historical full-depth feed.

### D. Yahoo/yfinance: optional secondary index context only

yfinance describes itself as an unofficial research/education tool and warns about Yahoo's personal-use terms. Use only where permitted; do not make partner-facing data redistribution or production reliability depend on it. [yfinance documentation](https://ranaroussi.github.io/yfinance/).

A limited adapter may cross-check available NIFTY/SENSEX daily index prices and gaps against primary data. Discover/verify symbols and adjustment conventions; never substitute ETF prices for an index unnoticed. Do not use Yahoo option responses to claim coverage of the required Indian derivative contracts, or derive executable spreads from index prices. Missing data remains missing. No need to add this dependency if primary index history is sufficient.

### E. Other broker sources: useful alternatives, not verified free depth

Upstox documents expired-contract candles/OI, but the expired endpoint explicitly identifies Upstox Plus as required. Do not describe it as an unconditional free alternative. Verify current account entitlement before proposing integration. [Upstox expired history](https://upstox.com/developer/api-documentation/get-expired-historical-candle-data/).

Dhan provides an expired-options endpoint, but its data subscription is listed at ₹499 plus taxes monthly. Its presence does not establish historical depth coverage. Keep it as an optional fallback if the owner later chooses paid access, not a dependency of this no-new-vendor-cost plan. [Dhan expired-options support](https://dhan.co/support/platforms/dhanhq-api/do-dhan-provides-expired-options-data-via-the-api-s/), [Dhan API pricing support](https://dhan.co/support/platforms/dhanhq-api/how-to-access-dhan-api/).

Community repositories/sample datasets can test importers or reproduce a published study only when provenance, licence, timestamps and contracts are verifiable. No verified free community full-depth archive was established here. Reject unverifiable Telegram/Drive/CSV bundles as qualification evidence; open-source downloader code is not ownership of its upstream data.

## 4. Evidence levels: get value now without pretending to have missing data

Store these separately in every dataset, run and report:

| Level | Input | What it can establish | What it cannot establish |
|---|---|---|---|
| `UNDERLYING_RESEARCH` | Index/futures candles, calendar/context | Signal behaviour, trigger timing, regime and invalidation studies | Historical option profitability or fillability |
| `OPTION_CANDLE_MODELLED` | Actual contract candles/OI with modelled spread/slippage | More realistic option-path scenarios and cost sensitivity | Synchronous historical bid/ask, depth or assured multi-leg fills |
| `OBSERVED_QUOTE_REPLAY` | Archived provider timestamped quotes/depth and contract masters | Quote-observed prices/capacity and conservative replay under stated assumptions | Queue position, guaranteed simultaneous fills or the partner's actual outcome |
| `LIVE_CURRENT_PREVIEW` | Fresh current quotes and deterministic card checks | Present quote-backed card plausibility | Historical edge or future profit |

Observed quotes still require conservative execution modelling. Do not label them “execution proven.” Keep research qualification a reasoned review of data quality, sample size, uncertainty, economics and forward evidence—not a mandatory purchase of perfect tick data, an arbitrary waiting period or a hash-only gate.

The agent should run useful modelled studies immediately and collect forward observations in parallel. It must not auto-upgrade their evidence level. If current evidence is insufficient for actionable strategy qualification, show a precise blocker while continuing deployment, collection and non-trading Telegram diagnostics. Any new partner-facing market-watch category without actionable contracts needs explicit scope and rendering tests; never smuggle unqualified trade instructions through a status message.

## 5. Implementation work packages

### D1 — Preserve and inventory the existing evidence first

Create a bounded read-only export job/command, schema manifest and coverage report. Identify Production volumes, caches, daily masters and available backups. Extract applicable NIFTY/SENSEX data through a consistent snapshot/read transaction or supported backup API; do not copy a live SQLite file while ignoring its WAL.

Write exports to a separate configured research location with checksums, export timestamps and source schema/commit. Preserve observed five-minute LTP/OI as such. Do not interpolate it into “historical depth.” Add archive-before-purge verification through Dev/GitHub deployment; preserve operational cache retention unless measured capacity justifies a change.

Acceptance: reproducible counts/hash, no source writes, restart-safe export, verified manifest before archival deletion, missing-volume reporting and zero credentials in artifacts.

### D2 — Daily immutable contract catalogue and source adapters

Archive dated raw NFO/BFO masters plus canonical records: provider, exchange, segment, underlying, full symbol, token, expiry, strike, type, lot/tick size, validity interval and raw-file hash. Separate provider aliases and futures reference from spot index identity. Detect token reuse and contract changes rather than merging by token alone.

Implement a provider-neutral interface for historical candles, current snapshots, master lookup and source capability/entitlement reports. Reuse `kite_client.py`, `fno_chain.py` and `fno_instruments.py`; do not create duplicate authenticated clients competing for resources. Optional Breeze adapters have independent mapping/validation fixtures. Rate-limit/backoff/checkpoint all backfills; do not let research traffic starve operational quote requests.

Acceptance: both exchanges, same token reused after expiry, changed lots, missing expiry, provider alias mismatch and interrupted downloads. Snapshot each download's true coverage instead of assuming advertised history exists.

### D3 — Forward quote/depth collector independent of advice switches

Collector runs for authorised market-data observation even when partner delivery is off, no profile is saved, no setup appears, or qualification is pending. It must not subscribe to partner orders or invoke order APIs.

Initial universe proposal: two indices, two eligible future option expiries, ATM ±5 strikes, CE/PE—up to 88 option contracts—plus relevant underlying/futures references. This is an engineering starting point, not a fixed exchange structure. Keep all legs of published or evaluated still-active ideas subscribed until management ends, even when they move outside the current ATM window. Persist additions/removals and the selection reason; otherwise research has unrecorded selection bias.

Prefer full-mode WebSocket ingestion using the supported SDK and a bounded queue/writer, with a rate-limited REST full-quote fallback that is explicitly labelled lower-frequency. Reuse an existing stream if one actually exists and can be safely extended. Do not assume the initial code search proves no other collector exists.

Persist exchange timestamp, local UTC receipt timestamp, monotonic receive order, reconnect epoch, source/mode, contract identity, five depth levels with price/quantity/order count, LTP, last-trade time, cumulative volume/OI, missing-field flags and raw/normalised hashes. Record heartbeat separately from quote freshness. A reconnect gap cannot be backfilled with fabricated ticks or later snapshots.

At every evaluated candidate and management event, pin the exact quote evidence for both legs, underlying reference, received time, validation and rejection reasons. Collect eligible rejected alternatives too; collecting only sent/winning ideas invalidates comparisons.

Acceptance: stale/crossed/missing depth, timestamp ordering, timezone, reconnect, packet-type distinction, index packets, rejected candidates, dynamic subscriptions and backpressure. Do not call later data available earlier than its receive time in replay.

### D4 — Storage compatible with the desktop infrastructure

Measure actual disk/RAM/CPU and existing workloads first. Keep trading SQLite for operational state; use bounded append-only research segments, preferably compressed columnar daily partitions with atomic finalisation and manifests. A small SQLite catalogue can index manifests. Avoid unbounded raw-tick tables competing with order/risk writes.

Budget storage empirically from a measured session; do not claim a fixed MB/day for a variable stream. Make raw-event retention and compressed retention configurable, preserve report-pinned evidence, and alert before exhausting a reserved operational disk floor. A reasonable starting policy to measure is a short raw buffer plus 30–90 days of compressed events, extended only when capacity permits. Record every sampling/drop policy and gap. If overloaded, protect operational processes and report degraded research evidence rather than silently dropping data.

Acceptance: crash-safe segment recovery, checksum verification, retention never removes pinned qualification inputs, disk-pressure behaviour, bounded memory and measured additional API/CPU/disk load.

### D5 — Immediate historical study with explicit assumptions

Run the existing exact intraday strategy code and policy version on available underlying history now. Add actual option candles where retrievable from current/saved Kite contracts or optional Breeze. Do not price a two-leg entry by pairing each leg's favourable high/low from the same candle; those may never have coexisted.

Freeze chronological development/evaluation periods, calendar and parameter set. Include all eligible sessions and failures, not only convenient available contracts. For candle-only option research use conservative execution bands and delay/slippage/volatility stresses; missing exit price produces unknown/unresolved evidence, not zero loss or forward-filled certainty. If a model estimates option values, preserve model parameters and distinguish estimated IV from observed IV; EOD IV must not leak into morning decisions.

Compare a small declared set of entry/exit choices with current baseline using realistic same-day deadlines. Report directional accuracy separately from option net outcomes. Retain no-fill counts, sample dependence, losses, drawdown, turnover, fee burden, largest-day concentration and uncertainty. Keep per-index reports and shared-risk portfolio comparisons distinct. No fixed positive-return threshold is invented here; define review criteria before choosing a winner.

Acceptance: no look-ahead from EOD reports, no future master mapping, no fabricated expired chains, honest unknown states, deterministic reproducibility and independent payoff/cost oracles.

### D6 — Forward replay and qualification without unnecessary delay

Use archived observations to replay the same selected contracts and decision timestamps, including estimated manual reaction delays such as 15/30/60 seconds as declared scenarios. Cross both legs on conservative sides subject to displayed quantities and explicit slippage; missing depth or mismatched timestamps yields no usable execution estimate. Test realistic same-day exits and gap/timeout periods. Depth is cancellable and cannot establish a guaranteed fill.

Combine this with the broader modelled study, keeping evidence types separate. Review uncertainty, sample diversity, adverse sessions and model-vs-observation error. Do not qualify because “five days elapsed” or because a handful of trades won. Conversely, no paid historical-depth vendor is a mandatory prerequisite if adequate actual evidence can be built from existing access.

Generate actual dataset/run/report artifacts, compute fingerprints and register the justified scope under the established API only after review. Pin the matching code, index, structure and `INTRADAY` horizon. One index can progress independently; no assumed SENSEX qualification from a NIFTY result. Never mark a research registry entry qualified merely to restore message volume.

### D7 — Operator visibility and AI responsibilities

Add a concise per-source/index data-readiness view: entitlement, latest master, history date range, option coverage, observed depth start date, missing sessions, reconnect gaps, bytes stored, archive lag, current freshness and research evidence level. Show actionable reasons for missing qualification.

The coding agent owns fetching, parsers, tests, research execution, report/hash creation and payload preparation. MiniMax can summarise “what this evidence supports/does not support,” find anomalies for deterministic checking and explain cards from validated facts. It cannot synthesize missing historic observations or infer that a free dataset is licensed for redistribution.

Prepare compact partner advice rather than publishing raw data dumps; verify provider permissions for intended storage/use and any external content. This is a practical source-access check, not a request for partner credentials or a new blanket approval cycle.

## 6. Delivery order and release evidence

| Checkpoint | Deliver now | Can proceed without a new broker/vendor account? |
|---|---|---|
| A | Read-only inventory/export; daily contract archive; collector contract and tests | Yes with existing configured access |
| B | Kite forward collector, bounded storage and readiness screen | Yes if existing paid data entitlement is active |
| C | Underlying/modelled historical reports; optional Breeze capability probe | Kite/local work yes; Breeze needs that account's authorised access |
| D | Observed-quote replay, integrated current-data previews and qualification artifacts where justified | Yes as sufficient observations become available |
| E | Scoped advisory enablement through existing GitHub rollout plan | Only for evidenced eligible strategies; no data purchase inherently required |

Do not wait to complete a historical research report before building the collector; lost observations cannot be reconstructed later. No promised calendar date for proven edge. Ask for access only when a concrete capability probe requires it; continue independent work.

Current `8693ecc` adds a safe Telegram diagnostic according to the commit title. Inspect/reuse it rather than create a second diagnostic subsystem. A separately authorised non-trading diagnostic can verify receipt while automated advice remains off. Collection and report generation require no partner message.

All code and configuration changes in Dev, promotion through GitHub, no direct Production edits, no automatic account opening or purchase, no trading orders. This research turn made only read-only Production queries and created planning documentation; no historical-data download, collector deployment or live message was performed.

## 7. Inputs needed from the owner

No strategy details or partner positions are required. Existing Kite data entitlement should be verified by the agent. Optional question only if seeking Breeze history: whether the owner already has ICICIdirect/Breeze access and wants to use it. If not, continue Kite/local/exchange work. Never request secrets in chat or share another person's broker token.

Only consider a paid data source later if a report identifies a specific high-value gap, verified coverage and total cost. The current plan is to maximise already available and permitted free resources first.

## Copyable coding-agent assignment

> Implement `docs/2026-09-08-free-data-and-intraday-research-plan.md` alongside the final rollout checklist. First preserve/inventory available Production evidence read-only; then build the daily NFO/BFO contract archive and independent Kite full-mode quote/depth collector with bounded storage, gap reporting and exact candidate evidence. Work in Dev and deploy only through GitHub. Use existing Kite/local resources before any new paid source. Research now with clearly labelled underlying/option-candle models; investigate the official free-to-customers Breeze historical API for NIFTY and BFO/BSESEN only if authorised access is available, without blocking core work. Keep Yahoo secondary and do not scrape unapproved chain endpoints or invent historical depth. Execute actual frozen intraday research, forward quote replay and per-index reports; preserve all failed/no-fill/missing-data cases and validate code/data hashes before justified qualification. MiniMax assists interpretation, never fabricates prices or numerical authority. Deliver checkpoints A–E with tests, coverage/storage/latency evidence, immutable artifacts and a precise readiness table. No partner order monitoring, forced messages, purchases or qualification-by-placeholder.
