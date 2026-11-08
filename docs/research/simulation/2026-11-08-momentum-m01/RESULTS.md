# M01 results: the sealed Jan–Jul 2026 exam (scored once, November 8, 2026)

The freeze was `5a90870`, fixed before any scoring in `8f61189`. The exam then ran once, on the owner's word ("open it now"), with `python signals.py EXAM` and `python exam.py`. Its output is `results.json`.

- **Window:** 143 sessions, Jan 1 – Jul 31, 2026.
- **Data:** about 490 names plus NIFTY 50, full-day 15-minute bars from the Oct 5 Kite snapshot.

| Arm | Trades | Gross | Costs | Net | Net without best day | Max drawdown | Verdict |
|---|---:|---:|---:|---:|---:|---:|---|
| A0 shipped entries, live exits | 675 | −₹608 | ₹33,418 | **−₹34,026** | −₹36,733 | ₹34,101 | fails |
| A1 MOM_SELECTIVE, live exits (**the live rule**) | 85 | +₹864 | ₹4,208 | **−₹3,344** | −₹5,025 | ₹4,770 | fails |
| A2 MOM_SELECTIVE, VWAP exit | 85 | −₹468 | ₹4,205 | −₹4,674 | −₹6,896 | ₹6,896 | fails 3 of 5 checks |
| **A3 stocks-in-play breakout, VWAP exit** | 357 | +₹8,221 | ₹3,462 | **+₹4,759** | +₹3,449 | ₹3,343 | **passes all 5** |
| NULL: A3's rules on random liquid names | 279 | −₹6,602 | ₹2,763 | −₹9,365 | −₹9,686 | ₹9,951 | control |

**Hypotheses.** These compare each stock's 10:15 to 14:30 move with the day's mean, over 68,291 stock-days.
- **H1, momentum: fails.** The first-hour top decile did −0.031%, positive on 65 of 143 days.
- **H2, reversal: holds weakly.** The first-hour bottom decile did +0.033%, positive on 71 days.
- Aug–Nov showed the same: −0.059% and +0.093%.

## What it means

**The current Momentum rules have no edge.**
- The shipped entry was flat before costs on 675 unseen trades and lost on 165 seen ones. Costs of about ₹49 a full-pool trade decide the result.
- The live MOM_SELECTIVE rule lost ₹3,344 on 85 unseen trades.

**Buying intraday strength does not pay here.** In this universe, first-hour winners lag over the rest of the day on both windows.

**What did work is selection plus a VWAP exit.** A3 takes the 5 names with the heaviest first 15 minutes against their usual volume, with a green first bar, and sells at the next open after a close under VWAP.
- It beat random names under the same rules by ₹14,124 on the exam and by ₹119 on Aug–Nov.
- The stop almost never fires (5 of 512 trades). The VWAP exit does the work.

**But it is thin and mixed.**
- Exam: +₹4,759, or +₹13 a trade. Four of seven months were positive: −₹2,030, +1,177, −315, +2,186, −1,142, +1,668, +3,215.
- Aug–Nov: −₹2,531, two of four months positive.
- Together, 11 months come to +₹2,228 over 512 trades (₹50,000 book, five ₹10,000 slots, no leverage).

By the frozen rule it is **promising**: it goes to paper shadow and nothing else.

## Built (Dev): the A3 paper shadow

- **Module:** `python-engine/momentum_orb_shadow.py`.
- **When it runs:** 15:05 Mon–Fri on trading days, behind `MOMENTUM_ORB_SHADOW_ENABLED` (default true).
- **What it does:** it replays the frozen rule on that day's cached 15-minute and daily bars. It makes no Kite call and has no order path.
- **Store:** `<DB_PATH>.momentum-orb-shadow.db`.
- **Report:** `GET /experiments/momentum` returns it as `orb_shadow`.
- **Parity:** `runtime_parity.py` reproduces the research arm trade for trade, with 0 mismatched sessions:
  - Aug–Nov: 57 sessions, 155 trades, −₹2,531.33;
  - Jan–Jul: 143 sessions, 357 trades, +₹4,759.01.

**Unchanged:** MOM_SELECTIVE still decides the Momentum paper entries, and the owner's live-entry halt stays on.

**Next:** judge the shadow after at least 30 sessions and 100 trades, against its own random control and against the paper book on the same days. Real money is the owner's call.

Jan–Jul 2026 is now SEEN for Momentum. No unseen Momentum history is left, only sessions from Nov 9 on.
