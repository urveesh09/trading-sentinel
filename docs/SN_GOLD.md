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
