# Independent review of EN96-EN110

Date: 2026-11-18. Reviewed Dev HEAD `c1e195fb`. Research, not operational
performance assessment. Production checkout read-only: `55b5e9422d02`; containers
and live release were not inspected. No download, runtime change or deployment.

## Verdict

The principal reported results reproduce. No evidence in this review overturns
the decision not to promote. However, "nothing beats the comparison book" is
too broad: several fixed historical variants earn more; no family satisfied the
registered selection and nomination procedure. Lack of selection, lack of
activation, monetary failure and lack of statistical evidence are different.

The research engineering is substantially stronger than the trading evidence.
EN87 is a useful conditional development lead, not a proven OI trading edge.
We did not lose that lead merely because a nomination was not produced.

## Independent execution

Commands from Dev using `C:/Users/Urveesh/sentinel-ml-venv/Scripts/python.exe -B`:

1. `docs/research/simulation/2026-11-18-expiry-en111/audit10.py`
2. `docs/research/simulation/2026-11-18-expiry-en111/claims10.py`

The first calls the frozen source/data validator, synthetic mechanics and
fresh-process verifier, redirecting its output into this new folder. It never
overwrites round 9. Outbound network is denied inside the research process.

Measured receipts:

- `integrity10.json`: 70 source/procedure hashes, two sealed data-file hashes and
  the replay tape-array manifests match; 197 NIFTY and 63 SENSEX dates.
- `mechanics10.json`: 17 tests, zero failures/errors.
- `fresh-verification9.json`: PASS; all 304 configuration ledger identities;
  all 32 sampled full-calendar ordinary/adverse reruns identical; reference
  wallets reproduced; all 18 non-composition selection sets re-derived;
  six EN105 reference-genotype parity checks; duplicate groups consistent.
- `claims10.json`: independent arithmetic and recorded constraint reconciliation.

This is not a full rerun of all 318 nominal grid cells, every composition,
the 972 pre-freeze prefix checks or the full engine suite. The sampled reruns
reuse the frozen simulator: determinism and financial reconciliation do not
independently establish the truth of the simulator's market-fill assumptions.

## Headline reconciliation

Modelled rupees, already-studied NIFTY data; independent expiry sessions unless
the continuous wallet column is named explicitly.

| Policy | Ordinary | Adverse | Ordinary / adverse continuous wallet |
|---|---:|---:|---|
| Matched E03_env | 3,006.43 | 2,245.82 | -3,445.43 / -4,034.97 |
| EN87 | 6,114.14 | 5,840.68 | 5,305.89 / 4,948.38 |
| Native E03.2 | 14,275.20 | 11,586.18 | -4,122.87 / -4,035.53; halts |
| EN100 nearer contract, best adverse cell | 9,498.21 | 8,103.28 | See complete ledger receipt |
| EN101 continuation, best adverse cell | 8,249.99 | 7,944.09 | See complete ledger receipt |
| EN110 exit geometry, best adverse cell | 11,696.08 | 11,215.02 | See complete ledger receipt |

Last three rows are selected full-grid descriptions, not nominated policies.
EN100's direct comparison is EN87 **at one lot** (3,735.12 ordinary in the
archive; consult exact receipt), not a claim of risk-identical superiority over
every native book. Compare entry reserve, lots, dated contracts and wallets too.
The original higher-target transfer test is labelled post-score in `post9.json`;
the explanation is useful but it is not new validation.

## Findings requiring correction or qualification

### R1: support design was poorly matched to this lead

EN87's six inner counts are 9, 8, 7, 9, 10 and 8. It therefore does not satisfy
the ten-parent floor at five boundaries. "7-10 is below ten" is imprecise: ten
passes the count. The extra positive-wallet, ex-best-two, activity and improvement
requirements still apply. Preserve the old freeze and labels; do not lower its
floor retrospectively.

The auditor's prior proposal should have included an outcomes-blind feasibility
check before approving this 60-expiry selection design. Responsibility for that
design limitation is shared; preserving the rule was the correct implementation.

Constraint records across the five outer selection windows (not independent
trades; repeated candidates/windows overlap):

| Family | Records | Fail support | Support is the ONLY failure | Pass all |
|---|---:|---:|---:|---:|
| EN96 | 160 | 115 | 65 | 11 |
| EN100 | 45 | 39 | 21 | 4 |
| EN101 | 90 | 72 | 33 | 3 |
| EN99 | 85 | 84 | 3 | 0 |
| EN103 | 65 | 52 | 3 | 0 |
| EN110 | 90 | 72 | 32 | 0 |

Thus the floor genuinely suppresses promising component comparisons, but does
not explain away patient-entry/scout losses. EN110 also frequently fails the
ex-best-two and improvement requirements. More observations, not permission to
ignore losses, are needed.

### R2: three families did not answer their intended mechanism

- EN98's finite caps 0.5/1/2 ATR excluded every EN87 event (observed range
  2.49-7.01). This rejects those caps, not the whole extension concept.
- EN102's fifteen-minute OI opposition never occurred during these holds. It
  cannot establish that all information-responsive exits are useless.
- EN103's one-third and one-half scout both buy one lot first for plans of
  up to three lots. The staged execution DID trade and lost; the two fraction
  alternatives were behavior duplicates, not two separate tests of sizing.

My prior specification should have caught the unit mismatch and lot rounding.
The next proposal requires activation/dedup checks before any P&L search. Do not
keep expanding a grid whose arms are identical or never actionable.

### R3: SENSEX source capability check is incomplete (P2 research defect)

`families9.Spec.needs_oi()` tests whether the name contains `OI`. `VOTE2` does
not, even though IMPL9 treats that rule as OI-dependent. Two SENSEX cells reach
the scorer and show zero trades instead of being excluded as unavailable. The
archived verifier uses the same predicate, so its 268-cell null check misses
this case. This is acknowledged in the narrative; it is not fully repaired in
the frozen implementation.

For the successor, use explicit sets of required inputs per rule, independent
tests for every enum, and three-valued available/missing/not-applicable states.
Decide whether a two-of-three vote is allowed to degrade to two available
sources BEFORE testing; never let string spelling decide. Preserve round 9.

### R4: missed-arm markouts are not after-fee trade winners (P2 reporting)

`score9.diagnostics`, the EN99 unfilled-arm block, computes
`(future_bid - event_ask) * lot`. It subtracts no buy/sell charges and uses an
event-clock hypothetical entry, not the reference's actual next-bar fill.
The global after-charges framing and calling positive values "winners" are
therefore too strong for this diagnostic. The simulated trade ledgers DO
include fees and still reconcile.

Successor reports must show gross executable-price markout, explicit fees,
net hypothetical markout, and actual matched-reference lifecycle P&L separately.
Do not change the archived financial score or pretend an unsubmitted order filled.

### R5: "solid information" overstates what was measured

Twelve of eighteen representations producing identical trade decisions shows
representation robustness on this sample. Removing the traded pair is useful
against a narrow strike-selection artefact. Neither proves causal seller flow,
independent information, future stability or a profitable directional forecast.
Aggregate OI does not identify the initiating buyer/seller or dealer inventory.

EN87 beats 31 of 40 time/activity-matched random-retention books, below their
90th percentile. That is modest descriptive separation. It also loses in 2026
and its recent inner wallet is negative. Keep the mechanism, lower the certainty.

### R6: nominal trials are not independent evidence

318 cells were registered. Twelve packet cells were source-gated; EN105 is
composed at boundaries, not 64 ordinary fixed full-calendar policies. The 286
NIFTY scored records include controls/references and collapse to 181 distinct
ledgers. Most variants share the same 25 parents. This is useful anatomy, not
318 independent confirmations or 318 equally informative failures.

The calibrated null over-rejection (up to 9.7% at nominal 5%) was disclosed
before scoring. No significance claim is appropriate. Descriptive intervals
are not confidence guarantees for the selected maximum. Do not repeat an
uncalibrated test until it prints a favorable p-value.

### R7: small documentation inconsistency (P3)

COMPONENTS9 says no component existed at the other five boundaries after
discussing boundary 180. ANATOMY9/ledgers correctly show a signal component at
160. It had no outer trade effect. No P&L changes; correct in an addendum.

## Why this has not produced the hoped-for profits

1. A causal influence can be real but already reflected in the option ask.
   We need information available before an executable repricing, of sufficient
   magnitude to pay spread, fees, decay and mistakes. Hindsight 5x opportunities
   do not supply the missing timing information.
2. Most changes use the same rare impulses. Threshold/basket variations often
   change no actions; delayed confirmation misses the favorable impulse; scouts
   pay a higher price later or reserve cash that never earns.
3. The slow OI statistic is an admission context, not automatically a fast exit
   signal. Its overlapping fifteen-minute window remains positive through a
   short trade even if the latest one or three minutes deteriorate.
4. The native strategy and the matched envelope solve different money problems.
   A large independent-session sum can be unreachable after a real wallet halt.
   We must keep its losing prefix rather than reset away the difficulty.
5. Contract response and exit state matter. Nearer contracts retain more of the
   underlying move; premature partials change the exposure path. But these
   explanations must survive beyond a few selected 2024-25 trades.
6. The information and effective sample size are small relative to the search.
   Hundreds of configurations on the same 197 afternoons do not create new
   independent market observations. There is no software-quality fix that
   supplies unavailable information or guarantees no losses.

## What to retain

- EN87 as a named, unchanged development comparator and immediate-entry control.
- The moderate OI band as a sensitivity result, not another main tuning project.
- Nearer affordable one-lot contracts, higher first target and moderate hold
  extension as the first joint factorial to investigate.
- Continuous-wallet simulation, negative recent-period reporting, adverse fills,
  immutable records and component ablations. Those are preventing false success.
- A simple interpretable adaptive action controller is worth testing. It should
  change contract/hold/exit choices with observable state, and stay in cash when
  no executable action has demonstrated value. It must never relax the hard
  capital contract to manufacture activity.

Detailed successor families: `../../../EXPIRY_RESEARCH_EN111_EN120.md`.
