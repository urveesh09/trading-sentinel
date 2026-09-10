# Hedge remediation review and next implementation plan

Date: 6 September 2026 (IST). Reviewed application commit: `ea77517`; checkout: `c96345f` on `codex/production-correction-hedge-p0`. The later commit adds documentation. This review includes two small, uncommitted Dev corrections described below.

## Verdict

The remediation substantially meets the previous audit's immediate code objectives, but does **not** yet meet production delivery expectations. Passing tests establish useful regression coverage; they do not establish a working account adapter, safe recovery under every failure, or restored partner delivery. Keep hedging the highest partner priority, with advanced strategies in shadow until their evidence gates are satisfied.

The valid Phase-1 string handling, transactional position reconciliation, envelope ordering, partial-snapshot gating, and malformed live-balance rejection are meaningful corrections. The most consequential remaining work is account isolation and a recovery path that revalidates the advice it is about to send.

Production was inspected only for Git identity/status: HEAD `89926fb`, pre-existing untracked `migration/`. No Production files, configuration, processes, broker orders, or Telegram messages were changed. This is a code/remediation review, not a fresh live-run assessment. The earlier September-2 delivery outage diagnosis remains historical evidence; this review does not claim messages have resumed.

## Verification performed

- Before edits: 141 selected Python tests passed.
- After edits: the same selection plus two regression tests passed: **143 passed**, one existing Starlette lifespan deprecation warning.
- Gateway executor: **46 passed**.
- Reviewed changes in snapshot normalization/transactions, whole-portfolio gates, proposal identity, claims/recovery, transport classifications, and Phase-2/3 delivery call sites.
- These are selected suites, not the entire repository or a repeat of every test count in the implementation report. No live canary was attempted.

Python selection: `test_hedge_advisory`, `test_hedge_analytics`, `test_hedge_strategies`, `test_hedge_formatters`, `test_hedge_phase3`, `test_hedge_readiness`, `test_hedge_routes`, `test_partner_bot`, `test_partner_input_refresh`, `test_scheduler_closures_invoke`, and `test_main_surface_characterization` under `python-engine/tests`. Gateway command: `npm test -- --runInBand tests/unit/executor.test.js` from `node-gateway/server`.

## Corrections made during this review

### 1. Preserve timeout truth before updating status summaries

In `hedge_advisory.py::_send_claimed_review`, unsuccessful transport results previously updated `last_attempted_send` before recording the authoritative failed claim. If that ancillary write raised after `ambiguous_timeout`, the outer exception handler recorded `internal_error`; that turned uncertain remote delivery into an automatic retry candidate.

The authoritative claim now records the transport result first. A later status-summary failure is logged without changing delivery eligibility. The new regression injects a Telegram timeout and a status-write failure, calls the send path again five minutes later, and verifies exactly one mocked transport call.

This fixes this failure ordering only. It does not solve process death between remote acceptance and a durable local acknowledgement, or total ledger write failure; those remain explicit work below.

### 2. Respect the hedge kill switch during scheduled recovery

`recover_pending_hedge_deliveries` now checks both hedge enablement and partner transport availability before accessing the ledger. Previously recovery did not check hedge enablement. The new regression disables hedging and verifies recovery exits before ledger access.

This does not yet implement phase-specific readiness, trading-session, fresh-portfolio, or message-cap checks during recovery.

## Remaining correction packages, in implementation order

### P0 — Account ownership must exist below the envelope

Evidence: `partner_input_refresh.py::_normalise_snapshot` enforces expected source/account only when configured. `hedge_analytics.py::apply_partner_snapshot_transaction` checks position ownership by `source`, and complete snapshots close all open rows for that source. Position ownership is not account-scoped, although watermarks are keyed by `(source, account_id)`. `load_latest_partner_snapshot` chooses the most recently accepted envelope globally.

Consequence: absent fixed bindings, a second account using the same source can submit a complete empty snapshot that closes the first account's rows. Separately reading positions, reconciled positions, and the latest envelope can also combine different committed versions if a refresh occurs between reads. Writer atomicity alone does not make these separate reader connections atomic.

Implement either a deliberately single-account service with mandatory, immutable approved account/source binding at every mutation entry point, or account-scoped position ownership and queries throughout. The former is the smaller near-term change. Do not imply multi-account support from envelope fields alone. Read envelope and portfolio rows from one database read transaction and return a versioned evaluation input object.

Acceptance: account B cannot update or close account A's rows; missing/mismatched binding fails before mutation; two concurrent accepted refreshes cannot produce mixed-version advice; switching configured account requires an explicit migration rather than inheriting old positions. Test direct transaction entry as well as the HTTP adapter wrapper.

### P0 — Recovery must revalidate, not just replay rendered text

Evidence: `recover_pending_hedge_deliveries` reads `rendered_text` and calls `_send_claimed_review` without the original `min_gap` or `daily_cap`. Phase-2/3 caller details contain neither `valid_until` nor a persisted phase/readiness policy. Recovery checks neither current portfolio identity nor current phase readiness. The new master-switch guard is only a first correction.

Consequence: a queued advanced strategy can be delivered after its phase is disabled, after holdings close, after daily caps are reached, or after its original market context becomes stale. Phase-1 expiry protects some cases, but a portfolio can change before quote expiry.

Persist phase, account, snapshot/economic version, creation time, expiry, and policy version for every actionable proposal. Recovery should invoke the same policy evaluator as initial delivery: account binding, current complete portfolio, current phase readiness, trading calendar/session, quote validity, current economic relevance, and rate/cap limits. Retire superseded advice and rebuild from fresh data. Give morning/EOD summaries separate expiry semantics rather than borrowing an intraday quote rule.

Acceptance matrix: queued advice then account closure; partial refresh; phase disabled; readiness revoked; holiday; cap exhausted; newer proposal accepted; quote expired; and HTTP 429 beyond validity. Each must make zero transport calls or regenerate an explicitly new eligible proposal. One malformed ledger row must not prevent later valid rows from being processed.

### P0 — Treat uncertain sends and crash recovery conservatively

Evidence: `partner_bot.py` treats only `httpx.TimeoutException` as ambiguous; other transport exceptions become `network_error`, which the claim layer retries. A connection/read failure can happen after a request reached Telegram. A claimed row becomes reclaimable after its lease, without durable proof that transport never started. If both acknowledgement persistence and recovery-marker persistence fail, the outer handler can still record an ordinary internal failure.

Implement durable send-intent/transport-started state. Automatically retry only failures demonstrably preceding dispatch or explicit rate-limit rejection. Lost responses, post-dispatch disconnects, and abandoned in-flight claims should require delivery reconciliation/manual resolution. Document the tradeoff: Telegram sendMessage has no application-supplied idempotency key that makes arbitrary replay exactly once.

Acceptance: process crash immediately before POST and immediately after remote acceptance; read disconnect; acknowledgement DB failure plus fallback DB failure; expired lease with unknown transport outcome. Verify no blind resend. Add an operator recovery procedure that records who resolved ambiguity and on what evidence.

### P1 — Make proposal identity represent a decision

Evidence: `_proposal_identity` removes refresh timestamps, but still includes exact current prices, underlying prices, and Greeks. Ordinary mark movement therefore creates a different key even if recommended contracts and quantities are unchanged. Leg identity omits explicit side and lot size.

Separate an observation/evidence hash from a decision identity. Include action, side, instrument/expiry, units, account and exposure intent in decision identity. Use tested exposure/cost bands and hysteresis for material-change notifications, plus a supersession link. Keep every observation for audit without treating every observation as new advice.

Acceptance: identical decision across minor mark/Greek changes yields one notification; action reversal, lot-size correction or meaningful hedge-size change yields a new decision; a later legitimate re-entry has a new lifecycle identity. Measure duplicates per economic decision, not just duplicate database keys.

### P1 — Complete the real adapter lifecycle

The importer still resolves existing internal position IDs and rejects unknown IDs/reopening closed records. This is acceptable as an explicit first-stage reconciliation contract, but it is not a complete holdings producer. A configured URL alone will not maintain new purchases, reopened positions, corporate actions, and instrument mapping.

Define authoritative holdings/positions coverage, stable external identity, lot/unit conversion, lifecycle IDs, and instrument resolution. Validate marks and Greeks with independent observation timestamps. Reject inappropriate future timestamps and stale inputs explicitly, including VIX; a fresh envelope must not make old market data fresh. Require the dedicated token and approved source/account before enabling scheduled refresh. Never print credentials in audit artifacts.

Acceptance: new position; full close; subsequent re-entry; duplicate upstream row; corporate-action quantity change; missing Greeks; future mark/VIX timestamp; omitted coverage; adapter outage. Expose a truthful unavailable/partial state rather than an empty healthy account.

### P1 — Prove recovery operationally before promotion

Create an offline integration fixture that runs snapshot acceptance, real review construction, mocked delivery, recovery and next-refresh supersession together. Existing unit tests exercise valuable pieces but miss cross-stage policies. Record snapshot ID, decision ID, transport attempt, result, expiry and retirement reason in one trace.

Then promote through the normal GitHub workflow, provision the approved adapter/account mapping, and perform the explicitly authorized partner canary. Require evidence of intended recipient mapping, one acknowledgement, healthy recurring refresh, correct no-advice reporting, and working kill switches. A scheduler firing successfully is not evidence that the partner received useful advice.

## Ten improvement experiments for better net outcomes

These are proposed experiments, not proven profitable changes. The primary objective is net portfolio outcome after premium, transaction costs, slippage and capital usage, with drawdown constraints. More hedge messages and more trades are not success metrics. Keep existing directional partner suppression while building hedge usefulness.

| # | Improvement and mechanism | Implementation and validation | Promotion criterion / failure risk |
|---|---|---|---|
| 1 | Rank messages by incremental risk reduction. Send urgent protection changes before routine market commentary. | Calculate portfolio loss under common stress scenarios before/after each feasible hedge; queue by risk reduction, time sensitivity and confidence. Replay historical message windows. | Less time with material uncommunicated risk at the same message budget; avoid false precision in stress estimates. |
| 2 | Compare put, collar, partial reduction and no change on one decision card. | Show premium, residual downside, capped upside, margin and liquidity for equivalent exposure. Use actual instrument settlement rules and executable quotes. | Better out-of-sample cost/risk tradeoffs; a collar can sacrifice upside and should never be marketed as free protection. |
| 3 | Allocate an explicit protection budget. | Set a user-selected monthly/annual premium budget; track consumed premium and remaining protection. Optimize scenarios within that constraint. | Lower protection drag for the same downside target; a budget must not hide a breach of the user's maximum risk. |
| 4 | Use no-action bands to reduce unnecessary hedge turnover. | Recompute exposure frequently but notify/adjust only outside calibrated bands, with a separate urgent-risk override. | Lower net costs without worse tail losses; wide bands can leave risk unhedged during fast moves. |
| 5 | Measure partner execution delay. | Associate advice with a decision ID, validity window and optional acknowledgement/execution record. Revalue at realistic delay intervals in replay. | Advice retains value at observed partner response times; never count Telegram acknowledgement as trade execution. |
| 6 | Add portfolio proxy-quality scoring. | Estimate rolling and stressed tracking error when index options hedge a stock portfolio; flag concentrated sector/idiosyncratic risk. | Lower residual portfolio loss in held-out stress windows; stable historical beta is not guaranteed in a shock. |
| 7 | Plan hedge expiries against exposure horizon. | Compare expiry ladders and roll dates with expected holding period and event calendar; include bid/ask and roll costs. | Fewer unprotected gaps and lower all-in carry; avoid optimizing on settlement prices unavailable at decision time. |
| 8 | Make capital efficiency a selection input. | Compare broker-estimated basket margin and charges with stress liquidity reserves before recommending feasible alternatives. Save both estimate and later realized usage. | Lower capital consumed per unit of protection without increased short-leg risk; estimated margin can change. |
| 9 | Maintain a counterfactual outcome ledger. | Track unhedged baseline, recommended hedge, and confirmed executed hedge separately, including premium, fees, slippage and missed execution. | Explain where net value came from and retire negative-value policies; do not attribute market gains to the hedge. |
| 10 | Promote strategy challengers using time-separated evidence. | Freeze baseline and challenger rules, use chronological training/validation/test windows, realistic spreads and portfolio constraints, then shadow forward. Track all attempted variants. | Improvement survives costs and adverse regimes with tolerable drawdown; reject gains confined to one tuned period. |

Supporting references: [OIC collar explanation](https://prd-web.optionseducation.org/strategies/all-strategies/collar-protective-collar) explains the protection/cost/upside tradeoff; it is general options education, not an India-specific execution specification. [Kite margin calculation documentation](https://kite.trade/docs/connect/v3/margins/) supplies broker order/basket margin and charge interfaces. These sources support mechanics, not a claim that any experiment will earn more profit. The experiments and acceptance criteria above are engineering proposals from this review.

## Next work order

1. Review the two small Dev fixes and retain their regression tests.
2. Implement account isolation and consistent versioned reads.
3. Unify initial-send and recovery policy, then harden uncertain/crashed transport handling.
4. Complete the adapter lifecycle and decision identity; run the cross-stage offline matrix.
5. Establish the counterfactual ledger and risk-prioritized partner card before adding strategy complexity.
6. Promote through GitHub only after the release gates pass. Configure external prerequisites and conduct the separately authorized live canary.

The remaining packages are a correction plan, not implemented changes. The two small fixes in this review are uncommitted Dev changes. Production delivery restoration and profitability remain unverified.
