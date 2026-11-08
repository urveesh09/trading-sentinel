# Round 22 shared-wallet attribution

## Scope and acceptance checks

Reconcile the saved acceptance arm against the saved N11T control. Compute each session's residual as total acceptance net less the added sleeve's net and the control net. Trace the three most negative residuals from all five development windows. Preserve closed-clock accounting and the original rounded totals. Run the two unchanged frozen policies only to recover missing decision traces for the affected years. Require the original economic results and extra trades to reproduce before attributing any loss.

At each affected native signal capture the actual planner decision, held positions and sleeve, realised cash, pool, stance, selected strike, lots and native or tolerance sizing evidence. Separate a demonstrated gate from concurrent differences. If trace evidence cannot assign an effect uniquely, leave it unresolved. No new candidate, parameter change, held-out access, settings, migration or rollout. Rollback is to retire the standalone Dev attribution.

## Three largest native-book losses

| Session | N11T net | Acceptance sleeve net | Acceptance native net | Native-book change |
|---|---:|---:|---:|---:|
| June 1, 2026 | ₹22,638.94 | −₹1,523.70 | ₹0.00 | −₹22,638.94 |
| September 24, 2026 | ₹17,317.07 | ₹0.00 | ₹0.00 | −₹17,317.07 |
| February 11, 2025 | ₹27,597.54 | ₹0.00 | ₹10,295.53 | −₹17,302.01 |

These three days account for ₹57,258.02, or 50.1% of the five-window residual. Summing the stored daily cash yields a residual of −₹114,205.60. The original report's −₹114,205.58 uses the rounded annual nets. The ₹0.02 difference comes from that rounding order.

### June 1. Same-day re-entry rule

The sleeve bought one lot of the 23,650 put at 10:30:59 and stopped at 10:48:59 for −₹1,523.70. The later native short attempts had zero held positions. Both were refused by `reentry_not_confirmed`. With the stored sleeve entry future of 23,608.50, stop at 23,638.6325 and a 0.25R re-entry margin, a new short needed the future below 23,600.966875. The futures at the two matching control entries were 23,636 and 23,616. N11T bought two lots on each of those signals. Both later settled at hard flat. The acceptance book's 0.50× stance and same-day loss were also present, so the original control's full quantities cannot be inferred for a hypothetical entry with the gate lifted.

### September 24. Loss-streak pause

At 11:51:59 the acceptance book was flat and had no realised result that day. The matching native short was refused by `kill_switches_clear` because six consecutive losses triggered a pause that still covered September 24. Its latest loss was on September 23. All ten native attempts in the acceptance book carried the same pause. N11T had no active halt and its two-lot put closed for ₹17,317.07. The acceptance book also had a 0.25× drawdown stance. The first observed refusal came from the pause.

### February 11. Smaller initial position and no earned lot

Both books entered the 23,350 put at 11:30:59 for ₹153.65 and exited at 13:15:59 for ₹316.60. Both had a flat wallet at the entry and zero realised cash that day. N11T used the 1.00× base stance, bought 130 units and added 65 at 12:56:59. The acceptance book was in the 0.50× drawdown stance, bought 65 units and earned no additional lot. The smaller opening position explains ₹10,332.73 of the net gap and the absent earned lot explains ₹6,969.28. The two books' entry equity was ₹271,941.87 and ₹258,301.93 respectively. The saved trace shows how accumulated wallet state affected size on a day with no acceptance-sleeve trade.

### Prior losses and verification

Five of the six closes immediately preceding September 24's pause were sleeve losses. The sleeve's loss dates were August 28 and September 4, 11, 17 and 23. The remaining close was the September 7 native loss. The trade-level tail is in the [combined trace](round22-attribution.json). February's smaller size followed earlier account losses, including four sleeve losses in the eight completed trades immediately preceding the entry. The three cases explain half of the aggregate residual. The rest was kept at the aggregate level in this audit.

Run `round22_attribution.py --output <local-trace>` with `N12_YEAR` set separately to 2025 and 2026. The expected combine inputs are `_local/round22-attribution-2025-v2.json` and `_local/round22-attribution-2026-v2.json`. Then run `round22_attribution.py --combine --output <report>`. The scripts verified the frozen source hashes, dataset file hashes, saved acceptance daily and annual results, sleeve trade rows and original N11T economic tuples. The trace runs used separate annual processes and changed only observation. The named-signal memo miss counter was excluded from metric parity because its warm-up depends on the execution process. Repeated runs matched the original traces, and the combined report reproduced byte for byte. The 27 focused tests passed and the regenerated atlas remained at 304 modules.

Production remained at `398d44ad`. All changes are Dev research only with no runtime, configuration, migration or rollout effect. No new strategy or holdout was scored.
