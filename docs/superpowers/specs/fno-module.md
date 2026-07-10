# F&O Module — Design Spec

_Status: DRAFT, awaiting approval_
_Author: Uru + Claude, 2026-07-10_
_Target branch: `feat/fno-module` off `fix/penny-audit-phase2`_

---

## 0. Locked decisions

These were decided by the operator on 2026-07-10 and are not open for
re-litigation inside this spec. Everything below follows from them.

| Decision | Value | Consequence |
|---|---|---|
| Paper pool | Rs 1,00,000 | `FNO_PAPER_BANKROLL = 100000.0` |
| Live pool | Rs 0 (not armed) | Live leg refuses to arm; see §11 |
| Risk mandate | **Bounded max loss**, not "never sell" | `max_loss()` is the constitution (§4) |
| Underlying | **NIFTY only** | No BANKNIFTY, no SENSEX, no stock options |
| Holding period | **Intraday only** | Force-close 15:10 IST. No overnight. Ever, in P1. |
| P1 strategy | **FNO-MOM** only | FNO-VOL (§13) deferred; needs multi-day holds |

---

## 1. Goal and non-goals

### Goal

An autonomous intraday NIFTY-options module that trades without operator
approval (like the penny module, unlike swing/momentum), reports hourly to
Telegram, and whose maximum loss on any position is finite, known before the
order is placed, and enforced structurally rather than by convention.

### Explicit non-goals for P1

- **Making money.** P1 succeeds if the plumbing is proven honest: paper fills
  reconcile against real bid/ask, every gate is provably satisfiable, the
  engine does not freeze, and `max_loss()` holds. A flat paper equity curve
  with a fully validated execution path is a **pass**.
- Multi-day holds, straddles, spreads, any short leg.
- Any underlying other than NIFTY.
- Beating the momentum module. Different pool, different mandate.

### The honest expectation

A long-only index-option momentum book has a 30-40% win rate and a jagged
equity curve. Consistency comes from position sizing, not from win rate.
Losing streaks of 6-7 trades are routine, not evidence of a broken system.
The operator asked for "little but consistent profit"; that profile belongs to
a defined-risk premium *seller* (FNO-THETA, §13), which is unlocked at P4 and
only after the liveness problem is closed.

---

## 2. Why long-only, and why that is not a concession

The stated reason for buy-only was "selling has unlimited loss potential."
That is true only of **naked** shorts. A hedged short (vertical spread, iron
condor) has a maximum loss of `width - credit` — finite, arithmetic, knowable
at entry. So "never sell" is a *proxy* for the real requirement, and a
strictly more restrictive one. This spec adopts the real requirement:

> **Every position must have a finite maximum loss, computable at entry, and
> that computation must be enforced in code on the order path.**

The much stronger argument for long-only in P1 is operational, not
structural. On 2026-07-07 the python-engine froze for 6h32m — no log lines,
no cron fires, straight through market hours. Ask what a frozen engine costs
per position type:

- **Long option, engine dies:** you lose the premium already paid. The bound
  was set by the *structure* at entry, with no software in the loop.
- **Any short leg, engine dies:** the bound depends on a broker-resident stop
  firing. And **Zerodha does not support SL-M on options** (VERIFY-1, §14) —
  so you are leaning on SL-limit orders, which do not fill through a gap.

The penny module's central safety invariant — *"every entry is paired with a
mandatory broker-side SL-M, or we immediately market-unwind"* — **does not
port to F&O.** Long-only is the only structure whose risk bound survives our
own infrastructure failing.

This gives a falsifiable graduation criterion for spreads: not "when I feel
ready," but *when the liveness heartbeat has logged N consecutive clean days*
(§11).

---

## 3. The capital arithmetic (read this before anything else)

Options do not fractionalise. A NIFTY lot is ~75 (VERIFY-2 — **read it from
the instrument dump every morning, never hardcode**). One lot is the minimum
position and therefore the *floor* on per-trade risk.

```
premium_per_unit  P   = Rs 100      (ATM weekly, typical)
lot_size          L   = 75
committed             = P * L       = Rs 7,500        (7.5% of pool)
stop              s   = 25% of premium
risk_per_lot          = P * L * s   = Rs 1,875        (1.875% of pool)
```

So **a 2% per-trade risk cap is the tightest cap that still admits a single
lot**, and Rs 1,00,000 clears it with ~6% headroom. Now price a richer day:

```
P = Rs 150  ->  committed = Rs 11,250,  risk_per_lot = Rs 2,812  = 2.8% of pool
```

Over the cap. The required pool for that contract is Rs 1,40,625, and we do
not have it.

**Therefore `min_viable_pool` is evaluated per trade at entry, not once per
day as a constant:**

```python
def min_viable_pool(premium: float, lot_size: int, stop_pct: float,
                    max_risk_pct: float) -> float:
    return (premium * lot_size * stop_pct) / max_risk_pct
```

If `pool < min_viable_pool(...)`, the trade is rejected with
`reject_reason="pool_below_min_viable"`. On expensive-premium days the module
simply declines to trade rather than quietly oversizing.

**This is the most important property in the spec.** Premium is expensive
precisely when implied volatility is high — which is exactly when long options
are worst. The risk arithmetic therefore *yields a volatility filter for free*,
without anyone writing a volatility filter. Self-regulating, and impossible to
mis-tune because it falls out of the sizing identity.

**Consequence the operator must expect:** at Rs 1,00,000 the module can only
take a 1-lot trade when `premium <= (0.02 * 100000) / (75 * 0.25) = Rs 106.67`.
ATM NIFTY weeklies frequently print above that. **On a meaningful fraction of
days the module will correctly report zero trades.** This is healthy behaviour
and must be distinguishable from a dead gate — see §9.

Concurrency falls out the same way. A 15%-of-pool cap on total open long
premium gives Rs 15,000, which is two lots at Rs 7,500. `FNO_MAX_CONCURRENT=2`
is not a chosen number; it is what the premium cap implies.

---

## 4. The constitution: `max_loss()`

One pure function, in `fno_risk.py`, on the order path. Every proposed
position from every strategy passes through it before an order is placed.

```python
def max_loss(legs: list[Leg], lot_size: int) -> float:
    """Rupee max loss of a position. Returns math.inf if unbounded."""
```

### Algorithm

The expiry P&L of any option combination is a **continuous piecewise-linear
function of the underlying `S`**, with kinks only at the strikes. Its minimum
therefore occurs at `S=0`, at a strike, or in a tail.

1. Build `pnl(S) = sum(leg_payoff(S)) - net_debit_paid`.
2. Evaluate at `S = 0` and at every strike in `legs`. (Both tails' behaviour
   is captured by slope, below.)
3. **Right tail:** `slope_right = sum(+q for long calls) + sum(-q for short calls)`.
   Puts contribute 0 as `S -> inf`. If `slope_right < 0`, P&L falls without
   bound: **return `math.inf`.**
4. **Left tail:** always finite, because `pnl(0)` is finite. Already covered
   by step 2.
5. `max_loss = -min(evaluated pnl values) * lot_size`, floored at 0.

This is model-free — no Black-Scholes, no IV, no assumptions. It is exact.

### Truth table

| Position | `slope_right` | Result |
|---|---|---|
| Long CE | `+q` | debit (finite) |
| Long PE | `0` | debit (finite) |
| Bull call spread (long K1, short K2>K1) | `0` | net debit |
| Bear call spread (short K1, long K2>K1) | `0` | `(K2-K1) - credit` |
| Iron condor | `0` | `width - credit` |
| **Naked short call** | `-q` | **`inf` -> REJECTED**  |
| **Ratio spread** (short 2, long 1) | `-q` | **`inf` -> REJECTED** |

### Enforcement rules

- Rejection on `inf` is **unconditional**. No config flag, no env var, no
  operator override, no `force=True` kwarg. There is no code path that places
  an order for a position whose `max_loss` is `inf`.
- Also reject if `max_loss > FNO_MAX_LOSS_PER_TRADE`.
- `options_math` is **not** imported by `max_loss`. It must stay pure.
- **This function carries the heaviest test coverage in the repository.**
  100% branch coverage is a P0 exit criterion, and a go-live gate (§11).

The point of centralising it: a strategy module *cannot* propose an unbounded
position even by accident, even if the strategy has a bug. It also makes the
eventual P4 graduation safe — FNO-THETA proposes an iron condor, `max_loss`
returns `width - credit`, the invariant holds, and **nothing else in the
system changes.**

---

## 5. Module layout

```
python-engine/
  options_math.py       # BS pricing, IV via Brent, greeks. Pure. No I/O.
  fno_models.py         # Leg, Contract, OptionType, FnoSource enums
  fno_risk.py           # max_loss(), min_viable_pool(), caps, kill switches
  fno_instruments.py    # NFO dump -> (name,expiry,strike,type) -> token
  fno_chain.py          # ATM+/-5 snapshot, synthetic forward, staleness guard
  fno_engine_mom.py     # signal on NIFTY FUTURES bars. Never on premium.
  fno_executor.py       # LIMIT only. Fill timeout, cancel. Never chase.
  fno_orchestrator.py   # FNO_PAPER / FNO_LIVE dual leg
  fno_hourly_report.py  # per-hour Telegram brief
  fno_signal_log.py     # append-only /data/fno_signals.csv
```

### Isolation rule

Mirroring `tests/test_penny_isolation.py`, a new `tests/test_fno_isolation.py`
asserts that no `fno_*` module imports `penny_*`, `engine.py`, `risk_engine`,
`portfolio`, or `evaluate_signal`. A **read-only** import of `regime.py` is
permitted and expected.

Rationale: the isolation rule exists so one subsystem's bug cannot cascade.
F&O has real money and a fresh codebase; it gets the same firewall.

---

## 6. Data layer

### 6.1 NFO instruments (`fno_instruments.py`)

`GET /instruments/NFO` returns 60,000-90,000 rows. This gets its **own
structure**, keyed `(name, expiry, strike, instrument_type) -> token`, plus a
`tradingsymbol -> token` side map.

**It must NOT be poured into `kite_client.instrument_cache`.** That cache is a
flat `symbol -> token` dict of NSE equities; NFO tradingsymbols would collide
with equity symbols and would inflate a cache that already takes ~38 minutes
to fill on a cold container start (ops rule 61).

Refreshed once daily at 08:00 IST, alongside the penny universe refresh. From
the dump we read, never hardcode:

- `lot_size` (VERIFY-2)
- `strike` step
- `expiry` dates and the weekly/monthly expiry calendar (VERIFY-3)

### 6.2 Chain snapshot (`fno_chain.py`)

ATM +/- 5 strikes, both CE and PE = 22 contracts. Well inside Kite's
500-instrument `/quote` batch limit, so this is **one HTTP call**.

> Note: the penny scanner's per-ticker `/quote` pattern is a live production
> bug (see `penny-prod-bugs-2026-07-10.md`, BUG-2). Do not repeat it. Batch
> from day one.

**Price off the synthetic forward, not spot.** Back the forward out of
put-call parity at the ATM strike, or use the front-month futures price:

```
F = K_atm + (C_atm - P_atm) * e^(rT)
```

Using spot for index options quietly biases every IV and every delta the
module computes. This is a silent, systematic error, and it would corrupt
the stop conversion in §8.

### 6.3 `options_math.py`

Pure, dependency-free, exhaustively unit-tested:

- Black-Scholes call/put price (on forward `F`, i.e. Black-76)
- Implied volatility by Brent's method, bracketed `[0.01, 3.0]`, with a
  documented failure return (`None`, never an exception, never a silent 0.0)
- Greeks: delta, gamma, theta, vega

Needed for: delta (converts an underlying-point stop into a premium stop),
strike selection by delta, and the sanity gates in §7.

Kite's `/quote` does **not** return IV. We compute it. FNO-VOL would also need
an IV *percentile history* which we do not have — that is a reason FNO-VOL is
deferred, and intraday-only P1 removes the dependency entirely.

---

## 7. Entry gates

Evaluated in this order. **Every gate writes its `reject_reason` to
`/data/fno_signals.csv` whether or not it fires** (§9).

### 7.1 Calendar / session

| Gate | Rule |
|---|---|
| Trading day | NSE open, not a holiday |
| Entry window | `09:45 <= t < 14:45 IST` (needs 30m of bars for the opening range) |
| Expiry day | **No new entries at all in P1.** `FNO_EXPIRY_DAY_ENTRIES=False` |
| Hard flat | 15:10 IST, unconditional square-off |

Expiry-day gamma turns a directional position into a coin flip. Revisit at P3
with data, not before.

Even though P1 is intraday-only, encode the rule now for P3's sake:
**never let a long option expire ITM — always square off before close on
expiry day.** The STT treatment on exercised options changed in 2019 and is
less punitive than it once was (VERIFY-4), but there is no upside to
discovering the current rule with real money.

### 7.2 Regime

Read-only call into `regime.py`. **Block all entries in `REGIME_3_CRISIS`.**
Sizing is unaffected (we are always exactly 1-2 lots); the regime gate is
purely on/off.

### 7.3 Liquidity and microstructure

Penny never needed these. F&O lives or dies on them.

| Gate | Threshold | Setting |
|---|---|---|
| Open interest | `OI >= FNO_MIN_OI` | 5,000 contracts |
| Today's volume | `vol >= FNO_MIN_VOL` | 1,000 contracts |
| Bid-ask spread | `(ask - bid) / mid <= 0.015` | `FNO_MAX_SPREAD_PCT` |
| Quote freshness | `last_trade_time` within 120s | `FNO_MAX_QUOTE_AGE_SEC` |
| Two-sided market | `bid > 0 and ask > 0` | — |

### 7.4 Freak-trade guard

NSE options print genuine freak trades. Two **model-free** checks, so a bad IV
solve cannot itself become the bug:

1. **Intrinsic floor.** `premium >= max(0, F - K)` for a call,
   `premium >= max(0, K - F)` for a put. A premium below intrinsic is either
   an arbitrage or bad data. Either way: reject.
2. **Quote envelope.** `bid * 0.9 <= LTP <= ask * 1.1`.

A model-based sanity check runs *in addition*, never instead: reject if the
solved IV falls outside `[0.05, 1.00]`.

### 7.5 Capital

| Gate | Rule |
|---|---|
| Min viable pool | `pool >= min_viable_pool(premium, L, stop_pct, max_risk_pct)` |
| Open premium cap | `open_premium + new_premium <= 0.15 * pool` |
| Concurrency | `open_positions < FNO_MAX_CONCURRENT` (=2) |
| Trades per day | `trades_today < FNO_MAX_TRADES_PER_DAY` (=3) |

### 7.6 Kill switches

| Switch | Threshold | Action |
|---|---|---|
| Daily loss | 6% of pool | Halt entries for the day |
| Weekly loss | 12% of pool | Halt entries for the week |
| Monthly loss | 20% of pool | Halt, Telegram-page the operator |
| Consecutive losses | 6 | Pause 1 trading day, Telegram-page |
| Data staleness | chain snapshot > 60s old | No new entries |

Weekly and monthly caps exist because **options bleed slowly enough to walk
under a daily limit every single day for a month.** Penny only has a daily
switch; that is sufficient for penny and insufficient here.

The consecutive-loss halt exists because a long-option strategy's 6-loss
streak is statistically routine. The system should pause and ask, rather than
discover its edge is gone by spending the pool.

---

## 8. FNO-MOM: the strategy

### 8.1 Signal is computed on the underlying. Never on the option.

This is the mistake nearly everyone makes. An option's price series is
contaminated by theta decay and IV changes at once, so an EMA or RSI computed
on premium is measuring three things and reporting on none of them.

**Compute every signal on NIFTY front-month futures 5-min bars.** The option
is purely the expression vehicle. This also means the signal layer is largely
a port of existing momentum machinery, not an invention.

### 8.2 Entry

```
OR_high, OR_low  = high/low of 09:15-09:45 (opening range)
atr              = ATR(14) on 5-min futures bars

LONG (buy CE) when, on a closed 5-min bar:
    close > OR_high + 0.25 * atr
    EMA(21) > EMA(50)                    # trend agreement
    RVOL(5m) >= 1.2                      # participation
    regime != REGIME_3_CRISIS

SHORT (buy PE): symmetric, close < OR_low - 0.25 * atr, EMA(21) < EMA(50)
```

Re-entry after a stop-out is permitted only on a *fresh* break of the opening
range, capped by `FNO_MAX_TRADES_PER_DAY`.

### 8.3 Strike selection

Pick the strike whose `|delta|` is **closest to 0.55** — i.e. ATM or one
strike ITM.

Slightly ITM is the right default and the reasoning matters: more of the
premium is intrinsic value, so less of what you paid is theta-exposed; the
relative bid-ask is tighter; and IV crush does less damage. It costs more per
lot, which interacts with `min_viable_pool` — accepted, and the trade-off is
deliberate.

Never OTM. Cheap OTM options are how a "risk-controlled" system quietly turns
into a lottery-ticket machine.

### 8.4 Stops

Three layers, tightest wins:

1. **Structural (underlying):** `OR_low` for a long, `OR_high` for a short.
2. **Volatility (underlying):** `1.5 * atr` from entry.
3. **Premium backstop:** `premium <= 0.75 * entry_premium` (-25%).

Underlying stops convert to premium via delta:

```
premium_stop = entry_premium - delta * underlying_stop_distance
```

The premium backstop is the one that actually bounds `risk_per_lot` in the
sizing identity (§3), so it is the one `min_viable_pool` is computed against.
The others exist to exit earlier, never later.

**The stop is engine-managed.** Zerodha has no SL-M for options (VERIFY-1),
and an SL-limit will not fill through a gap. We accept this *only because* the
long-option structure already bounds the loss at the premium paid — a frozen
engine costs us the premium, nothing more. **This reasoning does not survive
the introduction of a short leg, which is why spreads are gated on liveness.**

### 8.5 Exits

| Trigger | Action |
|---|---|
| Target | 1.5R (in underlying points), then trail at `1.0 * atr` |
| Stop | Any of the three layers in §8.4 |
| Time stop | Not +0.5R within 45 minutes -> exit |
| Hard flat | 15:10 IST, unconditional |

The time stop is inherited from the penny module's insight (`penny_engine_
breakout.py:433`): a breakout that does not move is a failed breakout, and
holding it only pays theta.

---

## 9. Observability: making the penny failure impossible

Production ran a **mathematically unsatisfiable** breakout gate for nine
months. It emitted perfect breadcrumbs. It passed every health check. It
reported "0 trades — legit empty day" every evening. 215,814 lifetime
evaluations, zero accepts.

The F&O module gets, from its **first commit**, the two defences that would
have caught it on day two. Both are cheap. Both are also worth backporting to
penny.

### 9.1 Gate falsifiability tests

For every gate, a unit test that constructs an input which **passes** it.

Not "a test that the gate rejects bad input" — a test that proves the gate is
**satisfiable at all**. If no passing input can be constructed, the gate is
dead and CI says so on the day it is written.

The `bar_close > day_high` bug dies instantly under this rule, because nobody
can write the passing case: a bar's close cannot exceed a running high that
includes that bar.

```python
# tests/test_fno_gate_falsifiability.py
@pytest.mark.parametrize("gate", ALL_ENTRY_GATES)
def test_gate_is_satisfiable(gate):
    """Every gate MUST admit at least one passing input."""
    assert gate.accepts(gate.witness_input()), f"{gate.name} is unsatisfiable"
```

Each gate ships with a `witness_input()`. **A gate without a witness does not
merge.**

### 9.2 Accept-rate telemetry with an alarm

`/data/fno_signals.csv`, append-only, from day one — one row per evaluation
with `accepted` (0/1) and `reject_reason`. Ops rule 75 already established
that the CSV, not `docker logs`, is the ground truth for "is it really doing
nothing?"

Then: **if `accepts == 0` across N consecutive days while `evaluations > 0`,
fire a Telegram alert carrying the top reject-reason histogram.**

The alarm must distinguish two cases, and this is the whole reason §3's
reject taxonomy earns its keep:

- `reject_reason=pool_below_min_viable` dominating -> **healthy.** The module
  is correctly declining expensive-premium days. Do not alert; report it in
  the hourly brief as a self-regulation event.
- A histogram that **never varies**, or a reason that is 100% of rejects on
  every day regardless of market conditions -> **a dead gate.** Alert loudly.

Penny needs this more urgently than F&O does.

### 9.3 Inherited ops rules

All of these transfer directly and are P0, not P2:

- **Layered breadcrumbs** (rules 55, 56) — cron wrapper, orchestrator, and
  engine each emit a first-line breadcrumb, each wraps downstream calls in
  try/except with a distinct log tag.
- **DB-table preflight** (rule 57) — first DB call verifies its tables exist,
  logs `fno_db_unready reason=<table>_missing FIX=<remediation>`, and returns
  a well-formed empty result rather than raising.
- **Threaded liveness heartbeat** (rule 68) — a separate `threading.Thread`,
  not an asyncio task. A frozen event loop freezes an asyncio heartbeat, which
  is the exact failure it exists to detect.
- **WARNING escalation on degradation** (rules 72, 74) — a summary line with
  `applied=0` out of N is a WARNING, never an INFO.
- **structlog/stdlib logger unification** (rules 67, 69) — every `fno_*`
  module uses `structlog.get_logger()`. No `logging.getLogger(__name__)`.

---

## 10. Execution and accounting

### 10.1 Order path

- **LIMIT orders only. Never market.** The bid-ask spread on an option is the
  single largest controllable cost.
- Entry: LIMIT at ask (or `mid + 1 tick`), `FNO_FILL_TIMEOUT_SEC=30`, then
  cancel. **Never chase.** A missed fill is free; a chased fill is not.
- Exit: LIMIT at bid, escalating to a marketable limit at
  `bid - 3 ticks` after 15s. On the 15:10 hard flat, a marketable limit wide
  enough to guarantee the fill — the position must be closed.
- Every order is tagged with the leg source.

### 10.2 Cost model (`fno_costs.py`)

Flat fees punish small premiums, which is a structural argument for fewer,
larger, more meaningful positions. This inverts the penny module's
"many small bets" assumption; the cost model must be written fresh, not
copied from `calc_penny_costs`.

Round-trip on one lot at Rs 100 premium (Rs 7,500):

| Component | Approx |
|---|---|
| Brokerage | Rs 20 x 2 = Rs 40 |
| STT (sell side, on premium) | VERIFY-5 |
| Exchange txn (on premium) | ~Rs 4 |
| GST 18% on (brokerage + txn) | ~Rs 8 |
| Stamp duty | ~Rs 0.2 |
| **Total** | **~Rs 55, i.e. ~0.7% of the position** |

The module must clear ~0.7% of premium movement before it earns a rupee. On a
Rs 3,000 spread debit the same flat Rs 40 is ~1.3%. **There is no
`FNO_BROKERAGE_BYPASS`.** Penny has one for paper-mode proactiveness
measurement; F&O must not, because cost is a first-order term in whether this
strategy works at all, and hiding it would make the paper leg lie.

### 10.3 Pool isolation

New source tags `FNO_PAPER` / `FNO_LIVE`, and `fno_bankroll()` in
`performance.py`.

The existing strict-separation queries filter on
`source IN ('SYSTEM', 'MOMENTUM')` and `source = 'PENNY'`, so adding tags is
**purely additive**. An F&O drawdown cannot trip a Nifty circuit breaker and
cannot touch the penny pool. This preserves the operator mandate of
2026-06-24.

### 10.4 Dual-leg orchestrator

Reuse the `EDGE_PAPER` / `EDGE_LIVE` shape from `penny_edge_orchestrator.py`.
It is exactly the right pattern: one candidate scan, two legs, bankroll scales
the sizing, separate source tags so the legs cannot see each other's rows.

In P1 the live leg is disabled and `FNO_LIVE_BANKROLL = 0`. In P2 both run,
and **fill divergence between paper and live is the primary metric** — it is
the only way to learn whether our paper fills are honest.

---

## 11. Phasing and the go-live gate

| Phase | Scope | Exit criteria |
|---|---|---|
| **P0** | `options_math`, NFO cache, chain snapshot, `max_loss`, signal CSV, breadcrumbs. **No trading.** Shadow-log what it *would* have done. | `max_loss` at 100% branch coverage; every gate has a witness |
| **P1** | Paper FNO-MOM, hourly Telegram reports | >= 40 trading days, >= 60 paper trades |
| **P2** | Real money, 1 lot, paper+live side by side | Fill divergence tracked and bounded |
| **P3** | FNO-VOL (multi-day, needs IV history) | — |
| **P4** | Defined-risk spreads (FNO-THETA) | 30 clean liveness days |

### `fno_go_live_check()`

Make promotion a function, not a judgment call:

```python
def fno_go_live_check() -> list[str]:
    """Returns unmet conditions. The live leg refuses to arm if non-empty."""
```

It checks:

1. `pool >= min_viable_pool` for the current ATM contract
2. `>= 40` paper trading days **and** `>= 60` paper trades
3. Paper profit factor `>= 1.2`
4. **No liveness-heartbeat gap `> 5 min` in the last 30 days**
5. SL mechanism verified against the live broker — a real order placed and
   cancelled, not a unit test (this closes VERIFY-1 empirically)
6. `max_loss()` at 100% branch coverage

These numbers are fixed **now**, before there is a paper equity curve to
rationalise against. That is the entire reason they are encoded as a function
rather than written in a runbook.

---

## 12. Config surface

```python
# --- pools -------------------------------------------------------------
FNO_PAPER_BANKROLL:        float = 100000.0
FNO_LIVE_BANKROLL:         float = 0.0        # not armed
FNO_LIVE_TRADING:          bool  = False      # master switch
FNO_DISABLE_PAPER:         bool  = False
FNO_DISABLE_LIVE:          bool  = True

# --- universe ----------------------------------------------------------
FNO_UNDERLYING:            str   = "NIFTY"    # NIFTY only in P1
FNO_STRIKE_WINDOW:         int   = 5          # ATM +/- N strikes to snapshot
FNO_TARGET_DELTA:          float = 0.55       # ATM / 1-strike ITM

# --- sizing / risk -----------------------------------------------------
FNO_MAX_RISK_PCT:          float = 0.02       # per trade, of pool
FNO_STOP_PREMIUM_PCT:      float = 0.25       # premium backstop
FNO_MAX_OPEN_PREMIUM_PCT:  float = 0.15       # total committed premium
FNO_MAX_CONCURRENT:        int   = 2          # implied by the line above
FNO_MAX_TRADES_PER_DAY:    int   = 3
FNO_MAX_LOSS_PER_TRADE:    float = 2500.0
FNO_MAX_LOTS:              int   = 2

# --- kill switches -----------------------------------------------------
FNO_DAILY_KILL_PCT:        float = 0.06
FNO_WEEKLY_KILL_PCT:       float = 0.12
FNO_MONTHLY_KILL_PCT:      float = 0.20
FNO_MAX_CONSECUTIVE_LOSSES: int  = 6

# --- microstructure ----------------------------------------------------
FNO_MIN_OI:                int   = 5000
FNO_MIN_VOL:               int   = 1000
FNO_MAX_SPREAD_PCT:        float = 0.015
FNO_MAX_QUOTE_AGE_SEC:     int   = 120
FNO_IV_SANITY_MIN:         float = 0.05
FNO_IV_SANITY_MAX:         float = 1.00

# --- session -----------------------------------------------------------
FNO_ENTRY_START_MIN:       int   = 9*60 + 45  # 09:45 IST
FNO_ENTRY_END_MIN:         int   = 14*60 + 45 # 14:45 IST
FNO_HARD_FLAT_MIN:         int   = 15*60 + 10 # 15:10 IST
FNO_EXPIRY_DAY_ENTRIES:    bool  = False
FNO_OR_MINUTES:            int   = 30         # opening range window

# --- strategy ----------------------------------------------------------
FNO_OR_BUFFER_ATR:         float = 0.25
FNO_STOP_ATR_MULT:         float = 1.5
FNO_TARGET_R:              float = 1.5
FNO_TRAIL_ATR_MULT:        float = 1.0
FNO_TIME_STOP_MIN:         int   = 45
FNO_TIME_STOP_MIN_R:       float = 0.5
FNO_MIN_RVOL:              float = 1.2

# --- execution ---------------------------------------------------------
FNO_FILL_TIMEOUT_SEC:      int   = 30

# --- observability -----------------------------------------------------
FNO_SIGNAL_LOG_PATH:       str   = "/data/fno_signals.csv"
FNO_ZERO_ACCEPT_ALERT_DAYS: int  = 2
```

Every threshold above is a **guess** until a backtest says otherwise. They are
deliberately conservative. Per the `trading-strategy-safe-improvements` skill:
do not hand-tune these into "smart" filters without data.

---

## 13. Deferred: FNO-VOL and FNO-THETA

Recorded so the reasoning is not lost.

### FNO-VOL (P3) — the one long-only structure with a real edge

Buy volatility only when volatility is *cheap*:

- ATM IV below its 20th trailing percentile, **and**
- realized-vol / implied-vol `> 1.0` (the market is underpricing the movement
  it is actually delivering), **and**
- a known catalyst inside the holding window (policy, budget, big-4 earnings)

Long ATM straddle, **7-20 DTE — never a weekly.** The theta cliff in the final
three days is where long premium goes to die. Exit on IV expansion, on
realized move >= implied move, on DTE < 3, or a -40% premium stop.

Rare — perhaps a dozen setups a year. Blocked on two things: multi-day holds
(P1 is intraday-only by decision) and an IV percentile history we do not have.
Bootstrap options: NSE publishes historical India VIX free, or snapshot our
own daily ATM IV and wait ~6 months. Do both — bootstrap to start, log our own
in parallel so we eventually own the series. Note `regime.py` is deliberately
VIX-free, likely because the INDICES segment 403s on this Kite plan
(`kite_client.py:132`); this is the same wall, met again.

### FNO-THETA (P4) — where "consistent" actually lives

Defined-risk credit spreads and iron condors. Positive theta, bounded loss,
the profile the operator originally asked for. Requires:

- The bounded-loss mandate (already adopted, §2)
- `max_loss()` (already built, §4 — an iron condor returns `width - credit`
  and **nothing else in the system needs to change**)
- 30 clean liveness-heartbeat days, because a short leg's bound depends on
  software staying alive

---

## 14. Verification list — resolve BEFORE writing code

Do not build on any of these until checked against the live API or the
exchange. Each is load-bearing.

| # | Claim | Why it matters | How to check |
|---|---|---|---|
| **VERIFY-1** | Zerodha does not support SL-M on options | The entire penny safety model assumes SL-M exists. If absent, §8.4's engine-managed stop is forced, and §2's long-only argument becomes load-bearing rather than merely nice | Place and cancel a real SL-M on a liquid NIFTY option |
| **VERIFY-2** | NIFTY lot size is 75 | Every number in §3 scales with it. Revised in Nov 2024 and possibly since | Read `lot_size` from `/instruments/NFO` |
| **VERIFY-3** | NIFTY weekly expiry day | Changed several times in 2025. **Never hardcode** | Read `expiry` from `/instruments/NFO` |
| **VERIFY-4** | STT on exercised ITM options | The catastrophic pre-2019 version taxed full notional; reduced to intrinsic value in Sept 2019. Affects the §7.1 never-expire-ITM rule | Zerodha's current charge list |
| **VERIFY-5** | STT rate on the option sell side (on premium) | Raised in Oct 2024. Feeds §10.2 | Zerodha's current charge list |
| **VERIFY-6** | `/instruments/NFO` is accessible on this Kite plan | `kite_client.py:132` notes the INDICES segment returns 403. NFO is standard and should work, but the plan has surprised us before | `GET /instruments/NFO`, count rows |
| **VERIFY-7** | Kite `/quote` batch limit is 500 instruments | §6.2's single-call chain snapshot depends on it | Kite Connect docs + one live call with 22 tokens |

---

## 15. Open questions

1. **Futures bars for the signal.** Front-month NIFTY futures, or the spot
   index? Futures have a bid-ask and roll; spot has neither but is not
   tradeable. Recommendation: **futures**, because the forward in §6.2 already
   needs them and consistency between signal and pricing basis matters.
2. **Roll handling.** Front-month futures roll near expiry, creating a level
   discontinuity in the opening-range calculation. P1 sidesteps it (no expiry
   day entries) but P3 will not.
3. **Cold start.** The NFO dump is 60-90k rows. If it inherits the equity
   cache's ~38-minute cold-start pathology (ops rule 61), the 09:45 entry
   window is missed after any morning restart. Should `fno_instruments`
   persist to disk and re-hydrate, per rule 61's optimisation candidate (a)?
