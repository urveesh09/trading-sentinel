# Passive research release and partner advisory next steps

Implemented in Dev on `codex/production-correction-hedge-p0`, 8 September 2026, following review of `c0377a7`.

## Release decision

Ready to merge for a **monitored passive-data deployment**, with the deployment checks below. This is not approval of strategy profitability, partner delivery eligibility or unattended operation indefinitely. No Production files, orders or Telegram messages were changed by this implementation.

The small remaining release corrections are implemented:

- Archive operations use fail-fast writer admission, with a process lock and SQLite writer lease shared across processes using the same archive root. There is no growing archive writer queue. A busy writer is an explicit observation failure; preservation failure leaves protected source rows intact.
- Persistent daily write accounting covers atomic archive writes, quote/run appends and compression allowance, including temporary recovery/summary/report output. The configured 256 MiB budget is now a conservative daily write budget as well as the existing active-file limit. Restarts do not reset it. Failed writes consume reserved budget deliberately. Export/master/candidate/report producers share it; large preservation captures can exhaust it and postpone collection, which must be reported rather than hidden.
- Capacity admission reserves payload/temporary headroom above the configured operational free-space floor. Compression failure keeps the original segment. The counter/lease files add small metadata overhead; this is not a whole-filesystem quota, and other applications can independently consume disk space.
- Storage stops are logged distinctly. No automatic deletion of research inputs was introduced. Multi-day retention/cataloguing remains a next milestone; first-session observation does not need to wait for it.
- Readiness reads the persisted quote summary rather than scanning the open quote archive. It distinguishes fresh, stale, time-unknown, time-invalid and unusable books. Current-valid and last-seen timestamps are separate; finalisation retains the summary. Freshness currently uses a 120-second threshold and five-second future tolerance; these are operational snapshot criteria, not execution qualifications.
- Readiness filesystem work and export hash verification run outside the async event loop; run-journal tail reads are bounded to one MiB per retained recent day. Contract catalogue lookup remains filesystem-based and should become indexed as archives grow.
- Failure in contract selection or the second quote batch is isolated by index. Partial counts survive and the next index continues. Individual malformed packets remain isolated.

Validation: **102 selected Python tests passed**, including ten new parametrised/regression cases for stale/missing/future timestamps after finalisation, restart-persistent journal budget, candidate budget, low-disk finalisation, cross-process writer contention, index batch failure and changed-row preservation. Edited modules compile and diff whitespace validation passed. No live-provider, full-session load or real Telegram acceptance test was performed. One existing Starlette deprecation warning remains.

## Deployment and first-session acceptance

1. Merge through GitHub and verify the running image contains the correction commit. Verify the persistent archive mount, application user permissions and measured free space. Do not infer the image version from the host checkout.
2. Preserve the retained operational evidence using the application's verified user/path. Expected Docker layout:

```powershell
docker exec --user quantuser --workdir /app python-engine python research_cli.py export-fno --source-db /data/cache.db --archive-root /data/research --underlyings NIFTY,SENSEX
```

3. Verify capture hashes/counts and remaining daily budget. The source DB is read-only for this export. Do not disable preservation-before-purge when capacity is exhausted; arrange capacity or defer cleanup safely. Do not edit budget counters to conceal consumption.
4. During the next market session, confirm both NFO/NIFTY and BFO/SENSEX actual provider responses, current masters, timestamp-valid quote records and durable run outcomes. Observe first few intervals and end-of-session disk/latency/finalisation behaviour. If archive writes stop, inspect busy/budget/disk reasons rather than assuming an inactive market.
5. Keep strategy profile, qualification and final dispatch validation in force. Independently inspect effective settings against the authoritative Production database. No existing qualification or profile was verified as part of this implementation.
6. A separately authorised fixed TEST message can verify the partner route. It must not contain a trading recommendation or manufacture a qualification. No TEST was sent here.

## What changes for the partner

The earlier continuous F&O tips and the new manual advisory product have different output goals. The prior service's exact historical message content/performance was not re-audited here. The current product aims to provide a complete conditional trade idea: index, exact option legs, maximum entry debit, trigger, invalidation, target/horizon, cost/risk and intraday management deadline. The partner still decides and executes manually.

The new correction commit itself improves evidence and reliability. It does not create a profitable strategy, increase alert frequency, qualify tips or start sending them. Default limits currently allow two new ideas and four management updates per day; change these only after studying useful opportunity supply and notification burden. The system should scan actively while being selective about messages.

Directional debit spreads offer a defined payoff when both legs are correctly established, with capped upside as well as bounded premium risk. They can reduce upfront premium versus the corresponding long call, but incur two-leg execution/cost complexity and may underperform a naked option on a strong move. Intraday realised returns are not expiration payoff values. Uneven fills, delays and closing only one leg invalidate assumptions about the intact structure. A directional spread is not automatically a hedge for the partner's existing portfolio.

Reference for general payoff mechanics only, not Indian contract settlement rules: [OIC bull call spread](https://www.optionseducation.org/strategies/all-strategies/bull-call-spread-debit-call-spread).

## Speculated outcome — hypotheses to measure, not promised returns

- **Useful outcome:** the partner receives fewer ambiguous ideas, knows the price beyond which to skip, sees why an idea is invalidated and gets an intraday exit reminder. This can improve discipline even before a return advantage is established.
- **Possible profitable outcome:** a separately validated policy captures enough favourable moves that gains exceed losses, spreads, charges and manual delay. Demonstrate this on untouched evaluation data separately for each index.
- **Possible disappointing outcome:** false breakouts, missed fills, capped gains, costs or delayed action erase the apparent edge. The right response is to reject/revise that policy, not increase message frequency to manufacture activity.
- **No-edge outcome:** research fails to support delivery qualification. Continue useful research and diagnostics; do not disguise uncertainty as confidence. No honest win rate, monthly income or 'massive fast profit' estimate is available from this software work.

Illustrative intended wording, not a live signal: 'NIFTY bullish intraday spread. Enter only after the stated trigger and within the maximum debit. Skip if price has moved beyond that limit. Invalidate at the stated level; close by the dated intraday deadline.' Production cards must supply validated actual terms rather than placeholders.

## Next implementation, alongside live collection

1. **Exact policy evaluator:** reuse `partner-manual-intraday-v1` decision/payoff/expiry/deadline logic; separate NIFTY and SENSEX dated contract assumptions. The legacy NIFTY single-option backtest is not qualification evidence for debit spreads.
2. **Evidence coverage:** pin evaluated/active legs through outcome expiry even outside the ATM window; archive decision input bars and availability times. Integrate full-mode WebSocket observations with explicit lower-frequency REST fallback. Never infer 15-second fills from minute data.
3. **Reproducible replay:** retain immutable data/code/defaults/calendars, reject malformed/future inputs, and report no-fill/unknown outcomes. Measure spread costs, displayed capacity and manual-delay scenarios.
4. **Frozen strategy comparison:** trend continuation, opening-range breakout and a failed-breakout challenger, evaluated with chronological holdout. Compare net expectancy, drawdown, tails, useful opportunity frequency and index/regime stability. These are research hypotheses, not production recommendations yet.
5. **Qualification and product setup:** register genuine reviewed evidence for the exact index/policy; save explicit INTRADAY profile and partner cost/risk constraints; verify authenticated effective settings and delivery routing. No partner broker login or proprietary strategy is required.
6. **Measured advice improvements:** rank qualified timely opportunities, suppress duplicate correlated exposure, prioritise invalidation/exit updates and collect optional feedback. MiniMax can explain findings and suggest research asynchronously; it cannot approve its own strategies or bypass price/risk checks.
7. **Long-term operations:** indexed readiness, streaming export/finalisation, reference-aware retention and multi-session load tests. Existing exports/finalisation still materialise data in memory; keep the bounded release monitored and size these before increasing collection volume.

Do not wait idle for data: build 1–4 immediately with clearly labelled fixtures for software tests, then evaluate using actual retained observations. A single successful collection session validates plumbing, not trading edge.
