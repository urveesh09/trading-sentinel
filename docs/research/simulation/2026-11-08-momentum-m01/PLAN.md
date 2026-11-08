# M01: why Momentum loses, and one sealed exam (frozen November 8, 2026)

## Question

The owner asked (Nov 8) how the Momentum module can be improved. Its Production paper book has 54 closed trades since Aug 5, net −₹3,322.
- 50 trades closed on the clock, 4 at target, none at the stop.
- Gross was about −₹500; costs took the rest.

Since Oct 7, MOM_SELECTIVE has decided the real paper entries. It was turned on unscored.

## Development window (seen): Aug 11 – Nov 6, 2026

The data is Production's `intraday_cache` (15-minute bars, 500 names, 57 sessions), exported read-only. The bars end with the 14:30 bar, so every rule here exits by the 14:30 bar's open.

The shipped entry is the exact evaluator (`engine.evaluate_momentum_signal`, pool ₹50,000, REGIME_2_ELEVATED). A cheap pre-filter checks only conditions every accepted signal must meet. Against the full evaluator on 660 ticker-days it had 0 mismatches (`parity.py`).

**Findings (`explore_exits.py`, `explore_orb.py`, `dev_results.json`):**

**The shipped entry loses before costs under every exit.** These are the base entries, 163–165 trades:

| Exit | Gross | Net |
|---|---:|---:|
| Live lifecycle | −₹4,911 | −₹13,029 |
| Hold to the deadline | −₹6,440 | |
| 1.6R target | −₹7,238 | |
| Breakeven at 1R | −₹5,843 | |
| Runner trail | −₹7,385 | |
| VWAP exit | −₹2,849 | |

So the time stops are not the fault.

**MOM_SELECTIVE barely trades.** It took 8 trades in 57 sessions: −₹188 with live exits, +₹33 with the VWAP exit.

**A stocks-in-play opening-range breakout also fails.** This is the long-only version of the strategy in Zarattini, Barbon & Aziz (2024): the top 5 by first-bar volume over 20-day ADV, a green first bar, a stop-buy at the first bar's high and the first bar's low as the stop.
- Every arm lost before costs.
- The best arm, the VWAP exit, made −₹2,531 net over 155 trades.
- A random-name control made −₹2,650.

**The backdrop.**
- The average liquid stock lost 0.19% from the open to 14:30 each day; 75% of the universe fell over the window, while NIFTY was flat.
- The drift does not persist from day to day (lag-1 autocorrelation 0.08).

**There is no intraday momentum here; there is mild reversal.** This compares the move from 10:15 to 14:30 with the day's mean:
- the first-hour top decile: −0.059%;
- the first-hour bottom decile: +0.093%.

The winners-minus-losers spread was negative on 35 of 53 days. It has no day-to-day persistence (lag-1 −0.15), so a "momentum has been working" gate cannot help.

## Exam window (sealed): Jan 1 – Jul 31, 2026

This is the Kite snapshot acquired Oct 5 for round 3 (`docs/research/kite/2026-10-05-momentum-h1/_local/raw`): 143 sessions, about 490 names plus NIFTY 50, full days. It has never scored Momentum.

The owner skipped round 3 on Oct 7 and said not to reopen it unless asked. **This exam runs only on the owner's word.**

**Frozen arms** (same code, same fills and costs, deadline at the 14:30 bar's open):
- **A0_BASE_LIVE:** shipped entries, live exit lifecycle (reference).
- **A1_SELECTIVE_LIVE:** the live rule (reference).
- **A2_SELECTIVE_VWAP:** MOM_SELECTIVE entries, exit at the next open after a close under VWAP.
- **A3_ORB_TOP5_VWAP:** stocks-in-play opening-range breakout, top 5, VWAP exit, ₹600 risk and ₹10,000 cap per trade.
- **NULL_ORB_RANDOM5_VWAP:** the same as A3 with five random liquid names (seed 1).

**Hypotheses:**
- **H1 (the module's premise):** the first-hour top decile beats the day's mean from 10:15 to 14:30.
- **H2:** the first-hour bottom decile beats the day's mean (reversal).

**Decision rule for A2 and A3:**
- at least 30 trades;
- net > 0;
- net without the best day > 0;
- net above A1;
- max drawdown ≤ max(1.5 × A1's drawdown, ₹2,500).

An arm passing all five is only "promising": it goes to paper shadow, not to real money. A0 and A1 are also checked on their own: at least 30 trades, net > 0, and net without the best day > 0.

**Limits:**
- These are per-trade sums. Overlapping trades are not limited by one ₹50,000 book, so a sum overstates what one book could hold.
- 15-minute bars cannot show the path inside a bar; the stop wins.
- Slippage is 5 bps each way.

**Reproduce:**
1. `python signals.py DEV`, then `python explore_exits.py DEV` and `python explore_orb.py`.
2. Exam, after the owner's go-ahead: `python signals.py EXAM`, then `python exam.py`. `exam.py` refuses to run if any frozen file changed.
