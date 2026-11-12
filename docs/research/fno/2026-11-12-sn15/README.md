# SN10–SN15 (Nov 12, 2026): six iterations on the owner's small-wallet goal

Every result: NIFTY 1-minute candles 2023 – Oct 2026 (742 non-expiry sessions) unless stated, current Zerodha charges + ₹205 per lot per trade, a 20% day loss limit, losing days refilled.

| # | Idea | Result | Kept? |
|---|---|---|---|
| SN10 | Expiry-day mornings (to 13:00/14:00) on **10-second** option bars, 56 expiry days | Pick +₹10,506 on Sep 2025–Mar 2026, then **−₹20,705** on Apr–Sep 2026 (top-10 mean −₹7,004; random −₹4,782) | No |
| SN11 | "Exit when it rises, before it dips": first falling minute, small drop from best, or EMA flip, after +5% to +50% | All worse; held out picks the benchmark every year. First falling minute after +5%: 66 won / 52 lost days but −₹15,020 | No |
| SN12 | Wallet sizes | ₹20k at 1 lot +₹1,24,093, against ₹15k's +₹1,11,995 (it buys N11's own contract); 1 lot per ₹15k scales almost linearly | **Yes** |
| SN13 | Smarter second lot (₹30k) and day limits | Second lot on high-volatility days: +₹2,08,778, refill ₹1,55,737, 2023 −₹1,011. Two lots always: +₹2,06,650, refill ₹1,87,056. A 10% day limit is much worse | **Yes** |
| SN14 | Combinations and growth caps per year | Tables below | – |
| SN15 | Frozen forward check for A/B/C | `FORWARD.md` | – |

## Fixed wallets (farm), by year: profit / refilled

| Version | 2023 | 2024 | 2025 | 2026 | Total | Refilled | Won/lost/none | Worst day |
|---|---|---|---|---|---:|---:|---|---:|
| A ₹15k, 1 lot (benchmark) | −7,059 / 20,564 | 35,618 / 14,915 | 39,114 / 34,651 | 44,322 / 21,505 | 1,11,995 | 91,635 | 55/63/624 | −2,998 |
| B ₹20k, 1 lot | −7,591 / 21,096 | 49,512 / 12,118 | 31,273 / 44,856 | 50,899 / 28,272 | 1,24,093 | 1,06,342 | 60/69/613 | −3,997 |
| C ₹30k, volatility-sized | −1,011 / 28,153 | 76,154 / 23,967 | 46,198 / 57,622 | 87,437 / 45,995 | 2,08,779 | 1,55,737 | 59/70/613 | −5,997 |

## Growing wallet, volatility-sized lots, growth stopped after step k: profit / refilled

| Start | Stop after | 2023 | 2024 | 2025 | 2026 | Total | Refilled | Worst day | Final wallet |
|---|---:|---|---|---|---|---:|---:|---:|---:|
| ₹15k | 0 | −7,059 / 20,564 | 35,618 / 14,915 | 39,114 / 34,651 | 44,322 / 21,505 | 1,11,995 | 91,635 | −2,998 | 15,000 |
| ₹15k | 2 | −7,059 / 20,564 | 35,506 / 15,027 | 34,772 / 56,970 | 87,241 / 49,476 | 1,50,460 | 1,42,036 | −6,739 | 33,750 |
| ₹15k | 3 | −7,059 / 20,564 | 35,506 / 15,027 | 34,772 / 56,970 | 1,38,346 / 73,481 | 2,01,565 | 1,66,041 | −10,117 | 50,625 |
| ₹15k | 4 | −7,059 / 20,564 | 35,506 / 15,027 | 34,772 / 56,970 | 1,96,358 / 1,03,487 | 2,59,577 | 1,96,048 | −15,158 | 75,938 |
| ₹15k | 5+ | −7,059 / 20,564 | 35,506 / 15,027 | 34,772 / 56,970 | 2,16,654 / 1,08,131 | 2,79,873 | 2,00,691 | −15,158 | 1,13,906 |
| ₹20k | 1 | −7,591 / 21,096 | 70,318 / 12,136 | 46,198 / 57,622 | 87,437 / 45,995 | 1,96,362 | 1,36,848 | −5,997 | 30,000 |
| ₹20k | 2 | −7,591 / 21,096 | 67,959 / 14,597 | 70,898 / 81,637 | 1,44,655 / 69,254 | 2,75,921 | 1,86,584 | −8,998 | 45,000 |
| ₹20k | 3 | −7,591 / 21,096 | 67,959 / 14,597 | 82,519 / 1,21,495 | 1,96,452 / 1,01,219 | 3,39,339 | 2,58,406 | −13,489 | 67,500 |
| ₹20k | 4 | −7,591 / 21,096 | 67,959 / 14,597 | 82,519 / 1,21,495 | 2,88,472 / 1,47,280 | 4,31,358 | 3,04,467 | −21,712 | 1,01,250 |
| ₹20k | 5 | −7,591 / 21,096 | 67,959 / 14,597 | 82,519 / 1,21,495 | 4,11,053 / 2,07,815 | 5,53,939 | 3,65,002 | −30,320 | 1,51,875 |

**Caveats:** all of this is in-sample, because N11 was shaped on these years. Large wallets assume no extra slippage at 4–10 lots. The forward check is the test.
