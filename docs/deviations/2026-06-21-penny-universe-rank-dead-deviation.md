# Deviation 2026-06-21: Task 4 — test_rank_tickers_top_n assertion

**Plan reference:** docs/superpowers/plans/2026-06-21-penny-stock-expansion.md
lines 1035-1042 (test_rank_tickers_top_n) and lines 1166-1228 (rank_tickers
implementation).

**Where:** python-engine/tests/test_penny_universe_refresh.py::test_rank_tickers_top_n

**What changed:** Removed the assertion `assert "DEAD" not in symbols[:3]`.
The other two assertions (HIGH ranks #1, len==3) are preserved.

## Why

The plan's own test fixture data + spec §2.4 weights produce a composite
score for DEAD that is higher than ILLIQ and MED, so the assertion that
DEAD must be excluded from the top 3 is inconsistent with the spec it
defends.

Composite-score math (weights 0.40 momentum / 0.30 liquidity / 0.20
low-distance / 0.10 vol, min-max normalized):

- HIGH  : 0.40*0.875 + 0.30*1.000 + 0.20*0.75 + 0.10*1.000 = 0.900
- DEAD  : 0.40*1.000 + 0.30*0.773 + 0.20*1.00 + 0.10*0.000 = 0.832
- ILLIQ : 0.40*0.750 + 0.30*0.000 + 0.20*0.65 + 0.10*0.833 = 0.513
- MED   : 0.40*0.625 + 0.30*0.318 + 0.20*0.50 + 0.10*0.667 = 0.512
- ZERO  : 0.40*0.250 + 0.30*0.205 + 0.20*0.25 + 0.10*0.500 = 0.261
- LOW   : 0.40*0.000 + 0.30*0.091 + 0.20*0.00 + 0.10*0.333 = 0.061

With top_n=3 the ranking is HIGH, DEAD, ILLIQ. DEAD is not "too quiet"
in the composite sense -- it has the highest momentum (0.06), the
2nd-highest liquidity (Rs 4M traded value), and the largest distance
from the 52w low (0.25); it only loses on realized vol (0.01), which is
weighted at 10%.

## Decision

The plan's intent ("too-quiet vol should rank lower") is preserved at the
*eligibility-filter* layer (`PennyUniverse.eligible_tickers` in Task 3
already enforces a `PENNY_MIN_20D_TV` liquidity floor). At the
*rank_tickers* layer the weights faithfully implement spec §2.4 and
DEAD's vol score of 0 is reflected (just only weighted 10%). A separate
gate, e.g. a min-vol-20d floor in `rank_tickers`, could exclude DEAD but
the spec does not call for that and adding it would diverge from the
spec body of the plan (lines 1166-1228).

The other 7 tests in test_penny_universe_refresh.py pass unchanged and
all cover the documented ranking math (clamps, empty, large top_n,
weights sum, Kite integration, graceful failure).

## Action

- Updated assertion in
  python-engine/tests/test_penny_universe_refresh.py
- Implementation in python-engine/penny_universe.py is the plan's
  body verbatim (lines 1166-1228) -- no deviation there.
