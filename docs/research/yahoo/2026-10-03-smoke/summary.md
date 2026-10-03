# Yahoo-only current non-F&O backtests

Requested dates (inclusive IST): 2026-09-24 to 2026-09-30.
All market bars come from Yahoo; no Sentinel trade/price history is used.

| Module/window | Dates | State/scope | Evidenced result |
|---|---|---|---|
| penny-mis | 2026-09-24 to 2026-09-30 | UNAVAILABLE / LIFECYCLE | no ticker-day satisfies session_policy=complete_only: {'INVALID': 5, 'PARTIAL': 10} |
| penny-cnc | 2026-09-24 to 2026-09-30 | SUCCEEDED / LIFECYCLE | count=0; net=unavailable; unresolved=0 |
| penny-joint | 2026-09-24 to 2026-09-30 | UNAVAILABLE / PORTFOLIO_PARTIAL | joint cash requires successful same-window MIS and CNC lifecycle reports |
| edge | 2026-09-24 to 2026-09-30 | UNAVAILABLE / EVALUATOR | missing/invalid market context: NIFTYBEES |
| swing | 2026-09-24 to 2026-09-30 | UNAVAILABLE / EVALUATOR | missing/invalid market context: NIFTY 50, NIFTY BANK |
| momentum | 2026-09-24 to 2026-09-30 | UNAVAILABLE / EVALUATOR | intraday OHLC values must be finite and positive |
| range | 2026-09-24 to 2026-09-30 | SUCCEEDED / EVALUATOR | 0 ENTER decisions; P&L unavailable |
| partner | 2026-09-24 to 2026-09-30 | NOT_ADAPTED / ADVISORY_ONLY | Partner advisory/protection is not an OHLCV money-book replay; no adapter exists. |

Daily names excluded for missing/invalid evidence: 3.
Coverage, per-symbol errors, raw hashes, policy/defaults and costs are archived beside this report.
Recent diagnostics are separate shorter windows; evaluator results are not entry-to-exit portfolio performance.
Momentum uses a virtual full-quantity T1 exit; inspect exit_fidelity for any later-day fallback settlements.
Joint Penny count is admitted entries, not closed trades; locked notional is not marked equity.
No qualification, aggregate system return, orders or deployment.
