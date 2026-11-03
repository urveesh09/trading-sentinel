# E02: iterative expiry strategy development with a risk ceiling

Owner, November 3, 2026: use multiple iterations and genome methods to diagnose
and improve expiry, targeting profit without an excessive-loss trade-off. This
supersedes the previous study's two-proposal stopping point and small search
limit. It does not make a positive backtest inevitable or authorize real orders,
deployment, downloader quota changes, use of the protected 2023 exam or edits to
Production. Dev starts at 39caa62, same branch; existing owner work is preserved.

## Evidence, files and contracts

New research scripts, snapshots, trial ledger, folds, freezes, tests and results
live here. Native `expiry_paper` money/fee/whole-lot functions are reused. The
archived E01.1 2025 minute control is reproduced first. All old research is
immutable. Production is read-only; all implementation is in Dev. N11 stays as
it is. No broker, scheduler, delivery, SDK or network acquisition in the replay.

2025 NIFTY expiry minute chains are development, already seen in the earlier
exam. The 2026 ten-second opening-strike evidence is also seen and can support
conditional transfer/exit checks, not a complete chain entry replay. The unrun
November 2 E02 snapshot contains 52 NIFTY 2024 expiry sessions: reserve their
option paths for the final exam, no scores/prices/strikes inspected before the
final source/candidate freeze. Broader 2024 underlying regimes were used by
F&O research, so this is not a wholly unknown market regime. SQL must exclude
2023 at every step. No new history calls or alterations of raw evidence.

Minute proxy: actual independent index/front-future observations; causal
completed-bar features; next-bar fills; no intrabar look-ahead or perfect stops;
ordinary and worse execution; native exchange fees; actual observed option
prices, never theoretical fills. Missing quotes/strikes are refused, not filled.
Closing deadline precedes the dataset endpoint; no invented 15:38 auction fill.
Normalize to current NIFTY lot65/fees explicitly, with historical lot-size
robustness separate. BAR_LIFECYCLE research is not exact ten-second execution.

Standalone E02 research cash starts at Rs25,000, no refills/margin/leverage.
One directional long-option position at a time. Every entry reserves its whole
premium plus buy fees and one possible sale fee per lot. The sum of original
daily ticket reserves cannot exceed Rs2,500; profit never increases that day's
allowance. Maximum two entries. Stop losses are planned, not guaranteed prices;
a gap can lose the whole reserved ticket. Re-entry, if studied, needs a fresh
causal signal and the original unused daily reserve. No averaging down.

## Iterations and selection discipline

1. Diagnose 2025 losses using only contemporaneous entry features and later
   outcomes clearly labelled as labels. Audit controller/risk/execution defects
   before strategy selection. Reproduce old E01.1 controls exactly, retaining
   contract corrections separately when needed.
2. Build one reusable causal entry/exit/cash replay. Explore simple mechanisms:
   break continuation, retest/reclaim, and range fade; directional efficiency,
   stretch, option premium/participation and confirmation can refuse poor entries.
   Exits retain a hard premium backstop, gain protection and a finite time exit.
   No date/strike/month-ID rule, future label, future-fit indicator or giant
   condition tree is allowed.
3. Run reproducible seeded genome/search rounds on 2025 only. Count and retain
   every attempted rule, seed and score, including failures and family changes.
   Use chronological blocks, leave-best-session-out, conservative fills,
   minimum activity and a complexity penalty; test coarse parameter neighbours.
   Do not call reused 2025 folds untouched. Use cross-fitting/rolling selection
   as a diagnostic of selection decay, not a substitute for the final exam.
4. Iterate on explicit failure mechanisms, with round receipts before changes.
   Freeze at most two finalists, source/input hashes, adverse execution and
   acceptance BEFORE opening 2024 option paths. No new candidate after that exam
   can claim 2024 as untouched. A failed exam stays failed; later development is
   clearly in-sample and requires new forward data for qualification.

## Fixed target and acceptance

Prefer positive net after all fees, positive net without the best session,
profit factor >=1.2, at least15 trades/year, ordinary AND adverse, in both 2025
development and the 2024 final exam. Both halves of each year must be reported;
at least two quarters must be positive. Final daily loss must be no worse than
Rs1,250 and cumulative realized drawdown no worse than Rs5,000, and both no
worse than the same-cash E01.1 control. Hard full-premium reserve remains
Rs2,500/day. Report worst trade/day, marked and realized drawdown, losing streak,
cash exhaustion/brakes, fees, unresolved exposure and best-day concentration.
These are eligibility criteria for broker-free paper evaluation, not a guarantee
of future profit or a promise that future drawdown cannot exceed the sample.

Finalists must survive nearby parameters and source/execution audits. A positive
2024 result is only one additional historical test. SENSEX requires its own
recorded-chain validation before enabling entries; the NIFTY minute result
cannot silently qualify SENSEX or the whole A+B+C expiry book.

## Verification, rollout, rollback and remaining work

Tests: causal/truncated-history signal parity; pending next-bar orders; stop-
first priorities; entry limit/risk revalidation and dust; fees/cash identity;
daily reserve never recycled; missing volume/quote handling; lot/price tick
rounding; no negative premium, naked short or future-based sizing. Compare fast
search against exact native-money replay on every finalist. Snapshot and source
guards refuse changes after final freeze. Record real commands/results and
resource limits; one bounded worker, no heavy job beside a download.

Update guide/active plan/checklist per implementation commit; regenerate atlas
for source declarations and verify consistency immediately after each commit.
Record commit/push status and deployment separately. Only a supported finalist
may become a separately versioned Dev paper shadow, preserving current C and
all A/B/old shadows. No automatic main-rule promotion or deployment. Rollback:
disable/remove the isolated research/shadow without rewriting old records.

Remaining: source/coverage audit and baseline; replay/features; measured rounds;
final candidate freeze; 2024 exam; independent financial/causal audit; justified
Dev shadow if supported; final report, commits and handover.
