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
| Range mean reversion with strict invalidation | PARTIAL (constant only) | `RANGE_REVERSION_V1` — see update at §6 | Closed: profile accepted by dispatcher; **dedicated range-mean-reversion simulator still required for faithful semantics** |
| Cost-aware abstention | NOT SHIPPED as a profile; covered indirectly by allocator's `INSUFFICIENT_*` reasons | n/a | Compare report, not entry profile |
| Exit profile comparison | SHIPPED (3 profiles) | `STOP_TARGET_TIME_V1`, `BOUNDED_TIME_EXIT_60M_V1`, `TRAILING_STOP_V1` | Three orthogonal axes covered; `persist_exit_policy_comparison` emits three rows per run |
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

### 2.3 Hypothesis #3: range mean reversion — *partially closed (constant only, 2026-09-13 commit)*

`build_shadow_proposals` lines 167-172 emit a `RANGE_STABILIZATION_RECLAIM` proposal with `policy_id="range_reversion_v1"`. The proposal was always constructible but `simulate_shadow_research_trial` (line 388) raised `ValueError("unsupported shadow research profile")` because the policy_id was not in `_SHADOW_ENTRY_PROFILES`. Closing the dispatch gap required one string literal in the frozenset. The proposal is already constructed; one constant change is sufficient. **The closure landed in the second commit on `codex/production-correction-hedge-p0`, parent `16fd6af`:** `"RANGE_REVERSION_V1"` added to `_SHADOW_ENTRY_PROFILES`, plus a 5-test focused suite (`tests/test_range_reversion_profile.py`) proving proposal emit, allocator accept, dispatcher enum-check pass and a negative-control (unknown profile id still raises). The existing neighbour tests were made future-proof by deriving their comparison counts from the same constants rather than hard-coding 6/8.

**Historical residual, superseded by G.3/G.7**: the constant-only dispatcher originally routed `RANGE_REVERSION_V1` through completed-bar confirmation. G.3 added a dedicated verifier; G.7 (`2026-09-19-g7-range-comparison-causality-plan.md`) corrects its later-bar lookahead, insufficient-history fallback and stale comparison alias gate. New evidence must be frozen under the corrected implementation identity; old reports are not reinterpreted.

### 2.4 Hypothesis #4: cost-aware abstention

Already encoded indirectly via `allocate_shadow_proposals` rejection reasons (`INSUFFICIENT_SHADOW_CASH_AFTER_COST_RESERVE`, `INSUFFICIENT_SHADOW_RISK_BUDGET`, `OPEN_SHADOW_INSTRUMENT_EXPOSURE`). A *formal* comparison report (e.g. "30 % of proposals rejected for cost; running them anyway gives vs. not running them") requires a one-off held-out comparison script — not a stack change.

Acceptance gap: write a comparison script; reuse existing stack.

### 2.5 Hypothesis #5: exit profile comparison

`proactive_exit_research.simulate_partial_target_trail` (line 14) wraps proposal evaluation with three exits today (after this commit):

- `STOP_TARGET_TIME_V1` — fixed stop + target + time-stop (`simulate_shadow_trade`)
- `BOUNDED_TIME_EXIT_60M_V1` — 60-minute cutoff regardless of stop/target (deadline-tweaked variant of `STOP_TARGET_TIME_V1`)
- `TRAILING_STOP_V1` — Chandelier-style trailing stop with ``max(initial_stop, high - entry_risk)`` ratchet; new entry-bar high applies to *next* bar to avoid look-ahead (`python-engine/proactive_intelligence.py::_simulate_shadow_trailing_stop`, added 2026-09-13)

`persist_exit_policy_comparison` (line 55) writes a side-by-side report with one row per exit profile; `exit_policy_report` (line 73) reads it. With `TRAILING_STOP_V1` shipped, hypothesis #5 has three orthogonal points on the matrix: fixed stop/target, time-bounded, and ratcheting trailing. The fourth exit dimension (correlation with entry profile) lives at the higher cross of (`persisted_trials` rows × entry-profiles × exit-profiles = 4 × 3 = 12) available via `proactive_shadow_research_report`.

Acceptance gap: zero new code needed for a three-way comparison; a one-off comparison report can now be authored without further simulator changes.

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
- `_shadow_run_storage_key` (line 692) hashes `(account_id, run_id)` with SHA-256, truncated to 24 hex, *unless* `run_id == LEGACY_DEFAULT_V1_RUN_ID` (back-compat shortcut returning `account_id`). The constant `LEGACY_DEFAULT_V1_RUN_ID = "default-v1"` was centralised at line 40 on 2026-09-13 so the magic string has exactly one source of truth (the in-module grep test in `tests/test_legacy_run_id_shim.py::test_internal_usage_references_named_constant` enforces this).
- `_configured_shadow_run_id` (line 722) maps a label to a hashed run id (never re-introduces the bare `"default-v1"` literal).

**Back-compat shim risk (still open, now codified rather than mitigated)**: the legacy short-circuit at `_shadow_run_storage_key` line 692 means two distinct conceptual runs sharing the legacy label collapse to identical storage keys. A future migration that adopts `"default-v1"` for a new run will collide with the historical one. The constant `LEGACY_DEFAULT_V1_RUN_ID` and its three call sites make the constraint greppable; *do not* call `_shadow_run_storage_key` with this id from any new code path. Configured-runner callers (`run_shadow_workflow`, `run_shadow_replay`) keep the legacy default to preserve historical evidence readability but must opt into a fresh lineage via `_configured_shadow_run_id` whenever migration is in scope.

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

1. ~~`RANGE_REVERSION_V1` in `_SHADOW_ENTRY_PROFILES` (one constant change; permits hypothesis #3 to run).~~ **CLOSED 2026-09-13** (constant landed; focused 5-test suite in `tests/test_range_reversion_profile.py`; demo + neighbour tests made future-proof by deriving counts from `_SHADOW_ENTRY_PROFILES` and `_SHADOW_EXIT_PROFILES`). **Residual**: a *dedicated* range-mean-reversion simulator is still missing — the dispatcher currently routes `RANGE_REVERSION_V1` through the completed-bar-confirmation fallback, which is not a faithful interpretation. See §2.3 update.
2. ~~A promotion bridge document + refusal record surface + risk-budget surface (governance gap).~~ **CLOSED 2026-09-13 (persistence + state machine, refusal surface + risk-budget fields implemented; signing still NOT carried out by anyone)** — see `python-engine/promotion_bridge.py` and `python-engine/tests/test_promotion_bridge.py` (30 tests covering field validation, version guards, append-only, forward-only state machine, read fail-closed, G invariant triple, budget bounds, evidence-identity hashing). **Residual**: no operator has actually signed a bridge; the contract remains `UNSIGNED` until user input declares loss tolerance and `INITIAL_BANKROLL` cap.
3. ~~Optional third exit profile (`TRAILING_STOP_V1` or similar) for richer hypothesis #5 comparison.~~ **CLOSED 2026-09-13** (`python-engine/proactive_intelligence.py` adds `TRAILING_STOP_V1` to `_SHADOW_EXIT_PROFILES`, a dedicated `_simulate_shadow_trailing_stop` simulator with a Chandelier-style ratcheting stop, an explicit dispatcher branch in `simulate_shadow_research_trial`, and a third comparison row in `proactive_exit_research.persist_exit_policy_comparison`. Focused 8-test suite at `tests/test_trailing_stop_profile.py` proves constant shipped, dispatcher accept / negative-control, three exit-reason outcomes (TRAILING_STOP after a ratchet-raising bar, TRAILING_STOP on initial-stop breach, HOLDING_DEADLINE), and a **look-ahead safety** test that verifies the entry bar's high does *not* raise the trailing level above the initial stop before the exit check fires.)
4. A pre-declared comparison protocol that inherits C's `intraday_spread_holdout` split rules verbatim.
5. ~~A public note on the `"default-v1"` back-compat shim so future contributors don't collide.~~ **CLOSED 2026-09-13** (named constant `LEGACY_DEFAULT_V1_RUN_ID = "default-v1"` introduced at `python-engine/proactive_intelligence.py:34`; three former magic-string sites — the `_shadow_run_storage_key` short-circuit, `run_shadow_workflow`'s default, and `run_shadow_replay`'s default — now import the constant; `_shadow_run_storage_key`'s docstring expanded to describe the contract and cite audit §3.3; focused 9-test suite at `python-engine/tests/test_legacy_run_id_shim.py` proves (a) the literal value is preserved, (b) the storage-key short-circuit behaviour is preserved including the documented collision risk, (c) non-legacy ids continue to use the hashed form, (d) `_configured_shadow_run_id` never returns the legacy id, (e) a smoke test grep fails if the bare literal reappears anywhere else in the module source.)
6. ~~Schema-only forward-compat for `session_phase` on shadow trial rows (deferred to J's design).~~ **CLOSED 2026-09-13 as a typed placeholder, NOT as a schema column.** Plan §14 puts J (CAS / market-session correctness) ahead of any session-aware G rollout; J will own the canonical NSE/BSE/SEBI phase inventory. To avoid pre-determining J's schema, G commits: a module-level constant `_SESSION_PHASE_UNKNOWN = "UNKNOWN"` (declarative single source of truth), a pure helper `stamp_session_phase(*, observation_at) -> str` whose keyword-only signature is shaped for J's eventual classifier, and a `session_phase` key injected into both run manifests (`run_shadow_workflow`, `run_shadow_research_comparison`). **No DB schema change.** A 9-test focused suite at `python-engine/tests/test_session_phase_placeholder.py` proves (a) the constant value, (b) the helper is pure and total, (c) the helper signature uses a keyword-only `observation_at` so future callers must supply it explicitly, (d) both manifests now carry the placeholder. When J lands, replacing the helper body to return real phase strings is the only code change required. **Residual**: J's actual classifier and the additive migration to `proactive_shadow_research_trials.session_phase` (the columns where the value ought to be queryable) are still J-owned; this slice is the G-side seam, not the J-side schema.

## 7. Out-of-scope notes

- Existing 17 Python baseline failures (`HANDOVER_CHECKLIST.md` §D) are *not* G's problem to solve — they are infrastructure/fixture/encoding issues, not proactive_*. Confirm this by mapping each of the 17 names against `proactive_intelligence` imports and seeing none overlap.
- Live deployment (any D+E+I-style promotion) is explicitly out of scope until F + D close.
- This slice touches no runtime code. Status update in `NEXT_AGENT_PLAN.md` §15 matrix is documentation-only.

Status: G inventory documented at commits `16fd6af` (audit/bridge docs), `8c15ad6` (range-reversion constant), `877fae6` (promotion bridge persistence + state machine), `b2efc44` (trailing-stop exit profile), `f4a4a1e` (legacy-run-id shim), and the session-phase placeholder (this commit). G is **DOCUMENTED_INVENTORY_COMPLETE — six of six gaps closed** with the two outstanding residuals (range-reversion simulator, bridge signing) and one J-dependent seam (the session-phase schema column). Future user direction needed on whether to (a) wait for J's classifier and add the schema column itself, (b) close the dedicated range-mean-reversion simulator for hypothesis #3, or (c) defer any further G implementation until F + D close. Verified audit commit `16fd6af`; constant-change commit `8c15ad6`; bridge commit `877fae6`; trailing-stop commit `b2efc44`; shim commit `f4a4a1e`; session-phase commit SHA will be added when committed.

Verification (Dev, September 13): docs-only at `16fd6af` (no test rerun required). The constant-change commit (the next commit on `codex/production-correction-hedge-p0`) ran the focused 5-test suite (5/5 pass) and the whole-engine Python suite: 2,574 passed (was 2,545), 4 skipped (was 3), 23 warnings, in 122.52s. The +29 net passing tests = 5 new in `test_range_reversion_profile.py` plus 24 comparison-trial rows now generated across the existing suite because `_SHADOW_ENTRY_PROFILES` grew from 3 to 4. **No regression** to the previously closed 17 baseline failures; no new warnings.
