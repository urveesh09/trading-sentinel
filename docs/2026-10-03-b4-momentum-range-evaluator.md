# B4 — Momentum and Range shipped-policy replay (Dev only)

## Delivered

`momentum_replay.MomentumReplayConfig` and the Backtest Lab now default to
`MOM_BASE`, the shipped Momentum evaluator. `MOM_RECENCY_5` remains a named,
opt-in research comparison; a normal run no longer blends that experiment into
the baseline. The Momentum adapter remains `EVALUATOR`: its virtual full-T1
shadow exit is not the runtime partial-runner/trailing lifecycle, and historical
Swing-derived regime, Telegram approval, broker admission and shared capital
are not persisted.

The new `range_reversion_daily_evaluator` invokes the shipped
`range_reversion_entry` function once for each completed daily bar in an
explicit universe. It archives the exact `ENTER`/`WAIT_*` verdict and its
levels/reasons but reports no trades, P&L, allocation, fill or exit. It is not
renamed Swing evidence.

## Data/clock contract

Momentum still requires explicitly labelled 15-minute bars and strictly prior
daily history; malformed/mixed provenance fails closed. Range consumes only
validated daily bars from the frozen B1 contract. A Range decision uses the
current daily bar only after that session completed, matching the pure profile
input; it cannot prove an intraday action or recreate the proposal cutoff and
archived news/advisory context.

## Verification

- The Momentum default regression proves a baseline run contains only
  `MOM_BASE`; the two-variant comparison remains explicit in tests.
- The Range adapter test spies on `range_reversion_entry` and proves the last
  supplied bar equals the recorded completed-bar decision date.
- `python-engine/winvenv/Scripts/python.exe -m pytest python-engine/tests/test_backtest_lab.py python-engine/tests/test_momentum_replay.py python-engine/tests/test_range_reversion.py python-engine/tests/test_range_reversion_dispatcher.py python-engine/tests/test_range_reversion_profile.py -q`
  returned **70 passed**; one pre-existing httpx deprecation warning remained.

## Safety and remaining work

No broker/order path, allocation rule, runtime strategy setting, Production
file/database, migration, push or deployment changed. Neither adapter can
place orders or qualify an advisory result. B6 remains: standard reports,
comparison rules, held-out periods and uncertainty summaries. B5 remains
excluded by owner direction.
