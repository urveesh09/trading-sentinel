# N012-A2: can the N012-A trend lock be made better on the data we have? (Nov 8, 2026)

## Question

The owner (Nov 8): take the best strategy the N012 research found and make it better on the data and simulations we have, then deploy it. The best priced candidate is N012-A: N11T with the Round 30 trend-aware profit lock (`2026-11-05-fno-expiry-followup/regular_rules.py`). It added ₹4,051.45 over N11T on five seen ₹2,50,000 NIFTY windows (Jun–Dec 2022, 2023, 2024, 2025, Jan–Oct 2026), ₹710.38 without its five best incremental days, with the same worst day (−₹5,640.85).

## What N012-A changes, read from the code

The rule reads three completed 5-minute buckets of the front future plus the current price. SUPPORT (two moves with the trade) sets the lock's keep fraction to 0.35. ADVERSE (two moves against) sets the arm to min(0.60, arm) and keep to 0.65. ADVERSE while a trail is active and the lock is off switches the lock on at 1.0 R with keep 0.60. N11T's native lock arms at 0.40 R with keep 0.50, so **the 0.60 arm cap never binds**. Only three numbers can change a trade: S (keep on SUPPORT), A (keep on ADVERSE) and T (keep of the trail-time lock).

## Arms (frozen in `freeze.json` before any arm is scored)

27 arms: S ∈ {0.25, 0.35, 0.45} × A ∈ {0.55, 0.65, 0.75} × T ∈ {OFF, 0.60, 0.75}. The centre (0.35, 0.65, 0.60) is N012-A and must reproduce Round 30's `TREND_ONLY` net, counts, drawdown, worst day and daily nets exactly in every window. Everything else is the Round 30 lab unchanged: N11T entries, sizing, stops, costs (₹200 + ₹5 a lot), one-minute candle model.

## How a better arm is chosen, and when it replaces N012-A

All five windows are seen, so a plain best-of-27 would be tuned on seen data. The search itself is tested:

- **Leave one window out.** For each window, pick the arm with the highest increment over N11T on the other four. An arm qualifies only with no unresolved positions and no worst day more than ₹500 worse than N11T's in those windows. Ties go to the arm nearest the centre. Then score that pick on the held-out window. The sum of the five held-out increments is the search's honest estimate.
- **Final pick.** The same rule on all five windows.

The final pick replaces N012-A only if all five hold:

1. The search's held-out sum beats N012-A's ₹4,051.45. N012-A's own figure is in-sample, so this check favours keeping N012-A.
2. The pick's increment without its five best incremental days beats N012-A's ₹710.38.
3. The pick's worst day and its largest annual closed drawdown are no worse than N012-A's.
4. No window loses more than ₹2,500 against N11T.
5. The pick's grid neighbours (one step in one number) have a positive mean increment, so the pick is not a lone spike.

If any check fails, N012-A stays the candidate unchanged.

## What cannot be tested here

- **The new SENSEX history (Oct 2024–Jun 2025, 2026 remainder).** It is all unseen, but the book cannot be replayed on it natively. A read-only count on Nov 8 found every SENSEX futures and option minute from Sep 2024 to Jul 2025 with zero or missing open interest, so N11T's minimum-OI gate refuses every SENSEX entry, as Round 10 found for 2025–26. Only about a quarter of SENSEX futures minutes carry volume. A SENSEX-only route would need a separate OI and volume rule. That is the kind of infrastructure build the N012 closeout warned against, so it is recorded as an open item, not built.
- **The sealed NIFTY January–May 2022 exam** (`2026-11-05-fno-n12/EXAM_2022_H1.md`). It stays sealed. Q1 2022 is not downloaded, and the sheet allows April–May alone only if Q1 is declared unavailable first. That is the owner's call.

So the only fresh evidence will be forward paper.

## Rollout and rollback

Research is Dev only. The runtime change is a separate switch, `FNO_TREND_LOCK_ENABLED`, carrying the chosen numbers. It must match this study's rule on a shared test. Rollback is the switch off.

## Run

`N12_YEAR=<window> N12A2_BUDGET_SEC=480 python n012a2.py` is resumable in slices of 9 minutes or less. Then `python score.py` writes `results.json`.
