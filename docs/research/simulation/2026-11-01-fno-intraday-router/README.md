# Intraday strategy switching — November 1, 2026

**Result:** No tested switching policy clears the frozen acceptance bar.

The requested flexibility is implemented and tested in an offline Dev research adapter. It reassesses the market on each closed five-minute bar, can select different strategies during one session, and tests both normal exits and exits on confirmed regime invalidation. Production, current main-book code, order authority and capital switches are unchanged.

## The earlier loss was a research result

The +₹52,663 in 2024 and −₹113,494 in 2025 came from an isolated one-lot breakout experiment, not Production. It already used only days with prior daily ADX below 30, and diagnostic loss brakes were disabled. That allowed us to observe its failures. The current main book did not take that ₹1.13 lakh loss. The yearly main controls below use normal sizing, cash and brakes.

## What the switching tests earned

Each cash book starts every year with a fresh ₹250,000. It pays shipped fees, adverse modeled bid/ask and the existing extra execution allowance in its cash path. This is not a continuous account balance or a ₹15,000-account forecast. 2026 ends October 28. The static mix uses the same six experts as the routers, with no intraday state choice.

| Shared-cash replay, net ₹ | 2024 | 2025 | 2026 |
|---|---:|---:|---:|
| Current main | +16,371 | +5,710 | +30,540 |
| Static same-expert mix | +12,875 | -38,385 | -38,456 |
| Fixed intraday switching | +36,408 | -37,734 | -38,812 |
| Switching + invalidation exits | +38,286 | -38,560 | -37,877 |
| Past-outcome expert selector | -6,034 | -37,957 | +5,090 |

| Policy | Trades 2024/25/26 | Largest annual closed-cash fall | Extra state exits 2024/25/26 |
|---|---|---:|---|
| Fixed intraday switching | 237 / 46 / 73 | 18.54% | 0 / 0 / 0 |
| Switching + invalidation exits | 237 / 41 / 73 | 18.18% | 6 / 1 / 2 |
| Past-outcome expert selector | 167 / 75 / 60 | 20.65% | 0 / 0 / 0 |

Falls use booked cash after closing trades; they exclude intratrade marks. Risk brakes do not guarantee a maximum loss. One-lot actual router replays, ₹300 cost sensitivity, half-years, best-day removal, exact usage and all pass flags are retained in freshness/results.json. No static profit slices were substituted for a real switching book.

## Were the bad days identifiable before trading?

We attributed the original breakout to conditions observable at its entry, and separately to the shape of the full archived session. The latter is hindsight only and NEVER a routing/training input. ARCHIVED_TREND means the archived end-to-start move is at least half its high–low range. It is a simple descriptive proxy, not a verified universal trend-day label.

| Original breakout, hindsight shape | 2024 net / trades | 2025 net / trades | 2026 net / trades |
|---|---:|---:|---:|
| ARCHIVED_TREND | +89,255 / 137 | -31,834 / 154 | -7,144 / 103 |
| ARCHIVED_TWO_WAY | -36,592 / 166 | -81,659 / 121 | -26,567 / 122 |

In 2025 the breakout lost about ₹81,659 on archived two-way days and ₹31,834 even on archived directional days. Thus the loss was not confined to sideways days under this measure. Selecting only retrospectively directional days still leaves a loss that year. Direction, entry timing, exits, option premium and costs also matter. This table cannot determine how much loss came from theta or implied volatility; no such causal decomposition is claimed.

| Original breakout, entry-time state | 2024 net / trades | 2025 net / trades | 2026 net / trades |
|---|---:|---:|---:|
| RANGE | +78,396 / 119 | -23,604 / 103 | -56,739 / 76 |
| SHOCK | +14,004 / 9 | +11 / 3 | +12,454 / 5 |
| TRANSITION | -51,088 / 160 | -76,217 / 155 | +18,155 / 123 |
| TREND_DOWN | +6,924 / 6 | -9,306 / 7 | -1,559 / 13 |
| TREND_UP | +4,427 / 9 | -4,377 / 7 | -6,022 / 8 |

A key counterexample: the same RANGE-at-entry category earned ₹78,396 in 2024 and lost ₹23,604 in 2025. In2024 many winning breakouts began before a trend was confirmed. Waiting for a strong trend can remove those winners as well as losers. A current-state estimate is not a forecast that its next trade will pay.

The current main also does not obey a universal trend=profit/range=loss rule: using the same hindsight measure, in 2024 it earned ₹22,147 on two-way paths and lost ₹5,776 on directional paths; in 2025 it earned ₹15,423 on directional paths and lost ₹9,713 on two-way paths. A trade can profit from one section of a day that later reverses. Its opportunities require finer analysis than the final day label.

## What was built

- State inputs: warmed intraday ADX/DMI, recent directional efficiency and VWAP crossings/distance, ATR shock checks, and prior daily trend-strength context. Every input is available by its closed bar. Two consecutive labels confirm transitions; missing/gapped/invalid or shock observations reset admissions immediately.
- Fixed switch: breakout first during confirmed trends, then shipped pullback/momentum experts; Bollinger re-entry in ranges; TPB during transitions. Both option directions are supported. Trades retain their own stops/targets/management.
- Exit ablation: after at least 15 minutes, three confirmed contrary/range states can invalidate the entry. Existing stop/trail/hard-flat management runs first; a missing bid cannot become an invented sale.
- Learning switch: monthly models use only the prior 252 sessions and trades already closed before the month starts. Cell/global sample guards, shrinkage and positive scores choose experts. First 90 sessions use the declared fixed-rule fallback. These are labels from independent counterfactual expert books, not assumed simultaneous live fills.
- The two new experts can signal again when conditions become suitable. The old first-trigger-only breakout remains a separate exact parity control. Normal cash, crisis, expiry, day caps, duplicate-bar and deadline checks remain active. No state change resets cash or abandons exposure.

Plain language: a breakout buys an option when price escapes a recent channel; a pullback joins an existing move after a pause; reversal tries to profit as price returns from an extreme. Bearish signals buy puts. ADX measures current trend strength; efficiency measures how direct the recent price path was; VWAP is a volume-weighted reference price. These describe observed conditions, not the rest of the session. With six completed bars and confirmation, the new state selector cannot be fully ready at the opening bell.

## Did it actually use different strategies?

### Fixed intraday switching

| Expert | 2024 entries | 2025 entries | 2026 entries |
|---|---:|---:|---:|
| BOLL_REENTRY | 79 | 9 | 23 |
| DONCHIAN | 123 | 33 | 42 |
| EFF | 0 | 0 | 1 |
| OR20 | 2 | 0 | 0 |
| SHIPPED | 6 | 2 | 2 |
| TPB | 27 | 2 | 5 |

Failed frozen checks: positive_each_year, five_halves, without_year_best, beats_main_each_year, beats_static_each_year, drawdown, paired_main, paired_static, max_t.
Exact search-adjusted p: 0.9636. Learning fallback entries by year: 0 / 0 / 0.

### Switching + invalidation exits

| Expert | 2024 entries | 2025 entries | 2026 entries |
|---|---:|---:|---:|
| BOLL_REENTRY | 79 | 8 | 23 |
| DONCHIAN | 123 | 29 | 42 |
| EFF | 0 | 0 | 1 |
| OR20 | 2 | 0 | 0 |
| SHIPPED | 6 | 2 | 2 |
| TPB | 27 | 2 | 5 |

Failed frozen checks: positive_each_year, five_halves, without_year_best, beats_main_each_year, beats_static_each_year, drawdown, paired_main, paired_static, max_t.
Exact search-adjusted p: 0.9609. Learning fallback entries by year: 0 / 0 / 0.

### Past-outcome expert selector

| Expert | 2024 entries | 2025 entries | 2026 entries |
|---|---:|---:|---:|
| BOLL_REENTRY | 32 | 3 | 0 |
| DONCHIAN | 117 | 56 | 0 |
| EFF | 4 | 2 | 0 |
| OR20 | 1 | 1 | 0 |
| SHIPPED | 3 | 0 | 0 |
| TPB | 10 | 13 | 60 |

Failed frozen checks: positive_each_year, five_halves, without_year_best, beats_main_each_year, beats_static_each_year, drawdown, paired_main, paired_static, max_t.
Exact search-adjusted p: 0.9656. Learning fallback entries by year: 78 / 0 / 0.

The independent decision audit also checks days with multiple experts actually admitted in one cash book:

| Policy | Mixed-expert days 2024 / 2025 / 2026 |
|---|---|
| Fixed intraday switching | 25 / 3 / 5 |
| Switching + invalidation exits | 25 / 3 / 5 |
| Past-outcome expert selector | 18 / 10 / 0 |

First chronological mixed-expert example (not selected for profit), 2024-01-16:

| Entry IST | Observed state | Expert | Modeled trade net ₹ |
|---|---|---|---:|
| 11:51:59 | RANGE | BOLL_REENTRY | -2,223 |
| 13:25:59 | TREND_DOWN | DONCHIAN | -2,745 |
| 13:36:59 | TREND_DOWN | DONCHIAN | -4,194 |

Positions can overlap under the inherited normal paper-book rules; these are not the one-position live-test account. The switch is real in the replay, but a range reversal and a later trend breakout can both lose. Normal stops close those positions.
## Evidence, limitations and next work

- 63 fresh replays in total (45 original plus 18 corrected); 10,880 closed-record reconciliations, excluding copied base duplicates. Corrected analysis uses18 new candidate books plus 27 reused base books; 8,040 closed records there reconcile with zero unresolved/errors, max net difference below ₹0.00005. All 166 focused checks passed. All 699 archived sessions were freshly reconstructed from raw and matched their caches.
- 2,840 corrected routed decisions were independently checked for causal state, expert eligibility, model cutoff and fallback. 5,680 entry/exit prices match actual archived observation packets; all 29 state exits satisfy the minimum hold, confirmed-state rule and priced bid. This proves consistency with the declared quote model, not actual broker fills.
- A separate input-contract correction blocks reuse of a closed-bar state once its END is five minutes old, including after a long gap; switch exits also lose their stale history. Original sources/results remain intact. Rebuilt labels/models were byte-identical (no training trade had stale input), and all 18 corrected replays reproduced the original economics. The guard repairs a latent boundary, not the historical losing edge. Canonical results are freshness/results.json; root results.json is the preserved original version.
- Exact main and old-breakout trade-for-trade parity passed in all years before model use. Every routed trade carries a book/year/leg identity with immutable initial price, quantity, time and risk terms. Model files and underlying expert evidence were hash-sealed and committed before candidate scoring.
- All three years have been studied repeatedly. Past-only training and prefix checks prevent mechanical lookahead; they do not undo earlier researcher selection or make these years a clean holdout. The frozen six-book2023 exam is unchanged and unscored.
- Minute option candles and modeled spread are not historical executable depth. Current fees, normalized lot of 65, unknown recorded regimes, known negative-volume/gap defects and the declared special-session clock remain limits. A same-observation close/new entry is a model sequencing assumption, not proof of broker acknowledgement timing.
- Primary sources support online state estimation, persistence and adaptive momentum/reversal as research approaches; they do not establish NIFTY option returns. [Sources and scope](SOURCES.md). [Frozen plan](PLAN.md). [Commands and commits](VERIFICATION.md).

A separate post-run descriptive check of the 803 original breakout trades also finds that every calendar-days-to-expiry category with trades lost in 2025, as did all three entry-clock groups. These partitions are not additional strategy tests or deployable rules; sample counts differ sharply across years. Full results remain in opportunity-context.json.

Next steps: retain the main book unless a separate qualified change is approved. Score only the existing unchanged2023 exam after verified acquisition. For a new adaptive study, predeclare trade-level payoff features—option premium/expected move, actual spread/liquidity/quote age and causal direction/volatility—in addition to state. Validate whether those distinguish good opportunities within the SAME state, with dated prior-only training and independent frozen comparisons. Timestamped news, constituent breadth or signed order flow needs real historical input before it can help. Measure execution costs prospectively and version input repairs separately. A new state threshold alone is not evidence of an edge.

No adaptive router is activated in Production by this study. A later positive research lead still needs prospective frozen paper evaluation and separate deployment/real-money authorization. Flexibility can change decisions; it cannot guarantee profit or identify every bad session before it happens.
