# Backtesting Sentinel's shipped modules and F&O safety — October 3

## B1/B2 implementation override (later October 3)

B1 (bar data contracts) and the classic Penny MIS half of B2 (exact
lifecycle) are implemented in Dev. See [the B1/B2 slice](2026-10-03-b1-b2-data-contracts-and-penny-lifecycle.md). In the
catalogue below, *Classic Penny MIS Breakout* now has a `LIFECYCLE` adapter,
`penny_breakout_mis_lifecycle_1m`. Full runtime gates are replayed except
universe ranking, regime history, the sector filter and the event calendar.
The exact CNC Connors adapter and B3–B6 remain planned. F0 R1–R5 status is
unchanged by this work.

## Current acceptance override — independent F0 review

The [independent F0 review and R1–R5 correction plan](2026-10-03-fno-f0-independent-review.md)
supersedes the source-complete claim in the F0-E receipt. Implemented shared
paper brakes and atomic inserts remain, but fee-inclusive open exposure,
one-time dispatch/ambiguous entry recovery, exact cash clocks/completion,
broker-payload binding and admission occupancy/final clocks are not accepted.
Two small reader defects were corrected in Dev with regressions: no database
creation by read helpers and no false exposure release/block after zero fill.
Production remains unchanged at `044c016`; B1/B2 has not started.

## Explicit slice before implementation

Reuse the existing Backtest Lab Penny minute adapter, not a new strategy.
Add an inert `scripts/run_penny_research.py` CLI: collect a bounded,
metadata-selected sample from Production SQLite using `mode=ro` and one read
transaction; stream the collector to the container without installing/editing
anything; materialize an isolated temporary Dev research DB; execute the current
Dev adapter with only `PEN_BASE`, frozen one-share sizing and at least 20 prior
daily bars. Record exact requested dates, sample selection, dataset/source hashes,
default-regime/exit/fill assumptions and coverage. Never use Production backtest
API endpoints (they persist runs). No provider/order/message calls.

Predeclared exploratory window: August 11–20, 2026. Choose the first five
alphabetical symbols that have explicit minute rows with at least one full
09:15–15:29 session in that window and at least 20 preceding daily records.
Choose using timestamps/counts only, before any outcome is computed. Retain all
intervals for those tickers so the existing loader can reject mixed provenance.
This is a coverage-selected diagnostic sample, not a historically representative
universe, an OOS optimization or capital-return estimate. CLI also accepts an
explicit ticker list/date range for subsequent local evidence.

Acceptance: no new strategy rules, malformed/mixed data remains rejected,
collector bounded and missing DB never created; tests for selection, read-only
collection, exact baseline adapter and report limitations. Run existing replay
tests. Output only new files in Dev docs, no overwrites. Rollback removes the
CLI, leaving application/runtime/schema untouched. All broader development
below is planned, not implemented by this slice.

First-run finding before any P&L: the strict replay rejects the alphabetical
sample because it contains zero-volume minute rows. These can be valid no-trade
bars, so rejection is a data-contract limitation, not proof of a losing strategy.
Record that unavailable attempt. A second, explicitly coverage-selected equity
sample will use IDEA, OLAELEC, PCJEWELLER, SAGILITY and SOUTHBANK, selected from
the timestamp/positive-OHLCV inventory without examining outcomes. Do not infer
performance of illiquid Penny names from this liquid sample. Do not drop invalid
bars silently or weaken the existing loader for this experiment.

The failed load also reproduced a small Windows correctness issue: SQLite's
connection context manager commits/rolls back but does not close the handle;
it prevents temporary DB cleanup. Use `contextlib.closing` for the Penny
read-only loader and the new collector/temp writer. Add a regression proving
the read handle closes on normal and early-return paths. No trading behavior
changes; this affects only offline research resource cleanup.

## Evidence conclusions and implementation backlog

### 1. What we actually learned from F&O

The October 2 read-only report (`2026-10-02-fno-profitability-results.json`)
covered July 1–October 1 by exit/cash day, **not October as a whole**. Full
retained position P&L: single-leg -₹18,367.22 (38 closes), spreads -₹3,721.71
(28); combined -₹22,088.93. Old positions are not fully cash-reconciled and
span changing policy, fills and contract conventions. They are not a backtest
of today's code. The exactly linked September 17–October 1 subset is +₹10,755.67
(9 single-leg closes) and +₹3,187.60 (7 spreads), on only seven distinct sessions.

September 17 marks the beginning of **this exactly linked settlement sample**,
not a proved treatment date. Engineering improvements occurred before and
after it: July no-pyramid/target geometry, August premium-aware time stops,
September reconciliation/deadline/quote protections, and October exact spread
contracts/executable settlement and research binding. It is reasonable to say
recent performance improved; it is not valid to attribute that improvement
causally to one deployment using seven sessions. Require immutable release /
effective settings / pricing-policy / per-trade lineage to make that comparison.

Specific lessons, not generic requests for more filters:

- **Big winners matter.** Removing two recent single-leg winners leaves
  approximately -₹1,389.40. Do not cut winners indiscriminately to increase hit
  rate. Test current trailing/time exits against frozen peak-hold/giveback and
  confirmed-extension hypotheses on the same paths, with loser and hard-flat
  behavior unchanged. Estimate the occurrence rate of those winners by session.
- **Spread gains are partly legacy economics.** A retained October 1 spread
  used 75 units/unbound legs while its single-leg used 65. New Dev code uses
  exact contracts/executable sides; old mid/model results cannot be carried
  over as validated performance of that implementation. Re-measure fresh cash.
- **Two books are not independent alpha.** They share market direction and
  sometimes the same signal. Measure their joint capital/drawdown and compare
  single-leg-only, spread-only and a predeclared allocation, not sum their
  standalone returns or assume diversification.
- **No entry is sometimes correct; sometimes data is missing.** Record the
  difference. Study missed/stale opportunities and fill delay before changing
  thresholds; compare net outcomes of actual entry/exit hypotheses, not the
  count of signals admitted. Do not optimize by hindsight on the profitable week.
- **The auditor is not cash truth.** Some headline/table totals conflict. Use
  exact reconciled rows, preserve legacy uncertainty, and never paper over it
  with ticker/date guessed joins.

### 2. Capital safety: source guarantees versus claims we cannot make

Reviewed Dev `fno_risk.py`, `fno_gates.py`, `fno_orchestrator.py`,
`fno_executor.py` and `fno_dr_book.py`. No risk settings changed. These are
source defaults/contracts, **not an attestation of the running process's
effective settings or broker funds**. Direct `docker exec python` cannot import
the app's pydantic environment on this host; the stdlib SQLite collector works.
Selected container environment keys were unset, which does not prove application
defaults because settings can also load a dotenv file. Do not dump secrets to
resolve this; use an operator-safe allow-listed settings receipt later.

Single-leg buys a CE or PE; `direction=SHORT` means bearish view / bought PE,
**not naked option selling**. The order path sends BUY then SELL to close,
uses MIS LIMIT orders and does not order futures. A bought index option can
lose its entire paid premium plus charges. The structural risk validator rejects
unbounded payoff; stop-based working risk is a separate, weaker guarantee.
Default source values: 2% per-trade working risk, ₹6,250 working rupee ceiling,
₹30,000 structural ceiling, 15% open premium cap, two concurrent positions,
three trades/day. Engine loss brakes are 6% day / 12% week / 20% month, six-loss
pause, plus the single-leg entry path's 25% allocated-equity drawdown halt.

These are entry brakes, not broker-guaranteed liquidation levels. Working stops
are engine managed; outages, quote gaps and unfilled limits can exceed their
risk budget. The executor actually reports unfilled hard-flat orders requiring
operator action: its introductory phrase "guarantee the fill" is not a real
guarantee. No stop or finite historical drawdown proves a pool can never be lost
over repeated trades/months or through operational errors.

**New source-level gap found:** `maybe_open_dr_structure` checks enable/window,
existing structure, freshness and its finite ₹10,000 default maximum-loss ceiling,
but does not check shared equity/reservations or single-leg loss/drawdown brakes.
The orchestrator admits the paper DR book before `_fno_halted` gates single-leg
entries. Single-leg kill-switch cash queries are keyed to `fno_position:%` and
closed positions, excluding spread cash and partial settlements. Thus the whole
F&O pool is not governed by one uniform loss/capital contract. DR is paper-only
in this orchestrator, so this is not evidence of a live unhedged spread incident.

"No extra margin" must mean **no borrowing, no debit balance, no collateral from
other divisions and no allocation top-up**. It cannot mean "a short option leg
requires zero margin." Even a bounded debit/credit spread may require broker
initial/final margin and temporary legging funds. No explicit broker margin/
free-cash preflight was found in the inspected F&O admission/executor files;
paper risk arithmetic is not such a check. MIS product does not itself prove
borrowed funding, but neither does it verify cash-only affordability.
Sources: [Kite margin API](https://kite.trade/docs/connect/v3/margins/),
[Zerodha bear-put spread mechanics](https://zerodha.com/varsity/chapter/bear-put-spread/).

#### F0 — shared F&O risk contract (highest-priority planned implementation)

Problem/contracts: one authoritative per-source F&O capital/risk view shared by
single-leg and DR entries. Add a pure typed risk admission result backed by
exact partial/terminal cash and **OPEN/UNRESOLVED/in-flight reservations**.
Integrate `fno_risk.py`, `fno_gates.py`, `fno_orchestrator.py`, `fno_dr_book.py`
and existing position/settlement adapters. Do not import the orchestrator into
the risk module or invent fills to release reservations.

Acceptance: identical day/week/month/drawdown decisions across both books;
partial and spread losses counted once; stale/malformed capital fails entry
closed; competing entries cannot double-spend (transactional/idempotent
reservation); unresolved exits retain exposure; management/exits remain
allowed while entries halt. Bound joint catastrophic payoff plus fees, not just
planned stop loss. Defaults/owner policy must be explicit before rollout.
Review new limits for reachable affordable trades; do not solve by blindly
adding thresholds or automatically consuming more bankroll.

Rollout: characterization tests first, additive versioned paper risk receipts,
independent review, GitHub promotion, observe paper admissions/settlements.
Never turn on live spreads. Rollback reverts the admission policy code only,
preserving cash/reservation evidence; emergency entry disable is separate from
exit authority. This slice is **planned, not implemented** in the current turn.

**October 3 F0-A — shared evidence/reservation foundation (Dev only).**
`fno_shared_risk.py` now supplies a source-scoped, fail-closed read model over
the exact `TRADE_CLOSED` ledger cash, `OPEN`/`UNRESOLVED` single-leg losses,
`OPEN`/`UNRESOLVED` defined-risk losses and durable in-flight reservations.
It rejects missing tables, non-finite cash and missing worst-case values rather
than treating them as free capital. Its reservation operation takes a SQLite
immediate transaction, is idempotent only for the exact still-reserved key, and
has one-way consumed/released receipts; nothing is auto-expired. Focused
characterization includes cross-book loss, unresolved exposure, malformed
evidence, source isolation, capacity exhaustion and one-way resolution.
Verification: `python-engine/winvenv/Scripts/python.exe -W error -m pytest
python-engine/tests/test_fno_shared_risk.py python-engine/tests/test_fno_risk_switches.py
python-engine/tests/test_fno_max_loss.py python-engine/tests/test_fno_isolation.py -q`
reported **49 passed**. The unchanged broader lifecycle selection reported
**52 passed** without warnings-as-errors; its warnings-fatal version reached
99 assertions before two known Windows/FastAPI socket-lifespan warnings were
escalated, so it is not claimed warnings-clean.
Source commit: `7b86d85` on `codex/production-correction-hedge-p0`; Dev-only
and pushed to GitHub; not deployed/Promoted. This additive local SQLite table is a schema impact
only once an entry caller invokes it; no deployed database was touched.

This is deliberately **not yet an entry-policy change**: neither existing
single-leg nor DR admission has been wired to reserve/consume in the same
transaction as its position insert, and existing exit authority is untouched.
The next F0 slice must do that end-to-end, bind actual fee-inclusive catastrophe
cash, make shared day/week/month/drawdown decisions authoritative for both
books, and add restart/partial-settlement race coverage. No Production schema,
configuration, broker, order or message action occurred.

**October 3 F0-B — atomic paper-admission binding (Dev only).** Both paper
entry paths now reserve their full structural worst-case loss plus the existing
zero-premium catastrophe-exit fee estimate before dispatch/admission. A refused
or malformed shared view skips only that new entry; it does not change sizing,
quote selection, strategy conditions, management or exits. On success, the
single-leg/DR row and its matching reservation consumption share one SQLite
immediate transaction. A rejected executor explicitly releases its reservation;
a filled order whose durable receipt fails retains the reservation for
reconciliation rather than falsely freeing capital. The unchanged paper fixture
still admits its feasible single leg and debit spread, and proves both consumed
receipts. Shared day/week/month/drawdown enforcement and actual partial
settlement release remain the next F0 slice.
Source commit: `0ba2d29` on `codex/production-correction-hedge-p0`; Dev-only,
pushed to GitHub, not deployed. It adds an additive local reservation table used by paper entry;
no Production schema/data, configuration, broker or message action occurred.

**October 3 F0-C through F0-E — shared policy and verified partial residuals
(Dev only).** F0-C applies the existing day/week/month, drawdown and
consecutive-loss policies to both paper books from all exact source-scoped
`TRADE_CLOSED` cash. F0-D makes an open live partial residual usable only when
its ordered quantity/generation chain, ledger identity and pro-rata loss agree.
F0-E closes the remaining source-integrity gap: recovery rows persist the
entry/fill/gross/cost/net values from their atomic resolution transaction, the
shared view verifies their broker-evidence digest and exact linked ledger cash,
and additive triggers protect recovery receipts plus populated quantity/loss
baselines from rewrites. Missing legacy partial economics fail new entry closed;
no historical data is fabricated. No threshold was tightened, and no broker,
live-spread, signal, sizing or exit-management authority changed. Focused
shared-risk/recovery selection: 32 passed warnings-fatal (two documented
non-F0 test exclusions); broader F&O admission/lifecycle/DR/orchestrator
selection: 150 passed normally. Its warnings-fatal form has one pre-existing
socket-lifecycle warning in an orchestrator timing test. F0 Dev source work is
complete pending GitHub promotion and paper admission/recovery observation;
F1 is still required before any live funding. Source commit `a9fef57` is
Dev-local, not pushed or deployed.

#### F1 — cash-only funding and catastrophe acceptance

Before real allocation, pin operator-approved funding semantics. Introduce a
read-only broker cash/margin adapter with current funds, existing orders,
initial/final basket margin and charges. Admission requires both assigned
available capital and cash-only broker capacity, with bounded contingency;
never use other divisions or assumed credit. The current DR paper logic is not
a live multi-leg executor: any live implementation needs separate authority,
hedge-first fill confirmation, partial-leg/unwind reconciliation and explicit
no-unhedged-short invariants before it can be considered.

Test premium-to-zero, quotes missing until flat, engine restart/dead transport,
gap stops, rejected/unfilled exits, expiry/lot rolls, multiple correlated open
positions, failed hedge leg, margin change and broker/internal disagreement.
Report residual losses and recovery needs; never label a simulation an absolute
capital guarantee. Keep broadening to stock options/futures out of this slice.

#### F2 — profitability research, not blind gate relaxation

Implement the full current-policy replay and licensed-data work in the October
2 F&O assessment. Compare paired exit hypotheses before opening more risk.
Then examine entry timing/re-entry, regime suitability, executable spread width
and joint allocation on future/untouched data. Deliver MFE/MAE, premium theta/
IV contribution where evidenced, cost/slippage stress, missed-fill and time-
deadline attribution, winner concentration and session-level uncertainty.
Freeze each hypothesis before its evaluation sample; keep baseline results.
Any promotion is a reviewed paper-policy change, not autonomous live authority.

### 3. Backtest catalogue — shipped strategies only

| Module/book | Existing reusable tooling | Fidelity / work still needed |
| --- | --- | --- |
| Classic Penny MIS Breakout | `penny_intraday_replay.py`; Lab `penny_breakout_intraday_1m_replay` | Current entry evaluator; one-share shadow exit, default calm regime; full runtime gates/sizing/smart-EOD missing |
| Classic Penny CNC Connors | `penny_engine_connors.py`; inspect daily tools | Adapter must reuse exact CNC entry/exit; don't confuse with EDGE Connors |
| Adaptive Penny EDGE / Connors | `penny_edge_backtest.py`; `tools/connors_backtest.py` | Separate shipped family; fee/entry/exit/sizing parity review required |
| Penny daily proxy research | Lab `penny_breakout_daily_proxy`, `..._walk_forward`; `penny_backtest_v2.py` | Different daily strategy; no full costs, cannot validate MIS profitability |
| Intraday Momentum | `momentum_replay.py`; Lab `momentum_intraday_15m_replay` | Entry/exit replay exists; historical regime, universe, shared paper admission/capital need binding |
| Momentum exit/timing/allocation studies | `momentum_exit_experiment.py`, `momentum_entry_timing_research.py`, `momentum_allocation_research.py` | Paired research, not full-strategy historical portfolio |
| Swing regime daily | `backtest.py`; Lab `swing_regime_daily` | Shared daily evaluator; proxy regime/neutral VIX/breadth, no modeled fees; not full deployed portfolio |
| Range reversion | `range_reversion.py` and dispatcher | Explicit shipped-policy adapter, historical context and shared risk/exit contract needed |
| F&O single-leg momentum | `fno_backtest.py`, `fno_exit_experiment.py`; Lab FNO adapter UNAVAILABLE | Synthetic old full walk or real exit-only research; exact current full-policy replay missing |
| F&O debit spread / iron condor | `fno_dr_exit_experiment.py` | Exit-only evidence-bound research; full entry/portfolio/execution replay missing |
| Partner tips / conditional protection | `partner_full_policy_replay.py`, chronological spread/holdout tooling | Evidence-specific advisory replay, not an automated money book; qualification separate |
| Proactive research | `proactive_*_research.py` | Separate research policy, not automatically a tradable Sentinel module |

Do not count alerts, AI reviews, gateway transport or hedge informer as standalone
return-producing strategies. A future catalogue must enumerate real strategy
identities, modes, authority and fidelity; not promise every Python module has P&L.

### 4. What stock libraries can and cannot provide

Daily stocks are easier than expired option chains. A Python library is a client,
not a guarantee of free complete history. The inspected Production cache holds
1,235,334 daily rows across 5,642 symbols, dating back to August 2023, and
781,275 labelled minute rows across 186 symbols, July 30–October 1. Coverage
is per-symbol and includes sparse/truncated sessions, zero-trade bars and mixed
intervals. Stocks missing from today's universe/delisted names must not vanish.

Yahoo/yfinance can be an explicitly labelled daily research source; its official
download docs constrain intraday history to recent data (60 days), not arbitrary
past dates. Raw/split-adjusted/total-return series are distinct contracts; avoid
silently adjusted prices with unadjusted volume/stop levels. Use broker/licensed
intraday data where needed, exchange calendars/actions, and persist immutable
cache/provenance so old inputs remain reproducible. No libraries were installed
or network market data downloaded this turn.
[yfinance download documentation](https://ranaroussi.github.io/yfinance/reference/api/yfinance.download.html).

### 5. Concrete cross-module backtest implementation plan

**B0 — catalogue and one offline entry point.** Extend `backtest_lab.py` rather
than create another simulator. Add a registry/CLI under existing research tools:
`catalogue`, `coverage`, `snapshot`, `run`, `compare`, `report`. A request names
one shipped strategy ID and current-release policy, dates, universe version and
capital assumptions. Reject arbitrary callback/code strategies and unsupported
fill/fee overrides. Show scope `EVALUATOR`, `LIFECYCLE` or `FULL_PORTFOLIO`;
do not advertise an evaluator study as the complete live system. Reuse existing
authenticated research routes later, never use Production routes during testing.

**B1 — immutable multi-resolution data adapters.** Separate daily/minute/
15-minute/futures/option datasets. Validate interval/clock/timezone, OHLC bounds,
duplicates/conflicts, exchange sessions, holidays/haltdays, corporate actions,
listing/universe membership, missing warm-up and point-in-time data publication.
Mixed known intervals should be selectable without treating one as another;
`legacy_unknown` stays unavailable. Handle zero-volume no-trade bars explicitly:
they can inform a mark/clock but cannot prove an executable fill. Complete-session
coverage requirements must be strategy-specific, not blindly forward-filled.
Default `PARTIAL`/`UNAVAILABLE` on missing required evidence, never zero-profit
success. Freeze providers/licensing, raw hashes, actions, warm-up and gaps.

**B2 — exact classic Penny lifecycle first.** Keep the executed baseline
diagnostic. Add characterization fixtures binding real evaluator decisions,
bar-open versus completed-bar availability, next executable fill after latency,
broker-style fees, stop/gap/circuit/illiquidity behavior, partial targets, time
stops and smart-EOD exits. Then exact CNC Connors adapter. Reconstruct historical
Penny regime/scanner/risk/universe and same-time admission/available cash before
claiming full portfolio returns. Preserve no-trade runs and investigate reasons,
not adjust thresholds just to manufacture a profitable sample.

**B3 — Swing and EDGE daily parity.** Audit existing helpers for their exact
family; freeze existing defaults. Replace proxy market regimes with timestamped
NIFTY/VIX/breadth only where available, share current exits/fee functions and
prior-known corporate/universe facts. Model suspended/delisted stocks and
next-session entry causality. Unit and differential tests compare live decisions
and replay; no daily Penny proxy substitution for the intraday strategy.

**B4 — Momentum and range lifecycle/portfolio.** Reuse Momentum evaluator and
exit studies; add exact admission outcomes, capital reservations, correlated
positions, paper path binding and historic regime inputs. Distinguish near-miss/
counterfactual allocation from real baseline. Add explicit Range adapter rather
than relabel a Swing result. AI context cannot be backfilled from present news;
replay deterministic policy or archived advisory context with declared scope.

**B5 — F&O/partner evidence adapters.** Execute F0/F1 before live consideration.
Reuse typed masters/quotes, exact economics and existing spread/full-policy
research. Exit-only sample cannot reproduce missed entry decisions. Buy licensed
data only after the owner chooses provider/cost; retain unavailable coverage.
Partner outputs cannot auto-register qualification or send tips from a backtest.

**B6 — professional comparison/reporting.** Require policy/code/settings/data
manifest; same input universe and chronology across comparisons; exact cash
reconciliation and known unavailable paths. Output net/gross/fees/slippage,
trades/exposure/turnover, win/loss distribution, MFE/MAE, holding time, drawdown
on marked equity where possible, month/regime/session slices, risk-adjusted
returns only with a valid cash/equity clock, winner exclusion and bootstrapped
session uncertainty. Predeclare walk-forward/untouched holdout and guard against
overlapping folds, search leakage, survivorship and repeated test selection.

Rollout/rollback per B0–B6: offline Dev first, deterministic fixtures and parity
tests, read-only datasets and bounded temporary artifacts; then GitHub deployment
of research surfaces only. No order/API secrets, automatic capital changes,
partner qualification or runtime strategy switch. Reverting a research adapter
must preserve archived reports/manifests. Acceptance is evidence/code correctness,
not a promise of profit. New strategy tuning requires a separate declared study.

Target interface after adapters, **not a command implemented today**:

```
research_cli backtest run --strategy penny_breakout_full_policy \
  --from YYYY-MM-DD --to YYYY-MM-DD --dataset <frozen-manifest> \
  --policy <current-release-manifest> --output <new-research-report>
```

We can accept any dates, but must honestly answer unavailable/partial when data
does not cover them. "Any strategy, any historical date, exact results" is not
currently code-ready and cannot be guaranteed by installing a stock library.

### 6. Penny run and verification receipt

Current-Dev baseline, August 11–20, PCJEWELLER and SOUTHBANK only:
5,790 minute rows, 1,506 prior daily rows, 16 ticker-days (eight calendar trading
dates each), 5,774 evaluations, **zero entries/closes**. Net profit/return,
profit factor, expectancy and drawdown are unavailable—not zero-risk evidence.
Both August 17 sessions end early (270 rows, no time-exit bar); remaining
14 ticker-days have 375 rows. The sampler did not insert missing bars or invent
an exit. Full date/session coverage and historical universe are not established.

Artifacts: `2026-10-03-penny-baseline-unavailable.json` retains the zero-volume
alphabetical attempt; `2026-10-03-penny-baseline-results.json` retains the
five-equity mixed-interval rejection; `2026-10-03-penny-baseline-two-stock-results.json`
is the completed diagnostic. All three are intentional records, not three
profitability samples. Existing rejection strings include prices/minute values,
splitting histogram categories; add bounded reason codes to research reporting
without changing evaluator behavior in B2.

Implemented: offline baseline CLI and research-only SQLite connection closure.
No F&O risk/entry/exit change, no generic all-module full backtester implemented,
no new provider, dependency, schema, Production edit/restart or broker call.
Temporary Dev research DBs are cleaned after success/unavailable paths; the
first failed Windows attempt left a uniquely named temporary file, not any
Production artifact (safe cleanup can be handled separately).

Commands/results:

- `python-engine/winvenv/Scripts/python.exe -m pytest scripts/tests/test_run_penny_research.py -q -W error`: **4 passed**, normal exit.
- Engine `tests/test_penny_intraday_replay.py -q -W error`: **11 passed**, normal exit.
- Engine Penny replay/Lab/F&O max-loss/risk-switch/defined-risk focused selection:
  **82 passed, one known HTTPX TestClient deprecation warning**, normal completion.
  Initial warnings-fatal combined run: 81 passed, one failure caused by that
  existing warning; no strategy assertion failure. Do not claim combined run
  warnings-clean. No dependency upgrade was attempted.
- CLI execution via `--container python-engine` is read-only SQLite collection
  over stdin, current **Dev** policy replay locally, output in Dev docs.
  Successful command uses `--tickers PCJEWELLER,SOUTHBANK`; baseline dates above
  are defaults. Future reruns need a new output path (overwrites rejected).
- Read-only container Python lacks app pydantic imports; no dependency install
  or application entry point invoked. This does not diagnose a running-service
  failure; it limits effective-settings verification for this inspection.
- Source/dataset identities are in the successful JSON. Tests verify mechanisms,
  not profits. Commit recoverable with `git log -- scripts/run_penny_research.py`.

## Next priority and fresh-task handoff

Start with F0 shared risk semantics and B1 data contracts, then B2 full classic
Penny lifecycle/coverage. Explicit owner semantics for permitted broker blocked
margin versus forbidden borrowing must precede any live funding. R6 deployment/
reconciliation/partner qualification/canary gates remain distinct. Fresh-task
orientation: `2026-10-03-successor-inheritance.md`.
