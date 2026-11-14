# SN211–SN220: a smart fail-safe exit for the weekly seller, and the Gold v6 question (Nov 14, 2026)

**Owner:** "certain days wiped it all off … a smart fail safe mechanism … master the exit … slice down the losses as much as possible while ensuring that the profit is maintained … a gold V6 which includes gold V5 and the gap covering strategy … till SN 220."

**How it was tested**
- **Plan:** `PLAN.md`, frozen at `2c2d1b66` before any number. An amendment after SN212 (development description only) added the expiry-day gate.
- **Freezes:** `2693893f` (SN213–SN218) and `f8a5b533` (SN219).
- **The engine (`wk2.py`):** replays each weekly position minute by minute, with a reaction delay, fresh prices only, and an opening penalty. With no rule it reproduces SN204's WK-S exactly on every sample (SN211, 0.0 rupee difference).
- **Development:** NIFTY Apr 2022 – Aug 2026, chosen by year held out.
- **The second look:** the three samples where WK-S lost (TEST, NIFTY Dec 2021 – Mar 2022, SENSEX Oct 2024 – Apr 2026). Their intraday paths had never been studied; every exit was frozen before they were run, once.

**A correction first (told to the owner):** WK-S is not a better *entry*. It sells options and is paid on quiet days. On unseen data it lost beyond its single worst week. So the question was whether an exit can cut the big losses *and* leave a profit.

## Results

| SN | Study | Development (NIFTY 2022–26, per lot) | Verdict |
|---|---|---|---|
| 211 | Engine and data | Full-minute mirrors of the exam expiries (NIFTY 768k rows, SENSEX 4.36M). Parity with WK-S exact on all four samples | Engine proven |
| 212 | Where the losses come from | Overnight gaps **earn** (+₹1.62 lakh). Losing weeks lose on **expiry day (−₹4.17 lakh)** and intraday (−₹2.99 lakh). Only 8 of 139 winners were ever down 1× the credit. After the index touches a short strike (93% of weeks), holding ended better 60% of the time | The tail is expiry day and gaps |
| 213 | Exit when the index breaks past a strike | Exiting at or near the strike destroys the profit (−₹10k to +₹1.15 lakh). Far past it (0.5 straddle) keeps +₹2.94 lakh, worst month −₹49,901 | Only the far version is harmless |
| 214 | Minute loss stop / profit take | Stops at 0.5–2× the credit: +₹2.26–3.08 lakh, worst week unchanged (−₹39,844, an expiry-day loss). Profit takes: no help | No tail cut |
| 215 | Crash-speed exit | Cuts profit (−₹37k to +₹1.73 lakh), worst month worse | FAIL |
| 216 | Buy protection when threatened | +₹1.26–1.62 lakh, worst month worse (−₹60k) | FAIL |
| 217 | Calendar (Budget / RBI / election) and **expiry-day gate** | Calendar: +₹2.11 lakh, worst month −₹35,105. **Gate** (hold into expiry only while the index is still inside the strikes): **+₹3,04,942 (97% of the profit), worst month −₹32,138 (−37%), worst week −₹32,745 (−18%), 5 of 5 years** | Best in development |
| 218 | Combined smart exit (30 candidates, LOYO) | LOYO +₹2.21 lakh (< 80% of WK-S). No candidate cuts the worst week by 30%: the April 2025 weekend gap (−₹32,745) cannot be exited | FAIL (frozen screen) |
| **219** | **Gold + seller (development) and the second look (once)** | Development: Gold + WK-S +₹8.76 lakh; Gold + gate +₹8.65 lakh with the worst month −₹31,981 (vs −₹56,645). **Second look (TEST + NIFTY 2021–22 + SENSEX 2024–26, 96 weeks):** WK-S −₹1,22,113; with the gate **−₹1,56,870**; breach + gate −₹1,14,945 (NIFTY +₹7,971, worst week −₹7,602 vs −₹40,884); never through expiry day −₹71,141 | **FAIL: no exit makes the seller profitable on the samples it lost** |
| 220 | Synthesis | below | – |

## SN220: synthesis

1. **The smart exit does what an exit can do.**
   - The expiry-day gate keeps 97% of the development profit and cuts the worst month by over a third.
   - Breach + gate cut the NIFTY 2021–22 worst week from −₹40,884 to −₹7,602.
2. **What an exit cannot do:**
   - **Stop a gap:** a crash at the open (Apr 7, 2025; Feb 24, 2022) has already happened before any exit can act.
   - **Create an edge:**
     - on the second-look samples every version still loses;
     - on SENSEX the gate made it worse (−₹99,023 vs −₹42,022), because it gave up the expiry-day decay that paid there.
   - Exits move losses around; they do not turn a losing trade into a winning one.
3. **So the weekly seller is not "a good entry that needs a good exit".**
   - Its profit in 2022–26 NIFTY did not repeat on data it had not seen, with or without a fail-safe.
   - That is the same pattern as every gap-day idea since SN01: it is real in the years it was built on and gone outside them.
4. **No Gold v6.** Gold v5 stays as it is.
   - Adding the seller (with or without the exit) would have added +₹2.2 lakh in development and lost on all unseen samples.
   - On Gold's empty days, staying flat is still the honest answer.
5. **What would still be worth doing:**
   - **New information:** the tick recorder's order flow from Mon Nov 16.
   - **A true crash test** of any seller: NIFTY 2020 (March 2020) and Jan–Sep 2021. These need a new Breeze target and a probe; ICICI may not serve such old weekly options.
   - **The daily income:** keep paying it from Gold (SN177's salary account).
6. **Lesson for the record:**
   - A fail-safe exit is worth building once an edge exists. It cannot replace the edge.
   - The only fair proof is data the rules have never seen.

## Files

- **Plan and engine:** `PLAN.md`, `wk2.py` (the minute exit engine), `fam.py` (the family runner).
- **Studies:** `sn211.py` … `sn219.py`, with `results-sn211.json` … `results-sn219.json`.
- **`_local` (not committed):** `mirror-nifty-exam-full.sqlite`, `mirror-sensex-exam-full.sqlite`, `sn218-wkx.pkl`.
- **`logs/`:** git-ignored, local only.
