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
    text, kind, r = po._signal_outcome(bars, DETAIL)
    assert "target" in text
    assert kind == "target"
    # 67.5 pts target / 45 pts risk = 1.5R by construction
    assert r == pytest.approx(1.5)


def test_outcome_stop_first():
    bars = _bars([
        ("09:55", 25010, 25105, 25005, 25100),
        ("10:00", 25100, 25110, 25050, 25060),   # stop prints
        ("10:05", 25060, 25200, 25055, 25190),   # target later: irrelevant
    ])
    text, kind, r = po._signal_outcome(bars, DETAIL)
    assert "stop" in text
    assert kind == "stop"
    assert r == pytest.approx(-1.0)


def test_outcome_neither_reports_close():
    bars = _bars([
        ("09:55", 25010, 25105, 25005, 25100),
        ("10:00", 25100, 25120, 25080, 25110),
    ])
    text, kind, r = po._signal_outcome(bars, DETAIL)
    assert "neither printed" in text and "25,110" in text
    assert kind == "neither"
    # +10 pts on 45 pts risk
    assert r == pytest.approx(10.0 / 45.0)


def test_outcome_unavailable_on_garbage():
    text, kind, r = po._signal_outcome(None, {"bar_ts": "not-a-ts"})
    assert kind is None and r is None
    assert "unavailable" in text


# ---------------------------------------------------------------------------
# [PARTNER-ENRICH 2026-07-19] track record (T1c)
# ---------------------------------------------------------------------------

async def _seed_signal(db, key, detail, sent_at="2026-07-15 10:00:00"):
    import aiosqlite
    async with aiosqlite.connect(db) as conn:
        await conn.execute(
            "INSERT OR REPLACE INTO partner_messages "
            "(sent_at, kind, dedup_key, delivered, detail) VALUES (?,?,?,?,?)",
            (sent_at, "signal", key, 1, json.dumps(detail)),
        )
        await conn.commit()


@pytest.mark.asyncio
async def test_track_record_aggregates_resolved_signals(wired, monkeypatch):
    await _init(wired.db)
    monkeypatch.setattr(settings, "PARTNER_TRACK_MIN_N", 3)
    base = {"direction": "LONG", "close": 25100.0, "stop": 25055.0}
    outcomes = [("target", 1.5), ("stop", -1.0), ("target", 1.5), ("neither", 0.2)]
    for i, (kind, r) in enumerate(outcomes):
        await _seed_signal(
            wired.db, f"NIFTY:2026-07-1{i} 09:55:00",
            dict(base, outcome_kind=kind, outcome_r=r),
        )
    # Unresolved signal today + SHORT signal must both be excluded.
    await _seed_signal(wired.db, "NIFTY:2026-07-20 09:55:00", dict(base))
    await _seed_signal(
        wired.db, "NIFTY:2026-07-16 11:00:00",
        {"direction": "SHORT", "outcome_kind": "stop", "outcome_r": -1.0},
    )
    line = await po._track_record(wired.db, "NIFTY", "LONG", NOW)
    assert "2/4 target-first" in line
    # (1.5 - 1.0 + 1.5 + 0.2) / 4 = 0.55 -> +0.6R
    assert "avg +0.6R" in line


@pytest.mark.asyncio
async def test_track_record_empty_below_min_sample(wired, monkeypatch):
    await _init(wired.db)
    monkeypatch.setattr(settings, "PARTNER_TRACK_MIN_N", 5)
    await _seed_signal(
        wired.db, "NIFTY:2026-07-15 09:55:00",
        {"direction": "LONG", "outcome_kind": "target", "outcome_r": 1.5},
    )
    assert await po._track_record(wired.db, "NIFTY", "LONG", NOW) == ""


@pytest.mark.asyncio
async def test_stamp_outcome_roundtrip(wired):
    import aiosqlite
    await _init(wired.db)
    detail = {"direction": "LONG", "bar_ts": "2026-07-20 09:55:00"}
    await _seed_signal(wired.db, "NIFTY:2026-07-20 09:55:00", detail,
                       sent_at="2026-07-20 09:56:40")
    await po._stamp_outcome(
        wired.db, "NIFTY:2026-07-20 09:55:00", detail, "target", 1.5,
    )
    async with aiosqlite.connect(wired.db) as conn:
        cur = await conn.execute(
            "SELECT sent_at, detail FROM partner_messages WHERE dedup_key=?",
            ("NIFTY:2026-07-20 09:55:00",),
        )
        sent_at, detail_json = await cur.fetchone()
    stamped = json.loads(detail_json)
    assert stamped["outcome_kind"] == "target"
    assert stamped["outcome_r"] == 1.5
    # sent_at untouched: it doubles as the retention timestamp.
    assert sent_at == "2026-07-20 09:56:40"


# ---------------------------------------------------------------------------
# [PARTNER-ENRICH 2026-07-19] option premium outcome (T2b)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_option_outcome_line_from_ltp_series(wired):
    import fno_oi_store
    await fno_oi_store.init_oi_db(wired.db)
    import aiosqlite
    async with aiosqlite.connect(wired.db) as conn:
        for ts, ltp in [
            ("2026-07-20 09:50:00", 100.0),   # before the signal: excluded
            ("2026-07-20 10:00:00", 120.0),
            ("2026-07-20 10:05:00", 156.0),
            ("2026-07-20 15:25:00", 140.0),
        ]:
            await conn.execute(
                "INSERT INTO fno_chain_oi "
                "(snap_ts, underlying, expiry, strike, opt_type, oi, volume, ltp, iv) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (ts, "NIFTY", "2026-07-23", 25000.0, "CE", 1000, 100, ltp, 0.12),
            )
        await conn.commit()
    detail = {
        "underlying": "NIFTY", "bar_ts": "2026-07-20 09:55:00",
        "tradingsymbol": "NIFTY25JUL25000CE", "strike": 25000.0,
        "opt_type": "CE", "expiry": "2026-07-23", "premium_paid": 112.0,
    }
    line = await po._option_outcome_line(detail, "2026-07-20")
    assert "paid ~112.0" in line
    assert "peak 156.0 (+39%)" in line
    assert "last 140.0 (+25%)" in line


@pytest.mark.asyncio
async def test_option_outcome_line_empty_without_option_or_rows(wired):
    import fno_oi_store
    await fno_oi_store.init_oi_db(wired.db)
    assert await po._option_outcome_line({"direction": "LONG"}, "2026-07-20") == ""
    detail = {
        "underlying": "NIFTY", "tradingsymbol": "X", "strike": 25000.0,
        "opt_type": "CE", "expiry": "2026-07-23", "premium_paid": 112.0,
    }
    assert await po._option_outcome_line(detail, "2026-07-20") == ""


# ---------------------------------------------------------------------------
# [PARTNER-ENRICH 2026-07-19] scan tick with a strike pick (T1a/T1d wiring)
# ---------------------------------------------------------------------------

def _chain_quote(strike, ot, oi, ltp, lot_size=75):
    from fno_models import Contract, ContractQuote
    c = Contract(
        token=int(strike) * 10 + (1 if ot == "CE" else 2),
        tradingsymbol=f"NIFTY25JUL{int(strike)}{ot}",
        name="NIFTY", expiry=date(2026, 7, 23), strike=float(strike),
        instrument_type=ot, lot_size=lot_size,
    )
    return ContractQuote(
        contract=c, bid=ltp - 0.5, ask=ltp + 0.5, ltp=ltp,
        oi=oi, volume=50000,
    )


def _mk_snap(oi_and_ltp, forward=25100.0, now=NOW):
    """oi_and_ltp: {(strike, ot): (oi, ltp)}"""
    from fno_chain import ChainSnapshot
    from fno_models import Contract, ContractQuote
    quotes = {
        (float(k), ot): _chain_quote(k, ot, oi, ltp)
        for (k, ot), (oi, ltp) in oi_and_ltp.items()
    }
    fut_c = Contract(
        token=900, tradingsymbol="NIFTYFUT", name="NIFTY",
        expiry=date(2026, 7, 30), strike=0.0, instrument_type="FUT",
        lot_size=75,
    )
    fut_q = ContractQuote(
        contract=fut_c, bid=forward - 1, ask=forward + 1, ltp=forward,
        oi=200000,
    )
    return ChainSnapshot(
        taken_at=now, expiry=date(2026, 7, 23), forward=forward,
        parity_forward=None, lot_size=75, fut_quote=fut_q, quotes=quotes,
    )


@pytest.mark.asyncio
async def test_scan_tick_with_pick_ships_scenarios_and_sizing(wired):
    await _init(wired.db)
    scan = _fired_scan()
    scan.snap = _mk_snap({(25100, "CE"): (150000, 112.0)})
    scan.pick = (scan.snap.quotes[(25100.0, "CE")], 0.12, 0.55)
    wired.state["scan"] = scan
    await po.partner_scan_tick(NOW)
    tips = [s for s in wired.sent if s[0] == "signal"]
    assert len(tips) == 1
    msg = tips[0][1]
    assert "at target ≈" in msg and "at stop ≈" in msg
    assert "option RR ≈" in msg
    assert "risk to stop" in msg
    # detail now carries what the EOD premium-path needs
    import aiosqlite
    async with aiosqlite.connect(wired.db) as db:
        cur = await db.execute(
            "SELECT detail FROM partner_messages WHERE kind='signal'"
        )
        (detail_json,) = await cur.fetchone()
    detail = json.loads(detail_json)
    assert detail["strike"] == 25100.0
    assert detail["opt_type"] == "CE"
    assert detail["expiry"] == "2026-07-23"
    assert detail["premium_paid"] == pytest.approx(112.5)  # ask side


# ---------------------------------------------------------------------------
# [PARTNER-ENRICH 2026-07-19] analytics tick: wall flow (T2a) + pin (T3a)
# ---------------------------------------------------------------------------

@pytest.fixture
def analytics_wired(wired, monkeypatch):
    import asyncio
    import main

    monkeypatch.setattr(main, "state_lock", asyncio.Lock())

    async def _no_halt(db_path):
        return False, []

    monkeypatch.setattr(main, "check_circuit_breakers", _no_halt)
    monkeypatch.setattr(main, "momentum_signals_today", [], raising=False)
    monkeypatch.setattr(po, "load_underlying_names", lambda: set())
    # module-global event state must not leak across tests
    monkeypatch.setattr(po, "_last_wall_flow_reported", {})
    monkeypatch.setattr(po, "_last_walls_reported", {})
    monkeypatch.setattr(po, "_last_iv_reported", {})
    monkeypatch.setattr(po, "_last_regime_reported", None)
    monkeypatch.setattr(po, "_halt_reported_on", None)

    state = {"snap": None}

    async def _chain(kite, book, now, strike_window=None):
        return state["snap"]

    monkeypatch.setattr(po, "take_chain_snapshot", _chain)
    wired.analytics = state
    return wired


BASE_CHAIN = {
    (24900, "PE"): (10000, 40.0), (24900, "CE"): (2000, 240.0),
    (25100, "PE"): (3000, 90.0), (25100, "CE"): (10000, 110.0),
}


@pytest.mark.asyncio
async def test_wall_flow_fires_on_oi_build_and_not_on_repeat(analytics_wired):
    import fno_oi_store
    w = analytics_wired
    await _init(w.db)
    await fno_oi_store.init_oi_db(w.db)
    # tick 1 (baseline snapshot persists; no baseline delta yet)
    w.analytics["snap"] = _mk_snap(BASE_CHAIN)
    await po.partner_analytics_tick(NOW)
    assert [s for s in w.sent if s[0] == "wall_flow"] == []
    # tick 2: support strike PE OI +30% vs open -> defended event
    # (distinct taken_at, else the snapshot row REPLACEs the baseline)
    grown = dict(BASE_CHAIN)
    grown[(24900, "PE")] = (13000, 40.0)
    later = IST.localize(datetime(2026, 7, 20, 10, 33))
    w.analytics["snap"] = _mk_snap(grown, now=later)
    await po.partner_analytics_tick(later)
    flows = [s for s in w.sent if s[0] == "wall_flow"]
    assert len(flows) == 1
    assert "Support 24,900 PE OI +30% vs open" in flows[0][1]
    assert "defended" in flows[0][1]
    # tick 3: unchanged OI -> no re-report
    even_later = IST.localize(datetime(2026, 7, 20, 11, 33))
    await po.partner_analytics_tick(even_later)
    assert len([s for s in w.sent if s[0] == "wall_flow"]) == 1


@pytest.mark.asyncio
async def test_wall_flow_support_and_resistance_both_fire_same_tick(analytics_wired):
    """Regression: support (PE) and resistance (CE) throttle independently.
    With a shared throttle key the second one was silently dropped."""
    import fno_oi_store
    w = analytics_wired
    await _init(w.db)
    await fno_oi_store.init_oi_db(w.db)
    w.analytics["snap"] = _mk_snap(BASE_CHAIN)
    await po.partner_analytics_tick(NOW)
    # both walls move >= threshold in the same later tick
    grown = dict(BASE_CHAIN)
    grown[(24900, "PE")] = (13000, 40.0)   # support PE +30%
    grown[(25100, "CE")] = (13000, 110.0)  # resistance CE +30%
    later = IST.localize(datetime(2026, 7, 20, 10, 33))
    w.analytics["snap"] = _mk_snap(grown, now=later)
    await po.partner_analytics_tick(later)
    flows = [s for s in w.sent if s[0] == "wall_flow"]
    assert len(flows) == 2
    joined = " ".join(f[1] for f in flows)
    assert "Support 24,900 PE" in joined
    assert "Resistance 25,100 CE" in joined


@pytest.mark.asyncio
async def test_pin_note_once_on_expiry_afternoon(analytics_wired, monkeypatch):
    import fno_oi_store
    w = analytics_wired
    await _init(w.db)
    await fno_oi_store.init_oi_db(w.db)

    class _ExpiryBook(_Book):
        def is_expiry_day(self, day):
            return True

    monkeypatch.setattr(po, "get_instruments_for", lambda name: _ExpiryBook())
    w.analytics["snap"] = _mk_snap(BASE_CHAIN)
    afternoon = IST.localize(datetime(2026, 7, 20, 13, 35))
    await po.partner_analytics_tick(afternoon)
    pins = [s for s in w.sent if s[0] == "pin"]
    assert len(pins) == 1
    assert "max pain" in pins[0][1]
    # re-tick: once per day only
    await po.partner_analytics_tick(
        IST.localize(datetime(2026, 7, 20, 14, 35))
    )
    assert len([s for s in w.sent if s[0] == "pin"]) == 1


@pytest.mark.asyncio
async def test_no_pin_before_1330_or_off_expiry(analytics_wired):
    import fno_oi_store
    w = analytics_wired
    await _init(w.db)
    await fno_oi_store.init_oi_db(w.db)
    w.analytics["snap"] = _mk_snap(BASE_CHAIN)
    # _Book.is_expiry_day is False -> never a pin even in the afternoon
    await po.partner_analytics_tick(
        IST.localize(datetime(2026, 7, 20, 14, 35))
    )
    assert [s for s in w.sent if s[0] == "pin"] == []
