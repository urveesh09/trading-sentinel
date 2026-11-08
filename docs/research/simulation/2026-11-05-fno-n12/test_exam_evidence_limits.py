from datetime import datetime, timedelta, timezone
from pathlib import Path
import runpy
import sqlite3
import sys
from types import SimpleNamespace

import pytest


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
SKILL_CHECK = Path.home() / ".agents/skills/breeze-history-download/scripts/coverage_check.py"
sys.path[:0] = [str(ROOT / "python-engine"), str(HERE.parent / "2026-11-05-fno-expiry-followup")]
from fno_exit_rules import evaluate_single_leg_exit, live_single_leg_exit_params
from regular_rules import Trend, trend_params
from config import settings


@pytest.mark.parametrize(("observed_minutes", "guard_flags_future"), [(0, True), (258, False), (356, False)])
def test_guard_checks_futures_presence_rather_than_complete_clock(monkeypatch, observed_minutes, guard_flags_future):
    if not SKILL_CHECK.is_file():
        pytest.skip("Breeze coverage checker is installed on the owner's machine")
    guard = runpy.run_path(str(SKILL_CHECK))
    fixture = sqlite3.connect(":memory:")
    fixture.executescript(
        "CREATE TABLE requests(key TEXT, status TEXT, rows INTEGER, returned_expiry TEXT);"
        "CREATE TABLE candles(kind TEXT, underlying TEXT, expiry TEXT, strike REAL, opt TEXT, "
        "interval TEXT, datetime TEXT, close REAL);"
    )
    day, weekly = "2022-04-29", "2022-05-05"
    opened = datetime.fromisoformat(day + "T09:15:00")
    clocks = [(opened + timedelta(minutes=i)).isoformat(" ") for i in range(356)]
    insert = "INSERT INTO candles VALUES (?,?,?,?,?,?,?,?)"
    fixture.executemany(insert, (("index", "NIFTY", "", 0, "", "1minute", at, 10000) for at in clocks))
    fixture.executemany(insert, (("future", "NIFTY", "2022-05-26", 0, "", "1minute", at, 10000)
                                 for at in clocks[:observed_minutes]))
    fixture.execute(insert, ("daily", "NIFTY", "", 0, "", "1day", day + " 00:00:00", 10000))
    for right in ("CE", "PE"):
        fixture.execute(insert, ("option", "NIFTY", weekly, 10000, right, "1minute", clocks[15], 100))
        fixture.execute("INSERT INTO requests VALUES (?,?,?,?)",
                        (f"option|NIFTY|{weekly}|10000|{right}|{day}|{day}", "ok", 1, '["05-MAY-2022"]'))
    fixture.execute("INSERT INTO requests VALUES (?,?,?,?)",
                    (f"future|NIFTY|2022-05-26|{day}|{day}", "ok", observed_minutes, '["26-MAY-2022"]'))
    monkeypatch.setattr(guard["L"], "ro_connect", lambda **_kwargs: fixture)
    report = guard["scan"]({"name": "synthetic", "verify": ["NIFTY", day, day]})
    assert not report["problems"]
    expected = ["session without future bars"] if guard_flags_future else []
    assert [row["what"] for row in report["unexplained_items"]] == expected


def test_frozen_a_can_require_quotes_after_native_lock_exit():
    ist = timezone(timedelta(hours=5, minutes=30))
    now = datetime(2099, 1, 7, 10, 15, tzinfo=ist)
    position = SimpleNamespace(
        direction="LONG", entry_time=(now - timedelta(minutes=20)).isoformat(),
        entry_underlying=1000., stop_underlying=950., target_underlying=1100., atr_at_entry=10.,
        entry_premium=100., best_premium=140., premium_stop=75., best_underlying=1030.,
        trail_active=False, trail_stop_underlying=None,
    )
    params = {**live_single_leg_exit_params(settings), "FNO_PROFIT_LOCK_ENABLED": True,
              "FNO_PROFIT_LOCK_KEEP_FRACTION": .50, "FNO_PROFIT_LOCK_CONFIRM_SEC": 8.}
    trend = Trend()
    for offset, future in ((605, 1000), (305, 1010), (5, 1020)):
        trend.update(now - timedelta(seconds=offset), future, "LONG")
    assert trend.update(now, 1030, "LONG") == "SUPPORT"

    def look(at, bid, chosen, breach=None):
        return evaluate_single_leg_exit(position, now_ist=at, fut_price=1030, exit_px_basis=bid,
                                        hard_flat=False, params=chosen, lock_breach_since=breach)

    a_params = trend_params(params, position, "SUPPORT")
    native_first = look(now, 116, params)
    a_first = look(now, 116, a_params)
    assert native_first.profit_lock_floor == 120
    assert a_first.profit_lock_floor == 114
    assert not native_first.exit_reason and not a_first.exit_reason
    second = now + timedelta(seconds=10)
    assert look(second, 116, params, native_first.lock_breach_since).exit_reason == "profit_lock"
    assert not look(second, 116, a_params, a_first.lock_breach_since).exit_reason
    later = now + timedelta(seconds=20)
    a_breach = look(later, 112, a_params)
    assert not a_breach.exit_reason
    assert look(later + timedelta(seconds=10), 112, a_params, a_breach.lock_breach_since).exit_reason == "profit_lock"
