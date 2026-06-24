# 2026-06-24 — Penny hourly report: diagnostic breakdown in no-action case

## Problem

The Telegram hourly heartbeat for the penny subsystem currently
reports only:

```
No action in Penny this hour. (regime: PR1_CALM, open: 0/5, deployed: Rs 0)
```

This is a *symptom* with no *cause*. On 2026-06-24 the operator
(Uru) received this report for two consecutive hours and asked:
"is the universe too small (100) or are the filters too tight?"

The honest answer required digging through the penny module manually
to find:

- `PENNY_UNIVERSE_SIZE=100` truncates the universe before filters
  (`config.py:162`)
- `PENNY_MIN_20D_TV=500_000` (Rs 5 lakh 20-day median traded value)
  is the most aggressive filter (`config.py:163`, enforced at
  `penny_universe.py:115`)
- `penny_universe.py` filter loop uses bare `continue` — it never
  logs *why* a ticker was rejected at the universe-eligibility stage,
  so the existing `reject_reason` column in `penny_signals` only
  captures strategy-level rejects (RSI not < 10, breakout not
  confirmed, volume too low), not universe-level (price band, TV,
  promoter, P/B)

Without the operator having these facts surfaced *by the report
itself*, every "No action" hour requires manual archaeology in
the code to debug. This is not acceptable for a production
heartbeat (spec §9.4: "A missing report is itself an alert" — the
same principle implies an *uninformative* report should also be
treated as a failure mode).

## User intent

Uru 2026-06-24: "two hours have gone by, and I got the report from
Telegram for my penny module that no action was taken yet ... maybe
the filters we have put are very hard for it to take any action ...
should we expand the scope from 100 to 500? Or what do we do just
for the enrichment of our software now?"

The user's question reveals two sub-goals:

1. **Diagnose**: understand whether the empty hour is universe
   under-supply (small candidate pool) or filter over-tightness
   (candidates exist but strategies don't fire).
2. **Decide later**: do not pre-commit to "expand to 500" or "soften
   filters" without evidence. ("More data? is often a flag to look
   at labels, not a request to scrape" — user-profile memory rule.)

The investigation must precede the decision.

## Decision

Add a **second line** to the no-action case in the hourly report:

```
No action in Penny this hour. (regime: PR1_CALM, open: 0/5, deployed: Rs 0)
Scanned: 87 | top rejects: RSI(2)=14.3 not below threshold (×42), breakout not confirmed (×18), volume too low (×11)
```

Where:

- `Scanned: N` — how many tickers the scanner observed this hour.
  Comes from the latest penny scan's `accept + reject + error` count.
  If unknown, the line is omitted entirely (backwards-compatible).
- `top rejects:` — top 3 reject reasons from the `penny_signals`
  table in the last hour, sorted by descending count, with the
  reason string truncated to 50 chars + ellipsis to stay bounded.

**What this is NOT:**

- Not a loosening of any filter. `PENNY_MIN_20D_TV`, `PENNY_UNIVERSE_SIZE`,
  and the four hard filters are unchanged. The diagnostic is purely
  observational.
- Not a CSV/log exporter. The hourly Telegram heartbeat is the
  only delivery surface. For deep dives, the existing
  `penny_signals` SQLite table is the source of truth.
- Not a fix for the underlying scarcity of penny entries. The
  strategy triggers (RSI(2) < 10, 3× volume breakout) are rare by
  design — that's the Connors strategy profile, not a bug.

**What Task B (loosen `PENNY_MIN_20D_TV` 5L→2L) was deferred:**

Uru approved "Ship A only now, B after one morning of diagnostic
data." This deviation intentionally does NOT touch the TV floor.
After one trading morning of diagnostic data, the operator will
have evidence to decide:

- If top reject is "RSI(2) not below threshold" with high counts
  → strategy triggers are too tight, not universe
- If top reject is "volume too low (dead stock)" with high counts
  → liquidity filter is the real ceiling, Task B justified
- If `Scanned: N` is consistently tiny (<30) → universe size is
  the real ceiling, expand Task C/D
- If `Scanned: N` is reasonable but the report shows
  "no rejection rows logged" → scanner died before logging;
  investigate scanner crash, not strategy

## Implementation

### `penny_hourly_report.py` — the report itself

1. Added `universe_size: int = 0` parameter to `PennyHourlyReport.build_report`.
   Defaults to 0 so older callers (pre-2026-06-24 tests, anyone
   not yet on this commit) see the legacy single-line form.

2. Added `_build_diag_tail(reject_reasons, universe_size, top_n=3)`
   static helper. Returns:
   - `""` if both universe_size == 0 AND no rejections
   - `"Scanned: N | (no rejection rows logged)"` if universe known
     but no rejects (scanner may have died)
   - `"Scanned: N | top rejects: r1 (×c1), r2 (×c2), r3 (×c3)"`
     when both are present, sorted descending by count

3. The no-action path now returns:
   ```python
   head + "\n" + diag   # if diag is non-empty
   head                  # otherwise (backwards-compat)
   ```

   Hard constraints preserved: body still <1000 chars, ≤15 lines.

### `main.py` — plumbing

Added module-level global `_last_penny_scan_universe_size: int = 0`
that:

- Is set in `run_penny_scanner_once()` after each 30-second scan to
  `result["accept"] + result["reject"] + result["error"]`.
- Is set in `run_penny_connors_scan()` after the daily 09:30 CNC
  pass to `len(universe)`.
- Is read by `run_penny_hourly_report()` and passed through to
  `penny_hourly_report.run_hourly_report(universe_size=...)`.

This avoids coupling `penny_hourly_report` to the scanner (which
would violate the strict-separation rule). The hourly report
already imports from `config`, `penny_models`, `penny_signal_log`,
`penny_risk`, stdlib — and that's the allow-list per the module
header docstring (test `test_penny_isolation` enforces this).

### Threading

`penny_hourly_report.run_hourly_report` gained the same
`universe_size: int = 0` parameter and passes it through to
`build_report`. Same default, same backwards-compat behaviour.

## Tests

Six new tests in `tests/test_penny_hourly_report.py`:

| Test | Pin |
| --- | --- |
| `test_diag_tail_empty_when_universe_unknown` | Backwards-compat: `universe_size=0` (default) → no extra line. Single line. |
| `test_diag_tail_shows_scanned_count_only` | `universe_size=87`, no rejects → "Scanned: 87 \| (no rejection rows logged)" |
| `test_diag_tail_shows_top_rejects` | Top 3 sorted by descending count; ×4 before ×2 before ×1 |
| `test_diag_tail_truncates_long_reason_to_50_chars` | 100-char reject_reason clipped to 50 + ellipsis; body still <1000 chars |
| `test_diag_tail_with_diagnostic_stays_under_15_lines` | 10 rejection rows + universe_size → still ≤15 lines (spec §9.4) |
| `test_build_diag_tail_unit` | Static helper direct test: all 4 (universe_known × rejections_present) combinations |

Plus the existing 14 tests in this file still pass — including the
strict <1000-char and ≤15-line invariants for the no-action case.

### Full-suite result

638 passed, 1 skipped, 3 failed (pre-existing order-dependent
failures also present on `b0f5bcb` baseline — not caused by this
change):

- `tests/test_performance.py::TestPoolBreakdown::test_paper_mode_uses_paper_bankroll`
- `tests/test_performance.py::TestPoolBreakdown::test_paper_mode_penny_trades_still_tracked`
- `tests/test_universe_expansion.py::test_load_universe_with_fallback_uses_csv_when_present`

These three pass when run in isolation (`pytest tests/test_performance.py`
and `pytest tests/test_universe_expansion.py` independently both
show 100% green). They are flaky tests that need separate cleanup;
out of scope for this diagnostic add.

## Files

- `python-engine/penny_hourly_report.py` — `build_report` signature
  extended, `_build_diag_tail` static helper added, no-action path
  extended. Module header docstring still enforces the
  strict-separation allow-list (penny_models, penny_signal_log,
  penny_risk, config, stdlib).
- `python-engine/main.py` — module-level
  `_last_penny_scan_universe_size` global; updated in
  `run_penny_scanner_once` and `run_penny_connors_scan`; passed
  into `run_hourly_report`.
- `python-engine/tests/test_penny_hourly_report.py` — 6 new tests
  at the bottom of the file.