# October 3 — P1–P4 completion slice (Dev only)

## Authority and invariant

The owner approved nominal book allocations of Swing ₹1,000, Penny ₹2,000,
Momentum ₹3,000 and EDGE ₹3,000, with transfer of unused allocation allowed.
They delegated the remaining contingency decision. This slice uses **full
bounded entry exposure + calculated charges + 1% of executable notional**.
The 1% protects a bounded limit-price preflight from fees and a small price
move before a live fill; it is not leverage or extra funding. The account-wide
own-cash check remains authoritative, so book attribution is observable but
the four figures are not stranded pools.

No Production file, container, broker order, push or deployment is in scope.

## P1 — account-wide admission

**Problem.** The Python engine and Node gateway could each admit an entry
against the same broker snapshot. A single caller's F1-A check is insufficient
when another book is simultaneously dispatching.

**Contracts/files.** A compatible, additive SQLite reservation ledger in the
shared `/data/cache.db`; Python `KiteClient` and gateway executor admission
adapters; explicit book attribution/configuration; broker-order reconciliation
and tests. A reservation is acquired before dispatch, remains for accepted,
ambiguous or partially-filled orders, and is released only by verified terminal
zero exposure. Exits never acquire or wait on admission reservations.

**Acceptance.** Cross-process candidates exceeding account own cash cannot both
be sent; unusable broker evidence fails closed; restart, broker disagreement,
unknown order and partial fill retain a reservation; a verified cancelled,
zero-fill order releases it. Charges/contingency are included once and broker
pending orders are not silently treated as free cash. The account cap is
respected even when allocation transfers are used.

**Rollout/rollback.** Additive schema and Dev tests first. Paper observation
is required before any owner-controlled promotion. Rollback never deletes or
auto-releases unresolved rows; entry remains closed when proof is absent.

## P3 — lifecycle/portfolio parity

**Problem.** Existing adapters reuse valuable entry evaluators but do not
reconstruct shared admission, fills, partial exits, cash or unavailable market
context. They must not be called full portfolios.

**Contracts/files.** Extract only pure, shipped decision/admission/exit helpers
where they exist; add a deterministic, evidence-labelled joint portfolio
ledger to Lab adapters. Inputs must archive the prior-known context and reject
unavailable universe/regime/news/session evidence. No neutral or current
context substitution is permitted.

**Acceptance.** Differential fixtures against shipped decision kernels;
completed-bar boundaries; fees, gap/worse-fill and partial-exit accounting;
simultaneous entry cash contention; portfolio reconciliation; unavailable date
declarations. Any unarchived runtime input leaves a run `PARTIAL` or
`UNAVAILABLE`, not a fabricated return.

## P4 — prospective qualification

**Problem.** A date declaration does not prove a holdout was never observed or
selected after results were known.

**Contracts/files.** A versioned, append-only hypothesis/holdout registry and
CLI wiring. Each qualification freezes policy/data/context hashes and
development window before execution, records evaluation and reuse, and rejects
retroactive creation, policy drift and mismatched context. Reports expose
session-block uncertainty and marked-capital drawdown only when their evidence
exists.

**Acceptance.** Tests reject retroactive/duplicate/reused-as-untouched holds,
post-freeze policy changes and incompatible context; retain old runs as
`DECLARED_UNVERIFIED`; retain IID bootstrap as descriptive only. Registry
entries are never rewritten by this tooling.

## Remaining operator work

Real data availability, an actual paper-observation period, release acceptance,
GitHub push and Production promotion remain separate owner-controlled steps.

## Dev verification receipt

Combined P1/P3/P4 focused Python regression passed: 90 tests, one existing
HTTPX deprecation warning. The gateway executor suite passed: 59 tests. The local
Node test dependency has no `better-sqlite3` binary for the workstation's Node
24 ABI, so executor tests mock the native ledger boundary; syntax checks pass
and the Python ledger tests exercise the deliberately identical SQLite schema
and protocol. Container/paper observation remains mandatory before promotion.
