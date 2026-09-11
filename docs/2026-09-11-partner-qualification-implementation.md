# Partner qualification development implementation

## Implemented in Dev

This implementation completes the code portion of the September 11 qualification plan. It does not qualify either index, enable advice delivery, send a message, place an order, or edit Production.

### Complete-policy research

- `python-engine/partner_qualification.py` composes the deployed `evaluate_fno_mom`, `build_directional_debit_spread`, `validate_candidate`, and `validate_profile` functions. It does not reproduce the older close-versus-trigger evaluator under the deployed-policy name.
- Each decision freezes policy configuration, full bar fingerprint, regime, dated-master fingerprint when available, and separate event/receipt/retrieval provenance. Future contemporaneous inputs are rejected; retrospective and missing evidence remain explicitly non-qualifying.
- Accepted, rejected, and no-setup decision records preserve the signal, validation reasons, selected legs, debit/risk/profit/cost fields, trigger, invalidation, target, and management deadline. `write_full_policy_decision` writes these atomically.

### Selected-leg coverage

- `python-engine/research_leg_subscriptions.py` is a restart-safe SQLite journal keyed by decision and exact token identity.
- `persist_candidate` registers selected candidate legs through their declared management deadline without changing candidate validity or delivery authority.
- `research_quote_collector` prioritizes pinned legs, reports capacity shortfalls and missing packets, and still requests a pinned leg when a rolling contract master/futures reference is unavailable. It never replaces it with a nearby strike.
- Terminal subscriptions are retained for the configured compressed-evidence window and then purged, bounding storage. Readiness exposes active-leg and missing-packet coverage.

### Replay and review

- Chronological replay retains executable bid/ask, full-lot depth, two-leg round-trip costs, exact selected-contract identity, manual response delay, cancellation, no-fill, unresolved exit, and exact management-cutoff semantics.
- `replay_cost_scenarios` evaluates fixed fee/slippage stresses against identical receipt-ordered evidence; it never drops an adverse or unresolved scenario.
- `python-engine/partner_qualification_review.py` freezes held-out criteria and binds them to a complete-policy manifest. Its states separately show collection, causal research, outcome coverage, reviewed qualification, and Telegram routing. It never writes a qualification registry row or grants send/order authority.

## Run sequence

1. Keep collection running after this Dev change is promoted through GitHub. Verify `selected_leg_retention` and `selected_leg_coverage` in the protected research-readiness view.
2. Retrieve/retain bar history with explicit provenance and run `evaluate_deployed_full_policy` for each decision. Persist every outcome with `write_full_policy_decision`.
3. Replay each exact selected pair using the immutable archive and declared delay/cost scenarios. September 10–11 remain development diagnostics, not held-out sessions.
4. Predeclare later hold-out sessions and qualification criteria, build the review package, and have a human review it before any registry promotion. Negative, partial, or unresolved evidence remains unqualified.

## Operational evidence still required

No code can create genuine future held-out sessions, contemporaneous full-policy bars, complete selected-leg exit coverage, a human review, or Telegram routing verification. These are production rollout prerequisites, not defaults to be bypassed.
