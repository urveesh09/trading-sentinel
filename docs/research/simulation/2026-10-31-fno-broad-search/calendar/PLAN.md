# O31i-C: explicit special-session replay clock correction

Before inspecting the broad screen's financial rankings, its 2024 replay ledger
showed 15 arms with one unresolved position each, on March 2 or May 18. Both
were split special sessions, not normal 15:30 closes. Preserve the original
screen and failures; do not treat unresolved positions as zero-profit trades.

Official contracts: NSE/MSD/60677 (February 14, 2024),
https://nsearchives.nseindia.com/content/circulars/MSD60677.pdf ; and
NSE/MSD/61893 (May 7, 2024),
https://nsearchives.nseindia.com/content/circulars/MSD61893.pdf . The F&O sessions
were 09:15–10:00 and 11:30–12:30. Broker primary confirmation for March 2:
https://zerodha.com/marketintel/bulletin/371327/live-trading-session-on-saturday-march-02-2024 .

Correction fixed independently of profits: only on those two ISO dates, stop
entries at 12:00 and request hard flat from 12:25, leaving five minutes before
the official close. Ordinary dates, including January 20, remain unchanged.
Use only actual archived observations; no invented quotes during the break,
perfect stops, or price interpolation. Missing exits remain unresolved.

Rerun ALL 59 2024 books, not just broken arms. Reuse 2025/2026 original outputs
only because the date-specific override is provably inactive for every date
in those windows; bind each reused file by hash and test ordinary-call parity
and exception restoration. Controls must still reproduce the previously
verified main and TPB books exactly. Separate caches preserve both versions.

Use the unchanged parent selection and acceptance functions. Freeze and commit
this source before scoring; commit the corrected selection before direction-
restricted and shared-cash replays. Corrected outputs are the canonical screen;
original outputs remain the superseded unresolved-calendar diagnostic.

Files: calendar_lab.py, analyze_calendar.py, test_calendar.py, freeze.json,
results/selection and ignored local receipts. No application, settings file,
migration, broker authority or Production change. Rollback: stop workers and
retain original and corrected evidence. Statistical/in-sample limitations from
the parent plan remain; no 2023 exam changes or qualification claims.
