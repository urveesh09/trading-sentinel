# N04 — preserve the balanced reference and isolate the two exit behaviors

Owner asks to continue the next plan, cautiously consider parameters, and retain
the best comparison across compaction/handoffs. Preferred BALANCED_RETEST_N03 is
NORMAL|TPB_ONE|RETEST from N03, source2de5448/results4a90fdc: net56,192/50,090/
54,153, closed drawdown2.16/5.22/4.02%. It is a preferred balanced seen-data
research reference, not a universal winner, qualified policy or deployed system.
Persist docs/FNO_RESEARCH_REFERENCE.md/json with exact source/data/book/evaluation
hashes and make the active plan point to it. Never silently replace its identity.

## Two hypotheses, no new thresholds

N03 HORIZON combined early departure and conditional continuation; its mixed
results do not identify which behavior helped. Keep its existing constants and
entry functions and test ONLY two exit variants separately:

- STALL_ONLY: the original EFF60min exit, except from30–60min, while trail is
  unarmed, net liquidation at positive bid after shipped fees AND stress<=0
  and underlying progress<0.5 initial-risk units, use30min soft time stop.
  Never extend to90. Missing bid does not fabricate a liquidation price.
- CONTINUE_ONLY: original60min exit until age60; up to90min only while net
  liquidation>0, progress>=1R and fresh completed bar continues on the relevant
  side of VWAP with improving close and valid volume. Missing/stale/invalid
  continuation immediately returns60min; never apply early30 departure.

BASE is unchanged own EFF exits. All other members, stop/target/trail, premium
backstop, hard-flat, entry cutoff, cash and brakes unchanged. Per-leg overrides
restore even on errors; no averaging, partials, widened stops or new size cap.
No hindsight per-year mixture, no combined third variant, no parameter grid.
N02 orchestration structure is improved in research, not profit-qualified.

## Books, inputs and source freeze

Normal contexts MAIN, TPB_ONE, BALANCED_RETEST, CORE_SELECT each BASE/STALL_ONLY/
CONTINUE_ONLY:12 books/year. MAIN/TPB_ONE/CORE_SELECT retain original EFF entries;
BALANCED_RETEST retains the EXACT N03 retest entry and TPB_ONE low-day extension.
Fixed-one-lot diagnostic contexts MAIN and BALANCED_RETEST each three modes:
6/year.18×3=54 fresh annual books. Reuse unchanged TPB_FULL and N03 combined-exit
benchmarks ONLY by sealed hashes, label them reused, not new scores.

Fresh250k/year, current normal2-lot/3-when-proven caps and extra low-day TPB1lot;
ONE changes both caps to1, retaining brakes. Existing adverse modeled bid/ask,
shipped fees and stress(200+5*lots)*lots in actual cash. Annual resets are not
continuous wealth; no sum across independent books. Same699 sealed2024/25/26
sessions through2026Oct28, special-session clock fixes, gaps/negative-volume and
unknown historical depth/regime limits retained. No new data/API/login/packages.
2023 option data/exam remains uninspected/unscored; warmup stays declared.

Old CORE_SELECT choices are reused exactly, not retrained on new strategy returns.
Changing exits may change future admissions/size; distinguish exact immutable
economic entry pairs from resized/missing/different admissions. No ticker/date
profit pairing or adding rejected-trade P&L back into a nonexistent account.

Freeze source/config/inputs/daily/memos/old decision and reference/eval hashes,
all18 books/acceptance and reference registry BEFORE scoring; commit/push.
15 controls must reproduce N03 exactly: four normal BASE contexts/year and
ONE MAIN BASE/year, normalize only new admission identity. ONE BALANCED is a new
diagnostic control, verified mechanically, not represented as old parity.

## Acceptance and reporting

Eight normal candidate/context comparisons, same frozen rule: net>0 each year,
positive without annual best trade AND day,>=12 trades/year>=60total,>=5/6
nonnegative halves, net>=matched BASE EACH year and better aggregate, annual
closed-cash drawdown<=max(1.5*BASE,.05), paired weekly t>=2 and shared four-week
sign-flip max-t p<=.05 across ALL eight pairs (4096 draws,seed110401).
Zero unresolved/financial/memo/source/identity/clock defects. Also show each
candidate versus unchanged MAIN, BALANCED_RETEST_N03 and stronger TPB_FULL.
No thresholds relaxed or offspring chosen from scores. All years seen, even a
pass is exploratory and cannot qualify money, partner tips or deployment.

Report net/trades/costs, cash drawdown, best-day/winner sensitivity, halves,
member contributions, separate early/extended choices, lost/new admissions,
exact-entry exit deltas and equal-size diagnostics. Keep preferred reference
unless a later explicit selection contract supports a versioned change; a
higher historical total alone does not erase failed consistency/statistical bars.

Independently replay exit lifecycles from exact entry terms to first executable
ordinary exit, reconstruct original/retest source paths, reconcile archive prices
and accepted traces, recompute annual/weekly/resample statistics. Verify adapter
BASE delegates unchanged, modes cannot invoke the other branch, per-leg clocks
restore on error and urgent exits still win. Reuse source-bound N03 mechanics
checks and raw/cache receipts by hash where no inputs/source change; do not
count reused checks as fresh. Fresh per-session footprints/price checks on new
books remain necessary.

Post-run descriptive case audit: retain causal source-bar efficiency/body/rvol,
VWAP/stretch, ATR, stop/target distances, option premium/spread, dated expiry and
clock for original EFF admissions in ALL three years, highlighting2026 losses
of retest opportunities. Later confirmation/outcome are labels, never earlier
inputs or economic P&L pairs. No fitted case gate introduced this round.

## Files, rollout and remaining work

exit_lab.py isolated adapter, exit_rules.py pure ablation selector, analyze_exit.py
complete ledger/control checks, tests and nested reporting audits. Stable
docs/FNO_RESEARCH_REFERENCE.md/json plus source/result/config hashes. Maintain
SYSTEM_GUIDE/NEXT_AGENT_PLAN/HANDOVER_CHECKLIST each implementation commit;
regenerate atlas, immediately check committed doc consistency. Preserve unrelated
work. At most3 memory-guarded workers,550s resumable slices. No Production/runtime
config/migration/order/message/money change or restart. Rollback stops research
workers; retain all failures. Deliver results and next contract, keeping2023
deferred until owner requests its exam. Prospective evidence is still required.
