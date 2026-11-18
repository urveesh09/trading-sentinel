# Round 10 anatomy: EN111–EN125 (development screen on studied sessions; descriptive only)

**Run.** Scored once at freeze `b9aff5ef`. `verification10.json` PASS:
- 525 ledger identities;
- 69 fresh-process reruns from every family and learned family;
- 14 selection views re-derived;
- reference wallets and duplicate groups consistent.

Every table is in `ANATOMY10-tables.md`. Rupee figures are NIFTY adverse fills, independent sessions, unless marked otherwise.

**References** reproduce round 9 exactly:

| Book | Adverse net | Parents | Continuous wallet | Adverse net, entry one bar later |
|---|---:|---:|---|---:|
| EN87 | 5,841 | 25 | no halt | 5,590 |
| E03_env | 2,246 | 55 | adverse halt | 4,795 |
| E032_native | 11,586 | 66 | **halts 2024-01-18** | **3,642** |
| EN55 | 11,056 | 68 | no halt | **−2,480** |

## Nominations: read this first

The frozen rule nominated **EN115:0001 and EN115:0002**.
- **Duplicates.** Both are hash-identical to **EN111:0010** (EN87 clocks, nearest one lot, +100%, 8 minutes). Phase zero had already declared EN115 a DUPLICATE of NEAREST.
- **Why they passed.** EN115's primary comparator is the legacy contract at one lot, which tests the contract mechanism.
- **Against the deployable EN87** (legacy, up to 3 lots) the same ledger fails the 3-of-4-years check: 2023 −₹6, 2024 −₹183.
- **What this means.** The nomination therefore stands for one policy only, "nearest one lot at EN87 clocks". It is not evidence for the response model.
- **Against EN87 itself**, the cells that pass every check are EN111:0012 (nearest one lot, +100%, hold 12: +₹3,764, +₹1,464 without the best two days, 24 changed parents) and EN123:0002 (nearest one lot, stop 25%: +₹2,635).

This is a labelled post-score reading; the registration files are left as written. Nothing is promoted. Any forward test is the owner's decision.

## Lessons (where it won and lost)

1. **The runner is the harmful part of EN87's exit ladder.** At +100%, EN87 sells half and trails the rest at 50% of the peak; that remainder gives back. The fix pays the same way in four families:

   | Change | Family | vs EN87 (adverse) |
   |---|---|---:|
   | Sell every lot at +100% | EN111 no-partial control | +₹4,409 (8 min), +₹7,338 (12 min) |
   | End the runner at the clock | EN114 fixed-8 base and runner | +₹4,453 |
   | Exit at the OI wall | EN125 AT_WALL | +₹1,807 |
   | Higher target | EN111 +150% / round 9 EN110 | — |

   - The gains come from the same **five** target-reaching parents in 2024–25 (for example 2024-02-22 +₹1,349, 2024-08-08 +₹1,262, 2025-09-02 +₹1,353). They are sparse, not proven.
   - On a single lot, a runner is catastrophic: EN123 keep-50% runner ₹1,245, against ₹7,914 for selling all.

2. **Nearer contract.**
   - NIFTY: nearest one lot beats legacy one lot in 9 of 9 EN111 pairs.
   - **E03.2's wallet halt disappears** with the nearest affordable contract at the same room (EN121): 14,194 / 13,909 / 16,252 adverse with no halt, against the halting E032 at 11,586.
   - **SENSEX contradicts it.** Nearer is worse in every book there (for example E03_env 4,746 → 817–1,905), on only 7–12 parents.

3. **A 12-minute hold beats 8**: EN87 +₹1,925; E03_env legacy hold 12 is 5,842 against 2,246 with no wallet halt.
   - EN124's "sell one bar late" stress *gained* +₹4,901, mostly from time exits (+₹2,501). That is the same effect: EN87 exits early.
   - Holds are non-monotone (10 is worse than 8 or 12), which says noise.
   - Joint "three good parts" (EN111:0018, nearest/150/12): 7,898. Target 1.5 adds nothing on one lot (1.25 ≡ 1.5).

4. **The OI gate on calls only** improves native E03.2 in all 16 EN122 structure pairs.
   - It removes 17 calls (−₹1,762) and keeps every put.
   - Native E03.2 rises from 11,586 to 13,770. Envelope money with the 15:00 window and 2× puts reaches 14,292, with a wallet of 9,694 and no halt, and it survives entry+1 (11,096).
   - Not available on SENSEX (no OI).

5. **Latency fragility.** One minute of entry delay takes E03.2 from 11,586 to 3,642 and EN55 from 11,056 to −2,480; EN87 barely moves (5,841 → 5,590). This matters for the paper main and EN55's forward test.

6. **Learned and adaptive layers add little.**

   | Family | Result |
   |---|---|
   | EN118 action values | Mostly cash (k ≥ 2 never trades); best −₹41 against EN87 on dates 100–196 |
   | EN116 HMM | Below the fixed profile; a random state mapping did as well; next-5-minute forecast separation is tiny (1.26 vs 1.18 ATR) |
   | EN120 controller | All 12 cells beat EN87 on dates 100–196 (+₹1,386 to +2,176), via EN87 fallback plus 13–19 selected range trades (+₹590 to +1,410). The selection reduced to the fixed EN111 profile at 4 of 6 boundaries, so the procedure is not a candidate |

7. **Inert or harmful parts.**
   - **EN113 fast OI:** all 12 cells are identical to fixed-12. 1-minute OI never moves, and 3- or 5-minute confirmations never coincided with an open position.
   - **EN114 activity clocks:** they cut slow winners and never beat the fixed clock with the same runner scope.
   - **EN112 context:** activation-limited (1–14 changed parents). Random assignment at the same rate beat the real assignment (10,690 vs 9,060).
   - **EN117 range rejection:** loses on every cell and both indices (−₹5,056 to −22,761 on NIFTY). The failed-escape direction beats random entries at the same clocks (−₹5k vs −₹31k), but long options cannot pay the costs.
   - **EN125 half-step wall exits** hurt.

## Next decisions (owner)

1. Unseen or forward data only:
   - EN87 with sell-all at +100% and a 12-minute hold;
   - nearest one lot;
   - E03.2 with the calls-only OI gate.
2. Check E03.2 and EN55 paper fill timing against the entry+1 fragility.
3. Whether to acquire NIFTY 2020–22 via the breeze skill for a transport test.
