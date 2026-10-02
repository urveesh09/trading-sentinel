# Jev Decision Layer — revised design proposal

**Original date:** 2026-09-27

**Review revision:** 2026-09-28

**Scope:** Dev design only; no implementation, Production edit, deployment, broker order, or partner message
**Status:** Draft for owner discussion; this Markdown revision supersedes the earlier proposal. The `.docx` and `.pdf` copies still contain the earlier draft and must be regenerated only after this design is approved.

## 1. Decision in brief

Jev may be useful as a cheap, typed **measurement instrument** for narrow judgments. Begin with **one parallel, shadow-only news-category experiment**. Keep the current MiniMax classification and downstream review context unchanged. Do not implement trade grading, signal plausibility, classifier replacement, or any M2/M3 authority in the first slice. Expand only if the shadow result is accurate and operationally useful on Sentinel's own labelled, held-out evidence.

Jev does not establish a trading edge, make the system a profitable trader, qualify partner tips, or authorize real-money orders. Autonomous momentum paper entries and explicit owner EXEC approval for every new real-money momentum entry remain unchanged. Hard session, sizing, broker, kill-switch, and F&O gates remain deterministic.

## 2. Evidence and assumptions

TypeSafe's current API supports `Choice`, `Score`, and `Noul` questions against a text/JSON `state`. The documented endpoint is `POST https://api.typesafe.ai/v1/systemone`. The current versioned model ID is `jev-1.13.0`; `jev-latest` is a moving alias. The published price is **$0.042 per million input tokens**, with output tokens free. These are vendor terms, not a measured Sentinel cost or latency receipt. Confirm them again when implementation begins.

Source: [TypeSafe API](https://docs.typesafe.ai/api), [models and pricing](https://docs.typesafe.ai/models), [confidence](https://docs.typesafe.ai/confidence), [Jev 1.13 limitations](https://docs.typesafe.ai/model-jaggedness/jev-1.13).

Important distinctions:

- A `Choice` returns a selected category, option probabilities, and a distribution-derived `confidence`. A `Score` returns a rubric-weighted score, level probabilities, and confidence. A `Noul` returns one yes-probability **without a separate confidence field**.
- Vendor-level calibration and speed claims do **not** prove calibration or p95 latency on Sentinel's Indian-market headlines, signals, or trade outcomes. Measure them locally. Do not assert that a 0.9 score means 90% correctness on this task before labelled evaluation.
- Jev is suited to narrow semantic judgments, not precise arithmetic, time comparison, broker truth, exit economics, or broad strategy reasoning. Compute those in code. Provider documentation explicitly lists numerical, date/time, large-state, and adversarial-content limitations.
- The public crypto trading demo illustrates API use; it is not evidence that this system's penny, momentum, F&O, or partner strategies will improve.

## 3. Current Sentinel contract and the actual seam

`agent/news_classifier.py` currently produces one bounded, eight-category informational `ClassificationResult` per sourced headline using a dedicated MiniMax client with no SDK retries and a one-second per-item timeout. A failed/low-confidence classification becomes `UNKNOWN`; the raw sourced news remains available. `agent/agent.py::_maybe_classify_news` can feed these classifications into `analyze_with_minimax` review context when enabled. Therefore a *replacement* classifier can change the operator-facing review, even though the category is not direct order authority. It is inaccurate to call a direct swap “zero order-path impact.”

`agent/async_reviews.py` already provides a bounded optional-AI worker. The scanner and F&O paths have deadline and scheduling constraints. An awaited 500 ms HTTP call or SQLite write inside their evaluation/close functions is **not** off-path merely because it is wrapped in `try/except`. Any future annotation worker must be demonstrably detached, bounded, and unable to delay decisions, exits, or protection.

The existing momentum-paper admission/lifecycle and exit-study evidence remains the source for reconciled outcomes. Jev labels must not bypass exact-key admission binding, cash reconciliation, quote-path provenance, or held-out research gates described in `docs/NEXT_AGENT_PLAN.md`.

## 4. Revised phased plan

### Phase 0 — define the experiment before coding

1. Freeze one question: classify a **sourced, timestamped headline** into the existing eight-category taxonomy (`REGULATORY`, `EARNINGS`, `M_AND_A`, `GUIDANCE`, `MACRO`, `RUMOR`, `TECHNICAL`, `UNKNOWN`). Define edge cases and the meaning of `UNKNOWN`. Keep text/source validation outside Jev.
2. Build an independently human-labelled, bounded evaluation set with disagreement adjudication. Include ordinary, stale, ambiguous, rumor, adversarial, and source-missing cases. Partition by time/source/ticker so near-duplicate headlines cannot leak between tuning and holdout.
3. Freeze comparison metrics and thresholds *before* viewing held-out results: category accuracy/macro-F1, confusion by class, abstention/coverage, proper probability scoring where labels are available, API availability, p50/p95/p99 end-to-end latency, actual token spend, and any disagreement with MiniMax. Report sample sizes and uncertainty. No fixed 0.7 cutoff is presumed optimal.
4. Specify a privacy/retention policy for provider-bound headlines and stored responses. No API keys, account secrets, or unrestricted position state may enter requests or raw logs.

**Phase-0 output:** a small experiment contract and frozen labelled sample definition. If adequate labels cannot be made, do not claim calibration or promote the classifier.

### Phase 1 — one shadow-only integration

1. Add an optional, explicit `JEV_SHADOW_ENABLED` switch, default **off**. The missing-key path records `DISABLED` without changing any existing classification or review. Use the provider's documented credential name (`TYPESAFE_API_KEY`) unless a single explicitly documented alias is chosen. Never print it.
2. Use a **versioned** configured model ID (initially `jev-1.13.0`, subject to verification) and log the resolved response model. Do not default to `jev-latest` while claiming a model pin. Roll forward only through an explicit reviewed config change and shadow comparison.
3. Implement a small client adapter with request/response shape validation, strict per-call deadline, no unbounded retries, bounded payloads, and error categories. Provider HTTP/schema/version failures produce a shadow `UNAVAILABLE` outcome; they do not alter MiniMax's output. Record token usage and actual measured spend.
4. Run Jev `Choice` in **parallel shadow** on the same source-validated headline snapshot as MiniMax. Persist a bounded annotation event with an immutable input/event ID, taxonomy/rubric version, input fingerprint, source timestamp/reference, provider model/version, choice/probabilities, latency, usage, and status. Store enough bounded input evidence or an independently verifiable archive reference to reproduce the assessment. Do not store unlimited raw responses.
5. The shadow request, queue, persistence, and reporting must be **off the existing decision deadline**. Use a bounded queue or equivalent detached worker with concurrency, age, backpressure, and shutdown limits. Record dropped/expired events as such. Never hold a scanner, close, stop, notification, or review transaction open while calling the provider. Existing MiniMax classification and review context remain byte-for-byte behaviorally unchanged when shadow is on or off.
6. Add a read-only operator report of coverage, error reasons, disagreements, latency tails, and measured cost. A dashboard panel is optional and follows useful evidence; it is not a Phase-1 ship requirement.

**Phase-1 acceptance:** unit/contract tests for missing key, 401/422/429/529, timeouts, malformed/extra answers, probability bounds and normalization, model mismatch, duplicate/event identity, queue saturation, restart/shutdown, and secret redaction; tests prove identical existing review/entry/exit decisions with the feature off and on under simulated provider failure. A staging/paper observation demonstrates no material scheduler-tail or deadline regression. Production remains unchanged until normal reviewed GitHub promotion.

### Phase 1 review — decide whether Jev is useful

Compare Jev, current MiniMax, and a simple deterministic/source-only baseline on a **future held-out** headline set. Present confusion matrices, abstentions, probability calibration by category, outcome coverage, latency tails, error rate, and measured total cost. Examine *which decisions* differ and whether those differences would have improved a human review. A lower bill or faster median call alone is insufficient.

If Jev is no better, leave it shadow-only or disable it. If it is better, propose a separate, reviewed classifier-routing spec that defines exactly when its label may enter MiniMax context and what happens on uncertainty/outage. No automatic swap or order/partner authority follows.

### Possible Phase 2 research — only after Phase 1 evidence

- **Retrospective trade grading:** try narrow, explicit rubric questions on fully reconciled paper lifecycles. Keep arithmetic, costs, risk, entry/exit timestamps and counterfactual comparisons in code. Human-labelled grades and prospective outcome association are required before claiming predictive value. Never infer that a post-close grade could have warned before the close.
- **Signal annotation:** begin with a precisely defined semantic question, not “is this plausible?” over a large state dict. Capture accepted *and rejected* evaluations using source-scoped immutable IDs and preserve the evaluation denominator. De-duplication that can be computed exactly remains deterministic code. A Jev Noul has one probability and no `plausibility_confidence` column.
- **No confidence overlay on F&O hard gates in this spec.** That would be a separate risk/authority design with owner review. Neither four weeks nor a score threshold automatically promotes an annotation to M2/M3.

These are research candidates, not commitments to build all three in one pass.

## 5. Data and evaluation contract

Do **not** implement the earlier proposed tables verbatim. `position_id` alone may not be globally unique across books; `(scan_id, ticker, leg)` may collapse repeated evaluations. Before migration, define a source-scoped immutable event key and uniqueness semantics for each producer. Retain event time, evaluated state/source reference, model and rubric versions, status (`COMPLETE`, `UNAVAILABLE`, `DROPPED`, `EXPIRED`, etc.), bounded answer, and usage/latency. Use additive idempotent migrations and a retention limit. Provider data is annotation, never ledger or order truth.

Reliability checks can validate schema, model ID, queue health and latency now. **Calibration is not a static contract invariant**: it needs independently labelled outcomes of sufficient size. A hand-built 100-row fixture tests the calibration *algorithm*, not Jev's real-world calibration. Brier scoring applies to defined probabilistic labels (for example a correctly-labelled news class or a predeclared binary outcome), not directly to an unlabelled 0–2 quality score. For ordinal grades, predefine human agreement and appropriate ordinal error/calibration metrics.

Counting only available grades/annotations creates selection bias. Every report must include total eligible events, successful annotations, failures/drops, unresolved outcomes, and labels by class/source/session. A four-week calendar observation is a review checkpoint, **not** a sample-size or accuracy guarantee; continue observation if the effective labelled sample is too small.

## 6. Operational risk, rollback, and authority

Shadow failure is recorded as unavailable; the existing MiniMax and deterministic paths continue unchanged. This is **failure isolation**, not an added trading veto. No provider call may delay a protective exit or create a broker/order/partner message. A bounded queue can lose annotation work under overload; that loss must be visible rather than silently counted as a negative signal.

Rollback: turn off `JEV_SHADOW_ENABLED`; drain/stop its worker under a bounded shutdown; keep prior annotations for audit. Additive schema remains but is unused. If the existing classifier/review behavior changes, treat that as a regression and revert the integration through Dev/GitHub. Production is never edited directly.

All new real-money momentum entries continue to require explicit owner EXEC approval plus existing hard checks. Partner tips require their own genuine qualification and separately authorized transport canary. Jev output is neither approval nor advice.

## 7. Open decisions for discussion

1. Is sourced news classification the right first narrow experiment, or is there a better semantic question with reliable human labels and a clear decision consequence?
2. What minimum held-out quality improvement over MiniMax **and** the simple baseline would justify a later classifier-routing proposal? Decide this before seeing results.
3. What headline data may be sent to TypeSafe and retained locally, and for how long?
4. Should the shadow trial start in Dev/staging only, or be promoted through GitHub to a disabled-by-default Production build after contract tests? Enabling Production would be a separate operator decision.
5. What sample-size/uncertainty standard should trigger a review? Do not substitute “seven days” or “four weeks” for sufficient labelled evidence.

## 8. Implementation handoff (not yet authorized)

**Problem:** test whether typed, inexpensive semantic classification adds measurable information without degrading Sentinel deadlines or changing authority.

**Files/contracts to inspect:** `agent/news_classifier.py`, `agent/agent.py`, `agent/async_reviews.py`, `agent/contract_health.py`, the agent-to-engine optional-AI status bridge, related tests, configuration and operator reports. Do not assume an existing queue can be reused safely until its capacity/shutdown behavior is checked.

**Acceptance:** Phase-0 frozen labels/metrics; Phase-1 shadow isolation and adverse-path tests; staging/paper operational receipt; later held-out comparison.

**Rollout:** Dev implementation and tests → reviewed GitHub promotion → disabled-by-default deployment verification → separately authorized shadow enablement and observation.

**Rollback:** disable the shadow switch or GitHub-revert the isolated integration; preserve evidence and prior classification behavior.
**Remaining work:** no Jev code has been implemented by this revision, no live provider calls were made, and no profitability, partner qualification, or live authority has been established.
