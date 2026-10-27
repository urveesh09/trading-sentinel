# F&O consistency grid — 2026-10-27 (O27)

The owner's request on Oct 27 was to test many mixed-and-matched strategies on the archived F&O sessions: "I don't want the most earning one. I want the one that is most consistent."

This file was written and `freeze.json` committed **before any arm was scored**. The results section below the line is added after the run, and the frozen part is not edited.

## What is replayed

Every arm is the whole NIFTY single-leg paper book, run through `python-engine/fno_policy_replay.py`:
- the live entry plan, strike choice, sizing and loss brakes;
- the exit ladder at fast-exit cadence (each archived quote batch, about 60 s);
- buys at the ask and sells at the bid, with real charges.

Each arm changes one entry signal and one exit setting; everything else is the shipped book: target 1.8R, the 25% premium backstop, hard flat at 15:10, 3 trades a day and the expiry-day block.

**Entries: 5 families, each with and without the EMA check.**

| Entry | Definition |
| --- | --- |
| OR30 | The shipped break: a 30-minute opening range and the first close beyond it ±0.25 ATR (`evaluate_fno_mom`). |
| OR20 / OR45 | The same, with a 20- or 45-minute range (recorded shadow variants). |
| CONFIRM1 | One confirming bar after the cross, with extension of at most 0.35 ATR (recorded shadow variant). |
| CONT | The break, or after it a pullback to within 0.25 ATR of the break level followed by a bar that resumes (recorded shadow variant). |
| *_NOEMA | The same entry without the multi-day EMA(21/50) agreement (`FnoShadowVariant.ema_filter=False`). |

**Exits: 4 locks × 3 time stops × 3 trails.**

| Axis | Values, in neighbour order |
| --- | --- |
| Profit lock | TIGHT (arms at 0.25R, keeps 60% of the best gain), LIVE (0.40R, keeps 50%), LATE (0.80R, keeps 50%), OFF. All have a 0.10R floor. |
| Time stop | 30, 45 or 75 minutes, needing 0.5R by then. |
| Trail after the target | 0.6, 1.0 or 1.5 ATR. |

That makes 10 entries × 36 exits = 360 ranked arms, plus one parity arm.
- **CURRENT** is `OR30|LOCK_LIVE|T45|TR1.0`, the shipped book. The freeze checks that the live settings still equal it.
- **The parity arm** evaluates the shipped break through the variant code path, with the EMA check on. It must trade exactly as CURRENT; otherwise the with/without-EMA comparison is confounded.

## Data

- **Source:** a read-only export of the Production research archive (`scripts/export_fno_replay_dataset.py`, run Oct 27 at 16:30 IST).
- **Sessions:** 29 NIFTY sessions, Sep 10 – Oct 26, all sealed. They are kept out of git under `_local/dataset/`; `freeze.json` binds the manifest hash.
- **A_select (choosing):** Sep 10 – Oct 9, 19 sessions.
- **B_check (checking):** Oct 12 – Oct 26, 10 sessions. Expiry days count as sessions; the single-leg book does not trade on them.
- **Settings:** all 123 effective `FNO_*` settings in Dev equal Production's. They were compared by per-key hash, and only names were printed.

**All of this data has been seen before.**
- A_select was used by earlier F&O studies.
- B_check was the Oct 24 entry study's decision window.
- Oct 21, 23 and 26 are the days whose rejected breaks prompted the no-EMA entries. A no-EMA arm that passes B is therefore partly circular.

The grid can rank robustness on seen data; it cannot qualify anything. The first untouched evidence is forward sessions from Oct 28.

## Selection rule (frozen)

1. **Consistency score (CS)** for an arm in a window = net excluding its best winner ÷ max(max drawdown, ₹1,000). It rewards profit that does not depend on one trade and is earned with a small drawdown.
2. **Eligible on A:** at least 8 trades, net > 0, and net excluding the best winner > 0.
3. **Score = plateau CS:** the median CS on A of the arm and its exit neighbours. A neighbour has the same entry and is one step away on exactly one axis. A lucky spike surrounded by losing settings scores low; a region that works scores high.
4. **Rank:** plateau CS, highest first. Ties go to the higher green-week share on A, then fewer red days, then the name.
5. **Check on B:** net ≥ 0, and max drawdown ≤ max(1.5 × CURRENT's B drawdown, ₹5,000).
6. **Recommended:** the first ranked arm that passes the check. If none passes, keep CURRENT.

**What a recommendation allows:** a broker-free live shadow plus a nightly replay forward.
- There is no paper or live change in the proving week (Oct 26–30). The Nov 2 real-money test mirrors the paper book.
- Promotion is the owner's call, made on forward evidence.

## Run

```
python scripts/run_fno_consistency_grid.py freeze --data docs/research/fno/2026-10-27-consistency-grid/_local/dataset --out docs/research/fno/2026-10-27-consistency-grid
python scripts/run_fno_consistency_grid.py run --out docs/research/fno/2026-10-27-consistency-grid --jobs 6
```

`run` refuses to start if any bound source, dataset file or setting has changed since the freeze.
- Each arm is replayed once over the whole window, and its trades are split by entry date. Sizing and brakes therefore carry over from A into B, as they would live.
- Each arm's report is written once under `_local/arms/`.
- The parsed sessions are cached under `_local/observations/`.

---

## Results (run Oct 27, 16:39–17:37 IST, 6 workers; `results.json`)

- **Parity:** the shipped break, run through the variant code path, traded exactly as CURRENT, so the EMA comparisons are clean.
- **Verdict under the frozen rule:** `SHADOW_CANDIDATE`, pick `OR20|LOCK_LATE|T75|TR1.5`; 32 of the 360 arms were eligible on A.
  - CURRENT ranks 27th of the 32. On full-window CS it is at the 83rd percentile of all 360 arms.
- **The rule had a gap, found only after scoring, so it is reported here rather than repaired.** An arm with **no trades** in B_check passes "net ≥ 0". The pick made **0 trades from Oct 12 to Oct 26**, as did 10 of the 32 eligible arms, so its check tested nothing.
  - The pick stands as the frozen rule's answer, but it has no out-of-sample support.
  - Post hoc, and not the frozen rule: if at least one trade in B had been required, the first passing arm would be #7, `OR20_NOEMA|LOCK_LATE|T75|TR1.5`. Its B trades fall on Oct 21, 23 and 26, the days that suggested the no-EMA idea.

| Arm (window: trades, net ₹, max DD ₹) | A Sep 10–Oct 9 | B Oct 12–26 | All 29 sessions | Net without the top two trades | Days traded / green |
| --- | --- | --- | --- | --- | --- |
| `OR20\|LOCK_LATE\|T75\|TR1.5` (frozen pick) | 11, +12,916, 2,877 | 0, 0, 0 | 11, +12,916, 2,877 (PF 3.0) | −1,616 | 8 / 5 |
| `OR20_NOEMA\|LOCK_LATE\|T75\|TR1.5` (post hoc) | 15, +11,266, 3,423 | 4, +19,301, 831 (+1 unpriced) | 19, +30,567, 3,423 (PF 3.9) | +13,693 | 15 / 10 |
| CURRENT `OR30\|LOCK_LIVE\|T45\|TR1.0` | 12, +7,286, 1,991 | 1, +3,515, 0 | 13, +10,801, 1,991 (PF 3.0) | +178 | 10 / 6 |

What holds across many arms is more reliable than any single winner:
- **No arm is a daily earner.** The best arms trade on 8–15 of 29 sessions and are green on 5–11. Every arm's profit comes mostly from a few trend days held with a trail. The single-leg opening-range book loses small often and wins big rarely.
- **A 20-minute opening range is the most robust entry.**
  - All 36 OR20 exits are profitable over the full window, at the lowest median drawdown of the frequent families (₹2,877).
  - 21 of the 32 eligible arms are OR20 or OR20_NOEMA.
  - The top six ranks are OR20 with a 75-minute time stop, a plateau rather than one lucky setting.
- **Time stop:** 30 minutes is the worst setting (70% of arms profitable; median ₹5,498). 45 minutes gives 90% and ₹10,244; 75 minutes gives 86% and ₹9,635.
- **Profit lock and trail settings barely matter.** Medians range ₹7.2k–10.2k; the extra rupees are not worth more tuning.
- **Continuation (CONT, with the EMA check) loses:** only 1 of 36 exits is profitable, at a median of −₹4,182. CONFIRM1 trades too rarely to judge (3–5 trades).
- **The EMA check depends on the regime, and neither keeping nor removing it wins everywhere.**
  - On A, removing it raised net in only 3 of 36 exits for OR30, 4/36 for OR20 and 1/36 for OR45. The medians fell from ₹6,194 to −₹1,510, ₹6,493 to ₹3,304 and ₹4,542 to ₹1,366: the check filtered bad trades in September and early October.
  - On B, removing it raised net in 36/36 exits for OR30, OR20, CONFIRM1 and CONT. It lagged the late-October trends; those days motivated the idea.
  - A smarter trend check, one that notices when the multi-day trend has turned, is a new hypothesis. It would be frozen and judged on forward sessions only.
- **Unpriced:** 32 arms (every no-EMA family except CONFIRM1, 8 exits each, on Oct 21) hold the same put (NIFTY 23050 PE, bought 10:45) that went deeper in the money than the archived ATM±5 strikes, so it cannot be priced or scored. These puts were held through a 311-point fall, so the B figures of those arms probably understate them; the amount is unknown.
- **Earlier exploration (scratchpad, not frozen, Sep 10–Oct 23):** 12 quick-scalp single-leg designs all lost after charges, from −₹427 to −₹8,932. These were momentum bursts, pullbacks and fades with ₹200 targets or 0.6-ATR exits. Of 6 debit-spread versions, one was positive: +₹962 over 22 trades, which is noise. Charges plus spread are about ₹75 a round trip, against moves that pick a side correctly only 42% of the time before −₹300.

**Next steps (owner's call):**
- Forward-only evidence for the frozen pick, the post-hoc no-EMA arm and CURRENT.
  - Re-export the archive after each session seals, replay the three arms on sessions from Oct 28, and score them with the same metrics.
  - This needs no Production change. The paper and live books stay as they are through the proving week and the Nov 2 real-money test.
- Decide after about 10 forward sessions. Nothing here qualifies a strategy, and tests do not show profitability.
