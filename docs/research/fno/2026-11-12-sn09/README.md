# SN09: option open interest (Nov 12, 2026): NOT PROVEN

**Freeze:** `627d8af8`.

**Data:** option OI per strike-minute from the sealed candles (`sn09_oi.py`). OI moves every 3 minutes, the exchange's snapshot rhythm.

**A. OI entries on N11's empty days** (`sn09.py`, 10,500 rule sets):
- the families were PCR shift, writer flow, OI-wall breakout and OI-wall bounce, with N11-style exits and optional ADX/DMI gates;
- causality was checked by perturbing OI and price after a cut.

| | Four years |
|---|---:|
| Held-out picks (0 of 4 years positive) | **−₹1,80,378** |
| Random entries behind the same gates | −₹1,57,721 |
| Combination held out (N11 on its days, the SN09 pick on the others) | −₹68,385 |
| Benchmark | +₹1,11,995 |

Median per trade in the random pool:

| Family | Per trade |
|---|---:|
| WALLB | −₹242 |
| PCRD | −₹274 |
| FLOW | −₹294 |
| WALLR | −₹346 |
| Random | −₹316 |

**B. OI flow as a confirmation filter on N11's trades** (`confirm.py`, 49 settings):

| | Four years | Won/lost days |
|---|---:|---|
| Benchmark | +₹1,11,995 | 55/63 |
| Best in-sample (k15 w150, skip if opposing by 2%) | +₹1,04,127 | 46/48 |
| Held-out picks | **+₹71,964** | 42/52 |

- Some settings cut losing days to 36 and make 2023 positive (k15 w150 oppose 0.5%: +₹98,635, 36/36 days), at a cost in profit. They are not stable held out.

**Verdict:** the benchmark stays. OI adds no reliable edge to entries in this data.

**10-second data:** the house's 10-second data covers only 27 expiry days (`2026-11-03-expiry-auction`), and SN does not trade expiry days.
