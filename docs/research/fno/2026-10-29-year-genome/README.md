# O29f: the year genome. Strategy books searched and tested on almost a year of NIFTY data

**Status: frozen before scoring; results are added below after the run.**
Research only: Production was only read, and no paper, live or proving-week rule changes.

## Why this study

Every earlier F&O study (O27 to O29e) replayed the same 29–31 sessions of Sep 10 – Oct 28, because the system's own quote archive starts on Sep 10. The owner's ICICI Direct account comes with the free Breeze API, which serves 1-minute candles of **expired** NIFTY and SENSEX options and futures. That gives NIFTY sessions from Jan 1 2026, and **Jan 1 – Sep 9 has never been used by any F&O study**.

The owner asked for two things:
- a new genome search on this year, mixing the best components of the winners, sometimes with a little randomness and sometimes without;
- the best winner, without hindering Production's RAM.

## Data: a declared candle model (`yeardata.py`)

A candle is not a quote, so the model is fixed before anything is scored:

| Part | Rule |
| --- | --- |
| Observation | one per minute, stamped at the minute's last second, priced at the minute's close. The archive also samples about once a minute (median gap 59 s). |
| Bid / ask | close ∓ half the archive's **75th-percentile** spread for that premium. The archive recorded ₹0.10 under ₹50, ₹0.30 at ₹100–150 and ₹0.80 under ₹450, on NIFTY near strikes, 09:30–15:15, Sep 10 – Oct 28. |
| No trade in a minute | the contract keeps its last price and last trade time, so the planner's 120-second quote-age gate ages it as live would. |
| Futures | the front monthly future carries the price. Its 5-minute bars come from its own 1-minute bars, including the 21 days before it became the front contract, as live reads them. |
| Regime (only a crisis blocks F&O) | the label the live engine logged for the bar (Jul 14 – Oct 28), else UNKNOWN, which leaves the gate open. A rebuild with the live RegimeEngine from daily bars called 30 of 32 Sep–Oct sessions a crisis where live logged 1, so it is kept in the manifest as a description only. |
| Lot | 65 (today's contract), so every session is sized as the book would size it now. |
| Options downloaded | the nearest weekly expiry each non-expiry day: calls from 4 strikes below the day's low to 4 above its high, puts up to 7 above (the live chain centres on the futures price, which carries basis). Expiry days have no options; the book makes no entries then. |

## The search (`lab.py`)

- **A genome is a book.** It has 1–4 members in priority order, the shape of the live UNION_DRIVE book.
  - Each member is either a named component exactly as studied (SHIPPED, OR20, EFF, TPB) or an O27f lab family (trend pullback, prior-day level, VWAP band, momentum burst) with its genes.
  - Each member has its own day gate: ALWAYS, or one O28 09:45 condition such as `open_drive:HIGH`.
  - Each member has its own exits: OWN/LIVE/LATE/LOOSE/RUN, and the VWAP-lost exit.
- **The book itself is unchanged.** Every book runs through the shipped single-leg book: planner, sizing, brakes, exit ladder, costs, buying at the ask and selling at the bid. Each book is replayed once over Jan 1 – Oct 28, and windows are slices of that one path.
- **Recombination:**
  - Children take members slot by slot from both parents, and two same-family lab members mix their genes.
  - **40% of children get no mutation at all.** The rest get gene mutations and structural changes: add, drop or reorder a member.
  - Elites carry over unchanged, and two random immigrants join each generation.
- **Walk-forward of the whole search (anchored):**

  | Fold | Train | Test |
  | --- | --- | --- |
  | F1 | Jan 1 – Mar 31 | Apr 1 – May 31 |
  | F2 | Jan 1 – May 31 | Jun 1 – Jul 31 |
  | F3 | Jan 1 – Jul 31 | Aug 1 – Sep 30 |
  | F4 | Jan 1 – Sep 30 | Oct 1 – Oct 28 |
  | FINAL | Jan 1 – Oct 28 | (forward test only) |

- **The NULL track** runs random-entry books with the same budget, gates and exits.
- **The fixed books are frozen here:** the live UNION_DRIVE, its parts, UNION and the O28 theories. They are scored on the unseen Jan 1 – Sep 9, with 20 random-entry books as the luck yardstick.
- **The frozen rule (`lab.RULE`).** The search works only if all of these hold for REAL out-of-sample (Apr 1 – Oct 28):
  - net above 0;
  - beats UNION_DRIVE on the same sessions;
  - beats NULL;
  - at least 3 of 4 folds above 0;
  - worst day at or above −₹5,000.

  The FINAL pick is a forward-test candidate only.
- **Production's RAM:** at most 4 replays run during market hours (09:00–15:45 IST), and no new replay starts while free RAM is under 2 GB (1.5 GB after hours).

## Pre-freeze checks (disclosed)

- **Archive parity is exact** for six books: each named component alone, the live UNION_DRIVE (33 trades, ₹44,169.53) and the O27f trend pullback as a lab member (14 trades, ₹17,347.49). The replay code is the same code.
- **Timing smoke on a partial Sep export:** about 0.1 s per session once the named signals are warmed. The September comparison showed the same setups on both data sets, with per-trade rupees differing by a few hundred, because a candle's close can sit up to a minute from the recorded quote. The full fidelity table (archive against candles on the same 29 sessions) is part of the run.
- `test_lab.py`: 8 passed.

## Files

- `yeardata.py` (export and the replay dataset), `lab.py` (the search), `analyze.py` (`results.json`) and `test_lab.py`.
- `freeze.json` is committed before the run.
- The data and raw replays live in the ignored `_local/`: `dataset-nifty/` is the sealed export, and `evals/` holds one JSON per replay.
- To reproduce: `python yeardata.py export`, then `lab.py run --jobs 8`, then `analyze.py`. The run refuses if any bound source, setting or dataset file changed.
