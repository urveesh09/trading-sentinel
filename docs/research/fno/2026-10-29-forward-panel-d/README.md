# F&O forward panel D (O29b): the opening-drive filter, from Oct 29

Research only. Neither arm trades. The paper and live F&O books are unchanged, and so are the proving week (Oct 26–30) and the real-money test (Nov 2–6).

## Why

The O29b chop study (`../2026-10-28-chop-study/README.md`) asked why every breakout lost on Oct 28 and how to tell such a day in time.
- The only filter that held up out of sample is the **09:45 opening drive**: trade a breakout only on a morning whose first 30 minutes were one-way.
- It passed the frozen walk-forward for EFF (+₹20,518 against +₹13,519 unfiltered, worst day −₹1,457 against −₹7,311), and marginally for OR20.
- It did not pass for the shipped strategy.
- Every session was seen, and Oct 28 prompted the study. Only sessions from Oct 29 can tell.

## Arms (the O29b picks, chosen before Oct 29)

| Arm | What it is |
| --- | --- |
| `SHIPPED` | the shipped book (CURRENT), the control |
| `SHIPPED_DRIVE` | the shipped strategy, only on HIGH-drive mornings (did not pass; here so the owner can see it forward) |
| `OR20_DRIVE` | the O27 grid's 20-minute break, only on HIGH-drive mornings |
| `EFF_DRIVE` | the O27e efficiency break, only on HIGH-drive mornings |
| `DRIVE_BOOK_FADE` | the FINAL smart book: the breakouts on HIGH drive, the trend-day pullback, a VWAP 2σ rejection fade (its fade family failed; observed only) |

- **HIGH drive:** the drive is above the median of the previous 20 sessions' drives.
- Every arm runs through the shipped book's brakes unchanged. Panel C already runs the four together with the drive filter (`UNION_DRIVE`) from Oct 28.

## Rule (frozen)

- **Promising** means panel A's checks plus no day worse than −₹5,000:
  - forward trades ≥ 5, net > 0, net without the best day > 0, net > SHIPPED;
  - max drawdown ≤ max(1.5 × SHIPPED's, ₹5,000).
- **Alarm:** a day worse than −₹5,000 or a drawdown above ₹12,500 is flagged at the top of `REPORT.md`.
- **A filtered arm sits out many days.** Fewer trades are not a win by themselves.
- Reports before Nov 27 are provisional. Promotion is the owner's call, never in a proving week.

## Correctness

`test_panel_d.py` passes 4:
- the arms equal the study's FINAL picks;
- the extreme-loss check works;
- on the study's data, the forward machinery reproduces the study's path trade for trade, for `EFF_DRIVE` and `DRIVE_BOOK_FADE`.

`run` refuses to start if any bound input changed since the freeze: the engine sources, the panel scripts, the labs, the O28 router, the O29b study and its freeze, or the effective F&O settings.

## How it runs

- **Pinned copy:** `C:\Users\Urveesh\sentinel-operations\fno-forward-panel-d-20261029\`, with `run_panel_d.cmd`.
- **Schedule:** panel A's launcher calls it after panel C, in the owner's 16:00 IST Mon–Fri task.
- **Output:** `_local/REPORT.md`, `latest.json` and `history.jsonl` in the pinned folder.
