# O29d SENSEX check: the four-strategy book on SENSEX (Oct 28, 2026)

## Question

The owner asked on the evening of Oct 28: "why are you just sticking on nifty? ... You can apply it anywhere you want okay so you just have to ensure that the strategy is flexible and smart that the losses are less and the profits are consistent."

O29c made the engine's `UNION_DRIVE` book (`python-engine/fno_book.py`) the paper book's NIFTY strategy. Every study that chose its strategies and its opening-drive filter used NIFTY data only. Each SENSEX session in the archive is therefore data the book was never fitted to.

## Method (`check.py`, frozen in `freeze.json`, commit abfc27a, before scoring)

- **The book:** the engine's book, unchanged, run through the shipped single-leg book (`fno_policy_replay`).
- **Data:** every archived SENSEX session from Sep 10 to Oct 28 (31 sessions):
  - SENSEX quote batches and SENSEX's own option-expiry calendar;
  - SENSEX front-future bars for every price rule. Wherever a strategy reads volume (RVOL, VWAP), it reads the NIFTY front future's volume for the same bar, as the shipped SENSEX signal already does;
  - BSE charges.
- **Opening drive:** from SENSEX's own bars; its threshold is the median of SENSEX's own previous 20 sessions.
- **Arms:** `SHIPPED` (today's SENSEX strategy), `UNION_DRIVE` (the candidate) and `UNION` (the four always on, for context). Each arm is a separate SENSEX-only book.
- **Rule:** SENSEX switches to `UNION_DRIVE` only if all three hold:
  1. it beats the shipped break's net;
  2. its net without its best day is above 0;
  3. its worst day is no worse than −₹5,000.

## Result (`results.json`)

| Arm | Trades | Net | Net without best day | Worst day | Max drawdown | Green / red days |
|---|---|---|---|---|---|---|
| SHIPPED | 10 | −₹8,622 | −₹9,290 | −₹2,545 | ₹9,027 | 2 / 7 |
| **UNION_DRIVE** | 30 | **+₹12,759** | +₹2,639 | **−₹5,317** (Oct 28) | ₹8,595 | 7 / 7 |
| UNION | 48 | +₹11,487 | +₹1,367 | −₹6,682 | ₹12,644 | 10 / 11 |

**Verdict: the switch is not made.** UNION_DRIVE passed checks 1 and 2 but failed check 3, the worst-day bound, by ₹317.
- **The failing day:** on Oct 28, SENSEX's opening drive was HIGH, while NIFTY's was LOW. The book took the 09:45 efficiency-break call (−₹2,772) and the shipped 10:15 put (−₹2,545).
- **Consistency:** without its best day, the book made only +₹2,639 over 31 sessions. That is not yet the "consistent" profit the owner asked for.
- **SENSEX keeps the shipped break.** Nothing was tuned on these sessions.

## Limits

- **Pool and direction rule not modelled:** the live SENSEX book shares the paper pool with NIFTY and refuses a SENSEX entry in the direction NIFTY already holds. Neither is replayed here.
- **Partial match with live:** the replayed shipped arm matches the live SENSEX paper trades only partly. Live SENSEX traded 6 times from Oct 13 for −₹3,543; the replay has 10 trades. The Oct 28 72800PE matches: −₹2,529 live against −₹2,545 replayed.
- **Unpriced exits:** 11 exit checks found no archived quote for a held contract. Those exits waited for the next priced quote.
