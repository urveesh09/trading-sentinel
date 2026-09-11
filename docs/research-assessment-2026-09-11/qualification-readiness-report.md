# Research data qualification and readiness report — September 11

## Decision

**NIFTY: INSUFFICIENT EVIDENCE. SENSEX: INSUFFICIENT EVIDENCE. Neither is qualified for actionable intraday strategy delivery by this assessment.** This is a completed assessment with a negative readiness result, not an unfinished request. No Production qualification registry or profile was changed. No message or order was sent.

Good news: forward collection is producing useful observed option books for both exchanges. The blocker is now precisely identified: complete causal strategy evaluation and persistent selected-leg coverage, not merely needing an unspecified number of days.

## Evidence inspected and reproducibility

Read-only /data/research journals for September10 and11, four dated NFO/BFO masters, packet raw hashes, latest Production DB schema/counts and deployed evaluator code. The assessor is saved alongside this report as assess_archive.py; results.json contains file fingerprints, raw-master validation and per-index statistics. retention.json contains the independent universe-retention comparison. qualification-decision.json is a research decision, not a registry authorization artifact.

61335 observed packets:59972 option packets and1363 futures-reference packets. 59887 option packets pass this assessment's basic30-second provider-age, positive non-crossed top book and at-least-one-lot top depth screen. All raw-packet hashes checked matched; zero mismatches in the compared contract-master fields (symbol, expiry, instrument type and lot). Four raw CSV master fingerprints matched their manifests. This is not an exhaustive independent validation of every contract field, every file manifest or trading permission.

September10 was compressed/finalized; September11 was an open segment read after its last market observations. File hashes identify inspected bytes, but no lock/snapshot of all live files was acquired simultaneously. Re-run fingerprints before using the files as immutable qualification inputs. Raw evidence remains in Production; this Dev report contains aggregates rather than a copy of the full archive.

## Data quality by index/session

| Session | Index | Option packets | Pass basic screen | Paired-book batches | Maximum usable-batch gap | Gaps >90s |
|---|---|---:|---:|---:|---:|---:|
| Sep10 | NIFTY |15004|15004|341|121.96s|38|
| Sep10 | SENSEX |14960|14875|340|153.92s|36|
| Sep11 | NIFTY |15004|15004|341|144.75s|38|
| Sep11 | SENSEX |15004|15004|341|152.32s|36|

SENSEX Sep10:45 option packets exceeded30-second provider age;40 had missing/unusable clock or book fields. These were excluded rather than repaired. Provider-age p95 for the four groups was approximately1.59–2.43seconds. Quotes are usually fresh when obtained, but observation intervals have gaps up to2.57minutes. Those gaps cannot reveal intervening stops, execution prices or continuous available depth.

Paired-book batch means at least one same-expiry/type pair within5-second observed-time synchronization with positive debit below strike width. All combinations were inspected as a liquidity screen. These are NOT selected strategy opportunities, actual fills, recommendations or independent statistical samples. OI/volume/spread limits, candidate thesis, Greeks, detailed cost/tax schedule and profile eligibility have not all been applied in this screen; passing it is not qualification.

Entry-window batches with such pairs:291/290 (NIFTY/SENSEX) on Sep10 and292/291 on Sep11. This establishes availability of books during much of the entry window, not strategy profitability.

## Selected-leg retention is a concrete gap

At the first09:20 batch each index had44 option tokens. Comparing those same tokens with the first15:15-or-later batch:

| Session | Index | Early tokens still present | Early tokens absent |
|---|---|---:|---:|
| Sep10 | NIFTY |36/44|8|
| Sep10 | SENSEX |36/44|8|
| Sep11 | NIFTY |28/44|16|
| Sep11 | SENSEX |16/44|28|

This is a universe-retention diagnostic, not proof a traded leg was lost: no advisory trade was recorded. It nevertheless proves rolling selection does not retain every initially observed contract through the management window. Candidate/active legs need explicit retention. The first observed15:15 batch arrives around15:15:25–26; that is after the exact15:15:00 boundary. Replay must declare minute-level versus exact-second deadline semantics and preserve uncertainty rather than pretending an on-time fill.

## Why no honest profitable replay/qualification is possible yet

1. Production has zero advisory ideas, research artifacts and strategy qualifications. There are no persisted advisory trade outcomes to analyse.
2. The deployed signal is evaluate_fno_mom: opening range + ATR buffer, fresh crossing, regime, EMA agreement, historical per-slot relative volume, stops/target and later spread validations. The artifact's orb_threshold_v1 evaluator reproduces a close-versus-trigger test, not that entire policy. A threshold report must not qualify the deployed full policy by name alone.
3. The retained fno_signals table has NIFTY observations but no accepted NIFTY paper signals on Sep10/11; it is a separate paper signal path, not authoritative partner decisions and not SENSEX coverage. Earlier accepted trades exist outside the two quote-archive sessions. They cannot be retroactively priced with these later books.
4. A targeted intraday_cache lookup found no NIFTY/SENSEX labels or the queried reference-token keys. This does not prove all historical bars are inaccessible; the by-token provider path may not persist them there. Sparse futures snapshots are not full causal5-minute OHLCV history or the multi-session RVOL baseline. Retrieve/retain the exact history with provenance and distinguish retrospective retrieval from observed-at-decision evidence.
5. No frozen causal train/holdout strategy comparison exists for these archives. Two dates can be used for pipeline development, but cannot be relabelled unseen after tuning on both. No predeclared policy-consistent costed outcome sample exists from which to calculate expectancy, win rate or drawdown. Those metrics are unavailable, not zero.

No synthetic trade or cherry-picked spread was introduced to make the report look productive. A liquidity combination count would grossly exaggerate the strategy sample size.

## Next actions, in execution order

A. Freeze one actual intraday policy manifest per index/structure. Implement/reuse the complete deployed signal evaluator to generate causal research decisions, with source bars, regime, OR/ATR/EMA/RVOL inputs, receipt cutoffs, config and master versions. Bind the selected contracts and decision IDs. Do not request the partner's personal strategy; Sentinel already has one that must be tested accurately.
B. Run a historical diagnostic on these two sessions after retrieving any available underlying bar history. Label retrospectively obtained history and missing contemporaneous inputs honestly. Include no-setup and rejected decisions; do not force an entry. Produce a reproducible report even if it contains zero trades. This is diagnostic, not sufficient approval by itself.
C. Pin all evaluated candidate/active legs through expiry of the idea and management exit window; keep existing quote budget and gap reporting. Preserve rejected/no-fill observations for selection-bias checks. Verify token/master changes and bounded storage.
D. Execute causal chronological replay with actual full-lot bid/ask, profile cost/risk bounds, nonzero manual-delay sensitivity, complete two-leg costs, unresolved exits and documented deadline semantics. Missing data must block the corresponding inference. A stop between sparse observations is not a known fill.
E. Predeclare evidence/coverage and statistical review criteria BEFORE assessing future held-out sessions. Assess net expectancy and uncertainty, drawdown, cost stress, per-index coverage and unresolved risk. Require evidence appropriate to the strategy's opportunity frequency; no arbitrary date or one/two-run promise.
F. Register genuine reviewed qualifications only if that report supports them. If it does not, keep the policy unqualified and compare a small frozen alternative rather than loosening gates. Profile already exists; Telegram routing can be checked separately with an explicitly authorised TEST/no-advice message.

## What this means for the partner

Technical collection is usable for further research now. Actionable tips are not approved by this assessment. More passive waiting alone will not resolve the evaluator/retention gaps. The next deliverable is a complete-policy causal diagnostic and bounded active-leg retention, then unseen outcome evidence. No partner account access or additional profile input is required to perform that work. The existing profile's limits are retained, not changed by this report.
