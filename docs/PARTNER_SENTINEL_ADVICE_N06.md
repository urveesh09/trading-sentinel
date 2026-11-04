# N06 — The Sentinel's way of trading, as advice to the partner (2026-11-04)

Owner's order, Nov 4: the partner lost ₹51,869 in one day with the watch's messages arriving on time. Make the advice
better "so that instead of such loss-making idiotic trades, they follow the trades of the sentinel", using the
strategies built for N08–N11 and the expiry book, and "no matter what still we will not take any action on behalf
of the partner. Only advice."

Code: `python-engine/partner_sentinel.py` (new), `python-engine/partner_watch.py`, `python-engine/config.py`
(`PARTNER_SENTINEL_ADVICE_ENABLED`, default true). Tests: `python-engine/tests/test_partner_sentinel.py`. Study
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

## What the partner now gets

All of it is messages only, with `PARTNER_SENTINEL_ADVICE_ENABLED` on.

**Every buy's plan and every check** carry "📏 The Sentinel's size for this":
- the lots its rule allows: at most 2% of the day's cash lost at the plan stop, charges included;
- or "none" when even one lot loses more. Then it says what one lot loses and that the Sentinel would pass or take
  a cheaper option.
- A check adds "You asked about 5 lots" when they ask for more than that; a plan adds "You bought 5 lots".
- Shares under 10% show one decimal, so 2.5% never reads as 2%.

**Oversized buys** (over 1.5× their usual share) add their own record: "buys much bigger than your usual, 57
trades, −₹38,024; your usual size, 175 trades, −₹2,130". This line appears only while the frozen score says
SUPPORTED.

**Buys within 30 minutes of a losing exit** add the Sentinel's own rule and their record. The rule: after a losing
trade it takes one lot at most for the rest of the day (`fno_n11.lot_ceiling`). The record also appears only while
SUPPORTED.

**Averaging down** (an ADDED buy under the first one) adds: the Sentinel adds a lot only to a trade already up by a
full stop, never to a falling one (N11's earned lot).

**The DAY message** adds the after-loss rule when the day had buys right after losses.

**A check:**
- leaves out the ⚠️ chased-spike line while that warning's frozen verdict is NOT_SUPPORTED. The run stays among
  the facts.
- says what the Sentinel holds on that index now: "🤖 The Sentinel now holds …" or "holds nothing on SENSEX now
  (1 trade today)".

**The watch-on message (after login)** adds:
- both supported records;
- what the Sentinel will send;
- a line when NIFTY or SENSEX options expire today.

**The Sentinel's own trades**, as they happen (new kinds `SENTINEL` and `SENTINEL_EXIT`; fixed text; never muted
by "Quiet today"):
- **What is relayed:**
  - the F&O paper main book's buys (source `FNO_PAPER`, the N11 book; the earned lot `N11_ADD` is left out);
  - the expiry book's main ticket while `EXPIRY_MAIN_STRATEGY` is `E032`.
- **Each buy says:**
  - the option, its price and time;
  - its stop as an index level and as an option price. For F&O that is the higher of the delta-priced stop and the
    25% backstop, whichever the Sentinel reaches first;
  - its target;
  - the lots its rule gives the partner's cash: "If you follow, one lot at most" when even one lot is over 2%. For
    the expiry ticket, capped at its own lots, plus what a lot loses if the price jumps through the stop;
  - its own record: the last 20 closed main-book trades per lot after charges, or the expiry ticket's record on
    that index;
  - that it is paper, can lose, and that following is the partner's call.
- **Timing:** a buy is told only while 5 minutes fresh. A sale is told while 30 minutes fresh, and only once its
  buy was sent. It adds "You still hold N of it" when they do.

Real-data preview (Nov 4, rendered in Dev from Production's rows copied read-only; `preview.py`):

```
🤖 The Sentinel's own trade (paper, not a tip): bought SENSEX 77000 CE (05 Nov) at ₹345.55 at 12:41.
🛑 Its stop: SENSEX future 76,819, about ₹259.16 on the option. 🎯 Its target: SENSEX future 77,465.
📏 For your ₹32,305 cash: one lot (20) loses about ₹1,788 at its stop, 5.5% of your cash, more than the 2% it risks itself (₹646 for you). If you follow, one lot at most.
📊 Its last 20 paper trades: 7 won, −₹5,308 a lot after charges. It loses on many days; its edge in years of replays is small.
I'll tell you when it sells. Whether to follow is your call.

🤖 The Sentinel sold its SENSEX 77000 CE at ₹345.4 at 13:11 (its time limit): −₹42 a lot after charges (paper).
```

## Honest limits

- **The what-if is in-sample.** The rule was not fitted to these days, but the days are seen. The forward check is
  the partner's next weeks: compare buys at or under the Sentinel's size with bigger ones, on the same frozen score.
- **The 2% rule usually says "none" for this account.** At ₹30k–₹80k of cash, one lot of an at-the-money SENSEX
  option already risks more than 2% at a normal stop. The message then says one lot at most. That is the honest
  answer for the size of the account, not a softer rule.
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
- **Rollback without a code change:** set `PARTNER_SENTINEL_ADVICE_ENABLED=false` in `.env` and recreate the
  engine. The watch is then exactly as before N06; the tests pin that, because `tests/conftest.py` sets it false.
- **Verification in Dev:**
  - `tests/test_partner_sentinel.py`: 11 passed.
  - Partner tests: 252 passed.
  - The partner-watch tests with the advice on: only the two DAY wording assertions differ, no errors.
  - Whole engine suite: 3,309 + 2,905 passed, 4 skipped, `pytest_exit=0` for each half.
