"""[Gold V8 shadow 2026-11-16, + SN337 own inventory] V8's orders and holdings are kept beside SN Gold's paper actions;
nothing is placed; off by default; a failure never changes the paper step; V8 sells exactly what V8 holds."""
import json
from datetime import datetime
from pathlib import Path

import aiosqlite
import pytest
import pytz

import sn_gold
import sn_gold_v8 as v8
from config import settings
from fno_costs import calc_fno_costs
from tests.test_sn_gold import _bars, _close_paper, _paper, _row, at, db, quotes, run, sig, snapshot  # noqa: F401

IST = pytz.timezone("Asia/Kolkata")


def test_entry_order_limits_two_ticks_over_the_ask_and_fits_cash():
    o = v8.entry_order(180.0, 1, 65, 15000.0, 140.0)
    assert o["side"] == "BUY" and o["order_type"] == "LIMIT" and o["limit_price"] == 180.10 and o["qty"] == 65
    assert o["cash"] == pytest.approx(180.10 * 65 + calc_fno_costs(180.10, 0.0, 65), abs=0.01) and o["fits"]
    assert o["stop_trigger"] == 140.0 and o["stop_limit"] == 133.0


def test_entry_order_reduces_lots_to_the_wallets_cash():
    o = v8.entry_order(231.0, 2, 65, 30000.0, 200.0)      # 2 x 231.10 x 65 = 30,043 > 30,000
    assert o["lots"] == 1 and "1" in o["note"]
    assert v8.entry_order(230.0, 2, 65, 30000.0, 200.0)["lots"] == 2   # 29,913 + fees still fits
    none = v8.entry_order(470.0, 1, 65, 30000.0, 400.0)                # one lot 30,556 > 30,000
    assert none["lots"] == 0 and none["order_type"] == "NONE" and not none["fits"]


def test_add_order_uses_cash_paid_not_the_new_ask():
    # the auditor's case: a first lot at 270 and an add at 200 commits 30,550 before fees on a 30,000 wallet
    o = v8.add_order([[270.0, 1]], 200.0, 65, 30000.0, 199.0, 6000.0)
    assert o["lots"] == 0 and o["order_type"] == "NONE" and not o["fits"]
    # the reverse (150 then 240): the cash would fit, but Gold's own add rule (2 x 240 x 65 = 31,200 > 30,000) declines it.
    # V8 keeps Gold's rule and only adds the cash check (SN311's G1); "true cash" adds failed their frozen test.
    o = v8.add_order([[150.0, 1]], 240.0, 65, 30000.0, 239.0, 6000.0)
    assert o["lots"] == 0 and "Gold's add rule" in o["note"]
    # an add both rules allow: 1 lot at 150 on a 45,000 wallet, ask 200 -> Gold adds 2 (45,000 // 13,000 = 3, minus 1 held)
    o = v8.add_order([[150.0, 1]], 200.0, 65, 45000.0, 199.0, 9000.0)
    assert o["lots"] == 2 and o["fits"] and o["stop_trigger"] < 199.0


def test_exit_orders_are_market_on_the_stop_and_failsafe():
    assert v8.exit_order(190.0, 65, "n11:time_stop")["order_type"] == "LIMIT_THEN_MARKET"
    assert v8.exit_order(190.0, 65, "n11:time_stop")["limit_price"] == 189.9
    assert v8.exit_order(190.0, 65, "day_loss_stop")["order_type"] == "MARKET"
    assert v8.exit_order(190.0, 65, "failsafe_1515")["order_type"] == "MARKET"


async def _rows(path, table):
    async with aiosqlite.connect(path) as d:
        d.row_factory = aiosqlite.Row
        try:
            return [dict(r) for r in await (await d.execute(f"SELECT * FROM {table} ORDER BY rowid")).fetchall()]
        except Exception:
            return []


def test_v8_sells_what_v8_holds_not_what_paper_holds(tmp_path):
    """SN337, the auditor's reproduction: paper holds 2 lots (130 units); V8's cash check entered 1 lot (65); the exit sells 65."""
    path = str(tmp_path / "v8.db")
    now = IST.localize(datetime(2026, 11, 18, 10, 5))
    o = run(v8.on_entry(path, position_id=7, now=now, symbol="NIFTY26N2423900CE", token=1, ask=230.5, bid=230.0, lots=2,
                        lot_size=65, wallet=30000.0, stop=200.0))
    assert o["lots"] == 1, "2 x 230.60 x 65 + fees > 30,000"
    run(v8.on_exit(path, position_id=7, now=now.replace(hour=11), bid=240.0, ask=240.5, reason="n11:time_stop", paper_qty=130, paper_net=1200.0))
    entry, exit_ = run(_rows(path, "sn_gold_v8_intents"))
    assert entry["qty"] == 65 and entry["paper_qty"] == 130
    assert exit_["qty"] == 65 and exit_["paper_qty"] == 130, "V8 sells only its own 65 units"
    (p,) = run(_rows(path, "sn_gold_v8_positions"))
    assert p["status"] == "CLOSED" and p["net"] == pytest.approx((239.9 - 230.6) * 65 - calc_fno_costs(230.6, 239.9, 65), abs=0.01)
    assert p["paper_net"] == 1200.0


def test_v8_not_entered_records_no_add_or_exit(tmp_path):
    path = str(tmp_path / "v8.db")
    now = IST.localize(datetime(2026, 11, 18, 10, 5))
    run(v8.on_entry(path, position_id=8, now=now, symbol="X", token=1, ask=470.0, bid=469.0, lots=1, lot_size=65, wallet=30000.0, stop=400.0))
    assert run(v8.on_add_trigger(path, position_id=8, now=now, ask=480.0, bid=479.0, room=6000.0, paper_added_lots=0)) is None
    assert run(v8.on_exit(path, position_id=8, now=now, bid=480.0, ask=None, reason="n11:x", paper_qty=65, paper_net=0.0)) is None
    (p,) = run(_rows(path, "sn_gold_v8_positions"))
    assert p["status"] == "NOT_ENTERED" and [x["kind"] for x in run(_rows(path, "sn_gold_v8_intents"))] == ["ENTRY"]


def test_shadow_off_by_default_writes_nothing(db):
    assert settings.SN_GOLD_V8_SHADOW_ENABLED is False
    _bars(db.path)
    pid = run(_paper(db.path))
    run(sn_gold.on_paper_signal(db.path, sig(), snapshot(), at("10:05")))
    run(_close_paper(db.path, pid))
    run(sn_gold.tick(None, db.path, now=at("10:50"), fut_prices={"NIFTY": 24055.0}, read_quote=quotes({112: 190.0})))
    assert run(_rows(db.path, "sn_gold_v8_intents")) == []
    assert run(_row(db.path))[0]["status"] == "CLOSED"


def test_shadow_on_records_entry_and_exit_and_paper_is_unchanged(db, monkeypatch):
    monkeypatch.setattr(settings, "SN_GOLD_V8_SHADOW_ENABLED", True)
    _bars(db.path)
    pid = run(_paper(db.path))
    run(sn_gold.on_paper_signal(db.path, sig(), snapshot(), at("10:05")))
    run(_close_paper(db.path, pid))
    run(sn_gold.tick(None, db.path, now=at("10:50"), fut_prices={"NIFTY": 24055.0}, read_quote=quotes({112: 190.0})))
    (r,) = run(_row(db.path))
    assert r["status"] == "CLOSED" and r["net"] == pytest.approx((190.0 - 180.0) * 65 - calc_fno_costs(180.0, 190.0, 65))
    entry, exit_ = run(_rows(db.path, "sn_gold_v8_intents"))
    assert entry["kind"] == "ENTRY" and entry["side"] == "BUY" and entry["limit_price"] == 180.10 and entry["paper_price"] == 180.0
    assert entry["qty"] == 65 and entry["fits"] == 1 and entry["stop_trigger"] == pytest.approx(r["stop_price"])
    assert exit_["kind"] == "EXIT" and exit_["side"] == "SELL" and exit_["qty"] == 65 and exit_["limit_price"] == 189.9
    assert json.loads(exit_["note"]) == "n11:time_stop"
    (p,) = run(_rows(db.path, "sn_gold_v8_positions"))
    assert p["status"] == "CLOSED" and p["paper_net"] == pytest.approx(r["net"], abs=0.01)


def test_shadow_on_records_the_scale_in_with_cash_paid(db, monkeypatch):
    monkeypatch.setattr(settings, "SN_GOLD_V8_SHADOW_ENABLED", True)
    _bars(db.path)
    run(_paper(db.path))

    async def wallet(path, now):
        return {"wallet": 30000.0, "steps": 1, "progress": 0.0, "banked": 0.0, "refilled": 0.0}
    monkeypatch.setattr(sn_gold, "wallet_state", wallet)
    run(sn_gold.on_paper_signal(db.path, sig(), snapshot(forward=24050.0), at("10:05")))
    run(sn_gold.tick(None, db.path, now=at("10:07"), fut_prices={"NIFTY": 24061.0}, read_quote=quotes({113: 220.0})))
    assert json.loads(run(_row(db.path))[0]["pieces"]) == [[215.0, 1], [220.5, 1]]
    intents = run(_rows(db.path, "sn_gold_v8_intents"))
    assert [x["kind"] for x in intents] == ["ENTRY", "ADD"]
    add = intents[1]
    assert add["qty"] == 65 and add["paper_qty"] == 65 and add["limit_price"] == 220.6 and add["fits"] == 1
    assert add["cash"] == pytest.approx(215.1 * 65 + calc_fno_costs(215.1, 0.0, 65) + 220.6 * 65 + calc_fno_costs(220.6, 0.0, 65), abs=0.01)
    (p,) = run(_rows(db.path, "sn_gold_v8_positions"))
    assert json.loads(p["pieces"]) == [[215.1, 1], [220.6, 1]]


def test_shadow_failure_never_changes_the_paper_step(db, monkeypatch):
    monkeypatch.setattr(settings, "SN_GOLD_V8_SHADOW_ENABLED", True)

    async def boom(*a, **k):
        raise RuntimeError("shadow down")
    monkeypatch.setattr(v8, "on_entry", boom)
    _bars(db.path)
    run(_paper(db.path))
    assert run(sn_gold.on_paper_signal(db.path, sig(), snapshot(), at("10:05"))) is not None
    assert run(_row(db.path))[0]["status"] == "OPEN"


def test_shadow_module_has_no_order_path():
    src = Path(v8.__file__).read_text(encoding="utf-8")
    for word in ("place_order", "fno_live", "executor", "kite.", "order_execution", "modify_order", "cancel_order"):
        assert word not in src, word
