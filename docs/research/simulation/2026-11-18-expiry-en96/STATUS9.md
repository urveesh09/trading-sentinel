# Round 9 status

IMPLEMENTED, FROZEN AND SCORED ONCE (development screen on studied sessions). No strategy qualifies; no champion nominated.

| Step | Commit / receipt |
|---|---|
| Auditor's proposal (EN96–EN105, 231 configurations) | `366d0b0d` (PLAN9.md, SOURCES9.md, families9.json) |
| Implementation + my families EN106–EN110 (87 configurations), checks, freeze | `99958d97` (IMPL9.md, freeze9.json, parity/reproduce/causal/unit/selftest receipts) |
| One-shot score | `results9-started.json` (head `99958d97`), `results9.json`, `anatomy9.json`, `trials9.jsonl` |
| Reconciliation | `verification9.json` PASS |
| Labelled post-score diagnostics | `post9.json` |
| Write-up | `ANATOMY9.md`, `COMPONENTS9.md`, `ANATOMY9-tables.md` |

**Why most labels are "INCONCLUSIVE — support".** EN87 funds only 7–10 parents per 60-session window, below the registered selection floor of 10. The chronological selection therefore fell back to EN87 in 3–5 of 5 folds for every EN87-based family. The floor was not lowered.

**Inference** is descriptive only. The calibration receipts show over-rejection under negatively skewed nulls; this was decided before the score.

**State:**
- Dev only; pushed to `codex/production-correction-hedge-p0`; not deployed. Production stays `55b5e942`.
- E03.2, EN55's registration, normal F&O, runtime configuration and capital are unchanged.
- The EN99 packet block stays source-gated, and SENSEX OI-dependent cells are null.
