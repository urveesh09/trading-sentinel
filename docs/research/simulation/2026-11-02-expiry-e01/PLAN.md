# E01 — expiry research and bounded paper improvements

Base Dev6d6caf7, branch codex/production-correction-hedge-p0. Production
d52642f is read-only. November2,2026; today's session is not finished.

## Problem and first slice

The expiry book has A breakout, B late strangle, C lottery and independent
shadows. Its history mixes promoted versions and includes assumed settlement
and auction-window fills. Only eight Production expiry sessions exist. The
regular F&O multi-year exports must not be assumed to contain zero-day options.
Determine exact data coverage; reproduce historical execution and current v3
on immutable recorded packets before selecting improvements.

Files/contracts: this study's offline exporter/replay/tests/configuration and
evidence, then bounded pure E01 policy/native shadow integration ONLY if the
declared comparison supports it. All changes in Dev; preserve N11 and live
order authority, original expiry A/B/C rules and historical records. Read
docs/2026-10-05-expiry-day-paper-book.md and the dated Production expiry audits.

## Evidence and execution

- Online SQLite backup from a read-only source mount into Dev; never copy an
  active main file without its journal. Snapshot all eight historical expiry
  sessions through2026-10-29; no unfinished/current day and no credential data.
- Bind recorded quotes/depth/timestamps/spot/future, requested catalogue,
  versions, fees, day states and observed positions. Raw data stays `_local`.
- Freeze code/configuration/inputs before candidate scoring; maintain separate
  exact historical parity and current-rule counterfactual controls.
- Replay native `_tick_underlying` offline, using only current packet data and
  its actual decision clock. No scheduler, provider, broker, Telegram delivery,
  Production restart, build or deployment. One worker; at most two only after
  market close and with sufficient host memory.
- Unknown quotes/depth/settlement remain unavailable or explicitly assumed.
  Auction-window fills are unverified execution, never broker-filled profit.
  Do not manufacture depth or use next-week options as zero-day substitutes.

## Finite development, not an unlimited winning-number search

Inspect baseline failure mechanisms first. At most TWO candidate policies per
round and at most TWO rounds (four novel policy arms total). A later round
must document the previous failure before its source/acceptance freeze. Small
fixed neighbouring settings may diagnose robustness but cannot replace a
failed primary. No test on2022; no new download, target, or repair implicit here.

Profit route: higher modeled net than current v3, no worse worst day and closed
drawdown, net excluding own best session no less, both underlyings no worse,
and unchanged capital/full-premium ceilings and execution fidelity.
Loss-control route: smaller worst day AND drawdown, aggregate net no less than
90% of baseline positive net (or higher if baseline net<=0), no worsening of
net excluding the best session, and no extra budget/order authority. Check
both routes at ordinary and a declared adverse fee/slippage scenario. All
conditions must hold; no switching to an easier benchmark after seeing scores.
Freeze concrete policies/scenarios and all source before their first replay.

Eight correlated expiry sessions cannot establish profitability, even if a
screen passes. The small sample limits iteration; do not count quote ticks or
shadow duplicates as independent trades. Keep every failure and mark dates
already examined. Genuine forward evidence remains required.

## Acceptance / rollout / rollback

Exact baseline position/event/fee parity where source/packets support it;
independent cash/fees/depth/clock/budget/pending-exit/carry/settlement checks;
focused native regression tests; source/atlas/documentation consistency.
Any accepted E01 addition is paper-only, independently versioned, replayable,
and preserves historical A/B/C. Promotion to main is not automatic. Rejected
arms stay research; do not ship them as a profitable default.

Push completed slices on the SAME branch, updating SYSTEM_GUIDE and active
plan/checklist each commit. Rollback of research needs no runtime action;
any optional paper shadow has an explicit switch and preserves open exits.
Production promotion only through GitHub, separately authorized. Remaining
work and coverage limits must be recorded even if no candidate passes.
