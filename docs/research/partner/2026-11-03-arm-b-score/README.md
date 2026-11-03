# Arm B (profit protection) scored on the partner's recorded trades, Oct 27 to Nov 2

Research only. No message was switched on.

**Rule (frozen Oct 24, O24, before these days).** Once the best bid reaches P + max(W, P − S), the stop moves
to the buy price P (break-even). After that it trails at best − W.
- P is the plan's buy price, S the plan stop and W the normal 5-minute swing.

**Scoring.** The rule is treated as a message: the partner keeps their own exits. When B's stop is hit before
their first sale, they sell everything one reaction time later, at that look's bid. A trip without a plan
stop or swing, or with a sale before B fired, keeps its actual result.

**Data.** The Production partner tables in `docs/audit-evidence/2026-11-02-partner/partner-evidence.json`:
- 166 closed trips (Oct 26 is not stored as trips);
- looks every 15 s while held;
- fills from `partner_orders`.

Charges use the trip's own order count.

| Reaction | Fired | Better | Worse | Actual ₹ | With B ₹ | Change ₹ |
| --- | --- | --- | --- | --- | --- | --- |
| 0 s | 11 | 8 | 3 | −34,484 | −26,418 | +8,065 |
| 20 s | 8 | 5 | 3 | −34,484 | −29,021 | +5,463 |
| 60 s | 8 | 5 | 3 | −34,484 | −30,618 | +3,866 |

By day, at 20 s: Oct 27 +2,825, Oct 28 +5,052, Oct 29 −514, Oct 30 0, Nov 2 −1,901.

**Reading.**
- B fires on about 5% of trips, so it is too rare to judge. The frozen evaluation (`partner_watch_score`)
  needs 20 or more warned trades, and B has 8.
- The result is positive overall but negative on two of the five days.
- On Nov 2 it would not have helped the 10:36 SENSEX 75800 CE trade. Arming needed a bid of 388.4
  (329.30 + 59.10); the best was 346.
- Not enabled. Not tuned on these days: a looser arm, such as P + W, is a new rule. It has to be frozen
  first and scored on later days.

Files: `score_b.py` (reaction in seconds, `--detail` lists each fired trip), `results.txt`.
