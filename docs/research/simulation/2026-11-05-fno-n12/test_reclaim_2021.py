from datetime import date, datetime, timedelta
import sqlite3
import subprocess
import sys

import pytest

import reclaim_2021 as exam
from test_reclaim_minute import DAY, FRONT, PREVIOUS, archive


def test_calendar_and_immutable_input_binding(tmp_path):
    sessions, weekly = exam.calendar()
    assert len(sessions) == 104
    assert (sessions[0], sessions[-1]) == exam.WINDOW
    assert "2021-11-04" not in sessions and "2021-11-03" in weekly
    assert "2021-08-18" in weekly and weekly[-1] == "2022-01-06"
    dataset = tmp_path / "dataset"
    dataset.mkdir()
    exam.write_new(dataset / "manifest.json", {"underlying": "NIFTY", "lot_size": 50, "sessions": sessions,
                                               "weekly_expiry_calendar": weekly, "option_expiries": weekly,
                                               "future_expiries": exam.FUTURES,
                                               "logged_regimes": {}})
    (dataset / "breeze.sqlite").touch()
    exam.write_new(tmp_path / "daily.json", {})
    binding = {"window": list(exam.WINDOW), "prior_session": exam.SEED, "provenance": "synthetic",
               "files": {name: exam.digest(tmp_path / name) for name in exam.INPUT_FILES}}
    assert exam.validate_inputs(tmp_path, binding) == sessions
    (dataset / "breeze.sqlite-wal").touch()
    with pytest.raises(ValueError, match="standalone SQLite"):
        exam.validate_inputs(tmp_path, binding)
    (tmp_path / "daily.json").write_text("changed", encoding="utf-8")
    with pytest.raises(ValueError, match="Changed 2021 snapshot input"):
        exam.validate_inputs(tmp_path, binding)


def test_gate_requires_support_and_withholds_incomplete_results():
    native = {stress: {name: {"trades": []} for name in ("N11", "N11T")} for stress in exam.COSTS}
    days = {f"2021-08-{day:02d}": {"status": "closed", "net_pnl": 300, "exit_time": f"2021-08-{day:02d}T11:00:00"}
            for day in range(2, 17)}
    sleeve = {stress: {"complete": True, "days": days.copy()} for stress in exam.COSTS}
    assert exam.score(native, sleeve)["verdict"] == "pass"
    sleeve["standard"]["days"].pop("2021-08-02")
    assert exam.score(native, sleeve)["verdict"] == "insufficient"
    sleeve["doubled"]["complete"] = False
    assert exam.score(native, sleeve) == {"verdict": "incomplete"}


def test_evaluation_claim_survives_an_interruption(tmp_path, monkeypatch):
    binding = tmp_path / "inputs.json"
    exam.write_new(binding, {"source_revision": "dev", "settings_sha256": "effective"})
    monkeypatch.setattr(exam, "BINDING", binding)
    monkeypatch.setattr(exam, "WORK", tmp_path)
    monkeypatch.setattr(exam, "committed", exam.read)
    monkeypatch.setattr(exam, "validate_sources", lambda revision: None)
    monkeypatch.setattr(exam, "settings_fingerprint", lambda: "effective")
    monkeypatch.setattr(exam, "validate_inputs", lambda work, binding: (DAY,))
    monkeypatch.setattr(sys, "argv", ["reclaim_2021.py"])

    def interrupted(*_):
        raise RuntimeError("synthetic interruption")

    monkeypatch.setattr(exam, "controls", interrupted)
    with pytest.raises(RuntimeError, match="synthetic interruption"):
        exam.main()
    assert exam.read(tmp_path / "evaluation/started.json")["source_revision"] == "dev"
    with pytest.raises(FileExistsError):
        exam.main()


def test_native_controls_and_reclaim_share_the_actual_archive_reader(tmp_path):
    dataset = tmp_path / "dataset"
    dataset.mkdir()
    data = archive(dataset)
    manifest = dataset / "manifest.json"
    manifest.unlink()
    exam.write_new(manifest, {**data.manifest, "option_expiries": data.manifest["weekly_expiry_calendar"]})
    with sqlite3.connect(data.db) as db:
        start = datetime.fromisoformat(f"{DAY}T09:15:00")
        rows = [("index", "", 0, "", (start + timedelta(minutes=minute)).isoformat(" "),
                 25020, 25024, 25015, 25020, 0, 0) for minute in range(375)]
        rows.extend(("future", FRONT, 0, "", (start + timedelta(minutes=minute)).isoformat(" "),
                     25080, 25085, 25075, 25080, 100, 100) for minute in range(48, 375))
        rows.extend(("future", FRONT, 0, "", f"{day} 09:15:00", 25080, 25085, 25075, 25080, 100, 100)
                    for day in ("2021-06-24", "2021-06-25", "2021-06-28", "2021-06-29", "2021-06-30"))
        db.executemany("INSERT INTO candles VALUES (?,?,?,?,?,?,?,?,?,?,?)", rows)
    last = date.fromisoformat(DAY)
    days = [(last - timedelta(days=offset)).isoformat() for offset in range(260, -1, -1)]
    exam.write_new(tmp_path / "daily.json", {"rows": [[day, 23000 + i, 23100 + i, 22900 + i, 23000 + i]
                                                    for i, day in enumerate(days)]})
    script = """
from pathlib import Path
import sys
from reclaim_2021 import controls, score, settings_fingerprint
work = Path(sys.argv[1])
day, previous = sys.argv[2:]
assert len(settings_fingerprint()) == 64
data, history, native = controls(work, work / 'cache', (day,), previous)
from reclaim_minute import replay_stresses
assert history['notes']['start_equity'] == 250000
for arms in native.values():
    for result in arms.values():
        assert result['notes']['grid_phase_default'] == 1
        assert result['notes']['start_equity'] == 250000
sleeve = replay_stresses(data, (previous, day))
assert sleeve['standard']['days'][day]['entry_qty'] == 50
assert sleeve['standard']['days'][day]['exit_reason'] == 'midpoint_target'
assert score(native, sleeve)['verdict'] == 'insufficient'
import sqlite3
from reclaim_2021 import qualify_data
with sqlite3.connect(data.db) as db:
    db.execute("DELETE FROM candles WHERE kind='index' AND datetime=?", (f'{day} 10:00:00',))
try:
    qualify_data(data, work / 'daily.json', (day,), previous)
except ValueError as err:
    assert 'Incomplete minute clocks: index' in str(err)
else:
    raise AssertionError('Missing clock was accepted')
"""
    run = subprocess.run([sys.executable, "-c", script, str(tmp_path), DAY, PREVIOUS], cwd=exam.HERE,
                         capture_output=True, text=True, timeout=120)
    assert run.returncode == 0, run.stdout + run.stderr
