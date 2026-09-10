# Partner manual-trader advisory: Production findings and implementation specification

Date: 7 September 2026, review approximately 22:12–22:20 IST.
Production working-copy HEAD: `2c87ecd`. Dev reviewed HEAD: `175c22a`.
Scope: inspect actual Production message evidence and specify the next focused Dev assignment. No Production edits, messages or orders were made by this review. The working-copy SHA is not a verified running-container image SHA.

## 1. Product correction: what the partner actually needs

The partner is an independent manual trader using substantial capital. They want timely F&O ideas, especially hedged/defined-risk strategies and useful protection guidance. They do not want Sentinel's portfolio reconciliation logs as their advisory feed. Their capital is independent of Sentinel's approximately ₹8k test account.

The earlier requirement was interpreted too narrowly as a portfolio-dependent hedge monitoring service. Correct that product interpretation. **Hedge-first means prioritising relevant protection and hedged trade ideas; it does not mean suppressing all market-based opportunities until the partner uploads positions.**

Build three explicitly different advisory scopes:

1. **Market setup:** a self-contained, quote-backed F&O idea, preferably a defined-risk structure. Does not require partner holdings or Sentinel funding. Explain the trade's objective and prerequisites; never claim it hedges an unknown existing portfolio.
2. **Conditional protection idea:** “For an existing long exposure of this type, consider this protection structure if these conditions hold.” Show per-unit economics and limitations. It is not personalised sizing or a claim that the partner owns the exposure.
3. **Personalised exposure review:** uses current, confirmed holdings, account binding and reconciliation to propose quantities and portfolio effects. Retain all existing completeness/readiness protections here.

A standalone hedged strategy can still be speculative. A hedge to an existing position cannot be judged without knowing what it protects. Preserve this distinction in code, cards, research and outcome reporting.

Owner clarification: the partner trades **NIFTY and SENSEX**. Interpret NIFTY as NIFTY 50 for this implementation. The initial partner universe is NIFTY 50 derivatives on NSE and SENSEX derivatives on BSE; other indices and stock derivatives are outside this release. Capital, maximum loss, usual holding period and willingness to share holdings remain unknown. Build profiles and safe per-structure output while those inputs remain unknown; do not borrow Sentinel's limits or infer unlimited capacity from “huge amounts.”

### Binding amendment — NIFTY 50 and SENSEX release scope

This amendment takes precedence over generic instrument examples elsewhere in this document and is part of Checkpoints A–D, not a later enhancement.

- Configure both indices as first-class advisory instruments. Inspect existing underlying registration, broker segment mapping, quote subscriptions, historical coverage and chain discovery. A working NIFTY path is not evidence that SENSEX works. Missing BSE data must produce a specific owner-visible availability state, without blocking independently valid NIFTY ideas.
- Use separate exchange-aware instrument IDs, option chains, futures references, lot sizes, strike increments, tick sizes, available expiries and settlement calendars. Load current contract metadata; do not hard-code expiry weekdays or translate a NIFTY symbol/strike into a SENSEX contract. Do not substitute India INX contracts for domestic BSE contracts.
- Evaluate each index independently using its own completed bars, executable quotes, liquidity, costs and historical strategy evidence. Compare qualified alternatives by risk-adjusted economics and execution quality, not nominal option premium or number of index points. Do not assume either index is always the preferred trade.
- Default research candidates are same-index, same-expiry defined-risk vertical spreads; selective bounded premium structures require their existing volatility/event gates. Conditional protection must identify the exact exposure it assumes. Generic equity-collar examples are not ready-made index hedges: index futures plus options require their own payoff, margin, expiry and coverage validation.
- Treat simultaneous same-direction NIFTY and SENSEX ideas as potentially overlapping market exposure. Prefer one best-supported expression of a shared thesis, or clearly label the alternative. Never advertise two index ideas as diversification merely because their names differ. Cross-index hedging is outside the initial release; it requires separately validated basis/correlation risk and exposure mapping.
- Add expiry-aware handling per index: contract rollover, holiday-adjusted dates, near-expiry sensitivity, widening spreads, declining executable depth and entry/exit cutoffs. Same-day-expiry setups require separate research qualification and profile enablement; do not infer that preference from the instrument names.
- Morning preparation and session review should cover both indices concisely. Event-driven actionable cards name the exchange and exact index prominently. If only one index has a qualified opportunity, send only that opportunity; do not create a second idea for symmetry.

Additional mandatory acceptance evidence: NIFTY-only and SENSEX-only valid candidates; one feed stale while the other remains usable; same-looking broker symbols across segments; wrong-index hedge legs; different expiries/lot sizes; holiday rollover; same-direction overlap suppression; and independent no-holdings standalone advice on each index. Deliver at least one complete preview card and lifecycle replay for each index using recorded or clearly synthetic fixtures, plus separate per-index rejection/latency metrics. Neither fixture establishes profitable performance.

## 2. What Production actually sent today

Read-only sources: `docker logs --since 2026-09-07T00:00:00+05:30 python-engine`, plus SQLite opened with `mode=ro` at `/data/cache.db` in that container. Partner identifiers and credentials are intentionally omitted.

| Time IST, 7 September | Message kind | Actual content | Ledger evidence |
|---|---|---|---|
| 09:37:10 render; 09:37:11 recorded | `hedge_service_status` | “No recommendation: no accepted portfolio snapshot.” Wait for reconciled holdings and usable market data. | `delivered=1`, detail `state=acknowledged` |
| 09:50:00 | `hedge_morning_summary` | “Portfolio inputs: 0/0 open positions reconciled.” “Current assessment state: no accepted portfolio snapshot.” No personalised quantity. | `delivered=1`, `acknowledged` |
| 15:40:00 | `hedge_eod_summary` | Same absent-input state in an end-of-day summary. | `delivered=1`, `acknowledged` |

The inspected hedge ledger contains exactly these three records for today. The legacy `partner_messages` table has no rows for today, and the available current-container `partner_msg` logs show these same three messages. This supports the user's observation; it is not an independent Telegram chat-history export or proof the recipient read them.

Both `partner_input_snapshots` and `partner_positions` had **zero rows** at inspection. Repeated intraday logs report `partner_hedge_tick_no_portfolio_input reason=NO_ACCEPTED_PORTFOLIO_SNAPSHOT`.

Analytics were running: examples at 14:42, 14:47 and 14:52 report three persisted underlying snapshots, one considered event, zero sent and one suppressed, with `analytics_suppression_enabled=True`. The F&O engine also evaluated opportunities, with observed reasons including `iv_rank_below_condor_min`, `not_fresh_break` and `outside_entry_window`. These are evidence of evaluated conditions, not proof a profitable trade was missed. Do not weaken those gates merely to increase messages.

Conclusion: **delivery worked for status messages, but the useful advisory stream was gated away.** Today's three messages were operational status, not actionable trade setups.

## 3. Code evidence and relationship to W1–W10

In both inspected copies, `partner_orchestrator.py` returns early from `partner_scan_tick` when hedge mode and directional suppression are active. Analytics and legacy briefs/EOD have similar suppressors. Config defaults enable these suppressors. Runtime analytics logs explicitly confirm analytics suppression; the review did not successfully load the running process's entire effective settings, so defaults alone are not asserted as every runtime flag value.

`hedge_advisory.py` requires accepted portfolio input for personalised evaluations. That is appropriate for personalised sizing; it is inappropriate as the prerequisite for every partner idea.

Do not solve this by simply flipping suppression flags. The old signal route sends directly through `send_partner`, lacks the full new advisory lifecycle, and can render estimated stop-risk-based “lots per ₹1L.” Its premium scenarios are model estimates, not assured execution or a maximum-loss bound. Reuse its market scanning where useful, but pass candidates through the new validated advisory path.

Dev has eight additional W-series commits through `175c22a`, including market-bar evidence, reconciliation, basket/research, cost and exit challengers, source contract and AI/harness work. This review does not independently certify complete acceptance of W1–W10. The remediation log explicitly describes W8's provider transport as external and W10's harness as `scheduler: NOT_STARTED_BY_DESIGN`, without authenticated browser proof. Those limitations remain; the new partner priority must not inherit a mistaken “everything is live verified” status.

Relevant existing modules to reuse: `partner_orchestrator.py`, `partner_content.py`, `partner_bot.py`, `hedge_advisory.py`, `hedge_strategies.py`, `hedge_analytics.py`, `hedge_readiness.py`, `fno_defined_risk.py`, `fno_risk.py`, scheduler registration, source adapters and delivery ledger. Avoid a parallel transport with weaker safeguards.

Focused baseline verification this review: **77 tests passed** across `test_partner_orchestrator.py`, `test_partner_content.py`, `test_partner_bot.py`, `test_hedge_formatters.py`, `test_fno_defined_risk.py`. Passing existing tests does not satisfy the new product behaviour.

## 4. Required architecture and scope contracts

### P1 — Separate partner advisory from account execution

Create a versioned partner preference/profile model: enabled scopes, instruments, holding periods, timezone, delivery windows, permitted structures, educational versus actionable preference, optional capital/risk limits and optional confirmed holdings. Do not require broker execution access for market advice.

Candidate generation must not depend on Sentinel's order placement, current cash reservation, simulated fills, paper positions or a broker entry approval. Market data and evidence gates remain mandatory. A valid market candidate can exist when Sentinel places no trade. Partner quantities remain absent unless supported by a separate current partner risk profile and, where needed, exposure.

Use an explicit `advisory_scope` enum such as `MARKET_SETUP`, `CONDITIONAL_PROTECTION`, `PERSONALISED_HEDGE`. Dispatch validation must branch on scope. It must never fabricate a zero-position snapshot to satisfy personalisation gates. Migrate old records conservatively; missing scope must not be inferred as permission to send.

Acceptance: with no holdings and no Sentinel funds, a fully validated standalone setup reaches preview/delivery eligibility; a personalised hedge still fails closed; neither creates an order or inserts a fake holding.

### P2 — Hedge-first candidate selection, not blanket suppression

Replace broad suppressors with explicit category policy and a common ranking/dedup layer. Priority order:

1. Material invalidation or risk change affecting an active advisory; protection adjustment for confirmed exposure when available.
2. Timely protection opportunities relevant to the selected profile.
3. High-quality, self-contained defined-risk F&O setups.
4. Selective directional futures/options ideas that meet the profile and stronger risk disclosure/validation requirements.
5. Useful session preparation/review. Infrastructure diagnostics belong to the owner dashboard/operations channel.

This is a default design priority, not permission to send on someone else's behalf during development. A directional idea must not outrank an urgent invalidation because its raw signal score is larger. Deduplicate overlapping structures on the same thesis; explain one preferred structure and at most one materially different alternative.

A lack of holdings should not generate three repetitive partner notices. Provide an optional one-time onboarding explanation for personalised services; show persistent missing-data status to the owner. If the market has no valid setup, a concise scheduled market brief can say so and name what would change that assessment. Do not fabricate activity to meet a daily quota.

### P3 — A small, rigorously evaluated strategy family

Reuse the existing deterministic F&O context, chain selection and payoff functions. Initial candidates: directional debit spreads, conditional protective puts/collars where coverage assumptions are explicit, and selective defined-risk premium structures only when volatility/regime/liquidity evidence supports them. Futures ideas require separate notional, margin and adverse-gap analysis; they are not bounded-risk trades merely because a stop is listed.

Do not equate high IV alone with attractive premium selling. Check how the supplied IV rank is calculated, its historical coverage, point-in-time provenance and suitability across expiries. Missing volatility evidence must not become a neutral positive score. Evaluate trend/range suitability, upcoming events and volatility changes, costs, liquidity and holding horizon together.

Keep this bounded: no broad strategy invention or AI-generated strikes. Compare a small frozen family out of sample using the W-series research infrastructure; retain rejected setups and all variants. Establish a separate evidence state for a strategy family (`UNVALIDATED`, `RESEARCH_ONLY`, `QUALIFIED_FOR_ADVISORY`, `SUSPENDED`) with documented review criteria. Qualification is not a profit promise.

### P4 — Precision gate for every actionable card

Validate before rendering and again immediately before dispatch:

- Exact exchange, underlying, tradingsymbol/instrument ID, expiry, strike, option type, side, ratio and current lot size. Resolve from current instrument metadata, not hard-coded expiry weekdays or lot sizes.
- Fresh executable bid/ask on every leg with synchronised timestamps, non-crossed quotes, spread and depth/volume/OI checks. Last traded price or midpoint alone cannot support an actionable execution price.
- Net debit/credit at conservative prices, estimated full-structure costs, payoff/breakeven calculation, premium/margin requirement and assumptions. Never confuse margin with maximum loss.
- Payoff bounds calculated from all legs and coverage assumptions. For defined-risk spreads, say the theoretical bound assumes all intended legs are filled and maintained; legging, exits and settlement can create additional operational losses.
- Proposed entry condition/price limit, maximum acceptable deterioration, time-to-live, thesis invalidation, management triggers and exit/expiry instructions. A target scenario is not a guaranteed premium value.
- Partner size/capacity: per-lot/per-structure economics by default. Personal quantity requires known risk budget and capacity checks; substantial capital does not establish liquidity. Do not linearly extrapolate “lots per ₹1L” from a modelled stop loss.
- Profile-specific event, expiry and settlement checks, including stock delivery obligations where applicable. Verify current exchange/broker rules from supported metadata and authoritative documentation.

If any required field is missing, downgrade to a clearly labelled watch condition without trade legs or suppress actionable output with an owner-visible reason. Do not send a half-valid actionable card.

### P5 — Manual execution and follow-up lifecycle

Persist advisory ID, economic version, scope, evidence hashes, generated/quote/validity times, policy version and supersession links. Lifecycle: candidate → validated → preview/queued → acknowledged-delivery or ambiguous → active idea → invalidated/expired/closed-for-observation. Delivery acknowledgement is not a trade fill.

Track `NOT_REPORTED`, `TAKEN`, `SKIPPED`, `CLOSED` as separate optional manual feedback. Partner actions are never inferred from delivery. Follow-ups without feedback must say “If you took idea X…” rather than asserting an open position. Manual feedback containing exposure must be confirmed and versioned before personalised calculation; a casual free-text reply is not an automatically trusted complete portfolio.

Multi-leg cards must address legging and abandonment: do not describe a single short leg as safely bounded before its protection is established. Provide instructions to recheck the combined executable price and broker requirements. No broker execution buttons or automatic order consumer in this partner product.

After a material price move or expiry, an old entry must not be replayed as fresh advice. Invalidation/replacement references the original idea clearly and includes what changed. A missed notification does not change economic validity.

### P6 — Timeliness, cadence and operator diagnostics

Use existing market-session calendar and supported scanner cadence. Proposed service targets for validation, not unmeasured guarantees: evaluate after each eligible completed signal bar; normally finish candidate evaluation and queueing within 60 seconds of available complete data; use a configurable all-leg quote age limit initially tested at 30 seconds and reject stale cards. Record p50/p95 delays and missed opportunities caused by delay. Adjust limits to measured provider capability without relabelling stale quotes as fresh.

Session preparation should arrive before its intended decision window with no stale executable prices. Live actionable ideas arrive on conditions, not arbitrary three-times-a-day schedules. Start with one concise optional morning brief and one useful review, plus event-driven qualified ideas and material updates. Dedup/cooldown must not swallow an urgent invalidation; destination-wide Telegram rate limits still apply. Prioritise the queue under those limits and alert the owner if urgent content expires undelivered.

Measure the full funnel: data-ready → considered → rejected with exact reason → validated → expired-before-send → dispatched → acknowledged/ambiguous → followed-up. Include independently the scheduler heartbeat and market-data freshness. Owner diagnostics should explain silence within the session rather than wait several days.

### P7 — Preserve delivery safety while generalising validation

Reuse durable decision-level guards, generation expiry, destination backoff, claim ownership, durable transport-start tracking and sticky ambiguity. Scope-specific validation is essential: market ideas validate market/profile/research revision; personalised ideas additionally validate portfolio revision and binding.

Do not remove portfolio checks globally to let standalone ideas through. Do not route the new ideas through a legacy best-effort send that bypasses guards. Recover only by revalidating/regenerating current advice; no blind replay of rendered text. Acknowledged equivalent decisions remain deduplicated; material changed advice gets a linked version.

The current transport truncates text above Telegram's limit. Actionable multi-leg advice must instead use a bounded validated renderer; never truncate away a hedge leg, loss limitation or validity condition. Prefer one complete concise card and an authenticated detail view. Test overlength cards explicitly.

### P8 — Useful optional AI, deterministic numeric authority

AI may draft a concise explanation from validated facts, rank questions for review or summarise source-linked events. It must not invent contracts, prices, portfolio holdings, risk budgets, probability of profit or expiry rules. Template rendering remains available with no key, outage or budget. Validate model text against the structured facts; unsafe or inconsistent text falls back to deterministic wording.

For this partner's large-capital use, precision means tested numbers, known assumptions, fresh inputs and operational discipline. “AI confidence 95” and disclaimer text are not substitutes.

## 5. Partner-facing card contract

Example schema below is a design template only, not a current recommendation. Do not send bracket placeholders.

```
[SETUP / CONDITIONAL PROTECTION / PERSONALISED HEDGE] • [underlying]
Idea [ID/version] • Data [IST time] • Valid until [IST time]
Why now: [two concrete facts and one uncertainty]
Structure: [every leg: BUY/SELL, exact expiry, strike/type, ratio/lot size]
Act only if: [trigger and maximum combined debit/minimum credit]
Per structure: [premium, estimated fees, margin where known]
Risk: [theoretical bound or unbounded/gap risk; assumptions]
Invalidation / management: [conditions, exit and expiry deadline]
Skip if: [price moved, stale quote, spread/depth, event or incomplete hedge]
[Personal size absent unless verified profile/exposure supports it]
Manual decision. Recheck current executable quotes before acting.
```

Market briefs should explain regime, meaningful levels, event risk, preferred strategy conditions and “what would trigger an idea.” They should not contain SQL state names, “0/0 reconciled,” internal claim IDs or the unsupported generic assertion “paper-validated only.” Show the actual strategy evidence level where relevant, without claiming validation that has not occurred.

## 6. Required tests and acceptance evidence

1. Reproduce today's setup: zero partner positions/snapshots, hedge preference enabled. Valid recorded-market setup becomes eligible; personalised hedge remains blocked; no repetitive reconciliation notices sent to partner.
2. Sentinel cash zero/₹8k/order disabled does not change market-idea eligibility. Partner risk profile stays separate.
3. Stale/missing/crossed/out-of-sync leg quotes, missing lots, wrong expiry, inconsistent strikes/ratios, insufficient depth and expired data cannot produce an actionable card.
4. Independent payoff-oracle tests over underlying price scenarios for every structure, including fees and coverage assumptions. Modelled stop loss is never labelled guaranteed maximum loss.
5. Large-size scenario exceeds displayed liquidity/capacity: no naive lot scaling. Unknown partner budget yields no personal quantity.
6. NIFTY/SENSEX expiry, calendar, event and index-settlement cases use versioned exchange-specific metadata. Gaps and incomplete multi-leg execution are explicit. Stock-delivery rules must not be applied to these index cards; stock derivatives remain outside this release.
7. Concurrent workers, acknowledged duplicate, 429 across categories, timeout after possible acceptance, status-write failure, crash/restart and stale-recovery ownership tests preserve current safeguards.
8. No portfolio required for standalone dispatch; account mutation invalidates personalised dispatch; profile or market revision invalidates affected standalone advice. Legacy rows do not acquire new authority.
9. Oversized text cannot lose a leg/risk/expiry field. All partner fixtures are plain readable cards, not operator logs.
10. Replay morning→trigger→quote movement→invalidation→EOD with simulated manual take/skip/no-response. Follow-up wording never invents a fill or position.
11. Provider/AI outages do not block deterministic evaluation or generate invented facts. Demonstrate an actual fake-provider failure, not a status-only fixture.
12. Registered scheduler + authenticated preview/API + real UI, with safe fake transport and market clock. Capture exact rendered cards and the delivery/economic audit trail. No demo-mode substitution for integration proof.

Deliver a requirements matrix P1–P8 and tests 1–12. Preserve frozen fixtures containing no credentials or personal identifiers. Store real forward-shadow outcomes separately from hypothetical per-card payoff scenarios. Partner profit is unknown unless voluntarily supplied and reconciled; Telegram acknowledgement is not a performance record.

## 7. Development and rollout sequence

**Checkpoint A — correct scope and content:** P1/P2, profile model, scoped dispatch validation, status routing, card renderer and no-holdings acceptance. This is the first useful product change, not just another message-log feature.

**Checkpoint B — quality and lifecycle:** P3–P5, payoff/quote/capacity validation, versioned ideas, manual follow-ups, large-size and expiry tests.

**Checkpoint C — integration:** P6–P8, delivery safety, latency metrics, actual scheduler/API/UI proof with fake transport. Retain old pathways behind explicit rollback-compatible routing; migration must not unsuppress all legacy messages.

**Checkpoint D — forward observation and release candidate:** run with current market data and no partner send, collect exact cards including rejection reasons, compare with observed market paths and independently inspect numbers. Resolve strategy evidence and profile limitations; do not promise perfect forecasts. Produce a GitHub PR, exact configuration migration, rollback instructions, test counts and remaining external inputs.

**Live enablement is separate:** no canary message, partner outreach or Production mutation is authorised by this document. The owner should review actual rendered examples and the intended destination/routing before separately authorising live delivery. A canary validates delivery and presentation, not profitability. Promotion remains through GitHub.

Do all independent Dev work before asking for external credentials or live approval. Do not stop after Checkpoint A and call the full assignment done. Conversely, do not activate unvalidated trade advice because the partner uses large amounts; that increases the need for precise evidence.

## 8. Copyable next-developer assignment

> Binding instrument scope: implement **NIFTY 50 (NSE) and SENSEX (BSE)** as first-class instruments throughout the assignment below. Apply the binding amendment in Section 1, including independent feeds/chains/metadata, per-index validation and evidence, overlap-aware selection and previews for both. Do not expand into other indices/stocks, reuse NIFTY contract assumptions for SENSEX, or make an unvalidated cross-index hedge. Partner holding period and risk budget remain explicit unknowns.

> Prioritise `docs/2026-09-07-partner-manual-trader-advisory-plan.md`. Work only in Dev and preserve previous audit artifacts. Today's Production evidence confirms three acknowledged status messages and zero accepted partner snapshots: the product currently suppresses market tips while waiting for a portfolio. Build an independent manual-trader advisory product with hedge-first priorities: standalone defined-risk F&O opportunities without portfolio or Sentinel-capital dependence, conditional protection ideas, and separately gated personalised hedges. Implement P1–P8 and tests 1–12 through Checkpoints A–D; do not merely disable suppression flags or re-enable legacy sends. Reuse existing market/payoff modules and hardened delivery machinery with explicit scope-aware final validation. Require fresh executable multi-leg quotes, exact instruments/lot sizes, independently tested payoffs, full costs, truthful risk/capacity assumptions, validity and actionable management/invalidation. No naive lots-per-lakh scaling, invented holdings, forced message quota, guessed fills or AI-generated numerical authority. Provide exact preview cards and registered scheduler/API/UI evidence using safe fakes, then current-data no-send observations. Report requirements, commits, tests and external prerequisites precisely. Do not change Production, send partner messages, place orders or increase capital; prepare a GitHub promotion candidate for separate owner review.

## 9. Supporting references and limits

Collars protect an existing long exposure with a put and a covered call, trading protection cost against upside; this is why coverage must be explicit and a collar cannot be advertised as protection for an unknown portfolio. [OIC collar strategy reference](https://prd-web.optionseducation.org/strategies/all-strategies/collar-protective-collar). Use this for payoff concepts, not Indian contract/settlement rules.

Use current Indian instrument/contract information and risk requirements rather than static assumptions: [NSE individual securities derivatives](https://www.nseindia.com/static/products-services/equity-derivatives-individual-securities), [NSE derivatives risk management](https://www.nseindia.com/static/products-services/equity-derivatives-risk-management).

For this narrowed release, use [NSE NIFTY 50 contract information](https://www.nseindia.com/static/products-services/equity-derivatives-nifty50) and [NSE contract specifications](https://www.nseindia.com/static/products-services/equity-derivatives-contract-specifications). Obtain current domestic BSE contract information and chains through the exchange links in [SEBI's equity-derivatives information directory](https://www.sebi.gov.in/curation/equity_derivatives.html). Exact current lot sizes and expiry weekdays are deliberately not frozen in this plan; validate them against the contracts used in each advisory.

This plan improves the relevance, precision and delivery of decision support. It cannot ensure the best entry/exit in advance or guarantee profits, especially at large size. Success must be measured by truthful usable advice, realistic outcomes after costs, managed risk and disciplined operational evidence.
