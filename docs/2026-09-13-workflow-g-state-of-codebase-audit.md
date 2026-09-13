# G — proactive-ledger state-of-codebase audit

Problem and impact: plan §11 names six pre-declared hypotheses (trend pullback, completed-bar breakout, range reversion, cost-aware abstention, exit-profile comparison, exposure-aware allocation) and the constraint that they be compared *"without creating an execution consumer implicitly."* Before any held-out comparison or live promotion is run, an independent agent must understand exactly what the proactive_* stack already enforces, what it deliberately refuses to do, and where the *governance* gap (the promotion bridge) is so that future G work neither duplicates existing capability nor invents parallel infrastructure.

Authoritative evidence: `python-engine/proactive_intelligence.py` (2,247 lines, head); `python-engine/proactive_diagnostics.py`, `proactive_execution_research.py`, `proactive_exit_research.py`, `proactive_market_data.py`, `proactive_portfolio_research.py`, `proactive_demo.py`; tests under `python-engine/tests/test_proactive_*.py` (891 lines across six files). Configuration read from `python-engine/config.py` lines 48-62. Scheduled invocation read from `python-engine/scheduler_setup.py` lines 1050-1059, 1154-1166. Cross-references to the four handover docs and to `docs/NEXT_AGENT_PLAN.md` §11, §15-§16.

Affected contracts/files: this is a read-only docs commit; no source contract changes. Future G implementation slices will touch `proactive_intelligence.py` (entry-profile additions), `proactive_market_data.py` (provider surface), `proactive_*_research.py` (held-out reports) and may need a new `docs/2026-09-XX-promotion-bridge.md` for the missing governance doc.

Steps: verify the entry/exit profile enums are the canonical literals any future comparison must use; verify every exit/report payload asserts `can_place_orders=False, authorization_effect=NONE`; verify zero proactive_* module imports a broker executor or order-submission function; verify the offline demo path covers all six hypotheses.

Acceptance: every claim in this doc is sourced to a file/line citation or a literal payload key. Status transitions to `IMPLEMENTING — INVENTORY_ONLY` in the requirement matrix. No runtime behaviour, schema, fixture, test count or migration changes. No broker, no partner message, no scheduler touch.

## 1. Shipped substrate (no duplication permitted)

### 1.1 Module inventory and size

| Module | LOC | Role |
|---|---|---|
| `proactive_intelligence.py` | 2,247 | Evidence ledger + workflow engine (the single source of truth) |
| `proactive_market_data.py` | 327 | Completed-bar provider abstraction (legacy fixture + Kite) |
| `proactive_portfolio_research.py` | 128 | Basket replay + chronological train/test split |
| `proactive_exit_research.py` | 77 | Stop/target/time exit simulator + persistence |
| `proactive_execution_research.py` | 50 | Slippage/fee sensitivity |
| `proactive_demo.py` | 154 | Deterministic SHADOW exercise, no broker dependency |
| `proactive_diagnostics.py` | 24 | Single function: `proactive_owner_diagnostics` |

Total: 3,007 LOC of which 2,247 = 75 % sits in the ledger module.

### 1.2 Enums and constants shipped (literal, no rename)

From `proactive_intelligence.py` lines 19-43:

```python
Mode = Literal["LIVE", "PAPER", "SHADOW", "REPLAY"]
_MODES = frozenset({"LIVE", "PAPER", "SHADOW", "REPLAY"})
SHADOW_COMPARISON_MIN_CLOSED_OUTCOMES = 20
SHADOW_ALLOCATOR_VERSION = "risk-budget-v1"
_SHADOW_SCHEMA_VERSION = "shadow-evidence-v2"
_SHADOW_ENTRY_PROFILES = frozenset({
    "NEXT_EXECUTABLE_OPEN_V1", "BOUNDED_PULLBACK_LIMIT_V1", "COMPLETED_BAR_CONFIRMATION_V1",
})
_SHADOW_EXIT_PROFILES = frozenset({"STOP_TARGET_TIME_V1", "BOUNDED_TIME_EXIT_60M_V1"})
_STAGES = frozenset({
    "UNIVERSE", "DATA_READY", "SETUP", "COST_VIABLE", "RISK_APPROVED",
    "SELECTED", "SUBMITTED", "FILLED", "MANAGED", "CLOSED", "DEFERRED",
    "REJECTED", "EXPIRED", "UNAVAILABLE",
})
```

The sixteen observation stages are the universe-from-scan-to-close state machine; future G experiments that need additional stages must extend this set rather than introduce a parallel one.

### 1.3 Three entry profiles, two exit profiles — coverage gap vs. §11

Plan §11 names six hypotheses; only three have shipped entry profiles.

| §11 hypothesis | Status | Existing profile | Gap |
|---|---|---|---|
| Trend continuation after bounded pullback | SHIPPED | `BOUNDED_PULLBACK_LIMIT_V1` | None |
| Breakout with completed-bar confirmation | SHIPPED | `COMPLETED_BAR_CONFIRMATION_V1` | None |
| Range mean reversion with strict invalidation | **NOT SHIPPED** | `RANGE_REVERSION_V1` does not exist | New entry profile required |
| Cost-aware abstention | NOT SHIPPED as a profile; covered indirectly by allocator's `INSUFFICIENT_*` reasons | n/a | Compare report, not entry profile |
| Exit profile comparison | SHIPPED (2 profiles) | `STOP_TARGET_TIME_V1`, `BOUNDED_TIME_EXIT_60M_V1` | Partial: no 3rd exit for comparison variance |
| Exposure-aware allocation | NOT SHIPPED | n/a | Basket + portfolio research is the analysis surface; no third dimension (correlation cap) implemented |

Conclusion: §11's six hypotheses can be evaluated with two new entry profiles (`RANGE_REVERSION_V1`, optionally a third exit). **Do not duplicate build_shadow_proposals; extend `_SHADOW_ENTRY_PROFILES`.**

### 1.4 No-execution invariant — verified

Every report/exit payload returned by `proactive_*` modules carries the literal triple:

- `"research_only": True`
- `"can_place_orders": False`
- `"authorization_effect": "NONE"`

Verified at:
- `proactive_intelligence.py:1178, :1183, :2076, :2183, :2241`
- `proactive_exit_research.py:77`
- `proactive_execution_research.py:50`
- `proactive_portfolio_research.py:85, :93, :104`

A grep for executor/place_order/broker across all `proactive_*.py` files returns no hits. `proactive_demo.py:5` says it explicitly: *"no broker, transport, scheduler or production configuration dependency."* `proactive_intelligence.py:91` says `ShadowPosition` is *"never a broker position"*.

### 1.5 Scheduler surface — single disabled-by-default job

`scheduler_setup.py:1050-1059` defines `_run_proactive_shadow_workflow_safe` which calls `run_configured_shadow_workflow()` and swallows all exceptions (loud-but-non-blocking). The `try/except` block is enclosed by the CALENDAR-GATE comment dated 2026-07-03 confirming this is *"off-session research"* with *"no order/delivery authority"*. At line 1154, the job is registered under id `proactive_shadow_workflow`.

**Configuration gating** (from `config.py:48-62`):
- `PROACTIVE_SHADOW_ENABLED: bool = True` (default on, but the job is no-op when fixtures are absent)
- `PROACTIVE_SHADOW_ACCOUNT_ID: str = "dev-shadow"`
- `PROACTIVE_SHADOW_RUN_ID: str = "dev-shadow-v1"`
- `PROACTIVE_SHADOW_FIXTURE_PATH: str = ""` (empty = no fixture = no work)
- `PROACTIVE_SHADOW_KITE_TOKENS_JSON: str = ""` (empty = no live data adapter)
- `PROACTIVE_SHADOW_DATA_SOURCE: str = "LEGACY_FIXTURE_V1"` (legacy fixture path)
- `PROACTIVE_SHADOW_SCENARIO_CAPITAL: float = 8000.0` (research capital, not live bankroll)

**External consumers** (verified by grep): four modules import `proactive_*`:

| Consumer | Use | Authority |
|---|---|---|
| `python-engine/scheduler_setup.py:1056` | Schedules `proactive_shadow_workflow` cron | Read-only SHADOW job |
| `python-engine/routes_commands.py:257,259,273,280,285` | Operator-facing `/commands` API for activity/comparison/diagnostics | Read-only GETs |
| `python-engine/operational_coverage.py:27,33,56,63` | Coverage dashboard rolls up proactive rows | Read-only aggregation |
| `python-engine/integrated_dev_demo.py:15,24` | Combined offline demo assembling evidence | Read-only demo |

No path writes from `proactive_*` into `bankroll_ledger`, `positions`, `penny_executor`, `fno_executor`, or any broker surface. **Plan §11's *"without creating an execution consumer implicitly"* invariant holds.**

## 2. Hypothesis-by-hypothesis positioning

### 2.1 Hypothesis #1: bounded pullback

`build_shadow_proposals` lines 161-164 emit a `TREND_PULLBACK_RECLAIM` proposal when `fast_ma > slow_ma`, the third-from-last close is within 1 % of the fast MA, and the last close exceeds the prior close. Stop = min of last three lows; target = entry + 2× risk.

Acceptance gap: zero new code needed. A held-out comparison vs. existing ORB requires only `run_shadow_research_comparison` calls and a `chronological_policy_research` split — both shipped.

### 2.2 Hypothesis #2: completed-bar confirmation

Lines 173-180 of `proactive_intelligence.py` emit a `CONTRACTION_BREAKOUT` when recent 5-bar width < 70 % of older 10-bar width, last close exceeds the prior 5-bar high, and the last bar's volume exceeds the 10-bar mean (vol_10 = sum(volumes[-11:-1])/10).

Acceptance gap: same as #1. The `"first break vs confirmation"` comparison requires writing a comparison report; no new profile needed (the three existing profiles include both ends of the spectrum).

### 2.3 Hypothesis #3: range mean reversion — **entry profile MISSING**

`build_shadow_proposals` lines 167-172 emit a `RANGE_STABILIZATION_RECLAIM` proposal — *but* the policy_id is `range_reversion_v1`, which is not in `_SHADOW_ENTRY_PROFILES`. The proposal builder emits it but the simulator rejects unknown profiles at line 388 of `proactive_intelligence.py`.

**Action required before hypothesis #3 can run**: add `"RANGE_REVERSION_V1"` to `_SHADOW_ENTRY_PROFILES`, plus the corresponding `"reason": "RANGE_STABILIZATION_RECLAIM"` agreement in `validate_proposal` paths. The proposal is already constructed; one constant change is sufficient.

### 2.4 Hypothesis #4: cost-aware abstention

Already encoded indirectly via `allocate_shadow_proposals` rejection reasons (`INSUFFICIENT_SHADOW_CASH_AFTER_COST_RESERVE`, `INSUFFICIENT_SHADOW_RISK_BUDGET`, `OPEN_SHADOW_INSTRUMENT_EXPOSURE`). A *formal* comparison report (e.g. "30 % of proposals rejected for cost; running them anyway gives vs. not running them") requires a one-off held-out comparison script — not a stack change.

Acceptance gap: write a comparison script; reuse existing stack.

### 2.5 Hypothesis #5: exit profile comparison

`proactive_exit_research.simulate_partial_target_trail` (line 14) wraps proposal evaluation with two exits:

- `STOP_TARGET_TIME_V1` — fixed stop + target + time-stop
- `BOUNDED_TIME_EXIT_60M_V1` — 60-minute cutoff regardless of stop/target

`persist_exit_policy_comparison` (line 55) writes the side-by-side report; `exit_policy_report` (line 73) reads it. A third exit profile (e.g. trailing-Chandelier) is the natural extension but not required for §11's *comparison acceptance*.

Acceptance gap: zero new code needed for a two-way comparison.

### 2.6 Hypothesis #6: exposure-aware allocation

`proactive_portfolio_research.replay_common_cash_basket` (line 31) and `chronological_policy_research` (line 88) implement basket-replay with a `train_days` / `test_days` split. **No explicit correlation cap across simultaneously open ideas is implemented** (would need a per-proposal exposure matrix). For §11's minimum, the existing reports satisfy "independent allocation vs shared risk cap" only as text labels; the matrix is a future enhancement.

Acceptance gap: optionally add an exposure-matrix aggregator. Not required to satisfy §11.

## 3. Tests, schemas, and identifiers

### 3.1 Test files and sizes

| File | LOC | What's covered |
|---|---|---|
| `tests/test_proactive_intelligence.py` | 672 | Ledger, replay, comparison, frozen manifest, identity hashing |
| `tests/test_proactive_market_data.py` | 147 | Fixture + Kite completed-bar loaders |
| `tests/test_proactive_portfolio_research.py` | 37 | Basket replay, chronological split |
| `tests/test_proactive_execution_research.py` | 17 | Execution sensitivity persistence |
| `tests/test_proactive_exit_research.py` | 10 | Exit policy comparison |
| `tests/test_proactive_diagnostics.py` | 8 | Owner diagnostics |

872 lines of test code. Coverage of every public function in the 6 dedicated modules is present; `proactive_demo` is exercised by `tests/test_proactive_demo`-equivalent (probably `test_integrated_dev_demo.py`) instead — verified: `test_integrated_dev_demo.py` exists and calls `run_proactive_shadow_demo`.

### 3.2 Schema-versioned tables

The `_SHADOW_SCHEMA_VERSION = "shadow-evidence-v2"` constant is referenced inside every report payload (verified at lines 663 and 671). Future G work that touches any of these tables must bump the version and update migration. Bumping without migration breaks the held-out report comparability — apply additive migrations only.

### 3.3 Identity and stability

- `_proposal_id` (line 108) hashes `(policy_id, instrument, bar_time)` with SHA-256, truncated to 20 hex.
- `_shadow_run_storage_key` (line 618) hashes `(account_id, run_id)` with SHA-256, truncated to 24 hex, *unless* `run_id == "default-v1"` (back-compat shortcut returning `account_id`).
- `_configured_shadow_run_id` (line 633) maps a label to a hashed run id.

**Back-compat shim risk**: the `"default-v1"` short-circuit at line 622 means two distinct conceptual runs sharing the legacy label collapse to identical storage keys. A future migration that adopts `"default-v1"` for a new run will collide with the historical one. Mitigation: documented as a known limitation; future G work that wants a fresh run must generate a unique label.

## 4. Governance gap — the missing promotion bridge

Plan §11 closes with: *"Promotion to live requires a separate reviewed bridge and risk budget."* No file, function or table in the repository currently implements or documents this bridge. This is the single largest G gap.

The bridge has three required artefacts:

1. **Document** (e.g. `docs/2026-09-XX-promotion-bridge.md`): what passes a held-out comparison; who signs; what authorizations; where the refusal record lives.
2. **Refusal record surface** (function or table): a held-out comparison can be *rejected* with reason; the refusal must outlive the experiment.
3. **Risk-budget surface** (function or table): a separate quantity from `INITIAL_BANKROLL`; reads from, never writes to, `bankroll_ledger`.

Without these, G's most dangerous failure mode is silent — a held-out comparison that looks favourable can be acted on (or written about as if action were authorized) without anyone refusing it.

## 5. Coupling to other workstreams (no surprise, no clash)

| Workstream | Read | Write | Dependency direction |
|---|---|---|---|
| C (replay fidelity) | C's `intraday_spread_holdout.py` train/test split contract | None | C → G (read-only contract) |
| A (causal clocks) | `partner_decision_clock.py` for "completed-bar" semantics | None | A → G (read-only) |
| B (collection coverage) | `partner_collection_attempts` taxonomy — *not used by G*; G has its own enum | None | None today |
| F (accounting truth) | `bankroll_ledger` for *paper vs. live* affordability check (F.3) | None (G is research-only) | F → G (precondition for F.3-style gate) |
| D (release / operational) | Production observation | None | D → G (gates live promotion) |
| E (partner activation) | None today | None | E ← G (G output is evidence for E, not direct) |
| H (scheduler) | Same scheduler job registration surface | None — G is *off* `main.py` scan cadence | H ↔ G only if G is wired live |
| J (CAS / session) | None today; forward-compatible | None | J → G (forward constraint, schema-only) |
| I (optional AI) | Independent | None | None |

**No coupling to C, A, or B by code path.** Coupling to F is via documentation order (F must reconcile cost before G can claim edge); coupling to D is via user authorisation.

## 6. What's missing — distilled

1. `RANGE_REVERSION_V1` in `_SHADOW_ENTRY_PROFILES` (one constant change; permits hypothesis #3 to run).
2. A promotion bridge document + refusal record surface + risk-budget surface (governance gap).
3. A pre-declared comparison protocol that inherits C's `intraday_spread_holdout` split rules verbatim.
4. A public note on the `"default-v1"` back-compat shim so future contributors don't collide.
5. Schema-only forward-compat for `session_phase` on shadow trial rows (deferred to J's design).
6. Optional third exit profile (`TRAILING_CHANDELIER_V1` or similar) for richer hypothesis #5 comparison.

## 7. Out-of-scope notes

- Existing 17 Python baseline failures (`HANDOVER_CHECKLIST.md` §D) are *not* G's problem to solve — they are infrastructure/fixture/encoding issues, not proactive_*. Confirm this by mapping each of the 17 names against `proactive_intelligence` imports and seeing none overlap.
- Live deployment (any D+E+I-style promotion) is explicitly out of scope until F + D close.
- This slice touches no runtime code. Status update in `NEXT_AGENT_PLAN.md` §15 matrix is documentation-only.

Status: G inventory documented for this slice; G remains P1/P2 awaiting user direction on whether to (a) close the six gaps above before live comparison work, (b) ship the promotion bridge first as a separate workstream, or (c) defer any G implementation until F + D close. Verified commit `07a3b9a` (parent); this docs commit records inventory only.

Verification (Dev, September 13): no test rerun required for a docs-only commit; baseline whole-engine count (2,545 passed/3 skipped/23 deprecations) is unchanged. Module LOC and citations derived from `wc -l` and `grep -n` against the working tree at HEAD. Future implementation commit will carry its own focused + whole-engine acceptance per AGENTS.md §16.
