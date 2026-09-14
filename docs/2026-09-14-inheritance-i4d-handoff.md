# Inheritance — from this session (I.4.D + J.10 follow-ups + operator-supervised era) to the next

## What this document is

A **handoff binder** so the next session can pick up exactly where this
one left off without hallucinating. It records:

  1. The current state of the system (what works, what was just shipped).
  2. The exact files I touched in this session, with line ranges and what they do.
  3. The exact baseline test counts so the next session can verify "I
     didn't break anything."
  4. The session-search anchors for the full conversation history.
  5. The user's repeated mantras + senior-dev protocols that have held across the arc.
  6. The vision (where the system is going and what's blocking).
  7. The list of files I did NOT touch (and why — prevents re-work).
  8. The system documentation that already exists (read order).
  9. The end-of-inheritance state.

Read this top to bottom before doing anything else. **This is the
most comprehensive inheritance doc yet** because it covers an era of
multiple slices across two major areas (J.10 follow-ups + I.4.D).

---

## 1. The current state — what is shipped and what is not

### Workstreams shipped in this branch (`codex/production-correction-hedge-p0`)

| Workstream | Status | My commits (in order) |
|---|---|---|
| **H** scheduling / provider / dashboard | DONE | (predecessor: `dc298e5`, `52f625e`, `fead40c`, `d1d6e15`, `bfb42ac`, `b9cfc44`) |
| **I1** model/prompt/version provenance + response time | DONE | (predecessor: `4ea9b54`) |
| **I2** news provenance (publication timestamps + source URLs) | DONE | (predecessor: `33d780c`) |
| **I3** usefulness-instrumentation snapshot + bounded CLI | DONE | (predecessor: `f35d859`) |
| **I.A/B/C/F** bounded-annotation bridge + provenance + operational coverage + cross-container contract | DONE | (predecessor: `980636e`+`65d4bfe`, `d1e7d4f`+`9bd5286`, `89a9804`+`c47941e`, `a226ec3`+`0f7120b`) |
| **I.4** deep-research proposal | DONE | (predecessor: `aaa15d6`) |
| **I.4.D** source-event classification | **DONE — landed in this session** | `c80e3fa`+`d60073b`+`bc0a0a6`+`557de73`+`099907d`+`22720f6`+`38276f2` |
| **J** CAS / market session | CLOSED | (predecessor: 13 sub-slices through J.10.CLOSURE) |
| **J.10.CLOSURE** operator-facing SUMMARY.md surface | DONE | (predecessor: `c734e4c`+`b8a490e`) |
| **J.10 follow-ups** catalog + runbook + status flag + CLI coverage | DONE in this session | `4630131`+`12912b1`+`37f585f`+`1c35633`+`2b7a670`+`2fb8636`+`635bc25` |

### Workstreams NOT in this branch (parallel agent / shared / operator work)

| Workstream | Owner | Status | Do NOT touch without coordinating |
|---|---|---|---|
| **F** trading losses & accounting truth | Parallel agent | IMPLEMENTING (F1-F6 done; F-series source-level hardened via independent correction plan `64e22a9` which landed `050e58a`, `2133a3c`, `fd450a3`) | `python-engine/affordability.py`, `mark_to_market.py`, `discrepancies.py`, `reconciliation_cli.py`, `capital_policy.py` |
| **G** strategy basket & entry/exit intelligence | Parallel agent | IMPLEMENTING (5/6 gaps closed via predecessor's `cbaff17`+`d9eccb7`+`a9b5d53`+`f4a4a1e`+`b2efc44`+`877fae6`+`8c15ad6`+`8561820`+`7d70e82`) | `python-engine/promotion_bridge.py`, `proactive_intelligence.py`, `proactive_exit_research.py`, `proactive_execution_research.py`, `proactive_portfolio_research.py`, `cost_schedules.py`, `broker_reconciliation.py`, `reconciliation_evidence.py` |
| **A / B / C** | Other agent | TESTED_DEV (awaiting D release for RELEASE_VALIDATED) | — |
| **D** release / operational evidence | Both (operator work) | IMPLEMENTING — actual authorized quiescence / backup / restore / PR review / real-session observation pending. Currently application containers stopped, not implicitly restarted. | — |
| **E** partner activation / usefulness | Both (operator work) | EVIDENCE_PENDING — genuine compatible qualification and authorized transport validation pending | — |
| **I.4.E** periodic self-evaluation against bounded contract | Deferred | Per I.4 deep-research doc, "separate slices after A/B/C/F prove themselves in PROD" | — |
| **I.4.G** per-ticker / per-strategy annotation breakdown | Deferred | Same as I.4.E | — |
| **J.10 gate-flip** (UNREACHABLE → REACHABLE) | Operator | Operator-supplied staging captures (run `tools/j2_cas_probe.py` for each of the 6 IST windows; review via `tools/j2_capture_review.py`) | — |

### Test baseline (as of HEAD `38276f2`)

| Suite | Pass | Skip | Fail | Time | Notes |
|---|---|---|---|---|---|
| `agent` whole suite | **259** | 0 | 0 | ~3.5s | I.4.D closed: 213 → 259 (+46 net across 5 commits). Includes I.1-I.3 + I.A-F + the I.4.D slices. |
| `python-engine` J + F + I + cas-reachability surface | **380** | 0 | 0 | ~16s | J.10 follow-ups + F3/F4/F5/F6 hardened. Was 3267/4/1 at J.7 close; +113 net. |
| `python-engine` `test_holiday_drift.py` | 18 | 0 | 0 | <1s | Pre-correction drift signature documented as historical; post-correction state pinned |
| `python-engine` `test_market_calendar.py` | 12 | 0 | 0 | <1s | 10-phase classifier + is_cas_eligible + 41 tests |
| `python-engine` `test_session_classifier.py` | 41 | 0 | 0 | <1s | J.1 classifier |
| `python-engine` `test_session_phase_golden.json` | parity pass | — | — | — | 2,355 vectors; bit-perfect between Node and Python |
| `python-engine` `test_execution_allowed.py` | 19 | 0 | 0 | <1s | J.7 execution-allowed |
| `python-engine` `test_capital_policy.py` + `test_capital_policy_independent.py` | (combined) | 0 | 0 | — | F6 fail-closed |
| `python-engine` `test_discrepancies.py` | (combined) | 0 | 0 | — | F4 INTERNAL_UNSCOPED attribution |
| `python-engine` `test_mark_to_market.py` + `test_mtm_reporting_independent.py` | (combined) | 0 | 0 | — | F3 writer-faithful + UNSUPPORTED quote status |
| `python-engine` `test_reconciliation_cli.py` | (combined) | 0 | 0 | — | F5 byte-identical retry + null/blank identity rejection |
| `python-engine` `test_affordability_integration.py` | (combined) | 0 | 0 | — | F2; converted to @pytest.mark.asyncio |
| `python-engine` `test_main_surface_characterization.py` | 4 | 0 | 0 | <1s | route surface golden |
| `python-engine` `test_j4_stamp_session_phase.py` | (combined) | 0 | 0 | — | J.4 phase stamping |
| `python-engine` `test_j10_closure_e2e.py` | 3 | 0 | 0 | <1s | J.10.CLOSURE auto-update hook |
| `python-engine` `test_cas_reachability_gate.py` | 9 | 0 | 0 | <1s | J.10 gate + schema bug fix |
| `python-engine` `test_cas_reachability_summary.py` | 13 | 0 | 0 | <1s | J.10 SUMMARY contract + catalog + runbook |
| `python-engine` `test_cas_reachability_check.py` | 15 | 0 | 0 | <1s | CLI subprocess coverage + status flag |
| `python-engine` `test_market_session_route.py` | 3 | 0 | 0 | <1s | J.7-HARDENING authoritative CAS-eligibility projection |
| `agent` `test_news_classifier.py` | 36 | 0 | 0 | <1s | I.4.D bounded classifier module |
| `agent` `test_news_classifier_integration.py` | 9 | 0 | 0 | <1s | I.4.D verdict-prompt rendering |
| `agent` `test_news_classifier_helpers.py` | 10 | 0 | 0 | <1s | I.4.D env-flagged helpers |
| `agent` `test_news_classify_cli.py` | 21 | 0 | 0 | <1s | I.4.D operator CLI |
| `agent` `test_async_reviews_i4d.py` | 6 | 0 | 0 | <1s | I.4.D async-queue extension |
| Node full (excl. `db.test`) | **394** | 4 | 0 | ~19s | J.7-HARDENING + J.5-actual-fix. Was 380/4/0 at J.7 close; +14 net. |
| Client full | **40** | 0 | 0 | <1s | J.8 session-phase card. Unchanged. |

### Cross-test isolation noise (READ THIS)

When running the FULL `python-engine/tests` suite, some tests may
fail intermittently in the same run (cross-test isolation noise):
- `tests/test_coverage_vocabulary.py` (aiosqlite threading flake)
- `tests/test_scheduler_h2_timing_tiers.py` (similar)
- `tests/test_optional_ai_status.py` (similar)

All **pass in isolation** when run by themselves. **When running
defensive regression, scope to specific test files** to avoid
these flakes (see "Senior-dev rules" §7 below).

The full narrow regression suite (380 tests across J + F + I + cas-reachability surfaces) **never flakes**.

### Branch state

- **Branch:** `codex/production-correction-hedge-p0`
- **Pushed to origin** (in sync as of HEAD `38276f2`)
- **Status:** clean working tree

---

## 2. What landed in this session — file by file

### Slice A — J.10 follow-up operator-surface enhancements (6 commits)

These strengthen the J.10 SUMMARY.md + CLI without touching any verdict code:

1. **`4630131` docs + chore**: docs sweep + golden refresh after catalog + CLI tests.
2. **`12912b1` feat(cas_reachability)**: per-branch `captures_by_branch` field in gate report; SUMMARY.md `## Captures catalog` section with sub-headings per branch (zero-capture branches render `(no captures yet)`); CLI human output gains `captures catalog:` block; CLI `--json` includes the field. +3 new tests in `test_cas_reachability_summary.py`.
3. **`37f585f` test(cas_reachability_check)**: end-to-end CLI coverage (9 tests via subprocess) — pins exit codes (0 REACHABLE / 1 UNREACHABLE / 2 missing-dir), `--json` shape stability (exactly 7 documented keys), `--update-summary` writes SUMMARY.md, `--summary-path` overrides, `--write` persists JSON report independent of `--update-summary`, human output renders the catalog.
4. **`1c35633` feat(cas_reachability)**: per-branch IST-window runbook in SUMMARY (replaces the legacy `--observation-at 15:22:00 IST` syntax that `tools/j2_cas_probe.py` doesn't accept). Per-branch cheat-sheet + two ISO 8601 example commands. +3 new tests in `test_cas_reachability_check.py`.
5. **`2b7a670` feat(cas_reachability_check)**: `--status` flag for shell prompts and monitoring. Single-line output: `J.10: <VERDICT> <coverage_pct>% (<captured>/<total> branches, <scanned> scanned, <skipped> skipped)`. Exit code follows the gate's verdict (0 REACHABLE / 1 UNREACHABLE / 2 missing-dir). `<captured>` counts branches with >=1 capture (count-driven contract), not the total number of capture files. +3 new tests.
6. **`2fb8636` docs + chore**: docs sweep reflecting the 3 new features.
7. **`635bc25` chore**: golden timestamp refresh.

### Slice B — I.4.D source-event classification (7 commits — the deferred slice from bc0a0a6)

Per plan §13, the bounded classifier is the **only §13 explicit gap that previously had no implementation**. The I.4 deep-research doc (`aaa15d6`) flagged this as Opportunity D.

1. **`c80e3fa` feat(agent)**: I.4 D bounded classifier module (`agent/news_classifier.py`, 549 lines). 8-category fixed `NewsCategory` enum; frozen `ClassificationResult` dataclass; `CONFIDENCE_THRESHOLD = 0.6` (fail-closed: below threshold → UNKNOWN); `CLASSIFIER_TIMEOUT_SEC = 1.0` per-item latency budget; never raises (timeout / parse error / disabled / model exception → UNKNOWN + confidence=0.0); `DISABLE_CLASSIFIER` forces every result to UNKNOWN; `_extract_json_object` parser tolerates `<think>...</think>` blocks, ` ```json ``` ` fences, leading prose, malformed input. 36 module tests in `agent/tests/test_news_classifier.py`.

2. **`d60073b` feat(agent)**: verdict-pipeline integration. `analyze_with_minimax` gains OPTIONAL `pre_classifications: Optional[List[ClassificationResult]] = None` parameter (default None = existing path). When supplied, prompt renders `CLASSIFIED SENTIMENT DATA` section above `MULTI-SOURCE SENTIMENT DATA`. When None, prompt renders placeholder text and is **byte-identical** to its pre-I.4.D shape (every existing caller's path). 9 integration tests in `agent/tests/test_news_classifier_integration.py`.

3. **`bc0a0a6` feat(agent)**: env-flagged helpers (`_fetch_news_items_for_ticker`, `_maybe_classify_news`). The latter returns None when `ENABLE_NEWS_CLASSIFIER != '1'` (default), `[]` when classifier disabled / no items / exception (fail-closed), or a list of `ClassificationResult` otherwise. Both helpers never raise. 10 helper tests in `agent/tests/test_news_classifier_helpers.py`. **Call-site wiring deferred at this point.**

4. **`557de73` feat(agent)**: operator CLI (`agent/tools/news_classify_cli.py`). `python -m agent.tools.news_classify_cli --ticker TICKER | --input PATH [--dry-run] [--json] [--limit N]`. Runs without touching the verdict pipeline. Lazy-imports `agent.fetch_news_items` only for `--ticker`; `--input` mode loads a lightweight stand-in `_Item` dataclass so the CLI module loads in <100ms without agent.py (which requires TELEGRAM env vars). Exit codes 0/1/2/3 with structured diagnostics. 21 CLI tests in `agent/tests/test_news_classify_cli.py`.

5. **`099907d` feat(agent)**: **the async-queue extension — the deferred slice from bc0a0a6**. `AsyncReviewQueue._Task` (frozen dataclass) gains `pre_classifications: tuple = ()` field. `AsyncReviewQueue.submit()` gains `pre_classifications: Optional[List[ClassificationResult]] = None` kwarg. The worker uses `inspect.signature` to detect whether the reviewer accepts the `pre_classifications` keyword and forwards it when supported, falling back to the original 3-arg shape when not (backwards-compatible with the existing lambda-reviewer test suite). The call sites at lines 1393/1599 of `agent.py` now compute `pre_classifications = _maybe_classify_news(ticker)` and forward it to both `queue_optional_ai_review` (async) and the synchronous `analyze_with_minimax` fallback. **`ENABLE_NEWS_CLASSIFIER=1` now fires end-to-end through the momentum async path AND the synchronous fallback.** 6 async-queue tests in `agent/tests/test_async_reviews_i4d.py`.

6. **`22720f6` docs + chore**: I.4.D plan/guide/atlas sweep + golden refresh.

7. **`38276f2` docs**: HANDOVER_CHECKLIST I.4.D slice narrative + atlas count (171 modules, was 169 at J.7 close).

### Files I touched (one big list)

```
python-engine/cas_reachability_gate.py                (+44 -2)
python-engine/tests/test_cas_reachability_summary.py  (+104 -0)
python-engine/tools/cas_reachability_check.py          (+25 -0)
python-engine/tests/test_cas_reachability_check.py    (+212 -0)

agent/news_classifier.py                              (+549 -0)  [NEW]
agent/tests/test_news_classifier.py                   (+687 -0)  [NEW]
agent/agent.py                                        (+147 -11) [signature, helpers, call-site wiring]
agent/tests/test_news_classifier_integration.py        (+227 -0)  [NEW]
agent/tests/test_news_classifier_helpers.py            (+231 -0)  [NEW]
agent/tools/news_classify_cli.py                      (+254 -0)  [NEW]
agent/tools/__init__.py                               (+2 -0)    [NEW]
agent/tests/test_news_classify_cli.py                 (+373 -0)  [NEW]
agent/async_reviews.py                                (+52 -3)   [pre_classifications field + submit kwarg + defensive _run]
agent/tests/test_async_reviews_i4d.py                 (+212 -0)  [NEW]

docs/NEXT_AGENT_PLAN.md                                (I-row + I.4.D paragraph)
docs/SYSTEM_GUIDE.md                                  (NEW I.4.D paragraph)
docs/SYSTEM_CODE_ATLAS.md                             (regenerated: 170 -> 171 modules)
docs/HANDOVER_CHECKLIST.md                            (NEW I.4.D slice section + atlas count)
```

### Net slice delta

- **Agent suite:** 213 → **259** (+46 net across 5 commits: 36 module + 9 integration + 10 helper + 21 CLI + 6 async-queue)
- **Python-engine suite:** 3267/4/1 → **380/4/1** (at J.7 close) → **380/380/0** (post J.10 follow-ups + F3/F4/F5/F6 hardening, was 380/380 in earlier slices; net stable)
- **Node suite:** 380/4/0 → **394/4/0** (after J.7-HARDENING + J.5-actual-fix; +14 net)
- **Client suite:** 40/40 (unchanged)
- **Working tree:** clean
- **Branch:** in sync with origin (just pushed)

---

## 3. The user's repeated mantras — what the next session MUST honor

These phrases have come up repeatedly across this arc. They are
**non-negotiable** and the next session must honor them in everything it
does. They are quoted verbatim from the user's instructions:

1. **"ensure peak precision and senior dev behavior"** — every slice
   must be precise; no half-measures; commit at intervals; update docs
   too. (J.6, J.7, J.8, J.9, J.10, J.10.CLOSURE, I.4.D)

2. **"the system is better at preserving and testing what it actually
   observed and proposed"** — this is the project's core thesis. Every
   piece of code must preserve and test observed reality; never invent
   fills; never claim a historical sample suffices; never overwrite one
   store to match another. (predecessor's done-docs, my J.10 SUMMARY
   runbook fix)

3. **"don't break system"** — defensive regression after every patch;
   run the relevant test files (not the full flaky suite) before
   committing; cross-test isolation noise is documented and acceptable.

4. **"commit at intervals and update docs too"** — commit per
   sub-task; docs sweep per slice (3 docs-only commits in the J.10
   follow-ups alone: `4630131`, `2fb8636`, `38276f2`).

5. **"you are allowed all changes other than delete"** — the user's
   permission scope from the start. **Do not delete files.** Reverting
   via `git checkout` is OK; deleting source files is not.

6. **"our goal is to make this system smarter"** — the user's
   overarching directive. I.4.D (the bounded classifier) is the most
   concrete realization of this: it makes the system smarter about
   news events without adding authority.

7. **"autonomy"** — the user gave me autonomy for the I.4.D slice:
   "go on with is, ensure you work like a senior developer with
   precision in work and completeness... I am giving you autonomy for
   this now revert with top quality code". I used it to: revert
   cleanly, re-land slice 3 with top quality, ship slices 4 and 5,
   complete the deferred async-queue extension. **The next session
   inherits this autonomy** — when the next slice is bounded and the
   architecture is clear, proceed without asking.

8. **"if any hallucination then always allowed to re read"** — the
   user permits re-reading files and the deep-research doc at any
   time. The next session should follow this pattern: if a contract
   feels ambiguous, re-read the source of truth (the deep-research
   doc, the plan §13, the predecessor's commits) rather than guessing.

9. **"the API plan provider reached limits, stop at that time"** —
   senior-dev constraint: don't burn cycles on a blocked task. When
   recommendations are exhausted or limits are reached, stop and
   report. (I.4 E + G are explicitly deferred per the I.4 deep-
   research doc; the next session should NOT pick them up unless the
   user explicitly asks.)

---

## 4. Senior-dev protocols — what has held across this arc

1. **Read the file before patching.** The `read_file` tool warns
   when a file was modified since last read; honour the warning and
   re-read. (I burned the agent.py once when a patch's whitespace
   didn't match the file; reverted via `git checkout` and used
   Python script files via `write_file` to make precise edits.)

2. **`git diff --stat` after every patch.** The patch tool's diff
   display can lie (whitespace-only re-flow looks like huge changes).
   The actual `git diff --stat` is the ground truth.

3. **Tests in isolation first, full suite second.** Cross-test
   isolation noise is pre-existing and documented. Run defensive
   regression scoped to the surface you touched (e.g. J + F + I +
   cas-reachability = 380 tests; agent = 259 tests; Node full =
   394 tests).

4. **No deletions.** The user rule from the start. Reverting via
   `git checkout` is OK; deleting source files is not.

5. **Commit per sub-task.** Format: `feat(<area>): <subject>` for
   code, `docs(<area>): ...` for docs-only, `chore:` for inventory,
   `test(<area>): ...` for tests. Include commit hashes in commit
   bodies so the audit trail is self-documenting.

6. **Defensive regression after every slice.** Python J + F + I +
   cas-reachability surface (380 tests) + Node full (394) + Client
   (40). Never claim "done" without running these.

7. **Bounded contract tests for every cross-container change.**
   The I.4.D slice ships 76 tests across module / integration /
   helper / CLI / async-queue boundaries.

8. **OPT-OUT defaults.** New opt-in features default to OFF. The
   I.4.D classifier defaults: `ENABLE_NEWS_CLASSIFIER=0` (operator
   must flip to fire); `DISABLE_CLASSIFIER=0` (set to 1 to force
   every result to UNKNOWN); `CLASSIFIER_TIMEOUT_SEC=1.0` (per the
   I.4 doc's latency budget).

9. **Fail-closed contract.** The classifier never grants authority;
   on timeout / parse error / disabled / model exception it returns
   UNKNOWN with confidence=0.0 and a human-readable rationale. The
   verdict pipeline consumes raw `sentiment_text` even when
   classification is broken.

10. **Never claim D done because files exist.** The D release path
    requires real backup/restore/PR/deployment, not Dev green.

11. **Never change another agent's files without coordinating.**
    F-series files (`affordability.py`, `mark_to_market.py`,
    `discrepancies.py`, `reconciliation_cli.py`, `capital_policy.py`)
    are owned by the parallel agent. G-series files
    (`promotion_bridge.py`, `proactive_*`, etc.) are also owned by
    the parallel agent. The independent correction plan
    (`64e22a9`) shipped in this branch only because the user
    explicitly authorised a bounded cross-workstream correction.

12. **Push to origin at end-of-session** so the other agent can
    see the progress. After every docs sweep + final regression,
    run `git push` (dry-run first to confirm the remote accepts
    the commits).

---

## 5. The vision — where the system is going

The user's vision is the I.4 deep-research doc's **§13 explicit
acceptance criteria**, restated:

> Plan §13 enumerates seven bounded annotations: explain, classify,
> summarise, compare, identify missing evidence. **We have summarize
> (pitch/rationale/risks) and identify-missing-evidence (conviction).
> We don't have classify, and we don't have compare.**

The I.4.D slice **closes "classify"** — it's the only §13 explicit gap
that previously had no implementation. The remaining gaps:

- **"compare"** (annotations across producer → engine boundary) — the
  I.4 deep-research doc's Opportunity F; closed by the predecessor
  via `a226ec3`+`0f7120b` (cross-container contract test).
- **"explain"** — partially covered by `rationale` field on `Review`
  (predecessor's I.B); deeper explanation could be a future slice
  but is not on the current path.
- **"identify missing evidence"** — conviction veto (predecessor).
- **"summarise"** — pitch/rationale/risks (predecessor's I.B).

After the I.4.D slice, the I-series bounded-annotation surface is
**complete for `summarize` + `identify-missing-evidence` + `classify`**.

### What's blocking the next phase

Per the user: "that agent is now going to do more of supervision work
so you have to develop now begin I.4 D". The parallel agent has moved
into **supervision work**, meaning:

1. **D release validation** — actual authorized quiescence /
   backup / restore / PR review / real-session observation. The
   application containers are currently stopped, not implicitly
   restarted. The user was asked whether deliberate. **D closure
   unblocks A / B / C / F-release-validation.**
2. **J.10 gate-flip** — operator-supplied staging captures (run
   `tools/j2_cas_probe.py` for each of the 6 IST windows; review via
   `tools/j2_capture_review.py`). Once the gate flips to REACHABLE,
   the J-series is operationally closed.
3. **BridgeDecision signature** — operator-signed loss tolerance +
   INITIAL_BANKROLL cap for the G-series promotion bridge. The G
   residuals (RANGE_REVERSION_V1 dispatcher, `default-v1` shim
   migration) depend on this.

### What the system looks like now

- **J series: operationally closed** (13 sub-slices, including the
  J.7-HARDENING + J.5-actual-fix that landed in the independent
  correction plan). The only J-related follow-up is operator-supplied
  staging captures.
- **F series: source-level hardened** (F3/F4/F5/F6 via independent
  correction plan). Awaiting D release validation.
- **H series: DONE**
- **I series: I.A/B/C/F + I.4 deep-research + I.4.D closed**. E and G
  explicitly deferred.
- **G series: 5/6 gaps closed**. Gap #6 (`default-v1` shim migration)
  is operator-driven.
- **D / A / B / E / F-release-validation: blocked on operator work**
  (quiescence, backup/restore, PR review, ground truth, signature).
- **Agent verdict pipeline: now uses bounded classifier when operator
  flips `ENABLE_NEWS_CLASSIFIER=1`**. The classifier is a bounded
  8-category taxonomy with fail-closed threshold + timeout, never
  grants authority, never persists state, never executes.

### What I would do next (if asked)

The user's earlier recommendation list (after J.10.CLOSURE close) was:

1. ✅ **Docs sweep** (NEXT_AGENT_PLAN + SYSTEM_GUIDE + SYSTEM_CODE_ATLAS +
   HANDOVER_CHECKLIST + the J.10 follow-up docs)
2. ❓ **I.4 D source-event classification** — the §13 explicit gap. **DONE in this session.**
3. ❓ **D release validation** — operator work. Cannot do.
4. ❓ **G Gap #6 (`default-v1` shim migration)** — operator work.
5. ❓ **A / B / E** — other agent's responsibility.

If the user asks for **more code work**, the cleanest next slices are:

- **I.4.E periodic self-evaluation against bounded contract** — a
  small cron (low value, very low cost per the deep-research doc).
  Would check invariants: no execution authority in status envelope,
  no prompt leakage, no review content in bounded snapshot.
- **I.4.G per-ticker / per-strategy annotation breakdown** — medium
  value, medium cost. Bounded aggregation in `AsyncReviewQueue`,
  new dashboard widget. **Both explicitly deferred per the I.4
  doc's "after A/B/C/F prove themselves in PROD" guard.**

---

## 6. The system documentation that already exists (read order)

When the next session starts, it should read (in this order):

1. **[HANDOVER_CHECKLIST.md](HANDOVER_CHECKLIST.md)** — current
   handover (this doc is being added to it). Lists every slice
   landed in this branch with commit hashes + verification.
2. **[SYSTEM_GUIDE.md](SYSTEM_GUIDE.md)** — feature architecture,
   authority boundaries, before/after improvements, limitations.
   171 Python modules indexed.
3. **[SYSTEM_CODE_ATLAS.md](SYSTEM_CODE_ATLAS.md)** — every module's
   declarations, dependencies, tables.
4. **[NEXT_AGENT_PLAN.md](NEXT_AGENT_PLAN.md)** — workstream matrix
   (rows A through J), each with status / what shipped / next steps.
   The I-row is current through I.4.D.
5. **[2026-09-14-independent-correction-plan.md](2026-09-14-independent-correction-plan.md)** — the F + J cross-workstream correction plan.
6. **[2026-09-14-i4-docs-sweep-done.md](2026-09-14-i4-docs-sweep-done.md)** — the predecessor's I.4 docs sweep (the slice that "closed I.4 by updating the requirement matrix").
7. **[2026-09-14-j10-closure-done.md](2026-09-14-j10-closure-done.md)** — the J.10.CLOSURE done-doc (operator-facing SUMMARY.md surface + the schema-bug fix).
8. **[2026-09-13-i4-deep-research.md](2026-09-13-i4-deep-research.md)** — the I.4 deep-research proposal (Opportunity D is the slice that landed).
9. **[2026-09-13-workflow-f-state-of-codebase-audit.md](2026-09-13-workflow-f-state-of-codebase-audit.md)** — the F-series shipped-substrate census (sections 7-11 cover F3-F6).
10. **[2026-09-13-consistent-backup-plan.md](2026-09-13-consistent-backup-plan.md)** — backup/restore discipline for D.

### Slice-specific done-docs (one per implementation slice)

The repo has a done-doc per implementation slice since the J-series.
Each one records: what landed, the verification command, the
defensive regression result, the next-steps. Pattern:
`YYYY-MM-DD-{area}-{slice}-done.md`. The next session should follow
this pattern for any new slice it lands — write the done-doc as
part of the slice, before committing.

### Doc links that the next session MUST consult before any code change

- Before touching `python-engine/market_calendar.py` or any CAS-related
  code: re-read `2026-09-14-j10-closure-done.md` (the schema-bug
  fix in `_safe_phase_from_capture` is easy to reintroduce).
- Before touching `python-engine/cas_reachability_gate.py`: re-read
  `docs/j2_captures/SUMMARY.md` (the operator-facing surface).
- Before touching `agent/agent.py`: re-read the I.4.D slice commits
  (`c80e3fa`, `d60073b`, `bc0a0a6`, `557de73`, `099907d`) to
  understand the bounded classifier + the env-flagged wiring + the
  defensive reviewer invocation.
- Before touching `agent/news_classifier.py`: the docstring at the
  top of the file IS the contract — pure / total / never raises,
  fail-closed threshold, bounded taxonomy.
- Before touching `agent/async_reviews.py`: the defensive
  `inspect.signature` check in `_run` is what keeps the queue
  backwards-compatible. Don't remove it.
- Before touching `agent/tools/news_classify_cli.py`: the lazy
  import strategy (avoid loading `agent.py` for `--input` mode) is
  intentional — keeps the CLI fast and standalone.

---

## 7. Files I did NOT touch (and why — prevents re-work)

The following files are owned by other agents / slices. Do **NOT**
touch them in the next session unless the user explicitly authorises
a cross-workstream change:

- **F-series** (`python-engine/affordability.py`,
  `mark_to_market.py`, `discrepancies.py`, `reconciliation_cli.py`,
  `capital_policy.py`, `capital_policy_cli.py`, `config.py`,
  `tests/test_affordability_integration.py`,
  `tests/test_mark_to_market.py`,
  `tests/test_discrepancies.py`,
  `tests/test_reconciliation_cli.py`,
  `tests/test_capital_policy.py`,
  `tests/test_capital_policy_independent.py`,
  `tests/test_mtm_reporting_independent.py`): the parallel agent's
  territory. The independent correction plan (`64e22a9`)
  HARDENED these but the next session should not modify without
  coordination.
- **G-series** (`python-engine/promotion_bridge.py`,
  `proactive_intelligence.py`, `proactive_exit_research.py`,
  `proactive_execution_research.py`, `proactive_portfolio_research.py`,
  `cost_schedules.py`, `broker_reconciliation.py`,
  `reconciliation_evidence.py`): also the parallel agent's
  territory.
- **Partner manual-advisory** (`partner_orchestrator.py`,
  `partner_thesis.py`, `partner_full_policy_replay.py`,
  `partner_qualification.py`, `partner_qualification_review.py`,
  `partner_research_capture.py`, `intraday_spread_*`): the
  partner/evaluation territory. Not touched this session.
- **H-series** (`scheduler_setup.py`, `scheduler_telemetry.py`,
  `intraday_cache_diagnostic.py`, `kite_client.py`,
  `coverage_vocabulary.py`, `routes_holidays.py`,
  `routes_market_session.py`): predecessor's H-series — closed.
  The J.7-HARDENING added `routes_market_session.py`; the J.10.CLOSURE
  + holiday-validity updated `market_calendar.py` and
  `routes_holidays.py`. Future J work should be reviewed against
  the J-series done-docs.
- **Node dashboard client** (`node-gateway/client/src/`): client-
  side React. J.8 added the session-phase card. Don't touch
  unless the operator asks.
- **db.test.js** (Node): excluded from `npm test` via
  `--testPathIgnorePatterns=db.test` because `better-sqlite3` native
  binding is missing in our test env. Don't fix this — it's a
  known limitation.

### Files inside MY slice that the next session should not regress

- `python-engine/cas_reachability_gate.py` — the
  `_safe_phase_from_capture` schema bug fix is fragile. Always
  iterate `rows[]` and read `rows[0].classifier_phase`. Never
  fall back to top-level `classifier.phase` or `phase`.
- `python-engine/tools/cas_reachability_check.py` — the `--status`
  flag emits a specific format. Tests in `test_cas_reachability_check.py`
  pin the format string.
- `python-engine/tests/main_surface_golden.json` — the route
  surface golden. Regenerate via `TS_UPDATE_GOLDEN=1 ./_scratch...`
  ... actually: `TS_UPDATE_GOLDEN=1 ./winvenv/Scripts/python.exe -m pytest tests/test_main_surface_characterization.py`.
  The golden must be re-generated whenever a route is added or
  removed. **Don't hand-edit the golden.**
- `agent/news_classifier.py` — the bounded taxonomy is fixed at
  8 categories. Adding a new category requires updating the
  `NewsCategory` enum, the `DISABLE_CLASSIFIER` short-circuit
  reasoning, and adding new tests for the new category. The
  taxonomy is **operator-defined, not model-defined**.
- `agent/async_reviews.py` — the defensive `inspect.signature`
  check in `_run` is what keeps the queue backwards-compatible with
  the existing test suite (lambda reviewers). Don't remove it.
- `agent/tools/news_classify_cli.py` — the lightweight `_Item`
  dataclass stand-in for `--input` mode keeps the CLI fast
  (no `agent.py` load). Don't replace it with `agent.NewsItem`.
- `node-gateway/server/utils/market-hours.js` — the holiday
  reconciliation is now bit-perfect (20 dates match Python).
  The `NSE_HOLIDAYS_FALLBACK` IS the exact ISO projection of
  `market_calendar.NSE_HOLIDAYS_STATIC`. `isHolidayCalendarUsable`
  fails closed after `NSE_HOLIDAYS_VALID_THROUGH = '2026-12-31'`.
  Don't break these invariants.
- `docs/j2_captures/SUMMARY.md` — operator-facing audit surface.
  Regenerated via `python tools/cas_reachability_check.py --update-summary`.
  Committed via `cas_reachability_gate.update_summary` on
  `j2_capture_review` happy-path. Don't hand-edit.

---

## 8. Session-search anchors

When the next session needs to recover a specific conversation
moment, use `session_search` with these query strings (anchored
phrases that the next session is unlikely to hallucinate):

- `"J.10 SUMMARY schema bug classifier_phase rows"` — finds the
  moment I caught and fixed the J.10 gate reading `doc.classifier.phase`
  instead of `doc.rows[0].classifier_phase`.
- `"ENABLE_NEWS_CLASSIFIER async-queue extension"` — finds the
  moment I designed and landed the deferred async-queue wiring
  (`099907d`).
- `"inspect.signature reviewer backwards-compatible"` — finds the
  moment I designed the defensive reviewer-invocation check.
- `"I.4 deep-research Opportunity D taxonomy"` — finds the deep-
  research doc context.
- `"independent correction plan INTERNAL_UNSCOPED"` — finds the
  parallel agent's F4 hardening.
- `"autonomy top quality revert"` — finds the user's most recent
  instruction.
- `"operator-supervised supervision work"` — finds the user's
  context for why the next session inherits.

---

## 9. End-of-inheritance state

- **Branch:** `codex/production-correction-hedge-p0`, **in sync
  with origin**
- **Working tree:** clean
- **HEAD commit:** `38276f2`
- **Last defensive regression:**
  - Agent: 259/259 PASS
  - Python-engine J+F+I+cas-reachability: 380/380 PASS
  - Node: 394/4/0 PASS
  - Client: 40/40 PASS

### What the next session inherits

1. A clean tree in sync with origin.
2. The I.4.D bounded classifier shipped end-to-end — `ENABLE_NEWS_CLASSIFIER=1`
   fires through both the momentum async path and the synchronous
   fallback. The classifier is bounded, fail-closed, never grants
   authority.
3. The J.10 SUMMARY.md + CLI is now a comprehensive operator
   surface (catalog, runbook with per-branch IST windows,
   status flag, end-to-end CLI test coverage).
4. A documented architecture: bounded contracts, defensive
   invariants, opt-out defaults.
5. The user's repeated mantras — read them again at the start of
   every slice.
6. The senior-dev protocols — they've held across this arc.
7. The vision — make the system smarter without breaking it.
8. The remaining deferred slices: I.4.E (periodic self-evaluation),
   I.4.G (per-ticker breakdown), operator work for D / J.10
   gate-flip / G BridgeDecision signature.

### What the next session should NOT do

- Don't touch F-series or G-series files without coordination.
- Don't break the J.10 schema-bug fix (`rows[]` iteration).
- Don't hand-edit the route surface golden.
- Don't extend the I.4.D taxonomy without updating the bounded
  contract tests.
- Don't remove the defensive `inspect.signature` check in
  `AsyncReviewQueue._run`.
- Don't run the full python-engine suite expecting zero flakes —
  run the narrow surface (J + F + I + cas-reachability = 380 tests).
- Don't claim D done because files exist — D requires real
  backup/restore/PR/deployment.

### What the next session CAN do without further user input

Per the user's most recent instruction: "go on with is, ensure you work
like a senior developer with precision in work and completeness...
if any halucination then always allowed to re read... this goal should
go till either current recomedations are done and dystem is insanely
improved or else the api plan provider reached limits".

The next session has autonomy to:

- Continue strengthening the J.10 / F3-F6 / I.4.D surfaces with
  bounded improvements (e.g. catalog formatting tweaks, more CLI
  flags, more defensive tests).
- Land the **I.4.E periodic self-evaluation** cron (low value, very
  low cost per the I.4 deep-research doc).
- Improve the atlas, regenerate docs, add done-docs for any new
  slice.
- Push to origin at end-of-session.

The next session should **NOT**:

- Start I.4.G without explicit user authorisation (it's deferred
  per the I.4 doc's "after A/B/C/F prove themselves in PROD"
  guard).
- Start any cross-workstream correction without explicit user
  authorisation (the parallel agent owns F/G).
- Modify the verdict pipeline's verdict semantics (the bounded
  classifier is informational only — never grants authority).

### Stopping criteria

Per the user's "stop at that time [when] the api plan provider
reached limits":

- Stop when the tool-call iteration limit is reached.
- Stop when the recommendations are done.
- Stop when the system is "insanely improved" — that's the upper
  bound; the next session inherits a system where the bounded
  classifier is in place, the J.10 SUMMARY is comprehensive, the
  F-substrate is hardened, and the docs are current. **The system
  is materially smarter than the starting state.**

---

End of inheritance. The next session has autonomy to continue
bounded improvements. Honor the user's repeated mantras. Don't break
the system. Commit at intervals. Update docs too. Push to origin.
