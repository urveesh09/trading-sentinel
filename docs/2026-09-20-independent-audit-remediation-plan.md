# Independent audit remediation — implementation slice

Authorized: user requested implementation of the independent audit corrections.
All implementation is in Dev; promotion remains through GitHub. Preserve existing
golden-fixture edits and offline audit artifacts. No live messages, orders,
qualifications, invented account limits, or Production edits are authorized here.

## Sequence and ownership

1. CAS unknown/freshness and final-entry session checks (calendar, route, gateway,
   focused tests): fail closed on unresolved eligibility; preserve exits.
2. F&O close/ledger atomic settlement (positions, orchestrator, ledger contracts,
   tests): exactly one local economic settlement; recover after interruption.
3. Qualification report verification, expiry, and complete economic fingerprints
   (advisory, research, routes and dispatch): invalid or incompatible evidence
   cannot authorize delivery; existing unsupported qualifications fail closed.
4. Expected-slot collection integrity and honest readiness outputs (store/CLIs,
   tests): unavailable/duplicate rows cannot manufacture complete coverage.
5. Real completed-bar shadow provider integration and bounded post-session
   research/report orchestration: use existing providers and research contracts,
   remain non-ordering and do not auto-qualify strategies.
6. Owner authority/exposure diagnostics, operational readiness and final
   integration verification. Document remaining evidence/operator inputs.

## Acceptance

Reproduce and close the audit probes; test empty/stale/unknown CAS membership,
session-boundary waits, duplicate/concurrent/faulted settlements, fabricated and
expired qualification packages, changed economics, mixed-unavailable collection,
duplicate scheduler slots, and diagnostic-success versus delivery readiness.
Run affected integration suites in compatible isolated runtimes. No tests touch
Production SQLite. Regenerate atlas for source changes. Update system guide,
active plan and handover with verified behavior and configuration/migration impact.

## Rollout / rollback

Review migrations against temporary copies and preserve cash/claims/history.
Missing real broker/research evidence stays visibly unavailable. New operational
data paths are shadow/read-only. Promote only via GitHub; rollback disables new
entries/delivery while preserving exits and durable settlement/recovery state.
No increase in live risk, partner risk ceilings or automatic qualification.

## External work that code cannot complete

Fresh broker login, real heldout trading outcomes, approved partner loss limits
and hedge exposure, account-scoped broker statements, and explicitly authorized
Telegram transport test. These remain prerequisites, not implementation claims.
