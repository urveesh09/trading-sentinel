# Workflow C.F2 — defensive runtime cap on research_quote_collection_tick (F-2 from prod audit)

## Source

Per the 2026-09-16 production deep audit F-2:
> 🟡 F-2 (MED): Scheduler cascade-skip persists (improved from yesterday)
> - 8 penny skips, 60 MAX_INSTANCES total (research_quote + fno_tick dominate).
> - The `penny_scan_interval` fix from PR #92 partially worked (8 down from 32), but the underlying issue is **per-scan runtime > trigger interval** for `research_quote_collection` (14s avg on 60s trigger, but max 114s — overlap guaranteed).
> - Recommended action: Either (a) lengthen `research_quote_collection` trigger from 60s → 180s, OR (b) parallelize the archive writer (which C.B.1 race-fix already addressed — but the runtime is still too long).

Per the user's directive on 2026-09-16: "the operator call for F-2 I give you permission to decide as long as you remember that our goal is to earn good and fast profit with minimum loss."

**Decision: keep the 60s cadence; cap tail latency.** Lengthening the trigger to 180s would mean stale prices every 3 minutes — operators want fresh data every 60s for fast decisions. The bounded fix is a **soft runtime cap** that breaks the per-underlying loop early when the tick is running long, returning whatever data has been collected.

## What landed

| File | Type | Purpose |
|---|---|---|
| `python-engine/config.py` | source (extended) | New `RESEARCH_QUOTE_RUNTIME_CAP_SEC` setting (default 48.0) |
| `python-engine/research_quote_collector.py` | source (extended) | New `runtime_exceeded` + `partial_collected_ref` params on `collect_rest_quote_snapshot`; cap-checked iteration; `runtime_capped` field on the journal entry |
| `python-engine/tests/test_research_quote_runtime_cap_f2.py` | test (new) | 7 tests pinning the runtime-cap contract |
| `docs/2026-09-16-workflow-c-f2-runtime-cap-done.md` | doc (new) | This file |

## The shift in defensive posture

Before this slice, a slow `research_quote_collection_tick` (e.g., 114s when the trigger fires every 60s) caused a cascade-skip at `apscheduler`: the next tick can't start until the previous one finishes, so it gets skipped. Each skip = 60s of missing market data = potentially missed entry opportunities.

After this slice, the cap fires when the tick exceeds 80% of the trigger interval (48s on a 60s interval). The cap breaks the per-underlying iteration early, returning whatever data has been collected (still useful — partial coverage is better than skip = no coverage). The audit log gains a `runtime_capped` field so operators can distinguish:

| Audit query | Meaning |
|---|---|
| `SELECT count(*) WHERE runtime_capped=True` | Slow ticks that hit the cap |
| `SELECT count(*) WHERE runtime_capped=False AND elapsed_sec < cap` | Normal ticks |
| `SELECT count(*) WHERE elapsed_sec > trigger_interval` | Tail-latency outliers |

The first query tells operators "the cap is firing" — actionable signal. The previous 60 MAX_INSTANCES skips were unattributable; now we know if they're scheduler-skips or runtime-capped returns.

## Key design choices

- **60s cadence preserved.** Operators want fresh data every 60s for fast decisions. We do NOT lengthen the trigger.
- **Cap default = 80% of trigger interval** (48s on 60s). Leaves headroom for the post-loop `archive_journal` write (~5s) so the cap fires BEFORE the journal write, not during.
- **Cap-checked at each underlying boundary**, not per-contract. The NIFTY/SENSEX loop iterates over 2 underlyings; checking between them is the natural granularity. A per-contract check would be too noisy.
- **Soft cap, not hard kill.** A partial result is returned — operators can see what was collected before the cap fired.
- **`runtime_capped` is a JOURNAL annotation**, not a log level. The `archive.record_collection_run()` call sees the field so future audit SQL can filter on it.
- **`elapsed_sec` is in the result** so operators can build histograms of tick runtime.

## Defensive regression

| Test file | Tests | Δ |
|---|---|---|
| `test_research_quote_runtime_cap_f2.py` | 7 | +7 (new file) |
| `test_research_archive.py` | 17 | 0 (no changes) |
| `test_research_leg_subscriptions.py` | 10 | 0 |
| `test_research_release_safety.py` | 10 | 0 |

74/74 PASS across `test_kite_client*.py` + `test_research_*.py` + `test_research_quote_runtime_cap_f2.py`. Zero regressions.

## Test discipline

7 tests pin the contract:
- `test_runtime_cap_disabled_when_callable_none`: legacy callers (no `runtime_exceeded`) work unchanged.
- `test_runtime_cap_engages_when_callable_returns_true`: cap fires → loop breaks → `partial_collected` set on result.
- `test_partial_collected_ref_is_updated_incrementally`: the ref dict accumulates across contracts.
- `test_no_cap_when_no_runtime_exceeded_passed`: default-no-arg case preserves legacy behaviour.
- `test_partial_collected_zero_when_no_quotes_returned`: cap fires before any contract → `partial_collected=0`.
- `TestRuntimeCapConfig::test_default_cap_is_48_seconds`: the hard-coded default is 48s.
- `TestRuntimeCapConfig::test_cap_is_less_than_or_equal_to_trigger_interval`: invariant — cap must be ≤ interval or it never fires.

## What this does NOT solve

- **The underlying cause** (why some ticks take 114s when avg is 14s) is not addressed. The audit's recommendation was "either lengthen trigger OR parallelize writer" — we chose the third option: cap the tail. The root-cause investigation is operator-owned.
- **Cascade-skip from `fno_tick`** (also flagged at 60 MAX_INSTANCES total) is still cascading. The F-2 fix is scoped to `research_quote_collection`. A separate slice could apply the same cap to `fno_tick` if the operator wants.

## Critical invariants preserved

- `research_quote_collection_tick` public API unchanged (legacy callers still work without `runtime_exceeded`).
- `collect_rest_quote_snapshot` API is additive (`runtime_exceeded` and `partial_collected_ref` are optional kwargs with defaults).
- The cap-discipline is testable in isolation — every test uses a tmp_path DB.
- No new dependencies.
- `RESEARCH_QUOTE_INTERVAL_SEC` (60s) unchanged.

## Operator runbook

After deploy to PROD:

1. Operators can run `SELECT count(*) FROM research_runs WHERE runtime_capped=True` to see how often the cap fires.
2. If the cap fires >10% of ticks, the underlying cause (slow SQLite writer, slow Kite API, etc.) needs investigation.
3. The cap default (48s) can be overridden via `RESEARCH_QUOTE_RUNTIME_CAP_SEC` env var if the audit shows the cap is too aggressive.

## Audit-trail summary

```
e2fe147  C.F5     -- J.10 features inventory CLI
729f7f1  C.F2     -- Kite LTP fanout observability (audit naming; this slice is C.F2-of-audit-2026-09-16)
0ba14a9  C.B.3    -- penny_universe stale warning dedup
dfc306a  C.C1     -- structured asymmetric-fill diagnostic
04aa166  C.B.2    -- agent dedup file observability
7cf87c3  C.B.1    -- research finalize_prior_days race fix
63d46ad  C.F8     -- bankroll_ledger TRADE_OPENED audit trail
49456be  C.B1+B3  -- held-out adequacy + settlement assumptions
31bf71d  C.C2     -- asymmetric partial-fill pricing model
315fa72  C.C2.WIRE -- wire partial-fill model into replay
045661d  J.10.DRY_RUN_ATTRIBUTION -- surface real vs simulation captures
d212250  D.1      -- release-readiness test receipt
40e31b0  C.F1     -- defensive alert dispatch (F-1 from 09-16 audit)
[pending] C.F3     -- cache_miss_reason observability (F-3 from 09-16 audit)
[pending] C.F2     -- runtime cap on research_quote_collection (F-2 from 09-16 audit)
```

PROD untouched. Dev only.
