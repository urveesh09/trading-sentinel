# One-shot exam runner

The frozen January–May candidate needs a runner that cannot reuse the June–December paper reference or open an arbitrary archive. Implement the scoring half first. It takes a committed request-key and coverage file, a committed snapshot manifest, and the exact isolated dataset and daily file named in that manifest. The source-side metadata capture and snapshot preparation remain a separate, read-only step. No requests are sent to Breeze by the runner.

Validate the committed candidate and source hashes, request scope, selected window, snapshot hashes, and exact expected sessions. Require an explicit prior Q1 unavailability record for the April–May fallback. Match the same-day index and front-future coverage and exact dated nearest-weekly coverage on every eligible session. Report own-expiry exclusions separately. A one-shot marker shared by both possible windows is created before opening the snapshot or evaluating any arm. Retain the marker, each arm's output and any failure. Any source-integrity correction needs its own documented authorization and evidence. The runner writes only under the Dev research directory.

Reuse the June–December adapter and its fixed 65-unit research lot, daily gate, observed minute source and matching cost assumptions. The 65 units preserve comparability to the registered historical books. Record that convention separately from actual 2022 contracts and the ₹15,000 trial. Rebuild the one-lot brakes-off paper history from the selected exam window alone. Report N11 informationally, N11T and A at ordinary and doubled cost, and the unchanged scorer's gate decisions. Compare 2022 windows as separate accounts and report their arithmetic sum and the old 200-session and ten tolerance-trade gates.

Synthetic checks cover wrong-window and fallback requests, changed snapshot hashes, repeat-run refusal, absent eligibility coverage, both stress passes and the result's 2022 accounting. Audit the actual strategy wiring without opening unseen prices. No runtime, config, migration, orders, deployment, or forward shadow registration. Rollback is to retire the runner and retain the one-shot record.

## Implemented scoring half

`python exam_run.py` requires `exam-2022-h1-requests.json` and `exam-2022-h1-snapshot.json` to exist and match Git. The former binds the selected window, clean guarded checks, ordered finished requests with row counts, exact session list and the two scorer source hashes. The latter binds the request file hash, minute coverage by session and hashes for the local `dataset/manifest.json`, `dataset/breeze.sqlite` and `daily.json`. Calendar dates and nearest dated futures and option contracts must agree. The reference and all arms start at the frozen ₹250,000. The paper reference is reset before evaluation and each later admission sees only earlier closes. A tolerance increase counts only when a new initial two-lot ticket actually enters.

Local `_local/exam-2022-h1/started.json` is exclusive to the entire exam, including the fallback. Its creation precedes snapshot reads. A failed run leaves this marker and any completed arm files in place. The scorer uses its own report for the sealed window. It also lists the arithmetic sum with June–December and counts the original tolerance threshold from baseline N11T only. The original 114 June–December option dates are a coverage report, so the combined 200-session field explicitly uses reported dates. A qualifying date count would still need complete coverage verification under the earlier registration.

Verification from this folder uses `python -m pytest test_exam_run.py test_exam_scoring.py test_n012_ab.py test_round30.py -q`. The 18 checks include a fresh-process replay on a synthetic session through the actual historical adapter. The first integration check exposed the adapter's required `option_expiries` metadata. The fixture and validation now carry it alongside the calendar. The synthetic reference check also verifies that an exit stamped exactly at the decision clock is invisible to that decision.

At scoring-runner implementation, the guarded history tool listed Q1 and Q2 as open and the day's quota as used. Neither unseen option nor futures prices were read. See the source preparation slice below for the subsequent check of the saved guard results and archive metadata.

## Independent calendar slice

Use the NSE F&O holiday list and Thursday expiry conventions to establish expected sessions and dated contracts independently of option availability. Cross-check only date fields in the source's daily metadata. Add a committed calendar hash to the request manifest and reject dropped sessions or a different nearest dated expiry before opening the snapshot. Verify both allowed windows and the April holiday shift. Keep the scoring rules and rollback above.

The official calendar and 2022 NIFTY daily date metadata agree on all 101 January–May sessions. The book skips the 21 weekly or monthly expiries, leaving at most 80 eligible option dates. April–May alone has 40 sessions and at most 32 eligible option dates. With the previously reported 114 June–December dates, the original 200-session threshold can reach at most 194 on the primary exam or 146 on the fallback. This does not change the new N012 pass rules. Any improvement to the earlier June–December coverage needs its own documented reconciliation with the original registration. [NSE holiday circular](https://archives.nseindia.com/content/circulars/FAOP50561.pdf), [NSE weekly convention](https://nsearchives.nseindia.com/global/content/about_us/NSEBusinessResponsibilityReport.pdf), [NSE monthly convention](https://nsearchives.nseindia.com/content/circulars/FAOP68747.pdf).

The [calendar file](exam-2022-h1-calendar.json) retains all expected session dates, the shifted April 13 expiry, the June 2 weekly contract needed on May 30–31 and the June monthly front. The request manifest must include its SHA-256 as `calendar_sha256`. The runner independently checks that the prepared snapshot contains the expected nearest contracts for every session. The date-only cross-check read no candle prices.

## Source preparation slice

Add `exam_prepare.py` with separate `capture` and `snapshot` commands. Capture requires matching completed full guarded check receipts, no active downloader and a committed calendar. In a read-only transaction, record finished request identities and date, clock and traded-right coverage without selecting price columns. Commit that metadata before the snapshot command can read OHLC. Scope the snapshot to the covered request contracts, exact NSE sessions, prior front-future lookback, and frozen daily warm-up. Keep the April–May path gated by a prior explicit unavailability record.

Snapshot creation must reject a changed request ledger or a changed coverage record and preserve a failed attempt for audit. Write only to the Dev research directory, verify the files and emit the snapshot manifest for a separate commit. Synthetic tests must show that capture cannot select price fields, that stray contracts and dates do not enter the snapshot, and that stale or incomplete coverage refuses safely. Keep runtime, order and rollout authority outside this research path. Rollback is to retire the preparer and retain the sealed records.

### Implemented workflow

1. After the owner obtains clean full guarded checks, run `python exam_prepare.py capture`. A read-only connection and SQLite authorizer restrict the capture to request metadata, dates, clocks and volume. It records a fingerprint of the exact selected contract rows and clocks, missing minute counts, traded rights during the entry window, and available prior futures sessions. The April–May flag additionally requires a committed `exam-2022-q1-unavailable.json` with a nonempty `q1_unavailability` reason supplied before either window is opened.
2. Verify and commit `exam-2022-h1-requests.json`. Then run `python exam_prepare.py snapshot` while the downloader is idle. The preparer checks the captured source, calendar, request ledger, clock fingerprint and warm-up before exporting prices into Dev. The export includes only request-scoped contracts and dates. It retains the observed future closing tail and both daily-index warm-up streams. A changed request or observation refuses the export. The preparer preserves its exclusive attempt marker and files for audit if it stops partway.
3. Verify and commit `exam-2022-h1-snapshot.json`, then use the one-shot runner. It checks that the snapshot's coverage equals the committed pre-price capture. The two manifests contain no candle prices.

The focused suite passed 23 checks using `python -m pytest test_exam_prepare.py test_exam_run.py test_exam_scoring.py test_n012_ab.py test_round30.py -q`. The source tests prohibit price columns during capture, check read-only access, exclude an unrelated contract, strike and date, and reject stale or changed evidence before prices are read. The real `capture` command exited 1 because Q1 has no saved full guard check. It created neither an input manifest nor a preparation marker. The atlas regenerated without changes. This is Dev research with no runtime, settings, migration or rollout change.

### Current archive blockers

The saved full Q2 check at 06:59 IST on November 6 is complete for its planned requests and has an unclean result. The in-window problem is May 31. The front NIFTY future dated June 30 has zero minutes on May 31 and 376 on June 1. The two-session request `future|NIFTY|2022-06-30|2022-05-31|2022-06-01` is already marked `ok` with 376 rows. This is a one-day reply recorded as complete. Its row count is below the 1,000-candle ceiling addressed by the existing repair target. A scope-specific guarded resolution is needed. Ordinary reruns skip finished request keys.

The Q2 check also flagged missing June 14 cash-index minutes and ten archive-wide volume validation issues from 2024–2025. Those findings are outside the N012 exam dates. The saved guard result remains unclean and the preparer requires a clean result. The May 31 gap affects both frozen windows and cannot be solved by selecting April–May. The January–March target still needs its completed guard check. This audit used only the request ledger and timestamp counts. Neither unseen price window has been opened or scored.

### Session-by-session April–May metadata audit

Read the 40-session calendar, exact archived request scopes and only candle clocks and volumes, under the preparer's price-denying authorizer. The 706 finished scoped requests covered every required cash-index minute and both traded option rights in the entry window on all 32 non-expiry dates. Four front-futures sessions were incomplete through 15:10 IST.

| Session | Front expiry | Missing minutes | Last observed | Existing request rows | Session type |
|---|---|---:|---|---:|---|
| April 28 | April 28 | 244 | 11:06 | 488 | Expiry |
| April 29 | May 26 | 98 | 13:32 | 634 | Regular |
| May 26 | May 26 | 246 | 11:04 | 110 | Expiry |
| May 31 | June 30 | 356 | None | 376 | Regular |

The exact finished keys are `future|NIFTY|2022-04-28|2022-04-27|2022-04-28`, `future|NIFTY|2022-05-26|2022-04-29|2022-05-02`, `future|NIFTY|2022-05-26|2022-05-26|2022-05-26` and `future|NIFTY|2022-06-30|2022-05-31|2022-06-01`. All returned fewer than 1,000 rows and are already marked finished. The dated regular book would skip the two own-expiry entries. The declared snapshot still requires complete session evidence, and the two regular-session gaps independently prevent either exam. The first April session also has no archived prior minutes of its front contract in the authorized request scope, with one and two prior sessions respectively for April 4 and 5. The audit does not select the fallback or prepare an exam dataset.
