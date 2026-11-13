# SN116–SN120 (phase C): the combined learning, and what goes forward (Nov 13, 2026)

Frozen at `2a3683bd` (`PLAN.md`) after phases A and B, before any phase C scoring. Numbers in `results-*.json`; logs local.

**One line:** Gold v5's entries are a genuine edge: it beats all 400 random-entry versions of itself. Its research numbers hold up under measured costs. Extra money earns far more inside Gold than in any empty-day companion.

## Results

### SN116 — where should the next rupee go? (matched total capital, in-sample)

| ₹45k in total | Fixed | Growing, stop after 3 | Growing, stop after 5 |
|---|---:|---:|---:|
| Gold ₹30k alone (reference, ₹30k only) | 2,80,508 | 8,50,882 | 15,51,780 |
| Gold ₹30k + the straddle in Gold's wallet | 2,94,288 | 8,90,419 | 16,99,131 |
| Gold ₹30k + a separate ₹15k straddle sleeve | 2,97,653 | 8,68,027 | 15,68,925 |
| **Gold ₹45k** | **4,63,780** | **13,20,826** | **23,48,253** |
| Gold ₹45k, stepping after 50% profit | 4,63,780 | 15,00,260 | 30,78,045 |
| Worst day, Gold ₹45k (vs ₹30k) | −8,995 (−6,110) | −30,320 (−21,113) | −68,263 (−45,464) |

- At ₹50k total the picture is the same: growing, stop after 3, Gold ₹50k ₹14,70,693 vs Gold ₹35k + sleeve ₹10,07,493.
- **The straddle sleeve alone** (₹15k, refilled) made ₹17,145 in four years, with a ₹19,418 drawdown and ₹39,221 of refills.
- **Lesson:** the marginal ₹15k adds ₹4.70 lakh inside Gold against ₹17,145 in the best empty-day companion (about 27× more). On empty days the best use of money is to be ready for Gold's next signal.

### SN117 — Gold under the measured costs

- **The measured cost.** From the 22 Production paper trades with fresh quotes at both ends: about **₹175 per lot** (median ₹138) on top of the model's spread. The bootstrap 5–95% range is ₹69–275, against our flat ₹205.
- **Gold v5 at ₹30k growing (stop 3):**
  - 5th / 50th / 95th percentile: **₹7.95 / ₹8.75 / ₹9.80 lakh**;
  - at the point estimate with every entry 1 minute late: ₹8.42 lakh;
  - house figure ₹8.51 lakh, at ₹0 ₹11.07 lakh, at ₹400 ₹4.96 lakh.
- **Lesson:** the research figures sit at the middle of the realistic range. These are paper fills; real broker fills are the only remaining unknown.

### SN118 — real money, no refills (every monthly start Jan 2023 – Jun 2026, to Oct 28 2026)

| Start | Sizing equity | Median final multiple | Starts ending below start | Dead accounts | Worst final | Worst drawdown |
|---|---|---:|---:|---:|---:|---:|
| ₹30k | capped at ₹1,01,250 (realistic) | **24.6×** | **0 of 42** | **0** | ₹92,731 (Apr 2026 start) | **52.3%** |
| ₹50k | capped at ₹1,01,250 | 16.2× | 0 of 42 | 0 | ₹1,91,553 | 58.2% |
| ₹30k / ₹50k | uncapped | 309× / 284× | 0 | 0 | – | – |

- **The uncapped rows are not believable.** They compound to hundreds of lots, beyond the 6-lot depth SN109 measured.
- **The real risk:** a Jan 2023 start fell from ₹30,000 to **₹14,782** before recovering. A bad first year can halve the account even though no start ever finished below its stake.
- In-sample, and the 2023–2026 path only.

### SN119 — is Gold's edge real after all the selection?

Gold v5's full machinery was fed random entries, 200 draws each. `N1` keeps Gold's own days; `N2` uses random days.

| Wallet | v5 | N1 mean / 95th / best | N2 mean / 95th / best | v5 percentile |
|---|---:|---|---|---:|
| ₹15k | 1,51,155 | −54,403 / −7,058 / 26,320 | −60,456 / −6,739 / 51,397 | 100 / 100 |
| ₹30k sized | 2,80,508 | −95,797 / −1,871 / 91,168 | −1,00,037 / 5,275 / 1,10,563 | 100 / 100 |
| Growing from ₹15k (stop 3) | 3,99,906 | −54,799 / −5,852 / 49,701 | −62,247 / −5,230 / 71,791 | 100 / 100 |
| ₹30k growing (stop 3) | 8,50,882 | −1,04,512 / −2,239 / 1,60,177 | −1,10,467 / −6,830 / 2,45,436 | 100 / 100 |

- **Lesson:** Gold's money management on random entries loses about ₹1 lakh. **The profit is N11's entry timing and direction, not the exits or sizing** (consistent with SN02/SN04 and SN92).
- Even the luckiest of 400 random books makes less than a third of v5.

### SN120 — the scoreboard

`results-sn120.json`, printed by `sn120.py`, lists every SN91–SN119 candidate with its basis and verdict.
- Its SN118 line shows the *uncapped* multiple (309×); the realistic capped figure is 24.6× (above).
- **Passed:** nothing as a strategy change.
- **Confirmed as information:** SN101's volatility persistence (p = 0.002).
- **Confirmed as facts:**
  - SN109 / SN115 / SN117: costs are realistic;
  - SN119: Gold's entries are a genuine edge.

## The forward plan (frozen here)

1. **Production stays as it is:** SN Gold v5 paper, ₹30k, step after 100% profit, stop after 3 (`82b08371`). Its forward check is `docs/research/fno/sn-gold/FORWARD_V5.md` (≥ 20 trades, net > 0 and > 0 without the best trade).
2. **Watch only:**
   - **SN95-L** (frozen in `../2026-11-13-sn92/README.md`), scored offline from Production's quote archive once ≥ 20 signals exist (about 2 years at 9–12 a year).
   - No module and no money. If it passes, it goes as a *separate* sleeve, never inside Gold's wallet (SN110 / SN116).
3. **The owner's levers** (measured, in-sample; each is a choice of risk, not a signal):

   | Lever | ₹30k growing, stop 3 | Worst day | Notes |
   |---|---:|---:|---|
   | As deployed | ₹8.51 lakh | −₹21,113 | – |
   | Start ₹45k | ₹13.21 lakh | −₹30,320 | – |
   | Start ₹50k | ₹14.71 lakh | −₹33,689 | – |
   | Step after 50% profit | ₹9.48 lakh | Same | `SN_GOLD_STEP_TRIGGER=0.5`, the owner's word only |
   | Stop after 5 | ₹15.52 lakh | −₹45,464 | – |

   - Real money without refills can fall about 50% in a bad first year.
4. **New information, in order of value:**
   1. small real-money broker fills, to replace the paper-fill cost estimate (owner's decision, real money);
   2. NIFTY next-week expiry minute history, for the straddle watch (SN103: half the decay per rupee), via the Breeze skill on the owner's word.
   - Not justified by the evidence: BANKNIFTY options (SN105), 1-minute constituents (SN96), order-book capture (SN108).
5. **Gold v6** needs the SN110 bar:
   - ≥ 15% more net at matched capital;
   - no worse drawdown or worst-5%;
   - robust at ₹400 and late entries;
   - then a forward pass.

   Nothing in SN91–SN120 reached it.
