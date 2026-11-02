# O31h: when did the failed complements work, and was that knowable at entry?

Dev research only. Start checkout9304144. Production read-only. Reuse sealed
NIFTY2024/25/Jan–Oct28 2026 inputs and O31g's failed trades; do not alter O31g.

1. Diagnose positive trades/months/halves and failures. Keep costs, best-day
   dependence and sample sizes visible. Distinguish realized underlying
   direction from option profitability. No causal claims from associations.
2. Describe conditions AVAILABLE AT ENTRY: prior daily DMI/EMA direction,
   prior daily ADX and RV10, first30m range relative to prior dailyATR,
   entry relative to sessionVWAP, same-slot historical relative volume,
   six-bar efficiency, gap direction and entry clock. Fixed round thresholds;
   publish all buckets, missing inputs and year splits, not only winners.
   Full-session trend/range and subsequent price moves are HINDSIGHT ONLY.
3. Cross-check prefix causality and financial partitions. Any conditional
   trade subset is diagnostic, not a replay: removing a trade can release
   later trades or alter cash/brakes. Selection on two years is an exploratory
   stability check, not a new holdout (all three years are already seen).
4. Research primary sources on continuation versus reversal after large moves
   and trend pullbacks. After diagnosis, freeze AT MOST TWO concrete follow-up
   entry mechanisms and unchanged pass/fail rules before any new replay.
5. Replay alone and in the shared main book, keeping original cash/risk/lot
   limits and deadlines; retain all failures. No application change or deploy.

Files/contracts: diagnose.py, diagnostic JSONs, lab_follow.py, analyze_follow.py,
tests, configuration/freeze, report and crosschecks in this new folder. Raw
prices/trades remain ignored in _local. Old2023 exam unchanged and unopened;
existing daily warmup permitted. No downloads or market-data/broker calls.

Acceptance: old yearly/candidate parity; source/data/memo bindings match;
causal clocks; own-cash, whole lots, fees and no unresolved exposure. A new
candidate needs positive net EVERY year after Rs200/lot/trade, >=8/year and
>=40 total, >=5/6 nonnegative halves, positive without each year's best day,
weekly t>=2. Its complete combined book must improve main EVERY year, paired
weekly t>=2, yearly realized-equity drawdown<=main+1 percentage point. Rs300
sensitivity reported. A pass allows prospective paper research only.

Rollout/rollback: research only; stop workers; keep evidence. No config or
migration impact. Update guide/active plan/checklist with findings and commits;
regenerate atlas if relevant. Remaining: diagnosis, source review, frozen
follow-up, focused checks, run/reconcile/report; preserve all unrelated work.
