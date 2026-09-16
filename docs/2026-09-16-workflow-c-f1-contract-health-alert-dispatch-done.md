# Workflow C.F1 — defensive alert dispatch in contract_health_cron (F-1 from prod audit)

## Source

Per the 2026-09-16 production deep audit (just captured today):

> 🔴 F-1 (HIGH, NEW): `contract_health_cron` TypeError fires every hour
>
> **Evidence:**
> ```
> 2026-09-16 09:28:11  WARNING  contract_health_alert_dispatch_failed
>   File "/app/contract_health_cron.py", line 140, in contract_health_cron_tick
>   TypeError: send_telegram_alert() missing 1 required positional argument: 'review'
> 2026-09-16 10:28:11  WARNING  contract_health_alert_dispatch_failed (same traceback)
> ... (15:28:17 too — fired every hour from 09:28 to 15:28, 7 fires)
> ```
>
> **Root cause:** `contract_health_cron.py:140` calls `alert_fn(alert_text)` but `send_telegram_alert()` requires a `review` argument. This is a **signature regression** introduced either in PR #87 (I.4.E contract-health work) or a subsequent change.
>
> **Impact:** Hourly contract-health alerts are silently dropped. If a real contract-health incident occurred (e.g. a stuck scanner), no Telegram notification would fire. By-design the contract-health cron is supposed to escalate problems to the operator; this is broken.
>
> **Recommended fix (Dev branch):** In `python-engine/contract_health_cron.py` line 140, change `alert_fn(alert_text)` to pass the `review` object: `alert_fn(review, alert_text)` or inspect the receiver's signature (defensive `inspect.signature` per trading-sentinel-ops rule 110). Test should pin both signatures (accepts_kwarg=True and False) and the contract that the cron's first call site must satisfy.
>
> **Priority:** HIGH — observability + safety surface broken.

## What landed

| File | Type | Purpose |
|---|---|---|
| `agent/contract_health_cron.py` | source (extended) | New `_dispatch_alert` helper using `inspect.signature` for adaptive alert dispatch |
| `agent/tests/test_contract_health_cron.py` | test (extended) | 8 new tests pinning the dispatch contract across 5 receiver shapes |
| `docs/2026-09-16-workflow-c-f1-contract-health-alert-dispatch-done.md` | doc (new) | This file |

## The shift in defensive posture

Before this slice, the cron's `alert_fn(alert_text)` call site assumed the receiver takes a single `text: str` argument. The real production `send_telegram_alert(signal: Dict, review: "Review")` takes 2 positional args. The signature mismatch raised `TypeError: send_telegram_alert() missing 1 required positional argument: 'review'` every hour — silently dropping all contract-health Telegram alerts.

After this slice, the cron uses `inspect.signature` to detect the receiver's shape and dispatch accordingly:

| Receiver signature | Dispatch |
|---|---|
| `(text)` | `alert_fn(alert_text)` — historical contract |
| `(signal, review, ...)` | `alert_fn({"source": "contract_health_cron", "kind": "violation"}, review)` — production contract |
| `()` | `alert_fn()` |
| `(*args)` | `alert_fn(review, alert_text)` |

The cron is now robust to receiver shape changes — receivers can take `(text)`, `(signal, review)`, `(signal, review, extra)`, `(*args)`, or `()` and the cron will dispatch correctly.

## Key design choices

- **Defensive `inspect.signature`** per trading-sentinel-ops rule 110 — the cron inspects the receiver's signature AT DISPATCH TIME, not at module load. Tests injecting custom `alert_fn` overrides still work.
- **Backward compatible**: existing tests (`_StubAlert.__call__(self, text)`) still pass — the 1-arg shape is supported.
- **The "signal" placeholder** carries `{"source": "contract_health_cron", "kind": "violation"}` so the production `send_telegram_alert` receives a structured payload (matching its type signature). Receivers that ignore the `signal` field still see the alert text.
- **Permissive on `*args`**: a `*args` receiver is treated as accepting any count — safer than refusing (a `*args` dispatcher is still valid).
- **Outer try/except unchanged**: a receiver that raises is logged as `contract_health_alert_dispatch_failed` and the cron returns the report normally. The dispatch improvement is purely a "call correctly" fix; the failure-handling boundary is preserved.

## Test discipline

8 new tests in `TestDispatchAlert` + `TestDispatchAlertSignatureRegression`:

| Test | Pin |
|---|---|
| `test_zero_arg_receiver_invoked_with_no_args` | 0-arg shape |
| `test_one_arg_receiver_receives_alert_text` | historical 1-arg shape (test stubs) |
| `test_two_arg_receiver_receives_signal_and_review` | production 2-arg shape |
| `test_three_or_more_required_args_passes_signal_and_review` | defensive 3+ args |
| `test_var_positional_receiver_receives_review_and_text` | `*args` shape |
| `test_receiver_raising_exception_is_logged_not_propagated` | failure-handling boundary |
| `test_receiver_with_keyword_only_args_is_invoked_with_no_args` | `*`-only shape |
| `test_production_send_telegram_alert_signature_is_supported` | imports the REAL `send_telegram_alert` from `agent.py`, verifies it has 2+ positional args. Pins the contract that this regression guard must catch future signature changes. |

The signature regression test is the load-bearing one — it actually imports `agent.send_telegram_alert` and asserts its signature. If PR #87 or a future change alters `send_telegram_alert`'s shape, this test fails and the cron dispatch is reviewed.

## Defensive regression

| Test file | Tests | Δ |
|---|---|---|
| `test_contract_health_cron.py` | 21/21 PASS | +8 (13 → 21) |
| Full agent suite | 338/338 PASS | +8 (330 → 338) |

Zero regressions. Existing tests (incl. `_StubAlert` 1-arg shape) still pass.

## What this does NOT solve

- The audit's F-2 (scheduler cascade-skip) and F-3 (intraday_cache 0% hit rate) are separate findings. They need their own slices.
- The contract-health cron still fires every hour — the fix only ensures the alert dispatch is correct. If the operator wants different cadence, that's a config change in `agent/schedule`.

## Critical invariants preserved

- `contract_health_cron_tick`'s public API unchanged.
- `format_violation_alert` unchanged.
- The cron's outer try/except still catches any receiver exception.
- The cron's lazy import of `send_telegram_alert` still works.
- All 13 pre-existing tests pass without modification.

## Operator runbook

After deploy to PROD:

1. The hourly `contract_health_cron_tick` will fire correctly.
2. If a contract-health violation is detected, the operator receives a Telegram alert.
3. The alert text contains the formatted violation summary (same as before).
4. If `send_telegram_alert`'s signature changes in a future PR, the regression test catches it before deploy.

## Audit-trail summary

```
e2fe147  C.F5     -- J.10 features inventory CLI
729f7f1  C.F2     -- Kite LTP fanout observability
0ba14a9  C.B.3    -- penny_universe stale warning dedup
dfc306a  C.C1     -- structured asymmetric-fill diagnostic
04aa166  C.B.2    -- agent dedup file observability (F-7 from 09-15 audit)
7cf87c3  C.B.1    -- research finalize_prior_days race fix (F-3 from 09-15 audit)
63d46ad  C.F8     -- bankroll_ledger TRADE_OPENED audit trail
49456be  C.B1+B3  -- held-out adequacy + settlement assumptions
31bf71d  C.C2     -- asymmetric partial-fill pricing model
315fa72  C.C2.WIRE -- wire partial-fill model into replay
045661d  J.10.DRY_RUN_ATTRIBUTION -- surface real vs simulation captures
d212250  D.1      -- release-readiness test receipt
<pending> C.F1     -- contract_health_cron defensive alert dispatch (F-1 from 09-16 audit)
```

PROD untouched. Dev only.
