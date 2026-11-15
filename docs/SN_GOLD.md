# SN Gold: the owner's small-wallet F&O book (paper), from Nov 13, 2026

**Paper only. It never places an order, and it changes nothing in N11, the main paper book or the partner companion.**

- Module: `python-engine/sn_gold.py`, called from `fno_orchestrator.py` at two guarded hooks.
- Research it follows: SN Gold v5 (`docs/research/fno/sn-gold/SN_GOLD_V5.json`, tag `sn-gold-v5`, verified by `verify_gold_v5.py`).

## The rules (as the owner gets them)

**The wallet:**
- It starts at **₹30,000**. The owner left the starting amount to the agent on Nov 13 ("if you think 30,000 starting amount is better than I am fine with that"). From ₹30k the research account survived every one of 15 start quarters without a refill; from ₹15k it ran dry 3 times (SN70/SN71).
- Profits are banked and never traded. A losing day is **refilled**: the next day starts at the full wallet again, and the loss is counted as a refill.
- Each time the net profit since the last step reaches the wallet, the wallet grows **50%**, at most **3 times**: ₹30,000 → ₹45,000 → ₹67,500 → ₹1,01,250.
- The day loss limit is **20% of the wallet**: ₹6,000 at the start, ₹20,250 at the top.

**Entries:**
- Every NIFTY signal on N11's live paper record, when SN Gold has no position open.
- Plus the signals N11 only waits on, because SN Gold follows N11's sister book R0.85. It waits only when yesterday's volatility is below **0.85** of usual (N11 uses 0.9) *and* N11's last 20 paper trades sum to zero or less.
- No expiry-day trades (N11 records none).

**Size:** `floor(wallet / ₹15,000)` lots, halved (minimum 1) when N11's volatility reading is not up. From ₹30,000: 2 lots on lively days, 1 on quiet days, and up to 6 at the top wallet.

**Strike:**
- The deepest in-the-money strike where every lot fits the wallet: **1 strike** in with under ₹17,500 of wallet per lot, **2** under ₹20,000, **3** from ₹20,000.
- Else N11's own strike, else one strike further out of the money.
- Bought at the ask of the same chain snapshot N11 used.

**Protection:** a stop on the option at the price where the day would lose its 20%. If it is touched, SN Gold sells.

**Pressing a winner:** once, when the NIFTY future has moved **1 × its 1-minute ATR** in the trade's favour, it buys as many more lots as the wallet carries. It does this only if the whole position's stop still fits the day's limit.

**Exits:**
- With N11's paper lot (the same exit ladder the research replayed).
- A trade up **≥ 25%** on its first fill at that moment is **kept**, with a trail **3 × the 1-minute ATR** behind the best future price, until **15:10**.
- Anything still open leaves at 15:15.

**Money:** real bid/ask and the shipped Zerodha charges. `net_stressed` keeps the research's extra ₹205 per lot beside it.

**Messages:** a line on each buy and sell, and one summary on days it traded: the day's result, the refill, the wallet, and won / refilled / net since the start.

## What research says to expect

These figures are in-sample (`docs/research/fno/2026-11-13-sn51/README.md`):
- From ₹30,000 with refills, stopped after 3 steps (SN70): **+₹8,50,882** net over Jan 2023 – Oct 2026.
- The worst day was −₹21,113, near the top wallet.
- From ₹15,000 the same rules made +₹3,99,906.
- As a real account with no refills, ₹30k ended at ₹90k–₹5.44 lakh, depending on the start quarter.
- About 63 winning, 70 losing and 609 no-trade days out of 742.
- **About 1 trade every 5–6 sessions.** Most days nothing happens.
- A typical year at a fixed ₹30k wallet makes about +₹67k, with refills around ₹47k. The chance of a losing year is 4.4%.

This paper run is also SN Gold's forward check (`docs/research/fno/sn-gold/FORWARD_V5.md`). It is judged at ≥ 20 trades.

## Data

All tables are in the engine database:
- `sn_gold_positions`: each position, its pieces, stop, exit and net;
- `sn_gold_days`: each day's net, refill and wallet;
- `sn_gold_wallet`: the running wallet, steps, banked and refilled;
- `sn_gold_skips`: signals not taken, and why;
- `sn_gold_bars`: fallback minute bars.

## Switch off and rollback

- **Off:** `SN_GOLD_ENABLED=false` in the engine's `.env`, then recreate the engine. The tables stay; nothing else reads them.
- **Rollback:** redeploy the previous release. No other table or setting is touched.
- **Real money:** none. Real money would need the owner's word, a passed forward check and its own runbook.

## Gold v6 (from Nov 15, 2026, Dev): SN Gold v5 + WK-H, the hedged weekly straddle

**The owner, Nov 15:** "That gold v5 + wk-h is the new gold v6 … I allow you to do that in Dev right now … this will be our baseline, and we will be calling this Gold V6."

**Gold v6 = the SN Gold v5 book above, unchanged, plus WK-H** (`python-engine/sn_wkh.py`), the leg for the days Gold does not trade.
- Paper only, never an order.
- In Dev; Production runs it only after a deploy on the owner's word.

**WK-H, the rules as the owner gets them:**
- **When:** at **15:15 on the first session after the last weekend or holiday before the weekly expiry**. With Tuesday expiries that is the Monday 15:15. It never holds a weekend.
- **What:** sell the at-the-money NIFTY call and put, **2 lots** for each ₹5 lakh.
- **The hedge:**
  - every 15 minutes from the next morning's 09:15, the system measures which way the straddle is leaning;
  - if the lean exceeds 0.6 lot, it buys or sells NIFTY futures to cancel it;
  - on expiry day it stops adding orders at 14:30, and the futures close at about 15:25.
- **The result:** the straddle settles at the official NIFTY close on expiry day. The week's result is booked at the next morning's first tick, after charges, and banked or refilled.
- **The wallet:** ₹5 lakh, a margin estimate not yet checked on Zerodha.
- **Messages:** the sale, each futures order, a 15:15 value line on the days in between, the hedge close, and the week's result.

**What research says to expect, per option lot (SN221–SN230):**
- about ₹1,000 a week on average, with 59% of weeks winning;
- the unseen NIFTY Oct 2020 – Nov 2021 exam made +₹61,511 per lot, worst month −₹6,251;
- with Gold over 2023 – Aug 2026: +₹8.17 lakh against Gold's +₹6.42 lakh, and a smaller worst month (−₹28k against −₹38.5k).
- **Weak point:** a late move on expiry afternoon after 14:30 (May 16 2024, −₹24.6k per lot).
- Full record: `docs/SN_WEEKLY_SELLER_AND_GOLD_V6.md`.

**Data:**
- `gold_v6_wkh_weeks`: each week, its strikes, fills, hedge, settlement and net;
- `gold_v6_wkh_orders`: every futures order;
- `gold_v6_wkh_marks`: the 15:15 value lines;
- `gold_v6_wkh_wallet`: banked, refilled and weeks.

**Off:** `SN_WKH_ENABLED=false` in the engine's `.env`, then recreate the engine. SN Gold v5 keeps running; the tables stay.

## Gold v7 (Nov 15, 2026, Dev default): the same WK-H leg with a wider hedge band

- **The change:** `SN_WKH_BAND = 0.8` instead of Gold v6's 0.6. The futures are re-hedged only when the lean exceeds 0.8 lot, so there are fewer, cheaper orders. Messages read "Gold v7 · WK-H".
- **Why:** SN231–SN250 (`docs/research/fno/2026-11-15-sn231`). Over Jan 2023 – Oct 2026 with SN Gold v5:
  - **33 of 46 months positive** against 31;
  - **worst month −₹28,981** against −₹38,228;
  - net +₹13.71 lakh against +₹11.96 lakh.
- **Its weak spot:** in fast markets it earns less than band 0.6.
- **Back to Gold v6:** `SN_WKH_BAND=0.6` and `SN_WKH_LABEL="Gold v6"`.
- **Still to come:** the NIFTY 2020 crash test, once that download is complete.

## Gold v7: the complete rule card, expectations and the road to real money (Nov 15, 2026; on paper in Production `052a6d6e`)

**Leg 1, SN Gold v5 (unchanged; option buying, N11's entries):**
- **Wallet:** ₹30,000. Profits are banked; a losing day is refilled.
- **Growth:** +50% after net profit equal to the wallet, at most 3 times: ₹30k → ₹45k → ₹67.5k → ₹1,01,250.
- **Lots:** floor(wallet ÷ ₹15,000), halved on low-volatility days. The deepest in-the-money strike the wallet affords.
- **Day loss limit:** 20% of the wallet (₹6,000 at ₹30k). A scale-in once at a 1-ATR move.
- **Exits:** with N11; winners up 25% are kept on a 3-ATR trail to 15:10; everything is out by 15:15.

**Leg 2, WK-H (option selling, hedged), the Gold v7 setting:**
- **Unit:** ₹5,00,000 = 2 NIFTY option lots (fixed; no growth step in the runtime).
- **Entry:** 15:15 on the first session after the last weekend or holiday before the weekly expiry (with Tuesday expiries, the Monday). Sell the ATM call and put.
- **Hedge:**
  - NIFTY futures, checked every 15 minutes from the next 09:15;
  - re-hedged when the lean exceeds **0.8 lot**;
  - no new orders from 14:30 on expiry day; the futures close at their 15:00–15:25 mean.
- **Settlement:** the options settle at the official close; the week is booked at the next open and banked or refilled.
- **No stop** (the research's 1× credit stop never fired).

**What the research expects** (Jan 2023 – Oct 2026, both legs; expectations, not promises):

| | Gold v7 |
|---|---:|
| Net, 46 months | +₹13,70,643 (≈ ₹29.8k a month on average) |
| Months positive | 33 of 46 (72%) |
| Sessions green / red (refilled) / flat | 291 / 361 / 292 of 944 |
| Sessions earning ≥ ₹750 / ≥ ₹1,500 | 270 / 244 |
| Average per session | ₹1,452 |
| Banked on green days / refilled on red days | ₹27.1 lakh / ₹13.4 lakh |
| Worst day / week / month | −₹48,695 / −₹50,234 / −₹28,981 |
| By year 2023 / 2024 / 2025 / 2026 (to Oct) | −₹26,648 / +₹3,43,667 / +₹5,68,064 / +₹4,85,561 |

**Refills from the pocket or from profit:**
- Paying every refill from accumulated profit, the account starting Jan 2023 went at most **₹30,699 below zero** (Jul 24 2023), and was above zero for good from Nov 9 2023.
- The worst start month (May 2024) went ₹78,681 below zero (Jun 4 2024, election day) and recovered by Jul 23 2024.
- So the owner should keep **about ₹80,000 ready** for the first weeks. After that, past profit has always covered the refills in the research.
- **A fixed daily wage from a buffer:** ₹750 every session needed a ₹2.39 lakh buffer from Jan 2023; ₹1,000 needed ₹3.26 lakh.

**Real money: the gates (all must hold; then the owner's word):**
1. **Paper record:** at least **8 settled WK-H weeks** on Production paper (about 2 months). In it:
   - no `UNRESOLVED` week;
   - hedge checks executed in ≥ 95% of the 15-minute slots;
   - fills no worse than the research costs (the entry credit at least the model bid; futures fills within 1.5 points of the quote mid).
2. **The pre-registered NIFTY 2020 crash test** run once and passed (C1 net > 0, C2 worst month ≥ −₹34,163 per lot). If it fails, WK-H stays on paper.
3. **Margin:** Zerodha basket margin for 2 short ATM lots + 2 futures lots confirmed below the ₹5 lakh unit, with headroom for expiry-day margin increases.
4. **A real-money WK-H module (not built yet).** It must:
   - place and confirm the straddle and every hedge order;
   - reconcile positions with Zerodha after each step;
   - **close everything if the engine misses two hedge slots or the week's loss passes −₹50,000**;
   - send an owner alarm on any rejected order.
   - It is tested on paper first, as every live path was.
5. **Gold v5's own forward check** (`docs/research/fno/sn-gold/FORWARD_V5.md`) consistent with its research.

**Recommended first real step:**
- **1 unit only** (₹5 lakh margin + ₹30k Gold wallet), with the week stop above.
- No unit growth for at least 6 months; adding units raised the worst month in proportion (SN240).
