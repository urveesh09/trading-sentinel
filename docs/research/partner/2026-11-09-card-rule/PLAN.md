# N09c: does the partner's card make money? (plan, November 9, 2026)

## Problem

The owner asked whether the system can help the partner earn, not only lose less, and where the partner's suggestions come from. Production, read-only (Oct 27 – Nov 9):

- **Where suggestions come from.** All of them are in-house.
  - **Buy cards:** the shipped opening-range break (`evaluate_fno_mom`), held to the index target, the index stop or 15:15.
  - **"🤖 Sentinel bought…":** the paper N11 book (four strategies, a 75-minute time stop, profit lock and trail) and the expiry book.
- **Forward records.**
  - **Cards since Oct 1:** 18 resolved, 9 at target and 9 stopped. Winners ran far: Nov 5 NIFTY +60% at 15:12, Nov 6 SENSEX +99%. Stopped cards lost about 11–15% of the premium.
  - **N11 paper book since Oct 27:** −₹7,650, up on 2 of 8 days.
- **Partner trades.** In a live card's direction: 62 trades, 48% won. All their other trades: 271, 33% won. Against a live card: 5 trades, all lost.
  - **Card trades cut early:** on Nov 6 they bought the card's option and sold it at −11% before its stop, and the card then doubled. On Nov 3 they sold just above the stop, and the card reached its target at 13:30.

That is 18 cards in a strongly rising month: all the big winners were calls. The rule is tested on history before the partner is coached to lean on it.

## The test (frozen in `freeze.json` before any replay)

- **Rule replayed, unchanged.** The shipped break on the NIFTY front future's 5-minute bars, through the shipped single-leg replay at one lot with the book's costs and option choice.
  - The index stop.
  - A sale at the index target (zero-width trail once it is hit).
  - Otherwise, the hard flat at 15:10.
  - No time stop and no profit lock.
- **Data.** NIFTY 2024, 2025 and Jan – Oct 2026 on the Breeze 1-minute year data (the O29f / O30 datasets).
  - These years are seen for F&O rules, but the card rule was not chosen on them.
  - Jan – May 2022 stays reserved for the N012 exam and is not read.
  - SENSEX is not in the year option data.
- **Pass rule** (`lab_x.RULE`, applied by `analyze_x.py`). Per lot, the card rule must meet all of these:
  - net > 0 in each year;
  - net > 0 over the three years at +₹200 per trade;
  - net > 0 without its best day;
  - at most 1 red half-year of 6;
  - at least 40 trades a year;
  - above the median of 20 random-entry books with the same stop, target and exits, in every year.
- **Informational, decided in advance.** The card's exits against the book's own exits on the same entries. The card holding after its target with a 1.5 ATR trail. The live UNION_ADX book.

- **Replay stack:** the current engine files, hashed in `freeze.json` (the template's check against the Oct 29 O29i freeze is bypassed, so these replays are not claimed comparable with O29i's). Consistency check, informational: `INFO|live_union_adx` against the O30c case study's `BASE|UNION_ADX` per-lot nets for 2025 and 2026. A difference is reported, with the engine changes since Oct 29 as the first suspect.

## What follows

- **Pass:** build the card-led watch (N09c-W).
  - When the partner holds a card's option, the watch names it as the card's trade with its index stop. Selling before the stop gets one line saying the card is still alive.
  - A buy against a live card gets one line.
  - "One card, one trade": a re-buy after the card's stop is said once.
  - Messages only, behind a switch, never a block.
- **Fail:** the partner is not coached to lean on the card. The result is reported as it is, and the card stays as it is.
- **Either way:** nothing in the runtime, settings or orders changes on this result. The cards keep being scored forward, and profit is not promised.

## Files

`lab_x.py` (books, card exits, rule), `analyze_x.py` (the verdict), `test_lab_x.py` (books and the exit ladder: a sale at the target, no time stop or lock, the index stop kept), `freeze.json`, `results.json` after the run. Raw replays are in `_local/` (not committed).

## Verification before the freeze

- `test_lab_x.py`: 5 passed.
- The January 2026 plumbing smoke (exit reasons only, no P&L read):
  - the card made 11 trades: 3 sold at target, 6 index stops, 1 premium backstop, 1 hard flat;
  - the book's exits made 12 trades: 6 time stops and 2 profit locks among them.
