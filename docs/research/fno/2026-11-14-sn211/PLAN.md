# SN211–SN220: a smart fail-safe exit for the weekly seller, and a Gold v6 candidate (frozen plan, Nov 14, 2026, before any score)

## The owner's brief (Nov 14)

> "there were some noteworthy ones … that actually earned money, but certain days wiped it all off … we can have a … smart fail safe mechanism … now we have to master the exit … create smart exit mechanisms so that our profit is not cut down, but we are able to avoid massive pitfalls … once you master a good exit … we can make a gold V6 which includes gold V5 and the gap covering strategy … our goal currently is … to slice down the losses as much as possible while ensuring that the profit is maintained … 10 more strategy slots till SN 220."

## What we start from (SN201–SN210)

- **WK-S** sells a call and a put ±0.5 straddle out of the money at 15:15, 3 sessions before the weekly expiry. Its only fail-safe is a check once a day at 15:15 (exit when the loss ≥ the credit received); otherwise it holds to expiry.
- **Development** (NIFTY Apr 2022 – Aug 2026): +₹3,13,523 per lot, worst week −₹39,844, worst month −₹51,245.
- **The three samples where it lost:** TEST −₹23,348; NIFTY Dec 2021 – Mar 2022 −₹56,743; SENSEX Oct 2024 – Apr 2026 −₹42,022.
  - They were opened once, by SN209, at the weekly level only.
  - Their intraday paths have never been studied.
  - Here they are **second-look samples**: every exit is frozen before they are run again, once. Their results are known in outline (for example, the Russia week), and this is disclosed.
- **Correction to the brief (said to the owner):** WK-S is not a better *entry*. It is a different trade, an option seller paid on quiet days. On unseen data it lost beyond its single worst week (NIFTY 2021–22 was still −₹15,859 without the Russia week). An exit can cut the big losses; whether that is enough is exactly what SN211–SN220 test.

## Data

- **Development** minute paths: option minute closes on demand from the sealed NIFTY year datasets (all minutes, sessions before expiry), plus the index minutes.
- **Second-look samples:**
  - full-minute read-only mirrors of the NIFTY and SENSEX exam expiries (SN211; option rows of the sessions before expiry; counts only);
  - TEST from the development datasets.
- **The expiry day:** the NIFTY datasets hold no option prices on expiry day itself, so no exit can act during it. Two bases are tested:
  - **settle:** hold through expiry day, as WK-S does;
  - **pre:** close at 15:15 on the day before expiry, so the position is never left unwatched.

## The exit engine (`wk2.py`)

- **Built on** `wk.py` (fills, charges, settlement). With no smart rule it returns WK-S's trades exactly (the parity check in SN211).
- **Every minute** from 15:16 on the entry day to the last session before expiry, it values the position:
  - each leg's last print that day (else the previous day's last print);
  - shorts bought at the ask, wings sold at the bid;
  - charges plus ₹100 per leg-lot.
- **A trigger at minute j executes at the first minute ≥ j + 1** where every short leg has printed within 3 minutes (a reaction delay; executable prices only).
  - Exits before 09:20 pay an extra ₹100 per leg-lot (opening spreads).
  - A trigger at 15:29 executes the next morning (an overnight gap cannot be stopped).
- **The base rules stay:** the 15:15-mark stop at 1× credit, settlement or the pre-expiry exit.

## The pass rule for the smart exit (WK-X), all must hold

1. **Development:**
   - the LOYO total (2022–2026, each held-out year scored with the parameters best on the other four) ≥ 80% of WK-S's +₹3,13,523;
   - ≥ 4 of 5 years positive.
2. **Development, worst week and worst month:** each at least 30% smaller than WK-S's (≥ −₹27,891 and ≥ −₹35,872).
3. **Development robustness:** > 0 at ₹200 per leg-lot and with exits 2 minutes later.
4. **Second-look samples (SN219, once):**
   - TEST + NIFTY 2021–22 + SENSEX 2024–26 combined > 0;
   - better than WK-S on each of the three.

**Gold v6 = Gold v5 + WK-X** is proposed only if 1–4 hold. Even then it is paper-only until a forward record (≥ 20 weeks) and an unseen test: NIFTY Oct–Nov 2021 options (download unfinished), and NIFTY 2020 / Jan–Sep 2021 (the 2020 crash is the real fail-safe test). Real money needs the owner's word.

## The 10 studies

| SN | Study | Rule (frozen) |
|---|---|---|
| 211 | **Engine and data** | Full-minute mirrors of the exam expiries (counts, hashes). Parity: `wk2` with no rule = SN204 WK-S, trade by trade, for both bases. |
| 212 | **Where the losses come from (development)** | For WK-S (settle and pre bases), split each week's result into: the entry evening; overnight gaps (last value of a session → its first fresh minute the next session); intraday sessions; expiry day (last pre-expiry value → settlement). Also each trade's worst intraday value (MAE); how many winners were down ≥ 1× credit at some minute; after the index first crosses a short strike, how often expiry ends beyond it vs back inside, and exiting then vs holding. Description only. |
| 213 | **Breach exit** | Exit when the index is beyond a short strike by b·Q, b ∈ {−0.25, 0, 0.25, 0.5}, at any minute. Both bases. |
| 214 | **Minute loss stop and profit take** | Exit when the value ≤ −L × credit, L ∈ {0.5, 1, 1.5, 2}, checked every minute. Separately, exit when the value ≥ p × credit, p ∈ {0.5, 0.7}. Both bases. |
| 215 | **Speed exit (crash detector)** | Exit when the index moves ≥ z·Q within 30 minutes (across the open, the gap counts), z ∈ {0.3, 0.5, 0.7}. Both bases. |
| 216 | **Protect instead of exit** | At a breach (b ∈ {0, 0.25}), buy the wing 0.5·Q beyond the threatened short strike (turning that side into a credit spread) and hold to the base exit; the other side can be protected later the same way. If the wing has no price, exit instead (counted). Both bases. |
| 217 | **Calendar fail-safe** | Skip a week whose holding window holds a scheduled shock day: Union Budget (Feb 1 2022, Feb 1 2023, Feb 1 2024, Jul 23 2024, Feb 1 2025, Feb 1 2026), the 2024 election result (Jun 4 2024), RBI decisions (round 31's sourced list for Jun 2022 – Oct 2026, plus Dec 8 2021, Feb 10 2022 and Apr 8 2022 added from knowledge). Both bases, alone and with the best single exit of SN213–SN216. |
| 218 | **The combined smart exit, WK-X** | Candidates: each family's LOYO winner from SN213–SN217 and every pair of two families (one trigger + one of protect / profit take / calendar). Choose by LOYO on development with the pass rules 1–2 as the screen. WK-X = the best development total among those passing 1–2 (else the best LOYO, marked failing). Robustness: exits 2 minutes later, ₹200 per leg-lot, a ₹200 opening penalty, the neighbours of its parameters. |
| 219 | **Gold v6 candidate and the second look** | Development 2023 – Aug 2026: Gold v5 ₹30k growing + WK-X daily (green days, worst day / week / month, per year), against Gold + WK-S. Then WK-S and WK-X on TEST, NIFTY Dec 2021 – Mar 2022 and SENSEX Oct 2024 – Apr 2026, scored once. Pass rule 4. |
| 220 | **Synthesis** | Gold v6 or not, what goes on paper, what data would test it truly (NIFTY 2020 / 2021), docs. |

## Order and freezes

1. This plan, `wk2.py`, SN211 and SN212 are committed before any number.
2. SN213–SN218 are frozen after SN212 (it describes development only) and before any exit is scored.
3. SN219 is frozen before it runs, once.
4. Post-freeze fixes are disclosed, and the first log is kept (locally in `logs/`).

## Amendment after SN212 (development description; written before any exit was scored)

**What SN212 shows on development (WK-S settle):**
- **Overnight gaps earn:** +₹1.62 lakh in all weeks, +₹29,709 even in the losing weeks.
- **The losing weeks lose on expiry day (−₹4.17 lakh) and intraday (−₹2.99 lakh).**
- **Expiry day is the biggest earner overall (+₹2.13 lakh) and the biggest tail.**
- **Winners rarely go deep:** only 8 of 139 were ever down 1× the credit.
- **Exiting at a strike touch looks costly:** after the index first touches a short strike (93% of weeks), holding ended better 60% of the time (+₹1,634 a week).

**Added to SN217:** the **expiry-day gate**, settle base only.
- At the 15:15 mark before expiry, hold into expiry only when the index is ≥ c·Q inside both short strikes; else close then.
- c ∈ {−0.25, 0, 0.25, 0.5}, chosen by LOYO.
- It is a candidate family for SN218 like the others.
