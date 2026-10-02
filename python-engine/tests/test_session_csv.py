import csv
import json

import pytest

from session_csv import append_session_rows


def _row(stamp: str, value: str) -> dict:
    return {"scanned_at": stamp, "value": value}


def _rows(path):
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def test_rotates_previous_ist_session_with_header_rows_and_manifest(tmp_path):
    current = tmp_path / "signals.csv"
    first = append_session_rows(
        str(current), ["scanned_at", "value"],
        [_row("2026-10-01T09:30:00+05:30", "first")],
    )
    assert first == {"rows": 1, "rotated": False, "session_date": "2026-10-01"}
    second = append_session_rows(
        str(current), ["scanned_at", "value"],
        [_row("2026-10-02T09:30:00+05:30", "second")],
    )
    assert second == {"rows": 1, "rotated": True, "session_date": "2026-10-02"}
    archive = tmp_path / "signals.sessions" / "2026-10-01.csv"
    assert _rows(archive) == [{"scanned_at": "2026-10-01T09:30:00+05:30", "value": "first"}]
    assert _rows(current) == [{"scanned_at": "2026-10-02T09:30:00+05:30", "value": "second"}]
    manifest = [json.loads(line) for line in (tmp_path / "signals.sessions" / "manifest.jsonl").read_text().splitlines()]
    assert manifest[0]["session_date"] == "2026-10-01"
    assert manifest[0]["archive"] == "2026-10-01.csv"
    assert len(manifest[0]["sha256"]) == 64


def test_restart_same_session_appends_once_without_second_header_or_rotation(tmp_path):
    current = tmp_path / "signals.csv"
    append_session_rows(str(current), ["scanned_at", "value"], [_row("2026-10-02T04:30:00Z", "one")])
    result = append_session_rows(str(current), ["scanned_at", "value"], [_row("2026-10-02T10:30:00+05:30", "two")])
    assert result["rotated"] is False
    assert _rows(current) == [
        {"scanned_at": "2026-10-02T04:30:00Z", "value": "one"},
        {"scanned_at": "2026-10-02T10:30:00+05:30", "value": "two"},
    ]
    assert current.read_text(encoding="utf-8").count("scanned_at,value") == 1


def test_legacy_unlabelled_current_file_is_preserved_not_assigned_to_new_session(tmp_path):
    current = tmp_path / "signals.csv"
    current.write_text("scanned_at,value\nold,value\n", encoding="utf-8")
    append_session_rows(str(current), ["scanned_at", "value"], [_row("2026-10-02T10:30:00+05:30", "new")])
    archives = list((tmp_path / "signals.sessions").glob("legacy-*.csv"))
    assert len(archives) == 1
    assert archives[0].read_text(encoding="utf-8") == "scanned_at,value\nold,value\n"
    assert _rows(current) == [{"scanned_at": "2026-10-02T10:30:00+05:30", "value": "new"}]


@pytest.mark.parametrize("stamp", ["", "not-a-date", "2026-10-02T10:30:00"])
def test_rejects_unverifiable_session_clock_without_writing(tmp_path, stamp):
    current = tmp_path / "signals.csv"
    with pytest.raises(ValueError):
        append_session_rows(str(current), ["scanned_at", "value"], [{"scanned_at": stamp, "value": "x"}])
    assert not current.exists()


# [S3 review 2026-10-02] Crash-window fault injection.  Each test fails on the
# pre-correction rotation and passes once recovery is idempotent.
COLUMNS = ["scanned_at", "value"]
DAY1, DAY2, DAY3 = "2026-10-01T09:30:00+05:30", "2026-10-02T09:30:00+05:30", "2026-10-05T09:30:00+05:30"


def _manifest(tmp_path):
    path = tmp_path / "signals.sessions" / "manifest.jsonl"
    if not path.exists():
        return []
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return records


def test_crash_after_archive_move_before_manifest_is_recovered(tmp_path, monkeypatch):
    import session_csv
    current = tmp_path / "signals.csv"
    append_session_rows(str(current), COLUMNS, [_row(DAY1, "first")])
    real_append = session_csv._append_manifest

    def crash(*_args, **_kwargs):
        raise OSError("injected crash before manifest append")

    monkeypatch.setattr(session_csv, "_append_manifest", crash)
    with pytest.raises(OSError):
        append_session_rows(str(current), COLUMNS, [_row(DAY2, "second")])
    monkeypatch.setattr(session_csv, "_append_manifest", real_append)
    append_session_rows(str(current), COLUMNS, [_row(DAY2, "second")])
    records = _manifest(tmp_path)
    assert [record["archive"] for record in records] == ["2026-10-01.csv"]
    assert _rows(tmp_path / "signals.sessions" / "2026-10-01.csv") == [{"scanned_at": DAY1, "value": "first"}]
    assert _rows(current) == [{"scanned_at": DAY2, "value": "second"}]


def test_crash_after_new_header_before_state_never_mislabels_or_blocks(tmp_path, monkeypatch):
    import session_csv
    current = tmp_path / "signals.csv"
    append_session_rows(str(current), COLUMNS, [_row(DAY1, "first")])
    # Reproduce the pre-correction on-disk state: day-1 archived, a fresh
    # header-only current file, and session state still naming day 1.
    archive_dir = tmp_path / "signals.sessions"
    archive_dir.mkdir(exist_ok=True)
    (archive_dir / "2026-10-01.csv").write_bytes(current.read_bytes())
    session_csv._append_manifest(archive_dir / "manifest.jsonl", session_date="2026-10-01",
                                 archive=archive_dir / "2026-10-01.csv")
    session_csv._write_header(current, COLUMNS)
    append_session_rows(str(current), COLUMNS, [_row(DAY2, "second")])
    assert _rows(archive_dir / "2026-10-01.csv") == [{"scanned_at": DAY1, "value": "first"}]
    assert _rows(current) == [{"scanned_at": DAY2, "value": "second"}]
    assert [record["archive"] for record in _manifest(tmp_path)] == ["2026-10-01.csv"]


def test_state_is_recorded_before_the_new_header(tmp_path, monkeypatch):
    import session_csv
    current = tmp_path / "signals.csv"
    append_session_rows(str(current), COLUMNS, [_row(DAY1, "first")])

    def crash(*_args, **_kwargs):
        raise OSError("injected crash creating the new header")

    real_header = session_csv._write_header
    monkeypatch.setattr(session_csv, "_write_header", crash)
    with pytest.raises(OSError):
        append_session_rows(str(current), COLUMNS, [_row(DAY2, "second")])
    monkeypatch.setattr(session_csv, "_write_header", real_header)
    assert json.loads((tmp_path / "signals.csv.session.json").read_text())["session_date"] == "2026-10-02"
    append_session_rows(str(current), COLUMNS, [_row(DAY2, "second")])
    append_session_rows(str(current), COLUMNS, [_row(DAY3, "third")])
    assert [record["archive"] for record in _manifest(tmp_path)] == ["2026-10-01.csv", "2026-10-02.csv"]


def test_torn_manifest_line_is_isolated_and_later_records_stay_parseable(tmp_path):
    current = tmp_path / "signals.csv"
    append_session_rows(str(current), COLUMNS, [_row(DAY1, "first")])
    append_session_rows(str(current), COLUMNS, [_row(DAY2, "second")])
    manifest = tmp_path / "signals.sessions" / "manifest.jsonl"
    with manifest.open("ab") as handle:
        handle.write(b'{"archive":"torn')  # crash mid-append, no newline
    append_session_rows(str(current), COLUMNS, [_row(DAY3, "third")])
    assert [record["archive"] for record in _manifest(tmp_path)] == ["2026-10-01.csv", "2026-10-02.csv"]


# [S3 R4 2026-10-02] Capacity handling.
def test_low_free_space_refuses_and_counts_rows_without_touching_files(tmp_path, monkeypatch):
    import session_csv
    from collections import namedtuple
    current = tmp_path / "signals.csv"
    append_session_rows(str(current), COLUMNS, [_row(DAY1, "first")])
    before = current.read_bytes()
    usage = namedtuple("usage", "total used free")
    monkeypatch.setattr(session_csv.shutil, "disk_usage", lambda _p: usage(10, 10, 10))
    result = append_session_rows(str(current), COLUMNS, [_row(DAY1, "x"), _row(DAY1, "y")])
    assert result["dropped"] == 2 and result["reason"] == "insufficient_free_space"
    assert current.read_bytes() == before
    assert session_csv.dropped_row_counts()[str(current)] >= 2


def test_over_quota_archive_is_flagged_and_never_pruned(tmp_path, monkeypatch):
    from config import settings
    monkeypatch.setattr(settings, "SESSION_CSV_ARCHIVE_MAX_BYTES", 1)
    current = tmp_path / "signals.csv"
    append_session_rows(str(current), COLUMNS, [_row(DAY1, "first")])
    result = append_session_rows(str(current), COLUMNS, [_row(DAY2, "second")])
    assert result["rotated"] is True and result["archive_over_quota"] is True
    assert _rows(tmp_path / "signals.sessions" / "2026-10-01.csv") == [{"scanned_at": DAY1, "value": "first"}]


def test_torn_final_row_is_isolated_before_the_next_append(tmp_path):
    current = tmp_path / "signals.csv"
    append_session_rows(str(current), COLUMNS, [_row(DAY1, "first")])
    with current.open("ab") as handle:
        handle.write(b"2026-10-01T09:31:00+05:30,tor")  # crash mid-row, no newline
    append_session_rows(str(current), COLUMNS, [_row(DAY1, "second")])
    lines = current.read_text(encoding="utf-8").splitlines()
    assert lines[-2] == "2026-10-01T09:31:00+05:30,tor"
    assert lines[-1] == "2026-10-01T09:30:00+05:30,second"
