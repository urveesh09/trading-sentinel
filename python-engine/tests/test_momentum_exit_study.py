import ast
from datetime import datetime, timedelta
import inspect
import json

import pytest

import momentum_exit_study as study


SOURCE_REF = "sha256:" + ("a" * 64)


def _quotes(*, target=104.0, close=106.0, gap_at=None):
    start = datetime.fromisoformat("2026-09-25T10:00:00+05:30")
    deadline = datetime.fromisoformat("2026-09-25T15:15:00+05:30")
    values = {}
    current = start
    while current <= deadline:
        values[current] = close if current >= start + timedelta(minutes=2) else 100.0
        current += timedelta(minutes=1)
    values[start + timedelta(minutes=1)] = target
    values[start + timedelta(minutes=2)] = close
    if gap_at is not None:
        values.pop(start + timedelta(minutes=gap_at), None)
    return [
        {"entry_id": "entry-1", "observed_at": stamp.isoformat(), "ltp": price}
        for stamp, price in values.items()
    ]


def _packet(**changes):
    packet = {
        "schema": study.INPUT_SCHEMA,
        "study_id": "paired-exit-test",
        "max_quote_gap_seconds": 60,
        "entries": [{
            "entry_id": "entry-1",
            "source_ref": SOURCE_REF,
            "ticker": "ACME",
            "entry_at": "2026-09-25T10:00:00+05:30",
            "entry_price": 100.0,
            "stop_loss_initial": 98.0,
            "target_1": 104.0,
            "shares": 10,
            "atr_14_at_entry": 1.0,
            "vwap_at_entry": 99.0,
            "regime_at_entry": "REGIME_1_NORMAL",
        }],
        "quotes": _quotes(),
    }
    packet.update(changes)
    return packet


def _write(tmp_path, packet):
    path = tmp_path / "input.json"
    path.write_text(json.dumps(packet, separators=(",", ":")), encoding="utf-8")
    return path


def test_same_complete_path_is_paired_and_target_hold_trail_is_predeclared(tmp_path, monkeypatch):
    monkeypatch.setattr(study.settings, "MOMENTUM_USE_SCALE_OUT", False)
    report = study.build_momentum_exit_study(_write(tmp_path, _packet()))

    pair = report["pairs"][0]
    baseline, alternative = pair["baseline"], pair["alternative"]
    assert pair["status"] == "COMPLETE"
    assert baseline["status"] == alternative["status"] == "CLOSED"
    assert baseline["reason"] == "target_hit"
    assert alternative["target_hold_activated_at"] == "2026-09-25T10:01:00+05:30"
    assert alternative["reason"] == "intraday_deadline"
    assert alternative["net_pnl"] > baseline["net_pnl"]
    assert alternative["costs"] > 0 and baseline["costs"] > 0
    assert report["summary"]["qualification"] == "NOT_ASSESSED"


def test_baseline_uses_the_current_pure_exit_evaluator(tmp_path, monkeypatch):
    monkeypatch.setattr(study.settings, "MOMENTUM_USE_SCALE_OUT", False)
    real = study.evaluate_momentum_exit
    calls = []

    def wrapped(position, ltp, now):
        calls.append((position.get("ticker"), ltp, now))
        return real(position, ltp, now)

    monkeypatch.setattr(study, "evaluate_momentum_exit", wrapped)
    report = study.build_momentum_exit_study(_write(tmp_path, _packet()))

    assert report["pairs"][0]["baseline"]["reason"] == "target_hit"
    assert calls
    assert all(ticker == "ACME" for ticker, _ltp, _at in calls)


def test_protective_stop_is_not_removed_by_the_hold_variant(tmp_path, monkeypatch):
    monkeypatch.setattr(study.settings, "MOMENTUM_USE_SCALE_OUT", False)
    packet = _packet(quotes=_quotes(target=97.0, close=97.0))
    report = study.build_momentum_exit_study(_write(tmp_path, packet))

    pair = report["pairs"][0]
    assert pair["baseline"]["reason"] == "protective_stop_observed"
    assert pair["alternative"]["reason"] == "protective_stop_observed"
    assert pair["alternative"]["target_hold_activated_at"] is None


@pytest.mark.parametrize("mutate,expected", [
    (lambda packet: packet.update({"quotes": _quotes(gap_at=100)}), "quote_gap_exceeds_declared_maximum"),
    (lambda packet: packet["quotes"].pop(), "exact_1515_ist_quote_missing"),
    (lambda packet: packet["quotes"].insert(2, {"entry_id": "entry-1", "observed_at": "2026-09-25T10:01:00+05:30", "ltp": 105.0}), "conflicting_quote_clock"),
    (lambda packet: packet["quotes"].insert(0, {"entry_id": "entry-1", "observed_at": "2026-09-25T09:59:00+05:30", "ltp": 100.0}), "quote_precedes_entry"),
])
def test_incomplete_or_ambiguous_paths_are_not_given_synthetic_exits(tmp_path, mutate, expected):
    packet = _packet()
    mutate(packet)
    report = study.build_momentum_exit_study(_write(tmp_path, packet))

    pair = report["pairs"][0]
    assert pair["status"] == "INSUFFICIENT_EVIDENCE"
    assert pair["reason"] == expected
    assert pair["baseline"]["legs"] == pair["alternative"]["legs"] == []
    assert report["summary"]["baseline"]["net_pnl"] is None


def test_exact_duplicate_quote_is_idempotent_but_later_quote_cannot_change_earlier_exit(tmp_path, monkeypatch):
    monkeypatch.setattr(study.settings, "MOMENTUM_USE_SCALE_OUT", False)
    packet = _packet()
    target_quote = next(row for row in packet["quotes"] if row["observed_at"].endswith("10:01:00+05:30"))
    packet["quotes"].insert(2, dict(target_quote))
    with_duplicate = study.build_momentum_exit_study(_write(tmp_path, packet))

    baseline = with_duplicate["pairs"][0]["baseline"]
    assert baseline["exit_at"] == "2026-09-25T10:01:00+05:30"
    assert baseline["legs"][0]["exit_price"] == 104.0


def test_scale_out_costs_are_kept_as_partial_legs_then_one_terminal_leg(tmp_path, monkeypatch):
    monkeypatch.setattr(study.settings, "MOMENTUM_USE_SCALE_OUT", True)
    monkeypatch.setattr(study.settings, "MOMENTUM_SCALE_OUT_R", 1.0)
    monkeypatch.setattr(study.settings, "MOMENTUM_SCALE_OUT_FRAC", 0.5)
    packet = _packet(quotes=_quotes(target=102.0, close=103.0))
    packet["entries"][0]["target_1"] = 104.0
    report = study.build_momentum_exit_study(_write(tmp_path, packet))

    legs = report["pairs"][0]["baseline"]["legs"]
    assert len(legs) == 2
    assert legs[0]["quantity"] == 5
    assert legs[-1]["reason"] == "intraday_deadline"
    assert report["pairs"][0]["baseline"]["costs"] == pytest.approx(sum(leg["costs"] for leg in legs))


def test_report_is_deterministic_and_output_never_overwrites(tmp_path, monkeypatch):
    monkeypatch.setattr(study.settings, "MOMENTUM_USE_SCALE_OUT", False)
    path = _write(tmp_path, _packet())
    first = study.build_momentum_exit_study(path)
    second = study.build_momentum_exit_study(path)
    assert first == second
    assert first["report_fingerprint"].startswith("sha256:")

    output = tmp_path / "report.json"
    study.write_study_report_once(first, output)
    original = output.read_bytes()
    with pytest.raises(study.ExitStudyError, match="without overwrite"):
        study.write_study_report_once(first, output)
    assert output.read_bytes() == original


def test_cli_builds_a_new_immutable_report_without_runtime_state(tmp_path, monkeypatch):
    monkeypatch.setattr(study.settings, "MOMENTUM_USE_SCALE_OUT", False)
    output = tmp_path / "cli-report.json"
    assert study._main(["--input", str(_write(tmp_path, _packet())), "--output", str(output)]) == 0
    written = json.loads(output.read_text(encoding="utf-8"))
    assert written["schema"] == study.REPORT_SCHEMA
    assert written["summary"]["qualification"] == "NOT_ASSESSED"


def test_invalid_input_is_rejected_before_any_report(tmp_path):
    packet = _packet()
    packet["entries"][0]["source_ref"] = "not-an-archive-hash"
    with pytest.raises(study.ExitStudyError, match="source_ref"):
        study.build_momentum_exit_study(_write(tmp_path, packet))

    packet = _packet()
    packet["entries"][0]["shares"] = "10"
    with pytest.raises(study.ExitStudyError, match="shares"):
        study.build_momentum_exit_study(_write(tmp_path, packet))


def test_module_has_no_runtime_order_network_or_storage_capability():
    tree = ast.parse(inspect.getsource(study))
    imports = set()
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".")[0])
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, ast.Name):
            names.add(node.id)
    assert not (imports & {"httpx", "requests", "aiosqlite", "kite", "fno_executor"})
    assert not (names & {"place_order", "modify_order", "cancel_order", "post", "put", "delete"})
