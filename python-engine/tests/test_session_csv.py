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
