"""[O27h] The owner hears once per new trend-day pullback thesis; nothing else is told; a failed send retries."""
from __future__ import annotations

from datetime import datetime

import aiosqlite
import pytest
import pytz

import fno_shadow
import fno_shadow_alert
from config import settings

IST = pytz.timezone("Asia/Kolkata")
NOW = IST.localize(datetime(2026, 10, 28, 12, 7))


def _row(variant="FNO_TREND_PULLBACK", bar="2026-10-28 12:00:00", direction="LONG", accepted=True, priced=False):
    outcome = ({"available": True, "entry_at_observed_ask": 182.5, "delta_at_evaluation": 0.553, "quantity": 65}
               if priced else {"available": False, "reason": "no already-resolved option chain"})
    return {"trading_date": bar[:10], "underlying": "NIFTY", "bar_ts": bar, "variant": variant,
            "accepted": accepted, "reject_reason": None if accepted else "no_trend_pullback",
            "direction": direction if accepted else None,
            "features": {"close": 25412.5, "stop_underlying": 25340.0, "target_underlying": 25629.0},
            "config": {}, "post_cost_outcome": outcome}


class _Notify:
    def __init__(self, ok=True):
        self.ok, self.sent = ok, []

    async def __call__(self, text, *, event):
        self.sent.append((text, event))
        return self.ok


@pytest.mark.asyncio
async def test_one_message_per_new_thesis_with_the_levels_and_the_option(db_path):
    await fno_shadow.persist_fno_shadow_results(db_path, [
        _row(priced=True), _row(bar="2026-10-28 12:05:00"),                        # same thesis, a later bar
        _row(variant="FNO_CONTINUATION", bar="2026-10-28 12:00:00"),              # not an alerted variant
        _row(bar="2026-10-28 11:55:00", accepted=False)])
    notify = _Notify()
    sent = await fno_shadow_alert.check(db_path, NOW, notify=notify)
    assert len(sent) == 1 and notify.sent[0][1] == "fno_shadow_signal"
    text = sent[0]
    for part in ("not traded", "trend-day VWAP pullback", "LONG (calls)", "NIFTY", "12:00 bar", "25,412.5",
                 "stop 25,340.0", "target 25,629.0", "₹182.50", "delta 0.55", "lot 65", "current strategy"):
        assert part in text, part
    assert await fno_shadow_alert.check(db_path, NOW, notify=notify) == []      # told once
    await fno_shadow.persist_fno_shadow_results(db_path, [_row(bar="2026-10-28 13:00:00", direction="SHORT")])
    later = await fno_shadow_alert.check(db_path, NOW, notify=notify)
    assert len(later) == 1 and "SHORT (puts)" in later[0] and "would buy" not in later[0]


@pytest.mark.asyncio
async def test_a_failed_send_is_tried_again_and_nothing_outside_the_window_or_day_is_told(db_path):
    await fno_shadow.persist_fno_shadow_results(db_path, [
        _row(), _row(bar="2026-10-28 14:40:00", direction="SHORT"),               # closes 14:45: book won't act
        _row(bar="2026-10-27 12:00:00", direction="SHORT")])                      # yesterday
    failing = _Notify(ok=False)
    assert await fno_shadow_alert.check(db_path, NOW, notify=failing) == [] and len(failing.sent) == 1
    working = _Notify()
    assert len(await fno_shadow_alert.check(db_path, NOW, notify=working)) == 1
    async with aiosqlite.connect(db_path) as db:
        told = await (await db.execute("SELECT variant, candidate_key FROM fno_shadow_alert_told")).fetchall()
    assert told == [("FNO_TREND_PULLBACK", "2026-10-28|NIFTY|LONG")]


@pytest.mark.asyncio
async def test_switched_off_or_broken_it_stays_silent_and_never_raises(db_path, monkeypatch):
    await fno_shadow.persist_fno_shadow_results(db_path, [_row()])
    monkeypatch.setattr(settings, "FNO_SHADOW_OWNER_ALERTS", False)
    notify = _Notify()
    assert await fno_shadow_alert.check(db_path, NOW, notify=notify) == [] and notify.sent == []
    monkeypatch.setattr(settings, "FNO_SHADOW_OWNER_ALERTS", True)

    async def boom(text, *, event):
        raise RuntimeError("gateway down")
    assert await fno_shadow_alert.check(db_path, NOW, notify=boom) == []
    assert len(await fno_shadow_alert.check(db_path, NOW, notify=notify)) == 1


def test_the_alert_module_has_no_order_or_broker_surface():
    source = open(fno_shadow_alert.__file__, encoding="utf-8").read()
    for word in ("kite", "place_order", "executor", "FnoExecutor", "fno_positions"):
        assert word not in source
