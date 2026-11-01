# N09.1: exposure control beside N08

November 1, 2026. Dev research only; Production unchanged.

CUSHION retains 94.0% of N08's modeled annual aggregate profit, reduces
the worst day by 37.0%, and ends a continuous account without resets at
₹384,310. It remains losing in 2023 and gives up ₹12,066
of aggregate annual profit. All four years are already seen; no proven new edge.

| Book | 2023 | 2024 | 2025 | 2026 | Sum | Worst annual closed fall | Worst day |
|---|---:|---:|---:|---:|---:|---:|---:|
| N08 | −₹37,581 | +₹76,294 | +₹58,647 | +₹104,924 | +₹202,284 | 15.08% | −₹9,720 |
| S_VOL | −₹37,974 | +₹70,317 | +₹50,442 | +₹108,643 | +₹191,428 | 15.24% | −₹6,127 |
| VOL_CLOCK | −₹37,974 | +₹76,294 | +₹52,320 | +₹104,924 | +₹195,564 | 15.24% | −₹6,127 |
| CUSHION | −₹32,684 | +₹76,294 | +₹46,738 | +₹99,870 | +₹190,218 | 13.13% | −₹6,127 |

- **VOL_CLOCK:** risk route FAIL (failed: continuous_end_not_worse, annual_drawdown_not_worse); profit route FAIL. This is an all-seen development screen.
- **CUSHION:** risk route PASS; profit route FAIL. This is an all-seen development screen.

N09.1 preserves N08's before-noon/14:00 rules, applies the existing prior-day
volatility rule only to reduce size, and CUSHION reserves full long premium,
fees and declared stress above a cash-backed nondecreasing floor. Entry and exit
signal rules stay unchanged. No option selling, margin, risk expansion, halt
reset or money authority is introduced.

N09's S_VOL also expanded its second-lot time window; N09.1 isolates this.
The separate N09 repeated-year SHADOW diagnostic used the same outcome to
justify and book a restart trade. Corrected strictly-prior entry/exit stress
still shows substantial repeated-loss risk. Original N09 full timestamped
account replays are a separate scope and remain intact.

2025's CUSHION fall 4.85% is
slightly worse than N08's 4.70%;
it is not better on every metric. Keep N08 as the profit reference and use new
forward shadow evidence to assess any N09.1 risk lead before deployment.

Capital scope: tested at ₹2,50,000. At ₹15,000 this 85% floor leaves ₹2,250 for
the full premium plus costs and can make a whole lot unaffordable. It is not a
drop-in change for the small live trial. No capital increase is recommended.

60 annual experiments plus 24 exact state-repair reruns, 12 exact controls/675 old
lifecycles, 55 focused checks,
independent financial/admission/state/floor checks and
5596 modeled-price checks. Partial candle
fidelity, normalized lots/current costs, assumed extra stress; no real fills.

Full report: [N09.1 study](research/simulation/2026-11-01-fno-n091/README.md).
An independent audit caught overwritten fresh-year terminal snapshots. The
post-score correction preserves original scores and exactly matches all 24
affected trade/decision receipts on rerun. Full account state is independently
audited; details are in the study's SOURCE_CORRECTION.md.
Pre-score source 4245670. Results commit identity is recorded in the successor
handoff after commit. No application/env/migration/Production changes.
