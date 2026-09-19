"""[WORKFLOW-F.9 2026-09-17] Capital-increase loss-tolerance loader.

Per Workstream F in NEXT_AGENT_PLAN.md:
> Establish capital-increase criteria from externally
> reconciled net results, drawdown, execution quality and
> operational stability. Leave the user's loss tolerance
> as an explicit input if not supplied.

This module complements the existing
``python-engine.capital_policy`` (and its CLI). The base
policy reads ``LOSS_TOLERANCE_PCT`` from settings. This
module adds:

  - ``load_loss_tolerance(input_path)`` -- reads an explicit
    loss-tolerance from a JSON file supplied by the user.
    Format::

        {
          "loss_tolerance_pct": 25.0,
          "max_drawdown_pct": 15.0,
          "min_win_rate_pct": 50.0,
          "max_consecutive_losses": 5,
          "min_live_bankroll_inr": 1500.0,
          "operator": "urveesh"
        }

  - ``LossToleranceConfig`` -- a dataclass with the
    validated values.
  - ``merge_loss_tolerance(base_config, operator_config)``
    -- merges operator-supplied overrides into the base
    policy. The base config keeps its values; the operator
    config overrides only the fields it explicitly provides.

The plan: "Leave the user's loss tolerance as an explicit
input if not supplied." So this module is a read-only
loader -- it doesn't write any state. The operator decides
when to apply the override (typically at the
capital-policy-gate decision point).

Pure function. No I/O. No DB. No clock injection.
"""
from __future__ import annotations

import dataclasses
import enum
import json
import math
from pathlib import Path
from typing import Any, Mapping, Optional


class LossToleranceField(str, enum.Enum):
    """The fields the operator can override."""
    LOSS_TOLERANCE_PCT = "loss_tolerance_pct"
    MAX_DRAWDOWN_PCT = "max_drawdown_pct"
    MIN_WIN_RATE_PCT = "min_win_rate_pct"
    MAX_CONSECUTIVE_LOSSES = "max_consecutive_losses"
    MIN_LIVE_BANKROLL_INR = "min_live_bankroll_inr"


# All fields are required to be present + valid.
_REQUIRED_FIELDS: tuple[str, ...] = (
    "loss_tolerance_pct",
    "max_drawdown_pct",
    "min_win_rate_pct",
    "max_consecutive_losses",
    "min_live_bankroll_inr",
)


@dataclasses.dataclass(frozen=True)
class LossToleranceConfig:
    """An operator-supplied loss-tolerance override."""
    loss_tolerance_pct: float
    max_drawdown_pct: float
    min_win_rate_pct: float
    max_consecutive_losses: int
    min_live_bankroll_inr: float
    operator: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "loss_tolerance_pct": self.loss_tolerance_pct,
            "max_drawdown_pct": self.max_drawdown_pct,
            "min_win_rate_pct": self.min_win_rate_pct,
            "max_consecutive_losses": self.max_consecutive_losses,
            "min_live_bankroll_inr": self.min_live_bankroll_inr,
            "operator": self.operator,
        }


def _validate_field(name: str, value: Any) -> Any:
    """Validate a single field. Returns the cleaned value or
    raises ``ValueError`` with a descriptive message."""
    if value is None:
        raise ValueError(f"{name} is required (cannot be null)")
    if name in ("loss_tolerance_pct", "max_drawdown_pct",
                  "min_win_rate_pct"):
        try:
            result = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"{name} must be a number"
            ) from exc
        if not math.isfinite(result):
            raise ValueError(f"{name} must be finite")
        if result < 0 or result > 100:
            raise ValueError(
                f"{name} must be between 0 and 100 (got {result})"
            )
        return result
    if name == "max_consecutive_losses":
        try:
            result = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"{name} must be an integer"
            ) from exc
        if result < 0:
            raise ValueError(
                f"{name} must be >= 0 (got {result})"
            )
        return result
    if name == "min_live_bankroll_inr":
        try:
            result = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"{name} must be a number"
            ) from exc
        if not math.isfinite(result) or result < 0:
            raise ValueError(
                f"{name} must be a finite non-negative number"
            )
        return result
    raise ValueError(f"unknown field: {name}")


def load_loss_tolerance(
    input_path: str | Path,
    *,
    from_stdin: bool = False,
) -> LossToleranceConfig:
    """Load an operator-supplied loss-tolerance config.

    Args:
        input_path: path to a JSON file, or ``-`` for
            stdin (when ``from_stdin=True``).
        from_stdin: when True, read the JSON from stdin
            instead of the file. The ``input_path`` arg is
            ignored in that case.

    Returns:
        A ``LossToleranceConfig`` with validated values.

    Raises:
        FileNotFoundError: when the file doesn't exist.
        ValueError: when the JSON is malformed, missing
            required fields, or has invalid values.
    """
    if from_stdin:
        import sys
        data = json.loads(sys.stdin.read())
    else:
        path = Path(input_path)
        if not path.is_file():
            raise FileNotFoundError(f"input file not found: {path}")
        data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, Mapping):
        raise ValueError("loss-tolerance config must be a JSON object")

    missing = [f for f in _REQUIRED_FIELDS if f not in data]
    if missing:
        raise ValueError(
            f"loss-tolerance config missing fields: {missing}"
        )

    cleaned = {
        field: _validate_field(field, data[field])
        for field in _REQUIRED_FIELDS
    }
    operator = data.get("operator")
    if operator is not None and not isinstance(operator, str):
        raise ValueError("operator, if present, must be a string")

    return LossToleranceConfig(
        loss_tolerance_pct=cleaned["loss_tolerance_pct"],
        max_drawdown_pct=cleaned["max_drawdown_pct"],
        min_win_rate_pct=cleaned["min_win_rate_pct"],
        max_consecutive_losses=cleaned["max_consecutive_losses"],
        min_live_bankroll_inr=cleaned["min_live_bankroll_inr"],
        operator=operator,
    )


def merge_loss_tolerance(
    base_config: LossToleranceConfig,
    override: Mapping[str, Any],
) -> LossToleranceConfig:
    """Merge an operator override into a base config.

    The override is a dict (typically loaded from
    ``load_loss_tolerance`` and then mutated). Only fields
    explicitly present in the override are merged; missing
    fields keep the base value. This lets operators
    override individual thresholds without re-stating
    everything.

    Raises:
        ValueError: when an override value is invalid.
    """
    base = base_config.to_dict()
    for field in _REQUIRED_FIELDS:
        if field in override:
            cleaned = _validate_field(field, override[field])
            base[field] = cleaned
    # Operator field is special: any string override is
    # accepted (or cleared if None).
    if "operator" in override:
        op = override["operator"]
        if op is not None and not isinstance(op, str):
            raise ValueError("operator, if present, must be a string")
        base["operator"] = op
    return LossToleranceConfig(**base)


__all__ = [
    "LossToleranceConfig",
    "LossToleranceField",
    "load_loss_tolerance",
    "merge_loss_tolerance",
]
