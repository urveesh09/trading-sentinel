# E03.2 refusal evidence plan

A no-trade summary cannot tell whether a setup was absent or the entry was blocked. Add bounded per-session counts in the existing E03.2 state JSON, separated into signal checks, contract checks and pending-entry checks. Existing state loads with empty counts and a new session clears them. Keep fills, policy, alerts, scheduler and E02/E03/E03.1 outputs identical. Add no table or configuration. Counts are informational and have no authority over admission. Surface the compact funnel in the existing expiry summary when there is no ticket. Verify native strategy tests, state restoration and causal replay against November 5. Roll back by reverting the Dev code through GitHub. The extra JSON fields are safe for the previous reader.
## Dated contract identity correction

The causal replay hit a real Contract instance and raised AttributeError before option selection. The deployed selector and pending fill read .underlying, while FnoInstruments maps the dataclass .name. Use .name at both boundaries. Replace the four synthetic contract fixtures with the real dataclass. Expiry and lot-size checks stay intact. Existing paper state and risk configuration need no migration. Roll back through the normal GitHub path. The old paper shadow had no eligible setup on November 5 if the corrected parity replay establishes zero signals.
## Verification

Six expiry test files passed with 111 tests. The atlas regenerated with 304 Python modules. The corrected sampled replay used all 966 November 5 packets and reconciled the zero-ticket E03.2 state and legacy A's ₹1,962.21 close. This code is local to Dev. The qualification criteria and book settings are unchanged.
