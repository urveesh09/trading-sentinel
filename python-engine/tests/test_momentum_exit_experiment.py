"""S6a: frozen read-only momentum exit experiments."""
from __future__ import annotations

import ast
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

import pytest

import momentum_exit_experiment as experiment
import momentum_exit_study as study
from momentum_exit_study import ExitStudyError

SOURCE_REF = "sha256:" + ("b" * 64)
START = datetime.fromisoformat("2026-09-25T10:00:00+05:30")
DEADLINE = datetime.fromisoformat("2026-09-25T15:15:00+05:30")
BEFORE = datetime(2026, 9, 1, tzinfo=timezone.utc)   # freeze before the entry -> HOLDOUT
AFTER = datetime(2026, 9, 30, tzinfo=timezone.utc)   # freeze after the entry -> DEVELOPMENT


def _path(price_at):
    """One quote per minute from entry to the exact 15:15 deadline."""
    rows, current = [], START
    while current <= DEADLINE:
        rows.append({"entry_id": "entry-1", "observed_at": current.isoformat(),
                     "ltp": round(price_at((current - START).total_seconds() / 60.0), 4)})
        current += timedelta(minutes=1)
    return rows


def _packet(quotes, **entry_changes):
    entry = {
        "entry_id": "entry-1", "source_ref": SOURCE_REF, "ticker": "ACME",
        "entry_at": START.isoformat(), "entry_price": 100.0, "stop_loss_initial": 98.0,
        "target_1": 104.0, "shares": 10, "atr_14_at_entry": 1.0, "vwap_at_entry": 99.0,
        "regime_at_entry": "REGIME_1_NORMAL",
    }
    entry.update(entry_changes)
    return {"schema": study.INPUT_SCHEMA, "study_id": "s6a-test", "max_quote_gap_seconds": 60,
            "entries": [entry], "quotes": quotes}


def _run(tmp_path, packet, *, candidate=experiment.THESIS_POLICY, frozen_at=BEFORE):
    path = tmp_path / f"input-{len(list(tmp_path.iterdir()))}.json"
    path.write_text(json.dumps(packet), encoding="utf-8")
    manifest = experiment.freeze_experiment_manifest(
        experiment_id="s6a", candidate_policy=candidate, frozen_at=frozen_at)
    return experiment.build_exit_experiment(path, manifest)


def _slow_then(after):
    """Flat +0.1R until the 90-minute slow time stop, then ``after(minutes)``."""
    return lambda minute: 100.2 if minute <= 90 else after(minute)


def _rising(minute):
    return min(103.5, 100.2 + (minute - 90) * 0.05)


def test_confirmed_time_stop_extension_captures_continuation(tmp_path):
    report = _run(tmp_path, _packet(_path(_slow_then(_rising))))
    pair = report["pairs"][0]
    assert pair["baseline"]["reason"].startswith("time_stop_90min")
    assert pair["candidate"]["exits_replaced"][0]["exit_replaced"].startswith("time_stop_90min")
    assert pair["candidate"]["net_pnl"] > pair["baseline"]["net_pnl"]
    assert pair["sample_class"] == "HOLDOUT"
    assert report["summary"]["holdout"]["paired"]["candidate_better"] == 1
    assert report["summary"]["qualification"] == "NOT_ASSESSED"


def test_bad_continuation_exits_when_confirmation_is_lost_and_is_reported_worse(tmp_path):
    fading = _slow_then(lambda minute: 100.2 if minute < 100 else 99.9)
    report = _run(tmp_path, _packet(_path(fading)))
    pair = report["pairs"][0]
    assert pair["candidate"]["reason"] == "thesis_confirmation_lost:progress_below_minimum"
    assert pair["candidate"]["exit_at"] == (START + timedelta(minutes=100)).isoformat()
    assert pair["candidate"]["net_pnl"] < pair["baseline"]["net_pnl"]
    assert report["summary"]["all"]["paired"]["candidate_worse"] == 1


def test_gap_through_stop_exits_at_the_observed_gap_price_for_both(tmp_path):
    gap = lambda minute: 100.5 if minute < 30 else 97.0
    pair = _run(tmp_path, _packet(_path(gap)))["pairs"][0]
    for side in ("baseline", "candidate"):
        assert pair[side]["reason"] == "protective_stop_observed"
        assert pair[side]["legs"][-1]["exit_price"] == 97.0
    assert pair["candidate"]["mae_r"] == -1.5


@pytest.mark.parametrize("changes", [{"vwap_at_entry": None}, {"regime_at_entry": "REGIME_3_CRISIS"}])
def test_unconfirmable_thesis_leaves_the_baseline_exit_unchanged(tmp_path, changes):
    pair = _run(tmp_path, _packet(_path(_slow_then(_rising)), **changes))["pairs"][0]
    assert pair["candidate"]["exits_replaced"] == []
    assert pair["candidate"]["net_pnl"] == pair["baseline"]["net_pnl"]
    assert pair["candidate"]["reason"] == pair["baseline"]["reason"]


def test_confirmed_target_is_extended_with_a_rising_trail_and_deadline(tmp_path, monkeypatch):
    monkeypatch.setattr(study.settings, "MOMENTUM_USE_SCALE_OUT", False)
    runner = lambda minute: 100.0 + min(minute, 70) * 0.1  # target 104 at minute 40, 107 by 70
    pair = _run(tmp_path, _packet(_path(runner)))["pairs"][0]
    assert pair["baseline"]["reason"] == "target_hit"
    assert pair["candidate"]["exits_replaced"][0]["exit_replaced"] == "target_hit"
    assert pair["candidate"]["reason"] == "intraday_deadline"
    assert pair["candidate"]["net_pnl"] > pair["baseline"]["net_pnl"]
    assert pair["candidate"]["giveback_r"] == pytest.approx(0.0, abs=1e-6)


def test_later_quotes_cannot_change_earlier_decisions(tmp_path):
    first = _run(tmp_path, _packet(_path(_slow_then(_rising))))["pairs"][0]["candidate"]
    altered = _slow_then(lambda minute: _rising(minute) if minute <= 150 else 95.0)
    second = _run(tmp_path, _packet(_path(altered)))["pairs"][0]["candidate"]
    cutoff = (START + timedelta(minutes=150)).isoformat()
    assert first["exits_replaced"] == second["exits_replaced"]
    assert [leg for leg in first["legs"] if leg["at"] <= cutoff] == \
           [leg for leg in second["legs"] if leg["at"] <= cutoff]


def test_target_hold_candidate_reproduces_the_v1_alternative(tmp_path, monkeypatch):
    monkeypatch.setattr(study.settings, "MOMENTUM_USE_SCALE_OUT", False)
    packet = _packet(_path(lambda minute: 100.0 + min(minute, 70) * 0.1))
    report = _run(tmp_path, packet, candidate=study.ALTERNATIVE_POLICY)
    v1_path = tmp_path / "v1.json"
    v1_path.write_text(json.dumps(packet), encoding="utf-8")
    v1 = study.build_momentum_exit_study(v1_path)["pairs"][0]
    candidate = report["pairs"][0]["candidate"]
    assert {key: candidate[key] for key in v1["alternative"]} == v1["alternative"]
    assert {key: report["pairs"][0]["baseline"][key] for key in v1["baseline"]} == v1["baseline"]


def test_entries_before_the_freeze_are_development_only(tmp_path):
    report = _run(tmp_path, _packet(_path(_slow_then(_rising))), frozen_at=AFTER)
    assert report["pairs"][0]["sample_class"] == "DEVELOPMENT"
    assert report["summary"]["holdout"]["pairs"] == 0
    assert report["summary"]["holdout"]["paired"] == {"complete_pairs": 0}


def test_tampered_or_stale_manifest_is_refused(tmp_path, monkeypatch):
    path = tmp_path / "input.json"
    path.write_text(json.dumps(_packet(_path(_slow_then(_rising)))), encoding="utf-8")
    manifest = experiment.freeze_experiment_manifest(experiment_id="s6a", candidate_policy=experiment.THESIS_POLICY,
                                                     frozen_at=BEFORE)
    tampered = json.loads(json.dumps(manifest))
    tampered["candidate_parameters"]["max_pullback_from_running_high_r"] = 5.0
    with pytest.raises(ExitStudyError, match="FROZEN_POLICY_MISMATCH: candidate_parameters"):
        experiment.build_exit_experiment(path, tampered)
    monkeypatch.setattr(study.settings, "MOMENTUM_TIME_STOP_MIN", 120)
    with pytest.raises(ExitStudyError, match="FROZEN_POLICY_MISMATCH: evaluator_settings"):
        experiment.build_exit_experiment(path, manifest)


def test_incomplete_path_is_insufficient_for_both_policies(tmp_path):
    quotes = [row for row in _path(_slow_then(_rising)) if row["observed_at"] != (START + timedelta(minutes=50)).isoformat()]
    quotes = [row for row in quotes if row["observed_at"] != (START + timedelta(minutes=51)).isoformat()]
    pair = _run(tmp_path, _packet(quotes))["pairs"][0]
    assert pair["status"] == "INSUFFICIENT_EVIDENCE"
    assert pair["baseline"]["status"] == pair["candidate"]["status"] == "INSUFFICIENT_EVIDENCE"


def test_cli_freeze_and_evaluate_never_overwrite(tmp_path):
    packet = tmp_path / "packet.json"
    packet.write_text(json.dumps(_packet(_path(_slow_then(_rising)))), encoding="utf-8")
    manifest, report = tmp_path / "manifest.json", tmp_path / "report.json"
    assert experiment._main(["freeze", "--experiment-id", "cli", "--candidate", experiment.THESIS_POLICY,
                             "--output", str(manifest)]) == 0
    assert experiment._main(["evaluate", "--manifest", str(manifest), "--input", str(packet),
                             "--output", str(report)]) == 0
    assert json.loads(report.read_text(encoding="utf-8"))["schema"] == experiment.REPORT_SCHEMA
    with pytest.raises(SystemExit):
        experiment._main(["evaluate", "--manifest", str(manifest), "--input", str(packet),
                          "--output", str(report)])


def test_experiment_has_no_runtime_caller_or_side_effect_imports():
    root = Path(experiment.__file__).resolve().parent
    tree = ast.parse((root / "momentum_exit_experiment.py").read_text(encoding="utf-8"))
    imported = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)} | {
        alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
    assert not imported & {"aiosqlite", "sqlite3", "httpx", "requests", "kite_client", "main",
                           "scheduler_setup", "telegram", "fno_executor"}
    assert _importers(root, "momentum_exit_experiment") == []


def _importers(root, module):
    """Engine modules that actually import ``module`` (AST, not text)."""
    found = []
    for path in sorted(root.glob("*.py")):
        if path.stem == module:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
        except SyntaxError:
            continue
        names = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)} | {
            alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
        if module in names:
            found.append(path.name)
    return found
