# F5 (broker statement automation skeleton) — done and committed

## What landed (commit `48d95ba`)

**Branch**: `codex/production-correction-hedge-p0`
**Files changed**: 8 (3 new, 5 modified), +1,408 / -2 lines
**Tests**: +45 net passing
**Whole-engine**: 2,881 passed / 4 skipped / 39 warnings in 128.75s
**Status**: F5 of the six-slot F plan delivered in partial form
(CLI + routes; no scheduler; no broker network integration; no
DISC-A1..A5 retroactive population).

## Code surface

### New module: `python-engine/reconciliation_cli.py` (470 lines)

Three subcommands:
- `import-statement --payload <path> --output <path>` —
  reads JSON, calls `import_broker_statement`, runs
  `record_current_state` (F4), writes structured JSON.
- `run-report --account <id> [--source] [--limit] [--record] --output <path>` —
  runs both existing reports; `--record` enables discrepancy recording.
- `list-discrepancies [--account] [--source] [--category] [--status] [--since] [--until] [--limit] --output <path>` —
  filters the discrepancies table.

Atomic output helper (`_write_output_atomic`) produces
byte-identical retries; `allow_nan=False` rejects NaN/Infinity
silently written to JSON.

### New routes in `python-engine/routes_commands.py` (+158 lines)

- `POST /reconciliation/import-statement` —
  programmatic ingestion surface; same async function as the CLI.
  Returns `{imported, broker_status, discrepancy_ids, can_place_orders}`.
- `GET /reconciliation/discrepancies` —
  read-side filter; mirrors `/analytics/reconciliation-evidence` style.

All responses carry `can_place_orders=False`.

### New tests

- `tests/test_reconciliation_cli.py` (29 tests): ISO-8601 parsing,
  payload validation, atomic output writes (byte-identical retries,
  NaN rejection, parent-directory creation), every CLI subcommand
  end-to-end, validation errors return non-zero exit code.
- `tests/test_routes_reconciliation.py` (16 tests): happy path,
  idempotent repost (flips the `imported` flag), every 422 path,
  `can_place_orders=False` always, GET route validation.

### Golden file update

`tests/main_surface_golden.json` was deliberately regenerated via
`TS_UPDATE_GOLDEN=1 pytest tests/test_main_surface_characterization.py`.
Diff is exactly 2 routes added (`get_reconciliation_discrepancies`,
`post_reconciliation_import_statement`); nothing else drifted.

### F3 flake fix

`test_mark_to_market.py::TestReproducibility::test_summary_string_format_stable`
was using `age_seconds=0` which crossed the freshness boundary under
sub-second clock jitter. Rebuilt the tick with `age=1s` (strictly in
the past) and explicitly excluded the `age=Ns` substring from the
structural-shape assertion. 10/10 reruns in isolation green.

## Senior-dev design choices

1. **Atomic byte-identical output writes** — the operator can re-run
   the CLI with the same payload and get the same file (or a clean
   error if the new payload differs). This matches the
   `research_cli._write_comparison_output` discipline and lets the
   F4 framework's idempotency surface through the file system.
2. **Same async function for CLI and route** — both surfaces call
   `import_broker_statement` then `record_current_state`; there's
   one place where the wiring lives.
3. **CLI does not require the F4 framework to be initialised** —
   `record_current_state` calls `init_discrepancies_db` internally,
   so the operator doesn't need a separate `init` step.
4. **Exit codes are honest** — 0 on success, 1 on validation error,
   2 on import/DB error. The output JSON is written even on failure
   so the operator can see what went wrong.
5. **`can_place_orders=False` on every response** — defensive
   contract; the route is never an order authority.
6. **NaN/Infinity rejected at the JSON encoder level** — `allow_nan=False`
   catches `float("nan")` slip-through before the file is written.

## Senior-dev self-corrections in this slice

1. **Circular import trap**: `routes_commands.py` does `import main as _main`,
   and `main.py` does `from routes_commands import router`. My test
   module tried `import routes_commands as route` first — this
   triggered the cycle. Fixed by `from main import app` (the same
   pattern as other route tests).
2. **FastAPI's built-in body validator** rejects non-dict payloads
   *before* my route's manual `if not isinstance(payload, dict)`
   check can run. My test expected the route's error message;
   FastAPI returns its own. Fixed the test to match the actual
   behaviour and added an inline comment explaining the asymmetry.
3. **F3 flake**: my F3 `test_summary_string_format_stable` was
   non-deterministic under load because `age_seconds=0` crossed the
   freshness boundary when the test helper's `_now()` and the
   `mark_open_positions` call happened to straddle a second boundary.
   Hardened with `age=1s` tick and removed the `age=Ns` assertion.
4. **Tried to refactor `TestClient` to `httpx.ASGITransport`** to
   silence the `'app' shortcut` DeprecationWarning — but the
   sync `httpx.Client` doesn't drive async ASGI apps correctly.
   Reverted to `TestClient(app)` to match the existing pattern in
   the codebase; the warning is the same one other route tests
   already produce.
5. **Golden file update**: caught the legitimate route-surface
   regression in `test_main_surface_characterization` and regenerated
   the golden deliberately via `TS_UPDATE_GOLDEN=1`, then verified
   the diff contains exactly the 2 new routes and nothing else.

## Why this should not need the other agent's edits

- **Strictly additive.** No existing module is removed or renamed.
  The two new routes are appended to the end of `routes_commands.py`
  and the new CLI module is a standalone file.
- **Golden file update is justified and minimal.** The diff is
  exactly 2 routes added; nothing else drifted.
- **No new schema.** F4's `discrepancies` and `discrepancy_status_log`
  tables are reused as-is.
- **No scheduler / daemon / cron change.** The CLI and route are
  operator-invoked; nothing fires automatically.

## What was explicitly NOT done in this slice

- **No scheduler.** The CLI is operator-invoked; the route is
  on-demand. No periodic refresh.
- **No broker network integration.** The CLI reads a local JSON
  file the operator supplies; the route accepts a JSON body. No
  Kite, no Zerodha API.
- **No retroactive DISC-A1..A5 population.** The five audit-doc
  entries remain `UNKNOWN / UNVERIFIED`. A future commit can call
  `record_from_evidence_report` with hand-supplied evidence to
  back-fill when real screenshots / ledger rows are obtained.
- **No `/reconciliation/discrepancies` mutation surface.** The
  GET is read-only; status transitions remain a CLI-only or direct
  DB call.

## Disclaimers (preserved per the source-backed discipline)

- **No real broker-statement automation acceptance.** The CLI and
  route exist; no operator has run an import against a real
  statement yet; no admin UI surfaces the discrepancy IDs. The
  value is structural (the CLI/route pair is one import away from
  operator use, the F4 framework is wired into the import path,
  the golden route table is updated).
- **The five DISC-A1..A5 reconciliation warnings remain
  UNKNOWN / UNVERIFIED.** This slice did not touch them.
- **`EQUITY_INTRADAY_EFFECTIVE_DATE` remains None.** This slice
  did not touch cost provenance.
- **`kite_client.py` was not modified.** This slice uses no Kite
  functionality.

## What's next — and what F-series work is left

**Only F6 remains.** From the plan section 10 / NEXT_AGENT_PLAN row F:

> 5. Establish capital-increase criteria from externally reconciled
>    net results, drawdown, execution quality and operational
>    stability. Leave the user's loss tolerance as an explicit
>    input if not supplied.

F6 is **blocked on user input** for two reasons:
1. The user's loss tolerance must be supplied explicitly (per the
   plan quote above).
2. The capital-increase criteria are policy decisions — what
   drawdown threshold, what net-result floor, what execution-quality
   gate — that the operator must approve.

What's deliverable *without* that input:
- A `python-engine/capital_policy.py` module that reads the user's
  loss tolerance (from config or environment) and produces a
  `CapitalPolicy` dataclass with `initial_capital_inr`,
  `loss_tolerance_inr`, `max_drawdown_pct`, and a `is_increase_authorized(...)`
  guard that returns a structured verdict (similar to F2's
  `AffordabilityEvaluation`).
- A CLI subcommand `python -m python_engine.capital_policy_cli evaluate`
  that prints the policy verdict for a candidate live-growth request.
- ≥25 unit tests covering threshold parsing, evaluation logic, and
  the explicit-loss-tolerance-as-input contract.

What is **not** deliverable without user input:
- The actual numeric loss-tolerance value.
- The capital-increase criteria themselves (drawdown cap, net-result
  floor, execution-quality gate).

**Awaiting your call** on whether to proceed with F6 with a *placeholder*
loss tolerance (clearly marked as PLACEHOLDER, with the input slot
preserved for your override), or pause until you supply the real
input.

## Reference paths

- `docs/2026-09-13-workflow-f-state-of-codebase-audit.md`
  section 10 (new this commit) — full module description and
  route documentation.
- `docs/NEXT_AGENT_PLAN.md` requirement matrix row F — updated
  this commit to reflect F1+F2+F3+F4+F5 closure.
- `python-engine/tests/main_surface_golden.json` — regenerated
  this commit via `TS_UPDATE_GOLDEN=1` (2 routes added, no drift).
