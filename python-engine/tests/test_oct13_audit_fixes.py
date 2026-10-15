"""Regression tests for the Oct 13 2026 Production audit (non-expiry items).

O13-B1 terminal buyer ideas, O13-B2 flow-pulse retry, O13-B3 exchange fees,
O13-B4 sampled-outcome wording, O13-Q1 send-time quote spacing, O13-Q2
dispatcher cancellation, O13-P1 Penny exit provenance, O13-R1 lifecycle
receipts, and the Penny report / buyer fallback / unlisted-symbol fixes.
"""
from __future__ import annotations

import asyncio
import json
import sqlite3
import time
from datetime import datetime, timezone

import aiosqlite
import pandas as pd
import pytest
import pytz

import lifecycle_receipts as lr
import partner_buyer as pb
from config import settings
from kite_client import QuoteBatchCancelled, QuoteBudget
from partner_manual_advisory import (
    CLOSED_INVALIDATED, load_advisory_diagnostics, pending_management_updates, queue_management_updates,
    run_intraday_session_lifecycle,
)
from tests.test_oct12_audit_fixes import _Resp, _budget_client
from tests.test_partner_buyer import NOW, _persist

IST = pytz.timezone("Asia/Kolkata")


# ---------------------------------------------------------------------------
# O13-B1: an invalidated idea is closed for good
# ---------------------------------------------------------------------------

@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "RESEARCH_ARCHIVE_ENABLED", False)
    monkeypatch.setattr(settings, "PARTNER_MANUAL_ADVISORY_SEND_UNQUALIFIED", True)
    return str(tmp_path / "advisory.db")


async def _delivered(store, monkeypatch):
    _c, _v, stored = await _persist(store, True, monkeypatch)
    async with aiosqlite.connect(store) as db:
        await db.execute("UPDATE partner_advisory_ideas SET status='DELIVERED_ACKNOWLEDGED' WHERE advisory_id=?",
                         (stored["advisory_id"],))
        await db.commit()
    return stored["advisory_id"]


async def _idea_status(store, advisory_id):
    async with aiosqlite.connect(store) as db:
        return (await (await db.execute("SELECT status FROM partner_advisory_ideas WHERE advisory_id=?",
                                        (advisory_id,))).fetchone())[0]


@pytest.mark.asyncio
async def test_stop_closes_the_idea_and_a_later_target_is_never_queued(store, monkeypatch):
    advisory_id = await _delivered(store, monkeypatch)
    stop = await queue_management_updates(store, underlying="NIFTY", observed_underlying=22470.0,
                                          observed_at=NOW.replace(hour=11, minute=45, second=0))
    assert [q["event_type"] for q in stop] == ["INVALIDATION"]
    assert "Idea closed" in stop[0]["rendered_update"]
    assert await _idea_status(store, advisory_id) == CLOSED_INVALIDATED
    # Oct 13: the market recovered past target at 14:40 -> nothing for this idea.
    later = await queue_management_updates(store, underlying="NIFTY", observed_underlying=22900.0,
                                           observed_at=NOW.replace(hour=14, minute=40, second=0))
    assert later == []
    assert await run_intraday_session_lifecycle(store, now=NOW.replace(hour=15, minute=10, second=5)) == []


@pytest.mark.asyncio
async def test_the_stop_itself_still_dispatches_for_a_closed_idea(store, monkeypatch):
    await _delivered(store, monkeypatch)
    observed = NOW.replace(hour=11, minute=45, second=0)
    await queue_management_updates(store, underlying="NIFTY", observed_underlying=22470.0, observed_at=observed)
    pending = await pending_management_updates(store, now=observed.replace(second=40))
    assert [p["event_type"] for p in pending] == ["INVALIDATION"]


@pytest.mark.asyncio
async def test_a_queued_target_expires_once_the_stop_is_seen(store, monkeypatch):
    advisory_id = await _delivered(store, monkeypatch)
    target_at = NOW.replace(hour=11, minute=40, second=0)
    target = await queue_management_updates(store, underlying="NIFTY", observed_underlying=22900.0,
                                            observed_at=target_at)
    assert [q["event_type"] for q in target] == ["TARGET_ZONE"]
    stop_at = NOW.replace(hour=11, minute=45, second=0)
    await queue_management_updates(store, underlying="NIFTY", observed_underlying=22470.0, observed_at=stop_at)
    pending = await pending_management_updates(store, now=stop_at.replace(second=30))
    assert [p["event_type"] for p in pending] == ["INVALIDATION"]
    async with aiosqlite.connect(store) as db:
        row = await (await db.execute(
            "SELECT status,status_reason FROM partner_advisory_updates WHERE advisory_id=? AND event_type='TARGET_ZONE'",
            (advisory_id,))).fetchone()
    assert row == ("EXPIRED_UNSENT", "idea_closed_invalidated")


@pytest.mark.asyncio
async def test_rows_from_before_the_terminal_status_are_closed_on_the_next_pass(store, monkeypatch):
    advisory_id = await _delivered(store, monkeypatch)
    await queue_management_updates(store, underlying="NIFTY", observed_underlying=22470.0,
                                   observed_at=NOW.replace(hour=11, minute=45, second=0))
    async with aiosqlite.connect(store) as db:                # as written by the Oct 13 build
        await db.execute("UPDATE partner_advisory_ideas SET status='DELIVERED_ACKNOWLEDGED' WHERE advisory_id=?",
                         (advisory_id,))
        await db.commit()
    later = await queue_management_updates(store, underlying="NIFTY", observed_underlying=22900.0,
                                           observed_at=NOW.replace(hour=14, minute=40, second=0))
    assert later == [] and await _idea_status(store, advisory_id) == CLOSED_INVALIDATED


@pytest.mark.asyncio
async def test_final_authorizer_refuses_any_update_after_a_recorded_stop(store, monkeypatch):
    """Belt and braces at the send boundary, even if a row slipped through."""
    import hedge_advisory
    from partner_manual_advisory import PartnerAdvisoryProfile, save_partner_profile
    monkeypatch.setattr(settings, "PARTNER_MANUAL_ADVISORY_ENABLED", True)
    monkeypatch.setattr(settings, "PARTNER_MANUAL_ADVISORY_DELIVERY_ENABLED", True)
    profile = PartnerAdvisoryProfile(holding_period="INTRADAY")
    await save_partner_profile(store, profile, now=NOW)
    advisory_id = await _delivered(store, monkeypatch)
    stop_at = NOW.replace(hour=11, minute=45, second=0)
    await queue_management_updates(store, underlying="NIFTY", observed_underlying=22470.0, observed_at=stop_at)
    late_at = NOW.replace(hour=11, minute=46, second=0)
    await hedge_advisory.init_hedge_advisory_db(store)
    async with aiosqlite.connect(store) as db:                # a stale live row + a late target
        await db.execute("UPDATE partner_advisory_ideas SET status='DELIVERED_ACKNOWLEDGED' WHERE advisory_id=?",
                         (advisory_id,))
        await db.execute(
            "INSERT INTO partner_advisory_updates(update_id,advisory_id,event_type,observed_at,observed_underlying,"
            "rendered_update,status,created_at,updated_at) VALUES('late',?,'TARGET_ZONE',?,22900,'Book profit',"
            "'QUEUED',?,?)", (advisory_id, late_at.isoformat(), late_at.isoformat(), late_at.isoformat()))
        stop_id = (await (await db.execute(
            "SELECT update_id,rendered_update FROM partner_advisory_updates WHERE event_type='INVALIDATION'"
        )).fetchone())
        for key in ("late", stop_id[0]):
            await db.execute("INSERT INTO partner_hedge_messages(kind,dedup_key,sent_at,delivered,claim_token) "
                             "VALUES('manual_advisory_update',?,?,0,'tok')", (key, late_at.isoformat()))
        await db.commit()

    def detail(update_id, event, observed, text):
        return {"phase": "manual_update_v1", "update_id": update_id, "advisory_id": advisory_id,
                "profile_id": profile.profile_id, "observed_at": observed.isoformat(),
                "event_type": event, "rendered_text": text}

    authorize = hedge_advisory._authorize_dispatch
    assert await authorize(store, "manual_advisory_update", "late", "tok",
                           detail("late", "TARGET_ZONE", late_at, "Book profit"),
                           now=late_at.replace(second=20)) is False
    assert await authorize(store, "manual_advisory_update", stop_id[0], "tok",
                           detail(stop_id[0], "INVALIDATION", stop_at, stop_id[1]),
                           now=stop_at.replace(second=40)) is True


@pytest.mark.asyncio
async def test_diagnostics_count_a_stopped_card_as_delivered(store, monkeypatch):
    await _delivered(store, monkeypatch)
    await queue_management_updates(store, underlying="NIFTY", observed_underlying=22470.0,
                                   observed_at=NOW.replace(hour=11, minute=45, second=0))
    diag = await load_advisory_diagnostics(store)
    assert diag["by_index"]["NIFTY"]["delivered"] == 1


def test_delivery_blocker_report_treats_closed_and_retired_cards_as_delivered():
    import partner_delivery_blockers as blockers
    assert {"CLOSED_INVALIDATED", "RETIRED_SESSION_END", "DELIVERED_ACKNOWLEDGED"} <= blockers.DELIVERED_STATUSES


def test_wrap_ends_the_held_premium_path_at_the_stop():
    series = [("2026-10-13 09:55:00", 263.8), ("2026-10-13 11:00:00", 240.0),
              ("2026-10-13 11:45:00", 190.0), ("2026-10-13 14:40:00", 340.0)]
    text = pb.premium_path(263.8, series, stopped_at="2026-10-13 11:45:00")
    assert text.startswith("option ₹263.8 → ₹190 at the stop (-28%)")
    assert "after exit (not held) peak ₹340" in text
    assert "peak ₹340 (+29%), last" not in text
    # A target-first card keeps the whole path.
    assert pb.premium_path(263.8, series).startswith("option ₹263.8 → peak ₹340")


@pytest.mark.asyncio
async def test_wrap_outcome_without_an_event_says_not_seen(monkeypatch):
    import partner_orchestrator as po
    out = await po._buyer_card_outcome("NIFTY", "2026-10-13", {"time": "09:55", "direction": "LONG"})
    assert out["outcome"] == "no level seen (5-min samples)"


# ---------------------------------------------------------------------------
# Buyer fallback never sends a SELL leg
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_missing_buyer_view_falls_back_to_one_option_not_the_spread(store, monkeypatch):
    from partner_manual_advisory import PartnerAdvisoryProfile, persist_candidate
    from tests.test_partner_buyer import _setup
    monkeypatch.setattr(settings, "PARTNER_BUYER_MESSAGES", True)
    candidate, _snap = _setup()
    stored = await persist_candidate(store, candidate, PartnerAdvisoryProfile(holding_period="INTRADAY"),
                                     now=NOW, queue_for_delivery=True, buyer_view=None)
    card = stored["rendered_card"]
    assert stored["status"] == "QUEUED"
    assert "BUY NIFTY 22550 CE" in card and "SELL" not in card and "Structure:" not in card
    assert "fut" in card and "Loss at SL" not in card


# ---------------------------------------------------------------------------
# O13-B3: SENSEX options are charged the BSE schedule
# ---------------------------------------------------------------------------

def test_sensex_option_costs_use_bfo_and_match_the_audit():
    from fno_costs import calc_fno_costs, options_exchange_for
    assert options_exchange_for("SENSEX") == "BFO" and options_exchange_for("nifty") == "NFO"
    assert options_exchange_for("UNKNOWN") == "NFO"
    nfo = calc_fno_costs(304.05, 321.55, 20)
    bfo = calc_fno_costs(304.05, 321.55, 20, exchange="BFO")
    assert nfo == pytest.approx(62.28941497216, abs=1e-6)       # recorded on call 42
    assert bfo == pytest.approx(61.84206092416, abs=1e-6)       # audit's same-fill BSE figure


def test_buyer_loss_at_stop_uses_the_contract_exchange():
    assert pb.max_loss_per_lot(274.40, 193.45, 0.75, 20) == pytest.approx(1691.07, abs=0.01)
    assert pb.max_loss_per_lot(274.40, 193.45, 0.75, 20, exchange="BFO") == pytest.approx(1690.74, abs=0.01)


def test_position_fee_reserve_follows_the_underlying_exchange():
    from fno_costs import calc_fno_costs
    from fno_positions import _with_entry_baselines
    sensex = _with_entry_baselines({"entry_premium": 310.25, "qty": 20, "underlying": "SENSEX"})
    nifty = _with_entry_baselines({"entry_premium": 310.25, "qty": 20, "underlying": "NIFTY"})
    assert sensex["risk_fee_reserve_rupees"] == pytest.approx(calc_fno_costs(310.25, 0.0, 20, exchange="BFO"))
    assert nifty["risk_fee_reserve_rupees"] == pytest.approx(calc_fno_costs(310.25, 0.0, 20))
    assert sensex["risk_fee_reserve_rupees"] < nifty["risk_fee_reserve_rupees"]


def test_single_leg_exit_and_admission_pass_the_exchange():
    import inspect
    import fno_orchestrator
    src = inspect.getsource(fno_orchestrator)
    assert 'exchange=spec.segment if spec is not None else "NFO"' in src
    assert "calc_fno_costs(ask, 0.0, qty, exchange=options_exchange_for(underlying))" in src


# ---------------------------------------------------------------------------
# O13-Q1 / Q2: quote spacing at the send, and no stranded callers
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_a_delayed_batch_task_cannot_send_inside_the_quote_interval():
    """The audit's probe: batch 1 is admitted, its task starts late, batch 2
    is admitted on time. Admission spacing alone sent both ~50 ms apart."""
    budget = QuoteBudget(rate=10.0)                       # 100 ms interval
    sends: list[float] = []
    first = asyncio.Event()

    original_run = budget._run

    async def late_run(fetch, batch, merged, lane, admitted_at):
        if not first.is_set():
            first.set()
            await asyncio.sleep(0.15)                       # the stalled task start
        await original_run(fetch, batch, merged, lane, admitted_at)

    budget._run = late_run

    async def fetch(merged, lane):
        await budget.before_send()
        sends.append(time.monotonic())
        return {t: {"t": t} for t in merged}, {}

    one = asyncio.create_task(budget.submit(fetch, [1], "normal"))
    await first.wait()
    two = asyncio.create_task(budget.submit(fetch, [2], "normal"))
    await asyncio.wait_for(asyncio.gather(one, two), timeout=3)
    assert len(sends) == 2
    assert sends[1] - sends[0] >= 0.1 - 1e-3
    assert budget.snapshot()["send_gate_waits"] >= 1


@pytest.mark.asyncio
async def test_admission_waits_for_the_last_actual_send():
    budget = QuoteBudget(rate=20.0)                       # 50 ms interval
    budget.limiter()
    budget._last_send = time.monotonic()
    waited = await budget.admit(None, "management")
    assert waited >= 0.05 - 2e-3


@pytest.mark.asyncio
async def test_every_numeric_and_keyed_attempt_passes_the_send_gate(tmp_path, monkeypatch):
    client = _budget_client(tmp_path, rate=50.0)
    gates = []
    original = client.quote_budget.before_send

    async def counted():
        gates.append(1)
        return await original()

    monkeypatch.setattr(client.quote_budget, "before_send", counted)
    calls = []

    async def fake_get(path, params=None):
        calls.append(1)
        if len(calls) == 1:
            return _Resp(data={})                           # empty -> numeric retry
        return _Resp(data={str(v): {"last_price": 1.0} for _n, v in params})

    monkeypatch.setattr(client.client, "get", fake_get)
    await client.get_quote_with_timing([11])
    assert len(gates) == len(calls) == 2
    await client.get_quote_by_instruments_with_timing({12: "NSE:X"})
    assert len(gates) == len(calls) == 3


class _BlockedLimiter:
    def __init__(self, error=None):
        self.error = error
        self.entered = asyncio.Event()

    async def acquire(self, priority=None):
        self.entered.set()
        if self.error is not None:
            raise self.error
        await asyncio.Event().wait()


@pytest.mark.asyncio
async def test_cancelling_the_dispatcher_during_admission_releases_queued_callers():
    budget = QuoteBudget(rate=10.0)
    shared = _BlockedLimiter()

    async def fetch(merged, lane):
        return {}, {}

    callers = [asyncio.create_task(budget.submit(fetch, [1], "normal", shared=shared)),
               asyncio.create_task(budget.submit(fetch, [2], "bulk", shared=shared))]
    await shared.entered.wait()
    budget._dispatcher.cancel()
    results = await asyncio.wait_for(asyncio.gather(*callers, return_exceptions=True), timeout=2)
    assert all(isinstance(r, QuoteBatchCancelled) for r in results)
    assert budget.snapshot()["cancelled_queued"] == 2
    # A later request starts a fresh dispatcher.
    budget._limiter = None
    result, _timing = await asyncio.wait_for(budget.submit(lambda m, l: _ok(m), [3], "normal"), timeout=2)
    assert result == {3: 1}


async def _ok(merged):
    return {t: 1 for t in merged}, {}


@pytest.mark.asyncio
async def test_a_dispatcher_error_reaches_every_queued_caller():
    budget = QuoteBudget(rate=10.0)
    shared = _BlockedLimiter(error=RuntimeError("limiter broke"))

    async def fetch(merged, lane):
        return {}, {}

    caller = asyncio.create_task(budget.submit(fetch, [1], "normal", shared=shared))
    with pytest.raises(RuntimeError, match="limiter broke"):
        await asyncio.wait_for(caller, timeout=2)


@pytest.mark.asyncio
async def test_a_cancelled_caller_does_not_cancel_its_neighbour():
    budget = QuoteBudget(rate=50.0)

    async def fetch(merged, lane):
        await asyncio.sleep(0.01)
        return {t: t for t in merged}, {}

    mine = asyncio.create_task(budget.submit(fetch, [1], "normal"))
    other = asyncio.create_task(budget.submit(fetch, [2], "normal"))
    await asyncio.sleep(0)
    mine.cancel()
    result, _timing = await asyncio.wait_for(other, timeout=2)
    assert result == {2: 2}


# ---------------------------------------------------------------------------
# O13-B2: failed pulses keep their cap and retry soon
# ---------------------------------------------------------------------------

def _state(**kw):
    base = {"count": 0, "failed": 0, "last_delivered_at": None, "last_attempt_at": None, "last_ok": None}
    base.update(kw)
    return base


def test_failed_pulses_do_not_consume_the_success_cap():
    import partner_orchestrator as po
    now = datetime(2026, 10, 13, 12, 0)
    # Six failures, none delivered: still allowed after the short backoff.
    state = _state(failed=6, last_attempt_at="2026-10-13 11:50:00", last_ok=False)
    assert po._pulse_blocked(state, now) is False
    # Right after a failure: short backoff only.
    assert po._pulse_blocked(_state(failed=1, last_attempt_at="2026-10-13 11:58:00", last_ok=False), now) is True
    # The 30-minute gap counts from the last DELIVERED pulse.
    assert po._pulse_blocked(_state(count=1, last_delivered_at="2026-10-13 11:45:00",
                                    last_attempt_at="2026-10-13 11:50:00", last_ok=False), now) is True
    assert po._pulse_blocked(_state(count=settings.PARTNER_FLOW_PULSE_DAILY_CAP), now) is True
    assert po._pulse_blocked(_state(failed=po.PULSE_MAX_FAILED_ATTEMPTS), now) is True


@pytest.mark.asyncio
async def test_pulse_state_round_trips_delivered_and_failed_counts(tmp_path, monkeypatch):
    import partner_orchestrator as po
    db = str(tmp_path / "p.db")
    now = IST.localize(datetime(2026, 10, 13, 12, 0))
    await po.init_partner_db(db)
    await po._record(db, "flow_pulse", "NIFTY", False,
                     detail={"day": "2026-10-13", "count": 2, "failed": 3, "last_delivered_at": "2026-10-13 11:00:00"},
                     now=now)
    state = await po._pulse_state(db, "NIFTY", "2026-10-13")
    assert state["count"] == 2 and state["failed"] == 3 and state["last_ok"] is False
    assert state["last_delivered_at"] == "2026-10-13 11:00:00"
    assert await po._pulse_count_today(db, "NIFTY", "2026-10-13") == 2
    assert (await po._pulse_state(db, "NIFTY", "2026-10-14"))["count"] == 0


# ---------------------------------------------------------------------------
# Penny reports and exit provenance
# ---------------------------------------------------------------------------

def _penny_db(path):
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE bankroll_ledger (id INTEGER PRIMARY KEY, timestamp TEXT, event_type TEXT, ticker TEXT, "
                "pnl REAL, notes TEXT, source TEXT)")
    con.execute("CREATE TABLE positions (ticker TEXT, entry_date TEXT, entry_price REAL, shares INTEGER, "
                "status TEXT, source TEXT, exit_date TEXT, r_multiple REAL, product_type TEXT)")
    return con


def test_daily_attribution_reads_r_from_the_settled_position(tmp_path):
    from penny_daily_attribution import build_daily_attribution
    db = str(tmp_path / "a.db")
    con = _penny_db(db)
    stamp = "2026-10-13T08:08:11.126840+00:00"
    con.execute("INSERT INTO bankroll_ledger(timestamp,event_type,ticker,pnl,notes,source) VALUES(?,?,?,?,?,?)",
                (stamp, "TRADE_CLOSED", "UNITEDPOLY", -9.0411, "confirmed_exit:protective_stop_paper", "PENNY_PAPER"))
    con.execute("INSERT INTO positions VALUES('UNITEDPOLY','2026-10-13T08:06:38+00:00',51.92,0,'CLOSED_TIME',"
                "'PENNY_PAPER',?,-3.7206172839,'MIS')", (stamp,))
    con.commit()
    con.close()
    body = build_daily_attribution(db, now=datetime(2026, 10, 13, 10, 0, tzinfo=timezone.utc), source="PENNY_PAPER")
    assert "Avg R: -3.72" in body


def test_daily_attribution_says_na_when_no_r_is_known(tmp_path):
    from penny_daily_attribution import build_daily_attribution
    db = str(tmp_path / "a.db")
    con = _penny_db(db)
    con.execute("INSERT INTO bankroll_ledger(timestamp,event_type,ticker,pnl,notes,source) VALUES(?,?,?,?,?,?)",
                ("2026-10-13T08:08:11+00:00", "TRADE_CLOSED", "X", -1.0, "confirmed_exit:smart_eod", "PENNY_PAPER"))
    con.commit()
    con.close()
    body = build_daily_attribution(db, now=datetime(2026, 10, 13, 10, 0, tzinfo=timezone.utc), source="PENNY_PAPER")
    assert "Avg R: n/a" in body


@pytest.mark.asyncio
async def test_hourly_report_shows_the_paper_fill_not_the_signal_close(tmp_path):
    from penny_hourly_report import PennyHourlyReport
    from penny_signal_log import init_penny_signal_db
    db = str(tmp_path / "h.db")
    await init_penny_signal_db(db)
    async with aiosqlite.connect(db) as con:
        await con.execute("INSERT INTO penny_signals(ticker,leg,close,stop_loss,target_1,shares,scanned_at,reject_reason) "
                          "VALUES('UNITEDPOLY','MIS',52.92,51.65,55.46,9,'2026-10-13T08:06:30+00:00',NULL)")
        await con.execute("CREATE TABLE IF NOT EXISTS positions (ticker TEXT, entry_date TEXT, entry_price REAL)")
        await con.execute("INSERT INTO positions VALUES('UNITEDPOLY','2026-10-13T08:06:38.625733+00:00',51.92)")
        await con.commit()
    body = await PennyHourlyReport(db).build_report(
        now=datetime(2026, 10, 13, 8, 30, tzinfo=timezone.utc), regime="PR1_CALM", open_positions=[],
        deployed_capital=0.0, unrealised_pnl=0.0, kill_switch_active=False, circuit_blocks=0)
    assert "UNITEDPOLY MIS x9 @ 51.92 (signal 52.92)" in body


@pytest.mark.asyncio
async def test_paper_exit_records_reference_price_and_model_decrement():
    from penny_executor import PAPER_EXIT_FILL_MODEL, PennyExecutor
    from penny_models import PennyLeg
    executor = PennyExecutor(object(), paper_mode=True, tick_size_lookup=lambda _t: 0.01)
    result = await executor.execute_exit("UNITEDPOLY", PennyLeg.MIS, 9, reference_price=51.49)
    assert result["fill_price"] == pytest.approx(50.97)
    assert result["reference_price"] == 51.49 and result["fill_model"] == PAPER_EXIT_FILL_MODEL
    assert result["model_decrement_per_share"] == pytest.approx(0.52)


# ---------------------------------------------------------------------------
# O13-R1: lifecycle receipts
# ---------------------------------------------------------------------------

def test_clock_jump_tells_host_sleep_from_a_stalled_process():
    assert lr.clock_jump(0, 0, 60, 60, period_sec=60) is None
    sleep = lr.clock_jump(0, 0, 5738, 60, period_sec=60)                # wall ran, monotonic did not
    assert sleep["kind"] == "host_suspend" and sleep["suspended_sec"] == 5678.0
    stall = lr.clock_jump(0, 0, 400, 400, period_sec=60)
    assert stall["kind"] == "thread_stall" and stall["stall_sec"] == 340.0


def test_market_overlap_counts_only_session_minutes():
    start = IST.localize(datetime(2026, 10, 13, 10, 5, 52)).timestamp()
    end = IST.localize(datetime(2026, 10, 13, 11, 40, 11)).timestamp()
    assert lr.market_overlap_sec(start, end) == pytest.approx(5659, abs=1)
    night = IST.localize(datetime(2026, 10, 12, 21, 0)).timestamp()
    morning = IST.localize(datetime(2026, 10, 13, 8, 0)).timestamp()
    assert lr.market_overlap_sec(night, morning) == 0.0
    weekend = IST.localize(datetime(2026, 10, 17, 10, 0)).timestamp()      # Saturday
    assert lr.market_overlap_sec(weekend, weekend + 3600) == 0.0


def test_clean_shutdown_then_startup_receipt(tmp_path, monkeypatch):
    db = str(tmp_path / "cache.db")
    with open(lr.heartbeat_path(db), "w") as fh:
        json.dump({"ts_epoch": time.time() - 120, "boot_id": "old"}, fh)
    lr.mark_clean_shutdown(db, "old")
    with open(lr.heartbeat_path(db)) as fh:
        prior = json.load(fh)
    receipt = lr.startup_receipt(db, prior, time.time(), "new")
    assert receipt["cause"] == "clean_shutdown" and receipt["prior_boot_id"] == "old"
    kinds = [e["kind"] for e in lr.recent_events(db)]
    assert kinds == ["clean_shutdown", "startup"]


def test_unclean_market_gap_pages_with_open_exposure(tmp_path, monkeypatch):
    db = str(tmp_path / "cache.db")
    gap_start = IST.localize(datetime(2026, 10, 13, 10, 5, 52)).timestamp()
    now = IST.localize(datetime(2026, 10, 13, 11, 40, 11)).timestamp()
    lr.record_event(db, "host_suspend", suspended_sec=5600.0, boot_id="old")
    monkeypatch.setattr(lr, "host_uptime_sec", lambda: 86400.0)
    receipt = lr.startup_receipt(db, {"ts_epoch": gap_start, "boot_id": "old"}, now, "new")
    assert receipt["cause"] == "unclean_stop" and receipt["prior_host_suspend_sec"] == 5600.0
    text = lr.restart_alert_text(receipt, {"F&O singles": 0, "F&O spreads": 1, "equity/Penny": 0})
    assert "94-min market-hours gap" in text and "F&O spreads 1" in text and "Host sleep" in text
    assert lr.restart_alert_text({**receipt, "market_overlap_sec": 60.0}, {}) is None


def test_a_vm_restart_is_named(tmp_path, monkeypatch):
    monkeypatch.setattr(lr, "host_uptime_sec", lambda: 100.0)
    assert lr.classify_restart({"ts_epoch": 1}, 5000.0, 100.0) == "host_or_vm_restarted"
    assert lr.classify_restart(None, None, None) == "first_boot_or_no_heartbeat"


# ---------------------------------------------------------------------------
# Liquidity filter: catalogue-unlisted names drop once, quietly
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_liquidity_filter_drops_unlisted_symbols_without_fetching(monkeypatch):
    import main
    monkeypatch.setattr(settings, "UNIVERSE_MIN_ADV_CRORE", 1.0)
    fetched = []

    class Kite:
        instrument_cache = {f"S{i}": i for i in range(1000)} | {"GOOD": 1}

        async def get_historical(self, ticker, a, b):
            fetched.append(ticker)
            return pd.DataFrame({"close": [100.0] * 30, "volume": [1e6] * 30})

    universe = pd.DataFrame({"tradingsymbol": ["GOOD", "HEG", "HFCL"], "exchange": ["NSE"] * 3})
    kept = await main._filter_by_liquidity(universe, Kite(), pd.Timestamp("2026-10-13"))
    assert fetched == ["GOOD"] and list(kept["tradingsymbol"]) == ["GOOD"]


# ---------------------------------------------------------------------------
# EDGE startup catch-up waits for the token and runs once a day
# ---------------------------------------------------------------------------

def test_edge_catchup_waits_for_token_and_skips_a_completed_day():
    import inspect
    import scheduler_setup
    src = inspect.getsource(scheduler_setup.register_penny_scheduler_jobs)
    assert "_startup_loop.create_task(_run_penny_edge_scan_catchup())" in src
    assert "while not _main.kite.access_token and waited < max_wait_sec" in src
    assert "if _edge_scan_done_today(today):" in src
    # The mark is written only after a scan returns, never on a skip.
    body = src[src.index("async def _run_penny_edge_scan_safe"):src.index("def _edge_scan_state_path")]
    assert body.index("_mark_edge_scan_done(today)") > body.index("summary = await run_penny_edge_scan(")
