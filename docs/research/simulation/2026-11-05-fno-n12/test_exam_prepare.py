from contextlib import closing
from datetime import datetime, timedelta
import sqlite3

import pytest

import exam_prepare as prep
import exam_run as exam


FIRST, EXPIRY = "2022-01-03", "2022-01-06"
FRONT, WARM_DAY = "2022-01-27", "2021-12-30"
STAMP = "2026-11-06T10:00:00+05:30"
FREEZE = exam.read(exam.FREEZE)
WINDOW = FREEZE["primary_window"]
CHECKS = {target: {"at": STAMP} for target in (exam.Q1, exam.Q2)}
CALENDAR = {"sessions": [FIRST, EXPIRY], "weekly_expiry_calendar": [EXPIRY],
            "front_future_expiries": [FRONT]}


@pytest.fixture
def archive(tmp_path):
    file = tmp_path / "source.sqlite"
    with closing(sqlite3.connect(file)) as db, db:
        db.execute("CREATE TABLE requests (key TEXT PRIMARY KEY,status TEXT,rows INTEGER,returned_expiry TEXT,at TEXT)")
        db.execute("CREATE TABLE candles (kind TEXT,underlying TEXT,expiry TEXT,strike REAL,opt TEXT,interval TEXT,"
                   "datetime TEXT,open REAL,high REAL,low REAL,close REAL,volume REAL,oi REAL)")
        keys = [f"index|NIFTY|{FIRST}|{EXPIRY}", f"future|NIFTY|{FRONT}|{WARM_DAY}|{EXPIRY}",
                f"daily|NIFTY|{FIRST}|{EXPIRY}", f"daily|BANKNIFTY|{FIRST}|{EXPIRY}",
                f"option|NIFTY|{EXPIRY}|17000|CE|{FIRST}|{EXPIRY}",
                f"option|NIFTY|{EXPIRY}|17000|PE|{FIRST}|{EXPIRY}",
                f"option|NIFTY|2022-01-13|17000|CE|{FIRST}|{EXPIRY}"]
        db.executemany("INSERT INTO requests VALUES (?,?,?,?,?)", ((key, "ok", 1, "[]", STAMP) for key in keys))

        def insert(kind, name, expiry, strike, opt, when):
            rows = ((kind, name, expiry, strike, opt, "1day" if kind == "daily" else "1minute",
                     clock, 100, 101, 99, 100, 10, 5000) for clock in when)
            db.executemany("INSERT INTO candles VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)

        for day in (FIRST, EXPIRY):
            first_tick = datetime.fromisoformat(day + "T09:15:00")
            times = [(first_tick + timedelta(minutes=i)).isoformat(" ") for i in range(356)]
            insert("index", "NIFTY", "", 0, "", times)
            insert("future", "NIFTY", FRONT, 0, "", times)
            for name in ("NIFTY", "BANKNIFTY"):
                insert("daily", name, "", 0, "", [day + " 00:00:00"])
            for opt in ("CE", "PE"):
                insert("option", "NIFTY", EXPIRY, 17000, opt, [day + " 10:00:00"])
        insert("future", "NIFTY", FRONT, 0, "", [WARM_DAY + " 10:00:00", "2022-01-04 10:00:00"])
        insert("option", "NIFTY", "2022-01-13", 17000, "CE", [FIRST + " 10:00:00"])
        insert("option", "NIFTY", EXPIRY, 17100, "CE", [FIRST + " 10:00:00"])
    return file


def get_capture(db, checks=CHECKS):
    return prep.prepare_metadata(db, FREEZE, CALENDAR, WINDOW, checks, None)


def test_metadata_capture_and_snapshot_scope(archive, tmp_path, monkeypatch):
    monkeypatch.setattr(prep, "SOURCE", archive)
    with closing(prep.source_open()) as db:
        db.set_authorizer(prep.metadata_only)
        record = get_capture(db)
        assert record["coverage"][FIRST]["option_rights"] == ["CE", "PE"]
        assert record["coverage"][FIRST]["front_prior_sessions"] == 1
        assert not record["coverage"][EXPIRY]["option_rights"]
        assert len(record["requests"]) == 6
        assert len(record["coverage_sha256"]) == 64
        with pytest.raises(sqlite3.DatabaseError, match="prohibited"):
            db.execute("SELECT close FROM candles").fetchone()
        db.set_authorizer(None)
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            db.execute("DELETE FROM requests")
        work = tmp_path / "work"
        work.mkdir()
        warm = {"rows": {name: [[WARM_DAY, 99, 100, 98, 99]] for name in ("NIFTY", "BANKNIFTY")}}
        result = prep.export_data(db, work, record, CALENDAR, warm)
    assert result["coverage_sha256"] == record["coverage_sha256"]
    exam.check_snapshot(work, record, result)
    with closing(sqlite3.connect(work / "dataset/breeze.sqlite")) as db:
        assert db.execute("SELECT DISTINCT expiry,strike,substr(datetime,1,10) FROM candles WHERE kind='option'").fetchall() == [
            (EXPIRY, 17000., FIRST)]
        assert db.execute("SELECT DISTINCT substr(datetime,1,10) FROM candles WHERE kind='future' ORDER BY 1").fetchall() == [
            (WARM_DAY,), (FIRST,), (EXPIRY,)]
    assert exam.read(work / "daily.json")["bank_rows"][0][0] == WARM_DAY


def test_snapshot_rejects_changed_ledger_and_minute_metadata_before_prices(archive, tmp_path):
    with closing(sqlite3.connect(archive)) as db, db:
        db.set_authorizer(prep.metadata_only)
        record = get_capture(db)
        db.execute("UPDATE requests SET rows=2 WHERE key LIKE 'index|%'")
        with pytest.raises(ValueError, match="ledger changed"):
            prep.export_data(db, tmp_path, record, CALENDAR, {})
        db.execute("UPDATE requests SET rows=1 WHERE key LIKE 'index|%'")
        db.execute("UPDATE candles SET volume=11 WHERE kind='option' AND opt='CE' AND datetime LIKE ?", (FIRST + "%",))
        with pytest.raises(ValueError, match="minute or daily coverage changed"):
            prep.export_data(db, tmp_path, record, CALENDAR, {})
    assert not (tmp_path / "dataset").exists()


def test_capture_rejects_missing_quotes_and_stale_guard_evidence(archive):
    with closing(sqlite3.connect(archive)) as db, db:
        checks = {target: {"at": "2026-11-06T09:00:00+05:30"} for target in CHECKS}
        with pytest.raises(ValueError, match="predates a scoped request"):
            get_capture(db, checks)
        db.execute("UPDATE candles SET volume=0 WHERE kind='option' AND opt='PE'")
        with pytest.raises(ValueError, match="Missing dated option rights"):
            get_capture(db)


def test_guard_evidence_must_be_full_and_completed(tmp_path):
    path = tmp_path / f"check-{exam.Q1}-latest.json"
    payload = {"target": exam.Q1, "at": STAMP, "clean": True, "incomplete": False, "structural": None}
    exam.write_new(path, payload)
    with pytest.raises(ValueError, match="completed clean full"):
        prep.guarded_checks(tmp_path, [exam.Q1])
    path.write_text('{"target":"nifty-2022-q1-fno","at":"2026-11-06T10:00:00+05:30","clean":true,'
                    '"incomplete":false,"structural":{"sqlite_quick_check":"ok","new_issues":{}}}')
    assert prep.guarded_checks(tmp_path, [exam.Q1]) == {
        exam.Q1: {"at": STAMP, "sha256": exam.digest(path), "sqlite_quick_check": "ok", "new_issues": {}}
    }


def test_snapshot_cannot_read_before_committed_capture(monkeypatch):
    def refuse(path):
        assert path == exam.REQUESTS
        raise ValueError("Uncommitted capture")

    monkeypatch.setattr(exam, "committed", refuse)
    monkeypatch.setattr(prep, "source_open", lambda: pytest.fail("Source opened without committed capture"))
    with pytest.raises(ValueError, match="Uncommitted capture"):
        prep.snapshot(FREEZE, CALENDAR)
