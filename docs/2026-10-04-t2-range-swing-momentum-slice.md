# T2 — Range, Swing, Momentum candidates and the Penny CNC audit (Dev, offline)

Status: **implemented and scored on pre-registered untouched windows. No
candidate is profitable, so all stay OFF; Range reclaim (−30% loss) and
SWING_TRADER_V1 (−80% loss) clearly reduce losses versus baseline.** Nothing
is enabled, qualified, pushed or deployed. Owner direction for this slice:
existing running modules (including EDGE) stay as they are. This is the T2 step
of the [adaptive trader plan](2026-10-04-adaptive-non-fno-trader-development-plan.md),
using the method in [RESEARCH_TESTING_METHOD.md](RESEARCH_TESTING_METHOD.md).

## What was built

| Piece | File | Notes |
| --- | --- | --- |
| Shared own-cash daily book | `python-engine/daily_portfolio.py` | One implementation of next-open market and resting-limit entries, drift/geometry checks, risk re-sizing, dust skip, stop-first then ascending resting levels, close-time policy hooks, per-order costs, marked equity. EDGE was moved onto it: identical trade counts, drawdowns and final equity against the frozen T1 runs; net P&L now reconciles exactly with equity (the old EDGE code rounded the entry price before computing P&L, a sub-paisa inconsistency). |
| Range replay | `python-engine/range_portfolio_replay.py`, Lab `range_reversion_portfolio_replay` | Declared BASELINE lifecycle of the shipped `range_reversion_entry` verdict (Range has no shipped daily horizon): next-open buy, strict stop, mean target, 5-session time exit, 1% equity risk capped at an equal slot of equity. |
| Swing replay | `python-engine/swing_portfolio_replay.py`, Lab `swing_regime_portfolio_replay`; `SwingDecisionClock` in `research_daily_decision_replay.py` | Shipped `evaluate_signal` decisions with tracker-parity exits: T1 half then breakeven, Chandelier trail, T2 capped at 5R in Regime 1, 15-day limit. Ties resolve stop-first and the trail applies from the next bar (the runtime tracker is more optimistic on both). |
| Momentum clock + candidate | `python-engine/momentum_replay.py` | `entry_clock=NEXT_BAR_OPEN` (R3 fix: the accepted bar's close is only known at bar end; fill at the next bar's open at the same rupee risk; the legacy clock remains default only for archived receipts) and `exit_model=THESIS_EXIT`. |
| One study tool | `scripts/run_preregistered_study.py` | Data-driven freeze/run for every module, replacing the two T1 per-module scripts. |
| CNC audit | `scripts/audit_penny_cnc_conjunction.py` | Diagnostic of the Connors conjunction on completed daily bars. |
| Cleanup | — | Removed superseded subset-only gates (`swing_candidate_gate`, `range_candidate_gate`, `penny_exit_thesis`), the flawed EDGE independent-trial proxy (adapter, replay, tests) and unused imports. `penny_context_gate` is kept for PEN_CONTEXT receipts. |

## Candidates (declared before scoring, frozen in commit `68e0754`)

| Module | Candidate | Change |
| --- | --- | --- |
| Range | `RANGE_RECLAIM_ENTRY` | A touch arms the thesis on the frozen range; entry needs a stabilization close (up close above the open) within 3 sessions with no close below the range low. Baseline exits. |
| Range | `RANGE_TRADER_V1` | Same entry plus thesis exits: close below the range low, <30% progress to the mean after 3 sessions, breakeven at half-way, 7-session cap. |
| Swing | `SWING_PULLBACK_ENTRY` | Signals more than 1 ATR above EMA21 rest a limit at max(EMA21, close − 1 ATR) for 3 sessions instead of chasing. Baseline exits. |
| Swing | `SWING_TRADER_V1` | Same entry; no T1 halving; breakeven after a +1R close; Chandelier trail plus T2; exit after two closes below the causally updated EMA21. |
| Momentum | `MOM_THESIS_EXIT` | T1 half when ≥2 shares, breakeven after +1R, trail 1R under the highest close after +1.5R, exit on two closes under the entry VWAP or a stall (no +0.5R in four bars while under entry). BASELINE is the shipped exit evaluator; both use next-bar-open entries. |

## Results

Receipts: `docs/research/yahoo/2026-10-04-{range-trader-t2,swing-trader-t2,momentum-thesis-t2}/results.json`.

### Range (₹1,00,000 paper book, 499-stock universe)

| Policy | Dev Jul–Sep: trades / net / max DD | **Untouched Jan–Jun**: trades / net / net excl. best / max DD |
| --- | --- | --- |
| BASELINE | 225 / −₹11,666.66 / 11.86% | 174 / −₹9,024.10 / −₹9,886.54 / 9.58% |
| RANGE_RECLAIM_ENTRY | 156 / −₹8,976.07 / 10.15% | 99 / −₹6,274.73 / −₹6,904.50 / 6.68% |
| RANGE_TRADER_V1 | 159 / −₹9,269.88 / 10.45% | 99 / −₹6,650.49 / −₹7,280.26 / 7.05% |

Verdict for `RANGE_TRADER_V1`: **NOT_SUPPORTED_STAYS_OFF** (beats baseline and
drawdown checks; not profitable). The reclaim entry cuts losses by ~30% in both
windows; the thesis exits add nothing beyond it. Why Range loses: the strict
stop sits a median 0.83% under entry, so ordinary daily noise stops it out (120
stops versus 50 mean targets on the baseline). Delivery costs (≈0.25% round
trip) consume about a third of the loss when the target is only ~1% away.

### Swing (SYSTEM ₹4,500 pool; owner ₹1,000 book)

| Policy | Dev Jul–Sep ₹4,500: trades / net / max DD | **Untouched Jan–Jun ₹4,500**: trades / net / marked return / max DD | Untouched ₹1,000: net / marked return |
| --- | --- | --- | --- |
| BASELINE | 20 / −₹54.18 / 11.65% | 70 / −₹1,287.67 / −28.61% / 29.42% | −₹11.09 / −1.11% |
| SWING_PULLBACK_ENTRY | 15 / +₹159.17 / 13.69% | 57 / −₹1,069.71 / −23.77% / 28.91% | −₹38.44 / −3.84% |
| SWING_TRADER_V1 | 12 / −₹40.92 / 10.20% | **55 / −₹254.81 / −5.66% / 20.91%** | −₹17.28 / −1.73% |

Verdict for `SWING_TRADER_V1`: **NOT_SUPPORTED_STAYS_OFF** (beats baseline and
drawdown; not profitable). Not halving at T1 and exiting on a broken trend cut
the baseline's untouched loss by ~80%. The pullback-entry alone did not help on
untouched data. The ₹4,500 pool cannot fund most signals (197 dust and 82
zero-size skips in the baseline); stops sit a median 7.5% away and losses are
gross, not costs.

### Momentum (15-minute, 499 stocks, next-bar-open entries)

| Policy | Dev Sep 24–30: trades / net | **Untouched Aug 10–Sep 23 + Oct 1**: trades / net / net excl. best / max DD / win rate |
| --- | --- | --- |
| BASELINE (shipped exits) | 1 / −₹0.83 | 54 / −₹120.87 / −₹164.00 / ₹177.19 / 31.5% |
| MOM_THESIS_EXIT | 1 / −₹6.43 | 54 / −₹149.76 / −₹210.86 / ₹157.94 / 29.6% |

Verdict: **NOT_SUPPORTED_STAYS_OFF**. Seven accepted signals could not fill at
the next bar's open (stop or target already crossed) — the old close-fill clock
counted them. The entry, not the exit, is the problem: only 5 of 54 baseline
trades reached target, and most ended on shipped time stops within ±0.5R; the
thesis exit mostly converts those into stall exits (26) without changing the
outcome. Sizes are small (₹2,500 Momentum pool), so rupee figures are small.

### Penny CNC audit (Jan 1–Sep 30, 2026; 95 tickers; 16,315 ticker-days)

| Condition | Passes alone | First rejection |
| --- | --- | --- |
| ≥250 bars of history | 14,709 | 1,606 |
| close > SMA200 | 5,463 | 9,246 |
| close > SMA50 | 6,620 | 1,537 |
| RSI(2) < 10 | 5,337 | 2,983 |
| RSI(2) rising for 2 bars | 2,412 | 940 |
| volume ≥ 0.5 × 20-day average | 11,137 | 3 |
| **Full conjunction (can fire)** | **0** | — |

Uptrend plus oversold happened 888 times; the "RSI rising two bars" clause
rejected every one, because "below 10" and "rising twice" rarely coexist. The
runtime Penny CNC rule therefore cannot fire on this universe. Removing the
clause does not reveal an edge: uptrend-oversold days returned −0.70% mean /
−1.44% median from the next open to five sessions later (all days: −0.10% /
−1.39%). An armed reclaim (close above the prior high within 3 sessions) showed
+0.55% mean but −1.08% median from 183 cases, an outlier-driven descriptive
statistic with no stops, costs or cash. No CNC candidate was built.

## Acceptance and verification

- 149 focused tests pass (shared book, EDGE/Range/Swing policies, Momentum clock
  and thesis exit, Penny trader/lifecycle, Lab, CLI, non-F&O research, breakout,
  Penny risk/isolation); unused-import scan clean on touched files; atlas
  regenerated; `git diff --check` clean.
- EDGE refactor regression: the four frozen paper-book EDGE runs reproduce trade
  counts, drawdowns and final equity exactly on the shared book.
- Freezes committed in `68e0754` before `run`; each study verified its bound
  hashes and wrote every report once. Momentum's own Yahoo acquisition module
  result was refused by the runner's drift guard (source edited during the
  download); the data snapshot itself validated and is what the study uses.
- Environment limits: Yahoo-only data; 15-minute retention ~60 days; daily-bar
  execution proxies; current (not historical) universes; no manual approval or
  broker evidence.
- Dev only, branch `codex/production-correction-hedge-p0`; not pushed or
  deployed; no Production access/edit, settings, schema, dependency or F&O change.

## Rollout / rollback

Offline only; new selectors default to BASELINE; runtime Range/Swing/Momentum/
Penny code, settings, schedules and F&O are unchanged. Rollback is to stop
selecting a candidate. EDGE and other running modules stay as the owner wants.
