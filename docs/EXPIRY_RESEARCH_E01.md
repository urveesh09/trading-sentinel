# E01: improve the expiry lottery's exits, then measure new expiry days

November 2, 2026. Dev research and a separate paper shadow; not deployed.

E01 improved both profit and losses on the eight archived expiry sessions. It
keeps the lottery's entry and upside rules, but adds a planned 30% premium stop.
This is an exit improvement, not another entry filter. A second idea, closing
the late strangle after a 30% pair loss, failed and was rejected.

Eight already examined sessions cannot establish reliable future profit. This
result still depends on one large winner, and SENSEX still loses overall.
Regular F&O's N11 research is separate and does not qualify expiry trading.

## What the module does and what went wrong

The existing expiry-v3 main book has three independent paper experiments:

- A: confirmed index/futures breakout after the 13:00–13:30 range, with a
  premium stop, failed-break exit, time stop and banking/trailing.
- B: a late call-and-put strangle, with a whole-pair profit target.
- C: a cheap option on the breakout, with a failed-break exit and large-winner
  banking/trailing. Unlike A, it had no premium stop: an option can decay badly
  even without the index crossing its failed-break level.

Each main play has its own Rs 2,500 daily full-premium/fee ceiling. This is not
one shared broker account. None of these experiments places real orders.

On five sessions, E01 sold C earlier at the recorded executable bid and reduced
its loss. It left the largest winning expiry unchanged. The pair-loss idea
instead sold before a recovery on October 8, increasing the combined loss.
One mechanism cannot safely be imposed on every play.

## Measured comparison

All amounts are rupees after the native frozen fee schedules. Baseline means
current expiry-v3 replayed on the same packets, not a mix of old historical
versions. E01's alternative is A + B + CE01 **instead of** A + B + C; never add
C and its shadow together as strategy profit.

| Eight recorded expiry sessions | Current v3 | E01 alternative |
|---|---:|---:|
| Modeled net | +6,548.10 | **+11,095.17** |
| Worst session | -1,427.00 | **-1,000.15** |
| Cumulative daily-P&L drawdown | 4,520.04 | **2,100.73** |
| Net without the largest winning session | -7,232.64 | **-2,685.57** |
| Positive / negative / zero sessions | 1 / 6 / 1 | **3 / 4 / 1** |
| NIFTY net | +9,986.91 | +11,634.74 |
| SENSEX net | -3,438.81 | -539.57 |
| Unresolved positions after modeled reconciliation | 0 | 0 |

The gain is Rs 4,547.07. Drawdown above is a fall in the running sum of daily
P&L, measured in rupees, **not** a finite-account percentage or a shared-capital
portfolio result. There is no compounding or capital reset claim.

| Session | Index | Current v3 | E01 alternative | Change |
|---|---|---:|---:|---:|
| 2026-10-06 | NIFTY | -1,285.60 | -1,000.15 | +285.45 |
| 2026-10-08 | SENSEX | -1,427.00 | +23.62 | +1,450.62 |
| 2026-10-13 | NIFTY | +13,780.74 | +13,780.74 | 0.00 |
| 2026-10-15 | SENSEX | -954.88 | -954.88 | 0.00 |
| 2026-10-19 | NIFTY | -1,357.93 | -903.80 | +454.13 |
| 2026-10-22 | SENSEX | 0.00 | 0.00 | 0.00 |
| 2026-10-27 | NIFTY | -1,150.30 | -242.05 | +908.25 |
| 2026-10-29 | SENSEX | -1,056.93 | +391.69 | +1,448.62 |

At each ask 5 paise higher and bid 5 paise lower, with unchanged timestamps and
depth, net is +10,994.22 versus +6,361.82; worst session -1,022.95 versus
-1,441.98. The improvement also survives excluding the oldest, weaker-clock
session. The fixed 20% and 40% stop diagnostics support it. Although 20% scored
more here, the predeclared 30% remains selected. No post-result parameter change.

The strangle pair-loss primary failed: +5,758.39, worst session -2,960.10 and
drawdown 4,739.64. Its neighbours failed too. All results remain on record.

## What the money does and does not mean

Recorded paper fill-event net changes from +13,791.10 to +14,059.17. Assumed
residual settlement changes from -7,243.00 to -2,964.00. Their sums give the
modeled totals above. Most of the improvement comes from avoiding assumed
expiry write-offs through earlier recorded-bid exits.

This is not broker-realized money. Auction-window paper fills remain
unverified; settlement uses sampled index values, not an official final
settlement receipt. Missing/stale bids remain non-fills. A 30% stop is a trigger,
not a loss guarantee: gaps, missing depth and delayed quotes can lose more,
up to the funded ticket. No short option or margin exposure is added by E01.

## Data limits and how the test was kept honest

The snapshot contains 7,594 ticks over eight sessions, with original gaps kept.
October 6 lacks raw index/futures timestamps and deeper option depth: only its
recorded observed values and one depth level are used. The other seven retain
raw clocks. October 22's zero-entry main session stays in the comparison.

All four existing sealed 2023–2026 regular-F&O exports contain **zero same-day
expiry option rows**. Their millions of other quotes cannot validate this
module. Next-week options are not substitutes. No 2022 data, ICICI requests,
new download, target or repair was used. A future one-minute expiry dataset can
help research, but cannot reproduce the native ten-second depth decisions and
two confirmations within 25 seconds on its own.

Historical source replay reproduced 95 position legs across all eight dates,
with only an explicit old-column DEFAULT 0 adaptation. Current-v3 and candidate
controls then used identical archived packets. The round was limited to two
primary hypotheses and four diagnostic neighbours: 80 declared cases including
ordinary and adverse controls. Failed adapter attempts are retained. There was
no second search round or selection of a favourable neighbour after scoring.

Research source/configuration were committed at **cbbdebb** before scores;
results at **c6537c6**. All 696 original source/config hashes were archived
before native integration. The app changes deliberately differ from that
freeze. Do not silently re-freeze old research against the new code. Reproduce
the research at its original source or verify the preserved source archive;
native integration has its own parity receipts.

## What is built

`CE01` (`expiry-e01-v1`, shadow-v6) is a separate default-enabled paper shadow.
It copies only a successfully saved, fresh C entry, with identical contract,
price, time, quantity, fees and full-premium ceiling. A durable primary ID and
matching economic terms are both required for a paired result. Missing or
mismatched identity/economics never becomes a zero or a profitable comparison.

Main A/B/C, N11 and real-order authority remain unchanged. CE01 adds no quote
request and no per-trade Telegram delivery; it appears beside C in the existing
summary. Old or already-started days are not silently enrolled. New day state
binds the version and enrollment. No database schema migration or `.env` edit
is required. `EXPIRY_E01_SHADOW_ENABLED=false` blocks new copies; existing CE01
positions still receive their pending, partial, failed-break, trailing and
settlement handling. Rollback the entry flag rather than removing the code
while CE01 positions remain open.

The native ordinary/adverse replay verifies identical CE01 economics to the
frozen candidate, unchanged main A/B/C and unchanged quote-call counts. Focused
tests cover old state, flags, saved admission binding, bad paired terms,
optional insertion failure, missing depth, partial exits and gap prices. See
[verification](research/simulation/2026-11-02-expiry-e01/VERIFICATION.md) and
[identity](research/simulation/2026-11-02-expiry-e01/IDENTITY.json) for exact counts,
source and push status. Production was not edited, restarted or deployed.

## Next work, fixed before new expiry outcomes

Collect at least **20 fresh, exactly paired C/CE01 entries**, including at least
five per index, after a normal authorized deployment. Run software/coverage
checks immediately; review economic promotion only when that sample is met.
Do not erase a losing day, loosen the 30% stop, add size or change the review
sample after outcomes. This is an initial evidence checkpoint, not statistical
proof or automatic promotion. At roughly two eligible expiries a week, several
months may be needed; missing admissions or coverage extend it.

Evaluate both aggregate and each index: net after fees, loss distribution,
drawdown, net without the best session, stop rebound opportunity cost, depth,
quote age, pending exits and unmatched/missing evidence. Keep actual fills,
paper fills, auction observations and assumed settlement separate. Apply the
same frozen profit/loss-control routes and adverse test; failing conditions
remain failed. Any later hypothesis gets a separate plan/freeze and new data.

The highest-value data improvement is reliable archived expiry quote paths and
official settlement evidence. Further genome rounds on eight known sessions
would give more opportunities to fit noise, not a trustworthy smarter trader.

Primary-source background and its limits are in
[SOURCES.md](research/simulation/2026-11-02-expiry-e01/SOURCES.md). That research
supports the risk mechanisms, not a claim that this Indian strategy will profit.
