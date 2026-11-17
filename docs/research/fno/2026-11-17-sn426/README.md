# SN426–SN440: Gold's missing expiry mornings, where the hindsight money sits, exits, fills, a hard loss bound, and Gold's feed / edge / cost (Nov 17, 2026)

**Owner (Nov 17):** the auditor's SN426–SN435 (`docs/SN426_SN435_RESEARCH_BRIEF.md`, committed as received in `f3c4fc1d`) plus five own slots. Plan `123301ac` (amendments in its section 4). Every script was committed before it ran; results were written once.

**Disclosed:**
- the SN426 date-label correction;
- the SN436 crash fix (the N08 stream);
- the SN439b follow-up;
- SN430, blocked by access.

**Status:** research only. No runtime, broker, Production or order change. The N11 rerun wrote only to this folder's `_local` and reproduced every saved evaluation exactly. Forward verdicts stay unopened.

## Results (in the order run)

| SN | Question | Result |
|---|---|---|
| **426** | Reconcile dates and decisions | **Per calendar session Gold makes ₹616.65 / ₹319.08** (₹205 / ₹400; reproduced).<br>**Of the 263 non-Gold dates:** 251 are NIFTY weekly expiries; 4 are special sessions (muhurat 2022-10-24, 2023-11-12, 2024-11-01, 2025-10-21); 8 are data holes (2022-01-12, 03-29, 03-30, 03-31, 05-31, 06-14, 2023-03-01, 2025-12-31).<br>**Signals:** of 434 N11 / R0.85 stream signals (the two books mostly duplicate each other), **66 arrived while Gold already held a position**, 2 after its day stop and 2 other. **70 untaken signals fall on days Gold traded**; SN422's "none untaken" held for zero-trade days only |
| **427** | Gold's signal on expiry mornings | **The hooked N11 / R0.85 rerun reproduces every saved evaluation** (2023–26, parity true).<br>**Coverage:** N11 has a chain-less candidate on 46 of ~200 expiry days, and a **morning one (09:20–12:30) on only 27** (about 7 a year).<br>**Priced history is tiny:** 3 on Breeze's 1-second expiring ATM (+283, +375, −3,028); 2 on archive quotes where **both tenors lost alike** (expiring −2,637 / −65; next week −2,556 / −109, at ~2.5× the premium).<br>**INSUFFICIENT:** worth about ₹28 a session even at Gold's one-lot average |
| **428** | Which decision makes the hindsight money | **Per decision** (42 days × 3 clocks, 1-ITM, 60-min hold, ₹205 / ₹400):<br>• BASE (coin side) −169 / −511;<br>• perfect SIDE +1,269 / +923;<br>• perfect CONTRACT +750 / +544;<br>• perfect EXIT +1,240 / +938;<br>• **perfect TIMING (±30 min) +2,126 / +1,928**;<br>• SIDE + EXIT +2,244 / +2,007 (79% / 72% ≥ ₹750).<br>**A fixed 60-min ITM trade needs about 56% directional accuracy at ₹205 and about 68% at ₹400 to break even.** Gold-empty days offer less (perfect side +946 / +443) |
| **429** | Checkpoint exits on Gold's entries | **FIXED exits at 30 / 60 / 90 min:** 2023–26 at ₹0.61 / 2.69 / 5.29 lakh against 8.51 (they cut the large winners), though 2022 improves at 60 min (−3,325 against −15,281).<br>**CUT if no progress at 30 / 60 / 90:** −7% / −5% / −3% in 2023–26 at ₹205; CUT-30 costs 35% at ₹400.<br>**No rule improves both periods at both stresses: the branch stops** |
| **434** | A hard full-loss bound | **Gold could barely trade:** the ₹6k day room at ₹30k cannot hold a lot. 2022 has 0 trades; 2023–26 has 4 (₹11,799).<br>**Under the current trigger stop, the largest debit at risk** is ₹28,784 (2022) and **₹1,00,166** (2023–26).<br>A true bound needs a bigger wallet or another contract choice: **the owner's policy call** |
| **436** | Widen Gold's feed (one book at a time) | **No book helps both periods.**<br>Five books (DOUBLE / NO_LOSS / NO_VOL / R0.95 / X0.75) duplicate N11 + R0.85 exactly.<br>NO_STAND / N10 / N08 add ~35 trades (2022 +₹20k, 2023–26 −₹1.5 lakh); X1.25 helps in sample only |
| **437** | Where Gold's edge lives | **Per lot by year:** 2022 −489, 2023 −358, 2024 +2,350, 2025 +1,134, 2026 +1,492.<br>**Entries before 10:30 lose in both periods** (19 trades, −₹484 a lot; too few for a cutoff).<br>2 sessions to expiry is the strongest; EFF is +₹1,682 a lot |
| **438** | Size by expert | **No arm improves both periods at ₹205:** setup EFF 2022 −13,524 / 2023–26 ₹6.52 lakh; EFF + TPB −16,606 / ₹8.14 lakh; TPB −21,827 / ₹7.55 lakh |
| **439** | Gold's exit headroom | **Realized ₹950 a lot**, against the best close before the stop of **₹3,035** (headroom ₹2,085).<br>**The best moment came in the first hour on 66% of trades** (median minute 34; median hold 70.5).<br>**82 of 106 losers were above entry first** |
| **439b** | A breakeven lock (follow-up) | **It hurts:**<br>• **LOCK-10%:** −13% in 2023–26 (losses avoided ₹34k, winners cut ₹57.5k), and 2022 worse;<br>• **20%:** fires 3 times;<br>• **30%:** never fires.<br>The give-backs were rarely far green |
| **440** | Gold's real cost per lot | **41 Production paper round trips** (Jul 16 – Oct 28) against the replay's model: real minus model **median +₹6.5 a lot, mean +₹59**, p90 +₹306 (15% above ₹205, 10% above ₹400).<br>**The ₹205 stress already covers the typical real extra about 3×.** Gold's realistic figure sits nearer ₹617 a session than ₹319.<br>Caveat: paper fills do not walk depth at Gold's larger sizes |
| **430** | The morning after bank results | **Blocked:** nseindia.com returned 403 to an automated request from this PC, and the retry was refused by the session's safety check (not worked around). Needs the owner's approval for a fetch method, or the auditor's filing list |
| **432** | 5 / 30 seconds of fill persistence (Nov 16, one morning, 252 decisions) | **IMMEDIATE** fills 171 (bid 60 s later −₹42 a lot).<br>**CONFIRM-5** (the ask holds 5 s) fills 76 at ₹55 a lot better, and the decisions it waited out were net IMMEDIATE losers.<br>**The inside ask held a median 1.6 s.**<br>**Random wait** also fills cheaper (the opening premium slides).<br>**Plumbing evidence only.** Prospective test: a CONFIRM-5 companion on fw7c's / Gold's recorder decisions, with missed winners charged |
| **433** | Gold's clock; the adapter's back-fill | **Gold's live ledger has no trade yet.**<br>3 of 932 Gold sessions start with back-filled minutes; **1 Gold trade (2025-01-31, entry 10:15)** sits inside a back-filled index stretch. Gold prices from option / futures arrays, which were complete, so the impact is likely nil |
| **431** | F1 on native BANKNIFTY books | **Blocked:** the recorder change `1bfed1d0` is not in Production (`0b645d77`) |
| **435** | The wage test | **Not triggered:** no survivor |

## Lessons
1. **The money in hindsight is mostly timing and direction, then exit.** With a coin side, the best entry minute within ±30 min is worth more than perfect direction. Break-even needs about 56% direction at ₹205 and about 68% at ₹400 for a fixed one-hour ITM trade. That is the bar any new signal must clear.
2. **Gold's exits leave money (₹2,085 a lot of headroom), but no simple rule captures it.** Fixed checkpoints, no-progress cuts and breakeven locks all cut the large winners Gold depends on.
3. **Gold's missing expiry mornings are not a hidden goldmine.** Its ordinary signal fires on only about 7 expiry mornings a year, and the few priced cases lose.
4. **₹205 is the realistic cost level for Gold.** Paper fills cost about ₹6–60 a lot more than the model, so Gold makes about ₹617 a real session at ₹30k. The wage gap to ₹750 is about ₹154 per non-Gold session at that cost.
5. **A hard loss bound and Gold are incompatible at ₹30k.** Gold's strength is size, and size requires a stop-based (not full-loss) risk policy.
6. **Gold's feed is already the useful union.** Other panel books either duplicate it or bring back the stand-aside's trades.

## Forward queue (unchanged; scored once)
- fw5 / fw7 / fw7a / fw7b / fw7c and fw8 / fw8a after SN300a's 20 sessions;
- fw9 / fw9a / fw9b at 15 cheap fills or 60 sessions;
- fw6 from Dec 7;
- F1 after the recorder change is deployed.

**Specified, not frozen:** a CONFIRM-5 fill companion (SN432), and an expiry-morning arm reading Production's `expiry_day_block` rows with recorder chains (SN427).

## Rule register
- **SN426:** date labels and signal classes.
- **SN427:** the hooked N11 rerun; the 1-second and archive pricing; a coin control.
- **SN428:** BASE / SIDE / CONTRACT / EXIT / TIMING / SIDE + EXIT at 3 clocks.
- **SN429:** FIXED / CUT at 30 / 60 / 90.
- **SN434:** DEPLOYED / NO_ADDS / BOUND.
- **SN436:** 12 added books.
- **SN437:** hour / weekday / sessions-to-expiry / year / expert.
- **SN438:** setup {EFF}, {EFF, TPB}, {TPB}.
- **SN439:** headroom; **SN439b:** LOCK 10 / 20 / 30%.
- **SN440:** paper against model.
- **SN432:** IMMEDIATE / CONFIRM-5 / CONFIRM-30 / RANDOM.
- **SN433:** the back-fill scan.
