# N02: incumbent-aware whole-policy selection

Owner asks why N01 displaced the main policy, why main2025 was weaker, and to
improve/test selection on2024–2026.2023 is explicitly deferred, uninspected
and unscored; do not amend its existing freeze in this round. Production remains
untouched. All three available market years have been repeatedly seen.

## Identified design weakness and diagnostic contract

N01 learned over six individual experts, not the working MAIN policy. It also
removed MAIN's dailyADX eligibility/priority and could let weak new experts
consume risk budget. In2026 its learner took60 LOW-daily-ADX TPB trades and0
of MAIN's33 exact signal/entry opportunities. This was an experimental design
weakness, not a Production incident. MAIN2025 EFF −21,174 offsets TPB +21,414.
Diagnose member/side/clock/exit/lot/stress contributions in all years; compare
fixed-lot controls too. Do not equate gate-evaluation counts to missed trades,
or call a signal/entry match an economic pair when clocks/prices/quantity differ.

## Policies and two frozen hypotheses

Keep underlying entry functions, targets/stops/exits and risk/deadline logic.
Reference whole policies, identical starting cash250k/year:
- MAIN: original four experts, prior dailyADX>=30, stretch0.5.
- NO_EFF: MAIN except EFF disabled. This is a previously studied challenger,
  not a new parameter optimization.
- TPB_FULL: MAIN plus puts-only TPB on low-ADX days, original normal sizing;
  this is the existing stronger research benchmark, not a qualified policy.
- TPB_ONE: identical to TPB_FULL except ONLY low-ADX additions capped at one
  lot. Main trades retain original lot limits. Caps restored after every call,
  including failures; no notional borrowing, forced fill, risk reset or exposure
  abandonment. Extra losses can still affect later MAIN admissions through
  shared equity/brakes; preservation of eligibility is not P&L protection.

Two candidates, frozen before new replays:
1. CORE_ADD: MAIN default, adds TPB_ONE only when past-only paired evidence
   clears the rule below. It never deliberately disables a MAIN member.
2. CORE_SELECT: MAIN default, may choose TPB_ONE or NO_EFF only under that same
   relative-evidence rule. MAIN is always an explicit competing option.

Recompute a decision daily before the session from the PRIOR84 archived sessions.
Compare each candidate's actual independent whole-policy daily cash with MAIN's
same dates. Need>=8 represented calendar weeks,>=10 nonzero paired days,
>=12 completed challenger trades and>=6 completed MAIN trades. Score is mean
paired weekly improvement minus one standard error. Require score>0, positive
total improvement after removing its best improvement day, and trailing closed-
cash fall<=max(1.5*MAIN fall,.05). Rank by score, deterministic TPB_ONE/NO_EFF
tie order. Require the same winning challenger on TWO consecutive archived
decision days before activation. Missing/insufficient/negative evidence returns
MAIN immediately, with no bad warmup strategy. No current/future-day outcome
or unclosed trade label may train the choice. CORE_ADD scores only TPB_ONE;
CORE_SELECT scores both. Reference capital histories differ; scores are proxies
of relative policy merit, never guaranteed incremental live P&L.

Actual intraday routing remains responsive to current completed signals,
daily context and price: preserve MAIN expert order/gates/stretch behavior;
use low-day TPB only when chosen and it signals a put. Do not let alternative
experts preempt a valid MAIN signal merely because a coarse intraday label
changed. CORE_SELECT can omit EFF only on days justified by prior evidence.
No forced liquidation when the chosen profile changes; existing positions keep
their entry strategy's exits and ordinary management/hard flat always runs.
Use N01-F's unavailable state boundary for new selector admissions if a latest
closed bar's END age>=5min; normal management is never stopped by that guard.

## Experiment, acceptance and files

12 fresh reference runs (four/year); exact legacy MAIN/NO_EFF/TPB_FULL economics
must reproduce after canonical member-name normalization. TPB_ONE is a new
bounded-size reference. Freeze daily choices and hashes BEFORE six actual
candidate runs. Preserve full annual cash/adaptive-risk state through every
daily selection; do not add P&L slices or reset brakes. Report displaced/matched
MAIN signal entries and causes, exposure/economic differences explicitly, policy
usage, model training windows/cutoffs, fallback, half-years/best days and drawdown.

Current shipped fees/adverse modeled quotes and extra(200+5*lots)*lots in cash
for all runs. No new indicator/stop/genome grid. This isolates selection design;
trade-payoff/IV features remain a separately frozen later hypothesis if needed.
Source/config/data/daily/memo/settings freeze committed before reference scoring;
daily models committed before candidate scoring. All years seen; no fresh
out-of-sample/profitability qualification, even if chronological choices improve.

Exploratory survivor: positive each year,>=12 trades/year and>=60total,
positive without each year's best day,>=5/6 nonnegative halves, net>=MAIN EACH
year and better aggregate, annual closed-cash fall<=max(1.5*MAIN,.05), paired
weekly t>=2 versus MAIN and two-policy four-week signflip p<=.05 (4096 draws,
seed110201). Also report strongest static TPB_FULL comparison, not just a weak
mix. Zero unresolved/financial/clock/source/memo defects. Every failure stays;
no relaxed pass rule or another offspring after seeing candidate results.

Files: core_policy.py, core_lab.py, analyze_core.py, tests, diagnosis,
configuration/freeze/model manifests/results in this folder. Checks: MAIN
fallback with no labels, matched-date relative score, strict past closure,
future mutation, hysteresis, exact baseline parity, MAIN member priority,
puts-only low additions, scoped lot-cap restoration, initial economic identity,
prices/fees/whole-cash reconciliation and deadline/management continuity.

Rollout/rollback: offline guarded Dev research, three workers in bounded slices.
No application/config/migration/real-order/messaging/Production edits/restarts.
No deployment or money activation from these tests. Stop workers to roll back,
retain results/unrelated work. Update guide/active plan/checklist and atlas with
commits; immediately verify documentation.2023 remains untouched as requested.
