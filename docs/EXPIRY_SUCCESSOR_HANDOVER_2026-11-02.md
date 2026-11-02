# Expiry successor handover — November 2, 2026

> **Update, November 2 evening.** The owner resumed this work. E01.1 is now built, frozen, scored and in Dev: [report](EXPIRY_RESEARCH_E011.md), [study](research/simulation/2026-11-02-expiry-e011/README.md). Section 1's "no E01.1 exists" and section 8's "untested" no longer hold. Section 7's warning proved exact: none of September's 11 breaks has a ticket in the files.

This document inherits **expiry-v3, completed E01, deferred E02 preparation and
the unfinished E01.1 request using September ten-second data**. Regular F&O
N11/N11T is covered in the [separate handover](FNO_SUCCESSOR_HANDOVER_2026-11-02.md).

## 1. Exact stopping point

The owner's latest instruction is **create two handovers only**. No E01.1
strategy has been implemented, frozen, scored, committed or deployed. Do not
continue the strategy search merely because a next-step outline appears here.

Before that instruction, the active research request was:

> Use the four full September expiry sessions derived from genuine one-second
> history to test the current strategy and, if useful improvements exist, make
> E01.1. Do not adjust the strategy to minute-by-minute data.

This superseded a just-started multiyear minute-data E02 study. E02 reached
data preparation only. **No strategy was scored on its minute dataset.**

The owner wants expiry upside, including occasional very large option moves,
with controlled paid-ticket losses. Do not promise to catch every "zero to
hero," guarantee a superior version, or hide failed hypotheses. E01 improves
loss shaping on eight known dates; it does not establish future profitability.

## 2. Source and environment identities

| Item | Identity/status |
|---|---|
| Dev | `C:/Users/Urveesh/Desktop/trading-sentinel` |
| Branch | `codex/production-correction-hedge-p0` |
| Reviewed Dev HEAD | `7711521f14cd0f044b9d2c68c9f33d8f6c4c841e` |
| E01 original research freeze | `cbbdebbb8c9f2faf0dd2f56b0cbe62f37ff28ccf` |
| E01 results | `c6537c602897b1ae4f29601bdbcf1b308b20002d` |
| E01 native integration | `9dd488144da2601b4e87992184a159f1205f72c0` |
| Identity handoff | `7747344`; final evidence-path correction `7711521` |
| Production Git HEAD, fresh read-only check | `d52642f5cbc973646a1bd9f8a1e207014d2985ee` |
| Engine, fresh read-only check | Running; start `2026-11-02T03:29:35.254673416Z` |
| E01 deployment | Pushed in Dev, not merged/deployed by this work |

Production was not edited, restarted, configured or deployed. No research
broker order, Telegram delivery or ICICI request was made. Git HEAD and
container start checks are not a fresh running-image-source attestation.

Start with `AGENTS.md` and the four required documents:
[guide](SYSTEM_GUIDE.md), [atlas](SYSTEM_CODE_ATLAS.md),
[plan](NEXT_AGENT_PLAN.md), [checklist](HANDOVER_CHECKLIST.md). Main expiry source
is `python-engine/expiry_paper.py`; flags are in `python-engine/config.py`.

## 3. Reading order and retained evidence

1. [E01 plain-language report](EXPIRY_RESEARCH_E01.md) and its JSON counterpart.
2. [E01 README](research/simulation/2026-11-02-expiry-e01/README.md),
   [plan](research/simulation/2026-11-02-expiry-e01/PLAN.md),
   [frozen round](research/simulation/2026-11-02-expiry-e01/ROUND1.md),
   [outcome](research/simulation/2026-11-02-expiry-e01/ROUND1_OUTCOME.md),
   [verification](research/simulation/2026-11-02-expiry-e01/VERIFICATION.md),
   and [identity](research/simulation/2026-11-02-expiry-e01/IDENTITY.json).
3. That study's `configuration.json`, `freeze-round1-v2.json`, `audit-results.json`,
   `native-parity-final.json`, `replay.py`, `verify_native.py` and `policies.py`.
4. Private evidence under that directory's `_local/`: immutable replay outputs,
   archived source, SQLite snapshot and final skill packet. These are not
   committed data and must remain on disk.

The successful private final packet is
`_local/evidence-report-final/VERIFIED.json`: **EVIDENCE_CHECKS_PASSED**, zero
errors, Git SHA `7711521...`, four modules and 898 sealed files. It explicitly
says post-run packaging, not preregistration, and whole-system profit
unavailable. A failed relative/absolute-path packet is retained separately.

## 4. Native expiry contracts to preserve

The main paper book is three independent experiments, not one shared broker
account. Each has its own default Rs 2,500 daily full-premium/fee ceiling.

| Play | Entry/management role |
|---|---|
| A | Confirmed index/futures breakout of the 13:00–13:30 box; premium stop, failed break, time stop, banking/trail |
| B | Late CE+PE strangle, entered 15:13:30–15:15; whole-pair profit target |
| C | Cheap directional option on breakout; structure exit, large-move banking/trail; baseline has no premium stop |
| CE01 | Exact-entry C shadow plus the fixed 30% premium backstop |

Important current constants: at least 30 box samples; two confirming
observations within 25 seconds; option quote maximum age 20 seconds; A flat
15:13; final flat 15:38. C's premium band is spot times 0.00004 through 0.0003;
it selects eligible contracts at the actual signal, not the day's opening ATM
strike. A may have two sequential entries; C one; native size ceilings are A/B
four lots, C ten, all still subject to funded depth and daily budget.

C banks half at three times entry, then trails only after the larger peak
threshold (five times entry, keeping 60% of peak). E01 inherits those upside
rules and adds the 30% stop. Flat, triggered/pending exits, missing depth and
partial fills retain native priority and behavior.

Key functions: `new_day_state`, `update_box`, `breakout_signal`, `failed_break`,
`manage_position`, `_try_exit`, `_new_position`, `_sell`, `_save_position`,
`affordable_fill`, `worst_case_loss`, and the E01 copy/pairing functions.
Use native fees, not a substitute flat-cost formula.

`manage_position` can mark banking pending before a fill; actual `_sell`
events determine proceeds and remaining lots. Do not claim capital recovery
because a trigger fired. Closing exits remain pending through missing depth
and later rebounds; never reopen them merely because price improved.

## 5. Completed E01: behavior, results and limits

`CE01`, version `expiry-e01-v1`, is a separate paper shadow in shadow-v6. It
copies **only a successfully saved fresh C entry**, matching contract, time,
price, quantity, fees and full-premium ceiling. Paired results require durable
parent identity **and** immutable economics. Legacy/missing/mismatched evidence
is unavailable, never silently zero.

`EXPIRY_E01_SHADOW_ENABLED` defaults true. New-day enrollment/version is bound
in state; old or already-started days are not retroactively enrolled. False
blocks new copies but existing CE01 legs keep exits/reconciliation. No schema
migration or extra quote call is required. No per-trade shadow Telegram is
sent; the existing summary carries the comparison. Main A/B/C and N11 stay
unchanged. Rollback the new-entry flag, preserving open-leg management.

Comparison is **A+B+CE01 instead of A+B+C**, never the sum of all four.

| Eight already-seen expiry sessions | Current v3 | E01 alternative |
|---|---:|---:|
| Modeled net | 6,548.10 | 11,095.17 |
| Worst session | -1,427.00 | -1,000.15 |
| Running daily-P&L drawdown, rupees | 4,520.04 | 2,100.73 |
| Net excluding the largest winner | -7,232.64 | -2,685.57 |
| NIFTY net | 9,986.91 | 11,634.74 |
| SENSEX net | -3,438.81 | -539.57 |
| Positive / negative / zero sessions | 1 / 6 / 1 | 3 / 4 / 1 |

Dates: Oct 6 NIFTY; Oct 8 SENSEX; Oct 13 NIFTY; Oct 15 SENSEX; Oct 19 NIFTY
(holiday-shifted expiry); Oct 22 SENSEX; Oct 27 NIFTY; Oct 29 SENSEX.
There are 7,594 observed ticks. October 22 is a genuine zero-entry session,
not an omitted loss or unavailable result.

At asks +0.05 and bids -0.05 with unchanged depth/clocks, E01 net is 10,994.22
versus 6,361.82; worst session -1,022.95 versus -1,441.98. The 20%/40%
diagnostics support the fixed 30%; 20% scored higher but was not substituted.
The other predeclared idea, a 30% whole-strangle loss exit, **failed**: net
5,758.39, worst session -2,960.10, drawdown 4,739.64. Do not silently reintroduce it.

Paper fill-event net is 14,059.17 versus 13,791.10. Assumed residual settlement
is -2,964 versus -7,243. Most improvement comes from earlier recorded-bid exits
instead of assumed write-offs. Settlement uses sampled index values, not an
official settlement receipt. Auction-window execution remains unverified.
Missing/stale bids remain non-fills. A 30% trigger cannot cap a gapped option's
loss at 30%; the paid ticket and fees remain at risk.

October 6 has weaker evidence: no raw index/futures clocks and only one depth
level. Later seven sessions retain raw clocks/depth. The instrument catalogue
is reconstructed from recorded eligible contracts, not a complete dated master.
Do not label this a multiyear test, finite shared-capital portfolio or broker
realized profit. Ex-best and SENSEX totals remain negative.

## 6. Verification and replay traps

Recorded completed checks, not rerun for this Markdown task:

- Historical source replay: eight sessions / 95 position legs match money and
  events, with only the declared legacy `bank_pending` DEFAULT-0 normalization.
- 80 predeclared research cases; 11 research tests; 63 existing expiry tests.
- Affected suite 95 passed before final binding; final E01/paired/summary
  regression 28 passed, including all 24 E01 tests after binding hardening.
- Three successive 16-case native integration runs. All main A/B/C economics
  and quote-call counts unchanged; CE01 equals the frozen candidate.
- Independent final audit: 128 research/integration executions, 506 legs,
  974 price/depth checks and 426 budgets pass. These executions reuse eight
  sessions; they are not 128 independent market days.

Do not overwrite `NATIVE_E01_FINAL` cases: the runner rejects reused paths.
New engineering needs a new labeled output. `replay.py` computes `primary`
from A+B+C; a new shadow comparison must explicitly substitute the candidate
for C. Never count a shadow as added portfolio profit.

The active original freeze is `freeze-round1-v2.json`; the original draft was
retained. All 696 original source/config files and 30 inputs were sealed;
original bytes are in `_local/frozen-source/`. Integration deliberately changes
the app relative to that research freeze. Reproduce with archived source or
perform a separately bound integration run. **Do not weaken the freeze or
silently replace old hashes with current code.**

On Windows, disable external networking inside the initialized async runner,
not before event-loop creation: the latter breaks its internal socket setup.
No credentials are needed for replay. Research must not send messages/orders.

Useful affected check after an actual source change, from Dev:

```powershell
& .\python-engine\winvenv\Scripts\python.exe -m pytest python-engine/tests/test_expiry_paper.py python-engine/tests/test_expiry_e01.py python-engine/tests/test_fno_isolation.py python-engine/tests/test_cost_schedules.py -q
```

## 7. New fine-resolution data: exact location and limits

Existing source export, read-only:

`C:/Users/Urveesh/sentinel-operations/breeze-history-20261029/data/nifty-expiry-10second-20261102/`

Read `coverage.json` and `README.md`. CSV names are
`NIFTY-YYYY-MM-DD-ATM-CE-PE-10second.csv`; September 1 instead ends
`-10second-PARTIAL.csv`. These are genuine one-second-history OHLC observations
aggregated into ten-second bins, **not** minute candles fabricated as seconds,
and **not** bid/ask ticks.

| Expiry | Fixed opening ATM strike | CE / PE ten-second bins | Missing original seconds, CE / PE |
|---|---:|---:|---:|
| 2026-09-08 | 23,750 | 2,250 / 2,250 | 177 / 179 |
| 2026-09-15 | 23,600 | 2,250 / 2,250 | 279 / 1,285 |
| 2026-09-22 | 23,450 | 2,250 / 2,250 | 301 / 300 |
| 2026-09-29 | 22,750 | 2,250 / 2,250 | 420 / 406 |

Each full grid is 09:15:00–15:29:50, 4,500 rows per day. Across eight legs,
3,347 original seconds are missing. Full ten-second grid does **not** mean
gap-free original seconds. Per-row provenance columns include observed/missing
seconds and invalid-volume counts. The export reports zero invalid-volume
source seconds for these four days. Gaps were flagged, never filled.

September 1 is partial: CE 192 bins through 09:46:50; PE 96 bins through
09:30:50. Do not score it as a complete expiry session.

The acquisition agent used 195 separately owner-authorized buffer requests;
the receipt reports 4,995 total that day and five left below 5,000. **This
agent made zero API calls.** The exception is November-2-only, not permission
to spend reserve tomorrow or bypass the normal 4,800 stop.

### Why these files still cannot reproduce full native E01

1. Only the **opening ATM strike**, fixed all day, is included. Native A/B/C
   can select other strikes at their actual admission times; C needs cheap
   eligible OTM options, not an arbitrary ATM replacement.
2. No ten-second index/front-futures path is included to reconstruct the box,
   two-observation confirmation and subsequent failed-break decisions.
3. No contemporaneous bid/ask/depth or full dated eligible contract set exists
   in these CSVs. OHLC cannot establish an executable fill or intrabar order.
4. Coverage ends 15:29:50, while current code's final flat is 15:38. That clock
   mismatch needs a separately declared historical session contract; do not
   fabricate the missing period, closing fills or official settlement.

These are **additional usable option paths**, not useless data. Conditional
exit-policy diagnostics are possible with causal, explicitly hypothetical
admissions and conservative bar handling. They must be labeled exit-only or
partial research, not a four-session exact E01 backtest. Missing evidence is
unavailable, not zero P&L. Never synthesize a confirming tick, spread or depth.

## 8. E01.1 idea discussed, but not built or tested

One bounded idea was proposed: replace C's fixed half-bank at 3x with a
**fee-aware whole-lot cost-recovery bank**, retaining more of the runner only
when actual bank proceeds can cover the original funded ticket and an honest
reserve for remaining exit-order costs. Entry, total initial lots, 30% stop,
deadlines and full-premium ceiling would remain unchanged.

Motivation is mechanical, not a new entry filter: fixed half-banking can sell
more lots than needed to recover initial cash after a large move. Conversely,
banking fewer lots can reduce locked profit if the runner collapses. It is
not automatically an improvement or a risk-free trade.

Possible accounting approach for a future frozen proposal:

- Use actual native buy/sell fees, original entry quantity and actual earlier
  fill proceeds. Find the smallest whole-lot bank that funds original paid
  premium plus fees and a justified remaining-order reserve.
- Leave at least one runner lot only when affordable and supported by depth;
  one-lot tickets need an explicit unchanged fallback.
- Recompute from actual partial fills; never set "capital recovered" on a
  pending request. Existing stop/clock/structure exit priority must remain.
- The native `worst_case_loss` uses full premium, buy fees and a per-lot fixed
  order-fee reserve. Reuse/prove its cost bounds rather than guessing future
  prices, future number of partial fills or fee-free exits.

This is **a hypothesis only**. No `expiry-e011` study directory or E01.1
source/test/score exists. An alternative breakeven runner floor was merely
considered; it was neither chosen nor tested. Do not report either as an
implemented enhancement, a failed candidate or a passed frozen screen.

Known October 13 winner already inspected while considering this idea:
10 lots at 2.90; five banked at 8.75; five exited at 29.00. That is **seen**
information and cannot serve as an independent test or justify choosing a
quantity solely to maximize that winner. Its original result is preserved.

## 9. E02 preparation left on disk, explicitly deferred

Untracked Dev directory:
`docs/research/simulation/2026-11-02-expiry-e02/`

Public preparation files: `PLAN.md`, `export_data.py`, `data-binding.json`,
`PREFLIGHT_CORRECTIONS.md`. Private `_local/` contains selected-row `data.sqlite`,
expiry request statuses and retained calendar-draft database/binding. Do not
delete these or mistake them for committed finished research.

This was a selected read-only export from shared history, not a cloned token,
calls ledger or whole operational database. No shared source rows were changed.
The first export wrongly treated Oct 21, 2025's evening Muhurat as the daytime
expiry, yielding 52 instead of 53 sessions. The corrected calendar excludes
the documented evening-only sessions before shifting expiry, includes Oct 20,
and retains the failed draft. No strategy was scored before or after this fix.

Independent downloader checks found:

- 2025: 53 expiry sessions / 1,663 contracts, closing coverage through at least
  15:29; five invalid/negative-volume rows preserved.
- 2024: 52 sessions / 1,700 contracts, same closing coverage; five such rows
  preserved.
- 2023: incomplete acquisition; the owner reported 1,406 requests done and
  116 remaining. Do not silently infer completion from an export file.

The full checks returned **CHECK NOT CLEAN**, not clean, because of those
invalid rows. Older unrelated store defects were distinguished in the
corrections note. Invalid source rows must not become accepted fills/signals.

Read the current skill at
`C:/Users/Urveesh/.codex/skills/expiry-download/SKILL.md` before any acquisition.
It changed during this work to describe the seconds-buffer job. Its exporter
rewrites the existing CSV export; do not rerun it needlessly over source files.
The ordinary history skill is unchanged. No new download is authorized by
this handover. Owner-only login remains required.

The 2023 expiry-specific dataset was not strategy-scored here. Nevertheless,
the same calendar years and market regimes have already informed regular F&O
research; a later study must describe that contamination honestly rather than
claiming an entirely untouched market environment.

## 10. Exact continuation plan, if the owner resumes E01.1

1. Read both handovers and the required ritual documents. Confirm source,
   owner dirt, data presence and Production state without changing Production.
2. Create a **new E01.1** plan before code or scores. Record problem,
   files/contracts, hypotheses, hard acceptance/failure criteria, output
   identity, rollback and remaining evidence. Keep E02 explicitly deferred.
3. Hash/copy only the permitted selected CSV evidence into a new private study
   snapshot; independently validate timestamps, unique contract/bins, OHLC,
   provenance and missing seconds. Do not overwrite originals or fill gaps.
4. Declare module feasibility. Full native strategy on these four files is
   unavailable; conditional exits are partial. For a complete replay, obtain
   actual selected contract coverage plus index/futures and quote/depth clocks
   through the real session horizon, under separately authorized acquisition.
5. Freeze at most one or two mechanism hypotheses before comparing scores.
   Reproduce E01 baseline parity first on the original eight quote sessions.
   Preserve all old outputs/source; use new labels and a separate evidence
   packet. Do not start an unlimited genome search on these small seen sets.
6. For optional conditional September exits, freeze causal admissions and
   observed-price/intrabar policy before results. Never pick the cheapest
   hindsight entry, fabricate a bid, assume high-before-low or label the result
   as native portfolio P&L. Retain missing/unresolved observations explicitly.
7. Cover actual fee recovery, whole lots, one-lot fallback, partial bank fills,
   missing depth, gaps, pending closing exits, old-state compatibility and
   unchanged initial ticket ceiling with focused regression checks. Audit
   cash, prices, lots and costs independently of the candidate calculator.
8. If nothing passes, report that and leave E01 intact. If a candidate passes
   a bounded descriptive screen, keep it paper-only with exact parent and
   economic binding; no increase in real-order authority or automatic main
   replacement follows. Update guide/plan/checklist, regenerate atlas only
   for source/declaration changes, commit/push only the owned slice.

Existing E01 forward criterion remains: at least **20 genuinely new exactly
paired C/CE01 entries**, at least five per index, before economic promotion
review. Software and coverage checks should occur immediately; the threshold
is not permission to ignore faults until then. Do not tune it after outcomes
or treat the four September historical paths as fresh prospective entries.

## 11. Documentation-only handover and safe resumption

This task creates Markdown inheritance documents and navigation only. No
application test suite was rerun or new profit result produced. Validate local
document links and `git diff --check`; atlas generation is unnecessary.
Documentation commit identity is discoverable with:
`git log -1 -- docs/EXPIRY_SUCCESSOR_HANDOVER_2026-11-02.md`.

Handover verification completed: both documents' local Markdown links resolve;
`git diff --check` passes; original owner dirt matches its preserved baseline.
The final E01 packet's passed receipt and all four new CSVs' 4,500-row counts,
unique per-leg grids, fixed strikes and 3,347 missing-second total were checked
read-only. This was a coverage/identity check, not a strategy backtest or a
fresh exhaustive OHLC/financial audit.

Preserve pre-existing owner changes in `.gitignore`, the three ritual docs,
`.agents/`, deployment notes, skill notes and earlier untracked simulation
directories. Stage only owned files/slices; never `git add .` this checkout.

Suggested next prompt:

> Read EXPIRY_SUCCESSOR_HANDOVER_2026-11-02.md and the four ritual documents.
> Resume E01.1 from the documented unimplemented hypothesis. Validate the four
> September ten-second datasets without fabricating missing entry, depth or
> closing evidence. Freeze a bounded experiment, preserve E01/E02 evidence,
> and keep Production and real-money authority unchanged.
