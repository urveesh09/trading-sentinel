# Runbook: the ₹12,500 real-money F&O test (O25, O25b)

_Written 2026-10-25, revised the same day after the audit-agent review (O25b).
Code: `python-engine/fno_live_test.py`, `fno_executor.py`, `fno_orchestrator.py`,
`fno_proving_week.py`, `fno_live_preflight.py`._

## What it is

The owner's decision (Oct 25): give the paper F&O single-leg book five
sessions to prove itself (Oct 26–30). If it does, put ₹12,500 of real money on
it for one bounded run, five sessions by default, with the sizing guardrails
relaxed, to see how the system trades with real fills. It is the pure intraday
single-leg book only: no expiry book, no spreads, no expiry-day trades.

One switch, `FNO_LIVE_TEST_ENABLED=true`, in the root `.env` that the
python-engine reads. It is off unless you set it.

The test **never decides a trade**. When the paper book buys a NIFTY option,
the test buys **one lot of the same contract** on the same signal bar. The
signal, strike, gates, reward/risk, the paper book's size tiers, loss brakes
and 15% drawdown halt decide for both. Exits use the same rules on the real
fill:

- the stop and target on NIFTY from the same signal;
- the 25% premium stop, the trail, the profit lock and the time stop;
- the 15:10 hard flat;
- a resting broker stop-loss order as a backstop.

| | Relaxed for this test only | Kept |
|---|---|---|
| Sizing | 2%-of-pool risk per trade: one lot instead; one stop-out risks about ₹1.5k–3.7k, 12–30% of ₹12,500 | own cash only: Kite refuses a buy the account's free cash cannot pay; no margin, no leverage |
| Pool gates | minimum-viable-pool and open-premium gates | the shared F&O ledger reserves the whole premium against the test's own equity |
| Go-live bar | PF ≥ 1.2, 60 trades, 40 days (`fno_go_live_check`) | NIFTY only (enforced in the buy itself), never on its expiry day, one position at a time, at most 3 entries a day |
| Run length | — | a bounded run: `FNO_LIVE_TEST_RUN` names it, `FNO_LIVE_TEST_SESSIONS` (default 5) trading sessions from its first armed day; then no new entry and you are told |
| Floor | — | no new entry while test equity (capital plus realised real P&L) is under `FNO_LIVE_TEST_FLOOR`, ₹7,000 by default |
| Orders | — | LIMIT orders only, MIS (intraday) |

**The floor stops new entries; it does not guarantee ₹7,000 remains.** A
position already open can lose its whole premium if its exits cannot execute.
A five-session result also cannot establish profitability.

**Entry.** The buy is a LIMIT at the fresh ask plus two ticks, so it trades at
the ask or better. It is skipped when:

- that ask is more than 2% above the paper price (`FNO_LIVE_TEST_MAX_CHASE_PCT`);
- the quote is stale or one-sided;
- the spread is over 1.5%.

An unfilled buy is cancelled after 30 s and never chased.

**Exit.** One SELL LIMIT just under the bid, moved lower in steps until it
fills: 0.5%, then 3%, then 10% (or ₹5) under the bid, about 30 s in all.

- **Before it is sent:** the exit's own broker tag is recorded.
- **Once Kite gives an order id:** the id is recorded, before any wait. After
  a restart the engine follows the same order. A send whose reply was lost is
  found in Kite's order book by its tag. One that never reached Kite is sent
  again.
- **Price changes:** only those Kite accepts count. A refused change is
  retried on the next pass.
- **There is never a second SELL order.** The engine also never sells more
  than the broker shows it holding as MIS on NFO: an NRML holding of the same
  contract is not the system's to sell.

## Before you switch it on (in this order)

1. **The verdict.** It arrives on Telegram on Fri Oct 30 at 15:50.
   You can also read it at any time:
   `docker exec python-engine python -m fno_proving_week`.
   The rules were fixed on Oct 25:
   - PROVED: at least one trade, no loss at one lot after one lot's own
     charges, nothing broken, and no drawdown halt;
   - NOT PROVED: otherwise;
   - NO EVIDENCE: no trade;
   - UNAVAILABLE: the halt state could not be read.

   The decision is yours.
2. **Deploy.** Merge the PR (`codex/production-correction-hedge-p0` → `evolve/smart-strategies`),
   then rebuild one service at a time: the engine, then the gateway.
3. **Cash.** At least ₹12,500 of free cash in the Zerodha account. Pledged
   holdings and margin do not count. A typical lot has cost about ₹8–9k; the
   morning check compares the two.
4. **Order route, with the switch still off.** Kite accepts orders only from
   the app's registered static IPs. Add **one** of these to the root `.env`:
   - `KITE_ORDER_PROXY_URL=http://161.118.160.180:<port>` (preferred, encrypted):
     only once the VM runs a CONNECT proxy. See "The relay" below.
   - `KITE_ORDER_BASE_URL=http://161.118.160.180:31527` (works today, plain HTTP):
     the current relay.

   Then recreate the engine, so it reads the new value:
   `docker compose up -d python-engine`.
5. **Check the route the engine now uses**, before any order:
   `docker exec python-engine python -m fno_live_preflight`
   This only reads. It must print the route you set, your free cash and no
   problem lines.
6. **Preflight test order**, after the morning login, in market hours:
   `docker exec -it python-engine python -m fno_live_preflight --test-order`
   It places **one real BUY 20% under the bid** of a NIFTY call, cancels it and
   reads it back.
   - Expect `PASS`.
   - A static-IP refusal trips the order-authorization halt. Fix the route,
     then clear the halt.
   - In the very unlikely case it fills, it is recorded as a real position.
     The engine sells it at once (`preflight_flatten`) and you are paged. Do
     not switch on until Kite shows it flat.
7. **Switch on.** Add `FNO_LIVE_TEST_ENABLED=true` to the root `.env`.
   Optionally set `FNO_LIVE_TEST_RUN=1`, `FNO_LIVE_TEST_SESSIONS=5`,
   `FNO_LIVE_TEST_CAPITAL=12500` and `FNO_LIVE_TEST_FLOOR=7000`.
   Then `docker compose up -d python-engine`, before 09:15 or after the 15:40
   close.

**Run the preflight once.** Repeat it only after something in the order path
changes: the route, the relay or its IP, the Zerodha API key or app, or a new
static IP. You don't run anything daily. While the test is on, the engine
checks every trading day by itself (next section).

## What you will see

- **09:25 each trading day (while on):** `✅ REAL-money F&O test ready today`,
  or `⚠️ NOT ready` with the reason:
  - the route;
  - no login yet;
  - free cash against a typical lot;
  - F&O positions held at the broker;
  - the run's session ("session 2 of 5") or that it has ended;
  - equity against the floor;
  - anything left from earlier.
- **Each real trade:** a `💰 REAL MONEY ENTRY [FNO_LIVE]` line with the paper
  price beside it, then a `💰 REAL MONEY EXIT` line.
- **15:50 each trading day:** each real trade beside its paper twin, with:
  - one lot each, after its own charges;
  - the decision-to-fill delay;
  - entry and exit slippage against paper;
  - how many times the exit price was moved, and how many changes were refused;
  - the state of the broker stop;
  - the paper trades not bought for real, and why;
  - anything outstanding (open positions, claimed exits, held reservations);
  - test equity.
- **Alerts:**
  - the floor was reached, or the run ended;
  - a real exit was not placed (it is retried), is still working, or is
    unclear;
  - the broker does not hold (or only partly holds) a position;
  - a backstop was not placed;
  - order authorization was blocked;
  - the preflight test buy filled.

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
  An open real position is still managed to its exit. When the run's sessions
  are used up, entries stop by themselves. A new run needs a new
  `FNO_LIVE_TEST_RUN` name.
- **Now:** sell in Kite. The engine checks the broker's MIS positions before
  any real sell, so it will not sell it again. It pages you to record the exit
  with F&O exit recovery: `POST /ops/fno-exit-intents/{id}/resolve` with the
  Kite order id of your sale (`GET /ops/fno-exit-intents` lists it).

## The relay (what is possible, and who does what)

Today every order or quote that goes through `161.118.160.180:31527` is plain
HTTP. That means the `Authorization` header (API key and the day's access
token) crosses the internet unencrypted, and the port is open to anyone. On
Oct 25 the relay answered a plain request, but refused an HTTP CONNECT tunnel
(404): it is a forwarding proxy, not a tunnelling one. The gateway already
sends all its Kite traffic this way. The engine sends only orders through it,
and only once you set the route.

| Option | Who | What it gives |
|---|---|---|
| 1. Firewall the port to this home's public IP (Oracle security list + `iptables`) | you, on the VM (~5 minutes) | nobody else can use the relay, so a captured token cannot place orders (Kite takes orders only from the registered IP). Still unencrypted. If the home IP changes, orders fail safely (refused, alerted) until you update the rule. |
| 2. A CONNECT proxy on the VM (e.g. `tinyproxy`: `Allow <home IP>`, `ConnectPort 443`, filter to `api.kite.trade`), then `KITE_ORDER_PROXY_URL=http://161.118.160.180:<port>` | you install it; the engine side is done (O25b) | orders are encrypted end to end (TLS to api.kite.trade) and still leave from the registered IP. The token is never in clear text. |
| 3. A private tunnel (WireGuard or Tailscale) between this host and the VM | you, more setup | everything to the VM is encrypted, including the gateway's traffic |

Recommended: **1 now, then 2** before the real-money run. The gateway's own
route is unchanged by this work (it still uses `KITE_BASE_URL` in
`node-gateway/.env`). Moving it to a tunnel is a separate change.

## Known limits

- One lot only. A partial fill of one lot cannot happen on NSE (lots trade whole).
- Five sessions are a small sample. Paper and real will differ by fills and
  timing; the 15:50 report shows the gap per trade.
