# N05 — protect recovering trades before considering larger lots

**STRUCT30 improves the original balanced reference in every studied year,
without changing its169 economic admissions or any size cap. It does not beat
the previous STALL30 challenger on2025/2026 profit or worst drawdown, and fails
the stricter predeclared primary test. Orchestration remains unproven.**

Keep all three identities across compaction. Read
[FNO_RESEARCH_PROGRESS.md](../../../FNO_RESEARCH_PROGRESS.md),
[the unchanged reference](../../../FNO_RESEARCH_REFERENCE.md) and
[the unchanged prior challenger](../../../FNO_RESEARCH_CHALLENGERS.md).
Their machine records bind exact configurations/evaluation hashes/status.
No configuration is represented as a known winner or qualified live replacement.

## What was implemented

Finish N04's explicit plan before sizing experiments. On unchanged MAIN +
one-lot LOW-day TPB additions + EFF retest entry, compare original BASE exits
and exact prior STALL30 against TWO frozen refinements:

- **DELAY45:** evaluate existing untrailed/negative-net/progress<0.5R stagnation
  from45min rather than30. Re-evaluate the current bid/net/progress; do not latch
  a losing observation from30min or fill retrospectively at45.
- **STRUCT30:** keep existing STALL30 eligibility, but additionally require a
  fresh completed5-minute close to lose the ORIGINAL retest broken level against
  the trade. Strict LONG below/SHORT above, no buffer; equality does not trigger.
  The level comes from immutable admission evidence. No current/future-bar leak.

Missing/stale/invalid structure means native management, with all underlying/
premium stops, trail and hard-flat active.60min remains the original soft
stagnation check, not a maximum holding cap. No90min branch, widened stop,
averaging, extra indicator grid, higher lot limit or capital/risk change.

## Results under unchanged normal size limits

| Review rule | 2024 | 2025 | 2026 to Oct28 | Worst annual closed fall |
|---|---:|---:|---:|---:|
| Original saved reference | Rs+56,192 | Rs+50,090 | Rs+54,153 | 5.22% |
| Prior early-exit challenger | Rs+51,303 | Rs+54,051 | Rs+77,135 | 4.65% |
| Review stagnation at45min | Rs+56,192 | Rs+50,538 | Rs+62,195 | 4.92% |
| Review30min only after retest level fails | Rs+57,243 | Rs+50,726 | Rs+61,496 | 5.00% |

FreshRs250,000 each year; normal2-lot/3-when-proven caps; ONLY extra LOW-day
TPB remains1lot, normalized lot65. All figures modeled NIFTY single-leg net
after current fees, adverse candle-derived bid/ask and stress(200+5*lots)*lots.
Independent annual accounts/books are not a continuous wallet, whole-system
portfolio, actual broker fills or a forecast for a small live account.

STRUCT30 annual closed falls2.16%/5.00%/2.77%, versus original2.16%/5.22%/4.02%.
Its gains over the original are aboutRs1,051/Rs636/Rs7,344. It is a useful
**STRUCTURAL_RETEST_N05** research lead and is recorded separately. Existing
BALANCED_RETEST_N03 and BALANCED_RETEST_STALL_N04 are not overwritten.

The prior STALL30 still earns aboutRs3,325 more in2025 andRs15,639 more in2026,
with lower worst-year drawdown4.65%. STRUCT30 instead preserves more2024 profit.
There is a measured trade-off, not a single proven best configuration.

## Where the profit improvement actually comes from

STRUCT30 retains ALL33/80/56 original signal-and-entry opportunities and their
exact initial time, premium, quantity, stop and target. Non-EFF exit lifecycles
also match exactly. Only six EFF exits change: one2024, one2025 and four2026.
Each new exit is still a LOSS, but a smaller loss than the original. Paired
delta sums exactly to the all-year book uplift. There is no larger-position
effect or changed admission behind this particular comparison with BASE.

The two2024 trades cut too early by STALL30 are allowed to recover because the
original retest level has not failed at the early review. A different2024 trade
does lose the level and exits earlier, reducing loss by aboutRs1,051.
This is price-aware management of an existing trade, not knowledge that its
entry was destined to profit. Six changed cases cannot establish reliable entry
confidence or justify increasing their lot sizes; all six actually close at a loss.

DELAY45 restores2024 BASE economics, adds aboutRs448 in2025 andRs8,042 in2026.
Some2026 change involves other-member exposure/cash history, so its full gain
must not be presented as pure paired exit improvement. effect-accounting.json
reports both BASE and STALL30 comparisons with immutable-term pairing; resized/
missing entries stay unpaired. review-case-audit.json keeps known review inputs
separate from later original outcomes and never fits on those future labels.

## Equal-quantity diagnostic

| Review rule | 2024 | 2025 | 2026 to Oct28 | Worst annual closed fall |
|---|---:|---:|---:|---:|
| Original saved reference | Rs+36,439 | Rs+45,487 | Rs+51,469 | 4.01% |
| Prior early-exit challenger | Rs+32,922 | Rs+48,530 | Rs+57,873 | 3.99% |
| Review stagnation at45min | Rs+36,439 | Rs+46,531 | Rs+56,280 | 4.01% |
| Review30min only after retest level fails | Rs+36,964 | Rs+46,123 | Rs+55,907 | 4.01% |

Both new rules improve the original one-lot book in all three years, confirming
the direction is not simply a normal-sizing artifact. It remains a diagnostic;
no live limit recommendation or post-result choice of sizing mode follows.

## Acceptance registered before scoring

The owner specifically asks for more profit without more drawdown. This round
therefore requires a normal candidate to beat BOTH saved references each year
and have no larger annual closed fall than EITHER reference. Unlike older
rounds there is no1.5x drawdown allowance. This rule was frozen before new
scores, not used to rewrite earlier results. Full-precision net/fall values
are used for the checks, not rounded display tables.

Both candidates pass positive-all-years, sample, best-winner/day removal and
half-year checks, but neither meets the full primary objective:

| Candidate | Failed primary tests | t versus STALL30 | Adjusted p versus STALL30 |
|---|---|---:|---:|
| DELAY45 | net_not_worse_both_each_year, better_total_stall, drawdown_not_worse_both_each_year, paired_weekly_stall, max_t | -1.03 | 0.7374 |
| STRUCT30 | net_not_worse_both_each_year, better_total_stall, drawdown_not_worse_both_each_year, paired_weekly_stall, max_t | -1.03 | 0.7374 |

Diagnostic paired t versus ORIGINAL BASE is2.01 for DELAY45 and2.05 for STRUCT30.
The registered primary comparison versus STALL30 is−1.03 for both, adjusted
p0.7374. Do not promote the favorable secondary benchmark to primary after
viewing results. Two-arm max-t is exploratory and does not undo all earlier
searches on these repeatedly inspected years. No candidate qualifies, and no
third offspring/parameter sweep was run after these outcomes.

## Verification

Pre-score source/config/reference/27-book/acceptance freeze **f11544c**; all
frozen files remain unchanged. Availability probe used ALL12 prior normal early
review locations (3/4/5), all with level/fresh context/positive bid, without
looking for a threshold that isolates favorable cases.

- 27 fresh annual full-cash replays,9/year, completed first550s slices in
 116/126/106s;3 memory-guarded workers. Fifteen control books reproduce N04
  economics exactly, apart from fresh IDs/metadata tags.
- 1,464 financial/immutable-admission/accepted-trace identities,2,928 archive
  entry/exit prices and184 original retest paths verified with zero errors.
- 138 EFF first-executable-exit lifecycles reconstructed over6,868 observations,
  including293 structural review checks using independent causal closes.
  These counts overlap repeated books, not independent market samples.
- Independent27 cash paths,9 weekly vectors/two resampled primary tests match
  the full-precision profit/drawdown objective.124 focused tests pass:25 new,
 45 parent,5 native-soft-clock and49 existing affected book/replay checks.
- Prior699 raw/cache/coverage checks reused only by identical inherited
  source/data/calendar/daily/memo hashes; no fresh699 reparse is claimed.
  All new admission/quote/review/exit paths were audited separately.

Commands/status/environment in VERIFICATION.md, canonical results.json,
path-crosschecks/statistics/effect-accounting/review-case-audit preserve failures.
Current fees/normalized lots/candle-model quotes, unknown historical depth/
regimes, gaps and unchanged56 negative-volume2025 bars limit execution fidelity.
Closed-cash fall is not intraday MTM loss. All2024–2026 years seen;2023 option
data/exam not inspected/scored, inherited prior daily/futures warmup declared.

## What is still left before larger sizing

The orchestration design defect was corrected in research. Code/control/causal
checks are not proof that the switch selects the right profitable variant.
No selector was trained here; the entry strategy was fixed so exit effects
could be isolated. Static exit-refinement slice is now complete. Retain all
three named alternatives rather than keep fitting more knobs to these years.

Next work is prospective quote/depth/slippage/cost evidence, and a separately
frozen past-only variant-selection test with the original main explicit. Any
new label must be closed before the selection clock, with sample/calibration
guards; no hindsight best-year combination or entry-confidence claim from the
six losing-exit examples. Keep2023 deferred until the owner requests its exam.

Larger-size research is conditional LATER work, not something to unlock because
one backtest looks confident. Preserve the old cap as control and evaluate only
bounded strategy-specific reallocation inside unchanged cash/per-trade/daily/
portfolio risk budgets. Require prior-data-only calibration, equal-risk controls,
concentration/gap/full-premium-loss/spread stress and predeclared drawdown/ruin
checks on fresh evidence. No unlimited cap, borrowing, widened risk budget or
automatic Production/money change. Increasing size can amplify losses too;
no tested drawdown is a promised future ceiling (primary risk sources in SOURCES).

No application/config/migration/Production/order/message/capital/lot-limit
change or restart. Dev research/docs only, unrelated dirty work retained.
Workers finish before handoff; rollback stops research workers only.

## Complete27-run inventory

| Book | 2024 net / trades | 2025 net / trades | 2026 net / trades |
|---|---:|---:|---:|
| NORMAL / BALANCED_RETEST / BASE | +56,192 / 33 | +50,090 / 80 | +54,153 / 56 |
| NORMAL / BALANCED_RETEST / STALL30 | +51,303 / 33 | +54,051 / 80 | +77,135 / 56 |
| NORMAL / BALANCED_RETEST / DELAY45 | +56,192 / 33 | +50,538 / 80 | +62,195 / 56 |
| NORMAL / BALANCED_RETEST / STRUCT30 | +57,243 / 33 | +50,726 / 80 | +61,496 / 56 |
| ONE / BALANCED_RETEST / BASE | +36,439 / 34 | +45,487 / 80 | +51,469 / 56 |
| ONE / BALANCED_RETEST / STALL30 | +32,922 / 34 | +48,530 / 80 | +57,873 / 56 |
| ONE / BALANCED_RETEST / DELAY45 | +36,439 / 34 | +46,531 / 80 | +56,280 / 56 |
| ONE / BALANCED_RETEST / STRUCT30 | +36,964 / 34 | +46,123 / 80 | +55,907 / 56 |
| NORMAL / MAIN / BASE | +16,371 / 25 | +5,710 / 50 | +30,540 / 33 |
