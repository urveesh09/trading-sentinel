# F1-A — owner rule "no extra margin": every live entry fully paid from own cash (October 3, 2026)

**Independent review limitation:** this slice checks each entry's notional
against a broker snapshot. It has no common durable account reservation across
Python and gateway, so simultaneous entries can pass against the same cash.
It does not yet establish the owner's account-wide rule. See
[F1-B acceptance plan](2026-10-03-post-implementation-independent-review.md)
for atomic commitments, charges/contingency, book budgets and catastrophe tests.
Malformed Python order-book payloads now remain unavailable rather than empty.
The audit below describes the pre-F1-A baseline; historical findings are preserved.

## Owner definition (verbatim intent, October 3)

> "The amount I invest is only what is mine and that amount — not like other
> cases where you invest 100 and it invests 100000, and if you win you win big
> but on losing you lose bigger."

Contract derived from it:
- **No leverage.** No position, and no set of open positions, may cost more
  than the owner's own cash. Broker MIS leverage, collateral margin, adhoc
  limits and borrowing never fund an entry.
- **Bounded loss.** For bought equity or bought options, the worst-case loss
  is then bounded by the cash put in, plus charges.
- **Short options.** No live short-option path exists (the read-only audit
  found none), and none may be added without a separate decision.

## Audit (read-only, verified against source)

**No current path enforces the rule.**
- No Python path checks broker funds before a live entry.
- The node-gateway `preflightEntryMargin` (`services/executor.js:50-86`)
  replaces the order notional with the broker's *order margin* (about 20%
  of notional for MIS) and compares it with `live_balance`. After an MIS buy
  only that margin is blocked, so repeated leveraged MIS buys pass.

**Momentum (MIS) and Swing (CNC) EXEC taps are the live paths today.** They
have no paper/live switch; every EXEC tap is a real order.

**Book-level over-allocation found.** These over-commit *own* cash across
books rather than borrow; they are reported for an owner decision.
- Classic Penny live: 5 × ₹500 per stock = ₹2,500, against a ₹2,000
  bankroll. The book is off by default.
- Swing sizes from the whole ₹4,500 Nifty bankroll per trade, with no sum
  across open positions.
- The Momentum pool check ignores pending (untapped) alerts.
- EDGE has no notional cap. It is hard-blocked for live.

## Slice

**Rule at both broker boundaries (BUY entries only; exits never blocked)**

> new order value ≤ own_cash − committed_long_cost − pending_buy_value − realised_loss_today

where:
- `own_cash` is the broker margins `equity.available.cash`, excluding
  collateral, adhoc margin and leverage;
- `committed_long_cost` is the sum of `quantity × average_price` over net
  positions with quantity > 0;
- `pending_buy_value` is the sum of `pending_quantity × price` over open
  BUY orders;
- `realised_loss_today` is `max(0, −equity.utilised.m2m_realised)`.

Any net short position, or any missing or invalid evidence, fails closed
(entry refused, exits unaffected).

**Node-gateway (`executor.js`).** The existing broker check
(`required ≤ live_balance`) now uses `max(order value, broker order
margin)`, and the own-cash rule is added. Error codes:
`OWN_CASH_INSUFFICIENT` and `MARGIN_EVIDENCE_UNAVAILABLE`.

**Python `KiteClient.place_order`.** For `intent="entry"` and
`transaction_type="BUY"` (live only, since paper never calls it):
- New read-only `get_margins` (`GET /user/margins`).
- The same rule, using `orders_snapshot` and `get_broker_positions`.
- A refusal returns `status=ERROR`, `dispatch_certainty=NOT_SENT` and
  `own_cash_refused=True`, so R2 releases capital correctly.

**Not changed:** book-level allocation sizing (that is an owner decision),
exit paths and paper books.

## Acceptance

- A leveraged MIS buy whose order value exceeds own cash is refused, even
  when the broker's margin check would pass.
- Committed positions, pending buys and realised losses reduce own cash.
- A short net position, an unavailable margins/orders/positions response,
  or invalid numbers fail closed with nothing sent.
- A fully covered entry passes. Exits are never consulted.
- The existing gateway and Python suites pass, with the one test that
  encoded leveraged acceptance updated.

## Rollout and rollback

- **Rollout.** Dev, then GitHub promotion. It affects live Momentum and
  Swing entries immediately, by design: a leveraged entry is refused.
- **Rollback.** Revert both guards. No data or schema is involved.

## Implementation result (Dev only; not pushed, not deployed)

### Node-gateway (`services/executor.js`, `utils/errors.js`)

- **`ownUncommittedCash(margins, positions, orders)`.** Computes own
  uncommitted cash as:

  > `available.cash` − Σ long net-position cost − Σ pending BUY value − realised loss today

  It returns `null` (fail closed) when there is a short position, or when
  cash, average price, pending price or `m2m_realised` is missing or
  invalid.
- **`preflightEntryMargin`.**
  - It now reads positions and orders too, and refuses with
    `OwnCashInsufficientError` (`OWN_CASH_INSUFFICIENT`) when the full
    order value exceeds own uncommitted cash.
  - The broker check now requires `max(order value, broker order
    margin)`. A smaller, leveraged broker margin no longer lowers the
    requirement.
- **Unit tests.**
  - The test that encoded leveraged acceptance is now the F1-A refusal
    test.
  - Two placement tests count one extra `getOrders` read (the preflight).
  - New tests cover:
    - leveraged MIS refusal;
    - committed positions, pending buys and realised loss;
    - shorts and malformed evidence;
    - positions/orders failure;
    - the broker-balance refusal kept as a separate code.

### Python (`kite_client.py`)

- **`own_uncommitted_cash`** is the same pure rule.
- **`get_funds_margins`** is a read-only `GET /user/margins`.
- **`KiteClient.place_order`.** For `intent="entry"` and BUY only, after
  both halt checks and before sending, it refuses with `status=ERROR`,
  `dispatch_certainty=NOT_SENT` and `own_cash_refused=True` in three cases:
  - the order value is unknown (no LIMIT price);
  - the evidence is missing;
  - the order value exceeds own uncommitted cash.
- **Exits** are never checked.
- **Real paths affected.** Both real Python entry paths (Penny executor
  and F&O executor) already send LIMIT orders.
- **Test fixtures.** Three test fixtures that sent a price-less entry or
  answered every request with one error now serve funds evidence and use a
  LIMIT price. Their subjects (halt scoping, dispatch certainty, 403
  permission halt) are unchanged.

### Verification

| Suite | Result |
| --- | --- |
| Gateway `npx jest tests/unit/executor.test.js` | **58 passed** |
| Full gateway suite | 458 passed, 18 failed, 4 skipped |
| Gateway baseline (F1-A stashed) | 453 passed, the same 18 failed |
| Python `tests/test_f1a_own_cash.py -W error` | **16 passed** |
| Full Python suite | **4733 passed, 4 failed, 4 skipped** in 257 s, no hang |

**Gateway failures.** The 18 failures are in the same two suites
(`db.test.js` and `backlog-reconciliation.test.js`), which fail on Windows
without F1-A as well.

**Python failures.** All 4 fail identically on the committed baseline:
- `test_dev_acceptance_harness::...ai_outage...`;
- `test_integrated_dev_demo::...all_offline_consumers`;
- `test_mark_to_market::...dr_writer_row...`;
- `test_proactive_intelligence::...historical_backfill...`.

### Owner decisions still open (book-level, own cash but over-allocated)

- **Classic Penny live caps.** 5 × ₹500 per stock against a ₹2,000
  bankroll. The book is off by default; lower `PENNY_PER_STOCK_CAP`, or
  lower the position count, before enabling it.
- **Swing sizing.** Swing sizes per trade from the whole Nifty bankroll,
  with no sum across open positions.
- **Momentum pending alerts.** The Momentum pool check ignores pending
  (untapped) alerts.
- **EDGE.** No notional cap; hard-blocked for live.

The account-level guard now prevents any of these from **borrowing**. They
can still allocate one book's own cash to another.
