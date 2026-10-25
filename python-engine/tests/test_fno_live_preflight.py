"""[O25] The owner-run preflight before the real-money F&O test (broker double only)."""
from datetime import datetime
from types import SimpleNamespace

import pytest
import pytz

import fno_instruments as fi
import fno_live_preflight as preflight
import kite_client

REAL_KITE_CLIENT = kite_client.KiteClient
import token_lifecycle
from config import settings
from tests.test_fno_orchestrator import FUT_TOKEN, _build_book

IST = pytz.timezone("Asia/Kolkata")


class Account:
    """The broker as the preflight sees it: one account, one order book."""

    instances = []

    def __init__(self, db_path):
        self.placed, self.settled, self.state, self.cancels = [], [], {}, []
        self.refuse = self.route_down = None
        self.cancelled_status = "CANCELLED"
        Account.instances.append(self)

    async def probe_order_route(self):
        return self.route_down

    async def get_instruments_dump(self, segment):
        """Kite's NFO dump as the test book holds it (the engine's own book is not today's at a weekend)."""
        rows = ["instrument_token,tradingsymbol,name,expiry,strike,tick_size,lot_size,instrument_type,exchange"]
        for c in fi._instruments.by_key.values():
            rows.append(f"{c.token},{c.tradingsymbol},NIFTY,{c.expiry.isoformat()},{c.strike},0.05,{c.lot_size},"
                        f"{c.instrument_type},NFO")
        return "\n".join(rows)

    def set_token(self, token):
        self.token = token

    async def get_funds_margins(self):
        return {"equity": {"enabled": True, "available": {"cash": 15000.0}, "utilised": {"m2m_realised": 0.0}}}

    async def get_broker_positions(self):
        return {"net": []}

    async def orders_snapshot(self):
        return []

    async def get_quote(self, tokens):
        book = fi._instruments
        call = book.option(book.option_expiries[0], 25100.0, preflight_ce())
        return {FUT_TOKEN: {"last_price": 25100.0},
                call.token: {"last_price": 104.0, "lower_circuit_limit": 0.05, "depth": {"buy": [{"price": 100.0}]}}}

    async def place_order(self, **kw):
        self.placed.append(kw)
        if self.refuse:
            return {"order_id": None, "dispatch_certainty": "BROKER_REJECTED", "message": self.refuse}
        self.state["P1"] = {"status": "OPEN", "filled_quantity": 0}
        return {"order_id": "P1", "dispatch_certainty": "ACCEPTED"}

    async def cancel_order(self, order_id, variety="regular"):
        self.cancels.append((order_id, variety))
        self.state[order_id] = {"status": self.cancelled_status, "filled_quantity": 0}
        return {"status": "CANCELLED"}

    async def order_history(self, order_id):
        return [dict(self.state[order_id], order_timestamp="2026-07-10 10:00:00")]

    def settle_entry_reservation(self, order_id, *, final_status, filled_quantity):
        self.settled.append((order_id, final_status, filled_quantity))
        return True


def preflight_ce():
    from fno_models import OptionType
    return OptionType.CE


@pytest.fixture
def account(monkeypatch):
    Account.instances.clear()
    book = _build_book()
    monkeypatch.setattr(fi, "_instruments", book)
    monkeypatch.setattr(kite_client, "KiteClient", Account)
    monkeypatch.setattr(token_lifecycle, "_load_persisted_kite_token_if_fresh", lambda: {"access_token": "T"})
    monkeypatch.setattr(preflight, "datetime", SimpleNamespace(now=lambda tz: IST.localize(datetime(2026, 7, 10, 10, 0))))

    async def no_wait(_seconds):
        return None

    monkeypatch.setattr(preflight.asyncio, "sleep", no_wait)
    monkeypatch.setattr(settings, "FNO_LIVE_TEST_CAPITAL", 12500.0)
    return book


@pytest.mark.asyncio
async def test_the_reads_name_the_order_route_and_the_cash(account, monkeypatch, capsys):
    monkeypatch.setattr(settings, "KITE_ORDER_BASE_URL", "")
    monkeypatch.setattr(settings, "KITE_ORDER_PROXY_URL", "")
    assert await preflight.run(test_order=False) == 1                    # no order route set: a problem
    out = capsys.readouterr().out
    assert "neither KITE_ORDER_PROXY_URL nor KITE_ORDER_BASE_URL is set" in out and "Own free cash: ₹15,000.00" in out
    monkeypatch.setattr(settings, "KITE_ORDER_BASE_URL", "http://relay.test:31527")
    assert await preflight.run(test_order=False) == 0
    assert "carries the access token unencrypted" in capsys.readouterr().out
    assert Account.instances[-1].placed == []                           # reads only
    monkeypatch.setattr(settings, "KITE_ORDER_BASE_URL", "")
    monkeypatch.setattr(settings, "KITE_ORDER_PROXY_URL", "http://relay.test:8888")
    assert await preflight.run(test_order=False) == 0
    assert "through the CONNECT proxy http://relay.test:8888 (TLS end to end)" in capsys.readouterr().out
    monkeypatch.setattr(settings, "KITE_ORDER_BASE_URL", "http://relay.test:31527")
    assert await preflight.run(test_order=False) == 1                    # both set: ambiguous


@pytest.mark.asyncio
async def test_the_reads_check_the_route_answers_and_never_show_its_password(account, monkeypatch, capsys):
    """[O25c] The route's setting is not enough: it must answer, and the tunnel password is never printed."""
    monkeypatch.setattr(settings, "KITE_ORDER_BASE_URL", "")
    monkeypatch.setattr(settings, "KITE_ORDER_PROXY_URL", "http://kite:s3cret0123456789abcdef@161.118.160.180:31528")
    assert await preflight.run(test_order=False) == 0
    out = capsys.readouterr().out
    assert "through the CONNECT proxy http://kite:***@161.118.160.180:31528 (TLS end to end)" in out
    assert "Order route answers: yes" in out and "s3cret" not in out
    original = Account.__init__

    def tunnel_down(self, db_path):
        original(self, db_path)
        self.route_down = "ProxyError: 407 Proxy Authentication Required"

    monkeypatch.setattr(Account, "__init__", tunnel_down)
    assert await preflight.run(test_order=False) == 1
    assert "Order route answers: NO (ProxyError: 407 Proxy Authentication Required)" in capsys.readouterr().out


def test_regular_in_market_hours_after_market_outside_them_and_never_around_the_bells():
    at = lambda h, m, day=10: IST.localize(datetime(2026, 7, day, h, m))
    assert preflight.variety_for(at(9, 15), True) == "regular" and preflight.variety_for(at(15, 24), True) == "regular"
    assert preflight.variety_for(at(15, 45), True) == "amo" and preflight.variety_for(at(8, 59), True) == "amo"
    assert preflight.variety_for(at(9, 0), True) is None and preflight.variety_for(at(9, 14), True) is None
    assert preflight.variety_for(at(15, 25), True) is None and preflight.variety_for(at(15, 44), True) is None
    assert preflight.variety_for(at(11, 0, day=11), False) == "amo"            # Saturday: all day


def test_the_proxy_route_tunnels_orders_to_kite_over_tls(tmp_path, monkeypatch):
    RealClient = REAL_KITE_CLIENT
    monkeypatch.setattr(settings, "KITE_BASE_URL", "https://api.kite.trade")
    monkeypatch.setattr(settings, "KITE_ORDER_BASE_URL", "")
    monkeypatch.setattr(settings, "KITE_ORDER_PROXY_URL", "http://relay.test:8888")
    client = RealClient(str(tmp_path / "proxy.db"))
    client.set_token("TOKEN")
    assert str(client.order_client.base_url) == "https://api.kite.trade"
    assert client.order_client._mounts and client.order_client.headers["Authorization"].endswith(":TOKEN")


@pytest.mark.asyncio
async def test_the_test_order_is_far_under_the_market_and_cancelled(account, monkeypatch, capsys):
    monkeypatch.setattr(settings, "KITE_ORDER_BASE_URL", "http://relay.test:31527")
    assert await preflight.run(test_order=True) == 0
    broker = Account.instances[-1]
    [order] = broker.placed
    assert (order["transaction_type"], order["order_type"], order["product"], order["exchange"]) == \
        ("BUY", "LIMIT", "MIS", "NFO")
    assert order["price"] == 80.0 and order["quantity"] == 75 and order["intent"] == "entry"
    assert order["tradingsymbol"].endswith("25100CE") and order["channel"] == "fno"
    assert broker.settled == [("P1", "CANCELLED", 0)]                    # its cash hold is freed
    assert "PASS: order P1 was accepted by Kite and cancelled with nothing filled" in capsys.readouterr().out


@pytest.mark.asyncio
async def test_a_refused_test_order_fails_the_preflight(account, monkeypatch, capsys):
    monkeypatch.setattr(settings, "KITE_ORDER_BASE_URL", "http://relay.test:31527")
    original = Account.__init__

    def refusing(self, db_path):
        original(self, db_path)
        self.refuse = "IP not allowed"

    monkeypatch.setattr(Account, "__init__", refusing)
    assert await preflight.run(test_order=True) == 1
    assert "REFUSED (BROKER_REJECTED): IP not allowed" in capsys.readouterr().out


@pytest.mark.asyncio
async def test_a_filled_test_buy_is_handed_to_the_engine_which_sells_it(account, monkeypatch, tmp_path, capsys):
    """[O25b] The tool never sells by itself: the fill becomes a real position the engine exits at once."""
    import sqlite3
    from contextlib import closing

    import fno_live_test
    import fno_orchestrator
    import fno_positions as fpos
    from tests.test_fno_live_test import Broker, _live, _no_page

    db = str(tmp_path / "engine.db")
    monkeypatch.setattr(settings, "DB_PATH", db)
    monkeypatch.setattr(settings, "KITE_ORDER_BASE_URL", "http://relay.test:31527")
    pages = []

    async def page(text, event):
        pages.append(event)

    monkeypatch.setattr(fno_live_test, "_page", page)

    async def filled_before_the_cancel(self, order_id, variety="regular"):
        self.state[order_id] = {"status": "COMPLETE", "filled_quantity": 75, "average_price": 80.0}
        return {"status": "ERROR", "message": "order already complete"}

    monkeypatch.setattr(Account, "cancel_order", filled_before_the_cancel)
    assert await preflight.run(test_order=True) == 1
    broker_side = Account.instances[-1]
    assert [o["transaction_type"] for o in broker_side.placed] == ["BUY"]          # no SELL from the tool
    assert broker_side.settled == [("P1", "COMPLETE", 75)] and pages == ["fno_live_preflight_filled"]
    assert "recorded as real position" in capsys.readouterr().out
    [held] = await fpos.open_positions(db, "FNO_LIVE")
    assert held.bar_ts == "PREFLIGHT-P1" and held.entry_order_id == "P1" and held.qty == 75

    monkeypatch.setattr(fno_orchestrator, "_page_live_exit_once", _no_page)
    engine_broker = Broker(fill_after_modifies=0)
    engine_broker.get_quote = lambda tokens: _quote(held.token)
    mid_morning = IST.localize(datetime(2026, 7, 10, 10, 1))
    closed = await fno_orchestrator._manage_open_positions(engine_broker, db, "FNO_LIVE", _live(engine_broker),
                                                           mid_morning, 25100.0)
    assert len(closed) == 1 and closed[0]["reason"] == "preflight_flatten"
    assert engine_broker.placed[0]["transaction_type"] == "SELL" and engine_broker.placed[0]["quantity"] == 75


async def _quote(token):
    return {token: {"last_price": 82.0, "depth": {"buy": [{"price": 82.0}], "sell": [{"price": 82.5}]}}}


@pytest.fixture
def saturday(account, monkeypatch, tmp_path):
    """[O25c] A weekend: the engine's book is Friday's, so the preflight fetches its own (never the engine's file)."""
    monkeypatch.setattr(preflight, "datetime", SimpleNamespace(now=lambda tz: IST.localize(datetime(2026, 7, 11, 11, 0))))
    monkeypatch.setattr(settings, "FNO_INSTRUMENTS_JSON_PATH", str(tmp_path / "engine-instruments.json"))
    monkeypatch.setattr(preflight.tempfile, "gettempdir", lambda: str(tmp_path))
    monkeypatch.setattr(settings, "KITE_ORDER_BASE_URL", "http://relay.test:31527")
    return account


@pytest.mark.asyncio
async def test_a_weekend_test_order_is_an_after_market_order_cancelled_before_it_reaches_the_exchange(
        saturday, tmp_path, capsys):
    import os

    assert await preflight.run(test_order=True) == 0
    broker = Account.instances[-1]
    [order] = broker.placed
    assert order["variety"] == "amo" and order["transaction_type"] == "BUY" and order["product"] == "MIS"
    assert order["price"] == 83.2                                         # 20% under the ₹104 last price
    assert broker.cancels == [("P1", "amo")]                               # DELETE /orders/amo/P1
    assert broker.settled == [("P1", "CANCELLED", 0)]
    out = capsys.readouterr().out
    assert "an after-market order, held by Kite until 09:15" in out
    assert "PASS: order P1 was accepted by Kite and cancelled with nothing filled (an after-market order: it never " \
           "reached the exchange)" in out
    assert not os.path.exists(settings.FNO_INSTRUMENTS_JSON_PATH)         # the engine's snapshot is untouched
    assert os.path.exists(tmp_path / "fno_live_preflight_instruments.json")


@pytest.mark.asyncio
async def test_a_cancelled_amo_reads_as_cancelled_and_an_unconfirmed_one_must_be_cancelled_before_09_11(
        saturday, monkeypatch, capsys):
    original = Account.__init__

    def kite_says(status):
        def init(self, db_path):
            original(self, db_path)
            self.cancelled_status = status
        return init

    monkeypatch.setattr(Account, "__init__", kite_says("CANCELLED AMO"))
    assert await preflight.run(test_order=True) == 0
    assert Account.instances[-1].settled == [("P1", "CANCELLED", 0)]
    capsys.readouterr()
    monkeypatch.setattr(Account, "__init__", kite_says("AMO REQ RECEIVED"))
    assert await preflight.run(test_order=True) == 1
    out = capsys.readouterr().out
    assert "UNCLEAR: order P1 reads 'AMO REQ RECEIVED'" in out and "cancel it before 09:11" in out
    assert Account.instances[-1].settled == []                             # its cash hold stays until it is known


@pytest.mark.asyncio
async def test_an_after_market_price_never_goes_under_the_days_lower_circuit(saturday, monkeypatch):
    async def banded(self, tokens):
        book = fi._instruments
        call = book.option(book.option_expiries[0], 25100.0, preflight_ce())
        return {FUT_TOKEN: {"last_price": 25100.0}, call.token: {"last_price": 104.0, "lower_circuit_limit": 90.03}}

    monkeypatch.setattr(Account, "get_quote", banded)
    assert await preflight.run(test_order=True) == 0
    assert Account.instances[-1].placed[0]["price"] == 90.05              # the band's floor, on the tick grid


@pytest.mark.asyncio
async def test_no_test_order_in_the_minutes_around_the_open(account, monkeypatch, capsys):
    monkeypatch.setattr(preflight, "datetime", SimpleNamespace(now=lambda tz: IST.localize(datetime(2026, 7, 10, 9, 5))))
    monkeypatch.setattr(settings, "KITE_ORDER_BASE_URL", "http://relay.test:31527")
    assert await preflight.run(test_order=True) == 2
    assert Account.instances[-1].placed == [] and "Try again then" in capsys.readouterr().out


@pytest.mark.asyncio
async def test_the_order_route_probe_reads_through_the_order_client_and_hides_a_proxy_password(tmp_path, monkeypatch):
    import httpx

    monkeypatch.setattr(settings, "KITE_ORDER_BASE_URL", "")
    monkeypatch.setattr(settings, "KITE_ORDER_PROXY_URL", "http://kite:s3cret0123456789abcdef@relay.test:31528")
    client = REAL_KITE_CLIENT(str(tmp_path / "probe.db"))
    seen = []

    def kite(request):
        seen.append((request.method, request.url.path, request.headers.get("authorization")))
        if request.headers.get("authorization", "").endswith(":TOKEN"):
            return httpx.Response(200, json={"status": "success", "data": {"user_id": "AB1234"}})
        return httpx.Response(403, json={"status": "error", "message": "Incorrect `api_key` or `access_token`."})

    client.order_client = httpx.AsyncClient(base_url="https://api.kite.trade", transport=httpx.MockTransport(kite))
    client.set_token("TOKEN")
    assert await client.probe_order_route() is None
    assert seen[-1][:2] == ("GET", "/user/profile")
    client.set_token("STALE")
    assert await client.probe_order_route() == "HTTP 403: Incorrect `api_key` or `access_token`."

    def broken(request):
        raise httpx.ProxyError("cannot reach http://kite:s3cret0123456789abcdef@relay.test:31528")

    client.order_client = httpx.AsyncClient(base_url="https://api.kite.trade", transport=httpx.MockTransport(broken))
    reason = await client.probe_order_route()
    assert reason.startswith("ProxyError: cannot reach http://kite:***@relay.test:31528") and "s3cret" not in reason
    assert kite_client.redact_url_credentials("http://u:p@h:1 and https://a:b@c") == "http://u:***@h:1 and https://a:***@c"
