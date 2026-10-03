"""F0-R2: one dispatch owner per reservation and evidence-backed entry outcomes."""
import asyncio
from datetime import date, datetime, timezone

import aiosqlite
import pytest

from fno_executor import FnoExecutor
from fno_dr_book import init_dr_db
from fno_positions import init_fno_positions_db, insert_position_with_risk_reservation
from fno_shared_risk import (
    SharedFnoRiskPolicy, claim_shared_fno_entry_dispatch, init_shared_fno_risk_db,
    reconcile_shared_fno_entry_dispatch, reserve_shared_fno_risk,
    resolve_shared_fno_entry_dispatch, resolve_shared_fno_risk_reservation,
    shared_fno_risk_view,
)
from performance import init_ledger
from tests.test_fno_r1_fee_exposure import _position

SOURCE = "FNO_PAPER"
POOL = 50_000.0
DAY = date(2026, 10, 5)
AMOUNT = 8_000.0
OBSERVED = datetime(2026, 10, 5, 6, 0, tzinfo=timezone.utc)   # 11:30 IST on DAY


async def _ready(db_path):
    await init_ledger(db_path)
    await init_fno_positions_db(db_path)
    await init_dr_db(db_path)
    await init_shared_fno_risk_db(db_path)


async def _reserve(db_path, key="entry-a", book="SINGLE_LEG"):
    return await reserve_shared_fno_risk(
        db_path, source=SOURCE, pool_rs=POOL, reservation_key=key, book=book,
        worst_case_cash_rs=AMOUNT, entry_day_ist=DAY, policy=SharedFnoRiskPolicy(),
        observed_at=OBSERVED,
    )


async def _claim(db_path, key="entry-a", book="SINGLE_LEG", day=DAY):
    return await claim_shared_fno_entry_dispatch(
        db_path, reservation_key=key, source=SOURCE, book=book, pool_rs=POOL,
        entry_day_ist=day, policy=SharedFnoRiskPolicy(), observed_at=OBSERVED,
    )


async def _rows(db_path, sql, args=()):
    async with aiosqlite.connect(db_path) as db:
        return await (await db.execute(sql, args)).fetchall()


# ---- one owner ---------------------------------------------------------------

@pytest.mark.asyncio
async def test_identical_concurrent_callers_get_exactly_one_dispatch_claim(db_path):
    await _ready(db_path)
    first, second = await asyncio.gather(_reserve(db_path), _reserve(db_path))
    assert first.allowed and second.allowed            # an idempotent read receipt...
    claims = await asyncio.gather(*(_claim(db_path) for _ in range(4)))
    granted = [c for c in claims if c.granted]         # ...but only one right to dispatch
    assert len(granted) == 1 and granted[0].owner
    assert {c.reason for c in claims if not c.granted} == {"dispatch_already_claimed:DISPATCHING"}
    assert await _rows(db_path, "SELECT state FROM fno_entry_dispatches") == [("DISPATCHING",)]


@pytest.mark.asyncio
async def test_halted_retry_of_a_reserved_entry_is_denied_before_dispatch(db_path):
    await _ready(db_path)
    assert (await _reserve(db_path)).allowed
    async with aiosqlite.connect(db_path) as db:   # same-day -3,100 > 6% of 50,000
        await db.execute(
            "INSERT INTO bankroll_ledger (timestamp,event_type,pnl,source) VALUES (?,?,?,?)",
            ("2026-10-05T05:00:00+00:00", "TRADE_CLOSED", -3_100.0, SOURCE),
        )
        await db.commit()
    retry = await _reserve(db_path)
    assert retry.allowed and retry.reason == "already_reserved"   # receipt only
    claim = await _claim(db_path)
    assert not claim.granted and claim.reason.startswith("daily_loss_halt")
    assert await _rows(db_path, "SELECT * FROM fno_entry_dispatches") == []
    state, reason = (await _rows(
        db_path, "SELECT state,resolution_reason FROM fno_risk_reservations"))[0]
    assert state == "RELEASED" and reason.startswith("policy_denied_before_dispatch:daily_loss_halt")


@pytest.mark.asyncio
async def test_orphaned_dispatch_after_restart_keeps_capital_until_verified_reconciliation(db_path):
    await _ready(db_path)
    await _reserve(db_path)
    assert (await _claim(db_path)).granted          # process "dies" after claiming
    again = await _claim(db_path)
    assert not again.granted and again.reason == "dispatch_already_claimed:DISPATCHING"
    view = await shared_fno_risk_view(db_path, SOURCE, POOL)
    assert view.reserved_worst_case_cash_rs == AMOUNT
    assert view.unresolved_entry_dispatch_count == 1
    # The generic resolver cannot free a claimed reservation.
    assert not await resolve_shared_fno_risk_reservation(
        db_path, reservation_key="entry-a", state="RELEASED", resolution_reason="timer")
    # Reconciliation needs an operator and verifying evidence.
    good = {"account_id": "USER01", "checked_at": "2026-10-05T06:00:00+00:00",
            "matching_orders": []}
    assert not await reconcile_shared_fno_entry_dispatch(
        db_path, reservation_key="entry-a", operator="", outcome="no_order_verified", evidence=good)
    assert not await reconcile_shared_fno_entry_dispatch(
        db_path, reservation_key="entry-a", operator="ops", outcome="no_order_verified",
        evidence={**good, "matching_orders": [{"order_id": "X"}]})
    assert not await reconcile_shared_fno_entry_dispatch(
        db_path, reservation_key="entry-a", operator="ops", outcome="no_order_verified",
        evidence={**good, "checked_at": "2026-10-05T06:00:00"})
    assert await reconcile_shared_fno_entry_dispatch(
        db_path, reservation_key="entry-a", operator="ops", outcome="no_order_verified", evidence=good)
    after = await shared_fno_risk_view(db_path, SOURCE, POOL)
    assert after.reserved_worst_case_cash_rs == 0.0 and after.unresolved_entry_dispatch_count == 0
    assert await _rows(db_path, "SELECT state,outcome,operator FROM fno_entry_dispatches") == [
        ("RELEASED", "no_order_verified", "ops")]


# ---- typed outcomes ----------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("outcome,evidence,applied,released", [
    ("rejected", {"dispatch_certainty": "BROKER_REJECTED", "order_id": None}, "rejected", True),
    ("no_dispatch", {"dispatch_certainty": "NOT_SENT", "order_id": None}, "no_dispatch", True),
    ("zero_fill_verified", {"order_id": "O1", "final_status": "CANCELLED", "filled_quantity": 0},
     "zero_fill_verified", True),
    # unverifiable "releases" are applied as unknown and retained
    ("zero_fill_verified", {"order_id": "O1", "final_status": "CANCELLED", "filled_quantity": None},
     "unknown", False),
    ("zero_fill_verified", {"order_id": "O1", "final_status": "OPEN", "filled_quantity": 0},
     "unknown", False),
    ("rejected", {"dispatch_certainty": "AMBIGUOUS", "order_id": None}, "unknown", False),
    ("no_dispatch", {}, "unknown", False),
    ("partial", {"order_id": "O1", "final_status": "CANCELLED", "filled_quantity": 25},
     "partial", False),
    ("unknown", {"order_id": "O1", "cancel_error": "boom"}, "unknown", False),
])
async def test_only_verified_outcomes_release_capacity(db_path, outcome, evidence, applied, released):
    await _ready(db_path)
    await _reserve(db_path)
    claim = await _claim(db_path)
    result = await resolve_shared_fno_entry_dispatch(
        db_path, reservation_key="entry-a", owner=claim.owner, outcome=outcome, evidence=evidence)
    assert result == applied
    view = await shared_fno_risk_view(db_path, SOURCE, POOL)
    assert view.reserved_worst_case_cash_rs == (0.0 if released else AMOUNT)
    state = (await _rows(db_path, "SELECT state FROM fno_entry_dispatches"))[0][0]
    assert state == ("RELEASED" if released else "UNRESOLVED")
    # applied exactly once, and never by another owner
    assert await resolve_shared_fno_entry_dispatch(
        db_path, reservation_key="entry-a", owner=claim.owner, outcome="unknown", evidence={}) is None


@pytest.mark.asyncio
async def test_wrong_owner_cannot_resolve(db_path):
    await _ready(db_path)
    await _reserve(db_path)
    await _claim(db_path)
    assert await resolve_shared_fno_entry_dispatch(
        db_path, reservation_key="entry-a", owner="intruder", outcome="no_dispatch",
        evidence={"dispatch_certainty": "NOT_SENT"}) is None
    assert (await shared_fno_risk_view(db_path, SOURCE, POOL)).reserved_worst_case_cash_rs == AMOUNT


@pytest.mark.asyncio
async def test_position_requires_a_claim_and_an_unresolved_fill_can_later_be_recorded(db_path):
    await _ready(db_path)
    await _reserve(db_path)
    with pytest.raises(RuntimeError, match="not_consumed"):
        await insert_position_with_risk_reservation(db_path, reservation_key="entry-a", **_position())
    assert await _rows(db_path, "SELECT COUNT(*) FROM fno_positions") == [(0,)]
    claim = await _claim(db_path)
    assert await resolve_shared_fno_entry_dispatch(
        db_path, reservation_key="entry-a", owner=claim.owner, outcome="unknown",
        evidence={"order_id": "O1"}) == "unknown"
    # The operator later finds the fill and records it through the normal writer.
    position_id = await insert_position_with_risk_reservation(
        db_path, reservation_key="entry-a", **_position())
    assert await _rows(db_path, "SELECT state,position_ref FROM fno_entry_dispatches") == [
        ("FILLED", f"fno_position:{position_id}")]
    assert await _rows(db_path, "SELECT state FROM fno_risk_reservations") == [("CONSUMED",)]
    async with aiosqlite.connect(db_path) as db:
        with pytest.raises(aiosqlite.IntegrityError, match="dispatch evidence is immutable"):
            await db.execute("UPDATE fno_entry_dispatches SET state='RELEASED'")
        with pytest.raises(aiosqlite.IntegrityError, match="dispatch evidence is immutable"):
            await db.execute("DELETE FROM fno_entry_dispatches")


@pytest.mark.asyncio
async def test_unresolved_claim_cannot_return_to_dispatching(db_path):
    await _ready(db_path)
    await _reserve(db_path)
    claim = await _claim(db_path)
    await resolve_shared_fno_entry_dispatch(
        db_path, reservation_key="entry-a", owner=claim.owner, outcome="partial",
        evidence={"order_id": "O1"})
    async with aiosqlite.connect(db_path) as db:
        with pytest.raises(aiosqlite.IntegrityError, match="dispatch evidence is immutable"):
            await db.execute("UPDATE fno_entry_dispatches SET state='DISPATCHING'")


# ---- live executor evidence -------------------------------------------------

class _Broker:
    def __init__(self, *, place=None, place_exc=None, histories=(), cancel_exc=None,
                 history_exc=None):
        self.place, self.place_exc = place, place_exc
        self.histories, self.cancel_exc, self.history_exc = list(histories), cancel_exc, history_exc
        self.cancelled = []

    async def place_order(self, **kwargs):
        if self.place_exc:
            raise self.place_exc
        return self.place

    async def order_history(self, order_id):
        if self.history_exc:
            raise self.history_exc
        return self.histories.pop(0) if len(self.histories) > 1 else self.histories[0]

    async def cancel_order(self, order_id):
        self.cancelled.append(order_id)
        if self.cancel_exc:
            raise self.cancel_exc


def _executor(broker):
    ex = FnoExecutor(kite=broker, paper_mode=False, source_tag="FNO_LIVE")
    ex.fill_timeout_sec = 0.0           # skip the fill wait: go straight to verification
    ex.poll_interval_sec = 0.0
    return ex


def _state(status, filled=None, average=None):
    return [{"status": status, "filled_quantity": filled, "average_price": average,
             "order_timestamp": "2026-10-05 10:00:00"}]


@pytest.mark.asyncio
@pytest.mark.parametrize("place,expected", [
    ({"order_id": None, "dispatch_certainty": "NOT_SENT"}, "no_dispatch"),
    ({"order_id": None, "dispatch_certainty": "BROKER_REJECTED"}, "rejected"),
    ({"order_id": None, "dispatch_certainty": "AMBIGUOUS"}, "unknown"),
    ({"order_id": None}, "unknown"),                       # a client that cannot say
])
async def test_entry_without_order_id_is_classified_by_dispatch_certainty(place, expected):
    out = await _executor(_Broker(place=place)).execute_entry("NIFTYX", 75, 100.0)
    assert out["status"] == expected and out["evidence"]["order_id"] is None


@pytest.mark.asyncio
async def test_transport_exception_after_send_is_unknown_not_rejected():
    out = await _executor(_Broker(place_exc=TimeoutError("read timeout"))).execute_entry("X", 75, 100.0)
    assert out["status"] == "unknown"
    assert out["evidence"]["dispatch_certainty"] == "AMBIGUOUS"


@pytest.mark.asyncio
@pytest.mark.parametrize("history,kwargs,expected", [
    (_state("CANCELLED", 0), {}, "zero_fill_verified"),
    (_state("REJECTED", 0), {}, "zero_fill_verified"),
    (_state("CANCELLED", 25), {}, "partial"),
    (_state("COMPLETE", 75, 101.5), {}, "filled"),               # filled during the cancel
    (_state("COMPLETE", 75, None), {}, "unknown"),               # filled, price unknown
    (_state("CANCELLED", None), {}, "unknown"),                  # zero fill not proven
    (_state("OPEN", 0), {"cancel_exc": RuntimeError("cancel failed")}, "unknown"),
    (_state("OPEN", 0), {"history_exc": RuntimeError("no history")}, "unknown"),
])
async def test_unfilled_entry_is_verified_against_the_final_order_state(history, kwargs, expected):
    broker = _Broker(place={"order_id": "O1", "dispatch_certainty": "ACCEPTED"},
                     histories=[history], **kwargs)
    out = await _executor(broker).execute_entry("NIFTYX", 75, 100.0)
    assert out["status"] == expected
    assert broker.cancelled == ["O1"]
    if expected == "filled":
        assert out["fill_price"] == 101.5
    if "cancel_exc" in kwargs:
        assert out["evidence"]["cancel_error"].startswith("RuntimeError")


@pytest.mark.asyncio
async def test_executor_zero_fill_evidence_is_accepted_by_the_release_check(db_path):
    """Contract between the two halves: real executor evidence releases; partial does not."""
    await _ready(db_path)
    for key, history, released in (("k-zero", _state("CANCELLED", 0), True),
                                   ("k-part", _state("CANCELLED", 25), False)):
        await _reserve(db_path, key)
        claim = await _claim(db_path, key)
        out = await _executor(_Broker(place={"order_id": "O1", "dispatch_certainty": "ACCEPTED"},
                                      histories=[history])).execute_entry("X", 75, 100.0)
        applied = await resolve_shared_fno_entry_dispatch(
            db_path, reservation_key=key, owner=claim.owner, outcome=out["status"],
            evidence=out["evidence"])
        assert (applied == "zero_fill_verified") is released
    view = await shared_fno_risk_view(db_path, SOURCE, POOL)
    assert view.reserved_worst_case_cash_rs == AMOUNT     # only the partial is retained


# ---- orchestrator: a second identical attempt never reaches the executor -----

@pytest.mark.asyncio
async def test_orchestrator_does_not_redispatch_an_unresolved_entry(monkeypatch, db_path):
    from tests.test_fno_orchestrator import FakeKite, NOW, _breakout_bars, _build_book, _quote_table
    import fno_instruments as fi
    import fno_orchestrator

    book = _build_book()
    monkeypatch.setattr(fi, "_instruments", book)
    calls = []

    async def ambiguous_entry(self, tradingsymbol, qty, ask):
        calls.append(tradingsymbol)
        return {"status": "unknown", "order_id": "O1", "fill_price": None,
                "evidence": {"order_id": "O1", "final_status": None}}

    monkeypatch.setattr(fno_orchestrator.FnoExecutor, "execute_entry", ambiguous_entry)
    kite = FakeKite(_breakout_bars(), _quote_table(book, NOW))
    await fno_orchestrator.run_fno_tick(kite, db_path=db_path, regime="REGIME_1_NORMAL", now_ist=NOW)
    await fno_orchestrator.run_fno_tick(kite, db_path=db_path, regime="REGIME_1_NORMAL", now_ist=NOW)
    assert len(calls) == 1
    single = await _rows(db_path, "SELECT d.state, r.state FROM fno_entry_dispatches d "
                                  "JOIN fno_risk_reservations r USING (reservation_key) "
                                  "WHERE d.book='SINGLE_LEG'")
    assert single == [("UNRESOLVED", "RESERVED")]
    assert await _rows(db_path, "SELECT COUNT(*) FROM fno_positions") == [(0,)]


# ---- broker client: dispatch certainty -------------------------------------

def _kite(monkeypatch, handler, *, halted=False):
    import httpx
    import kite_client
    from kite_client import KiteClient

    verdict = type("Verdict", (), {"allowed": not halted, "reason": "owner halt"})()
    monkeypatch.setattr(kite_client, "is_owner_entry_halted", lambda channel: verdict)
    monkeypatch.setattr(kite_client, "assert_not_halted", lambda channel: None)
    def routed(request):
        # F1-A funds evidence is served normally; the scenario applies to the order POST.
        if request.method == "GET" and request.url.path == "/user/margins":
            return httpx.Response(200, json={"data": {"equity": {"available": {"cash": 1e7}}}})
        if request.method == "GET" and request.url.path == "/portfolio/positions":
            return httpx.Response(200, json={"data": {"net": [], "day": []}})
        if request.method == "GET" and request.url.path == "/orders":
            return httpx.Response(200, json={"data": []})
        return handler(request)

    client = KiteClient(db_path=":memory:")
    client.client = httpx.AsyncClient(base_url="https://api.kite.trade",
                                      transport=httpx.MockTransport(routed))

    async def fast_acquire():
        return None

    client.limiter.acquire = fast_acquire
    return client


async def _place(client):
    return await client.place_order(exchange="NFO", tradingsymbol="NIFTYX", quantity=75,
                                    order_type="LIMIT", price=100.0, intent="entry", channel="fno")


@pytest.mark.asyncio
@pytest.mark.parametrize("behaviour,certainty", [
    ("accepted", "ACCEPTED"),
    ("accepted_without_id", "AMBIGUOUS"),
    ("http_400", "BROKER_REJECTED"),
    ("http_503", "AMBIGUOUS"),
    ("connect_error", "NOT_SENT"),
    ("read_timeout", "AMBIGUOUS"),
])
async def test_place_order_reports_dispatch_certainty(monkeypatch, behaviour, certainty):
    import httpx

    def handler(request):
        if behaviour == "accepted":
            return httpx.Response(200, json={"data": {"order_id": "ORD-1"}})
        if behaviour == "accepted_without_id":
            return httpx.Response(200, json={"data": {}})
        if behaviour == "http_400":
            return httpx.Response(400, json={"message": "Invalid price"})
        if behaviour == "http_503":
            return httpx.Response(503, text="gateway")
        if behaviour == "connect_error":
            raise httpx.ConnectError("refused", request=request)
        raise httpx.ReadTimeout("no response", request=request)

    result = await _place(_kite(monkeypatch, handler))
    assert result["dispatch_certainty"] == certainty


@pytest.mark.asyncio
async def test_place_order_halt_and_validation_refusals_are_not_sent(monkeypatch):
    sent = []

    def handler(request):
        sent.append(request)
        raise AssertionError("must not send")

    halted = await _place(_kite(monkeypatch, handler, halted=True))
    assert halted["dispatch_certainty"] == "NOT_SENT" and halted["halted"] is True
    invalid = await _kite(monkeypatch, handler).place_order(tradingsymbol="", quantity=75,
                                                            intent="entry")
    assert invalid["dispatch_certainty"] == "NOT_SENT"
    assert sent == []
