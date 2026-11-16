# SN366–SN380: pressure before NIFTY moves, entries after the opening premium settles, Gold's 2022 exam (Nov 16, 2026)

**Owner (Nov 16):** the auditor's SN366–SN375 (`docs/SN366_SN375_RESEARCH_BRIEF.md`, `e7f7aadf`) plus five own slots.

**Method:**
- Plan frozen at `3740b461` before any number. Each script is committed before it runs; results are written once.
- Amendment B1 (fw6: expiry-day rows are research evidence only) went in before any CAS session exists.

**Status:** research only. No runtime, broker, Production or order change.

**Agreed with the auditor:**
- V8's fully closed subset is 6 positions, ₹1,15,088 against ₹92,270 for the ₹205 replay. My 7-trade figure valued one unsold remainder at the last bid.
- fw6's expiry-day rows are outside the owner's expiry-day clock.

**Power cut, Nov 16 ~18:00–19:23:** Production restarted on its own. All six containers are healthy, the database integrity check passes, Gold's Nov 16 close row and the open WK-H paper week are intact, and the brief was already committed.

## Results (in the order run)

| SN | Question | Result |
|---|---|---|
| **366** | Gold / N11 on 2022 | **Gates passed; exam run once (results below).**<br>**Gate W (wiring):**<br>• N08's TEST2025 repoint, replayed from empty, equals its stored receipt (4 books × 80 trades).<br>• N11's chain on TEST2025 reproduces N08, VOL_CLOCK, N10 retry and N11 trade for trade (₹58,646.53 / ₹52,319.97 / ₹51,582.51 / ₹53,094.68). The receipt's `pass=false` comes from a mis-specified cross-lab key check (disclosed note).<br>**Gate W2 (evidence wiring):**<br>• With the paper-evidence readers replaced, N11, CUSHION, N10 one try and N10 retry reproduce 2025 exactly.<br>• Negative control: an empty paper stream turns N11 into exactly the stored NO_STAND (₹57,454.27), so the patch reaches the replay workers.<br>**Gate D (data, from this PC only):**<br>• 2022 Jan–Dec: 242 sessions, 190 with options (the 52 without are expiry days, as in 2023), no bad rows.<br>• 2021L Sep–Dec: 83 sessions, for N11's paper evidence.<br>• Daily bars (A1): Breeze's daily close is the 15:29 minute close. 2020–21 warm-up bars are made on that convention; 6 Breeze 2022 rows with gross errors (e.g. Apr 29: 17,347.2 against the official 17,102.55) take the minute high / low / close.<br>• `n08_lab.py` stays byte-identical (two freezes hash it); the 2022 points live in `n08_shim.py`.<br>**Paper evidence:** 54 (2021L) + 57 (2022) one-lot N08 paper trades |
| **371** | Does the opening direction still pay at 10:15, after the premium resets? | **No.**<br>• **Gap direction at 10:15** (619 trades, 2022–2026): 60-minute net −₹361 at ₹205, against a coin flip −₹386 and the opposite side −₹340. After 10:15 the index moves −0.2 points the gap's way. Negative every year.<br>• **Auction direction at 10:15** (153 trades): −₹619, against a coin flip −₹245. The early move reverses, so 09:16 → 11:15 loses ₹803.<br>• **IV-normalized, untraveled days:** the gap still beats a coin flip by about ₹135–145, but an ATM leg held an hour costs about ₹390 (time decay, spread and stress).<br>**Lesson: the opening forecast is a 20–30-minute effect, gone or reversed by 10:15** |
