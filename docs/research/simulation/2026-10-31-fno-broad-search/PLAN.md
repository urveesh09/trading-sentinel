# O31i: broad search for weak-day and weak-call complements

Owner explicitly authorizes a broad strategy/genome search, overriding the
usual two-candidate-per-round limit for this research. Start Dev408def1.
Production and real-money settings remain untouched; no deployments/orders.

Predeclare48 genomes:12 entry families x4 balanced gene combinations over
lookback10/20, stop1/1.5ATR, target2/3R, LIVE/RUN exits, plus8 seeded random-entry
controls under the same weak-day/no-stretch execution scope. Families: EMA crossover,
adaptive KAMA turn, Donchian break, Bollinger reentry, CCI reentry, confirmed
RSI divergence, regression-channel reversal, prior-day failed auction,
gap-fill/reclaim, compression release, OBV-confirmed break and same-clock
historical momentum. All use completed bars and known earlier history.

Screen one lot on dailyADX<30, no inherited VWAP-stretch filter on these NEW
families (that filter was selected for the original four). Keep original
cash/risk/premium/fee/expiry/day-clock constraints. Diagnostic brakes off and
Rs200/lot extra after replay, Rs300 sensitivity. Main controls keep ADX30,
stretch0.5, normal brakes and cost in cash path. No change to application policy.

Genome selection frozen in advance: from2024+2025 only, rank full-sample or
direction-subset proposals by their worse annual net per trade. Require
positive net and>=12 trades in EACH fitting year; take at most6, at most1 per
family, deterministic tie breaks. A subset only proposes a candidate; then
rerun that direction alone and the complete shared main+candidate book on ALL
three years. Commit the mechanically selected list before these replays. If no
eligible proposal, report no selection; do not weaken the rule.2026 is an
internal assessment, not an untouched holdout: all three years already seen.

Promising research candidate must earn>0 EVERY year afterRs200,>=8 trades/year
and>=40 total,>=5/6 nonnegative halves,>0 after removing each year's best day,
weekly t>=2, above the best valid random control, and pass a shared4-week-block sign-flip maximum-t sensitivity over
the48 screened strategies and actual selected direction replays (4096 samples,
seed310126, p<=0.05). Invalid/unresolved replays are never ranked. That diagnostic
does NOT account for all prior searches or prove profitability. Combined book
must improve main every year, paired weekly t>=2, fall<=main+1percentage point,
no unresolved positions. No automatic live promotion even for a pass.

Separate frozen option-expression diagnostic: same freshly reproduced main
and TPB-on-closed-day signals, matched entry/exit clocks, normalized one lot.
Compare50/100/150-point same-expiry debit verticals and inverse credit verticals
using actual same-minute positive-volume option candles, modeled adverse
bid/ask, current four-order fees and Rs200/400 extra per spread. Record missing
legs/invalid bounds as UNAVAILABLE, never zero. Reserve full strike width plus
fees from own cash for credit structures; no reuse of premium credit, borrowing
or naked exposure. This is paired expression evidence, NOT a spread book,
broker-margin proof or faithful spread exit/admission replay. Do not add its
profit to main. A paired expression is only an exploratory lead if its
entry-risk-compatible cohort covers>=95% of ALL requested trades in EVERY year,
has>=12 trades/year and>=40total, is positive EVERY year afterRs400 extra,
is positive after removing each year's best day and beats the single leg on
that same cohort EVERY year. Must report coverage/losses; still no portfolio
qualification or claim of a new traded strategy.

Investigate archived failures by causal side/direction/clock, but do not create
post-hoc rules from winning dates. Review primary sources for covered and
unavailable domains: volatility/spreads, stock residuals/pairs, news/order flow,
overnight/calendar structures and adaptive models. No fabricated data. Preserve
the fixed2023 exam and its candidate list; no downloads or quota changes.

Files/contracts: lab_broad.py, analyze_broad.py, spread_pairs.py, tests,
configuration/freeze/selection, sources, results and crosschecks in this folder.
Acceptance: exact main/control parity, all-prefix causality, financial and
cash checks, immutable data/source/cache receipts, source freeze committed and
pushed before scoring. Three guarded workers; monitor Production availability.
Raw data and trade evidence remain ignored under_local.

Rollout/rollback: offline Dev research only; stop workers and retain results.
No application config/migration impact. Update guide/active plan/checklist and
atlas as required; verify after every commit; preserve unrelated dirty work.
