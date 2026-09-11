# Partner input diagnosis — September 10

Production read-only diagnosis. No profile writes, messages or orders performed.

## Confirmed code defect

fno_signal_scan.scan_underlying deliberately returns a valid signal result without a chain snapshot when sig.direction is None. partner_orchestrator.partner_manual_advisory_tick tests `scan.error or scan.snap is None` before testing direction. Therefore ordinary no-direction results are incorrectly counted as unavailable. The later healthy_no_setup branch is unreachable for those ordinary results. This is a deterministic caller/callee contract mismatch, not missing partner input.

It also means conditional protection and management updates are coupled to a newly fired ORB direction. Existing advice should be evaluated for public-condition invalidation from fresh market observations even when a new entry signal is absent; the separate clock-only lifecycle cannot replace market-condition evaluation.

Today's aggregate logs cannot distinguish this misclassification from true instruments/chain/expiry failures. Do not claim every unavailable count was benign, or that fixing this classification alone produces advice. Read-only FNO paper signal counts today show 53 no_or_break, 3 not_fresh_break, 2 rvol_below_min, 1 opening-window and 4 kill-switch-clear records; this is supporting context from a separate scanner, not a reconstruction of each partner tick.

## Confirmed setup blockers

Running /data/cache.db: partner_advisory_profiles=0; partner_advisory_research_artifacts=0; partner_advisory_strategy_qualifications=0. These independently prevent qualified intraday delivery. load_partner_profile silently returns a default object with holding_period=None if no profile exists, which obscures the missing setup.

Profile creation/update exists at authenticated PUT /partner/advisory/profile (engine route; gateway prefix /api/proxy). No matching profile setup endpoint usage was found in the client source. This was a developer/operator API setup requirement, not a requirement for the partner to enter data into Telegram. Prior onboarding did not make this accessible.

Known requirements already supplied: independent manual trader; NIFTY and SENSEX; INTRADAY only; no automated orders. No partner personal strategy, broker credentials or portfolio feed is needed for generic directional debit-spread advice. Conditional protection requires declared exposure assumptions and remains separate.

The current profile API permits optional capital/risk limits. They are not technically mandatory. If supplied, they must be explicit positive values; never infer them from Sentinel's 8000 rupees. Ask whether generic per-lot advice with manual sizing is intended, or a rupee risk/entry-cost ceiling should filter cards. Genuine research artifacts are implementation/research work, not information the user or partner must invent.

## Precise correction handoff

1. Classify explicit scan.error separately; then handle sig.direction=None as no-entry setup, retaining the reason. Missing sig is unavailable, not healthy. Obtain fresh public-condition data independently where active advice/protection requires it; don't fetch unnecessary full chains for every quiet entry tick.
2. Separate market-condition management from new-entry eligibility and profile permission to create new advice. Existing invalidation/exit priorities remain intact; absent fresh data is explicit, never invented.
3. Persist per-index stage/reason for instrument readiness, bars, no-direction, expiry, chain, validation, profile and qualification. Report observed attempt/success clocks and data freshness. Never equate healthy_no_setup with delivery-ready.
4. Add a small authenticated profile/readiness setup view with saved-versus-default distinction, INTRADAY fields and optional financial limits. Use existing versioned save API; no qualification bypass. Do not expose secrets.
5. Regression tests: valid no-direction/no-snapshot; explicit input error; missing signal; fired direction/missing snapshot; active advice invalidation without new signal; fresh-chain failure; missing profile vs missing qualification; independent NIFTY/SENSEX status.
6. Implement exact-policy research and genuine qualification separately. Saving a profile and correcting metrics do not establish strategy edge.

No Production changes should be made by direct file editing. Code corrections belong in Dev; promotion through GitHub. Operator profile save is an explicit runtime configuration step after the profile scope is settled, not a source-code placeholder.
