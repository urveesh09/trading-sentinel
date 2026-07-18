"""
[PARTNER-TIPS-TESTS 2026-07-18] Orchestration (plan WS5): per-bar signal
dedup (a restart or re-tick must never re-send a tip), the event
throttle window, gating (disabled / non-trading day / session window),
and the EOD signal-outcome walk.
"""
import json
from datetime import date, datetime
from types import SimpleNamespace

import pandas as pd
import pytest
import pytz

import partner_orchestrator as po
from config import settings
from fno_engine_mom import MomSignal
from fno_models import FnoDirection
from fno_signal_scan import UnderlyingScan
from fno_underlyings import UnderlyingSpec

IST = pytz.timezone("Asia/Kolkata")
NOW = IST.localize(datetime(2026, 7, 20, 10, 3))   # Monday, inside session
SPEC = UnderlyingSpec("NIFTY", "NFO")


def _fired_scan(bar_ts="2026-07-20 09:55:00"):
    sig = MomSignal(
        bar_ts=bar_ts, direction=FnoDirection.LONG, close=25100.0,
        or_high=25010.0, or_low=24990.0, atr=30.0, rvol=2.5,
        stop_underlying=25055.0, target_underlying=25167.5,
    )
    return UnderlyingScan(name="NIFTY", sig=sig)


class _Book:
    def ready(self, today):
        return True

    def nearest_option_expiry(self, today):
        return date(2026, 7, 23)

    def is_expiry_day(self, day):
        return False

    def front_future(self, today):
        return None


@pytest.fixture
def wired(tmp_path, monkeypatch):
    import main

    db = str(tmp_path / "partner.db")
    monkeypatch.setattr(settings, "DB_PATH", db)
    monkeypatch.setattr(settings, "PARTNER_BOT_ENABLED", True)
    monkeypatch.setattr(settings, "PARTNER_TELEGRAM_BOT_TOKEN", "t")
    monkeypatch.setattr(settings, "PARTNER_TELEGRAM_CHAT_ID", "c")

    async def _open_day(*a, **kw):
        return True

    monkeypatch.setattr(main, "is_trading_day", _open_day)
    monkeypatch.setattr(main, "kite", SimpleNamespace(access_token="tok"))
    monkeypatch.setattr(main, "_fno_regime_str", lambda: "REGIME_1_NORMAL")

    sent = []

    async def _send(text, kind="partner_msg"):
        sent.append((kind, text))
        return True

    monkeypatch.setattr(po, "send_partner", _send)
    monkeypatch.setattr(po, "analytics_underlyings", lambda: [SPEC])
    monkeypatch.setattr(po, "get_instruments_for", lambda name: _Book())

    state = {"scan": _fired_scan(), "scan_calls": 0}

    async def _scan(kite, spec, regime, now):
        state["scan_calls"] += 1
        return state["scan"]

    monkeypatch.setattr(po, "scan_underlying", _scan)

    import asyncio
    asyncio.get_event_loop()
    return SimpleNamespace(db=db, sent=sent, state=state)


async def _init(db):
    await po.init_partner_db(db)


# ---------------------------------------------------------------------------
# gating
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_disabled_is_a_total_noop(wired, monkeypatch):
    await _init(wired.db)
    monkeypatch.setattr(settings, "PARTNER_BOT_ENABLED", False)
    await po.partner_scan_tick(NOW)
    await po.partner_analytics_tick(NOW)
    await po.partner_morning_brief(NOW)
    assert wired.state["scan_calls"] == 0
    assert wired.sent == []


@pytest.mark.asyncio
async def test_non_trading_day_is_a_noop(wired, monkeypatch):
    await _init(wired.db)
    import main

    async def _closed(*a, **kw):
        return False

    monkeypatch.setattr(main, "is_trading_day", _closed)
    await po.partner_scan_tick(NOW)
    assert wired.state["scan_calls"] == 0


@pytest.mark.asyncio
async def test_outside_session_window_is_a_noop(wired):
    await _init(wired.db)
    late = IST.localize(datetime(2026, 7, 20, 16, 30))
    await po.partner_scan_tick(late)
    assert wired.state["scan_calls"] == 0


# ---------------------------------------------------------------------------
# signal tips: per-bar dedup
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_signal_tip_sent_once_per_bar(wired):
    await _init(wired.db)
    await po.partner_scan_tick(NOW)
    await po.partner_scan_tick(NOW)     # same bar re-scanned next tick
    tips = [s for s in wired.sent if s[0] == "signal"]
    assert len(tips) == 1
    assert "NIFTY ORB LONG" in tips[0][1]
    assert "you own the trade" in tips[0][1]


@pytest.mark.asyncio
async def test_new_bar_gets_a_new_tip(wired):
    await _init(wired.db)
    await po.partner_scan_tick(NOW)
    wired.state["scan"] = _fired_scan(bar_ts="2026-07-20 10:15:00")
    await po.partner_scan_tick(NOW)
    assert len([s for s in wired.sent if s[0] == "signal"]) == 2


@pytest.mark.asyncio
async def test_signal_detail_persisted_for_eod(wired):
    await _init(wired.db)
    await po.partner_scan_tick(NOW)
    import aiosqlite

    async with aiosqlite.connect(wired.db) as db:
        cur = await db.execute(
            "SELECT detail FROM partner_messages WHERE kind='signal'"
        )
        (detail_json,) = await cur.fetchone()
    detail = json.loads(detail_json)
    assert detail["direction"] == "LONG"
    assert detail["stop"] == 25055.0 and detail["target"] == 25167.5


# ---------------------------------------------------------------------------
# event throttle
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_event_throttle_window(wired):
    await _init(wired.db)
    await po._send_event(wired.db, "pcr_shift", "NIFTY", "shift 1", NOW)
    await po._send_event(wired.db, "pcr_shift", "NIFTY", "shift 2", NOW)
    assert len(wired.sent) == 1

    # age the record past the gap -> the next event goes out
    import aiosqlite

    old = (NOW.replace(tzinfo=None)).strftime("%Y-%m-%d %H:%M:%S")
    aged = "2026-07-20 08:00:00"
    async with aiosqlite.connect(wired.db) as db:
        await db.execute(
            "UPDATE partner_messages SET sent_at=? WHERE sent_at=?", (aged, old)
        )
        await db.commit()
    await po._send_event(wired.db, "pcr_shift", "NIFTY", "shift 3", NOW)
    assert len(wired.sent) == 2


@pytest.mark.asyncio
async def test_event_kinds_throttle_independently(wired):
    await _init(wired.db)
    await po._send_event(wired.db, "pcr_shift", "NIFTY", "a", NOW)
    await po._send_event(wired.db, "iv_move", "NIFTY", "b", NOW)
    assert len(wired.sent) == 2


# ---------------------------------------------------------------------------
# morning brief / EOD dedup
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_morning_brief_once_per_day(wired, monkeypatch):
    await _init(wired.db)

    async def _no_chain(kite, book, now, strike_window=None):
        return None

    monkeypatch.setattr(po, "take_chain_snapshot", _no_chain)
    wired.state["scan"] = UnderlyingScan(name="NIFTY", sig=MomSignal(
        bar_ts="", or_high=25010.0, or_low=24990.0, atr=30.0, close=25000.0,
    ))
    await po.partner_morning_brief(NOW)
    await po.partner_morning_brief(NOW)
    briefs = [s for s in wired.sent if s[0] == "brief"]
    assert len(briefs) == 1
    assert "Partner brief" in briefs[0][1]


# ---------------------------------------------------------------------------
# EOD signal-outcome walk
# ---------------------------------------------------------------------------

def _bars(rows):
    idx = pd.to_datetime([f"2026-07-20 {hm}" for hm, *_ in rows])
    cols = list(zip(*[r[1:] for r in rows]))
    return pd.DataFrame({
        "open": cols[0], "high": cols[1], "low": cols[2], "close": cols[3],
    }, index=idx)


DETAIL = {
    "direction": "LONG", "bar_ts": "2026-07-20 09:55:00",
    "close": 25100.0, "stop": 25055.0, "target": 25167.5,
}


def test_outcome_target_first():
    bars = _bars([
        ("09:55", 25010, 25105, 25005, 25100),
        ("10:00", 25100, 25170, 25090, 25160),   # target prints
        ("10:05", 25160, 25165, 25050, 25060),   # stop later: irrelevant
    ])
    assert "target" in po._signal_outcome(bars, DETAIL)


def test_outcome_stop_first():
    bars = _bars([
        ("09:55", 25010, 25105, 25005, 25100),
        ("10:00", 25100, 25110, 25050, 25060),   # stop prints
        ("10:05", 25060, 25200, 25055, 25190),   # target later: irrelevant
    ])
    assert "stop" in po._signal_outcome(bars, DETAIL)


def test_outcome_neither_reports_close():
    bars = _bars([
        ("09:55", 25010, 25105, 25005, 25100),
        ("10:00", 25100, 25120, 25080, 25110),
    ])
    out = po._signal_outcome(bars, DETAIL)
    assert "neither printed" in out and "25,110" in out
