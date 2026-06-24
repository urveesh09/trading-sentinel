"""
[PENNY-TEST 2026-06-24] Unit tests for the soft time-stop helper in
penny_engine_breakout.

The time-stop is "soft" in the sense that it returns a boolean; the
caller (executor) decides what action to take (typically: cancel SL-M
and exit at MARKET). The function MUST handle:
  - tz-aware vs naive datetime entry_time (per smart_eod_check pattern)
  - string entry_time from DB ISO format
  - malformed string entry_time (fall back to False, don't crash)
  - the feature being disabled (PENNY_TIME_STOP_MIN=0)
"""
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from penny_engine_breakout import time_stop_triggered  # noqa: E402


def _set_window(minutes: int):
    from config import settings
    settings.PENNY_TIME_STOP_MIN = minutes


def test_disabled_returns_false():
    _set_window(0)
    now = datetime.now(timezone.utc)
    entry = now - timedelta(hours=2)
    assert time_stop_triggered(entry, now) is False


def test_fresh_position_not_triggered():
    _set_window(30)
    now = datetime.now(timezone.utc)
    entry = now - timedelta(minutes=5)  # only 5 min old
    assert time_stop_triggered(entry, now) is False


def test_old_position_triggered():
    _set_window(30)
    now = datetime.now(timezone.utc)
    entry = now - timedelta(minutes=45)  # 45 min old, past 30-min window
    assert time_stop_triggered(entry, now) is True


def test_naive_entry_with_aware_now():
    _set_window(30)
    now = datetime.now(timezone.utc)
    naive_entry = (now - timedelta(minutes=45)).replace(tzinfo=None)
    assert time_stop_triggered(naive_entry, now) is True


def test_string_entry_from_db():
    _set_window(30)
    now = datetime.now(timezone.utc)
    entry_str = (now - timedelta(minutes=45)).isoformat()
    assert time_stop_triggered(entry_str, now) is True


def test_malformed_string_falls_back_to_false():
    _set_window(30)
    now = datetime.now(timezone.utc)
    # Garbage string -- should NOT crash, should fall back to False
    assert time_stop_triggered("not-a-date", now) is False


def test_exact_boundary_is_triggered():
    """30 min window: position exactly 30 min old is triggered (>=)."""
    _set_window(30)
    now = datetime.now(timezone.utc)
    entry = now - timedelta(minutes=30)
    assert time_stop_triggered(entry, now) is True


def test_just_under_boundary_not_triggered():
    _set_window(30)
    now = datetime.now(timezone.utc)
    entry = now - timedelta(minutes=29, seconds=59)
    assert time_stop_triggered(entry, now) is False
