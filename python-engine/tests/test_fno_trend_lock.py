"""[N012-A] The trend-aware profit lock (fno_trend_lock) on the paper F&O main book.

The rule must be the research's exactly (docs/research/simulation/2026-11-05-fno-expiry-followup/regular_rules.py,
scored in 2026-11-05-fno-n12 Round 30 and 2026-11-08-fno-n012-a2), act only on N11 paper positions, and change
only the premium profit lock.
"""
from datetime import datetime, timedelta
import importlib.util
from pathlib import Path
import random
from types import SimpleNamespace

import pytest
import pytz

import fno_positions as fpos
import fno_trend_lock as tl
from config import settings
from fno_models import FnoSource

IST = pytz.timezone("Asia/Kolkata")
NOW = IST.localize(datetime(2026, 11, 9, 11, 0))
RULES = Path(__file__).resolve().parents[2] / "docs/research/simulation/2026-11-05-fno-expiry-followup/regular_rules.py"
BASE = {"FNO_PROFIT_LOCK_ENABLED": True, "FNO_PROFIT_LOCK_ARM_R": 0.40, "FNO_PROFIT_LOCK_KEEP_FRACTION": 0.5,
        "FNO_PROFIT_LOCK_FLOOR_R": 0.10, "FNO_STOP_PREMIUM_PCT": 0.25}


def _research():
    if not RULES.is_file():
        pytest.skip("research rules not in this checkout")
    spec = importlib.util.spec_from_file_location("n012_regular_rules", RULES)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("step_sec", [10, 60])
def test_the_trend_reads_the_same_as_the_research_rule_on_a_random_walk(step_sec):
    research = _research()
    rng = random.Random(20261108 + step_sec)
    for direction in ("LONG", "SHORT"):
        ours, theirs = tl.Trend(), research.Trend()
        price, now = 22600.0, NOW
        seen = set()
        for _ in range(6 * 3600 // step_sec):
            now += timedelta(seconds=step_sec + (rng.random() < .02) * rng.choice((90, 400)))   # some gaps
            price += rng.gauss(0, 3.0)
            future = None if rng.random() < .01 else round(price, 2)
            a, b = ours.update(now, future, direction), theirs.update(now, future, direction)
            assert a == b, (now, direction)
            seen.add(a)
        assert {"SUPPORT", "ADVERSE", "MIXED", "UNKNOWN"} <= seen


@pytest.mark.parametrize("trend", ["SUPPORT", "ADVERSE", "MIXED", "UNKNOWN"])
@pytest.mark.parametrize("lock_on", [True, False])
@pytest.mark.parametrize("trailing", [0, 1])
def test_the_parameters_are_the_research_rule_at_the_n012a_numbers(trend, lock_on, trailing):
    research = _research()
    params = {**BASE, "FNO_PROFIT_LOCK_ENABLED": lock_on, "FNO_TIME_STOP_MIN": 60.0}
    position = SimpleNamespace(trail_active=trailing)
    ours = tl.trend_params(params, position, trend, support_keep=.35, adverse_keep=.65, trail_keep=.60)
    assert ours == research.trend_params(params, position, trend)
    assert {k for k in ours if ours[k] != params.get(k)} <= {
        "FNO_PROFIT_LOCK_ENABLED", "FNO_PROFIT_LOCK_ARM_R", "FNO_PROFIT_LOCK_KEEP_FRACTION"}


def test_no_trail_lock_when_its_keep_is_off():
    params = {**BASE, "FNO_PROFIT_LOCK_ENABLED": False}
    out = tl.trend_params(params, SimpleNamespace(trail_active=1), "ADVERSE", support_keep=.35, adverse_keep=.65,
                          trail_keep=None)
    assert out == params


def test_it_applies_to_n11_paper_positions_only(monkeypatch):
    monkeypatch.setattr(settings, "FNO_TREND_LOCK_ENABLED", True)
    paper = FnoSource.FNO_PAPER.value
    assert tl.applies(paper, True, SimpleNamespace(strategy="N11_EFF"))
    assert tl.applies(paper, True, SimpleNamespace(strategy="N11_ADD"))
    assert not tl.applies(FnoSource.FNO_LIVE.value, False, SimpleNamespace(strategy="N11_EFF"))   # real money
    assert not tl.applies(paper, False, SimpleNamespace(strategy="N11_EFF"))     # a real fill in the paper loop
    assert not tl.applies(paper, True, SimpleNamespace(strategy="SHIPPED"))
    monkeypatch.setattr(settings, "FNO_TREND_LOCK_ENABLED", False)
    assert not tl.applies(paper, True, SimpleNamespace(strategy="N11_EFF"))


def _row(**over):
    row = dict(source="FNO_PAPER", tradingsymbol="NIFTY26NOV22600CE", token=4242, underlying="NIFTY",
               expiry="2026-11-17", strike=22600.0, opt_type="CE", direction="LONG", lots=1, lot_size=65,
               qty=65, entry_time=NOW.isoformat(), entry_date="2026-11-09", entry_premium=200.0,
               entry_underlying=22600.0, delta_at_entry=0.5, iv_at_entry=0.15, atr_at_entry=30.0,
               stop_underlying=22500.0, target_underlying=22900.0, premium_stop=150.0, trail_active=0,
               trail_stop_underlying=None, best_underlying=22600.0, best_premium=260.0, max_loss_rupees=3250.0,
               status="OPEN", entry_order_id="PAPER-TEST", bar_ts="2026-11-09 10:55:00", strategy="N11_OR20")
    row.update(over)
    return row


async def _walk(tmp_path, monkeypatch, enabled):
    """A held N11 call whose future rises bucket after bucket (SUPPORT), then a give-back to ₹228: the native lock
    (keep 0.50 of the ₹60 gain, floor ₹230) sells; the trend lock (keep 0.35, floor ₹221) holds."""
    from unittest.mock import AsyncMock, MagicMock
    from fno_executor import FnoExecutor
    from fno_orchestrator import _manage_open_positions
    monkeypatch.setattr(settings, "FNO_TREND_LOCK_ENABLED", enabled)
    monkeypatch.setattr(settings, "FNO_HARD_FLAT_MIN", 15 * 60 + 10)
    tl._TRENDS.clear()
    tmp_path.mkdir(parents=True, exist_ok=True)
    db = str(tmp_path / "fno.db")
    from performance import init_ledger
    await init_ledger(db)
    await fpos.init_fno_positions_db(db)
    await fpos.insert_position(db, **_row())
    kite = MagicMock()
    executor = FnoExecutor(kite, paper_mode=True, source_tag="FNO_PAPER")
    closed = []
    looks = [(NOW + timedelta(minutes=m, seconds=50), 22610.0 + 10 * (m // 5), 240.0) for m in range(16)]
    looks += [(NOW + timedelta(minutes=16), 22640.0, 228.0), (NOW + timedelta(minutes=16, seconds=10), 22640.0, 228.0)]
    for at, fut, bid in looks:
        kite.get_quote = AsyncMock(return_value={4242: {"last_price": bid, "depth": {"buy": [{"price": bid}]}}})
        closed += await _manage_open_positions(kite, db, "FNO_PAPER", executor, at, fut_price=fut,
                                               fut_prices={"NIFTY": fut})
        if closed:
            break
    return closed


@pytest.mark.asyncio
async def test_a_supported_trade_keeps_its_room_where_the_native_lock_sells(tmp_path, monkeypatch):
    native = await _walk(tmp_path / "off", monkeypatch, enabled=False)
    assert [c.get("reason") for c in native] == ["profit_lock"]
    trend = await _walk(tmp_path / "on", monkeypatch, enabled=True)
    assert trend == []
    assert len(tl._TRENDS) == 1                    # one position's buckets, kept between looks


def test_closed_positions_lose_their_buckets():
    tl._TRENDS.clear()
    tl._TRENDS[("FNO_PAPER", 1)] = tl.Trend()
    tl._TRENDS[("FNO_PAPER", 2)] = tl.Trend()
    tl._TRENDS[("FNO_LIVE", 3)] = tl.Trend()
    tl.forget_all_but("FNO_PAPER", {("FNO_PAPER", 2)})
    assert set(tl._TRENDS) == {("FNO_PAPER", 2), ("FNO_LIVE", 3)}
    tl._TRENDS.clear()
