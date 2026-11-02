# E01.1: frozen plan

November 2, 2026. Written after the eight archived sessions were studied and before any September ticket's later price was read. Dev only, same branch. Production, real money and the main book don't change.

## Problem

The owner asked for E01 improved on 12 sessions: the eight archived October sessions plus four September expiries of ten-second data. "Earn more or lose less." Genome search and iteration allowed. Don't adapt the strategy to minute data.

## What the data allows

- **Eight October sessions:** real five-level depth, clocks, index and future. Full book replay. All seen.
- **Four September sessions:** one fixed strike, call and put, ten-second OHLC, ending 15:29:50. Never scored. `preflight-sept.json`, which reports no outcome: none of the 11 breaks has a ticket C could buy, because by the afternoon the fixed strike is in the money or above C's band. A and B can't run. So **September can't replay E01**.
- **What September can do:** own a ticket and compare what different exits do after it. `panel.py` has the rules. The admission rule was changed once after counting tickets, because the first version found none. That choice saw entry times and entry prices, and no later price.
- **Before this freeze I had read:** the implied forward at nine clock times on each September day, and the 1-minute index only as a check on the proxy. No option outcome.

## What the search found on the seen sessions

- **Free genome search doesn't choose well.** Rerun with each session hidden, it earns -2,564 on the hidden days against E01's +6,394. It loses less on the losing days, but it can't learn about Oct 13 when Oct 13 is hidden. Its full-sample winners earn about Rs 18,000-21,000 on five or fewer tickets. Not usable.
- **One bug, kept on record.** The first genome ran with no premium stop, because the engine reads a new position's first stop by play name and the candidate's name was unknown. `_local/ga-no-stop-bug/` keeps that run. `parity.py` now checks a renamed play and `test_e011.py` pins it.
- **A and B were tried and left alone.** No change to them beat the native rule on these days without leaning on one session or breaking under adverse quotes.
- **Rejected, each with its table in `one_gene.py` or `second_look.py`:** re-entry after a stop (-1,289, four days worse), proof before buying and scaling in (Oct 13 falls off a cliff under adverse quotes or a small stop change), a 15% stop (Oct 13 stopped under adverse quotes), the ticket's own and the straddle's ratio over ten minutes (results swing between neighbours).

## Hypotheses

The ticket keeps C's exact entry, size, failed-break exit and deadlines. Only what happens after purchase changes.

1. **Stop 25%, not 30%.** Five of the seven tickets stop out on these days, each losing less. 20% earns more here and 15% breaks, so 25% is taken from inside the range, not from its edge. E01's 30% came from A, not from the ticket's own path.
2. **Sell only what takes the ticket's cost back, at 3x.** C's bank sells half whatever the ticket cost. A ticket worth 3x needs about a third of its lots sold to return its cost, so the rest can run for free. Reserves the order fee on every remaining lot.
3. **A 60% floor from 3x.** C's own 60% trail starts at 5x, so a ticket can reach 4x and still fall to a stop below cost. Starting that trail where the bank fires closes the gap without a new number. It doesn't change any seen result, so it has no evidence here. It's insurance.

Two primaries, which differ on hypothesis 2:

| Arm | Stop | At 3x | From 3x |
|---|---:|---|---|
| **E011** | 25% | sell just enough to recover cost | 60% floor |
| **E011R** | 25% | sell nothing, the whole ticket runs | 60% floor |

E011R's lead rests entirely on Oct 13. On a ticket that reaches 3x and collapses, E011 should earn more.

**Not carried, reported apart:** skipping wide boxes and buying cheaper tickets. They change which ticket is bought, and September can't test that. Native entry stays an exact copy of C.

## Frozen tests

Neighbours judge a primary and never replace it. All on A + B + the arm's ticket for the eight sessions, and the arm's ticket alone for September.

**T1. E01's own routes on the eight sessions.** The profit route from `score_e01.py`, unchanged: higher net, worst session no worse, drawdown no worse, net without the best session no worse, each index no worse, nothing unresolved. Ordinary and adverse, all eight and the seven with raw clocks.

**T2. Neighbours.** Stop 20% and 30%, floor keeping 50%. Each must also have net and worst session no worse than E01, ordinary.

**T3. Late entry.** Every ticket entered 10, 20 and 30 seconds late, all arms alike. The primary's ticket net must beat E01's at each delay.

**T4. Every break as a ticket, seen sessions.** Each break on each session is its own ticket with real depth, far more paths than the book's seven. The primary's total must be no worse than E01's, ordinary and adverse.

**T5. September, once.** `panel.py`'s tickets, ordinary and adverse. Each primary's total must be no worse than E01's in both, and its worst ticket no worse than E01's on ordinary quotes. Any ticket E01 closes at Rs 1,000 or more that the primary closes at a loss is reported by name.

**Decision.**
- A primary that passes T1-T5 becomes E01.1.
- If both pass, E011 is E01.1 unless E011R is at least as good as E011 on T4 and T5 in both scenarios. A single winner on Oct 13 is not enough.
- If neither passes, E01 stands. Whatever is tried next treats September as seen.

## Limits, stated before the result

September's panel is a few call tickets on two days. It tests the exit rule in the only way those files allow, and can't prove the book would make money. All eight October sessions are seen, one of them carries most of the money, and no test here is untouched by the people choosing the rules. The next real exam is the full-year data, frozen before it arrives. E01.1 stays a paper shadow beside C and CE01. No real order, no main-book change, no promotion without the owner.

## Rollout and rollback

If accepted: `CE011`, a separately versioned paper shadow copying C's saved entry exactly, in `python-engine/expiry_paper.py`, with a flag that blocks new copies and keeps managing open legs. Native parity against this lab on all eight sessions, ordinary and adverse. Off: the flag and an engine restart. Pushed on `codex/production-correction-hedge-p0`. Not merged, not deployed.
