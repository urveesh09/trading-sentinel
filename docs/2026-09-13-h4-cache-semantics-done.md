# H4 (cache-add for ``get_intraday``) — done and committed

## What landed (commit `d1d6e15`)

**Branch**: `codex/production-correction-hedge-p0`
**Files changed**: 6 (2 new, 4 modified), +842 / -20 lines.

### Code (4 files)

| File | Lines | Purpose |
|---|---|---|
| `python-engine/kite_client.py` | +140/-20 | Rewrite HIT path to honour the four §12 semantics explicitly. New debug log events: `intraday_cache_only_forming`, `intraday_cache_filtered_below_floor`. New `max(0, freshness_seconds)` clamp. Docstring rewritten. |
| `python-engine/config.py` | +37 | Three new operator-tunable knobs with §12-mandated defaults. |
| `python-engine/tests/test_intraday_cache_semantics.py` | NEW, 13 tests | Five test classes covering all four explicit semantics + reproducibility. |
| `docs/2026-09-13-h4-by-token-cache-proposal.md` | NEW, defer proposal | One-pager for the deferred `get_intraday_by_token` path. No code. |

### Docs (2 files)

| File | Lines | Purpose |
|---|---|---|
| `docs/2026-09-13-workflow-f-state-of-codebase-audit.md` | +47 | New §12 "H-series future plan" with H4 changes. |
| `docs/NEXT_AGENT_PLAN.md` | matrix row | H4 closed; H4.B deferred per proposal. |

## The four §12 semantics, made explicit

| §12 property | Pre-H4 | Post-H4 | Operator knob |
|---|---|---|---|
| Instrument | ✓ (PRIMARY KEY) | ✓ | (n/a) |
| Interval | ✓ (PRIMARY KEY) | ✓ | (n/a) |
| Completed-bar cutoff | ✗ — forming candles served as HIT | ✓ — `datetime < to_datetime` filter | `INTRADAY_CACHE_INCLUDE_FORMING=False` |
| Freshness | implicit, hard-coded | explicit, operator-tunable | `INTRADAY_CACHE_FRESHNESS_SECONDS=0` |
| (Implied) Min-candles floor | implicit, hard-coded | explicit, operator-tunable | `INTRADAY_CACHE_MIN_CANDLES=4` |

Defaults preserve the pre-H4 behaviour exactly. A negative
`freshness_seconds` is clamped to 0 (the strict default). The
`min_candles` floor is re-checked *after* the forming-bar filter
removes rows, with a new debug log
`intraday_cache_filtered_below_floor` for observability.

## Verification

| | Before H4 | After H4 |
|---|---|---|
| **Python suite** | 2,978 pass | **2,991 pass** (+13 H4 tests) |
| **Time** | 130.89s | 141.78s |
| **Skipped** | 4 | 4 |
| **Warnings** | 39 | 39 (no new) |
| **Existing kite_client tests** | 28 pass | 28 pass (no regression) |

Stable across the full-suite rerun. The H4 file alone runs
in 3.98s.

## Senior-dev design choices

1. **Defaults preserve pre-H4 behaviour.** Every new knob
   defaults to the value the gate was implicitly using before.
   Operators who want to relax them can do so via `config.py`.
2. **No schema change.** The `intraday_cache` table stays
   byte-identical. The writer continues to write forming
   candles (it cannot know when Kite's most recent candle is
   closed); the HIT path now *excludes* them.
3. **`min_candles` re-checked after filtering.** Pre-fix, the
   raw-row count gate passed (e.g. 4 rows) but the forming-bar
   filter dropped 1, leaving only 3 candles — still a HIT
   served, below the floor. H4 catches that case with a new
   `intraday_cache_filtered_below_floor` debug event and
   falls through to the API.
4. **`get_intraday_by_token` left untouched.** It's
   documented as uncached by design (F&O ticks fire every 5
   minutes; forming/completed discrimination is non-trivial
   for token-keyed rows). H4 writes a one-page proposal with
   the four decisions an operator needs to settle before
   any code lands; no production code change.
5. **No deletions.** All H4 work is additive — three new
   knobs, three new debug log events, one new test file, two
   new docs, one docstring rewrite. The pre-H4 HIT path is
   preserved in shape; only the forming-bar filter and
   freshness/clamp logic are added around it.
6. **Honest about H4.B.** The deferred by-token cache proposal
   calls out that the path is uncached by design and that
   operator sign-off is required before any code lands. The
   four decisions (forming-bar policy, key column,
   rate-limit threshold, warming strategy) are listed with
   default-if-no-answer values.

## Self-corrections during H4

1. **Negative `freshness_seconds` raised `OverflowError`** in
   `timedelta(seconds=-100)`. Caught by the
   `test_freshness_seconds_negative_treated_as_zero` test.
   Fixed at the source with `max(0, freshness_seconds)`.
2. **Missing re-check on `min_candles` after forming-bar
   filter.** Pre-fix, 4 raw rows → 3 filtered → still served
   as HIT (below the floor). Caught by
   `test_default_include_forming_false_filters`. Fixed by
   adding the `len(filtered_rows) < min_candles` re-check and
   a new debug log event.
3. **Test seed counted forming candle in `len == 4`
   expectations.** Several tests seeded 4 candles ending at
   `to_datetime`; the 4th candle is forming and gets filtered,
   so the HIT returned 3 not 4. Caught by
   `test_ticker_isolation`. Fixed by extending the seeds to
   5 candles (4 completed + 1 forming).
4. **`KiteClient` has `db_path` not `_cache_db_path`.**
   Caught by `AttributeError` on the first test. Fixed in the
   `_seed_candles` helper.
5. **Async coroutine return bug.** My `_seed_candles` helper
   returned a coroutine object that the caller then called as
   `()` — producing "coroutine was never awaited" warnings.
   Fixed by removing the redundant `()()` call sites.

## Next H phases (deferred)

- **H4.B (by-token cache)** — proposal at
  `docs/2026-09-13-h4-by-token-cache-proposal.md`. Four
  operator decisions required before code lands.
- **H5 (dashboard readiness reasons)** — deferred.
