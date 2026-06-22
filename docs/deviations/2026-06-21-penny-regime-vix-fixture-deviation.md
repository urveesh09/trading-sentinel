# Deviation 2026-06-21: Task 5 — VIX proxy test fixture + constant-series handling

**Plan reference:** docs/superpowers/plans/2026-06-21-penny-stock-expansion.md
lines 1455-1461 (test_vix_proxy_high_when_close_below_ema) and lines
1654-1684 (compute_vix_proxy body code).

**Where:** python-engine/tests/test_penny_regime.py::test_vix_proxy_high_when_close_below_ema
and python-engine/penny_regime.py::compute_vol_rank (constant-series branch).

## Two distinct changes

### Change 1: compute_vol_rank constant-series returns 0.5

The plan's body code for `compute_vol_rank` returns `sd / 0.10` for any
input, including a constant series where `sd = 0` -> return 0.0.

The plan's docstring (lines 1632-1637) explicitly says: "Short /
constant series return 0.5 (degenerate)."

The plan's test (lines 1421-1427) asserts:
  `assert abs(rank - 0.5) < 1e-6`

Body and test contradict each other. The docstring + test are
internally consistent and reflect the correct spec intent ("zero
realized vol is degenerate -> neutral 0.5"). Fix: added a constant-
series guard before the log-return loop that returns 0.5.

```python
if len(set(closes)) <= 1:
    return 0.5
```

### Change 2: test_vix_proxy_high_when_close_below_ema fixture

The plan's test fixture is `closes = [110.0] * 50 + [100.0] * 50` with
the assertion `proxy > 0.5`. The plan's comment claims "EMA near 105"
but the actual math:

- alpha = 2/(50+1) = 0.039216
- seed SMA = 110
- after 50 iterations of c=100:
  ema = 110 * (1 - alpha)^50 + 100 * (1 - (1 - alpha)^50)
      = 110 * 0.1351 + 100 * 0.8649
      = 14.86 + 86.49
      = 101.35
- dist = (100 - 101.35) / 101.35 = -0.01332
- proxy = 1.0 - (dist + 0.10) / 0.15
       = 1.0 - 0.08668 / 0.15
       = 1.0 - 0.5779
       = 0.4221  (FAIL: < 0.5)

Wilder EMA(50) decays from 110 to ~101.35 after 50 steps of 100, not
the "near 105" the plan comment claimed. With dist=-1.3%, the
[-10%, +5%] -> [1, 0] linear map produces 0.42, not > 0.5.

To produce proxy > 0.5 with the same Wilder EMA(50) body code, the
seed must be larger so the EMA after decay lands above 102.56 (the
threshold for dist < -2.5%). Bumping the seed from 110 to 120:

- ema = 120 * 0.1351 + 100 * 0.8649 = 16.21 + 86.49 = 102.70
- dist = (100 - 102.70) / 102.70 = -0.02633
- proxy = 1.0 - 0.07367 / 0.15 = 0.5089  (PASS: > 0.5)

Change: test fixture updated to `[120.0] * 50 + [100.0] * 50`. The
implementation body code (lines 1654-1684) is unchanged.

## Decision

Both fixes preserve the plan's intended invariants:

- Change 1 aligns the body code with the plan's docstring + test
  intent ("constant series = degenerate = 0.5").
- Change 2 keeps the test's invariant "close below EMA -> elevated
  proxy above neutral" with a fixture that the plan's body code can
  actually produce. The plan's claim of "EMA near 105" was a math
  mistake (the EMA lands at 101.35 for that fixture); the corrected
  fixture [120]*50 + [100]*50 makes the test meaningful.

## Action

- python-engine/penny_regime.py: added constant-series guard in
  compute_vol_rank (3-line change, docstring-aligned).
- python-engine/tests/test_penny_regime.py::test_vix_proxy_high_when_close_below_ema:
  fixture changed to [120]*50 + [100]*50; implementation unchanged.
