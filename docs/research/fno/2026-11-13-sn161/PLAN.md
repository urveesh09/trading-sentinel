# SN161–SN185: the daily wage — frozen plan (Nov 13, 2026, written before any score)

## The owner's goal (Nov 13, evening)

> "the main goal of starting the whole SN series was not yearly return. It was a daily 10% target … a kind of a daily wage situation … ₹1500 in futures and options never felt that hard … Gold V5 is truly satisfactory … but the number of trades are so peaceful that … if this system is sent to somebody who is living on a daily wage, they will never be able to live … who said that for ₹15,000 we only had to buy one lot. You can try some cheaper futures and options … I allow you to train on that … 5% or 3% you keep for testing the latest data … every single day be it a trending day or a sideways day … if the system knows when to enter and when to exit the system will learn … different starting prices … in a micro and macro level we are profitable … a smart trading Sentinel, not just a filtering system."

**The question for SN161–SN185:** can the system earn a wage — **+10% of the wallet (₹1,500 on ₹15,000) on most trading days** — and keep more than it loses, at the day level (micro) and the year level (macro)?

## Data and the split (the owner's rule)

- **Sessions:** 742 NIFTY non-expiry sessions with minute options, 2023-01 … 2026-10-28 (`ph.sessions()`, the SN lab; fill model, charges and stops as in `docs/SN_TESTING_PROCEDURE.md`).
- **TEST = the latest 5%:** the last 37 sessions, **2026-08-20 … 2026-10-28**. Scored **once**, by the frozen SN181 script, after every pick is frozen.
- **DEVELOPMENT = the other 705 sessions:** 2023-01-02 … 2026-08-19. All training, tuning and choosing happen here, with leave-one-year-out (LOYO) inside development where a choice is made.
- **Honest limit:** 2026 was seen by earlier SN rounds, so TEST is a time-ordered hold-out, not unseen data. With 37 sessions its intervals are wide. The fair judges remain the forward paper record (tick recorder from Nov 16) and, with the owner's word, the unseen SENSEX Oct 2024 – Dec 2025 data.
- Other layers used: 1-second archives (Apr 6 – Nov 12 2026; TEST = their latest 5% of days), the real-quote archive (Sep 10 – Nov 11 2026), N11/Gold v5 day nets (SN110 player, v5 parity proven), E-series expiry-day results (in-sample only).

## Definitions (fixed)

- **Wage day:** the day's net ≥ +10% of the day's starting wallet (₹1,500 at ₹15k). **Red day:** net < 0. **Flat day:** no trade.
- **Wage lock:** once the day's realised net reaches the wage, the day stops (the owner's SN01 rule). **Day limit:** −20% of the wallet (₹3,000 at ₹15k), as SN01.
- **Money:** Zerodha charges on every leg (`fno_costs`), +₹205 per lot per trade (house stress); sensitivity at ₹100 and ₹400 per lot; 1-minute-late entries. Fills: ask in, bid out (P75 half-spread model), stop on the bid low (ties go to the stop), target as a limit on the bid high.
- **Lots:** as many as the wallet buys at the ask (the owner: "who said … only one lot"), unless a study fixes it.
- **The null (always matched):** the same exits, the same days, the same number of trades, with a random entry minute (09:30–14:30) and a random side; 2,000 draws; its mean and 95th percentile.

## The pass rule for a wage candidate (all must hold)

1. TEST net > 0 at ₹205 per lot and above the matched null's 95th percentile.
2. TEST wage-day share above the null's mean wage-day share **and** TEST net > 0 (hit rate alone is not money).
3. TEST net > 0 at ₹400 per lot and with entries 1 minute late.
4. TEST net without its best 2 days > 0.
5. Where a rule was chosen in development: its LOYO held-out sum > 0 with ≥ 3 of 4 development years positive.

A pass means **paper candidate only**. Real money needs the forward record and the owner's word.

## The 25 studies

### Phase P1: the wage arithmetic (SN161–SN165)

| SN | Study | What it measures / decides |
|---|---|---|
| 161 | **Wage calendar of today's system** | Gold v5 day nets (₹15k 1 lot, ₹30k production sizing), SN95-L and SN126-L on the same calendar: wage / red / flat days per month, monthly sum, by development year (TEST in SN181). How far today's system is from a daily wage. |
| 162 | **Seen vs kept** | For every session, 1 lot ATM CE, ATM PE and the random side bought at 09:20: the day's best net (peak) against the 15:10 net. Share of days a position *touched* +₹1,500; share where it was *kept*. Explains the partner's mid-morning +₹6–7k. |
| 163 | **The coin-flip wage trader (the null, in full)** | Random minute and side, ATM, max lots, wage lock; target +₹1,500 / +₹750; stop −₹750 / −₹1,500 / −₹3,000; 1, 2 or 3 attempts a day. Wage-day share against net per year. |
| 164 | **Cheaper contracts** | The same wage lock on ATM, 1–4 strikes OTM (max lots), and a 1-lot debit spread (ATM / ATM+2): random entries and a fixed momentum entry (15-minute range break). Which shape gives the best wage profile, and what costs eat per rupee. Futures margin noted (no NIFTY future fits ₹15k). |
| 165 | **Capital ladder** | ₹15k, ₹30k, ₹50k, ₹1 lakh with a fixed ₹1,500 wage vs a 10% wage, on the SN163/164 best shapes: how the wage share and the net move with capital. |

### Phase P2: learning when to enter and exit (SN166–SN170)

| SN | Study | Rule |
|---|---|---|
| 166 | **Triple-barrier dataset** | Every minute 09:30–14:45, four actions (ATM CE, ATM PE, 2-OTM CE, 2-OTM PE, max lots at ₹15k): which comes first, +₹1,500, −₹1,500 or 15:10, and the net. Base rates by minute, action, weekday, gap and volatility (development only). |
| 167 | **Wage classifier (LightGBM)** | SN131's 44 features + 4 new (minutes left, RV forecast ratio, opening-range width, the day's realised net so far = 0 at first trade). P(+₹1,500 first) per action. Quarterly expanding retrain inside development; threshold θ ∈ {0.40, 0.45, 0.50, 0.55, 0.60} chosen on development's walk-forward; final model trained on all development, scored once on TEST. One trade a day (wage lock), then a second only if the first stopped and P > θ again. |
| 168 | **Meta-labelled signals** | Primary signals: 15-minute range break, VWAP cross with slope, 1-minute impulse ≥ 2σ (the partner's move), EMA9/21 cross. A LightGBM gate (same features) learns which to take; θ chosen in development walk-forward; TEST once. |
| 169 | **Learned exit** | At each minute of an open trade (random entries and SN168's primary signals): P(the rest of the day adds ≥ ₹500 more before giving back ₹500). Exit when P < φ (φ ∈ {0.3, 0.4, 0.5}, chosen in development). Against the fixed wage lock. |
| 170 | **Online contextual bandit** | Each morning at 09:45 choose one of six day-plays (none, range-break follow, open fade, 10:00 straddle, 2-OTM momentum, VWAP reversion) by Thompson sampling on day context (gap, yesterday's ADX, VIX ratio, opening-range width, R_today). It learns every day from 2023; scored on development years (online, no look-ahead) and on TEST against the best fixed play chosen in development and a random play. |

### Phase P3: other perspectives (SN171–SN175)

| SN | Study | Rule |
|---|---|---|
| 171 | **Volatility forecast (HAR-RV)** | Rest-of-day realised variance forecast from yesterday's, last week's and last month's daily RV plus this morning's RV (OLS fitted on development). At 10:00 buy the ATM straddle (₹30k) or the 1-OTM strangle (₹15k) when forecast / implied ≥ κ (κ by LOYO). All days, not only hot days. |
| 172 | **Afternoon window** | 13:15 entries: straddle / strangle (volatility), and the 13:00–13:15 range break (direction), exit 15:10 or wage lock. LOYO choice, TEST once. |
| 173 | **Opening gap** | Gap ≥ g × yesterday's ATR (g ∈ {0.3, 0.5, 0.8}): fade or follow at 09:20 / 09:30, 1-OTM, wage lock. LOYO choice. |
| 174 | **Quiet-day VWAP reversion** | On days the SN171 forecast calls quiet: buy the option toward VWAP when the index is ≥ k × σ from VWAP (k ∈ {1.5, 2, 2.5}), exit at VWAP touch, wage lock or 15:10. LOYO choice. |
| 175 | **1-second impulse with a learned exit** | 1-second archives: 60-second impulses ≥ k σ buy the opening-ATM leg; a LightGBM exit learned on the first 95% of days; TEST = the latest 5% of days. |

### Phase P4: wallets and the wage itself (SN176–SN180)

| SN | Study | Rule |
|---|---|---|
| 176 | **The wage day player** | Gold v5 first; on Gold's empty days the development picks of P1–P3 (frozen list, one position at a time), wage lock at 10%, day limit 20%. ₹15k / ₹30k / ₹50k. |
| 177 | **The salary account** | Gold v5 (₹30k, growing, stop 3) plus a reserve pays a fixed wage (₹750 / ₹1,000 / ₹1,500) every trading day from Jan 2023. Smallest starting capital that never misses a payment; months short for ₹15k / ₹30k / ₹50k / ₹1 lakh. A daily wage from a lumpy edge. |
| 178 | **Sweep vs compound** | Gold v5 with profits above the wallet swept out daily vs compounding: wage paid, wallet at the end. |
| 179 | **Robustness of SN176** | ₹400 per lot, 1 minute late, without the best 5 days, a monthly bootstrap. |
| 180 | **Starting price grid** | SN176 and SN177 from ₹15k to ₹1 lakh: net, wage days a month, worst month, refills. |

### Phase P5: the exam and the answer (SN181–SN185)

| SN | Study | Rule |
|---|---|---|
| 181 | **The frozen TEST** | Every candidate from P1–P4, frozen in one committed script, scored once on 2026-08-20 … 10-28 against matched nulls; the pass rule above. |
| 182 | **Real quotes** | Candidates replayed where the real-quote archive overlaps TEST (Sep 10 – Oct 28): do measured spreads change the verdict? |
| 183 | **Expiry days in the calendar** | The expiry-day books' stored day results (E-series, 2024–2025, in-sample) added to the wage calendar: how many wage days a month exist when expiry days are counted. |
| 184 | **The honest wage table** | For each wallet: what a wage-earner gets per month (median, worst), with today's system, the best book and the salary account. |
| 185 | **Synthesis** | What was learned, what goes on paper from Monday with the tick recorder, what would change the answer. |

## Order of work

P1 → P2 → P3 → P4 freeze their scripts (one commit per phase) before running them. P5's SN181 script is frozen after P4 and before any TEST number of a P2–P4 candidate is read. Phases P1–P4 report development numbers only; their TEST columns are filled by SN181.
