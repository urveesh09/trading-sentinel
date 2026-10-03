"""F1-A: every live BUY entry must be fully paid from own uncommitted cash."""
import asyncio

import httpx
import pytest

from kite_client import KiteClient, own_uncommitted_cash


def _client(monkeypatch, *, cash=20_000.0, realised=0.0, net=None, orders=None, fail=None, order_response=None):
    import kite_client
    verdict = type("Verdict", (), {"allowed": True, "reason": ""})()
    monkeypatch.setattr(kite_client, "is_owner_entry_halted", lambda channel: verdict)
    monkeypatch.setattr(kite_client, "assert_not_halted", lambda channel: None)
    posts = []

    def handler(request):
        path = request.url.path
        if fail and path == fail:
            return httpx.Response(503, text="down")
        if path == "/user/margins":
            return httpx.Response(200, json={"data": {"equity": {
                "available": {"cash": cash, "live_balance": cash, "collateral": 1e9},
                "utilised": {"m2m_realised": realised}}}})
        if path == "/portfolio/positions":
            return httpx.Response(200, json={"data": {"net": net or [], "day": []}})
        if path == "/orders" and request.method == "GET":
            if order_response is not None:
                return order_response
            return httpx.Response(200, json={"data": orders or []})
        if path == "/orders/regular" and request.method == "POST":
            posts.append(request)
            return httpx.Response(200, json={"data": {"order_id": "ORD-1"}})
        return httpx.Response(404)

    client = KiteClient(db_path=":memory:")
    client.client = httpx.AsyncClient(base_url="https://api.kite.trade",
                                      transport=httpx.MockTransport(handler))

    async def fast():
        return None

    client.limiter.acquire = fast
    return client, posts


def _buy(client, qty=100, price=100.0, **extra):
    return asyncio.run(client.place_order(
        exchange="NSE", tradingsymbol="AAA", transaction_type="BUY", quantity=qty,
        product="MIS", order_type="LIMIT", price=price, intent="entry", channel="penny", **extra))


def test_pure_rule_subtracts_committed_pending_and_realised_losses():
    margins = {"equity": {"available": {"cash": 20_000.0, "collateral": 1e9},
                          "utilised": {"m2m_realised": -2_000.0}}}
    positions = {"net": [{"quantity": 2, "average_price": 4_000.0}, {"quantity": 0, "average_price": 5.0}]}
    orders = [{"status": "OPEN", "transaction_type": "BUY", "pending_quantity": 3, "price": 1_000.0},
              {"status": "TRIGGER PENDING", "transaction_type": "SELL", "pending_quantity": 2, "price": 3_900.0},
              {"status": "COMPLETE", "transaction_type": "BUY", "pending_quantity": 0, "price": 1.0}]
    assert own_uncommitted_cash(margins, positions, orders) == 7_000.0


@pytest.mark.parametrize("margins,positions,orders", [
    ({"equity": {"available": {"collateral": 50_000.0}}}, {"net": []}, []),        # no own cash
    ({"equity": {"available": {"cash": 100.0}}}, {"net": [{"quantity": -1, "average_price": 10}]}, []),
    ({"equity": {"available": {"cash": 100.0}}}, {"net": [{"quantity": 1, "average_price": None}]}, []),
    ({"equity": {"available": {"cash": 100.0}}}, {}, []),
    ({"equity": {"available": {"cash": 100.0}}}, {"net": []}, None),
    ({"equity": {"available": {"cash": 100.0}}}, {"net": []},
     [{"status": "OPEN", "transaction_type": "BUY", "pending_quantity": 1, "price": 0}]),
    ({"equity": {"available": {"cash": 100.0}, "utilised": {"m2m_realised": "x"}}}, {"net": []}, []),
    ({"equity": {"enabled": False, "available": {"cash": 100.0}}}, {"net": []}, []),
])
def test_pure_rule_fails_closed_on_shorts_and_bad_evidence(margins, positions, orders):
    assert own_uncommitted_cash(margins, positions, orders) is None


def test_leveraged_entry_is_refused_before_any_order_is_sent(monkeypatch):
    client, posts = _client(monkeypatch, cash=2_000.0)
    result = _buy(client, qty=100, price=100.0)                  # 10,000 order on 2,000 own cash
    assert result["own_cash_refused"] is True and result["dispatch_certainty"] == "NOT_SENT"
    assert result["message"].startswith("OWN_CASH_INSUFFICIENT") and posts == []


def test_covered_entry_is_sent_and_existing_commitments_are_counted(monkeypatch):
    client, posts = _client(monkeypatch, cash=20_000.0, realised=-1_000.0,
                            net=[{"quantity": 50, "average_price": 100.0}])
    assert _buy(client, qty=100, price=100.0)["status"] == "PLACED"   # 10,000 <= 14,000
    assert len(posts) == 1
    refused = _buy(client, qty=150, price=100.0)                      # 15,000 > 14,000
    assert refused["own_cash_refused"] is True and len(posts) == 1


@pytest.mark.parametrize("path", ["/user/margins", "/portfolio/positions", "/orders"])
def test_missing_funds_evidence_refuses_the_entry(monkeypatch, path):
    client, posts = _client(monkeypatch, fail=path)
    result = _buy(client)
    assert result["own_cash_refused"] is True
    assert result["message"].startswith("OWN_CASH_EVIDENCE_UNAVAILABLE") and posts == []


def test_entry_without_a_limit_price_is_refused(monkeypatch):
    client, posts = _client(monkeypatch)
    result = asyncio.run(client.place_order(tradingsymbol="AAA", quantity=10, intent="entry",
                                            channel="penny"))
    assert result["own_cash_refused"] is True and posts == []


@pytest.mark.parametrize("payload", [{}, {"data": None}, {"data": {}}, {"data": "bad"}, []])
def test_malformed_order_book_does_not_prove_available_cash(monkeypatch, payload):
    client, posts = _client(monkeypatch, order_response=httpx.Response(200, json=payload))
    try:
        result = _buy(client)
        assert result["own_cash_refused"] is True and posts == []
        assert result["message"].startswith("OWN_CASH_EVIDENCE_UNAVAILABLE")
    finally:
        asyncio.run(client.client.aclose())


def test_invalid_json_order_book_does_not_prove_available_cash(monkeypatch):
    client, posts = _client(monkeypatch, order_response=httpx.Response(200, text="not-json"))
    try:
        result = _buy(client)
        assert result["own_cash_refused"] is True and posts == []
        assert result["message"].startswith("OWN_CASH_EVIDENCE_UNAVAILABLE")
    finally:
        asyncio.run(client.client.aclose())


def test_exits_are_never_checked(monkeypatch):
    client, posts = _client(monkeypatch, cash=0.0, fail="/user/margins")
    result = asyncio.run(client.place_order(
        tradingsymbol="AAA", transaction_type="SELL", quantity=100, order_type="LIMIT", price=99.0,
        intent="exit", channel="penny"))
    assert result["status"] == "PLACED" and len(posts) == 1
