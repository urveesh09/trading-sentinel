# I.4.E — bounded contract-health self-evaluation

## What landed

|| File | Type | Purpose |
|---|---|---|---|
| `agent/contract_health.py` | source (new) | 5 bounded invariant checks + aggregate report. Pure module (no model calls, no broker, no scheduler, no I/O). |
| `agent/tools/contract_health_check.py` | CLI (new) | Operator-facing CLI: `print-config`, `check <path>`, `self-check`. Read-only; does not invoke the model or mutate state. |
| `agent/tests/test_contract_health.py` | test (new) | 53 tests across the 5 invariants, the aggregate, the CLI, and the allow-list shape invariants. |

## The five bounded invariants

1. **`status_envelope_authority`** — the bounded health envelope the agent
   publishes to the engine carries **no execution authority**. Rejects
   `can_place_orders != False`, `authorization_effect != "NONE"`, and any
   top-level key outside the documented allow-list
   (`STATUS_ENVELOPE_ALLOWED_KEYS`).
2. **`no_prompt_leakage`** — the bounded usefulness snapshot carries **no
   prompt or reviewer content**. Rejects `prompt`, `rationale`, `pitch`,
   `risks`, `raw_response`, etc., at the top level and inside any
   `usefulness` sub-envelope.
3. **`usefulness_counters_only`** — if a `usefulness` envelope is present,
   every key must be in `USEFULNESS_ALLOWED_KEYS` AND every value must be
   a bounded primitive (`int` / `float` / `str` / `None`); `verdict_counts`
   must be `dict[str, int]`. `bool` values are rejected (they're a subclass
   of `int` but a boolean for a count field is never the intent).
4. **`classifier_fail_closed`** — for every `ClassificationResult`,
   confidence below the documented threshold (default 0.6) MUST map to
   `UNKNOWN`. Category outside the bounded enum is a violation. Rationale
   length > 280 chars is a violation (the rationale is bounded — never
   the prompt).
5. **`review_non_authoritative`** — a `Review` MUST NOT carry any of the
   `FORBIDDEN_REVIEW_DELTA_FIELDS` (`can_place_orders`,
   `authorization_effect`, `live_delta_inr`, `capital_delta`,
   `qualification`, `approved_live_budget`). Per plan §13: "The typed
   result must not change capital limits, qualification or
   order/delivery authority."

## The aggregate

`evaluate_contract(...)` runs every invariant and returns a
`ContractReport`:

- `passed` — `True` iff every check passed.
- `checks` — one `ContractCheck` per invariant in stable order.
- `evaluated_at` — UTC datetime when the report was built.
- `schema_version` — pinned at `i4e-v1` so consumers can version the shape.
- `to_dict()` — bounded JSON-serialisable representation.
- `violations()` — flat list of `f"{check_name}: {violation}"` lines.

All inputs to `evaluate_contract` are optional. `None` means "not
inspected in this run" — informational, never a violation. This lets
an operator run the harness with only one surface available (e.g.
just the status envelope) and still get a useful report.

## The CLI

```
python -m tools.contract_health_check print-config
python -m tools.contract_health_check check <path-to-snapshot.json>
python -m tools.contract_health_check self-check
```

- `print-config` — prints the bounded contract (allow-lists,
  forbidden fields, invariants). Exit 0.
- `check` — reads a JSON snapshot from `<path>` and runs every
  invariant. Exit 0 iff every check passed; exit 1 on any violation;
  exit 2 on I/O / parse / shape error.
- `self-check` — runs every invariant against synthetic well-formed
  inputs. A "does the harness work" smoke test; exit 0 iff every
  check passed.

The CLI is read-only: no model calls, no broker/network, no trading
control plane. Per inheritance §9, this is the bounded slice that
"strengthens the J.10 / F3-F6 / I.4.D surfaces" — no verdict
semantics change, no F/G files touched, no deletions.

## Design decisions

- **Pure module.** No I/O, no model calls, no scheduler. Imports
  `agent.news_classifier` lazily inside
  `check_classifier_fail_closed` so the module stays importable
  in isolation (the `agent.py` module triggers a Telegram env-var
  check at import time, which would force test environments to
  set `TELEGRAM_BOT_TOKEN` etc.).
- **Allow-lists as frozensets.** `STATUS_ENVELOPE_ALLOWED_KEYS`,
  `USEFULNESS_ALLOWED_KEYS`, and `FORBIDDEN_REVIEW_DELTA_FIELDS`
  are module-level constants. The TestAllowListShape class
  asserts they are `frozenset[str]` and that
  `FORBIDDEN_REVIEW_DELTA_FIELDS & STATUS_ENVELOPE_ALLOWED_KEYS`
  is empty (a field cannot be both required and forbidden).
- **Duck-typed review / classification inspection.** The
  `check_review_non_authoritative` function inspects
  `dataclasses.fields()` if available and falls back to
  `__dict__`. The `FakeReview` test stand-in is a plain class
  (not a dataclass, not slotted) so tests can inject forbidden
  authority fields at construction time — a real dataclass would
  reject those kwargs, and `__slots__` would block `setattr`.
- **None means "not inspected"**, never a violation. This is the
  bounded contract: `evaluate_contract()` with no inputs at all
  returns `passed=True`. The CLI's `self-check` subcommand uses
  this to verify the harness without requiring an operator-supplied
  snapshot.

## Senior-dev invariants preserved

- **NO deletions.** All 5 invariants are additive; existing
  `agent.py`, `advisory.py`, `async_reviews.py`, `news_classifier.py`,
  `optional_ai_metrics.py`, and the tools are untouched.
- **NO verdict-semantics change.** The classifier is still
  informational only; the verdict pipeline's existing path is
  byte-identical.
- **NO F/G files touched.** The parallel agent's territory is
  preserved.
- **NO new tables, NO new dependencies.** Stdlib only (`dataclasses`,
  `datetime`, `argparse`, `json`, `typing`). The CLI reuses the
  same patterns as `agent.tools.news_classify_cli` (lazy imports,
  bounded exit codes).
- **Fail-closed at every boundary.** Unknown envelope key →
  violation. Unknown usefulness key → violation. Bool for a
  count → violation. Confidence below threshold without UNKNOWN →
  violation. Any forbidden authority field → violation.

## Verification

- Focused `agent/tests/test_contract_health.py`: **53/53 PASS** in
  0.12s.
- Full agent suite: **312/312 PASS** in 3.81s (was 259 before this
  slice; +53 net, all from `test_contract_health.py`).
- Python-engine narrow regression surface (J + F + I + cas-reachability
  + main surface + holiday drift): **364/364 PASS** in 14.33s, 1
  pre-existing Starlette lifespan deprecation warning (NOT a
  regression from this slice).
- CLI smoke test:
  - `python -m tools.contract_health_check print-config` → exit 0,
    prints the bounded contract.
  - `python -m tools.contract_health_check self-check` → exit 0,
    every invariant passes against synthetic well-formed inputs.
  - `python -m tools.contract_health_check check <bad-snapshot.json>`
    → exit 1, surfaces the violations.
  - `python -m tools.contract_health_check check <missing.json>`
    → exit 2, structured diagnostic to stderr.

## Branch state

- **Branch:** `codex/production-correction-hedge-p0`
- **Working tree:** new files (3) + 1 file with imports adjusted
  to match the project's bare-module convention.
- **Pushed:** no (this slice's commit pending — see the
  `docs(HANDOVER): point read order at the new inheritance-i4d handoff`
  HEAD before this slice's commit lands).

## What this enables

After this slice, the operator has a one-command way to verify the
agent's bounded contract hasn't drifted:

```bash
python -m tools.contract_health_check check <published-snapshot.json>
```

If anything in the bounded contract regresses (a new field
inadvertently crosses the bridge; a review object gains authority;
the classifier's fail-closed path breaks), the CLI exits 1 with
a structured violation list. This is the "guard the guards"
pattern from the I.4 deep-research doc — the bounded contract is
now self-policing at the operator-tool layer, not just at the
test layer.

## What this slice deliberately does NOT include

- **No cron wiring.** Per inheritance §5, cron is a separate
  concern; the operator opts in by running the CLI or wiring it
  into their existing scheduler. Cron wiring is a follow-up slice
  if the operator asks.
- **No engine-side integration.** This is an agent-side harness;
  the engine's `optional_ai_status.load_optional_ai_status`
  consumer does not yet call this. That's intentional — the
  engine should never call into the agent's diagnostic module
  (the dependency arrow would be backwards).
- **No review-content scrubbing.** Invariant 2 (no prompt
  leakage) DETECTS leakage but does not scrub it. If the harness
  finds a violation, the operator fixes the producer, not the
  scrubber.
- **No F/G cross-workstream.** F/G files are owned by the parallel
  agent; per inheritance §7 "do not touch without coordination".

## Status

I.4.E **DONE**. The bounded-annotation surface is now:

- `summarize` (I.2 + I.B) — DONE
- `identify-missing-evidence` (conviction veto) — DONE
- `classify` (I.4.D) — DONE
- `compare` (I.F) — DONE
- `explain` — partial (`rationale` field on `Review`); deeper
  explanation is a future slice, not on the current path.
- `self-evaluate` (I.4.E) — DONE (this slice)

The I-series bounded-annotation surface is now complete for
`summarize` + `identify-missing-evidence` + `classify` + `compare` +
`self-evaluate`. I.4.G (per-ticker / per-strategy breakdown) is
explicitly deferred per the I.4 deep-research doc's "after
A/B/C/F prove themselves in PROD" guard.
