"""[Gold V8 shadow 2026-11-16] The real orders V8 would send are recorded beside SN Gold's paper actions; nothing is placed;
off by default; a failure never changes the paper step."""
import json
from pathlib import Path

import aiosqlite
import pytest

import sn_gold
import sn_gold_v8 as v8
from config import settings
from fno_costs import calc_fno_costs
from tests.test_sn_gold import _bars, _close_paper, _paper, _row, at, db, quotes, run, sig, snapshot  # noqa: F401


def test_entry_order_limits_two_ticks_over_the_ask_and_fits_cash():
    o = v8.entry_order(180.0, 1, 65, 15000.0, 140.0)
    assert o["side"] == "BUY" and o["order_type"] == "LIMIT" and o["limit_price"] == 180.10 and o["qty"] == 65
    assert o["cash"] == pytest.approx(180.10 * 65 + calc_fno_costs(180.10, 0.0, 65), abs=0.01) and o["fits"]
    assert o["stop_trigger"] == 140.0 and o["stop_limit"] == 133.0


def test_entry_order_reduces_lots_to_the_wallets_cash():
    o = v8.entry_order(231.0, 2, 65, 30000.0, 200.0)      # 2 x 231.10 x 65 = 30,043 > 30,000
    assert o["lots"] == 1 and "1" in o["note"]
    assert v8.entry_order(230.0, 2, 65, 30000.0, 200.0)["lots"] == 2   # 29,913 + fees still fits


def test_add_order_uses_cash_paid_not_the_new_ask():
    # the auditor's case: a first lot at 270 and an add at 200 commits 30,550 before fees on a 30,000 wallet
    o = v8.add_order([[270.0, 1]], 200.0, 1, 65, 30000.0, 250.0)
    assert o["lots"] == 0 and o["order_type"] == "NONE" and not o["fits"]
    # and the reverse: 150 then 240 commits 25,350 (+ fees), which fits
    o = v8.add_order([[150.0, 1]], 240.0, 1, 65, 30000.0, 200.0)
    assert o["lots"] == 1 and o["fits"]


def test_exit_orders_are_market_on_the_stop_and_failsafe():
    assert v8.exit_order(190.0, 65, "n11:time_stop")["order_type"] == "LIMIT_THEN_MARKET"
    assert v8.exit_order(190.0, 65, "n11:time_stop")["limit_price"] == 189.9
    assert v8.exit_order(190.0, 65, "day_loss_stop")["order_type"] == "MARKET"
    assert v8.exit_order(190.0, 65, "failsafe_1515")["order_type"] == "MARKET"


async def _intents(path):
    async with aiosqlite.connect(path) as d:
        d.row_factory = aiosqlite.Row
        try:
            return [dict(r) for r in await (await d.execute("SELECT * FROM sn_gold_v8_intents ORDER BY id")).fetchall()]
        except Exception:
            return []


def test_shadow_off_by_default_writes_nothing(db):
    assert settings.SN_GOLD_V8_SHADOW_ENABLED is False
    _bars(db.path)
    pid = run(_paper(db.path))
    run(sn_gold.on_paper_signal(db.path, sig(), snapshot(), at("10:05")))
    run(_close_paper(db.path, pid))
    run(sn_gold.tick(None, db.path, now=at("10:50"), fut_prices={"NIFTY": 24055.0}, read_quote=quotes({112: 190.0})))
    assert run(_intents(db.path)) == []
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
    entry, exit_ = run(_intents(db.path))
    assert entry["kind"] == "ENTRY" and entry["side"] == "BUY" and entry["limit_price"] == 180.10 and entry["paper_price"] == 180.0
    assert entry["qty"] == 65 and entry["fits"] == 1 and entry["stop_trigger"] == pytest.approx(r["stop_price"])
    assert exit_["kind"] == "EXIT" and exit_["side"] == "SELL" and exit_["order_type"] == "LIMIT_THEN_MARKET" and exit_["limit_price"] == 189.9
    assert json.loads(exit_["note"]) == "n11:time_stop"


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
    kinds = [x["kind"] for x in run(_intents(db.path))]
    add = [x for x in run(_intents(db.path)) if x["kind"] == "ADD"][0]
    assert kinds == ["ENTRY", "ADD"] and add["qty"] == 65 and add["limit_price"] == 220.6 and add["fits"] == 1
    assert add["cash"] == pytest.approx(215.0 * 65 + calc_fno_costs(215.0, 0.0, 65) + 220.6 * 65 + calc_fno_costs(220.6, 0.0, 65), abs=0.01)


def test_shadow_failure_never_changes_the_paper_step(db, monkeypatch):
    monkeypatch.setattr(settings, "SN_GOLD_V8_SHADOW_ENABLED", True)

    async def boom(*a, **k):
        raise RuntimeError("shadow down")
    monkeypatch.setattr(v8, "record", boom)
    _bars(db.path)
    run(_paper(db.path))
    assert run(sn_gold.on_paper_signal(db.path, sig(), snapshot(), at("10:05"))) is not None
    assert run(_row(db.path))[0]["status"] == "OPEN"


def test_shadow_module_has_no_order_path():
    src = Path(v8.__file__).read_text(encoding="utf-8")
    for word in ("place_order", "fno_live", "executor", "kite.", "order_execution", "modify_order", "cancel_order"):
        assert word not in src, word
