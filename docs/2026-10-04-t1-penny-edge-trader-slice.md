# T1 — Penny and EDGE trader candidates (Dev, offline research)

Status: **implemented and scored on pre-registered untouched windows. No
candidate beat its baseline; all stay OFF. Nothing is enabled, qualified,
pushed or deployed.** This slice executes T1 of the
[adaptive trader plan](2026-10-04-adaptive-non-fno-trader-development-plan.md)
and reviews/corrects the T0 prototype. F&O is untouched.

## Problem

T0 delivered a setup-state prototype that could represent a baseline-rejected
Penny setup, but it had trader-logic defects and no replay. EDGE had only an
independent-trial proxy with no cash book. Neither could answer "does a smarter
entry/exit policy make money after costs?".

T0 defects found and fixed:

1. WATCH was invalidated by the post-breakout stop (anchor − ₹0.05), so ordinary
   consolidation under the base high killed the watch. WATCH now uses the base
   low; arming switches to the structural stop.
2. Expiry was measured from the anchor bar's age, so an old base high produced
   an already-expired watch. Expiry now runs from the decision clock.
3. A fixed ₹0.05 noise allowance is 0.5% at ₹10 and 0.05% at ₹100. The stop is
   now `anchor − max(1×ATR14, 0.4% of price, 3 ticks)`, tick-floored.
4. Volume/participation was never used; any close above the high armed.
5. No exits, sizing contract or replay existed.

## What was built

| Piece | File | Contract |
| --- | --- | --- |
| Pure Penny trader policy | `python-engine/adaptive_penny_policy.py` | No runtime/broker/DB imports. Context from strictly earlier bars (anchor, ATR); scored participation/surge/close-location/VWAP/chase/room with every failed condition reported; RSI recorded, never a veto. Fast entry for strong unextended breakouts; otherwise ARMED → bounded retest/reclaim or holding continuation; two closes back inside the base invalidate; intents are one-shot. Cost-aware sizing declines cost-dominated or >3.5% risk. Churn memory: 20-min cooldown and a higher anchor after a failure, ≤2 entries per ticker-day. Thesis exits: two closes below the anchor, 45-min stall, 14:30 loss cut, breakeven at +1R, trail after +1.5R, resting integer half-partial at 2R; stops only rise. |
| Penny replay wiring | `python-engine/penny_lifecycle_replay.py` | Same minute clock, LTP fills, drift/stop/quote/circuit/regime hard blocks (`_hard_constraint`, shared with baseline), paper stop monitor, 15:00 square-off, MIS costs per leg and an own-cash check. BASELINE output is unchanged (reproduces +₹15.1765 / 18 trades). Candidate reports add parameters, condition counts and breakdowns by entry kind, baseline status and exit. |
| EDGE own-cash portfolio | `python-engine/edge_portfolio_replay.py`, Lab id `penny_edge_portfolio_replay` | Shipped `scan_today` ranking at D close; D+1 open as the 09:30 proxy with the executor's 2% drift check, stop geometry and re-sizing to the signal's rupee risk; stop (gap fill at open) before resting target; time exit at the close on the live calendar-age rule; own cash only, no doubled ticker, 3 entries/day, dust fills (<25% of plan) skipped, CNC costs per order, marked daily equity, open positions marked not closed; tickers not yet listed in a window are excluded with a receipt. |
| Pre-registration | `scripts/run_penny_trader_oos.py`, `scripts/run_edge_trader_oos.py` | `freeze` binds source hashes, snapshot, windows, policies and decision rule; `run` refuses changed inputs and scores each window once. Freezes were committed before scoring (`22a7ce6`, `684de3d`). |

## Candidates (trial ledger)

| Module | Round | Name | Hypothesis |
| --- | --- | --- | --- |
| Penny | 1 | `PEN_TRADER_V1` | Structural 30-bar-base breakout states recover baseline-rejected setups; baseline exits on the structural stop. |
| Penny | 1 | `PEN_TRADER_V1_THESIS` | Same entries plus thesis exits. |
| Penny | 2 | `PEN_BASE_THESIS` | Shipped entry unchanged; only thesis exits differ (exit attribution). |
| Penny | 2 | `PEN_TRADER_V2` | From round-1 diagnostics (local highs, 09:30–10:00 and low-participation breakouts were noise): new-high-of-day structure after 10:30 with ≥1.8× pace volume, ≥2× bar surge and VWAP support; state machine, structural stop, no RSI veto, churn control and thesis exits retained. |
| EDGE | 1 | `EDGE_TRADER_V1` | MR and MO are different theses: skip MO gap-down and MR fresh-breakdown opens, cut a failed bounce/giveback at the close, breakeven after +1R, subtype holds within the live cap. |

Round 1 failed on the development window. Round 2 was designed from that
window, so its development numbers are in-sample only.

## Evidence windows

- Penny development: Sep 24–30 (5 sessions).
- Penny untouched: Sep 7–23 and Oct 1 (13 sessions) from a new Yahoo 1-minute
  acquisition (`docs/research/yahoo/2026-10-04-penny-trader-window`, Sep 7–Oct 3;
  Sep 4 was refused at Yahoo's 30-day limit, Oct 2 holiday, Oct 3 Saturday).
- EDGE development: Jul–Sep 2026 (seen by the review). EDGE untouched: Jan–Jun 2026.

## Results

Receipts: `docs/research/yahoo/2026-10-04-penny-trader-oos/results.json` and
`docs/research/yahoo/2026-10-04-edge-trader-oos/results.json` (per-run reports
under each git-ignored `_local/`). Paper books, PR1_CALM declared regime, the
same 95-ticker universe and configuration as the review receipts.

### Penny MIS (paper ₹100,000 book, ₹500 per-stock cap)

| Policy | Dev Sep 24–30: trades / net / net excl. best / max DD | **Untouched Sep 7–23 + Oct 1**: trades / net / net excl. best / max DD |
| --- | --- | --- |
| BASELINE (shipped) | 18 / +₹15.18 / −₹27.74 / ₹45.10 | **24 / +₹63.17 / +₹30.53 / ₹32.47** |
| PEN_TRADER_V1 | 47 / −₹192.76 / −₹235.68 / ₹195.45 | 91 / −₹102.94 / −₹140.73 / ₹152.64 |
| PEN_TRADER_V1_THESIS | 123 / −₹214.03 / −₹233.07 / ₹216.84 | 283 / −₹104.89 / −₹146.98 / ₹160.19 |
| PEN_BASE_THESIS | 19 / −₹17.08 / −₹32.62 / ₹46.96 | 27 / −₹16.68 / −₹52.14 / ₹76.10 |
| PEN_TRADER_V2 | 24 / +₹39.72 / +₹12.45 / ₹21.25 (in-sample) | 80 / −₹17.02 / −₹39.59 / ₹76.73 |

Frozen decision for `PEN_TRADER_V2`: all four checks false →
**NOT_SUPPORTED_STAYS_OFF**. Its development gain was overfitting to five
sessions; the freeze caught it. The shipped baseline was profitable on the
untouched window (a small, coverage-selected sample; not qualification).

- Recognising more setups (V1) multiplied trades and losses; breakouts of local
  highs in these penny names showed no edge even before costs.
- Thesis exits cut individual losers smaller but freed capacity, so churn and
  costs grew (283 trades). On the shipped entry they also hurt: breakeven at a
  one-candle 1R ejects trades that later work.
- Candidate development reruns on the newly acquired snapshot differ from the
  first in-session run (V1 −₹141.86 vs −₹192.76; V2 +₹42.93 vs +₹39.72) while
  BASELINE is identical: re-fetched Yahoo minute bars differ slightly and the
  candidates are sensitive to that. Small-sample differences are not edge.

### EDGE (own cash, no margin)

| Window / book | BASELINE: trades / net / marked return / max marked DD | EDGE_TRADER_V1 |
| --- | --- | --- |
| Dev Jul–Sep, ₹100,000 | 84 / −₹27,222.74 / −27.22% / 32.99% | 80 / −₹21,895.27 / −21.90% / 28.72% |
| Dev Jul–Sep, ₹3,000 owner | 84 / −₹787.61 / −26.25% / 31.77% | 80 / −₹651.56 / −21.72% / 28.53% |
| **Untouched Jan–Jun, ₹100,000** | **140 / −₹40,166.31 / −40.17% / 44.50%** | 136 / −₹44,776.60 / −44.78% / 49.08% |
| Untouched Jan–Jun, ₹3,000 owner | 141 / −₹1,172.03 / −39.07% / 43.31% | 137 / −₹1,324.65 / −44.15% / 48.35% |

Frozen decision: **NOT_SUPPORTED_STAYS_OFF**. More important is the baseline:
the shipped EDGE strategy loses heavily in a causal own-cash replay. Untouched
baseline anatomy: 69 targets averaging +2.76% of notional against 64 stops
averaging −5.2% (gap stops −6.2%, worst −13%); gross −₹35,786 before ₹4,380
costs. Targets of 3–5% against stops of 4–6% need a hit rate well above 60%;
it achieved ~50%. MR lost −₹29,562 of the −₹40,166. The executor's 2% drift
rule rejected 136 signals and own cash rejected or resized 32 more, so the
earlier trial proxy overstated what was executable. Daily-bar 09:30/15:15
proxies and the current (not point-in-time) event file remain limitations.

## Findings recorded without runtime change

- Runtime EDGE paper sizing never checks cash: `PENNY_EDGE_MAX_POSITIONS` caps
  entries per day, not concurrent positions, so 3/day × 3-day holds with
  risk-based shares can commit several times the bankroll. That is margin-like
  exposure the owner has ruled out; the replay enforces own cash for every policy.
- The 15:15 EDGE exit job books the simulator's TP/SL/time price, and EDGE_PAPER
  rows also pass through the daily OHLC position tracker; recorded paper P&L is a
  bookkeeping model, not one executable path.
- The 2% entry-drift check rejects roughly half of EDGE signals at the open.

## Acceptance and verification

- 144 focused tests pass (policy, trader replay, lifecycle replay, EDGE portfolio, Lab,
  CLI, non-F&O research, Momentum replay, breakout engine, Penny risk, Penny
  isolation); atlas regenerated (243 modules); `git diff --check` clean.
- BASELINE Penny reproduces the archived receipt exactly (+₹15.1765, 18 trades,
  same funnel) after the shared-helper refactor.
- Freezes committed in `22a7ce6` (Penny) and `684de3d` (EDGE) before `run`;
  `run` verified bound source/snapshot hashes and wrote each report once.
- Environment limits: Yahoo-only data, ~30-day 1-minute retention, partial (gap)
  sessions under `allow_gaps`, daily-bar EDGE execution proxies.
- Dev only, branch `codex/production-correction-hedge-p0`; not pushed or
  deployed; no Production access, broker action, settings, schema, dependency
  or F&O change.

## Rollout / rollback

Offline only. Every candidate is a named research selector; default remains
BASELINE and runtime Penny/EDGE code, settings, schedules and F&O are unchanged.
Rollback is to stop selecting the candidate.

## Remaining work

- EDGE: the shipped stop/target geometry is the first problem, not entry timing.
  A round-2 hypothesis must be designed on 2026 data (now seen) and judged on a
  still-untouched window (2024–2025 daily history is in the snapshot). Owner
  decision recommended: keep EDGE live disabled and consider pausing EDGE paper
  until a redesign survives an untouched window.
- Penny: keep the shipped baseline; archive forward minute data weekly (Yahoo
  keeps ~30 days); any new Penny round needs a fresh untouched window.
- T2: Range/Swing/Momentum adapters and the small CNC audit.
- R5/T3: dependence-aware uncertainty, owner-allocation study, untouched
  qualification and F&O noninterference before any runtime adapter.
