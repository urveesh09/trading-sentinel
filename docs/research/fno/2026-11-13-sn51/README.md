# SN51–SN75 (Nov 13, 2026): twenty-five perspectives on SN Gold v4 → SN Gold v5

- **Lab:** `lab.py`, built by `make_lab.py` from the frozen `../sn-gold/gold_v4.py`.
- **Frozen versions:** v3, v4 and v5 are in `../sn-gold/` with verifiers. All three reproduce after this round. The tags are `sn-gold-v3`, `sn-gold-v4` and `sn-gold-v5`.
- **Scoring:** every variant at every wallet:
  - A: ₹15k, 1 lot;
  - B: ₹20k, 1 lot;
  - C: ₹30k sized;
  - growth from ₹15k, stopped after 0, 2, 3 (Gold) or 5 steps.
- **Selection:** chosen on three years and scored on the fourth.
- **Costs:** Zerodha charges + ₹205 per lot per trade, 20% day limit. The entries are in-sample.

| SN | Perspective | Result | What it taught | Kept |
|---|---|---|---|---|
| 51 | The owner's question "is the cap costing us?" + start amounts | No profit cap exists in Gold; "stop after k" caps size and risk. Uncapped "₹57 lakh" needs hundreds of lots (worst day −₹3.57 lakh) and is not achievable | The cap protects; it doesn't cost | – |
| 52 | A real account with no refills | From ₹15k or ₹20k, a 2023 start drains it below one lot: dead. ₹30k survives and grows to ₹4,36,492 | Refills keep a small account alive; ₹30k is self-sustaining | Insight |
| 53 | Option writers' flow as SIZING (SN09's good part) | Worse at every sized wallet | OI is closed as a signal | No |
| 54 | Puts get the second lot more often | Small in-sample gain, not stable held out | – | No |
| 55 | Second lot by trend regime (ADX) | Worse | – | No |
| 56 | **N11 + its sister book R0.85's extra entries** | A +₹1,33,773, B +₹1,65,981; held-out pick 4 of 4 at A/B | Standing aside slightly less adds good trades | **v5** |
| 57 | Day limit 30% | C better, A/B worse, bigger worst days | 20% stays | No |
| 58 | No new trade after a big day | Worse | Never stop a big day (SN45) | No |
| 59 | Second lot by the book's own recent results | Worse | Recent form doesn't predict | No |
| 60 | Deepest strike the wallet can buy | Worse than v4's depth rule | – | No |
| 61 | **Scale-in when the index has moved 1 ATR** | Better at every wallet in-sample | The index move is a better "it's working" signal than the option's % | **v5** |
| 62 | **Scale-in buys the full wallet (pyramid)** | Best when combined (SN69) | Press winners hard, inside the day room | **v5** |
| 63 | Give-back trail on top of the 3-ATR trail | No change at all | The 3-ATR trail always exits first | – |
| 64 | Hold extended winners to 15:20 | Worse | The last minutes hurt | No |
| 65 | Slippage as a share of premium (1–2% per side) | Still positive everywhere | Robust to harsh fills | – |
| 66 | 2-minute delays, partial fills | Still positive everywhere | Robust to execution | – |
| 68 | Start date (15 quarters) | Every start profitable, refilled or as a real ₹30k account | Not a lucky start date | – |
| 69 | **Fair contest of the kept parts** | v5 wins held out: A 4/4, G3 4/4, B 3/4, C 3/4 | – | **v5** |
| 70 | v5 × start amount × growth trigger | Table below | – | Levers |
| 71 | v5 one-year risk and the real account from every start | Below | – | – |
| 72 | v5 without its best days | A: +₹1,51,155 → +₹92,230 (best 5 out) → +₹45,239 (best 10 out; v4: +₹30,055) | Less concentrated than v4 | – |
| 73 | v5 under +₹400 stress, 1% of premium, both, 2-minute delays, partial fills | Positive at every wallet in every case | – | – |
| 74 | Freeze v5 next to v3/v4 | `../sn-gold/SN_GOLD_V5.json`, `gold_v5.py`, `verify_gold_v5.py`, tag `sn-gold-v5` | – | – |
| 75 | This report | – | – | – |

## SN Gold v5, per year: profit / refilled, and the net at the end

Net at the end = won on winning days − refilled.

| Wallet | 2023 | 2024 | 2025 | 2026 | Won on winning days | Refilled | **Net at the end** | Won/lost/none | Worst day |
|---|---|---|---|---|---:|---:|---:|---|---:|
| A ₹15k | 397 / 26,547 | 52,158 / 15,338 | 48,506 / 36,792 | 50,094 / 22,468 | 2,52,300 | 1,01,145 | **1,51,155** | 58/64/620 | −2,998 |
| B ₹20k | −1,305 / 29,321 | 72,538 / 14,234 | 43,957 / 50,531 | 61,656 / 32,810 | 3,03,742 | 1,26,896 | **1,76,846** | 64/69/609 | −3,997 |
| C ₹30k | −12,107 / 52,422 | 1,15,439 / 25,061 | 70,789 / 67,633 | 1,06,387 / 47,930 | 4,73,554 | 1,93,046 | **2,80,508** | 61/72/609 | −6,110 |
| Grow, stop after 2 | 397 / 26,547 | 84,668 / 23,840 | 87,386 / 76,258 | 1,12,543 / 56,087 | 4,67,726 | 1,82,732 | **2,84,994** | 63/70/609 | −6,740 |
| **Grow, stop after 3** | 397 / 26,547 | 82,363 / 26,301 | 1,43,065 / 1,22,788 | 1,74,081 / 90,260 | 6,65,802 | 2,65,896 | **3,99,906** | 63/70/609 | −10,119 |
| Grow, stop after 5 | 397 / 26,547 | 82,363 / 26,301 | 2,21,056 / 2,30,857 | 4,37,859 / 2,09,027 | 12,34,407 | 4,92,732 | **7,41,675** | 63/70/609 | −22,740 |

**Start amount × growth trigger** (net at the end; worst day in brackets):

| Start | Step after 100%, stop 3 | Step after 50%, stop 3 | Step after 50%, stop 5 |
|---|---:|---:|---:|
| ₹15k | 3,99,906 (−10,119) | 4,54,692 (−10,119) | 9,60,885 (−22,740) |
| ₹20k | 5,36,968 (−13,492) | 6,53,133 (−13,492) | 13,53,208 (−30,320) |
| ₹30k | 8,50,882 (−21,113) | 9,47,841 (−21,113) | 20,24,800 (−45,469) |

**Risk (SN71):**
- **One year at ₹15k:** median +₹36,528; 5th percentile +₹2,690; 95th +₹75,416; a 3.5% chance of a losing year; refill median ₹25,053 (95th ₹37,253).
- **₹30k:** median +₹67,094, 4.4% losing years.
- **Real account with no refills, started in each of 15 quarters:** from ₹15k it dies 3 times, from ₹20k once, from ₹30k never (ends ₹90k–₹5.44 lakh).

**Caveats:**
- The entries are N11's and in-sample.
- R0.85 has no live paper record, so the forward check scores v5 on N11's signals until one exists (`../sn-gold/FORWARD_V5.md`).
