# N03 — improve EFF independently, then test whole-book consequences

Owner authorizes the next plan and underlying strategy improvements. N02 fixed
MAIN's absence from the research selector; it did not prove switching profitable.
Target EFF first: MAIN2025 EFF27 trades net−21,174,15 time stops; fixed-lot
diagnostic negative too, and five trades lose despite favorable underlying exit.
2024/2026 EFF contributions can be positive, so no blanket deletion/call ban.

## Scope and information contract

Offline Dev only,2024/2025/2026 through October28, all already seen. Keep2023
uninspected/unscored and its existing exam unchanged. No Production changes,
orders/messages, capital/configuration, download/login or new dependencies.
Use actual archived option/future candles under the existing modeled quote,
expiry/calendar/clock/risk assumptions. Audit causal features/quote availability
first. Missing IV, news and historical depth remain missing, not fabricated.

Two hypotheses ONLY; no combined third arm, grid, genome or post-score tuning:

1. **RETEST entry:** original EFF signal arms a setup when normal priority reaches
   EFF. No immediate EFF entry. Within the NEXT three consecutive closed5-minute
   bars, require a retest of the broken previous-four-bar high/low (zone±0.25
   original ATR), close back on the breakout side, direction-matching candle and
   improvement over the preceding close. A close beyond the far side of that
   zone, original stop breach, missing/old state, bar gap, crisis or expiry of
   the15-minute window invalidates it. Day changes reset it. Prior SHIPPED/OR20
   priority still wins; confirmation may preempt TPB as ordinary EFF does.
   Stop remains the original breakout stop; target resets to1.8R from the
   confirmation close, ATR/current rvol refresh from closed bars. Normal planner
   recomputes option choice/size using the actual current quote and cash.
2. **HORIZON exit:** original EFF entries/stops/target/trail unchanged. When age
   is30–60min, trail not armed, net liquidation at current positive bid after
   shipped fees AND declared stress cost<=0, and signed underlying progress<0.5
   original risk units, set that leg's soft time stop to30min. At age60–90min,
   extend soft time stop to90 ONLY while net liquidation>0, underlying progress
   >=1R, and a fresh completed5-minute close is on the directional VWAP side
   and improving over the prior close. Missing/invalid/stale features or loss of
   continuation returns the original60min rule immediately. Hard-flat, premium/
   underlying stops, trail and all other urgent exits always remain active.
   No averaging, partial fills, extra size, stop widening or risk reset.

Reference every outcome at its causal clock; cache repeated evaluations of the
same closed signal consistently without modifying the shared original memo.
Per-leg exit policy overrides restored even on exceptions; concurrent EFF legs
can have different exit choices. Record source setup/confirmation and exit
context on the exact immutable admission identity, not ticker/date guesses.

## Books, costs and experiment

Normal sizing: four contexts EFF_ONLY, MAIN, TPB_ONE and CORE_SELECT, each with
BASE/RETEST/HORIZON (12 books/year), plus unchanged TPB_FULL benchmark (1).
Fixed-one-lot sizing: EFF_ONLY and MAIN, each BASE/RETEST/HORIZON (6/year).
Total19/year,57 fresh annual replays, at most three workers in550-second slices.
Fresh250k each year; current cash/risk/2-lot/3-when-proven caps, declared special
session clocks and inherited modeled quotes/fees, plus(200+5*lots)*lots stress
in actual cash. Fixed-one-lot changes BOTH size caps only, retaining all brakes.
Do not sum independent books or treat yearly cash resets as a continuous wallet.

CORE_SELECT daily choices remain exactly the N02 sealed past-only decisions;
do not retrain them on modified strategy returns in this experiment. This
isolates underlying changes, not a newly optimized joint selector. MAIN stays
the explicit incumbent. TPB_ONE caps only added LOW-day TPB puts, not main size.
All unchanged normal MAIN/TPB_ONE/TPB_FULL/CORE_SELECT controls must reproduce
their N02 economics exactly before interpreting candidate differences.

Before scoring commit source/configuration/data/memo/daily/decision-file hashes,
coverage probe, all19 books, acceptance and original2023-exam hash. Strategy
source stays frozen afterward; separate nested reporting/tests can audit it.

## Acceptance and checks

Report every book/year, whole-cash net, fees, trades, best winner/day removal,
closed-cash drawdown, six halves, entry displacement/changed exposure, EFF-only
and non-EFF contributions, causal setup/exit choices, and fixed-size attribution.
An improvement is descriptive, never an independent qualification on seen data.

For each of the eight normal candidate/context pairs: net>0 every year,
net excluding best trade AND best day>0 every year, >=8 trades/year and>=40total
for EFF_ONLY or>=12/year and>=60total for other contexts, >=5/6 nonnegative
halves, net>=matched BASE in EACH year and greater aggregate; annual closed
drawdown<=max(1.5*BASE,.05); paired weekly t>=2; shared four-week sign-flip
max-t adjusted p<=.05 across ALL eight pairs (4096 draws,seed110301).
Zero unresolved/cash/fee/clock/source/memo/identity defects. Fixed-lot results
are diagnostic: disclose whether normal improvements survive equal quantity;
do not pick normal versus fixed mode after scores. No pass relaxation.

Tests: causal/future-bar invariance, correct retest direction/next-bar/window,
gap/day/crisis invalidation, same-bar repeat consistency, immutable admission
terms, bid/net-cost thresholds, age30/60/90 boundaries, stale continuation,
different policies for concurrent EFF legs, restoration on error, urgent exits
and special-session hard-flat preserved, non-EFF members unchanged. Independently
check archive entry/exit quotes, actual confirmed paths and exit decisions.

## Files, rollout and remaining work

eff_rules.py pure context/retest/exit choices; eff_lab.py isolated adapter and
freeze; analyze_eff.py complete ledgers and unchanged-control parity; focused
tests and nested reporting verifiers. Update SYSTEM_GUIDE/NEXT_AGENT_PLAN/
HANDOVER_CHECKLIST for implementation commits, regenerate atlas and immediately
verify committed doc slices. Preserve unrelated work. No application deployment
from these results. Rollback stops research workers, leaving resumable outputs.
After scoring keep failures visible; next underlying member requires a separately
frozen later study. Prospective evidence and eventually the owner-requested2023
exam remain separate. No automatic live or partner qualification.
