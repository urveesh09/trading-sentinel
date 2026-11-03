# Why there is a second freeze

The first freeze (`freeze.json`, commit `b7c90bd`) was committed before scoring. Its first `score` run
crashed inside the futures-basis diagnostic before any result was computed or printed: on October 15
(SENSEX) the Production recording has no index or future value from 15:00 to 15:15. The fix, and nothing
else: a day without a recorded index at 15:20 or from 15:31 is unavailable (never zero), and the
futures diagnostic is empty when its basis cannot be measured. Rules, days, pass tests and the plan are
unchanged. `freeze-v2.json` hashes the fixed script; `freeze.json` stays as the superseded record.
