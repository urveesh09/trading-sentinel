"""Regression tests for the Oct 15 2026 Production audit (non-expiry items).

O15-N1 provider outage visibility, O15-H1 historical send gate, O15-M1
provably unsent partner sends retry, O15-R1 restart page for a held book and
the EDGE catch-up elapsed wait, O15-B2 stop-sample wording and the 15:15
held-path end, O15-D2 late notices dated.
"""
from __future__ import annotations

import asyncio
import socket
import time
from datetime import datetime, timedelta

import aiosqlite
import httpx
import pandas as pd
import pytest
import pytz

import lifecycle_receipts as lr
import partner_buyer as pb
from config import settings
from kite_client import EndpointBudget, KiteClient, SendWindowGate, transport_error_kind
from partner_bot import PartnerSendResult

IST = pytz.timezone("Asia/Kolkata")


def _epoch(h, m, s=0, day=15):
    return IST.localize(datetime(2026, 10, day, h, m, s)).timestamp()


# ---------------------------------------------------------------------------
# O15-N1: calls with no HTTP answer are counted, and form an outage
# ---------------------------------------------------------------------------

def _dns_error():
    try:
        raise socket.gaierror(-2, "Name or service not known")
    except socket.gaierror as cause:
        try:
            raise httpx.ConnectError("[Errno -2] Name or service not known") from cause
        except httpx.ConnectError as exc:
            return exc


def test_transport_failures_are_classified():
    assert transport_error_kind(_dns_error()) == "dns"
    assert transport_error_kind(httpx.ConnectError("[Errno 111] Connection refused")) == "connect"
    assert transport_error_kind(httpx.ConnectTimeout("timed out")) == "connect_timeout"
    assert transport_error_kind(httpx.ReadTimeout("read timed out")) == "timeout"
    assert transport_error_kind(httpx.RemoteProtocolError("closed")) == "other"


def test_an_outage_runs_from_the_first_failure_to_the_next_answer():
    wall = {"t": _epoch(14, 57)}
    budget = EndpointBudget(wall_clock=lambda: wall["t"])
    for _ in range(3):
        budget.record_transport("quote", _dns_error())
        wall["t"] += 60
    budget.record_transport("historical", httpx.ConnectTimeout("x"))
    current = budget.connectivity()["current"]
    assert current["failures"] == 4 and current["kinds"] == {"dns": 3, "connect_timeout": 1}
    wall["t"] = _epoch(15, 16)
    budget.record_answer()
    conn = budget.connectivity()
    assert conn["current"] is None
    assert conn["recent"][0]["end_epoch"] - conn["recent"][0]["start_epoch"] == 19 * 60
    snap = budget.snapshot()
    assert snap["quote"]["transport_errors"] == {"dns": 3}
    assert snap["quote"]["http_errors"] == {}                    # the Oct 15 blind spot
    assert snap["historical"]["transport_errors"] == {"connect_timeout": 1}


def test_an_http_error_answer_also_ends_an_outage():
    budget = EndpointBudget()
    budget.record_transport("quote", _dns_error())
    budget.record_status("quote", 503)          # the provider answered: the network is back
    budget.record_answer()
    assert budget.connectivity()["current"] is None


@pytest.fixture
def quote_client():
    client = KiteClient(db_path=":memory:")
    calls = {"n": 0, "fail": True}

    def handler(request):
        calls["n"] += 1
        if calls["fail"]:
            raise httpx.ConnectError("[Errno -2] Name or service not known", request=request)
        return httpx.Response(200, json={"data": {"1001": {"last_price": 10.0}}})

    client.client = httpx.AsyncClient(base_url="https://api.kite.trade", transport=httpx.MockTransport(handler))

    async def fast_acquire(*_a, **_k):
        return None

    client.limiter.acquire = fast_acquire
    client.quote_budget = None
    return client, calls


def test_quote_dns_failures_are_counted_and_recovery_closes_the_outage(quote_client, monkeypatch):
    client, calls = quote_client

    async def no_sleep(_sec):
        return None

    monkeypatch.setattr("kite_client.asyncio.sleep", no_sleep)
    assert asyncio.run(client.get_quote([1001])) == {}
    snap = client.endpoint_budget.snapshot()
    assert snap["quote"]["transport_errors"] == {"dns": 3}       # three attempts, no HTTP answer
    assert client.endpoint_budget.connectivity()["current"]["failures"] == 3
    calls["fail"] = False
    assert 1001 in asyncio.run(client.get_quote([1001]))
    assert client.endpoint_budget.connectivity()["current"] is None
    assert len(client.endpoint_budget.connectivity()["recent"]) == 1


# ---------------------------------------------------------------------------
# O15-N1: the outage pages once while it lasts and once when it ends
# ---------------------------------------------------------------------------

def _outage(start, failures=42, end=None):
    row = {"start_epoch": start, "failures": failures, "kinds": {"dns": failures},
           "last_failure_epoch": start + 60, "endpoints": {"quote": failures}}
    if end is not None:
        row["end_epoch"] = end
    return row


def test_a_market_hours_outage_pages_lost_then_restored(tmp_path):
    db = str(tmp_path / "cache.db")
    start = _epoch(14, 57)
    # 90 s in: not yet.
    assert lr.provider_outage_alerts(db, {"current": _outage(start), "recent": []}, start + 90) == []
    queued = lr.provider_outage_alerts(db, {"current": _outage(start), "recent": []}, start + 150,
                                       exposure_fn=lambda: {"overnight": 2, "Smart": None, "expiry": 0})
    assert queued == [f"provider-outage:{int(start)}:lost"]
    text = lr._load_outbox(db)[0]["text"]
    assert "Market data down since 14:57 IST" in text and "dns 42" in text
    assert "overnight 2, Smart unknown" in text and "expiry" not in text
    # Asking again does not page again.
    assert lr.provider_outage_alerts(db, {"current": _outage(start), "recent": []}, start + 210) == []
    # The outage ends at 15:16; the end page retires the undelivered start page.
    end = _epoch(15, 16)
    queued = lr.provider_outage_alerts(db, {"current": None, "recent": [_outage(start, end=end)]}, end + 30)
    assert queued == [f"provider-outage:{int(start)}:restored"]
    rows = {row["id"]: row for row in lr._load_outbox(db)}
    assert rows[f"provider-outage:{int(start)}:lost"]["state"] == "SUPERSEDED"
    assert "Market data back 15:16 IST after 19 min (14:57-15:16)" in rows[f"provider-outage:{int(start)}:restored"]["text"]
    assert lr.provider_outage_alerts(db, {"current": None, "recent": [_outage(start, end=end)]}, end + 90) == []


def test_short_or_after_hours_or_sparse_outages_do_not_page(tmp_path):
    db = str(tmp_path / "cache.db")
    start = _epoch(14, 57)
    assert lr.provider_outage_alerts(db, {"current": None,
                                          "recent": [_outage(start, end=start + 60)]}, start + 90) == []
    assert lr.provider_outage_alerts(db, {"current": _outage(start, failures=2), "recent": []},
                                     start + 600) == []
    night = _epoch(20, 0)
    assert lr.provider_outage_alerts(db, {"current": _outage(night), "recent": []}, night + 3600) == []
    assert lr._load_outbox(db) == []


@pytest.mark.asyncio
async def test_outage_pages_go_through_the_acknowledged_outbox(tmp_path):
    db = str(tmp_path / "cache.db")
    start = _epoch(14, 57)
    lr.provider_outage_alerts(db, {"current": _outage(start), "recent": []}, start + 150, exposure_fn=dict)
    sent = []

    async def post(text):
        sent.append(text)
        return "failed" if len(sent) == 1 else "delivered"

    assert await lr.deliver_restart_alerts(db, post, start + 150) == 1
    assert await lr.deliver_restart_alerts(db, post, start + 200) == 0
    assert len(sent) == 2 and lr._load_outbox(db)[0]["state"] == "DELIVERED"


# ---------------------------------------------------------------------------
# O15-H1: historical sends stay within 3 per second at the moment of sending
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_send_window_gate_never_lets_four_sends_into_one_window():
    gate = SendWindowGate(limit=3, window_sec=0.2)
    stamps = []

    async def send():
        await gate.before_send()
        stamps.append(time.monotonic())

    await asyncio.gather(*(send() for _ in range(7)))
    stamps.sort()
    for i in range(len(stamps) - 3):
        assert stamps[i + 3] - stamps[i] >= 0.2 - 1e-3
    assert gate.waits > 0


@pytest.mark.asyncio
async def test_a_late_scheduled_burst_is_spread_at_send_time():
    """Admissions spaced 1/3 s apart can reach the socket together when the
    loop is busy; the gate is the last step before the HTTP call."""
    now = {"t": 100.0}
    gate = SendWindowGate(limit=3, window_sec=1.05, clock=lambda: now["t"])
    for _ in range(3):
        await gate.before_send()
    slept = []

    async def fake_sleep(sec):
        slept.append(sec)
        now["t"] += sec

    import kite_client
    real = kite_client.asyncio.sleep
    kite_client.asyncio.sleep = fake_sleep
    try:
        await gate.before_send()
    finally:
        kite_client.asyncio.sleep = real
    assert slept and 1.05 <= sum(slept) + 1e-9 < 1.06


def test_the_client_gates_every_historical_call_site():
    import inspect
    import kite_client
    src = inspect.getsource(kite_client.KiteClient)
    assert src.count('await _historical_send_gate(self)\n            _record_endpoint(self, "historical")') == 3
    assert isinstance(KiteClient(db_path=":memory:").historical_gate, SendWindowGate)


# ---------------------------------------------------------------------------
# O15-M1: a send that never connected is retried; an ambiguous one is not
# ---------------------------------------------------------------------------

@pytest.fixture
def partner_on(monkeypatch):
    monkeypatch.setattr(settings, "PARTNER_BOT_ENABLED", True)
    monkeypatch.setattr(settings, "PARTNER_TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setattr(settings, "PARTNER_TELEGRAM_CHAT_ID", "12345678")


@pytest.mark.asyncio
@pytest.mark.parametrize("exc,state", [
    (httpx.ConnectError("[Errno -2] Name or service not known"), "unsent_connect"),
    (httpx.ConnectTimeout("connect timed out"), "unsent_connect"),
    (httpx.ReadTimeout("read timed out"), "ambiguous_timeout"),
    (httpx.RemoteProtocolError("server closed"), "ambiguous_transport"),
])
async def test_only_a_failure_to_connect_counts_as_unsent(partner_on, monkeypatch, exc, state):
    import partner_bot

    async def post_once(_client, _text):
        raise exc

    monkeypatch.setattr(partner_bot, "_post_once", post_once)
    result = await partner_bot.send_partner_result("Square off by 15:15")
    assert result.delivered is False and result.state == state


@pytest.mark.asyncio
async def test_the_15_10_reminder_is_retried_after_a_dns_failure(tmp_path, monkeypatch):
    """Oct 15: ConnectError -> manual_recovery_required -> EXPIRED_UNSENT."""
    import hedge_advisory
    from partner_manual_advisory import (
        PartnerAdvisoryProfile, dispatch_queued_management_update, pending_management_updates,
        run_intraday_session_lifecycle, save_partner_profile,
    )
    from tests.test_oct13_audit_fixes import _delivered
    from tests.test_partner_buyer import NOW
    monkeypatch.setattr(settings, "RESEARCH_ARCHIVE_ENABLED", False)
    monkeypatch.setattr(settings, "PARTNER_MANUAL_ADVISORY_SEND_UNQUALIFIED", True)
    monkeypatch.setattr(settings, "PARTNER_MANUAL_ADVISORY_ENABLED", True)
    monkeypatch.setattr(settings, "PARTNER_MANUAL_ADVISORY_DELIVERY_ENABLED", True)
    store = str(tmp_path / "advisory.db")
    profile = PartnerAdvisoryProfile(holding_period="INTRADAY")
    await save_partner_profile(store, profile, now=NOW)
    await _delivered(store, monkeypatch)
    reminder_at = NOW.replace(hour=15, minute=10, second=5)
    await run_intraday_session_lifecycle(store, now=reminder_at)
    outcomes = [PartnerSendResult(False, state="unsent_connect", error="ConnectError"),
                PartnerSendResult(True, message_id=7, state="acknowledged")]
    sends = []

    async def transport(text, *, kind):
        sends.append(text)
        return outcomes.pop(0)

    monkeypatch.setattr(hedge_advisory, "send_partner_result", transport)
    first_at = reminder_at + timedelta(seconds=1)
    [update] = await pending_management_updates(store, now=first_at)
    assert update["event_type"] == "SESSION_EXIT_REMINDER"
    assert not await dispatch_queued_management_update(store, update, now=first_at, clock=lambda: first_at)
    async with aiosqlite.connect(store) as db:
        detail = (await (await db.execute(
            "SELECT detail FROM partner_hedge_messages WHERE kind='manual_advisory_update'")).fetchone())[0]
    assert '"state": "retry_scheduled"' in detail and '"unsent_proven": true' in detail
    # Not before the 30 s backoff ...
    early = first_at + timedelta(seconds=10)
    [update] = await pending_management_updates(store, now=early)
    assert not await dispatch_queued_management_update(store, update, now=early, clock=lambda: early)
    assert len(sends) == 1
    # ... then once, inside the reminder's own freshness bound.
    retry_at = first_at + timedelta(seconds=45)
    [update] = await pending_management_updates(store, now=retry_at)
    assert await dispatch_queued_management_update(store, update, now=retry_at, clock=lambda: retry_at)
    assert len(sends) == 2 and sends[0] == sends[1]
    assert await pending_management_updates(store, now=retry_at + timedelta(seconds=60)) == []


@pytest.mark.asyncio
async def test_an_ambiguous_failure_still_goes_to_manual_recovery(tmp_path):
    import hedge_advisory as ha
    db = str(tmp_path / "advisory.db")
    now = IST.localize(datetime(2026, 10, 15, 15, 10, 5))
    token = await ha._claim(db, "manual_advisory_update", "u1", now=now, detail={"attempts": 1})
    assert token
    await ha._fail_claim(db, "manual_advisory_update", "u1", token,
                         detail={"delivery": {"state": "ambiguous_transport", "error": "ReadError"}}, now=now)
    async with aiosqlite.connect(db) as conn:
        detail = (await (await conn.execute("SELECT detail FROM partner_hedge_messages")).fetchone())[0]
    assert '"state": "manual_recovery_required"' in detail


# ---------------------------------------------------------------------------
# O15-R1: a short restart with a held book pages
# ---------------------------------------------------------------------------

def _receipt(overlap):
    return {"market_overlap_sec": overlap, "prior_heartbeat_ist": "2026-10-15T10:34:56+05:30",
            "cause": "host_or_vm_restarted"}


def test_a_short_market_restart_with_a_held_spread_pages():
    text = lr.restart_alert_text(_receipt(168.6), {"F&O spreads": 1, "Smart": 0})
    assert text is not None and "2.8-min market-hours gap" in text and "F&O spreads 1" in text


def test_a_short_restart_with_an_unreadable_book_pages():
    assert lr.restart_alert_text(_receipt(90.0), {"F&O spreads": 0, "Smart": None}) is not None


def test_a_short_restart_with_every_book_flat_stays_quiet():
    assert lr.restart_alert_text(_receipt(168.6), {"F&O spreads": 0, "Smart": 0}) is None
    assert lr.restart_alert_text(_receipt(30.0), {"F&O spreads": 1}) is None
    assert "6.0-min market-hours gap" in lr.restart_alert_text(_receipt(360.0), {"F&O spreads": 0})


# ---------------------------------------------------------------------------
# O15-R1: the EDGE token wait is bounded in elapsed time
# ---------------------------------------------------------------------------

class _Clock:
    def __init__(self, start):
        self.now = start

    def __call__(self):
        return self.now


@pytest.mark.asyncio
async def test_edge_catchup_wait_is_elapsed_time_not_poll_count():
    """Review probe: each 10 s sleep woke 60 s later; a 60 s budget lasted 360 s."""
    from penny_edge_orchestrator import run_edge_catchup
    clock = _Clock(IST.localize(datetime(2026, 10, 15, 10, 0)))
    sleeps = []

    async def late_sleep(sec):
        sleeps.append(sec)
        clock.now = clock.now + pd.Timedelta(seconds=60)

    async def scan():
        raise AssertionError("no token, no scan")

    outcome = await run_edge_catchup(now_fn=clock, token_ready=lambda: False, run_scan=scan,
                                     max_wait_sec=60, poll_sec=10, sleep=late_sleep)
    assert outcome == "no_token" and len(sleeps) == 1


@pytest.mark.asyncio
async def test_edge_catchup_still_ends_if_the_clock_does_not_move():
    from penny_edge_orchestrator import run_edge_catchup
    clock = _Clock(IST.localize(datetime(2026, 10, 15, 10, 0)))
    sleeps = []

    async def frozen_sleep(sec):
        sleeps.append(sec)

    async def scan():
        raise AssertionError("no token, no scan")

    assert await run_edge_catchup(now_fn=clock, token_ready=lambda: False, run_scan=scan,
                                  max_wait_sec=60, poll_sec=10, sleep=frozen_sleep) == "no_token"
    assert len(sleeps) == 6


# ---------------------------------------------------------------------------
# O15-B2 and the 15:15 held-path end in the buyer wrap
# ---------------------------------------------------------------------------

DAY = "2026-10-15"


def test_an_old_sample_is_not_called_the_stop_price():
    """Review probe: 10:00 ₹101, stop 11:45, 14:00 ₹200."""
    series = [(f"{DAY} 10:00:00", 101.0), (f"{DAY} 14:00:00", 200.0)]
    text = pb.premium_path(124.1, series, stopped_at=f"{DAY} 11:45:00", exit_by=f"{DAY} 15:15:00")
    assert "last seen ₹101 at 10:00" in text and "no price seen near the stop" in text
    assert "just before the stop" not in text
    assert "after exit (not held) peak ₹200" in text


def test_a_nearby_sample_is_shown_with_its_own_time():
    series = [(f"{DAY} 11:40:00", 99.0), (f"{DAY} 12:00:00", 130.0)]
    text = pb.premium_path(124.1, series, stopped_at=f"{DAY} 11:45:00")
    assert text.startswith("option ₹124.1 → ₹99 at 11:40, just before the stop (-20%)")


def test_no_sample_before_the_stop_gives_no_line():
    assert pb.premium_path(124.1, [(f"{DAY} 12:00:00", 130.0)], stopped_at=f"{DAY} 11:45:00") == ""


def test_prints_after_the_15_15_exit_are_not_the_cards_result():
    """Oct 15 card: last pre-deadline 14:57 ₹177.25, then 15:17 ₹169.90, 15:27 ₹171."""
    series = [(f"{DAY} 09:57:00", 122.35), (f"{DAY} 13:37:00", 263.0), (f"{DAY} 14:57:00", 177.25),
              (f"{DAY} 15:17:00", 169.9), (f"{DAY} 15:27:00", 171.0)]
    text = pb.premium_path(124.1, series, exit_by=f"{DAY} 15:15:00")
    assert text == "option ₹124.1 → peak ₹263 (+112%), ₹177.25 at 14:57 before the 15:15 exit (+43%)"
    assert "171" not in text
    # A stop's after-exit peak also ends at the deadline.
    stop = pb.premium_path(124.1, series + [(f"{DAY} 15:20:00", 400.0)], stopped_at=f"{DAY} 13:40:00",
                           exit_by=f"{DAY} 15:15:00")
    assert "peak ₹177.25" in stop and "400" not in stop


@pytest.mark.asyncio
async def test_the_wrap_passes_the_cards_deadline(tmp_path, monkeypatch):
    import fno_oi_store
    import partner_orchestrator as po
    card = {"event": "TARGET_ZONE", "event_time": "10:50", "event_at": f"{DAY}T10:50:00+05:30",
            "signal_at": f"{DAY}T09:56:00+05:30", "exit_by": f"{DAY}T15:15:00+05:30",
            "buyer_view": {"strike": 22850, "opt_type": "CE", "expiry": "2026-10-19", "ask": 124.1}}

    async def series(*_a, **_k):
        return [(f"{DAY} 13:37:00", 263.0), (f"{DAY} 14:57:00", 177.25), (f"{DAY} 15:27:00", 171.0)]

    monkeypatch.setattr(fno_oi_store, "strike_ltp_series", series)
    out = await po._buyer_card_outcome("NIFTY", DAY, card)
    assert "before the 15:15 exit" in out["premium"] and "171" not in out["premium"]
    # A legacy card without a stored deadline uses the configured one.
    legacy = {**card, "exit_by": None}
    out = await po._buyer_card_outcome("NIFTY", DAY, legacy)
    assert "before the 15:15 exit" in out["premium"]


# ---------------------------------------------------------------------------
# O15-D2: a notice delivered on a later day carries its own date
# ---------------------------------------------------------------------------

def test_a_late_notice_says_which_day_it_belongs_to():
    from edge_overnight_paper import _dated_for_delivery
    now = IST.localize(datetime(2026, 10, 15, 9, 0))
    late = _dated_for_delivery("NO ENTRY — quotes unavailable", "2026-10-14", now)
    assert late == "[Wed 14 Oct, delivered late] NO ENTRY — quotes unavailable"
    assert _dated_for_delivery("ENTRY", "2026-10-15", now) == "ENTRY"
    assert _dated_for_delivery("ENTRY", "garbage", now) == "ENTRY"


@pytest.mark.asyncio
async def test_flush_dates_only_the_sent_text_not_the_stored_row(tmp_path):
    import edge_overnight_paper as eop
    db = str(tmp_path / "cache.db")
    with eop._store(eop.overnight_db_path(db)) as conn:
        conn.execute("INSERT INTO edge_overnight_paper_notices (run_date, phase, message, created_at) "
                     "VALUES ('2026-10-14','ENTRY','NO ENTRY — quotes unavailable','2026-10-14T15:20:00+05:30')")
    sent = []

    async def send(text):
        sent.append(text)

    now = IST.localize(datetime(2026, 10, 15, 9, 0))
    assert await eop.flush_notices(send, db, now=now) == 1
    assert sent == ["[Wed 14 Oct, delivered late] NO ENTRY — quotes unavailable"]
    with eop._store(eop.overnight_db_path(db)) as conn:
        assert conn.execute("SELECT message FROM edge_overnight_paper_notices").fetchone()[0] \
            == "NO ENTRY — quotes unavailable"
