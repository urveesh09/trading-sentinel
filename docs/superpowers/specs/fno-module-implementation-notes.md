# F&O Module — Implementation Notes (P0+P1)

_Status: IMPLEMENTED on `feat/fno-module`, 2026-07-10_
_Companion to `fno-module.md` (the spec). This file records what was
built, where the implementation deviates from the spec draft and why,
and the answers adopted for the spec's open questions._

---

## What shipped

All P0 + P1 scope in one branch, paper-only. Live leg structurally
disarmed four ways: `FNO_DISABLE_LIVE=True`, `FNO_LIVE_TRADING=False`,
`FNO_LIVE_BANKROLL=0`, and `fno_go_live_check()` must return `[]`.

| Module | Spec § | Notes |
|---|---|---|
| `options_math.py` | 6.3 | Black-76 + hand-rolled Brent (stdlib-pure; purity CI-enforced) |
| `fno_models.py` | 5 | Leg / Contract / ContractQuote / OptionType / FnoSource |
| `fno_risk.py` | 3, 4, 7.6, 11 | `max_loss()`, `min_viable_pool()`, `lots_for_pool()`, kill switches, `fno_go_live_check()`. **100% branch coverage** (whole module, not just `max_loss`) |
| `fno_costs.py` | 10.2 | Fresh cost model, post-Oct-2024 rates, **no bypass flag** (test-enforced) |
| `fno_instruments.py` | 6.1 | Own keyed structure; never touches the equity cache; persists to disk + same-day rehydrate |
| `fno_chain.py` | 6.2 | One batched /quote; futures LTP as forward + parity cross-check that logs on >0.5% drift |
| `fno_engine_mom.py` | 8 | Signal on futures 5-min bars only; time-of-day-adjusted RVOL from day one |
| `fno_gates.py` | 7, 9.1 | *(new module)* every gate is an object shipping `witness_input()`; CI parametrizes over `ALL_ENTRY_GATES` |
| `fno_positions.py` | — | *(new module)* own positions table (options don't fit the equity schema); IST dates so kill-switch windows can't drift vs the session |
| `fno_signal_log.py` | 9.2 | CSV + SQLite, stable schema, best-effort writes |
| `fno_executor.py` | 10.1 | LIMIT-only; paper fills at real ask/bid (paper pays the spread deliberately) |
| `fno_orchestrator.py` | 10.4 | Dual-leg tick; exits before entries; one entry per signal bar per leg, restart-safe via `bar_ts` |
| `fno_hourly_report.py` | 1, 9.2 | Distinguishes healthy-zero (self-regulation) from suspicious-zero in prose |
| `fno_accept_watchdog.py` | 9.2 | Zero-accept alarm with the self-regulation vs dead-gate classification |
| `performance.fno_bankroll()` | 10.3 | Additive source tags; pool isolation test-enforced |
| `main.py` | 9.3 | `register_fno_scheduler_jobs()`: 08:05 instruments refresh (+catchup), 60s tick, hourly report, 15:45 watchdog. Breadcrumb layers per ops rules 55/56 |

Tests: 195 assertions across 10 files, including per-gate falsifiability,
the §4 truth table, IV round-trips, and a paper end-to-end (entry at ask
→ hard flat at bid → costs → ledger row).

---

## Deviations from the spec draft

### 1. `FNO_MAX_LOSS_PER_TRADE` split into two caps (spec bug)

§12 set `FNO_MAX_LOSS_PER_TRADE = 2500` and §4 enforced it against
structural `max_loss()`. For a long option, structural max loss is the
FULL premium (~Rs 7,500/lot at Rs 100) — so as drafted, **every trade
the pool can afford is rejected**: a mathematically unsatisfiable order
path, i.e. exactly the BUG-1 dead-gate class §9.1 exists to catch. The
witness discipline caught it at design time.

Resolution:
- `FNO_MAX_LOSS_PER_TRADE = 2500` now caps **stop-based risk**
  (`premium × qty × stop_pct`), consistent with §3's `risk_per_lot`
  arithmetic. Enforced in `lots_for_pool()`.
- `FNO_MAX_STRUCTURAL_LOSS_PER_TRADE = 12000` (new) caps `max_loss()`
  — it bounds the frozen-engine catastrophe case (whole premium lost),
  not the working risk. Enforced in `validate_position()`.
- Regression test: `test_order_path_is_satisfiable_end_to_end` goes red
  if anyone "restores the spec".

### 2. Two module additions to the §5 layout

- `fno_gates.py` — gates as witness-carrying objects, so the §9.1 test
  is a parametrize over `ALL_ENTRY_GATES` instead of hand-written cases.
- `fno_positions.py` — dedicated `fno_positions` table. Options carry
  premium+underlying stop state that the equity `positions` schema can't
  hold without abuse. Ledger rows still flow to the shared
  `bankroll_ledger` with `FNO_PAPER`/`FNO_LIVE` tags (§10.3 unchanged).

### 3. Cost figures updated (VERIFY-4 / VERIFY-5 resolved)

STT on sell-side premium is 0.1% since 2024-10-01 (spec table said
VERIFY). Honest round trip on 1 lot @ Rs 100 is **~Rs 61 (~0.8%)**, not
the spec's ~Rs 55/0.7%. Exercised-ITM STT (0.125% of intrinsic,
post-2019) is encoded in a comment; moot in P1 (intraday only).

### 4. Liveness go-live condition is an attested flag

Condition 4 of §11 (no heartbeat gap >5 min in 30 days) lives in docker
logs, not the DB. Until tooling exists, `FNO_LIVENESS_30D_CLEAN=false`
is a config attestation the operator flips only after running the ops
rule 62 grep. Unmet by construction until then — fails safe.

---

## Open questions (spec §15) — answers adopted

1. **Futures vs spot for the signal: futures.** The forward already
   needs them; the tick fetches one instrument's bars, and signal basis
   == pricing basis.
2. **Roll handling: deferred to P3** as the spec allows. The engine's
   opening range uses today-only bars, so the roll discontinuity only
   touches the multi-day EMA/RVOL frame for ~1 session near expiry —
   and P1 takes no expiry-day entries.
3. **Cold start: yes, persist to disk.** `fno_instruments` writes the
   filtered NIFTY book (a few thousand rows, not the 60-90k dump) to
   `FNO_INSTRUMENTS_JSON_PATH` and rehydrates if the snapshot is from
   today (IST). A morning restart no longer risks the 09:45 window.

## VERIFY items status

| # | Status |
|---|---|
| VERIFY-1 (no SL-M on options) | Design assumes TRUE (Zerodha blocked SL-M for options in Sept 2021; never re-enabled). Empirical close-out is go-live condition 5 — a real order placed and cancelled. |
| VERIFY-2 (lot size) | Read from the dump every morning; modal value across option rows. Never hardcoded. |
| VERIFY-3 (expiry day) | Read from the dump. Never hardcoded. |
| VERIFY-4 (STT on exercise) | Resolved: 0.125% of intrinsic. Moot in P1. |
| VERIFY-5 (STT sell side) | Resolved: 0.1% of premium since Oct 2024. In config. |
| VERIFY-6 (NFO on this plan) | Runtime check: `get_instruments_dump` logs a loud FIX line on 403. Confirm on first prod morning. |
| VERIFY-7 (quote batch 500) | Snapshot uses 23 tokens; nowhere near the limit. |

## First-week operator checklist

1. Deploy the branch; log in via Telegram before 08:05 IST.
2. Day 1: confirm `fno_instruments_refreshed ... lot_size=75` (or
   whatever the dump says) in the logs — VERIFY-6 closes here.
3. Watch the hourly briefs. **Zero-trade days that report
   `pool_below_min_viable` are correct behaviour**, not silence —
   NIFTY weeklies above ~Rs 107 premium make Rs 1,00,000 decline by
   arithmetic.
4. After 2 weeks: read `/data/fno_signals.csv` (ops rule 75 — the CSV
   is the ground truth), check accepts > 0 on at least some days, and
   check fill honesty once live quotes flow.
