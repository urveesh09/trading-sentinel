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
| **366** | Gold / N11 on 2022 | **In progress.** SN186's 2022 dataset is in N08's format but has 184 sessions (Apr–Dec); the exam needs ≥ 200. Jan–Mar 2022 options are already on the PC. The N08 → N11 chain hard-codes 2023–2026 (paper evidence `keys-diag-<year>`, carry and `YEAR == "2023"` branches), so 2022 needs its own point at each stage. The engine replays wait for free RAM ≥ 3 GB: 2.5–2.8 GB after the restart |
| **371** | Does the opening direction still pay at 10:15, after the premium resets? | **No.**<br>• **Gap direction at 10:15** (619 trades, 2022–2026): 60-minute net −₹361 at ₹205, against a coin flip −₹386 and the opposite side −₹340. After 10:15 the index moves −0.2 points the gap's way. Negative every year.<br>• **Auction direction at 10:15** (153 trades): −₹619, against a coin flip −₹245. The early move reverses, so 09:16 → 11:15 loses ₹803.<br>• **IV-normalized, untraveled days:** the gap still beats a coin flip by about ₹135–145, but an ATM leg held an hour costs about ₹390 (time decay, spread and stress).<br>**Lesson: the opening forecast is a 20–30-minute effect, gone or reversed by 10:15** |
