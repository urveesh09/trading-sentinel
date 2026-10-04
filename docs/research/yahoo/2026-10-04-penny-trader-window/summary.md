# Yahoo-only current non-F&O backtests

Requested dates (inclusive IST): 2026-09-07 to 2026-10-03.
All market bars come from Yahoo; no Sentinel trade/price history is used.

| Module/window | Dates | State/scope | Evidenced result |
|---|---|---|---|
| penny-mis | 2026-09-07 to 2026-10-03 | SUCCEEDED / LIFECYCLE | count=0; net=unavailable; unresolved=0 |
| penny-mis-gap-sensitivity | 2026-09-07 to 2026-10-03 | SUCCEEDED / LIFECYCLE | count=42; net=78.35; unresolved=0 |

Daily names excluded for missing/invalid evidence: 0.
Coverage, per-symbol errors, raw hashes, policy/defaults and costs are archived beside this report.
Recent diagnostics are separate shorter windows; evaluator results are not entry-to-exit portfolio performance.
Momentum uses a virtual full-quantity T1 exit; inspect exit_fidelity for any later-day fallback settlements.
Joint Penny count is admitted entries, not closed trades; locked notional is not marked equity.
No qualification, aggregate system return, orders or deployment.
