# Broad F&O gap search — October 31,2026

**Result:** No new addition clears the frozen acceptance bar. No main-book rule, application, real-money switch or Production service was changed.

The search is complete: 48 fixed genome-style variants across 12 entry families; eight deterministic random controls; three main/TPB controls; corrected special-session replays; three direction-restricted proposals and their actual shared-main-book replays. Separately, 15 bounded option expressions were compared at two execution-cost levels. This is a broad fixed population, not repeated mutation until an attractive number appears.

## What the direction-specific proposals actually did

Only 2024+2025 selected these directions. The list was committed as 60c27eb before child replays. All three years had been studied previously; 2026 is an internal stability check, not a clean holdout. Direction subsetting only proposed candidates; the table below uses actual reruns. Standalone numbers use one normalized lot and extra ₹200 per trade. Combined numbers start each year with a fresh ₹250,000 and apply normal main-book sizing, costs and brakes. Annual profits are not a continuous account balance or a forecast for ₹15,000.

| Book | 2024 | 2025 | 2026 through Oct 28 |
|---|---:|---:|---:|
| Main, shared-book control | +16,371 | +5,710 | +30,540 |
| GAP_REPAIR / g0 / LONG standalone | +7,378 | +293 | -1,454 |
| Main + GAP_REPAIR / g0 / LONG | +20,045 | -808 | +34,009 |
| EMA_CROSS / g1 / SHORT standalone | +3,430 | +695 | -9,131 |
| Main + EMA_CROSS / g1 / SHORT | +16,172 | +9,824 | +19,181 |
| CLOCK_MOMO / g3 / SHORT standalone | -936 | +6,568 | -19,910 |
| Main + CLOCK_MOMO / g3 / SHORT | -7,095 | +8,170 | -4,625 |

| Proposal | Standalone trades by year | Failed predeclared checks | Selected max-t p |
|---|---|---|---:|
| GAP_REPAIR / g0 / LONG | 27 / 17 / 8 | positive_each_year, five_nonnegative_halves, positive_without_year_best, weekly_t, combined_better_each_year, combined_fall, combined_t, selected_max_t | 0.999 |
| EMA_CROSS / g1 / SHORT | 50 / 43 / 50 | positive_each_year, five_nonnegative_halves, positive_without_year_best, weekly_t, combined_better_each_year, combined_fall, combined_t, selected_max_t | 1.000 |
| CLOCK_MOMO / g3 / SHORT | 111 / 105 / 103 | positive_each_year, five_nonnegative_halves, positive_without_year_best, weekly_t, combined_better_each_year, combined_fall, combined_t, selected_max_t | 1.000 |

Largest annual falls in the closed-trade cash curve: main 7.47%; GAP_REPAIR / g0 / LONG 6.78%; EMA_CROSS / g1 / SHORT 12.68%; CLOCK_MOMO / g3 / SHORT 27.96%. These exclude intratrade marks. The time-of-day addition reached 27.96% and fails the drawdown bar; risk brakes are not a guaranteed maximum loss.

No two-sided parent genome was profitable in all three years. [Full 48-genome ledger](TRIAL_LEDGER.md) includes every failed arm; no winner-only presentation. All eight random results, half-year/sample/best-day checks, cost ₹300 sensitivity, weekly tests and drawdown comparisons remain in the JSON results.

## Breadth and what failed

The 12 families were moving-average crossovers, adaptive-average turns, channel breakouts, Bollinger re-entry, CCI re-entry, RSI divergence, regression reversion, failed prior-day levels, gap repair, compression breakout, OBV-confirmed breakout, and momentum from earlier sessions at the same clock. Each had four fixed combinations of horizons of 10/20 bars, stops of 1/1.5 ATR, targets of 2/3 risk units, and existing LIVE/RUN exit profiles. New entries used their own logic on daily ADX<30 days; they did not inherit the old four-strategy stretch filter. Main remained ADX 30/stretch 0.5 with its own exits and brakes.

For example, channel-breakout g2 earned about ₹52,663 in 2024 but lost ₹113,494 in 2025 and ₹33,711 in 2026 after the allowance. RSI-divergence g3 earned ₹27,704 in 2026 but lost ₹69,637 in 2024. These are descriptive examples, not proposed year switches. A good historical year does not tell the system in advance when the rule will work. The shared four-week-block sign-flip sensitivity preserves arm correlation, but cannot correct all previous searches, all proposed subsets, or repeated use of these years.

## What the loss-making parts have in common

All 222 main/TPB entries were reconstructed from causal inputs. Mutating future minute prices and daily prices unavailable at the signal left every feature unchanged. Partitions by side, member, prior trend, volatility, VWAP location, range, volume, gap and clock reconcile to the control totals. These are diagnostic slices, not backtested new filters.

| Main component | Trades | Net after extra ₹200 | Before that extra allowance |
|---|---:|---:|---:|
| Calls | 56 | −7,662 | +3,538 |
| EFF | 71 | −13,956 | +244 |
| TPB | 20 | +31,070 | +35,070 |

The before-allowance column already includes shipped fees and modeled bid/ask. It is not gross profit. EFF still lost in 2024/2025 even before the extra allowance, and calls still lost in 2024/2026. Costs are material but are not the only explanation. Daily DMI or EMA agreement did not consistently turn the main book profitable in each year. TPB low-ADX puts remain the existing more promising control (+13,199/+27,831/+23,560 one-lot standalone); that is previously seen evidence, not a discovery or qualification from this round.

## Can an option structure fill the gap?

Tested: 50/100/150-point debit verticals, inverse credits, same-direction credits using the other option type, and neutral ironfly/condors with widths of 50/100 and offsets of 0/50/100. Every leg required a positive-volume exact-minute candle at both recorded entry and exit; missing/incoherent quotes remained unavailable. Prices use adverse modeled bid/ask, four/eight-order current fees and extra ₹200/₹400 per complete structure. Entry risk uses entry-only information; full-width/two-width cash is reserved, with no credit-funded exposure.

No expression clears the frozen 95%-risk-compatible-coverage, sample, all-year-positive at ₹400, best-day and same-cohort-improvement bar. A150-point debit on main puts looks positive on a tiny compatible subset (+556/+71/+173), but covers only 4/16,2/25,5/23 requested trades and underperforms those same single-leg trades. A complete 50-point same-direction credit on main calls loses roughly ₹6,708/₹15,351/₹7,239 at ₹400 extra. Wider or favorable-only subsets are not reliable replacements.

All 222 parent records are sealed by file and record hashes. 2,664 original expression rows were independently rebound/repriced, plus 3,996 extension rows checked for exact economic binding and financial identities. Those 6,660 rows reuse 222 signals; they are not independent trades. Stored stops are closing/trailing fields, not immutable initial-stop evidence.

These are matched-clock expression diagnostics, not a spread portfolio or independently timed volatility strategy. They do not model a joint spread stop, hedge-first order lifecycle, partial leg fills, historical broker margin or a ₹15,000 account. No conclusion that every credit/neutral strategy fails follows from this test. A true adapter is required before one can claim such a strategy trades profitably. [Primary-source mechanics and limits](expressions/SOURCES.md), [broader research map](SOURCES.md).

## Correctness and limits

- 254 fresh replays, 39,070 closed records reconciled; max net discrepancy below ₹0.00005. Original 15 unresolved records remain preserved; corrected screen and children have zero unresolved. The many replay records share the same 699 sessions and are not independent market evidence.
- Special March 2/May 18,2024 sessions closed 12:30. A separately frozen calendar repair uses entry cutoff 12:00/hard flat 12:25 only on those dates, with actual observations and no invented break quotes. All 59 2024 arms were rerun; 118 ordinary 2025/26 outputs were reused with exact hashes and inactive-date proof. Main/TPB controls and ordinary raw records match. This clock is a declared research assumption, not a historical live-execution claim.
- All 699 cached sessions freshly reparsed from sealed raw candles and identical; original/source/memo/settings/data and nested source hashes checked. No market-data API calls or downloads. Known 2025 negative-volume bars, missing depth/gaps, UNKNOWN archived regimes, normalized lot of 65 and current rather than historical fees remain limitations. No historical fill guarantee.
- 138 focused tests passed; no full-engine-suite claim. Production availability remained HTTP 200 at the recorded checks; its checkout stayed c97cb8c3ba0eeb4ac8e9966135b07034d760b40d. No edits/restarts/orders/messages/capital activation.
- Preparatory calendar harness launch failures (wrong cache field and uncommitted regenerated receipt) were caught before any corrected replay. Source was corrected/re-frozen before scoring; logs, failed versions and planned bounded-slice timeouts are retained. [Commands and commit handoff](VERIFICATION.md).

- Final reporting review caught NumPy boolean checks serialized as text. Original outputs remain intact; v2 files strictly normalize 51 known flags, recheck numeric statistical contracts, and preserve every economic metric and rejection verdict. Reports use v2. The 11 new regression checks include the actual NumPy/JSON reproducer and reject ambiguous or inconsistent flags. No strategy or threshold changed.

## Concrete next work

1. Keep these additions out of runtime. Preserve current main, existing TPB-put and no-EFF comparisons; do not replace them because one new calendar year or subset looked attractive.
2. Run the original 2023 exam with its six books unchanged after verified acquisition. Its own rule, candidate list and owner decision remain authoritative. Do not append this round’s proposals to that exam. No 2023 test was scored here; earlier daily/futures warmup is not a full untouched option exam.
3. Measure actual entry/exit spreads, quote age, displayed depth and fill slippage by clock/liquidity on prospective observations. Replace the conservative execution allowance only with evidence and a new frozen comparison. Preserve adverse tails; do not lower costs simply to pass.
4. Repair/validate negative-volume and special-session inputs as a separately versioned data/adapter task. Preserve original receipts and compare every affected session. A candidate whose conclusion depends on the special clock needs an independently frozen clock sensitivity before any promotion.
5. Research event/news reaction, constituent-relative strength or volatility selection only after obtaining timestamped arrival/revision histories, point-in-time constituents, or suitable multi-leg quotes. Current unsigned volume/price candles cannot supply signed order flow or historical executable depth.
6. If a funded spread idea later warrants further work, first build a two/four-leg lifecycle with entry-only cash/margin checks, no uncovered leg, partial-fill/recovery behavior, conservative exits and genuine shared-account replay. This round’s paired returns cannot substitute for it. Freeze a small new question and prospective paper acceptance before tuning.

Research is complete and stored in Dev. Nothing here proves future profitability, permits deployment, changes strategy authority, or guarantees capital preservation. A smarter entry/exit system needs repeatable decision value after costs; this search did not establish that value for a new addition.
