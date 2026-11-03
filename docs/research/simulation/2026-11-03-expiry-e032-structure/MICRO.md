# Quote-level exam contract: snapshot imbalance, actual spread and charges

Round three also failed: equal-budget verticals earn less and lose in 2025;
butterflies lose, with one unresolved pack. None is a replacement. Their
simultaneous-pack assumption does not establish real combination execution.

Use ONLY the two existing read-only 2026 archived databases from E03's frozen
recorded-proxy manifest, ONLY NIFTY October 6/13/19/27 and November 3. These dates
are already seen; new features do not make new days. No acquisition or protected
exam access. Source bytes hashed before any quote-return measurement.

Test whether one concrete microstructure signal survives executable spread
and fees, rather than optimize old thresholds. On sampled quotes 13:00-15:00:

- The current and previous same-symbol observations have five valid bid and
  five ask levels and native fresh timestamps; current index/future fresh too.
- Option is currently OTM within 200 points; ask 5-20; spread at most 10%.
- Total five-level bid size exceeds ask size by 2:1 (imbalance >1/3), newly
  crossed since the previous snapshot. Spot and independent future moved in
  this option's profitable direction over the last two snapshots (gaps <=15s).
- This is **displayed snapshot imbalance**, NOT order-flow imbalance. Ten-second
  snapshots cannot identify all additions/cancellations, trader identity or queue.
- Decide at snapshot k; one lot may buy at the NEXT snapshot's actual ask-depth
  walk, fresh and <=110% decision ask, <=1,250 worst-case reserve. No same-quote
  fill. Exit on first observed fresh bid-depth quote at/after +30 seconds or
  +120 seconds from entry, at most 25 seconds late. Both horizons fixed now.
  The requested horizon has no gap-free intraperiod stop claim.
- All buy/sell native NFO fees, spread and whole-lot displayed capacity apply.
  Missing/late exit is unavailable, not an invented sale or a dropped zero.
  Report full-premium-loss bound for missing exits separately.

Primary diagnostics: per-day event counts, raw midpoint return, executable
one-lot net markout after fees, positive fraction, median/mean, missing outcomes,
per-day positive/negative means, costs as fraction of premium. Control: all
eligible quotes with direction agreement but no pressure requirement, same
clocks, one-lot constraints and costs. It is an observational comparison, not
a randomized causal test. Overlapping events are not independent trades.

**EVALUATOR only**: these are conditional fixed-horizon marks, NOT a funded
portfolio, a stopped strategy, independent new forward tickets or cumulative
profit. Do not sum event marks into a strategy return. No capital/risk/brakes
change, native trading-engine change or rollout. A promising observation would
need a separately frozen continuous cash/stop lifecycle before any E03.2.
Freeze code, tests, manifest and this contract in Git before scoring.

Pre-score correction: `freeze-micro.json` was an uncommitted draft produced
after a synthetic test used an invalid negative-price depth ladder. No market
return had been scored. That test is corrected; explicit previous-underlying
freshness and each 15-second gap are enforced as intended. The retained draft
is superseded by `freeze-micro-v2.json`, committed before the first score.
