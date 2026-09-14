# J.2 — CAS eligibility list + broker-behaviour probe

You are continuing Workstream J of the trading-sentinel system. The
prior session shipped J.1 (CAS-aware session classifier) on branch
`codex/production-correction-hedge-p0` at commit `63a98ab`. Your job
is J.2: populate the Phase 1 F&O eligibility list and ship the
broker-behaviour probe procedure.

---

## Step 1 — read these files before touching any code

  1. `docs/2026-09-13-inheritance-j2-handoff.md` — the full handoff
     binder. Read it top to bottom before doing anything else.
  2. `docs/2026-09-13-workflow-j-deep-research.md` — verified NSE/BSE
     facts (CAS Phase 1 effective 2026-01-19, index-futures CAS-
     aligned band effective 2026-09-07).
  3. `docs/2026-09-13-workflow-j-classifier-plan.md` — J.1 plan slice
     with acceptance and rollback.
  4. `docs/2026-09-13-workflow-j-classifier-done.md` — J.1 post-
     commit summary.
  5. `python-engine/market_calendar.py` — read lines 1-50 (the
     constants block) and lines 250-460 (the classifier +
     `is_cas_eligible`). Do not refactor anything outside this
     region.
  6. `python-engine/tests/test_session_classifier.py` — the 41 tests
     that define the bounded contract.

## Step 2 — verify the J.1 baseline before writing anything

Run:

```bash
cd /c/Users/Urveesh/Desktop/trading-sentinel/python-engine
./winvenv/Scripts/python.exe -m pytest \
  tests/test_session_classifier.py \
  tests/test_session_phase_placeholder.py \
  tests/test_market_calendar.py \
  tests/test_calendar_gates.py -q
```

You should see **61 tests pass**. If any fail, stop and report — do
not attempt to "fix" them.

Also verify `git status` is clean and `git log -3` shows the J.1
commits.

## Step 3 — senior-dev rules (NON-NEGOTIABLE)

  1. **Read the file before patching.** If the patch tool warns
     "file was modified since last read", re-read it before
     patching.
  2. **`git diff --stat` after every patch.** The patch tool's
     diff display can lie about scope (whitespace re-flow looks
     like huge changes). The actual `git diff --stat` is the
     ground truth.
  3. **Tests in isolation first, full suite second.** Cross-test
     isolation noise is pre-existing and documented in the
     handoff doc.
  4. **No deletions.** All work is additive.
  5. **Commit per sub-task.** `feat(J.2.PART): <subject>` for code,
     `docs(J.2.PART): ...` for docs-only, `chore:` for inventory.
  6. **Post-commit summary doc for every implementation commit.**
  7. **Bounded contract tests for every change.** If you add an
     eligibility list, the allow-list is a frozen set at the top
     of the test file.
  8. **Opt-in defaults.** Any new flag defaults to OFF; rollback
     is one env var.
  9. **Never claim D done.** The D release path requires real
     backup/restore/PROD deployment, not Dev green.
  10. **Never change another agent's files without coordinating.**
      F-series files (`promotion_bridge.py`,
      `proactive_intelligence.py`, `affordability.py`,
      `mark_to_market.py`, `discrepancies.py`,
      `reconciliation_cli.py`, `capital_policy.py`,
      `cost_schedules.py`, `broker_reconciliation.py`,
      `reconciliation_evidence.py`, `proactive_exit_research.py`,
      `proactive_execution_research.py`,
      `proactive_portfolio_research.py`) are owned by the
      parallel agent.

## Step 4 — J.2 scope

The deep-research and handoff docs already spell out the full plan.
Summary:

### Part 1 — CAS eligibility list

Add `CAS_PHASE1_FNO_UNDERLYINGS: tuple[str, ...] = ()` to
`python-engine/config.py` (default empty, operator-populated).
Wire `is_cas_eligible(symbol)` in `python-engine/market_calendar.py`
to consult the list (case-insensitive, whitespace-stripped match).

Tests in `test_session_classifier.py` covering:

  - Empty list returns False for any symbol.
  - Symbol in list returns True.
  - Case-insensitive match (`RELIANCE` vs `reliance`).
  - Whitespace-stripped match.
  - Lazy import: `is_cas_eligible` must NOT crash on `config`
    import failure (use lazy import to keep `market_calendar`
    importable in isolation).

Commit pattern: `feat(J.2.1): operator-supplied CAS Phase 1 F&O
eligibility list`.

### Part 2 — broker-behaviour probe (documentation-only in Dev)

The probe cannot run in Dev (no live broker). Ship:

  - NEW `python-engine/tools/j2_cas_probe.py` — a CLI that the
    operator runs in staging. Documented step-by-step. Not
    exercised by automated tests.
  - NEW `docs/2026-09-13-j2-broker-behaviour-probe.md` — the
    evidence-collection procedure, what fields to record, and
    what to do with the result.

Commit pattern: `feat(J.2.2): CAS-window broker-behaviour probe
procedure (staging-only CLI)`.

### Part 3 — doc updates

After Parts 1 and 2 land:

  - EDIT `docs/SYSTEM_CODE_ATLAS.md` to include the new
    `classify_session_phase`, `is_cas_eligible`, and
    `_VALID_SESSION_PHASES` declarations (the atlas was last
    regenerated before J.1).
  - EDIT `docs/SYSTEM_GUIDE.md` to add a J section under
    workstreams.
  - EDIT `docs/NEXT_AGENT_PLAN.md` matrix row J to reflect
    IMPLEMENTING (Parts 1+2 done; broker-behaviour verification
    remains for staging).

Commit pattern: `docs(J.2): system docs regenerated after J.2
implementation`.

## Step 5 — what you must NOT change

  - `python-engine/kite_client.py` — out of scope.
  - `python-engine/fno_chain.py::EXPIRY_CUTOFF_HOUR/_MIN = 15, 30` —
    documented but NOT FIXED until operator sign-off.
  - `python-engine/hedge_strategies.py::_EXPIRY_CUTOFF = time(15, 30)` —
    same.
  - `python-engine/proactive_intelligence.py::stamp_session_phase` —
    the G forward-compat seam. **Unchanged.** Still returns
    `_SESSION_PHASE_UNKNOWN` for every input.
  - `python-engine/operational_coverage.py` — owned by I.C.
  - `python-engine/promotion_bridge.py` — owned by F/G.
  - `node-gateway/server/utils/market-hours.js` — Container B
    parity deferred.
  - `node-gateway/client/src/pages/Dashboard.jsx` — no dashboard
    change required.

## Step 6 — verification

  - Run the targeted J.1+J.2 tests: must be **≥70 pass** (61 from
    J.1 + ≥4 new is_cas_eligible tests + ≥5 new probe-CLI tests
    if applicable).
  - Run the F/G + J critical paths under warning-fatal: must be
    **≥225 pass** (no regression).
  - Run the agent suite: must be **177 pass** (unchanged).
  - Run the dashboard build: must be **OK**.
  - Whole python-engine suite in isolation: may show the documented
    2 intermittent failures in `test_mark_to_market.py` and
    `test_scheduler_h2_timing_tiers.py`. Verify these pass in
    isolation. If they fail only in the full-suite run, the work
    is not regressed.

## Step 7 — quality bar

The senior-dev quality bar the user has set in prior arcs:

  - "peak quality, extraordinary UX, never-before-felt"
  - "make a code so good the other agent has no need to change"
  - "ensure Precision and correctness in work"
  - "ensure good quality code instead of slop"
  - "the system's quality should not be compromised"

J.2 must meet this bar. The eligibility list and the probe
procedure are the contract between Sentinel and NSE; a sloppy
implementation here would mis-classify real CAS-eligible stocks
in PROD.

---

## Step 8 — output

At the end of J.2, post a `docs/2026-09-13-j2-eligibility-list-and-probe-done.md`
summary doc and commit. The doc must include:

  - The list of underlyings you seeded (Part 1, if operator
    provides any — otherwise the empty-list default).
  - The probe CLI usage and what to do with the result (Part 2).
  - The verification table (engine tests, agent tests, dashboard,
    whole-suite).
  - Honest self-corrections (any test failures caught during
    development and how they were fixed).
  - The remaining gap (broker-behaviour verification pending;
    J.3 or future slice consumes the result).

Then await further instruction.

---

## Anchor: branch state at session start

  - Branch: `codex/production-correction-hedge-p0`
  - HEAD before J.2: `63a98ab`
  - Working tree: clean
  - 98 commits ahead of `origin/codex/production-correction-hedge-p0`

Begin.
