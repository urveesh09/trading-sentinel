# J.2 (CAS eligibility list + broker-behaviour probe) — done and committed

## What landed (three commits on `codex/production-correction-hedge-p0`)

| Commit    | Increment | Files changed | Tests added |
|-----------|-----------|---------------|-------------|
| `ba117fb` | J.2.1 eligibility list | `config.py`, `market_calendar.py`, `tests/test_session_classifier.py` (+274/-13) | +6 (`TestIsCasEligible`) |
| `f6e07da` | J.2.2 broker-behaviour probe | NEW `tools/j2_cas_probe.py`, NEW `docs/2026-09-13-j2-broker-behaviour-probe.md` (+618) | none (tool not exercised by pytest per the prompt) |
| (this commit) | J.2 docs sweep | `SYSTEM_CODE_ATLAS.md` (regen + 1 entry), `SYSTEM_GUIDE.md` (J section), `NEXT_AGENT_PLAN.md` (J row) | none |

## J.2.1 — Operator-supplied eligibility list

**Config.** Added `CAS_PHASE1_FNO_UNDERLYINGS: str = ""` in
`python-engine/config.py`. Wire format is plain CSV (env var
`CAS_PHASE1_FNO_UNDERLYINGS="RELIANCE, HDFCBANK, INFY"`). Deliberately
*not* typed `tuple[str, ...]` — pydantic-settings v2.2.1 auto-JSON-
decodes complex fields, which would force operators to write JSON in
their `.env`. Keeping the wire format as a string sidesteps the JSON
trap and lets `is_cas_eligible` normalise at the point of use.

**Behaviour.** `is_cas_eligible(symbol)` now consults
`settings.CAS_PHASE1_FNO_UNDERLYINGS`. Defensive guard order:
1. None / non-string / empty symbol → False (no `config` import).
2. Lazy `from config import settings` — survives import errors
   (returns False; the classifier is total).
3. Normalise symbol (`strip().upper()`) and the configured CSV
   (split on `,`, strip + upper + drop empties). Result is a
   `frozenset[str]` built once per process via
   `@functools.lru_cache(maxsize=1)`.

**Tests.** 6 new tests in `TestIsCasEligible`:
- empty list returns False for any symbol (incl. None / empty /
  non-string defensive inputs),
- symbol in list returns True,
- case-insensitive match (upper / lower / mixed),
- whitespace stripped (input symbol + configured list entries),
- lazy import does not crash on `config` import failure,
- CSV parser tolerates whitespace / double commas / mixed case /
  empty / whitespace-only.

## J.2.2 — Broker-behaviour probe (staging-only CLI)

**Tool.** NEW `python-engine/tools/j2_cas_probe.py` (~290 lines). The
operator runs it in staging (NOT in Dev — Dev has no live Kite
session). Captures, per `--symbols` and one or more `--observation-at`
instants: the classifier verdict, the CAS-eligibility verdict, the Kite
quote (cash fields + upper/lower circuit + `broker_extra_fields` for
any CAS-window-specific keys Kite appends).

Flags: `--symbols` (required, CSV) / `--observation-at` (ISO 8601,
IST-aware) | `--now` (current IST, mutually exclusive) /
`--output` (path, default stdout) / `--dry-run` (no broker call —
for Dev sanity checks). Exit codes: `0` ok, `1` broker error,
`2` config error.

**Procedure.** NEW `docs/2026-09-13-j2-broker-behaviour-probe.md`
documents the operator workflow: sanity-check the wiring in Dev with
`--dry-run`, pick two CAS sub-windows (e.g. 15:17 + 15:32) plus a
pre-CAS reference (e.g. 15:10), run the probe in staging, review
against the six-point checklist (eligibility true for every symbol,
classifier phase matches the IST window, quote non-null, circuit
limits present, `ohlc.close` matches the pre-CAS close,
`broker_extra_fields` non-empty), and only after ALL pass enable a
future CAS-aware strategy.

**NOT exercised by automated tests** — per the prompt. pytest does
not import the tool; CI does not run it. The "test" is the
operator's manual review of the captured JSON.

## Verification table

| Run | Before J.2 | After J.2 | Notes |
|---|---|---|---|
| Targeted J-slice (5 files: classifier + placeholder + market_cal + calendar_gates + calendar_and_band_fixes) | 79 pass | **106 pass** | +27 includes 6 new TestIsCasEligible plus the rows that grew over intervening arcs. No regression. |
| F/G + J critical paths (10 files warning-fatal) | 225 pass | **210 pass** | Drop from 241 → 210 is not a regression: this run drops the proactive-execution/exit/portfolio/diagnostics/market_data files that triggered cross-test isolation noise (the handoff doc's documented Windows-specific intermittent failures). The F/G + J files the prompt explicitly lists all pass. |
| `TestProductionBehaviourPreserved` (2 tests) | 2 pass | **2 pass** | `stamp_session_phase(observation_at=…)` still returns `"UNKNOWN"` for every input. `is_market_open` unchanged. Zero production behaviour change. |
| Probe CLI smoke (Dev `--dry-run`) | — | **6/6 pass** | help text, default flag set, valid invocation (15:17 IST), `--now`, empty symbols rejected (exit 2), unparseable timestamp rejected (exit 2). |
| Cross-test isolation noise | 2 intermittent failures in `test_mark_to_market.py` + `test_scheduler_h2_timing_tiers.py` per the handoff doc | **Same 2 files still subject to cross-test noise**, NOT introduced by J.2. Verified in isolation: all targeted tests pass cleanly. | |

## Honest self-corrections during J.2

1. **Pydantic-settings v2 JSON-decode trap (caught before commit).**
   First cut typed the field as `tuple[str, ...]` per the handoff
   doc's recommendation. Live verification immediately surfaced the
   JSON-decode error: pydantic-settings v2.2.1 calls
   `decode_complex_value` on `list`/`tuple` fields BEFORE the
   `field_validator` runs, so a CSV env var breaks Settings
   instantiation. Two redesigns attempted before settling: (a) tuple
   + validator (didn't work — validator never sees the raw string),
   (b) `str` field with parser inside `is_cas_eligible` (works,
   keeps operator `.env` friendly). Documented the rationale inline
   and in the field docstring.

2. **`lru_cache` mocking in tests (caught and corrected before
   commit).** First cut of `TestIsCasEligible` monkeypatched
   `_normalised_cas_eligibility_set` to fake a populated list. The
   test failed because `is_cas_eligible` short-circuits on empty
   `settings.CAS_PHASE1_FNO_UNDERLYINGS` *before* calling the helper.
   Reframed the tests to monkeypatch `settings.CAS_PHASE1_FNO_UNDERLYINGS`
   directly (real-thing integration test). The helper-only unit test
   is still present as `test_csv_whitespace_tolerance_in_parser`.

3. **Test fixture isolation.** Dropped the `autouse=True` `importlib.reload`
   fixture I'd drafted; it would re-execute the module's top-level
   imports and risk silent side effects across the test file. Replaced
   with explicit `cache_clear()` calls in each test that mutates the
   state.

4. **Docstring deletion in test file.** Inadvertently deleted the
   `TestProductionBehaviourPreserved` docstring with a too-broad
   `patch` `old_string`. Caught on second read and restored the
   docstring in a follow-up patch. Final tree-diff confirms the
   class shape is unchanged.

## What was NOT changed (explicitly preserved)

- `proactive_intelligence.py::stamp_session_phase` — still returns
  `_SESSION_PHASE_UNKNOWN` for every input. The G forward-compat
  seam is preserved exactly.
- `fno_chain.py::EXPIRY_CUTOFF_HOUR/_MIN = 15, 30` — the 15:30 → 15:40
  mismatch for derivatives is documented but not fixed (per plan §14:
  "Preserve earlier strategy deadlines unless explicitly revised and
  qualified").
- `hedge_strategies.py::_EXPIRY_CUTOFF = time(15, 30)` — same.
- `kite_client.py` — out of scope; the probe uses its public
  `get_quote` API.
- `market-hours.js` (Container B) parity — deferred.
- Holiday reconciliation Python↔Node — deferred.
- Dashboard — no change required (the classifier is engine-internal).

## Honest scope statement

J.2 is the **smallest correct second slice**. It wires the existing
J.1 classifier to the operator-supplied CAS eligibility list and
ships the staging-only evidence-collection tool that J.3 (or any
future CAS-aware strategy) needs to be eligible to run. It does NOT
authorise any CAS-aware trading behaviour. The classifier is the
seam; the probe is the receipt; nothing in between is a strategy.

## Remaining gap (NOT J.2's contract)

- **Broker-behaviour verification pending.** The probe must run in
  staging with a live Kite session, at IST 15:15-15:35, and the
  captured JSON must pass the six-point operator checklist. Until
  that happens, `is_cas_eligible` returning `True` is necessary but
  NOT sufficient for any CAS-aware strategy to be trusted. The next
  slice (J.3 or whatever the user names) consumes the captured
  evidence and decides whether the classifier's CAS branches are
  broker-faithful.

## Commits & history

```
ba117fb  feat(J.2.1): operator-supplied CAS Phase 1 F&O eligibility list
f6e07da  feat(J.2.2): CAS-window broker-behaviour probe procedure (staging-only CLI)
<this commit>  docs(J.2): system docs regenerated after J.2 implementation
```

Branch: `codex/production-correction-hedge-p0`. Local only — not
pushed, not deployed, not promoted to Production. Production
application containers are still observed stopped per
`docs/HANDOVER_CHECKLIST.md`; the user has not authorised restart.
