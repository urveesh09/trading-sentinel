# Adaptive momentum exit study — implementation slice

## Scope and decision boundary

This Dev slice implements the first executable item in the adaptive-trader
roadmap: a **read-only, paper-only paired exit study**.  It compares the
current pure momentum exit evaluator with one fixed alternative on the same
already-recorded entry and quote path.  It is research instrumentation, not an
exit-policy rollout.

The alternative is deliberately narrow and predeclared:
`target_hold_trail_v1` does not loosen the initial stop, time-stop, hard-flat
deadline, sizing or entry policy.  Only after the current evaluator would
close for `target_hit`, it holds the remaining paper quantity and ratchets a
0.5R trail; all other current evaluator decisions remain in force.  It is not
an overnight/swing conversion and may not create broker, Telegram or scheduler
authority.

## Problem and contracts

Historical 15-minute OHLC alone cannot faithfully reproduce a monitor that
acts on intraday LTP observations.  The study therefore accepts a bounded JSON
packet of immutable entry identities and timestamped LTP observations.  Each
entry needs a unique identifier, ticker, timezone-aware entry clock, exact
entry/stop/target/quantity and source archive hash.  Every quote needs that
entry identifier, a timezone-aware observed clock and a finite positive LTP.

`momentum_exit_study.py` will:

1. Read only an input packet; it has no database, broker, HTTP, scheduler or
   outbound-message dependency.
2. Require chronological, same-session IST quote evidence from entry to the
   15:15 IST deadline, with a predeclared maximum observation gap.  Duplicate
   clocks with conflicting prices, pre-entry quotes, session crossing, missing
   close coverage, malformed times, and missing source hashes make that entry
   `INSUFFICIENT_EVIDENCE`; they never receive a synthetic time/price exit.
3. Reuse `evaluate_momentum_exit` for the baseline state machine, including
   partial/ratchet decisions and cost accounting.  The trailing alternative
   changes only target handling after the target is actually observed.
4. Produce canonical JSON containing the exact input SHA-256, frozen policy
   snapshot, per-entry paired paths, costs, P&L/R, quote-observed capture,
   drawdown and unresolved counts.  A report may not state an edge,
   qualification or promotion verdict.
5. Optionally write a report exactly once using exclusive creation.  The CLI
   otherwise emits canonical JSON to stdout.

## Files and acceptance checks

- Add `python-engine/momentum_exit_study.py` and
  `python-engine/tests/test_momentum_exit_study.py`.
- Update the adaptive roadmap, system guide, next-agent plan and handover with
  the actual boundary and validation receipt; regenerate the code atlas after
  source changes.
- Focused tests must prove: baseline policy reuse; paired same-path outcome;
  target-only trail activation; no look-ahead; stop/deadline preservation;
  incomplete/gapped/cross-session/conflicting evidence stays unresolved;
  costed partial accounting; deterministic canonical output; exclusive output;
  and structural absence of broker/network/order/message dependencies.
- Run focused tests plus affected momentum paper/exit/replay tests, Python
  compilation, `git diff --check`, and the atlas generator.

## Rollout, rollback and remaining work

The module is inert until an operator runs it with preserved input evidence.
It changes no runtime import, environment flag, database schema, live/paper
monitor, broker call, EXEC approval, risk gate, or partner delivery path.
Rollback is a GitHub revert of this isolated research module; it never deletes
input packets or already generated report evidence.

After this slice, build the wider decision-quality baseline and a separately
predeclared strategy basket only from retained data.  Real-session collection,
future held-out sessions, owner review and any new authority remain external
gates; a completed study can reject the alternative and cannot prove a
profitable strategy.

## Implementation receipt — Dev only

Implemented as `python-engine/momentum_exit_study.py` with a small CLI:

```powershell
.\python-engine\winvenv\Scripts\python.exe python-engine\momentum_exit_study.py `
  --input C:\evidence\momentum-exit-study-input.json `
  --output C:\evidence\momentum-exit-study-report.json
```

The input is a UTF-8 `momentum_exit_study_input_v1` JSON object containing a
study identifier, a 1–300 second maximum quote gap, bounded entries and their
quotes.  Each entry provides `entry_id`, `source_ref` (a `sha256:` archive
fingerprint), `ticker`, timezone-aware `entry_at`, `entry_price`,
`stop_loss_initial`, `target_1`, `shares`, and optional entry ATR/VWAP/regime.
Each quote provides that `entry_id`, timezone-aware `observed_at`, and `ltp`.
The report carries the exact input bytes SHA-256 and an effective exit-settings
snapshot.  `--output` uses exclusive creation and refuses to replace a prior
report; without it, canonical report JSON is written to stdout.

The baseline additionally represents the existing broker SL-M as the first
observed protective-stop trigger because `evaluate_momentum_exit` deliberately
delegates that live responsibility to the broker.  This is an observed-LTP
model, not a claim of exact stop fill quality.  It requires a quote exactly at
15:15 IST and never uses a later quote to close the position.  The output says
`NOT_ASSESSED` for qualification in every case.

Validation in Dev: 13 new exit-study tests passed with warnings fatal; 109
focused momentum exit/paper/replay/shadow tests passed with one pre-existing
Starlette lifespan deprecation warning; Python compilation and `git diff
--check` passed.  The system code atlas was regenerated to 213 Python modules.
No Production file, service, broker order, Telegram message, runtime
configuration, database schema, monitor schedule, live exit or EXEC authority
changed.
