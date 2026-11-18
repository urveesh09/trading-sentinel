# Round 8 — EN86–EN95

Research-only implementation of `docs/EXPIRY_RESEARCH_EN86_EN95.md`. Rules and
pre-score resolutions: PLAN8.md; actual progress: STATUS8.md. Prior frozen files
and runtime policies are never edited. All history here has already been studied.

From Dev, using `C:/Users/Urveesh/sentinel-ml-venv/Scripts/python.exe -B`:

```
test8.py unit
test8.py parity
test8.py causal
test8.py modelcausal
score8.py freeze                 # once, after checks; commit freeze + rules
score8.py score                  # once, refuses altered source/data/restart
verify8.py
runner8.py rehearse              # once, separate seen-data ledger, no new evidence
render8.py
```

The anatomy follows the other developer's convention: ANATOMY8.md explains each
slot, ANATOMY8-tables.md contains all arms and controls, results8.json carries
metrics, anatomy8.json contains day/parent/order/event records. Separate source,
mechanics, causality, calibration and replay receipts state actual checks.

Forward work is manual, offline and requires a sealed SQLite snapshot (the
operations-store candle schema with explicit interval), its expected SHA256,
and an explicit dated calendar independent of downloaded data. No future session
is scored automatically. Example argument structure, with real local paths:

```
runner8.py run --calendar CALENDAR.json --snapshot SNAPSHOT.sqlite --expected-snapshot-sha SHA256 --now 2026-11-24T18:00:00+05:30
runner8.py status
review8.py --ledger LEDGER.sqlite --out REVIEW.json
```

That example clock is not permission to score unfinished/future sessions. Supply
the actual completed-session assessment time. A calendar needs `source`,
`verified_through`, and `sessions` entries with `underlying`, `day`, optional
`close` (15:30 default). No calendar is fabricated from weekday assumptions.
Refresh its authoritative dated coverage before it ends; no result for uncovered
dates is implied. New cohorts start after the actual committed implementation
freeze and verification. SENSEX OI remains unavailable in the present input set.

The new ledger uses SQLite unique immutable final keys and leases, with PENDING
before the 48-hour deadline and MISSING afterward. A later dataset gets a linked
sensitivity, never silently replaces a final record. Review reprices eligible
sessions at changing cash/brakes; gaps prevent an exact continuous-wallet claim.
This does not append to EN85's old ledger or change EN55's old registration.

Reporting correction after scoring: `review8.py` wraps the archived runner's
review so cells with zero eligible observations show null money, not zero. It
also separates a mechanical tail-screen label from continuous-wallet rejection.
`test_review8.py` checks this reporting adapter. Frozen rules/results are unchanged.

No network, broker, Telegram, scheduler, `.env`, Production or capital changes.
Process-scoped network audit hooks guard replay entrypoints. Raw inputs and
scratch ledgers remain in ignored `_local`/external sealed data paths.
