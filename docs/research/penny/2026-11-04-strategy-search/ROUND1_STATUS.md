# Round 1 — retained training failures

Source/harness/data freeze committed before scoring: `ca3b748`.
Post-commit guide, active plan, checklist and atlas consistency checks passed;
owner-only changes remain unstaged in their original working copies.

The daily study's 2019–2022 training runs reject both initial hypotheses:

| Candidate | Closes | Net | Gross | Costs | Marked drawdown |
|---|---:|---:|---:|---:|---:|
| D1 pullback | 563 | -33,181.10 | -13,896.36 | 19,284.74 | 35,301.01 |
| D1 flush/recovery | 693 | -69,210.08 | -49,536.56 | 19,673.52 | 69,989.11 |

Same Rs 100,000 starting allocation, own cash and 10 bps per-side slippage.
Pullback wins only in 2021; flush loses in every training year. Costs worsen
the result, but removing them does not rescue either strategy. Three-session
time exits dominate, so more entries or a fee-only explanation is unsupported.
These are static-universe daily-bar proxies, not historical broker fills.

Next hypotheses (not scored here): a sustained trend/longer winner-holding
strategy and a genuine daily breakout strategy. Preserve the failed initial
rules and use training diagnostics only. Current EDGE and intraday baseline
runs remain in progress. Validation outcomes have not been opened.

Data-contract correction before scoring: the original coverage receipt includes
119 invalid daily histories from the provider's incomplete Nov 3 daily closes.
Each scored window now reads only daily candles before its declared cutoff;
Nov 3 intraday entries need daily warmup only through Nov 2. The raw replies,
original coverage and immutable snapshot remain unchanged. No price was filled
or repaired and no strategy result informed this cutoff rule. The final
round-1 source freeze records the corrected reader before any scoring.
