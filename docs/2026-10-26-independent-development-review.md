# Independent review of October 26 development

Reviewed 2026-10-26, Dev `e0993a9` (application `a848bcb`), including `6ec5ce1`, `cf6befc`, `a848bcb` and their documentation. This is a review and implementation plan; none of the findings below has been fixed by this reviewer.

## Deployment and scope

Production checkout and engine/gateway/agent image plus HTTP release identities independently verify as `f9547c5cb926a2d0b6ab1a780c1889a1562af1f6` (verification 2026-10-26 14:19:39 UTC). The three October 26 development slices are NOT deployed. All three services were healthy. No Production edit, restart, broker order, Telegram message or live activation was performed during this review.

Read the four system documents and reviewed all application diffs from `d01be1e` through `e0993a9`. Preserved existing unrelated work in the Dev checkout. The production audit describes observed behavior on the deployed older release; reproductions below use current Dev and fake evidence.

## Useful corrections confirmed

- The extra owner/global halt check follows the awaited BUY cash reads and reservation and precedes dispatch; its refusal releases an undispatched hold and leaves exit handling intact. Both new cash/halt tests passed.
- CHECK now tests its price deadline again after the awaited outbox claim; the new delayed-claim test passed. Future local quote clocks are rejected when the provided current time establishes the mismatch.
- DAY and SIZE messages respect manual decision-making, use separate outbox identities, and survive Quiet under their defined rules. No order authority or blanket trade veto was introduced.
- Intraday trade storage, a later warning review, explicit charge totals, and management of remaining F&O positions after 15:25 are useful additions. Existing tests are not sufficient to establish all edge cases below.
- NSE currently documents continuous trading for CAS stocks ending at 15:15 and derivatives trading to 15:40. The timing rationale is valid; missing data alone does not prove CAS eligibility or a fill. Source: https://www.nseindia.com/static/products-services/closing-auction-session (checked October 26).

## Confirmed remaining findings

### R1 — P2: opening at T1 can still award the whole position T2 despite an ambiguous stop

`python-engine/position_tracker.py:346-373` and `research_penny_cnc_lifecycle.py:140-152`.

The new exception disables stop-first for the whole bar when its open reaches either target. Opening at T1 proves only the first partial can fill first; it does not prove T2 occurred before the stop for the remainder. With entry 10, stop 9.7, T1 10.3, T2 10.6, and OHLC 10.3/10.7/9.5/9.6, both the actual tracker and its mirror close all 40 shares at T2 10.6. This can overstate paper/research profit. It is a residual issue in the attempted ambiguity correction, not evidence of an actual live fill or loss.

Acceptance: process known opening events separately from uncertain later touches; opening at T1 fills only its declared partial and the remainder uses the declared conservative ambiguity rule, including its newly active stop. Cover open-at-T1/stop/T2, T1-only then stop, open-at-T2, gap-through-stop, already-partial positions and same-day entries. Keep runtime and mirror aligned. Do not reconstruct pre-entry touches as post-entry evidence.

### R2 — P2: unavailable warning inputs become an unwarned comparison group

`python-engine/partner_watch_score.py:55-71,129-149`.

`warnings_of` returns an empty set when run, usual size or other inputs are unknown. `score` then counts these trades as unwarned. A controlled sample of 20 spike-warning trades losing 100 each and 20 profitable trades with no warning evidence returns SUPPORTED. It does not establish that the warning distinguishes the losses from genuinely warning-free trades; missing coverage is being treated as absence.

Acceptance: store explicit per-warning eligibility/known-negative/positive/unknown states and provenance; compare positive versus known-negative only, report excluded coverage, and define ANY with unknown inputs explicitly. Keep partial-fill estimates and exact-fill results separately visible. No automatic rule activation or default veto follows this score.

### R3 — P2: the CAS fallback invents exits for unrelated missing bars and historical sessions

`python-engine/momentum_shadow.py:555-571,617-628` and `momentum_replay.py:282-304`.

Both new helpers derive a synthetic 15:15 bar from a final 15:00 candle without checking ticker eligibility, effective session calendar or why data ended. A frame dated 2025-01-02 receives the same synthetic exit, even though the new code's own CAS justification applies from 2026-01-19. A non-CAS stock whose last candle is missing is equally affected. The closing candle is also a price proxy, not proof that a sale at 15:15 executed at that price.

Acceptance: require dated instrument/session evidence for the special handling. Missing ordinary data remains unavailable/censored. Version any new execution assumption and report last-continuous valuation as modeled/proxy evidence rather than silently upgrading it to an evidenced fill. Test CAS/non-CAS, dates before applicability, missing/interrupted feeds, unsorted frames and the announced December session transition. No Production backfill is authorized by this review.

### R4 — P2: first partial fill freezes the opening size too small

`python-engine/partner_watch.py:3570-3596`.

COALESCE preserves `paid_share` and `after_loss` as first known, but the opening order's cumulative filled value is not final at its first fill. With 100,000 cash, an initial 65 units at 100 is stored as 6.5%. After that SAME order fills 650 units in total, the row has bought=650 but still paid_share=6.5%, although the opening order used 65% of cash. Against a usual 20%, the UNUSUAL_SIZE score incorrectly stays absent. The first-known rule can also freeze a bigger-after-loss classification before that opening order is complete.

Acceptance: distinguish immutable decision-time observations from cumulative execution facts. Persist opening order identity, fill state, observation times and final opening notional; update execution-derived size as fills arrive without using later unrelated add orders or future market information. Test delayed fills, partial-fill cancellation, restart, newly exact trade-book fills and the after-loss size comparison.

### R5 — P2 hardening: the test guard blocks DNS, not all network traffic

`python-engine/tests/conftest.py:62-80`.

Replacing getaddrinfo stops ordinary hostname-based clients, but a direct socket.connect to a numeric address does not use that function. A fake-transport reproduction confirms connect is reached under the new guard; no external packet was sent. Test subprocesses also do not inherit a Python monkeypatch. Thus the documentation's universal assertion that tests never reach the network is stronger than the implemented boundary. Fake tokens are valuable defense in depth, not complete isolation.

Acceptance: deny non-local connect/connect_ex at the socket or test-runner boundary, include child processes or document a narrower guarantee, and use an explicit opt-in integration harness. Add tests for named hosts, numeric IPv4/IPv6, pre-resolved clients, subprocesses and local test servers. Preserve fake credentials before clients are initialized.

### R6 — P2 research contract: the frozen scorer imports changeable thresholds

`python-engine/partner_watch_score.py:55-67`.

The frozen scorer imports current SPIKE_RUN_PCT and USUAL_SIZE_MULT from partner_insights each time. Changing the shared spike threshold from .20 to .30 changes the classification of the same .25 historical run. No rule version or snapshot is bound to the rows. This is a confirmed contract gap; no such threshold change occurred in this review.

Acceptance: freeze a versioned scoring specification, including thresholds, eligibility, costs/data status and cohort rules, persist its identity with results, and test that unrelated live threshold changes cannot rewrite a frozen score. Twenty warned trades is the declared minimum for this descriptive diagnostic, not statistical proof of predictive value or money saved.

## Independent verification

Dev interpreter: `python-engine/winvenv/Scripts/python.exe`.

Focused suite: test_partner_watch.py, test_partner_watch_score.py, test_f1a_own_cash.py, test_momentum_replay.py, test_oct21_audit_fixes.py, test_research_penny_cnc_lifecycle.py and test_scheduler_closures_invoke.py, with `-q --disable-warnings --tb=short`.

- First combined run: 235 passed, 1 failed (the new post-cutoff scheduler test, DR-only 15:39 case), 2 warnings.
- Isolated failed test: 1 passed.
- Exact combined repeat: 236 passed, 2 warnings, 34.96 s.
- Root cause of the one failure is NOT established. Investigate deterministic clock/lock/background-work isolation before claiming repeatable suite cleanliness. No confirmed Production scheduler failure is inferred from it.
- Six controlled reproductions: 6 passed by asserting the defective behavior, 1.35 s. These are evidence of open gaps, NOT fix acceptance.
- Reproductions and the combined repeat output are outside the repositories in `C:/Users/Urveesh/sentinel-operations/independent-review-20261026/`. Temporary SQLite, fake broker/Telegram evidence and a fake socket connect only. No real trade was used to test anything.
- Full engine suite was not repeated by this reviewer. The developer's reported full-suite count is separate evidence.

## Concrete follow-up slices

1. Isolate and fix the daily-bar opening/partial/stop ordering (R1), runtime and mirror together. Run focused tracker/research and accounting tests; version any changed research assumption.
2. Correct trade-size observation identity and missing-data eligibility (R4/R2), then bind the frozen warning spec (R6). Add partial-fill/restart and coverage regressions before interpreting SUPPORTED results.
3. Replace the unconditional CAS-derived bar with evidence-gated, explicitly modeled terminal handling (R3). Preserve existing historical receipts; any backfill is a separately approved operation.
4. Harden the test boundary (R5), and reproduce/fix the intermittent scheduler test with deterministic timing; no tests may touch actual Telegram or broker services.
5. Promote reviewed fixes through GitHub and stamped image verification. This review itself does not approve deployment or live activation. Roll back with the prior stamped engine image or revert the relevant slice; retain the additive trip table. No live switch, halt or strategy threshold needs changing to address these gaps.

For later enrichment: clearly label modeled charges even with exact fills; show explicit input coverage and session timestamps; add a proper after-hours CHECK planning mode; show net target reward versus loss and executable price at requested size; then evaluate adaptive hold/trail/exit scenarios with fresh recorded paths and held-out evidence. Preserve manual partner discretion and owner live-order authority. More warning messages alone do not establish better trading.
