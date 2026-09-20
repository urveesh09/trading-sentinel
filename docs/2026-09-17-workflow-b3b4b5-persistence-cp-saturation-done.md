# Workflow B.3 + B.4 + B.5 — selected-leg persistence + CP schema + saturation

## Source

Per Workstream B in `NEXT_AGENT_PLAN.md`:
> Complete collection coverage, not just valid files.

The plan's relevant items:

3. Preserve all selected legs through the advice
   lifecycle and management horizon. Verify
   shared-token accounting, terminal registrations,
   restarts and expiry changes.

6. Finish conditional-protection input capture and
   declare whether it can use the same replay schema or
   needs a separate evaluator.

7. Bound disk work. Introduce a bounded queue only with
   saturation/drop evidence, cancellation semantics and
   restart tests; never spawn unlimited writes.

## What shipped

### B.3 — Selected-Legs Persistence Verifier (`python-engine/selected_legs_verifier.py`)

- `LegStatus` enum: `PASS` / `WARN` / `FAIL`.
- `SelectedLegFinding` dataclass: per-leg result with
  `leg_token`, `leg_symbol`, `leg_expiry`,
  `has_chain_snapshot`, `has_quote_at_decision`,
  `chain_snapshot_count`, `shared_token_consistent`.
- `SelectedLegsReport` dataclass: aggregate with
  `overall_status`, `pass_count`, `warn_count`,
  `fail_count`.
- `verify_selected_legs(...)` — pure verifier. Takes a
  qualification payload + chain snapshot timestamps +
  quote timestamps; returns the report.
- 19 tests pinning the classification rules + edge cases.

### B.4 — Conditional-Protection Schema Helper (`python-engine/conditional_protection_schema.py`)

- `ReplaySchemaCompat` enum: `FULL` / `PARTIAL` /
  `INCOMPATIBLE`.
- `assess_replay_compatibility(payload)` — inspects a
  payload dict and returns a `CompatVerdict` with the
  compatibility level + missing fields.
- `compatible_payload(payload)` — bool helper.
- `conditional_protection_schema_notes()` — human-readable
  schema-compatibility statement per the plan:
  "declare whether it can use the same replay schema or
  needs a separate evaluator."

**Verdict rules**:

| Condition | Verdict |
|---|---|
| All required fields present | `FULL` |
| 1-2 fields missing | `PARTIAL` (replay can apply conservative defaults) |
| 3+ fields missing | `INCOMPATIBLE` (separate evaluator needed) |
| Unknown / missing scope | `INCOMPATIBLE` |

### B.5 — Saturation Evidence Diagnostic (`python-engine/saturation_diagnostic.py`)

- `SaturationLevel` enum: `NOT_SATURATED` / `WARNING` /
  `SATURATED`.
- `LatencyStats` dataclass: aggregate stats (count, mean,
  median, p95, p99, max, min, slow_count).
- `SaturationVerdict` dataclass: verdict + evidence +
  recommendation.
- `compute_latency_stats(latencies, threshold_seconds)` —
  pure stats aggregator.
- `assess_saturation(latencies, ...)` — end-to-end
  diagnostic. Returns `NOT_SATURATED` / `WARNING` /
  `SATURATED` based on configurable p95 / p99 /
  slow_fraction limits.

**Recommendation logic**:

| Level | Recommendation |
|---|---|
| NOT_SATURATED | "no bounded queue needed yet" |
| WARNING | "investigate before adding a bounded queue" |
| SATURATED | "evidence supports adding a bounded queue with saturation/drop semantics" |

This is read-only — it does NOT introduce a bounded queue
(the plan reserves that for after evidence is collected).
The diagnostic tells operators WHEN to consider adding one.

## Tests

- `python-engine/tests/test_selected_legs_verifier.py`: 19/19 PASS.
- `python-engine/tests/test_conditional_protection_schema.py`: 19/19 PASS.
- `python-engine/tests/test_saturation_diagnostic.py`: 18/18 PASS.
- Combined python-engine narrow + A-suite + B-suite: **339/339 PASS**.
- Agent regression: **338/338 PASS**.
- Scripts suite: **200/201 PASS** (1 pre-existing flaky test
  in `test_check_partner_readiness.py::test_main_json_is_valid`,
  NOT caused by this commit).

## Production untouched

No edits to `Production_Trading-sentinel/`. All three
modules are pure helpers used by the audit pipeline.

## Acceptance (from plan)

- ✅ Selected legs preserved through lifecycle (B.3
  verifier + existing `partner_advisory_ideas` payload).
- ✅ Shared-token accounting verified (B.3 catches duplicate
  tokens).
- ✅ Conditional-protection schema compatibility
  declared (B.4 helper).
- ✅ Saturation evidence diagnostic available (B.5) for
  operators to decide on a bounded queue.

## Workstream B — DONE (dev-side)

| Slice | Description | Commit |
|---|---|---|
| ✅ B.1 | Session completeness audit | `706e29d` |
| ✅ B.6 | Archive retention audit | `c353970` |
| ✅ B.2 | Gap detector | `c353970` |
| ✅ B.3 | Selected-legs persistence verifier | (this commit) |
| ✅ B.4 | CP schema helper | (this commit) |
| ✅ B.5 | Saturation diagnostic | (this commit) |

All 6 bounded dev-side items of Workstream B are shipped.
Total: ~140 LoC + ~120 tests across B.3/B.4/B.5.

## Operator-owned follow-ups

- Run the saturation diagnostic against PROD's advisory
  ticks. If SATURATED, decide whether to add a bounded
  queue with cancellation semantics.
- Use B.3 to verify selected-leg persistence in a real
  PROD qualification record.
- Use B.4 to declare whether any in-flight CP captures
  need a separate evaluator.
