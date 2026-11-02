# E01 round1 outcome — retain CSTOP30, reject the strangle loss floor

Source/active pre-score freeze commit cbbdebb. No parameter or score rule changed.
All80 declared cases finished (8 existing ordinary controls,48 ordinary variants,
24 adverse variants);72 new candidate/stress replays took156.92seconds. Eight
historical controls and two retained preflight replay attempts are separate.

| Current-rule comparison, eight sessions | Native v3 | CSTOP30 |
|---|---:|---:|
| Modeled net | 6,548.10 | 11,095.17 |
| Worst session | -1,427.00 | -1,000.15 |
| Cumulative P&L drawdown, rupees | 4,520.04 | 2,100.73 |
| Net without each book's best session | -7,232.64 | -2,685.57 |
| Positive / negative / zero sessions | 1 / 6 / 1 | 3 / 4 / 1 |
| NIFTY net | 9,986.91 | 11,634.74 |
| SENSEX net | -3,438.81 | -539.57 |

CSTOP30 passes the frozen profit AND loss-control routes on ordinary/adverse
quotes and both all8 and raw-clock7 populations.20% and40% neighbour diagnostics
both support the ordinary improvement, but the predeclared30% stays selected:
20% made more on this sample and is not substituted after seeing the outcome.
The largest winning expiry is unchanged. Five losing tickets are exited sooner.

Money is paper-native, not broker execution. Filled-event/fee net changes from
13,791.10 to14,059.17; assumed residual net changes from-7,243.00 to-2,964.00.
Most of the4,547.07 improvement is avoiding assumed expiry write-offs by selling
lottery tickets into recorded bids earlier. Auction-window fills remain
unverified and sampled-index settlement remains assumed. No negative residual
was hidden, assigned zero or treated as a broker fill.

PAIR30 FAILS: net5,758.39, worst day-2,960.10, cumulative drawdown4,739.64.
It sells a strangle before a recovery on Oct8, the mechanism the old BR audit
already warned about. Its20%/40% neighbours also fail. No promoted pair stop.

Independent audit:80 cases,290 primary legs,560 price/depth checks (480
continuous and80 unverified auction events),240 full-premium entry-budget
checks and13 pair-loss exits reconcile. Existing63 expiry tests and11 new
frozen tests pass. The eight/95-position historical parity includes only an
explicit DEFAULT0 schema adaptation, not financial tolerance changes.

## Stop searching this sample; implement a forward shadow

Only eight correlated expiry sessions exist, all seen. Results still lose money
without the large Oct13 winner, and SENSEX remains negative. A passing small
screen is not a reliable profitability estimate. Do NOT run a second genome
round merely to improve the historical number.

Next slice: implement **CE01**, a separately versioned paper shadow with C's
exact entry/size/failed-break/bank/trail/flat rules plus the frozen30% premium
stop. Current main A/B/C remain unchanged. Use existing quotes, existing
2500 full-premium per-play ceiling, existing durable pending exits and outbox.
No broker/order authority, N11 interaction or extra provider request.

Files: expiry_paper.py, config.py, tests/test_expiry_paper.py and focused E01
tests. New shadow toggle only gates new entries; open CE01 legs continue to be
managed with it off. Old day states are not silently enrolled mid-session.
Fresh day state binds E01 version/enabled state; old days remain historical.
The day summary pairs CE01 with C by exact entry, not by day/ticker guessing.

Acceptance: replay actual native CE01 across all8 ordinary and adverse sessions;
match the frozen CSTOP30 positions/fees/events after play-name translation;
prove every main A/B/C outcome is unchanged; test pending exits/partial depth,
disabled/new versus already-open legs and old-state compatibility. Run native
expiry and isolation/settings checks; update guide/plan/atlas on commit.

The research source was archived byte-for-byte at its original696 hashes before
application integration. Integration intentionally changes source: do not
silently re-freeze the research or claim its strict working-tree guard still
matches afterwards. Reproduce it at cbbdebb/in an isolated checkout, or verify
the archived source tree. Native integration parity is a separate receipt.
Rollback disables new CE01 entries while preserving its existing exits. No
Production edit/restart/merge/deployment is authorized by this study.
