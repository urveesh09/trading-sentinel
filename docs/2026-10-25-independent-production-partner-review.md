# October 25 independent Production and partner review

Status: review completed in Dev against Production release `74688534434aeb00164b31a8f9c717d7ae883cb2` and Dev `6e91f3b`. No application fix, Production edit, restart, trading activation, real order or outbound message was performed during this review. Findings below remain open. This is software and operational evidence, not proof of profitability.

## Verified deployment and recent development

- Production checkout and all three running application images report `7468853` (PR #117). `scripts/verify_deployment.py --expected-sha <full Production HEAD>` passed container/image identity and HTTP release checks.
- Dev's application tree equals that Production release. Its later committed changes are the O25k documentation receipt. Existing unrelated Dev edits remain untouched.
- Independently compared normalized file contents, rather than trusting release labels alone: 293 non-test Python engine files, 38 gateway server JS/JSON files and 11 agent Python files match the running containers. One initial raw-byte difference was Windows CRLF versus LF, not a source difference. The compiled React bundle was not independently rebuilt during this review; its source tree matches the release and the deployed gateway serves HTTP 200.
- Engine, gateway, agent and nginx are healthy; application restart policies are `always`. Engine logging is effective at 20m x 25 files.
- Both gateway and engine have their intended tunnel settings, with no conflicting engine order-base override. Gateway startup reports encrypted routing. The Mumbai Oracle VM's `kite-tunnel` is active/enabled and its installed source hashes identically to current Dev `scripts/kite_tunnel.py`.
- Architecture clarification: the full Production application runs in Docker on the owner's Windows PC. Oracle Mumbai hosts the Kite routing service, not another deployed copy of the engine/dashboard. Docker is not installed on that VM. Its UTC host clock is not an application scheduler defect: application scheduling uses IST.
- New O25k behavior is present: 07:00 trading-day login reminder, separate owner and partner app links, 30-minute scheduler misfire grace, partner skip when already connected. Its happy-path and scheduler tests pass. Failed-delivery semantics need the correction in finding R3.
- Current engine health is DEGRADED/trading_ready=false, with `no_kite_token`, `instrument_cache_unavailable`, `order_execution_unverified`. These are actual pending operational prerequisites on Sunday, not evidence of a successful broker login or order test.
- Effective switches: FNO_LIVE_TEST_ENABLED=false, FNO_LIVE_TRADING=false, FNO_DISABLE_LIVE=true, OWNER_LIVE_ENTRY_HALT=true; channel list momentum,penny,edge. No live switch was changed.
- Recent bounded log scan: engine 2,948 lines, gateway 91, agent 3; no traceback, MAX_INSTANCES or partner failure matched in that sample. This Sunday/startup sample does not establish market-load performance or rule out other errors.

## Reproduced findings

### R1 — P1: queued CHECK replies can present old financial levels as current

Files/contracts: `python-engine/partner_watch.py`, `ALWAYS_SENT`, `LIFETIME_SEC`, `answer_check`, `_say`, `_build`, `_deliver`.

CHECK is stored as fixed text in the durable outbox and shares the ALWAYS_SENT bypass used by login/status messages. Its lifetime is 120 seconds. A retry after a provably unsent connection failure does not refresh its market inputs, price, stop, target or account context.

Reproduction: enqueue a CHECK at 10:00 with an ask-now price; fake a first `unsent_connect`; retry at 10:00:30. The unchanged original text is acknowledged. That is already outside the watch's stated 15-second quote freshness limit. It can also happen on a delayed first send. No real message was sent in this test.

Required fix: distinguish a financial CHECK from fixed login/help messages. Persist its request, exact resolved contract identity and observation times; rebuild actionable numbers from current evidence at delivery, or expire them with an explicit request to recheck. A retry must not silently select a different expiry. A short message TTL alone is insufficient if the quote was already old or computation used most of its freshness window. Preserve deduplication, bounded reads, urgent-alarm priority and ambiguous-send handling.

Acceptance: market changes while queued, first-send delay, safe retry after connection failure/429/5xx, restart, contract/expiry rollover and lost account login. An old ask may be shown only as a timestamped historical observation, never "now". No partner order authority is introduced.

### R2 — P2: freshness validation is incomplete, and a typed price bypasses known stale inputs

Files/contracts: `python-engine/partner_watch.py:948`, `_top`, `_quotes`, `_market_plan`, `check_text`.

- `stale()` requires both exchange and receipt timestamps before rejecting exchange age. Missing exchange time, or an exchange time ten minutes in the future, is accepted as fresh when the local read is recent. `level_state(90, quote_with_ltp_100)` returns VALID for both cases.
- `_market_plan` rejects a stale ask only when the partner did not supply an entry price. With a supplied price, a quote already known to be ten minutes stale can still produce a plan stop and be printed as "the ask now". The supplied entry assumption does not make the quote, future or model inputs current.

Required fix: use an explicit freshness/availability result with required aware timestamps and bounded clock-skew tolerance. Treat missing/unparseable times as unverified, material future times as invalid, and keep unknown distinct from genuinely stale. Apply validation to the option and future inputs, independently of whether entry price was typed. A useful conditional check can still state the user's assumed price and arithmetic; unavailable live spread, model level or account data must be labelled unavailable, not invented or presented as current.

Acceptance: missing/malformed/naive/future timestamps, receipt and exchange-age boundaries, stale option versus stale future, supplied versus fetched entry price, closed session and incomplete quotes. Update test fixtures to contain valid clocks rather than weakening checks to preserve old fixture expectations.

### R3 — P2: failed 07:00 partner reminder suppresses every later attempt that day

Files/contracts: `python-engine/partner_broker_sync.py:1175`, `partner_orchestrator._seen/_record`, scheduler job `premarket_login_nudge`.

The reminder records a row even when delivery failed. `_seen` treats any row as already reminded. Reproduction: fake `unsent_connect`, invoke again 20 seconds later; result is `already_reminded`, with only one send attempt and delivered=0. There is also no dedicated retry job. The existing 09:00 watch prompt provides another login opportunity but does not repair the promised 07:00 delivery.

Required fix: retain bounded per-attempt state including delivered, unsent, ambiguous and terminal outcomes. Retry only provably unsent/retryable failures inside a short morning window; do not resend a potentially delivered timeout. Stop after successful acknowledgement, successful login or expiry. Do not change `_seen` globally: other message types depend on its current contract. Review brief/EOD/coach uses separately, because they use the same attempted-versus-delivered pattern.

Acceptance: unsent then success, timeout ambiguity, duplicate cron/invocation, restart, login before retry, disabled/unconfigured bot, closed day and attempts/time cap. Preserve separate login links and owner/partner failure isolation. Owner reminder acknowledgement currently means gateway acceptance, not necessarily Telegram receipt; improve that observability without claiming exactly-once delivery.

## What the partner system currently contains

| Surface | Current behavior | Important limit |
| --- | --- | --- |
| Login | 07:00 trading-day reminder with their own Kite link; 09:00 watch prompt when not connected; reconnect message after restart | Login is manual; the partner session is kept in memory. R3 remains open. |
| Market context | 09:50 brief and 15:50 wrap: NIFTY/SENSEX context, premium conditions, direction/levels and available card outcomes | Depends on current inputs/owner login. Context can coexist with advice; legacy noisy intraday alerts are suppressed by policy. |
| New ideas | NIFTY/SENSEX buyer-oriented manual cards: exact option/expiry, bounded entry, stop/invalidation, modeled target, costs and validity; lifecycle target/invalidation/exit reminders | Signal- and input-dependent, not guaranteed daily. Caps default to two new ideas and four material management updates. |
| Ask before purchase | In the same partner Telegram chat, `check 22300 pe`, `chk nifty 22300pe 75.5 x2`, or `check sensex 81000 ce 120 2 lots` | NIFTY defaults when omitted; nearest available expiry and one lot default. Explicit expiry selection is not implemented. It is a hypothetical check, never a recorded fill or trade approval. R1/R2 remain open. |
| Watch after buying | Reads actual orders/fills and reconciles quantities with positions; calculates a plan and estimates loss after charges; records later size/plan versions | Current focus is long option positions. These are modeled reference levels, not guaranteed fills or loss limits. |
| Protection alarms | Missing/partial/cancelled/lowered stops, triggered but unfilled exits, broker refusal, excessive/orphan/wrong-product sell orders, blind/recovered account reads and close warning | Five-second polling is the default cadence, not a guaranteed delivery bound. Reads, model work and Telegram add latency. Stops can trigger without filling. |
| Quiet mode | Mutes routine PLAN/ADDED/NO_STOP/PARTIAL/CLOSE messages | Urgent protection/order/read-failure alarms and requested CHECK replies remain on. |
| Evening learning | Actual broker fills, orders and changes feed trade-by-trade review, costs, behavior/stop observations, daily lesson/progress and PDF review | Incomplete days or price paths cannot support precise counterfactual savings/profit claims. |
| Order stream | Implemented order-update wake-up with REST reconciliation and polling fallback | Production PARTNER_WATCH_STREAM_ENABLED=false; not live-verified. It does not subscribe to price/depth packets. |
| Trading judgment | Quote paths are intended to support testing profit protection, trailing, thesis failure and holding winners | No active promise of optimal profit-taking/trailing. Those judgment messages await evidence/scoring. |
| Portfolio hedging | Separate input/reconciliation-dependent capability | PARTNER_HEDGE_ENABLED=true but input refresh=false. A flag does not establish a current reconciled portfolio or active personalized hedge coverage. |

Every partner trade is still placed/modified/cancelled by the partner in Zerodha. "Ask before purchase" does not ask the owner to approve the partner's buy. It is optional decision support for a human trader, including their own ideas.

Current evidence: watch_messages=0, watch_looks=0, trade_reports=24 (latest broker day Oct 23), strategy qualifications=0, saved advisory profiles=1. Historical brief/EOD/coach/signal delivery rows exist, but they do not prove that the newly deployed watch/CHECK worked live. Latest saved NIFTY/SENSEX input status is Oct 23, NO_ENTRY_SETUP/not_fresh_break. Historical rejected/expired cards must not be mistaken for currently deliverable ideas.

Importantly, Production has PARTNER_MANUAL_ADVISORY_SEND_UNQUALIFIED=true and delivery=true. Missing qualification alone therefore does not block the owner-authorized NOT CHECKED advice path. Such cards must retain their explicit unqualified label; all price/profile/entry-window/liquidity/delivery checks still apply. Do not promise qualified or profitable tips, and do not manufacture qualification from elapsed days.

## Concrete next implementation order

1. **Repair delivery evidence and freshness first (R1/R2/R3).** Three independently reviewable slices with adversarial tests, updated guide/plan and normal GitHub promotion. Paper admission preferences and all real-order authority stay unchanged. Roll back each slice independently; do not disable existing exit/protection alarms.
2. **Verify the first real partner session.** After both morning logins, collect readiness, book reconciliation, message outcomes and event-to-detection-to-acknowledgement timing. Compare the day's orders/positions to what the watch saw. Do not place an unnecessary real trade merely to test. Use a genuine manual trade or a clearly labelled owner-authorized non-trading transport check. Acceptance is persisted evidence of actual delivery and no stale/superseded action, not just enabled flags.
3. **Activate the existing order stream only after entitlement/live verification.** Verify the partner's paid plan, current token, LIVE state and observed updates from manual Kite activity; preserve REST polling/reconciliation through disconnects, duplicates and out-of-order frames. Rollback is stream off, polling retained. Kite specifically recommends WebSocket order updates for orders placed manually on web/mobile; app webhook postbacks alone are not equivalent coverage. [Official order-update scope](https://kite.trade/docs/connect/v3/postbacks/).
4. **Add bounded market-data streaming for what matters.** Subscribe only to held/checked/advised options and their relevant futures/indices; consume full bid/ask depth, quote clocks and sizes into a freshness-aware cache. Resubscribe on reconnect and expire stale data; preserve a bounded REST fallback and protect the owner's exit-data priority. The current stream drops binary quote frames, so merely enabling it will not deliver this enhancement. [Official stream/depth contract](https://kite.trade/docs/connect/v3/websocket/).
5. **Improve pre-buy decisions without a blanket veto.** Explicit expiry, parsed-request confirmation, timestamp and validity, assumed price versus executable ask, spread/depth for the requested lots, existing same-direction exposure and incremental loss if adding. Offer short reasoned scenarios such as entry now versus waiting for a pullback/retest, including the possibility of missing a strong move. Present uncertainty and unavailable evidence. Persist request/response-to-later-fill linkage without pretending the question was a purchase or that the response caused it.
6. **Build and score actual entry/exit judgment.** Freeze alternatives before scoring: hold through normal pullback, trail after progress, exit on thesis failure, time-based exit and partial profit-taking where quantity allows. Use the same observed paths and manual reaction delay, executable depth, charges and slippage; compare against the unchanged baseline on held-out sessions. Score gains retained and strong trades missed alongside losses avoided. Report coverage, drawdown, tail loss, sample size and dependence on the best winner; no arbitrary twenty-trade threshold proves an edge. Only promote supported messages, with reasons and invalidation, after an operator-reviewed result. The present evidence has no watch paths, so this learning has not already happened.
7. **Make learning visible and honest.** One concise action/reason/rupee-impact message with last-update time; a per-trade timeline of what changed; review actual fills separately from modeled alternatives. Track whether advice arrived before action, and distinguish followed/ignored/unknown without blaming a trade's result on compliance. Show a readiness page for login, latest book, market feed, delivery, qualification and disabled features. Keep urgent notifications as new alerts; an edit alone may not notify the reader.
8. **Schedule the upcoming exchange-calendar change before December 7.** Current 15:40 derivative session support agrees with today's published timings. New rules announced October 15 change the session from December 7: normal F&O to 15:45, expiring index contracts to 15:30 on expiry day, and changes to CAS/settlement. Implement an effective-date/exchange/contract-aware session policy across execution gates, expiry clocks, watch warnings, historical replay and EOD completeness. Preserve October/November and older replay semantics rather than globally changing a constant. Boundary tests must cover Dec 4 versus Dec 7, expiring/non-expiring contracts and the later February 2027 order-transition rules. [Broker bulletin](https://zerodha.com/marketintel/bulletin/461085/changes-to-closing-auction-session-cas-from-december-7-2026), [SEBI circular](https://www.sebi.gov.in/legal/circulars/oct-2026/review-of-certain-aspects-of-the-closing-auction-session-market-timings-and-settlement-methodology-for-derivatives-contracts_105293.html).

Known infrastructure limit: broker credentials are protected by TLS to Kite, but the direct CONNECT proxy password itself travels outside TLS. The runbook already discloses this. A later TLS-protected proxy/transport or suitably restricted network path would improve it; avoid silently switching to a desktop-session-dependent fallback or retiring the old route before the replacement is verified.

## Verification and remaining work

- Independent focused suite A: login reminder, daily bootstrap, watch, order stream, broker sync, fill capture and scheduler surface: **183 passed**, two warnings, 30.08s.
- Independent focused suite B: manual advisory/orchestration, buyer, coach, lessons, insights, stop reading, bot, renderer, decision clock, delivery blockers, live-test/preflight and endpoint probe: **307 passed**, two warnings, 23.54s.
- Four isolated fake-data reproductions: **4 passed by reproducing the existing defects**, not by fixing them. Cases: unsent reminder suppressed; unchanged CHECK retry after 30s; missing/future quote clocks accepted; supplied entry price with known ten-minute stale market quote still producing ask-now/stop text. Evidence script: `C:/Users/Urveesh/sentinel-operations/independent-review-20261025/test_audit_reproductions.py`. Temporary databases and fake senders only; no broker/Telegram network calls.
- Existing full-suite O25k receipt remains the developer's 6,015 passed/4 skipped. This review did not rerun that full suite or infer its passing result proves the missing edge cases.
- No source/schema/configuration change in this review, so no atlas regeneration or deployment was needed. Review documents/plan only in Dev; running Production remains `7468853`. Remediation and its regression coverage are still to be implemented.
