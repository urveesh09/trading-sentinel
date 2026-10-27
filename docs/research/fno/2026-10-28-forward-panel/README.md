# F&O forward panel — Oct 28 to Nov 27, 2026 (O27c)

On Oct 27 the owner asked: "integrate the best and then let's do this run tomorrow and ahead to test this in upcoming month".

The best candidates from the O27 grid and the O27b evolution are tested **forward, on sessions no study has seen**.
- Each day they are replayed through the whole live book next to the shipped book.
- Nothing trades: no candidate passed a held-out check on the 29 archived sessions.
- The proving week (Oct 26–30) and the Nov 2–6 real-money test keep the paper book as it is.

This file and `freeze.json` were committed on Oct 27, before the first forward session existed. The freeze was re-made the same evening, still before any forward session, when the owner moved the daily run to 16:00 IST: the PC is usually off at 06:30, and a 16:00 run can include that day's own session. The first freeze is in commit `e6af14b`.

## Panel

| Arm | What it is | Why it is here | Archived A / B (seen) |
| --- | --- | --- | --- |
| SHIPPED | The live book: 30-min range, EMA 21/50, profit lock 0.4R, 45-min time stop, trail 1.0 | Control | A +₹7,286 (12 trades) / B +₹3,515 (1) |
| EVO_PLATEAU_1 | 20-min range, buffer 0.4 ATR, range ≤ 1.25× usual, stop 1.0 ATR, no lock, 75-min time stop, trail 1.5 | Evolution finalist 1 (most robust neighbourhood) | A +₹15,330 (9) / B +₹2,568 (1) |
| EVO_BEST_FITNESS | 30-min range, buffer 0.4, RVOL 1.0, only with the gap, range ≤ 1.25×, no lock, T75, trail 1.5 | Evolution's top fitness (9.53) | A +₹21,035 (8) / B +₹2,568 (1) |
| EVO_OR20_LET_RUN | 20-min range, no lock, 75-min time stop needing 0.25R, trail 1.5 | The simplest evolved change | A +₹21,110 (11) / B 0 (0) |
| O27_PICK | 20-min range, late lock, T75, trail 1.5 | The O27 frozen rule's pick | A +₹12,916 (11) / B 0 (0) |
| O27_OR20_NOEMA | O27_PICK without the EMA check | Keeps trading in trends against the multi-day EMA (post hoc) | A +₹11,266 (15) / B +₹19,301 (4) |

The tests tie each arm to its source: the evolution's `results.json` finalists and the O27 arm names mapped to genomes.

## Daily run

`scripts/run_fno_forward_panel.py run` runs from a pinned copy of this commit's files in `C:\Users\Urveesh\sentinel-operations\fno-forward-panel-20261028\`. A Windows scheduled task, "Sentinel F&O forward panel", starts it at 16:00 IST Monday to Friday, or as soon as the PC is on if that time was missed. Each run:
1. Takes a read-only export of the Production research archive in a throwaway container, with the data volume mounted read-only. It uses `--include-finished-today`: from 15:50 IST the day's own journal is final (the quote collector's last tick is 15:40) and is included, so the 16:00 run replays up to that same day.
2. Replays every arm from Oct 28 to the newest exported session.
3. Writes `_local/REPORT.md` (a table plus daily net per arm), `_local/latest.json` and `_local/history.jsonl` in the pinned copy's study folder. Only the newest export is kept.

A run refuses if a bound source or the effective `FNO_*` settings have changed since the freeze. The copy is pinned, so later Dev work does not change it.

## Rule (frozen)

A candidate is **promising** on the forward window (Oct 28 – Nov 27) if all of these hold:
- at least 5 trades;
- net > 0;
- net excluding its best day > 0;
- net > SHIPPED's net;
- max drawdown ≤ max(1.5 × SHIPPED's, ₹5,000).

Reports before Nov 27 are provisional; nothing is promoted or stopped early on them.

**What "promising" leads to:** the owner's decision, through Dev → GitHub → Production. That never happens during a proving week, and the real-money test keeps mirroring the paper book until the owner says otherwise.

## Limits

- **Six candidates against one control:** one of them can look good by chance over about 22 sessions. Read a pass as the next step, not as proof.
- **Unpriceable holds:** the archive holds ATM±5 strikes, so a deep in-the-money hold on a big trend day can be unpriceable. It is reported separately.
- **The control is pinned:** SHIPPED is the Oct 27 book. If the live book changes later, the panel still compares against Oct 27.
- **Python packages:** the runner uses Dev's `python-engine/winvenv` packages. If they change, results could shift slightly.
