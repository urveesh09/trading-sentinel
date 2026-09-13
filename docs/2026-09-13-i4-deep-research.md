# I4 — Deep research for AI-enrichment opportunities

## Context

Phases I1, I2, I3 shipped:

- **I1** — Optional-AI provenance (model/prompt/version + response time) on the agent side, captured per-review at every `analyze_with_minimax` return site.
- **I2** — News provenance (publication timestamps + source URLs) for the sentiment prompt.
- **I3** — Usefulness instrumentation (bounded counters: verdict counts, cache hits/misses, response_seconds_mean/p95/last, circuit_opens). New `optional_ai_metrics.py` CLI with `print-config` and `read-snapshot` subcommands.

What's NOT yet done:
- The I3 usefulness metrics live only on the agent side. They never reach the engine's `optional_ai_status` table, the dashboard, or `operational_coverage_report`.
- The I1 provenance fields (`model`, `prompt_version`, `response_seconds`) are captured per-review but not surfaced in the alert banner or dashboard.
- I3 deliberately did not invent a "did this help" metric.

This document is **research, not code**. It identifies the highest-value AI-enrichment opportunities I can find by re-reading the existing agent/engine/dashboard surfaces and the §13 acceptance criteria. Each opportunity has a senior-dev honest assessment of cost, risk, and plan-§13 compliance.

## The full surface area (where AI can plug in)

I traced every site where the agent and engine interact, and every site where the operator sees AI output:

### Agent side (Python, container C)

| Site | What it does | Plan §13 contract |
|---|---|---|
| `analyze_with_minimax` | Returns a `Review` (verdict + conviction + payload) | Verdict + reasoning |
| `send_momentum_telegram_alert` | Builds the EXEC-button Telegram message; reads `review.banner()`, `analysis.pitch`, `analysis.rationale`, `analysis.risks` | Annotation surfaces to operator |
| `send_conviction_veto_notice` | Sends a REJECT notice with rationale | Annotation surfaces to operator |
| `publish_optional_ai_status` | POSTs health envelope to engine `/ops/optional-ai-status` | Status only |
| `optional_ai_status()` | Returns dict (state, queue counters) | Status only |
| `usefulness_snapshot()` (NEW I3) | Bounded counters; not yet posted to engine | Usefulness |

### Engine side (Python, container B)

| Site | What it does | Plan §13 contract |
|---|---|---|
| `optional_ai_status.record_optional_ai_status` | Persists agent's status envelope | Persisted health |
| `optional_ai_status.load_optional_ai_status` | Reads the envelope back | Persisted health |
| `routes_ops.post_optional_ai_status` | Receives agent status POST | Authenticated intake |
| `routes_ops.get_optional_ai_status` | Returns status for dashboard | Dashboard surface |
| `operational_coverage_report` | Per-producer health (H5) — does NOT include optional AI | Producer coverage |

### Dashboard side (React, container G)

| Site | What it does | Plan §13 contract |
|---|---|---|
| `OptionalAiEvidence` (Dashboard.jsx) | Renders state + queue counters | Operator visibility |
| `useOptionalAiStatus` (hook) | SWR fetcher | Operator visibility |

### Plan §13 explicit acceptance (from `docs/NEXT_AGENT_PLAN.md` §13)

1. Use AI for bounded annotation: explain a deterministic setup, classify sourced events, summarize risk context, compare research findings and identify missing evidence.
2. Store model/prompt/version, source references, response time and expiry. **(I1, I2 partial)**
3. The typed result must not change capital limits, qualification or order/delivery authority.
4. Test disabled mode, timeout, stale response, queue saturation, budget exhaustion and restart. Deterministic paths must still operate.
5. News must have publication/event timestamps and a reliable source; an unsupported model statement is not a market fact. **(I2 done)**
6. Evaluate annotation usefulness separately from trading outcome. **(I3 done — instrumentation only)**
7. Expected benefit: better explanations and event-awareness.
8. Main risk: plausible but wrong context arriving too late.

## Opportunities (ranked by senior-dev value/cost)

### **Opportunity A — Bridge I3 usefulness metrics to the engine** *(highest value, low cost)*

**What**: extend `optional_ai_status._ALLOWED_STATES` and the `clean_queue` allow-list to surface I3's `verdict_counts`, `cache_hit_rate`, `response_seconds_p95`, `circuit_opens`. Add a new `usefulness` key on the engine side; surface in the dashboard.

**Cost**: ~50-80 lines. Touches:
- `agent/agent.py::publish_optional_ai_status` — include `usefulness_snapshot()` in payload
- `python-engine/optional_ai_status.py` — extend `clean_queue` allow-list (security whitelist); add a new bounded `usefulness` envelope with its own field validator
- `python-engine/routes_ops.py` — no change (reuses existing GET)
- `node-gateway/client/src/pages/Dashboard.jsx::OptionalAiEvidence` — render new fields

**Senior-dev honest assessment**:
- ✅ Plan §13: surfaces usefulness metrics for operator review
- ✅ No deletion — additive only
- ✅ Bounded — only aggregated counters cross the bridge, never review content
- ✅ Reversible — operators can ignore the new fields
- Risk: the agent could spam the engine with updates. Mitigation: agent already batches via `publish_optional_ai_status` on `MINIMAX_ASYNC_REVIEW_ENABLED` cadence; we extend that one path.

**Why this matters**: I3's data is currently stranded. The senior-dev rule "make it visible" applies here — if usefulness data lives only on the agent side, operators can't see it.

**Acceptance**:
- Agent posts `usefulness` in the status envelope.
- Engine validates `usefulness` (bounded int/float/dict keys, no nested objects with unbounded keys).
- Dashboard renders `verdict_counts`, `cache_hit_rate`, `response_seconds_p95`, `circuit_opens`.
- Whole-engine tests still green; new bounded field validation tests added.

---

### **Opportunity B — Surface I1 provenance in the operator alert** *(medium value, low cost)*

**What**: extend `Review.banner()` to include `prompt_version` and `response_seconds`. Operators see which model/prompt produced the verdict and how long it took, in the alert itself.

**Cost**: ~10-20 lines. Touches `agent/advisory.py::Review.banner()`.

**Senior-dev honest assessment**:
- ✅ Plan §13: "Store model/prompt/version ... response time" — surfacing them is the user-visible half of I1
- ✅ The banner is already operator-facing; one more line is bounded
- ✅ No new surface area, no new model call
- Risk: banner length — Telegram has practical limits (~4096 chars). Mitigation: the existing banner is short; adding `model/prompt/seconds` is ~30 chars.

**Why this matters**: I1 captured provenance in the data structure but the operator never sees it. The point of I1 was operator auditability; without surfacing, the auditability is theoretical.

**Acceptance**:
- Banner includes `model`, `prompt_version`, `response_seconds` formatted to 1 decimal.
- Banner length stays under 200 chars (room for the alert body).
- Existing banner tests updated to assert the new fields.

---

### **Opportunity C — `operational_coverage_report` includes optional AI** *(medium value, low cost)*

**What**: add `optional_ai` as a new producer in `operational_coverage_report`, mirroring the same `{state, reason, observed_at, ...}` contract. The producer sources its data from `load_optional_ai_status`. Apply the H5 vocabulary validator: map `READY` → `NO_SETUP` (or new `READY` mapped to `NO_SETUP` is debatable; the H5 mapping already exists for `OBSERVED_USABLE`), `OUTAGE_CIRCUIT_OPEN` → `ERROR`, `DISABLED_*` → `DISABLED`.

**Cost**: ~30-50 lines. Touches `python-engine/operational_coverage.py` only.

**Senior-dev honest assessment**:
- ✅ Plan §13: surfaced through the dashboard's `OperationalCoverage` component alongside other producers
- ✅ Reuses H5's `STATE_TO_DESCRIPTOR` mapping (already has `OUTAGE_CIRCUIT_OPEN` conceptually; would need `READY`, `DISABLED_*` mapped)
- ✅ Self-validating through the existing `validate_coverage_report`
- Risk: the optional AI's `_ALLOWED_STATES` doesn't overlap with H5's `STATE_TO_DESCRIPTOR`; we'd need to extend H5's vocabulary. Senior-dev: that's exactly the right move — bounded vocabulary catches drift.
- The H5 vocab already has the §12 descriptors; we just add more states.

**Why this matters**: Right now `OptionalAiEvidence` (in Dashboard.jsx) is a separate section. Merging into `OperationalCoverage` makes the dashboard consistent — operators see all producer health in one place.

**Acceptance**:
- `operational_coverage_report` includes `optional_ai` producer with the standard contract.
- H5 vocabulary extended to map optional AI states to descriptors.
- Dashboard's `OperationalCoverage` includes optional AI; `OptionalAiEvidence` stays for now as a richer detail view.

---

### **Opportunity D — Source-event classification (plan §13 explicit)** *(high value, high cost)*

**What**: plan §13 says *"classify sourced events"* — i.e. use the model to label each news item with a category (regulatory / earnings / M&A / rumor / no-news) before the existing pipeline summarises. Currently `scrape_sentiment` only collects headlines with timestamps (I2); the model prompt asks it to "evaluate whether the news/catalyst justifies a sustained move" — it has to do its own classification implicitly.

**Cost**: ~100-200 lines. Touches:
- New `agent/news_classifier.py` — classifies one `NewsItem` against a fixed taxonomy
- Modified `analyze_with_minimax` — accept pre-classified events instead of raw text
- New bounded `ClassificationResult` dataclass (frozen, with `category`, `confidence`, `rationale`)
- Tests: ≥10 (taxonomy, edge cases, classification fallback)

**Senior-dev honest assessment**:
- ✅ Plan §13 explicit: "classify sourced events"
- ⚠️ Risk: a new code path in the bounded-annotation pipeline. Must not change verdict semantics (still non-authoritative).
- ⚠️ Risk: a new prompt + a new model call could spike latency. Mitigation: classify locally with a faster model call (a separate, smaller prompt); keep the existing verdict pipeline untouched.
- ⚠️ Risk: misclassification. Mitigation: fixed taxonomy; confidence threshold; UNKNOWN fallback.
- ⚠️ Risk: dataset drift. A category the model invented last year may not exist this year. Mitigation: the taxonomy is operator-defined and versioned; a category not in the taxonomy is labelled `UNKNOWN`.

**Why this matters**: This is the only §13 explicit acceptance that has no current implementation. Plan §13 lists seven annotations: explain, classify, summarise, compare, identify missing evidence. We have summarize (pitch/rationale/risks) and identify-missing-evidence (conviction). We don't have classify, and we don't have compare.

**Acceptance**:
- Fixed taxonomy of 8 categories (regulatory, earnings, M&A, guidance, macro, rumor, technical, unknown).
- One-shot classification with confidence; UNKNOWN below threshold.
- Latency budget: < 1s per item (fast model call).
- Deterministic pipeline untouched: the verdict (`REJECT`/`APPROVE`) is still produced by the existing pipeline; classification is informational only.

---

### **Opportunity E — Periodic self-evaluation against the bounded contract** *(low value, very low cost)*

**What**: a small cron that runs once per hour and produces a structured "contract health" report — does the agent still respect the bounded contract (no execution authority in the status envelope, no prompt leakage, no review content in the bounded snapshot). Surfaces any drift in the dashboard's existing coverage vocabulary.

**Cost**: ~30-50 lines. Touches:
- New `agent/contract_health.py` — checks invariants
- New bounded cron in `python-engine/scheduler_setup.py`

**Senior-dev honest assessment**:
- ✅ Plan §13: "The typed result must not change capital limits, qualification or order/delivery authority" — checking this automatically is the senior-dev right move
- ✅ Bounded: the cron is read-only
- ⚠️ Risk: a cron is a moving part; we already have many. Mitigation: piggyback on the existing `system_health_check` cadence.

**Why this matters**: It's a "guard the guards" pattern. The H5 vocabulary validator already catches state drift; this would catch *content* drift (e.g. if someone accidentally puts `pitch` in a status envelope).

**Acceptance**:
- Cron runs hourly, checks 5 invariants, produces a structured report.
- Existing cron tests still pass; new cron test added.

---

### **Opportunity F — Compare annotations across the producer → engine boundary** *(medium value, medium cost)*

**What**: a test suite that, given the agent's status envelope, asserts the engine persists exactly the bounded fields and nothing more. Catches silent schema drift between the two containers.

**Cost**: ~50 lines. Tests in both `agent/tests` and `python-engine/tests`.

**Senior-dev honest assessment**:
- ✅ Plan §13: "permit only bounded, presentation-safe operational fields" — the existing `optional_ai_status.record_optional_ai_status` enforces this with a whitelist. A test that round-trips a known-bad envelope catches future drift.
- ✅ No new code in production; tests only
- ⚠️ The test must be versioned so a legitimate schema addition doesn't break it.

**Why this matters**: cross-container contracts are easy to break silently. A round-trip test catches drift at CI time, not in PROD.

---

### **Opportunity G — Per-ticker / per-strategy annotation breakdown** *(medium value, high cost)*

**What**: track which tickers / strategies get vetoed most often. Surfaced in a bounded report ("RELIANCE was vetoed 3 times in the last 7 days; TCS was approved 5 times"). Operators can spot trends like "this strategy is no longer working because the AI keeps vetoing it."

**Cost**: ~150-300 lines. New bounded aggregation in `AsyncReviewQueue`, new dashboard component.

**Senior-dev honest assessment**:
- ✅ Plan §13: "evaluate annotation usefulness separately from trading outcome"
- ⚠️ Risk: opens a new dimension for verdict counting — must remain bounded (cap at top N tickers, top N strategies)
- ⚠️ Risk: this is the closest we've come to "did this help" — must be careful not to imply operator decisions should follow it

**Why this matters**: this is the *only* opportunity that gives operators a longitudinal view of annotation behavior. The current snapshot is point-in-time.

**Acceptance**:
- New `usefulness_snapshot_by_ticker(top_n=10)` returns bounded list.
- New dashboard widget renders the bounded list.
- Whole-engine tests still green.

---

## Opportunities I am NOT proposing

- **A new model endpoint / SDK.** The plan says optional AI is bounded. Adding a second model provider doubles the surface area without §13-mandated value.
- **Real-time annotation streaming.** Latency pressure; the current async queue already delivers under the 90s deadline.
- **A "did this help" composite metric.** Per §13 the operator must supply ground truth; we can't invent a heuristic.
- **Streaming the alert before the verdict.** §13 explicit: deterministic paths must still operate. A streaming verdict that races with the alert is a regression.
- **A new verdict type.** Four verdicts are already exhaustively tested; adding a fifth creates churn.
- **Replacing `MiniMax-M3` with a different model.** The I1 provenance work is precisely so a future model change doesn't invalidate old annotations. Switching now contradicts that.

## Recommendation

**Implement A, B, C, F in one slice.** That gives:
- I3 usefulness metrics visible on the dashboard (A)
- I1 provenance visible in the operator alert (B)
- Optional AI status integrated into operational_coverage (C)
- A cross-container contract test (F)

D, E, G are valuable but stretch the §13 contract further; they should be separate slices after A/B/C/F prove themselves in PROD.

This keeps the I-series honest: each slice lands a bounded, observable improvement that the operator can verify, rather than chasing ever-fancier AI capabilities.

## Self-corrections during research

1. I almost proposed A + B + C + D in one slice, then realised D is the only one that introduces new annotation logic and a new prompt — it's qualitatively different from the others (operational plumbing, not new capability). Folding them together would mix bounded-contract extension with new-feature introduction; better as two slices.
2. I almost proposed opportunity G as the headline, then realised it's not what the user asked. The user said "how to enrich our system using the AI module" — enrichment is about *visibility* (A, B, C) and *correctness* (D, F), not new internal analytics. Re-prioritised accordingly.
3. I noted that the I1 provenance fields are currently invisible. The fix (opportunity B) is the cheapest of all the opportunities — 10-20 lines — but the user-impact is high (every operator sees which model/prompt produced a verdict). I moved it from "nice-to-have" to "first 4 slice".
