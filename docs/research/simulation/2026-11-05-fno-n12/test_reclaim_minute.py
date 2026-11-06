from datetime import date, datetime
import json
from pathlib import Path
import sqlite3
import sys

import pytest

HERE = Path(__file__).resolve().parent
YEAR_GENOME = HERE.parents[2] / "research/fno/2026-10-29-year-genome"
sys.path.insert(0, str(YEAR_GENOME))
from yeardata import YearData, bid_ask
import options_math
from fno_chain import RISK_FREE_RATE, years_to_expiry
from fno_exit_rules import IST
from prior_range_reclaim import clock
from reclaim_minute import replay, replay_stresses


PREVIOUS = "2021-07-01"
DAY = "2021-07-02"
FRONT = "2021-07-29"
WEEKLY = "2021-07-08"
LOT = 50


def archive(root, *, stale_entry=False, stale_exit=False, absent_future=False, stale_future=False):
    meta = {"underlying": "NIFTY", "lot_size": LOT, "sessions": [DAY],
            "weekly_expiry_calendar": [WEEKLY], "future_expiries": [FRONT], "logged_regimes": {}}
    (root / "manifest.json").write_text(json.dumps(meta), encoding="utf-8")
    with sqlite3.connect(root / "breeze.sqlite") as db:
        db.execute(
            "CREATE TABLE candles(kind TEXT,expiry TEXT,strike REAL,opt TEXT,datetime TEXT,"
            "open REAL,high REAL,low REAL,close REAL,volume REAL,oi REAL)"
        )
        rows = [("future", FRONT, 0, "", f"{PREVIOUS} {clock(minute)}", 25080, 25180, 24980, 25080, 100, 100)
                for minute in range(555, 930)]
        for minute in range(555, 603):
            if minute == 601 and absent_future:
                continue
            ohlc = (25020, 25024, 25015, 25020)
            if 590 <= minute < 595:
                ohlc = (24965, 25005, 24955, 24965)
            if 595 <= minute < 600:
                ohlc = (24991, 25001, 24966, 24991)
            if minute == 600:
                ohlc = (24990, 25000, 24985, 24990)
            if minute >= 601:
                ohlc = (25080, 25085, 25075, 25080)
            volume = 0 if minute == 601 and stale_future else 100
            rows.append(("future", FRONT, 0, "", f"{DAY} {clock(minute)}", *ohlc, volume, 100))
        expiry = date.fromisoformat(WEEKLY)
        for minute in (599, 600, 601, 602):
            at = IST.localize(datetime.fromisoformat(f"{DAY} {clock(minute)}").replace(second=59))
            for strike in range(24750, 25251, 50):
                for right in ("CE", "PE"):
                    px = round(options_math.black76_price(24990, strike, years_to_expiry(expiry, at),
                                                          .15, RISK_FREE_RATE, right == "CE"), 2)
                    if minute >= 601:
                        px += 30
                    volume = 0 if (minute == 600 and stale_entry) or (minute == 601 and stale_exit) else 20_000
                    rows.append(("option", WEEKLY, strike, right, f"{DAY} {clock(minute)}",
                                 px, px, px, px, volume, 50_000))
        db.executemany("INSERT INTO candles VALUES (?,?,?,?,?,?,?,?,?,?,?)", rows)
    return YearData(root)


def test_real_minute_adapter_uses_first_close_and_dated_option(tmp_path):
    data = archive(tmp_path)
    result = replay_stresses(data, (PREVIOUS, DAY))
    native = result["standard"]["days"][DAY]
    doubled = result["doubled"]["days"][DAY]
    assert result["standard"]["complete"] and result["doubled"]["complete"]
    assert (native["entry_time"], native["exit_time"]) == (DAY + "T10:00:59+05:30", DAY + "T10:01:59+05:30")
    assert native["entry_qty"] == LOT and native["exit_reason"] == "midpoint_target"
    observations, _ = data.observations(DAY)
    entry, exit_ = [obs for obs in observations if obs.at.minute in (0, 1) and obs.at.hour == 10]
    option, = [q for q in entry.options.values() if q.contract.tradingsymbol == native["tradingsymbol"]]
    assert native["entry_premium"] == bid_ask(option.ltp)[1]
    assert native["exit_premium"] == bid_ask(exit_.options[option.contract.token].ltp)[0]
    assert native["net_pnl"] - doubled["net_pnl"] == pytest.approx(205)
    assert result["standard"]["net"] == pytest.approx(native["net_pnl"])


def test_carried_entry_quote_cannot_fill_first_minute(tmp_path):
    report = replay(archive(tmp_path, stale_entry=True), (PREVIOUS, DAY))
    assert report["days"][DAY]["reason"] == "selected_contract_no_trade_this_minute"
    assert report["complete"] and report["net"] == 0


@pytest.mark.parametrize(("flag", "reason"), [
    ("stale_exit", "held_bid_unavailable"),
    ("absent_future", "held_future_minute_unavailable"),
    ("stale_future", "held_future_minute_unavailable"),
])
def test_later_valid_trade_cannot_settle_through_gap(tmp_path, flag, reason):
    report = replay(archive(tmp_path, **{flag: True}), (PREVIOUS, DAY))
    assert report["days"][DAY]["reason"] == reason
    assert report["days"][DAY]["gap_at"] == DAY + "T10:01:59+05:30"
    assert not report["complete"] and report["net"] is None


def test_declared_scope_cannot_silently_drop_day(tmp_path):
    with pytest.raises(ValueError, match="declared calendar"):
        replay(archive(tmp_path), (PREVIOUS, DAY, "2021-07-05"))



def test_prior_session_more_than_four_days_is_explicitly_excluded(tmp_path):
    report = replay(archive(tmp_path), ("2021-06-25", DAY))
    assert report["days"][DAY]["status"] == "prior_session_gap_excluded"
    assert report["complete"] and report["net"] == 0
