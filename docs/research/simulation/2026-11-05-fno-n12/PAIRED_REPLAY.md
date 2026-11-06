# Frozen N012-A paired directional replay

## Scope and acceptance checks

Add an offline N11T versus frozen N012-A driver around the existing two-venue control. Both arms receive the same causal market ticks and independent N11 shadow gate inputs. Each starts with its own 250,000 rupee wallet and owns its positions, cash, stops and lock timers. Call the frozen Trend and trend_params logic on each candidate parent at management time. Keep the existing entry rules, venue order, child handling and fees.

Require an explicit list of expected regular entry scan clocks and a hard-flat horizon for each session. Flag missing clocks, missing held bids or futures and management cadence gaps in either arm. A candidate still open after the native exit continues on its own exact contract. A later valid print cannot erase earlier missing evidence. Return a paired net only when both directional paths are qualified. Retain changes in directional entries and their decision reasons. Identical supplied spread cash and reserve are conditional external inputs. Independent spread decisions are outside this slice.

Verify native control parity, an actual exit divergence, effects on a later SENSEX entry, refusal to score if either arm's continuation is absent, and the arithmetic of qualified synthetic results. Use synthetic inputs only for this slice. The frozen market candidate and the sealed 2022 exam remain untouched. No runtime, configuration, migration or rollout. Rollback is to retire the offline driver.

## Verified behavior

The Dev driver calls the actual frozen rule source, verified against commit `2758869`. N11T uses the unchanged exit path. Each candidate parent owns its trend state and lock timer. The paired runner feeds both arms the same entry scans, marks and exact dated option sizes. Each wallet applies its own realised cash, correlation, re-entry and sizing gates. The independent one-lot shadow input supplies the same gate for both. A change in directional entry is retained with the venue, signal bar, reason, symbol, quantity and available cash.

In the synthetic case N11T exited a NIFTY call at 10:15:20 and accepted a same-direction SENSEX call in that tick. N012-A kept the NIFTY call until 10:15:40 and refused SENSEX through the existing correlation rule. The native branch exactly matched a standalone native replay. Synthetic net was ₹1,763.15 for N11T and ₹1,807.57 for N012-A after segment costs. The illustrative ₹44.42 difference is a check of the paired cash arithmetic.

The driver withheld both summaries when a bid went missing after the native close, even though later quotes let A exit. It also caught an omitted management tick, an omitted entry scan and a session without the hard-flat horizon. Missing held evidence records the affected venue and token. The replay uses the configured ten-second fast-management interval as a strict maximum gap while either book holds a leg. The caller must qualify the complete entry scan schedule, dated chains and market quotes before invoking it. Provided spread cash is applied identically and flagged in the result. An independent spread strategy for each arm is still needed for a full regular F&O portfolio comparison.

## Verification and limits

Run the Dev venv's pytest on `test_paired_control.py` and `test_shared_control.py`. The 27 checks passed, including five new paired tests. The wider focused set passed 164 checks. The regenerated atlas remains at 304 modules. Production was read-only at `398d44ad`. No runtime, configuration, migration, broker or rollout effect. No historical challenger outcome was scored. The frozen January–May 2022 inputs stayed sealed. The 31-session archive lacks complete shadow and held-path evidence for a historical portfolio result, and the read-only November 6 check had no eligible directional trade.
