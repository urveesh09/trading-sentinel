# SN248: the pre-registered crash test, NIFTY Jan–Sep 2020 (written Nov 15, 2026, before that data is complete)

**Do not change this sheet after any 2020 option price has been read.** Run `sn248.py --data-complete` once, after the downloading agent reports that every NIFTY 2020 target through Sep 2020 is finished. Until then the script refuses.

## Why

- NIFTY Jan–Sep 2020 holds the COVID crash: about −38% from Jan to Mar 23 2020, realised volatility above 60%, limit-down opens. No study has read its option prices.
- It is the only unseen history left on the device, and the hardest test any short-premium leg can face.

## What is scored (once; nothing re-selected)

Per option lot, weekly expiries **Jan 2 2020 – Sep 24 2020** (weeks with more than 5 sessions drop those on or before expiry − 7 days, as SN221 did). The engine is `wk4.book4`, with costs as SN221–SN247.

| Leg | Recipe |
|---|---|
| **Gold v7's leg (WK-H band 0.8)** | `("STRADDLE", "M", "settle", {"band": 0.8})` |
| Gold v6's leg (WK-H band 0.6) | `("STRADDLE", "M", "settle", {})` |
| WK-H band 0.7 (neighbour) | `{"band": 0.7}` |
| Information: band 0.8 + synthetic hedge | `{"band": 0.8, "instrument": "synth"}` |
| Information: band 0.8 + flatten at 14:30 | `{"band": 0.8, "flatten_j": 315}` |
| Reference: the same straddle unhedged | `wk3.book3(..., "STRADDLE", "M", "settle", "none")` |
| Reference: WK-S | `("STRANGLE 0.5", 3, "settle stop1", "none")` |

## Pass rule for Gold v7's leg (frozen)

- **C1:** net > 0 over Jan–Sep 2020;
- **C2:** worst month ≥ −₹34,163 per lot (the SN221 tail bar);
- **C3:** Mar 2020 alone, reported. If it is below −₹50,000 per lot, the result recommends a crash brake (a rule that stands WK-H aside when realised volatility is extreme). The brake would itself be frozen and tested only on the forward record.

**What each result means:**
- **C1 and C2 pass:** Gold v7's leg survived the worst market in the data.
- **Either fails:** the result is written down as it comes out; Gold v7 stays on paper; the owner decides.
- **No rerun, no new leg chosen on 2020 afterwards.**

Gold v5 cannot be replayed on 2020: its N11 parent book has no 2020 replay. So this tests the WK-H leg only.
