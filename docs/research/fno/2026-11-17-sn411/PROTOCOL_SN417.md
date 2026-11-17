# SN417 blind-replay protocol: what the partner sees before entry (frozen Nov 17, 2026; not run)

**Status:** design only. It needs the owner's consent and the partner's time. It creates no signal for the partner and no order, and it never copies a trade.

**Question:** which part of the partner's decision repeats: direction, price discipline (the maximum acceptable ask), or abstention (when to sit out)?

## Material
- **Clips** end before the decision, with only what was visible then: the NIFTY index / futures path from 09:15, the option chain's bid / ask at the clip's end (from the archive or the recorder), and the clock.
- **No outcome, label, P&L, later frame or trade marker** appears in a clip.
- **Sources:**
  - **(a)** moments just before the partner's own past entries, from the frozen, de-identified extract of their round trips (time and contract only, never rupee totals);
  - **(b)** matched ordinary moments at the same clocks on other sessions, where the partner did not trade;
  - **(c)** random moments.
  - One third each, shuffled; the partner is not told which is which.
- **About 60 clips per round,** in sessions of 15 or fewer.

## What the partner records, before any later frame is shown
- BUY CE / BUY PE / PASS;
- the maximum ask they would pay;
- the invalidation (an index level or a premium);
- one line of reason.

## Scoring (after all answers are locked)
- **Execution:**
  - each BUY is executed at the next quote after a 5-second latency, at the walked ask;
  - it exits at the invalidation or after 30 minutes, at the walked bid;
  - charges plus ₹205 / ₹400 stress.
- **Controls:** random BUY / PASS at the same base rate, and a fixed-ask rule at the same clocks.
- **Measured:**
  - **Direction:** hit rate against 50%.
  - **Price discipline:** fills missed because of the stated maximum, and the net of those misses.
  - **Abstention:** net of the PASSED clips if they had been taken.
  - **Reasons:** whether the same reason recurs before similar outcomes.

## Rules
Partner data stays private: no rupee totals and no account identifiers in committed files. The partner companion remains messages-only. Results feed research hypotheses only, and nothing reaches the partner's live advice without the owner's word.
