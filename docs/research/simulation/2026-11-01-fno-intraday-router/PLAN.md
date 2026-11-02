# N01: causal intraday strategy switching

Owner request: determine whether switching strategies as the session evolves
can repair the prior breakout's2025 losses and fill main-book weak periods.
The Rs52,663/−113,494 figures were standalone one-lot diagnostic research on
prior dailyADX<30 days, not Production losses. A daily low-ADX gate does not
identify the current intraday state. Earlier O30m routers used daily/09:45
labels; this experiment updates every closed five-minute bar.

## Frozen hypotheses and information contract

Six experts: the four shipped entry functions/exits (SHIPPED, OR20, EFF, TPB),
Donchian g2 (10 bars,1.5ATR stop,3R target,RUN exits), Bollinger g2 (same genes,
mean re-entry). Both new experts evaluate every qualifying closed-bar trigger;
the earlier first-trigger-per-direction-per-day restriction is retained ONLY
in a separate exact old-breakout parity control. This change is explicit:
a strategy unavailable at an early signal can signal again after conditions
change. Duplicate-bar, cash, per-day, expiry, crisis and normal risk gates remain.

Use causal intraday ADX/DMI14 with prior intraday warmup; six-to-twelve current
session bars for efficiency and VWAP crossings, current/prior ATR and prior
dailyADX macro HIGH30/LOW. No full-day highs, future close, final-day label,
smoothed HMM state, fitted-on-all-years classifier or invented news/order flow.
At least six continuous valid bars from09:15; nonfinite/negative volume or
session gaps reset state. A bar with true range>3 times priorATR is SHOCK.
Trend: ADX>=25, efficiency>=.45, DMI direction agrees with recent return and
price is at least .25ATR on the same side of VWAP. Range: efficiency<=.25 and
at least two VWAP crossings, OR ADX<=20 and efficiency<=.35. Else TRANSITION.
Two consecutive raw labels confirm a change; unavailable/shock resets immediately.
Recompute from completed prefixes; prior daily macro uses strictly earlier days.

Three fixed candidates, authorized by the owner's broad mix/genome request:

1. RULE: TREND chooses Donchian first, then TPB/SHIPPED/OR20/EFF; require signal
   direction with observed trend. RANGE chooses Bollinger; TRANSITION TPB.
   SHOCK/UNAVAILABLE admits nothing; existing positions keep being managed.
2. RULE_EXIT: identical entries, plus an ablation of regime-invalidation exits.
   After15min minimum hold, three consecutive contrary/range states invalidate
   a trend entry; a contrary trend invalidates a range entry. Normal management
   and hard-flat run first. Exit only at an actual archived priced observation;
   no guaranteed fill, instantaneous reversal, removed stop or abandoned leg.
3. LEARN: same state inputs, but select experts by prior completed outcomes.
   Monthly as-of models use ONLY the prior252 archived sessions with exits
   strictly before month start. Need30 total past expert trades and12 in the
   state+macro cell. Shrink cell mean toward global expert mean with12 pseudo
   trades; score minus .5 standard-error penalty. Rank positive scores only;
   deterministic expert-order ties, next positive expert if no signal.
   First90 archived sessions use RULE as a declared warmup fallback. Later
   insufficient/negative evidence admits nothing. Report fallback/training
   cutoffs/strategy usage; causal missing cells cannot become profitable rules.

All rules fixed before scoring. Existing named stretch0.5 remains on named
signals, never presumed appropriate for Donchian/Bollinger. No parameter sweep
or offspring after seeing results. State labels are observable proxies, never
a claim to know whether the remainder of the day will be profitable.

## Experiment, attribution and acceptance

Base phase: exact current-main control, exact old low-ADX Donchian control,
six always-eligible one-lot expert books for training, static exact union of
the same six experts. Then freeze/hash monthly models before candidate runs.
Candidate phase: three routers, one-lot diagnostic and actual normal-size
Rs250k shared cash book, over2024/25/Jan–Oct28,2026. Canonical special-session
clock correction12:00 entry/12:25 hard flat remains on March2/May18,2024.
Source/data/daily/memo/settings frozen and committed before base scores;
training artifacts committed before candidate scores. Entire market years
already seen; chronological training is an internal test, not a fresh holdout.
Do not touch/append candidates to the frozen six-book2023 exam.

Costs: current shipped fees/adverse modeled quotes; RAW extraRs200/lot after
replay, Rs300 sensitivity. Exact shared-book extra(200+5*lots)*lots IN its cash
path. Own cash, original risk/brakes/deadlines preserved; never reset an
intraday book on a state change or add independent-arm profit. Fresh250k each
year is not continuous wealth or a15k-account simulation.

Report old breakout losses by causal entry state, direction, exit and clock;
show BOTH profitable/loss-making states and each year's frequency. Explain
that a hindsight day label cannot be used at its open. Compare routers with
main attribution too; additionally show archived full-path direction/range
efficiency>=.5 as an explicitly HINDSIGHT-only shape, never a routing input.
This distinguishes what was observable at entry from what the day later became.
Compare routers with
main AND identical-component static union, actual expert usage, transitions,
switch-exits, fallback, half-years, best-day removal and closed-cash drawdown.
Exploratory survivor: positive every year,>=12 trades/year and>=60total,
>=5/6 nonnegative halves, positive without each year's best day, better than
main AND static union each year, annual closed-cash fall<=max(main*1.5,.05),
paired weekly t>=2 versus each, zero unresolved/memo/economic/clock defects.
All three router outcomes retained; four-week shared signflip sensitivity over
all six candidate books,4096 draws/seed110126, p<=.05. No surviving in-sample
result qualifies live trading. Do not weaken the bar after seeing results.

Files/contracts: regime_policy.py, router_lab.py, analyze_router.py, focused
tests, configuration/freeze/training and results in this folder. Required
checks: all-prefix and future-mutation invariance, state gap/reset/hysteresis,
multiple triggers, as-of label rejection, missing-state fail closed, old/main
parity, per-leg metadata/fee/cash/clock reconciliation, preserved management
and deadlines. Use existing guarded three-worker bounded offline slices.

Rollout: research adapter in Dev only; no application/config/migration/order
authority/Production edits or restarts. Promotion is a separate GitHub and
operator decision after evidence review. Rollback by stopping research
workers, retaining every result and unrelated owner work. Update guide/active
plan/checklist and regenerate atlas with commits; verify each handoff.
