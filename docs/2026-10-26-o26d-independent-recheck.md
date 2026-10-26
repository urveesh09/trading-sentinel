# Independent recheck of O26d corrections

Reviewed 2026-10-26: Dev `cf42b3b` (application `4205eef`). This is a review receipt and follow-up plan, not an implementation or deployment.

## Verified state and checks

- Production remains `f9547c5cb926a2d0b6ab1a780c1889a1562af1f6`; running engine/gateway/agent image and HTTP release identities independently verified at 2026-10-26 15:41:46 UTC. All three services healthy. O26 through O26d are not deployed.
- Read the four system documents, reviewed `e0993a9..cf42b3b`, and preserved unrelated existing Dev changes.
- Focused independent run: 270 passed, 3 warnings, 37.25 s. Files: test_partner_watch.py, test_partner_watch_score.py, test_research_penny_cnc_lifecycle.py, test_position_tracker_highlow.py, test_oct21_audit_fixes.py, test_momentum_replay.py, test_scheduler_closures_invoke.py, test_network_guard.py, test_s5_provider_lanes.py; interpreter python-engine/winvenv/Scripts/python.exe, flags -q --disable-warnings --tb=short.
- Independent scenarios: 8 passed, 0.76 s: six check corrected original behavior; two deliberately assert the remaining defects below. These latter passes do not mean the defects are fixed.
- Scenario source is outside the repository: C:/Users/Urveesh/sentinel-operations/independent-review-20261026/test_o26d_recheck.py. Run with PYTHONPATH pointing at python-engine and `python -m pytest -p tests.conftest <scenario-file> -q -s --disable-warnings --tb=short`. Uses temporary databases/archives and the new test-network guard. No real broker or Telegram calls.
- The developer's full-suite receipt (6,110 passed, 4 skipped) was not independently repeated. The earlier scheduler-test timing issue now has a counter-based correction and frozen-clock regression coverage.

## Corrections confirmed

1. Original R1: opening at T1 10.3 with entry 10, stop 9.7 and later range through T2 and stop now gives the T1 partial then the remainder at breakeven 10, rather than all shares at T2.
2. Original R2: missing warning inputs stay UNKNOWN; a sample with 20 spike-positive losses and 20 trades without run data yields TOO_FEW, with zero known-negative controls and 20 unknowns.
3. Original R3 example: a missing 15:15 bar before the CAS applicability window is no longer synthesized. Dated contract evidence and an explicit model are checked. Broader per-trade version isolation remains incomplete below.
4. Original R4: the same opening order growing from 65 to 650 units at 100 on 100,000 cash now updates paid_share from .065 to .65 and opening_final=1.
5. Original R5: direct numeric socket connections are blocked; the focused guard suite also covers asyncio and inheriting Python children. The narrower subprocess/non-Python limitations are documented.
6. Original R6: changing the live spike threshold no longer rewrites classification under the frozen scoring SPEC. Unknown coverage, estimated charge wording and rule identity are meaningful improvements.

The corrected CAS start of August 3, 2026 agrees with Zerodha's published implementation notice, which also names the December 7 change: https://zerodha.com/z-connect/general/everything-you-need-to-know-about-closing-auction-session-cas (checked October 26). This review makes no new claim about December timings.

## Remaining finding F1 — P2: the terminal resolver applies today's CAS model to legacy execution records

Files/contracts: python-engine/momentum_shadow.py:638-665 and :668-671; cas_time_exit_evidence and _advance_and_open.

The evidence helper correctly returns NO_MODEL when explicitly given legacy execution JSON. The actual terminal resolver, however, selects only ticker/variant, checks eligibility without passing the saved execution, and feeds the resulting derived bar to _advance_and_open. Thus eligibility is based on current EXECUTION rather than the immutable execution attached to each trade.

Controlled reproduction: seed a trade with the old execution definition (all original cost fields, no cas_time_exit) before immutable insertion, archive an eligible dated NFO master, and supply the final 14:45/15:00 candles. The helper says NO_MODEL for that saved execution, but resolve_momentum_shadow_day closes the trade with receipt time_exit_last_continuous at 15:15 anyway. No Production record was modified. The new model therefore changes an older trade's methodology despite the version contract; new and legacy variants for one ticker also cannot be handled correctly by a single ticker-wide eligibility decision.

Acceptance: bind terminal handling to each saved execution_json and declared time-exit contract; pass only ordinary observed bars to legacy/no-model records, and derived bars only to records declaring the exact approved model. Test mixed legacy/new records for one ticker, explicit helper NO_MODEL through the full resolver, restart/rerun idempotency and declared alternative exit times. Legacy missing evidence remains censored unless separately replayed under a new, explicitly labelled research identity.

## Remaining finding F2 — P2: a gapped minute path is treated as enough evidence to override conservative exits

Files/contracts: python-engine/position_tracker.py:84-104 and :125-137; shared day_exits used by runtime and research mirror.

usable_minutes sorts and checks end time, broad daily extrema and (on later days) first time. It does not establish intermediate coverage or entry-time coverage. On the entry day it neither requires the path to start at entry nor requires it to explain the relevant range.

Controlled reproduction: entry at 09:30, daily open 10.1/high 10.7/low 9.6, entry 10/stop 9.7/T1 10.3/T2 10.6. Supply only minute rows at 10:30, 15:13 and 15:14, all above the stop. The first post-entry hour and intervening hours are absent. day_exits nevertheless returns basis MINUTES, T1=10.3 and close CLOSED_T2=10.6, replacing the conservative daily result. A separate four-row later-day path with a multi-hour hole also passes usable_minutes. Missing provider evidence could contain a stop before the observed targets; no such ordering has been established.

Acceptance: require an explicit completeness contract for the relevant exchange/session/instrument, starting at the entry interval on entry day; validate dates, duplicate/conflicting timestamps, finite coherent OHLC and gaps. Distinguish verified no-trade intervals from provider loss instead of silently treating every gap as inactivity. Without adequate path evidence retain an explicitly conservative/unavailable result and record the coverage reason. Add missing first post-entry hour, interior gaps, non-CAS final minutes, contradictory bars and complete-path controls. Preserve runtime/research parity and version the changed accounting assumptions.

## Follow-up and rollout

- [ ] F1: isolate per-trade execution versions in the terminal resolver and add full-path mixed-version regressions.
- [ ] F2: define/validate minute-path completeness before choosing MINUTES; add runtime and mirror regressions.
- [ ] Rerun affected shadow/replay, tracker/mirror and accounting tests. Existing passing tests alone do not close F1/F2.
- [ ] Update guide/active plan and regenerate atlas if source/declarations change. Promote through GitHub with stamped deployment verification when authorized. Keep the prior engine image for rollback; retain additive partner-trip columns. No Production backfill or live activation follows from this review.

No new partner-message text bug was confirmed in this slice. The remaining findings affect paper/research evidence, not an observed live order. Existing deferred work (chandelier look-ahead, after-hours planning, December calendar transition and live-session validation) remains separate; tests are not evidence of profitability.

Reviewer changed documentation only. No application source edits, commits, pushes, Production writes/restarts, messages, orders or switch changes in this recheck.
