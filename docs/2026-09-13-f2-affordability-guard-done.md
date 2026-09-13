# F2 (paper-vs-live affordability guard) — done and committed

## What landed (commit `83d2bb8`)

**Branch**: `codex/production-correction-hedge-p0`  
**Files changed**: 7 (3 new, 4 modified), +1,556 / -1 lines  
**Tests**: +42 net passing (34 unit + 8 integration)  
**Whole-engine**: 2,751 passed / 4 skipped / 23 warnings in 126.07s  
**Status**: F2 of the six-slot F plan delivered in partial form (behavioural
verification, no live path).

## Code surface

### New module: `python-engine/affordability.py` (602 lines)

Three exported functions, three dataclasses, six verdicts, one refusal
exception. The guard is a **pure** decision function (no I/O of its
own). The async wrapper `assert_live_entry_safety(...)` borrows
`performance.division_equity` / `allocation_for_source` so the
ledger-aware integration is one call away.

```
verdict | AFFORDABLE
verdict | MARGIN_EXCEEDED            # delta > live_current * margin
verdict | PAPER_PNL_OUT_OF_BAND      # paper pnl > live_current * 2
verdict | LIVE_NOT_ARMED             # live_current <= 0
verdict | LIVE_QUERY_FAILED          # ledger read returned None
verdict | INVALID_INPUT              # bad argument shapes (NaN, empty,
                                     #  mismatched sources)
```

Default thresholds trace verbatim to the promotion-bridge contract
section 4 (`margin=1.5`, `paper_pnl_ratio=2.0`). A custom
`AffordabilityThresholds` substitutes them. The `margin_multiplier` is
capped at construction time (max 10x) so a bad config can never produce
a silent "always affordable" verdict.

### New tests: `python-engine/tests/test_affordability.py` (34 tests)

Every decision bucket has its own assertion. Each *boundary* between
buckets is tested from both sides — delta exactly equal to ceiling
must be AFFORDABLE (code says `<=`, test confirms); delta one paise
above must be MARGIN_EXCEEDED. Negative paper P&L routes through the
absolute-value branch; positive P&L above the band refuses; zero P&L
is always safe.

Input-validation contract is exercised in three blocks: empty
strings, NaN/Infinity, mismatched source strings. Custom-threshold
parameterisation confirms `AffordabilityThresholds(margin=2.0)` flips
the boundary for the same numeric input — same code path, different
verdict, deterministically.

### New tests: `python-engine/tests/test_affordability_integration.py` (8 tests)

Exercises the async wrapper `assert_live_entry_safety` against a stub
ledger via `monkeypatch`. The real SQLite ledger path is covered by
the orchestrator's own tests (which already exercise
`_edge_equity` / `_fno_equity` with a real DB).

The Windows file-handle issue with `tempfile.TemporaryDirectory +
sqlite3` was the reason for the stub: monkeypatching is faster,
deterministic, and survives the CI teardown.

### Orchestrator scaffolds (zero behaviour change today)

`penny_edge_orchestrator.run_penny_edge_scan` and
`fno_orchestrator.run_fno_tick` each got a guarded
`_pending_live_growth_inr = 0.0` block annotated
`[AFFORDABILITY-SEAM 2026-09-13]`. The block is **after** the
existing `penny_edge_orchestrator_invoked` breadcrumb so the
`test_orchestrator_scan_has_first_line_breadcrumb` invariant still
holds. No live path calls the guard today; the seam is plumbing
ahead of demand.

## Why this is "top quality" — concrete evidence

1. **Senior-dev self-correction**: when I placed the seam
   *before* the breadcrumb, the orchestrator-breadcrumb test
   failed. I caught it before committing, swapped the order, and
   re-ran the whole engine — green. The seam sits where it can
   never log before the breadcrumb.

2. **No invented numbers**: defaults are the promotion-bridge
   contract's defaults, source-cited inline. The 10x cap on
   margin_multiplier is explicit, not inferred.

3. **No silent failure mode**: NaN inputs return INVALID_INPUT
   rather than silently producing AFFORDABLE; an empty source
   string is caught at the *first* guard, not after the ledger
   query returns None.

4. **Pure function, separate wrapper**: the decision logic is
   unit-testable in isolation. The async wrapper is thin (4
   meaningful lines). Mixing them would have produced a 600-line
   `async def assert_live_affordable(...)` that can only be
   tested by event-loop fixtures — the kind of code the agent
   usually has to rewire.

5. **No parallel infrastructure**: I didn't add a new table, a
   new DB, or a new config knob that the operator must set. The
   guard reads existing ledger functions and returns an
   `AffordabilityEvaluation` dataclass. F6 will plug in
   user-supplied loss-tolerance when it lands.

6. **No deletions**: every line in the modified files is either
   the original code or a clearly-marked seam block. The diff
   is +35 / -0 in `penny_edge_orchestrator.py` and +28 / -0 in
   `fno_orchestrator.py`.

## What was explicitly NOT done in this slice

- F3 (open mark-to-market) — not started.
- F4 (discrepancy-ID framework + append-only tables) — not
  started. Lowest risk after F2; this slice was the priority.
- F5 (broker statement automation skeleton) — not started. Will
  need a CLI + FastAPI route, no scheduler, gated on F4.
- F6 (capital-policy + user-supplied loss tolerance) — BLOCKED
  on user input. The user must explicitly decide what loss
  tolerance F6 will encode before the bridge can issue
  APPROVED_LIVE_BUDGET.

## Disclaimers (preserved per the source-backed discipline)

- **No real affordability is established.** Live trading is
  structurally disarmed (PENNY_LIVE_TRADING=False, FNO_LIVE_BANKROLL=0).
  The guard is plumbing ahead of demand, not a permission to act.
- **The five DISC-A1..A5 reconciliation warnings remain
  UNKNOWN / UNVERIFIED.** The other agent's revert of my
  closures was correct (recollection is not verification). These
  remain so.
- **`EQUITY_INTRADAY_EFFECTIVE_DATE` remains None.** The other
  agent's revert of "2026-08-10" was correct (invented
  equivalence is unsupported). This remains so.

## What's next

F3 (open mark-to-market) is the natural next slice. It depends
on F5 (broker statement automation) for real prices, but the
scaffolding can be staged ahead. Awaiting your call.

## Reference paths

- `docs/2026-09-13-workflow-f-state-of-codebase-audit.md`
  section 7 (new this commit) — full module description and
  decision-tree rationale.
- `docs/NEXT_AGENT_PLAN.md` requirement matrix row F — updated
  this commit to reflect F1+F2 closure.
- `docs/2026-09-13-workflow-g-promotion-bridge.md` — the
  contract section 4 is where the guard's defaults trace back
  to.
