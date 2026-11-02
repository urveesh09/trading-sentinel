# E01 round1 — exits, not additional filtering or risk

Written before any candidate is replayed. Current v3 control is the benchmark,
not the worse mixed historical rules. All eight dates are already seen. Zero
same-day-expiry rows exist in the four existing sealed multi-year F&O exports;
next-week options cannot substitute. No2022 access or download in this round.

Two hypotheses, inherited30% from A rather than a fitted new threshold:

1. **PAIR_30:** B keeps its same two legs, sizing,20% net pair target and clocks.
   Also latch an all-leg exit if the fully executable NET liquidation of the
   pair reaches a loss of30% of premium paid. One missing/stale/thin leg makes
   the mark unavailable; it is never a zero-price loss signal. Pending orders
   keep being retried at actual bid depth; the pair is not assumed atomic.
2. **CSTOP_30:** C keeps its original entry, full-premium ceiling, failed-break,
   bank, trail and deadlines. Add A's30% premium backstop, filled at actual bid
   depth with pending-exit retries. No parent-stop alteration or increased size.

Neighbour diagnostics:20% and40% for EACH mechanism; neither replaces a failed
30% primary. A unchanged. All existing shadows remain independent.

80 candidate/control cases: ordinary baseline8 already computed, six ordinary
variants48; adverse baseline and two primaries24. Eight historical source
controls are a separate parity set, plus retained failed preflight attempts.
Adverse quotes move each actual option ask level UP by0.05 and bid DOWN by0.05,
keeping quantities/timestamps/gaps; nonpositive bids stay absent. No invented
depth. Native spread/budget gates apply equally to baseline and candidates.

Acceptance: the PLAN profit OR loss-control route must pass in BOTH ordinary
and adverse scenarios, both on all eight sessions and on the seven sessions
with recorded raw index/future clocks (Oct6 remains an explicit lower-fidelity
diagnostic). For a passing profit primary, both ordinary neighbours must keep
net at/above baseline and worst day no worse; for a passing loss-control primary,
both must also meet that loss-control route. Do not choose a neighbour instead.
Budget/deadline/native fee/depth/latched-exit invariants must pass independently.

Cumulative drawdown means peak-to-trough RUPEES of chronologically summed
session P&L, not a finite shared account or invented percentage. Main plays
have separate2500 daily ceilings. Filled-event and assumed residual values,
continuous and unverified auction-window events stay separately attributable.
No monetary route is eligible with unresolved exposure. All-case modeled totals
are not broker money or proof of future edge.

The old10-expiry owner's review remains intact. Only eight expiry sessions,
including a zero-entry day, exist; a genome sweep on them would be misleading.
If round1 fails, document causes before a separately frozen round2 (maximum two
additional mechanisms), then stop. Any acceptable E01 initially stays a paper
shadow, with main A/B/C and real-money authority unchanged.
