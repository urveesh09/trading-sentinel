# EN86–EN95: make the option-information lead falsifiable and tradable

November 18, 2026. Developer handoff, research only. Read alongside
`research/simulation/2026-11-18-expiry-review-en86/AUDIT.md` and its verification
receipt. Starting Dev commit: `21735463`. Production checkout: `55b5e942`.
No new strategy result is claimed in this document.

## What changes in our approach

Round 7 supplied a specific lead: NIFTY option-derived direction outperformed
the sampled random-side controls, but ordinary gains vanished under adverse
execution. The useful next question is not which new indicator to try. It is
whether that information survives synchronized observation, improves timing or
payoff selection, and can be bought in a contract that captures enough of the
move. These ten slots test different parts of that chain.

The independent replay reproduces NIFTY EN75 at +5,844 ordinary / -1,423 adverse
and EN83 at +4,722 / -3,886. E03_env is +3,006 / +2,246. Neither option-information
policy has established superiority. SENSEX EN75 is deeply negative, and its thin
future can manufacture an apparent lead. Keep E03.2 and registered EN55 unchanged.

Important qualifications:

- OI imbalance is observable positioning information, not identified seller,
  buyer, institutional or dealer activity. A contract always has both sides.
- EN75's minute bars use synthetic spreads around last-trade prices. Those can
  disagree simply because the legs traded at different times. Verify the lead
  on received, synchronized quotes before treating it as a market inefficiency.
- The reported 61% break-even accuracy belongs to one synthetic predictor and
  action distribution. It is not a universal requirement. Correct direction on
  tiny moves can lose; fewer correct calls with larger payoffs can earn. Measure
  conditional net rupees, move size, decay and execution, not accuracy alone.
- There is still no untouched historical expiry sample. Every old-date result
  below is development evidence. Combining good-looking pieces from these dates
  does not create an independent test.

## Research basis and what it does not establish

These sources guide mechanisms and controls; none proves an Indian expiry edge.

1. [OIC's OI explanation](https://www.optionseducation.org/referencelibrary/faq/general-information)
   and [CME's definition](https://www.cmegroup.com/market-data/volume-open-interest/about.html)
   explain why OI cannot reveal the initiating participant. Rename EN83's narrative
   to OI imbalance. Do not infer dealer gamma sign from aggregate OI.
2. [Pan and Poteshman](https://www.mit.edu/~junpan/volume.pdf) find information in
   specially identified opening option volume for individual stocks. They also
   distinguish publicly inferred flow and report no comparable informed-direction
   evidence in their index-option test. Copying their headline into a NIFTY OI
   strategy would substitute different data, instrument and horizon.
3. [Muravyev, Pearson and Broussard](https://research.hanken.fi/sv/publications/is-there-price-discovery-in-equity-options/)
   find, in their US equity sample, that options often adjust when parity-implied
   prices disagree with stocks. This makes “which market actually catches up?” a
   necessary control, rather than proof that options always lead or never lead.
4. [Gârleanu and Pedersen](https://w4.stern.nyu.edu/facdir/lpederse/papers/DynamicTrading.pdf)
   connect signal decay and trading costs. This motivates measuring the useful
   holding horizon. Their portfolio solution is not an expiry-option trading rule.
5. [Kite's packet specification](https://kite.trade/docs/connect/v3/websocket/)
   distinguishes receipt information, exchange time, last-trade time, cumulative
   volume and five-level depth. These fields support a causal quote replay, but
   do not give complete trade-by-trade aggressor labels or exchange queue identity.
6. [NSE's feed specification](https://nsearchives.nseindia.com/web/sites/default/files/inline-files/Real%20time-FO-L1L2-V1.7.pdf)
   documents a separate OI message. Measure actual OI availability; don't assume
   every newly timestamped quote contains a newly measured OI observation.
7. [OIC's expiry-risk discussion](https://www.optionseducation.org/news/may-keytakeaways)
   explains the joint gamma/theta exposure near expiry. A nearer-money option can
   react more to a small move while still losing quickly. Strike choice must be
   tested with the premium budget and real quotes, not just delta.
8. [Novy-Marx's multiple-signal analysis](https://www.nber.org/papers/w21329)
   explains why selecting combinations after seeing profits exaggerates evidence.
   EN95 therefore has one predetermined combination and specified ablations.

## Prerequisites outside the ten strategy slots

Implement these as versioned research infrastructure, with an erratum and old
outputs preserved. They are not new strategy thresholds and must not edit the
frozen round-7 files in place.

**Forward evidence.** EN83 currently reads a sealed historical OI database even
when EN85 builds a new tape from the operations database. Supply a hashed,
per-session OI panel through the data contract. Missing OI must produce MISSING
for an OI-dependent arm, not a zero-trade result. Pass a future-date synthetic
crossing test, then demonstrate the source used for each forward date.
Test a 2027 date too: the frozen reader's year-to-file map currently ends at 2026.

EN85 also needs a dated calendar independent of downloaded options, coverage for
the actual front contract and decision/exit windows, per-arm eligibility, a fixed
data-arrival deadline, crash-safe unique session records, and the promised forward
review/wallet command. Before the deadline, missing downloads are PENDING. After
the deadline they are MISSING; later data receive a linked sensitivity result.
Do not make missing sessions permanently invisible or quietly replace old rows.
Sequential dry-run idempotence alone does not establish these properties.

**Quantity accounting.** Repair the partial-sale defect in `frontier7.act` in a
new helper, and inspect older ML label consumers with the same pattern. Sell only
filled lots, retain the remainder, retry, charge actual orders, and preserve
unresolved exposure. Test two lots bought / one sold / later second sold and no
second fill. The audit found no affected ordinary delay-zero canonical historical
action; that is a bounded impact check, not permission to keep defective code.

**Passive proxy labels.** The repaired estimator still calls a full fill LOWER
when a fresh ask crosses below the limit, even if only one unit is offered and
no post-arrival trade occurred. The new audit reproduces this on a 65-unit order.
Treat these as conditional scenarios, account for quantity and order timing,
and publish versioned sensitivities. Do not label a paper proxy confirmed or a
guaranteed execution bound. The nine new primaries use marketable orders, so this
does not require changing registered EN55 or inventing a cash fill experiment.

**Power/calibration.** One rejection in twenty random controls is an initial smoke
test, not established test size. Use at least 1,000 inexpensive synthetic calendar
paths with symmetric, skewed, heavy-tailed and dependent zero-mean nulls, plus
declared known effects. Bind seeds and process before financial scoring. Report
Monte Carlo uncertainty. State the assumptions of the chosen test; sign-flipping
blocks is not distribution-free for arbitrary skewed observational returns.

## Shared contract for this round

### Scope, capital and execution

- Nine strategy primaries, EN87–EN95; EN86 is a diagnostic/gate. Register both
  indices up front as 18 index/policy cells, retaining unavailable cells. NIFTY
  has the immediate development data. SENSEX needs its own covered OI, synchronized
  option quotes and reliable underlying reference before a result is eligible.
  Do not use NIFTY OI as a silent SENSEX substitute.
- Separate comparison wallet per policy: 30,000, 50% of cumulative positive
  profit swept under the existing rule; unchanged 1,500/3,000/4,000 drawdown brakes.
  Show wallet cash, swept money and combined wealth. Do not add separate-policy
  profits as though one 30,000 wallet funded them all.
- Long options only. No futures position, short-option leg, margin borrowing,
  top-up or automatic transfer from the normal F&O book.
- Full-premium-plus-fees parent reserve at most 2,500; at most three lots unless
  a slot explicitly uses one. Daily aggregate room also 2,500: realized losses
  consume room; realized profits do not expand it. One open parent, at most two
  submitted parents per expiry. Size from the full possible premium loss, not a
  promised stop fill. Include the permitted sell-order fee reserve.
- Default window: completed decisions 13:00–14:29; flat under the current dated
  policy, no later than 15:14 for this research family. Respect dated contract
  closes and holidays. Longer holding slots do not extend market hours.
- Default action: E03_env's chooser, capped marketable entry and exit lifecycle.
  No passive entry in these primaries. EN55 remains a separate unchanged reference.
  Failed entry stays a non-fill. No retrospective switch to a cheaper strike.
- Default stop/target/partial/runner handling is exactly E03.2's, including its
  one-lot handling. Change only the component named by the slot. Freeze the full
  effective rule dump rather than relying on inherited defaults.
- Preserve ordinary/adverse/catastrophe definitions from the reconciled baseline.
  Minute-bar results remain BAR_LIFECYCLE with synthetic spreads, not measured
  bid/ask profits. Packet replay uses receipts, fresh depth, whole lots, independent
  timestamp fields and a 1-second arrival baseline; stress 3 and 10 seconds and
  measured worse latency. No sale reuses liquidity already consumed.
- Current lots/costs normalization is a present-policy screen, not actual historic
  broker cash. State the normalization; a historical-cost study needs dated lots,
  taxes and contract identities.

### Canonical evidence and decisions

For every causal event save a record whether or not the funded policy can enter:
index/date/receipt time, source basket and observation ages, feature values,
threshold training dates, side, affordable action, spread/depth/fees, rejection
reason, later label maturity, fills, exit requests and eventual cash flows.

Use two comparisons. A **matched-clock one-lot diagnostic** holds clocks,
contracts where appropriate, quantities and horizons fixed to isolate information.
A **funded policy comparison** recomputes stops, future admissions, remaining
room and wallet state. Report both. Round 7's “same bars” controls did not keep
all funded clocks identical. Never interpret a policy P&L gap as pure direction.

For info-event slots, EN83 is the immediate component control; E03_env and cash
are the common system controls. E03/EN55 native books are shown separately, so a
funding change is never attributed to a signal improvement. Existing developer
extras are extra hypotheses, not free unreported attempts.

### Evaluation and stopping

1. Old years are development screens only. Freeze each exact candidate, data
   requirements, costs, test, seeds, minimum meaningful improvement and cohort
   before its first prospective session. The first prospective date is after the
   implementation freeze and infrastructure verification; do not backdate a new
   strategy into EN85's existing cohort.
2. Use every scheduled expiry, with no-trade zeroes and explicit MISSING/PENDING
   records. No conclusion may condition on successful fills or surviving the brake.
3. First mechanism review at 20 eligible expiries; scheduled financial review at
   40. At least 20 funded parents over 10 traded expiries per index is a minimum
   screening floor, not proof of adequate power. Changes to E03 also need at least
   20 affected parent opportunities on 10 expiries for a change-effect verdict.
4. Maximum 100 eligible expiries for this registration. Insufficient support or
   intervals that still include the minimum meaningful effect mean INCONCLUSIVE,
   not demonstrated failure and not qualification. Publish an activity-based time
   estimate before running; rare variants may be commercially too slow to assess.
5. Primary evidence is after-fee expiry P&L and the paired difference versus
   matched E03_env; also compare with cash and the component control. Require
   positive ordinary AND adverse net before any profit-candidate label. Report
   intervals, worse-latency sensitivity, mark-to-liquidation drawdown and whole-
   wallet survival. Use the prevalidated clustered/dependence-aware method and Holm
   across the 18 primary cells; unavailable cells stay at p=1. If requiring both
   superiority to cash and control, use their maximum p as the cell test before
   family adjustment. This does not erase the previous adaptive search.
6. Income, tail and protection are different claims. Income needs broad returns
   including without the best two days and credible positive paired evidence.
   Tail strategies must disclose concentration and demonstrate repeated independent
   prospective tail wins with survivable ordinary/adverse losses; a high multiple
   alone proves nothing. Protection can earn less while reducing loss but cannot
   be advertised as alpha or as the requested big-profit result.
7. No threshold, holding period, model or selected component changes after scoring.
   Diagnostic alternatives cannot become the winner of the same cohort. No real
   money, capital increase or deployment follows automatically from any label.

## EN86 — verify that option information arrives before the tradable move

**Question.** Are EN75/EN83 useful received information, or mostly asynchronous
prices, repeated observations, basket changes and current momentum?

**Implementation.** Create `information86.py` and an event-level panel. Reproduce
the frozen bar signals first. Separately reconstruct EN75 from as-of packet
quotes: call and put bid/ask at the same strike/expiry, minimum three strike
pairs, exchange ages at most two seconds and cross-leg exchange-time skew at
most one second. Each source must have been received before the decision.
Use the European parity convention with a declared discount-rate assumption.
Do not equate the weekly option-implied expiry level with a monthly future;
remove the causal carry/basis and its uncertainty before testing innovations.
Carry intervals through the comparison, rather than declaring the midpoint fair.

For OI retain actual zero values, distinguish missingness and record the last
observed OI change/receipt. Compare the original current-ATM basket with a basket
anchored fifteen minutes earlier, using identical contracts at both endpoints.
Decompose threshold crossings associated with basket replacement. Do not call
the original changing basket look-ahead simply because its membership changes.

**Controls.** Own-price-only; lagged option information; option information matched
to another expiry at the same time bucket; leave the traded strike out of the
information basket; current versus lag-anchored baskets. These are diagnostics,
not candidates from which to select the most profitable version.

Measure distinct, nonoverlapping event responses at 30/60/180/480 seconds on
packets and 1/3/8 completed bars separately. Track future, cash reference and
option-pair adjustments. Report expiry-clustered response and payoff curves with
and without the largest days. Three minute-bar confirmations are not three
independent votes. Measure joint incremental information at aligned clocks, not
agreement somewhere during the same day.

**Acceptance/lesson.** Publish a classification by source: survives causal
synchronization / explained by freshness or price / too little data. Before
calling a packet mechanism repeatable, require at least 20 covered expiries and
100 nonoverlapping events, with at least 95% source coverage in its registered
decision windows. No hard profit claim follows from these minimum counts. If
the apparent lead disappears, stop building strategies around that source until
new independent information is available. A one-day pilot cannot pass this gate.

**Difference from EN75.** This tests information identity, available timestamps,
residual response and executable timing; it does not repeat the same bar P&L
under a new label. Downstream bar screens can proceed with an UNVALIDATED SOURCE
label while recording accumulates; they cannot promote through that label.

## EN87 — use OI at E03's timing, rather than trade every OI event

**Hypothesis.** E03's entry clock and the option-market side may complement each
other. This is a direct timing × information test, not two redundant flow votes.

**One primary rule.** At an unchanged E03_env signal with direction d, compute
the existing EN83 fifteen-minute score S on completed data and its existing
prior-20-covered-expiry 80th-percentile absolute-score threshold q. Enter only
if d × S > q. A fresh OI crossing is not required: that would test simultaneous
rare events instead of the state at E03's clock. Disagreement means abstain,
never automatic reversal. Missing score/threshold means unavailable decision.
Keep the E03 contract, sizing, order and exits unchanged.

**Controls.** E03_env; same clocks with an unrelated-day OI gate; rejected E03
parents shown as an anatomy cohort. Side-flipping is diagnostic only. Publish
matched parent deltas and the funded policy with changed later admissions.

**Files/tests.** `signals87.py`, registered rule dump and per-clock gate reason.
Test zero/missing OI, a strong agreeing score without a crossing, disagreement,
and future-bar deletion. Assert no new entry clocks and no unregistered flip.

**Win or useful failure.** Improvement must come from removing bad entries
without merely deleting exposure. Measure forgone winning tails. Too few changed
parents is INCONCLUSIVE. If conditional OI adds nothing at E03's clocks, the
option-information result does not strengthen this entry family.

## EN88 — trade OI innovation beyond what price already explains

**Hypothesis.** EN83 agrees with fifteen-minute price direction 88% of the time.
Its valuable component may be the part price does not already explain.

**One primary rule.** On each decision day, fit a ridge with penalty 10 and an
unpenalized intercept on the previous 20 covered expiry afternoons. Target is
current EN83 S, not future profit. Predictors are fifteen-minute futures return
divided by causal ATR, thirty-minute realized volatility, and time of day. Train
with equal expiry weight and prior-only standardization. This is a feature
residualization model, not a claimed price-prediction model.

Let R = S − fitted S. Freeze a threshold at the 80th percentile of absolute
residuals in that prior training panel. A fresh crossing of |R| above it creates
an event in sign(R). Re-arm after |R| falls below the threshold. Choose and trade
the ordinary E03 action with default exits. Do not require the raw S sign or price
sign to agree; save both. No call/put or year-specific retuning.

**Controls.** Raw EN83; price-predicted S at exactly the residual event clocks;
random side at those clocks. Report alignment/disagreement strata descriptively
without selecting one after scoring. Check whether residual features add to the
future return/payoff conditional on price in a new cohort.

**Tests/lesson.** Synthetic OI fully explained by price produces no substantive
residual signal; planted extra OI information does. Corrupting later sessions
must not change current coefficients or orders. If the residual has no forward
value, “new option information” was largely price repackaged. This is distinct
from EN73's failed all-session future-return forecast.

## EN89 — option-informed pullback and reclaim, with a price ceiling

**Hypothesis.** The signal can be right while the first option purchase is too
expensive. EN14's second push and EN81's refusal to chase are useful mechanisms
to test with the new OI information; neither is independently proven alpha.

**One primary rule.** An unchanged EN83 event arms a setup for five completed
minutes. Freeze its E03 contract, event-time ask and ATR; if no contract fits,
do not arm. Track the best completed futures close in the signal direction.
Require a pullback of at least 0.5 frozen ATR from that close, followed by the
first completed candle closing beyond the previous candle's high for a call
(below its low for a put). At that reclaim, raw S must still have the original
sign and exceed its frozen event threshold. Otherwise cancel, or expire at five
minutes/window end. At most one submitted order per armed event.

Entry is a new marketable order, never a resting-bid fill assumption. Its maximum
price is the smaller of the ordinary decision-time capped limit and 1.08 × the
event-time ask for that same contract. Recompute affordable whole lots and daily
room then. No fill above the ceiling; no switch to another strike or chase later.
Default E03 exits start from the actual fill.

**Controls.** Immediate EN83; the identical price-ceiling delay without a reclaim
condition; reclaim at the same price events with an unrelated-day OI state.
Compare missed runaways, entries saved from buying a decline and extra decay.
Include unaffordable/expired/unfilled setups in the event ledger.

**Tests/lesson.** Rising straight through the ceiling must remain missed;
pullback without reclaim is not bought; intrabar high touches do not establish
a reclaim. A profitable development spike that depends on exactly one delay
is not accepted as a timing mechanism. If better prices arrive only on failing
moves, this repeats passive adverse selection and should be rejected.

## EN90 — separate OI unwinding from new open-position growth

**Hypothesis.** EN83 combines different changes that need not have the same
economic meaning. Test that decomposition before inventing a dealer story.

For the same fixed five-strike basket at a decision, let C0/P0 be call/put OI
fifteen minutes earlier and Ct/Pt their current values. Compute **per contract**
before summing, so additions and declines at different strikes do not cancel
before classification:

```
U = sum(max(C0-Ct,0) - max(P0-Pt,0)) / sum(C0+P0)
D = sum(max(Pt-P0,0) - max(Ct-C0,0)) / sum(C0+P0)
S = U + D
```

The identity must match the raw EN83 score on identical valid endpoints. U is
net OI contraction asymmetry; D is growth asymmetry. Neither identifies who
closed or opened a position. Require at least three complete strike pairs;
never convert missing OI into zero.

**One primary rule.** Apply EN83's existing prior-20-expiry 80th-percentile
fresh-crossing procedure to |U| and trade sign(U), with default action/exits.
Freeze this sign convention before outcomes. Do not try both signs and promote
the winner. D and raw S at U's clocks are controls, not additional selectable
primaries. Also report full raw EN83 funded-policy P&L.

**Tests/lesson.** Test pure growth, pure contraction, equal changes, true zero,
missing endpoints and the exact S identity. Save which contracts contributed.
If only contraction has persistent value, we have localized the phenomenon;
if neither component survives, the aggregated score's old gains may be accidental.
This is not a claim that every OI decline is a short-covering squeeze.

## EN91 — give the option-information trade one fixed longer horizon

**Hypothesis.** Eight minutes may monetize too little of a slow signal, even
if the direction is useful. A longer hold also pays more decay and can be worse.

**One primary rule.** Unchanged EN83 event, action, sizing, 35% premium stop and
profit/runner ladder. Replace only its eight-minute time exit by 24 minutes.
Never extend the dated flat cutoff. No re-entry or extra holding after that
clock just because the score is still positive. Other exit reasons retain their
normal precedence and order-based retries.

**Controls.** Native eight-minute EN83; identical entry tickets with fixed 8/24
minute liquidation diagnostics; price-sign strategy at those same event clocks.
Return curves at 3/8/16/24/32 minutes are descriptive, not a horizon tournament.
Report the actual funded policy separately because longer exposure can block
later entries. Measure direction drift, option value change, decay, IV change,
fees and latency on the same tickets.

**Tests/lesson.** Stop occurs first in an ambiguous bar; a near-cutoff entry is
flat on time; increased holding never creates a new funded parent. If underlying
drift grows while executable option net falls, the information is too weak/expensive
for this instrument. If the drift reverses before 24 minutes, the signal is not
slow continuation. Do not respond by selecting the prettiest curve point.

## EN92 — buy one affordable higher-sensitivity contract

**Hypothesis.** Cheap far-OTM contracts can fail to capture a small directional
lead. One nearer-money option may capture more, within the same maximum loss.

**One primary rule.** At unchanged EN83 entry clocks, consider every covered
same-day, same-direction contract in the declared chain universe, including ITM
and ATM. Among contracts with a fresh valid two-sided market and one whole lot
fitting the 2,500 full-premium/fee reserve and remaining cash/room, choose the
highest-moneyness contract: minimize d × (strike − cash index). This deterministic
ranking avoids treating unstable model delta as a forecast. Tie-break by lower
quoted round-trip cost then strike. Buy exactly one lot; default E03 exits and
one-lot handling. No available contract means abstain, not assumed ATM exposure.

For a bar screen use the frozen synthetic-spread/volume contract and label it;
packet results must use actual bid/ask/depth. Do not silently require new depth
evidence only from the candidate while giving the matched control free fills.

**Controls.** EN83's existing chooser at one lot; its original whole-lot sizing;
and a cash-commitment matched diagnostic. Show count/price of unaffordable ATM
contracts, strike distance, actual theta/gamma sensitivity diagnostics, fees,
ordinary/adverse money and missed tail gains. “Cheaper relative spread” alone
does not establish a superior contract.

**Tests/lesson.** It must never overspend one lot, use a missing strike or select
on future liquidity. If stronger underlying sensitivity pays but still fails the
cash budget, record the affordability frontier without asking for more capital
or creating a short leg. This differs from EN53's E03-only ATM substitution and
EN63's lowest-friction ranking: it tests the new information on the most responsive
contract actually fundable by this book.

## EN93 — predict the new signal's realized option payoff directly

**Hypothesis.** The relevant forecast is net option money, not a uniform hit
rate or a theoretical option value. EN61 lacked this new option-information
input; EN73 added model-pricing error to weak price forecasts.

**One primary rule.** At raw EN83 events use the ordinary E03 action. Train one
ridge, penalty 10 with unpenalized intercept, to forecast actual after-fee return
on committed reserve under that exact action/exit policy. Use only four completed-
data features: signed standardized raw OI imbalance, signed standardized EN75
parity innovation, observable round-trip friction/reserve, and time of day.
Missing parity/OI produces an unavailable decision, not an invented zero.

Use the last 60 covered prior expiries for training, followed chronologically by
20 for calibration; all labels must have matured before fitting. Weight expiries
equally. Save every potential event, including no-fills at outcome zero, and
keep overlapping events grouped by expiry. Future labels never decide which
training candidates exist. No Black-model value substitutes for the observed
option outcome. Refuse a model with fewer than 100 covered event rows on 40
training expiries or fewer than 20 calibration expiries; report the startup cost.

Predict net rupees at actual contemplated reserve. Correct for the mean of
calibration-expiry residuals and subtract 1.645 × their standard error. Submit
only if this conservative score exceeds zero. This score is a heuristic, not a
guaranteed conditional confidence bound; freeze it and test its realized
calibration specifically on selected trades in the next cohort.

**Controls.** Intercept-only net predictor; identical four-feature model without
the OI/parity features; unconditional EN83; matched random side. Publish forecast
versus actual net, calibration by predeclared score terciles, selection coverage,
tail contribution and fee drag. Do not call a better squared error a profitable
policy. Do not tune regularization, features or the zero threshold after scoring.

**Tests/lesson.** A planted net edge must be recoverable; a zero/negative net world
must not appear profitable solely through the pricing/conversion layer. If it
cannot separate positive payoff states, that directly limits the commercial value
of the current information panel. Too few selected trades remains INCONCLUSIVE.

## EN94 — exit when the information reverses, not merely when price dips

**Hypothesis.** The failed instant-stop experiments reacted to price noise.
A reversal in the information that justified entry might be a better early exit.

**One primary rule.** Unchanged EN83 entry/action and all native exits, including
the eight-minute clock. At the actual entry freeze the OI source basket. Each
later completed minute recompute its fifteen-minute OI imbalance on those same
contracts. If d × S_hold < 0 on two successive valid observations, submit a
full exit at the next executable opportunity. A missing observation resets the
two-reading counter; it cannot stand for a reversal. Exits already requested
remain queued and all remaining lots must be accounted for. No automatic flip.

**Controls.** EN83 unchanged; price-sign reversal at matched clocks; informational
reversal events that did not trigger a funded exit. Parity reversal is a diagnostic,
not an additional primary gate. Keep all stops and clock exits operational even
when OI is missing. A failed entry monitor must never disable exit machinery.

**Tests/lesson.** One reversed reading cannot trigger; reversal then missing data
requires two new valid readings; basket membership cannot change mid-trade; a
partial exit cannot close unsold lots. Report losses saved versus rescued trades
cut, fee effects and loss after gap fills. At least 20 affected parent opportunities
is required before a change-effect claim. If it barely fires, say that this
information is too slow for an eight-minute exit, rather than weakening the rule.

## EN95 — one predetermined complete trader, with component ablations

**Hypothesis.** A better entry price, responsive contract and information-based
invalidation may work together even if none wins every isolated comparison.

**One primary policy, fixed before results.** EN89's option-informed pullback/
reclaim entry, EN92's one-lot higher-sensitivity chooser, EN94's information exit.
All other default exits, clocks, cash and risk limits remain unchanged. No scout,
patient bid, EN91 extension, learned selector or post-score best-component swap.

Resolve the contract interaction explicitly: EN89 arms from a valid raw EN83
event; EN95 chooses its EN92 contract at that event and freezes that contract
and its event-time ask. The same reclaim/ceiling then applies to that contract.
EN94 freezes its OI basket at the actual fill. No later strike substitution.

**Controls.** Matched E03_env, raw EN83 and three predeclared remove-one controls:
remove the reclaim entry; remove the chooser; remove the information exit. Each
control gets the same capital, fees and causal executor. These ablations explain
the one primary; they are not alternative candidates eligible for promotion.
Publish individual components and the interaction, not just the best total.

The complete policy is frozen and recorded alongside the other primaries. Its
registration must not wait for this round's component P&L. If a mechanism/data
prerequisite is absent, it is unavailable rather than replaced with a convenient
substitute. This avoids both untested “mix the winners” selection and the false
assumption that a combination can never help unless every component wins alone.

**Tests/lesson.** Trace an ordinary winning setup, false reclaim, runaway above
the ceiling, losing setup, one-lot double, OI reversal, stale data and restart
through the complete state machine. Check the same order/cash conservation on
every arm. Success means independently demonstrated net/risk improvement under
adverse execution, not three modules agreeing. Failure must identify which part
changed the entry, payoff, exit or affordability and how much it cost.

## Delivery contract and order of work

Use a new Dev research folder, e.g. `2026-11-18-expiry-en86/`, with independent
registration JSONs, source/data hashes, causal event and cash ledgers, feasibility
report, frozen acceptance criteria, commands/environment, development results,
forward ledger and a per-slot anatomy. Preserve all failures, controls and
unavailable dates. Update the system guide/active plan with implementation commits;
regenerate the runtime atlas only if runtime source declarations actually change.

1. Repair/version forward OI sourcing, completeness, quantity accounting and
   crash-safe receipts; publish the bounded erratum. Reconcile old controls.
2. Build EN86 and begin its source-quality panel. No new paid feed/download or
   Production recorder expansion is authorized by this proposal alone.
3. Prioritize EN87, EN88 and EN90: timing complement, residual information and
   OI decomposition. They most directly test what round 7 actually learned.
4. Then EN89, EN91, EN92 and EN94: entry price, signal horizon, contract and exit
   invalidation. Keep each component identifiable.
5. Build EN93 only after its labels, support and calibration tests work. Register
   EN95's complete policy before any component outcomes, even if implementation
   finishes later. Freeze actual first eligible cohorts without backdating.

No new trading edge can be guaranteed from the present evidence. A useful round
must at least distinguish false lead, weak residual information, bad entry price,
wrong horizon, poor contract sensitivity and execution failure. The final report
should say which explanation survived, rather than simply printing another list
of FAIL results. E03.2/EN55 and the normal F&O engine stay unchanged throughout.
