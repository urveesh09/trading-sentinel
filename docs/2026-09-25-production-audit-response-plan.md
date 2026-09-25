# 25 September Production audit: corrections and next implementation plan

## Scope and receipt

This plan reconciles the 25 September Production deep audit
(`C:\Users\Urveesh\Desktop\Production_Trading-sentinel\docs\2026-09-25-production-deep-audit.md`)
with read-only Production SQLite/container checks and current Dev source at
`b58cfc5`. Production runs merge `f52f4d5c` and was not edited or restarted
for this review. The audit's market-hours logs are partial because the
application container was replaced at 16:15 IST, **after** the 15:30 market
close. No broker order, Telegram message, qualification registration,
configuration change or strategy change is authorized here. Treat all P&L
below as paper-ledger evidence, not partner or live returns.

## Verified state and audit corrections

| Topic | Evidence and corrected interpretation |
| --- | --- |
| Paper P&L | Read-only `bankroll_ledger` has one `MOMENTUM_PAPER` close at -₹237.17 and five `PENNY_PAPER` closes totaling -₹60.62 on 25 Sep: -₹297.79. The three-day +₹1,450.88 is a short paper sample, not positive expected value. |
| Paper-admission migration | The real table is `momentum_paper_admission_outcomes`, not the audit's singular `momentum_paper_admission`. It **already exists** in Production with two 25 Sep rows: TENNIND `opened` at 11:48:41 IST and PARADEEP `zero_shares` at 12:03:41 IST. The source creates it idempotently at the admission boundary. Do not run a speculative migration. |
| “HIGH-007 default-approve caused TENNIND paper loss” | TENNIND's paper opening precedes its 11:50 classifier calls. The classifier returns informational `UNKNOWN` on timeout; the independent paper book opens before agent review. The later `Registered approved snapshot` and Telegram alert warrant a separate reviewer-policy trace, but cannot be used to infer classifier approval or paper causality. Changing classifier fallback to a veto would change authority and would not retroactively prevent this paper opening. |
| Log rotation | Effective Production driver remains `json-file`, `20m × 10`; the earlier read-only measurement found one unrotated 18.13 MiB Python file spanning 35.897 hours. A container replacement at 16:15 makes the old container's `docker logs` unavailable unless retained elsewhere. The saved pre-restart partial logs and DB evidence do not prove the 200 MiB rotation cap was reached. The deployed verifier pins the rendered configuration; it is not a log archive or a YAML increase. |
| F&O basis warning | `fno_chain.py` computes put-call parity from ATM option mids and warns when it differs by >0.5% from the front-future LTP. The warning path does **not** reject the snapshot or veto DR entry. A 0.66–0.76% difference does not prove which leg is stale; expiry/tenor mismatch, wide quotes, last-trade ages and calculation assumptions remain alternatives. The 20s `fno_dr_entry_skipped` deadline is a separate entry-preparation guard. Zero DR trades do not prove either warning caused every non-entry. |
| Penny health after restart | `run_penny_scanner_once` intentionally returns outside 09:15–15:30 IST. `_last_penny_scan_at` is in-memory and remains null after a 16:15 replacement, so post-close `DEGRADED`/`UNKNOWN` is expected from the current freshness contract. A liveness tick is not a scan. Treat a stale state **after the next logged-in market-hours scan** as a defect; do not promise a post-close cycle will clear it. |
| Partner readiness | Production has one saved intraday profile, 33 `MARKET_SETUP` ideas (15 `VALIDATED_SHADOW`, 14 superseded, four rejected), **zero** general strategy qualifications and **zero** general research-artifact registrations. The per-index attempt journal recorded 165 NIFTY and 165 SENSEX attempts on 25 Sep, all with public input observed; SENSEX had 11 candidate-input observations and six `CANDIDATE_RECORDED` decisions, while NIFTY had no setup. The audit's 0/7 staging-days, 0/1 chain verification and 0/5 reviews are for the **separate personalized hedge phase**; they do not describe general market-setup collection. The hedge portfolio adapter is unconfigured, so personalized advice remains unavailable. |

The audit also describes 16:15 as “mid-market,” despite identifying it as after close. Its `research_quote` maximum of 48s and lower aggregate scheduler skips are encouraging first-session observations after release, not proof of three-session stability or preserved NIFTY/SENSEX coverage. The warning in `fno_chain.py` predates this deployment; it is newly observed in the audit, not a newly deployed safety gate.

## Ordered implementation and operational plan

### P0 — Preserve forensic continuity across releases/replacements

**Problem:** The existing 200 MiB per-container bound does not retain `docker logs` for a container removed by Compose, even if no rotation occurred. The operator needs both complete opening-to-close logs and durable decision evidence.

1. Read-only inventory: compare old/new container IDs and Compose replacement timing, Docker retained-file sizes/time bounds, saved log exports and disk headroom. Distinguish `--tail` sampling, rotation and container deletion. Do not expose secrets or full request payloads.
2. Decide a bounded, recoverable retention mechanism (for example, an operator-owned export before replacement or a managed central sink) with explicit retention days, access control, byte budget, secret redaction, failure alert and rollback. Do not add an unbounded application log volume or blindly set `max-file: 25`.
3. If Dev source/Compose changes are warranted, test `docker compose config`, the existing `scripts/verify_compose_logging.py`, focused retention/rotation checks and a harmless replacement rehearsal against disposable logs. Release through GitHub only; no direct Production edit or restart by this plan.

**Acceptance:** Three real logged-in sessions retain opening-to-close Python, gateway and agent decision logs across an ordinary reviewed release/replacement; the exact container/image SHA and archive time bounds are independently retrievable. A sink failure is visible rather than silently discarding the only forensic copy. Rollback must preserve prior exports and databases.

### P1 — Validate deployed admission, research and F&O safety behavior

- **Admission:** Query the correct `momentum_paper_admission_outcomes` table read-only alongside accepted signals and positions. Verify TENNIND `opened` and PARADEEP `zero_shares` remain coherent after restart. No migration or code change is justified by the audit's wrong table name. Add an operator query/receipt only if the existing surface remains hard to find.
- **Research collector/DR deadlines:** Compare per-index requested/received/partial/capped quote evidence and `fno_tick` stage durations for three logged-in sessions after `d19b30f`/`311cc24`. A 48s research max is good only if SENSEX/NIFTY active legs and public management evidence are not silently lost. Preserve exits/hard-flat ahead of speculative DR entry; investigate recurrent 20s skips with stage and provider/limiter timings before changing budgets.
- **Parity warning:** Reconstruct same-tick future and ATM call/put contract identities, expiries, bid/ask mids, last-trade and receipt timestamps, spread/depth, and tenor/carry assumptions. Write a minimal counterexample and test if the calculation or wording is wrong. Do not relax a genuine price/quality gate or claim Kite staleness without packet evidence. If quality genuinely fails, make the entry decision explicit and fail closed; keep exit management independent.
- **Penny health:** On the next logged-in market session, verify the first successful scanner tick sets scan and regime state and health returns to OK within the documented freshness budget. If not, reproduce the restart path and fix only the ownership of the missing state, with off-hours and no-token tests. Do not fabricate a post-close “healthy” scan.
- **Classifier/reviewer:** Check the typed review and Telegram policy for TENNIND independently of the paper book. Keep `UNKNOWN` informational and no-retry classifier latency bounded. A proposed default-veto is a product-authority change requiring a separate decision and evidence, not a fix established by this loss.

**Acceptance:** Focused tests for each demonstrated defect; unchanged order/alert authority, admission and exit deadlines; no stale or fabricated market packet; read-only Production session receipt after GitHub promotion. If a result remains an unproven audit inference, close it as such rather than creating a speculative patch.

### P0 for partner usefulness — qualify the general intraday pathway, separately from personalized hedge

1. Verify the saved `INTRADAY` profile's current constraints, destination and final-dispatch configuration through authenticated/read-only surfaces. The profile exists; do not ask to recreate it or require partner holdings for a general NIFTY/SENSEX setup.
2. For each index, report the *funnel*, not “days running”: expected/attempted public observations, complete option books/selected legs, independent decision units, candidate-valid/invalid/no-setup cases, post-entry management coverage and costs. Preserve the 25 Sep 165-per-index attempts and six SENSEX candidate decisions as data, not six qualified trades. Explain why NIFTY had no setup instead of lowering filters to force a tip.
3. Freeze one policy version, cost/slippage assumptions, sample and review criteria **before** a future held-out window. Use real immutable completed-bar/public/option archives and the existing full-policy replay, stress, review and authorization-package path. Include no-fill days, duplicate decisions, partial/unknown exits and adverse costs; do not cherry-pick the 15 shadow ideas or three profitable paper days. If coverage is inadequate, fix collection rather than inventing fills.
4. Have an independent human review the held-out result. Only if the existing authority verifier admits a compatible artifact should an operator register qualification and separately authorize a clearly marked TEST delivery/canary. Check destination, duplicate/ambiguous delivery recovery, card clarity, deadlines and revocation. No automatic Telegram advice or promise of a date before these gates pass.
5. Personalized hedge remains a separate opt-in: an approved portfolio input adapter, reconciled exposure, seven genuine staging days, chain verification and sample reviews are required by its own policy. Do not fill those counters from general market observations or toggle them to seven.

**Acceptance:** Per-index explainable readiness, immutable replay and predeclared held-out review with a costed outcome and explicit uncertainty; no qualification if the current strategy fails. After authorization, a TEST canary is distinguishable from advice and no message is sent twice. Rollback revokes qualification/delivery without erasing evidence.

### P2 — Predeclared strategy comparisons; no immediate gate loosening

The 25 Sep five penny STOPs and TENNIND loss are hypotheses, not statistical proof. Research two bounded alternatives against the current baseline in shadow only: (a) an entry-time liquidity/spread and volatility-persistence filter for penny breakouts, using only information available at the decision; and (b) a cost-aware momentum or defined-risk index candidate whose entry/exit deadlines and maximum loss are unchanged. Do not use post-entry stop timing as an entry feature, change thresholds after seeing held-out results, or transfer a stock-paper result to partner index options. Pre-register variants and evaluation rules, compare the same independent opportunities with realistic fees, spreads, slippage, missed fills and adverse periods, then reserve future sessions for held-out testing. A variant that reduces trades but has no robust net benefit stays research-only. See the [primary backtest-overfitting study](https://escholarship.org/uc/item/4w1110bb) and [SEBI's F&O loss study](https://www.sebi.gov.in/media-and-notifications/press-releases/sep-2024/updated-sebi-study-reveals-93-of-individual-traders-incurred-losses-in-equity-fando-between-fy22-and-fy24-aggregate-losses-exceed-1-8-lakh-crores-over-three-years_86906.html) for why positive in-sample paper P&L is insufficient.

## Documentation, release and remaining authority

This is a plan-only Dev documentation change; no application or Compose source is modified. Future implementation slices need a failing reproducer, exact files/contracts, focused and cross-component tests, updated `SYSTEM_GUIDE.md`/active plan, regenerated atlas if declarations change, an immediate post-commit consistency check, and a recorded Dev/pushed/deployed SHA. Preserve the existing unrelated golden-fixture edits and audit artifacts. Production stays read-only until normal reviewed GitHub promotion and a separate operator deployment. Broker live-trading readiness is still `order_execution_unverified`; paper results and a working delivery transport do not override that gate.
