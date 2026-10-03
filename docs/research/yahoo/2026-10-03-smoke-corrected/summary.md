# Yahoo-only current non-F&O backtests

Requested dates (inclusive IST): 2026-09-24 to 2026-09-30.
All market bars come from Yahoo; no Sentinel trade/price history is used.

| Module/window | Dates | State/scope | Evidenced result |
|---|---|---|---|
| penny-mis | 2026-09-24 to 2026-09-30 | UNAVAILABLE / LIFECYCLE | no ticker-day satisfies session_policy=complete_only: {'INVALID': 1, 'PARTIAL': 14} |
| penny-mis-gap-sensitivity | 2026-09-24 to 2026-09-30 | SUCCEEDED / LIFECYCLE | count=0; net=unavailable; unresolved=0 |
| penny-cnc | 2026-09-24 to 2026-09-30 | SUCCEEDED / LIFECYCLE | count=0; net=unavailable; unresolved=0 |
| penny-joint | 2026-09-24 to 2026-09-30 | UNAVAILABLE / PORTFOLIO_PARTIAL | joint cash requires successful same-window MIS and CNC lifecycle reports |
| penny-joint-gap-sensitivity | 2026-09-24 to 2026-09-30 | SUCCEEDED / PORTFOLIO_PARTIAL | count=0; net=0.0; unresolved=0 |
| edge | 2026-09-24 to 2026-09-30 | SUCCEEDED / EVALUATOR | 2 candidates; 1 selections; P&L unavailable |
| swing | 2026-09-24 to 2026-09-30 | SUCCEEDED / EVALUATOR | 0 ENTER decisions; P&L unavailable |
| momentum | 2026-09-24 to 2026-09-30 | SUCCEEDED / EVALUATOR | count=0; net=unavailable; unresolved=see report |
| range | 2026-09-24 to 2026-09-30 | SUCCEEDED / EVALUATOR | 0 ENTER decisions; P&L unavailable |
| partner | 2026-09-24 to 2026-09-30 | NOT_ADAPTED / ADVISORY_ONLY | Partner advisory/protection is not an OHLCV money-book replay; no adapter exists. |

Daily names excluded for missing/invalid evidence: 0.
Coverage, per-symbol errors, raw hashes, policy/defaults and costs are archived beside this report.
Recent diagnostics are separate shorter windows; evaluator results are not entry-to-exit portfolio performance.
Momentum uses a virtual full-quantity T1 exit; inspect exit_fidelity for any later-day fallback settlements.
Joint Penny count is admitted entries, not closed trades; locked notional is not marked equity.
No qualification, aggregate system return, orders or deployment.
