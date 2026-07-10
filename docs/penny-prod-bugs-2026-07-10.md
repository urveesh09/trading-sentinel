# Penny module — production bug list

_Audited: 2026-07-10_
_Production checkout: `~/Desktop/trading-sentinel`, branch `evolve/smart-strategies` @ `f402413`_
_(which already merged `fix/penny-audit-phase2` = `26c9779`, so phases 1 and 2 ARE in prod)_

---

## Read this first

**Every bug below is already fixed — in the UNCOMMITTED working tree at
`~/trading-sentinel` (branch `fix/penny-audit-phase2`).**

```
$ cd ~/trading-sentinel && git status --short
 M python-engine/config.py
 M python-engine/kite_client.py
 M python-engine/main.py
 M python-engine/penny_backtest_v2.py
 M python-engine/penny_engine_breakout.py
 M python-engine/penny_scanner.py
 M python-engine/tests/test_penny_engine_breakout.py
 M python-engine/tests/test_penny_scanner.py
?? python-engine/tests/test_penny_audit_phase3_fixes.py
```

That diff (363 insertions) is the "phase 3 audit" work. It is **not
committed, not merged, and not deployed.** So the fixing job is mostly:
commit it, test it, ship it to Desktop.

Line numbers below refer to the **production** files.

Priority key: **P0** = penny cannot trade / actively harms other subsystems.
**P1** = materially wrong behaviour. **P2** = observability and resilience.

---

## BUG-1 (P0) — The MIS breakout gate is mathematically unsatisfiable

**Files:** `python-engine/penny_scanner.py:301,442` and
`python-engine/penny_engine_breakout.py:278-283`

The scanner reads the day high from the **live quote**:

```python
# penny_scanner.py:300-301
ohlc = q.get("ohlc") or {}
day_high = ohlc.get("high") or ltp
```

and passes it straight into the breakout evaluator:

```python
# penny_scanner.py:440-442
return evaluate_breakout_entry(
    ticker=ticker, cum_vol_today=cum_vol, median_vol_20d=median_vol_20d,
    breakout_bar=breakout_bar, day_high=day_high, rsi_14=rsi_14, ...
```

which gates on:

```python
# penny_engine_breakout.py:278-283
anchor = day_high
required = anchor * (1.0 + effective_buffer)   # buffer = 0.003
if bar_close <= required:
    return {"accept": False, "reject_reason": "breakout not confirmed ..."}
```

`ohlc.high` is the **running intraday high, which already includes the current
bar.** A bar's close can never exceed the running high that contains its own
high. So `bar_close <= day_high` holds *always*, and
`bar_close > day_high * 1.003` is unsatisfiable by arithmetic.

**The MIS leg has never accepted a single trade in its lifetime.**

Evidence, from the phase-3 audit of `/data/penny_signals.csv`:
- 215,814 lifetime evaluations
- 0 accepts
- max observed `close / anchor` = **1.0002**, against a required **1.003**

This is the answer to "is penny dead because of the market or because of a
bug?" It is the bug. The market is not involved.

**Fix (already written):** anchor on the high of the bars *strictly before*
the breakout bar. A close **can** exceed the max high of the prior bars —
that is precisely what a breakout is.

```python
prior_bars_high = float(intraday["high"].iloc[:-1].max())
```

Plus a guard returning `reject_reason="no prior bars to anchor breakout"` when
`len(intraday) < 2`.

> Note: `PENNY_BREAKOUT_USE_VWAP=True` would have masked this by swapping the
> anchor to VWAP. It defaults to `False` (`config.py:245`), so the escape
> hatch was never taken.

---

## BUG-2 (P0) — Penny starves the momentum and swing screeners

**File:** `python-engine/penny_scanner.py:294`

Each ticker fetches its own quote inside the evaluation loop:

```python
q = await self._get_quote_safe(token)   # one HTTP call, per ticker
```

With a ~100-ticker universe that is **~100 HTTP requests per 30-second scan**,
against a **global 3 req/s rate limiter** (`kite_client.py:16`) that penny
*shares with the momentum and swing screeners*.

100 requests at 3/s is ~33s of pure rate-limit wait. Penny overruns its own
30s cadence, and the limiter queue it leaves behind delays every other
subsystem's quote call.

**This is very likely why momentum "also isn't working these days."** It is
not a momentum bug. Penny is eating the rate limiter.

**Fix (already written):** batch-prefetch the whole surviving universe in
**one** `/quote` call (Kite allows up to 500 instruments per request), pass
the resulting `quote_map` down into `_evaluate_ticker_breakout`, and keep the
per-ticker path as a fallback when the batch fails.

```
100 requests / 30s  ->  1 request / 30s
```

**Fix BUG-1 and BUG-2 together.** Fixing BUG-1 alone makes penny start
accepting trades, which makes it scan harder, which makes BUG-2's starvation
of momentum *worse*.

---

## BUG-3 (P1) — The volume gate demands ~9x normal pace

**File:** `python-engine/penny_engine_breakout.py:257`

```python
if median_vol_20d <= 0 or cum_vol_today < settings.PENNY_BREAKOUT_VOL_MULT * median_vol_20d:
```

`cum_vol_today` is a **running cumulative** figure. `median_vol_20d` is a
**full-day** figure. They are compared raw.

The breakout entry window opens at 10:30 IST (`PENNY_BREAKOUT_TIME_START`), by
which point only ~20% of the 09:15-15:30 session has elapsed. Demanding
`1.8x` the *full-day* median at that moment is demanding roughly **9x normal
volume pace.**

Phase-3 audit: **37,521 lifetime rejects** on this gate.

Note this gate sits *before* BUG-1's gate, so it was independently starving
the leg even in a world where the anchor was correct.

**Fix (already written):** scale the baseline by the fraction of the session
elapsed, turning the gate into a true relative-volume check — *"is today's
volume running 1.8x its normal pace for this time of day?"*

```python
elapsed = min(max(mins - (9*60+15), 1.0), 375.0)   # 09:15 -> 15:30
vol_baseline = median_vol_20d * (elapsed / 375.0)
```

Behind `PENNY_BREAKOUT_RVOL_TIME_ADJUSTED`, **defaulting to True** — the
unscaled comparison is a bug, not a tuning choice.

---

## BUG-4 (P1) — The Connors CNC leg is evaluated in UTC, not IST

**File:** `python-engine/main.py:431-433`

```python
decision = await scanner._evaluate_ticker_connors(
    t["symbol"], as_of=datetime.now(timezone.utc),
    prev_close=t.get("prev_close"),
)
```

The evaluator's late-day gate does `as_of.replace(hour=9, minute=15)` and
treats the result as IST market open. Fed a **UTC** `now()`, `minutes_since_
open` comes out negative (about -5h30m).

**The late-day gate has been passing by accident, not by design**, for its
entire life. The MIS path already passes `datetime.now(IST)` — only the CNC
path is wrong, so the two legs disagree about what time it is.

**Fix (already written):** `as_of=datetime.now(IST)`.

---

## BUG-5 (P1) — No `no_access_token` guard on any penny cron

**File:** `python-engine/main.py` — the guard exists at only two sites:

```
1918:  logger.warning("screener_skipped", reason="no_access_token")           # swing
2336:  logger.warning("momentum_screener_skipped", reason="no_access_token")  # momentum
```

`run_penny_scanner_once`, `run_penny_connors_scan`, and `run_penny_edge_scan`
have **no equivalent guard.** Without a token they run their full loop and
fail deep inside on quote fetches, producing a wall of
`penny_eval_skipped reason=quote_unavailable` rather than one clear
`skip reason=no_access_token` line.

This is the ops-rule-59 four-breadcrumb tree failing at its own game: the
operator sees "engine ran, candidates=0" (row 4 — *legit empty day*) when the
truth is "engine never had a token."

**Fix (already written):** a `no_access_token` guard at the top of all three
penny cron handlers, mirroring the swing screener's.

---

## BUG-6 (P2) — CNC evaluations are never written to the signal log

**File:** `python-engine/main.py` — `grep -c "_log_cnc" main.py` returns `0`.

Only the MIS breakout leg writes rows to `/data/penny_signals.csv`. The
Connors CNC leg evaluates, decides, and leaves no trace.

Ops rule 75 makes that CSV the **authoritative ground truth** for "is penny
really doing nothing?" — with the CNC leg absent from it, any such audit is
answering the question for half the system. BUG-1's diagnosis came from that
CSV; a CNC-side BUG-1 would still be invisible today.

**Fix (already written):** an `async def _log_cnc(ticker, decision)` helper
called for every CNC evaluation, writing the same `accepted` /
`reject_reason` columns.

---

## BUG-7 (P2) — The Kite access token does not survive a restart

**File:** `python-engine/main.py` — `grep -c "restore_kite_token_if_fresh"`
returns `0`.

The token lives in memory only. Any container restart (and per the 2026-07-07
incident and the 2026-07-08 host reboot, these happen) drops it, and the
engine is blind until the operator manually re-logs-in.

Combined with BUG-5, a post-restart engine runs every penny cron tokenless and
reports clean empty days. Combined with ops rule 61 (~38-minute cold-start
instrument cache), a morning restart can silently cost the entire session.

**Fix (already written):** `_persist_kite_token()` / `restore_kite_token_if_
fresh()` writing a same-day token cache to disk, re-armed at startup, with a
masked breadcrumb on both persist and restore.

---

## BUG-8 (P2) — RSI ceiling hardcoded

**File:** `python-engine/penny_engine_breakout.py:285`

```python
if rsi_14 >= 70:
```

Not tunable without a code change.

**Fix (already written):** `settings.PENNY_BREAKOUT_RSI_MAX`, **default 70**.

Do **not** raise the default. The phase-3 `penny_backtest_v2` sweep
(2026-04-01 to 2026-07-08) found that the extra trades admitted between RSI 70
and 80 **lost ~Rs 13,500 net.** Daily-bar RSI is an imperfect proxy for 1-min
RSI, so the default stays at the proven-shipped 70 until an intraday backtest
says otherwise. The setting exists so the operator can experiment via `.env`.

---

## Structural gaps — present in BOTH dev and prod, fixed by neither

These are not in the phase-3 diff. They are the reason a 9-month bug went
undetected, and they matter more than any individual fix above.

### GAP-1 — No gate falsifiability tests

Nothing in the test suite asserts that a gate **can be passed**. Every penny
test asserts that bad input is rejected; none asserts that any input is
accepted.

The fix is ~30 lines of harness: for each gate, a `witness_input()` that
provably passes it, and a parametrised test asserting so.

```python
@pytest.mark.parametrize("gate", ALL_ENTRY_GATES)
def test_gate_is_satisfiable(gate):
    assert gate.accepts(gate.witness_input()), f"{gate.name} is unsatisfiable"
```

**BUG-1 dies instantly under this rule**, on the day it is written, because
nobody can construct a bar whose close exceeds a running high containing it.

### GAP-2 — No zero-accept alarm

215,814 evaluations and 0 accepts produced **no alert of any kind.** The
four-breadcrumb decision tree (rule 59) classified every one of those days as
row 4: *"both breadcrumbs present, candidates=0 — legit empty day."*

The fix: if `accepts == 0` across N consecutive days while `evaluations > 0`,
fire a Telegram alert carrying the top reject-reason histogram.

This would have caught BUG-1 **on day two**. It was instead found on day nine,
and only because the operator went looking.

Both gaps are specified in the F&O module
(`docs/superpowers/specs/fno-module.md` §9) and should be backported here.
Penny needs them more urgently than F&O does.

---

## Suggested fix order

1. **Commit the phase-3 working tree** at `~/trading-sentinel` — it closes
   BUG-1 through BUG-8. Run the full suite first; `tests/test_penny_audit_
   phase3_fixes.py` is untracked and must be added.
2. **Deploy to `~/Desktop/trading-sentinel`.** Per the ops skill, the live
   containers build from the Desktop checkout, so nothing reaches production
   until that merge lands there.
3. Watch `/data/penny_signals.csv` for the first non-zero `accepted` row.
   That single row is the entire acceptance test for BUG-1.
4. Confirm momentum's quote latency recovers after BUG-2 (compare
   `momentum_screener` wall-clock before and after).
5. **Then** build GAP-1 and GAP-2, before adding any new penny strategy.

A note on sequencing: BUG-1 and BUG-3 both *loosen* gates that have never
fired. Shipping them together means the MIS leg goes from 0 trades/day to an
unknown number, on real money, on day one. Consider deploying with
`PENNY_LIVE_TRADING=False` for the first week and reading the accept rate off
the CSV before arming it.
