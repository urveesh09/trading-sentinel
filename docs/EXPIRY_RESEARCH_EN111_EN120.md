# EN111-EN120: adaptive actions with a fixed capital contract

2026-11-18 developer proposal. **Not scored or deployed.** Each slot is a
family of permutations, not one attempt. Independent review and measured
receipts: `research/simulation/2026-11-18-expiry-en111/REVIEW10.md`.

The useful round-9 findings remain: nearer affordable contracts, a higher first
target and a modest hold extension. EN87 is still a conditional development
lead; representation stability does not prove a profitable OI edge. Existing
history is all development data. Neither E03.2 nor EN55's registration changes.

Flexibility means choosing an observable, executable action: contract, hold,
bank profit, range reversal or cash. It does not mean forgiving losses when a
model feels confident. Fast deterministic code and a probabilistic model can
coexist; neither guarantees correct predictions or loss-free trading.

| Slot | Family | Policy cells |
|---|---|---:|
| EN111 | Joint contract/target/hold geometry | 18 |
| EN112 | Context changes management, not admission | 18 |
| EN113 | Fast OI innovation during a position | 12 |
| EN114 | Activity clock with a wall-clock ceiling | 18 |
| EN115 | Contract choice by observed response | 12 |
| EN116 | Causal probabilistic market states | 8 |
| EN117 | Cost-qualified range rejection/reclaim | 16 |
| EN118 | Supported net action-value policy | 12 |
| EN119 | Urgency-dependent execution (packet gated) | 12 |
| EN120 | Small stateful controller, one wallet | 12 |

Total **138 cells: 126 bar policies + 12 packet policies**, before named
controls and ablations. Counts are a ceiling, not a target for redundant tests.
Any additional variants/families need a pre-score amendment and remain in the
trial registry. No tuning after new P&L is inspected under the same freeze.

## Shared implementation contract

- Matched round-9 envelope: ₹30,000 own cash; ₹2,500 parent/day full-loss room;
  max3 lots, two buy submissions, two admissions, one open parent. Adds and
  catch-ups consume submissions. Long options only; selling existing inventory
  is an exit. No borrowed money, additional books/top-ups or cross-module funds.
- Preserve ₹1,500/3,000/4,000 drawdown scheduling, 50% profit sweep and the
  non-resetting wallet. Continue shadow observations after a halt if useful,
  but their hypothetical trades never enter funded P&L. Do not restart the
  wallet to reach a later winner.
- Reserve full premium plus buy and worst permitted sell-order fees. Handle
  partials, unresolved exposure, cancellation races and pending exits. A stop
  requests an exit; it does not guarantee that price or eliminate losses.
- Decisions 13:00-14:29. Dated compulsory exits/market close always dominate.
  No auction-era clock copied into a later market-hours regime.
- Completed bars, next executable fill, frozen ordinary/adverse/catastrophe
  assumptions. Minute volume is a capacity proxy, not displayed depth. No
  perfect intrabar barrier sequencing or one-second claims from minute bars.
- Use explicit dependency sets, independently tested for every rule enum.
  Missing OI is not zero. Current SENSEX OI policies remain unavailable.
- New versioned research hooks; reuse existing strategy functions. Hooks off
  reproduce round9. Never edit archived engines/results to bless a new variant.
- Per family show original EN87, matched E03_env and native E03.2 separately.
  Native has a different window/put size/day room. Independent-session totals
  and one continuous wallet are distinct results.
- Contract tests show equal lots, identical causal eligibility and actual
  premium/reserve. Near-one-lot versus far-three-lots is a deployable policy
  comparison; equal-one-lot is the contract mechanism control. Show both.
- Eligibility must be observable before entry. A no-fill/too-expensive case
  remains a policy outcome. Never delete unprofitable new-only clocks after
  seeing results. Matched-parent anatomy is an additional labelled view.

## Phase zero: avoid another inert or unlearnable grid

Before any new family P&L is displayed, expand IDs/dependencies, test synthetic
state reachability, lot rounding and action-ledger duplication. Inspect only
old feature distributions, missingness, activation and action counts; exclude
outcome fields from this stage. Each axis must reach both sides of its rule.
Use extension ranks among comparable impulses instead of a cutoff below every
entry. Verify that short-horizon OI actually updates.

If all cells are identical or never activate, record DUPLICATE / NOT IDENTIFIED.
Permit one documented geometry-only revision before the money freeze; preserve
the original. No threshold revision based on winners or losses. Estimate the
number of independent dates/parents each fit and comparison can actually use.
Many minutes of one parent do not create many independent samples.

Round9's ten-parent/60-expiry selection rule stays frozen. It was poorly matched
to EN87's activity. This proposal separates mechanism anatomy, model training
support and prospective qualification instead of repeating that mistake.

## EN111 - combine the three useful parts

**Base:** unchanged EN87 entry clocks/directions and native hard protection.
Full factorial18: contract `{LEGACY_UP_TO_3, NEARER_ONE_LOT}` × first premium
target `{100%,125%,150%}` × initial time stop `{8,10,12}` minutes from fill.
Nearer uses EN100's nearest affordable chooser, no friction cap and its causal
legacy-one-lot eligibility. All other rules fixed. Targets use liquidation bids.
One-lot inability to half-sell is preserved; native runners keep native handling
and their elapsed hold is reported separately from the initial time-stop value.

Controls: EN87; eighteen equal-one-lot companions; main-factor toggles; no-partial
exit as a named control, not a newly tuned candidate. Higher-target transfer to
E03_env is a sensitivity panel, not independent evidence for OI.

Anatomy: full main/pair interactions; per-parent reserve, fee/order count,
target-request versus fill, giveback and changed re-entry room. Show each
quarter/year, ex-best1/2 and gains reachable before a continuous-wallet halt.
This tests the actual good parts jointly before inventing more signal filters.

## EN112 - let impulse maturity change management

**Base/control:** EN87 entries. Never reject an entry in this family.
Features: round9's `X=d*(F[t]-F[t-15])/ATR10[t]`; its rank among same-direction
E03 events in prior40 covered expiries, min20 prior events; acceleration flag
`d*(F[t]-F[t-3])/3 >= d*(F[t]-F[t-15])/15`. Low extension means rank<=0.5.
No same-day future events in a rank. Missing features use original management.

Grid18: context `{EXTENSION_RANK, ACCELERATION, BOTH}` × assignment
`{FRESH_GETS_ROOM, MATURE_GETS_ROOM}` × profile `{TARGET_ONLY,HOLD_ONLY,BOTH}`.
Fresh = low extension, acceleration or conjunction according to context;
mature is its valid complement. At admission give the specified state target150,
hold12 or both; the other state retains100/8. Freeze this assignment per parent,
so a target cannot move retrospectively. Contract/risk unchanged.

Controls: each fixed profile applied to every entry; reversed state assignment;
random assignment matched to training activation rate; original EN87.
Required lesson: does context predict the *paired benefit of extra room*,
beyond a prior-selected best fixed profile? Predicting hindsight big winners
or relabelling the same state three ways is insufficient.

## EN113 - fast new OI deterioration, not a slow positive window

**Base:** EN87 entries/contract, target100, initial hold12. Compare to this
fixed12 policy and original8. This new baseline does not rewrite EN102.
Compute the existing S numerator/denominator with lag L on the fixed entry
basket. Actual finite endpoints required; unchanged OI is not opposition.
Threshold q is prior20 covered expiries' p-quantile of absolute same-lag
current-ATM S. The training-current-basket versus held-fixed-basket approximation
is disclosed and sensitivity-tested, never hidden.

Grid12: lag `{1,3,5}` × percentile `{80,90}` × response
`{DENY_EXTENSION,EXIT_WITH_GIVEBACK}`. Deterioration = `d*S_L < -q` on two
consecutive completed bars. Deny uses normal8 instead of12 when confirmed at
the eight-minute clock. Giveback exits remaining inventory after confirmation
only if liquidation bid <=90% of the best bid in the previous3 bars.
Hard exits always win. No flips/adds. Missing fast inputs revert to the native8
cap, without blocking earlier protection; pending exits remain queued.

Controls: price-giveback alone; fast-OI alone; fixed8/12; source-lag companion.
Phase zero must establish genuine short-horizon OI updates. Count rescued
losers and cut winners. Fewer than5 changed parents is activation-limited,
not a verdict that all information-responsive exits work or fail.

## EN114 - an activity clock with a hard time ceiling

**Base:** EN87 admissions/target100. Freeze v0 as mean squared futures price
increments over the30 completed increments before decision. Require positive
v0/complete source. Since actual fill accumulate `A=sum(DeltaF^2)/v0`.
One unit is a baseline minute of squared movement, not expected volatility/theta.

Grid18: activity budget `{4,8,12}` × wall ceiling `{8,12,16}` minutes ×
scope `{BASE_ONLY,BASE_AND_RUNNER}`. After min4 wall minutes, request full exit
on activity-budget exhaustion or wall ceiling. Native hard protection wins.
BASE_ONLY leaves the rule after a native runner transition; ALL applies to
remaining lots too. No reset after partial. Missing intervals are not quiet;
fall back to native8. Dated compulsory exit still wins.

Controls: fixed4/8/12/16 with corresponding runner scopes; volatility-ratio
management; original EN87. Match average holding time using training data.
Required lesson: is there state information beyond simply a different average
hold? Report slow winners retained, noisy losers ended and runners cut.

## EN115 - choose contracts by observed price response

**Base:** EN87 same clocks, one lot. Require causal legacy-one-lot eligibility.
Candidates are real quoted affordable long contracts of the needed kind with
EN100 source/capacity checks. Do not fit a rolling-ATM synthetic contract.

Fit causal ridge `Delta3 premium = alpha + beta*Delta3 futures` per contract
using completed trailing data. Normalize x by decision ATR and y by current
premium; unpenalized intercept; convert back to rupee units. Require15 valid
endpoint pairs and nonzero predictor variance. Actual midpoint only with
simultaneous quotes; otherwise label historical close as proxy. Residuals mix
pricing effects; they are not identified theta or implied-volatility shocks.

Grid12: window `{20,40,60}` bars × ridge penalty `{1,10}` × residual penalty
`{0,1}`. Rank by one-lot scenario score:
`lot*(alpha + beta*d*ATR - residual_penalty*MAD_residual) - spread - fees`.
The common one-ATR scenario is NOT expected future drift. Tie-break lower full
reserve then strike/id. No positive-score entry gate. No usable fit -> legacy
one-lot with logged fallback. Scenario/model prices never become fill prices.

Controls: nearest-one-lot; legacy-one-lot; min-friction; constant beta across
contracts; equal-reserve companion where feasible. Show unaffordable/no-fill
cases. Score later response calibration and net lifecycle economics separately.
If regression choices equal NEAREST, reject unnecessary model complexity.

## EN116 - causal probabilistic state, then an action

Earlier price-regime filters failed. This must improve state prediction AND
management beyond a simple control; attractive state names do not count.
Fit a diagonal-Gaussian HMM on prior40 covered expiries, separate daily sequence
boundaries/equal-day weights. Inputs: ER10, signed5-minute move/ATR, RV5/RV30.
Train standardizers/clipping only on past data. No P&L, final-day range,
EOD trend label or future-smoothed state probabilities. Reset daily filter to
fitted initial distribution, then update on completed observations only.

Map high-coherence states as fitted mean ER >= median centroid ER (ties by id);
sum their FILTERED probability pTrend. No claim of identifying dealer inventory.
Degenerate fit/missing warmup -> original EN87, logged as fallback.

Grid8: states `{2,3}` × refit every `{1,5}` covered expiries × persistence
`{IMMEDIATE,TWO_BAR_HYSTERESIS}`. Activate high state at pTrend>=0.6 (two valid
consecutive bars for hysteresis); clear below0.4. At EN87 admission, active
state chooses nearer-one-lot/target150/hold12, otherwise original EN87.
Freeze contract/target. At minute8 allow extra base holding only while state
is active and fee-adjusted liquidation P&L positive. Never widen an old stop.

Controls: fixed high profile; EN87; simple ER10 state matched to training
activation rate; random state mapping registered before scoring. Compare next5
minute movement/coherence forecasts to unconditional prior, plus paired action
benefit. Replay/refit/restart must reproduce exact policy versions/probabilities.

## EN117 - a range rejection that pays for its long option

Independent setup, not looser E03. EN13/32/45 already showed that a range label
or VWAP target alone is inadequate. New question: confirmed failed escape PLUS
enough affordable option response. It may still honestly answer no.

At each minute after13:00 form q10/q90 bands from the30 futures closes BEFORE
the two event bars. Freeze these bands for the event. Require ER30<0.25,
positive width. Prior close below lower-buffer*ATR then current close inside
is a call rejection; mirror is a put. No entry at an unobserved intrabar trough.
First rejection per side/day only; five-minute cooldown; one shared day budget.

Grid16: excursion buffer `{0,0.25}` ATR × target `{MIDPOINT,OPPOSITE_QUARTILE}`
× structural stop buffer `{0.25,0.5}` ATR × scenario cost coverage `{1,2}`.
Opposite quartile is q75 for call/q25 for put of frozen window. Contract nearest
affordable one lot. Use EN115's fixed causal window40/lambda10 response fit to
estimate premium movement to the target, require it > chosen multiple of
spread+buy/sell fees. This is a feasibility scenario, not guaranteed/expected
bounce. No fit -> unavailable, never assume delta=1.

Freeze bands/ATR/target at admission; structural break beyond band+stop buffer
exits; hard premium stop35%, max8-minute hold, target on completed observation
then next executable fill. No runners/adds. Hard dated exits retain priority.
Controls: cost gate off; same clocks opposite/random direction; earlier range
adapter after parity where available; cash. Show profitable rejects too.
Required lesson: does failed escape add predictive value beyond range location,
and can actual contract response cover costs? Do not cure failure with short
options, margin or larger investments.

## EN118 - supported net action values, not direction labels

Earlier fixed-horizon and direction models failed. This learns the value of
actual lifecycle actions including cash; it is not a promise that AI predicts
accurately. Universe: causal E03_env events plus EN117 rejections, deduplicated
by date/clock/event. No automatically loosened E03 event grid.

Actions: CASH; LEGACY_100_8; NEARER_100_8; NEARER_150_12; range only on literal
EN117 default (excursion0.25, midpoint, stop0.5, coverage2) events. Trend actions
only at E03 events. Direction belongs to the event. Label feasible actions by
their full replay lifecycle/fees/no-fill on the same evidence. These are
simulator counterfactuals, not identified treatments or propensity-weighted
estimates of real historical orders.

Fixed features: ER10; prior-E03 extension rank; elapsed session fraction;
one-lot friction/reserve; OI agreement z clipped[-3,3]. No date id, future best
strike/high/regime. Missing OI excludes the OI model on SENSEX; a separately
registered no-OI model must be evaluated independently.

Estimate mean reward and mean loss magnitude normalized by2500. Action score:
`mean_reward - 0.5*mean_loss - k*prediction_instability`. Instability is standard
deviation of estimates from200 fixed-seed expiry-cluster bootstrap fits, NOT
a guaranteed confidence bound. Cash score0. Choose highest positive supported
score; ties lower reserve/fixed id. Predictions do not remove realized losses.

Grid12: learner `{RIDGE,STUMP}` × regularization `{LIGHT,HEAVY}` × k `{0,1,2}`.
Ridge penalties1/10 after normalization. Stump depth1 with minimum20/40 distinct
dates per leaf, equal total date weight. Each action needs >=20 prior distinct
dates with feasible funded examples; training needs >=40 dates overall. Exclude
unsupported actions. None supported -> original EN87 at its own valid event,
else cash. Expose fallback rate; fallback is not evidence for the new policy.

Controls: unconditional action means, fixed profiles, direction-only model,
k0 point estimate, cash, EN87. Report all-cash behavior and specific predicted
winners that lost. Lower forecast error without executable net value fails.

## EN119 - execution depends on urgency (packet gated)

Source gate: >=20 synchronized expiry sessions of eligible option/futures/index
quotes, fresh depth and post-arrival trades. Existing one-day packets test
mechanics only. No download, Production export or new recorder authorized here.
Execution optimization cannot make an adverse signal profitable by definition.

At EN87 events urgency is positive3-second option-mid change divided by median
absolute1-second mid change over prior60 seconds, with same-direction positive
futures progress over those3 seconds. Zero scale/missing updates -> unavailable.
Grid12: wait `{1,3}` seconds × urgency z `{1,2}` × event-ask ceiling
`{1.02,1.04,1.08}`. High urgency buys immediately with capped marketable limit.
Low urgency rests at observed bid, then cancels and catches up once only for
remainder, with favorable futures progress/ask within ceiling. Missing urgency
uses capped immediate entry. No extra submissions or hidden full-size buy.

Cancellation uncertainty keeps quantity reserved. Never submit possible fills
above parent quantity/capital. Costs per actual order/partial; shared two-buy
ceiling. Controls: immediate taker; fixed patience; passive no-fill; strict
post-arrival-trade opportunity; queue-stress proxy; latency0/1/3/10 seconds.
No passive proxy confirms queue fills or supplies a guaranteed lower bound.
No candidate status dependent only on optimistic passive assumptions.

Required lesson: discount versus adverse selection conditional on urgency;
include missed runaways, no-fills, stale data and cancel races. Book depth shows
displayed execution opportunity, not actual broker receipt. Absent source gate
-> SOURCE-GATED, not a minute-bar answer to a second-level question.

## EN120 - interpretable controller, one persistent wallet

Complete adaptive policy, not sum of independent strategies. Literal profiles:
EN87; EN111 nearer-one-lot/target150/hold12; EN117 buffer0.25/midpoint/stop0.5/
coverage2; cash. No hindsight best components substituted after results.
Routing features only ER10 rank, RV5/RV30, one-lot cost/reserve. Estimate past
feasible action values with equal expiry weights/instability as EN118; fit a
shallow tree to maximize risk-buffered action value. Direction/eligibility still
belongs to each setup. An ex-post perfect router is a labelled unattainable
upper-bound diagnostic, never a target used for fitting.

Grid12: tree depth `{1,2}` × refit every `{5,20}` expiries × switching margin
`{0,0.1,0.25}` normalized2500 units. EN118 date/action support required.
At overlapping flat-book opportunities choose one supported profile; uncertain
ties EN87 if valid, else cash. Margin applies to changing profile for new
admissions, never delays exits. Contract/management frozen while inventory
exists; no within-trade strategy switching. No current unobserved labels in fits.

All profiles share actual cash/reserve, pending orders, admission/submission
limits, cooldown, sweep and drawdown history. A bad range trade can block a good
later EN87 trade: charge that opportunity cost (EN09 lesson). Serialize state;
restarts produce identical policy ids, pending orders and trade ids.

Controls: each fixed profile; fixed-priority union; past-P&L-only EN79-style
chooser; zero switching margin. Compare to a best FIXED comparator selected only
on earlier data, under the identical continuous wallet. Show state occupancy,
all-cash/fallbacks, blocked good trades and added complexity/latency. Reference
fallback or cash-only survival is not labelled a smart profitable system.

## Evaluation and evidence rules

### Separate mechanism screens from qualification

All current history is studied. Every fixed cell gets a full calendar and
continuous wallet at all declared fill stresses. Years/quarters/local blocks
are stress descriptions, not restored out-of-sample tests. Repeated searching
of197 dates cannot become new independent evidence through a new split.

EN111-115 mechanism anatomy uses all causal events with paired effects and
changed-parent counts. <5 changed parents -> activation-limited; <20 -> sparse
economic screen. These descriptive labels do not authorize promotion. They
avoid an unachievable ten-in-sixty selection test masking useful explanations.

Learned policies use outer boundaries100/120/140/160/180, last17 dates visible,
and prior-only expanding training. Purge unfinished outcome labels at fit time.
Hyper-selection uses chronological blocks entirely inside training. Insufficient
dates/actions -> no fit for that action. Never use IID minute labels, shuffled
dates or future-smoothed state. EN116 unsupervised state fitting and monetary
action fitting have different support requirements.

Predeclare ranking: median inner-block paired adverse net/scheduled expiry,
no wallet halt, simpler fixed-profile tie. Sparse folds take registered fallback.
Do not grow a window until a preferred variant becomes profitable; the expanding
window uses ALL prior dates by rule. Stitch outer policies into one30k wallet
from date100; also show full-calendar fixed wallets from date0. Never reset each
outer block. Compare same-date reference wallets.

### Prospective registration is separate

At most two new fixed policies or fully frozen learning procedures may be
nominated for new paper observation. A nomination is not profitability proof.
Existing EN55 registration stays unchanged. Learning update cadence, sources,
normalization and state serialization are part of the frozen policy.

Preflight activity/power using expiry-cluster simulations with skew, dependence,
missed fills and changing regimes. Old nominal tests over-rejected; do not reuse
them for significance. If no acceptable calibrated method, report descriptive
screens without a significance claim. Do not lower standards to create a winner.

Draft future support: >=40 covered expiries/index, >=20 funded parents, enough
changed parents for the paired question. EN87 pace implies ~158 expiries for20
parents; a100-expiry cap likely ends INCONCLUSIVE. Choose feasible duration,
stopping rules and endpoint BEFORE any future result; one final review, no
optional-stopping promotion. Prospective alpha/multiplicity covers actual
policies/index endpoints and the entire fitted search procedure.

Primary: paired adverse net/scheduled covered expiry versus frozen comparator;
also positive absolute adverse wallet, no halt/risk violation, best-day
concentration and recent-period stability. Missing dates remain missing and
limit exact continuity. Direction accuracy alone cannot qualify an option policy.

Unexamined2020-22 history may provide an older-regime transport test only after
authorized acquisition, OI/source capability checks and proof it was untouched.
Disclose dated fee/lot/calendar differences. It cannot verify current live fills.
No acquisition or capital increase authorized/performed by this proposal.

## Required developer artifacts and acceptance

Preserve proposal/review in the round10 folder. Write IMPL10 exact formulas,
source dependencies, activation/support check, folds, rollout/rollback before
implementation score. Expand every cell/control/ablation/revision in a machine
manifest and trials ledger. Freeze code/data/settings/calendar/environment.
Never edit prior freezes/results. All new outputs get distinct paths.

ANATOMY10 and COMPONENTS10 must show each family's good/bad/removal/interactions,
plateau/duplicates, full and matched supports, inactive/missing/fallback paths.
Every financial row: gross, spread/slippage, buy/sell fees/order counts, net,
premium at risk, actual exits versus assumed/unresolved values, ex-best1/2,
losing dates, continuous cash/sweep/brakes and recent performance.

Acceptance: independent source-gate enum tests; hooks-off parity; causal prefixes
for features/models/actions/refits; whole-lot reserve invariants; no depth reuse;
exit retries/cancel races; restart equality; fresh-process samples from every
family and every learned boundary. Hash integrity, ledger identity and economic
validity are separate. Record real exit codes/test limits/commit/push/deploy state.
Regenerate atlas if its covered runtime source changes. Normal F&O/Production
remain untouched; any eventual release uses the normal GitHub promotion path.

## Research basis

Source notes: `research/simulation/2026-11-18-expiry-en111/SOURCES10.md`.
[Garleanu/Pedersen](https://w4.stern.nyu.edu/facdir/lpederse/papers/DynamicTrading.pdf)
connects signal persistence, changing targets and costs, motivating action control.
[Adams/MacKay](https://arxiv.org/abs/0710.3742) motivates causal state-change
inference; our HMM is a different simpler model, not their algorithm or proof.
[Gibbs/Candes](https://www.jmlr.org/papers/v25/22-1218.html) motivates monitoring
changing forecast uncertainty; coverage is not profitable selected actions.
[Lehalle/Mounjid](https://arxiv.org/abs/1610.00261) explains limit-order adverse
selection/latency. [Foster et al.](https://proceedings.mlr.press/v178/foster22a.html)
and [Sachdeva et al.](https://arxiv.org/abs/2006.09438) explain policy-learning
support limits. [Cawley/Talbot](https://www.jmlr.org/papers/v11/cawley10a.html)
explains overfitting selection itself. None proves an Indian expiry trading edge.
[OIC gamma](https://www.optionseducation.org/advancedconcepts/gamma) and
[theta](https://www.optionseducation.org/advancedconcepts/theta) explain response
and time erosion, not future price guarantees.

Priority: independent capability/reporting fixes, then EN111. Preflight EN112-118
before fitting complexity. Keep EN119 packet-gated. EN120 runs only after literal
components and shared-wallet mechanics pass. Success is a supported improvement
or a sharp honest lesson, not a required spectacular historical equity curve.
