import json
import sys
from types import SimpleNamespace

import pytest

from research_cli import main, _write_comparison_output


def test_freeze_cli_explicit_inputs_and_no_backdating(tmp_path, monkeypatch, capsys):
    calls = []
    async def freeze(db, manifest, **kwargs):
        calls.append((db, manifest, kwargs))
        return {"protocol_id": manifest["protocol_id"], "manifest_sha256": "a" * 64}
    async def evaluate(*args, **kwargs):
        raise AssertionError("freeze must not evaluate")
    monkeypatch.setitem(sys.modules, "proactive_comparison_protocol", SimpleNamespace(
        freeze_comparison_protocol=freeze, evaluate_comparison_protocol=evaluate))
    source = tmp_path / "manifest.json"
    source.write_text(json.dumps({"protocol_id": "fixture"}), encoding="utf-8")
    db, output = str(tmp_path / "offline.db"), str(tmp_path / "out.json")
    args = ["freeze-strategy-comparison", "--db", db, "--manifest", str(source), "--output", output]
    assert main(args) == 0
    assert calls == [(db, {"protocol_id": "fixture"}, {})]
    assert json.loads(capsys.readouterr().out)["can_place_orders"] is False
    assert main(args) == 0  # Immutable identical retry.
    with pytest.raises(SystemExit):
        main(args + ["--now", "2020-01-01T00:00:00Z"])


def test_evaluate_cli_forwards_aware_proposals_and_complete_input(tmp_path, monkeypatch):
    calls = []
    async def freeze(*args, **kwargs):
        raise AssertionError("evaluate must not create a protocol")
    async def evaluate(db, **kwargs):
        calls.append((db, kwargs))
        return {"protocol_id": kwargs["protocol_id"], "report_id": kwargs["report_id"],
                "can_place_orders": False, "can_qualify": False, "authorization_effect": "NONE"}
    monkeypatch.setitem(sys.modules, "proactive_comparison_protocol", SimpleNamespace(
        freeze_comparison_protocol=freeze, evaluate_comparison_protocol=evaluate))
    row = dict(opportunity_id="o1", policy_id="orb", instrument="NIFTY", entry=100, stop=99,
               target=102, valid_until="2026-09-14T10:00:00Z", signal_at="2026-09-14T09:00:00Z",
               score=1, required_capital=100, reason="fixture")
    inputs = {"proposals": [row], "future_bars": {"NIFTY": []}, "session_coverage": {"2026-09-14": "MISSING"}}
    source = tmp_path / "inputs.json"
    source.write_text(json.dumps(inputs), encoding="utf-8")
    args = ["evaluate-strategy-comparison", "--db", str(tmp_path / "offline.db"), "--protocol-id", "p1",
            "--report-id", "r1", "--inputs", str(source), "--output", str(tmp_path / "report.json")]
    assert main(args) == 0
    _, forwarded = calls[0]
    assert forwarded["proposals"][0].signal_at.utcoffset().total_seconds() == 0
    assert forwarded["future_bars"] == inputs["future_bars"]
    assert forwarded["session_coverage"] == inputs["session_coverage"]
    assert "now" not in forwarded
    row["signal_at"] = "2026-09-14T09:00:00"
    source.write_text(json.dumps(inputs), encoding="utf-8")
    assert main(args) == 2
    assert len(calls) == 1


def test_comparison_output_rejects_overwrite_and_cleans_scratch(tmp_path):
    path = tmp_path / "out.json"
    _write_comparison_output(str(path), {"value": 1})
    _write_comparison_output(str(path), {"value": 1})
    with pytest.raises(ValueError, match="different immutable"):
        _write_comparison_output(str(path), {"value": 2})
    assert json.loads(path.read_text(encoding="utf-8")) == {"value": 1}
    assert not list(tmp_path.glob(".comparison-*"))


def test_comparison_cli_requires_explicit_database():
    with pytest.raises(SystemExit):
        main(["freeze-strategy-comparison", "--manifest", "fixture.json", "--output", "out.json"])


def test_conflicting_concurrent_outputs_preserve_exactly_one_value(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    path = str(tmp_path / "concurrent.json")
    def publish(value):
        try:
            _write_comparison_output(path, {"value": value})
            return "accepted"
        except ValueError:
            return "rejected"
    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(publish, [1, 2]))
    assert sorted(outcomes) == ["accepted", "rejected"]
    assert json.loads((tmp_path / "concurrent.json").read_text(encoding="utf-8"))["value"] in {1, 2}
    assert not list(tmp_path.glob(".comparison-*"))


def test_real_cli_registers_protocol_and_retains_missing_zero_sessions(tmp_path):
    from datetime import datetime, timedelta, timezone
    from zoneinfo import ZoneInfo
    now = datetime.now(timezone.utc)
    today = now.astimezone(ZoneInfo("Asia/Kolkata")).date()
    holdout = (today + timedelta(days=2)).isoformat()
    manifest = {"protocol_id": "real-cli-fixture", "account_id": "fixture-only",
                "code_revision": "a" * 40, "frozen_at": now.isoformat(),
                "training_sessions": [(today - timedelta(days=2)).isoformat()], "holdout_sessions": [holdout],
                "alternatives": [{"name": "orb", "entry": "NEXT_EXECUTABLE_OPEN_V1", "exit": "STOP_TARGET_TIME_V1"}],
                "baseline": "orb", "cash": 8000,
                "cost_snapshot": {"fee_rate": .001, "slippage_bps": 5, "schedule_version": "FIXTURE_ONLY"},
                "cost_stress": {"fee_multiplier": 2, "additional_slippage_bps": 10},
                "thresholds": {"minimum_closed_outcomes": 20, "minimum_complete_sessions": 5,
                               "maximum_drawdown_pct": .1, "minimum_net_expectancy": 0,
                               "minimum_paired_delta": 0, "confidence_level": .95, "bootstrap_samples": 200}}
    source = tmp_path / "protocol.json"
    source.write_text(json.dumps(manifest), encoding="utf-8")
    db, frozen = str(tmp_path / "offline.db"), tmp_path / "frozen.json"
    args = ["freeze-strategy-comparison", "--db", db, "--manifest", str(source), "--output", str(frozen)]
    assert main(args) == 0
    assert main(args) == 0
    retained = json.loads(frozen.read_text(encoding="utf-8"))
    assert retained["can_place_orders"] is False
    assert retained["account_id"] == "fixture-only"
    inputs = tmp_path / "inputs.json"
    inputs.write_text(json.dumps({"proposals": [], "future_bars": {},
                                "session_coverage": {"orb": {holdout: "MISSING"}}}), encoding="utf-8")
    output = tmp_path / "report.json"
    evaluate = ["evaluate-strategy-comparison", "--db", db, "--protocol-id", "real-cli-fixture",
                "--report-id", "missing", "--inputs", str(inputs), "--output", str(output)]
    assert main(evaluate) == 0
    assert main(evaluate) == 0
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["approval_usable"] is False
    assert report["can_qualify"] is False
    assert report["authorization_effect"] == "NONE"
    assert report["disposition"] in {"REJECTED", "UNCERTAIN"}
    assert report["profiles"][0]["coverage"] == [{"session": holdout, "status": "MISSING"}]
