# SN01: ₹15,000 fixed wallet, 10% day target, 20% day loss (Nov 12, 2026)

**Verdict: NOT PROVEN.** The rule frozen in `PLAN.md` (commit `ca045b3c`) failed on both counts:
- the search does not generalise to a year it did not see;
- the final pick is not robust to costs.

This is research only, in Dev. Nothing changed at runtime, nothing was written to Production, no order was placed, and no real money was involved.

## The question

The owner asked for SN01, which runs beside the N11/N012 paper main book:
- The ₹15,000 wallet stays fixed. Profit is banked, and a losing day is refilled.
- The day target is 10% after charges (₹1,500), and then F&O stops for the day. The day loss limit is 20% of the wallet (₹3,000).
- Quick entries and exits, on every kind of day.
- After 100% of the wallet in profit, the wallet grows by 50%. The target grows by 50% once every 2 or 3 steps.
- The owner's improvement idea: past 10%, lock 10% with a stop and let the trade run.

Readings I chose are listed in `PLAN.md`; the main one is that wallet steps count net profit, because refills are the owner's money.

## What was tested

- **Data:** NIFTY weekly options in 1-minute candles: 2023, 2024, 2025 and Jan–Oct 28, 2026. That is 742 non-expiry sessions, all already seen. Real charges, bid/ask fills, and the stop taken first on any tie.
- **Search size:** 21,066 rule sets.
  - The entry styles: ORB, MOMO, TPB, VWAPX, EMAX, FADE and PDX, alone or in pairs.
  - Each with these settings: strike, lots, stop, target, time stop, trail, trades per day (1–20), entry window, direction bias and lock.
- **The honest checks:**
  - choose on three years and score on the fourth, for each year in turn;
  - the same search on random entries (NULL);
  - extra costs of +₹0, +₹100 and +₹200 per lot per trade.

## Results

### 1. Leave one year out, at the realistic cost (+₹100 per lot per trade): the search does not carry over

| Held-out year | SN01 pick | Random-entry pick |
|---|---:|---:|
| 2023 | −28,657 | −82,250 |
| 2024 | −31,974 | −38,153 |
| 2025 | −22,070 | −14,601 |
| 2026 | −39,445 | −111 |
| **Sum** | **−1,22,146** | **−1,35,115** |

- None of the 4 years was positive. The rule needed at least 3.
- Even with no extra cost (+₹0), only 2025 was positive: the sum was −₹22,147, against random's −₹43,700.
- The search beats random only slightly.

### 2. Every entry style costs about the same as random entries

Per trade, in the random pool, at +₹100:

| Entry | Median per trade |
|---|---:|
| ORB | −₹210 |
| MOMO | −₹194 |
| TPB | −₹212 |
| VWAPX | −₹210 |
| EMAX | −₹216 |
| FADE | −₹219 |
| PDX | −₹212 |
| Random | −₹218 |

Each trade pays about ₹60–65 in charges plus ₹20–30 in spread on one lot before any slippage, and the entries don't predict direction well enough to cover it.

**More trades, more loss.** Median four-year totals at +₹100:

| Trades a day | Median four-year total |
|---|---:|
| Under 0.5 | −38,510 |
| 0.5–1 | −1.24 lakh |
| 1–2 | −2.49 lakh |
| 2–4 | −4.63 lakh |
| 4–8 | −8.68 lakh |

Quick entry and exit is the costliest way to chase ₹1,500.

### 3. The final pick (chosen on all four years, so a description, not a test)

**The pick:**
- Entries: opening-range break (15 minutes, 0.5 ATR) or a 5-minute burst on the right side of VWAP, only in the direction of the daily trend.
- One lot ATM, one trade a day.
- Exits: stop −8%, target +20%, a trail, and the lock at 0.5.

It turned into a one-trade-a-day book: the search dropped "active".

| Extra cost | 2023 | 2024 | 2025 | 2026 | Four years | Target days |
|---|---:|---:|---:|---:|---:|---:|
| +₹0 | +9,352 | +9,149 | +11,401 | +14,601 | +44,503 | 69 of 742 |
| +₹100 | −6,847 | −3,573 | −6,247 | +2,864 | −13,803 | 54 |
| +₹200 | −23,675 | −21,799 | −22,058 | −10,157 | −77,688 | 40 |

### 4. The owner's wallet, Jan 2023 → Oct 2026, final pick

| Extra cost | Target rule | Total profit | Wallet steps | Days won / lost / no trade | Refilled by the owner |
|---|---|---:|---:|---|---:|
| +₹0 | every 2 | +34,726 | 2 (Jul 26 2024 → ₹22,500; Feb 2 2026 → ₹33,750, target ₹2,250) | 281 / 327 / 134 | 2,16,966 |
| +₹0 | every 3 | **+43,222** | 2 (target stays ₹1,500) | 281 / 327 / 134 | 2,16,966 |
| +₹0 | 10% of wallet | +29,168 | 1 | | |
| +₹100 | any | −13,803 | 0 | 274 / 324 / 144 | 2,42,985 |
| +₹200 | any | −77,688 | 0 | 273 / 325 / 144 | 2,75,441 |

- **Day ends:**
  - the 20% loss limit was never hit (worst day −₹1,690), because the stop is small;
  - the target was hit on 56 days.
- **every 3 against every 2:** every 3 earned more, because the step on Feb 2, 2026 lifted every 2's target to ₹2,250, which was reached less often. At realistic costs the wallet never grew, so the choice didn't matter.
- **Gross counting** (winning days only) grew the wallet 5 times, to ₹1,13,906, while the four-year profit was only +₹16,650. The wallet grows on paper when the money isn't there. Count net.

### 5. Why 10% a day is not easy (from `explain.json`)

- **Hindsight:** on 92–96% of days, one ATM lot did reach +₹1,500 after charges at some point after 09:30. The owner is right that the move is there almost every day.
- **Luck:** buy a random side at 09:30 and hold for +₹1,500, −₹3,000 or 15:15.
  - The target came first on 54% of days.
  - The total was still −₹1,79,368 over 741 days, before any extra cost.
  - Each losing day costs twice a winning day, and time decay drags on every hold.
- A high share of target days is what a coin gives. Only the rupee total shows skill.

### 6. The owner's lock idea is the one change that helped

On the final pick, the wallet rules with target every 2:

| | +₹0 | +₹100 |
|---|---:|---:|
| Sell at the target (no lock) | +28,041 | −32,533 |
| Lock, trailing 0.5 × target | +34,726 | −13,803 |
| Lock 0.25 | +35,268 | −18,672 |
| Lock 1.0 | +34,015 | −15,566 |

All four held-out picks chose a lock as well. That is in-sample; it is a lead, not proof.

## What this means

- SN01 as specified is not a strategy to put money on. The search found no entry that beats costs on years it did not choose on.
- **What the data says works better than many quick trades:**
  - fewer trades;
  - the lock;
  - trading with the daily trend.
  - Even that is about break-even at realistic costs.
- **The forward check was not run.** It could not change a failed verdict, and Oct 29 – Nov 12 stays unseen for the next SN01 attempt.
- **If the owner still wants SN01:**
  - the only honest next step is the final pick as a zero-cost paper shadow, scored forward for at least 20 sessions;
  - real money only on the owner's word, by its own runbook.

## Files

- **The study:**
  - `PLAN.md`, `freeze.json` (the freeze);
  - `sn01_data.py` (sealed caches);
  - `sn01_sim.py` (simulator);
  - `sn01_search.py` (pool and genetic search);
  - `sn01_ledger.py` (wallet rules);
  - `sn01_analyze.py` (the frozen rule) → `results.json`;
  - `sn01_explain.py` (after the verdict, descriptive) → `explain.json`;
  - `test_sn01.py` (15 tests).
- **Not committed:** `_local/evals.jsonl` (21,066 evaluations) and the year caches.
- **Reproduce** from this folder, with `python` = `python-engine\winvenv\Scripts\python.exe`:
  1. `python sn01_data.py`
  2. `python sn01_search.py pool`
  3. `python sn01_search.py ga`
  4. `python sn01_analyze.py` (once)
  5. `python sn01_explain.py`
