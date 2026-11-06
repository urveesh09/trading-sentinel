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

## Historical data feasibility

| Year | NIFTY archive sessions | Dated SENSEX overlap | Overlap with recorded positive intraday option OI |
|---|---:|---:|---:|
| 2025 | 248 | 80 | 1 |
| 2026 through October 28 | 203 | 131 | 0 |
| **Total** | **451** | **211** | **1** |

The two dated SENSEX snapshots have disjoint calendars. Round 9 has 896,633 option rows, with 12,884 positive OI rows all on September 23, 2025. Of those, 12,845 meet the configured 5,000-unit floor. Round 36 has 1,945,903 option rows and no positive OI. The [earlier calendar run](ROUND10.md) already showed that missing OI can force simulated entry refusals despite traded option volume. Treat those dates as unavailable for the native entry replay. Prior-session closing OI is a separate proxy and changes what the benchmark tests. One date with nonzero values also falls short of entry parity because it still needs verified observations at decision clocks and the rest of the chain inputs.

Counts come from intersecting each frozen NIFTY manifest's `sessions` with the union of the two SENSEX session lists, and querying both snapshot databases read-only. For each snapshot use `SELECT count(*), sum(oi>0), count(DISTINCT CASE WHEN oi>0 THEN substr(datetime,1,10) END) FROM candles WHERE kind='option'`. The Round 9 manifest SHA-256 is `935bfdb971d443479417020fa6d46f72b9e3b3f94f3db834b973c37c19d6ba8a`. See [Round 36](ROUND36_DATA.md) for that manifest hash. No replay or P&L was computed from these gaps.

Historical trade or order book data would need a sample with dated SENSEX series, bid and ask, last-trade time, volume and intraday OI to qualify as a source. BSE advertises historical and derivative data. Its public daily market summary describes session-level OI, and the published materials inspected here do not establish that the available historical package includes the needed intraday field. [BSE data catalogue](https://www.bseindia.com/downloads1/Information_Products_Pricing_Sheet.pdf), [BSE derivative file formats](https://www.bseindia.com/downloads1/File_Format_Equity_Derivatives.pdf).
