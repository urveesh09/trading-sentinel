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
        self.placed, self.settled, self.state = [], [], {}
        self.refuse = None
        Account.instances.append(self)

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
        return {FUT_TOKEN: {"last_price": 25100.0}, call.token: {"depth": {"buy": [{"price": 100.0}]}}}

    async def place_order(self, **kw):
        self.placed.append(kw)
        if self.refuse:
            return {"order_id": None, "dispatch_certainty": "BROKER_REJECTED", "message": self.refuse}
        self.state["P1"] = {"status": "OPEN", "filled_quantity": 0}
        return {"order_id": "P1", "dispatch_certainty": "ACCEPTED"}

    async def cancel_order(self, order_id, variety="regular"):
        self.state[order_id] = {"status": "CANCELLED", "filled_quantity": 0}
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
