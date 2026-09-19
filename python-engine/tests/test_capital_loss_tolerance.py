"""[WORKFLOW-F.9 2026-09-17] Tests for the capital-increase
loss-tolerance loader.

Per Workstream F in NEXT_AGENT_PLAN.md:
> Establish capital-increase criteria from externally
> reconciled net results, drawdown, execution quality and
> operational stability. Leave the user's loss tolerance
> as an explicit input if not supplied.

These tests pin the loss-tolerance loader:

  - ``load_loss_tolerance`` reads a JSON config file.
  - Required fields are validated (loss_tolerance_pct,
    max_drawdown_pct, min_win_rate_pct,
    max_consecutive_losses, min_live_bankroll_inr).
  - Invalid values raise ``ValueError``.
  - ``merge_loss_tolerance`` overlays operator overrides
    on a base config without dropping untouched fields.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

PYTHON_ENGINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PYTHON_ENGINE))

from capital_loss_tolerance import (  # noqa: E402  -- import path
    LossToleranceConfig,
    LossToleranceField,
    load_loss_tolerance,
    merge_loss_tolerance,
)


def _write_config(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _valid_payload() -> dict:
    return {
        "loss_tolerance_pct": 25.0,
        "max_drawdown_pct": 15.0,
        "min_win_rate_pct": 50.0,
        "max_consecutive_losses": 5,
        "min_live_bankroll_inr": 1500.0,
        "operator": "urveesh",
    }


# -- 1. LossToleranceField enum -----------------------------


def test_loss_tolerance_field_has_five_values():
    assert {f.value for f in LossToleranceField} == {
        "loss_tolerance_pct",
        "max_drawdown_pct",
        "min_win_rate_pct",
        "max_consecutive_losses",
        "min_live_bankroll_inr",
    }


# -- 2. Load a valid config ---------------------------------


def test_load_valid_config(tmp_path):
    config_path = tmp_path / "lt.json"
    _write_config(config_path, _valid_payload())
    cfg = load_loss_tolerance(config_path)
    assert cfg.loss_tolerance_pct == 25.0
    assert cfg.max_drawdown_pct == 15.0
    assert cfg.min_win_rate_pct == 50.0
    assert cfg.max_consecutive_losses == 5
    assert cfg.min_live_bankroll_inr == 1500.0
    assert cfg.operator == "urveesh"


def test_load_valid_config_without_operator(tmp_path):
    payload = _valid_payload()
    payload.pop("operator")
    config_path = tmp_path / "lt.json"
    _write_config(config_path, payload)
    cfg = load_loss_tolerance(config_path)
    assert cfg.operator is None


def test_load_valid_config_integer_loss_tolerance(tmp_path):
    """[WORKFLOW-F.9 2026-09-17] Integers are coerced to
    floats for the percentage fields."""
    payload = _valid_payload()
    payload["loss_tolerance_pct"] = 25  # int, not float.
    config_path = tmp_path / "lt.json"
    _write_config(config_path, payload)
    cfg = load_loss_tolerance(config_path)
    assert cfg.loss_tolerance_pct == 25.0


# -- 3. Required fields --------------------------------------


def test_missing_field_raises(tmp_path):
    payload = _valid_payload()
    del payload["max_drawdown_pct"]
    config_path = tmp_path / "lt.json"
    _write_config(config_path, payload)
    with pytest.raises(ValueError, match="missing fields"):
        load_loss_tolerance(config_path)


def test_multiple_missing_fields_listed_in_error(tmp_path):
    payload = {"loss_tolerance_pct": 25.0}
    config_path = tmp_path / "lt.json"
    _write_config(config_path, payload)
    with pytest.raises(ValueError) as exc_info:
        load_loss_tolerance(config_path)
    msg = str(exc_info.value)
    assert "max_drawdown_pct" in msg
    assert "min_win_rate_pct" in msg
    assert "max_consecutive_losses" in msg
    assert "min_live_bankroll_inr" in msg


# -- 4. Value validation ------------------------------------


def test_loss_tolerance_pct_negative_raises(tmp_path):
    payload = _valid_payload()
    payload["loss_tolerance_pct"] = -1.0
    config_path = tmp_path / "lt.json"
    _write_config(config_path, payload)
    with pytest.raises(ValueError, match="between 0 and 100"):
        load_loss_tolerance(config_path)


def test_loss_tolerance_pct_above_100_raises(tmp_path):
    payload = _valid_payload()
    payload["loss_tolerance_pct"] = 150.0
    config_path = tmp_path / "lt.json"
    _write_config(config_path, payload)
    with pytest.raises(ValueError, match="between 0 and 100"):
        load_loss_tolerance(config_path)


def test_max_drawdown_pct_negative_raises(tmp_path):
    payload = _valid_payload()
    payload["max_drawdown_pct"] = -1.0
    config_path = tmp_path / "lt.json"
    _write_config(config_path, payload)
    with pytest.raises(ValueError, match="between 0 and 100"):
        load_loss_tolerance(config_path)


def test_max_consecutive_losses_negative_raises(tmp_path):
    payload = _valid_payload()
    payload["max_consecutive_losses"] = -1
    config_path = tmp_path / "lt.json"
    _write_config(config_path, payload)
    with pytest.raises(ValueError, match=">= 0"):
        load_loss_tolerance(config_path)


def test_max_consecutive_losses_must_be_integer(tmp_path):
    payload = _valid_payload()
    payload["max_consecutive_losses"] = "five"  # not a number.
    config_path = tmp_path / "lt.json"
    _write_config(config_path, payload)
    with pytest.raises(ValueError, match="integer"):
        load_loss_tolerance(config_path)


def test_min_live_bankroll_inr_negative_raises(tmp_path):
    payload = _valid_payload()
    payload["min_live_bankroll_inr"] = -100.0
    config_path = tmp_path / "lt.json"
    _write_config(config_path, payload)
    with pytest.raises(ValueError, match="non-negative"):
        load_loss_tolerance(config_path)


def test_non_numeric_field_raises(tmp_path):
    payload = _valid_payload()
    payload["loss_tolerance_pct"] = "not a number"
    config_path = tmp_path / "lt.json"
    _write_config(config_path, payload)
    with pytest.raises(ValueError, match="must be a number"):
        load_loss_tolerance(config_path)


# -- 5. File I/O --------------------------------------------


def test_missing_file_raises(tmp_path):
    bogus = tmp_path / "does_not_exist.json"
    with pytest.raises(FileNotFoundError):
        load_loss_tolerance(bogus)


def test_invalid_json_raises(tmp_path):
    config_path = tmp_path / "lt.json"
    config_path.write_text("not valid json {", encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        load_loss_tolerance(config_path)


def test_non_object_json_raises(tmp_path):
    """[WORKFLOW-F.9 2026-09-17] A list (not a dict) is
    rejected."""
    config_path = tmp_path / "lt.json"
    config_path.write_text("[1, 2, 3]", encoding="utf-8")
    with pytest.raises(ValueError, match="must be a JSON object"):
        load_loss_tolerance(config_path)


def test_operator_field_must_be_string_or_null(tmp_path):
    payload = _valid_payload()
    payload["operator"] = 42  # not a string.
    config_path = tmp_path / "lt.json"
    _write_config(config_path, payload)
    with pytest.raises(ValueError, match="operator.*must be a string"):
        load_loss_tolerance(config_path)


# -- 6. merge_loss_tolerance --------------------------------


def test_merge_overrides_loss_tolerance_pct(tmp_path):
    """[WORKFLOW-F.9 2026-09-17] Operator override changes
    loss_tolerance_pct; other fields keep base values."""
    base = LossToleranceConfig(
        loss_tolerance_pct=25.0, max_drawdown_pct=15.0,
        min_win_rate_pct=50.0, max_consecutive_losses=5,
        min_live_bankroll_inr=1500.0, operator="base",
    )
    merged = merge_loss_tolerance(base, {
        "loss_tolerance_pct": 30.0,
    })
    assert merged.loss_tolerance_pct == 30.0
    assert merged.max_drawdown_pct == 15.0
    assert merged.min_win_rate_pct == 50.0
    assert merged.max_consecutive_losses == 5
    assert merged.min_live_bankroll_inr == 1500.0
    assert merged.operator == "base"


def test_merge_overrides_operator():
    """[WORKFLOW-F.9 2026-09-17] Operator field can be
    overridden or cleared."""
    base = LossToleranceConfig(
        loss_tolerance_pct=25.0, max_drawdown_pct=15.0,
        min_win_rate_pct=50.0, max_consecutive_losses=5,
        min_live_bankroll_inr=1500.0, operator="base",
    )
    merged = merge_loss_tolerance(base, {"operator": "ops-1"})
    assert merged.operator == "ops-1"


def test_merge_clears_operator_with_null():
    base = LossToleranceConfig(
        loss_tolerance_pct=25.0, max_drawdown_pct=15.0,
        min_win_rate_pct=50.0, max_consecutive_losses=5,
        min_live_bankroll_inr=1500.0, operator="base",
    )
    merged = merge_loss_tolerance(base, {"operator": None})
    assert merged.operator is None


def test_merge_rejects_invalid_override():
    base = LossToleranceConfig(
        loss_tolerance_pct=25.0, max_drawdown_pct=15.0,
        min_win_rate_pct=50.0, max_consecutive_losses=5,
        min_live_bankroll_inr=1500.0, operator="base",
    )
    with pytest.raises(ValueError):
        merge_loss_tolerance(base, {"loss_tolerance_pct": -1})


def test_merge_with_empty_override_keeps_base():
    """[WORKFLOW-F.9 2026-09-17] Empty override is a
    no-op; the merged config equals the base."""
    base = LossToleranceConfig(
        loss_tolerance_pct=25.0, max_drawdown_pct=15.0,
        min_win_rate_pct=50.0, max_consecutive_losses=5,
        min_live_bankroll_inr=1500.0, operator="base",
    )
    merged = merge_loss_tolerance(base, {})
    assert merged.to_dict() == base.to_dict()


# -- 7. LossToleranceConfig dataclass ----------------------


def test_to_dict_includes_all_fields():
    cfg = LossToleranceConfig(
        loss_tolerance_pct=25.0, max_drawdown_pct=15.0,
        min_win_rate_pct=50.0, max_consecutive_losses=5,
        min_live_bankroll_inr=1500.0, operator="urveesh",
    )
    d = cfg.to_dict()
    expected = {"loss_tolerance_pct", "max_drawdown_pct",
                "min_win_rate_pct", "max_consecutive_losses",
                "min_live_bankroll_inr", "operator"}
    assert set(d.keys()) == expected


def test_to_dict_with_no_operator_returns_none():
    cfg = LossToleranceConfig(
        loss_tolerance_pct=25.0, max_drawdown_pct=15.0,
        min_win_rate_pct=50.0, max_consecutive_losses=5,
        min_live_bankroll_inr=1500.0,
    )
    d = cfg.to_dict()
    assert d["operator"] is None
