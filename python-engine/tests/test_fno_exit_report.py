"""[O24h] fno_exit_report: how far F&O paper exits ran past their own levels (read-only)."""
import sqlite3

import pytest

import fno_exit_report as report

COLS = ("id INTEGER, source TEXT, status TEXT, entry_date TEXT, exit_time TEXT, tradingsymbol TEXT, direction TEXT, "
        "qty INTEGER, delta_at_entry REAL, exit_reason TEXT, exit_underlying REAL, exit_premium REAL, "
        "stop_underlying REAL, trail_stop_underlying REAL, premium_stop REAL, pnl REAL")


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "cache.db"
    con = sqlite3.connect(path)
    con.execute(f"CREATE TABLE fno_positions ({COLS})")
    rows = [
        # a put (SHORT thesis): its index stop above; exit 26 points above it
        (1, "FNO_PAPER", "CLOSED", "2026-10-07", "2026-10-07T14:27:09", "NIFTY..22700PE", "SHORT", 65, -0.57,
         "underlying_stop", 22684.0, 174.35, 22658.0, None, 167.14, -3228.0),
        # a call (LONG): its trail under the price; exit 5 points above it (better than the level)
        (2, "FNO_PAPER", "CLOSED", "2026-10-10", "2026-10-10T13:00:00", "NIFTY..22500CE", "LONG", 130, 0.5,
         "trail_stop", 22605.0, 150.0, 22560.0, 22600.0, 90.0, 2500.0),
        # a premium stop: level 80, sold at 78
        (3, "FNO_PAPER", "CLOSED", "2026-10-11", "2026-10-11T11:00:00", "NIFTY..22400CE", "LONG", 65, 0.5,
         "premium_stop", 22400.0, 78.0, 22300.0, None, 80.0, -1500.0),
        (4, "FNO_PAPER", "CLOSED", "2026-10-11", "2026-10-11T12:00:00", "NIFTY..22400CE", "LONG", 65, 0.5,
         "time_stop", 22410.0, 99.0, 22300.0, None, 75.0, -300.0),
        (5, "FNO_PAPER", "OPEN", "2026-10-12", None, "NIFTY..22400CE", "LONG", 65, 0.5,
         None, None, None, 22300.0, None, 75.0, None),
        (6, "FNO_LIVE", "CLOSED", "2026-10-12", "2026-10-12T12:00:00", "NIFTY..22400CE", "LONG", 65, 0.5,
         "underlying_stop", 22200.0, 60.0, 22300.0, None, 75.0, -2000.0),
    ]
    con.executemany(f"INSERT INTO fno_positions VALUES ({','.join('?' * 16)})", rows)
    con.commit()
    con.close()
    return str(path)


def test_exits_are_measured_against_their_own_level(db):
    data = report.exit_slippage(db)
    by_id = {item["symbol"] + item["reason"]: item for item in data["exits"]}
    stop = by_id["NIFTY..22700PEunderlying_stop"]
    assert (stop["past"], stop["unit"], stop["rupees_estimate"]) == (26.0, "points", round(26.0 * 0.57 * 65))
    trail = by_id["NIFTY..22500CEtrail_stop"]
    assert trail["past"] == -5.0 and trail["rupees_estimate"] == 0         # sold above its trail: no cost
    premium = by_id["NIFTY..22400CEpremium_stop"]
    assert (premium["past"], premium["unit"], premium["rupees_estimate"]) == (2.0, "premium", 130)
    assert data["without_level"] == {"time_stop": 1}                       # no fixed level
    assert len(data["exits"]) == 3                                         # open and non-paper rows left out
    assert data["by_reason"]["underlying_stop"] == {"n": 1, "rupees_estimate": 963, "worse": 1,
                                                    "past_median": 26.0, "past_max": 26.0}
    text = report.render(data)
    assert "underlying_stop: 1 exits, 1 worse than the level, median +26, max +26, about Rs963 in all" in text
    assert "Without a level: time_stop 1" in text
    assert report.exit_slippage(db, "2026-10-10", "2026-10-10")["exits"][0]["reason"] == "trail_stop"


def test_the_report_opens_the_database_read_only(db):
    with pytest.raises(sqlite3.OperationalError):
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        con.execute("DELETE FROM fno_positions")
    assert len(report.exit_slippage(db)["exits"]) == 3
