# Round 9 plan slice - family search proposal

Status: PROPOSAL, not implementation or score. Date: 2026-11-18.
Starting Dev commit: cceabe62087b4f774f38427b5171a5830737fea2.

Problem: the owner wants each EN slot to explore a mechanism's planned variations,
not reject it after a single setting. Preserve EN87's useful conditional entry
lesson while isolating payoff, admission, risk and execution effects in failures.

Files/contracts: `docs/EXPIRY_RESEARCH_EN96_EN105.md`, `families9.json`,
`SOURCES9.md`, `STATUS9.md`, `verification-plan9.json`, and new round pointers in
SYSTEM_GUIDE, NEXT_AGENT_PLAN, HANDOVER_CHECKLIST and EXPIRY_RESEARCH_EN.
No engine/source/declarations change; no atlas regeneration is needed for docs.

Acceptance checks this turn: confirm prior result/freeze integrity, inspect
round-8 source and lessons, primary-source research, ten unique families and
machine-verifiable 231 planned configurations, write developer-ready rules and
component controls, preserve unrelated dirty files and every frozen prior file.
Verify internal links and diff whitespace. No new profitability claim or test
suite claim. Record actual status and commit identity via Git.

Developer remaining work: implement versioned adapters and full grid expansion;
mechanics/parity/source gates; freeze all controls/configuration before money;
execute the registered development search and report full anatomy; nominate at
most two candidates for a separate new prospective registration if justified.

Rollout: documentation handoff only in Dev. No runtime config/migration, broker,
network acquisition, Production copy/deploy or existing forward-ledger change.
Any later deployment follows GitHub promotion. Rollback: revert this proposal's
own files/pointers, preserving prior results and other agents' work.
