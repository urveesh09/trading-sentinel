# J — CAS and market-session correctness: deep research

## Scope per plan §14

Inventory hard-coded clocks in market calendars, gateway market-hours,
scheduler jobs, bars, expiry/square-off, UI and replay. Introduce an
exchange/security/session-phase model only after verifying effective
dates and broker behavior. Preserve earlier strategy deadlines unless
explicitly revised and qualified.

Acceptance: ordinary days, eligibility differences, holidays, shortened/
special sessions and phase transitions have tests. No accidental extension
of partner holding horizon.

## Verified facts (primary sources, 2026-09-13)

### NSE Closing Auction Session (CAS) — Phase 1

Source: <https://www.nseindia.com/static/products-services/closing-auction-session>
(checked 2026-09-13). Cross-referenced with circulars NSE/CMTR/73362
(2026-03-18 SOP) and NSE/CMTR/76170 (2026-09-03 update effective 2026-09-07).

- **Applicability (Phase 1)**: only stocks in the cash segment on which
  derivative contracts are available. NOT all equities.
- **Session timing (separate session, 20 minutes)**:
  - 15:15–15:20 IST: Reference price calculation / transition from CTS to CAS
  - 15:20–15:25 IST: Order entry period (limit + market orders)
  - 15:25–15:30 IST: Order entry/cancellation for limit orders only;
    market orders blocked; system-driven random closure in last 2 min
  - 15:30–15:35 IST: Order matching and trade confirmation
  - 15:35–15:50 IST: Transition period (CAS to post-close session)
  - 15:50–16:00 IST: Post-close session (unchanged from current modalities)
- **Reference price**: VWAP of trades executed in the stock during
  15:00–15:15 IST.
- **Price band**: ±3% from reference.
- **Order types**: limit + market only.
- **Prohibited in CAS**: stop-loss, iceberg.
- **Market Price Protection (MPP)**: not applicable.
- **Self-Trade Prevention (STP)**: yes, as in pre-open.

### Equity derivatives session

Continuous trading 09:15–15:40 IST.

### Non-CAS cash continuous trading

Continuous trading 09:15–15:30 IST.

### BSE CAS — equity derivatives

Source: BSE Notice 20260801-2 (2026-08-01), partial modification of
Notice 20260430-19. Effective 2026-08-03.

- Continuous trading 09:15–15:40 IST.
- 15:15–15:40: Futures price band aligned with CAS cash price band (±3%).
- Trade modification window until 16:15 IST.

### Effective dates

- NSE Phase 1 CAS: introduced 2026-01-19 (circular NSE/CMTR/72394); SOP
  2026-03-18 (NSE/CMTR/73362); trading modalities 2026-05-29 (NSE/CMTR/74466).
- NSE index futures CAS reference price: 2026-09-07 (NSE/CMTR/76170).
- BSE CAS derivatives: 2026-08-03.

## Current state — hard-coded clocks inventoried

### Container A (python-engine)

| File | Line | Code | What it controls |
|---|---|---|---|
| `market_calendar.py` | 80–95 | `is_market_open()` | 09:15–15:30 IST only. **No CAS.** |
| `market_calendar.py` | 109–139 | `is_trading_day()` | Holiday + weekend only. **No session-phase.** |
| `market_calendar.py` | 141–145 | `next_trading_day()` | Holiday-aware date arithmetic. |
| `market_calendar.py` | 183–203 | `is_trading_day_sync()` | Sync version, same semantics. |
| `config.py` | 367–381 | `MOMENTUM_USE_TIME_GATE`, `MOMENTUM_ENTRY_START_MIN`, etc. | "Skip 9:15–9:30 + 15:00–15:30" — pre-CAS window. **Conflicts with CAS eligibility.** |
| `config.py` | 621–624 | `PENNY_DAILY_ATTRIBUTION_TIME = 15*60 + 30` | 15:30 IST daily P&L. After CTS, before CAS ends. |
| `fno_chain.py` | 39–40 | `EXPIRY_CUTOFF_HOUR, EXPIRY_CUTOFF_MIN = 15, 30` | Already a constant. **Could be wrong for derivatives** (15:40). |
| `fno_engine_mom.py` | 45 | `SESSION_OPEN_MIN = 9 * 60 + 15` | 09:15 IST constant. |
| `fno_orchestrator.py` | 110, 327 | Hardcoded 09:15:00, mentions 15:30 | Bar open + broker safety net. |
| `fno_signal_scan.py` | 116 | Hardcoded 09:15:00 | Bar open. |
| `hedge_strategies.py` | 43, 316 | `_EXPIRY_CUTOFF = time(15, 30)` | **Should be 15:40 for derivatives.** |
| `daily_bootstrap.py` | 24, 286, 293 | "08:00–15:30" gate, 09:15 pre-open nudge | Scheduler window. |
| `scheduler_setup.py` | 125, 365, 557, 621–683, 728, 747, 839, 958 | "15:15 IST daily", 15:15 EOD exit, 15:30 attribution, 09:20–15:30 partner tick | Multiple scheduler cron-like entries. |
| `chandelier_stop.py` | 23 | "auto-square-off at 15:15" | Documented constant. |
| `proactive_intelligence.py` | 745–762 | `stamp_session_phase()` | **J seam — currently `_SESSION_PHASE_UNKNOWN`.** |
| `proactive_intelligence.py` | 817, 2268 | `stamp_session_phase(observation_at=None)` called from `_ensure_shadow_run` and `run_shadow_research_comparison` | Manifest key. |
| `signal_log.py` | 34 | "minutes_from_open INTEGER ... minutes from 9:15 IST" | Schema column. |

### Container B (node-gateway)

| File | Line | Code | What it controls |
|---|---|---|---|
| `utils/market-hours.js` | 41–108 | `isMarketOpen()`, `isPreMarket()` | 09:00 pre-market, 09:15–15:30 main. **No CAS.** |
| `utils/market-hours.js` | 7–25 | `NSE_HOLIDAYS` set | 18 dates; **conflicts with python-engine's static list on Sept 5 vs Sept 14.** |
| `services/executor.js` | 291 | "fill until the 15:15" comment | Order-management comment. |
| `routes/orders.js` | 71 | "Called by Container B at 15:15 IST" | Square-off comment. |
| `tests/unit/market-hours.test.js` | 28–125 | Mocked-time tests | Already covers pre-market + main session only. **No CAS test.** |

### Container C (agent)

No CAS or session-phase handling — agent does not enforce trading windows
(it annotates only).

## Inconsistencies / gaps surfaced

1. **No CAS awareness anywhere.** Both `market_calendar.py` and
   `market-hours.js` treat the trading day as a single block
   09:15–15:30. CAS securities (cash stocks with derivative contracts)
   trade 15:15–15:35 in a separate session. A penny/HFT strategy
   trading a CAS-eligible stock today would mis-classify the
   15:15–15:35 window as after-hours.

2. **`EXPIRY_CUTOFF` semantics mismatch.** `fno_chain.py:40` and
   `hedge_strategies.py:43` both use `15:30` as the expiry cutoff.
   But equity derivatives close at 15:40 (per NSE), not 15:30.
   A weekly options strategy that assumes options can be
   settled up to 15:30 is missing the last 10 minutes of the
   derivatives session. **Silent bug.**

3. **Holidays lists disagree.** `market_calendar.py` has 20 dates
   including `2026-09-14` (today). `market-hours.js` has 18 dates
   including `2026-09-05` but NOT `2026-09-14`. Two separate truth
   sources for the same calendar.

4. **`stamp_session_phase` is a placeholder.** Returns
   `_SESSION_PHASE_UNKNOWN` for every input. The docstring
   explicitly says: "the single place J will replace when the
   official NSE/BSE/SEBI session inventory lands." This is the
   forward-compat seam.

5. **`MOMENTUM_USE_TIME_GATE`** explicitly excludes "15:00–15:30"
   for entries. If the operator's policy is to trade CAS-eligible
   stocks, they cannot enter during the pre-CAS reference-price
   window (15:00–15:15). This is correct per CAS design, but the
   constant's name and intent pre-date CAS. **No mention of CAS in
   the comment.**

6. **`fno_engine_mom.py` opening range uses 09:15 + FNO_OR_MINUTES.**
   For CAS-eligible underlyings the continuous-trading close is
   still 15:30 in cash and 15:40 in derivatives — but if a strategy
   keys off the **cash** 15:30 close and tries to settle positions
   after that, it sits in a window where CAS is already running.
   The P&L attribution at 15:30 (`PENNY_DAILY_ATTRIBUTION_TIME`) is
   during the CAS reference-price calculation window — `attribution`
   is observation, not trade execution, so this is acceptable.

## What the plan §14 actually asks for (re-read)

1. **Inventory hard-coded clocks** — DONE ABOVE.
2. **Verify effective dates and broker behavior** — DONE ABOVE for
   NSE; BSE confirmed.
3. **Introduce exchange/security/session-phase model only after
   verifying** — i.e. AFTER the inventory. The model is the J-side
   deliverable, NOT the inventory.
4. **Preserve earlier strategy deadlines unless explicitly revised
   and qualified** — i.e. don't change the 15:15 auto-square-off
   without operator sign-off; don't extend the partner's holding
   horizon.
5. **Do not assume auction imbalance is available in Kite's current
   feed** — i.e. don't write a CAS-eligible strategy yet. Inventory
   only.
6. **Acceptance**: ordinary days, eligibility differences, holidays,
   shortened/special sessions and phase transitions have tests.

## Proposed J scope (smallest correct slice)

Per the user's directive ("senior dev with precision and correctness in
code ensure that system becomes better"), the smallest correct slice
is the **inventory + classifier + tests** — NOT the strategy change.

The plan is unambiguous: "introduce ... only after verifying effective
dates and broker behavior." We have verified dates. We have NOT verified
broker behavior (we don't have a live broker). So:

### Slice J.1 — Session classifier + central session constants (NOW)

1. **Central session constants** in `market_calendar.py` — replace the
   hard-coded `time(9, 15)` and `time(15, 30)` with named constants
   that document the source (NSE CAS page, NSE circulars).
2. **CAS-aware `is_market_open()`** — distinguish:
   - `CLOSED`
   - `PRE_MARKET` (09:00–09:15 IST)
   - `CONTINUOUS_TRADING` (09:15–15:30 IST)
   - `CAS_REFERENCE_PRICE_WINDOW` (15:15–15:20 IST, only for CAS securities)
   - `CAS_ORDER_ENTRY` (15:20–15:25 IST, all orders)
   - `CAS_LIMIT_ENTRY_ONLY` (15:25–15:30 IST)
   - `CAS_MATCHING` (15:30–15:35 IST)
   - `CAS_POST` (15:35–16:00 IST)
   - `DERIVATIVES_CLOSE` (15:30–15:40 IST, only for derivatives)
3. **`is_cas_eligible(symbol: str) -> bool`** — Phase 1 is "stocks in
   cash segment on which derivative contracts are available." We do
   NOT have the F&O stock list locally. **The honest answer is to
   return False with a documented reason.** Operators must populate
   a static list when they know.
4. **Wire `stamp_session_phase`** to the classifier. The G seam
   becomes real (still returns `UNKNOWN` for instruments without
   the F&O eligibility list).
5. **Reconcile the holiday lists** between Python and Node — pick
   one authoritative set (the python-engine set, since it has the
   `+5:30` static fetch fallback).
6. **Tests for ordinary days, holidays, special sessions, CAS
   windows, derivatives close.**

### Slice J.2 — Broker-behaviour verification (LATER, not in this slice)

After a real Kite feed is exercised at 15:15 on a CAS-eligible
stock, verify whether `get_intraday("day")` returns the pre-CAS
close or the post-CAS close. This is NOT something we can do in
Dev without a broker.

## Out of scope (deferred)

- Any new trading strategy that uses CAS.
- Any modification to the 15:15 auto-square-off behavior.
- Any modification to the partner's holding horizon.
- BSE-specific session details (BSE has CAS too but plan §14 is NSE-
  focused; cross-exchange parity is a separate slice).
- Auction-imbalance research (explicitly excluded by plan §14).

## Risks

1. **Holiday list reconciliation could affect OPERATIONS** if the
   active day is misclassified. Mitigation: keep both lists as
   source-of-truth, surface divergence in a drift report, let
   operators decide.
2. **CAS eligibility list is empty in Dev.** `is_cas_eligible` will
   return False for everything; the classifier still labels CAS
   windows correctly (CAS_REFERENCE_PRICE_WINDOW etc.) but eligibility
   is explicit `False`. Operators can populate.
3. **`EXPIRY_CUTOFF` semantics change.** Moving from 15:30 → 15:40
   for derivatives is a **real schedule change**. Per plan §14 it
   must NOT be done without operator sign-off. **Therefore J.1
   introduces a NEW constant `DERIVATIVES_CLOSE_TIME = 15:40` and
   leaves the existing `EXPIRY_CUTOFF_HOUR/_MIN = 15:30` alone** —
   we surface the gap in tests, not change behavior.

## Conclusion

The senior-dev right move for J.1 is: build a session classifier that
returns the correct phase for any UTC/IST timestamp, with documented
constants, without changing any production behavior. The classifier
becomes the single source of truth that `stamp_session_phase` and any
future strategy uses. Tests cover ordinary days, holidays, CAS
windows, and derivatives close. Existing behavior preserved exactly.
