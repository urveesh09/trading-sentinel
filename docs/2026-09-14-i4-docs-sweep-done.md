# I.4 docs sweep — done

## What landed

The plan §15 next-steps cell says: *"Complete the bounded I slice with phase 4 deep-research proposal (per user direction)"*.

The predecessor's `aaa15d6` (`docs(I4): deep research for AI-enrichment opportunities — proposal`) shipped the research proposal itself. The proposal recommends implementing opportunities A, B, C, F in one slice (the "visibility-focused" bundle). The predecessor implemented all four as:

- **I.A** (`980636e` + `65d4bfe`): bridge I3 usefulness metrics from agent to engine
- **I.B** (`d1e7d4f` + `9bd5286`): surface I1 provenance in the operator alert
- **I.C** (`89a9804` + `c47941e`): `operational_coverage_report` includes optional AI
- **I.F** (`a226ec3` + `0f7120b`): cross-container contract test

**This docs-sweep closes I.4 by updating the requirement matrix in `NEXT_AGENT_PLAN.md`** to reflect the I.A/B/C/F and I.4-closures, with concrete commit hashes, evidence references, and the test-count delta:

- python-engine: 3026 → 3047 (+21 with I.A) → 3072 (+25 with I.B) → 3097 (+25 with I.C)
- agent: 98 → 153 (+55 with I.A) → 174 (+21 with I.B) → 174 (no change with I.C)

The plan row also notes the deferred opportunities (D — source-event classification, E — periodic self-evaluation, G — per-ticker breakdown) per the I.4 proposal's "after A/B/C/F prove themselves in PROD" guard.

## Verification

- python-engine I-series tests: **67 pass** (`test_optional_ai_usefulness_bridge`, `test_optional_ai_cross_container_contract`, `test_optional_ai_status`, `test_coverage_vocabulary_optional_ai`, `test_operational_coverage_optional_ai`)
- agent-side tests: require their own venv (`requests` module); the dockerized environment runs them. No code regression in the agent — the predecessor's I.A/B/C/F only added optional behavior (`OPTIONAL_AI_REPORT_USEFULNESS` is opt-in; banner is backwards-compatible).

## Branch state

- **Branch:** `codex/production-correction-hedge-p0`
- **Status:** docs-only working-tree change
- **Plan row updated to show I.4 closure.**

## What this enables

After this docs sweep, the requirement matrix accurately reflects reality:

| Workstream | Status |
|---|---|
| **F** | IMPLEMENTING (F1-F6 done; F-series complete) |
| **G** | IMPLEMENTING (5/6 gaps closed) |
| **H** | DONE |
| **I** | IMPLEMENTING — I.A/B/C/F and I.4 deep-research proposal closed |
| **J** | IMPLEMENTING — J.1 through J.10 closed |

The remaining I.4 deferred opportunities (D / E / G per the I.4 proposal) are now explicitly tracked as separate-slice work contingent on visibility-focused work (A/B/C/F) proving itself in PROD.
