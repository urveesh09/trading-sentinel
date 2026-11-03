# Retain the ticket eligibility, change only the one-lot payoff

Standalone credit loses, and the old absolute drawdown brakes stop most later
admissions because one protected pack has more reserved risk than a long ticket.
No profitable score is selected or any original result overwritten.

The earlier learning was that E03.1 needs **both** the trend cue and an affordable
cheap ticket. Credit-only changed that price eligibility. Two final primary
hypotheses retain it, using only the original decision-time lot count:

- **HYBRID_8M**: original affordable plan has >=2 lots -> original E03.1 long.
  One lot -> protected opposite-side CREDIT_8M if feasible at decision; otherwise
  original one-lot E03.1. No fallback to a hypothetical long after seeing the
  next credit fill fail; wait for another causal signal.
- **HYBRID_TREND**: same, using CREDIT_TREND. No learned thresholds, classifier,
  best-day selection, new price band or retrospective trade list.

First original plan uses the original nearest eligible contract and fee/price
limits inside max 1,250 and current cash. A credit is feasible only with CREDIT.md
cash/collateral, positive credit, fees and remaining daily risk limits. If the
current credit plan cannot fit, a long may use only its original causal plan,
resized by genuine remaining risk. Max two sequential tickets, 5-minute cooldown.
One long position or short liability pack at a time; fully paid residual long
hedges are carried explicitly and never fund further entries at a positive mark.

Independent cash starts 25,000. Hybrid daily original full-loss reserve 5,000,
same absolute 1,500/3,000/4,000 cash brakes, same 5,000 drawdown acceptance limit
from PLAN.md. Long tickets <=1,250; credit pack limits exactly CREDIT.md. Every
closure uses the original individual long/credit engine rather than a daily
sum of unrelated experiments. E03.1 control must reproduce full event histories.

Diagnostics fixed now: replay both hybrids and credit-only policies without
the inherited drawdown brakes but with cash/collateral and daily reserve still
binding. This separates raw payoff from controller selection; it cannot rescue
a large-risk or margin-unqualified policy. Report full cash drawdowns. Additional
direction-reversed controls, fixed friction and coarse holding/width changes
are diagnostic only, never a post-score winner. No unsupported short settlement.

These ideas are motivated by already seen failures/data; not independent proof.
Shared positive/improvement/ex-best checks apply, and margin/atomic execution
remain explicitly unqualified. If none passes, close this bounded investigation
with the concrete outcomes; no manufactured new strategy generation. No native,
config/schema/Production/flag/provider/download or real capital changes.
