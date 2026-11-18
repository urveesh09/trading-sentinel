# EN41–EN55: where each slot won and lost

Scored once on Nov 18, 2026 by `en_score5.py` under `PLAN5.md`, frozen at `4376ba80` before any score.
- **Results:** `results5.json`, `anatomy5.json` and `results5-started.json`.
- **Tables:** `ANATOMY5-tables.md`, rendered by `render5.py`.

**Books:** NIFTY 197 expiry afternoons (2023 – Oct 2026) and SENSEX 63 (Jul 2025 – Oct 2026). All are seen, so every result below is development screening.

**How to read the figures:**
- **Fixed-cap:** each expiry runs on its own, with its full day reserve and no brakes.
- **Wallet:** one continuous Rs 30,000 book, brakes on the trading high-water, 50% of profits swept out.
- Rupees are net after fees at ordinary fills unless stated.

## The answer first

**Nothing passes.**
- No new entry is positive both overall and without its two best expiries on both indices.
- No modification beats its control.
- The ten primary tests are all far from significant: the smallest raw p is 0.395 and every Holm-adjusted p is 1.0.

**Three findings matter for money:**

**1. The learned E03.2 (EN55) is the only version that survives a continuous wallet.** It is E03.2 with the patient entry, the half-first scout and the stall runner.

| NIFTY (197 expiries) | E03.2, Rs 30,000 | EN55 |
|---|---:|---:|
| Fixed-cap ordinary / adverse / severe | +14,275 / +11,586 / **−12,347** | +13,165 / +11,056 / **+991** |
| Without its two best expiries | +652 | +1,045 |
| Worst expiry | −1,281 | −854 |
| **Continuous wallet** | **−4,123** (halted from Jan 18, 2024, 146 halted sessions) | **+3,445** (never halted; Rs 2,890 swept) |

On SENSEX, EN55 made +2,470 against +2,449: its worst expiry was −784 against −1,125, and its wallet ended at +2,470 against +1,987.

The caveat: its NIFTY wallet came within Rs 387 of the Rs 4,000 halt (worst drawdown 3,613). Its pieces were chosen on these very sessions, so the plan makes it **FORWARD-ONLY**: it is registered for the next 20 expiries per index (`FORWARD5.md`).

**2. Every expiry does swing, but the swing usually comes after the stop.** The managed straddle (EN51) is the cleanest test of your point:
- On NIFTY it reached +25% before −25% on 42 of 134 entries (+59,414), and −25% first on 87 (−76,634).
- On SENSEX: 14 targets (+16,515) against 20 stops (−20,874).
- Holding to 15:14 instead (`EN51_hold_diag`) loses −45,581 on NIFTY.

The opportunity is real, but the time decay comes first two times out of three.

**3. The straddle that drops its loser (EN52) is the most profitable new idea on NIFTY, and it is a lottery.**
- **NIFTY:** +16,554 ordinary, +3,658 adverse, **−32,962 severe**, −8,588 without its two best days.
- **SENSEX:** −8,351.
- **The anatomy:**
  - 23 tickets where the kept leg reached 15:14 or 10x made about +99,800;
  - 44 joint stops lost −36,325;
  - 65 tickets lost −46,286: the kept leg trailed back to its cost after the other leg had been sold at a loss.

## The auditor's ten

| Slot | Result | Where it won / lost |
|---|---|---|
| EN41 book pressure | **DATA_UNAVAILABLE** | Needs sealed depth packets. TR01 began Nov 13 inside Production, so at most two expiry sessions exist, unexported. Exporting it is your separate call. |
| EN42 pressure failure | **DATA_UNAVAILABLE** | Same data as EN41. |
| EN43 weighted constituents | **DATA_UNAVAILABLE** | No dated weights or sub-minute stock prices; only Kite 15-minute bars. |
| EN44 opening-range retest | **FAIL** | NIFTY 2023–25 mornings: 43 tickets, −4,298, below its random-side null (−3,694). 18 futures-reentry stops −3,285; 7 premium stops −2,912. The immediate breakout was worse (−5,987); the same rule at 12:00–12:30 lost −3,487 on NIFTY and made +233 on SENSEX. SENSEX has no morning options. |
| EN45 failed escape to VWAP | **FAIL** | NIFTY −10,898 on 136 tickets (null −8,405, so worse than random); SENSEX −2,270. The VWAP target was reached 32 times (+1,551), but 38 continued breaks (−7,748) and 65 clock exits (−4,262) lost more. Fading immediately was worse (−17,079). |
| EN46 does the move pay the option | **FAIL** | Kept 34 of 104 NIFTY signals. +1,202 against equal-risk E03.2's +7,174: it removed the winners with the losers. With zero drift it never buys (0 tickets): without a directional edge, no option purchase pays its decay. |
| EN47 strike by response | **FAIL** | Under Rs 1,250 almost no strike moves enough to beat its spread and two order charges: 4 NIFTY tickets and 1 SENSEX ticket. |
| EN48 RBI decisions | **INCONCLUSIVE** | One officially verified RBI decision (Aug 8, 2024) fell on an expiry session in our history. |
| EN49 payoff model | **INCONCLUSIVE (it abstained)** | Over 12,632 NIFTY and 1,067 SENSEX decision rows, its highest forecast 3-minute net was −4.1% (NIFTY) and −1.7% (SENSEX) of the reserve. The real average was −6.9% and −5.4%. It ranks a little (top decile −5.6% against bottom −9.9%), but every forecast was negative. The fixed trend rule on the same grid lost −19,597. |
| EN50 hold-another-minute model | **INCONCLUSIVE** | Its model existed on 69 NIFTY sessions and changed only 3 tickets. SENSEX never had enough history. |

## My five

| Slot | Result | Where it won / lost |
|---|---|---|
| EN51 managed straddle (±25%) | **FAIL** | NIFTY −17,539, SENSEX −4,932: stops are hit first about two times in three. 62 NIFTY and 27 SENSEX days were refused because the straddle cost more than Rs 5,000. |
| EN52 straddle, drop the loser | **FAIL** | NIFTY +16,554 but −8,588 without its two best days and −32,962 at severe fills; SENSEX −8,351 (above). |
| EN53 E03.2 signals at the money | **FAIL** | NIFTY +5,273 against E03.2's +14,275; SENSEX +259 against +2,449. At-the-money doesn't make 10x, so it gives up the hero. It cut calls' losses (calls +2,096 against −569). |
| EN54 straddle only when cheap | **FAIL** | NIFTY −15,220; SENSEX +630 (24 tickets, not enough to judge). Cheapness did not rescue the straddle. |
| EN55 the learned E03.2 | **FORWARD-ONLY** | Above. The best continuous-wallet result of the round. |

## Capital (Rs 30,000 and 50% retention)

**NIFTY:** the extra Rs 5,000 changes nothing. The brakes are rupee amounts, so the original E03.2 halts on the same day in a Rs 25,000 or a Rs 30,000 wallet. Equal-risk E03.2 halts later (Mar 13, 2025).

**SENSEX:** retention works as designed. E03.2 swept Rs 2,422 at its peak. Its later losses left the wallet at Rs 29,565 although the strategy's total was +1,987: losses reduce the wallet in full, and swept money is not returned.

## What this round taught

1. **At 3–8-minute horizons the costs win.** Spread plus two order charges is about 5–7% of a cheap expiry option. A model trained on twelve thousand real decisions never found a positive 3-minute trade.
2. **Fading, retesting and range ideas lose on both indices,** even when their target is hit: EN44, EN45 and EN13 before them.
3. **The money on expiry afternoons is in the few big directional days.** E03.2's puts, EN52's kept legs and the heroes all come from them. Everything that avoids losses also avoids those days, except the mechanisms in EN55: probe with half, enter patiently, let the runner earn its hold. That combination kept the profit, avoided the halt, and is now the one to prove forward.
4. **The brakes matter more than any filter.** E03.2's continuous book died in January 2024. EN55's survived by Rs 387.

## Round 5b (Nov 18): EN41 / EN42 on real order-book packets, and a resting-bid fill check

The owner authorised a read-only extraction. TR01's two complete recorded days were copied out of the Production container with `docker cp`; nothing in Production changed.
- **Export:** `sentinel-operations/tr01-export-20261118`. All 802 chunks were re-hashed against the recorder's manifests and all match.
- **Plan:** `PLAN5B.md`, frozen at `8737707a`.
- **Scorer:** `en5b.py`, run once, writing `results5b.json`.

**Coverage:** the auditor's rule needs ≥ 80% of seconds with a fresh futures quote.
- Nov 16 had 75.9% and is excluded.
- Nov 17, the only expiry session recorded so far, had 81.5% and 1,556 valid 10-second windows.
- Kite's "full" feed sends about one futures snapshot a second, so order flow is measured on delivered snapshots, not every exchange event.

| Slot | Result | Where it won / lost |
|---|---|---|
| EN41 book pressure | **INCONCLUSIVE** (one session, by construction) | Of 1,391 standardised windows, 91 reached \|z\| ≥ 2, only 9 came as consecutive pairs, and 2 also had the price move. Both were puts, and both lost: −118 at a 1-second delay, −108 at 3 s, −147 at 10 s. In the 30–180 s after each signal the future moved 19–45 ticks against the trade. The random-side median was −95. |
| EN42 pressure fails | **INCONCLUSIVE** (never fired) | No episode had both a flat price under strong pressure and three replenishments of the defending quote. |
| Order-flow information (all 1,186 valid windows) | No continuation | +1.0 ticks after 30 s (t = 0.77), +0.1 after 60 s, −6.3 after 180 s. |
| **Q28: do resting bids fill?** | **Measured** | Over 240 one-lot bids at the best bid (13:00–15:00), behind a median queue of 349 lots: **72% filled within 10 s and 89% within 60 s** (conservative rule). The minute-candle assumption EN28 used (88%) agreed with the packet evidence on 97.5% of orders. **But fills are adversely selected:** a minute later the option's mid was −2.1% after a fill and +17.6% after a miss. The fills you get are the falling ones; the misses are the runaways. |

**What it means:**
- At the feed we have, pressure on the order book adds nothing that the price doesn't already show.
- EN28's patient entry fills about as often as round 4 assumed. Its saving of about half a spread comes with a cost: winners are the ones that run away unfilled.

The EN55 learned E03.2 has a capped fallback buy for exactly that case, which is part of what its forward test measures.
