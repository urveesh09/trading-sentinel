"""[N13] The paper N11 lock on one look a minute (fno_lock_cadence), and the N11 main book's underlyings."""
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
import pytz

import fno_lock_cadence as cad
from fno_exit_rules import evaluate_single_leg_exit

IST = pytz.timezone("Asia/Kolkata")
T0 = IST.localize(datetime(2026, 11, 5, 10, 51, 30))
# OR20's own exits on N11 (fno_book.EXIT_OVERRIDES["N11_OR20"]), as recorded with position 58 on Nov 5.
OR20 = {"FNO_HARD_FLAT_MIN": 910, "FNO_PROFIT_LOCK_ARM_R": 0.8, "FNO_PROFIT_LOCK_CONFIRM_SEC": 8.0,
        "FNO_PROFIT_LOCK_ENABLED": True, "FNO_PROFIT_LOCK_FLOOR_R": 0.1, "FNO_PROFIT_LOCK_KEEP_FRACTION": 0.5,
        "FNO_STOP_PREMIUM_PCT": 0.25, "FNO_TIME_STOP_MIN": 75.0, "FNO_TIME_STOP_MIN_R": 0.5,
        "FNO_TIME_STOP_RESPECTS_PREMIUM": False, "FNO_TRAIL_ATR_MULT": 2.0}
MINUTE = {**OR20, cad.LOOK_KEY: 55.0}


def _position(**kw):
    base = dict(direction="LONG", entry_time=T0.isoformat(), entry_premium=154.0, entry_underlying=24396.0,
                stop_underlying=24340.0, target_underlying=24600.0, premium_stop=115.5, atr_at_entry=40.0,
                trail_active=0, trail_stop_underlying=None, best_underlying=None, best_premium=None)
    base.update(kw)
    return SimpleNamespace(**base)


def _walk(path, params, fut=24440.0):
    """Run looks (seconds after T0, bid) through the cadence wrapper as the orchestrator does; the first exit or None."""
    p = _position()
    breach = look = None
    for sec, bid, *rest in path:
        now = T0 + timedelta(seconds=sec)
        f = rest[0] if rest else fut
        d, look = cad.evaluate(p, now_ist=now, fut_price=f, exit_px_basis=bid, hard_flat=False, params=params,
                               lock_breach_since=breach, lock_look_at=look)
        breach = d.lock_breach_since
        if d.exit_reason:
            return d.exit_reason, sec, bid
        if d.persist_trail:
            p.trail_active, p.trail_stop_underlying, p.best_underlying = (1 if d.trail_active else 0, d.trail_stop,
                                                                          d.best_underlying)
        p.best_premium = d.best_premium
    return None


def _nov5_like():
    """A minute-sampled climb to ~182 with one 10-second spike to 189.7 and later a 10-second dip under its floor."""
    path = []
    for i in range(0, 4200, 10):                       # 70 minutes of 10-second looks
        bid = min(182.0, 154.0 + i / 100.0)
        if i == 3010:
            bid = 189.7                                # a 10-second peak between minute looks
        if i in (3610, 3620):
            bid = 170.35 if i == 3610 else 170.95      # a 10-second dip under the 10-s floor (171.85)
        path.append((i, bid))
    return path


def test_off_is_the_ladder_exactly():
    p = _position()
    now = T0 + timedelta(minutes=3)
    for params in (OR20, {**OR20, cad.LOOK_KEY: 0}, {**OR20, cad.LOOK_KEY: None}):
        d, look = cad.evaluate(p, now_ist=now, fut_price=24450.0, exit_px_basis=170.0, hard_flat=False,
                               params=params, lock_breach_since=None, lock_look_at=None)
        assert d == evaluate_single_leg_exit(p, now_ist=now, fut_price=24450.0, exit_px_basis=170.0,
                                             hard_flat=False, params=params, lock_breach_since=None)
        assert look is None


def test_nov5_ten_second_lock_sells_the_dip_and_the_minute_lock_holds():
    """[N13] Reproduced: Nov 5's OR20 call (best 189.70 on one 10-s look, floor 171.85, sold at 170.95 after the 8 s
    confirmation). On one look a minute neither the spike nor the dip is read and the lock holds."""
    path = _nov5_like()
    assert _walk(path, OR20) == ("profit_lock", 3620, 170.95)
    assert _walk(path, MINUTE) is None


def test_the_minute_lock_sells_on_its_first_look_under_the_floor_without_confirmation():
    path = [(i, min(190.0, 154.0 + i / 50.0)) for i in range(0, 1800, 10)]       # best 190 on minute looks
    path += [(1800 + i, 168.0) for i in range(0, 300, 10)]                        # floor 172: a lasting fall
    reason, sec, bid = _walk(path, MINUTE)
    assert reason == "profit_lock" and bid == 168.0
    assert sec - 1800 < 60                       # within the first minute look under the floor, no 8 s wait


def test_stops_trail_and_backstop_still_read_every_look():
    stop = [(i, 160.0, 24400.0) for i in range(0, 120, 10)] + [(125, 150.0, 24335.0)]   # a 5-second stop between looks
    assert _walk(stop, MINUTE) == ("underlying_stop", 125, 150.0)
    backstop = [(i, 160.0) for i in range(0, 120, 10)] + [(125, 110.0)]
    assert _walk(backstop, MINUTE) == ("premium_backstop", 125, 110.0)


def test_the_best_moves_only_on_lock_looks_and_hard_flat_is_never_held():
    p = _position(best_premium=170.0)
    look = T0
    d, look2 = cad.evaluate(p, now_ist=T0 + timedelta(seconds=10), fut_price=24450.0, exit_px_basis=200.0,
                            hard_flat=False, params=MINUTE, lock_look_at=look)
    assert d.best_premium == 170.0 and look2 == look and d.exit_reason == ""
    d, look3 = cad.evaluate(p, now_ist=T0 + timedelta(seconds=55), fut_price=24450.0, exit_px_basis=200.0,
                            hard_flat=False, params=MINUTE, lock_look_at=look)
    assert d.best_premium == 200.0 and look3 == T0 + timedelta(seconds=55)
    d, _ = cad.evaluate(p, now_ist=T0 + timedelta(seconds=20), fut_price=24450.0, exit_px_basis=200.0,
                        hard_flat=True, params=MINUTE, lock_look_at=look)
    assert d.exit_reason == "hard_flat_1510"
    assert cad.is_lock_look(MINUTE, T0 - timedelta(seconds=5), T0)      # a clock that went back is a fresh minute


def test_it_applies_to_paper_n11_positions_only(monkeypatch):
    from config import settings
    from fno_models import FnoSource
    n11 = SimpleNamespace(strategy="N11_OR20")
    assert not cad.applies(FnoSource.FNO_PAPER.value, True, n11)          # off by default (FORWARD_CADENCE.md)
    monkeypatch.setattr(settings, "FNO_N13_LOCK_LOOK_SEC", 55.0)
    assert cad.applies(FnoSource.FNO_PAPER.value, True, n11)
    assert not cad.applies(FnoSource.FNO_PAPER.value, False, n11)          # a paper-forced live leg
    assert not cad.applies(FnoSource.FNO_LIVE.value, True, n11)            # real money: never
    assert not cad.applies(FnoSource.FNO_PAPER.value, True, SimpleNamespace(strategy="OR20"))
    assert cad.applies(FnoSource.FNO_PAPER.value, True, SimpleNamespace(strategy="N11_ADD"))
    monkeypatch.setattr(settings, "FNO_N13_LOCK_LOOK_SEC", 0.0)
    assert not cad.applies(FnoSource.FNO_PAPER.value, True, n11)


def test_the_n11_main_book_enters_nifty_only_by_default(monkeypatch):
    import fno_orchestrator as orch
    from config import settings
    assert settings.FNO_N13_MAIN_UNDERLYINGS == "NIFTY" and settings.FNO_N13_LOCK_LOOK_SEC == 0.0
    assert orch.n13_main_underlying("NIFTY") and orch.n13_main_underlying(" nifty ")
    assert not orch.n13_main_underlying("SENSEX")
    monkeypatch.setattr(settings, "FNO_N13_MAIN_UNDERLYINGS", "NIFTY,SENSEX")
    assert orch.n13_main_underlying("SENSEX")
    monkeypatch.setattr(settings, "FNO_N13_MAIN_UNDERLYINGS", "")
    assert orch.n13_main_underlying("SENSEX")


@pytest.mark.asyncio
async def test_the_paper_loop_holds_a_ten_second_dip_on_the_minute_clock_and_sells_a_lasting_fall(tmp_path,
                                                                                                    monkeypatch):
    """[N13] Through fno_orchestrator._manage_open_positions: a held N11 call (best Rs 260, native floor Rs 230)
    dips to Rs 228 for 10 seconds between minute looks. The old 10-second cadence sells it (look + 8 s confirmation);
    the minute cadence holds, and sells when the fall is still there at its next look."""
    from tests.test_fno_trend_lock import NOW, _walk
    flat = [(NOW + timedelta(minutes=m, seconds=50), 22610.0, 240.0) for m in range(16)]
    dip = flat + [(NOW + timedelta(minutes=16), 22610.0, 228.0), (NOW + timedelta(minutes=16, seconds=10), 22610.0, 228.0),
                  (NOW + timedelta(minutes=16, seconds=20), 22610.0, 240.0), (NOW + timedelta(minutes=16, seconds=50), 22610.0, 240.0)]
    old = await _walk(tmp_path / "ten", monkeypatch, enabled=False, look_sec=0.0, looks=dip)
    assert [c.get("reason") for c in old] == ["profit_lock"]
    minute = await _walk(tmp_path / "minute", monkeypatch, enabled=False, look_sec=55.0, looks=dip)
    assert minute == []
    lasting = flat + [(NOW + timedelta(minutes=16), 22610.0, 228.0), (NOW + timedelta(minutes=16, seconds=50), 22610.0, 228.0)]
    sold = await _walk(tmp_path / "lasting", monkeypatch, enabled=False, look_sec=55.0, looks=lasting)
    assert [c.get("reason") for c in sold] == ["profit_lock"]


@pytest.mark.asyncio
async def test_a_sensex_n11_signal_is_logged_once_as_a_shadow_and_never_traded(tmp_path, monkeypatch):
    """[N13] Nov 11: two SENSEX entries took the book's 3 trades a day and the 14:10 NIFTY OR20 put was refused
    trades_per_day. Now a SENSEX N11 signal stops before the chain snapshot: one fno_signals row per bar
    (n13_shadow:<strategy>), no entry. NIFTY's goes on as before."""
    import aiosqlite
    import fno_book
    import fno_orchestrator as orch
    from config import settings
    from fno_engine_mom import MomSignal
    from fno_models import FnoDirection
    from fno_signal_log import init_fno_signal_db
    db = str(tmp_path / "cache.db")
    await init_fno_signal_db(db)
    monkeypatch.setattr(settings, "FNO_BOOK", "N11")
    fired = MomSignal(bar_ts="2026-11-11 10:15:00", direction=FnoDirection.LONG, close=82300.0, strategy="N11_OR20")

    async def drive(*a, **k):
        return 0.7, "HIGH"

    async def adx(*a, **k):
        return 36.0, "HIGH"

    monkeypatch.setattr(fno_book, "drive_today", drive)
    monkeypatch.setattr(fno_book, "adx_today", adx)
    monkeypatch.setattr(fno_book, "n11_signal", lambda *a, **k: fired)
    snaps, entries = [], []

    async def no_snapshot(*a, **k):
        snaps.append(a)
        return None

    async def no_entry(*a, **k):
        entries.append(a)
        return None

    monkeypatch.setattr(orch, "take_chain_snapshot", no_snapshot)
    monkeypatch.setattr(orch, "_try_entry_for_leg", no_entry)
    at = IST.localize(datetime(2026, 11, 11, 10, 16))
    summary = {"stage_durations_sec": {}, "entries": []}
    kw = dict(bars=object(), sig=MomSignal(bar_ts=fired.bar_ts), snap=None, rvol_bars=None, regime="REGIME_2_ELEVATED",
              now_ist=at, evaluation_now_ist=at, scan_id="s1", is_trading_day=True, action_clock=None,
              paper_exec=None, live_exec=None)
    for _ in range(3):                                   # the 60-second tick sees the same bar three times
        note, _bars = await orch._single_leg_entries(None, db, "SENSEX", None, None, summary, **kw)
        assert note == "n13_shadow_underlying"
    async with aiosqlite.connect(db) as con:
        rows = await (await con.execute("SELECT underlying, leg, accepted, reject_reason, direction, bar_ts "
                                        "FROM fno_signals")).fetchall()
    assert rows == [("SENSEX", "FNO_PAPER", 0, "n13_shadow:N11_OR20", "LONG", "2026-11-11 10:15:00")]
    assert snaps == [] and entries == [] and summary["entries"] == []
    monkeypatch.setattr(settings, "FNO_N13_MAIN_UNDERLYINGS", "NIFTY,SENSEX")    # back to Oct 29: SENSEX trades
    note, _ = await orch._single_leg_entries(None, db, "SENSEX", None, None, summary, **kw)
    assert note == "chain_unavailable" and len(snaps) == 1
