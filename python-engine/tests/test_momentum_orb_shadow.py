"""[M01] The stocks-in-play breakout paper shadow: the frozen research rule, read from the caches, no orders."""
from datetime import datetime
import importlib.util
from pathlib import Path
import sqlite3
import sys

import pandas as pd
import pytest

import momentum_orb_shadow as orb
from config import settings

DAY = "2026-11-09"
LAB = Path(__file__).resolve().parents[2] / "docs/research/simulation/2026-11-08-momentum-m01"


def session(open_, first, later, volume=20000.0):
    """15-minute bars 09:15-15:15: a first bar ``first`` (o, h, l, c), then ``later`` closes (flat bars)."""
    stamps = pd.date_range(f"{DAY} 09:15", f"{DAY} 15:15", freq="15min")
    rows = [dict(zip(("open", "high", "low", "close"), first), volume=volume)]
    price = first[3]
    for k in range(1, len(stamps)):
        close = later[k - 1] if k - 1 < len(later) else price
        rows.append({"open": price, "high": max(price, close) + .2, "low": min(price, close) - .2, "close": close,
                     "volume": 10000.0})
        price = close
    return pd.DataFrame(rows, index=stamps)


def daily(close=100.0, volume=1_000_000.0, rows=30):
    dates = pd.date_range("2026-09-01", periods=rows, freq="B").strftime("%Y-%m-%d")
    return pd.DataFrame({"open": close, "high": close + 1, "low": close - 1, "close": close, "volume": volume},
                        index=dates)


def market():
    """Seven names: five green in play, one red, one illiquid. WIN runs up; LOSE falls through its stop."""
    up = [101.5 + .5 * k for k in range(30)]
    bars = {
        "WIN": session(100, (100, 101, 99.5, 100.8), up, volume=40000),
        "LOSE": session(100, (100, 101, 99.5, 100.8), [101.4, 99.0], volume=30000),
        "FLAT": session(100, (100, 101, 99.5, 100.8), [100.5], volume=25000),
        "FADE": session(100, (100, 101, 99.5, 100.8), [101.3, 100.2, 99.8], volume=22000),
        "SLOW": session(100, (100, 101, 99.5, 100.8), [101.2] * 30, volume=21000),
        "RED": session(100, (100, 101, 99.0, 99.4), up, volume=90000),
        "THIN": session(100, (100, 101, 99.5, 100.8), up, volume=90000),
    }
    prior = {t: daily() for t in bars}
    prior["THIN"] = daily(volume=1000.0)        # median traded value Rs 1 lakh, under Rs 5 crore
    return bars, prior


def test_the_top_five_green_names_in_play_trade_the_first_bar_breakout():
    bars, prior = market()
    result = orb.session_trades(DAY, bars, prior)
    assert [t for t, _r in result["picks"]] == ["WIN", "LOSE", "FLAT", "FADE", "SLOW"]   # RED red, THIN illiquid
    trades = {t["ticker"]: t for t in result["trades"]}
    assert trades["WIN"]["reason"] == "deadline" and trades["WIN"]["net"] > 0
    assert trades["LOSE"]["reason"] == "stop" and trades["LOSE"]["net"] < 0
    assert trades["FADE"]["reason"] in {"vwap_exit", "stop"}
    assert "FLAT" not in trades                  # never traded through the first bar's high
    for t in result["trades"]:
        assert t["qty"] * t["entry"] <= orb.CAP + 1e-6
        assert t["entry"] == pytest.approx(101.0 * (1 + orb.SLIP)) and t["stop"] == 99.5


def _lab():
    if not (LAB / "lab.py").is_file():
        pytest.skip("M01 research lab not in this checkout")
    sys.path.insert(0, str(LAB))
    spec = importlib.util.spec_from_file_location("m01_lab", LAB / "lab.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["m01_lab"] = module              # its dataclasses look their module up
    spec.loader.exec_module(module)
    return module


def test_the_runtime_rule_is_the_frozen_research_arm():
    lab = _lab()
    bars, prior = market()
    data = {"window": "TEST", "bars": {(t, DAY): b for t, b in bars.items()},
            "daily": {t: p.set_axis(pd.to_datetime(p.index)) for t, p in prior.items()}}
    research = lab.orb_day(data, DAY, lab.Orb("top5_vwap", exit=lab.Exit("VWAP", vwap_exit=True)), 600.0, 10000.0)
    runtime = orb.session_trades(DAY, bars, prior)["trades"]
    key = lambda x: (x["ticker"], x["entry_at"], round(x["entry"], 6), x["qty"], x["reason"], round(x["net"], 6))
    assert sorted(map(key, research)) == sorted(map(key, runtime))


def _cache(tmp_path):
    bars, prior = market()
    path = tmp_path / "cache.db"
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE intraday_cache (ticker TEXT, interval TEXT, datetime TEXT, open REAL, high REAL, "
                     "low REAL, close REAL, volume REAL, fetched_at TEXT)")
        conn.execute("CREATE TABLE ohlcv_cache (ticker TEXT, date TEXT, open REAL, high REAL, low REAL, close REAL, "
                     "volume REAL, fetched_at TEXT)")
        for t, frame in bars.items():
            for stamp, r in frame.iterrows():
                if stamp.strftime("%H:%M") <= "14:30":          # what the 14:45 scan has cached
                    conn.execute("INSERT INTO intraday_cache VALUES (?,?,?,?,?,?,?,?,?)",
                                 (t, "15minute", stamp.strftime("%Y-%m-%d %H:%M:%S"), r.open, r.high, r.low, r.close,
                                  r.volume, ""))
        for t, frame in prior.items():
            for d, r in frame.iterrows():
                conn.execute("INSERT INTO ohlcv_cache VALUES (?,?,?,?,?,?,?,?)",
                             (t, d, r.open, r.high, r.low, r.close, r.volume, ""))
    return str(path)


def test_a_session_is_recorded_once_from_the_caches_and_compared(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "MOMENTUM_ORB_SHADOW_ENABLED", True)
    db = _cache(tmp_path)
    first = orb.run_day(db, DAY)
    assert first["status"] == "recorded" and first["trades"] >= 2 and first["actual_fill"] == "UNKNOWN"
    assert orb.run_day(db, DAY)["status"] == "repeat"
    report = orb.comparison(db)
    assert report["status"] == "observed" and report["sessions"] == 1 and report["trades"] == first["trades"]
    assert report["net"] == pytest.approx(first["net"])


def test_disabled_or_unread_never_creates_a_store(tmp_path, monkeypatch):
    db = _cache(tmp_path)
    assert orb.comparison(db)["status"] == "not_collected"
    monkeypatch.setattr(settings, "MOMENTUM_ORB_SHADOW_ENABLED", False)
    assert orb.run_day(db, DAY) == {"status": "disabled"}
    assert not Path(orb.store_path(db)).exists()


@pytest.mark.asyncio
async def test_the_job_skips_a_holiday_and_never_touches_the_broker(tmp_path, monkeypatch):
    from unittest.mock import AsyncMock
    import main
    monkeypatch.setattr(settings, "MOMENTUM_ORB_SHADOW_ENABLED", True)
    monkeypatch.setattr(settings, "DB_PATH", _cache(tmp_path))
    monkeypatch.setattr(main, "is_trading_day", AsyncMock(return_value=False))
    assert await orb.run_momentum_orb_shadow(datetime.fromisoformat(f"{DAY}T15:05:00")) is None
    assert not Path(orb.store_path(settings.DB_PATH)).exists()
    monkeypatch.setattr(main, "is_trading_day", AsyncMock(return_value=True))
    result = await orb.run_momentum_orb_shadow(datetime.fromisoformat(f"{DAY}T15:05:00"))
    assert result["status"] == "recorded"
    source = Path(orb.__file__).read_text(encoding="utf-8")
    assert "place_order" not in source and "kite" not in source.lower().replace("no kite call", "")
