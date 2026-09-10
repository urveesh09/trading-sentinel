# Final partner advisory plan: AI-assisted research, setup and Production rollout

Date: 8 September 2026. Latest inspected Dev HEAD: `1a766ba`, containing `a077d54`.

This is the consolidated rollout assignment, updated with the owner's latest clarification. Earlier audit documents remain supporting evidence. Inspect current HEAD before implementation; the baseline above is not a claim that newer commits were reviewed.

For obtaining data and producing the evidence package without an immediate specialist-vendor purchase, follow [the free-data and intraday research plan](2026-09-08-free-data-and-intraday-research-plan.md). It documents existing Production LTP/OI records, Kite forward-depth collection, optional free-to-customers Breeze history, source limitations and concrete implementation checkpoints. Do not block collection on research completion or treat modelled candles as observed historical depth.

## Confirmed product and division of work

- Sentinel generates **its own intraday NIFTY 50/NSE and SENSEX/BSE ideas**. The partner's existing strategy is optional context, not a prerequisite or a source of strategy qualification.
- Prioritise hedged/defined-risk trade ideas with concrete entry, invalidation, costs and same-day management. Initial delivery scope is independently qualified directional debit spreads. These are bounded-risk speculative setups, not automatically hedges of an unknown portfolio.
- Advice is for manual use. No partner order placement, broker monitoring, mandatory feedback or holdings upload. Personalised protection of a particular trade requires that trade's details and remains a separate optional feature.
- **Partner delivery means Telegram messages only.** Turning it off stops automatic advice messages, not preview generation or research. It must not secretly switch off unrelated Sentinel execution or existing protective management.
- The owner is the developer using a coding agent. The **coding agent must execute the research/setup work**, prepare profile and qualification payloads, tests, report artifacts and the deployment handoff. Do not hand the owner a list of internal database fields and stop.
- MiniMax may assist with source-grounded explanations, research hypotheses and report interpretation. Deterministic code handles data integrity, prices, payoff, costs, risk, deadlines and eligibility. MiniMax cannot invent data, approve its own unsupported strategy or override a failed gate. Its outage must not stop deterministic advice or management updates.

No additional partner trading preference is required to begin this assignment. Capital/risk limits may remain unspecified for non-personalised per-structure output. Never infer unlimited capacity from a large account.

## Where we are

The developer reports the recent lifecycle/freshness corrections implemented. This guide inspected the implementation note, development handover and artifact APIs; it is not a new independent full acceptance audit of a077d54.

The handover still lists genuine NIFTY and SENSEX intraday research, qualification, saved profile and deployed checks as pending. These are technical deliverables, not missing trading preferences. The owner has already specified intraday-only NIFTY/SENSEX, hedge-first, manual decisions and no partner order monitoring.

Separate **deploying software** from **enabling partner advice**. Research and advisory-quality evidence need not hold up preparation of an explicitly non-delivering deployment. Conversely, enabled flags and a registered hash are not evidence that recommendations are useful.

## Fastest practical sequence

### 1. Developer prepares two parallel deliverables now

**Deployment candidate:** run the relevant regression suite and actual registered-scheduler lifecycle test using a fake transport. Prepare a GitHub PR with exact image/commit, configuration inventory, database migration check and rollback procedure. Preserve existing Production broker/trading settings; do not broadly activate or disable unrelated trading strategies.

For initial deployment, explicitly configure `PARTNER_MANUAL_ADVISORY_DELIVERY_ENABLED=false` through the normal GitHub deployment configuration mechanism. Do not rely on missing profiles/qualifications to prevent sends. Review legacy-route suppression so staging this advisory path does not accidentally reactivate older tips. Read-only previews/research can run only where their actual data source is configured; synthetic fixtures must remain labelled synthetic.

**Evidence package:** find existing usable historical market data and genuine research artifacts first. Reuse valid evidence where it matches the actual intraday policy; do not repeat research unnecessarily. Otherwise run the implemented intraday policy separately on NIFTY and SENSEX with realistic bid/ask, entry delay, costs, no-fills and same-day exits. Keep an untouched chronological evaluation period and report losses, drawdown, uncertainty and limitations, not just profitable examples. Synthetic tests are not strategy research.

The coding agent must make this concrete:

1. Inventory actual available historical underlying and option data, contract mappings and existing evaluators. State dates, coverage, missing fields and provenance separately for each index.
2. Freeze the exact policy, parameters, intraday deadlines, cost/execution assumptions and chronological evaluation split before examining evaluation results. Use the same deterministic decision logic as the advisory consumer.
3. Evaluate the actual option structure, not only whether the index moved in the predicted direction. If historical bid/ask/depth is unavailable, explicitly distinguish modelled scenarios from executable-price evidence; index candles alone cannot establish spread execution. Start a read-only forward quote archive where authorised existing data access permits.
4. Produce a reproducible run manifest and report with candidate/filled/no-fill counts, costs, net outcomes, losses/drawdown, manual-response delay sensitivity, sample limitations and a documented qualify/reject/insufficient-evidence decision. Do not promise a fixed profitable return or choose acceptance rules after seeing the results.
5. Save the actual artifacts, compute their SHA-256 hashes and prepare matching registry payloads automatically. A synthetic fixture, MiniMax's confidence, a report filename or a hash alone cannot establish qualification.

Deliver research for each index independently; a failed or insufficient result is useful evidence, not permission to fabricate success. Keep deployment preparation and receipt testing moving while resolving genuine data/evidence gaps.

If a required data source is missing, identify the exact provider/access/dataset gap and continue independent deployment work. The owner should not be told merely “register artifacts” while the developer has not produced any.

### 2. Merge/deploy the non-delivering candidate after checks

Owner merges the reviewed PR through GitHub using the existing promotion workflow. Developer/operator verifies running image SHA, effective delivery=false, migrations, authenticated APIs, both market feeds and scheduler jobs. A local working-copy SHA does not prove which image is running.

No direct Production source edits or ad-hoc database writes. Keep secrets out of logs/chat. Data API access may be needed; partner broker credentials, holdings or order monitoring are not needed for standalone ideas.

### 3. Developer/operator completes setup through the authenticated service

Use the profile already specified in `2026-09-08-intraday-partner-advisory-implementation-plan.md`: profile ID `default`, next monotonic version, INTRADAY, NIFTY/SENSEX, MARKET_SETUP, DIRECTIONAL_DEBIT_SPREAD, Asia/Kolkata. Proposed configured entry window is 09:45–14:45, reminder 15:10, management deadline 15:15, adjusted to supported session rules. Leave personal limits unspecified and conditional protection disabled initially; do not infer personal size.

Use these existing endpoints through the secure internal path:

- `GET` then `PUT /partner/advisory/profile?profile_id=default`.
- `POST /partner/advisory/research-artifacts`: register actual preserved report content with its correctly computed SHA-256.
- `POST /partner/advisory/qualifications`: record a justified decision for each supported index/structure under `INTRADAY` and `partner-manual-intraday-v1`.
- `GET /partner/advisory/effective-settings`, `/partner/advisory/diagnostics`, `/partner/advisory/cards`: verify actual state and current-data previews.

A registry accepts metadata; the reviewer must still inspect the actual research. Do not upload a dummy report/hash or mark an untested strategy qualified merely to make the gate green. If one index qualifies before the other, prepare a per-index limited rollout; do not qualify both by association.

### 4. Test Telegram receipt separately from trading advice

Off means automated trading advice is off. It cannot prove live Telegram receipt. Use two distinct tests:

1. Automated tests use a safe fake transport to verify routing, rendering, claims, backoff and ambiguity without contacting anyone.
2. A separately explicitly authorised one-off diagnostic message verifies the real destination. Use fixed content such as: **“TEST MESSAGE — NOT A TRADE RECOMMENDATION. Sentinel Telegram connection test. No action required.”** Include a diagnostic reference/time, but no prices, contracts or trade buttons.

Inspect whether a diagnostic sender exists. If absent, implement a narrowly scoped authenticated operator command/endpoint: fixed non-trading template, configured partner destination only, no arbitrary recipient/body, bounded invocation, auditable acknowledgement and conservative timeout handling. It must work without a strategy qualification and without enabling automatic advice. This exception must not allow an ordinary candidate to bypass profile/qualification gates.

Implement and test this capability now; this plan alone does not authorise sending that new diagnostic message. Use an existing explicit authorization for that exact test if present, otherwise request it only when the diagnostic is ready. Never repeatedly resend after an ambiguous result. Record API acknowledgement separately from human receipt/read confirmation; a Telegram acknowledgement is not proof the partner read it.

### 5. Validate the complete no-send advice path, then enable the authorised delivery scope

Preserve complete current-data preview cards for each eligible index. Verify exact contracts, paired payoff, all-in costs, full-lot feasibility, fresh data, trigger/invalidation, same-day deadline, no invented holdings and no broker-order consumer. Exercise reminder/invalidation/deadline/restart/ambiguity cases with safe doubles.

Deliver one release sheet naming the exact eligible strategies, profile version, report fingerprints, effective settings, test results and known limitations. Then enable only the intended partner delivery configuration through the existing authorised GitHub rollout process. This does not require asking again about intraday preferences or requesting partner order access. If the scope changes materially, explain that specific change rather than reopening blanket approval.

Observe initial naturally generated messages and their acknowledgements, latency and reasons for rejection/silence. An acknowledgement proves transport, not trading success. Do not send arbitrary live test advice or force a setup to obtain an example.

## Scope of the first release and subsequent improvements

First release: own-strategy intraday debit-spread ideas on whichever of NIFTY/SENSEX has matching reviewed evidence; defined entry conditions and per-structure economics; material invalidation/target updates; truthful clock-only exit reminder; session retirement; no personal position assumptions. The aim is useful action at the right time, not a daily message quota.

Complete per-index conditional-protection assumptions and their strategy evaluation before enabling that additional category. Neutral premium structures, futures-specific recommendations, richer morning briefs and AI-assisted explanations are subsequent evidence-backed increments; do not advertise them as delivered by the initial spread-only release. Preserve optional AI and intraday-only constraints throughout.

When deciding what else from the day's work can be deployed, inventory each feature's actual source, dependencies, runtime flags and live effects. Classify it as ready observation/research, ready qualified advice, or not yet ready. Do not turn on every innovation merely because it exists in the branch, and do not let an unrelated unfinished feature block ready independent work.

## What is required from the owner

No additional mandatory trading preference or partner strategy is missing. The owner's normal action is to merge the prepared, verified GitHub release when ready. If the coding agent discovers missing market-data access, it should request that specific access through a secure mechanism. A one-off live diagnostic needs its own explicit send authorization if not already provided. Optional personal risk filtering can wait; no personal quantities should be inferred in the meantime.

Do not make the owner enter SQL, invent qualifications, produce backtests or supply credentials in chat. Those technical setup steps belong to the developer/operator.

## Required status report from the developer

Return one table with: deployment PR/test status; effective advice-delivery gate; saved profile version; NIFTY research/qualification; SENSEX research/qualification; feed freshness; preview evidence; scheduler/reminder test; diagnostic Telegram test status/acknowledgement versus recipient confirmation; delivery readiness; exact blocker and who can resolve it. Mark unknowns explicitly. Do not claim all daily innovations are ready without inspecting their individual source/configuration requirements.

## Copyable assignment

> Execute the consolidated plan in `docs/2026-09-08-fast-production-rollout-checklist.md`, not another planning-only checkpoint. The owner is the developer; you, the coding agent, must locate/run real NIFTY/SENSEX intraday strategy research, prepare actual report hashes and justified qualifications, generate the already specified default INTRADAY profile setup, implement/test any missing narrow Telegram diagnostic capability and prepare the GitHub deployment candidate. Sentinel supplies its own strategies; do not require the partner's strategy, holdings, broker access or manual research input. Use MiniMax only as optional analysis/explanation assistance; deterministic calculations and evidence control numeric authority. Work in Dev, preserve audits and unrelated trading settings. Keep automated advice explicitly off during staging, while testing the full no-send path and separately preparing a fixed non-trading receipt test for explicit send authorization. Verify deployed image, effective configuration, per-index feeds, scheduler deadlines and exact preview cards. Record qualifications only for genuine reviewed evidence; report exact data gaps or insufficient evidence rather than manufacturing approval. Continue independent deployment work while research runs. Return the readiness table and scoped delivery-enable change under the existing advisory rollout authorization, with subsequent protection/futures features clearly separated from the initial spread release. No direct Production source edits, arbitrary live messages, fabricated profitability or partner order monitoring.
