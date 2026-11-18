# EN01–EN05: what improved E03.2 and what did not

November 17, 2026.
- **Two fixes make the paper book honest and make live E03.2 trade the window it was tested on.**
- **The three strategy ideas all failed their frozen tests**, so the E03.2 rule stays exactly as it is.
- **On NIFTY 2023, the one year it had never seen, E03.2 and its whole family lost money.**
- Paper only, no real orders.

## Why E03.2 has not traded yet

In four live sessions (Nov 5, 9, 12, 17) it opened no ticket:
- Its trend-strength check said no 404 times out of 480.
- That is by design. In 2024–2025 it traded on about one expiry in three.
- EN03 below shows that loosening that check loses money.

## The five slots

| Slot | What | Result |
|---|---|---|
| **EN01** | Honest exits (the audit's three items) | **Done in Dev**, 8 tests |
| **EN02** | Start recording at 12:47, so E03.2 can decide from 13:00 | **Done in Dev** |
| EN03 | More put tickets (a looser trend check for puts) | **Failed**: the extra tickets lose |
| EN04 | Bigger puts (2.5x, 3x, 3.5x) | **Failed as frozen**: 3x passed, its neighbours did not. It also lost on 2023 |
| EN05 | Keep part of a winning put after the 8-minute clock | **Failed**: worse in both years |

**EN01, honest exits:**
- A single displayed bid can no longer be sold twice in one quote snapshot.
- Every sale now gets its own message.
- A ticket that cannot be sold before the close is valued at settlement: intrinsic value from our
  sampled index, or its worst case if there is none. It is marked "assumed, not a fill" and you get a
  message. It no longer blocks the next expiry.
- From December 7, no paper sale is booked after the expiring contracts' 15:30 close. The old A/B/C
  book's 15:38 sale moves to 15:28.

**EN02, 13:00 start:**
- E03.2 needs twelve one-minute bars. Recording began at 12:59, so it could not decide before about 13:11.
- In testing, 2 of its 39 tickets came in 13:00–13:10 (+Rs 1,715).

## The numbers

NIFTY 2024 + 2025, one Rs 25,000 book. In-sample, because E03.2 was built on these years.

| | E03.2 | Puts 2.5x | **Puts 3x** | Puts 3.5x | Looser put check (0.65) | Put runner (1.2) |
|---|---:|---:|---:|---:|---:|---:|
| Normal fills | +21,518 | +23,846 | **+34,165** | +39,240 | +10,367 | +18,351 |
| Worse fills | +20,001 | +22,102 | **+31,341** | +34,933 | +7,367 | +17,166 |
| Very bad fills | −2,438 | −3,343 | **−3,277** | −4,232 | −4,070 | −3,046 |
| Worst day | −647 | −1,247 | **−1,247** | −1,847 | −1,117 | −647 |
| 2025 alone | +5,937 | +7,853 | **+9,363** | +9,575 | −4,026 | +3,719 |

**What we learned:**
- **The trend check is load-bearing.** Put signals just below its threshold lost money in both years.
  At 0.60, the extra put tickets were 16 in 2024 (4 winners) and 14 in 2025 (3 winners). The edge exists
  only in the strongest moves. Loosening the check to get more trades is the wrong way to make E03.2
  busier.
- **More money on puts is the only lever that kept working.**
  - 3x puts passed every test, including the risk limits frozen on Nov 3.
  - The rule written for this round also required 2.5x and 3.5x to pass. 2.5x fell short of E03.2 without
    its best day (lot rounding), and 3.5x lost more on very bad fills.
  - So 3x was not adopted. It went to the 2023 exam as an arm and lost there too.
- **The 8-minute sale is right for puts too.** Keeping a runner after it gave money back in both years.

## NIFTY 2023: the fresh test, and it failed

You said open it, so it was scored once, exactly as frozen. It covered 49 of 2023's 52 expiries; the
first three January ones were never downloaded.

| | E02 | E03 | E03.1 | **E03.2** | Puts 3x |
|---|---:|---:|---:|---:|---:|
| Normal fills | −2,416 | −3,222 | −3,132 | **−3,645** | −4,215 |
| Worse fills | −2,764 | −3,167 | −3,076 | **−4,036** | −4,319 |
| Tickets (winning days) | 17 (3) | 17 (3) | 17 (3) | **17 (3)** | 14 (4) |

**What this means, plainly:**
- **Every version loses in 2023, in every quarter.** E03.1's signal did worse than 39 of 40 books that
  bought at random minutes.
- **The put advantage did not hold.** E03.2's puts lost Rs 1,982 over 7 tickets and its calls Rs 1,663
  over 10. Bigger puts lose more.
- 2023 is also the year every option-buying strategy in this system lost, including the F&O books on
  Nov 1. That year was calm and grinding, a hard market for option buyers.
- So E03.2's profit is a 2024–2025 result, not a proven edge.

**What changes:**
- E03.2 stays on paper only. No size increase, nothing toward real money.
- Its forward paper tickets (0 of 20 so far) are now the main evidence.
- The fixes (EN01, EN02) still matter: they make that paper record honest and complete.

## The five extra slots (EN06–EN10)

| Slot | What | Result |
|---|---|---|
| **EN06** | Paper sales can no longer reuse the same quote twice, even across restarts. The evening report shows real fills and assumed values apart. Messages can't be lost in a crash. December 7 rules are applied. | **Done in Dev**, shipping in tonight's release |
| **EN07** | Re-checked the 2023 test with the stricter "strikes present at that minute" rule the auditor asked for | Same result to the paisa. The 2023 loss is real. |
| EN08 | Skip calm mornings (the quietest third of days) | Failed. It halves the 2023 loss but ruins 2025, whose calm days were E03.2's best. No "type of day" explains when it earns. |
| EN09 | A different entry: breakout after a quiet spell | Failed. It lost every year, worse than picking the side at random. |
| EN10 | A one-lot ticket banks its gain earlier | Failed. Only 6 tickets in 3 years changed, mixed. |

**Bottom line:**
- E03.2 is unchanged and nothing tested beats it.
- 2024 earned, mostly from one day. 2025 earned a little. 2023 lost.
- The system now records paper results honestly, so each new expiry adds real evidence.
- What can genuinely move this forward is new data (below) and forward paper tickets.

## Fifteen more slots (EN11–EN25): ten from the auditor, five of mine

None beat E03.2, so it stays exactly as it is. Every slot's anatomy, where it won and where it lost, is in
[ANATOMY3.md](research/simulation/2026-11-17-expiry-en/ANATOMY3.md).

| Slot | Idea | What happened | Worth keeping |
|---|---|---|---|
| EN11 | Sell the moment the price touches the stop | Worse every year. Cheap expiry options dip through the stop and come back: 16 of 42 did within a minute. | Selling on the completed minute is right. |
| EN12 | At 2x, sell just enough to get the money back | Changed one ticket | The "keep a runner" rule paid only on the one big day (+8,903). On the other four 2x winners it cost 4,104. |
| EN13 | Trade sideways days: buy at the edge, sell at the middle | Lost every year | Nothing. The move to the middle is too small for an expiry option. |
| EN14 | Wait for the second push of a fast move | Lost in 2 of 3 years | Always better than chasing the first burst (+7,707 over three years). |
| EN15 | Watch the 50 stocks for an early lead | No lead at all | Not worth buying stock-minute data for this. |
| EN16 | Check the next week's options before buying | Agrees almost always, so it filters nothing | — |
| EN17 | Buy a call and a put on a sudden burst | 13 of 15 lost | Nothing |
| EN18 | Pick the cheaper strike next door | The cheaper strike always costs more per rupee (about double) | E03.2's strike choice is already the efficient one. |
| EN19 | One small late shot when the index leaves a strike | Lost in 2 of 3 years | Its few runners paid. |
| EN20 | Re-enter after a stop only if the move proves itself | Only one retry in three years | E03.2's existing retries are profitable. Keep them. |
| **EN21** (mine) | Buy half first, add the rest only once it rises 20% | Halved 2023's stop losses, but halved slow 2025 winners | The best "smaller loss when wrong" idea, but most of its gain is the one big day. |
| **EN22** (mine) | No stop at all, just the time and trend exits | About the same | The stop isn't the leak; the losing entries are. |
| **EN23** (mine) | Last-half-hour momentum (a known index effect) | 4 winners in 25 | Too small an effect for expiry options. |
| **EN24** (mine) | Only enter when futures volume backs the move | Removed the 2024 big day | Volume is not a quality signal here. |
| **EN25** (mine) | Wait at the bid instead of paying the ask | About even normally; much better when fills are bad | A safety idea to measure on real quotes. |

**Bottom line:**
- Every exit idea (faster stop, no stop, smaller runner) and every entry filter (volume, calm mornings) either moves money from one year to another or removes the one big 2024 day.
- E03.2 loses on wrong entries. None of these fifteen fixes that.
- Only fresh data can move this forward: SENSEX, NIFTY 2026, and forward paper tickets.

## The fresh test you arranged (Nov 18): NIFTY 2026 and SENSEX, plus EN26–EN40

The new data is NIFTY's expiry afternoons from Jan to Sep 2026 and SENSEX's from Jul 2025 to Sep 2026. No study had touched them before. Everything was frozen before scoring and scored once. Every slot's wins and losses are in [ANATOMY4.md](research/simulation/2026-11-17-expiry-en/ANATOMY4.md).

**E03.2 failed its first fresh test:**

| | Result | Tickets | Without its best day |
|---|---:|---:|---:|
| NIFTY 2026 (36 expiries) | **−3,847** (random entries lost less: −961) | 9 (2 winners) | −3,917 |
| SENSEX (58 expiries) | **+2,082**, all from one put on Nov 13, 2025 (+5,255) | 11 (3 winners) | −3,173 |

- **Over all 248 expiry afternoons we hold** (NIFTY 2023–26 and SENSEX), E03.2 made +16,107. **Two tickets made all of it.** The other 74 lost −918 together.
- **It is a lottery on rare put days, not a steady earner.** Its losses are stop-outs and entries after 14:30.
- **Size:** the risk check says do not increase it. Even at today's size, the chance of a losing year is above 60%.

**The fifteen new slots: none passes, so nothing changes.**

| Slot | Idea | What happened |
|---|---|---|
| EN26 | Sell early only when the damage is confirmed | Happened once in 248 days. The normal stop already does this job. |
| EN27 | Buy half first; add only when it proves itself | Wrong trades lost half as much (+3,793 saved), but slow winners earned less (−4,789). Better than E03.2 on both fresh books, worse in 2024–25. |
| EN28 | Wait at the bid, with one capped retry | Same trades, 0.5% cheaper, about the same money. Passed on SENSEX, not on NIFTY. Real fill rates need our depth recorder. |
| EN29 | Sell the leftover "runner" when the move stalls | Kept the 2024 big day and trimmed giveback. Only 6 cases, too few to judge. |
| EN30 | Second wave: enter on a held pullback, not a breakout | Better than chasing in 2023–25, but no better than random on fresh data. |
| EN31 | After a stop, flip only if the market proves the other side | Happened once. Flipping blindly is a coin toss. |
| EN32 | Range trades with at-the-money options | Losses cut by 20–99%, still losing, and rarely affordable. |
| EN33 | NIFTY futures lead SENSEX | True by about a minute, but too small to pay option costs. |
| EN34 | Buy next week's option instead | Not possible: one lot costs Rs 8,900–11,900 against a Rs 1,250–2,500 ticket. |
| EN35 | Combine the best pieces | Not eligible. As a check it was the best version on NIFTY 2026 (−2,355). |
| **EN36** (mine) | Buy only when options are cheap | Bad years far smaller, but the big days are skipped: they happen when options are already expensive. |
| **EN37** (mine) | The option flow must agree | Agrees almost always, so it removes nothing. |
| **EN38** (mine) | Futures must lead the cash | The steadiest version (worst year −2,442 against −3,847). Passed on SENSEX, lost on NIFTY 2026, skips the big days. |
| **EN39** (mine) | Trade only 14:00–14:30 | SENSEX +3,358 on 3 trades, NIFTY −705 on 2. Far too rare. |
| **EN40** (mine) | No double size on puts | The double is a bet on the big put day: it paid on SENSEX and cost on NIFTY. |

The four parts held over from the last round (EN21, EN25, EN14, EN12) did not hold on fresh data. The auditor's repairs to the quote harness left both old verdicts unchanged.

**Bottom line:**
- No rule found here earns steadily without big losses.
- Anything that cuts the losing trades also cuts the rare big winners, and nothing we measured can tell the big days in advance.
- E03.2 stays on paper exactly as it is, and nothing is deployed.
- Whether it remains the paper main on NIFTY after failing this test is your call.

## Round 5 (Nov 18): fifteen more slots, ten from the auditor and five of mine

Every expiry afternoon we hold has now been looked at, so this round can only screen ideas. Anything that survives must prove itself on the next expiries. Every slot's wins and losses are in [ANATOMY5.md](research/simulation/2026-11-18-expiry-en41/ANATOMY5.md).

**Nothing passed.** The three things that matter:

**1. The "learned E03.2" (EN55) is the only version that survives one continuous ₹30,000 wallet.** It is E03.2 plus waiting at the bid, buying half first and adding only when it proves itself, and selling the leftover when the move stalls. Each of these was learned in earlier rounds.

| NIFTY, 197 expiries | E03.2 | Learned E03.2 |
|---|---:|---:|
| Profit, each expiry on its own | +14,275 | +13,165 |
| With bad fills | −12,347 | **+991** |
| Worst expiry | −1,281 | −854 |
| **One continuous ₹30,000 wallet** | **−4,123, stopped by the brake from Jan 2024** | **+3,445, never stopped** |

- **SENSEX:** +2,470 against +2,449, with a smaller worst day.
- **Caveat:** it came within ₹387 of the brake. Its pieces were chosen on these same days, so it is registered for a forward test on the next 20 expiries per index ([FORWARD5.md](research/simulation/2026-11-18-expiry-en41/FORWARD5.md)). Nothing changes until that test is read.
- **Correction (Nov 18, before the first session):** the first forward sessions are SENSEX Nov 19 and NIFTY Nov 23 (Nov 24 is an exchange holiday), not Nov 20 and 24. 20 sessions will hold only about 7 NIFTY and 3 SENSEX trades, so they are a comparison only. Qualification now needs the first 40 expiries per index, at least 20 trades, and a profit at normal and bad fills ([ERRATA-20261118.md](research/simulation/2026-11-18-expiry-en41/ERRATA-20261118.md)).

**2. You are right that every expiry swings.** But the managed straddle (EN51: buy the call and the put at 13:00, sell at +25% or −25%) shows the decay usually comes first.
- NIFTY: it reached +25% first on 42 days and −25% first on 87.
- SENSEX: 14 against 20.
- It lost on both indices.

**3. The straddle that drops its losing leg (EN52) made the most on NIFTY (+16,554).** But it is the same lottery:
- −8,588 without its two best days;
- −32,962 with bad fills;
- −8,351 on SENSEX.

**The auditor's ten:**

| Slot | What happened |
|---|---|
| EN41, EN42 (order-book pressure) | Need depth data our recorder has only for two expiries, and not exported. |
| EN43 (weighted stocks) | No dated weights or second-level stock data. |
| EN44 (opening-range retest) | Lost on NIFTY mornings (−4,298), below random. |
| EN45 (failed break back to VWAP) | Lost on both indices (NIFTY −10,898). |
| EN46 (does the move pay the option) | Removed winners with losers. With no direction forecast it never buys at all. |
| EN47 (strike by response) | Under ₹1,250 almost no strike moves enough to pay its spread and order charges. |
| EN48 (RBI days) | Only one verified RBI decision fell on an expiry. |
| EN49 (small payoff model) | Over 13,700 real decisions it never forecast a profitable 3-minute trade. Spread plus two order charges are about 5–7% of a cheap expiry option. *Correction: its candidate list peeked at the next minute's fill and trained on one lot only. It never traded, so no result changed, but it tested one narrow model, not every short trade.* |
| EN50 (hold-another-minute model) | Changed only 3 trades. |

**My other four:**

| Slot | What happened |
|---|---|
| EN51 (straddle bracket) | Lost on both indices. |
| EN52 (straddle that drops its loser) | Lost: the lottery above. |
| EN53 (E03.2 with at-the-money options) | Lost: at-the-money tickets earned less from the few huge winners under that sizing. (At-the-money options can still multiply.) |
| EN54 (straddle only when cheap) | Lost on NIFTY; too few SENSEX trades to judge. |

**On the ₹30,000 and the 50% profit sweep:**
- The extra ₹5,000 changes nothing for NIFTY, because the brakes are rupee amounts.
- The sweep works: on SENSEX it banked ₹2,422 at the peak. Later losses reduce the wallet, and the swept money stays out.

**Bottom line:**
- The money on expiry afternoons is in a few big directional days.
- Every filter that avoids losses also avoids those days, except the learned E03.2's way of cutting losers.
- That is the one to prove forward.

## Order-book test on the recorder's data (Nov 18, after your go-ahead)

I copied the tick recorder's two finished days out of Production, read-only, and checked every file against its own hashes. Only Nov 17, the one expiry recorded so far, met the auditor's freshness rule.
- **Order-book pressure (EN41)** fired twice all day, and both trades lost. EN42 never fired.
- **On this feed (about one futures snapshot a second),** the order book shows nothing that the price doesn't already.
- **Do patient bids really fill? Probably, mostly, but this feed can't prove it.** Two different estimates gave 72–75% within 10 seconds and about 88–89% within a minute. These are model estimates, not confirmed fills: one-second snapshots don't show where each trade happened in the queue.
- **They seem to fill on the falling options:** a minute after the decision, the options marked filled were 2.1% lower than our bid, and the ones marked unfilled were 17.6% higher. This compares prices at a fixed time after the decision, not returns after an actual fill; round 6 measures it properly.
- Corrections: [ERRATA-20261118.md](research/simulation/2026-11-18-expiry-en41/ERRATA-20261118.md).

Details are in [ANATOMY5.md](research/simulation/2026-11-18-expiry-en41/ANATOMY5.md), round 5b.

## Round 6: the auditor's EN56–EN65 plus my five (Nov 18)

Frozen before scoring (`7c58df23`), scored once. Details are in [ANATOMY6.md](research/simulation/2026-11-18-expiry-en56/ANATOMY6.md).

**No new strategy passed, and E03.2 and EN55 stay as they are.** What we learned:

- **You're right that every expiry has a big opportunity, but only in hindsight.**
  - On 181 of 197 NIFTY expiries there was a trade inside ₹2,500 that made at least ₹1,250 after all charges.
  - But an average entry loses ₹60–190, direction over 5–30 minutes is right only 49.5% of the time, and the option still loses 40% of the time when the direction is right.
  - Picking the moment is the whole game.
- **More trades means more losses.**
  - A more active learned E03.2 (signals from 12:30, looser filter) took 3× the trades and turned +13,165 into −7,120: each extra trade lost about ₹149.
  - Stricter is better: the strictest version made almost the same profit with a third of the trades.
- **What really protects the learned E03.2 is buying half first.** That keeps the wallet alive.
  - Its patient entry only looks good because minute bars assume resting orders fill.
  - On real depth (Nov 17), patient orders filled on options that then fell about 4% in 3 minutes, and market orders did better.
  - If resting orders never filled, the learned E03.2 would lose −3,036.
- **Puts don't earn for a structural reason.** Their profit is the index falling on a few big days (+22,421), not volatility (−71).
- **One wallet for both indices is bigger, not steadier.** It stops at the ₹4,000 brake in May 2026, when both indices lost together.
- **The chance a fresh ₹30,000 book stops within a year** (replaying our history in random order):

  | Book | NIFTY | Both indices together |
  |---|---:|---:|
  | Learned E03.2 | 1.4% | 24% |
  | E03.2 | 6% | 49% |

  About one year in three ends at a loss.
- **The new entry ideas all lost**, mostly against a random side at the same times: sequential trend detection, option mispricing, price impact, a 15-minute payoff model. So did straddle packages and profit-funded extra trades.

**For the forward test that starts tomorrow:**
- It needs ICICI index and futures minutes for each expiry, because Breeze has no futures after Oct 28.
- The recorder's own bars aren't accurate enough yet to stand in (83% of option closes match, against the 95% required).
- Testing the patient entry honestly needs real resting orders: the live-paper choice you deferred.

## Data still open

The full list is in [DATA_REQUESTS.md](research/simulation/2026-11-17-expiry-en/DATA_REQUESTS.md).

1. **Next week's options on each NIFTY expiry day, 2023–2026** (near the money). This re-runs EN16 properly.
2. **1-minute bars for the 50 NIFTY stocks on expiry days** (from Kite, not ICICI).
3. **1-second data for the cheap strikes E03.2 buys, 2026.** EN11's speed check and EN26's confirmation need it.
4. **NIFTY 2020–2022 and SENSEX before July 2025.** More history for anything that survives.
5. **Index and futures minutes for every expiry from Nov 19** (ICICI). EN55's forward test needs them (new, round 6).

Real bid/ask depth can't be bought. It comes only from our own recorders, which I keep. EN28's fill rate and EN26 can only be settled there.

Technical record: [research/simulation/2026-11-17-expiry-en/README.md](research/simulation/2026-11-17-expiry-en/README.md).
