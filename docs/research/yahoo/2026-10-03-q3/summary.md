# Yahoo-only current non-F&O backtests

Requested dates (inclusive IST): 2026-07-01 to 2026-09-30.
All market bars come from Yahoo; no Sentinel trade/price history is used.

| Module/window | Dates | State/scope | Evidenced result |
|---|---|---|---|
| penny-mis | 2026-07-01 to 2026-09-30 | UNAVAILABLE / LIFECYCLE | Yahoo rejected requested 1m window: YahooDataError: Unprocessable Entity: 1m data not available for startTime=1782844200 and endTime=1783449000. The requested range must be within the last 30 days. |
| penny-mis-gap-sensitivity | 2026-07-01 to 2026-09-30 | UNAVAILABLE / LIFECYCLE | Yahoo rejected requested 1m window: YahooDataError: Unprocessable Entity: 1m data not available for startTime=1782844200 and endTime=1783449000. The requested range must be within the last 30 days. |
| penny-cnc | 2026-07-01 to 2026-09-30 | UNAVAILABLE / LIFECYCLE | Yahoo rejected requested 1m window: YahooDataError: Unprocessable Entity: 1m data not available for startTime=1782844200 and endTime=1783449000. The requested range must be within the last 30 days. |
| penny-joint | 2026-07-01 to 2026-09-30 | UNAVAILABLE / PORTFOLIO_PARTIAL | Yahoo rejected requested 1m window: YahooDataError: Unprocessable Entity: 1m data not available for startTime=1782844200 and endTime=1783449000. The requested range must be within the last 30 days. |
| penny-joint-gap-sensitivity | 2026-07-01 to 2026-09-30 | UNAVAILABLE / PORTFOLIO_PARTIAL | Yahoo rejected requested 1m window: YahooDataError: Unprocessable Entity: 1m data not available for startTime=1782844200 and endTime=1783449000. The requested range must be within the last 30 days. |
| edge | 2026-07-01 to 2026-09-30 | SUCCEEDED / EVALUATOR | 1142 candidates; 167 selections; P&L unavailable |
| swing | 2026-07-01 to 2026-09-30 | SUCCEEDED / EVALUATOR | 171 ENTER decisions; P&L unavailable |
| momentum | 2026-07-01 to 2026-09-30 | UNAVAILABLE / EVALUATOR | Yahoo rejected requested 15m window: YahooDataError: Unprocessable Entity: 15m data not available for startTime=1782844200 and endTime=1790793000. The requested range must be within the last 60 days. |
| range | 2026-07-01 to 2026-09-30 | SUCCEEDED / EVALUATOR | 1097 ENTER decisions; P&L unavailable |
| partner | 2026-07-01 to 2026-09-30 | NOT_ADAPTED / ADVISORY_ONLY | Partner advisory/protection is not an OHLCV money-book replay; no adapter exists. |
| penny-mis-recent-diagnostic | 2026-09-24 to 2026-09-30 | UNAVAILABLE / LIFECYCLE | no ticker-day satisfies session_policy=complete_only: {'PARTIAL': 404, 'UNAVAILABLE': 71} |
| penny-mis-recent-diagnostic-gap-sensitivity | 2026-09-24 to 2026-09-30 | SUCCEEDED / LIFECYCLE | count=18; net=15.18; unresolved=0 |
| penny-cnc-recent-diagnostic | 2026-09-24 to 2026-09-30 | SUCCEEDED / LIFECYCLE | count=0; net=unavailable; unresolved=0 |
| penny-joint-recent-diagnostic | 2026-09-24 to 2026-09-30 | UNAVAILABLE / PORTFOLIO_PARTIAL | joint cash requires successful same-window MIS and CNC lifecycle reports |
| penny-joint-recent-diagnostic-gap-sensitivity | 2026-09-24 to 2026-09-30 | SUCCEEDED / PORTFOLIO_PARTIAL | count=18; net=15.18; unresolved=0 |
| momentum-recent-diagnostic | 2026-09-24 to 2026-09-30 | SUCCEEDED / EVALUATOR | count=2; net=-0.83; unresolved=see report |

Daily names excluded for missing/invalid evidence: 6.
Coverage, per-symbol errors, raw hashes, policy/defaults and costs are archived beside this report.
Recent diagnostics are separate shorter windows; evaluator results are not entry-to-exit portfolio performance.
Momentum uses a virtual full-quantity T1 exit; inspect exit_fidelity for any later-day fallback settlements.
Joint Penny count is admitted entries, not closed trades; locked notional is not marked equity.
No qualification, aggregate system return, orders or deployment.
