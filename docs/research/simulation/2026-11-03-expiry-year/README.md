# E01.1 on the new expiry history — November 3, 2026

**E01.1 reduces losses compared with E01, but this larger test does not establish
a profitable expiry system. Neither new exit idea passed its untouched tests.
The main paper rule is unchanged.** The pre-registered 20% stop and cheaper band
deserve a full-chain forward comparison; these results do not justify promotion.

This is Dev research on branch `codex/production-correction-hedge-p0`, starting
at `65a11f1`. Source/input/candidate freeze: **`99d3de3`**; documentation receipt:
`4caa79c`. The old handover's deployment statement is superseded: the Production
checkout is `06bed07`, and the earlier release receipt already records E01.1 as
paper main C. This task did not change or deploy Production, touch N11/N11T,
call Breeze/Kite, change capital/settings/schema or send a message.

## What was actually available

The authoritative November 3 export contains 110 opening-ATM expiry dates:
57 NIFTY and 53 SENSEX. 100 have every paired afternoon ten-second observation
needed by the study and valid rows. Four are previously seen NIFTY September
sessions and are excluded from the new exam. **96 new dates were eligible:**

| Window | NIFTY | SENSEX | Purpose |
|---|---:|---:|---|
| January–June 2026 | 26 | 25 | Development, diagnoses and two candidate designs |
| July–October 1, 2026 | 9 | 14 | Untouched validation, excluding seen September NIFTY |
| Available September–December / October–December 2025 | 17 | 5 | Untouched second window |

Ten more dates are unavailable under the complete-afternoon test, including
provider-gapped SENSEX dates and partial download endpoints. They remain in
[coverage.json](coverage.json); their result is unknown, never zero. Individual
missing source seconds within present bars remain flagged and were not filled.
The source verification records 66,623 missing NIFTY seconds and 48,780 SENSEX
seconds over the requested export horizons. A complete ten-second grid is not
gap-free tick data.

There is also a wider recorded-chain **NIFTY minute archive on all 53 expiry
sessions in 2025**. A separate C-only minute proxy tested entries and exits on
that archive. There are no 2026 same-day-expiry option minute rows in this source;
the broad 2026 regular F&O archive does not supply those missing expiry strikes.
No pre-2025 prices were read by this task. NIFTY 2023 remains protected.

## Two distinct experiments

**Ten-second conditional exit panel.** The existing frozen `panel.py` admission
rules buy an available opening-strike option at a break or its own momentum
signal. All exit arms receive exactly the same ticket. Some tickets cost up to
two or three times C's usual band, and they can overlap or duplicate an
opportunity under different admission rules. There is no failed-break exit in
this panel, as in the original September test. It is not C's actual entry book,
an independent sample of 220 market opportunities, A/B, or a portfolio profit.
The underlying is a three-observation put-call-parity proxy; future equals that
proxy, so independent futures confirmation is unavailable.

**NIFTY 2025 C minute proxy.** Uses the recorded wider chain and independent
index/front-future closes, C's actual strike picker, failed-break rule and one
ticket per day. Two completed minute observations with at most 65 seconds
between them replace native ten-second confirmation. It schedules liquidation
from 15:28 because the archive cannot observe the native 15:38 exit. It filled
53 tickets under each execution scenario. This is a partial recorded-chain and
bar-timing proxy, not exact native parity or the whole A+B+C book.

Both use a **current-size normalization**: NIFTY 65, SENSEX 20, current native
per-exchange charges, independent Rs 2,500 full-premium pockets, ten-lot cap.
These rupees describe that experiment, not the historically realizable cash
result at the lot sizes/taxes in force in 2025. BFO spreads are provisionally
transferred from the old NIFTY calibration and remain unverified. Volume is a
20% participation proxy, not depth or an independently verified executable size.

The ordinary model decides on a completed bar and executes on the next bar's
open plus/minus the frozen spread. Adverse execution uses the next bar's high
for buys, low for sales, and twice the spread. Entry size is planned on the
decision quote, capped by participation, then revalidated against the full
premium ceiling at execution; adverse quantities are an explicitly modelled
budget recheck, not a native historical order. Exit orders remain pending through
insufficient volume. Execution timestamps are bar completion times; no second
decision sees the execution bar before it completes. No intrabar path/high-low
ordering or perfect stop fill is invented. Stops act on observed closes, as a
sampled controller, not a guaranteed continuously monitored barrier.

Any unclosed remainder would carry a separate unresolved full-premium loss
bound. **All scored positions closed in the declared model:** no assumed
settlement or terminal zero-price sale contributes to the figures below.
Auction-window execution, bid/ask, actual depth and settlement remain unverified.

## What E01.1 did

**NIFTY 2025 recorded-chain C minute proxy, 53 tickets:**

| Rule | Ordinary net | Adverse net | Ordinary without best day | Ordinary worst day |
|---|---:|---:|---:|---:|
| E01 | -29,338 | -47,440 | -33,410 | -1,301 |
| **E01.1** | **-20,638** | **-42,315** | **-25,350** | **-1,103** |
| E01.1, 20% stop | -19,551 | -37,849 | -24,262 | -1,103 |
| E01.1, cheaper band | -17,073 | -35,238 | -20,086 | -1,074 |

**New ten-second conditional exit panel, both indices, 220 filled pockets:**

| Window | Tickets | E01 ordinary | E01.1 ordinary | E01 adverse | E01.1 adverse |
|---|---:|---:|---:|---:|---:|
| Development, Jan–Jun 2026 | 101 | -22,398 | -16,829 | -35,893 | -30,732 |
| Validation, later 2026 | 65 | +12,323 | +16,435 | -1,436 | +6,140 |
| Available 2025 | 54 | -30,589 | -19,164 | -37,748 | -27,116 |

Across these conditional pockets E01.1 totals -19,557.58 ordinary and
-51,708.47 adverse, compared with E01's -40,664.52 / -75,076.07. Fees are
11,749.83 / 11,647.97. Its ordinary NIFTY subtotal is +13,758.26, SENSEX
-33,315.84; adverse NIFTY -2,150.91, SENSEX -49,557.56. These are independent
panel sums and must not be added to the minute proxy or described as live P&L.

The original frozen relative exit screen passes for E01.1 versus E01: net is
higher, worst session and net without the best are no worse, ordinary/adverse.
It does **not** imply absolute profitability or a completed full-book exam.
Per-year, per-index, CE/PE, fees, all exits, session sums and drawdown are in
[analysis.json](analysis.json), the raw result files and
[daily-results.csv](daily-results.csv). Panel drawdown means cumulative sums of
independent pockets, not an account's realizable drawdown.

## Why losses persist, and what more could have been earned

- **Most tickets never develop.** 201 of 220 ordinary E01.1 pockets lose. The
  median losing ticket's best observed premium is only 1.094 times its entry.
  Moving the 3x bank or its floor cannot rescue those tickets. Fees amplify
  small-premium losses. This is primarily an admission/continuation problem.
- **The big winner still dominates.** August 25, 2026 contributes +48,157.73
  across several overlapping NIFTY panel tickets. Remove that session and
  E01.1's ordinary panel is -67,715.31. These repeated exposures to one move do
  not become independent evidence because there are several tickets.
- **Stopping earlier also loses recoveries.** 19 ordinary losing tickets later
  print a bar high at least 3x the entry. That later high is hindsight, not a
  price an exit rule could reliably realize, and does not authorize re-entry.
- **No bank looks attractive only with the biggest winner.** It improves the
  ordinary panel headline to +5,850.01, but net without the best falls to
  -72,877.22, worse than E01.1. It also loses to E01.1 on the 2025 minute proxy.
  It fails the frozen replacement test.
- **The 20% stop is a useful candidate, not an established upgrade.** It passes
  the original aggregate relative screen and improves the minute proxy. But
  stressed SENSEX across the ten-second panel falls from -49,557.56 to
  -52,201.87. Its descriptive session-cluster 95% interval for the stressed
  overall improvement includes zero (-18,750.63 to +21,130.57). No primary swap.
- **A cheaper ticket helps the minute proxy but still loses.** Halving the
  premium-band top retains four of four ordinary baseline days that earned at
  least Rs 1,000, under a descriptive day-based retention reading. Opening-
  strike data cannot test this entry change. A full-chain forward exam remains
  necessary; retaining a profitable day is not exact same-contract retention.

## Two new ideas, both rejected

Exactly two mechanisms were chosen on January–June development, with one setting
each and no parameter sweep. IDLE8 borrows A's eight-minute / +40% progress
requirement. LOCK40 protects half the peak gain from A's +40% trigger, borrowing
AL's gain floor. They were frozen before validation/2025 outcomes were opened.

| New arm | Development ordinary | Validation ordinary | 2025 panel ordinary | 2025 minute ordinary |
|---|---:|---:|---:|---:|
| E01.1 control | -16,829 | +16,435 | -19,164 | -20,638 |
| IDLE8 | -10,607 | -16,359 | -17,331 | -16,206 |
| LOCK40 | -23,898 | -13,560 | -17,864 | -7,640 |

Both fail the frozen requirement for positive net and positive ex-best net,
higher net and no worse worst-session/drawdown on validation and 2025 under
ordinary/adverse fills. Their 2025 improvements do not erase their validation
failures. The early exits remove important later runners. Neither was tuned,
renamed as a winner, added to the runtime or promoted.

There is no honest way to ensure zero overfitting. This study limits it by
registering the comparison, keeping validation unseen until the committed
freeze, counting every candidate and preserving failures. The selection-risk
motivation is discussed in Bailey et al.,
[The Probability of Backtest Overfitting](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf).
No trader-advice page supplied a strategy rule.

## Verification and reproducibility

- Inherited archived E01/E01.1/no-bank mechanics reproduce **42 legs, zero
  mismatches** in prices, quantities, clocks, peak, stops, fees and events. The
  first audit found six record-only context differences; these are preserved
  in `parity-initial-context-mismatch.json`, not hidden financial failures.
- The independent post-score audit reconstructs cash flows and checks every
  model execution price/size against its frozen source bar: **4,032 arm-position
  records, 7,967 execution events, zero cash-flow/price/lot/budget errors**. These
  counts include comparison arms, not unique market trades.
- Tests: completed-bar clock, next-bar execution, no future-range entry quote,
  thin-bar nonfill, pending exits, terminal unresolved state, stop priority,
  fee-inclusive ceiling, paired entries and explicit minute confirmations.
  **139 expiry/research tests passed in 197.42 seconds**, including 12 new
  research checks. The combined scope covers `test_expiry_paper.py`,
  `test_expiry_e01.py`, `test_expiry_e011.py` and this study's `test_study.py`.
- Frozen sources/configuration/effective fee schedules and every selected raw
  file are rehashed before scoring. Source data are local under ignored
  `_local/`; sharing the reports alone cannot recreate unavailable raw evidence.
- Atlas regenerated: 294 runtime Python modules, no diff. No runtime declarations
  changed. Source snapshots and initial owner documentation changes are retained
  locally. No full engine-suite rerun was needed for isolated research.

Use `python-engine/winvenv/Scripts/python.exe` from Dev:

```text
study.py snapshot                 # only for a NEW study; refuses overwriting
minutes.py snapshot               # only for a NEW study, selected 2025 SQL
study.py parity
pytest test_study.py -q
study.py run --group development
study.py run --group development --candidates
study.py freeze                   # then commit before any unseen scoring
study.py verify
study.py run --group validation --candidates
study.py run --group test2025 --candidates
minutes.py run
analyze.py
```

Commands are study-relative; `pytest` runs through `python -m pytest`. The
existing result files are immutable and reruns refuse to overwrite them.
Snapshot/freeze commands must not be used to re-seal these now-seen windows as
untouched. Detailed command status and final verification live in
`verification.json`; the skill-format report is under `evidence/`.

## What should change next

**Keep E01.1 as paper main, with its current shadows; no additional trading-rule
change is supported here.** The research improvement is a causal, frozen,
audited comparison that rejects plausible but harmful changes, rather than
quietly optimizing against every year.

The next useful strategy work is an admission/continuation test on the actual
afternoon chain. The inherited approved target shape is documented in
`../2026-11-02-expiry-e011/EXAM_YEAR.md`: afternoon strikes around the 13:00
price, with dated contracts/lot sizes, underlying/future observations and a
supported closing tail. Any new calls go through the expiry-download skill
with fresh date-bound authorization; this task made none.

The 20% stop and cheaper band are fixed named hypotheses for that future
comparison, not permission to find a better threshold on 2025/2026. N11's lesson
is to test when a trade deserves admission; copying its filters into expiry
without an expiry-specific exam would merely create another untested rule.
All 2025/2026 outcomes opened here are now seen forever. Keep 2023 protected and
use genuinely new full-chain/forward paired tickets for the next decision.
