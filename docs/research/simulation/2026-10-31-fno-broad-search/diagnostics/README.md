# Descriptive loss attribution and verification

`diagnose_failures.py run` uses O30F_YEAR=2024 OR O30C_YEAR=2025/2026, then
`diagnose_failures.py report` combines the saved inputs. It reconstructs all222
raw-main/TPB control entries using only closed signal bars and earlier daily
history. Future minute/daily prices are mutated at every entry and must leave
features unchanged. Direction/member/feature partitions reconcile exactly to
their control totals. These are descriptive slices, not executable routers,
fresh tests, risk-path backtests or additional candidate selections.

Member, side, exit reason, prior daily DMI/EMA alignment, prior ADX/volatility,
opening range/daily ATR, VWAP location, relative volume, six-bar efficiency,
gap direction and clock are reported. Unknown values stay MISSING. The named
stretch buckets reflect the original main/TPB location rule, not a universal
limit for the48 new genomes. No result from these partitions changes a rule.

`verify_study.py inputs` rechecks the frozen current source/data/memo bindings
and independently reparses every archived session from raw candles against its
derived cache. `verify_study.py ledgers` rechecks source/evidence hashes, all
closed-record gross/fee/extra arithmetic, whole lots, closed-bar clocks,
session cutoffs, day caps, main/TPB parity, ordinary-day parity and reused files.
Original unresolved special-session records remain preserved and unavailable;
the corrected screen/children must resolve. It does not prove actual execution
or qualify an apparent historical edge.
