# November 6 regular F&O observation

## Scope frozen before reading outcomes

Use the finished November 6 IST session in the existing read-only Panel D export at `20261106T103349Z`. Verify the manifest source, extraction clock and database and held-path file hashes. The same-day recorder journal can be copied after the collector stops and remains marked unsealed until a later session. Carry that status into the result. Use a separate read-only scoped Production query to verify the exported paper positions' count, identities and settlement state. Compare the deployed source identity with the Dev functions used for parity.

Report observed N11T directional and defined-risk paper cash separately. Independently replay directional exits where the exact held marks and position records permit, including each strategy's EFF clock and native segment fees. If a directional parent exists, apply the already frozen N012-A `Trend` and `trend_params` to the same observed entry and management looks. Give A independent trail and lock state, apply the native hard flat, and use each dated lot and segment. Require native exit parity before attributing a challenger result. If A still holds at the end of the native path, flag unresolved and report which continuation evidence is missing. A minute proxy or the native exit price cannot settle A. If there are no eligible positions, report zero observed opportunities and no efficacy measurement. Preserve all gaps.

This is one post-freeze market day and a fixed-entry diagnostic. Report eligibility and execution coverage separately from simulated prices. No new candidate selection, trade, order, deployment or changes to the sealed January–May 2022 exam. Keep the ₹250,000 paper scope separate from the ₹15,000 trial. Verification includes repeating the analysis against the same file hashes and documenting its input limits. Rollback is to retire the observation.

## Result from finished Production records

| Paper book | Trades | Observed net |
|---|---:|---:|
| N11T directional, NIFTY and SENSEX | 0 | ₹0.00 |
| Defined-risk NIFTY debit spread | 1 | ₹5,252.77 |
| Combined observed regular F&O | 1 | ₹5,252.77 |

The deployed N11 book had tolerance enabled and a ₹250,000 allocation. It recorded 60 rejected five-minute evaluations per venue. Of 120 evaluations, 115 found no fresh break, three rejected a stretched move and two were still inside the opening-range window. No directional signal reached paper admission and no directional exposure carried in from the prior session. The frozen N012-A only changes exits and therefore had zero eligible comparisons on this day.

The NIFTY spread bought the 24,650 call and sold the 24,750 call in three lots of 65. It opened at 09:51:06 IST and closed at its target at 14:52:36 IST. Production reserved ₹8,709.23, or 3.48% of the initial allocation. The reserve matches ₹8,492.25 maximum loss plus ₹216.98 estimated fees. The settled paper gross of ₹5,469.75 minus ₹216.98 fees matches both the position and the cash ledger. The mid-mark result was ₹5,340.52 net, ₹87.75 above settled paper cash. The spread attribution uses recorded paper settlement. Exact held leg quotes were unavailable for an independent spread exit replay. The cash record gives one verified spread reserve and settlement interval for the shared control.

## Verification

The Panel D export completed at 16:04:32 IST. Its database and quote journal passed the exported SHA-256 checks. The November 6 journal was still unsealed. The separate read-only Production query matched all scoped positions and signal counts. The Production exporter predates the spread ledger export and dedicated spread recorder, so the audit took the settlement and reserve directly from the read-only live database. The first checks exposed the absent recorder setting and absent archive ledger table. The audit records both limits explicitly.

Production reported release `398d44ad` and all five runtime module hashes matched that Git revision. The Dev N11, exit and fee source hashes matched Production. Dev's book and orchestrator had newer code. The two N012-A exit sources matched freeze `2758869`. No challenger outcome was inferred from a quote proxy. The sealed January–May 2022 inputs stayed unopened.

Reproduce with `nov6_observation.py --runtime` in the Production engine container via stdin under the read-only query, then run `python nov6_observation.py --export <panel-d-export> --production-evidence <local-runtime-json>` in Dev. The [machine-readable report](nov6-observation.json) reproduced byte for byte. The 34 focused research and native entry checks passed and the regenerated atlas remains at 304 modules. This Dev commit has no configuration, migration or rollout effect.
