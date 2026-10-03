# Successor inheritance — Trading Sentinel, October 3, 2026 (IST)

## Start here; do not replay the entire conversation

Human's current vision: a smart trader with good entries, flexible evidence-led
exits, room for big winners and disciplined capital protection—not a machine
that only adds filters. Paper Momentum may remain autonomous/advisory on AI
failure; real-money Momentum requires owner approval. Jev is deferred.
No backtest grants live-order, funding or partner-tip authority.

Latest requests handled: explain long-context/fresh-task tradeoff; deep handover;
clarify F&O history versus recent improvement; inspect no-extra-funding and
catastrophe guardrails; derive concrete F&O improvements; enumerate shipped
module backtests; run one Penny baseline using existing code; plan a unified
reproducible shipped-strategy backtest interface. Read the new October 3 plan
for details. Full multi-module replay and F&O risk fixes are **planned**, not
silently implemented.

## Mandatory environment and authority boundary

- Dev: `C:\Users\Urveesh\Desktop\trading-sentinel` — implement/test here.
- Production: `C:\Users\Urveesh\Desktop\Production_Trading-sentinel` — assess
  read-only; never edit/configure/restart directly. Promotion through GitHub.
- PowerShell, Windows, Asia/Calcutta. Python for Dev:
  `python-engine\winvenv\Scripts\python.exe`.
- Read applicable AGENTS and the four handover docs at start; preserve user
  edits. Explicit problem/contracts/tests/rollout/rollback plan before source
  changes; update guide/active plan/checklist, regenerate atlas, commit locally,
  immediately revalidate docs. Do not equate test passes with profitability.
- No agent messages/new Codex tasks, Production migrations, orders, provider
  purchases or partner canaries authorized by this handover alone.
- Subagents only if current user/applicable instructions explicitly permit.
  The user-specific 5.6 Sol delegation rule is conditional; do not infer model
  identity or spawn unnecessarily. No subagents used for October 2/3 assessment.

## Exact repository state to revalidate

Dev branch: `codex/production-correction-hedge-p0`.
October 2 assessment commit: `eca3b65be51968267813447ec8114f6a02cc7476`, local,
not pushed by this agent. Parent `e313e662f7b06f667fda427a30271b8afb974469`.
Current October 3 source slice can be found with
`git log -- scripts/run_penny_research.py`; see delivery for its hash.

Do not assume remote/deployed parity. Production HEAD was d90c775 before the
October 2 assessment; read-only check during October 3 observed
`044c016584118fd5c5b515fc6d03909dbcaa8c4b`. This agent did not promote/edit it.
Another operator/task may have changed it; inspect current Git and image/runtime
identity before deciding what is deployed. Container name `python-engine`.
Read-only stdlib SQLite access works at `/data/cache.db`. Container `python`
could not import application pydantic; don't diagnose a running outage or install
dependencies from that observation. Safe effective-settings attestation remains
needed; selected exec environment keys were unset, not proof of runtime defaults.

Before edits, run `git status --short` in Dev. Earlier unrelated fixtures/audits/
Jev files existed but latest pre-October-3 status was clean. Preserve any newly
appearing work. Do not blindly reset old dirt from conversation history.

## Authoritative documents in reading order

1. `docs/2026-10-03-backtesting-and-fno-safety-plan.md` — current F0–F2 and
   B0–B6 contracts, safety gap, completed Penny diagnostic, exact limitations.
2. `docs/2026-10-02-fno-profitability-assessment.md` and corresponding
   `...-results.json` — direct Production evidence, not a current-policy backtest.
3. Four handover docs: `SYSTEM_GUIDE.md`, `SYSTEM_CODE_ATLAS.md`,
   `NEXT_AGENT_PLAN.md`, `HANDOVER_CHECKLIST.md`. Topdated receipts take precedence
   over stale historical completion/open-checkbox statements further down.
4. `docs/2026-10-02-s7-s10-independent-review.md` and S1–S6 review for historical
   findings. R1–R5 were subsequently implemented by another agent (see below);
   do not redo obsolete findings as though still unimplemented.
5. Production `docs/2026-09-30-production-deep-audit.md` and
   `docs/2026-10-01-production-deep-audit.md` are hypotheses/context, not cash truth.

## Recent implemented project history (not a deployment attestation)

Earlier independent review `750227d`: small S10 deadline/retry, S7 settings/fee
freezes, S8 cash ordering/day/coverage and minimal fixture-loop correction.
Then other-agent commits: R1 `af6f424` exact F&O spread/single-leg replay binding;
R2 `dcc2f35` gateway read-only backlog report plus separately approved idempotent
apply; R3 `1550886` optional-AI diagnostics/original-alert completion/shutdown;
R4 `c118598` CSV capacity/bounded off-path writes and durable scheduler timing;
R5 `addf46b` source-bound timing/allocation/decision-quality learning contracts.
Their independent acceptance/deployment must be verified, not assumed from docs.

R6 stays operational: migrations/schema/recovery/settlement inspection,
representative sessions and preserved paths, new prospective freezes before
future samples, qualification criteria/adequate closes/coverage and separately
authorized partner delivery canary. Old partner empty qualification evidence is
not a code switch to bypass. No guaranteed date for partner tips.

Documentation mentions an owner-authorized Production AI-unavailable env change
by another task on October 2. That is not authority for the successor to repeat
or extend direct Production edits. Maintain current task's Dev-only rule.

## F&O assessment: numbers and limits you must preserve

July 1–October 1 (not all October), stored terminal position results:
single-leg 38 closes -₹18,367.22; spread 28 closes -₹3,721.71.
Historical total -₹22,088.93, **not fully exact cash-reconciled**.
Exactly linked September 17–October 1 subset: single-leg 9 closes +₹10,755.67
(5W/4L); spread 7 closes +₹3,187.60 (5W/2L), seven distinct sessions combined.
Single-leg removing two biggest winners gives ~-₹1,389.40. Big winners are
legitimate trend mechanics but their future occurrence is not established.

29 early single-leg and 21 early spread positions lack exact terminal keys;
50 old cash rows unassigned by exact source/origin. No guessed ticker/date
reconciliation. Recent matches prove stored arithmetic, not market-fill realism.
Legacy spread had 75-unit/unbound JSON versus 65-unit single-leg on October 1;
new Dev exact-contract/executable settlement changes cannot retroactively
validate old modeled marks. Auditor totals conflicted; direct DB wins.

Quote archive dates September 10–October 1 only (14 dated directories).
Token candle cache begins earliest August 25. Directory existence is not complete
quote paths. `fno_backtest.py` is old constant-IV synthetic options, fixed lots,
own bar-level exit ladder/no spread book; cannot claim current F&O profitability.
Kite does not supply the needed expired-option full intraday data. Operator must
choose/supply licensed data; neither a new script nor waiting restores old quotes.

## Newly found F&O safety priority: F0

Single-leg is long option BUY (bearish `SHORT` direction is a bought PE), not
naked selling/futures order. Source has per-entry working/structural caps,
open-premium/concurrency limits, loss brakes and 25% allocation drawdown halt.
Stops are engine-managed, unfilled hard-flat possible; do not promise zero
loss/capital cannot be depleted. Source defaults are not effective-settings proof.

Paper DR `maybe_open_dr_structure` lacks unified equity/reservation and common
loss/drawdown gates. Orchestrator opens it before the single-leg drawdown halt.
Single-leg kill-switch query excludes spread cash/partials. DR source default
finite max-loss ceiling is ₹10,000 and one structure at a time, not common-pool
protection. Implement/test shared per-source risk admissions before extra exposure.
Existing management/exit authority must remain active during entry halts.

Cash-only allocation ≠ zero broker margin. Hedged short legs may require initial/
final margin and temporary execution capacity. No inspected F&O preflight proves
broker free-cash/no-other-division funding. DR currently paper-only; do not create
a live executor implicitly. F1 cash/margin + legging catastrophe acceptance needs
owner semantics/authority. Detailed files/contracts/tests in October 3 plan.

## Penny run completed October 3

New inert CLI `scripts/run_penny_research.py`: Production read-only stdlib collector
over stdin; isolated temporary local DB; existing Lab
`penny_breakout_intraday_1m_replay`, PEN_BASE only, one share, 20 prior daily bars.
No new strategy/provider/dependency/order/schema or Production mutation.

Window August 11–20. First alphabetic metadata sample rejected on zero-volume
bars (`...penny-baseline-unavailable.json`). Five-stock coverage sample rejected
on mixed minute/15-minute evidence (`...penny-baseline-results.json`). Both
retained deliberately. Existing strict loader may be overstrict for known mixed
intervals/zero-trade bars; B1 proposes explicit contracts, not silent dropping.

Successful narrowed PCJEWELLER/SOUTHBANK sample
(`...penny-baseline-two-stock-results.json`): 5,790 minute rows, 1,506 daily rows,
16 ticker-days, 5,774 evaluations, **0 trades**; return/expectancy unavailable.
August 17 truncated for both tickers; all other sample sessions complete.
This is current entry evaluator + shadow exits/default calm regime, NOT full
Penny runtime gates/capital/scanner/regime/smart-EOD or representative universe.
Do not tune gates until it trades. Report zero entries honestly.

Small reproducible Windows correction: `penny_intraday_replay` used SQLite
connection context manager without closing; this prevented temp-file cleanup
on rejection. Changed to `contextlib.closing` with early/normal-close regressions.
No strategy decision changed. First failed attempt left uniquely named
`sentinel-penny-research-6p09sa4a` temporary directory; don't broadly delete Temp.

## Verification and reruns

Dev runtime above. October 2: new assessment 12 tests + existing F&O mechanisms
49 warnings-fatal passed. October 3: CLI 4 warnings-fatal; Penny replay 11
warnings-fatal; combined Penny/Lab/F&O max-loss/risk-switch/defined-risk 82 passed
with one existing HTTPX TestClient deprecation. Initial combined warnings-fatal
failed solely on that warning; not a warning-clean suite. Focused checks exited.
Earlier broad Windows suite teardown hangs are documented; use a minimal
reproducer, not broad dependency/application changes, to investigate.

Useful commands (run from Dev, use new output filename each time):

```
.\python-engine\winvenv\Scripts\python.exe scripts/run_penny_research.py --container python-engine --from 2026-08-11 --to 2026-08-20 --tickers PCJEWELLER,SOUTHBANK --output docs/<new-name>.json
.\python-engine\winvenv\Scripts\python.exe scripts/assess_fno_profitability.py --container python-engine --start 2026-07-01 --end 2026-10-01 --output docs/<new-name>.json
```

Penny outputs are fingerprints/settings/source-hashed research artifacts; F&O
assessment is a history/cash reconciliation diagnostic. Neither qualifies tips
or funding. Output restriction prevents overwriting user evidence. No pushes
or GitHub PRs performed for these slices.

## Recommended fresh-task instruction

“Read docs/2026-10-03-successor-inheritance.md and the October 3 backtesting/
F&O safety plan in Dev. Revalidate checkout/deployment without editing
Production. First implement the F0 shared F&O risk-admission contract with
regression coverage, then B1/B2 data contracts and exact classic Penny lifecycle
backtesting. Reuse shipped strategy functions and Backtest Lab; no made-up
strategy, silent data substitution, live funding or partner authority. Keep
documentation current; commit completed slices locally and report deployment
status and remaining evidence.”

A fresh task reduces irrelevant conversation history but must read this durable
context; it does not reset account limits or guarantee lower token usage. Do not
fork the whole long conversation when a short fresh prompt plus these docs suffices.
