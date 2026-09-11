import json

import pytest

from intraday_spread_replay import ReplayInputError
from intraday_spread_signal_artifact import generate_orb_threshold_artifact, load_signal_artifact, write_signal_artifact


def payload(**changes):
    value = {"format": "intraday_spread_signal_artifact_v1", "evaluator_id": "orb_threshold_v1",
             "evaluator_sha256": "a" * 64, "policy_id": "policy-v1", "policy_sha256": "b" * 64,
             "config_sha256": "c" * 64, "underlying": "NIFTY", "session_date": "2026-09-10",
             "source_manifests": [{"reference": "quotes/2026-09-10", "sha256": "d" * 64}],
             "signals": [{"decision_id": "nifty-open", "received_at": "2026-09-10T04:30:10+00:00",
                          "decision_cutoff": "2026-09-10T04:30:10+00:00", "score": 1.0,
                          "evaluator_input": {"direction": "LONG", "close": 101, "trigger": 100,
                          "source_packets": [{"packet_id": "bar-1", "received_at": "2026-09-10T04:25:00+00:00"}]}}]}
    value.update(changes)
    return value


def test_signal_artifact_is_reproducible_and_tamper_evident(tmp_path):
    one, two = tmp_path / "one.json", tmp_path / "two.json"
    first, second = write_signal_artifact(one, payload()), write_signal_artifact(two, payload())
    assert first["artifact_sha256"] == second["artifact_sha256"]
    saved = json.loads(one.read_text(encoding="utf-8")); saved["signals"][0]["score"] = 0.0
    one.write_text(json.dumps(saved), encoding="utf-8")
    with pytest.raises(ReplayInputError, match="score does not reproduce"):
        load_signal_artifact(one, underlying="NIFTY", policy_id="policy-v1", session_date="2026-09-10")


def test_signal_artifact_rejects_future_causal_source_and_wrong_scope(tmp_path):
    path = tmp_path / "artifact.json"
    bad = payload(signals=[{"decision_id": "x", "received_at": "2026-09-10T04:30:00+00:00",
                            "decision_cutoff": "2026-09-10T04:30:00+00:00", "score": 1.0,
                            "evaluator_input": {"direction": "LONG", "close": 101, "trigger": 100,
                            "source_packets": [{"packet_id": "future", "received_at": "2026-09-10T04:31:00+00:00"}]}}])
    with pytest.raises(ReplayInputError, match="future"):
        write_signal_artifact(path, bad)
    write_signal_artifact(path, payload())
    with pytest.raises(ReplayInputError, match="underlying"):
        load_signal_artifact(path, underlying="SENSEX", policy_id="policy-v1", session_date="2026-09-10")


def test_signal_artifact_rejects_duplicate_causal_packet_identity(tmp_path):
    bad = payload()
    bad["signals"][0]["evaluator_input"]["source_packets"].append(
        {"packet_id": "bar-1", "received_at": "2026-09-10T04:26:00+00:00"}
    )
    with pytest.raises(ReplayInputError, match="duplicate"):
        write_signal_artifact(tmp_path / "artifact.json", bad)


def test_registered_evaluator_generates_scores_and_future_packet_cannot_change_earlier_decision(tmp_path):
    common = dict(underlying="NIFTY", policy_id="policy-v1", evaluator_sha256="a" * 64,
                  policy_sha256="b" * 64, config_sha256="c" * 64, session_date="2026-09-10",
                  source_manifests=[{"reference": "recorded.json", "sha256": "d" * 64}])
    first = generate_orb_threshold_artifact(tmp_path / "one.json", **common, decisions=[{
        "decision_id": "early", "received_at": "2026-09-10T04:30:00+00:00", "decision_cutoff": "2026-09-10T04:30:00+00:00",
        "evaluator_input": {"direction": "LONG", "close": 101, "trigger": 100,
        "source_packets": [{"packet_id": "early-bar", "received_at": "2026-09-10T04:29:00+00:00"}]}}])
    second = generate_orb_threshold_artifact(tmp_path / "two.json", **common, decisions=[{
        "decision_id": "early", "received_at": "2026-09-10T04:30:00+00:00", "decision_cutoff": "2026-09-10T04:30:00+00:00",
        "evaluator_input": {"direction": "LONG", "close": 101, "trigger": 100,
        "source_packets": [{"packet_id": "early-bar", "received_at": "2026-09-10T04:29:00+00:00"}]}}, {
        "decision_id": "later", "received_at": "2026-09-10T04:35:00+00:00", "decision_cutoff": "2026-09-10T04:35:00+00:00",
        "evaluator_input": {"direction": "SHORT", "close": 99, "trigger": 100,
        "source_packets": [{"packet_id": "future-for-early", "received_at": "2026-09-10T04:34:00+00:00"}]}}])
    assert first["signals"][0] == second["signals"][0]
    assert first["signals"][0]["score"] == 1.0
