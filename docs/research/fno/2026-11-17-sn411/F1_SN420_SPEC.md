# SN420: the next paper decision (pre-registered Nov 17, 2026, before any qualifying observation exists)

**At most two candidates were allowed:** one instrument route and one information route.

- **Information route: none.**
  - USDINR has no data on this PC (SN416).
  - Results filings and stock-option quotes are absent (SN415).
  - RBI days are insufficient, with 3 events that all hit the stop (SN402).
- **Instrument route: one candidate, F1.** It is frozen here and judged only on data that does not exist yet: BANKNIFTY quotes from the recorder, after the owner deploys `1bfed1d0` (SN413 C).

## F1: the bank-sector residual fade
- **Why:**
  - **The reversal.** SN414b's 27-cell grid saw the BANKNIFTY-constituent basket's residual against NIFTY reverse over the next 15–30 minutes in every cell (−5 to −14 bp in the residual's direction, t down to −2.86).
  - **Small and post hoc.** It rests on only 6–28 overlapping triggers in Jan – Jul 2026, and the effect was found after looking. **The prior is low.**
  - **The hurdle.** SN413 A / SN414 put a BANKNIFTY option's hurdle at about 4–7 bp.
- **Signal (forward only, recorder packets, HONEST):**
  - **Clocks:** 10:30, 11:00, 11:30, 12:00, 12:30, 13:00.
  - **Residual:** r_b = the BANKNIFTY front future's 30-minute mid return, and r_n = NIFTY's front future over the same window. residual = r_b − β r_n, with β from OLS of 15-minute mid returns over the previous 20 recorded sessions.
  - **z:** residual / the standard deviation of 30-minute residuals over those sessions.
  - **Trigger:** |z| ≥ 2 and |r_n| ≤ 0.15%, with no Gold position open. First trigger per session.
  - **Calibration:** the first 20 recorded sessions are calibration only.
- **Trade:**
  - **Contract:** buy the BANKNIFTY option against the residual's direction (a PE after a positive residual): 1-ITM, else ATM, on the front monthly.
  - **Cash and cap:** admissible only if the walked one-lot ask plus entry charges ≤ ₹15,000 (affordable mostly in the last week before expiry: SN413 A). The limit is the decision ask + 2 ticks, never above the room. The entry follows fw7c's rules: fresh book ≤ 2 s and limit-legal depth.
  - **Exit:** hold 30 minutes; ₹3,000 stop; exit at the walked bid. An unresolved exit counts as the premium lost.
- **Controls (same triggers):**
  - the same option bought in the residual's direction;
  - a seeded coin side;
  - NIFTY's ITM option against the residual's direction.
- **Verdict (once):**
  - **When:** after 30 qualified triggers, or 120 recorded sessions after calibration, whichever comes first.
  - **PASS requires all of:**
    - per-trigger net > 0 at ₹205 and ₹400;
    - > 0 without the best 5 days;
    - above every control;
    - the futures-level reversal mean in the trade's direction > 0 with t > 2.
  - **Otherwise** FAIL, or INSUFFICIENT below 15 fills.
  - **Reported:** zero for every abstention, skips, unresolved fills, the share of sessions reaching ₹750, and the incremental wallet net per market session.
- **First admissible observation:** the first recorded session after deployment plus 20 calibration sessions.
- **Variants ledger:** this is the only variant. Any change is a new candidate with its own date.
