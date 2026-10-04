# Non-F&O independent review and repeated Yahoo results — October 4

**No demonstrated performance improvement yet.** The new commits added offline
helpers/measurement; active policies and the all-module Yahoo defaults did not
change. The original smart-entry/exit plan is **partially implemented**.
See [findings, minor corrections and R1–R5 follow-up](2026-10-04-non-fno-independent-review-and-repeat-plan.md).

Reviewed implementation `65e050a` and documentation `434c4cc` against the
October 3 plan. This task started from a clean Dev worktree. Corrections,
documentation and evidence below are Dev-local and uncommitted; no Production
access, broker action, push or deployment occurred. F&O remains excluded.

## Same parameters and same independent market data

Requested quarter: **July 1–September 30, 2026**, inclusive IST. Separate
intraday diagnostic: **September 24–30**, five trading sessions, as before.
Reused verified archived **Yahoo** data, not Sentinel price/trade history.
No new downloads or repaired/filled candles. Fixed effective universes remain
95 Penny names and 499 stock names, with the same six daily exclusions.

Original bankrolled research configurations remain unchanged: Penny paper
uses its frozen ₹2,000 allocation; Momentum ₹4,500 bankroll/₹2,500 pool; EDGE
₹100,000 hypothetical paper bankroll, three selections and 0.45 strength floor.
The EDGE number is a research default, not permission to fund that book.
Owner-approved nominal live book allocations were not substituted into these
repeats. Missing new selector fields resolve to BASELINE/TARGET_1_PROXY, the
same effective policies as before.

Two all-module runs were completed: before corrections and after corrections.
**All 16 outcome states, dates, scopes, effective configurations and metrics
match the original** in each repeat. Original failures/unavailability remain
preserved. Quarter intraday data stays unavailable; the short diagnostic never
replaces the primary window. No aggregate system-profit figure is available.

| Module / window | Previous | Final repeat | Interpretation |
| --- | --- | --- | --- |
| Penny MIS gap sensitivity, Sep 24–30 | 18 closes, **+₹15.1765** | **Identical** | Partial-session lifecycle; not quarter/live profit |
| Joint Penny gap sensitivity, same dates | 18 admitted, +₹15.1765 | Identical | Same MIS outcomes; not additional profit |
| Penny CNC, same dates | 0 entries | Identical | Profitability unavailable |
| Momentum default T1 proxy, same dates | 2 closes, **−₹0.827101** | **Identical** | Existing virtual exit model, not live execution |
| EDGE daily evaluator, Q3 | 1,142 candidate appearances / 167 selections | Identical | No filled-trade P&L |
| Swing daily evaluator, Q3 | 171 entry decisions | Identical | No complete trade/exit P&L |
| Range daily evaluator, Q3 | 1,097 ENTER verdicts | Identical | SHADOW/evaluator, not executed trades |
| Strict Penny and quarter intraday primaries | Unavailable | Identical | Retention and complete-session coverage limits remain |
| Partner | NOT_ADAPTED | Identical | No money-book simulation |

Penny's fragility is unchanged: removing the largest winner gives −₹27.7362;
adverse-fill diagnostic −₹115.8338; five wins/thirteen losses and realized cash
drawdown ₹45.0962. More faithful testing is useful even when it fails to increase
the rupee result. It must not be labelled newly profitable trading behavior.

## Separately frozen studies of the newly available code

The [three-study freeze](research/yahoo/2026-10-04-review-candidates/trial-freeze.json)
was written before execution. Prices, universes, scored dates and relevant
bankrolls stay as above. Only the explicitly named candidate/adapter changes.
These are retrospective development diagnostics, **not untouched holdouts**.

| Study | Result | What it establishes |
| --- | --- | --- |
| PEN_CONTEXT, Sep 24–30, same Penny gap policy | **0 entries; net unavailable** | All 46 baseline-accepted observations were filtered. Five prior same-minute volume profiles cannot be supplied by a five-session scored archive; missing/gapped prefixes are not valid substitutes. This does not demonstrate a better entry policy. |
| Momentum `LIVE_EXIT_LIFECYCLE` diagnostic, same MOM_BASE entries | **2 closes, −₹19.007674** | Worse than the proxy by ₹18.180573. Calls the shipped exit evaluator, but OHLC path/completed-bar clocks remain unresolved; measurement change, not a deployed policy comparison. |
| EDGE next-open **PROXY**, Q3 | **167 trials: 129 closed, 35 no-fill, 3 unresolved; closed-trial net sum −₹60,813.839964** | Unfavourable diagnostic retained. Independent discovery-sized trials reuse hypothetical capital; holding-clock/fill/cash semantics are unvalidated. This is not loss on one account or a qualified portfolio return. No comparable prior EDGE lifecycle P&L exists. |

Momentum diagnostic details: ONESOURCE exits at the recorded 12:00 bar via slow
time stop, net −₹6.988026; TENNIND at 11:00 via fast time stop, net −₹12.019648.
The original proxy held both until 15:15, yielding −₹7.38705 and +₹6.559949.
These bar labels are not verified live order times. Both new-model trades close
without a partial fill; they cannot validate the runner's economics. Fourteen
exit settings and the actual diagnostic assumptions are now frozen in its result.

The Penny candidate currently only filters baseline accepts, so it cannot make
a baseline-rejected opportunity enter. EDGE's proposed ranking/exit improvements
are not implemented. Range/Swing helpers remain disconnected from a complete
candidate lifecycle. Their existing evaluator counts are therefore unchanged;
there is no honest improved-profit number to report for them.

## Corrections and verification

Minor research corrections made:

- Penny retest anchor excludes both confirmation candles; previously a valid
  prior close could never exceed its own included high. Consecutive chase bars
  do not masquerade as a fresh reclaim. Prior cumulative-volume profiles require
  every minute from the session open to the same decision boundary.
- Momentum's new diagnostic uses actual `atr_at_entry` and declared regime.
  Next-session, zero-volume and later-than-deadline bars cannot silently supply
  an intraday fill; missing exact square-off evidence remains unresolved.
  Exit settings/model assumptions are recorded rather than describing a runner
  as a full-quantity T1 proxy.
- EDGE's new adapter/catalogue now declares **PROXY/EVALUATOR_ONLY**. Its
  independent-trial P&L and unvalidated holding clock are explicitly disclosed.
  The runtime EDGE simulator and orchestrator were not changed.

Focused command:

```powershell
.\python-engine\winvenv\Scripts\python.exe -m pytest python-engine\tests\test_momentum_replay.py python-engine\tests\test_non_fno_research.py python-engine\tests\test_penny_lifecycle_replay.py python-engine\tests\test_backtest_lab.py python-engine\tests\test_backtest_cli.py python-engine\tests\test_penny_edge_engine.py python-engine\tests\test_range_reversion.py scripts\tests\test_backtest_all_yahoo.py -q
```

**130 passed**, one existing HTTPX deprecation; initial pre-correction selection
had 124 passes. Regressions cover real retest/chase geometry, incomplete volume
prefixes, ATR/regime forwarding and next-day/zero-volume/late-deadline refusal.
Affected source passed compilation and diff checks. Atlas regenerated to
241 modules and verified byte-identical on a second regeneration.

Both repeats verify all 1,203 raw responses and raw/validated snapshot identity,
plus per-report hashes, dates, effective configuration and universe. The
[delivery integrity receipt](research/yahoo/2026-10-04-review-candidates/verification.json)
binds 32 repeat outcomes and three frozen studies to current source/settings.
[Study details](research/yahoo/2026-10-04-review-candidates/details.json)
extract warnings/funnels/trades from the verified reports; the CLI's compact
return contains metrics only. Losing and unavailable diagnostics are retained.

Large raw reports, snapshot databases and coverage/provider manifests remain
local and Git-ignored; retention sidecars bind their hashes. A Git clone alone
does not carry enough data for offline reproduction. Protected F&O/shipped
strategy/shared runtime paths and F&O catalogue entries match the starting
checkout. Source isolation is not a measured Production latency/cash guarantee;
operational noninterference remains a gate before any future integration.

## Next work

Follow R1–R5 in the [review plan](2026-10-04-non-fno-independent-review-and-repeat-plan.md):
explicit candidate interface and native historical context; causal EDGE and
Momentum lifecycle/cash accounting; actual Range/Swing adapters and bounded
entry/exit hypotheses; untouched qualification and F&O compatibility.
No live thresholds, funding, runtime configuration, dependencies or schemas
changed. Do not tune this five-session sample to manufacture an improvement.
