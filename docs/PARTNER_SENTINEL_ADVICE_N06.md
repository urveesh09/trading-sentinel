# N06 — The Sentinel's way of trading, as advice to the partner (2026-11-04)

Owner's order, Nov 4: the partner lost ₹51,869 in one day with the watch's messages arriving on time. Make the advice
better "so that instead of such loss-making idiotic trades, they follow the trades of the sentinel", using the
strategies built for N08–N11 and the expiry book, and "no matter what still we will not take any action on behalf
of the partner. Only advice."

Code: `python-engine/partner_sentinel.py` (new), `python-engine/partner_watch.py`, `python-engine/config.py`
(`PARTNER_SENTINEL_ADVICE_ENABLED` and [N06c] `PARTNER_WATCH_BROKEN_ENABLED`, both default true). Tests: `python-engine/tests/test_partner_sentinel.py`. Study
scripts and their read-only outputs: `docs/research/partner/2026-11-04-n06/`.

## What the stored days say (Production, read-only)

### The frozen warning score

`partner_watch_score` rule v2-a3150fcf5a68, frozen on Oct 26 before the days it decides on. 232 closed trades over
7 days, Oct 27 – Nov 4 (`score-output.txt`):

| Warning at the buy | Warned trades | Their total | Other trades | Their total | Verdict |
|---|---|---|---|---|---|
| Much bigger than the usual share of cash | 57 | −₹38,024 | 175 | −₹2,130 | SUPPORTED |
| Within 30 min of a losing exit | 143 | −₹31,721 | 89 | −₹8,433 | SUPPORTED |
| Bigger than the losing trade before it | 22 | +₹1,787 | 210 | −₹41,941 | NOT_SUPPORTED |
| After a 20% run in 15 min ("chased spike") | 96 | +₹49,703 | 132 | −₹94,312 | NOT_SUPPORTED |

The partner's usual-size trades are about even (175 trades, −₹2,130). Nearly the whole loss is the 57 oversized
buys. The chased-spike warning was wrong for this partner: their buys after a run made money.

### What-if on the same trades (`whatif.py`, `whatif-output.txt`)

The rule constants are the Sentinel's own (`FNO_MAX_RISK_PCT` = 2% of cash lost at the stop); nothing was fitted
to these days. This is in-sample arithmetic on seen days, not a forecast.

| Day | Actual | Sentinel's size (min 1 lot) | Size + plan stop | 1 lot + plan stop | Sentinel's own trades, 1 lot |
|---|---|---|---|---|---|
| Oct 27 | +31,240 | +377 | +822 | +822 | −1,214 (1) |
| Oct 28 | −40,320 | −16,218 | −14,912 | −12,339 | −2,351 (2) |
| Oct 29 | −14,554 | −13,068 | −10,590 | −9,226 | +440 (3) |
| Oct 30 | −16,578 | −5,222 | −5,325 | −4,705 | 0 (0) |
| Nov 2 | +5,728 | +233 | −824 | −824 | −4,298 (3) |
| Nov 3 | +46,199 | +29,054 | +27,575 | +27,575 | −241 (1) |
| Nov 4 | −51,869 | −7,097 | −4,940 | −5,002 | −42 (1) |
| **Total** | **−40,154** | **−11,942** | **−8,193** | **−3,700** | **−7,706 (11)** |
| Worst day | −51,869 | −16,218 | −14,912 | −12,339 | |

"Plan stop" sells at the first stored 15-second look whose bid is at or under the plan's stop, at that bid. A trade
sold below its stop between looks counts as sold at the stop.

**Reading.**
- Sizing is the lever. It turns a −₹40k week into about −₹8k to −₹12k, and the worst day from −₹52k to about −₹15k.
- It does not turn the period into a profit. Neither does following the Sentinel: its own main F&O paper trades
  lost ₹7,706 a lot on those days, over 11 trades.
- The Sentinel's edge in years of replays is small, and it loses on many days. No model here predicts minute-scale
  option moves. What it has is discipline: few trades, a fixed loss per trade, stops, and smaller size after a loss.

## What the partner now gets (N06c, Nov 4 night)

**Owner's direction:**
- "remove the quiet today button itself and the explaination thing";
- "long long paragraph with market on reading is impossible: if with concrete the explaination is consice and
  direct its good else" drop it;
- build the auditor's ideas only where they really help the partner.

**Rendered from Nov 4's real rows in Dev's code** (`normal_day.py` in the scratchpad, shown here):

```
After login
✅ Trade watch on until 15:40: stops missing, moved or not selling, refused orders, a trade under its plan stop, and each 10% of cash the day loses or gives back. Messages only: nothing is placed for you.
🔎 Before a buy, send the option, e.g. 76700 ce.
📊 Your buys since 27 Oct: usual size −₹2,130 (175) · oversized −₹38,024 (57) · within 30 min of a loss −₹31,721 (143).
🤖 The Sentinel's own trades (paper) come here as it takes them.
⏳ SENSEX expires today: its options lose time value fastest and settle at the close.

A buy (Nov 4, 10:24: 5 lots, a minute after a loss)
🟢 You bought SENSEX 76700 CE · 5 lots (100) at ₹598.75
🛑 Plan stop ₹499.9: one normal 5-minute swing (₹98.82) under your price. If it sells there: about −₹10,051 with charges, 12% of your cash.
⚠️ ₹59,875 in this trade, 74% of your cash: much bigger than your usual 31%. Since 27 Oct such buys: −₹38,024 (57); usual size −₹2,130 (175).
📏 At the plan stop: 1 lot −₹2,048 (2.5%) · 2 lots −₹4,049 (5.0%). The Sentinel risks at most 2% (₹1,609).
🎯 Target zone ₹784.95 (SENSEX future 77,439).
⚠️ Your last trade closed −₹2,957 at 10:23, 1 min before this buy. Since 27 Oct such buys: −₹31,721 (143). The Sentinel takes 1 lot after a loss.
Trade 13 today · ₹1,808 in charges so far.
Place an SL sell now: trigger ₹499.9, limit a little under it; the price was ₹597 at 10:24:40.

The price goes under the plan stop (no stop of their own at or over it)
⛔ SENSEX 76700 CE (100) is under its plan stop ₹499.9: ₹495 now.
Sell all now −₹10,610, 13% of your cash · sell 2 lots (40) −₹4,264 · or hold: your call.

The Sentinel's own trade, then its sale
🤖 Sentinel bought SENSEX 77000 CE (05 Nov) at ₹345.55, 12:41:15 (paper).
🛑 Stop SENSEX fut 76,819 (option ≈₹259.16) · 🎯 target fut 77,465.
📏 At its stop: 1 lot −₹1,788 (5.5%) · 2 lots −₹3,528 (11%). The Sentinel risks at most 2% (₹646).
📊 Its last 20 paper trades: 7 won, −₹5,308 a lot. It loses often. Your call.
🤖 Sentinel sold SENSEX 77000 CE at ₹345.4, 13:11 (time limit): −₹42 a lot (paper).
```

**What each part does and why:**
- **No "Quiet today" button.**
  - An accidental tap silenced the watch for the day; to silence the chat they can mute it in Telegram.
  - A tap on an old button in the chat history is answered ("Quiet was removed …") and changes nothing.
  - The muting code and the quiet-day SIZE message are gone. The review page's "quiet today" line can no longer
    show, because `watch_status` always says quiet is off.
- **The check takes just the option.** "76700 ce" or "sensex 76700ce 120 2 lots" is a check now.
  - Such a message counts only when every word reads and it names a strike and CE or PE. "b 22300 pe 75", "ok" and
    "75.5" are not checks, so chat and old trade reports go on as before.
  - Without an index, the check takes the one whose nearest expiry lists that strike (`infer_underlying`;
    NIFTY's 50s near 24,000, SENSEX's 100s near 77,000). It guesses nothing when none or both do.
- **The size line gives choices in rupees** (the audit's first point):
  - the loss at the plan stop for 1 lot and for 2 lots, each with its own charges (order fees paid once), as a
    share of the day's cash;
  - and the most the Sentinel risks on a trade, 2%.
  - The partner's own size is already in the stop line above it. Their usual size is described only in the size
    warning ("much bigger than your usual"), never as advice.
- **A warning and its record are one line:**
  - the oversized-buy record joins the size warning;
  - the after-loss record and the Sentinel's rule ("takes 1 lot after a loss") join the after-loss warning.
  - Records appear only while the frozen score says SUPPORTED.
- **The PLAN lost two lines of explanation:**
  - the "•" facts line (the swing, the 15-minute run, the trend). The run warning was refuted for this partner,
    and the trend said "with you" on every big loser on Nov 4. The check, which they ask for, keeps the facts.
  - "The futures stop … sits inside that swing".
  - Also "In a fast fall an SL order can trigger and still not fill" from the SL line, which UNFILLED tells when
    it happens.
- **BROKEN** (the audit's third point, for losing trades):
  - **When:** one message when the price is first read under the plan stop after being read over it, from 2
    minutes past the buy (before that NO_STOP and the PLAN say it).
  - **Only if not already protected:** no stop of the partner's own at or above the plan stop. Such a stop sells by
    itself, and UNFILLED tells it if it does not.
  - **What it says:** what selling all gives now, against the bids' sizes ("or worse" when the bids shown take
    fewer), and half in whole lots when two lots or more are held, "or hold: your call". A lower stop of their own
    is named.
  - **Once a trade.** Rebuilt at send, so it is not sent if the price is back over the stop or the trade is sold.
  - **Switch:** `PARTNER_WATCH_BROKEN_ENABLED` (default true).
  - On Nov 4 it would have come for the 10:13 and 10:24 trades, sold at ₹600 and ₹422.65 against plan stops of
    ₹650.25 and ₹499.9.
- **The Sentinel's own trades** (`SENTINEL`, `SENTINEL_EXIT`, fixed texts):
  - **What is relayed:**
    - the F&O paper main book's buys (source `FNO_PAPER`; the earned lot `N11_ADD` is left out);
    - the expiry book's main ticket while `EXPIRY_MAIN_STRATEGY` is `E032`.
  - **Which buys:** a buy is told only while the trade is still open and at most 2 minutes old. The audit's case of
    a trade bought and sold inside the window announced as a fresh buy is fixed and reproduced in tests.
  - **Sales:** told while 30 minutes fresh, only once their buy was sent.
  - **Each buy is four short lines:**
    - the option and price;
    - its stop and target. For F&O the option stop is the higher of the delta-priced stop and the 25% backstop;
    - the loss at its stop for 1 and 2 lots in the partner's rupees;
    - its own record, "It loses often. Your call."
- **Kept from N06:**
  - averaging down (ADDED under the first buy) adds "The Sentinel adds only to a trade already up a full stop";
  - DAY adds the after-loss rule when the day had buys right after losses;
  - a check leaves out the chased-spike warning while its frozen verdict refutes it, and says what the Sentinel
    holds on that index.

**Not built, and why:**
- **Winner management** (hold, partial profit, trailing): those are judgments that must be frozen and scored on
  recorded days before they are sent (owner rule). The watch records the price looks for that.
- **A "big move is N× more likely" line:** for an option buyer it cuts both ways. Its out-of-sample AUC
  (0.60–0.82) measures ranking, not a probability for the next trade, so it waits for a frozen forward check.
- **Measuring what the partner did after each message** (stop placed, sold, added, followed): useful to the owner,
  not to the partner. It is the next step, read from the stored orders and messages.

## Honest limits

- **The what-if is in-sample.** The rule was not fitted to these days, but the days are seen. The forward check is
  the partner's next weeks: compare buys at or under the Sentinel's size with bigger ones, on the same frozen score.
- **The 2% rule is a reference, not a limit.** At ₹30k–₹80k of cash, one lot of an at-the-money SENSEX option
  already risks more than 2% at a normal stop. The owner asked for freedom, so the line gives the rupees for 1 and
  2 lots and states the Sentinel's rule beside them.
- **The Sentinel's own forward record is negative.**
  - The last 20 main-book trades are −₹5,308 a lot.
  - The expiry ticket E03.2 runs on SENSEX for the first time on paper. It was fitted on seen NIFTY 2024/2025.
  - Following it is fewer and smaller trades, not a promise of profit. Every message says so.
- **The evening review still teaches its own chased-spike lesson.** That rule (`partner_insights._chased_spike`) is
  stricter: a 20% run and near the day's high, from candles. The frozen score measures the live check's rule, not
  that one, so the review is unchanged. Whether to drop or re-score it is the owner's call.
- **No login, no messages.** The Sentinel's trades are told from the watch's ticks, so a partner who has not logged
  in gets none (as with every other watch message).

## Rollout and rollback

- **Rollout:** no migration. The new kinds use the existing `partner_watch_messages` outbox. One new setting:
  `PARTNER_SENTINEL_ADVICE_ENABLED` (default true).
- **Rollback without a code change:**
  - `PARTNER_SENTINEL_ADVICE_ENABLED=false` turns off the Sentinel advice: the size line, the records, the rules,
    the Sentinel's trades, the spike gate and the check's Sentinel line.
  - `PARTNER_WATCH_BROKEN_ENABLED=false` turns off BROKEN.
  - Set either in `.env` and recreate the engine.
  - Not behind a switch (owner's orders, N06c): no Quiet button, the shorter PLAN and watch-on texts, and the check
    by the option alone. Going back on those needs a revert.
- **Verification in Dev (N06c):**
  - `tests/test_partner_sentinel.py`: 16 passed.
  - Two end-to-end BROKEN tests through the watch tick, in `tests/test_partner_watch.py`.
  - Partner tests: 280 passed.
  - Whole engine suite: 3,199 + 3,036 passed, 4 skipped, `pytest_exit=0` for each half.
  - In one earlier full run `test_s5_provider_lanes::test_cancelled_bulk_waiter_is_removed` failed once. It is
    unrelated (Kite request lanes) and passed 3 of 3 alone and in every other full run.
