# N13: learn from the main book's forward misses (Nov 11, 2026)

## Question

The owner (Nov 11): "see the performance of the strategy today and of the shadows as well. It seems the shadows perform better than the main strategy. Learn from the mistakes … try to create a better strategy … better than the 012."

## What happened forward

The source is Production, read-only. The window starts with the fresh ₹2,50,000 paper start on Nov 3 and ends with the Nov 11 close.

| Book | Trades | Net |
|---|---:|---:|
| Paper main book (`fno_positions`, N11T + N012-A), NIFTY legs | 4 | +₹4,056 |
| Paper main book, SENSEX legs | 6 | −₹7,053 |
| **Paper main book, total** | **10** | **−₹2,997** |
| One-lot N11 paper record (`fno_n11_paper`, NIFTY, no brakes) | 5 | +₹12,883 |
| Forward panel B: trend pullback (TPB) alone, Oct 28–Nov 11 | 5 | +₹9,820, of which +₹8,157 is one day |

Where the main book lost ground against the one-lot record:

1. **SENSEX: −₹7,053 over 6 trades, all of them losses.** The N11/N11T/N012 research is NIFTY only. SENSEX history cannot replay the book: its futures and options minutes carry zero open interest (N012-A2 PLAN). SENSEX shares the book's 3 trades a day with NIFTY.
2. **The shared cap cost a researched NIFTY trade.** On Nov 11, after two SENSEX entries, the 14:10 NIFTY OR20 put was refused `trades_per_day`. The record took it at 14:15 and held to the 15:10 flat: +₹4,577.
3. **The native profit lock sold a runner.** On Nov 5 the NIFTY OR20 call entered at 10:51 (₹154.00) and was sold by the lock at 12:03 (₹170.95), +₹1,029. The record held the same entry on its trail to 14:22 (₹252.20), +₹6,095. This was the original lock (arm 0.40 R, keep 0.50); N012-A's trend lock went live on Nov 8.
4. **Not a mistake:** the Nov 9 TPB put (shadow estimate +₹6,871) was refused `expiry_day_block`. Nov 9 was NIFTY's expiry, and expiry days belong to the expiry book by the owner's rule.

Ten trades decide nothing. History has overruled forward impressions before: EFF lost every forward trade, but removing it cost ₹24,157 on the researched years (`docs/FNO_FINAL_STRATEGY_2026-10-31.md`). The forward panel's TPB arm is judged by its own frozen rule on Nov 27, and N13 does not act on it.

## What can be tested on history: where the lock arms

N08 found locks small and mixed: "best +4,214, and worse in 2025". N012-A2 moved only the trend rule's keep fractions, never the arm. N13 moves one number, the premium-R gain at which the native lock arms. Each arm keeps N012-A's trend rule exactly (`regular_rules.trend_params`).

| Arm | The lock arms at | Note |
|---|---|---|
| `ARM0.40` | 0.40 R | **N012-A, the centre.** It must reproduce Round 30 `TREND_ONLY` exactly in every window. |
| `ARM0.70` | 0.70 R | ADVERSE trend still caps the arm at 0.60 (N012-A's rule). |
| `ARM1.00` | 1.00 R | Same cap. |
| `LOCK_OFF` | never | No profit lock at all, native or trend-made. Stops, trail, time stops and the 15:10 flat are unchanged. |

Everything else is the Round 30 lab unchanged: N11T entries, sizing, the earned lot and tolerance, stops, costs (₹200 + ₹5 a lot), and the one-minute candle model. The data is the five seen NIFTY windows: Jun–Dec 2022, 2023, 2024, 2025 and Jan–Oct 2026. Each window starts with a fresh ₹2,50,000.

## The rule (frozen in `freeze.json` before any arm other than the centre is run)

This is N012-A2's five-check rule, with N012-A as the fixed comparison and N11T as the base of every increment:

- **Leave one window out.** For each window, pick the arm with the highest increment over N11T on the other four. The pick needs no unresolved positions and no worst day more than ₹500 worse than N11T's. Ties go to the arm nearest the centre. Score the pick on the held-out window.
- **Final pick:** the same rule on all five windows.

The final pick replaces N012-A only if all five checks hold:

1. The search's held-out sum beats N012-A's ₹4,051.45.
2. The pick's increment without its five best incremental days beats N012-A's ₹710.38.
3. Its worst day and its largest annual closed drawdown are no worse than N012-A's (−₹5,640.85, 6.97%).
4. No window loses more than ₹2,500 against N11T.
5. Its neighbours on the arm line (0.40, 0.70, 1.00, off) have a positive mean increment.

If any check fails, N012-A stays and the Nov 5 case is recorded as one trade, not a rule.

## What cannot be tested here, and what to do about it

- **SENSEX.** It cannot be replayed (zero OI). The forward record is the only evidence, and it is ten trades. The structural point does not need a replay: the paper main book trades a second index that its research never priced, and that index can take the researched NIFTY trades' daily slots. The proposal for the owner is a book that matches its research. NIFTY keeps its own 3 trades a day, and SENSEX either leaves the main book for a shadow or gets a separate allowance that never blocks NIFTY. It is the owner's call (O29e put SENSEX on the paper book).
- **The sealed NIFTY January–May 2022 exam** (`2026-11-05-fno-n12/EXAM_2022_H1.md`). It stays sealed: Q1 2022 is not downloaded, and the download is the owner's.

## Rollout and rollback

Research is Dev only. No engine file, setting, schema or Production change. If an arm is adopted, a runtime change would be a separate, tested switch (`FNO_PROFIT_LOCK_ARM_R` already exists), deployed only on the owner's word. Rollback is the old value.

## Run

`N12_YEAR=<window> N13_BUDGET_SEC=480 python n13.py` is resumable in slices of 9 minutes or less. Then `python score.py` writes `results.json`.
