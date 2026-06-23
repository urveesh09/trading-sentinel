"""
[2026-06-22] Tests for the 6 KiteClient methods added per
docs/deviations/2026-06-22-kite-client-methods-deviation.md:
  - get_quote
  - get_instruments_nse_eq
  - get_corporate_actions
  - place_order
  - cancel_order
  - order_history

These tests use httpx.MockTransport to validate the right HTTP
request is sent to the right Kite endpoint with the right params.
"""
import asyncio
import csv
import io
import json
import os
import sys

import httpx
import pytest

# Path setup (mirrors other tests)
HERE = os.path.dirname(__file__)
ENGINE_DIR = os.path.abspath(os.path.join(HERE, ".."))
if ENGINE_DIR not in sys.path:
    sys.path.insert(0, ENGINE_DIR)

from kite_client import KiteClient


@pytest.fixture
def mock_kite_client():
    """A KiteClient that records every request and lets us set canned responses."""
    captured_requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured_requests.append({
            "method": request.method,
            "url": str(request.url),
            "content": request.content.decode("utf-8", errors="ignore") if request.content else "",
        })
        # Default responses
        if request.url.path == "/quote":
            return httpx.Response(200, json={"data": {
                "1001": {"last_price": 12.5, "ohlc": {"high": 12.6, "low": 12.0, "close": 12.5}, "volume": 100000},
            }})
        if request.url.path == "/instruments/NSE":
            csv_text = (
                "instrument_token,exchange,tradingsymbol,segment,instrument_type,name,tick_size,lot_size\n"
                "1001,NSE,AAA,NSE,EQ,AAA Corp Ltd,0.05,1\n"
                "1002,NSE,BBB,NSE,EQ,BBB Corp Ltd,0.05,1\n"
                "1003,NSE,CCC,NSE,EQ,CCC Corp Ltd,0.05,1\n"
            )
            return httpx.Response(200, text=csv_text)
        if request.url.path.startswith("/orders/regular/") and request.method == "DELETE":
            order_id = request.url.path.split("/")[-1]
            return httpx.Response(200, json={"data": {"order_id": order_id}})
        if request.url.path.startswith("/orders/") and request.method == "GET":
            return httpx.Response(200, json={"data": [
                {"order_id": "ORD-001", "status": "COMPLETE", "filled_quantity": 50,
                 "average_price": 12.5, "transaction_type": "BUY"}
            ]})
        if request.url.path.startswith("/orders/regular") and request.method == "POST":
            return httpx.Response(200, json={"data": {"order_id": "ORD-001"}})
        return httpx.Response(200, json={"data": {}})

    transport = httpx.MockTransport(handler)
    # Use an in-memory db to avoid touching the real one
    client = KiteClient(db_path=":memory:")
    # Replace the underlying httpx client
    client.client = httpx.AsyncClient(base_url="https://api.kite.trade", transport=transport)
    # Bypass the rate limiter for tests
    async def fast_acquire():
        return None
    client.limiter.acquire = fast_acquire
    return client, captured_requests


def test_get_quote_returns_normalized_dict(mock_kite_client):
    """get_quote([tokens]) -> dict {int_token: {...}, ...}"""
    client, requests = mock_kite_client
    result = asyncio.run(client.get_quote([1001]))
    assert 1001 in result
    assert result[1001]["last_price"] == 12.5
    # Verify request URL used ?i=1001
    quote_req = next(r for r in requests if r["url"].endswith("/quote") or "/quote?" in r["url"])
    assert "i=1001" in quote_req["url"]


def test_get_quote_accepts_single_token(mock_kite_client):
    """get_quote(token_int) is also valid (normalized to list)."""
    client, _ = mock_kite_client
    result = asyncio.run(client.get_quote(1001))
    assert 1001 in result


def test_get_instruments_nse_eq_returns_eq_only(mock_kite_client):
    """CSV is parsed; only EQ rows are returned; instrument_cache is updated."""
    client, requests = mock_kite_client
    result = asyncio.run(client.get_instruments_nse_eq())
    assert len(result) == 3
    assert all(r["instrument_type"] == "EQ" for r in result)
    assert all(r["exchange"] == "NSE" for r in result)
    # instrument_cache populated
    assert client.instrument_cache.get("AAA") == 1001
    assert client.instrument_cache.get("BBB") == 1002
    # Request was made
    assert any(r["url"].endswith("/instruments/NSE") for r in requests)


def test_get_corporate_actions_returns_empty_list(mock_kite_client):
    """No public Kite endpoint; falls back to local file at caller level."""
    client, requests = mock_kite_client
    result = asyncio.run(client.get_corporate_actions())
    assert result == []
    # No API request was made
    assert not any("/corp" in r["url"] for r in requests)


def test_place_order_posts_to_orders_regular(mock_kite_client):
    """place_order() -> POST /orders/regular with form data."""
    client, requests = mock_kite_client
    result = asyncio.run(client.place_order(
        tradingsymbol="AAA", transaction_type="BUY", quantity=50,
        product="MIS", order_type="LIMIT", price=12.5,
    ))
    assert result["status"] == "PLACED"
    assert result["order_id"] == "ORD-001"
    # Find the POST request
    post = next(r for r in requests if r["method"] == "POST")
    assert "/orders/regular" in post["url"]
    # Body has the params
    body = post["content"]
    assert "tradingsymbol=AAA" in body
    assert "quantity=50" in body
    assert "order_type=LIMIT" in body
    assert "price=12.5" in body


def test_place_order_validates_inputs(mock_kite_client):
    """Empty tradingsymbol or zero quantity -> ERROR without API call."""
    client, requests = mock_kite_client
    result = asyncio.run(client.place_order(tradingsymbol="", quantity=50))
    assert result["status"] == "ERROR"
    result = asyncio.run(client.place_order(tradingsymbol="AAA", quantity=0))
    assert result["status"] == "ERROR"
    # No POST was made
    assert not any(r["method"] == "POST" for r in requests)


def test_place_order_with_sl_m_sends_trigger_price(mock_kite_client):
    """SL-M orders include trigger_price in the body."""
    client, requests = mock_kite_client
    asyncio.run(client.place_order(
        tradingsymbol="AAA", transaction_type="SELL", quantity=50,
        product="MIS", order_type="SL-M", trigger_price=11.5,
    ))
    post = next(r for r in requests if r["method"] == "POST")
    assert "trigger_price=11.5" in post["content"]
    assert "order_type=SL-M" in post["content"]


def test_cancel_order_deletes_correct_path(mock_kite_client):
    """cancel_order(order_id) -> DELETE /orders/regular/{order_id}."""
    client, requests = mock_kite_client
    result = asyncio.run(client.cancel_order(order_id="ORD-001"))
    assert result["status"] == "CANCELLED"
    delete = next(r for r in requests if r["method"] == "DELETE")
    assert "/orders/regular/ORD-001" in delete["url"]


def test_order_history_returns_list(mock_kite_client):
    """order_history(order_id) -> list of status updates, index 0 is latest."""
    client, _ = mock_kite_client
    result = asyncio.run(client.order_history(order_id="ORD-001"))
    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0]["order_id"] == "ORD-001"
    assert result[0]["status"] == "COMPLETE"


def test_methods_go_through_rate_limiter():
    """All new methods must call self.limiter.acquire() (not bypass the limit)."""
    import inspect
    from kite_client import KiteClient
    for name in ["get_quote", "get_instruments_nse_eq", "place_order",
                 "cancel_order", "order_history"]:
        method = getattr(KiteClient, name)
        source = inspect.getsource(method)
        assert "self.limiter.acquire" in source, \
            f"{name} does not go through rate limiter"
