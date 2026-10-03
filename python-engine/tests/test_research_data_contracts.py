"""[B1 2026-10-03] Bar data contract: interval, clock, session, zero-volume, coverage."""
from datetime import date, datetime, timedelta
import sqlite3

import pytest

from research_data_contracts import (
    ALLOW_SESSION_GAPS, BAR_NO_TRADE_MARK, BAR_TRADED, BAR_ZERO_VOLUME_WITH_RANGE,
    COMPLETE_SESSIONS_ONLY, IST, STATUS_COMPLETE, STATUS_INVALID, STATUS_PARTIAL,
    STATUS_UNAVAILABLE, DatasetUnavailable, TradingCalendar, interval_spec,
    load_daily_dataset, load_intraday_dataset, parse_bar_start, validate_daily_rows,
    validate_intraday_rows,
)

DAY = "2026-08-11"  # Tuesday


def _session(ticker="AAA", day=DAY, *, label="minute", step=1, end="15:29", sep=" ",
             volume=1000.0, skip=()):
    start = datetime.fromisoformat(f"{day}T09:15:00")
    rows = []
    minute = 0
    while True:
        stamp = start + timedelta(minutes=minute)
        if stamp.strftime("%H:%M") > end:
            break
        if stamp.strftime("%H:%M") not in skip:
            rows.append((ticker, label, stamp.strftime(f"%Y-%m-%d{sep}%H:%M:%S"),
                         10.0, 10.2, 9.9, 10.1, volume))
        minute += step
    return rows


def _status(dataset, ticker="AAA", day=DAY):
    return dataset.coverage_for(ticker, day)


def _validate(rows, **kwargs):
    params = {"interval": "minute", "start": DAY, "end": DAY, "tickers": ["AAA"]}
    params.update(kwargs)
    return validate_intraday_rows(rows, **params)


def test_complete_session_is_complete_and_bars_are_aware_ist_with_visibility_clock():
    dataset = _validate(_session())
    row = _status(dataset)
    assert row["status"] == STATUS_COMPLETE and row["rows"] == 375 and row["reasons"] == []
    bars = dataset.bars[("AAA", DAY)]
    assert bars[0].start == datetime(2026, 8, 11, 9, 15, tzinfo=IST)
    assert bars[0].available_at == datetime(2026, 8, 11, 9, 16, tzinfo=IST)
    assert all(bar.kind == BAR_TRADED and bar.executable for bar in bars)


def test_mixed_labels_select_exact_interval_and_report_others_without_merging():
    rows = _session() + _session(label="15minute", step=15) + _session(label="legacy_unknown", end="09:20")
    minute = _validate(rows)
    assert _status(minute)["status"] == STATUS_COMPLETE
    assert _status(minute)["other_labels_present"] == ["15minute", "legacy_unknown"]
    assert minute.manifest["row_counts"]["by_label"] == {"15minute": 25, "legacy_unknown": 6, "minute": 375}
    quarter = _validate(rows, interval="15minute")
    assert _status(quarter)["status"] == STATUS_COMPLETE and _status(quarter)["rows"] == 25
    assert len(quarter.bars[("AAA", DAY)]) == 25


def test_legacy_unknown_and_unregistered_intervals_are_never_usable():
    with pytest.raises(DatasetUnavailable):
        interval_spec("legacy_unknown")
    with pytest.raises(ValueError):
        interval_spec("day")


def test_only_other_labels_means_unavailable_not_substituted():
    dataset = _validate(_session(label="15minute", step=15))
    row = _status(dataset)
    assert row["status"] == STATUS_UNAVAILABLE
    assert row["reasons"] == ["no_rows_for_interval", "only_other_interval_labels"]
    assert ("AAA", DAY) not in dataset.bars


@pytest.mark.parametrize("mutate,reason", [
    (lambda r: (*r[:2], r[2][:-2] + "30", *r[3:]), "off_grid_seconds"),
    (lambda r: (*r[:2], f"{DAY} 15:30:00", *r[3:]), "outside_session"),
    (lambda r: (*r[:2], f"{DAY} 09:10:00", *r[3:]), "outside_session"),
    (lambda r: (*r[:3], 10.0, 9.0, 9.9, 10.1, 5.0), "ohlc_bounds_violated"),
    (lambda r: (*r[:3], 0.0, 10.2, 9.9, 10.1, 5.0), "non_positive_or_non_finite_price"),
    (lambda r: (*r[:3], float("nan"), 10.2, 9.9, 10.1, 5.0), "non_positive_or_non_finite_price"),
    (lambda r: (*r[:7], -1.0), "negative_or_non_finite_volume"),
])
def test_one_invalid_row_invalidates_the_whole_ticker_day(mutate, reason):
    rows = _session()
    rows[100] = mutate(rows[100])
    dataset = _validate(rows)
    row = _status(dataset)
    assert row["status"] == STATUS_INVALID and reason in row["invalid_reasons"]
    assert ("AAA", DAY) not in dataset.bars


def test_off_interval_grid_for_coarser_interval_is_invalid():
    rows = _session(label="15minute", step=15)
    rows[3] = (*rows[3][:2], f"{DAY} 10:05:00", *rows[3][3:])
    row = _status(_validate(rows, interval="15minute"))
    assert row["status"] == STATUS_INVALID and "off_interval_grid" in row["invalid_reasons"]


def test_identical_duplicate_in_another_format_is_deduplicated_but_conflict_invalidates():
    rows = _session() + [_session(sep="T")[0]]
    row = _status(_validate(rows))
    assert row["status"] == STATUS_COMPLETE and row["identical_duplicates"] == 1
    conflict = list(_session()[0])
    conflict[6] = 10.15
    row = _status(_validate(_session() + [tuple(conflict)]))
    assert row["status"] == STATUS_INVALID and "conflicting_duplicate" in row["invalid_reasons"]


def test_aware_timestamps_are_converted_to_ist_wall_clock():
    assert parse_bar_start("2026-08-11T03:45:00+00:00") == datetime(2026, 8, 11, 9, 15, tzinfo=IST)
    assert parse_bar_start("2026-08-11 09:15:00") == datetime(2026, 8, 11, 9, 15, tzinfo=IST)


def test_zero_volume_bars_are_marks_and_contradictory_ones_are_partial():
    rows = _session()
    rows[10] = (*rows[10][:3], 10.0, 10.0, 10.0, 10.0, 0.0)
    flat = _validate(rows)
    kinds = [bar.kind for bar in flat.bars[("AAA", DAY)]]
    assert kinds[10] == BAR_NO_TRADE_MARK and not flat.bars[("AAA", DAY)][10].executable
    assert _status(flat)["status"] == STATUS_COMPLETE and _status(flat)["no_trade_marks"] == 1
    rows[11] = (*rows[11][:3], 10.0, 10.1, 10.0, 10.1, 0.0)
    ranged = _validate(rows)
    assert ranged.bars[("AAA", DAY)][11].kind == BAR_ZERO_VOLUME_WITH_RANGE
    assert _status(ranged)["status"] == STATUS_PARTIAL
    assert _status(ranged)["reasons"] == ["zero_volume_with_range"]


@pytest.mark.parametrize("kwargs,reasons", [
    ({"end": "14:29"}, ["early_end"]),
    ({"skip": ("09:15", "09:16")}, ["late_start"]),
    ({"skip": ("11:00",)}, ["missing_bars"]),
])
def test_partial_sessions_are_reported_with_reasons_never_forward_filled(kwargs, reasons):
    dataset = _validate(_session(**kwargs))
    row = _status(dataset)
    assert row["status"] == STATUS_PARTIAL and row["reasons"] == reasons
    assert len(dataset.bars[("AAA", DAY)]) == row["rows"] < 375


def test_requested_trading_days_without_rows_are_unavailable_and_holidays_are_not_sessions():
    # 2026-08-14 Fri, 2026-08-15 Sat (also Independence Day), 2026-08-17 Mon
    dataset = _validate(_session(day="2026-08-14"), start="2026-08-14", end="2026-08-17",
                        tickers=["AAA", "BBB"])
    statuses = {(r["ticker"], r["trading_date"]): r["status"] for r in dataset.coverage}
    assert statuses == {
        ("AAA", "2026-08-14"): STATUS_COMPLETE, ("BBB", "2026-08-14"): STATUS_UNAVAILABLE,
        ("AAA", "2026-08-17"): STATUS_UNAVAILABLE, ("BBB", "2026-08-17"): STATUS_UNAVAILABLE,
    }
    assert dataset.usable_days(COMPLETE_SESSIONS_ONLY) == [("AAA", "2026-08-14")]


def test_rows_on_a_holiday_invalidate_that_day():
    calendar = TradingCalendar(frozenset({date(2026, 8, 11)}), date(2026, 1, 1),
                               date(2026, 12, 31), "test")
    row = _status(_validate(_session(), calendar=calendar))
    assert row["status"] == STATUS_INVALID and "non_trading_day" in row["invalid_reasons"]


def test_dates_outside_the_audited_calendar_are_unavailable_not_assumed():
    rows = _session(day="2027-01-05")
    dataset = _validate(rows, start="2027-01-04", end="2027-01-05")
    statuses = {r["trading_date"]: (r["status"], r["reasons"]) for r in dataset.coverage}
    assert statuses["2027-01-05"] == (STATUS_UNAVAILABLE, ["calendar_unavailable"])
    assert statuses["2027-01-04"] == (STATUS_UNAVAILABLE, ["calendar_unavailable"])
    assert not dataset.bars


def test_coverage_requirements_select_statuses_explicitly():
    rows = _session() + _session(ticker="BBB", end="14:29")
    dataset = _validate(rows, tickers=["AAA", "BBB"])
    assert dataset.usable_days(COMPLETE_SESSIONS_ONLY) == [("AAA", DAY)]
    assert dataset.usable_days(ALLOW_SESSION_GAPS) == [("AAA", DAY), ("BBB", DAY)]
    assert ALLOW_SESSION_GAPS.assumption == "MISSING_MINUTES_TREATED_AS_NO_TRADE_UNVERIFIED"


def test_manifest_hash_is_deterministic_order_independent_and_content_sensitive():
    rows = _session()
    a = _validate(rows).manifest["dataset_sha256"]
    b = _validate(list(reversed(rows))).manifest["dataset_sha256"]
    changed = list(rows)
    changed[5] = (*changed[5][:6], 10.15, changed[5][7])
    c = _validate(changed).manifest["dataset_sha256"]
    assert a == b != c and a.startswith("sha256:")


def _daily_rows(ticker="AAA", end=DAY, count=30, close=10.0, jump_on=None):
    rows, day = [], date.fromisoformat(end)
    while len(rows) < count:
        day -= timedelta(days=1)
        if day.weekday() >= 5 or day == date(2026, 8, 15):
            continue
        rows.append((ticker, day.isoformat(), close, close * 1.01, close * 0.99, close, 1000.0))
    rows.reverse()
    if jump_on:
        rows = [(t, d, o * 2, h * 2, l * 2, c * 2, v) if d >= jump_on else (t, d, o, h, l, c, v)
                for t, d, o, h, l, c, v in rows]
    return rows


def test_daily_is_point_in_time_and_reports_suspected_actions_without_repair():
    rows = _daily_rows(jump_on="2026-08-03")
    dataset = validate_daily_rows(rows + [("AAA", DAY, 20, 21, 19, 20, 1)], tickers=["AAA"], before=DAY)
    assert all(bar.day < date(2026, 8, 11) for bar in dataset.bars["AAA"])
    assert dataset.suspected_actions == {"AAA": ["2026-08-03"]}
    assert dataset.actions_between("AAA", date(2026, 8, 1), date(2026, 8, 10)) == ["2026-08-03"]
    before = dataset.known_before("AAA", date(2026, 8, 5), since=date(2026, 7, 30))
    assert [bar.day.isoformat() for bar in before] == ["2026-07-30", "2026-07-31", "2026-08-03", "2026-08-04"]
    assert dataset.bars["AAA"][-1].close == 20.0  # adjusted basis unknown: never rescaled


def test_invalid_daily_row_makes_that_tickers_history_unavailable():
    rows = _daily_rows()
    rows[3] = (*rows[3][:2], 10.0, 9.0, 9.5, 10.0, 1.0)
    dataset = validate_daily_rows(rows, tickers=["AAA"], before=DAY)
    assert "AAA" not in dataset.bars and dataset.invalid == {"AAA": {"ohlc_bounds_violated": 1}}


def _make_db(path, intraday, daily):
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE intraday_cache(ticker TEXT,interval TEXT,datetime TEXT,open REAL,"
                   "high REAL,low REAL,close REAL,volume REAL)")
        db.execute("CREATE TABLE ohlcv_cache(ticker TEXT,date TEXT,open REAL,high REAL,low REAL,"
                   "close REAL,volume REAL)")
        db.executemany("INSERT INTO intraday_cache VALUES(?,?,?,?,?,?,?,?)", intraday)
        db.executemany("INSERT INTO ohlcv_cache VALUES(?,?,?,?,?,?,?)", daily)
    sqlite3.connect(path).close()


def test_read_only_loaders_match_pure_validation_and_never_create_missing_db(tmp_path):
    path = tmp_path / "cache [ro] #1.db"
    _make_db(path, _session(), _daily_rows())
    loaded = load_intraday_dataset(str(path), interval="minute", start=DAY, end=DAY, tickers=["aaa"])
    assert loaded.manifest["dataset_sha256"] == _validate(_session()).manifest["dataset_sha256"]
    daily = load_daily_dataset(str(path), tickers=["AAA"], before=DAY)
    assert len(daily.bars["AAA"]) == 30
    missing = tmp_path / "absent.db"
    with pytest.raises(DatasetUnavailable):
        load_intraday_dataset(str(missing), interval="minute", start=DAY, end=DAY, tickers=["AAA"])
    with pytest.raises(DatasetUnavailable):
        load_daily_dataset(str(missing), tickers=["AAA"], before=DAY)
    assert not missing.exists()


def test_loader_closes_its_read_handle(tmp_path, monkeypatch):
    import research_data_contracts as module
    path = tmp_path / "close.db"
    _make_db(path, _session(), _daily_rows())
    opened = []
    original = sqlite3.connect

    def tracked(*args, **kwargs):
        connection = original(*args, **kwargs)
        opened.append(connection)
        return connection

    monkeypatch.setattr(module.sqlite3, "connect", tracked)
    load_intraday_dataset(str(path), interval="minute", start=DAY, end=DAY, tickers=["AAA"])
    load_daily_dataset(str(path), tickers=["AAA"], before=DAY)
    assert len(opened) == 2
    for connection in opened:
        with pytest.raises(sqlite3.ProgrammingError, match="closed"):
            connection.execute("SELECT 1")


def test_loader_rejects_cache_without_interval_provenance(tmp_path):
    path = tmp_path / "old.db"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE intraday_cache(ticker TEXT,datetime TEXT,open REAL,high REAL,"
                   "low REAL,close REAL,volume REAL)")
    sqlite3.connect(path).close()
    with pytest.raises(DatasetUnavailable, match="interval provenance"):
        load_intraday_dataset(str(path), interval="minute", start=DAY, end=DAY, tickers=["AAA"])


def test_off_calendar_daily_rows_are_kept_and_reported_not_history_fatal():
    rows = _daily_rows() + [("AAA", "2026-08-09", 10.0, 10.1, 9.9, 10.0, 500.0)]  # a Sunday
    dataset = validate_daily_rows(rows, tickers=["AAA"], before=DAY)
    assert "AAA" in dataset.bars and not dataset.invalid
    assert dataset.off_calendar == {"AAA": ["2026-08-09"]}
    assert dataset.manifest["off_calendar_dates"] == {"2026-08-09": 1}
    assert dataset.off_calendar_between("AAA", date(2026, 8, 1), date(2026, 8, 10)) == ["2026-08-09"]
