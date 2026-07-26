# Trading Sentinel — Thursday 2026-07-23 & Friday 2026-07-24 Production Audit

**Audited:** Sunday 2026-07-26
**Host:** prod stack at `~/Desktop/trading-sentinel`
**Prod HEAD:** `708f669` (Merge PR #70, `evolve/smart-strategies`)
**Sources:** container json-file logs (retained back to 2026-07-21), `/data/cache.db`,
`/data/signals.db`, `penny_signals.csv`, `momentum_signals.csv`, `fno_signals.csv`

---

## TL;DR

Infrastructure was **clean on both days** — no crashes, no mid-session restarts,
schedulers on cadence. The trading result was not.

The two days are dominated by **one defect with three compounding consequences**:
two momentum positions that were fully closed on **2026-07-20** are still
classified as open. Every trading day since, the system has

1. placed **real Zerodha sell orders** for shares it does not hold,
2. booked a **fabricated loss** into the bankroll ledger, and
3. kept **93–95% of the momentum capital pool locked**, so real setups could not be taken.

On Thursday **18 momentum candidates passed every strategy gate** and were rejected
for lack of cash. On Friday, **8**. Zero were taken. That is the headline: this was
not a signal drought — it was a capital-starvation event caused by a stale DB row.

Separately, the F&O defined-risk book has **never once opened a structure** since
PR #70 — it throws on every tick (297×/day) — while the legacy F&O paper book
traded freely and lost **₹5,718 on Friday**.

---

## 1. Availability

| | Thursday 07-23 | Friday 07-24 |
|---|---|---|
| Container start | 06:34 IST | 06:49 IST |
| Mid-session restarts | none | none |
| Shutdown | 22:26 IST (post-close) | — |
| Engine startups in log | 1 | 1 |
| Tracebacks | 299 | 297 |
| `[ERROR]` lines | 2 | 0 |

Both days the stack came up ~06:35–06:50 IST from a host boot, found a **stale Kite
token** (previous day's), and waited for the operator.

| | Thursday | Friday |
|---|---|---|
| Token injected | **07:05 IST** | **08:17 IST** |
| 08:00 bootstrap | ran on time (token already fresh) | **deferred** — `no_fresh_token_at_0800`, operator alerted |
| Penny universe ready | 08:01 IST | **09:12 IST** |
| F&O instruments ready | 08:01 IST | 09:12 IST |

Friday's bootstrap finished **3 minutes before the 09:15 open**. The penny-universe
fetch takes ~55 min, so an 08:17 login is the practical cut-off. Any later and the
first session hour runs on a stale universe. Thursday's 07:05 login was comfortable.

**Verdict:** infra healthy; the daily login window is uncomfortably tight and
depends entirely on the operator being awake. This is the same finding as the
2026-07-21 audit's action item #1, still unactioned.

---

## 2. The phantom-position defect (root cause of the two days)

### What is wrong

`THELEELA` (4 sh @ ₹490.90) and `LATENTVIEW` (1 sh @ ₹305.85) were entered and
fully exited on **2026-07-20**. Both rows sit in `positions` with
`status='CLOSED_T1'`, `t1_fired=0`, `exit_date='2026-07-20'`.

`position_tracker.py:86` deliberately treats `CLOSED_T1` as still-open:

```sql
SELECT * FROM positions WHERE status IN ('OPEN', 'CLOSED_T1')
```

— correct for penny/swing (the runner manages the remaining 50% after T1), wrong
for single-leg momentum MIS. Commit `64ce0e5` fixed the *writer* so new momentum
exits get a terminal status, and it **is deployed** (ancestor of `708f669`). But the
two pre-existing rows were never repaired, so they are phantom-open **forever**.

### Consequence A — real orders for shares that don't exist

`auto_square_momentum` (main.py:2742) runs at 15:15 IST, reads `get_open_positions()`,
gets the two phantoms, and sends a real order per phantom via
`POST /api/orders/square-off` → `kite.placeOrder()` (`orders.js:88`).

Both days, verified in the node-gateway log:

```
[SQUARE-OFF] THELEELA   | Qty: 4 | Type: LIMIT | Reason: AUTO_SQUARE_EOD   → 200
[SQUARE-OFF] LATENTVIEW | Qty: 1 | Type: LIMIT | Reason: AUTO_SQUARE_EOD   → 200
```

Limit prices were 0.5% below live LTP (Thu ₹473.30 / ₹292.90; Fri ₹472.50 / ₹294.80),
product `MIS`. **Zerodha accepted every one** — `placeOrder` returned an order_id and
the route replied 200 without throwing.

This has run on **07-21, 07-22, 07-23, 07-24** → **8 real sell orders** for stock the
account does not hold. A filled MIS sell with no long position opens a **naked
intraday short**, which Zerodha then force-squares in its own 15:20–15:25 window.

**Not verifiable from these logs:** whether the orders filled. The square-off route
never writes to `executed_orders` (last row there is dated 2026-07-20), so the system
holds **no record of these 8 orders at all** — no order_id, no fill, no P&L.
**This must be checked against the Zerodha orderbook/tradebook for 07-21 → 07-24.**
An aggressive sell limit on a liquid NSE stock normally fills.

### Consequence B — fabricated losses in the ledger

After placing each order, `auto_square_momentum` runs `record_trade_close()`
unconditionally, computing P&L from the **original 20 July entry price** against
today's LTP. The `UPDATE ... WHERE status='OPEN'` that should close the row matches
**zero rows** (status is `CLOSED_T1`), so the phantom survives to repeat tomorrow.

Ledger rows written at 15:15 IST, `source='SYSTEM'`:

| Date | THELEELA | LATENTVIEW | Day total |
|---|---|---|---|
| 2026-07-21 | −17.93 | −1.11 | −19.04 |
| 2026-07-22 | −7.34 | −1.21 | −8.55 |
| **2026-07-23** | **−62.90** | **−11.81** | **−74.71** |
| **2026-07-24** | **−66.10** | **−9.91** | **−76.01** |
| | | **Total** | **−178.31** |

Nifty bankroll: **₹5,009.03 → ₹4,830.73**. Every rupee of that ₹178 decline is
fiction — and it grows daily as the two stocks drift further from their July-20
entry prices (₹19/day → ₹76/day).

### Consequence C — the circuit breaker is now permanently tripped

CB2 (`performance.py:313`) counts consecutive negative `TRADE_CLOSED` rows for
`source IN ('SYSTEM','MOMENTUM')` since the last `CB_RESET`. There has **never been
a `CB_RESET` row**. Current streak walking back from id 45:

```
45 −9.91  44 −66.10  40 −11.81  39 −62.90
37 −1.21  36 −7.34   34 −1.11   33 −17.93   ← 8 losses
31 +3.33                                     ← streak stops here
```

`CB_MAX_CONSECUTIVE_LOSSES = 5`. **All 8 losses in the streak are phantom
re-closes** (ids 33+ are all 15:15 auto-square rows). The last two real momentum
trades, ids 30 and 31, were both **profits**.

So the system reported itself halted on both days —

- Thu 15:17 IST and Fri 09:22 IST partner broadcast: *"⛔ Our system halted its own trading today (CB_CONSECUTIVE_LOSSES)"*
- Both days ended: *"⚠ Day ended HALTED: CB_CONSECUTIVE_LOSSES"*

— on the strength of eight losses that never happened.

**Important nuance:** the halt is **advisory only**. `check_circuit_breakers` is
imported in `main.py` but never called there; its only consumers are
`penny_health.py` (health snapshot), `routes_ops`/`routes_portfolio` (display),
`nifty_commands` (`/nifty circuit`) and `partner_orchestrator` (the broadcast).
**No entry path is gated by it.** The halt did not cause the zero trades — it just
told you, and your partner-tips subscribers, something alarming and false.

### Consequence D — momentum could not trade (the expensive one)

`filter_momentum_signals` (portfolio.py:23) computes
`deployed_pool = Σ entry_price × shares` over "open" positions:

```
THELEELA    490.90 × 4 = 1,963.60
LATENTVIEW  305.85 × 1 =   305.85
                        ─────────
deployed                 2,269.45
```

| | Thursday | Friday |
|---|---|---|
| Nifty bankroll | ₹4,856.56 | ₹4,781.85 |
| Momentum pool (50%) | ₹2,428.28 | ₹2,390.93 |
| Locked by phantoms | ₹2,269.45 | ₹2,269.45 |
| **Free cash** | **₹158.83** | **₹121.48** |
| **% pool locked** | **93.5%** | **94.9%** |

Momentum needs a stock priced under ~₹159 (Thu) / ~₹121 (Fri) to buy even one share.
Almost nothing in the Nifty 500 qualifies.

Candidates that **passed every strategy gate** (`net_ev > 0`) and died at the
allocator:

| Reject reason | Thu | Fri |
|---|---|---|
| `MOMENTUM_POOL_EXHAUSTED` | 18 | 8 |
| `insufficient_pool_for_one_share` | 5 | 7 |
| `zero_shares_momentum` | 2 | 1 |
| **Total capital-starved** | **25** | **16** |

Thursday's kills included `CGCL` (₹244.45 × 9), `FIRSTCRY` (₹208.18 × 11),
`TMPV` (₹328.20 × 7), `PFC` (₹412.90 × 5), `USHAMART` (₹496.90 × 4), `KPITTECH`,
`INDIANB`, `GODREJPROP`, `TBOTEK`, `RAINBOW`, `ZFCVINDIA`, `NH`, `KPIL`, `GODREJIND`.
Friday's: `AWL` (₹187.16 × 12), `HEXT` (₹544.50 × 4), `KIMS` (₹787 × 3),
`JSWSTEEL`, `PAYTM`, `TORNTPOWER` (×2), `TEGA`.

The Telegram scan cards corroborate: Thursday logged **15 raw hits** across the day,
Friday **7** — "Raw hits: 4 / 3 / 1 …", every card ending `Accepted: 0`.

**This is the assessment's core point.** Momentum was not short of signals on either
day. It was short of ₹2,269 that a stale database row is pretending to hold.

---

## 3. Book-by-book activity

| Book | Thu evals | Thu accepts | Fri evals | Fri accepts |
|---|---|---|---|---|
| Penny MIS | 37,530 | **0** | 36,088 | **0** |
| Penny CNC | 54 | **0** | 52 | **0** |
| Penny EDGE | **0** | 0 | **0** | 0 |
| Momentum | 9,499 | **0** | 9,988 | **0** |
| F&O engine leg | 60 | **0** | 60 | **0** |
| F&O paper (legacy) | — | **1 trade** | — | **3 trades** |
| F&O defined-risk | — | **0 (crashes)** | — | **0 (crashes)** |

### Penny — genuine strategy drought, unchanged histogram

Penny scanned on its 30 s cadence all day (684 scans Thu, 683 Fri) and rejected
everything. The MIS reject profile is diffuse and dominated by time/confirmation
gates: `outside breakout time window` (~104–108 per minute-bucket, i.e. the whole
pre/post-window day), `breakout not confirmed` (close below level, e.g.
`22.70 <= 23.25`), `insufficient_intraday_bars` (~190–204/day).

CNC top rejects: `below 200 SMA` (37% Thu → 48% Fri), `below 50 SMA`,
`RSI not rising for 2 bars`. That is a rangebound-market signature, not a dead gate.

The system self-alarmed correctly on both days:

- `⚠️ Penny zero-accept alarm` — MIS (74,365 evals / 2 days Thu; 73,618 Fri) and CNC
- `🚨 PENNY DEAD-GATE SUSPECTED` — EDGE leg, "one gate rejects ≥90%"

The EDGE alarm is **stale and misleading**: it cites 3 evaluations over
2026-07-21 → 07-22, but the EDGE leg logged **zero evaluations on both Thursday and
Friday**. It is not being throttled by a gate; it is not running at all. Worth a
separate look.

**Penny universe data quality:** `degraded=34/54` (Thu) and `degraded=33/52` (Fri)
— **63% of the tradeable universe carries `data_quality=DEGRADED*`** on both days.
Given `_universe_audit_is_degraded`'s own comment that the promoter and P/B gates are
null-tolerant, this deserves verification that those two safety gates are actually
live for the degraded two-thirds. The corp-data seed from `6885a83` is in prod, so
this is not the old `corp_source=missing` failure — but 63% is high enough to check.

### F&O defined-risk book — never opened a single structure

`fno_dr_book.py:174` and `:187`:

```python
if snap is None or not snap.spot or snap.spot <= 0:   # line 174
...
atm = _nearest_strike(snap.spot, step)                # line 187
```

`ChainSnapshot` (`fno_chain.py:53`) has **no `spot` field**. Its pricing basis is
`forward` (futures LTP). Every tick throws:

```
[error] fno_dr_open_failed err='ChainSnapshot' object has no attribute 'spot'
AttributeError: 'ChainSnapshot' object has no attribute 'spot'
```

**297 times on Thursday, 297 on Friday** — once per 60 s tick, all day, both days.
The exception is caught, so the tick reports `executed successfully` and the
scheduler stays green. `fno_dr_positions` is empty.

The chain snapshot itself is healthy — `fno_chain_snapshot expiry=2026-07-28
forward=23709.4 atm=23700 contracts=62/62` — so this is a pure naming bug shipped
with PR #70. **Phase 2 of the defined-risk book has been dead since 2026-07-20 and
has produced no data whatsoever.**

Fix is a two-line rename (`snap.spot` → `snap.forward`), but it needs a test that
would have caught it — the existing tests evidently construct their own snapshot
shape.

### F&O legacy paper book — the only thing trading, and it lost

Directional NIFTY ORB via **long puts** (`direction=SHORT` = bearish view;
P&L = `(exit_premium − entry_premium) × qty`, so max loss = premium paid).

| Date | Symbol | Lots | Entry prem | Exit | Exit reason | P&L |
|---|---|---|---|---|---|---|
| 07-23 12:45 | NIFTY26JUL23900PE | 1 | 165.10 | 170.55 | time_stop | **+286.49** |
| 07-24 10:05 | NIFTY26JUL23700PE | 1 | 158.10 | 139.40 | time_stop | **−1,280.18** |
| 07-24 10:35 | NIFTY26JUL23700PE | 1 | 159.25 | 130.60 | time_stop | **−1,926.15** |
| 07-24 11:00 | NIFTY26JUL23700PE | 2 | 151.85 | 133.15 | underlying_stop | **−2,511.65** |

**Thursday +₹286. Friday −₹5,717.98.**

Two things stand out on Friday:

1. **It added to a loser, on the same strike.** Trade id 7 (1 lot, 23700PE) was open
   10:35 → 11:20. Trade id 8 (**2 lots, same 23700PE**) opened at **11:00** while id 7
   was still live and already losing. Peak concurrent premium at risk ≈ ₹30,000 on a
   single strike. There is no same-instrument or pyramiding guard.
2. **Position size is unmoored from the pool it books against.** Per-trade
   `max_loss_rupees` was ₹10,276 / ₹10,351 / ₹19,740. The hourly report calls the pool
   ₹250,000 — but the `bankroll_ledger` tracks `FNO_PAPER` equity as a running sum
   that went **₹725.81 → −₹5,841.22**. Two incompatible accountings of the same book,
   and the ledger side has no floor: it just goes negative.

Credit where due: the hourly F&O reports tracked Friday's damage accurately in
real time (`day_pnl=Rs -1,280` at 11:00 → `Rs -5,718` from 12:00 onward).

---

## 4. Real vs. fictional P&L for the two days

| Line | Thursday | Friday |
|---|---|---|
| Real broker fills initiated by strategy logic | **0** | **0** |
| Real orders sent for non-existent positions | **2** | **2** |
| Phantom ledger losses booked | −₹74.71 | −₹76.01 |
| F&O paper (fictional money) | +₹286.49 | −₹5,717.98 |
| **Genuine trading P&L** | **₹0** | **₹0** |
| **Unquantified real exposure** | 4 sh THELEELA + 1 sh LATENTVIEW sold | same |

Reported bankroll fell ₹4,906.73 → ₹4,830.73 across the two days. **None of that
movement corresponds to a trade the system actually took.**

---

## 4b. Resolution status (updated 2026-07-26)

Fixed in dev on `fix/fno-audit-phase1`, 1637 tests passing, **not yet deployed**:

| # | Item | Commit |
|---|---|---|
| P0 | Phantom rows can no longer be returned as open (`exit_date IS NULL` invariant) — neutralises both prod rows on deploy, no migration | `af545a0` |
| P1 | Auto-square refuses to order on an exited row; ledger write gated on `rowcount == 1`; broker `order_id` logged | `af545a0` |
| P1 | F&O `already_holding_this_contract` — no cross-bar pyramiding | `af545a0` |
| P2 | Partner broadcast no longer claims trading was halted | `af545a0` |
| P2 | 07:50 IST `premarket_login_nudge` | `af545a0` |
| P2 | Penny EDGE zero-candidate funnel breakdown | `af545a0` |
| — | Penny volume-gate reject now prints the threshold, not the baseline | `b1e2e4e` |

**Applied to prod 2026-07-26 15:30 IST** (`341d8fe`, backup
`/data/cache.db.bak-phantom-repair-20260726-153023`), verified through the
engine's own code paths:

| | Before | After |
|---|---|---|
| `nifty_bankroll()` | ₹4,705.8441 | **₹4,884.1512** |
| `check_circuit_breakers()` | `(True, ['CB_CONSECUTIVE_LOSSES'])` | **`(False, [])`** |
| Positions returned as open | 2 phantoms | **0** |

The repaired running balance lands on ₹5,009.0329 — exactly ledger id 31, the
last row before the bleeding began. That the arithmetic closes on the
pre-incident figure independently corroborates the reconstruction above.

**Still open:** the P0 broker-side question. Nothing in the repo can settle
whether the 8 real sell orders filled; that needs the Zerodha orderbook for
2026-07-21..24, and a fill would require its own reconciliation entry.

---

## 5. Prioritised actions

**P0 — verify real-money exposure.** Pull the Zerodha orderbook/tradebook for
2026-07-21 → 07-24 and determine whether the 8 `AUTO_SQUARE_EOD` sell orders filled.
If they did, the account has been opening and force-squaring naked intraday shorts
for four sessions with zero system-side record. This is the only item with real
money attached, and nothing in the logs can settle it.

**P0 — repair the two phantom rows.** Set `THELEELA` and `LATENTVIEW` (entry_date
2026-07-20) to a terminal status. This single change stops the daily real orders,
stops the fabricated losses, releases ₹2,269 (94% of the momentum pool), and clears
the consecutive-loss streak. Then insert a `CB_RESET` row and reverse the 8
fabricated `TRADE_CLOSED` rows (ids 33, 34, 36, 37, 39, 40, 44, 45; net +₹178.31)
so the bankroll reflects reality. Back up `cache.db` first.

**P1 — make the close idempotent and self-checking.** `auto_square_momentum` places
an order *then* writes P&L on a `WHERE status='OPEN'` update that can silently match
zero rows. It should refuse to act on a position whose `exit_date` is already set,
abort if the status update affects 0 rows, and record every order it places into
`executed_orders` so square-offs are reconcilable like entries are.

**P1 — fix the F&O defined-risk book.** `snap.spot` → `snap.forward` at
`fno_dr_book.py:174` and `:187`, plus a test that builds a real `ChainSnapshot` and
asserts `plan_structure` returns a structure. Phase 2 has been silently dead for
four sessions and has zero data to show.

**P1 — guard the F&O paper book.** No same-instrument stacking / no adding to an
open losing leg, and reconcile the ₹250,000 notional pool against the ledger's
`FNO_PAPER` running equity (currently −₹5,841). Add a floor so a paper pool cannot
go negative unnoticed.

**P2 — stop broadcasting a false halt.** The halt is advisory but it goes out to
partner-tips subscribers. Either gate the broadcast on a real streak or make CB2
ignore rows whose position has no matching open row. Also decide whether the
circuit breaker *should* gate entries — right now it is a label, not a control.

**P2 — pre-08:00 login nudge.** Carried over unactioned from the 2026-07-21 audit.
Friday's 08:17 login left 3 minutes of slack before the open. Schedule a 07:50
reminder off the existing `bootstrap_safety_tick`.

**P2 — investigate the silent penny EDGE leg.** Zero evaluations on both days, while
the alarm still cites a stale 07-21/07-22 dead-gate. And verify the promoter/P&B
gates are live for the 63% of the universe flagged `DEGRADED`.

---

## Appendix — verification notes

- Container logs retained from 2026-07-21 (json-file, 20 MB × 10, compressed), so
  both audited days are fully covered; `RestartCount=0` with today's `StartedAt`
  reflects a host reboot, not a container recreation.
- Momentum per-day eval counts read from the `momentum_signals` SQLite table rather
  than the CSV — the CSV's `raw` column contains embedded commas that shift fields.
- "Zerodha accepted the order" = `kite.placeOrder()` returned an order_id without
  throwing and the route replied 200. It is **not** evidence of a fill.
- The claim that the halt does not gate entries was checked by enumerating every
  call site of `check_circuit_breakers`: `main.py` imports it (line 34) and never
  calls it; all other consumers are reporting surfaces.
