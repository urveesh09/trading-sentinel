# G — promotion bridge contract

Problem and impact: `docs/NEXT_AGENT_PLAN.md` §11 closes with — *"Promotion to live requires a separate reviewed bridge and risk budget."* Without an explicit, name-and-shamable contract, a held-out comparison report is silently promotable: anyone could read a favourable report, narrate "we should put money on this", and the system has no structural refusal. This doc defines the bridge before any G implementation uses it.

Authoritative evidence: §11 acceptance; the literal payload key `"authorization_effect": "NONE"` returned by every `proactive_*` report function (`proactive_intelligence.py:1178, 1183, 2076, 2183, 2241`, `proactive_exit_research.py:77`, `proactive_execution_research.py:50`, `proactive_portfolio_research.py:85, 93, 104`); the `SHADOW_COMPARISON_MIN_CLOSED_OUTCOMES = 20` floor at `proactive_intelligence.py:21`; the bankroll ledger invariant from `performance.py` and `broker_reconciliation.py`; the seven-gate §9 checklist for partner activation.

Affected contracts/files: `python-engine/promotion_bridge.py` now persists non-authoritative decision/transition records. Atomic terminal transitions and budget/expiry checks are implemented; the full evidence gate is not. This document's requested gates are requirements, not proof that they run.

Steps: (a) state the contract, (b) name what *cannot* be bypassed, (c) provide the refusal-record template, (d) provide the risk-budget surface, (e) clarify what counts as evidence at each gate.

Acceptance: every later G implementation commit that intends to feed live must reference this document by name and quote the gate the implementation satisfies. The bridge is unsigned until user signs.

## 1. What the bridge is

The promotion bridge is the *handshake* between a SHADOW held-out comparison report and any future live order authority. It is not a strategy. It is not a setting. It is not a flag.

Three things the bridge carries:

1. **Identity** — which hypothesis, which entry/exit profile, which account, which run_id, which code revision, which shadow-schema version, which cost-schedule version.
2. **Evidence summary** — closed outcomes, sample size, drawdown, net expectancy with confidence interval, frozen manifest digest, heldout split digest.
3. **Authorisation state** — *one of* `UNSIGNED`, `REFUSED`, `APPROVED_WITH_BUDGET`, `APPROVED_LIVE_BUDGET`. Anything not in this set is a contract violation.

A held-out comparison report may be read by humans. It may not be promoted to live unless the bridge carries `APPROVED_WITH_BUDGET` or `APPROVED_LIVE_BUDGET` and is signed in the refusal-record surface by a named operator.

## 2. What cannot be bypassed

These are physical facts about the system, not policy. Code review cannot change them; only deliberate, documented refactors can.

### 2.1 The proactive stack never authorises orders

Every `proactive_*` report returns `can_place_orders=False, authorization_effect=NONE` (sources cited above). A future contributor who wants to add order authority to a `proactive_*` function must rename it (e.g. `proactive_live_*`) and add a new ledger entry. **Promotion cannot happen via the proactive namespace.**

### 2.2 The bankroll ledger is the only cash truth

The local `bankroll_ledger` and externally supplied broker statement are distinct evidence sources. Ledger INSERT paths have multiple owners; broker imports explicitly write separate statement tables, and report reads initialize missing tables. A statement's cash arithmetic MATCH is not broker-to-local reconciliation. Promotion records never mutate operational bankroll. Confirmed funding is not trading profit; do not invent a deposit from a bridge approval. See the corrected F inventory for exact ownership and limits.

### 2.3 Cost schedules are version-frozen

`cost_schedules.EQUITY_INTRADAY_SCHEDULE_VERSION = "ZERODHA_NSE_EQUITY_INTRADAY_AS_OF_2026-08-10"`. A bridge must record the cost-schedule version it was evaluated against. **Promotion cannot skip this; a new schedule needs a new bridge.**

### 2.4 Sample size gates are not relaxed by configuration

Reports may contain fewer than 20 closed outcomes and explicitly say INSUFFICIENT_CLOSED_OUTCOMES; 20 is not a report-issuance floor or proof of an edge. This proposed bridge policy requires at least 20 research/30 live closed outcomes, but counts alone do not establish statistical reliability, independent held-out provenance or live approval. The current bridge does not validate those report gates and always reads `approval_usable=False`.

## 3. Authorisation states

### 3.1 `UNSIGNED`

Initial state for every new held-out report. The report is visible to humans; no bridge action is implied. **Until signed, no live authority flows from this report.**

Operator-visible meaning: "this is evidence; it is not a permission."

### 3.2 `REFUSED`

A named operator has reviewed the report and chosen not to promote it. A refusal record (template in §5) captures who, when, why, and which gates were unsatisfied. **A refusal can be appealed only by re-running the comparison with a new `research_run_id` (a new evidence identity), not by amending the old one.**

Operator-visible meaning: "this evidence does not authorise money at risk; the comparison is preserved for context but is not a permission to act."

### 3.3 `APPROVED_WITH_BUDGET`

A research budget — distinct from `INITIAL_BANKROLL` — is authorised for further observation. The budget is a fixed IN₹ amount, expressed per strategy/account, with a hard expiry and a maximum drawdown. **APPROVED_WITH_BUDGET does not permit live order submission.** It permits paper/live profit-and-loss tracking against a bounded drawdown.

Operator-visible meaning: "approved to put this much money in the SHADOW path's ledger, with hard drawdown limits."

### 3.4 `APPROVED_LIVE_BUDGET`

The proposed live approval requires confirmed capital/risk input, ≥1 successful bounded observation cycle, F external reconciliation and D operational evidence. Those gates and a live consumer are not implemented by this persistence surface. The state label records operator intent only; it never creates a deposit, changes bankroll or permits orders. Reads remain `approval_usable=False` even with syntactically valid budget/signature.

Operator-visible meaning: "approved to put this much real money behind this exact evidence identity."

## 4. The seven required fields on every bridge

Every bridge record carries these seven fields. A bridge missing any one is invalid and cannot proceed.

| Field | Description | Source of truth |
|---|---|---|
| `bridge_id` | Unique identifier (UUID v4, or 16-hex identity hash) | Generator |
| `proposal_run_id` / `research_run_id` | The shadow run that produced evidence | `proactive_intelligence.py` |
| `evidence_identity` | SHA-256 of the held-out report's canonical JSON | Generator |
| `schema_version` | Shadow schema (today: `"shadow-evidence-v2"`) | `proactive_intelligence.py:27` |
| `cost_schedule_version` | Cost schedule used (today: `"ZERODHA_NSE_EQUITY_INTRADAY_AS_OF_2026-08-10"`) | `cost_schedules.py` |
| `code_revision` | Git SHA at comparison time | `git rev-parse HEAD` |
| `signed_at` | UTC instant of signature; tz-aware | ISO 8601 |
| `signer` | Operator identifier — **must** be a string, never a raw secret | Operator config |
| `authorisation_state` | One of the four states above | Signer |

## 5. Refusal-record template

```text
bridge_id: <UUID v4>
proposal_run_id: <shadow run id>
evidence_identity_sha256: <hex>
schema_version: shadow-evidence-v2
cost_schedule_version: ZERODHA_NSE_EQUITY_INTRADAY_AS_OF_2026-08-10
code_revision: <git sha of the comparison>
decided_at_utc: <ISO 8601>
decided_by: <operator identifier>
authorisation_state: REFUSED
gates_unsatisfied:
  - <gate name>: <one-line reason>
notes: <optional operator notes; never secrets>
```

A refusal record is *append-only*. Editing it to "approve later" is not permitted; the path is to issue a new bridge with `APPROVED_*` state.

## 6. Gating chain

A bridge can advance through states only in the order:

`UNSIGNED → REFUSED`
`UNSIGNED → APPROVED_WITH_BUDGET`
`UNSIGNED → APPROVED_LIVE_BUDGET`

Transitions are forward-only. A bridge may be superseded by a new bridge with a new `bridge_id`, but the old bridge record is preserved (never deleted) for audit. This is the ledger-style invariant.

## 7. Interactions with non-G workstreams

- **F (accounting truth)**: APPROVED_LIVE_BUDGET requires F's reconciled P&L for the prior period for the same account. A bridge issued without F produces a `REQUIRES_F_RECONCILIATION` advisory, but is not blocked at UNSIGNED.
- **D (release / operational evidence)**: APPROVED_LIVE_BUDGET requires a production observation window (per §15 ordering) where the comparison was reproducible. This is the user's call.
- **E (partner activation)**: a G-promoted strategy is *not* automatically a partner deliverable. A successful APPROVED_WITH_BUDGET cycle is **at most one input** to E; E has its own seven-gate checklist (`docs/NEXT_AGENT_PLAN.md` §9).
- **J (CAS / session-phase)**: if J lands and changes session semantics *after* a bridge is signed, the bridge's `schema_version` and `cost_schedule_version` may become stale. No re-issue is automatic; operators can re-evaluate by issuing a new bridge.
- **I (optional AI)**: AI verdicts may annotate a bridge (e.g. "the comparison looks suspect") but cannot change its `authorisation_state`. State changes are operator-led.

## 8. Open questions that block signing

The bridge is currently `UNSIGNED` for all live candidate strategies. To sign `APPROVED_WITH_BUDGET` for hypothesis #1 (bounded pullback), the following must be true:

1. Six gaps from `2026-09-13-workflow-g-state-of-codebase-audit.md` §6 closed (or a documented waiver).
2. A held-out comparison report has been generated with `code_revision` matching today's DEV branch and frozen in `docs/research/`.
3. The user has declared an explicit loss tolerance and maximum drawdown in the user profile.
4. The user's `INITIAL_BANKROLL` has been captured as a downstream cap (the research budget cannot exceed this).

Items 3 and 4 require user input — without them, **APPROVED_WITH_BUDGET cannot be granted.** A junior coder cannot fill these in on the user's behalf.

## 9. What this contract deliberately does NOT define

This contract is deliberately smaller than a full position-management policy:

- It does not define position-sizing rules. Those live in `risk_engine.py` and are per-strategy.
- It does not define drawdown-progression rules. Those are user-driven via risk tolerance.
- It does not define exit logic. That is `momentum_exits.py` / `chandelier_stop.py`, not G.
- It does not define the testing infrastructure beyond the comparison report.

Adding any of these here expands scope creep and re-implements work elsewhere. **If you find yourself wanting a new clause, place it in the right module instead.**

## 10. File/template persistence location

Refusal and approval records are persisted by `python-engine/promotion_bridge.py` into `promotion_bridges.db` (separate file from `cache.db`, located at `<settings.DB_PATH parent>/promotion_bridges.db`). The schema is two tables:

- `promotion_bridges` — one row per `bridge_id`, holding the seven required fields plus the four optional budget fields and the bridge-schema version `promotion-bridge-v1`.
- `promotion_bridge_transitions` — append-only audit log of every state change; `previous_state NULL` for the original `UNSIGNED` write; subsequent state changes append, never update the bridge row.

An unsigned record may exist and explicitly predeclare immutable budget fields. `persist_bridge(db_path, decision)` writes the initial record; `transition_bridge(...)` appends the one terminal directed decision under a serialized latest-state check. Approved transitions require relevant amount/DD/integer expiry inside the original-clock validity window; they cannot extend it. Markdown is a human template, not executable authorization or validated evidence. No current record grants live permission; stored signer strings are not an authenticated operator identity proof.

## 11. Status

This document defines the contract. The persistence surface (`promotion_bridge.py` + `tests/test_promotion_bridge.py`, 30 tests) is implemented on `codex/production-correction-hedge-p0` after `8c15ad6`. **Signing remains UNSIGNED for every live candidate**: no operator has yet issued a `BridgeDecision`, and the actual `INITIAL_BANKROLL` cap and loss tolerance required by §8 are still pending user input. Implementation follows AGENTS.md §16 and references this document by name.

Verification (Dev, September 13): contract-documenting commit `16fd6af`; the persistence+state-machine commit on the same branch ran the focused 30-test suite (`python-engine/tests/test_promotion_bridge.py`, 30/30 pass) and the whole-engine Python suite: 2,604 passed/4 skipped/23 warnings in 123.04s (was 2,574 before this commit, +30 net = the new promotion-bridge tests, no regression to the previously closed 17 baseline failures). Future signing events follow AGENTS.md §16 and reference this document by name.
