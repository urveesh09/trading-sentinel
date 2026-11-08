"""Auction contracts exercised on observed synthetic tapes, never alpha evidence."""
from datetime import datetime, time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
import sqlite3

import pytest

import penny_auction_forward as f
from config import settings


DAY = "2026-11-09"
NEXT = "2026-11-10"


def at(clock, day=DAY):
    return datetime.fromisoformat(day + "T" + clock).replace(tzinfo=f.IST)


def quote(clock="09:07:00", *, price=19., opening=19., volume=10000, bid=20., qty=10000, trade=None, day=DAY):
    return {"timestamp": at(clock, day), "last_trade_time": at(trade or clock, day),
            "last_price": price, "ohlc": {"close": 20., "open": opening}, "volume": volume,
            "depth": {"buy": [{"price": bid, "quantity": qty}],
                      "sell": [{"price": bid + .05, "quantity": 10000}]}}


@pytest.fixture
def cache(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "PENNY_AUCTION_FORWARD_ENABLED", True)
    monkeypatch.setattr(settings, "PENNY_SMART_V3_ENABLED", True)
    # Synthetic entry tests explicitly assume a usable indicative source.
    monkeypatch.setattr(settings, "PENNY_SMART_AUCTION_ENTRIES_ENABLED", True)
    monkeypatch.setattr(settings, "EDGE_OVERNIGHT_PAPER_ENABLED", True)
    monkeypatch.setattr(settings, "PENNY_SMART_V3_BANKROLL", 2000.)
    monkeypatch.setattr(settings, "EDGE_OVERNIGHT_PAPER_BANKROLL", 25000.)
    return str(tmp_path / "cache.db")


def smart(cache, q=None):
    f.capture_smart(cache, {"AAA": q or quote()}, {"AAA": (2e6, 1e5)}, {"AAA": 10000}, at("09:07:00"))


def read(cache):
    with f.store(cache) as c:
        return f.rows(c)


def phase(cache, name, quotes, clock, day=DAY):
    with f.store(cache) as c:
        f.apply_phase(c, name, quotes, at(clock, day))


def matched(cache, volume=10000):
    smart(cache)
    phase(cache, "MATCH", {"AAA": quote("09:12:00", trade="09:11:00", volume=volume)}, "09:12:00")


def overnight(cache):
    picks = [SimpleNamespace(ticker="AAA"), SimpleNamespace(ticker="BBB")]
    fillers = [SimpleNamespace(ticker="CCC")]
    f.capture_overnight(cache, day=DAY, decided=at("15:20:00"), picks=picks,
        nights={"AAA": .002, "BBB": .003}, features={"AAA": {"near_hi20": -.02}, "BBB": {"near_hi20": 0.}},
        fillers=fillers, late=None)


def test_smart_orders_are_paired_funded_and_frozen_before_clearing(cache):
    smart(cache)
    initial = read(cache)
    assert len(initial) == 2
    assert {r["order_quantity"] for r in initial} == {103}
    assert all(r["reserve"] <= 2000 and r["limit"] == 19.15 for r in initial)
    assert len({r["intent_at"] for r in initial}) == 1
    # Cheaper clearing cannot buy more than the previously funded order.
    phase(cache, "MATCH", {"AAA": quote("09:12:00", trade="09:11:00", opening=18.)}, "09:12:00")
    assert all(r["modeled_quantity"] == 103 and r["order_quantity"] == 103 for r in read(cache))


def test_matching_volume_partial_never_uses_continuous_volume(cache):
    matched(cache, volume=500)
    assert {r["modeled_quantity"] for r in read(cache)} == {50}
    assert {r["order_quantity"] for r in read(cache)} == {103}
    with pytest.raises(ValueError, match="phase window"):
        phase(cache, "MATCH", {"AAA": quote("09:16:00", volume=1000000)}, "09:16:00")
    assert {r["modeled_quantity"] for r in read(cache)} == {50}


@pytest.mark.parametrize("change", ["missing", "unsettled", "future", "crossday", "continuous", "zero"])
def test_invalid_auction_data_is_no_evidence_frees_the_reserve_and_reports_no_profit(cache, change):
    smart(cache)
    q = quote("09:12:00", trade="09:11:00")
    if change == "missing": q.pop("timestamp")
    if change == "unsettled": q["timestamp"] = at("08:59:59")
    if change == "future": q["timestamp"] = at("09:12:01")
    if change == "crossday": q["last_trade_time"] = at("09:11:00", NEXT)
    if change == "continuous": q["last_trade_time"] = at("09:15:00")
    if change == "zero": q["volume"] = 0
    phase(cache, "MATCH", {"AAA": q}, "09:12:00")
    assert all(r["status"] == f.NO_EVIDENCE for r in read(cache))
    for v in f.comparison(cache)["variants"].values():
        if v["intents"]:
            assert v["reserved_cash"] == 0 and v["complete_modeled_net"] is None and v["no_evidence"] == 1
    assert f.comparison(cache)["paired_smart"]["no_evidence_pairs"] == 1
    with f.store(cache) as c:
        assert f.free_cash(c, f.SMART[0]) == 2000


def test_an_auction_packet_from_before_the_buffer_is_evidence(cache):
    """The valid 09:10 matching result can be over 30s old in the buffer."""
    smart(cache)
    phase(cache, "MATCH", {"AAA": quote("09:10:10", trade="09:10:05")}, "09:12:00")
    assert {r["status"] for r in read(cache)} == {"OPEN"}


def test_a_missed_match_job_does_not_shut_the_smart_books(cache):
    smart(cache)                                 # 09:07 orders; the 09:12 job never ran
    f.capture_smart(cache, {"AAA": quote(day=NEXT)}, {"AAA": (2e6, 1e5)}, {"AAA": 10000}, at("09:07:00", NEXT))
    first, fresh = [r for r in read(cache) if r["day"] == DAY], [r for r in read(cache) if r["day"] == NEXT]
    assert {(r["status"], r["reason"]) for r in first} == {(f.NO_EVIDENCE, "evidence_phase_not_observed")}
    assert len(fresh) == 2 and {r["status"] for r in fresh} == {"PENDING"}


def test_the_preopen_quote_showing_only_the_previous_close_is_recorded(cache):
    """Production Nov 5-6: at 09:07 last_price was the previous close on 125 of 125 quotes."""
    smart(cache, quote(price=20.))               # previous close 20: no visible gap
    assert read(cache) == []
    assert f.comparison(cache)["smart_preopen_price"] == {
        "days": 1, "quotes": 1, "moved_from_previous_close": 0, "visible": False,
        "entry_enabled": True, "indicative_price_verified": False}


def test_open_over_frozen_limit_is_refused_and_no_fee_is_invented(cache):
    smart(cache)
    phase(cache, "MATCH", {"AAA": quote("09:12:00", trade="09:11:00", opening=19.2)}, "09:12:00")
    assert all(r["status"] == "REFUSED" and "costs" not in r for r in read(cache))
    with f.store(cache) as c:
        assert f.free_cash(c, f.SMART[0]) == 2000


def test_morning_exit_walks_bids_and_does_not_sell_close_arm(cache):
    matched(cache)
    q = quote("09:30:00", bid=20., qty=40)
    q["depth"]["buy"].append({"price": 19.9, "quantity": 100})
    phase(cache, "MORNING", {"AAA": q}, "09:30:00")
    control, morning = read(cache)
    assert control["status"] == "OPEN" and morning["status"] == "CLOSED"
    expected = (40 * 20 + 63 * 19.9) / 103
    assert morning["exit_price"] == pytest.approx(expected)
    assert morning["net"] == pytest.approx((expected - 19) * 103 - f.fees(19, expected, 103, True))


def test_insufficient_bids_and_circuit_carry_retry_with_delivery_charges(cache):
    matched(cache)
    phase(cache, "MORNING", {"AAA": quote("09:30:00", qty=10)}, "09:30:00")
    assert all(r["status"] == "OPEN" for r in read(cache))
    phase(cache, "MORNING", {"AAA": quote("09:30:00", day=NEXT, bid=18.)}, "09:30:00", NEXT)
    assert all(r["status"] == "CLOSED" for r in read(cache))
    assert all(r["costs"] == pytest.approx(f.fees(19., 18., 103, False)) for r in read(cache))


def test_frozen_costs_ignore_bypass_and_later_runtime_rate_changes(cache, monkeypatch):
    matched(cache)
    before = read(cache)[0]["cost_rates"]
    monkeypatch.setattr(settings, "PENNY_BROKERAGE_BYPASS", True)
    monkeypatch.setattr(settings, "PENNY_GST_PCT", .99)
    phase(cache, "MORNING", {"AAA": quote("09:30:00")}, "09:30:00")
    r = next(r for r in read(cache) if r["variant"] == f.SMART[1])
    assert r["costs"] > 0 and r["costs"] == f.fees(19., 20., 103, True, before)
    with f.store(cache) as c:
        assert f.free_cash(c, f.SMART[0]) < 1900


def test_postclose_control_uses_later_supported_volume_and_does_not_read_previous_close(cache):
    matched(cache)
    phase(cache, "MORNING", {"AAA": quote("09:30:00", bid=20.)}, "09:30:00")
    phase(cache, "POST_BASE", {"AAA": quote("15:51:00", price=20.5, volume=20000)}, "15:51:00")
    phase(cache, "POST_END", {"AAA": quote("16:03:00", trade="15:59:00", price=20.5, volume=40000)}, "16:03:00")
    r = next(r for r in read(cache) if r["variant"] == f.SMART[0])
    assert r["status"] == "CLOSED" and r["exit_price"] == 20.5 and r["actual_fill"] == "UNKNOWN"
    paired = f.comparison(cache)["paired_smart"]
    assert paired["resolved_pairs"] == 1 and paired["unresolved_pairs"] == 0
    assert paired["closed_pairs_morning_minus_close"] < 0


@pytest.mark.parametrize("bad", ["reset", "no_later_trade", "changed_price", "late_report"])
def test_postclose_missing_evidence_never_credits_an_exit(cache, bad):
    matched(cache)
    phase(cache, "POST_BASE", {"AAA": quote("15:51:00", price=20.5, volume=20000)}, "15:51:00")
    q = quote("16:03:00", trade="15:59:00", price=20.5, volume=40000)
    if bad == "reset": q["volume"] = 10000
    if bad == "no_later_trade": q["last_trade_time"] = at("15:50:00")
    if bad == "changed_price": q["last_price"] = 20.6
    if bad == "late_report": q["last_trade_time"] = at("16:01:00")
    phase(cache, "POST_END", {"AAA": q}, "16:03:00")
    assert next(r for r in read(cache) if r["variant"] == f.SMART[0])["status"] == "OPEN"


def test_overnight_v2_v3_ordering_and_funded_postclose_quantities(cache):
    overnight(cache)
    q = {t: quote("15:51:00", price=20., volume=20000) for t in ("AAA", "BBB", "CCC")}
    phase(cache, "POST_BASE", q, "15:51:00")
    records = read(cache)
    assert len(records) == 4 and all(r["intent_at"].endswith("15:51:00+05:30") for r in records)
    for v in f.OVERNIGHT:
        assert sum(r["reserve"] for r in records if r["variant"] == v) <= 25000
    before = {(r["variant"], r["ticker"]): r["order_quantity"] for r in records}
    end = {t: quote("16:03:00", trade="15:59:00", price=20., volume=100000) for t in q}
    phase(cache, "POST_END", end, "16:03:00")
    assert all(r["status"] == "OPEN" and r["modeled_quantity"] == before[r["variant"], r["ticker"]] for r in read(cache))
    # Auction exits require an actual earlier sell intention, not a reconstructed 09:17 sale.
    matching = {t: quote("09:12:00", trade="09:11:00", opening=21., day=NEXT) for t in q}
    phase(cache, "MATCH", matching, "09:12:00", NEXT)
    assert all(r["status"] == "OPEN" for r in read(cache))
    phase(cache, "EXIT_INTENTS", {}, "09:03:00", NEXT)
    phase(cache, "MATCH", matching, "09:12:00", NEXT)
    assert all(r["status"] == "CLOSED" and r["exit_price"] == 21 * .9995 for r in read(cache))


def test_an_unobserved_overnight_entry_is_no_evidence_and_frees_its_slots(cache):
    overnight(cache)
    phase(cache, "POST_BASE", {t: quote("15:51:00", price=20.) for t in ("AAA", "BBB")}, "15:51:00")
    phase(cache, "POST_END", {}, "16:03:00")
    assert all(r["status"] == f.NO_EVIDENCE for r in read(cache))
    with f.store(cache) as c:
        assert f.free_cash(c, f.OVERNIGHT[0]) == 25000
    f.capture_overnight(cache, day=NEXT, decided=at("15:20:00", NEXT), picks=[SimpleNamespace(ticker="AAA")],
                        nights={"AAA": .002}, features={"AAA": {"near_hi20": 0.}}, fillers=[], late=None)
    phase(cache, "POST_BASE", {"AAA": quote("15:51:00", price=20., day=NEXT)}, "15:51:00", NEXT)
    assert {r["status"] for r in read(cache) if r["day"] == NEXT} == {"PENDING"}


def test_a_missed_postclose_end_job_frees_the_overnight_books_next_session(cache):
    overnight(cache)
    phase(cache, "POST_BASE", {t: quote("15:51:00", price=20.) for t in ("AAA", "BBB")}, "15:51:00")
    phase(cache, "EXIT_INTENTS", {}, "09:03:00", NEXT)      # the 16:03 job never ran
    assert {(r["status"], r["reason"]) for r in read(cache)} == {(f.NO_EVIDENCE, "evidence_phase_not_observed")}


def test_no_trade_after_the_decision_is_measured_zero_capacity_not_missing_evidence(cache):
    overnight(cache)
    phase(cache, "POST_BASE", {t: quote("15:51:00", price=20.) for t in ("AAA", "BBB")}, "15:51:00")
    quiet = {t: quote("15:51:00", price=20.) for t in ("AAA", "BBB")}   # its last packet is the 15:51 one
    phase(cache, "POST_END", quiet, "16:03:00")
    assert {(r["status"], r["reason"]) for r in read(cache)} == {("REFUSED", "no_later_postclose_volume")}
    assert all(v["no_evidence"] == 0 for v in f.comparison(cache)["variants"].values())


# Production Nov 6, 2026 (edge_overnight_postclose_probe, read-only): the 15:32 CLOSE packet and the
# 16:03 POST packet of two of that day's picks. The 16:03 packets were 182 s and 189 s old.
NOV6 = "2026-11-06"
PROD = {
    "MTNL": dict(px=26.86, close=("15:31:22", "15:29:59", 83186522), post=("15:59:51", "15:59:50", 83200354)),
    "TTML": dict(px=39.77, close=("15:31:21", "15:29:59", 185082326), post=("15:59:58", "15:59:04", 185092017)),
}


def prod_packet(name, which):
    ts, trade, volume = PROD[name][which]
    return {"timestamp": at(ts, NOV6), "last_trade_time": at(trade, NOV6), "last_price": PROD[name]["px"],
            "volume": volume, "ohlc": {"open": PROD[name]["px"], "close": PROD[name]["px"]}}


def test_production_postclose_packets_are_evidence_at_their_real_age(cache):
    """The first version demanded a 16:03 packet under 30 s old; every real one is minutes old."""
    picks = [SimpleNamespace(ticker=t) for t in PROD]
    f.capture_overnight(cache, day=NOV6, decided=at("15:20:07", NOV6), picks=picks,
                        nights={t: .002 for t in PROD}, features={t: {"near_hi20": 0.} for t in PROD},
                        fillers=[], late=None)
    for name in PROD:                            # the old live-session rule rejects the real packets
        assert f.quality(prod_packet(name, "post"), at("16:03:00", NOV6),
                         trade_window=(time(15, 50), time(16))) == "stale_or_future_provider"
    # The base packet stands for a 15:51 read with no post-close trade yet (a constructed base).
    phase(cache, "POST_BASE", {t: prod_packet(t, "close") for t in PROD}, "15:51:00", NOV6)
    phase(cache, "POST_END", {t: prod_packet(t, "post") for t in PROD}, "16:03:00", NOV6)
    got = {(r["variant"], r["ticker"]): r for r in read(cache)}
    for variant in ("OVERNIGHT_V2", "OVERNIGHT_V3"):
        mtnl, ttml = got[variant, "MTNL"], got[variant, "TTML"]
        assert mtnl["later_volume"] == 13832 and ttml["later_volume"] == 9691
        # 1% of the later post-close volume, never more than the funded order.
        assert (mtnl["status"], mtnl["modeled_quantity"]) == ("OPEN", 138)
        assert (ttml["status"], ttml["modeled_quantity"]) == ("OPEN", 96)
        assert mtnl["order_quantity"] > 138 and ttml["order_quantity"] > 96


def test_unresolved_smart_halts_both_paired_entry_arms_next_day(cache):
    matched(cache)
    f.capture_smart(cache, {"AAA": quote(day=NEXT)}, {"AAA": (2e6, 1e5)}, {"AAA": 10000}, at("09:07:00", NEXT))
    assert len(read(cache)) == 2


def test_capture_deadline_and_bad_preopen_clocks_are_not_backdated(cache):
    f.capture_smart(cache, {"AAA": quote()}, {"AAA": (2e6, 1e5)}, {"AAA": 10000}, at("09:08:00"))
    assert f.comparison(cache)["status"] == "not_collected"
    smart(cache, quote("09:06:00"))
    assert read(cache) == []


@pytest.mark.asyncio
async def test_collection_restart_safety_bounded_batch_and_zero_order_calls(cache, monkeypatch):
    import edge_overnight_paper as eop
    smart(cache)
    get = AsyncMock(return_value={"AAA": quote("09:12:00", trade="09:11:00")})
    monkeypatch.setattr(eop, "_quotes", get)
    kite = MagicMock()
    r = await f.collect(kite, "MATCH", cache, now=at("09:12:00"))
    assert r["requested"] == 1
    assert (await f.collect(kite, "MATCH", cache, now=at("09:12:10")))["status"] == "repeat"
    get.assert_awaited_once_with(kite, ["AAA"])
    kite.assert_not_called()
    assert kite.mock_calls == []


@pytest.mark.asyncio
async def test_quote_receipt_crossing_window_is_rejected(cache, monkeypatch):
    import edge_overnight_paper as eop
    smart(cache)
    class Clock(datetime):
        calls = 0
        @classmethod
        def now(cls, tz):
            cls.calls += 1
            return at("09:12:00" if cls.calls == 1 else "09:15:00")
    monkeypatch.setattr(f, "datetime", Clock)
    # stamp still accepts actual datetimes through its parser.
    monkeypatch.setattr(f, "stamp", lambda x: x if isinstance(x, datetime) else None)
    monkeypatch.setattr(eop, "_quotes", AsyncMock(return_value={}))
    assert (await f.collect(object(), "MATCH", cache))["status"] == "quote_crossed_deadline"
    assert all(r["status"] == "PENDING" for r in read(cache))


@pytest.mark.asyncio
async def test_disabled_forward_is_zero_io(cache, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "PENNY_AUCTION_FORWARD_ENABLED", False)
    assert await f.collect(object(), "MATCH", cache, at("09:12:00")) == {"status": "disabled"}
    assert list(tmp_path.iterdir()) == []


def test_read_missing_and_damaged_store_never_creates_or_breaks_legacy_route(cache):
    assert f.comparison(cache)["status"] == "not_collected"
    from pathlib import Path
    Path(f.store_path(cache)).write_bytes(b"invalid sqlite")
    assert f.comparison(cache)["status"] == "unavailable"


@pytest.mark.asyncio
async def test_new_scheduler_jobs_have_their_own_calendar_and_enable_gates(cache, monkeypatch):
    import main
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    monkeypatch.setattr(main, "is_trading_day", AsyncMock(return_value=False))
    monkeypatch.setattr(main.kite, "access_token", "test")
    collect = AsyncMock()
    monkeypatch.setattr(f, "collect", collect)
    scheduler = AsyncIOScheduler(timezone=f.IST)
    def close_startup(coro):
        coro.close()
        return MagicMock(done=lambda: True)
    monkeypatch.setattr("scheduler_setup.asyncio.get_running_loop", lambda: SimpleNamespace(create_task=close_startup))
    main.register_penny_scheduler_jobs(scheduler)
    jobs = [j for j in scheduler.get_jobs() if j.id.startswith("penny_auction_")]
    assert len(jobs) == 5
    for job in jobs:
        await job.func(**job.kwargs)
    collect.assert_not_awaited()
    monkeypatch.setattr(main, "is_trading_day", AsyncMock(return_value=True))
    for job in jobs:
        await job.func(**job.kwargs)
    assert collect.await_count == 5


@pytest.mark.asyncio
async def test_classic_cnc_retirement_prevents_entry_scan(cache, monkeypatch):
    import main
    monkeypatch.setattr(settings, "PENNY_CLASSIC_CNC_ENTRIES_ENABLED", False)
    monkeypatch.setattr(main, "is_trading_day", AsyncMock(return_value=True))
    scanner = MagicMock()
    monkeypatch.setattr(main, "_get_penny_scanner", scanner)
    await main.run_penny_connors_scan()
    scanner.assert_not_called()


@pytest.mark.asyncio
async def test_original_preopen_job_captures_forward_inputs_without_changing_legacy_book(cache, monkeypatch):
    import penny_smart_v3 as native
    monkeypatch.setattr(native, "universe", lambda kite: ["AAA"])
    monkeypatch.setattr(native, "daily_medians", lambda *a: {"AAA": (2e6, 1e5)})
    monkeypatch.setattr(native, "thin_estimates", lambda *a: ({"AAA": 10000}, {"AAA": "test"}))
    monkeypatch.setattr(native, "_quotes", AsyncMock(return_value={"AAA": quote()}))
    result = await native.run_preopen(object(), cache, at("09:07:00"))
    assert result["picks"] == ["AAA"]
    assert len(read(cache)) == 2
    with sqlite3.connect(native.store_path(cache)) as c:
        row = c.execute("SELECT status,plan_shares,shares FROM sv3_trades").fetchone()
    assert row == ("DECIDED", None, None)


@pytest.mark.asyncio
async def test_authenticated_experiment_addition_is_read_only(cache, monkeypatch):
    import main
    import penny_smart_v3 as native
    from httpx import ASGITransport, AsyncClient
    monkeypatch.setattr(settings, "DB_PATH", cache)
    monkeypatch.setattr(native, "comparison", lambda *a: {"legacy_marker": True})
    async with AsyncClient(transport=ASGITransport(app=main.app), base_url="http://test") as client:
        assert (await client.get("/experiments/penny-smart-v3")).status_code == 403
        response = await client.get("/experiments/penny-smart-v3", headers={"X-Internal-Secret": settings.INTERNAL_API_SECRET})
    assert response.status_code == 200
    assert response.json()["legacy_marker"] is True
    assert response.json()["auction_forward"]["status"] == "not_collected"
    from pathlib import Path
    assert not Path(f.store_path(cache)).exists()
