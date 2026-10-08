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
                             "documented_limit_per_sec": 1, "http_errors": {}, "http_429": 0}
    budget.record_status("quote", 429)
    budget.record_status("quote", 503)
    assert budget.snapshot()["quote"]["http_429"] == 1
    assert budget.snapshot()["quote"]["http_errors"] == {"429": 1, "503": 1}
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


class _FakeHttp:
    """Records every /quote HTTP call with its clock and instruments."""

    def __init__(self):
        self.calls = []

    async def get(self, path, params=None):
        import time as _t
        keys = [value for _name, value in (params or [])]
        self.calls.append((_t.monotonic(), path, keys))

        class _R:
            status_code = 200

            def raise_for_status(self):
                return None

            def json(self):
                data = {}
                for key in keys:
                    token = int(key) if key.isdigit() else 900000 + len(key)
                    data[key if not key.isdigit() else str(token)] = {"instrument_token": token, "last_price": 1.0}
                return {"status": "success", "data": data}
        return _R()


@pytest.mark.asyncio
async def test_concurrent_penny_fno_and_expiry_quotes_respect_the_quote_budget(tmp_path, monkeypatch):
    """Follow-up F3: Penny bulk scans, main F&O exit reads and the expiry batch
    at once. /quote HTTP calls stay within the budget, concurrent token
    requests are merged (<= 500 instruments), every caller gets exactly its
    own tokens, and management waits stay bounded."""
    import asyncio
    import time as _t
    from kite_client import QuoteBudget, provider_lane

    client = KiteClient(str(tmp_path / "x.db"))
    rate = 10.0                                       # scaled 10x so the test is fast
    client.quote_budget = QuoteBudget(rate=rate)
    client.limiter = RateLimiter(rate=30.0, burst=1)  # shared limiter scaled alike
    client.access_token = "t"
    fake = _FakeHttp()
    monkeypatch.setattr(client, "client", fake)

    async def penny(i):
        with provider_lane("bulk"):
            tokens = list(range(1000 + i * 40, 1000 + i * 40 + 40))
            result = await client.get_quote(tokens)
            assert sorted(result) == tokens

    async def fno_exit(i):
        started = _t.monotonic()
        result, _timing = await client.get_quote_with_timing([50 + i], priority="management")
        assert list(result) == [50 + i]
        return _t.monotonic() - started

    async def expiry():
        with provider_lane("management"):
            result, _timing = await client.get_quote_by_instruments_with_timing({1: "BFO:A", 2: "BFO:B"})
            return result

    jobs = [penny(i) for i in range(30)] + [fno_exit(i) for i in range(5)] + [expiry()]
    out = await asyncio.gather(*jobs)
    exit_waits = out[30:35]
    quote_calls = [c for c in fake.calls if c[1] == "/quote"]
    # 36 requests needed far fewer HTTP calls: merged up to 500 instruments.
    assert len(quote_calls) < 10 and max(len(c[2]) for c in quote_calls) <= QuoteBudget.MAX_INSTRUMENTS
    gaps = [b[0] - a[0] for a, b in zip(quote_calls, quote_calls[1:])]
    assert all(gap >= (1 / rate) * 0.8 for gap in gaps)          # never faster than the budget
    assert max(exit_waits) <= 3 / rate + 0.5                      # management is served first
    assert client.quote_budget.snapshot()["batches"] >= 1
