# NIFTY/SENSEX partner rollout audit and next implementation

Date: 8 September 2026. Dev reviewed: `e930968`, following `c6afd2f`.
Objective: useful, timely manual-trader advice with sound economics, not portfolio logs or partner order monitoring.

## Verdict for the owner

The independent advisory foundation is useful progress, but **this enabled release is not yet ready to be relied on for substantial-capital decisions**. Existing tests pass, yet an offline probe accepts a spread with a negative maximum expiry profit. Other quality and delivery gates are incomplete.

Do not treat the current enabled defaults as proof of readiness. Correct the release blockers below before promoting or relying on actionable delivery. This audit does not change switches, deploy code, revoke prior rollout authorization, place orders or send messages. The owner already authorised advisory delivery; the remaining requirement is to make that authorised implementation correct.

The desired service remains NIFTY 50/NSE and SENSEX/BSE advisory only. No partner order API, broker monitoring, portfolio upload or Taken/Skipped feedback is required for standalone ideas or their public-condition updates. Optional feedback is optional. Unknown holdings must never be assumed. Critical follow-ups should say “If you took idea X…” where appropriate.

No engineering review can establish future profit. The specific present goal is to prevent economically invalid advice and improve evidence, timing, selection and management so a partner has a more useful decision aid.

## 1. Verification and evidence

- Reviewed both commits, `partner_manual_advisory.py`, the new orchestrator consumer, dispatch authorization, profile/card persistence, config, quote timestamp parsing and relevant tests.
- Reran the developer's listed nine Python test modules: **150 passed**, one existing deprecation warning. This differs from the reported 131; it is the independently observed count for the command used here.
- Added offline probes and rendered a synthetic card in [review-2026-09-08-partner](review-2026-09-08-partner/audit_probes.py). These import the existing test fixture and never call transport. [Synthetic card](review-2026-09-08-partner/sample-card.txt) is defect evidence, not a trade recommendation or actual partner message.
- Production working copy still reports `2c87ecd`. `docker ps` returned no running containers; today's queried advisory logs returned no records. Therefore this review cannot certify deployment, effective runtime flags or a message delivered today. It is primarily a Dev release review; yesterday's three status messages remain covered by the previous audit.

### Confirmed offline probe results

| Probe | Actual result | Required behaviour |
|---|---|---|
| Existing synthetic NIFTY fixture: 50-point width, 75 units, 53-point debit | ₹3,975 debit against maximum ₹3,750 expiry payout; maximum profit **−₹225 before ₹121.25 estimated costs**; validator returns valid | Reject an impossible positive-return structure |
| One displayed unit on each executable side | Valid for a full-lot card | Depth must cover the advertised ratio × lot quantity, or output must not claim that size is executable |
| Replace two-leg candidate with one leg while retaining claimed spread economics | Valid | Recompute and reject inconsistent structure/payoff |
| `RESEARCH_ONLY` candidate persisted with delivery requested | `delivery_eligible=True` | Research state cannot become actionable authority merely because a rollout flag is on |
| Profile permits no structures, has ₹1 risk limit and a delivery window outside test time | Still delivery-eligible | Enforce the configured profile or explicitly reject unsupported preferences |

These are reproducible software findings, not evidence that the partner received these particular defective cards. The first fixture uses synthetic contract identifiers and historical example lot sizes; do not interpret it as current exchange metadata.

## 2. What is implemented correctly, and where expectations exceed it

The code separates market advice from Sentinel cash and partner holdings, recognises NSE/NFO versus BSE/BFO, builds debit spreads from asks/bids, retains explicit advice IDs, has plain-text bounded cards, exposes authenticated APIs, and reuses durable transport claim/acknowledgement/ambiguity machinery. It correctly avoids treating Telegram acknowledgement as a broker fill. No partner order consumer was added.

However, today's scheduled consumer produces **only directional debit spreads from the existing signal scan**. The conditional protective-put builder is not scheduled as a delivered category. No futures-advice consumer, contextual morning brief, thesis-level invalidation/update service or useful position-independent management lifecycle was found in this new path. Therefore it is not yet the full hedge-first “help at critical times” product.

The current card says only “LONG signal on completed bar” and “same-expiry capped-risk vertical.” It does not carry the actual trigger price, underlying invalidation level, support/resistance context, signal timestamp/timeframe, event context, profit-taking policy or mandatory time exit. “Recheck both legs before entry” is execution caution, not trade management. The spread's capped payoff alone does not establish an edge.

## 3. Release-blocking corrections

### R1 — Independent economic and structural validation

Location: `partner_manual_advisory.validate_candidate`, `build_directional_debit_spread`, `fno_defined_risk.build_debit_spread`.

For a same-expiry equal-ratio vertical with width W, lot quantity Q and net debit D per unit, expiry maximum gain before costs is `(W − D) × Q`. Reject D ≤ 0, D ≥ W, and non-positive maximum gain after conservative costs. A higher maximum-gain/risk ratio is still not expected return.

Recompute from legs, not supplied `max_profit_rs`/`max_loss_rs`: required leg count, BUY/SELL pairing, same option type, correct strike ordering for direction, matched expiry/underlying/segment, positive integral ratios/lots, current metadata binding and finite numeric values. Enforce tick compatibility. Reconcile displayed debit, bounds and breakevens to recomputation within rounding tolerance. Validate costs as finite/non-negative and state whether every displayed bound includes them.

Reject NaN/infinity/negative sizes and wrong leg identities. Preserve the shared builder's existing consumers by running its broader F&O regression suite if modified. Use a separately implemented payoff grid oracle; calling the same production helper twice is not independent verification.

Acceptance: both indices, both directions, profitable geometry, debit equal/exceeding width, cost-erased reward, malformed one-leg/duplicate-leg/ratio cases, all terminal price regions. Convert the current synthetic fixture into a rejection test and add realistic valid fixtures.

### R2 — Evidence and profile gates must actually govern delivery

Location: `persist_candidate`, orchestrator, manual branch of `_authorize_dispatch`.

The orchestrator explicitly creates `RESEARCH_ONLY` candidates and queues them under the delivery flag. The persistence docstring claims research-only evidence is not delivery-eligible, but there is no such condition. Implement a versioned strategy qualification registry with policy, index, horizon, dataset and review evidence. `RESEARCH_ONLY`/`UNVALIDATED` can remain previews. Do not fix this by hard-coding `QUALIFIED_FOR_ADVISORY` instead.

Profile enforcement currently checks only scope/instrument permission at persistence. Enforce permitted structures, window, supported timezone/holding horizon and any provided capital/risk constraints; keep unknown personal quantity absent. `shadow_enabled=True` combined with main enabled=False must never be enough to send just because delivery_enabled remains True. Define one explicit actionability predicate and reuse it in scan, persistence, recovery and final authorization. Reject malformed/non-finite profiles.

Bind cards to profile ID and version throughout. The schema has version but no dedicated profile-ID column, and profile supersession updates all matching lower-version cards. Same-version foreign profiles must not authorise each other's cards. Use atomic profile validation/supersession and a documented default-profile identity.

Acceptance: every switch combination, all evidence states, all profile limits and cross-profile identities; profile changes between enqueue and dispatch; no false personal sizing.

### R3 — Actual pre-send time and executable quote evidence

The scan captures `now` once before sequential market work and passes it through persistence, claim and final authorization. The final manual branch compares stored expiry against that old value rather than a fresh wall clock. A slow second-index scan or database wait can therefore consume a 30-second validity window without the gate noticing.

Use an injectable fresh clock at the final boundary; record scan-start, quote provider time, response receipt, validation and transport-start separately. Re-fetch/revalidate quotes and the source signal if necessary, or retire the card if it cannot be sent within its genuine validity. Check all enable flags, profile/evidence revisions and session/calendar at final dispatch, not only stored empty `validation_reasons`.

`_quote_time` uses last-trade time, falling back to snapshot `taken_at`; the chain stamps `taken_at` from the caller's scan clock. Last-trade time is not a depth-quote timestamp. A missing quote timestamp cannot silently become fresh because a request was made. Parse provider quote timestamps, distinguish provider and receive clocks, and document conservative treatment when provider provenance is unavailable. Preserve usable quotes with older last-trade times when actual depth freshness is established.

Acceptance: fake-clock slow scans, 31+ second DB delay, profile revision during dispatch, missing provider timestamp, old last trade with fresh depth, actual stale depth, future timestamp and 429/recovery. Assert zero transport calls after expiry. Avoid broad claim that SQLite can atomically transact with Telegram; preserve uncertainty at that boundary.

### R4 — Full-lot liquidity, valid-before-ranking and expiry routing

Current minimum OI, volume and displayed depth default to 1; spread threshold is 15%. These defaults do not demonstrate executable capacity for even one lot, much less substantial size. Depth validation must require units covering lot × ratio and distinguish quoted from sustainable size. Keep liquidity/cost thresholds configurable and calibrate separately for each index/expiry. Show one-structure economics; never imply unlimited scalable capacity.

Current overlap selection runs **before** candidate validation. An invalid high-ranked candidate can suppress a valid alternative. Validate first, persist all rejections, then rank eligible candidates. Reassess overlap against active delivered theses, not just the two candidates in the current tick.

The shared chain chooses the nearest expiry including today; the new builder rejects today but does not choose the next eligible expiry. On expiry days this can remove all new advice for that index despite a valid later contract. Add an advisory-specific expiry resolver selecting the next *qualified* eligible contract; never enable same-day-expiry advice as a shortcut. Keep main trading expiry behaviour unchanged.

Acceptance: unavailable SENSEX never blocks valid NIFTY and vice versa; invalid preferred candidate cannot suppress a valid alternative; expiry-day next-contract selection; no incorrect cross-exchange substitution; full-lot depth and stressed slippage cases.

### R5 — Coherent immutable card generations and final persistence truth

`advisory_id` is stable for a thesis, while `economic_version` includes quotes and all leg fields. `persist_candidate` conflicts on advisory ID by updating **only updated_at**, but returns the newly rendered status/card as if it were stored. A rejected first version cannot become a valid new generation, and changed-price retries can return text that does not match the DB; final authorization then blocks it. Supersession searches the same economic version rather than the stable thesis, so changed economics do not establish the intended chain.

Separate stable thesis/decision identity from immutable economic version and expiring delivery generation. Include profile scope; preserve acknowledged/ambiguous generation terminality. Same input is idempotent; materially changed economics creates a linked new generation; routine timestamps do not fabricate a new thesis. Return the authoritative committed record. Persist reasoned expiry/retirement and retain active-thesis observation independently of entry-card TTL.

Acceptance: rejected→valid fresh quote; unacknowledged refresh; acknowledged refresh with no duplicate tip; profile change; conflict between workers; generation expiry; real rendering equals final stored payload. Keep existing durable transport protections intact.

### R6 — Release documentation and effective configuration

The implementation document first says delivery is enabled, then says no live delivery consumer was added. Orchestrator docstrings also still say “never sends.” Correct these contradictions. Record the precise configuration truth table and environment precedence: changing code defaults does not override an existing Production environment value.

Prepare a read-only effective-settings report that exposes only booleans, policy versions, feed readiness and masked destination—not secrets. Verify the deployed image SHA separately from working-copy SHA. Include registered scheduler/authenticated API/card evidence with safe transport doubles. Do not broadly switch on unrelated trading/research modes just to make this feed active.

## 4. Making the advice useful at critical moments

These are the next product increments after/alongside the blockers, not promises of profitable signals.

### E1 — Carry the actual decision thesis into the card

Persist signal bar/timeframe, trigger/confirmation level, spot versus futures reference, underlying price when evaluated, invalidation, target zones, expected holding horizon, volatility/regime and concise contrary evidence. The partner must know “why now” and “what would make this wrong.” Use only available point-in-time data; do not add unsupported confidence percentages.

Evaluate trend continuation/retest and failed-break scenarios using the existing signal research. A debit spread should not be recommended merely because a directional boolean is non-null. Compare entry distance to invalidation and executable spread economics after costs; never chase a move that has already consumed the expected reward.

### E2 — Protection ideas as a genuine second category

The current sender is directional spreads only. Integrate conditional protection for explicitly stated NIFTY/SENSEX exposure assumptions, with premium cost, protection range, horizon and residual risk. Prefer same-index constructions initially; cross-index hedging remains out of scope. Do not invent partner holdings or require them for generic conditional cards.

Neutral premium strategies and futures ideas are separate policy families needing their own validation. Futures cards must explain notional/margin and gap loss; a stop does not turn them into bounded-risk positions. Do not add families solely to make a quiet market generate messages.

### E3 — Useful management and invalidation without tracking orders

Observe published ideas against market conditions, not the partner's broker account. For each published thesis, define numeric/time management rules, a time stop and the session/expiry deadline. Send material invalidation, target-zone or changed-risk updates with the original idea ID and conditional wording. No mandatory Taken/Skipped loop.

Entry quote TTL and idea horizon are separate: 30 seconds may describe a quote's usable age, not the duration of the trading thesis. A manual recipient needs time to read and verify. Keep a trigger/limit-based setup valid only under clearly defined conditions, refresh executable evidence before send and never lengthen quote freshness to manufacture usability. Measure delivery-to-expiry time as part of acceptance.

### E4 — Priority budget for opportunities and urgent changes

Two first-entry ideas per day can be a starting anti-noise limit, but it must not consume the capacity for a later critical invalidation. Create separate categories for new ideas and material updates, respecting destination rate limits and duplicate suppression.

The current cap counts acknowledged rows; in-flight/ambiguous deliveries are not reserved against it. Add transactional quota reservations and explicit ambiguous-consumption semantics so concurrent unique claims cannot exceed the intended limit. Do not market this as exactly-once delivery.

Rank qualified ideas by evidence-supported expected net value, execution quality, horizon and uncertainty. Current maximum-payoff/risk ranking is not expectancy and its numerator does not deduct costs. Compare NIFTY versus SENSEX as alternative expressions of the thesis, not diversification. Reserve urgency for material changes rather than labelling every card urgent.

### E5 — Evidence that measures edge rather than attractive cards

Build a per-index, per-policy advisory outcome archive using the exact sent generation, realistic entry delay, ask/bid fills, costs and all no-fill/expired/rejected cases. Report hypothetical model outcomes separately from any voluntarily reported actual trades. No partner P&L claim from Telegram delivery.

Compare existing next-open/limit/confirmation entry and bounded exit challengers on frozen chronological folds. Include ordinary and event/expiry-adjacent sessions, uncertainty, drawdown, losing streaks, slippage sensitivity and execution capacity. Do not select on win rate or a few favourable examples. Reuse the W-series infrastructure but independently establish that it is integrated with this advisory consumer.

### E6 — Concise market preparation and silence diagnosis

Give an optional useful NIFTY/SENSEX preparation card: directional/range context, levels that matter, event time/source, preferred conditional playbook, and when to stand aside. After-market review should explain published ideas and lessons, not portfolio SQL states.

The current metrics aggregate both indices and classify absent directional signals as unavailable. Separate healthy-no-setup, missing/stale data, unsuitable economics, profile/evidence rejection, overlap suppression, throttled, expired-before-send and delivery ambiguity per index. Critical-time silence must be diagnosable without encouraging forced trades.

## 5. Precise developer sequence and completion gates

| Stage | Work | Acceptance |
|---|---|---|
| A: release blockers | R1/R2/R3 plus R4 validation order/depth | All five probe behaviours reversed; real-clock expiry/profile/evidence tests; current 150-test regression retained |
| B: coherent live advice lifecycle | R5, R6, R4 expiry resolver, E4 quotas | Stored and delivered generation match; restart/concurrency tests; authorised config report; no duplicate/expired send |
| C: actually useful content | E1/E2/E3 | Full NIFTY and SENSEX scenario: preparation→qualified entry→changed market→conditional update→expiry, no partner order integration |
| D: measurable edge and operability | E5/E6 | Frozen research comparisons, truthful forward-shadow archive, per-index funnel/latency evidence, real scheduler/API integration |

Checkpoint output: commits; requirement IDs; exact tests; immutable synthetic/recorded fixtures; full preview cards; remaining operational inputs. Do not claim all stages complete after fixing one validator. Preserve previous audits and developer work. Implementation remains Dev-only; GitHub promotion follows the already authorised rollout scope with verified effective settings. This review does not itself request another permission to implement authorised corrections.

Before relying on live partner advice, verify zero impossible-payoff cards, zero post-expiry sends, full-lot feasibility, research/profile gating, actionable management and urgent-update behaviour using safe failures and current-data no-send previews. A successful Telegram canary proves transport, not edge. If already deployed by another process, surface these findings promptly to the owner rather than silently modifying Production.

## 6. Copyable assignment

> Review `docs/2026-09-08-partner-rollout-audit-and-edge-improvement-plan.md` and the offline probes at `docs/review-2026-09-08-partner/audit_probes.py`. Work only in Dev. Fix R1–R6 before describing `e930968` as ready for partner decisions: impossible payoff acceptance, research/profile gate bypasses, scan-start-time freshness, inadequate lot depth, ranking before validation, expiry resolution, inconsistent persisted generations and contradictory rollout documentation. Preserve durable claims, acknowledgement and sticky transport ambiguity. Then complete E1–E6: actual trigger/invalidation/horizon data, conditional protection, market-based management updates, reserved urgent-message capacity, per-index research/outcome evidence and useful briefs/diagnostics. NIFTY 50 and SENSEX only. No partner broker monitoring, order placement, mandatory feedback or fabricated holdings. Use independent payoff-oracle and fake-clock/concurrency tests, then registered scheduler/authenticated API previews and no-send market observation. Respect existing rollout authorization, but do not replace validation with enabled defaults. Deliver stages A–D with exact evidence and a requirements matrix; do not claim guaranteed returns or fabricate strategy qualification.

## Sources

Vertical-spread payoff identity and limits: [OIC bull call spread reference](https://www.optionseducation.org/strategies/all-strategies/bull-call-spread-debit-call-spread). Used for payoff concepts, not Indian settlement rules.

Current instrument/expiry specifications must come from authoritative exchange information and the actual contract master: [NSE contract specifications](https://www.nseindia.com/static/products-services/equity-derivatives-contract-specifications), [SEBI directory linking NSE/BSE derivatives information](https://www.sebi.gov.in/curation/equity_derivatives.html). No fixed lot size or expiry weekday in the synthetic probes is asserted as today's rule.
