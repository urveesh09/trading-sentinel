# Runbook: the ₹12,500 real-money F&O test (O25)

_Written 2026-10-25. Code: `python-engine/fno_live_test.py`, `fno_executor.py`,
`fno_orchestrator.py`, `fno_proving_week.py`, `fno_live_preflight.py`._

## What it is

The owner's decision (Oct 25): give the paper F&O single-leg book five
sessions to prove itself (Oct 26–30). If it does, put ₹12,500 of real money on
it for about a week, with the sizing guardrails relaxed, to see how the system
trades with real fills. It is the pure intraday single-leg book only: no expiry
book, no spreads, no expiry-day trades.

One switch: `FNO_LIVE_TEST_ENABLED=true` in the root `.env`, which the
python-engine reads. It is off unless you set it.

The test **never decides a trade**. When the paper book buys an option, the
test buys **one lot of the same contract** on the same signal bar. The signal,
strike, gates, reward/risk, the paper book's size tiers, loss brakes and its
15% drawdown halt decide for both. Exits use the same rules on the real fill:

- the stop and target on NIFTY from the same signal;
- the 25% premium stop, the trail, the profit lock and the time stop;
- the 15:10 hard flat;
- a resting broker stop-loss order as a backstop.

| | Relaxed for this test only | Kept |
|---|---|---|
| Sizing | 2%-of-pool risk per trade: one lot instead; one stop-out risks about ₹1.5k–3.7k, 12–30% of ₹12,500 | own cash only: Kite refuses a buy the account's free cash cannot pay; no margin, no leverage |
| Pool gates | minimum-viable-pool and open-premium gates | the shared F&O ledger reserves the whole premium against the test's own equity |
| Go-live bar | PF ≥ 1.2, 60 trades, 40 days (`fno_go_live_check`) | NIFTY only, never on its expiry day, one position at a time, at most 3 entries a day |
| Floor | — | no new entry while test equity (capital plus realised real P&L) is under `FNO_LIVE_TEST_FLOOR`, ₹7,000 by default |
| Orders | — | LIMIT orders only, MIS (intraday) |

**Entry.** The buy is a LIMIT at the fresh ask plus two ticks, so it trades at
the ask or better. It is skipped when:

- that ask is more than 2% above the paper price (`FNO_LIVE_TEST_MAX_CHASE_PCT`);
- the quote is stale or one-sided;
- the spread is over 1.5%.

An unfilled buy is cancelled after 30 s and never chased.

**Exit.** One SELL LIMIT just under the bid, moved lower in steps until it
fills: 0.5%, then 3%, then 10% (or ₹5) under the bid, about 30 s in all. One
still working after that is followed up every pass, even after a restart.
There is never a second SELL order, and never a SELL for a contract the
broker no longer holds.

## Before you switch it on

1. **The verdict.** It arrives on Telegram on Fri Oct 30 at 15:50.
   You can also read it at any time:
   `docker exec python-engine python -m fno_proving_week`.
   PROVED, NOT PROVED or NO EVIDENCE are defined in `fno_proving_week.py` and
   were fixed on Oct 25. Five sessions cannot prove an edge; the decision is yours.
2. **Deploy.** Merge the PR (`codex/production-correction-hedge-p0` → `evolve/smart-strategies`),
   then rebuild one service at a time: the engine, then the gateway.
3. **Cash.** At least ₹12,500 of free cash in the Zerodha account. Pledged
   holdings and margin do not count; the system refuses them by design.
4. **Order route.** Kite takes orders only from the app's registered static
   IPs. The engine currently sends everything straight from this host. Add
   this line to the root `.env`:
   `KITE_ORDER_BASE_URL=http://161.118.160.180:31527`
   Then only place, modify and cancel go through the relay, whose IP is
   registered. Quotes stay direct.
5. **Preflight**, after the morning login, in market hours:
   `docker exec -it python-engine python -m fno_live_preflight --test-order`
   It reads the route, your free cash and any open F&O positions. It then
   places **one real BUY 20% under the bid** of a NIFTY call (it cannot fill
   unless the option falls 20% in two seconds), cancels it and reads it back.
   - Expect `PASS`.
   - A static-IP refusal trips the order-authorization halt. Fix the route,
     then clear the halt.
6. **Switch on.** Add `FNO_LIVE_TEST_ENABLED=true` to the root `.env`.
   Optionally also set `FNO_LIVE_TEST_CAPITAL=12500` and `FNO_LIVE_TEST_FLOOR=7000`.
   Then `docker compose up -d python-engine`, before 09:15 or after the 15:40
   close.

## What you will see

- Each real trade: a `💰 REAL MONEY ENTRY [FNO_LIVE]` line with the paper
  price beside it, then a `💰 REAL MONEY EXIT` line.
- 15:50 each trading day: the real trades beside their paper twins (one lot,
  after charges) and the test's equity.
- Alerts:
  - the floor was reached;
  - a real exit was not placed (it is retried every pass), is still working,
    or is unclear;
  - the broker no longer holds a position;
  - a backstop was not placed;
  - order authorization was blocked.

## What protects an open position

1. The engine's own exits, every 10 s (fast exit) and every 90 s (tick).
2. A resting SL order at the broker, 35% under the fill (limit 10% under
   that). It is for when the engine is down: the loss can then reach about
   35–45% of the premium, ₹2.5k–5k on a typical lot, not 25%. A gap through
   the limit can leave it unfilled.
3. The 15:10 hard flat. Behind it, Zerodha squares off MIS positions itself
   in the afternoon (with its own charge).

## To stop

- **New entries:** set `FNO_LIVE_TEST_ENABLED=false` and recreate the engine.
  An open real position is still managed to its exit; switching off never
  abandons it.
- **Now:** sell in Kite. The engine checks the broker's positions before any
  real sell, so it will not sell it again. It pages you to record the exit
  with F&O exit recovery: `POST /ops/fno-exit-intents/{id}/resolve` with the
  Kite order id of your sale (`GET /ops/fno-exit-intents` lists it).

## Known limits

- One lot only. A partial fill of one lot cannot happen on NSE (lots trade whole).
- Five sessions and one week are small samples. Paper and real will differ by
  fills and timing; the 15:50 report shows the gap per trade.
- The relay is plain HTTP on an open port. Restricting port 31527 to this host's
  IP on the Oracle VM is recommended before real money (an infrastructure
  change outside this repository).
