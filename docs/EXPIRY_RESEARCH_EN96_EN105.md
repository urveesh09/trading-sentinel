# EN96-EN105: expiry strategy families, not single attempts

Status: DEVELOPER PROPOSAL ONLY, 2026-11-18. No new strategy has been run,
qualified, promoted or deployed by this proposal. Dev base: cceabe62; prior
implementation freeze a5115893. The owner's latest instruction changes the
unit of development: **one EN slot is a strategy family, with multiple declared
variations, parameter checks, ablations and a component-level explanation.**

Read this document first, then
`research/simulation/2026-11-18-expiry-en86/LESSONS8.md`, `ANATOMY8.md` and the
machine evidence there. Family inventory and counts are in
`research/simulation/2026-11-18-expiry-en96/families9.json`; execution plan and
research status are in `PLAN9.md` and `STATUS9.md` beside it. Sources and the
limits of transferring their results to Indian index expiry are in `SOURCES9.md`.

## 1. What the new instruction changes

Do not reject a whole mechanism because one threshold failed. Within each
family, test the registered grid, separate the useful component from the harmful
one, inspect neighboring settings and explain how the entire trader changes.
Keep every failed, unavailable, identical and under-supported variant in the
ledger. A family can finish with a useful mechanism but no fundable strategy.

This explicitly supersedes the old one-version-per-slot approach **for new
development searches only**. It also authorizes more development variants than
the generic two-candidate limit in `docs/RESEARCH_TESTING_METHOD.md`. Do not
rewrite earlier freezes, results, qualifications or EN55's forward registration.
Do not tune on a forward comparison. Freeze the complete search procedure and
grid before running it; selecting inside the declared development folds is part
of that procedure. An additional idea after results is a new registered revision,
with its trial count retained, rather than a hidden retry of the same result.

There are **219 bar-policy configurations plus 12 packet-execution configurations
= 231 declared configurations**, before controls and execution sensitivities.
These are ceilings before canonical deduplication, not 231 independent discoveries.
EN105's 64 configurations are combinations of training-selected components;
their selection work and component trials must also remain visible.

Thorough means answering the question over a defined, economically sensible
range. It cannot mean proving that every imaginable version of a family fails
forever. Nor does a broad search turn already studied history into fresh evidence.

## 2. The evidence we should build on

These are the archived round-8 results, not new scores:

| Finding | What to retain | What to avoid carrying forward |
|---|---|---|
| EN87: matched E03 timing plus agreeing OI | NIFTY ordinary +6,114.14 versus matched E03 +3,006.43; adverse +5,840.68; without best two days +2,644.90; continuous wallet +5,305.89 | Only 25 parents over 197 expiries; 2026 -2,451.29; paired interval includes zero. No proven replacement. |
| EN87's excluded parents | 30 excluded parents net -2,601.10; information can improve a timing policy | They include 13 winners. This is selective participation, not perfect identification of losing trades. |
| EN88 residual OI | Conditional analysis can ask whether OI adds anything beyond price | Its residual-crossing entries added 213 parents losing -12,380.95. More crossings are not more edge. |
| EN89 reclaim | Better than a plain delay control | Still loses. It misses runaways and buys failed recoveries. |
| EN90 OI decomposition | Separate contraction and growth with an exact accounting identity | Neither component identifies who opened a short. A new clock can overwhelm a useful same-clock signal. |
| EN91 24-minute hold | On 158 shared parents, longer holds added +17,828.03 | Continuous wallet halts in 2024; 2026 -10,659.84. Large independent-day totals are inaccessible after ruin. |
| EN92 contract selection | +963.85 on 159 common clocks versus the old one-lot chooser | 34 new admissions lost -2,244.75. Contract choice, affordability and admission must be separated. |
| EN94 information exit | Some genuine loss reductions | It cut -3,409.19 from one large winner; net common-parent damage -1,278.03. Information reversal can be noise. |
| EN95 combination | Ablations can show whether a component is active | Removing its information exit changed nothing. More rules can be inactive or harmful. |
| EN55/patient orders | Scout sizing can protect a path; execution timing matters | Resting-bid fills are modeled, not confirmed; adverse selection can reverse the benefit. |

The working hypothesis is **conditional information + affordable execution +
selective continuation**, rather than a new indicator on every market minute.
It is a research hypothesis. Research on option flow uses information we often
do not have, including signed opening transactions. Aggregate OI is a count of
open contracts with a long and a short side, not identified seller pressure.
[OIC](https://www.optionseducation.org/referencelibrary/faq/general-information),
[Pan and Poteshman](https://www.mit.edu/~junpan/volume.pdf).

## 3. Shared contracts for every family

### Baselines, money and source fidelity

1. Keep immutable E032_native, EN55_native, E03_env, EN87 and EN83/raw controls.
   The primary policy comparison is **EN87 and E03_env under identical money,
   dates and execution assumptions**. Native policies are context, not fair
   substitutes for the matched comparison. For sizing/chooser changes, include
   an otherwise identical one-lot/reference-reservation control.
2. Use the round-8 symmetric envelope: own-cash long options only; INR30,000
   starting wallet; INR2,500 cumulative parent and day worst-case premium/fee
   envelope; at most three lots, two parent submissions, one open position.
   All buy submissions, including an add or passive catch-up, count toward the
   two-buy-submission daily ceiling; an unfilled submission still consumes one.
   Thus a two-order staged parent leaves no third buy for another parent.
   No short legs, borrowing, top-ups or funding from another book. Preserve the
   existing INR1,500/3,000/4,000 drawdown sizing/halt schedule and the registered
   50% cumulative-positive-profit sweep. Do not reset a halt weekly or annually.
   Retain the original reference arm with its own frozen risk semantics too.
   Any stricter universal reservation fix needs a named matched control and an
   explicit erratum; never silently change an archived baseline.
3. Every new order reserves full possible premium loss, buy charges and the
   maximum permitted number of exit-order fees. Count repeated purchases and
   partial sales. A favorable mark is not cash for an add. Stopping faster is
   never used to make an unaffordable lot fit. Unfilled exits remain exposed.
4. All variant decisions remain 13:00-14:29 IST unless the specific rule says
   otherwise. No slot expands into the untested late window. Native stops,
   target/runner behavior and dated compulsory exits remain unless named as
   the component under study. Read dated calendars/contracts; do not infer an
   expiry from a weekday or a series occurring in a download.
5. Historical primary fidelity remains BAR_LIFECYCLE: completed inputs, next
   executable bar, declared synthetic spreads and capacity, pessimistic
   same-bar ordering. It cannot answer whether a one-second execution wins.
   Packet variants need receive clocks, fresh bid/ask depth, post-arrival trades
   and conserved displayed/traded capacity. Queue position remains unknown.
6. NIFTY has studied minute OI. SENSEX OI is unavailable in the current panel:
   OI-dependent SENSEX cells must be DATA UNAVAILABLE with null money. Do not
   fill them with zero, forward-fill unavailable OI, infer OI from volume, or
   transfer a NIFTY calibration as if SENSEX had been validated.

### Common notation and mechanics

- `d` = +1 call / -1 put; `F_t` = completed futures close; `A_e` = the existing
  completed ATR value at the arming/entry decision. Freeze its exact lookback
  and implementation in the manifest. Invalid ATR means abstain, not zero.
- For an identical set of paired strikes at both endpoints:
  `S_L(t) = sum[(C_(t-L)-C_t)+(P_t-P_(t-L))] / sum[C_(t-L)+P_(t-L)]`.
  This is the round-8 `U+D` identity, with L minutes. Missing endpoints are
  unavailable; zero is valid only for an OI-capable source. Log each basket.
- `q(L,p,H)` is the p-th percentile of `abs(S_L)` from the prior H covered
  expiry afternoons, never the current day's later observations. Default
  L=15, p=80, H=20 reproduces EN87. Use the archived pooled-minute estimator
  for this reference; disclose its unequal-day weighting. At least 200 valid
  observations and all H prior covered dates are required. Do not opportunistically
  shorten warmup for a sparse candidate. Report common-warmup and available-history
  comparisons separately.
- `ER10 = abs(F_t-F_(t-10)) / sum(abs(diff(F_(t-10:t))))`, with zero denominator
  unavailable. This proposed efficiency measure is a feature, not an established
  expiry predictor. All extra features must pass future-prefix erasure tests.
- Exit priority: dated compulsory/risk/native protective exits first, then
  candidate information exit, then the native time exit unless explicitly
  extended. Pending sells block new buys/adds. No same-observation sell twice.
- Every armed event has a stable parent ID. No duplicate repeated signals,
  simultaneous opposing positions or unlimited retries. Actual fill time starts
  the holding clock. Restart state includes arms, expiry, maxima, confirmations,
  reservations and consumed-liquidity keys.

## 4. The ten families

### EN96 - Find the useful OI agreement range

**Question:** Is EN87 a robust agreement effect or an isolated 15-minute/q80
setting? Can moderate agreement recover activity without admitting the losing
raw-OI clock?

**Base:** the unchanged E03_env signal clock/direction, chooser and exits. Gate
each signal by `d*S_L > q(L,p,H)`. No independent OI entry and no reversal.

**Grid (32):** L in {5,10,15,30}; p in {60,70,80,90}; H in {20,40}. Recalibrate
each candidate using only its own prior valid observations. The (15,80,20) cell
must reproduce EN87 exactly. Common-40-date warmup is a compulsory companion
comparison, so a longer calibration is not punished simply for missing earlier
profitable or losing dates.

**Controls and explanation:** no OI gate; sign-only agreement; raw crossings;
unrelated historical-day OI with a predeclared mapping; activity-matched random
retention of E03 parents, sampled by expiry/time bin from training participation
rates. Use fixed seeds and preserve clustering. Match retention counts per
eligible bin where possible; mark bins without a valid match. These controls
cannot prove causality but distinguish selective participation from unusual timing.

**Deliver:** full heatmaps, trade-count frontier, adjacent-grid stability, annual
and chronological-fold contributions, newest-period losses, retention of large
winners and exclusion of losing parents. A stable moderate band is more useful
than one very profitable corner with five trades. Report if every less-strict
neighbor adds negative marginal expectancy. No calendar-year-specific threshold.

### EN97 - Make OI agreement survive changes in basket composition

**Question:** Does the signal reflect broad information, or a single strike and
the movement of the ATM basket? Test representation before calling it a mechanism.

**Grid (18):** basket half-width {1,2,3} strike steps; anchor {current ATM,
ATM at t-15, frozen 13:00 ATM}; aggregation {pooled S, median leave-one-pair-out S}.
Keep EN87's L15/p80/H20 gate on E03 clocks. Each representation gets its own
causal threshold. The full width-2/current/pooled cell must equal EN87.

Use the **same contract IDs** at both endpoints of each calculation. For pooled
S require at least `max(2,ceil(0.6 * planned_pairs))` valid pairs. For jackknife
S require at least three valid pairs before dropping one, then calculate S on
each leave-one-out basket and take their median. If the required centered
basket cannot exist in the source catalogue, mark that observation unavailable;
do not silently use a narrower basket. Frozen-13:00 anchors are unavailable
before that time. Apply identical rules during historical threshold construction.

**Controls:** fixed-basket versus moving-basket matched clocks; leave out the
eventual traded pair as a diagnostic only, with no new threshold optimization;
one-minute-lagged OI on packet-valid/source-valid observations. Track valid-pair
coverage, denominator size, fraction of OI change attributable to the largest
pair and ATM-boundary changes. A leave-traded-pair diagnostic must not select
the traded pair using future profitability.

**Deliver:** whether agreement survives the jackknife and nonmoving baskets;
whether improved P&L is just fewer available observations. Keep source failure
separate from weak information. This family can produce a better estimator,
but wider/more stable does not automatically mean more profitable.

### EN98 - Keep information, stop paying after excessive price extension

**Question:** Can an observable entry-state interaction reduce late chasing
without discarding all fast trends? This salvages context analysis from EN88
without trading its losing residual crossings.

**Base:** original EN87 gate, clock, chooser, sizing, eight-minute management.
Define signed extension `X=d*(F_t-F_(t-15))/A_t`.

**Grid (12):** maximum X in {0.5,1.0,2.0,unbounded}; minimum ER10 in
{0,0.25,0.50}. Require X <= chosen maximum and ER10 >= minimum. The
unbounded/zero cell equals EN87 on valid common-feature observations; separately
retain exact EN87 without the extra-feature availability requirement.

**Controls:** extension-only, efficiency-only, both, no context; sign-reversed
extension interaction as a diagnostic, explicitly counted if traded/scored.
Never remove a whole year or use the later intraday high to define extension.

**Deliver:** per-parent marginal additions/removals, lost runaways, damage
avoided, cash-versus-option move decomposition, and common-feature versus full
coverage. If ER simply selects fewer signals without better payoffs at matched
clocks, report it. A 2026 repair with severe damage to other periods is not robust.

### EN99 - Enter a valid signal efficiently without assuming patient fills

**Question:** Once timing and information agree, when does waiting improve
the actual opportunity instead of selecting falling options?

**Bar block (17):** start only from EN87-qualified events. Freeze d, A_e,
chosen contract, event ask and parent ID at arming. Variant definitions:

- Immediate entry: one reference configuration.
- Confirmation: TTL {1,3} minutes x favorable futures progress {0.10,0.25} A_e
  x ask ceiling {1.04,1.08} times event ask = eight.
- Pullback/reclaim: TTL {3,5} minutes x pullback depth {0.25,0.50} A_e x the
  same two ask ceilings = eight. Measure pullback from the favorable running
  futures extreme since arming. After reaching it, require a completed close
  beyond the preceding candle's high (long) or low (put direction).

In both delayed styles require original OI agreement still above q, before
14:30; missing data disarms rather than fabricating consecutive confirmation.
The first qualifying decision submits once. Use a marketable capped limit,
next-bar price/depth assumptions and whole lots; a limit below the next ask is
unfilled, not a favorable synthetic fill. Expiry of an arm consumes no premium
but its missed opportunity remains in the report. At most one active arm.

**Packet block (12, separate, source-gated):** wait {0,1,3,10} seconds and cap
catch-up at {1.00,1.02,1.04} times event ask. Zero wait submits a capped
marketable order. Positive wait posts one bid, cancels any remainder at TTL,
then attempts at most one capped marketable remainder. Allocate distinct buy
fees and preserve original day/parent reserve across both attempts. Model
cancel/ack races and prevent duplicate remainder purchases.

Use the same trigger events and a conservative passive-fill envelope: no fill,
strict post-arrival trade/capacity proxy, and separately quote-opportunity proxy.
None is a confirmed queue fill or a guaranteed lower bound. Include observed
latency stresses {0,1,3,10} seconds; minute bars cannot score these cells. One
recorded expiry is a pilot, not qualification. Require >=20 synchronized covered
packet expiries before estimating cross-day behavior; record support even then.

**Controls/deliver:** plain deterministic delay, immediate capped taker, missed
runaway markouts, post-fill adverse markouts, fills conditional on later price
direction, cancellation failures and full fee-adjusted parent P&L. A cheaper
filled subset alone is not improvement. Research explains why resting liquidity
can attract adverse fills and why execution timing can matter; it does not
establish our fill rates. [Lehalle/Mounjid](https://arxiv.org/abs/1610.00261),
[Muravyev/Pearson](https://www.cicfconf.org/sites/default/files/paper_745.pdf).

### EN100 - Improve the contract without smuggling in different admissions

**Question:** EN92 helped common opportunities but lost on added admissions.
Can a causal reference-eligibility condition retain the useful contract choice?

**Grid (9):** chooser {legacy, nearest-ATM-affordable, minimum round-trip
friction/reserve}; maximum estimated friction/reserve {0.05,0.10,unbounded}.
Use original EN87 clocks and **one lot for all cells and controls**. Full
premium/charges must fit current day/cash room before ranking. Friction is the
current ask-minus-bid plus actual buy/sell fees, divided by full loss reserve,
not a theoretical option price. Tie-break by distance to ATM, then strike,
then stable instrument ID. Current historical spreads remain declared proxies.

**Admission rule:** first run the unchanged legacy chooser's one-lot eligibility
test at the current clock/cash. If it cannot fund a legacy entry, no candidate
may enter. Only then choose among affordable current contracts. This observable
condition is implementable; deleting the hindsight cohort called 'new-only'
would not be. Retain an explicit unrestricted EN92-style companion control to
measure what the admission condition costs.

**Deliver:** exact same-signal/decision comparisons at equal lots; executable
friction, contract distance, sensitivity to one extra price step, volume/depth
capacity, native stop/target timing and equal-reserve sensitivity. Check whether
a closer strike improves repeatable payoff or merely sacrifices the rare tail.
Do not claim a contract is efficient from a lower premium or higher delta alone.

### EN101 - Earn the right to hold beyond eight minutes

**Question:** Can we retain EN91's continuation gains while avoiding holding
every weak ticket for 24 minutes?

**Grid (18):** maximum holding cap {12,16,24} minutes x continuation evidence
{information,price,both} x activation net gain {0,0.20} of original parent reserve.
Entry is unchanged EN87. Native protective and compulsory exits still win.

At the first completed decision at/after eight minutes from actual fill, extend
only if fee-adjusted liquidation P&L exceeds the activation gain and the
chosen evidence holds. Information: fixed-entry-basket `d*S15 > 0.5*q_entry`.
Price: `d*(F_t-F_(t-3)) > 0` and no break beyond the previous three completed
bars' adverse extreme (exclude the current bar when computing the extreme).
Both requires both. Invalid inputs deny extension. Freeze q_entry and basket
IDs; do not reset the hold clock on a partial sale.

During extension check permission each completed minute; two consecutive
permission failures request sale of remaining lots. A missing observation breaks
permission continuity and requests exit; it never renews a hold. The chosen cap
is absolute, not repeated extensions by another 12/16/24 minutes. Retain native
runner/partial-profit rules; applying the new time cap to a residual runner
must be explicit in the state machine and matched controls.

**Controls:** fixed eight minutes, fixed 12/16/24 minutes, and an equal-activity
training-rate extension control. **Deliver:** incremental loss exposure after
minute eight, positive-tail retained, giveback, partial-lot feasibility and the
continuous wallet's actual ability to reach later winners. Any halted wallet
fails the survival screen, however attractive its independent-day total.
Signal persistence versus costs is the economic motivation, not proof of this
permission rule. [Garleanu/Pedersen](https://w4.stern.nyu.edu/facdir/lpederse/papers/DynamicTrading.pdf).

### EN102 - Exit when information and damage agree, not at every flicker

**Question:** Can EN94's loser protection be separated from its premature
runner sales?

**Grid (18):** opposing OI threshold k in {0,0.5} x consecutive observations
{1,2,3} x damage requirement {none,entry damage,structure damage}.
Original EN87 entries and native eight-minute management. OI opposition means
fixed-entry-basket `d*S15 < -k*q_entry`.

- None: OI alone, to expose the noise cost.
- Entry damage: additionally `d*(F_t-F_entry_decision) < -0.25*A_entry`.
- Structure damage: additionally a completed close beyond the adverse extreme
  of the previous three completed futures bars.

Require the complete chosen conjunction on each consecutive valid observation;
missing data resets the confirmation count. This exit cannot bypass native
protective exits, postpone them, or automatically flip the position. It cannot
sell the same remaining lot twice after a restart.

**Controls/deliver:** EN94's exact raw-entry rule, OI-only, damage-only and native
exits. Attribute loss saved and winner profit removed separately. Show whether
damage confirmation actually delays harmful exits on the September 2024 type
of runner, without designing a one-date exemption. Report first exit request,
actual fill and unresolved gap exposure. Do not call a stop a locked profit.

### EN103 - Preserve the scout's protection without starving slow winners

**Question:** EN55's path survival came partly from buying less initially.
Can confirmation-based additions improve the loss/payoff trade-off at real lot
and fee granularity?

**Grid (13):** full size reference (one); initial fraction {one-third,one-half}
x option liquidation-bid gain {10%,20%,30%} x OI requirement {still qualified,
at least entry strength} = twelve staged cells. Entry is original EN87; exits
unchanged. 'Entry strength' is d*S15 measured on the fixed entry basket, with
its logged q and coverage. The second OI requirement is no weaker than continued
qualification. No add on a pending exit or at/after 14:30.

Compute intended lots from a worst-case episode reserve **including a second
buy fee and higher add price**. For staged cells, add limit is at most 1.40
times original entry ask and must also fit current cash, episode and daily
remaining commitment. The trigger is a bid gain, not a candle high. Add only
once after a completed signal; execute at the next permitted quote/bar under
that limit. Total premium purchased plus all worst-case fees across the entire
episode must stay within its original INR2,500 cap even if the first tranche
later becomes worthless. Do not recycle unrealized gains or sold premium into
an unbounded sequence of tickets.

Round initial lots down, with a one-lot minimum only when one lot fits. A
one-lot intended trade has no staged split: record equivalent behavior. Never
increase budget to manufacture two lots. Include full-entry controls both at
the same conservative planned-lot count and at native sizing, separating the
cost of add-fee reservation from the effect of waiting to add.

**Deliver:** planned/filled/added lots, slow-winner profits foregone, losses
saved, additions just before reversal, impossible/deduplicated cells and wallet
survival. A sizing family can be a useful risk improvement even if it earns
less; it cannot be described as an entry forecast improvement.

### EN104 - Recover timing signals whose information arrives shortly later

**Question:** EN87 is sparse. Is some of that a synchronization problem rather
than an absence of good E03 setups? Increase opportunity by waiting for missing
agreement, instead of letting raw OI create arbitrary new entries.

**Grid (18):** arm TTL {1,3,5} minutes x required later direction validity
{E03 still signals same side,price structure holds} x delayed OI quantile
{70,80,90}, always calibrated from prior 20 covered expiries.

**Core remains EN87 at q80.** Only an E03 signal with valid observed OI that
fails the immediate agreement gate may create a delayed arm. Source-unavailable
or warmup-missing signals cannot become arms. Freeze its direction, A_e,
contract and event ask. A later completed observation may enter if it first
meets the candidate quantile and its chosen validity condition. Structure holds
means no completed close beyond the adverse extreme of the three futures bars
preceding the original E03 event. At submission retain an event-ask ceiling of
1.08, current affordability and all original gates except the intentionally
replaced instantaneous OI coincidence. E03-still-signals means recomputing its
actual evaluator at that minute, not remembering the prior direction.

No lookahead search for the most profitable confirmation minute. Earliest valid
confirmation wins. Missing required inputs, opposite E03 signal, invalidated
structure or 14:30 cancels an arm. At a same-clock conflict an immediate EN87
entry has priority and cancels the arm. One active arm, one open parent, two
submissions and the **same INR2,500 total day cap** for core plus delayed entries.
No extra funded book or hidden extra loss budget. TTL expiry itself is not a buy.

**Controls/deliver:** EN87 alone, unconditional delayed E03 at the same TTL,
and EN83/raw clocks. Report new parent money, core parents blocked or resized,
late confirmation costs and admission counts. More activity qualifies as useful
only if the complete shared-capital path improves, not just the added tickets.

### EN105 - A finite, auditable component search with honest inheritance

**Question:** Does combining robust parts improve the whole trader, and which
interactions destroy benefits that looked good individually?

This is a controlled version of the owner's evolutionary idea. It is **not**
unlimited mutations scored until a pretty backtest appears.

**Grid (64):** six binary genes:

1. Information representation/threshold: EN87 reference versus one selected
   training-only policy from the union of EN96 and EN97.
2. Context: none versus the training-selected EN98 rule.
3. Entry: immediate versus the training-selected EN99 **bar** rule.
4. Contract: legacy one-lot versus the training-selected EN100 one-lot rule.
5. Management: native versus one training-selected rule from EN101/EN102.
6. Size: full versus the training-selected EN103 staged rule.

Choose components anew using only the inner history for each outer fold. Never
substitute the champion found from the full historical score into an earlier
fold. The combined rule must recompute thresholds for the chosen representation;
its context and entry tests consume that representation's information. All
management uses the actual combined entry, basket and fill, not the component's
standalone parent ledger. Choosing between extension and damage exit permits
one management mechanism, not an undeclared simultaneous exit optimization.

All 64 genotypes share the original **maximum-three-lot** sizing and money
envelope. The contract gene inherits the selected EN100 ranking/friction rule,
then the shared sizing routine determines affordable whole lots; it does not
inherit EN100's standalone one-lot experiment limit. This is an explicit
integration change, tested here rather than claimed from EN100's result.
Include an equal-one-lot control panel for all genotypes to distinguish chooser
benefit from induced sizing. With only one affordable intended lot, the scout
gene is behaviorally inactive: log and deduplicate, never invent fractional lots.

EN104 remains a separate activity challenger in this round. Its new parent
clock and shared-budget interaction need their own evidence before joining an
even larger combination search. Packet execution is also excluded until its
source gate is met. If any required component lacks support, that gene resolves
to its reference; log why.

**Controls/deliver:** all single-gene ablations and pair interactions, not just
the highest-P&L genotype. Report marginal changes conditional on other genes,
inactive/identical components, fee/lot effects, support loss and continuous-wallet
failures. A simpler cell on a stable neighborhood wins a tie. If combinations
lose despite good standalone pieces, identify changed clocks, sizing, exits or
budget competition explicitly. [Novy-Marx](https://www.nber.org/system/files/working_papers/w21329/w21329.pdf)
explains why combining selected signals greatly increases selection bias.

## 5. Selection, search and evidence rules

### Stage A: mechanics and a complete registered search

Before printing new candidate money, expand the manifest to stable variant IDs,
derive exact rules (including all controls), bind input hashes, and commit the
freeze. The reference cases above must reproduce the archived controls at
parent, order, fee, rejected-entry and daily-wallet levels. Keep both the initial
configuration count and behavior-deduplicated count. Degenerate or unavailable
configurations are a finding, not grounds to replace them with a secret extra try.

Minute-data grids can be run now as development. EN99 packet variants cannot be
evaluated as if 197 minute histories contained depth. SENSEX absence remains
visible. New acquisition or recorder deployment follows its separate approved
workflow; this proposal authorizes neither orders nor a Production change.

### Stage B: chronological development evaluation

All existing 2023-2026 expiry data have been studied. The following is a useful
selection stress test, **not restored out-of-sample validation**:

- Sort the complete independently verified expiry calendar, preserving missing
  dates. First 100 scheduled NIFTY expiry dates form initial development history.
  Advance in 20-expiry outer blocks; include a final partial block and label its
  length. Missing source observations remain missing, never zero-trade days.
- At each outer boundary, inner validation blocks are the last 60 dates of that
  100-date prior window, split into three consecutive 20-date blocks. Earlier
  data supply warmup; indicators never read later dates. Fit a component's
  thresholds on prior covered dates only. Do not randomly split intraday bars.
- Select within that historical inner window. Require at least ten funded
  parents pooled and activity in at least two inner blocks for a nonreference
  choice. Lower support remains INCONCLUSIVE, not FAIL or an invitation to
  lower the requirement. Controls with different source coverage compare only
  on declared common support, with excluded dates also reported.
- Selection uses continuous wallets for the whole inner evaluation path (one
  start, no resets between the three blocks). Require full exposure/fee
  reconciliation, no risk violation, no halt, ordinary and adverse wallet net
  positive, nonnegative independent-session net after removing the best two
  expiries, and a nonnegative median across the three blocks for paired adverse
  per-expiry improvement over matched EN87. Report constraints that reject every
  candidate. Cash/reference fallback is allowed and is not a successful strategy.
- Rank remaining cells by median inner-block paired adverse net per scheduled
  expiry on common complete support. Tie-break by lower liquidation drawdown,
  fewer modified components, then stable variant ID. Report net per calendar
  expiry and capital time, not just per trade. This objective/ranking must be
  executable from the manifest before any scoring.
- Apply the selected policy unchanged over the next outer block. For the
  stitched selected-policy wallet, start once at INR30,000 at the first outer
  scored date, retain cash/sweeps/brakes across blocks and changes of policy,
  and stop when its brake says so. Matched baselines start there too. In
  parallel show full-calendar fixed-variant wallets from the original start
  date; these answer different questions and must not be merged.
- Missing days prevent an exact continuous-wallet claim through those gaps.
  Report a conditional no-trading-on-missing path and full-loss stress for any
  open unresolved exposure. A whole-missing session is not magically a known
  flat account. Never restart after a halt to access later winners.

Thresholds, timing delays and alternative parent clocks all count as searched
choices. Include pre-study selection of EN87 and prior 85+ ideas in the narrative;
the current grid's finite trial count does not erase earlier adaptive search.

### Stage C: choose a stable development candidate

Publish the entire grid and parameter-neighbor results. In a numeric grid,
neighbors differ by one adjacent setting on one axis; categorical branch changes
are separate ablations. A 'plateau' report must include all such neighbors,
support and costs, including unavailable/failed ones. An isolated peak is a
warning, not automatically a winner. Do not smooth P&L using future dates.

Use round-8 calibrated long-calendar-group uncertainty as a descriptive
comparison, retaining its dependence/stationarity assumptions. Within a family
the chosen maximum is selected: do not apply an unadjusted p-value to it.
If reporting formal search p-values, impose a specified null, resample whole
calendar blocks jointly across all arms, and rerun the **entire component and
genotype selection** in each replicate. Calibrate the procedure's size and
power with skewed/heavy-tail/dependent nulls before interpreting it. If that
calibration is not implemented, report descriptive uncertainty and no new
significance claim. Deflated Sharpe may be supplementary, never the sole
criterion for sparse skewed trades. [Bailey/Lopez de Prado](https://davidhbailey.com/dhbpapers/deflated-sharpe.pdf),
[Cawley/Talbot](https://www.jmlr.org/beta/papers/v11/cawley10a.html).

### Stage D: genuinely new forward data

Nominate **at most two new champions in total**, not two per family: preferably
one profit/continuation candidate and one risk/entry-efficiency candidate.
Retain unchanged EN87, E03_env and native context benchmarks. Freeze source,
settings, data gates, calendar, alpha allocation, support requirements and
review horizon before the first new session. Existing EN55 registration remains
untouched. New sessions used to pick a champion are development data for it.

Draft planning floor: 40 covered expiries and 20 funded parents per index per
candidate, 100 scheduled expiries maximum. Before registering, use development
activity and effect-size simulations to show expected duration/power. EN87's
historical pace would miss 20 parents within 100 expiries; do not disguise that.
These counts are support floors, not guarantees of statistical power. If the
registered cap ends short, the outcome is INCONCLUSIVE. Keep index-specific
outcomes; do not fill a SENSEX shortfall with NIFTY tickets.

The forward comparison's primary endpoint should be **paired adverse net per
scheduled covered expiry versus frozen EN87**, with a separately required
positive adverse own-cash wallet and survival. Disclose paired E03_env results,
ordinary fills, without best one/two days, drawdown and missing coverage. Treat
baseline superiority and absolute profitability as different claims. Freeze
one final review; interim reports describe mechanics/risk, not optional-stopping
promotion. Correct multiplicity for the actually registered primary comparisons
across both champions/indices (for example Holm at familywise 5% over four
candidate-index cells if both indices are actually eligible). Sparse/unsupported
cells cannot be dropped later to make another cell significant.

No result here can guarantee majority wins, daily income or catching most
5-10x moves. A causal price move can be unobserved in time, already priced into
the option, or too small after trading costs. Automation can reduce decision
and execution delay; it cannot supply missing information. Long gamma produces
opportunity and long-option decay creates a hurdle. [OIC gamma](https://www.optionseducation.org/advancedconcepts/gamma),
[OIC theta](https://www.optionseducation.org/advancedconcepts/theta).

## 6. Developer implementation and anatomy contract

Use a new versioned folder `docs/research/simulation/2026-11-18-expiry-en96/`.
Never edit round-8 frozen sources. Proposed modules: `families9.py` expands and
canonicalizes grids; `signals9.py` computes causal information/context;
`policy9.py` supplies state-machine hooks; `search9.py` implements chronological
selection; `score9.py` writes immutable scores; `verify9.py` reconciles results;
`render9.py` builds anatomy tables. Reuse round-8 source/loaders and real
strategy functions through explicit versioned adapters. Refactoring a copied
day-loop without parity proof is not acceptable. No runtime integration yet.

Required artifacts:

| Artifact | Required content |
|---|---|
| `freeze9.json` | Code/data/calendar/config hashes, every expanded variant/control ID, source support, grids, dedup rules, folds, seeds, objectives, reserve arithmetic, stopping rules |
| `trials9.jsonl` | Every trial/revision, even failure/duplicate/unavailable, parent family, settings, support, run identity, code SHA |
| `results9.json` | Full grid, all costs/scenarios, no-score reasons, per-index/per-period metrics, outer selected-policy and fixed-policy results distinguished |
| `anatomy9.json` | Per-event feature clocks/IDs, per-parent decisions/fills/fees, rejected and missed orders, equity/cash/sweep/liquidation ledger |
| `ANATOMY9.md` | For EACH FAMILY: hypothesis, grid, where it won/lost, neighbor stability, causal implementability of any cohort rule, support limits, next decision |
| `COMPONENTS9.md` | Good part / harmful part / what happens when removed / interactions / retained as mechanism or rejected; no only-best-cell narrative |
| `verification9.json` | Exact checks/results, failures, environment limits, process exit, baseline parity, future erasure, financial identities and packet evidence limitations |
| `registration9/` | At most two immutable new prospective champions; no automatic promotion |

Minimum checks: reference-policy order/cash parity; grid count and deterministic
dedup; causal feature/threshold/selection prefix tests; missing versus zero OI;
frozen-anchor identity; same-clock tie ordering; TTL/restart idempotence; native
stop priority; partial-sale/add fees and max-loss arithmetic; impossible one-lot
splits; passive post-arrival evidence and cancellation race; full-wallet/sweep
reconciliation and persistence through folds/halts; score rerun adds nothing;
null cells stay null; coverage exclusions retained; component-off parity.

Recommended execution order: EN96/EN97 first, then EN98/EN104; EN100 and
EN99 bar timing; EN101/EN102; EN103; finally EN105. Packet EN99 is a parallel
data-gated research track, not a reason to substitute invented second-level
prices. Score the complete frozen grids; ordering here is for building and
debugging, not permission to stop after finding a flattering cell.

Acceptance of this phase is a trustworthy family-level report even if no
strategy qualifies. A positive development outcome would be a stable,
executable candidate that improves both adverse-money and path survival,
followed by a fresh prospective test. Main E03.2, EN55, normal F&O, Production,
broker messages, runtime configuration and capital are unchanged. Rollback of
this documentation phase is removal/revert of its own files and pointers only.
