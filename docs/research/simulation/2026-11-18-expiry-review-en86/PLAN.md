# EN71–EN85 review and EN86–EN95 handoff

Research-only work in Dev, starting from 2173546391116be8b8ac5ac449dce858a2542d0b.
Production checkout read-only: 55b5e9422d0262091719042daf4a72dbe9c94d6c.

Problem: assess the new option-market information claim and design ten useful,
distinct follow-up slots without treating repeatedly studied history as a holdout.

Contracts/files: frozen round-7 plan, scorer, precomputation, frontier, results,
anatomy and forward registration; new audit artifacts here; new developer handoff
at docs/EXPIRY_RESEARCH_EN86_EN95.md. Preserve other agents' existing dirty files.

Acceptance: verify frozen source identities and financial identities; independently
inspect EN75/EN83 signal semantics, EN71 execution and the strength of statistical
claims; distinguish reproduced findings from untested assertions; consult primary
research; specify ten slots with causal rules, controls, data gates and stopping
criteria. Keep original scored outputs immutable. No new strategy scored here.

Rollout/rollback: documentation and isolated research helpers only. No engine,
configuration, scheduler, broker, data acquisition or Production changes. No
commit/push/deploy requested. Runtime atlas regeneration is not applicable.

Completed: 39 frozen identities; 467 aggregate identities across 67 day views;
10 main ordinary/adverse replay views plus two price controls; synthetic partial-
exit, forward-OI source and passive-bound witnesses; primary-source research;
developer handoff docs/EXPIRY_RESEARCH_EN86_EN95.md with exactly ten slots.

Verification commands: sentinel-ml-venv Python -B audit.py (exit 0, 51.09 seconds)
and -B mechanics.py (exit 0). Details/limits: AUDIT.md, verification.json and
mechanics.json. No full engine suite: no runtime changes. No strategy scored.

Remaining developer work: versioned research-runner corrections; registrations,
implementation and causal tests; development screens and genuinely new forward
evidence. No authorization for direct Production edits or trading deployment is
implied. Deliverables are new, uncommitted Dev files; no commit/push/deployment.
