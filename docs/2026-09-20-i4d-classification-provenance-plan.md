# Workflow I.4.D classification provenance correction plan

Date: 2026-09-20  
Environment: Dev only (`codex/production-correction-hedge-p0`)  
Production impact: none until normal GitHub promotion and deployment

## Problem

The opt-in news-classification path currently fetches RSS items separately
from `scrape_sentiment()`. A changing feed can therefore make the bounded
classifications describe different headlines from the raw sentiment shown to
the verdict model. The classifier also records `NewsItem.source_name` in its
`ticker` field, drops the source URL/publication clock from its typed result,
and the async review cache key does not bind the classification context. A
cached verdict can consequently be reused across different classification
results even when the raw sentiment text is unchanged.

This contradicts plan section 13's requirement to retain model/prompt/version,
source references, response time and expiry. It is an annotation provenance
defect, not a request to make AI authoritative.

## Files and contracts

- `agent/agent.py`: fetch one immutable news batch per signal, render and
  classify that exact batch, pass the actual ticker, and include the bounded
  classification identity in optional-review cache keys.
- `agent/news_classifier.py`: retain bounded source URL/name, publication
  timestamp and correct ticker in each frozen result; provide one canonical
  classification-context digest.
- `agent/advisory.py`: expose bounded classification digest/count/source
  references and annotation expiry on the typed `Review`, with defaults for
  legacy callers and no authority fields.
- `agent/async_reviews.py`: attach the effective cache-validity deadline to
  READY/CACHED typed reviews, including tightened cached requests.
- Focused agent tests: prove one fetch per feed, exact item identity between raw
  and classified context, correct ticker/source/timestamp retention, cache-key
  separation, typed provenance and expiry tightening.
- Canonical guide/plan/checklist and regenerated code atlas.

No database/schema, environment default, model selection, broker, partner
transport, risk, capital, qualification or order behavior changes.

## Acceptance checks

1. One signal evaluation fetches Yahoo and Google once each; raw sentiment and
   classifications derive from the same frozen `NewsItem` objects.
2. Classification results carry the requested ticker rather than publisher,
   plus bounded source references and timezone-aware publication clocks.
3. Canonical context identity is deterministic and changes when a source,
   publication clock, classification, confidence, rationale or prompt version
   changes; classification completion time alone does not defeat reuse.
4. Optional review keys differ for different classification contexts and
   preserve the legacy key when classification is disabled.
5. Every typed review path retains the classification digest/count/source
   references. Queue READY/CACHED results expose the actual earlier of request
   deadline and cache TTL, and a shorter repeat request tightens that expiry.
6. Existing disabled, timeout, malformed response, saturation, budget,
   circuit, restart and non-authoritative behavior remains green.
7. Focused tests pass warning-fatal, the complete isolated agent suite passes
   warning-fatal, atlas/compilation/diff checks pass, and an appropriate
   repository regression run is recorded before commit/push.

## Rollout and rollback

Promote only through the normal Dev commit/push/PR/merge/deploy flow. The
feature remains opt-in under `ENABLE_NEWS_CLASSIFIER=1`; rollback is a reviewed
code revert or disabling that flag followed by an agent restart. Cached reviews
are process-local, so no data migration or cache conversion is required.

## Remaining work after this slice

- Production source freshness, provider latency and operator usefulness need
  real observed sessions; tests cannot supply them.
- Per-ticker usefulness aggregation (I.4.G) remains separately deferred.
- AI remains optional and cannot grant qualification, delivery or order
  authority.

## Baseline

The pre-change focused news/classifier/queue/pipeline group is **153 passed**
with warnings fatal in the isolated network-disabled agent image. The first
attempt named a nonexistent test file and ran no tests; it is not acceptance.

## Dev implementation result

Status: **TESTED_DEV; not deployed or Production-observed**.

- One feed bundle now supplies both raw rendering and classification; direct
  identity tests prove the classifier receives the exact fetched objects.
- `ClassificationResult` now carries the actual ticker, bounded source fields,
  aware UTC publication time and source digest. Missing URL, missing/naive time
  and future time fail closed before any model call. Canonical HTTP(S)+host
  validation and the existing seven-day stale boundary are enforced.
- The deterministic classification-context SHA-256 excludes `classified_at`
  but binds all source and semantic fields. Enabled optional-review keys carry
  it; disabled keys remain exactly compatible.
- `Review` carries context digest/count/structured source references and expiry.
  The queue stamps available, unavailable and exception results with context,
  independently rejects same-key context mismatches, and repeat lookups can
  only shorten validity. Sync late results become payload-free unavailable.
- First post-change focused run: **155 passed / 1 failed**; the sole failure was
  the pre-change CLI mock expecting no ticker kwarg. After correcting that
  expectation and adding provenance coverage, the focused superset is **185
  passed** warning-fatal.
- Independent review found and the final implementation closed seven further
  boundary defects: sync late-result enforcement, seven-day source validity,
  queue-internal cache-context checking, CLI RFC/ISO clock parsing, provenance
  on unavailable/exception paths, canonical HTTP(S)+host validation, and
  structured immutable source references.
- Complete isolated agent: **357 passed** warning-fatal, network disabled and
  Dev source mounted read-only. Changed Python compilation and diff checks
  passed. Atlas regeneration indexed **203 modules**.
- Engine/dashboard were not changed; their September 19 full receipts remain
  applicable. No profitable-strategy, deployment or partner-qualification
  claim follows from these tests.
