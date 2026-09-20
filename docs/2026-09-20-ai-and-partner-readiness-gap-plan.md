# AI activation and partner-readiness gap plan — 2026-09-20

## Problem and production evidence

Production was inspected read-only. The core `agent`, `node-gateway`, and
`python-engine` containers are stopped; each most recently exited with code
137, `OOMKilled=false`. The persistent database contains three manual-advisory
ideas from 2026-09-17, no partner strategy qualifications, no reconciled
partner positions, no advanced hedge shadow evaluations, and no
`partner_hedge_gate_evidence` rows. The 0/7 display is therefore the Phase-3
advanced-hedge rollout gate, not a count of system uptime or ordinary partner
advisory days.

The Production agent has a MiniMax credential, but the opt-in flags for the
bounded async review, news classification, and usefulness telemetry are not
set. The hedge parent switch is also unset/false, which prevents Phase-2/3
shadow cycles even though their phase-specific shadow defaults are true.

## Change slice and contracts

1. Make the reviewed, non-ordering AI capabilities explicit in Compose:
   bounded async MiniMax annotation, bounded news classification, usefulness
   telemetry, and their safe proceed/advisory policies.
2. Make manual partner advisory configuration explicit. Enable the hedge
   parent pipeline so Phase-2/3 shadow observation can run, while keeping both
   advanced delivery switches false and both shadow switches true.
3. Record a staging day automatically only when an advanced hedge shadow
   cycle actually processes at least one fresh option-chain/portfolio input.
   Container uptime, scheduler invocation, missing login, missing positions,
   unavailable chains, and exceptions must never count.
4. Preserve the manual live-chain verification and per-kind sample-review
   gates. Preserve advisory-only behavior and all order boundaries.
5. Correct the partner-readiness diagnostic to use the deployed tables and
   columns. Advanced Phase-3 hedge readiness must remain visible but must not
   block or be described as qualification for ordinary manual index advice.

Files/contracts:

- `docker-compose.yml`: explicit environment contract and safe defaults.
- `python-engine/hedge_readiness.py`: idempotent system-observation receipt.
- `python-engine/hedge_advisory.py`: receipt only after genuine processed
  input in Phase 2/3 shadow mode.
- `scripts/check_partner_readiness.py`: current-schema, read-only attribution
  across profile, inputs, ideas, qualifications, hardened transport and manual
  dispatch configuration.
- focused tests, `SYSTEM_GUIDE.md`, `NEXT_AGENT_PLAN.md`, and regenerated
  `SYSTEM_CODE_ATLAS.md`.

## Acceptance checks

- Rendered Compose config shows AI annotation/classification/usefulness enabled,
  safe AI policies selected, manual advisory enabled, hedge shadow collection
  enabled, and Phase-2/3 delivery disabled.
- A genuine processed shadow cycle records at most one staging day per phase
  and date; repeated ticks update/deduplicate the same receipt.
- Zero processed underlyings never records a staging day.
- Existing readiness still requires 5/7 distinct days, live-chain verification,
  and Phase-3 sample reviews; no code path changes a live delivery flag.
- Focused tests and the broader affected suites pass.
- A 0/7 advanced-hedge report does not return a manual-advisory blocker, and
  the diagnostic never creates a readiness table while inspecting a DB.

## Rollout and rollback

Changes are Dev-only until committed, pushed, reviewed, merged, and deployed
through GitHub. Production is not edited directly. Deployment must render and
review Compose configuration, rebuild/recreate the affected services, confirm
release identity and container health, and then observe a logged-in market
session. Rollback is the prior Git commit plus service recreation; individual
AI/shadow capabilities can also be disabled with their explicit environment
overrides without changing code.

## Remaining operator work

Production must be restored and promoted through the normal GitHub path. A
fresh broker login and genuine reconciled partner-position input are required
for advanced hedge shadow staging. The operator must still perform the live
chain check and review real emitted samples. Manual advisory strategy
qualification remains a separate evidence process and must not be fabricated
from elapsed days.

## Dev verification receipt

- Python engine: 4,122 passed, four skipped, 46 existing deprecation warnings
  in 218.99 seconds.
- Corrected E.1 diagnostic: 27 passed with warnings fatal in 1.37 seconds.
- Agent image: 357 passed with networking disabled in 3.82 seconds; explicit
  enabled-flag import smoke passed.
- `docker compose build agent python-engine`: passed; one existing Python
  Dockerfile casing warning.
- Rendered Compose and a Python-engine Compose run both show manual advisory,
  hedge parent, advanced shadow and proactive shadow enabled; Phase-2/3 live
  delivery disabled. Production remains unmodified and stopped.
- Implementation/docs commit `1a6e0d9` is pushed to
  `origin/codex/production-correction-hedge-p0`; it is not merged or deployed.
