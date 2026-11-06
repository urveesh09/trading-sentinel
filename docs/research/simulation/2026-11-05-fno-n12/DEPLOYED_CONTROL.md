# Deployed two-index control

Use the November 3 paper reset at ₹250,000. Reconcile NIFTY and SENSEX in chronological order, using the native exchange fee schedules and each position's actual initial lots and underlying. Include recorded defined-risk settlements in the account equity at their real clocks. Keep them separate from single-leg strategy attribution. Compare the five recorded admissions with their independently stored accepted signal events and recomputed decision-time pool. Replay management from the held path at its exact clocks. In particular, recompute the native N11 EFF soft time stop on every observation and verify the recorded parameter hash. Require matching contract, lots, exit clock, exit price, reason and net within ₹1.

This step can reconcile entries as recorded evidence and independently replay the exits. A signal-from-market admission replay also needs the original evaluation phase, current option packets, dated contract master and pre-tick cash state. Keep those fidelity levels distinct. A future historical run will require two-venue management by position owner, NIFTY-first priority on matching clocks, instrument-specific deduplication and stop re-entry levels, exchange fees, and one actual risk and cash ledger. The expanded ordinary SENSEX inventory supplies partial data only. The historical control must report the dates with missing SENSEX evidence. No SENSEX sleeve or new candidate is tested here.

Read immutable export hashes and only November 3–5 records. Report unavailable clocks and identity discrepancies rather than inferring them. No runtime, settings, migration, orders, expiry or rollout changes. Rollback is to retire this audit.

## November 3–5 observed reconciliation

| Position | Venue | Strike | Contracts | Exit | Net |
|---|---|---:|---:|---|---:|
| 55 | SENSEX | 76,600 CE | 2 × 20 | Time stop | −₹481.29 |
| 56 | SENSEX | 77,000 CE | 2 × 20 | Time stop | −₹84.97 |
| 57 | NIFTY | 24,400 CE | 2 × 65 | Time stop | −₹765.59 |
| 58 | NIFTY | 24,350 CE | 1 × 65 | Profit lock | ₹1,028.70 |
| 59 | NIFTY | 24,400 CE | 1 × 65 | Trail stop | ₹4,558.07 |

Across 2,263 held observations, all five recorded exits matched on clock, reason and price with independently recomputed costs. The recomputed single-leg sum was ₹4,254.93, of which ₹4,821.18 came from November 5. Defined-risk positions settled separately for ₹690.28 and ₹2,545.91. The first settlement entered the cash pool before the November 4 admission. The second settled after the last November 5 admission. The November 5 export is unsealed. The November 3 and 4 sessions may predate the current Production revision.

The [machine-readable audit](deployed-control-nov5.json) retains the exact clocks, symbol identities and equity at entry. `python deployed_control_nov5.py <local-export>` validated the file hashes and completed with five matches. Entry evidence comes from the recorded accepted signals and position ledger. Independently reconstructing all entry decisions, and the historical two-venue one-wallet comparison, remain open. The SENSEX time stops in the earlier fixed-clock replay disagreed because the live EFF stop was recomputed as each position stalled.
