# N06 — past-only saved-variant selection and execution-evidence availability

Status: implementation pending; no N06 candidate cash-path score inspected.

Problem: N03, N04 and N05 preserve useful but conflicting exit outcomes. A
mechanically causal router does not establish that choosing between them helps.
Test selection without changing their strategies, sizing, or real authority.

Contracts and files:

- Research-only `variant_policy.py`, `variant_lab.py`, tests and reporting here.
- Import the frozen N05/N04/N03/N02 replay graph; retain exact MAIN and three
  balanced policies. No application source, environment or migration changes.
- Two candidates only: MAIN_ANCHOR and STRUCT_ANCHOR, comparing whole saved
  MAIN/BASE/STALL30/STRUCT30 policies. Each falls back to its named anchor.
- Use previous 84 archived sessions in the same year; labels must have exited
  strictly before the selection date. At least eight weekly buckets, ten
  nonzero paired days, twelve challenger closes and six anchor closes; weekly
  mean advantage minus one standard error positive; advantage excluding its
  best day positive; trailing closed drawdown no larger than the anchor.
  Fixed tie order BASE, STALL30, STRUCT30, MAIN. Two consecutive qualifying
  decision dates required. Missing evidence returns to anchor immediately.
- Daily decision files are built from hash-bound prior N05 whole-book reference
  outcomes, then committed before candidate replay. All 2024–26 data is seen;
  chronological causality is not an independent holdout or profitability proof.
- Selection is fixed at entry. Bind selected policy, label cutoff, immutable
  entry terms and admission identity to that leg. Later selections must not
  change open legs. MAIN uses original EFF; balanced variants use N03 retest.
  Reset pending retest state at day/selected-profile transitions. Preserve
  original member priority, stale-bar refusal, deadlines and native hard flat.
- Fresh Rs250000/year, existing 2/3-lot caps, LOW TPB one lot, same modeled
  quotes/current fees and extra `(200+5*lots)*lots`; no budget increase.

Acceptance before replay: freeze source/input/reference/config hashes and commit;
focused tests for future-label mutation, insufficient/failed evidence, finite
values, persistence, per-leg policy binding, restoration after errors, missing
decisions, unchanged size and entry/exit clocks. Static adapters must reproduce
all twelve saved annual reference results exactly before candidate scoring.

Frozen research success: each candidate must earn at least all three saved
balanced references in each year, with annual closed-equity drawdown no larger
than any of them; positive net without best trade/day; >=12 closes/year and
>=60 total; >=5/6 profitable half-years; paired weekly t>=2 versus STALL30
and four-week-block two-arm max-T adjusted p<=0.05 (4096 draws, seed110601).
No pass can authorize deployment: all three years are already used. Retain all
failures. Closed drawdown is not maximum intratrade or guaranteed future loss.

Verification: independent cash/fee/trace/entry-price reconciliation, per-leg
closed-bar/exit checks, past-only selection and source/input hash rechecks.
Reuse prior 699 input checks only with exact inherited bindings; do not call
them new checks. Compare static controls before candidate cash paths.

Execution availability: inspect Production's verified existing container/data
volume read-only from a disposable network-disabled container, with outputs in
Dev only. Aggregate real fill availability separately from paper positions;
never infer real cost from paper fills or print secrets/account identifiers.
No broker, orders, Telegram, login, downloads, deployment, restart or 2023 exam.

Rollout: research/docs only; update SYSTEM_GUIDE, active plan and checklist with
each implementation commit; regenerate atlas; record hashes, commands and limits.
Rollback: stop only research workers; retain evidence; no Production rollback.

Remaining after this slice: fresh dated execution/cost evidence and prospective
shadow review; 2023 deferred until explicitly requested. Larger-size research
remains conditional, within unchanged risk/cash budgets, with equal-risk and
full-premium/gap/spread/concentration stress. No knowing a winner in advance.
