"""Review R6 (Oct 8): per-endpoint provider usage vs Kite's documented limits."""
import pytest

from kite_client import EndpointBudget, KiteClient, RateLimiter


class _Clock:
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t


def test_budget_counts_per_second_rate_and_over_limit_calls():
    clock = _Clock()
    budget = EndpointBudget(clock)
    assert budget.record("quote") == 1
    clock.t += 0.4
    assert budget.record("quote") == 2                 # two quotes within one second: over 1/s
    clock.t += 1.0
    assert budget.record("quote") == 1                 # window slid
    assert budget.record("historical") == 1
    assert budget.record("mystery") == 1               # unknown -> other
    snap = budget.snapshot()
    assert snap["quote"] == {"calls": 3, "peak_per_sec": 2, "over_documented_limit": 1,
                             "documented_limit_per_sec": 1}
    assert snap["historical"]["over_documented_limit"] == 0 and snap["other"]["calls"] == 1


@pytest.mark.asyncio
async def test_quote_calls_are_counted_without_changing_the_shared_rate(tmp_path, monkeypatch):
    client = KiteClient(str(tmp_path / "x.db"))
    assert isinstance(client.limiter, RateLimiter) and client.limiter.rate == 3.0
    client.access_token = "t"

    class _Resp:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"status": "success", "data": {"1": {"instrument_token": 1, "last_price": 10.0}}}

    async def fake_get(*_a, **_k):
        return _Resp()

    monkeypatch.setattr(client.client, "get", fake_get, raising=False)
    result = await client.get_quote([1])
    assert result[1]["last_price"] == 10.0
    assert client.endpoint_budget.snapshot()["quote"]["calls"] >= 1
