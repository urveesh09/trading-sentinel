# Disabled E03.1 paper experiment, after frozen robustness

Finalist freeze: 0c7f414. `robustness.json` is immutable. DEFENSIVE becomes the
E03.1 RESEARCH candidate; FOLLOW is rejected. No claim of large profit improvement.

Problem: some E03 losers crossed a slightly smaller loss threshold earlier;
one adverse-fill ticket gave back a 50% gain. E03.1 tightens initial stop from
40% to 35%, and before the runner stage ratchets a trigger floor to 1.1x entry
after the peak bid reaches 1.5x. Existing 60%-of-peak stop can only rise.
Everything else, including E03's entry, split runner and limits, stays E03's.

Evidence: continuous 25,000 cash gives ordinary +12,426.71 vs +11,956.35,
adverse +11,497.60 vs +11,114.83. Ordinary incremental gain spans six sessions;
ex-largest incremental day +288.71. Worst ordinary day -478.01 vs -568.26.
The extra is SMALL. Severe execution LOSES 3,234.08 (E03 loses 3,153.55 on this
continuous basis). One-minute extra entry delay worsens relative 2024 results;
only 8/16 coarse neighbours pass the strict improvement screen. Both years seen.
No financial qualification; selected-data bootstrap is not proof after search.

Files/contracts:
- expiry_e02.py: Variant gains optional initial_stop/lock_arm/lock_floor;
  E02/E03 retain defaults. New E031 version/play/path/three-lot/four-strike arm.
  Save full policy on each new position; do not change exits of saved positions.
  Update the floor before ordinary native stop management; runner branch unchanged.
- config.py: EXPIRY_E031_SHADOW_ENABLED false by default.
- scheduler_setup.py: third isolated shadow, same existing archive, no API calls.
  Existing held_contracts enumerates VARIANTS; no new primary batch logic needed.
- tests/test_expiry_e031.py and research native_parity.py: boundary, no-lowering,
  gap, one-lot/multi-lot, disabled/open, restart, funding/path/flag isolation.
- docs guide/plan/checklist, code atlas, plain report and evidence receipts.

Acceptance: old E02/E03 tests unchanged; research baseline remains exact;
all candidate positions replay through shipped native action with event/clock,
price/quantity/fee equality; financial/reserve/causal audit; full engine tests.
Test results establish mechanics only. Record all limits and actual exits.

Rollout: new separate `<DB_PATH>.expiry-e031.db` created only by later enable or
tests. No `.env`, existing schema, broker, ledger, cash reset or migration change.
Keep flag OFF, no deployment. Rollback flag off (open positions still managed),
or revert after exposure closes. New paired forward tickets, execution evidence
and a separately authorized GitHub promotion are required. Keep 2023 protected.
