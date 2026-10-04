# Smarter Momentum and Penny, Momentum direct trading (Dev)

Owner direction (October 4, 2026): improve the intraday modules first. Make
Momentum smarter about entries and exits and let it trade directly without a
Telegram approval, then do Penny, then test with the same pre-registered
method. F&O gets nothing further except SENSEX/NIFTY candle recording
(`72ff8d0`).

## Problem (Production evidence, read-only)

| Book | Record | What stands out |
| --- | --- | --- |
| Momentum paper (₹50k, automatic) | 47 trades, −₹2,353, 34% winners, PF 0.65 | 43 of 47 ended on the time stop; median move at exit −0.2% |
| Momentum live (manual EXEC, ₹2.5k) | 22 trades, −₹148 | No trades since Aug 4: alerts were not acted on |
| Penny paper (MIS) | 27 trades, −₹45 (≈₹200 per trade) | Stops 0.07–2% under entry (one-minute bar low); 16 of 27 ended on the clock |

Data defect noted: three `PENNY_PAPER` rows store `exit_price` as an 8-byte
blob (SAKHTISUG ×2, RAJSREESUG, Aug 31). Not fixed in this slice.

## Development evidence (seen windows only)

Momentum, Yahoo 15-minute bars, 499 stocks, Aug 10–Oct 1, 2026 (38 sessions,
NIFTY −8.8%):

- **All-stock first-range breakouts** (13,010 events, held to 15:15 with the
  range stop, ~12 bps costs) lost after costs on both sides. Longs averaged
  −0.16%. No bucket was positive, whether split by first-bar RVOL, gap, range
  width, ATR%, distance from the 20-day high, 5-day return, market direction,
  relative strength or entry time. The first bar's market direction did not
  predict the rest of the day (correlation −0.08).
- **The textbook "stocks in play" opening-range breakout** (Zarattini & Aziz):
  137 trades, −0.53% mean, 7 of 24 days positive.
- **Shipped Momentum at the ₹50,000 paper size:** 70 trades, −₹3,110, 31% winners.
- **`MOM_SELECTIVE`:** 0 trades. All 9 shipped signals in a 5-day sample failed a
  context check (market not up 2, relative strength 4, under yesterday's high 3).
  It sat out the falling market, so it avoided the loss but earned nothing.
- **`MOM_BASE_RUNNER`** (shipped entry + runner exit): 70 trades, **−₹3,854**,
  worse than the shipped exits (55 of 70 held to the square-off in a falling
  market). Selective refusals over the whole window: market not up 46,
  relative strength 12, under yesterday's high 15.

Decision from development: the study's decision candidate is **`MOM_SELECTIVE`**
(entry change, shipped exits). `MOM_SELECTIVE_RUNNER` is an attribution arm only.

Penny, Yahoo 1-minute bars, 95 tickers:

| Policy | Sep 24–30 (dev): trades / net / net excl. best / max DD |
| --- | --- |
| BASELINE (reproduces the archived +₹15.1765 / 18) | 18 / +₹15.18 / −₹27.74 / ₹45.10 |
| PEN_NOISE_STOP | 16 / +₹35.78 / −₹7.13 / ₹32.40 |
| PEN_NOISE_STOP_BE | 17 / −₹3.25 / −₹26.08 / ₹32.77 |

All seen Penny days (Sep 7–Oct 1): BASELINE 42 / +₹78.35 / +₹35.43 / ₹45.10;
PEN_NOISE_STOP 39 / +₹93.19 / +₹50.27 / ₹32.40; PEN_NOISE_STOP_BE 44 / −₹13.26 /
−₹40.76 / ₹63.29. Decision candidate: `PEN_NOISE_STOP`.

## Design

1. **`momentum_selective.py`** (pure, shared by research and a later runtime
   port). It takes a shipped Momentum signal only when all three hold:
   - NIFTY 50 is above its session open;
   - the stock's session return leads NIFTY's by at least 0.3%;
   - the close is above yesterday's high.

   A missing index bar fails closed.
2. **`momentum_replay`:** variant `MOM_SELECTIVE` (reads the `NIFTY 50` bars in
   the same snapshot), and exit model `RUNNER_EXIT`:
   - no target and no clock stop;
   - the stop moves to entry after a +1R close, then trails under completed bar lows;
   - square-off at 15:15.

   The Lab adapter accepts both, plus `index_ticker`.
3. **Penny (`penny_lifecycle_replay`):**
   - `PEN_NOISE_STOP` keeps the shipped entry and lifecycle, but puts the stop at
     least 1.5% and at least ₹0.03 under entry, at the same rupee risk (fewer shares);
   - `PEN_NOISE_STOP_BE` adds a break-even move after a +1R close.
4. **Untouched data:** Kite history for January–July 2026, never used by any study.
   It comes from `scripts/acquire_kite_history.py`, which uses the standard library
   only, reads market data only and writes the standard snapshot format.
   Studies `momentum-smart-t3` (candidate `MOM_SELECTIVE`, ₹50k paper book)
   and `penny-noise-t3` (candidate `PEN_NOISE_STOP`) are registered;
   `run_preregistered_study.py run --jobs N` scores independent arms in parallel.
5. **Momentum direct trading** (`MOMENTUM_AUTO_EXECUTE`, gateway env, default
   `false`):
   - `services/momentum-execution.js` is now the single Momentum execution path.
     It holds the once-per-ticker-per-day lock, uses the approved snapshot, calls
     the executor and persists the armed fill, for both the Telegram EM button and
     the new `POST /api/internal/momentum-auto-execute`.
   - The automatic route executes only a registered snapshot and never re-fetches
     engine data.
   - The agent calls the route after registering the snapshot. Its alert then says
     AUTO-EXECUTED without buttons, explains a refusal while keeping the button,
     or says "Do NOT retry" for a held or unknown outcome. The gateway also pages
     on its own for those.
   - Fixed in passing: an EM `outcomeUnknown` failure used to reset the signal to
     PENDING (retryable). It now stays locked, as the EXEC and web paths already did.

## Acceptance

- Unit tests: selective gate, runner exit, Penny noise floor and break-even,
  the gateway auto route (off by default, snapshot-only, once per day, session
  block, held stays locked and pages, auth/validation) and the agent alert
  wording.
- The Penny baseline reproduces its archive exactly. The Momentum baseline
  replay is unchanged.
- A study verdict counts only from the untouched Kite window, scored once
  after the freeze is committed.

## Rollout / rollback

- Research code is offline. The runtime Momentum and Penny strategies are
  unchanged until a candidate passes; only then is it ported (paper first).
- Direct trading ships OFF. Turning it on is the owner's call: set
  `MOMENTUM_AUTO_EXECUTE=true` in the gateway environment and restart. The
  executor's checks still apply: owner halt, CAS, ₹1,500 risk cap, drift,
  own cash, protective stop.
- Rollback: unset the variable.
