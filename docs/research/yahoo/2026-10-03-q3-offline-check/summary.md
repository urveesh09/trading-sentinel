# Yahoo-only current non-F&O backtests

Requested dates (inclusive IST): 2026-07-01 to 2026-09-30.
All market bars come from Yahoo; no Sentinel trade/price history is used.

| Module/window | Dates | State/scope | Evidenced result |
|---|---|---|---|
| edge | 2026-07-01 to 2026-09-30 | SUCCEEDED / EVALUATOR | 1142 candidates; 167 selections; P&L unavailable |
| range | 2026-07-01 to 2026-09-30 | SUCCEEDED / EVALUATOR | 1097 ENTER decisions; P&L unavailable |

Daily names excluded for missing/invalid evidence: 6.
Coverage, per-symbol errors, raw hashes, policy/defaults and costs are archived beside this report.
Recent diagnostics are separate shorter windows; evaluator results are not entry-to-exit portfolio performance.
Momentum uses a virtual full-quantity T1 exit; inspect exit_fidelity for any later-day fallback settlements.
Joint Penny count is admitted entries, not closed trades; locked notional is not marked equity.
No qualification, aggregate system return, orders or deployment.
