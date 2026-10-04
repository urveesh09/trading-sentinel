# F&O profitability assessment — October 2, 2026

## Plan slice (before implementation)

Question: does the current F&O policy have a profitable, deployable edge over
the last few months? Assess Production evidence read-only; change Dev only.

Implement `scripts/assess_fno_profitability.py`, a standard-library-only
read-only SQLite evidence report. Separate single-leg and defined-risk books,
paper/live sources, closed/partial cash, unmatched/duplicate settlement rows,
monthly results, closed-trade profit factor, realized drawdown and removal of
the best winner. Inventory archive session directories and retained candle
coverage without claiming quote completeness. This is an operational history
assessment, **not a current-policy historical backtest**.

Acceptance: SQLite `mode=ro`, one consistent read transaction; no migrations,
network provider calls, orders or messages; exact origin/source joins only;
missing/duplicate/mismatched/nonfinite evidence fails reconciliation. Focused
tests cover those cases, partial cash and UTC/IST month boundaries. Execute
against the existing Production container by streaming the script to stdin;
all output files remain in Dev. No source/config change inside Production.

Rollout: inert developer CLI, no runtime caller or dependency. Rollback: remove
the CLI/artifacts; no configuration or schema rollback. Remaining: obtain
historical executable quotes and contract masters, freeze current entry/exit/
cost policies, implement a full-policy chronological replay, then evaluate
independent sessions and realistic fill/cost stress. Do not retrofit a new
freeze onto earlier data and call it a prospective holdout.

## Executed results

The read-only Production database was assessed for July 1–October 1 inclusive,
using IST exit/cash dates. No container files/configuration were edited and no
service was restarted. The collector ran via stdin with a read-only SQLite
connection and one read transaction. The JSON report is
`2026-10-02-fno-profitability-results.json`; its snapshot digest identifies the
input collection, not authenticated provider provenance. Archive directory
inventory is not atomic with the SQLite snapshot and is not completeness proof.

### All retained position results — **not fully cash-reconciled**

| Exit month | Single-leg paper | Defined-risk paper |
| --- | ---: | ---: |
| July | -₹14,159.83 (13 closes) | -₹159.03 (4 closes) |
| August | -₹12,617.34 (14) | -₹7,269.33 (12) |
| September | +₹975.41 (10) | +₹2,046.08 (11) |
| October 1 only | +₹7,434.53 (1) | +₹1,660.57 (1) |
| Total | **-₹18,367.22 (38)** | **-₹3,721.71 (28)** |

These are stored terminal position P&Ls, not independently verified historical
fills. Policies and contract handling changed during this period. This is not
evidence that the *current* policy would lose or profit on those dates. The
combined reported loss is ₹22,088.93; a percentage return cannot be inferred
from these records without a historical funding/reservation/equity reconstruction.

### Exactly linked retained cash subset — September 17–October 1

| Book | Closes | W/L | Net after stored costs | Profit factor | Realized cash drawdown |
| --- | ---: | ---: | ---: | ---: | ---: |
| Single-leg paper | 9 | 5/4 | +₹10,755.67 | 4.23 | ₹2,056.25 |
| Defined-risk paper | 7 | 5/2 | +₹3,187.60 | 3.70 | ₹850.66 |

Combined linked net: ₹13,943.27. These 16 closes occur on only seven distinct
session dates, and the books share directional signals. They are not 16
independent demonstrations of an edge. No retained live F&O positions were
found; empty live results mean no demonstrated live execution performance.

Removing the single-leg best winner (+₹7,434.53) leaves +₹3,321.13. Removing
both that winner and the September 28 +₹4,710.54 winner leaves approximately
**-₹1,389.40**. Removing the spread best winner leaves +₹1,527.03. A trend
strategy can legitimately rely on big winners, but this tiny sample does not
estimate their future frequency. Drawdowns are realized cash only, not
intratrade drawdown or a future worst-case loss.

Reconciliation is globally **UNAVAILABLE**: 29 earlier single-leg and 21 earlier
spread positions lack exactly keyed terminal cash; 50 old cash rows cannot be
assigned using exact source/origin keys. Do not guess matches by date/ticker,
silently discard the early losses, or classify all history as reconciled.
The recent matching rows validate retained arithmetic, **not pricing realism**.
October 1's legacy spread row has 75-unit sizing and unbound leg JSON, whereas
the same-day single-leg has 65 units; this is an evidence limitation, not a
newly diagnosed current-Dev contract bug. Dev already uses exact contract-bound
spread handling. Old modeled/mid marks must not be presented as live fills.

The October 1 audit's opening figures conflict with its detailed tables.
Direct DB results also correct its linked spread total ₹3,186.60 to ₹3,187.60
and September 28's stated single-leg ₹5,026 to the actual three-close total
₹5,026.13 (largest trade ₹4,710.54). No Production audit was rewritten.

## Can the requested current-policy multi-month backtest run now?

**Not defensibly from the retained inputs inspected.** Quote archive directory
days cover September 10–October 1, just 14 dated directories, not July–September
coverage. Their contents have not been promoted to complete executable paths.
Token-specific 5-minute candle caches begin at earliest August 25; underlying
candles alone cannot establish option/spread fills, IV changes or liquidity.

`python-engine/fno_backtest.py` is a synthetic Black-76 constant-IV single-leg
simulation. It hardcodes 75-unit lots, synthesizes expiries, passes unavailable
microstructure fields and maintains its own bar-level exit ladder. It does not
exercise today's shared single-leg evaluator, complete orchestration, exact
spread book or historical contract changes. Its passing mechanism tests do not
make a run a test of the current F&O policy. No invented option paths or
synthetic profit percentage are reported here.

Kite's continuous history supports expired **futures day candles**, not a full
expired-option intraday chain with executable quotes. Source:
[official historical API documentation](https://kite.trade/docs/connect/v3/historical/),
[Zerodha expired F&O history guidance](https://support.zerodha.com/category/trading-and-markets/charts-and-orders/charts/articles/historical-data-for-expired-f-o-contract).
No paid data was purchased, provider requests made or secrets printed.

## Concrete next implementation/data plan

1. **Pin the policy and market-data contract.** Select the current release,
   runtime settings/cost snapshot and exact two books. Record source hashes,
   July–September dates plus warm-up, regime provenance, real expiry/calendar/
   lot changes, risk pool and capital/reservations across both books. Never
   call retrospective development data prospective HOLDOUT.
2. **Obtain licensed historical inputs.** Operator supplies a local dataset
   or chooses a provider: synchronized futures 5-minute bars and sufficiently
   granular option bid/ask (all candidate strikes/expiries), OI/volume, contract
   masters and exchange timestamps. Daily option candles or only traded strikes
   do not support exact chain selection. Missing quotes remain unavailable;
   do not interpolate executable prices or assume zero fills on unavailable days.
3. **Implement the smallest full-policy replay.** Reuse the current entry/gate/
   risk/exit and executable spread settlement functions. Each decision sees only
   data known then; fill after decision latency at executable sides; represent
   rejected/missing entries, incomplete exits and partial cash explicitly.
   Maintain a shared capital book and real hard-flat/expiry deadlines. No
   runtime caller or live authority. Existing S6 exit-only replays remain useful
   for exit attribution but are not a full-strategy backtest.
4. **Acceptance tests.** Characterize current Production/Dev differences;
   check shared evaluator parity, look-ahead rejection, roll/lot/calendar cases,
   stale/missing/crossed quotes, partials, same-time signals/capital exhaustion,
   ambiguous bar paths and missing flat quotes. Independently reconcile replay
   gross/cost/cash and rejected-path coverage. Freeze data and report manifests.
5. **Evaluate without cherry-picking.** Report each book and their shared
   portfolio by month/regime/session; complete and unavailable coverage, net
   expectancy, profit factor, marked-equity drawdown, adverse excursions,
   capital usage, winner concentration and block/session uncertainty. Stress
   fees/spreads/slippage and delayed fills. Reserve untouched sessions before
   tuning, then validate prospectively on newly deployed keyed paths.
6. **Money decision remains separate.** Set acceptable loss/drawdown and
   capital budget with the owner, complete deployment/reconciliation checks
   and independently review the evidence before any separately authorized
   small live pilot. No minimum trade count by itself authorizes funding.

**Conclusion:** recent paper improvement is encouraging; sustained profitability
of today's policy is **not established**, and allocating capital based solely
on this evidence would be premature. Historical data procurement is the next
blocking choice; waiting more days alone cannot recover July option quotes.

## Verification receipt

- Dev CLI and artifact only; no schema/config/runtime caller changes.
- `python-engine/winvenv/Scripts/python.exe -m pytest scripts/tests/test_assess_fno_profitability.py -q -W error`: **12 passed**, normal exit.
- `python-engine/winvenv/Scripts/python.exe scripts/assess_fno_profitability.py --container python-engine --output docs/2026-10-02-fno-profitability-results.json`: executed successfully; global reconciliation correctly unavailable.
- A first intermediate output was replaced by the final, richer report; only
  that newly generated Dev intermediate artifact was removed. No user evidence
  or Production files were removed.
- Existing `test_fno_backtest.py`, `test_fno_exit_experiment.py` and
  `test_fno_dr_exit_experiment.py`: **49 passed**, warnings-fatal, normal exit.
  These are mechanism/evidence regression checks, not profitability tests.
- `python scripts/build_system_code_atlas.py`: 228 engine/agent modules,
  unchanged atlas (developer scripts are outside its indexed scope).
- `git diff --check`: passed. No configuration/migration/promotion impact.
- Local implementation commit can be recovered with
  `git log -- scripts/assess_fno_profitability.py`; this slice is not pushed or
  deployed. Input checkout was `e313e662f7b06f667fda427a30271b8afb974469`.
