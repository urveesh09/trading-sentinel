# I.B (banner provenance) — done and committed

## What landed (commit `d1e7d4f`)

**Branch**: `codex/production-correction-hedge-p0`
**Files changed**: 3 (1 modified in source, 1 modified in tests, 1 new), +357 / -13 lines.

| File | Lines | Purpose |
|---|---|---|
| `agent/advisory.py` | +57 / -13 | `Review.banner()` now appends provenance suffix; new `_provenance_suffix()` helper handles format + edge cases. |
| `agent/tests/test_optional_ai_provenance.py` | -13 / +8 | I1 banner test re-pointed at the new file (contract change, not regression). |
| `agent/tests/test_review_banner_provenance.py` | NEW, 21 tests | Banner provenance acceptance: presence, format, length, verdict-specific, backwards-compat. |

## The contract change

### Before I.B

```
AI approved (conviction 72/100)
AI approved WITH CONCERNS (conviction 55/100)
AI REJECTED (conviction 20/100)
AI review UNAVAILABLE (timeout_100s) - unreviewed
```

### After I.B (when provenance is populated)

```
AI approved (conviction 72/100) · MiniMax-M3@v1 1.5s
AI approved WITH CONCERNS (conviction 55/100) · MiniMax-M3@v1 1.5s
AI REJECTED (conviction 20/100) · MiniMax-M3@v1 1.5s
AI review UNAVAILABLE (timeout_100s) - unreviewed · MiniMax-M3@v1 120.0s
```

### After I.B (when provenance is absent — legacy reviews)

```
AI approved (conviction 72/100)
... (no suffix; absence IS the signal that the call did not complete)
```

## Senior-dev design choices

1. **Suffix is opt-out by absence.** Half-provenance (only `model` OR only `prompt_version`) is treated as no-provenance. The contract requires both fields; emitting half would mislead operators.
2. **`?s` for missing response_seconds.** Honest about missing data, no fake zero. An operator sees `?s` and knows the call did not complete.
3. **Sub-100ms clamp at 0.1s.** Defensive against clock skew. A 0.05s review renders as `0.1s`, not `0.0s` (which would look like a no-op).
4. **`@` separator.** Visually separates model from prompt_version. Operators can scan the alert without context.
5. **UNAVAILABLE also gets the suffix.** Operators may want to know which prompt timed out — the failure context matters.
6. **Banner stays bounded.** All four verdict banners are < 200 chars; well within Telegram's 4096-char limit, well within the operator's readability budget.

## Verification

| | Before I.B | After I.B |
|---|---|---|
| **Agent suite** | 153 pass | **174 pass** (+21) |
| **python-engine suite** | 3,047 pass | 3,047 pass (unchanged) |
| **Dashboard build** | OK | OK |
| **Time** | 142.67s | 141.58s |
| **Skipped / warnings** | 4 / 42 | 4 / 42 (no new categories) |

## Self-corrections during I.B

1. **Stale I1 assertion.** My own I1 test `test_banner_includes_verdict_not_provenance` asserted that the banner contained no provenance. I.B's contract change supersedes that; the test is updated to point at the new dedicated file. This is a **contract change**, not a regression — the I1 contract said "store provenance"; the I.B contract says "show provenance." The change is captured in a documented test docstring.

2. **Patch output misled me earlier.** Your reminder about `ReconciliationEvidence` and `OperationalCoverage` was correct discipline. I confirmed via `git diff --stat` that the actual diff was 36 insertions, 0 deletions — both functions are still in the file. The patch tool's output had re-flowed line-endings (LF vs CRLF) of unrelated lines, which made it *look* like a much larger change. The actual code change was minimal and surgical. Lesson: always cross-check the patch tool's output against `git diff --stat` before assuming scope.

## I.A + I.B combined state

Two of the four recommended slices from `docs/2026-09-13-i4-deep-research.md` are now SHIPPED:
- ✅ **I.A** — bridge I3 usefulness metrics from agent to engine (`980636e`)
- ✅ **I.B** — surface I1 provenance in the operator alert (`d1e7d4f`)

Remaining recommended slices:
- **I.C** — `operational_coverage_report` includes optional AI
- **I.F** — cross-container contract test

## Next steps

Awaiting your call to proceed to I.C, I.F, or another slice.
