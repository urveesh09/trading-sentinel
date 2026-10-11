"""Oct 9 Production audit: recovery from a lost symbol cache and the paths it broke.

O9-R1 instrument cache recovery, O9-S1 Smart held-exit quotes and exposure,
O9-M1 bounded Momentum heartbeat, O9-O1 overnight unavailable input,
O9-Q1/Q2/Q3 quote dispatch spacing, error counting and the 500-key limit.
"""
import asyncio
import json
import sqlite3
import time
from datetime import datetime, timedelta, timezone

import httpx
import pytest

import edge_overnight_paper as eop
from kite_client import KiteClient, QuoteBudget


def _dump(n):
    rows = "\n".join(f'{100000 + i},{i},"SYM{i}","Name {i}"' for i in range(n))
    return "instrument_token,exchange_token,tradingsymbol,name\n" + rows


class _Resp:
    def __init__(self, text="", status=200, data=None):
        self.text, self.status_code, self._data = text, status, data or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            request = httpx.Request("GET", "http://kite/quote")
            raise httpx.HTTPStatusError("x", request=request, response=httpx.Response(self.status_code, request=request))

    def json(self):
        return {"status": "success", "data": self._data}


# --------------------------------------------------------------------------- O9-R1 instrument cache

@pytest.mark.asyncio
async def test_failed_refresh_falls_back_to_the_saved_snapshot_and_recovers(tmp_path):
    db = str(tmp_path / "cache.db")
    good = KiteClient(db)
    good.access_token = "t"

    async def ok(url, **_k):
        return _Resp(_dump(1500))

    good.client.get = ok
    assert await good.refresh_instrument_cache() is True
    assert (tmp_path / "nse_instrument_cache.json").exists()

    # The Oct 9 restart: a new process, token restored, DNS fails.
    restarted = KiteClient(db)
    restarted.access_token = "t"
    shared_ref = restarted.instrument_cache                  # universes hold this exact dict

    async def dns_down(url, **_k):
        raise httpx.ConnectError("[Errno -3] Temporary failure in name resolution")

    restarted.client.get = dns_down
    assert await restarted.refresh_instrument_cache() is False
    status = restarted.instrument_cache_status()
    assert status["source"] == "SNAPSHOT" and status["usable"] and status["size"] == 1500
    assert status["last_error_type"] == "ConnectError" and status["failures"] == 1
    assert restarted.instrument_cache is shared_ref and shared_ref["SYM7"] == 100007

    # The recovery job retries until a provider refresh succeeds, then is a no-op.
    calls = []

    async def back(url, **_k):
        calls.append(url)
        return _Resp(_dump(1600))

    restarted.client.get = back
    assert await restarted.ensure_instrument_cache() is True
    assert restarted.instrument_cache_status()["source"] == "PROVIDER"
    assert restarted.instrument_cache_status()["failures"] == 0
    assert await restarted.ensure_instrument_cache() is True and len(calls) == 1


@pytest.mark.asyncio
async def test_without_any_snapshot_the_cache_reports_unusable(tmp_path):
    client = KiteClient(str(tmp_path / "cache.db"))
    client.access_token = "t"

    async def dns_down(url, **_k):
        raise httpx.ConnectError("dns")

    client.client.get = dns_down
    assert await client.ensure_instrument_cache() is False
    status = client.instrument_cache_status()
    assert status["source"] == "EMPTY" and not status["usable"] and status["size"] == 0


def test_an_old_or_tiny_snapshot_is_refused(tmp_path):
    client = KiteClient(str(tmp_path / "cache.db"))
    path = tmp_path / "nse_instrument_cache.json"
    old = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    path.write_text(json.dumps({"saved_at": old, "tokens": {f"S{i}": i for i in range(2000)}}))
    assert client._load_instrument_snapshot() is False and client.instrument_cache == {}
    path.write_text(json.dumps({"saved_at": datetime.now(timezone.utc).isoformat(), "tokens": {"A": 1}}))
    assert client._load_instrument_snapshot() is False


@pytest.mark.asyncio
async def test_readiness_watchdog_pages_on_an_empty_symbol_cache(monkeypatch):
    import main
    import ops_watchdogs

    sent = []

    async def _notify(message, *, event="x"):
        sent.append(message)
        return True

    async def _trading_day(*a, **k):
        return True

    class _Kite:
        access_token = "t"

        def instrument_cache_status(self):
            return {"usable": False, "size": 0, "last_error_type": "ConnectError"}

    class _Sched:
        running = True

    monkeypatch.setattr(main, "kite", _Kite())
    monkeypatch.setattr(main, "scheduler", _Sched())
    monkeypatch.setattr(ops_watchdogs, "is_trading_day", _trading_day)
    monkeypatch.setattr("operator_alert.notify_operator", _notify, raising=False)
    monkeypatch.setattr("order_execution_readiness.snapshot", lambda: {"status": "AUTHORIZED"}, raising=False)
    monkeypatch.setattr("halt_switch.halt_state", lambda _x: (False, {}), raising=False)
    real = ops_watchdogs.datetime

    class _Now(real):
        @classmethod
        def now(cls, tz=None):
            return real(2026, 10, 9, 11, 30, tzinfo=tz)

    monkeypatch.setattr(ops_watchdogs, "datetime", _Now)
    ops_watchdogs._readiness_state.update(last_alert_monotonic=None, was_ready=True)
    await ops_watchdogs._trading_readiness_tick()
    assert sent and "NSE symbol list is unavailable" in sent[0]


# --------------------------------------------------------------------------- O9-S1 Smart held exits

@pytest.mark.asyncio
async def test_smart_held_exit_is_quoted_by_symbol_when_the_cache_is_empty(tmp_path, monkeypatch):
    import penny_smart_shadow as pss

    db = str(tmp_path / "smart.db")
    state = {"positions": {"TATSILV": {}, "STEELXIND": {}}, "binding": {"bankroll": 2000.0, "stock_cap": 500.0,
                                                                        "max_positions": 3}}
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE penny_smart_paper_state (policy TEXT PRIMARY KEY, state_json TEXT NOT NULL)")
        conn.execute("INSERT INTO penny_smart_paper_state VALUES (?,?)", (pss.SMART_VERSION, json.dumps(state)))
    seen = {}

    async def fake_observe(_db, _obs, raw, **_k):
        seen.update(raw)
        return {"open": 2}

    monkeypatch.setattr(pss, "observe_smart_shadow", fake_observe)

    class _Kite:
        instrument_cache = {}                       # Oct 9 after 11:19
        token_calls = []

        async def get_quote(self, tokens):
            self.token_calls.append(tokens)
            return {}

        async def get_quote_by_instruments(self, keyed):
            return {key: {"symbol": name} for key, name in keyed.items()}

    kite = _Kite()
    await pss.monitor_smart_shadow(db, kite, now=datetime.now(pss.IST))
    assert kite.token_calls == []
    assert seen == {"STEELXIND": {"symbol": "NSE:STEELXIND"}, "TATSILV": {"symbol": "NSE:TATSILV"}}


def test_smart_exposure_snapshot_flags_unpriced_deadline_positions(tmp_path):
    import penny_smart_shadow as pss

    ledger = str(tmp_path / "cache.db")
    assert pss.smart_exposure_snapshot(ledger)["status"] == "NO_BOOK"
    state = {"day": "2026-10-09", "mark_status": "UNAVAILABLE", "marked_pnl": None,
             "positions": {"STEELXIND": {"managed_at": "2026-10-09T11:17:00+05:30",
                                         "exit_pending": "SMART_SESSION_DEADLINE"}}}
    with sqlite3.connect(pss.smart_db_path(ledger)) as conn:
        conn.execute("CREATE TABLE penny_smart_paper_state (policy TEXT PRIMARY KEY, state_json TEXT NOT NULL)")
        conn.execute("INSERT INTO penny_smart_paper_state VALUES (?,?)", (pss.SMART_VERSION, json.dumps(state)))
    snap = pss.smart_exposure_snapshot(ledger, now=datetime(2026, 10, 9, 15, 30, tzinfo=pss.IST))
    assert snap["status"] == "ATTENTION" and snap["open"] == 1 and snap["mark_status"] == "UNAVAILABLE"
    assert snap["positions"][0]["exit_pending"] == "SMART_SESSION_DEADLINE"
    assert snap["positions"][0]["minutes_since_managed"] == 253.0


# --------------------------------------------------------------------------- O9-M1 Momentum heartbeat

def test_momentum_reason_families_collapse_ticker_detail():
    import main

    assert main._momentum_reason_family("exception: Unknown ticker: ICICIAMC") == "exception: Unknown ticker"
    assert main._momentum_reason_family("no_recent_vwap_crossover") == "no_recent_vwap_crossover"
    assert main._momentum_reason_family("exception: ") == "exception: error"


@pytest.mark.asyncio
async def test_oct9_heartbeat_with_497_unknown_tickers_stays_small_and_a_413_is_logged(monkeypatch, caplog):
    import main

    bodies = []

    class _Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json=None, **_k):
            bodies.append(json["message"])
            return httpx.Response(413)

    monkeypatch.setattr(httpx, "AsyncClient", _Client)
    rejected = [{"ticker": f"T{i}", "reject_reason": f"exception: Unknown ticker: T{i}"} for i in range(497)]
    rejected += [{"ticker": f"R{i}", "reject_reason": f"reason_{i}"} for i in range(30)]
    await main._notify_momentum_heartbeat(datetime(2026, 10, 9, 11, 30), 527, 0, 0, rejected, 2500.0)
    body = bodies[0]
    assert len(body.encode("utf-8")) < 10 * 1024 and len(body) <= main.MOMENTUM_HEARTBEAT_MAX_CHARS + 20
    assert "Exception: Unknown Ticker: `497`" in body and "other reasons" in body


# --------------------------------------------------------------------------- O9-O1 overnight input

class _SymbolKite:
    """Empty token cache; answers only EXCHANGE:SYMBOL lookups (or nothing)."""

    def __init__(self, quotes, answer=True):
        self.instrument_cache, self.quotes, self.answer, self.chunks = {}, quotes, answer, []

    async def get_quote(self, tokens):
        raise AssertionError("no token is known")

    async def get_quote_by_instruments(self, keyed):
        self.chunks.append(len(keyed))
        if not self.answer:
            return {}
        return {k: self.quotes[name.split(":", 1)[1]] for k, name in keyed.items()
                if name.split(":", 1)[1] in self.quotes}


@pytest.mark.asyncio
async def test_overnight_quotes_fall_back_to_symbols_in_500_key_chunks():
    names = [f"N{i}" for i in range(1100)]
    kite = _SymbolKite({name: {"last_price": float(i)} for i, name in enumerate(names)})
    out = await eop._quotes(kite, names)
    assert kite.chunks == [500, 500, 100]
    assert len(out) == 1100 and out["N0"]["last_price"] == 0.0 and out["N1099"]["last_price"] == 1099.0


@pytest.mark.asyncio
async def test_overnight_entry_without_quotes_retries_then_records_unavailable(tmp_path):
    from tests.test_edge_overnight_paper import TODAY, _at, _cache

    cache = _cache(tmp_path)
    kite = _SymbolKite({}, answer=False)
    first = await eop.run_overnight_entry(kite, cache, now=_at(TODAY, 15, 20))
    assert first["status"] == "DATA_UNAVAILABLE" and first["retry"] is True
    with sqlite3.connect(eop.overnight_db_path(cache)) as conn:
        assert conn.execute("SELECT COUNT(*) FROM edge_overnight_paper_runs").fetchone()[0] == 0
    ran = await eop.catch_up(kite, cache, now=_at(TODAY, 15, 25))                 # the last slot inside 15:29
    assert ran == ["ENTRY"]
    with sqlite3.connect(eop.overnight_db_path(cache)) as conn:
        summary = json.loads(conn.execute("SELECT summary FROM edge_overnight_paper_runs").fetchone()[0])
        notice = conn.execute("SELECT message FROM edge_overnight_paper_notices").fetchone()[0]
    assert summary["status"] == "DATA_UNAVAILABLE" and summary["quoted"] == 0 and summary["opened"] == []
    assert "quotes unavailable" in notice and "Not a no-signal day" in notice


# --------------------------------------------------------------------------- O9-Q1/Q2/Q3 quote budget

@pytest.mark.asyncio
async def test_quote_sends_stay_spaced_when_the_shared_limiter_delays_one(tmp_path, monkeypatch):
    """O9-Q1: the audit's probe -- a slot held up in the shared limiter sent
    0.336 s before the next slot's call. Sends must stay >= 1/rate apart."""
    client = KiteClient(str(tmp_path / "x.db"))
    rate = 10.0
    client.quote_budget = QuoteBudget(rate=rate)
    client.access_token = "t"
    sends = []

    class _SlowFirst:
        rate = 30.0
        n = 0

        async def acquire(self, priority=None):
            self.n += 1
            if self.n == 1:
                await asyncio.sleep(0.07)              # congestion on the shared 3/s limiter

    client.limiter = _SlowFirst()

    async def fake_get(path, params=None):
        sends.append(time.monotonic())
        return _Resp(data={key: {"last_price": 1.0} for _n, key in params})

    monkeypatch.setattr(client.client, "get", fake_get)
    await asyncio.gather(client.get_quote_by_instruments({1: "NSE:A"}),
                         client.get_quote_by_instruments({2: "NSE:B"}))
    assert len(sends) == 2 and sends[1] - sends[0] >= (1 / rate) * 0.98
    assert client.quote_budget.snapshot()["dispatch_gate_waits"] == 1


@pytest.mark.asyncio
async def test_instrument_keyed_quote_failures_are_counted(tmp_path, monkeypatch):
    client = KiteClient(str(tmp_path / "x.db"))
    client.access_token = "t"

    async def throttled(path, params=None):
        return _Resp(status=429)

    monkeypatch.setattr(client.client, "get", throttled)
    result, timing = await client.get_quote_by_instruments_with_timing({1: "NSE:A"})
    assert result == {} and timing["outcome"] == "FAILED" and timing["http_status"] == 429
    assert client.endpoint_budget.snapshot()["quote"]["http_429"] == 1


@pytest.mark.asyncio
async def test_token_quotes_over_500_are_chunked(tmp_path, monkeypatch):
    client = KiteClient(str(tmp_path / "x.db"))
    client.quote_budget = QuoteBudget(rate=50.0)
    client.access_token = "t"
    sizes = []

    async def fake_get(path, params=None):
        keys = [value for _n, value in params]
        sizes.append(len(keys))
        return _Resp(data={key: {"last_price": float(key)} for key in keys})

    monkeypatch.setattr(client.client, "get", fake_get)
    tokens = list(range(1, 972))                       # the Oct 9 overnight universe size
    result = await client.get_quote(tokens)
    assert max(sizes) <= QuoteBudget.MAX_INSTRUMENTS and sum(sizes) == 971
    assert sorted(result) == tokens and result[971]["last_price"] == 971.0


def test_penny_does_not_wait_60s_after_a_failed_refresh():
    """O9-R1: 95 Penny max-instance skips came from a 60 s wait on a refresh
    that had already failed. A failed, empty cache skips the tick at once."""
    from unittest.mock import MagicMock

    from penny_scanner import PennyScanner

    kite = MagicMock()
    kite.instrument_cache = {}
    kite.instrument_cache_status = lambda: {"source": "EMPTY", "failures": 2, "last_error_type": "ConnectError"}
    started = time.monotonic()
    ready = asyncio.run(PennyScanner(kite=kite, universe_json_path="/nonexistent.json")
                        ._wait_for_instrument_cache(min_count=100, timeout=5.0))
    assert ready is False and time.monotonic() - started < 0.5
