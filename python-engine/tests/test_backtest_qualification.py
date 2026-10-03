from datetime import datetime, timezone

import pytest

from backtest_qualification import (
    QualificationError, freeze, record_evaluation, validate_run,
)


NOW = datetime(2026, 10, 3, tzinfo=timezone.utc)


def _freeze(tmp_path):
    return freeze(
        registry=str(tmp_path / "holdouts.jsonl"), strategy_id="penny_breakout_mis_lifecycle_1m",
        development_window=("2026-01-01", "2026-10-03"), holdout_window=("2026-10-04", "2026-10-31"),
        snapshot_sha256="sha256:snapshot", policy={"code": "a"}, request_config={"tickers": ["AAA"]}, now=NOW,
    )


def test_freeze_precedes_holdout_and_locks_policy_snapshot_and_config(tmp_path):
    record = _freeze(tmp_path)
    verdict = validate_run(
        registry=str(tmp_path / "holdouts.jsonl"), qualification_id=record["qualification_id"],
        strategy_id="penny_breakout_mis_lifecycle_1m", window=("2026-10-04", "2026-10-31"),
        snapshot_sha256="sha256:snapshot", policy={"code": "a"}, request_config={"tickers": ["AAA"]},
    )
    assert verdict["status"] == "FIRST_EVALUATION"
    with pytest.raises(QualificationError, match="policy changed"):
        validate_run(registry=str(tmp_path / "holdouts.jsonl"), qualification_id=record["qualification_id"],
                     strategy_id="penny_breakout_mis_lifecycle_1m", window=("2026-10-04", "2026-10-31"),
                     snapshot_sha256="sha256:snapshot", policy={"code": "b"}, request_config={"tickers": ["AAA"]})


def test_retroactive_or_duplicate_freezes_are_refused(tmp_path):
    with pytest.raises(QualificationError, match="retroactive"):
        freeze(registry=str(tmp_path / "holdouts.jsonl"), strategy_id="x",
               development_window=("2026-01-01", "2026-01-02"), holdout_window=("2026-10-03", "2026-10-04"),
               snapshot_sha256="sha256:x", policy={}, request_config={}, now=NOW)
    _freeze(tmp_path)
    with pytest.raises(QualificationError, match="already frozen"):
        _freeze(tmp_path)


def test_every_evaluation_is_append_only_and_reuse_is_exposed(tmp_path):
    record = _freeze(tmp_path)
    first = record_evaluation(registry=str(tmp_path / "holdouts.jsonl"), qualification_id=record["qualification_id"],
                              report_sha256="sha256:r1", now=NOW)
    second = record_evaluation(registry=str(tmp_path / "holdouts.jsonl"), qualification_id=record["qualification_id"],
                               report_sha256="sha256:r2", now=NOW)
    assert (first["ordinal"], second["ordinal"], second["status"]) == (1, 2, "EVALUATED_REUSED")
    verdict = validate_run(registry=str(tmp_path / "holdouts.jsonl"), qualification_id=record["qualification_id"],
                           strategy_id="penny_breakout_mis_lifecycle_1m", window=("2026-10-04", "2026-10-31"),
                           snapshot_sha256="sha256:snapshot", policy={"code": "a"}, request_config={"tickers": ["AAA"]})
    assert verdict["status"] == "REUSED_HOLDOUT" and verdict["prior_evaluations"] == 2
