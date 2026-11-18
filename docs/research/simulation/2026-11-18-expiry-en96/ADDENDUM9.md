# Round 9 addendum (2026-11-18, after the auditor's REVIEW10)

This file corrects three statements in the round-9 write-up. It does not change any archived file, freeze, ledger or headline P&L. The corrections are carried forward in round 10 (`../2026-11-18-expiry-en111/IMPL10.md`, section 1).

1. **R3: SENSEX dependency check.**
   - **What went wrong.** `families9.Spec.needs_oi()` decides from the rule's name, so it reports that `VOTE2` needs no OI. IMPL9 treats `VOTE2` as OI-dependent. The two SENSEX VOTE2 cells therefore ran and traded zero, instead of being excluded as DATA UNAVAILABLE. `verify9`'s check that 268 OI-dependent SENSEX cells are empty shares that predicate, so it missed this case.
   - **Fix in round 10.** Every configuration declares its dependencies explicitly (`needs`). `test10.dependencies` reruns every NIFTY configuration that declares no OI with OI removed, and requires identical ledgers.

2. **R4: EN99 unfilled-arm markouts.**
   - **What went wrong.** `score9.diagnostics` computes `(bid 8 minutes later − event ask) × lot`. That is a **gross** executable-price markout. It subtracts no buy or sell charges and assumes a hypothetical fill at the event clock. ANATOMY9 and COMPONENTS9 call the positive values "winners" and "+₹161 to +219 per lot". Read them as gross price markouts, not after-fee trade results. The simulated trade ledgers themselves include fees and reconcile.
   - **Fix in round 10.** Every markout shows four values separately: gross, explicit fees, net hypothetical, and the matched-reference lifecycle.

3. **R7: COMPONENTS9 boundary statement.**
   - **What went wrong.** COMPONENTS9 says that "at the other five boundaries no gene had a passing component". In fact boundary 160 also had a signal component (EN96 5/60/40). It had no outer-block trade effect. ANATOMY9 and the ledgers were already correct. No P&L changes.
