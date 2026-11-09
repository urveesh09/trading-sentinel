# N09 coach scorecard (frozen November 9, 2026, before any forward session)

**What it judges:** whether the partner's trading habits change once the coach (N09) is live. It is not a profit claim. Ten sessions cannot show an edge, and the partner's results also depend on the market and on conversations outside the chat (the owner spoke to the partner on Nov 9).

## Definitions (`partner_habits.py`, `SPEC_ID = "n09-habits-v1"`)

Each session is read from `partner_watch_trips` (trades opened that session; options carried in are left out) and `partner_watch_messages` (LOWERED messages sent):

| Measure | Definition | Better when |
|---|---|---|
| `buys` | trades opened | (context only) |
| `early` | trades opened before 10:00 | lower |
| `quick_rebuys` | buys 0–1 whole minutes after a losing exit (`prior_exit`) | lower |
| `big_after_loss` | buys within 30 min of a losing exit worth ≥2× the trade just lost | lower |
| `quick_exit_share` | closed trades held under 2 minutes, as a share of closed trades | lower |
| `median_hold` | median minutes from first buy to close | higher |
| `lowered` | stops moved down (LOWERED messages sent) | lower |
| `result_sign` | the session's closed trades summed: +1 up, −1 down | (reported, not judged) |

`python partner_habits.py --db <cache.db> --from <first> --to <last>` prints the daily rows and their means (read-only).

## Windows

- **Baseline:** the 10 sessions Oct 27 – Nov 9, 2026 (already stored; Nov 9 read after its close).
- **Forward:** the first 10 sessions after N09 runs in Production. The dates are written here at deployment, before the first of them.

## The rule (frozen)

N09 **changed the habits** if at least 4 of the 6 judged measures (`early`, `quick_rebuys`, `big_after_loss`, `quick_exit_share`, `median_hold`, `lowered`) move at least 20% the better way, forward mean against baseline mean.

Red sessions and the day results are reported beside the habits and not judged alone. A change in habits with more red days is reported as exactly that.

## Baseline (read from Production, read-only, Nov 9 12:40 IST; Nov 9 still trading)

| Session | buys | early | quick re-buys | big after loss | quick-exit share | median hold (min) | stops lowered | day |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| Oct 27 | 24 | 5 | 7 | 1 | 0.136 | 11.1 | 10 | up |
| Oct 28 | 45 | 12 | 21 | 4 | 0.044 | 10.7 | 11 | down |
| Oct 29 | 50 | 12 | 21 | 5 | 0.100 | 7.6 | 14 | down |
| Oct 30 | 6 | 4 | 2 | 2 | 0.000 | 15.6 | 5 | down |
| Nov 2 | 44 | 6 | 13 | 4 | 0.023 | 8.6 | 19 | up |
| Nov 3 | 37 | 11 | 8 | 0 | 0.054 | 14.0 | 22 | up |
| Nov 4 | 29 | 10 | 11 | 1 | 0.172 | 8.5 | 10 | down |
| Nov 5 | 48 | 11 | 13 | 7 | 0.146 | 7.0 | 11 | up |
| Nov 6 | 39 | 13 | 17 | 2 | 0.077 | 8.9 | 10 | up |
| Nov 9 (to 12:40) | 32 | 12 | 15 | 1 | 0.226 | 6.8 | 8 | down |

The Nov 9 row is replaced by the full session after its close, before the baseline means are written. Means over the 10 rows as of 12:40: buys 35.4, early 9.6, quick re-buys 12.8, big after loss 2.7, quick-exit share 0.098, median hold 9.9 min, stops lowered 12.0, red sessions 5 of 10.

## Record behind the morning plan (same data)

10 sessions: mornings (entries before 12:00) ended down on 8; trades closed within 2 minutes won 5 of 35 (14%); trades held 15–60 minutes won 51 of 104 (49%).
