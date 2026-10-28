# F&O forward panel C (O28b): the four studied strategies in one book, from Oct 28

Research only. Neither arm trades. The paper and live F&O books keep the shipped opening-range break, and the proving week (Oct 26–30) and the real-money test (Nov 2–6) are unchanged.

## Why

On Oct 28 the owner delegated the choice of what to forward-test next. The answer comes from the O28 regime-router study (`../2026-10-28-regime-router/README.md`).

- **Switching strategies by a 09:45 condition did not help.** So no regime switch is built.
- **Running the four studied strategies together in one book did best on the sessions the walk-forward had not seen:** +₹33,662 over 16 sessions, against +₹9,528 for the shipped break alone and +₹8,530 for the trend-day pullback alone.
- It has a bigger downside: a worst day of −₹2,784 against −₹1,461 for the shipped break, and a 29-session drawdown of ₹5,941 against ₹1,991.
- The components were chosen on those same sessions, so only new sessions can tell. Panel C replays them, beside the shipped book, on every session from Oct 28.

## Arms (committed in O28 `d3b9a70` before the Oct 28 open)

| Arm | What it is |
| --- | --- |
| `SHIPPED` | the shipped book (CURRENT), the control |
| `UNION` | SHIPPED, OR20 (O27 grid), EFF (O27e efficiency break) and TPB (O27f trend-day pullback), always on, in one book |
| `UNION_DRIVE` | the same, with the three breakouts on only when the 09:45 opening drive is HIGH; TPB always on |

- **Brakes:** both arms run through the shipped book unchanged. That means 2% of the pool at risk per trade, at most 3 entries a day, the 15% open-premium cap, the two-loss day halt and the 15% drawdown halt.
- **Exits:** each trade keeps its own strategy's exits.
- **Priority:** when two strategies signal on the same tick, the declared order is SHIPPED, OR20, EFF, TPB.

## Rule (frozen)

- **Promising** means panel A's checks plus one more:
  - forward trades ≥ 5, net > 0, net without its best day > 0, net > SHIPPED's net;
  - max drawdown ≤ max(1.5 × SHIPPED's, ₹5,000);
  - **no day worse than −₹5,000** (2% of the ₹2,50,000 paper bankroll).
- **Extreme-loss alarm:** any arm with a day worse than −₹5,000 or a drawdown above ₹12,500 (5% of the bankroll) is flagged at the top of `REPORT.md`.
- Reports before Nov 27 are provisional. Nothing is promoted or stopped on them. Any promotion is the owner's call, through Dev → GitHub → Production, never in a proving week.

## Correctness

- `test_panel_c.py` passes 6:
  - On the O28 study's data, the forward machinery reproduces the O28 `UNION` path exactly (every trade and its strategy). It also recomputes the study's 09:45 values for all 29 sessions identically.
  - The arms are the O28 configs.
  - The contract map follows the roll to the November future.
  - The extreme-loss check and alarm work.
- **Each forward run** recomputes the 29 study sessions' 09:45 values from the fresh export. Any difference is printed in the report, because it would mean UNION_DRIVE's gating no longer matches the frozen rule.
- **Bound inputs:** `run` refuses to start if any bound input changed since the freeze: every engine source, the panel scripts, both earlier labs, the O28 router and its freeze, or the effective F&O settings.

## How it runs

- A pinned copy lives at `C:\Users\Urveesh\sentinel-operations\fno-forward-panel-c-20261028\` and has its own `run_panel_c.cmd`.
- Panel A's launcher calls it after panels A and B, in the same 16:00 IST Mon–Fri task.
- Each run takes a fresh read-only export of the Production research archive and replays all three arms from Oct 28 to the newest finished session.
- Output: `_local/REPORT.md`, `latest.json` and `history.jsonl` in the pinned folder.

Manual run, from the pinned folder:

```
"C:\Users\Urveesh\Desktop\trading-sentinel\python-engine\winvenv\Scripts\python.exe" docs\research\fno\2026-10-28-forward-panel-c\panel_c.py run --jobs 3
```

## Limits

- One month is about 20 sessions: enough to reject an arm, not to qualify it.
- Research settings are Dev's defaults, as in panels A and B.
- The real-money test is a one-lot mirror of the paper book and is not part of this panel.
