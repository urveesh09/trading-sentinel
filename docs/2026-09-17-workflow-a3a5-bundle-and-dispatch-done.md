# Workflow A.3 + A.5 — capture-bundle binding + dispatch independence

## Source

Per Workstream A in `NEXT_AGENT_PLAN.md`:
> Carry the chosen clocks and source IDs into the
> captured bundle and frozen decision manifest. Bind
> candidate and public captures to the same
> decision/run/account/index.
>
> Keep final dispatch revalidation independent: source
> availability does not grant transport authority.

## What shipped

### A.3 — Capture-bundle binding (`python-engine/capture_bundle.py`)

- `BUNDLE_VERSION_V1` constant -- schema version marker
  so future migrations are explicit.
- `BundleValidationCode` enum: machine-readable codes
  (`MISSING_FIELD`, `WRONG_TYPE`, `UNDERLYING_MISMATCH`,
  `RUN_ID_MISMATCH`, `ACCOUNT_MISMATCH`, `POLICY_MISMATCH`,
  `BAD_VERSION`, `EMPTY_CARD`, `CLOCK_NOT_READY`).
- `BundleValidationProblem` dataclass: one row of the
  validation report.
- `CaptureBundle` dataclass: the canonical captured bundle
  with `bundle_version`, `decision_id`, `run_id`,
  `account_id`, `underlying`, `policy`, `clock` (the
  DecisionClock payload), `source_ids` (public + chain),
  `card` (the candidate dict).
- `build_capture_bundle(...)` -- low-level builder. The
  `decision_id` is a SHA-256 hash binding the bundle's
  identity (run_id + account_id + underlying + policy +
  thesis_id + clock fingerprint).
- `bundle_from_clock_and_card(clock, card, ...)` --
  convenience wrapper that takes a DecisionClock directly.
  Source IDs default to the clock's stored IDs but can be
  overridden by the caller.
- `validate_bundle(bundle)` -- returns ALL binding problems
  (not just the first one).
- `has_required_bundle_fields(bundle)` -- quick assertion
  helper.
- `REQUIRED_BUNDLE_FIELDS` -- tuple of the required fields.

### A.5 — Dispatch independence verification (`python-engine/dispatch_independence.py`)

- `GateOutcome` enum: `PASS` / `FAIL`.
- `DispatchGateStatus` dataclass: per-gate result with
  outcome + reason.
- `DispatchGateReport` dataclass: combined report with
  `enabled`, `in_session_window`, `is_trading_day`,
  `fresh_token`, plus `overall_ok` aggregate and
  `failed_gates()` helper.
- `check_dispatch_gates(now, enabled, session_open_minute,
  session_close_minute, is_trading_day, token_fresh)` --
  pure, deterministic gate evaluation from explicit boolean
  inputs. Used by tests and the audit pipeline without
  instantiating the live dispatcher.
- `dispatch_independence_assertion(source_data_captured,
  candidate_constructed, dispatch_report)` -- returns a
  structured explanation string for audit logs. The
  assertion encodes the plan's rule: "Source availability
  does NOT grant transport authority."

## Per-gate semantics

| Gate | When it fails | Operator action |
|---|---|---|
| `enabled` | `PARTNER_MANUAL_ADVISORY_DELIVERY_ENABLED=False` | Operator must explicitly enable delivery. |
| `in_session_window` | Now is outside `[session_open, session_close]` minutes | Operator adjusts session window in settings. |
| `is_trading_day` | Today is not a configured trading day | Operator adds the day to the trading calendar. |
| `fresh_token` | Kite access token is missing or stale | Operator refreshes the token. |

All four must pass for `overall_ok = True`. The plan
forbids source data from overriding any of these gates.

## Tests

- `tests/test_capture_bundle.py`: **25/25 PASS.**
- `tests/test_dispatch_independence.py`: **19/19 PASS.**
- Combined A-suite (A.1 + A.4 + A.2 + A.3 + A.5 + existing
  partner_decision_clock): **127/127 PASS.**
- Combined partner suite (advisory + renderer + sizing +
  orchestrator + hedge_readiness + collection_attempts):
  **133/133 PASS.**
- Agent regression: **338/338 PASS.**

## Production untouched

No edits to `Production_Trading-sentinel/`. The two new
modules are pure helpers used by the audit pipeline.

## Acceptance (from plan)

- ✅ Clocks + source IDs carried into captured bundle (item 3).
- ✅ Decision / run / account / index bindings validated.
- ✅ Dispatch revalidation independent of source availability
  (item 5).

## Workstream A — DONE

All 5 bounded dev-side items of Workstream A are now
shipped:

| Slice | Description | Commit |
|---|---|---|
| ✅ A.1 | Clock injection contract | `c6b06eb` |
| ✅ A.4 | Cross-boundary safety net | `c6b06eb` |
| ✅ A.2 | Decision policy enum + version | `c6b06eb` |
| ✅ A.3 | Capture-bundle binding | (this commit) |
| ✅ A.5 | Dispatch independence verification | (this commit) |

The remaining A-related work is operator-owned:
- Verify the captured bundle survives a real collection
  session in PROD.
- Wire the operator's `staging_days` advancement through
  the bundle so old captures are version-invalidated when
  the policy switches.
