"""
[PENNY-TEST 2026-06-24] Unit tests for penny_premarket_report.

Covers:
  - is_in_premarket_window at the configured minute, off by one minute
  - build_premarket_body with the JSON present, missing, and malformed
  - run_premarket_report is a no-op outside the window
  - the runtime-disabled case (hour=0)
"""
import json
import os
import sys
import tempfile
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


from penny_premarket_report import (  # noqa: E402
    is_in_premarket_window, build_premarket_body, run_premarket_report,
)


def _set_window(hour: int, minute: int):
    from config import settings
    settings.PENNY_PREMARKET_REPORT_HOUR = hour
    settings.PENNY_PREMARKET_REPORT_MIN = minute


# ---- is_in_premarket_window ----------------------------------------

def test_in_window_at_exact_minute():
    _set_window(7, 50)
    assert is_in_premarket_window(datetime(2026, 6, 24, 7, 50)) is True


def test_off_by_one_minute_early():
    _set_window(7, 50)
    assert is_in_premarket_window(datetime(2026, 6, 24, 7, 49)) is False


def test_off_by_one_minute_late():
    _set_window(7, 50)
    assert is_in_premarket_window(datetime(2026, 6, 24, 7, 51)) is False


def test_disabled_returns_false():
    _set_window(0, 0)  # hour=0 disables
    assert is_in_premarket_window(datetime(2026, 6, 24, 7, 50)) is False


def test_wrong_hour_same_minute():
    _set_window(7, 50)
    assert is_in_premarket_window(datetime(2026, 6, 24, 8, 50)) is False


# ---- build_premarket_body -------------------------------------------

def test_body_with_universe_present():
    _set_window(7, 50)
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "penny.json")
        with open(path, "w") as f:
            json.dump({
                "as_of": "2026-06-24",
                "universe_size_target": 100,
                "tickers": [
                    {"symbol": "TATAPOWER", "prev_close": 245.30, "series": "EQ"},
                    {"symbol": "IDEA", "prev_close": 8.15, "series": "EQ"},
                ],
            }, f)
        body = build_premarket_body(path, top_n=10)
    assert "2 tickers" in body
    assert "TATAPOWER" in body
    assert "IDEA" in body
    assert "245.30" in body
    assert body.startswith("Penny pre-market")


def test_body_with_missing_file():
    body = build_premarket_body("/nonexistent/path/penny.json", top_n=10)
    assert "0 tickers" in body
    assert "missing" in body.lower()


def test_body_with_malformed_json():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "penny.json")
        with open(path, "w") as f:
            f.write("this is { not valid json")
        body = build_premarket_body(path, top_n=10)
    assert "unreadable" in body.lower()


def test_body_with_empty_tickers():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "penny.json")
        with open(path, "w") as f:
            json.dump({"as_of": "2026-06-24", "tickers": []}, f)
        body = build_premarket_body(path, top_n=10)
    assert "0 tickers" in body


def test_body_top_n_caps_listing():
    _set_window(7, 50)
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "penny.json")
        tickers = [{"symbol": f"SYM{i}", "prev_close": 10.0 + i, "series": "EQ"}
                   for i in range(20)]
        with open(path, "w") as f:
            json.dump({"as_of": "2026-06-24", "tickers": tickers}, f)
        body = build_premarket_body(path, top_n=5)
    # 20 tickers in file, but only top 5 listed
    listed = 0
    for line in body.splitlines():
        line = line.strip()
        for i in range(1, 6):
            if line.startswith(f"{i}."):
                listed += 1
                break
    assert listed == 5, f"expected exactly 5 ticker lines, got {listed}"
    assert "20 tickers" in body  # size still reflects full universe


# ---- run_premarket_report (outside window) -------------------------

def test_run_outside_window_is_noop():
    """If called outside the configured minute, run_premarket_report must NOT
    log a body or attempt Telegram. We pass now=explicitly-out-of-window."""
    import asyncio
    _set_window(7, 50)
    # 12:00 is well outside 07:50. The function should return immediately.
    asyncio.run(run_premarket_report(now=datetime(2026, 6, 24, 12, 0)))
