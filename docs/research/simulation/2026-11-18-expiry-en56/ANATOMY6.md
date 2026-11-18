# EN56–EN70: where each slot won and lost

Scored once on Nov 18, 2026 by `en_score6.py` under `PLAN6.md`, which was frozen at `7c58df23` before any score.
- **Outputs:** `results6.json`, `anatomy6.json`, `results6-started.json`.
- **Tables:** `ANATOMY6-tables.md`, rendered by `render6.py`.
- **After the score:** one reporting fix, `post6_en58.py` → `post6-en58.json`. It reruns the same frozen, deterministic code; EN58's fill markouts had come out as NaN because of missing quotes.

**Books:** NIFTY 197 expiry afternoons (2023 – Oct 2026) and SENSEX 63 (Jul 2025 – Oct 2026), plus NIFTY Nov 17 from recorder packets. All are seen, so everything below is **development screening**.

**How to read the figures:**
- **Fixed-cap:** each expiry runs on its own.
- **Wallet:** one continuous Rs 30,000 book, brakes on the trading high-water, 50% of profits swept out.
- Rupees are net after every fee at ordinary fills unless stated.

## The answer first

**No new strategy passes, and nothing replaces E03.2 or EN55.**
- **Strategy primaries (18 Holm tests):** each is FAIL or INCONCLUSIVE on each index; every Holm-adjusted p = 1.0.
- **Diagnostics:** all five are answered. EN70 is PARITY NOT ESTABLISHED.

**Five findings that matter for money:**

**1. Your point is right in hindsight: nearly every expiry offers a big trade (EN56).**
- **The opportunity exists:** in a fixed library of ATM, ITM1, OTM1 and OTM2 contracts every 5 minutes from 12:30 to 14:30, at least one trade inside Rs 2,500 would have made **≥ Rs 1,250 after every fee on 181 of 197 NIFTY expiries** and 58 of 63 SENSEX expiries.
  - The median best trade was Rs 3,405 (NIFTY) and Rs 3,695 (SENSEX).
  - Only 12 of those NIFTY best trades first fell 35%.
- **Picking it in advance is the problem:**
  - **Every** cell of the library loses on average: about −Rs 60 to −190 a trade at Rs 2,500.
  - It loses even before fees (gross −10 to −139), and even with the spread removed.
  - The direction is right 49.5% of the time, a coin flip.
  - When the direction *is* right, the option still loses 40% of the time.
  - Most trades pass through a profitable moment (61–81% are net-positive at some minute) and then give it back.

**2. E03.2's selection is worth something, and its selectivity is the whole value (EN56, EN67).**
- **At its own minutes:** E03.2's minutes and side make **+Rs 38** a trade at the 8-minute horizon (NIFTY, Rs 2,500, n = 176). A random side at the same minutes makes −40, and the unconditional grid −79.
- **More activity costs (EN67):** loosening it costs money at every step. EN55 with signals from 12:30 and efficiency 0.6 (`EN55_ACTIVE`):
  - **NIFTY:** 204 tickets, −7,120, against EN55's 68 tickets and +13,165. The 136 extra tickets lost **Rs 149 each**.
  - **SENSEX:** 31 extra tickets lost Rs 78 each.
- **The frontier is monotone.** NIFTY net at a 13:00 start:

  | Efficiency | Net | Tickets |
  |---|---:|---:|
  | 0.5 | −23,616 | 274 |
  | 0.6 | +129 | 166 |
  | 0.7 (EN55) | +13,165 | 68 |
  | 0.8 | +12,464 | 24 |

  A 12:30 start is worse at every level except 0.8.
- **What "active" means here:** the trades a more active E03.2 adds are, on average, losers.

**3. EN55's continuous-wallet survival is mostly the scout plus luck of path, and it depends on resting bids filling (EN57).** The eight-arm factorial on NIFTY:

| | Fixed-cap ordinary | Severe fills | Wallet | Halts? |
|---|---:|---:|---:|---|
| E03.2 | +14,275 | −12,347 | −4,123 | Jan 18, 2024 |
| + stall runner only | +15,952 | −12,347 | −4,123 | Jan 18, 2024 |
| **+ scout only** | +12,434 | −8,784 | **+12,918** | never |
| + patient entry only | +14,121 | +2,205 | −4,243 | Jan 18, 2024 |
| EN55 (all three) | +13,165 | +991 | +3,445 | never |

- **The scout keeps the wallet alive:** half-first entries keep the wrong entries small (worst expiry −793 against −1,281), so the drawdown stays under the Rs 4,000 halt until the March 28, 2024 hero.
- **The patient entry protects only against the severe-fill stress.** As the audit noted, that stress prices aggressive buys at the bar high but resting bids at their fixed price.
- **EN55 depends on resting bids filling:**
  - **No resting fills at all:** EN55 makes **−3,036**.
  - **Resting bids fill only when the option later falls:** **−9,590**, and its wallet halts on Mar 7, 2024.
  - Under the auditor's rule, that makes EN55's advantage **execution-unidentified**.
- **The wallet result is path luck around the halt:**
  - One extra adverse tick *raises* EN55's wallet to +12,631. One bar of extra delay raises it to +23,957.
  - E03.2's wallet halts only if it starts in Q1 2023. Started from Q2 2023 it ends at +16,422 and never halts.
- **Recent sessions lose:** both books lose on everything since Q4 2025 (E03.2 −2,780, EN55 −1,679 from Oct 2025).

**4. On real depth, patience lost to aggression (EN58, one session).** On Nov 17's 50 one-lot test orders:
- **The 60-second resting bid:**
  - It filled 44 and saved about 0.2% of price.
  - The options it filled on then fell **3.8% within 3 minutes**, while the ones it missed rose 27%.
  - Total: **−1,658**.
- **Market orders:** filled 48 and fell only 0.6%. Total: **−81**.
- **EN58's switch:** −2,797 to −3,352.
- **EN55's one real intent that day** (a 14:00 call) made +391 resting, +349 at market and +346 on the switch.
- **The consequence:** a minute-bar replay cannot settle EN55's patient entry. Only real resting orders (live paper) or recorder depth can.

**5. The put edge is direction on a few days, not a structural tailwind (EN69).** E03.2's NIFTY puts, decomposed:

| Component | Rupees |
|---|---:|
| Index move | +22,421 |
| Time decay | −5,918 |
| Implied-volatility change | **−71** |
| Fees | −1,634 |
| **Net** | **+14,844** |

- Across 25,000 library trades, implied volatility barely moves in 8 minutes. It rises about 0.2 points when the move goes against the option, for calls and puts alike, and is flat when it goes in its favour.
- **The consequence:** there is no evidence that puts earn for a structural reason. The 2× put size rests on a few big down days.

## The auditor's ten

| Slot | Result | Where it won / lost |
|---|---|---|
| EN56 opportunity map | **ANSWERED** | Above. Fees are about Rs 49–52 a round trip, and slippage Rs 6–18. On recorder depth (Nov 17), packet-walked fills came out Rs 2–4 *better* than the minute-bar proxy (correlation 0.998), so the bar spread model is slightly conservative. |
| EN57 EN55 attribution | **ANSWERED** | Above. On matched NIFTY tickets EN55 differs from E03.2 by only −88: −2,088 from the scout's half size, +2,192 from prices and exits, −192 fees. It added 3 tickets (−1,007). Hero days are Mar 28, 2024 and Aug 7, 2025. Without both, E03.2 makes +652 and EN55 +1,045. |
| EN58 patience or aggression | **INCONCLUSIVE** (one session) | Above. Aggression beat every patient variant on the test grid. |
| EN59 whole-straddle package | **INCONCLUSIVE** (7 affected pairs) | Inside Rs 2,500 the pair fits on only 21 of 197 NIFTY expiries and **no** SENSEX expiry. Package −5,969, against EN52 at the same cap −415. 16 of the 21 pairs hit the joint stop (−8,452); its 4 leg-outs made +1,849. Every Rs 2,500 straddle variant loses. **Retire the straddle family under this funding.** |
| EN60 sequential detection | **FAIL** | NIFTY −9,777 on 159 tickets against `E032_env` +1,567. A random side at its triggers has a median of −13,885 (p90 −1,045). Its 14 2× halves made +35,315; 46 stops lost −35,381; 51 reversal exits lost −17,769. Calls +14,054, puts −23,831. SENSEX −3,623. The 5-minute-range control lost −22,351. |
| EN61 15-minute payoff model | **FAIL** (NIFTY), **INCONCLUSIVE** (SENSEX) | It predicts *which outcome* is likely better than base rates (NIFTY log loss 0.985 against 1.046), but not *which trades pay*: its top decile realised −7.4% against −6.2% for the bottom. It traded 39 times: 20 losses −9,874, 8 wins +8,094, 11 timeouts +1,168. Net −612 (adverse −4,065), against the equal-envelope E03.2 control's +7,220 on the same 2024–26 sessions. The four controls traded 0–1 times. |
| EN62 option-specific relief | **FAIL** (NIFTY), **INCONCLUSIVE** (SENSEX) | NIFTY −16,264 on 94 tickets, **worse than a random side** at the same times (median −10,665). Direction alone lost −22,546; decay-only −3,148 (28 tickets). 32 premium stops −25,041; 10 residual targets +8,660. |
| EN63 liquid contract, 15 minutes | **FAIL** (NIFTY), **INCONCLUSIVE** (SENSEX) | NIFTY +282 against the native one-lot control's −2,084. But adverse −2,695, a worse worst expiry (−1,022 against −647), and its wallet halts (Apr 28, 2026). **The 2 × 2:** the liquid contract helped (+3,984 at 8 min, +3,238 at 15 min); the longer clock hurt (−872 native, −1,618 liquid). The best cell was the liquid contract at 8 minutes (+1,900; adverse −875). |
| EN64 price impact | **FAIL** (NIFTY), **INCONCLUSIVE** (SENSEX: no usable futures volume) | NIFTY −11,906 on 166 tickets, worse than a random side (median −5,505). Magnitude-only lost −27,282, volume-only −29,835. 72 efficiency exits lost −16,537; 8 2× halves made +18,693. |
| EN65 bank the core, profit-funded tail | **INCONCLUSIVE** (6 affected) | All 6 children hit their stop (−922). Banking the whole core at about 2× (6 tickets, +9,886) gave up the tail that E03.2's native half-and-runner keeps (6 tickets, +13,216). **Keep the runner; don't reset into a child.** |

## My five

| Slot | Result | Where it won / lost |
|---|---|---|
| EN66 one wallet for both indices | **ANSWERED: bigger, not steadier** | Jul 2025 – Oct 2026, 126 sessions. E03.2 combined +5,480 but **halts from May 5, 2026**; EN55 +4,754, halts from May 26, 2026. The separate wallets made +3,047 and +4,454. Only about 0.4 tickets a week: 10 weeks won, 9 lost, 44 flat. With rupee brakes, two indices losing together in 2026 reach the halt sooner. |
| EN67 what more activity costs | **FAIL** | Above: Rs 149 lost per added NIFTY ticket, and a 69% chance of a halt within a year. |
| EN68 probability of a halt | **ANSWERED** | One year of resampled seen sessions; see the table below. |
| EN69 why the puts earn | **ANSWERED: direction, not volatility** | Above. |
| EN70 recorder minute bars | **PARITY NOT ESTABLISHED** | Volumes match exactly (median ratio 1.00), and closes agree exactly on most bars (99.7% under Rs 5). But only 83.2% agree within Rs 0.10 overall (56% at Rs 20–100): one snapshot a second misses a minute's last trade. Breeze has **no NIFTY futures after Oct 28** and no index minutes for Nov 17, so the recorder's futures and index cannot be checked. Decisions on Nov 17 were identical: one 14:00 call for both E03.2 (+430) and EN55 (+476). |

**EN68: the chance a fresh Rs 30,000 book halts within a year** (2,000 policy replays of seen sessions, in blocks of 4 expiries):

| Book | NIFTY | SENSEX | Both indices in one wallet |
|---|---:|---:|---:|
| E03.2 | 6.1% (year-end loss 31%) | 15.8% (46%) | 49.2% (47%) |
| EN55 | **1.4%** (30%) | 4.3% (43%) | 24.4% (34%) |
| Equal-risk E03.2 | 0% (34%) | 0.4% (65%) | 8.2% (51%) |
| EN55_ACTIVE | 69.2% (83%) | 51.7% (57%) | 83.2% (63%) |

- EN55 on NIFTY: median year +1,615, 5th percentile −2,652, 95th +12,911.
- About one year in three ends at a loss, for every book.

## What this round taught

1. **The opportunity is real; the selection is the whole game.** Almost every expiry has a ≥ Rs 1,250 trade in hindsight, but an average decision loses Rs 60–190, and direction at 5–30 minutes is a coin flip.
2. **More trades means more losses.** Every loosening of E03.2 adds tickets with negative value. Being active is not the problem to solve; being selective is.
3. **The scout (half first) is the protection that works.** It keeps wrong entries small and the wallet alive.
4. **The patient entry's benefit cannot be verified on minute bars.** On real depth (one session), resting bids fill on the options that then fall.
5. **Nothing structural favours puts.** The put weighting is a bet on a few big down days.
6. **New entry ideas lose against a random side at the same times:** CUSUM detection, option residuals, price impact, a 15-minute model. So do straddle packages and profit-funded children. These families are closed under this funding.
7. **The continuous wallet is path-dependent around the halt:** one tick or one minute flips it. Judge books on fixed-cap results, worst days and halt probability, not on one wallet path.

## What changes now

- **Strategy:** nothing. E03.2 stays the paper main; EN55 stays registered for its forward test (`FORWARD5.md` + `ERRATA-20261118.md`), unchanged.
- **Data request (the forward test needs it):**
  - Breeze **index and front-future** 1-minute candles for every expiry session from Nov 19, alongside the chains. The recorder can't yet stand in for them (EN70).
  - The SENSEX futures minutes are too thin for EN64-type work.
- **For the owner, when ready:** EN55's patient entry can only be tested honestly with real resting orders, i.e. the live-paper mode you deferred, or recorder depth on each session. A minute replay will repeat round 5's assumption.
- **Hypotheses only, each needing its own registration before any test (I am not proposing them as strategies):**
  - E03.2 with the scout alone;
  - E03.2 at efficiency 0.8: 24 NIFTY tickets, +12,464, but two days carry it;
  - the liquid one-lot contract at 8 minutes.
