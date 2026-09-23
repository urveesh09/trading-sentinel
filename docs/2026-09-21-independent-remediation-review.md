# Independent review of audit remediation — 21 September 2026

Reviewed incoming commits `ce5684d`, `c237426`, `cfbbc06`, `b5999bf`,
`c44dc3d`, `c9e4379`, and `674a6fe` on
`codex/production-correction-hedge-p0`. User authorized correcting residual
defects in Dev. Production is unchanged; no message, order, deployment or
qualification is authorized by this review.

## Acceptance slice

The six labels are not accepted solely because isolated helper tests pass.
Verify actual registry/dispatch, broker-entry and settlement callers, expected
session coverage, and operator-visible diagnostics. Preserve existing golden
fixture edits and prior audit evidence. Canonical documentation and atlas must
reflect the reviewed integrated implementation before commit.

## Confirmed qualification gap and correction

Incoming A3 verifies an artifact hash only during registration. It accepts JSON
schema gaps as warnings, has an environment bypass, and does not call the new
verifier at qualification registration, candidate approval or final dispatch.
The runtime still accepts an unexpired-by-convention status-only registry row.
The separate A4 identity helper silently omits missing source modules and
duplicates its module list instead of defining one authoritative identity.

Correction uses the existing heldout and review evaluators, not an alternate
profit calculation. `partner_qualification_authority.py` verifies a bounded,
root-confined immutable package, recomputes heldout data from its source replay
reports and reconstructs the predeclared review decision. Qualification admission
and final dispatch require matching current policy code/config/profile, positive
net and stressed net outcomes, no review blockers, an explicit human approval,
and aware validity clocks (maximum 30 days from review). Missing/legacy evidence
fails closed. Artifact registration alone remains non-authoritative; the old
verification-disable setting cannot grant a bypass. The legacy pure schema
diagnostic is explicitly not an authorization API.

Code/config/economic identity now uses one source list, including spread
construction, asymmetric fill model, review and authority modules. Missing source
files fail closed. Profile changes, artifact tampering, index mismatch, registry
suspension and expiration must prevent new entry advice without disabling
management of already published ideas.

## Authorization package contract

The artifact root defaults to `/data/research/qualifications` inside the persistent
data mount. `dataset_ref` must resolve inside that root; bounded reads reject
traversal, missing files and oversized artifacts. Registered SHA-256 is computed
over the exact file bytes.

`partner_advisory_authorization_v1` contains:

- `underlying`, `structure_kind`, `horizon`, `policy_version` matching the request.
- `policy_manifest`: output of the deployed full-policy evaluator, including its
  frozen source/config/profile identity.
- `criteria_manifest`: genuinely predeclared `freeze_qualification_criteria` output.
- `source_reports`: complete `report` plus `signal_artifact_sha256` for every case.
- `heldout_report`: `build_heldout_comparison` output, reproducible from those cases.
- Optional `readiness` observations; these are not authority flags.
- `review_identity`: named `operator`, aware `reviewed_at`, `decision=APPROVED`.
- `validity_period.start/end`: aware clocks, after review, bounded to 30 days.

The qualification API accepts an explicit `profile_id` (default remains
`default`). A saved INTRADAY profile is mandatory. The report is checked against
that exact profile; changing its version/limits requires fresh compatible review.
This is an operator-reviewed evidence import, not automatic qualification or a
claim that a synthetic fixture proves profitability. No Production artifacts
were manufactured or registered.

## Rollout and remaining work

Promote through GitHub after integration tests; do not copy files into Production.
Existing weak/legacy qualification rows become non-deliverable until supplied
with compatible verified packages. This is intentional. Preserve the ledger,
delivery claims and raw archive on rollback; pause new entries/advice if the
compatibility contract cannot be maintained, while keeping exits/management.

A configuration verifier is not real-source activation. Explicit approved dated
instrument mapping, research account/run identity and real fresh market data
remain required. The post-session research pipeline, account-scoped broker
reconciliation, agreed partner risk/exposure and genuine market performance
remain separate from these six correctness fixes. No blanket Production or
profitability green light follows from this code review.

## Completion update — 23 September 2026

Incoming A1–A6 were useful but not complete at their actual execution boundaries.
The follow-up corrects these issues in Dev:

| Area | Corrected behavior |
|---|---|
| Entry admission | Authenticated signed owner-entry halt reaches gateway and direct Kite entry paths. Fresh session/eligibility checks follow network waits; protective exits bypass entry-only halts. UNKNOWN CAS cannot be treated as non-eligible. |
| F&O single-leg settlement | Source-scoped positive-generation uniqueness; allocation-inclusive ledger equity; position close, ledger insert and receipt consumption commit together. A durable pre-dispatch intent prevents another external exit after a crash or failed receipt write. Known fills retry local accounting. |
| Qualification | Actual registration, candidate and final dispatch paths revalidate current reviewed packages, immutable bytes, scope, code/config/profile and validity. Status-only legacy rows cannot authorize delivery. |
| Policy identity | One complete shared module map; missing participating modules fail closed. |
| Collection coverage | Distinct expected slots, future-row exclusion, mixed unavailable slots and explicit account scoping prevent false completeness. Collection never qualifies a strategy. |
| Diagnostics/source | WARN is not delivery-ready; qualification uses the real verifier. Source mapping validates token/basis/master digest and malformed explicit limits. Login/archive diagnostics read real files read-only; quiet ledgers are not classified as provider outages. |

### Configuration, migration and recovery implications

- No Production settings changed. `PARTNER_VERIFY_RESEARCH_ARTIFACTS` is deprecated;
  setting it false does not bypass authorization. Mount real reviewed packages at
  `PARTNER_ARTIFACT_ROOT`; never copy synthetic test packages into Production.
- Additive `fno_exit_execution_receipts` and `fno_exit_intents` tables are initialized
  with positions. The replacement positive-generation ledger index includes source.
  Index conflicts must fail visibly; preserve and reconcile conflicting rows.
- Single-leg F&O exit polling no longer cancels and replaces an order without proof
  of its final fill. An unresolved intent intentionally blocks another dispatch.
  This may require urgent operator action; it does not prove the position is flat.
- For a known broker fill, retain broker order/trade evidence, save the accurate
  receipt using `record_exit_execution_receipt`, then retry local settlement. Never
  delete an intent merely to retry. Partial fills/terminal zero-fill outcomes need
  an evidence-backed recovery workflow; no self-service recovery UI is added here.
  Keep live single-leg F&O disabled until that operational path is agreed/tested.
- This correction covers `fno_positions` single-leg exits; it is not a blanket
  certification of every strategy's execution/settlement path.
- Freshness is an on-demand diagnostic, not a scheduled alert. A current token file
  is retained-login evidence, not a successful broker API authentication probe.

### Next-agent execution order

1. **Release safely:** inspect this commit/diff and dirty-worktree state, back up
   retained databases/archives, merge through GitHub, rebuild stamped images and
   verify gateway/engine/dashboard identities with the deployment runbook. Preserve
   all stores. Re-run read-only readiness with real paths in the Production runtime:
   `python scripts/check_partner_readiness.py --db-path /data/cache.db --archive-root
   /data/research --token-path /data/kite_token.json --json --delivery-ready-only`.
   Paths are examples: confirm actual Compose mounts/settings first.
2. **Operational acceptance:** verify login, per-index inputs and quote timestamps;
   run `scripts/audit_session_completeness.py --help` and audit each actual account
   and session. Measure scheduler p95/max and missed intervals during market load.
   Confirm exits and published-idea management stay timely under chain/provider delay.
3. **Exit recovery:** build authenticated, evidence-backed operator inspection and
   resolution for unresolved F&O intents, including partial fills and terminal zero
   fills, with concurrent/restart tests. Never infer non-execution from a timeout.
4. **Real research:** activate the completed-bar source only with a dated archived
   instrument mapping, explicit account/run and frozen capital/cost assumptions.
   Freeze deterministic signal and review criteria before held-out evaluation; add a bounded operator package-building CLI
   for the documented authorization envelope (not an auto-approval command); replay
   collected active-leg sessions with fills, costs, slippage and missed fills. Produce
   per-index authorization packages only if those real outcomes pass review. A fixed
   number of sessions or a green test suite does not establish profitable performance.
5. **Partner launch:** confirm saved INTRADAY profile and risk limits; independently
   approve NIFTY and SENSEX evidence; run an explicitly authorized transport canary.
   Only then verify valid setup cards and lifecycle messages in a real session. No
   promise of messages every day or profitable outcomes follows from readiness.
6. **Accounting/observability:** reconcile retained ledgers/positions against broker
   statements and explain all mismatches. Connect actual Production account/run data
   to dashboard scopes. Add alert scheduling only after current diagnostics are
   validated against real evidence; do not conceal missing inputs with green defaults.

### Validation and promotion receipt

Final test counts are recorded in the September 23 handover entry. No Production
mutation, broker order, Telegram message or research qualification was performed.
Canonical guide/active plan/checklist and generated atlas accompany this correction.
Pre-existing golden-fixture edits and prior independent audit artifacts are excluded.


### Known scope limits

The six correction labels do not mean the entire passive-income roadmap is done.
The optional AI has no qualification/order override. This increment does not tune
strategies, increase risk, establish a profitable edge, generate real research,
activate a source or configure a partner. Older operational notes remain historical;
use the September 23 canonical entries and this checklist as the current handover.
The added API contract entry is exactly `GET /market-session/owner-entry-halt`;
scheduler contract changes are not part of this correction. A date-sensitive CAS
freshness test now uses an explicit clock; archive tests normalize IST fixtures to
UTC and retain PARTIAL when expected slots are missing.

### Final verification - 23 September 2026

- `python-engine/winvenv/Scripts/python.exe -m pytest python-engine/tests scripts/tests -q --tb=short`: **4,476 passed, 4 skipped**, 46 existing Starlette/httpx deprecation warnings; 235.33 seconds.
- Complete gateway Jest suite in an ephemeral Node 20.20.2 container, Dev source copied without `.env` or local native dependencies and `npm ci --include=dev`: **460 passed, 4 skipped**, 30 suites passed, one skipped. No Production runtime mount or service was changed.
- Changed Python source syntax and `git diff --cached --check`: passed.
- API golden change is the authenticated owner-entry-halt GET route only.
- Atlas regenerated: **209 Python modules**. All four canonical handover documents updated.
- Dev correction only; commit identity/push receipt is recorded below after commit. No claim of deployed or profitable behavior.

Implementation commit: `8f8f39f34377851075a3299e4b72f7dc0d1f610d`. Post-commit canonical-document and staged-scope consistency verified. Promotion remains GitHub-only; Production was not edited.
