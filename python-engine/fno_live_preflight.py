"""[O25 2026-10-25] Before the real-money F&O test: is the order route ready? Run by the owner.

    docker exec -it python-engine python -m fno_live_preflight              # reads only
    docker exec -it python-engine python -m fno_live_preflight --test-order # plus one order, cancelled

Reads (any time after the day's Kite login): the order route (KITE_ORDER_PROXY_URL or
KITE_ORDER_BASE_URL), whether it answers an authenticated read [O25c], own free cash
in the account (no margin, no collateral) against FNO_LIVE_TEST_CAPITAL, open F&O
positions at the broker, and the day's order book.

``--test-order`` (a real order): one lot of the nearest NIFTY call that does not
expire today, at the strike nearest the future, as a BUY LIMIT 20% under the
market. The order is then cancelled and read back: CANCELLED with nothing filled
proves Kite takes orders from this route (the static-IP rule covers placing,
modifying and cancelling).
  - In market hours (09:15-15:25 on a trading day) it is a regular order 20% under
    the bid. It cannot fill unless the option falls 20% in the two seconds before
    it is cancelled.
  - [O25c] After 15:45, before 09:00, and all day on a closed day (a weekend) it is
    an after-market order (AMO) 20% under the last price. Kite holds AMOs and sends
    F&O ones to the exchange only at the next open (09:15), so a cancelled AMO never
    reaches the exchange. That lets the whole checklist run on a weekend. If its
    cancel is not confirmed, cancel it in Kite before 09:11 on the next trading day.
  - Between 09:00 and 09:15 and between 15:25 and 15:45 it does not run.
[O25b] In the very unlikely fill (the order can fill before the cancel lands)
the holding is recorded as a real FNO_LIVE position and the running engine
sells it at once through its full exit path: the claim, the tagged order, the
price steps, the follow-up after a restart and the check that the broker still
holds it. The owner is paged. This tool never sells by itself: an unfilled sell
here would have had no one to follow it once the tool exited. A refusal for a
static-IP reason trips the order-authorization halt in kite_client (no live
entry anywhere until the owner clears it): that is intended.

Run it once before the first switch-on, and again only after the order route,
the relay, its IP, the API key or the account changes (a new key, a new
static IP). The engine checks the rest every day by itself.

Nothing here touches the F&O books, and no protective (SELL) order is ever sent
without a position: an SL order without one would be a short option.
"""
from __future__ import annotations

import argparse
import asyncio
import math
import os
import tempfile
import uuid
from datetime import date, datetime
from typing import Optional

import pytz

from config import settings

IST = pytz.timezone("Asia/Kolkata")
TEST_DISCOUNT = 0.20
REGULAR_HOURS = (9 * 60 + 15, 15 * 60 + 25)    # a regular test order
AMO_FROM, AMO_UNTIL = 15 * 60 + 45, 9 * 60      # Zerodha takes F&O AMOs 15:45-09:11; 09:00 keeps clear of the open


def variety_for(now: datetime, trading_day: bool) -> Optional[str]:
    """[O25c] "regular" in market hours; "amo" in the evening, at night, before 09:00 and on a closed
    day; None in the minutes around the open and the close."""
    minute = now.hour * 60 + now.minute
    if trading_day and REGULAR_HOURS[0] <= minute < REGULAR_HOURS[1]:
        return "regular"
    if not trading_day or minute >= AMO_FROM or minute < AMO_UNTIL:
        return "amo"
    return None


def order_route() -> tuple[str, bool, str]:
    """(description, encrypted end to end, problem or "") of where orders go."""
    from kite_client import redact_url_credentials
    proxy = redact_url_credentials((settings.KITE_ORDER_PROXY_URL or "").strip())
    base = (settings.KITE_ORDER_BASE_URL or "").strip()
    if proxy and base:
        return f"{base} through {proxy}", base.startswith("https://"), "Set KITE_ORDER_PROXY_URL or "             "KITE_ORDER_BASE_URL, not both."
    if proxy:
        return f"https://api.kite.trade through the CONNECT proxy {proxy} (TLS end to end)", True, ""
    if base:
        return f"{base} (KITE_ORDER_BASE_URL)", base.startswith("https://"), ""
    return (f"{settings.KITE_BASE_URL} (neither KITE_ORDER_PROXY_URL nor KITE_ORDER_BASE_URL is set)", True,
            "Orders would leave from this host's own IP; Kite accepts orders only from the app's registered "
            "IPs. Set KITE_ORDER_PROXY_URL (preferred) or KITE_ORDER_BASE_URL.")


def _floor_tick(value: float, tick: float) -> float:
    return round(max(tick, int(value / tick) * tick), 2)


def _ceil_tick(value: float, tick: float) -> float:
    return round(max(tick, math.ceil(round(value / tick, 6)) * tick), 2)


async def _instrument_book(kite, today: date):
    """Today's NIFTY book: the engine's (refreshed at 08:00 on trading days), else one fetched now into a
    temporary file, so a weekend or early run never overwrites the engine's own snapshot."""
    from fno_instruments import FnoInstruments, get_fno_instruments
    book = get_fno_instruments()
    if book.ready(today) or book.load_from_disk():
        return book
    private = FnoInstruments(json_path=os.path.join(tempfile.gettempdir(), "fno_live_preflight_instruments.json"))
    return private if await private.refresh(kite) else None


async def run(test_order: bool) -> int:
    from kite_client import KiteClient, own_uncommitted_cash
    from token_lifecycle import _load_persisted_kite_token_if_fresh

    payload = _load_persisted_kite_token_if_fresh()
    if not payload:
        print("No Kite login for today: log in first, then run this again.")
        return 2
    kite = KiteClient(settings.DB_PATH)
    kite.set_token(payload["access_token"])
    route, encrypted, problem = order_route()
    print(f"Order route: {route}")
    problems = 1 if problem else 0
    if problem:
        print(f"  {problem}")
    elif not encrypted:
        print("  Note: plain HTTP to the relay carries the access token unencrypted (docs/runbooks/fno-live-test.md).")
    probe = getattr(type(kite), "probe_order_route", None)
    if callable(probe):
        unreachable = await probe(kite)
        if unreachable:
            print(f"Order route answers: NO ({unreachable}). Check the tunnel (sudo python3 kite_tunnel.py status on "
                  "the VM), its password in the .env, and the Oracle security-list rule.")
            problems += 1
        else:
            print("Order route answers: yes (an authenticated read; only an accepted order proves the static IP).")
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
    from fno_models import OptionType
    from market_calendar import is_trading_day_sync

    now = datetime.now(IST)
    variety = variety_for(now, is_trading_day_sync(now.date(), settings.DB_PATH))
    if variety is None:
        print("The test order runs in market hours (09:15-15:25 on a trading day) or as an after-market order "
              "(after 15:45, before 09:00, or on a closed day). Try again then.")
        return 2
    today = now.date()
    book = await _instrument_book(kite, today)
    if book is None:
        print("NIFTY instruments could not be loaded from Kite: try again in a few minutes.")
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
    tick = float(contract.tick_size or settings.FNO_TICK_SIZE)
    if variety == "regular":
        buys = (quote.get("depth") or {}).get("buy") or []
        reference = float(buys[0]["price"]) if buys and buys[0].get("price") else 0.0
        if reference <= 0:
            print(f"{contract.tradingsymbol} has no bid right now; try again in a minute.")
            return 2
        price = _floor_tick(reference * (1.0 - TEST_DISCOUNT), tick)
        basis = f"bid ₹{reference:.2f}"
    else:
        try:
            reference = float(quote.get("last_price") or 0)
            lower = float(quote.get("lower_circuit_limit") or 0)
        except (TypeError, ValueError):
            reference = lower = 0.0
        if reference <= 0:
            print(f"{contract.tradingsymbol} has no last price to work from; try again later.")
            return 2
        # Kite refuses an AMO priced outside the day's band: never under the lower circuit.
        price = max(_floor_tick(reference * (1.0 - TEST_DISCOUNT), tick), _ceil_tick(lower, tick) if lower > 0 else 0)
        basis = f"last price ₹{reference:.2f}; an after-market order, held by Kite until 09:15"
    qty = int(contract.lot_size)
    tag = f"PF{uuid.uuid4().hex[:17]}"
    print(f"Test order: BUY {qty} {contract.tradingsymbol} LIMIT ₹{price:.2f} ({basis}), MIS, tag {tag}")
    resp = await kite.place_order(variety=variety, exchange="NFO", tradingsymbol=contract.tradingsymbol,
                                  transaction_type="BUY", quantity=qty, product="MIS", order_type="LIMIT",
                                  price=price, validity="DAY", tag=tag, intent="entry", channel="fno")
    order_id = resp.get("order_id")
    if not order_id:
        print(f"REFUSED ({resp.get('dispatch_certainty')}): {resp.get('message')}")
        return 1
    await asyncio.sleep(2)
    executor = FnoExecutor(kite, paper_mode=False, source_tag="FNO_LIVE")
    latest, cancel_error = await executor.cancel_and_read(order_id, variety)
    status, filled = latest.get("status"), latest.get("filled_quantity")
    if status == "CANCELLED AMO":
        status = "CANCELLED"
    if status in ("CANCELLED", "REJECTED") and filled == 0:
        kite.settle_entry_reservation(order_id, final_status=status, filled_quantity=0)
        if status == "CANCELLED":
            print(f"PASS: order {order_id} was accepted by Kite and cancelled with nothing filled"
                  + (" (an after-market order: it never reached the exchange)" if variety == "amo" else "")
                  + ". Orders from this route work.")
            return 0
        print(f"REJECTED by the exchange or the broker's checks: {latest.get('status_message')}. The route "
              "reached Kite (no static-IP refusal), but read the message before enabling the test.")
        return 1
    if type(filled) is int and filled > 0:
        # Filled (wholly, or before the cancel landed): the engine sells it.
        import fno_live_test
        kite.settle_entry_reservation(order_id, final_status="COMPLETE", filled_quantity=filled)
        try:
            average = float(latest.get("average_price") or price)
        except (TypeError, ValueError):
            average = price
        position_id = await fno_live_test.hand_off_preflight_fill(
            settings.DB_PATH, contract=contract, qty=filled, fill=average, order_id=order_id, forward=forward,
            now=datetime.now(IST))
        print(f"The test order FILLED: {filled} at ₹{average:.2f} (the option fell 20%). It is recorded as real "
              f"position {position_id} and the engine sells it within seconds (you were paged). Check Kite in a "
              "few minutes that no NIFTY position is left; do not enable the test until it is flat.")
        return 1
    print(f"UNCLEAR: order {order_id} reads {status!r} filled={filled} (cancel error: {cancel_error}). "
          "Open Kite, cancel it if it is still open"
          + (" (an after-market order goes to the exchange at 09:15: cancel it before 09:11)" if variety == "amo"
             else "")
          + ", and do not enable the test until it is understood.")
    return 1


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Is the real-money F&O test's order route ready?")
    parser.add_argument("--test-order", action="store_true",
                        help="also place one BUY 20%% under the market and cancel it (a real order; outside market "
                             "hours an after-market order)")
    args = parser.parse_args(argv)
    return asyncio.run(run(args.test_order))


if __name__ == "__main__":
    raise SystemExit(main())
