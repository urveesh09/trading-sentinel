"""Oct 12 Production audit: F&O lock and read deadlines, quote fairness, cache
validation, spread-tilt identity/freeze, Smart exit-date totals.

O12-F1 flat fast exit vs regular pass, O12-R1 defined-risk read deadlines,
O12-Q1/Q2 quote fairness and the 500-key bound, O12-C1/C2 instrument cache,
O12-T1/T2/T3 spread tilt, O12-S1 Smart exit-date reporting.
"""
import asyncio
import json
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

import fno_orchestrator
import fno_spread_tilt as tilt
from fno_models import OptionType
from fno_spread_tilt import Single, Spread
from kite_client import KiteClient, QuoteBatchCancelled, QuoteBudget, RateLimiter, _provider_lane


class _Resp:
    def __init__(self, text="", status=200, data=None):
        self.text, self.status_code, self._data = text, status, data or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            request = httpx.Request("GET", "http://kite/quote")
            raise httpx.HTTPStatusError("x", request=request, response=httpx.Response(self.status_code, request=request))

    def json(self):
        return {"status": "success", "data": self._data}


def _dump(n, prefix="SYM"):
    rows = "\n".join(f'{100000 + i},{i},"{prefix}{i}","Name {i}"' for i in range(n))
    return "instrument_token,exchange_token,tradingsymbol,name\n" + rows


# --------------------------------------------------------------------------- O12-F1 F&O lock

def _jobs(monkeypatch):
    import main
    import scheduler_setup
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from config import settings

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return main.IST.localize(datetime(2026, 10, 12, 11, 0))

    monkeypatch.setattr(scheduler_setup, "datetime", Clock)
    monkeypatch.setattr(main, "is_trading_day", AsyncMock(return_value=True))
    monkeypatch.setattr(main, "kite", MagicMock(access_token="test"))
    monkeypatch.setattr(settings, "FNO_FAST_EXIT_ENABLED", True)
    probe = AsyncIOScheduler(timezone=main.IST)
    main.register_fno_scheduler_jobs(probe)
    return {job.id: job for job in probe.get_jobs()}


@pytest.mark.asyncio
async def test_a_regular_tick_waits_for_a_fast_pass_instead_of_skipping(monkeypatch):
    """Oct 12: 4 regular passes skipped because a fast pass held the lock."""
    jobs = _jobs(monkeypatch)
    order = []
    fast_running = asyncio.Event()

    async def fast(*_a, **_k):
        order.append("fast_start")
        fast_running.set()
        await asyncio.sleep(0.05)
        order.append("fast_end")
        return {"exits": []}

    async def tick(*_a, **_k):
        order.append("tick")
        return {}

    monkeypatch.setattr(fno_orchestrator, "fast_exit_has_work", AsyncMock(return_value=True))
    monkeypatch.setattr(fno_orchestrator, "run_fno_fast_exit", fast)
    monkeypatch.setattr(fno_orchestrator, "run_fno_tick", tick)

    async def tick_during_fast():
        await fast_running.wait()
        await jobs["fno_tick"].func()

    await asyncio.gather(jobs["fno_fast_exit"].func(), tick_during_fast())
    assert order == ["fast_start", "fast_end", "tick"]          # waited, then ran its entry work


@pytest.mark.asyncio
async def test_a_flat_fast_pass_never_takes_the_lock(monkeypatch):
    jobs = _jobs(monkeypatch)
    manage = AsyncMock(return_value={"exits": []})
    seen_locked = []

    async def flat(*_a, **_k):
        seen_locked.append(True)
        return False

    monkeypatch.setattr(fno_orchestrator, "fast_exit_has_work", flat)
    monkeypatch.setattr(fno_orchestrator, "run_fno_fast_exit", manage)
    ticks = []

    async def tick(*_a, **_k):
        ticks.append(1)
        return {}

    monkeypatch.setattr(fno_orchestrator, "run_fno_tick", tick)
    await asyncio.gather(jobs["fno_fast_exit"].func(), jobs["fno_tick"].func())
    assert seen_locked and manage.await_count == 0 and ticks == [1]


@pytest.mark.asyncio
async def test_a_regular_tick_still_skips_behind_another_regular_tick(monkeypatch):
    jobs = _jobs(monkeypatch)
    calls = []

    async def tick(*_a, **_k):
        calls.append(1)
        if len(calls) == 1:
            await jobs["fno_tick"].func()                       # same work already running
        return {}

    monkeypatch.setattr(fno_orchestrator, "run_fno_tick", tick)
    await jobs["fno_tick"].func()
    assert calls == [1]


# --------------------------------------------------------------------------- O12-R1 DR read deadlines

def _nifty_book():
    from fno_instruments import FnoInstruments
    rows = ["instrument_token,exchange_token,tradingsymbol,name,last_price,expiry,strike,tick_size,"
            "lot_size,instrument_type,segment,exchange"]
    token = 100
    for strike in range(24500, 25551, 50):
        for ot in ("CE", "PE"):
            token += 1
            rows.append(f"{token},1,NIFTY2610{strike}{ot},NIFTY,0,2026-10-13,{strike},0.05,75,{ot},NFO-OPT,NFO")
    rows.append("900,1,NIFTY26OCTFUT,NIFTY,0,2026-10-27,0,0.05,75,FUT,NFO-FUT,NFO")

    class _Dump:
        async def get_instruments_dump(self, segment):
            return "\n".join(rows)

    book = FnoInstruments("NIFTY", json_path="unused")
    return book, _Dump()


class _ChainKite:
    def __init__(self, fut_price):
        self.fut_price = fut_price
        self.calls = []

    async def get_quote(self, tokens):
        self.calls.append((list(tokens), _provider_lane.get()))
        out = {}
        for t in tokens:
            if t == 900:
                out[t] = {"last_price": self.fut_price, "depth": {}}
            else:
                out[t] = {"last_price": 100.0, "depth": {"buy": [{"price": 99.5, "quantity": 75}],
                                                          "sell": [{"price": 100.5, "quantity": 75}]}}
        return out


@pytest.mark.asyncio
async def test_an_anchored_chain_snapshot_needs_one_quote_request():
    from fno_chain import take_chain_snapshot
    book, dump = _nifty_book()
    assert await book.refresh(dump)
    kite = _ChainKite(fut_price=25010.0)
    now = fno_orchestrator.IST.localize(datetime(2026, 10, 12, 10, 33))
    snap = await take_chain_snapshot(kite, book, now, anchor_price=25000.0)
    assert snap is not None and len(kite.calls) == 1             # ladder + future together
    assert snap.forward == 25010.0                               # forward from the fresh future, not the anchor
    plain = _ChainKite(fut_price=25010.0)
    assert await take_chain_snapshot(plain, book, now) is not None and len(plain.calls) == 2


@pytest.mark.asyncio
async def test_an_anchor_far_from_the_fresh_future_retakes_the_snapshot():
    from fno_chain import take_chain_snapshot
    book, dump = _nifty_book()
    assert await book.refresh(dump)
    kite = _ChainKite(fut_price=25400.0)                         # moved 8 strikes from the anchor
    now = fno_orchestrator.IST.localize(datetime(2026, 10, 12, 10, 33))
    snap = await take_chain_snapshot(kite, book, now, anchor_price=25000.0)
    assert snap is not None and len(kite.calls) == 3             # anchored try, then the normal two
    assert book.atm_strike(snap.forward) == 25400.0 and snap.quote(25400.0, OptionType.CE) is not None


@pytest.mark.asyncio
async def test_defined_risk_entry_reads_use_the_management_lane(monkeypatch):
    book, dump = _nifty_book()
    assert await book.refresh(dump)
    kite = _ChainKite(fut_price=25000.0)
    lanes = []

    async def bars(*_a, **_k):
        lanes.append(_provider_lane.get())
        return None

    monkeypatch.setattr(fno_orchestrator, "_fetch_futures_bars", bars)
    monkeypatch.setattr(fno_orchestrator, "evaluate_fno_mom", lambda *a, **k: MagicMock(direction=None))
    now = fno_orchestrator.IST.localize(datetime(2026, 10, 12, 10, 33))
    snap, _bars, _sig, reason = await fno_orchestrator._load_dr_entry_inputs(
        kite, book, 900, "REGIME_2_ELEVATED", now, anchor_price=25000.0)
    assert reason == "" and snap is not None
    assert [lane for _tokens, lane in kite.calls] == ["management"] and lanes == ["management"]
    assert _provider_lane.get() == "normal"                     # the lane does not leak to the caller


# --------------------------------------------------------------------------- O12-Q1/Q2 quote budget

def _budget_client(tmp_path, rate=20.0):
    client = KiteClient(str(tmp_path / "x.db"))
    client.quote_budget = QuoteBudget(rate=rate)
    client.limiter = RateLimiter(rate=rate * 3, burst=1)
    client.access_token = "t"
    return client


@pytest.mark.asyncio
async def test_a_management_read_arriving_during_a_bulk_wait_is_sent_first(tmp_path, monkeypatch):
    client = _budget_client(tmp_path, rate=10.0)
    sends = []

    async def fake_get(path, params=None):
        sends.append(sorted(int(v) for _n, v in params))
        return _Resp(data={v: {"last_price": 1.0} for _n, v in params})

    monkeypatch.setattr(client.client, "get", fake_get)

    async def bulk(start):
        tokens = list(range(start, start + 400))                 # cannot merge with each other (> 500)
        return await client.get_quote_with_timing(tokens, priority="bulk")

    async def management():
        await asyncio.sleep(0.02)                                # arrives while the bulk waits
        return await client.get_quote_with_timing([7], priority="management")

    out = await asyncio.gather(bulk(1000), bulk(2000), management())
    order = [s for s in sends]
    second = order[1]
    assert 7 in second and out[2][1]["quote_batch_lane"] == "management"   # label matches the batch it rode
    assert sorted(out[0][0]) == list(range(1000, 1400)) and list(out[2][0]) == [7]


@pytest.mark.asyncio
async def test_continuous_management_reads_cannot_starve_a_bulk_read(tmp_path, monkeypatch):
    """The audit's probe: a 500-token bulk read behind 250-token management
    reads that keep arriving. Bulk now leads a batch after 3 management batches."""
    client = _budget_client(tmp_path, rate=50.0)
    sends = []

    async def fake_get(path, params=None):
        tokens = [int(v) for _n, v in params]
        sends.append("bulk" if 1 in tokens else "management")
        return _Resp(data={str(t): {"last_price": 1.0} for t in tokens})

    monkeypatch.setattr(client.client, "get", fake_get)
    stop = asyncio.Event()

    async def management_stream():
        n = 0
        while not stop.is_set() and n < 12:
            n += 1
            base = 10_000 * n
            await asyncio.gather(client.get_quote_with_timing(list(range(base, base + 250)), priority="management"),
                                 client.get_quote_with_timing(list(range(base + 300, base + 550)),
                                                              priority="management"))

    async def bulk():
        await asyncio.sleep(0.005)
        result, _ = await client.get_quote_with_timing(list(range(1, 501)), priority="bulk")
        stop.set()
        return result

    result, _ = await asyncio.gather(bulk(), management_stream())
    assert len(result) == 500
    assert sends.index("bulk") <= QuoteBudget.FAIRNESS_BURST + 1
    assert client.quote_budget.snapshot()["fairness_promotions"] >= 1


@pytest.mark.asyncio
async def test_a_cancelled_batch_releases_every_waiting_caller(tmp_path, monkeypatch):
    client = _budget_client(tmp_path)
    started = asyncio.Event()

    async def hang(path, params=None):
        started.set()
        await asyncio.sleep(30)

    monkeypatch.setattr(client.client, "get", hang)
    callers = [asyncio.create_task(client.get_quote_with_timing([1, 2])),
               asyncio.create_task(client.get_quote_with_timing([3]))]
    await started.wait()
    budget = client.quote_budget
    assert budget.snapshot()["in_flight"] == 1
    for task in list(budget._inflight):
        task.cancel()
    results = await asyncio.wait_for(asyncio.gather(*callers, return_exceptions=True), timeout=2)
    assert all(isinstance(r, QuoteBatchCancelled) for r in results)
    assert budget.snapshot()["cancelled_batches"] == 1


@pytest.mark.asyncio
async def test_keyed_quotes_over_500_are_chunked_and_mapped(tmp_path, monkeypatch):
    client = _budget_client(tmp_path, rate=50.0)
    sizes = []

    async def fake_get(path, params=None):
        keys = [v for _n, v in params]
        sizes.append(len(keys))
        return _Resp(data={k: {"last_price": float(k.split(":")[1])} for k in keys})

    monkeypatch.setattr(client.client, "get", fake_get)
    request = {t: f"NSE:{t}" for t in range(1, 502)}
    result, timing = await client.get_quote_by_instruments_with_timing(request)
    assert sizes == [500, 1] and sorted(result) == list(range(1, 502)) and result[501]["last_price"] == 501.0
    assert timing["chunks"] == 2 and timing["attempt_count"] == 2 and timing["outcome"] == "COMPLETE"


@pytest.mark.asyncio
async def test_chunked_token_timing_reports_the_largest_request_not_a_sum(tmp_path, monkeypatch):
    client = _budget_client(tmp_path, rate=50.0)

    async def fake_get(path, params=None):
        return _Resp(data={v: {"last_price": 1.0} for _n, v in params})

    monkeypatch.setattr(client.client, "get", fake_get)
    _result, timing = await client.get_quote_with_timing(list(range(1, 972)))
    assert timing["chunks"] == 2 and timing["quote_batch_instruments"] == 500
    assert timing["attempt_count"] == 2


# --------------------------------------------------------------------------- O12-C1/C2 instrument cache

@pytest.mark.asyncio
async def test_a_truncated_dump_is_a_failed_refresh_that_keeps_retrying(tmp_path):
    client = KiteClient(str(tmp_path / "cache.db"))
    client.access_token = "t"
    responses = [_Resp(_dump(3)), _Resp(_dump(1500))]
    calls = []

    async def get(url, **_k):
        calls.append(url)
        return responses[len(calls) - 1]

    client.client.get = get
    assert await client.refresh_instrument_cache() is False
    status = client.instrument_cache_status()
    assert status["source"] == "EMPTY" and status["usable"] is False and status["failures"] == 1
    assert status["last_dump_size"] == 3 and client.instrument_cache == {}          # nothing merged
    assert not (tmp_path / "nse_instrument_cache.json").exists()
    assert await client.ensure_instrument_cache() is True                           # retried, recovered
    assert len(calls) == 2 and client.instrument_cache_status()["source"] == "PROVIDER"
    assert await client.ensure_instrument_cache() is True and len(calls) == 2       # done for the day


@pytest.mark.asyncio
async def test_a_full_refresh_drops_symbols_the_provider_no_longer_lists(tmp_path):
    client = KiteClient(str(tmp_path / "cache.db"))
    client.access_token = "t"
    shared = client.instrument_cache
    shared["DELISTED"] = 1

    async def get(url, **_k):
        return _Resp(_dump(1200))

    client.client.get = get
    assert await client.refresh_instrument_cache() is True
    assert client.instrument_cache is shared and "DELISTED" not in shared and len(shared) == 1200


def _snapshot(tmp_path, saved_at):
    path = tmp_path / "nse_instrument_cache.json"
    path.write_text(json.dumps({"saved_at": saved_at, "tokens": {f"S{i}": i for i in range(1200)}}))


@pytest.mark.parametrize("saved_at", [
    datetime.now().isoformat(),                                              # naive
    (datetime.now(timezone.utc) + timedelta(days=10)).isoformat(),          # future
    "not-a-clock",
])
def test_bad_snapshot_clocks_are_refused_without_raising(tmp_path, saved_at):
    _snapshot(tmp_path, saved_at)
    client = KiteClient(str(tmp_path / "cache.db"))
    assert client._load_instrument_snapshot() is False
    assert client.instrument_cache == {} and client.instrument_cache_status()["usable"] is False


def test_a_current_aware_snapshot_still_loads(tmp_path):
    _snapshot(tmp_path, (datetime.now(timezone.utc) - timedelta(days=6, hours=23)).isoformat())
    client = KiteClient(str(tmp_path / "cache.db"))
    assert client._load_instrument_snapshot() is True and len(client.instrument_cache) == 1200


# --------------------------------------------------------------------------- O12-T1/T2/T3 spread tilt

def _t(day, hh, mm, ss=0):
    return datetime(2026, 10, day, hh, mm, ss)


def test_same_clock_signals_on_different_underlyings_do_not_cross_pair():
    nifty = Single(1, _t(13, 10, 0), "CE", 6000.0, -100.0, "NIFTY", "2026-10-13", _t(13, 11, 0))
    sensex = Single(2, _t(13, 10, 0, 5), "CE", 9000.0, 900.0, "SENSEX", "2026-10-15", _t(13, 11, 0))
    spread = Spread(9, _t(13, 10, 0, 6), "CE", 1, 3000.0, 200.0, "NIFTY", "2026-10-13", _t(13, 11, 0))
    outcomes = tilt.pair_and_score([nifty, sensex], [spread])
    (pair,) = [o for o in outcomes if o.single_id and o.spread_id]
    assert pair.single_id == 1                                   # the nearer SENSEX entry is not a match


def test_different_expiries_and_ambiguous_types_never_pair():
    single = Single(1, _t(13, 10, 0), "CE", 6000.0, -100.0, "NIFTY", "2026-10-13", _t(13, 11, 0))
    other_expiry = Spread(9, _t(13, 10, 0), "CE", 1, 3000.0, 200.0, "NIFTY", "2026-10-20", _t(13, 11, 0))
    unknown = Spread(10, _t(13, 10, 0), None, 1, 3000.0, 50.0, "NIFTY", None, _t(13, 11, 0))
    outcomes = tilt.pair_and_score([single], [other_expiry, unknown])
    assert not any(o.single_id and o.spread_id for o in outcomes)
    (gap,) = [o for o in outcomes if o.spread_id == 10]
    assert gap.state == "UNAVAILABLE" and gap.reason == "ambiguous_long_type"


def test_spread_identity_comes_from_the_bound_contract_legs():
    def leg(ot, qty, underlying="NIFTY", expiry="2026-10-13"):
        return {"opt_type": ot, "strike": 25000, "quantity": qty, "premium": 1.0,
                "contract": {"underlying": underlying, "expiry": expiry}}

    assert tilt._spread_identity(json.dumps([leg("CE", 1), leg("CE", -1)])) == {
        "long": "CE", "underlying": "NIFTY", "expiry": "2026-10-13", "identity": "contract"}
    assert tilt._spread_identity(json.dumps([leg("CE", 1), leg("CE", -1, expiry="2026-10-20")])) == {
        "unavailable": "mixed_contract_identity"}
    legacy = json.dumps([{"opt_type": "PE", "strike": 1, "quantity": 1, "premium": 1.0},
                         {"opt_type": "PE", "strike": 2, "quantity": -1, "premium": 1.0}])
    assert tilt._spread_identity(legacy)["identity"] == "legacy"


def test_frozen_lot_cap_ignores_the_runtime_setting(monkeypatch, tmp_path):
    from config import settings
    db = str(tmp_path / "cache.db")
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE fno_positions (id INTEGER, source TEXT, entry_time TEXT, opt_type TEXT, "
                     "max_loss_rupees REAL, initial_max_loss_rupees REAL, pnl REAL, status TEXT, "
                     "underlying TEXT, expiry TEXT, exit_time TEXT)")
        conn.execute("CREATE TABLE fno_dr_positions (id INTEGER, source TEXT, kind TEXT, legs_json TEXT, "
                     "lots INTEGER, max_loss_rs REAL, pnl REAL, cash_pnl REAL, status TEXT, opened_at TEXT, "
                     "closed_at TEXT)")
        legs = json.dumps([{"opt_type": "CE", "strike": 25000, "quantity": 1, "premium": 100.0,
                            "contract": {"underlying": "NIFTY", "expiry": "2026-10-13"}},
                           {"opt_type": "CE", "strike": 25100, "quantity": -1, "premium": 60.0,
                            "contract": {"underlying": "NIFTY", "expiry": "2026-10-13"}}])
        conn.execute("INSERT INTO fno_positions VALUES (1,'FNO_PAPER','2026-10-13T10:00:00+05:30','CE',"
                     "9000,NULL,-300,'CLOSED','NIFTY','2026-10-13','2026-10-13T11:00:00+05:30')")
        conn.execute("INSERT INTO fno_dr_positions VALUES (1,'FNO_PAPER','DEBIT_SPREAD',?,1,3000,210,200,"
                     "'CLOSED','2026-10-13T10:00:05+05:30','2026-10-13T12:00:00+05:30')", (legs,))
    monkeypatch.setattr(settings, "FNO_DR_MAX_LOTS", 9)
    report = tilt.spread_tilt_report(db)
    (row,) = report["forward_signals"]
    assert row["variant_lots"] == 3 and report["runtime_differs_from_manifest"] is True
    assert report["manifest"]["max_lots"] == 3 and len(report["manifest_fingerprint"]) == 16
    assert report["forward"]["paired_variant_net"] == 600.0


def test_open_sides_wait_and_drawdown_runs_in_close_order():
    open_single = Single(1, _t(13, 10, 0), "CE", 6000.0, None, "NIFTY", "2026-10-13")
    spread = Spread(9, _t(13, 10, 0), "CE", 1, 3000.0, 200.0, "NIFTY", "2026-10-13", _t(13, 11, 0))
    (o,) = tilt.pair_and_score([open_single], [spread])
    assert o.state == "OPEN" and o.single_id == 1 and o.actual is None     # not "unpaired"
    a = Single(2, _t(14, 10, 0), "CE", 3000.0, 500.0, "NIFTY", None, _t(14, 15, 0))
    b = Single(3, _t(14, 11, 0), "PE", 3000.0, -800.0, "NIFTY", None, _t(14, 12, 0))
    sa = Spread(10, _t(14, 10, 0), "CE", 1, 3000.0, 100.0, "NIFTY", None, _t(14, 14, 0))
    sb = Spread(11, _t(14, 11, 0), "PE", 1, 3000.0, -300.0, "NIFTY", None, _t(14, 13, 0))
    summary = tilt._summary(tilt.pair_and_score([a, b], [sa, sb]))
    # close order: b+sb (-1100 at 13:00) before a+sa (+600 at 15:00): drawdown 1100.
    assert summary["paired"] == 2 and summary["paired_actual_max_drawdown"] == 1100.0
    assert summary["paired_variant_max_drawdown"] == 600.0                 # 2 lots x -300


@pytest.mark.asyncio
async def test_hourly_report_reads_the_tilt_off_the_event_loop(monkeypatch, tmp_path):
    import fno_hourly_report as hr

    def slow_report(db_path, source="FNO_PAPER"):
        time.sleep(0.3)                                          # a locked SQLite read
        return {"forward": {"paired": 0, "open": 0}, "scoring_from": "2026-10-12"}

    monkeypatch.setattr(tilt, "spread_tilt_report", slow_report)
    ticks = []

    async def heartbeat():
        for _ in range(20):
            ticks.append(time.monotonic())
            await asyncio.sleep(0.01)

    db = str(tmp_path / "cache.db")
    report, _ = await asyncio.gather(
        hr.build_hourly_report(db, datetime(2026, 10, 12, 11, 0, tzinfo=hr.IST)), heartbeat())
    assert len(ticks) == 20 and max(b - a for a, b in zip(ticks, ticks[1:])) < 0.2
    assert "no closed paired signal" in report


@pytest.mark.asyncio
async def test_a_late_tilt_read_is_reported_unavailable(monkeypatch, tmp_path):
    import fno_hourly_report as hr
    monkeypatch.setattr(hr, "SPREAD_TILT_REPORT_TIMEOUT_SEC", 0.05)
    monkeypatch.setattr(tilt, "spread_tilt_report", lambda *a, **k: time.sleep(0.3))
    report = await hr.build_hourly_report(str(tmp_path / "cache.db"),
                                          datetime(2026, 10, 12, 11, 0, tzinfo=hr.IST))
    assert "report unavailable this hour" in report


# --------------------------------------------------------------------------- O12-S1 Smart exit date

def test_smart_health_joins_carried_exits_to_the_exit_date_total(tmp_path):
    import penny_smart_shadow as shadow
    ledger = str(tmp_path / "cache.db")
    path = shadow.smart_db_path(ledger)
    now = datetime(2026, 10, 12, 16, 0, tzinfo=shadow.IST)
    state = {"day": "2026-10-12", "positions": {}, "realized": -18.0134, "marked_pnl": -18.0134,
             "trades": [{}] * 10, "bankroll": 1922.17}
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE penny_smart_paper_state (policy TEXT PRIMARY KEY, state_json TEXT NOT NULL)")
        conn.execute("CREATE TABLE penny_smart_paper_events (event_id TEXT PRIMARY KEY, policy TEXT NOT NULL, "
                     "at TEXT NOT NULL, ticker TEXT NOT NULL, kind TEXT NOT NULL, payload_json TEXT NOT NULL)")
        conn.execute("INSERT INTO penny_smart_paper_state VALUES (?,?)", (shadow.SMART_VERSION, json.dumps(state)))
        nets = [5.0267, 1.5485] + [-18.0134 / 10] * 10
        for i, net in enumerate(nets):
            at = f"2026-10-12T{9 + i // 6:02d}:{15 + i:02d}:54+05:30"
            conn.execute("INSERT INTO penny_smart_paper_events VALUES (?,?,?,?,?,?)",
                         (f"e{i}", shadow.SMART_VERSION, at, f"T{i}", "EXIT_FILLED",
                          json.dumps({"net_pnl": net})))
        conn.execute("INSERT INTO penny_smart_paper_events VALUES (?,?,?,?,?,?)",
                     ("old", shadow.SMART_VERSION, "2026-10-09T14:00:00+05:30", "X", "EXIT_FILLED",
                      json.dumps({"net_pnl": -8.5})))
    snap = shadow.smart_exposure_snapshot(ledger, now=now)
    exit_date = snap["exit_date"]
    assert exit_date["closes"] == 12 and exit_date["carried_closes"] == 2
    assert exit_date["net"] == pytest.approx(-11.4382, abs=1e-4)
    assert exit_date["book_day_realized"] == pytest.approx(-18.0134) and snap["marked_pnl"] == -18.0134
