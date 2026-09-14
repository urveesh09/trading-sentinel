# J.3 — broker-behaviour capture scaffolding: done and committed

## What landed (three commits on `codex/production-correction-hedge-p0`)

| Commit    | Increment | Files changed | Tests added |
|-----------|-----------|---------------|-------------|
| `6019279` | J.3.1 probe quality + classifier `cas_eligible` kwarg | `market_calendar.py` + `tools/j2_cas_probe.py` + 2 test files (+851/-14) | +56 (38 probe-quality + 18 classifier kwarg) |
| (this slice) | J.3.0 capture review tool + 17 tests | NEW `tools/j2_capture_review.py` + NEW `tests/test_j3_capture_review.py` | +17 |
| (this slice) | J.3.runbook operator protocol doc | NEW `docs/2026-09-13-j3-capture-protocol.md` | none |

## Architecture

The J.3 deliverable is **the scaffolding** that lets staging captures
land and be reviewed. Three artefacts:

1. **Sharpened probe** (`tools/j2_cas_probe.py` after J.3.1). Bumped to
   `SCHEMA_VERSION: 2`. Inline JSON Schema for every emitted document.
   New flags: `--schema-print`, `--eligibility-list`, `--require-eligible`,
   `--validate`. Strict ISO 8601 parser (rejects naive timestamps).
   Resolves eligibility once per row and passes the explicit boolean
   to the classifier (J.3.1 fix to the boundary-defect).

2. **Static review tool** (`tools/j2_capture_review.py`). Reads a
   captured JSON, runs the six-point checklist + an opt-in OHLC
   continuity check between two captures of the same symbol on the
   same trading day. Exits 0 only when every check passes.

3. **Operator protocol** (`docs/2026-09-13-j3-capture-protocol.md`).
   Six-window capture grid (15:10 / 15:17 / 15:22 / 15:27 / 15:32 /
   15:42 IST), exact invocations, six-point review pass criteria, and
   failure-handling discipline (no silent retries).

## Why three sub-slices

- **J.3.1** shipped first because testing the review tool
  required a probe that could honor the `--eligibility-list` override
  end-to-end. The override revealed a contract defect in the J.1
  classifier (the CAS branch consulted settings lookup, so the
  override didn't reach the CAS sub-window branches). J.3.1 added
  an explicit `cas_eligible: bool | None = None` kwarg on
  `classify_session_phase` with the senior-dev boundary:
  *callers resolve eligibility; the function does not decide it*.
  The default `None` preserves J.1 byte-identity; new callers pass
  the explicit value.
- **J.3.0** is the deterministic half — the review tool runs in Dev
  without a broker, against synthetic captures. Every PASS and
  every documented FAIL mode has a pinned test (17 tests across 5
  classes).
- **J.3.runbook** is the bridge to staging. It tells the operator
  exactly which invocations to run, in what order, and what
  evidence to commit.

## Honest self-corrections during J.3

1. **The boundary-defect (caught during the first test).** The
   J.3.1 parameterised test `test_cas_sub_windows_correct[15-37-
   CAS_POST]` failed with `CLOSED` instead of `CAS_POST`. Root
   cause: `classify_session_phase` consulted `is_cas_eligible`
   internally, but the probe's `--eligibility-list` override did
   not reach the classifier. Fixed by adding an explicit
   `cas_eligible` kwarg on the classifier (default `None` for
   legacy compat). Six J.2-monkeypatched tests continue to drive
   the legacy path; the new `TestClassifierCasEligibleKwarg`
   pins every boundary in the explicit path.

2. **Mutable-default-value trap (caught during the second test).**
   `_good_row(quote=None)` was re-interpreted as "use the
   default" because the default was also `None`. Fixed with a
   sentinel (`_GOOD_ROW_SENTINEL`, `_QUOTE_NONE`). Lesson:
   explicit ``None`` literals in test fixtures must use a
   distinct sentinel so the default and the explicit value are
   distinguishable.

3. **Same-file collision (caught during the third test).**
   `_write_capture(tmp_path, ...)` writes to `tmp_path/capture.json`
   always; the OHLC-continuity tests passing the same `tmp_path`
   for both captures wrote to the same path. Fixed by changing
   the helper to accept an explicit filename; updated callers to
   pass `tmp_path / "pre.json"` and `tmp_path / "cas.json"`.

4. **dry-run + circuit-limits / broker-extras (caught during the
   fourth test).** Dry-run documents have null quotes; the
   review tool's circuit-limits and broker-extras checks were
   tripping on a dry-run capture. The senior-dev move: dry-run
   documents legitimately lack broker-side data, so those checks
   should *skip* on dry-run, not fail. Fixed by adding the same
   dry-run skip circuit the `quote_present` check already had.

5. **Schema / row enum drift (caught by the inline validator).**
   The J.3.1 inline JSON Schema pinned both the required fields
   and the row enum. The schema validator runs on `--validate`
   and on the review tool's first check, catching a future
   refactor that adds a phase without updating the schema.

## Verification

| Run | Before J.3 | After J.3 |
|---|---|---|
| Targeted J-slice (7 files incl. J.3.1 + J.3.0) | 162 pass | **179 pass** (+17 J.3.0 review tests; -0 regressions) |
| F/G + J critical paths warning-fatal (12 files) | 266 pass | **283 pass** |
| J.1 contract (TestProductionBehaviourPreserved) | 2 pass | 2 pass (no change) |
| Probe CLI smoke (Dev `--dry-run`, 8 windows) | n/a | 8/8 PASS |
| Review CLI smoke (`--expected-eligibility`, 6 fail modes + 1 pass) | n/a | 17/17 PASS |

## What was NOT changed (explicitly preserved)

- `proactive_intelligence.py::stamp_session_phase` — J-forward-compat
  seam, still returns `_SESSION_PHASE_UNKNOWN` for every input.
- `fno_chain.py::EXPIRY_CUTOFF_HOUR/_MIN = 15, 30` and
  `hedge_strategies.py::_EXPIRY_CUTOFF` — operator-sign-off pending;
  J.7 slice owns the migration flag.
- `market-hours.js` (Container B) parity — deferred to J.6.
- Holiday reconciliation Python↔Node — deferred to J.5.
- Any production call site — J.3 is test + tool only; no engine
  call site touches the classifier by a path other than the legacy
  `is_cas_eligible(symbol)` lookup. New callers use the kwarg.
- The `J.1` monkeypatch-driven `TestCASWindows` still drives the
  CAS branches via `is_cas_eligible`. J.3's added `cas_eligible`
  kwarg default `None` preserves that path byte-for-byte.

## Remaining gap (NOT J.3's contract)

- **The captures themselves are operator-supplied artifacts.** The
  scaffolding is in Dev and tested. J.3.x signs off when
  `docs/j2_captures/` carries a per-trading-day set of JSON files
  passing the review tool. Until then:
  - `docs/NEXT_AGENT_PLAN.md` J row remains `IMPLEMENTING`.
  - No CAS-aware strategy is authorised.
  - The broker-behaviour question ("what does Kite actually return
    at 15:17 IST?") remains open.

When the operator runs the protocol and commits the captures,
J.3.x writes `docs/2026-09-13-j3-broker-behaviour-verified.md` with
the per-capture summary. That slice promotes J row to
`TESTED_DEV` (or back to IMPLEMENTING with the captured defect,
if any capture fails).

## Commits & history

```
6019279  feat(J.3.1): probe quality + explicit classifier cas_eligible kwarg
<this>    feat(J.3): broker-behaviour capture review tool + runbook
```

Branch: `codex/production-correction-hedge-p0`. Local only — not
pushed, not deployed, not promoted to Production. Production
application containers are still observed stopped per
`docs/HANDOVER_CHECKLIST.md`; the user has not authorised restart.
