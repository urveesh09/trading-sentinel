# Inheritance — from this session to the next (J.2 continues here)

## What this document is

A **handoff binder** so the next session can pick up exactly where this
one left off without hallucinating. It records:

  1. The current state of the system (what works, what was just shipped).
  2. The exact files I touched in J.1 with line ranges and what they do.
  3. The exact baseline test counts so the next session can verify "I
     didn't break anything."
  4. The session-search anchors for the full conversation history.
  5. The J.2 plan — what to build next, why, and how.
  6. The list of files I did NOT touch and why (to prevent re-work).
  7. The system documentation that already exists.

Read this top to bottom before doing anything else. Do **not** start
J.2 without first reading the J.1 deep-research doc and the J.1 plan
slice — they contain the verified NSE/BSE facts and the classifier
contract.

---

## 1. The current state — what is shipped and what is not

### Workstreams shipped in this branch (`codex/production-correction-hedge-p0`)

| Workstream | Status | My commits (HEAD range) |
|---|---|---|
| **H1** scheduler coroutine guard | DONE | `dc298e5` + `14961e9` |
| **H2** priority-tier breakdown | DONE | `52f625e` + `23f332a` |
| **H3** intraday-cache diagnostic | DONE | `fead40c` + `9780109` |
| **H4** four-semantics cache-add for `get_intraday` | DONE | `d1d6e15` + `2734851` |
| **H4.B** four-semantics cache-add for `get_intraday_by_token` | DONE | `bfb42ac` + `2b992b8` |
| **H5** dashboard readiness vocabulary | DONE | `b9cfc44` + `46e0e54` |
| **I1** model/prompt/version provenance + response time | DONE | `4ea9b54` |
| **I2** news provenance (publication timestamps + source URLs) | DONE | `33d780c` |
| **I3** usefulness-instrumentation snapshot + bounded CLI | DONE | `f35d859` |
| **I.A** bridge I3 usefulness metrics to engine | DONE | `980636e` + `65d4bfe` |
| **I.B** surface I1 provenance in alert banner | DONE | `d1e7d4f` + `9bd5286` |
| **I.C** operational_coverage_report includes optional AI | DONE | `89a9804` + `c47941e` |
| **I.F** cross-container contract test (agent↔engine) | DONE | `a226ec3` + `0f7120b` |
| **J.1** CAS-aware session classifier | DONE | `d82258f` + `63a98ab` |

### Workstreams NOT in this branch (parallel agent owns them)

| Workstream | Owner | Status | Do NOT touch without coordinating |
|---|---|---|---|
| **F** trading losses & accounting truth | Parallel agent | IMPLEMENTING (F1-F6 done; provenance corrections pending) | `python-engine/affordability.py`, `mark_to_market.py`, `discrepancies.py`, `reconciliation_cli.py`, `capital_policy.py` |
| **G** strategy basket & entry/exit intelligence | Parallel agent | IMPLEMENTING (5/6 gaps closed) | `python-engine/promotion_bridge.py`, `proactive_intelligence.py`, `proactive_exit_research.py`, `proactive_execution_research.py`, `proactive_portfolio_research.py`, `cost_schedules.py`, `broker_reconciliation.py`, `reconciliation_evidence.py` |
| **A/B/C** | Both | TESTED_DEV (awaiting D release for RELEASE_VALIDATED) | — |
| **D** release/operational evidence | Both | IMPLEMENTING (real backup/restore/PROD release pending) | — |
| **E** partner activation/usefulness | Both | EVIDENCE_PENDING | — |
| **J.2+** CAS eligibility list + broker probe | **NEXT SESSION** | J.1 just shipped; J.2 is the next slice | — |

### Test baseline (as of HEAD `63a98ab`)

| Suite | Pass | Skip | Warn | Time | Notes |
|---|---|---|---|---|---|
| `python-engine/tests/test_market_calendar.py` | 12 | 0 | — | <1s | All existing pass |
| `python-engine/tests/test_session_phase_placeholder.py` | 8 | 0 | — | <1s | G forward-compat seam; **unchanged behaviour** |
| `python-engine/tests/test_session_classifier.py` | **41** | 0 | 0 | <1s | **NEW J.1 tests** |
| `python-engine/tests/test_calendar_gates.py` | 11 | 0 | — | <1s | Existing |
| `python-engine/tests/test_calendar_and_band_fixes.py` | 8 | 0 | — | <1s | Existing |
| `python-engine/tests/test_penny_cron_gating.py` | (pre-existing) | — | — | — | Time-gate logic; passes |
| F/G + J critical paths (warning-fatal) | **225** | 0 | 0 | ~7s | `tests/test_F_phase1_inventory.py` + `cost_schedules` + `proactive_*` + `trailing_stop` + `promotion_bridge` + `range_reversion` + `legacy_run_id` + `session_phase_placeholder` + `market_calendar` + `session_classifier` |
| Agent whole suite | **177** | 0 | 0 | ~3s | Unchanged from I.F |
| Node dashboard build | OK | — | — | ~3s | Unchanged |
| Whole python-engine in isolation | **3,130** | 4 | 42 | ~145s | All J.1 tests pass; intermittent failures in F-series files are documented as cross-test isolation noise |

### Whole-suite cross-test isolation note (READ THIS)

When running the full `python-engine/tests` suite, **2 tests may fail
intermittently** in the same run:

  - `tests/test_mark_to_market.py::TestFnoMark::test_fresh_quote_uses_premium_multiplier`
  - `tests/test_mark_to_market.py::TestFnoDrMark::test_all_legs_fresh`
  - `tests/test_scheduler_h2_timing_tiers.py::TestOperationalCoverageTierEntry::test_coverage_includes_tier_entries`

All three **pass in isolation** when run by themselves. The failure is
documented cross-test DB-locking / asyncio-socket noise from Windows.
The parallel agent's F/G correction plan explicitly documents this as
"unclosed Windows asyncio socket during test-group transitions."

**Do not chase these failures.** The next session should run any new
tests in isolation first, then the full suite as a sanity check. If
only these specific tests fail and they pass in isolation, the work is
not regressed.

### Branch and remote state

  - Branch: `codex/production-correction-hedge-p0`
  - HEAD: `63a98ab`
  - Working tree: clean
  - 98 commits ahead of `origin/codex/production-correction-hedge-p0`
  - Local only — **not pushed**, no Production mutation

---

## 2. J.1 — what landed, file by file

### `python-engine/market_calendar.py` (+240 lines, additive)

**Imports**: unchanged. Still uses `aiosqlite`, `httpx`, `sqlite3`,
`datetime`, `time`, `structlog`, `pytz`. The `pytz.UTC` and `pytz.timezone("Asia/Kolkata")`
are the canonical IST helpers.

**Top of file constants block** (after `IST = pytz.timezone(...)`):

```python
MARKET_OPEN_TIME: time = time(9, 15)
MARKET_CLOSE_TIME: time = time(15, 30)  # cash continuous trading end
DERIVATIVES_CLOSE_TIME: time = time(15, 40)  # equity derivatives end
PRE_MARKET_OPEN_TIME: time = time(9, 0)
CAS_OPEN_TIME: time = time(15, 15)
CAS_REFERENCE_PRICE_END: time = time(15, 20)
CAS_ORDER_ENTRY_END: time = time(15, 25)
CAS_LIMIT_ENTRY_ONLY_END: time = time(15, 30)
CAS_MATCHING_END: time = time(15, 35)
CAS_POST_CLOSE_END: time = time(16, 0)
```

These are **aliases** of the existing `time(9, 15)` and `time(15, 30)`
literals inside `is_market_open()`. **Do not change `is_market_open()`
to use these constants** — the function body and its callers stay
byte-identical for behaviour preservation.

**Existing functions — UNCHANGED** (do not refactor):
  - `is_market_open()` (lines ~80-95)
  - `is_trading_day()` (lines ~109-139)
  - `next_trading_day()`, `prev_trading_day()` (lines ~141-151)
  - `_load_holidays_sync()`, `is_trading_day_sync()` (lines ~156-203)
  - `trading_days_between_sync()` (lines ~206-256)

**New symbols at end of file**:

```python
SESSION_PHASE_CLOSED: str = "CLOSED"
SESSION_PHASE_PRE_MARKET: str = "PRE_MARKET"
SESSION_PHASE_CONTINUOUS_TRADING: str = "CONTINUOUS_TRADING"
SESSION_PHASE_CAS_REFERENCE_PRICE_WINDOW: str = "CAS_REFERENCE_PRICE_WINDOW"
SESSION_PHASE_CAS_ORDER_ENTRY: str = "CAS_ORDER_ENTRY"
SESSION_PHASE_CAS_LIMIT_ENTRY_ONLY: str = "CAS_LIMIT_ENTRY_ONLY"
SESSION_PHASE_CAS_MATCHING: str = "CAS_MATCHING"
SESSION_PHASE_CAS_POST: str = "CAS_POST"
SESSION_PHASE_DERIVATIVES_CAS_ALIGNED: str = "DERIVATIVES_CAS_ALIGNED"
SESSION_PHASE_UNKNOWN: str = "UNKNOWN"

_VALID_SESSION_PHASES: frozenset = frozenset({
    SESSION_PHASE_CLOSED, SESSION_PHASE_PRE_MARKET,
    SESSION_PHASE_CONTINUOUS_TRADING,
    SESSION_PHASE_CAS_REFERENCE_PRICE_WINDOW,
    SESSION_PHASE_CAS_ORDER_ENTRY,
    SESSION_PHASE_CAS_LIMIT_ENTRY_ONLY,
    SESSION_PHASE_CAS_MATCHING,
    SESSION_PHASE_CAS_POST,
    SESSION_PHASE_DERIVATIVES_CAS_ALIGNED,
    SESSION_PHASE_UNKNOWN,
})

def _ist_clock_minutes(observation_at: datetime) -> tuple[int, int, int]: ...
def is_cas_eligible(symbol: str | None) -> bool: ...
def classify_session_phase(
    observation_at: datetime | None,
    *,
    symbol: str | None = None,
    is_derivative: bool = False,
) -> str: ...
```

**Critical: `is_cas_eligible` currently always returns `False`.** This
is by design — the Phase 1 F&O eligibility list is empty in Dev.
J.2 must populate it. The current behaviour is documented in the
function docstring as the "honest bounded default."

**Critical: `classify_session_phase` does NOT consult holidays.**
This is deliberate — phase is clock-only, holiday is a calendar
concern. Callers must combine the two if they need both.

**Critical: `stamp_session_phase` in `proactive_intelligence.py` is
UNCHANGED** (still returns `_SESSION_PHASE_UNKNOWN` for every input).
The classifier is the seam for J.2+ callers; production behaviour
is preserved exactly.

### `python-engine/tests/test_session_classifier.py` (NEW, 41 tests)

Eight test classes covering:

  1. **TestCentralSessionConstants** (10 tests): pins each constant's
     hour and minute so a typo fails CI.
  2. **TestBoundedPhaseSet** (2 tests): `_VALID_SESSION_PHASES` is
     exactly the 10 documented phases; exhaustive sampling of
     `(weekday, hour, minute, is_derivative, symbol)` never returns
     a phase outside the set.
  3. **TestOrdinaryDay** (9 tests): 09:30 / 12:00 / 14:55 / 15:00 /
     15:14:59 / 15:15 / 15:29:59 / 15:30 / 15:59:59 / 16:00 / 23:59
     IST → expected phase.
  4. **TestCASWindows** (6 tests): uses a `cas_eligible_world`
     monkeypatch fixture that forces `is_cas_eligible` to return True
     for any non-empty symbol. Tests the 5 CAS sub-windows:
     15:15-15:19 (REFERENCE_PRICE), 15:20-15:24 (ORDER_ENTRY),
     15:25-15:29 (LIMIT_ENTRY_ONLY), 15:30-15:34 (MATCHING),
     15:35-15:59 (POST). Plus a test that empty symbol stays in
     CONTINUOUS_TRADING.
  5. **TestDerivativesSession** (4 tests): 09:30 / 14:30 /
     15:15-15:29 → CONTINUOUS_TRADING; 15:30-15:39 →
     DERIVATIVES_CAS_ALIGNED; 15:40+ → CLOSED.
  6. **TestPreMarketAndWeekend** (3 tests): 09:00-09:14 →
     PRE_MARKET; Saturday / Sunday all hours → CLOSED.
  7. **TestDefensiveInputs** (5 tests): None / naive datetime /
     non-string symbol → UNKNOWN or CLOSED (never raises).
  8. **TestProductionBehaviourPreserved** (2 tests):
     `stamp_session_phase` still returns `"UNKNOWN"` for every input;
     `is_market_open` still callable. **Zero production behaviour
     change.**

The helper `_ist(h, m, *, weekday_offset=0, seconds=0)` builds a UTC
datetime that is `h:m:seconds` IST on `_BASE_DATE = date(2026, 9, 14)`
(Monday) plus `weekday_offset` days. Tests use this to probe IST
windows precisely.

### Documentation (NEW)

  - `docs/2026-09-13-workflow-j-deep-research.md` (~12K bytes):
    Verified NSE/BSE facts, hard-coded clock inventory across
    python-engine and node-gateway, real-bug list (the 15:30 → 15:40
    mismatch in `fno_chain.py` and `hedge_strategies.py`, the
    holiday-list divergence between `market_calendar.py` and
    `market-hours.js`).
  - `docs/2026-09-13-workflow-j-classifier-plan.md` (~6K bytes):
    Plan slice with problem, files, acceptance, rollback.
  - `docs/2026-09-13-workflow-j-classifier-done.md` (~6K bytes):
    Post-commit summary with verification table.

All three are **authoritative reference docs** for J.2. The
deep-research doc is especially critical — it has the verified
circular numbers and the BSE CAS notice.

---

## 3. Session-search anchors

If the next session needs to recover the full conversation history,
the session ID is:

```
session_id: 20260913_174852_4541ea
profile: default
```

(The previous compaction summary mentions parent session
`20260913_083112_02535f` which is the parent's ID. Use the session
search anchors above.)

Useful search queries for context recovery:

  - "workflow J CAS market session correctness" → finds the deep
    research, plan, and post-commit summary
  - "J.1 session classifier" → finds the classifier design + test
    history
  - "workstream F trading losses accounting truth" → finds F-series
    + parallel agent's correction plan
  - "cross-container contract test" → finds I.F
  - "operational_coverage optional AI" → finds I.C
  - "usefulness bridge" → finds I.A

---

## 4. The J.2 plan — what to build next

### Goal

Per the J deep-research doc: **broker-behaviour verification + CAS
eligibility list**.

The J.1 classifier is the seam. J.2 needs to verify (1) what the live
Kite feed returns at 15:15 IST for a CAS-eligible cash stock and (2)
populate the Phase 1 F&O eligibility list so `is_cas_eligible`
returns True for known CAS-eligible underlyings.

### Constraints (must NOT change)

  1. **`stamp_session_phase` contract** in `proactive_intelligence.py`
     stays `"UNKNOWN"` for every input. Production behaviour
     preservation rule from J.1.
  2. **`is_market_open()`, `is_trading_day_sync()`** unchanged.
  3. **`EXPIRY_CUTOFF_HOUR/_MIN = 15, 30` in `fno_chain.py`** stays.
     Plan §14: "Preserve earlier strategy deadlines unless
     explicitly revised and qualified." This is a separate
     operator-sign-off slice.
  4. **`hedge_strategies.py::_EXPIRY_CUTOFF = time(15, 30)`** stays
     for the same reason.
  5. **Holiday reconciliation** between Python and Node is deferred.
  6. **`market-hours.js` (Container B) parity** is deferred.

### The two-part slice

#### Part 1 — CAS eligibility list

The Phase 1 F&O eligibility list lives in NSE's contract-master API.
Dev has no live fetch. Two options:

**Option A (recommended)**: operator-supplied static list via config.
Add `CAS_PHASE1_FNO_UNDERLYINGS: list[str]` to `python-engine/config.py`
(default empty), wire `is_cas_eligible` to consult this list.

**Option B**: live fetch on demand from NSE's contract-master API. Adds
network dependency at classifier time; the deep-research doc notes
NSE routinely bot-blocks. Not recommended unless the operator has
explicit need.

For J.2, ship **Option A**. The static list is operator-curated and
version-controlled; future J-slice can swap to Option B if the
operator signals interest.

Concrete changes:

  - EDIT `python-engine/config.py`: add
    ```python
    CAS_PHASE1_FNO_UNDERLYINGS: tuple[str, ...] = ()  # populated by operator
    ```
    (tuple to match the existing immutable-settings convention;
    the agent convention is `tuple` for list-shaped config.)

  - EDIT `python-engine/market_calendar.py`: replace the body of
    `is_cas_eligible(symbol)` with:
    ```python
    from config import settings  # lazy import to keep this module's
                                  # import surface small
    if not symbol or not isinstance(symbol, str):
        return False
    return symbol.upper() in {s.upper() for s in settings.CAS_PHASE1_FNO_UNDERLYINGS}
    ```
    The `.upper()` normalisation is defensive: NSE lists underlyings
    in canonical form but the system may receive them in any case.

  - NEW tests in `python-engine/tests/test_session_classifier.py`:
    * `TestIsCasEligible::test_empty_list_returns_false_for_any_symbol`
    * `TestIsCasEligible::test_symbol_in_list_returns_true`
    * `TestIsCasEligible::test_case_insensitive_match`
    * `TestIsCasEligible::test_whitespace_stripped`

#### Part 2 — broker-behaviour probe (read-only)

This is the harder part. Per plan §14: "Introduce ... only after
verifying effective dates and broker behaviour." We have verified
dates; we have NOT verified broker behaviour.

The probe:

  1. Pick a known CAS-eligible underlying (RELIANCE, HDFCBANK, INFY
     — these are in F&O Phase 1 per NSE/CMTR/72394).
  2. At 15:17 IST on a real trading day, call `kite.quote()` (or
     `get_quote` via the existing Kite wrapper) and observe the
     response.
  3. Verify: response carries the CAS-window-specific fields
     (reference price, ±3% price band flag).
  4. **Document the observation** in a new doc
     `docs/2026-09-13-j2-broker-behaviour-probe.md`. This is the
     evidence the parallel agent's correction plan format requires.

**The probe cannot run in Dev** (no live broker). So J.2's Part 2 is
**documentation-only** in Dev — the doc explains how the operator
runs the probe in a staging environment, what to record, and what
to do with the result.

The deliverable for J.2 Part 2 is:

  - NEW `docs/2026-09-13-j2-broker-behaviour-probe.md` (~3K bytes)
    with a step-by-step probe procedure.
  - NEW `python-engine/tools/j2_cas_probe.py` (a CLI that the
    operator runs in staging; not exercised by automated tests).

#### Part 3 — doc-only: the J series matrix update

Per AGENTS.md §16: "With every implementation commit, update
SYSTEM_GUIDE.md for changed behavior and regenerate
SYSTEM_CODE_ATLAS.md when files/declarations change."

After J.2 lands:

  - EDIT `docs/SYSTEM_GUIDE.md` to add a J section under workstreams.
  - EDIT `docs/SYSTEM_CODE_ATLAS.md` to include the new
    `classify_session_phase`, `is_cas_eligible`, and
    `_VALID_SESSION_PHASES` declarations.

---

## 5. Files I did NOT touch (and why — prevents re-work)

| File | Reason |
|---|---|
| `python-engine/kite_client.py` | Owned by the parallel agent's F/G arc. J does not need Kite client changes for J.1 (the classifier is pure). |
| `python-engine/fno_chain.py` | The 15:30 → 15:40 mismatch is documented but per plan §14 NOT FIXED until operator sign-off. |
| `python-engine/hedge_strategies.py` | Same — `_EXPIRY_CUTOFF = time(15, 30)` stays. |
| `python-engine/proactive_intelligence.py` | `stamp_session_phase` is the G forward-compat seam; must not change. The classifier is additive — J.2+ callers use `classify_session_phase` directly. |
| `python-engine/operational_coverage.py` | Owned by the I.C slice; do not touch. |
| `python-engine/promotion_bridge.py` | Owned by the F/G correction plan. |
| `python-engine/config.py` | Touch only in Part 1 of J.2 to add `CAS_PHASE1_FNO_UNDERLYINGS`. Do not change any existing setting. |
| `node-gateway/server/utils/market-hours.js` | Container B parity deferred. |
| `node-gateway/client/src/pages/Dashboard.jsx` | No dashboard change required for J.1 or J.2 — the classifier is engine-internal. |

---

## 6. The system documentation that already exists

The next session should read these before any code change:

  - `docs/SYSTEM_GUIDE.md` — system behaviour and architecture.
  - `docs/SYSTEM_CODE_ATLAS.md` — module/function index. **Needs
    regeneration after J.1** (the atlas was last regenerated
    before J.1). J.2's post-commit summary should call this out.
  - `docs/HANDOVER_CHECKLIST.md` — D acceptance state and what is
    pending for release.
  - `docs/NEXT_AGENT_PLAN.md` — full §1-§17 workstream plan, current
    matrix (J row needs IMPLEMENTING update after J.1).
  - `docs/2026-09-13-fg-independent-correction-plan.md` — what the
    parallel agent is doing on F/G; required reading to avoid
    collision.
  - `docs/2026-09-13-workflow-f-state-of-codebase-audit.md` — F-series
    context.
  - `docs/2026-09-13-workflow-j-deep-research.md` — J-specific deep
    research.
  - `docs/2026-09-13-workflow-j-classifier-plan.md` — J.1 plan slice.
  - `docs/2026-09-13-workflow-j-classifier-done.md` — J.1 post-commit
    summary.

The next session should **not** re-read these from scratch — they're
large. Use `search_files` (ripgrep) with specific anchors like
"cas_eligible", "EXPIRY_CUTOFF", "stamp_session_phase" to verify
specific details.

---

## 7. The senior-dev rules that have held across this arc

The next session must follow these without exception:

  1. **Read the file before patching.** The `read_file` tool warns
     when a file was modified since last read; honour the warning
     and re-read.
  2. **`git diff --stat` after every patch.** The patch tool's diff
     display can lie (whitespace-only re-flow looks like huge
     changes). The actual `git diff --stat` is the ground truth.
  3. **Tests in isolation first, full suite second.** Cross-test
     isolation noise is pre-existing and documented.
  4. **No deletions.** The user rule from the start: "all
     permissions to run things other than deletions."
  5. **Commit per sub-task.** Format: `feat(J.X): <subject>` for
     code, `docs(J.X): ...` for docs-only, `chore:` for inventory.
  6. **Post-commit summary doc for every implementation commit.**
  7. **Bounded contract tests for every cross-container change.**
  8. **OPT-OUT defaults.** New opt-in features default to OFF; the
     rollback is one env var.
  9. **Never claim D done because files exist.** The D release path
     requires real backup/restore/PR/deployment, not Dev green.
  10. **Never change another agent's files without coordinating.**
      F-series files (`promotion_bridge.py` etc.) are owned by the
      parallel agent.

---

## 8. End-of-inheritance state

This arc has shipped 13 workstream slices (H1-H5, I1-I3, I.A, I.B,
I.C, I.F, J.1) without a single production behaviour change outside
of opt-in flags. The optional-AI subsystem is now bounded,
self-validating, and cross-container-contract-tested. The session
phase classifier is the seam J.2 will consume.

The next session should:

  1. Read this entire doc.
  2. Read `docs/2026-09-13-workflow-j-deep-research.md` (J-specific
     facts).
  3. Read `python-engine/market_calendar.py` lines 1-50 (constants
     block) and lines 250-460 (classifier).
  4. Read `python-engine/tests/test_session_classifier.py` (the 41
     test contract).
  5. Run `cd python-engine && ./winvenv/Scripts/python.exe -m pytest
     tests/test_session_classifier.py tests/test_session_phase_placeholder.py
     tests/test_market_calendar.py -q` and verify 61 tests pass.
  6. Begin J.2 Part 1.

Branch HEAD: `63a98ab`. Worktree clean. Quality preserved.
