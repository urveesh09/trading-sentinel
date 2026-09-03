import os
import sqlite3
import sys

import pytest

HERE = os.path.dirname(__file__)
ENGINE_DIR = os.path.abspath(os.path.join(HERE, ".."))
if ENGINE_DIR not in sys.path:
    sys.path.insert(0, ENGINE_DIR)

import memory_metrics
import penny_edge_engine as pee


def test_memory_metrics_report_current_and_peak_rss():
    """Both values must be available without adding a psutil dependency."""
    if not os.path.exists("/proc/self/status"):
        pytest.skip("current-RSS probe targets the Linux production container")
    assert memory_metrics.current_rss_kb() > 0
    assert memory_metrics.peak_rss_kb() >= memory_metrics.current_rss_kb()


def test_recent_edge_loader_bounds_each_ticker_and_keeps_order(tmp_path):
    db_path = tmp_path / "edge.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        """CREATE TABLE ohlcv_cache (
            ticker TEXT, date TEXT, open REAL, high REAL, low REAL,
            close REAL, volume REAL
        )"""
    )
    rows = []
    for ticker in ("AAA", "BBB"):
        for day in range(1, 81):
            date = f"2026-01-{day:03d}"
            rows.append((ticker, date, day, day + 1, day - 1, day, 1000))
    conn.executemany("INSERT INTO ohlcv_cache VALUES (?, ?, ?, ?, ?, ?, ?)", rows)

    loaded = pee.load_recent_daily_bars_from_db(conn, "2026-01-080", 60)
    conn.close()

    assert set(loaded) == {"AAA", "BBB"}
    assert all(len(bars) == 60 for bars in loaded.values())
    assert loaded["AAA"][0]["date"] == "2026-01-021"
    assert loaded["AAA"][-1]["date"] == "2026-01-080"


def test_recent_edge_loader_rejects_insufficient_feature_window(tmp_path):
    conn = sqlite3.connect(tmp_path / "edge.db")
    conn.execute("CREATE TABLE ohlcv_cache (ticker TEXT, date TEXT, open REAL, high REAL, low REAL, close REAL, volume REAL)")
    with pytest.raises(ValueError, match="20-session feature lookback"):
        pee.load_recent_daily_bars_from_db(conn, "2026-01-01", 20)
    conn.close()
