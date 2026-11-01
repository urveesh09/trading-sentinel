# N10 corrections, disclosed

Every first result stays on record. Round one's failure stands. No frozen file was edited after its freeze.

## 1. The code retried where the plan said "first reaches"

**What the plan said:** `PLAN.md`: "when the future's move in the trade's favour first reaches +X R". `PLAN2.md` kept round one's add.

**What the frozen code did:** `maybe_add` tries again at later minutes, while the trade stays at or above +1R, if an earlier try was refused. Refusals are often for planned risk, which falls to nothing once the first lots' trail locks.

**How it was caught:** the audit counted earned lots whose first reach of +1R came before the add: 4 in 2024, 1 in 2025, 6 in 2026, across the fresh and one-account replays.

**What it changes:**

| | One try | Frozen code |
|---|---:|---:|
| Four-year sum | 1,98,484 | 2,33,275 |
| Earned lots, and what they made | 7, +7,043 | 15, +30,440 |
| Check 1, above N08's 2,02,284 | **Fails by 3,800** | Passes |

**The ruling.** In N09 the noise-area book left the profit lock on against its plan, and I reran it as the plan said. The same standard applies here: read as written, N10 fails check 1. The retry is a reasonable rule, but it wasn't written before the numbers existed, so it can't claim the pass. It is now stated in `EXAM_2022.md` and has to earn it on unseen data.

## 2. THIRD's two limits came from looking

- **Only on a two-lot trade:** taken from round one's split, +25,411 on 17 lots against -6,879 on 41. The reasoning fits the volatility reading, but the split was seen first.
- **Planned risk at most Rs 5,000:** the owner's own limit (O31d), and it also happens to remove HYBRID_C's worst trade, which I had seen. It is partly fitted to one trade, and it was declared so in `PLAN2.md` before scoring.

## 3. Checks 3 and 4 were loosened for round two

Round one compared falls and 2023 with N09.1. Round two compares them with N08, and `PLAN2.md` gave the reason before scoring: part of N09.1's smaller 2023 loss is the trap itself. N10 would have failed round one's check 3 by 0.08 of a point (13.21% against 13.13%) and its check 4 by Rs 214 (-32,898 against -32,684). Those are stated here so that the loosening is visible.

## 4. The cliff test I froze didn't show the cliff

`PLAN2.md` planned cost shifts of 10%. At those N09.1 CUSHION ended at 4,34,509 and 4,17,045: not stuck, and both above its base. My expectation was wrong about those two points. The trap is real but needs a finer look, so `cliff_map.py`, added after the verdict, tries costs of 195, 198, 199, 201, 202 and 205: stuck at 199 and 202. N09.1's question still passes on spread (13.1% against 4.2%), but the clear evidence is from the post-verdict map, not the frozen test.

## 5. WATCH can fire when the account isn't trapped

The rule fires when an entry is refused because no lot fits above the floor. On Jan 10, 2025 that happened with Rs 32,554 free, because the option was expensive and another position was open. The floor dropped by a slice that the account didn't need. No harm showed in these years, and the floor stays bounded, but it isn't what the rule is meant for. A live version should fire only when the account can't fund a typical lot. That version isn't tested.

## 6. The overfitting score printed by `score2.py`

It read 0.107 with two exact duplicate pairs in the panel: N09.1 + WATCH equals N09.1 in fresh years, and N10 with and without WATCH are equal in fresh years. This repeats a mistake N09 had already warned about. `after_verdict.py` removes them: 0.106 on 21 books, 0.381 on all 89 books since N08. It changes no verdict.

## 7. My first idea was wrong

I expected the earned lot to beat the entry-time lot: the rough sum from saved trades suggested so. Exact replay said +1,51,406 against +2,02,284. The rough sum left out the earned lot's own stop, the time-stop exits and the first leg that waiting gives up. Rough sums from saved trades are for choosing what to test, and the plan said so.
