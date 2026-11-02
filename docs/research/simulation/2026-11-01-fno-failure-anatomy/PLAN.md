# N07 — N04/N05 failure anatomy and bounded repair experiment

Status: diagnosis first; candidate contracts not chosen or scored.

Pre-score implementation decision after Phase1: two break-even boundary rules,
not a new threshold search. PREMIUM_STALL adds bid<=immutable entry premium to
N04 eligibility. STRUCT_OR_PREMIUM adds that premium weakness as an alternative
to N05's existing closed-bar structural failure, within the SAME N04 eligibility.
Price strictly above entry preserves native management unless STRUCT_OR_PREMIUM
has a valid structural failure. Equality counts as no price gain. Missing bid
cannot create an early exit. All stops/trail/native60/hard-flat remain active.
Ten books/year: NORMAL/ONE each BASE/STALL30/STRUCT30 and both candidates.
Eighteen fresh annual controls must match before twelve candidate annual books.
NORMAL only is primary; ONE is diagnostic, never a post-result sizing choice.
Period rule is explicit:2024/25 Jan-Jun/Jul-Dec;2026 Jan-May/Jun-Oct28, inherited
from prior studies. Both period alternatives in N06 had the same failed verdict.
No candidate score or new strategy/cash path was inspected to choose these rules.

Additional pre-score cost sensitivity: all five policies with normal sizing and
ONLY synthetic extra stress removed ([0,0]); modeled candle spread/current fees
remain. Fifteen added annual diagnostics (45 books total). Not primary, not an
actual-cost claim or a route to selecting the best cost setting. Required because
the three2024 early cuts have positive premium gross and net after current fees
before synthetic stress; cost assumptions influence exit timing as well as P&L.
No new strategy hypothesis or free threshold. Fixed-one-lot diagnostics retained.

User asks why N04 fails, why selection chose it, whether countering those cases
also sacrifices profit, and whether N04/N05 can be directly improved. This is
newly authorized exploratory research after N06, not independent validation.

Scope: Dev research only, exact saved reference records unchanged. Production
read-only health/release checks only; no application/configuration/env/migration,
capital/lot/risk/live authority/order/Telegram/deploy/restart changes. No2023 exam,
downloads, login, Breeze or new packages. All2024–26 data already seen.

Phase1 diagnostic contracts:
- Enumerate ALL saved N04/N05 closed losses and wins, strategy/direction/session
  gates/exit reason, cost contribution and drawdown episodes, never only worst
  trades. Immutable admission terms for pairs; no ticker/date-only matching.
- Attribute N04 versus N03 and N05 into identical-entry exit effects, changed
  quantities/admissions and later shared cash paths. Review actual archived
  observations available THEN separately from later recovery/outcome labels.
- Trace every N06 accepted N04-variant trade to its frozen daily decision and
  earlier-label weekly score/support. N04 is a fixed policy, not the selector.
  N06 never selected N04 in2024; no false attribution of its2024 early cuts to
  a nonexistent switch. Current losses are not known at selection time.
- Diagnose bid premium, underlying progress, completed-bar direction/VWAP,
  original retest level and elapsed time. No retrospective winner labels as
  inputs; unknown real depth/IV/Greek contributions remain unknown.

Phase2 conditional implementation: at most TWO explicit exit-only hypotheses
supported by causal mechanics. Choose fixed rules after diagnosis, before any
new candidate replay; no threshold grid. Persist diagnosis, source/config/input
hashes, rule/acceptance freeze and commit before scoring. Native stops/trail,
entry deadline/hard flat, cash/brakes/2–3lot caps and LOW TPB1 remain unchanged.
Reproduce exact saved BASE/N04/N05 controls before comparing candidates; include
fixed-one-lot diagnostics to distinguish exit economics from resizing effects.

Acceptance to bind before replay: more annual net and no larger annual CLOSED
drawdown than BOTH N04/N05 in each year; positive without best trade/day;
>=12 annual/60 total closes;>=5/6 positive fixed periods; paired weekly t>=2
versus N04 and two-arm four-week-block max-T p<=.05,4096 draws,seed110701.
Declare actual2026 period boundaries explicitly before scoring. All results
remain seen-data/unqualified regardless of pass; no automatic promotion.

Verification: focused rule boundary/future-bar/quote absence/state restoration/
native-exit priority tests, exact control parity, independent fees/cash/entry
price/trace/retest/first-exit/selection/context/statistic reconciliation. Reuse
prior699 raw/cache checks only by exact inherited source/input hashes. Keep
every failed attempt/report. Full paths instead of profitable exit stitching.

Documentation/rollout: guide/active plan/checklist with each implementation
commit, atlas regeneration for source declarations; exact commits/commands/
limits/evidence and clear successor checkpoint. Push only owned slices,
preserving unrelated dirty40/42/50-line root-doc slices. Rollback stops research
workers only; no Production rollback. Remaining: fresh keyed shadow/actual cost
evidence, predeclared prospective review;2023 deferred; larger sizing conditional.
