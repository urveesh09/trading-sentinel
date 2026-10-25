"""[O25 2026-10-25] Before the real-money F&O test: is the order route ready? Run by the owner.

    docker exec -it python-engine python -m fno_live_preflight              # reads only
    docker exec -it python-engine python -m fno_live_preflight --test-order # plus one order, cancelled

Reads (any time after the day's Kite login): the order route (KITE_ORDER_BASE_URL),
own free cash in the account (no margin, no collateral) against
FNO_LIVE_TEST_CAPITAL, open F&O positions at the broker, and the day's order book.

``--test-order`` (market hours, a real order): one lot of the nearest NIFTY call
that does not expire today, at the strike nearest the future, as a BUY LIMIT 20%
under its bid. It cannot fill unless the option falls 20% in the two seconds
before it is cancelled. The order is then cancelled and read back: CANCELLED with
nothing filled proves Kite takes orders from this route (the static-IP rule).
In the very unlikely fill it is sold at once through the live exit ladder. A
refusal for a static-IP reason trips the order-authorization halt in kite_client
(no live entry anywhere until the owner clears it): that is intended.

Nothing here touches the F&O books, and no protective (SELL) order is ever sent
without a position: an SL order without one would be a short option.
"""
from __future__ import annotations

import argparse
import asyncio
import uuid
from datetime import datetime

import pytz

from config import settings

IST = pytz.timezone("Asia/Kolkata")
TEST_DISCOUNT = 0.20


def _floor_tick(value: float, tick: float) -> float:
    return round(max(tick, int(value / tick) * tick), 2)


async def run(test_order: bool) -> int:
    from kite_client import KiteClient, own_uncommitted_cash
    from token_lifecycle import _load_persisted_kite_token_if_fresh

    payload = _load_persisted_kite_token_if_fresh()
    if not payload:
        print("No Kite login for today: log in first, then run this again.")
        return 2
    kite = KiteClient(settings.DB_PATH)
    kite.set_token(payload["access_token"])
    problems = 0
    if settings.KITE_ORDER_BASE_URL:
        print(f"Order route: {settings.KITE_ORDER_BASE_URL} (KITE_ORDER_BASE_URL)")
    else:
        print(f"Order route: {settings.KITE_BASE_URL} -- KITE_ORDER_BASE_URL is not set, so orders leave from "
              "this host's own IP. Kite accepts orders only from the app's registered IPs: set it to the relay.")
        problems += 1
    margins = await kite.get_funds_margins()
    positions = await kite.get_broker_positions()
    orders = await kite.orders_snapshot()
    own = own_uncommitted_cash(margins, positions, orders)
    capital = float(settings.FNO_LIVE_TEST_CAPITAL)
    if own is None:
        print("Own free cash: could not be read (margins, positions or orders unavailable).")
        problems += 1
    else:
        print(f"Own free cash: ₹{own:,.2f} (the test needs ₹{capital:,.0f}; a lot costs about ₹6k-15k).")
        if own < capital:
            print("  Below the test capital: add cash or lower FNO_LIVE_TEST_CAPITAL.")
            problems += 1
    open_fno = [p for p in (positions or {}).get("net", []) or []
                if p.get("exchange") in ("NFO", "BFO") and p.get("quantity")]
    print(f"Open F&O positions at the broker: {len(open_fno)}" +
          ("" if not open_fno else " -- " + ", ".join(str(p.get("tradingsymbol")) for p in open_fno)))
    print(f"Today's order book: {'readable' if isinstance(orders, list) else 'NOT readable'}"
          + (f", {len(orders)} order(s)" if isinstance(orders, list) else ""))
    print(f"Test switch FNO_LIVE_TEST_ENABLED={settings.FNO_LIVE_TEST_ENABLED} capital ₹{capital:,.0f} "
          f"floor ₹{settings.FNO_LIVE_TEST_FLOOR:,.0f}")
    if not test_order:
        return 1 if problems else 0
    return await _test_order(kite) or (1 if problems else 0)


async def _test_order(kite) -> int:
    from fno_executor import FnoExecutor
    from fno_instruments import get_fno_instruments
    from fno_models import OptionType

    now = datetime.now(IST)
    if not (9 * 60 + 15 <= now.hour * 60 + now.minute < 15 * 60 + 25):
        print("The test order needs market hours (09:15-15:25 IST).")
        return 2
    book = get_fno_instruments()
    today = now.date()
    if not book.ready(today) and not book.load_from_disk():
        print("NIFTY instruments are not loaded for today: wait for the morning refresh.")
        return 2
    fut = book.front_future(today)
    expiry = next((e for e in book.option_expiries if e > today), None)
    if fut is None or expiry is None:
        print("No NIFTY future or later option expiry in today's instruments.")
        return 2
    fut_quote = (await kite.get_quote([fut.token])).get(fut.token) or {}
    forward = float(fut_quote.get("last_price") or 0)
    contract = book.option(expiry, book.atm_strike(forward), OptionType.CE) if forward > 0 else None
    if contract is None:
        print("Could not price the future or find its ATM call.")
        return 2
    quote = (await kite.get_quote([contract.token])).get(contract.token) or {}
    buys = (quote.get("depth") or {}).get("buy") or []
    bid = float(buys[0]["price"]) if buys and buys[0].get("price") else 0.0
    if bid <= 0:
        print(f"{contract.tradingsymbol} has no bid right now; try again in a minute.")
        return 2
    tick = float(contract.tick_size or settings.FNO_TICK_SIZE)
    price = _floor_tick(bid * (1.0 - TEST_DISCOUNT), tick)
    qty = int(contract.lot_size)
    tag = f"PF{uuid.uuid4().hex[:17]}"
    print(f"Test order: BUY {qty} {contract.tradingsymbol} LIMIT ₹{price:.2f} (bid ₹{bid:.2f}), MIS, tag {tag}")
    resp = await kite.place_order(variety="regular", exchange="NFO", tradingsymbol=contract.tradingsymbol,
                                  transaction_type="BUY", quantity=qty, product="MIS", order_type="LIMIT",
                                  price=price, validity="DAY", tag=tag, intent="entry", channel="fno")
    order_id = resp.get("order_id")
    if not order_id:
        print(f"REFUSED ({resp.get('dispatch_certainty')}): {resp.get('message')}")
        return 1
    await asyncio.sleep(2)
    executor = FnoExecutor(kite, paper_mode=False, source_tag="FNO_LIVE")
    latest, cancel_error = await executor.cancel_and_read(order_id)
    status, filled = latest.get("status"), latest.get("filled_quantity")
    if status in ("CANCELLED", "REJECTED") and filled == 0:
        kite.settle_entry_reservation(order_id, final_status=status, filled_quantity=0)
        if status == "CANCELLED":
            print(f"PASS: order {order_id} was accepted by Kite and cancelled with nothing filled. "
                  "Orders from this route work.")
            return 0
        print(f"REJECTED by the exchange or the broker's checks: {latest.get('status_message')}. The route "
              "reached Kite (no static-IP refusal), but read the message before enabling the test.")
        return 1
    if status == "COMPLETE":
        kite.settle_entry_reservation(order_id, final_status=status, filled_quantity=filled)
        fresh = (await kite.get_quote([contract.token])).get(contract.token) or {}
        fresh_buys = (fresh.get("depth") or {}).get("buy") or []
        sell_bid = float(fresh_buys[0]["price"]) if fresh_buys and fresh_buys[0].get("price") else price
        result = await executor.execute_exit(contract.tradingsymbol, qty, sell_bid, tick)
        print(f"The test order FILLED at ₹{latest.get('average_price')} (the option fell 20%). Sold at once: "
              f"{result['status']} {result.get('fill_price')} order {result.get('order_id')}. "
              "Check Kite that no NIFTY position is left.")
        return 1
    print(f"UNCLEAR: order {order_id} reads {status!r} filled={filled} (cancel error: {cancel_error}). "
          "Open Kite, cancel it if it is still open, and do not enable the test until it is understood.")
    return 1


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Is the real-money F&O test's order route ready?")
    parser.add_argument("--test-order", action="store_true",
                        help="also place one BUY 20%% under the bid and cancel it (market hours, real order)")
    args = parser.parse_args(argv)
    return asyncio.run(run(args.test_order))


if __name__ == "__main__":
    raise SystemExit(main())
