from collections import Counter
from datetime import datetime, timedelta
from decimal import Decimal
import json
import os
import sqlite3
import subprocess
import sys
from types import SimpleNamespace

import pytest

import exam_run as e


FREEZE = e.read(e.FREEZE)


def metadata(first="2022-01-03", partial=False):
    week, future = ("2022-04-07", "2022-04-28") if partial else ("2022-01-06", "2022-01-27")
    window = FREEZE["partial_window" if partial else "primary_window"]
    keys = [f"index|NIFTY|{first}|{first}", f"future|NIFTY|{future}|{first}|{first}",
            f"daily|NIFTY|{first}|{first}", f"daily|BANKNIFTY|{first}|{first}"]
    keys.extend(f"option|NIFTY|{week}|17000|{right}|{first}|{first}" for right in ("CE", "PE"))
    requests = {"window": window, "sessions": [first], "target_checks": {e.Q2: "CHECK CLEAN"},
                "requests": [{"key": key, "status": "ok", "rows": 356} for key in sorted(keys)]}
    if not partial:
        requests["target_checks"][e.Q1] = "CHECK CLEAN"
    snapshot = {"window": window, "request_manifest_sha256": "frozen",
                "files": dict.fromkeys(e.INPUT_FILES, "synthetic"),
                "coverage": {first: {"front_future": future, "weekly_option": week,
                                     "index_missing_minutes": 0, "front_missing_minutes": 0,
                                     "option_rights": ["CE", "PE"]}}}
    return requests, snapshot


def test_metadata_requires_scope_and_prior_fallback():
    requests, snapshot = metadata()
    assert e.validate_metadata(FREEZE, requests, snapshot, "frozen") == requests["sessions"]
    with pytest.raises(ValueError, match="request manifest"):
        e.validate_metadata(FREEZE, requests, snapshot, "different")
    requests, snapshot = metadata("2022-04-04", partial=True)
    with pytest.raises(ValueError, match="unavailability"):
        e.validate_metadata(FREEZE, requests, snapshot, "frozen")
    requests["q1_unavailability"] = "synthetic prior declaration"
    assert e.validate_metadata(FREEZE, requests, snapshot, "frozen") == requests["sessions"]
    requests["target_checks"][e.Q2] = "CHECK INCOMPLETE"
    with pytest.raises(ValueError, match="clean coverage"):
        e.validate_metadata(FREEZE, requests, snapshot, "frozen")


def test_metadata_requires_expected_minute_and_request_coverage():
    requests, snapshot = metadata()
    row = snapshot["coverage"][requests["sessions"][0]]
    row["front_missing_minutes"] = 1
    with pytest.raises(ValueError, match="Incomplete index"):
        e.validate_metadata(FREEZE, requests, snapshot, "frozen")
    row["front_missing_minutes"] = 0
    row["option_rights"] = ["CE"]
    with pytest.raises(ValueError, match="Missing dated option rights"):
        e.validate_metadata(FREEZE, requests, snapshot, "frozen")
    row["option_rights"] = ["CE", "PE"]
    requests["requests"][-1]["status"] = "empty"
    with pytest.raises(ValueError, match="completed request provenance"):
        e.validate_metadata(FREEZE, requests, snapshot, "frozen")


def test_snapshot_hash_and_one_shot_marker(tmp_path):
    requests, snapshot = metadata()
    dataset = tmp_path / "dataset"
    dataset.mkdir()
    (dataset / "breeze.sqlite").write_bytes(b"synthetic database")
    (tmp_path / "daily.json").write_text("{}")
    coverage = snapshot["coverage"][requests["sessions"][0]]
    manifest = {"underlying": "NIFTY", "lot_size": 65, "logged_regimes": {}, "window": requests["window"],
                "sessions": requests["sessions"], "option_expiries": [coverage["weekly_option"]],
                "weekly_expiry_calendar": [coverage["weekly_option"]],
                "future_expiries": [coverage["front_future"]],
                "files_sha256": {"breeze.sqlite": e.digest(dataset / "breeze.sqlite")}}
    e.write_new(dataset / "manifest.json", manifest)
    snapshot["files"] = {name: e.digest(tmp_path / name) for name in e.INPUT_FILES}
    e.check_snapshot(tmp_path, requests, snapshot)
    (tmp_path / "daily.json").write_text("changed")
    with pytest.raises(ValueError, match="Changed snapshot file"):
        e.check_snapshot(tmp_path, requests, snapshot)
    e.claim_once(tmp_path, requests["window"], "original", "snapshot", "commit")
    with pytest.raises(FileExistsError):
        e.claim_once(tmp_path, FREEZE["partial_window"], "different", "snapshot", "commit")
    assert e.read(tmp_path / "started.json")["request_sha256"] == "original"


def test_stress_arms_and_2022_accounting(tmp_path):
    call_order = []

    def run(name, model):
        call_order.append((name, model["cost"]))
        return {"trades": [], "tolerance_entries": [("X", "2022-01-03T10:00:00")] if name == "N11T" else []}

    models = {name: {"cost": FREEZE["standard_extra_cost"]} for name in ("N11", "N11T", "N012-A")}
    results = e.run_arms(tmp_path, FREEZE, models, run, lambda _: call_order.append("bound"), {"cost": None})
    assert call_order == [("paper_history", None), "bound",
                          ("N11", [200, 5]), ("N11T", [200, 5]), ("N012-A", [200, 5]),
                          ("N11T", [400, 10]), ("N012-A", [400, 10])]
    assert e.read(tmp_path / "N11T-doubled.json")["tolerance_entries"]
    prior = {name: {"net": 10, "notes": {"n11t_second_lots": 8}} for name in ("N11", "N11T", "TREND_ONLY")}
    summaries = {name: {"net": Decimal("1.2345")} for name in models}
    thresholds = {"minimum_option_sessions": 200, "minimum_tolerance_trades": 10}
    joined = e.combined_2022(results, summaries, prior, 114, range(86), thresholds)
    assert joined["two_independent_windows_net"]["N012-A"] == Decimal("11.2345")
    assert joined["clears_200_using_reported_dates"]
    assert joined["combined_n11t_tolerance_entries"] == 9
    assert not joined["clears_10_tolerance_entries"]


def test_only_committed_initial_tolerance_is_counted():
    class FakeReplay:
        def _entry(self, book, obs, frame, day, now):
            if obs != "ordinary":
                self.notes["n11t_second_lots"] += 1
            if obs != "lost":
                book.open[book.next_id] = SimpleNamespace(lots=2, tradingsymbol="X", entry_time=now)
                book.next_id += 1

    class AuditedReplay(e.ToleranceAudit, FakeReplay):
        notes = Counter()
        tolerance_entries = []

    engine, book = AuditedReplay(), SimpleNamespace(next_id=1, open={})
    engine._entry(book, "ordinary", None, None, "ordinary")
    engine._entry(book, "tolerance", None, None, "tolerance")
    assert engine.tolerance_entries == [("X", "tolerance")]
    with pytest.raises(ValueError, match="committed initial two-lot"):
        engine._entry(book, "lost", None, None, "lost")


def test_real_adapter_wires_synthetic_snapshot_in_fresh_process(tmp_path):
    requests, snapshot = metadata()
    dataset = tmp_path / "dataset"
    dataset.mkdir()
    day = requests["sessions"][0]
    coverage = snapshot["coverage"][day]
    e.write_new(dataset / "manifest.json", {"underlying": "NIFTY", "lot_size": 65,
                                           "logged_regimes": {}, "sessions": [day],
                                           "option_expiries": [coverage["weekly_option"]],
                                           "weekly_expiry_calendar": [coverage["weekly_option"]],
                                           "future_expiries": [coverage["front_future"]]})
    with sqlite3.connect(dataset / "breeze.sqlite") as conn:
        conn.execute("CREATE TABLE candles (kind TEXT, expiry TEXT, strike REAL, opt TEXT, datetime TEXT, "
                     "open REAL, high REAL, low REAL, close REAL, volume REAL, oi REAL)")
        start = datetime.fromisoformat(f"{day}T09:15:00")
        conn.executemany("INSERT INTO candles VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                         (("future", coverage["front_future"], 0, "", (start + timedelta(minutes=i)).isoformat(" "),
                           17000, 17002, 16998, 17000, 10000, 50000) for i in range(356)))
    warm = e.read(e.PRIOR / "_local/nifty-2022/pre-2022-warmup.json")["rows"]["NIFTY"]
    e.write_new(tmp_path / "daily.json", {"rows": [*warm, [day, 17000, 17002, 16998, 17000]]})
    e.write_new(tmp_path / "requests-fixture.json", requests)
    code = """
from datetime import datetime, timedelta
from pathlib import Path
import sys
import exam_run as e
import n012_ab as arms
work = Path(sys.argv[1])
freeze = arms.validate_freeze()
run, bind, diag = e.evaluator(arms, work, e.read(work / 'requests-fixture.json'), freeze)
assert arms.r.f.L.paper_stream() == ((), ())
raw = run('paper_history', diag)
assert raw['notes']['grid_phase_default'] == 1
closed_at = datetime.fromisoformat('2022-01-03T10:00:00+05:30')
bind({'trades': [{'status': 'CLOSED', 'entry_time': '2022-01-03T09:45:00+05:30',
                  'exit_time': closed_at.isoformat(), 'net_pnl': 100}]})
assert arms.r.f.L.paper_before(closed_at) == ()
assert arms.r.f.L.paper_before(closed_at + timedelta(seconds=1)) == (100,)
outputs = e.run_arms(work, freeze, arms.frozen_models(), run, bind, diag)
assert all(row['notes']['start_equity'] == 250000 for row in outputs.values())
assert all(row['notes']['grid_phase_default'] == 1 for row in outputs.values())
"""
    result = subprocess.run([sys.executable, "-c", code, str(tmp_path)], cwd=e.HERE,
                            env={**os.environ, "N12_YEAR": "2022"}, capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stdout + result.stderr
