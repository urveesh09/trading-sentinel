"""F0-R4: retained broker packets, entry economics and frozen costs bind every receipt.

Corruption is injected only inside each test's temporary database, after
dropping the immutability triggers there - the same isolated method the
independent review used. It demonstrates semantic validation, not a way to
bypass intact Production triggers.
"""
import hashlib
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import aiosqlite
import pytest

from fno_costs import calc_fno_costs_from_snapshot
from fno_dr_book import init_dr_db
from fno_exit_evidence import RecoveryConflict, derive_exit_facts, validate_retained_exit_receipt
from fno_shared_risk import init_shared_fno_risk_db, shared_fno_risk_view
from tests.test_atomic_settlement import _insert_open_position, fno_db  # noqa: F401
from tests.test_fno_exit_recovery import claim_exit_intent, pending_exit_intents, resolve

IST = timezone(timedelta(hours=5, minutes=30))
SYMBOL = "NIFTY26SEP19500CE"
POOL = 100_000.0


def _broker(*, qty, filled, price=110.0, order_id="EXIT01", trade_id="T1", now=None):
    now = now or datetime.now(timezone.utc)
    stamp = (now + timedelta(seconds=1)).astimezone(IST).strftime("%Y-%m-%d %H:%M:%S")
    order = {"order_id": order_id, "placed_by": "USER01", "tradingsymbol": SYMBOL,
             "exchange": "NFO", "product": "MIS", "transaction_type": "SELL",
             "tag": "FNO_LIVE", "status": "CANCELLED", "quantity": qty,
             "filled_quantity": filled, "order_timestamp": stamp}
    trades = [{"trade_id": trade_id, "order_id": order_id, "tradingsymbol": SYMBOL,
               "exchange": "NFO", "product": "MIS", "transaction_type": "SELL",
               "quantity": filled, "average_price": price,
               "fill_timestamp": now.astimezone(IST).strftime("%Y-%m-%d %H:%M:%S")}] if filled else []
    kite = AsyncMock()
    kite.orders_snapshot.return_value = [order]
    kite.order_trades.return_value = trades
    kite.get_broker_positions.return_value = {"net": [
        {"exchange": "NFO", "product": "MIS", "tradingsymbol": SYMBOL, "quantity": qty - filled}]}
    return kite


async def _partial(db_path, *, qty=150, filled=75, order_id="EXIT01", trade_id="T1", pid=None):
    """Create (or reuse) a live position and resolve one real partial exit for it."""
    if pid is None:
        pid = await _insert_open_position(db_path, source="FNO_LIVE", qty=qty,
                                          max_loss_rupees=100.0 * qty)
    # A new exit evaluation must start strictly after the latest recovery; on
    # Windows the coarse clock can otherwise stamp both at the same instant.
    async with aiosqlite.connect(db_path) as db:
        latest = (await (await db.execute(
            "SELECT MAX(resolved_at) FROM fno_exit_recoveries WHERE position_id=?", (pid,))).fetchone())[0]
    evaluation = datetime.now(timezone.utc)
    if latest is not None:
        evaluation = max(evaluation, datetime.fromisoformat(latest) + timedelta(milliseconds=1))
    assert await claim_exit_intent(db_path, pid, "FNO_LIVE", evaluation_started_at=evaluation)
    created = [i for i in await pending_exit_intents(db_path) if i["position_id"] == pid][0]["created_at"]
    kite = _broker(qty=await _qty(db_path, pid), filled=filled, order_id=order_id, trade_id=trade_id)
    await resolve(db_path, kite, pid, created, order_id=order_id)
    return pid


async def _qty(db_path, pid):
    async with aiosqlite.connect(db_path) as db:
        return (await (await db.execute("SELECT qty FROM fno_positions WHERE id=?", (pid,))).fetchone())[0]


async def _ready_view(db_path):
    await init_dr_db(db_path)
    await init_shared_fno_risk_db(db_path)
    return await shared_fno_risk_view(db_path, "FNO_LIVE", POOL)


async def _unprotected(db_path):
    """Drop recovery/identity triggers in this temporary DB only."""
    db = await aiosqlite.connect(db_path)
    for name in ("fno_exit_recoveries_evidence_update_immutable",
                 "fno_positions_identity_immutable", "fno_positions_entry_evidence_immutable"):
        await db.execute(f"DROP TRIGGER IF EXISTS {name}")
    await db.commit()
    return db


async def _rewrite_packet(db, mutate):
    raw = (await (await db.execute("SELECT broker_evidence_json FROM fno_exit_recoveries")).fetchone())[0]
    packet = json.loads(raw)
    mutate(packet)
    new = json.dumps(packet, sort_keys=True, default=str, separators=(",", ":"), ensure_ascii=True)
    await db.execute("UPDATE fno_exit_recoveries SET broker_evidence_json=?, broker_evidence_sha256=?",
                     (new, hashlib.sha256(new.encode()).hexdigest()))
    await db.commit()


# ---- genuine evidence ---------------------------------------------------------

@pytest.mark.asyncio
async def test_real_writer_output_binds_and_freezes_its_cost_schedule(fno_db):
    await _partial(fno_db)
    view = await _ready_view(fno_db)
    assert view.available, view.reason
    async with aiosqlite.connect(fno_db) as db:
        entry, fill, filled, costs, snapshot = await (await db.execute(
            "SELECT entry_premium,fill_price,filled_qty,costs,cost_snapshot_json FROM fno_exit_recoveries"
        )).fetchone()
    frozen = json.loads(snapshot)
    assert frozen["schedule_version"] and costs == pytest.approx(
        calc_fno_costs_from_snapshot(entry, fill, filled, frozen))


# ---- corrupted evidence fails closed --------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("mutate", [
    lambda p: p.clear(),                                                    # empty payload
    lambda p: p["order"].update(tradingsymbol="NIFTY26SEP19600CE"),         # wrong symbol
    lambda p: p.update(account_id="OTHER"),                                 # wrong account
    lambda p: p["order"].update(placed_by="OTHER"),
    lambda p: p["order"].update(order_id="EXIT99"),                         # wrong order
    lambda p: p["order"].update(tag="FNO_PAPER"),
    lambda p: p["trades"][0].update(average_price=120.0),                   # price in packet only
    lambda p: p["trades"].append(dict(p["trades"][0])),                     # duplicate trade id
    lambda p: p["net_position"][0].update(quantity=0),                      # residual disagrees
    lambda p: p["order"].update(status="OPEN"),
    lambda p: p.update(observed_at="2026-01-01T00:00:00"),                  # naive clock
])
async def test_rewritten_packets_with_matching_digest_fail_closed(fno_db, mutate):
    await _partial(fno_db)
    db = await _unprotected(fno_db)
    try:
        await _rewrite_packet(db, mutate)
    finally:
        await db.close()
    view = await _ready_view(fno_db)
    assert not view.available and view.reason == "recovery_payload_mismatch"


@pytest.mark.asyncio
async def test_internally_consistent_wrong_price_is_caught_by_the_packet(fno_db):
    """Receipt price, gross, costs, P&L and ledger cash all edited consistently."""
    pid = await _partial(fno_db)
    db = await _unprotected(fno_db)
    try:
        entry, filled, snapshot, ledger_id = await (await db.execute(
            "SELECT entry_premium,filled_qty,cost_snapshot_json,ledger_id FROM fno_exit_recoveries"
        )).fetchone()
        fake = 130.0
        gross = (fake - entry) * filled
        costs = calc_fno_costs_from_snapshot(entry, fake, filled, json.loads(snapshot))
        await db.execute("UPDATE fno_exit_recoveries SET fill_price=?,gross_pnl=?,costs=?,pnl=?",
                         (fake, gross, costs, gross - costs))
        await db.execute("UPDATE bankroll_ledger SET pnl=? WHERE id=?", (gross - costs, ledger_id))
        await db.commit()
    finally:
        await db.close()
    view = await _ready_view(fno_db)
    assert not view.available and view.reason == "recovery_payload_mismatch"
    assert pid


@pytest.mark.asyncio
async def test_wrong_costs_and_missing_or_invalid_provenance_fail_closed(fno_db):
    await _partial(fno_db)
    db = await _unprotected(fno_db)
    try:
        ledger_id = (await (await db.execute("SELECT ledger_id FROM fno_exit_recoveries")).fetchone())[0]
        # costs +1 with P&L and ledger adjusted consistently
        await db.execute("UPDATE fno_exit_recoveries SET costs=costs+1, pnl=pnl-1")
        await db.execute("UPDATE bankroll_ledger SET pnl=pnl-1 WHERE id=?", (ledger_id,))
        await db.commit()
    finally:
        await db.close()
    assert (await _ready_view(fno_db)).reason == "recovery_cost_mismatch"
    for bad in (None, "{}", json.dumps({"schedule_version": "x", "rates": {"gst_pct": -1}})):
        db = await _unprotected(fno_db)
        try:
            await db.execute("UPDATE fno_exit_recoveries SET cost_snapshot_json=?", (bad,))
            await db.commit()
        finally:
            await db.close()
        assert (await _ready_view(fno_db)).reason == "recovery_cost_provenance_unavailable"


@pytest.mark.asyncio
async def test_changed_entry_premium_fails_closed_and_is_trigger_protected(fno_db):
    pid = await _partial(fno_db)
    async with aiosqlite.connect(fno_db) as db:
        with pytest.raises(aiosqlite.IntegrityError, match="entry identity is immutable"):
            await db.execute("UPDATE fno_positions SET entry_premium=50 WHERE id=?", (pid,))
        with pytest.raises(aiosqlite.IntegrityError, match="entry identity is immutable"):
            await db.execute("UPDATE fno_positions SET tradingsymbol='X' WHERE id=?", (pid,))
    db = await _unprotected(fno_db)
    try:
        await db.execute("UPDATE fno_positions SET entry_premium=99 WHERE id=?", (pid,))
        await db.commit()
    finally:
        await db.close()
    view = await _ready_view(fno_db)
    assert not view.available and view.reason == "recovery_entry_economics_mismatch"


@pytest.mark.asyncio
async def test_trade_ids_must_be_unique_across_a_positions_recoveries(fno_db):
    pid = await _insert_open_position(fno_db, source="FNO_LIVE", qty=225, max_loss_rupees=22_500.0)
    await _partial(fno_db, qty=225, filled=75, order_id="EXIT01", trade_id="T1", pid=pid)
    await _partial(fno_db, qty=225, filled=75, order_id="EXIT02", trade_id="T2", pid=pid)
    assert (await _ready_view(fno_db)).available               # two genuine partials
    db = await _unprotected(fno_db)
    try:
        rows = await (await db.execute(
            "SELECT id,broker_evidence_json FROM fno_exit_recoveries ORDER BY id")).fetchall()
        packet = json.loads(rows[1][1])
        packet["trades"][0]["trade_id"] = "T1"                 # reuse the first fill's id
        new = json.dumps(packet, sort_keys=True, default=str, separators=(",", ":"), ensure_ascii=True)
        await db.execute("UPDATE fno_exit_recoveries SET broker_evidence_json=?,broker_evidence_sha256=? "
                         "WHERE id=?", (new, hashlib.sha256(new.encode()).hexdigest(), rows[1][0]))
        await db.commit()
    finally:
        await db.close()
    assert (await _ready_view(fno_db)).reason == "recovery_payload_mismatch"


# ---- the pure function itself ---------------------------------------------------

def _packet():
    order = {"order_id": "O1", "placed_by": "U", "tradingsymbol": SYMBOL, "exchange": "NFO",
             "product": "MIS", "transaction_type": "SELL", "tag": "FNO_LIVE", "status": "CANCELLED",
             "quantity": 150, "filled_quantity": 75, "order_timestamp": "2026-10-03 09:30:05"}
    trades = [{"trade_id": "A", "order_id": "O1", "tradingsymbol": SYMBOL, "exchange": "NFO",
               "product": "MIS", "transaction_type": "SELL", "quantity": 50, "average_price": 100.0,
               "fill_timestamp": "2026-10-03 09:30:06"},
              {"trade_id": "B", "order_id": "O1", "tradingsymbol": SYMBOL, "exchange": "NFO",
               "product": "MIS", "transaction_type": "SELL", "quantity": 25, "average_price": 106.0,
               "fill_timestamp": "2026-10-03 09:30:07"}]
    net = [{"exchange": "NFO", "product": "MIS", "tradingsymbol": SYMBOL, "quantity": 75}]
    return order, trades, net


def test_derive_exit_facts_weights_the_fill_price_and_checks_clocks():
    order, trades, net = _packet()
    created = datetime(2026, 10, 3, 4, 0, tzinfo=timezone.utc)          # 09:30 IST
    facts = derive_exit_facts(order=order, trades=trades, net_position=net, account_id="U",
                              order_id="O1", source="FNO_LIVE", tradingsymbol=SYMBOL,
                              intent_qty=150, intent_created_at=created,
                              observed_at=created + timedelta(minutes=1))
    assert facts["fill_price"] == pytest.approx((50 * 100.0 + 25 * 106.0) / 75)
    assert (facts["filled_qty"], facts["remaining_qty"], facts["trade_ids"]) == (75, 75, ["A", "B"])
    with pytest.raises(RecoveryConflict, match="future"):
        derive_exit_facts(order=order, trades=trades, net_position=net, account_id="U",
                          order_id="O1", source="FNO_LIVE", tradingsymbol=SYMBOL, intent_qty=150,
                          intent_created_at=created, observed_at=created)
    with pytest.raises(RecoveryConflict, match="predates"):
        derive_exit_facts(order=order, trades=trades, net_position=net, account_id="U",
                          order_id="O1", source="FNO_LIVE", tradingsymbol=SYMBOL, intent_qty=150,
                          intent_created_at=created + timedelta(hours=1),
                          observed_at=created + timedelta(hours=2))


def test_validate_retained_exit_receipt_rejects_unverifiable_receipts():
    order, trades, net = _packet()
    raw = json.dumps({"account_id": "U", "order": order, "trades": trades, "net_position": net,
                      "observed_at": "2026-10-03T04:01:00+00:00"})
    base = {"broker_evidence_json": raw, "broker_evidence_sha256": hashlib.sha256(raw.encode()).hexdigest(),
            "account_id": "U", "order_id": "O1", "intent_created_at": "2026-10-03T04:00:00+00:00",
            "terminal_status": "CANCELLED", "filled_qty": 75, "remaining_qty": 75,
            "entry_premium": 90.0, "fill_price": (50 * 100.0 + 25 * 106.0) / 75}
    from cost_schedules import options_cost_snapshot
    snapshot = options_cost_snapshot()
    base["cost_snapshot_json"] = json.dumps(snapshot)
    base["costs"] = calc_fno_costs_from_snapshot(90.0, base["fill_price"], 75, snapshot)
    ok = dict(base)
    assert validate_retained_exit_receipt(ok, source="FNO_LIVE", tradingsymbol=SYMBOL,
                                          position_entry_premium=90.0) == ("", ["A", "B"])
    cases = [
        ({"terminal_status": "COMPLETE"}, "recovery_payload_mismatch"),
        ({"remaining_qty": 0}, "recovery_payload_mismatch"),
        ({"broker_evidence_sha256": "0" * 64}, "recovery_payload_mismatch"),
        ({"intent_created_at": "2026-10-03T04:00:00"}, "recovery_payload_mismatch"),
        ({"entry_premium": 91.0}, "recovery_entry_economics_mismatch"),
        ({"cost_snapshot_json": None}, "recovery_cost_provenance_unavailable"),
        ({"costs": base["costs"] + 0.5}, "recovery_cost_mismatch"),
    ]
    for change, reason in cases:
        assert validate_retained_exit_receipt({**base, **change}, source="FNO_LIVE", tradingsymbol=SYMBOL,
                                              position_entry_premium=90.0)[0] == reason, change
    assert validate_retained_exit_receipt(base, source="FNO_PAPER", tradingsymbol=SYMBOL,
                                          position_entry_premium=90.0)[0] == "recovery_payload_mismatch"
