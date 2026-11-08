# Sealed 2022 data recovery handoff

At 18:18 IST on November 6, the guarded history status showed 4,800 of 4,800 requests used and no downloader active. The free Q1 plan listed 32 index requests in its first phase and directed the owner to the guarded probe. Futures and option request counts are unknown until that phase has data. The latest Q2 full check remains unclean. These checks did not read or score unseen derivative prices.

## Why an ordinary rerun skips the gaps

The coverage checker tests futures at date level. A synthetic archive with 258 of 356 required minutes produced the same no-gap result as one with all 356 minutes. It detected the session only when zero futures rows existed. The current ceiling repair selects multi-session replies of at least 1,000 rows. The four affected finished replies are smaller, and the downloader skips keys marked `ok` or `empty`. The exam preparer independently requires every front-contract minute from 09:15 through 15:10.

## Exact owner-maintainer scope

These four proposed request keys were absent in the read-only ledger on November 6. Each is inside the Q2 archive calendar and uses the dated front contract required by the exam. They are a scope for the guarded maintainer and owner to review.

| Missing session | Required NIFTY future | Proposed unused key |
|---|---|---|
| April 28 | April 28 | `future\|NIFTY\|2022-04-28\|2022-04-28\|2022-04-28` |
| April 29 | May 26 | `future\|NIFTY\|2022-05-26\|2022-04-29\|2022-04-29` |
| May 26 | May 26 | `future\|NIFTY\|2022-05-26\|2022-05-25\|2022-05-26` |
| May 31 | June 30 | `future\|NIFTY\|2022-06-30\|2022-05-31\|2022-05-31` |

May 26 already has a finished one-day key with 110 rows. May 25 is the preceding trading day and has 376 observed minutes for that exact contract. The proposed pair is distinct and its two full sessions fit under 1,000 rows. Verify the reply's date and expiry coverage independently even if the provider marks it successful. Retain the earlier keys and rows.

June 14's missing cash index is outside both exam windows and inside the existing Q2 guard target. Its single-date key is already marked empty. The June 13–14 index key is absent and could be reviewed separately if the owner wants the full Q2 target repaired. The whole-archive integrity scan also reports five 2024 and five 2025 negative-volume flags, outside the exam. The preparer still requires a clean approved guard result. A maintainer must resolve or classify these findings through that process.

The Breeze history skill requires owner approval for guard maintenance and an unlisted repair scope. No target was registered, no provider request was sent and no history file or request ledger was edited. After the owner completes the guarded Q1 work and the four required front futures dates pass exact checks, repeat the established capture and snapshot workflow. The January–May exam stays sealed. A prior declaration would still be required for the April–May fallback, and the four dates affect that window too.

The [Dev evidence test](test_exam_evidence_limits.py) ran the installed guard against in-memory synthetic data. Verification used `python -m pytest test_exam_evidence_limits.py test_exam_prepare.py test_exam_run.py test_exam_scoring.py test_n012_ab.py test_round30.py -q` and passed 27 checks. The [exam workflow](EXAM_RUNNER.md) retains the actual coverage findings and the scoring commands.
