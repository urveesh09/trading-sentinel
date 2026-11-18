# Round 9 anatomy — EN96–EN110 (each slot a family of variations)

Developed and scored once under `IMPL9.md` and `freeze9.json`:
- freeze commit `99958d97`;
- score start receipt `results9-started.json`;
- `verification9.json`: PASS.

These are modelled, after-charges development screens on the 197 NIFTY (and 63 SENSEX) expiry afternoons that earlier rounds already studied. **No strategy qualifies. No champion is nominated. Nothing is promoted or deployed.** All tables: `ANATOMY9-tables.md`. Machine evidence: `results9.json`, `anatomy9.json`, `trials9.jsonl`. Labelled post-score diagnostics: `post9.json`. Components: `COMPONENTS9.md`.

## The answer in one paragraph

The chronological selection the handoff asked for could not run. EN87 funds only 7–10 parents in any 60-session window, below the registered floor of 10, so almost every fold fell back to EN87. No family earned a DEVELOPMENT CANDIDATE label, and no champion is nominated. The full grids still taught four things:

1. EN87's agreement is robust to how OI is measured. Twelve of 18 basket representations give exactly EN87's trades. Every traded parent still agrees when its own strike pair is removed.
2. The money in EN87's informed parents is decided by exits and contracts, not by more filters:
   - letting a few strong winners run instead of half-selling at +100% (EN110);
   - a nearer-to-the-money contract (EN100);
   - a 12-minute hold (EN101).

   Each rests on a handful of trades.
3. Information does not rescue looser timing (EN108), does not transfer to native E03.2 (EN106), and does not work as a size dial (EN109).
4. Three families were inert by construction, which is a finding, not an absence of work:
   - EN98's extension caps were below every E03 entry;
   - EN102's OI-opposition exit never had an observation to act on;
   - EN103's two scout fractions are identical under a three-lot cap.

## 0. What the procedure could and could not do

| Item | Value |
|---|---|
| Registered configurations | 318 cells (231 auditor + 87 mine; 306 bar + 12 packet), 36 controls, 8 references |
| Scored | 286 NIFTY configurations (181 distinct trade ledgers) and 18 SENSEX configurations (9 distinct) |
| Null | 268 OI-dependent SENSEX cells (no SENSEX OI) |
| Source-gated | 12 EN99 packet cells (one recorded expiry; ≥ 20 needed) |
| EN105 | 64 genotypes at each of 6 boundaries, plus a one-lot panel |

**Stage B support.**
- EN87's own inner-window record at the six boundaries was 9, 8, 7, 9, 10 and 8 funded parents per 60 sessions.
- The registered constraint is ≥ 10 parents plus activity in 2 of 3 blocks.
- So EN87-like cells cannot pass it, and the handoff forbids lowering it.
- Families based on EN87 fell back to EN87 in 3–5 of 5 outer folds. Their stitched outer wallets therefore mostly *are* EN87's (₹3,659 ordinary / ₹3,769 adverse from session 100).

**Recent weakness.** At the final boundary (the most recent 60 expiries), EN87's own inner wallet is −₹1,292 / −₹932, so any "final pick" would have been chosen in a losing stretch.

**Inference** is descriptive only. The family max-t and Holm over long-group t over-reject on negatively skewed nulls (9.7% and 8.8% at a nominal 5%; `calibration9*.json`). This was decided before the score.

## 1. References (NIFTY, 197 expiries, independent sessions; wallet = one continuous ₹30,000 wallet)

| Book | Ordinary | Adverse | Parents | Net without best two | Wallet ordinary / adverse |
|---|---:|---:|---:|---:|---|
| E03_env (matched) | 3,006 | 2,246 | 55 | −1,298 | −3,445 / −4,035 (adverse halts) |
| **EN87** | **6,114** | **5,841** | 25 | 2,645 | 5,306 / 4,948 |
| EN87, one lot | 3,735 | 3,063 | 25 | 1,155 | 3,735 / 3,063 |
| Native E03.2 | 14,275 | 11,586 | 66 | 652 | −4,123 / −4,036 (halts Jan 2024) |
| Native EN55 | 13,165 | 11,056 | 68 | 1,045 | 3,445 / 11,573 |

All four archived headlines reproduce exactly (`verification9.json`).

## 2. Family verdicts

| Family | Frozen label | What the full grid shows |
|---|---|---|
| EN96 agreement range | INCONCLUSIVE — support | A moderate band (L 10–15 min, p 60–70) adds 2–5 parents and up to +₹8/session; p90 and L30 always worse |
| EN97 basket stability | INCONCLUSIVE — support | 12/18 representations identical to EN87; only the frozen-13:00 anchor loses winners |
| EN98 extension | INCONCLUSIVE — support | Inert: every EN87 entry is 2.5–7 ATR extended; caps of 0.5/1/2 ATR remove everything |
| EN99 entry timing | INCONCLUSIVE — support | Every delayed style loses (−₹16 to −34/session); arms mostly expire unfilled while their moves pay |
| EN100 contract | INCONCLUSIVE — support | Nearer contract on the same 25 clocks: +₹5,600 (one lot), mostly 2025 |
| EN101 continuation | INCONCLUSIVE — support | 12-minute caps gain (+₹4.9 to +10.7/session), mostly from holding 12, not from the evidence; 24 minutes loses |
| EN102 damage exit | INCONCLUSIVE — support | Inert: opposing OI never appears inside an EN87 hold; damage-only exits hurt |
| EN103 scout | INCONCLUSIVE — support | Every staged cell loses ~₹2,000; ⅓ and ½ identical |
| EN104 delayed agreement | INCONCLUSIVE — support | 1–2 extra parents at best; E03-still-signals never fires |
| EN105 combinations | INCONCLUSIVE — support | Components existed at only 2 of 6 boundaries |
| EN106 OI on native E03.2 | NO IMPROVEMENT | Gating E03.2 removes its winners; veto ≈ native; E03.2's wallet still halts |
| EN107 second sources | INCONCLUSIVE — support | Synthetic forward and basis add nothing or hurt; SENSEX cannot form thresholds |
| EN108 looser timing | INCONCLUSIVE — support | OI cuts the damage of looser timing but never makes it pay |
| EN109 graded size | NO IMPROVEMENT | Full size on agreement is best; weak-agreement lots lose; no dose-response |
| EN110 exit geometry | INCONCLUSIVE — support | Target +150%: +₹5,000–6,000 on every stop/keep, from 4 trades that also gain in E03_env |

## 3. Family by family

### EN96 — how strict must the OI agreement be? (32 cells)

**Hypothesis.** EN87 (15-minute OI change, 80th percentile, 20-session history) might be one lucky corner of a wider band.

**Where it won.** A moderate band beats EN87, and in its best cells the extra parents are net winners:

| Cell (L, p, H) | Ordinary / adverse | Parents | Net without best two | Wallet | Gain per session (adverse) |
|---|---|---:|---:|---|---:|
| (10, 60, 20) | 7,983 / 7,417 | 30 | 3,678 | 7,057 / 6,525 | +8.0 |
| (10, 70, 40) | 7,468 / 7,091 | — | — | — | +6.3 |
| (15, 60–70, 40) | 6,915 / 6,597 | — | — | — | +3.8 |

- In (10, 60, 20), five added parents net +₹1,869 and none of EN87's are removed.
- On the common warm-up support (156 sessions from 2023-11-09), the best cells gain +₹11.6 per session.

**Where it lost.**
- Every p90 cell loses (−₹7.8 to −24.2/session): it removes 2–9 parents including 2–5 winners.
- Every 30-minute cell loses (−₹4.8 to −15.9).

**Neighbours.** The improvement is a band (L 10–15, p 60–70), not one cell; 26% of cells beat EN87 and the median cell is −₹4.8.

**Controls.**

| Control | Ordinary / adverse | Notes |
|---|---|---|
| Sign-only agreement | 3,428 / 3,281 | 45 parents; the adverse wallet ends −₹3,575 |
| Raw crossings | 4,522 / −3,886 | 166 parents; the wallet halts |
| Unrelated-day OI | −118 / −388 | 4 parents |

**Random-retention control.** Keeping the same number of E03 signals per quarter and half-hour at random gives a median of ₹4,587 / ₹4,169 (p90 ₹6,896 / ₹6,456). EN87 ranks 31st of 40. Much of EN87's gain over E03_env comes from trading less in those bins; its choice of *which* signals is only modestly better than random.

**Support.** 16–31 parents; Stage B chose (5, 60, 40) in 2 folds and fell back in 3.

**Next.** A p60–70 / L10–15 band is the place to look on new data; tightening beyond EN87 is rejected.

### EN97 — is the agreement one strike or broad information? (18 cells)

- **Identical ledgers.** Twelve of 18 representations (half-width 1–3; current or lagged ATM; pooled or jackknife) give **exactly EN87's trade ledger**. Their S values and thresholds differ (e.g., at one minute S = −0.0097 / −0.0111 / −0.0133 for widths 1/2/3), but the yes/no decision at E03's clocks is the same.
- **Leave-traded-pair test.** All 25 traded parents still agree when the pair containing the traded strike is removed. The largest pair carries 42% of the absolute OI change on average.
- **ATM boundary.** The ATM moved between i−15 and i at 82% of EN87 events.
- **Lost.** Only the frozen-13:00 anchor loses (4,573–4,953): it drops 2–4 parents including 1–2 winners. One-minute-stale OI costs ₹0.5/session.

**Verdict:** the information is broad and robust to representation. That is good for the mechanism, but it means representation changes cannot add money.

### EN98 — stop paying after excessive extension (12 cells): inert

- Every EN87 event is extended 2.49–7.01 of E03's 10-bar ATR over 15 minutes (median 4.80). E03's own setup requires a ≥ 2.5 ATR impulse, and only 11.7% of all E03_env events are ≤ 2 ATR.
- So the caps of 0.5, 1 and 2 ATR remove every EN87 event (zero trades). The reversed diagnostics (keep only X > 0.5/1/2) equal EN87.
- The only active variation: ER10 ≥ 0.5 removes one winner (−₹1,806).

**Verdict:** the grid was scaled below this signal's range, so the family did not answer its question. A corrected registration would need caps around 3–6 ATR, and only on new sessions.

### EN99 — enter more patiently (17 bar cells; 12 packet cells source-gated)

- **Result.** Every confirmation and reclaim cell loses heavily against immediate entry (−₹16 to −34/session). They trade only 0–5 parents.
- **Arm outcomes** (of 38 events, e.g. confirm 3 min / 0.1 ATR / 1.08):

  | Outcome | Count |
  |---|---:|
  | Triggered | 8 |
  | Time limit expired | 19 |
  | Unaffordable at the event | 5 |
  | Another arm already active | 4 |
  | Window end | 1 |
  | Information lost | 1 |

- **The arms that never filled were winners on average:** +₹161 to +219 per lot at +8 minutes, positive 52–61% of the time. Waiting misses the moves EN87 exists for.
- **Deterministic delays:**

  | Delay | Ordinary / adverse | Parents |
  |---|---|---:|
  | 1 minute | 5,139 / 4,612 | 17 |
  | 3 minutes | 6,956 / 6,082 | 15 |
  | 5 minutes | 2,870 / 1,994 | 12 |

  The neighbours disagree, so this is not a plateau (round 7's EN81 showed the same spike pattern).

**Verdict:** immediate entry stays. Packet tests remain blocked by data.

### EN100 — a better contract without new admissions (9 cells, one lot)

- **Result.** Nearest-ATM-affordable and minimum friction-to-reserve choose identical contracts here: 9,335–9,498 / 7,914–8,103 on 24–25 parents, against 3,735 / 3,063 for EN87 at one lot.
  - Matched clocks gain +₹5,600: +₹6,396 on the reference's winners, −₹796 on its losers.
  - Net without the best two is 4,707–4,870.
  - Wallets are 8,501–9,537 / 7,236–8,171.
- **Equal reserve.** One nearer lot also beats EN87's native three far lots (6,114 / 5,841) within the same ₹2,500.
- **Where.** 13 of 22 changed parents gain (e.g., Dec 30 2025 +₹1,761, Sep 2 2025 +₹1,090, Feb 22 2024 +₹864). The stops cost more (Apr 4 2024 −₹635, Apr 25 2024 −₹463, Feb 24 2026 −₹450).
- **Concentration.**

  | Year | 2023 | 2024 | 2025 | 2026 |
  |---|---:|---:|---:|---:|
  | Gain vs one-lot reference (₹) | +476 | +45 | +4,459 | +620 |

  By half: first +₹521, second +₹5,079. It leans on 2025.
- **Friction cap.** The legacy chooser with a friction cap of 0.05 halves activity (11 parents) and loses.
- **Unrestricted control** (EN92-style, no admission rule): 6,103 / 4,517. Its 5 extra admissions lose −₹3,700. The admission rule is what separates this from EN92.
- **Uncalibrated family max-t** for the best cell: 0.047 (descriptive; true size could be near 10%).

**Verdict:** the strongest contract lesson so far, but most of its weight is in one year. Retain as a mechanism to test on new sessions.

### EN101 — earn the right to hold longer (18 cells)

- **12-minute caps all gain** (+₹4.9 to +10.7/session); the best is 12 / information / 20% activation (8,250 / 7,944).
- **16 minutes** is roughly neutral. **24 minutes with information-only permission loses badly** (1,795 / 1,573).
- **Most of the gain is simply holding to 12 minutes.** The fixed 12-minute control makes 7,961 / 7,766 (+₹9.8/session). The equal-activity random extensions are flat (−₹0.6 / +₹0.3 / −₹1.9).
- **The evidence-gated cell changes only 4 parents:** +₹1,129, +₹1,125, +₹278, −₹396.
- Fixed 16 and 24 minutes: 5,415 and 300.

**Verdict:** the 8-minute clock may be slightly short for informed parents; long holds are rejected (EN91's survival lesson holds).

### EN102 — exit when information and damage agree (18 cells): inert

- All 18 cells equal EN87 exactly.
- On the basket fixed at entry, d·S15 never turns negative inside any EN87 hold (holds of 3–41 minutes). A 15-minute OI flow strong enough to admit a trade does not reverse within it, so the exit never has an observation.
- Damage-only controls (no OI) hurt:

  | Control | Ordinary |
  |---|---:|
  | Entry damage 1 / 2 / 3 bars | 2,387 / 1,626 / 3,630 |
  | Structure damage 1 bar | 4,132 |
  | Structure damage 2–3 bars | = EN87 |

- Archived EN94 (raw entries plus its OI exit) is 2,400 / −5,275.

**Verdict:** on informed entries an OI exit is redundant; price-damage exits cut winners.

### EN103 — scout first, add on confirmation (13 cells)

- Every staged cell loses: 3,784–4,221 / 3,585–3,939 (−₹9.7 to −11.4/session).
- One-third and one-half give identical splits under the three-lot cap (registered finding).
- The conservative full-entry control, which reserves room for the add but buys everything at once, makes 5,232 / 4,241. So about ₹900 of the cost is the reserved add room, and the delayed add loses another ₹1,000–1,450.

**Verdict:** scouting helps a wallet only when the first lots are often wrong. For informed parents it starves the winners.

### EN104 — recover E03 setups whose OI agrees a little later (18 cells)

- "E03 still signals the same side" never happens within 1–5 minutes, so all 9 cells equal EN87.
- "Structure holds":

  | Cell | Result |
  |---|---|
  | p70 | adds 2 losing parents (−₹296) |
  | p80, 3 min | +1 parent (+₹1,155) |
  | p80, 5 min | +2 parents (+₹1,444); best cell 7,558 / 7,141, +₹6.6/session |
  | p90, 5 min | +₹289 |

- Unconditional controls:

  | Entry delay | Ordinary / adverse | Notes |
  |---|---|---|
  | +1 minute | 8,204 / 7,210 | 40 parents; 15 added parents net +₹2,090, but without best two only 1,251 |
  | +3 minutes | 4,190 / 3,173 | adverse wallet −₹2,816 |
  | +5 minutes | 4,561 / 2,687 | — |

**Verdict:** delayed agreement can recover one or two good parents; support is too thin to say more.

### EN105 — chronological component combinations (64 genotypes per boundary)

- **Most boundaries had nothing to combine.** At boundaries 100, 120, 140 and 197 every gene fell back to the reference, so all 64 genotypes were identical to EN87.
- **Boundary 160:** only the signal gene (EN96 5/60/40) existed. The pick changed nothing in the outer block.
- **Boundary 180:** signal + contract (nearest, 0.10) + management (EN101 12/info/0.2) were selected.
  - The chosen genotype 100110 made +₹500 / +₹154 in its 17-session outer block, against −₹873 / −₹1,419 for EN87 (3 against 2 parents).
  - Mean single-gene changes, inner adverse: signal +₹3,097, management +₹1,874, contract −₹263. Outer: signal +₹153, contract +₹1,420.
- **Stitched wallet** from session 100: ₹3,730 / ₹5,342 against EN87's ₹3,659 / ₹3,769. The outer paired gain is +₹16.2/session on 13 parents [−17.7, +50.5].

**Verdict:** the composition machinery works (genotype 000000 = EN87 at every fold), but there was too little support to learn interactions.

### EN106 (mine) — does EN87's information beat native E03.2? No

- **GATE** (60–80th percentile) keeps E03.2's wallet alive (never halts), but costs −₹35/session: 5,661–5,850 / 4,550–4,716. It removes 33–36 native parents worth +₹7,575 to +8,591, including 12–14 winners.
- **Most of E03.2's profit is in trades OI did not confirm:** the 14:30–15:00 window and the 2× puts. The bridge cells show this:
  - Extending EN87 to 15:00 lowers it (4,449–5,685).
  - Doubling its puts inside the matched ₹2,500 lifts it to 6,978 / 6,665.
- **VETO** (skip only strong opposition, 70–80th percentile) gives 14,458 / 11,798. That is +₹1.1/session over native, from one removed losing parent (−₹183), and the wallet still halts in January 2024. VETO 90 equals native.
- **TILT** (one lot unless OI agrees) loses −₹42 to −45/session.
- **On EN55:** VETO gives 14,085 / 12,016, wallet 4,366 / 12,533. That is slightly above native EN55's 13,165 / 11,056 (wallet 3,445 / 11,573), a +₹920 / +₹960 change on 2 removed parents.

**Verdict:** information cannot be bolted onto E03.2's own money and window. E03.2's problem (its halt) is not an information problem.

### EN107 (mine) — second information sources (16 cells)

| Cell | Ordinary | Notes |
|---|---:|---|
| Synthetic forward alone | 2,541–2,920 | 11–15 parents |
| Basis alone | −318 to −2,109 | removes 19 parents including 10 winners |
| OI ∨ basis, p70 | 6,788 / 6,300 | best cell, +₹2.3/session; 4 added parents +₹674 |
| Every AND rule | below EN87 | removes winners |
| Every rule with synthetic forward | below EN87 | — |

- On SENSEX, fresh futures exist in only ~74% of window minutes. No session meets the 95% coverage rule, so neither threshold ever forms and the cells traded nothing: effectively DATA UNAVAILABLE, not a result.
- **Reporting slip.** The VOTE2 cells were run on SENSEX because the OI check tested the name string. They traded nothing and are reported as unavailable.

**Verdict:** OI remains the only useful source; a second source cannot cure EN87's sparsity.

### EN108 (mine) — looser timing, stronger information (18 cells)

- **Ungated looser timing is a disaster:**

  | Efficiency | Ordinary / adverse | Parents |
  |---|---|---:|
  | 0.5 | −29,137 / −33,994 | 238 |
  | 0.6 | −13,144 / −19,949 | 153 |

- **The OI gate removes most of that damage but never makes it pay:**

  | Efficiency | Ordinary | Adverse | Wallets |
  |---|---|---|---|
  | 0.5 | −2,334 to +1,259 | −617 to −5,883 | halt |
  | 0.6 | −359 to 3,833 | −1,863 to +1,659 | negative |

- A wider premium band (₹30) at E03's efficiency also loses (3,009–3,192 / 1,554–1,935).

**Verdict:** rescue failed. E03's strict trend gate is essential; information is not a substitute for timing.

### EN109 (mine) — size by agreement strength (12 cells)

- No cell beats EN87.
- Trading weak agreement (0 ≤ z < 1) at one lot adds 13 parents that lose −₹831.
- Cutting the agreeing tier to 1–2 lots removes winner size (−₹738 to −1,934).
- **One-lot, 8-minute dose-response by z:**

  | z bin | Mean (₹) | Trades |
  |---|---:|---:|
  | < 0 | −79 | 11 |
  | [0, 1) | −40 | 14 |
  | [1, 1.5) | +564 | 5 |
  | [1.5, 2) | −301 | 4 |
  | ≥ 2 | +74 | 22 |

  Agreement works as a threshold, not a dial.

**Verdict:** full size on agreement, nothing below it — EN87 as is.

### EN110 (mine) — exit geometry for informed parents (18 cells)

- **Target +150% wins in every cell** (all three stops × both runner keeps): 11,174–12,153 / 10,508–11,215 (+₹23.7 to +27.3/session), without best two 5,529–6,478.
- Target +100% with a tighter runner (keep 0.7): +₹3.8 to +6.2. Target +60% always loses (−₹13.6 to −20.5). The stop level barely matters.
- **Where.** Four parents carry the whole gain. On each, EN87 sold half at +100% and its runner trail (half of the peak) gave back a sharp spike; holding full size to the 8-minute clock sold higher.

  | Date | Gain (₹) |
  |---|---:|
  | Sep 2, 2025 | +1,808 |
  | Feb 22, 2024 | +1,431 |
  | Aug 8, 2024 | +1,003 |
  | Dec 30, 2025 | +817 |

  2023 and 2026 are unchanged; each half of the calendar gains about +₹1.8k to +₹3.5k depending on the cell.
- **Post-score transfer** (`post9.json`, descriptive):
  - The same change on E03_env adds exactly the same +₹5,059.69 from the same four trades. **The effect is not about OI information.**
  - On native E03.2 it adds +₹4,729 ordinary / +₹4,491 adverse (+₹4,979 on its winners), but E03.2's wallet halts on the same day as before, so the wallet result does not change.
  - On EN55 +₹419; on SENSEX nothing (no SENSEX trade reached +100%).
- **Uncalibrated family max-t:** 0.039 (descriptive).

**Verdict:** a real exit question: E03's runner gives back too much on sharp expiry spikes. But the evidence is 4 tickets in 2 years, on studied data. It is worth a registered test only on sessions never studied.

## 4. Data, verification and limits

**Verification** (`verification9.json`, PASS):
- 304 ledger identities;
- 37 behaviour-duplicate groups consistent;
- 32 of 32 configurations rerun identically in a fresh process;
- reference wallets reproduced;
- every Stage B pick re-derived from its own records;
- the inner window always ends before its outer block;
- EN105's 000000 genotype equals EN87 at every boundary;
- 268 SENSEX OI cells are null.

**Pre-score receipts:**
- parity: 15,342 arm-days, 0 mismatches;
- reproduction: 11 reference cells exact;
- 972 causal prefix checks;
- 17 mechanics tests;
- selftest.

**Limits:**
- All sessions were studied before; Stage B is a selection stress test, not out-of-sample evidence.
- Fills are bar-lifecycle proxies (next-bar open ± declared half-spread, 20%-volume capacity). Adverse and catastrophe stresses are in the tables.
- SENSEX has no OI and thin futures.
- No engine, configuration, `.env`, scheduler, broker or Production change. Production stays `55b5e942`; E03.2 and EN55's registration are unchanged.

## 5. Next decisions (the owner's)

1. **Unseen sessions are the only route to an answer.** EN87's pace (about one parent per eight expiries) means a forward test needs about 158 expiries for 20 parents.
   - The realistic test set is NIFTY 2020–22 expiry afternoons, if a download through the breeze-history-download skill includes option OI.
   - On those, one new registration could test, unchanged:
     - EN87 with target +150%;
     - EN87 with the nearer one-lot contract;
     - EN87 with a 12-minute hold.
2. **A corrected EN98** (extension caps of 3–6 ATR) would need the same unseen data.
3. **E03.2 itself.** Nothing here makes E03.2's wallet survive. Its halt is a 2023–early-2024 losing stretch that no information or exit change in this round removes.
