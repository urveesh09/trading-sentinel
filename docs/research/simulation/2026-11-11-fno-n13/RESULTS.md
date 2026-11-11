# N13 results: keep the profit lock; the forward misses come from how the live book differs from its research

Frozen at `421068e4` (re-freeze of `630f7b88`; no arm was scored under the first). That makes 20 annual replays: 4 arms × 5 seen NIFTY windows, with a fresh ₹2,50,000 each window. N11T entries and costs are unchanged. In every window the centre reproduced Round 30's `TREND_ONLY` exactly (net, counts, drawdown, worst day, daily nets), and `score.py` reproduced N012-A's +₹4,051.45 and +₹710.38. Full table: `results.json`.

## Verdict (frozen five-check rule)

**N012-A stays.** The search picks N012-A in every left-out window and as the final pick, so there is nothing to adopt (`adopt: false`).

| Increment over N11T | Jun–Dec 2022 | 2023 | 2024 | 2025 | Jan–Oct 2026 | Total | Without 5 best days | Lock exits |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| **N012-A (locks as now)** | +305 | +405 | 0 | +1,937 | +1,405 | **+4,051** | +710 | 16 of 209 |
| OR20 lock off | −373 | +175 | 0 | −516 | +1,466 | +752 | −2,387 | 9 |
| Shipped-break lock off | +551 | −1,119 | 0 | +392 | +1,233 | +1,057 | −2,206 | 9 |
| No lock at all | −127 | −1,525 | 0 | −2,547 | +1,294 | **−2,904** | −5,469 | 0 |

- **With one look a minute, as researched, the lock earns its place.** Switching it off costs ₹6,955 against N012-A over five windows. It also raises the worst annual drawdown from 6.97% to 7.50%, and every window that changes gets worse (2026 only slightly).
- **2026 is the one window where every lock-off arm does about as well.** Jan–Oct 2026 was a strong trending window, where runners matter most. That fits the Nov 5 case, but it is one window, and the others outweigh it.
- **The lock is rare at this cadence: 16 exits in 209 trades (7.7%).**

## What this means for the forward misses

The Nov 3–11 shortfall against the one-lot record is not a weakness of N012-A's rules. The live main book is not quite the book that was researched.

1. **The live lock looks every 10 seconds; the research looks once a minute.** Live, the lock sold 6 of the paper book's 32 trades since Oct 1 (19%), about 2.5 times the researched rate. On Nov 5 it sold OR20 at 12:03, on a 10-second dip under a floor set by a 10-second peak. The once-a-minute record kept the same contract to 14:22, a difference of about ₹5,066. The cadence is a known open gap: SX-F1 added the 8-second confirmation, and N012-A2's RESULTS notes it. `fno_exit_cadence.py` exists to replay lock rules on the recorded 10-second looks. Its agreed rule is at least 20 scored trades, and a change to a live lock only with the owner.
   - The candidate fix is to judge the lock on one look a minute, with no confirmation, as researched, on paper N11 positions only. Stops and the trail stay on 10-second looks. On history this is the researched behaviour by construction. Forward, it should be scored as a declared `fno_exit_cadence` arm before any live change.
2. **SENSEX: 6 trades, −₹7,053, and it shares NIFTY's 3 trades a day.** It cannot be replayed (zero OI), and on Nov 11 it took the slots of a researched NIFTY trade (+₹4,577 in the record). The research-consistent book is NIFTY with its own 3 trades a day and SENSEX as a shadow. A separate allowance that never blocks NIFTY is the other option. The owner decides (O29e).

Neither fix adds a new edge. Together they make the live book the N012-A that was tested. On the Nov 3–11 forward record, the gap against the one-lot record is ₹15.9k. SENSEX (−₹7,053), the crowded-out trade (₹4,577) and the Nov 5 lock exit (₹5,066) add up to about ₹16.7k; lot sizes and the other exits make up the difference. That is ten trades, so part of it is noise.

## Not done here

- No engine, setting, schema or Production change. Both fixes need the owner's word. The lock fix also needs the cadence evaluator's ≥20-trade forward score, or the owner's explicit waiver.
- The sealed NIFTY January–May 2022 exam stays sealed.
- The forward panel's TPB-alone arm (+₹9,820 over 5 trades) is judged by its own frozen rule on Nov 27.

## Verification

- `freeze.json` source hashes were checked at every run, and so was `round1.verify_freeze()` (data manifests, N11/N11T controls). The centre equals Round 30 in all five windows. All runs finished with zero unresolved positions.
- Runtimes: 15–68 s per arm per window.
