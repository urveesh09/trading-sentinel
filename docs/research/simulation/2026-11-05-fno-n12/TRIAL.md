# Small-wallet trial. Keep cash or cap planned loss

The ₹15,000 mirror was brittle under the same-clock adverse assumptions. Test two independent admission screens, with no change to its modeled exits or contracts.

- CASH_BUFFER rejects a ticket unless full premium at the adverse native limit plus round-trip zero-exit costs fits inside 65% of the ₹15,000 starting wallet. The aim is to preserve room after one loss rather than find a cheaper contract.
- STOP_BUDGET rejects a ticket if 1.75 times its delta-implied loss at the original directional stop, limited by a 25% premium backstop, plus fees and ₹205, exceeds ₹1,500. This is a planned-loss sensitivity and does not limit realized losses at an unfillable stop. Signed stops and valid delta are required.

All screens use entry-only inputs and the same adverse entry limit in both execution scenarios. They supplement the mirror's cash, chase, single-position, daily count and floor checks. The small wallet keeps an independent cash ledger. Evaluate at current normalized contract size. Compare net, adverse years, worst loss, drawdown, floor refusals and opportunity cost. An improvement in the 2025 result alone is insufficient. This is a conditional pilot diagnostic. A candidate with a different exit or strike needs a new causal quote lifecycle comparison.
