# SN92–SN100: the other agent's ideas, built and tested (Nov 13, 2026)

**Owner:** "develop that, test it for various fixed or growth wallets, wallet limits, wallet caps, various starting amounts ... and let's see if it improves drastically the current Gold."

**Answer: nothing improves Gold drastically. Gold v5 stays as deployed. Every new empty-day strategy loses held out, and adding any of them to Gold's account makes it worse. One thin lead (SN95, a cheap straddle at 10:00) is positive held out but rests on five days.**

- Plan and scripts frozen before any scoring: `b4295b1c` (`PLAN.md`). Every result below comes from that frozen code; the numbers are in `results-*.json` (the console logs stay local in the git-ignored `logs/`).
- `levers.py` (the money-lever table and the SN95 lead description) was written after scoring. It is description only and chooses nothing.
- Shared harness `common.py` reproduces Gold v5 exactly at every wallet (₹1,51,155 / ₹1,76,846 / ₹2,80,508 / ₹3,99,906 / ₹7,41,675).
- **Costs:** Zerodha charges + ₹205 per lot per trade. Multi-leg structures: ₹100 per leg-lot (house) and ₹205 (strict). One position at a time; 20% day limit.
- **Testing:** choose on 3 years and score the 4th (LOYO), against controls run the same way. Research only: no runtime, Production or broker change.

## Results

| SN | Idea (from the proposal / review) | Held-out result | Controls (same procedure) | Verdict |
|---|---|---:|---|---|
| 92 | Where the money goes (description) | – | – | See below |
| 93 | Slow up-drift calls: persistent 15-minute progress, rising futures VWAP, shallow pullback, buy the reclaim | **−₹49,898** (all 4 years negative) | Random days at the same clock −₹10,599; random side −₹76,128; plain calls −₹2,04,046 | NOT PROVEN. The drift filter picks *worse* days than random |
| 94 | Confirmed failed breakout of the opening range, traded back toward the middle | **−₹86,916** (4/4 negative) | Unconditional fade −₹1,69,200; random side −₹98,635 | NOT PROVEN. Confirmation halves the fade's loss but still loses |
| 95 buy | Buy the ATM straddle when options look cheap against the day's realised movement | **+₹23,518** Gold-free days (35 trades), **+₹37,971** all days (47) | Random admission −₹29,556; every day −₹1,76,062 | NOT PROVEN: 2 of 4 years positive; **−₹16,930 without its best 5 days**; +₹4,574 at ₹400/leg |
| 95 sell | Sell an iron fly when options look rich | **−₹1,15,649** | Random admission −₹1,04,360 | NOT PROVEN (as SN77) |
| 96 | The 50 stocks inside NIFTY: breadth, agreement, banks vs the rest, concentration (15-minute bars, Feb–Oct 2026) | Information test: adding components made the next-30-minute forecast **0.43% worse**; residual breadth correlation +0.009 (95% interval −0.040 to +0.060) | Trading rules −₹25k to −₹41k: no better than index-only rules (−₹3k to −₹38k) or random sides (−₹28k to −₹42k) | NOT PROVEN. No direction information |
| 97 | Futures volume: Gold's lots, companions' confirmation; event days | Companions: SN93 −₹47,126, SN94 −₹19,605. Events (description): Gold made +₹2,297 on 4 RBI-day trades, +₹1,813 on 3 Budget-day trades | Random side −₹13,066 / −₹12,023 | NOT PROVEN. It only trades less |
| 98 | Expiry mornings priced (straddle / leg when cheap, exit 13:00) | Pick −₹16,757 | Random pick +₹291 | NOT PROVEN |
| 99 | Gold's lots: by setup, drop a setup, option cheapness, India VIX, futures volume, one deep lot | C ₹2,84,020 vs v5 ₹2,80,508; growth ₹4,06,098 vs ₹3,99,906 | At +₹400 the ₹30k pick falls behind v5 (₹1,61,768 vs ₹1,88,792); 1 minute late both fall behind | NOT PROVEN. v5 sizing stays |
| 100 | One shared account: Gold + companion | ₹30k growing (stop 3): Gold alone **₹8,50,882**; + SN93 ₹6,29,808 (**−₹2.21 lakh**); + SN94 ₹3,23,236 (**−₹5.28 lakh**) | – | Gold alone is best |

### SN92: where the money goes

**Gold v5 at ₹15k (140 trades, +₹1,51,155):**
- Costs: the ₹205/lot slippage stress ₹28,700, charges ₹10,742, spread ₹4,509.
- Additions: scale-ins +₹23,212, the extension +₹2,073. The best 5 trades are ₹59,291 (39%).
- By setup:

  | Setup | Trades | Net | Notes |
  |---|---:|---:|---|
  | TPB | 92 | +₹74,840 | Puts +₹67,431 |
  | EFF | 22 | +₹45,340 | – |
  | OR20 | 13 | +₹28,555 | Puts +₹27,202; calls weak (−₹11,421 at ₹30k) |
  | SHIPPED | 13 | +₹2,420 | +₹17,457 at ₹30k |

- R0.85's extra entries: 4 trades, +₹11,482.

**The empty-day opportunity map (517 Gold-empty sessions):**
- Buying the ATM call or put at 09:45, 10:30, 12:00 or 13:30 and holding 30 minutes to 15:10 loses ₹111–476 per lot on average. A straddle loses ₹525–697.
- The movement is there: the index moves 23–93 points against a cost hurdle of about 9 points. The direction is not: even the right side in hindsight pays only 63–76% of the time.
- Gold's own ADX ≥ 30 days look the same at fixed clocks (−₹131 to −₹629). Gold's edge is its entry timing, not the type of day.

### Gold's money levers (`levers.py`, in-sample, v5's per-lot rules in every row)

Net at the end (worst day):

| Start | Day limit | Step after 100%, stop 3 | Step after 50%, stop 3 | Step after 100%, stop 5 | Step after 50%, stop 5 |
|---|---|---:|---:|---:|---:|
| ₹15k | 20% | 3,99,906 (−10,119) | 4,54,692 (−10,119) | 7,41,675 (−22,740) | 9,60,885 (−22,740) |
| ₹20k | 20% | 5,36,968 (−13,492) | 6,53,133 (−13,492) | 10,04,746 (−30,320) | 13,53,208 (−30,320) |
| **₹30k (deployed)** | **20%** | **8,50,882 (−21,113)** | 9,47,841 (−21,113) | 15,51,780 (−45,464) | 20,24,800 (−45,469) |
| ₹50k | 20% | 14,70,693 (−33,689) | 16,86,732 (−33,689) | 26,41,440 (−75,794) | 34,43,885 (−75,794) |
| ₹30k | 15% | 6,45,200 (−15,182) | 7,57,379 (−15,182) | 10,82,643 (−34,273) | 14,90,843 (−34,273) |
| ₹30k | 25% | 8,54,633 (−25,298) | 9,67,949 (−25,298) | 15,38,561 (−56,906) | 20,30,938 (−56,906) |
| ₹30k | 30% | 9,54,281 (−30,360) | 10,11,097 (−30,360) | 17,62,679 (−68,291) | 21,78,118 (−68,314) |

Reading the table:
- **Starting money:** profit scales with it.
- **Growth step after 50% profit:** about +11% with the same worst day. The owner's switch is `SN_GOLD_STEP_TRIGGER=0.5`.
- **A 15% day limit** costs a quarter of the profit.
- **A 25–30% limit** adds little at ₹15–20k and raises the worst day. SN57 found 30% worse held out, so 20% stays.

## What this settles about the proposal and review

- **The component data exists.** The review assumed no intraday constituent panel. One does exist (Kite 15-minute Jan–Jul 2026, Production 15-minute Aug–Nov), and SN96 tested it.
  - The fitted weights match NIFTY's real ones: HDFC Bank 12.1%, Reliance 9.2%, ICICI 8.2%, Airtel 4.0%, L&T 3.9%.
  - At 15-minute resolution the stocks carry no next-15/30-minute direction beyond NIFTY's own move. A 1-minute constituent test would need a new download.
- **The pricing idea is the only one with a held-out profit.** Movement against the option price (SN95) is the only idea in SN76–SN100 with a positive held-out result that beats its controls. Its picks were the same rule in every fold. It still fails the frozen bar on years and the best-5 check, so it is a forward-watch item, not a strategy.
- **Untested for lack of data:** BANKNIFTY options, GIFT Nifty and global cues, and order-book depth. None is in the repo. Each would need a download on the owner's word, through the `breeze-history-download` skill for ICICI.
- **Fill mechanics:** the review's notes (same-second entries, gap stops in SN78, the stale-price fills in SN77) do not change these results.
  - SN93–SN100 use the minute harness: gap-through stops, printed-minute entries, and a 1-minute-late check.
  - SN95 marks multi-leg positions at closes, with a 5-minute stale-price guard on the implied-volatility input.

## The one lead, written down before any future data (forward watch, not a module)

**SN95-L, frozen here:**
- **Days:** Gold-free days (yesterday's ADX < 30).
- **Entry:** at 10:00, R_today (σ of 1-minute index returns since 09:20 ÷ the ATM straddle's implied per-minute σ, overnight allowance 125 minutes) is at or above the 80th percentile of all earlier sessions at 10:00.
- **Trade:** buy the ATM straddle, 1 lot each leg, hold to 15:10, ₹3,000 day limit.
- **Pass:** at ≥ 20 trades after Nov 13, 2026, net > 0 at ₹100/leg AND net without the best trade > 0.
- **Timing:** about 9–12 trades a year, so this is a 2-year check unless scored on new history (Jan–May 2022 stays sealed for its own exam).

## Commands

`python-engine\winvenv\Scripts\python.exe docs\research\fno\2026-11-13-sn92\sn9X.py` (each scorer refuses to run twice). `levers.py` reruns freely.
