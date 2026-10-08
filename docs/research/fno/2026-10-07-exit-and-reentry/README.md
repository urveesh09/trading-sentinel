# F&O single-leg: profit lock and re-entry confirmation (October 7, 2026)

Development evidence only. Every session here was already seen; nothing is
an untouched holdout. Forward paper sessions from October 8 decide.

## Question

The owner asked whether the system can keep small profits instead of letting a
trade that went green turn into a loss, without blindly pausing a direction
after one loss.

## Data

- Read-only export of the Production research archive
  (`scripts/export_fno_replay_dataset.py`, sealed days Sep 10 – Oct 6), plus a
  read-only copy of the October 7 open journal. They are kept out of git under
  `../2026-10-07-archive/_local/` and `_local/with-oct7/`.
- 18 NIFTY sessions; the replay reproduces the live paper book: 8 of the 11
  live trades match by bar and contract, October 7's two puts match by bar
  but chose the 22600 strike instead of 22650/22700, and Sep 21 entered one
  bar later (`parity` in `grid1-lock-sweep.json`). Sep 10 has one extra
  replay trade.

## How far each trade went into profit (`excursion.jsonl`, `mfe.py`)

Best sellable bid between entry and exit, net of costs:

| Trade | Result | Best point on the way |
| --- | --- | --- |
| Sep 17 (30) | −₹404 time stop | +₹1,561 |
| Sep 21 (31) | −₹764 time stop | +₹708 |
| Sep 23 (32) | −₹102 time stop | +₹1,160 |
| Sep 28 (33, 34) | +₹174 / +₹141 | +₹1,076 / +₹900 |
| Sep 30 (36) | −₹2,056 stop | never green (−₹81) |
| **Oct 7 (39)** | **−₹2,079 stop** | **never green (−₹211)** |
| **Oct 7 (40)** | **−₹3,228 stop** | **+₹210 for ~12 seconds** |

So both October 7 losses could not have been saved by any exit rule; they
were entry problems. The earlier trades did give back real gains.

## Replay results (`grid.py`, shipped rules via `fno_policy_replay`)

> **Superseded Oct 8.** These runs used the inverted bought-put time-stop
> sign (audit O8-F2). With the sign fixed and the time-stop deferral off,
> the shipped lock + re-entry replays at +₹6,968 (max DD ₹1,991, PF 2.26);
> see `../2026-10-08-time-stop-sign/README.md`.

| Arm | Trades | Net | Net excl. best | Max DD | PF |
| --- | --- | --- | --- | --- | --- |
| Baseline (lock off, re-entry off) | 12 | ₹5,323 | −₹1,784 | ₹3,831 | 1.79 |
| Lock armed at 0.2–0.25 R (any floor) | 10–12 | ₹546–3,674 | worse | ₹3,831 | ≤1.59 |
| Lock armed at 0.3 R | 12–13 | ₹4,785–5,714 | | ₹3,831 | |
| Lock armed at 0.4–0.5 R, keep half the gain | 13 | ₹6,041 | −₹1,066 | ₹3,831 | 1.91 |
| Faster management, no lock | 12 | ₹5,054 | −₹2,054 | ₹3,831 | 1.75 |
| Faster management + early lock | 12 | ₹3,252 | | | 1.50 |
| Re-entry confirmation (margin 0.25 R) | 11 | ₹7,693 | +₹586 | ₹1,991 | 2.75 |
| **Shipped: lock 0.4 R keep half + re-entry** | **12** | **₹8,411** | **+₹1,303** | **₹1,991** | **2.97** |

Why the early lock fails: between 60–90 s samples the option bid often
drops straight through a thin floor, so the "locked" exit lands at or below
entry after fees, and it also cut the Sep 28 trail winner. Faster checking did
not help on this data.

The `REENTRY_ONLY` row in `grid1-lock-sweep.log` predates the gate and equals
the baseline; `grid3-reentry-margin.json` is the valid run. A margin of 0 let
October 7's second put through (replay entry 0.9 points past the first).

## Re-entry cases in the whole paper history

| Day | Stopped entry | Re-entry | Past by ≥0.25 R? | Outcome |
| --- | --- | --- | --- | --- |
| Jul 27 LONG | 23,977.1 (R 17.6) | 23,989.0 | yes (+11.9) | +₹1,555, kept |
| Aug 19 SHORT | 24,105.0 (R 24.1) | 24,114.9 | no | −₹123, blocked |
| Sep 30 SHORT | 22,793.0 (R 41.1) | 22,772.0 | yes (21.0) | +₹1,622, kept |
| Oct 7 SHORT | 22,611.1 (R 43.8) | 22,619.2 | no | −₹3,228, blocked |

The margin was chosen after seeing these four cases; treat it as a paper
hypothesis, not a measured edge.
