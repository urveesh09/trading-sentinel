"""[WORKFLOW-E.3 2026-09-17] Tests for the hedge interpretation
helper.

Per Workstream E in NEXT_AGENT_PLAN.md:
> Hedge-first must have an explicit interpretation.
> Conditional protection states the exposure assumption and
> coverage; market directional spreads are not automatically
> personalized hedges. Ask for exposure details only if
> personalized protection is requested. Do not describe an
> unconfirmed action as taken/closed.

These tests pin the classification rules: a hedge message
must be classified as PERSONALIZED_PROTECTION (a real hedge
of an existing position) or DIRECTIONAL_SPREAD (a market
view expressed as an option spread) or UNCLEAR (the partner
must ask before acting).
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "interpret_hedge_message.py"
WORKDIR = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS_DIR))

from interpret_hedge_message import (  # noqa: E402  -- import path
    Interpretation,
    InterpretationFinding,
    finding_as_dict,
    format_report,
    interpret_hedge,
)


# -- 1. Personalized protection strategies -----------------------


def test_protective_put_with_full_ratio_is_personalized():
    f = interpret_hedge({
        "strategy": "ProtectivePutPlan",
        "covered_units": 1,
        "hedge_ratio": 1.0,
    })
    assert f.interpretation == Interpretation.PERSONALIZED_PROTECTION
    assert f.hedge_ratio == 1.0
    assert f.covered_units == 1


def test_protective_put_with_zero_ratio_is_directional_spread():
    """[WORKFLOW-E.3 2026-09-17] hedge_ratio=0 means the
    protection has no effect. Treat as directional spread."""
    f = interpret_hedge({
        "strategy": "ProtectivePutPlan",
        "hedge_ratio": 0.0,
    })
    assert f.interpretation == Interpretation.DIRECTIONAL_SPREAD
    assert "hedge_ratio is 0.0" in f.reason


def test_collar_plan_is_personalized_protection():
    f = interpret_hedge({
        "strategy": "CollarPlan",
        "covered_units": 2,
        "hedge_ratio": 1.0,
    })
    assert f.interpretation == Interpretation.PERSONALIZED_PROTECTION


def test_covered_call_is_personalized_protection():
    f = interpret_hedge({
        "strategy": "CoveredCallPlan",
        "covered_units": 1,
    })
    assert f.interpretation == Interpretation.PERSONALIZED_PROTECTION


def test_snake_case_personal_protection_strategy():
    """Plan names can be snake_case too (``collar``)."""
    f = interpret_hedge({"strategy": "collar"})
    assert f.interpretation == Interpretation.PERSONALIZED_PROTECTION


def test_personalized_protection_missing_units_surfaces_in_missing_fields():
    f = interpret_hedge({
        "strategy": "ProtectivePutPlan",
        "hedge_ratio": 1.0,
    })
    assert f.interpretation == Interpretation.PERSONALIZED_PROTECTION
    assert "covered_units OR protected_units" in f.missing_fields


# -- 2. Directional spread strategies ----------------------------


def test_bull_put_spread_is_directional():
    f = interpret_hedge({"strategy": "BullPutSpreadPlan"})
    assert f.interpretation == Interpretation.DIRECTIONAL_SPREAD


def test_bear_call_spread_is_directional():
    f = interpret_hedge({"strategy": "BearCallSpreadPlan"})
    assert f.interpretation == Interpretation.DIRECTIONAL_SPREAD


def test_iron_condor_is_directional():
    f = interpret_hedge({"strategy": "IronCondorPlan"})
    assert f.interpretation == Interpretation.DIRECTIONAL_SPREAD


def test_long_straddle_is_directional():
    f = interpret_hedge({"strategy": "LongStraddlePlan"})
    assert f.interpretation == Interpretation.DIRECTIONAL_SPREAD


def test_directional_spread_with_hedge_ratio_above_zero_is_unclear():
    """[WORKFLOW-E.3 2026-09-17] A directional spread with
    hedge_ratio > 0 is suspicious: spreads express a view,
    not a hedge. The partner must clarify."""
    f = interpret_hedge({
        "strategy": "BullPutSpreadPlan",
        "hedge_ratio": 0.5,
    })
    assert f.interpretation == Interpretation.UNCLEAR
    assert "directional spread" in f.reason


# -- 3. UNCLEAR cases -------------------------------------------


def test_empty_strategy_is_unclear():
    f = interpret_hedge({})
    assert f.interpretation == Interpretation.UNCLEAR
    assert "strategy" in f.missing_fields


def test_unknown_strategy_is_unclear():
    f = interpret_hedge({"strategy": "MagicHedgePlan"})
    assert f.interpretation == Interpretation.UNCLEAR
    assert "unrecognized" in f.reason or "empty" in f.reason.lower()


def test_non_dict_message_is_unclear_with_blocker():
    f = interpret_hedge("not a dict")  # type: ignore[arg-type]
    assert f.interpretation == Interpretation.UNCLEAR
    assert "not a dict" in f.reason


# -- 4. Snake_case + PascalCase mixed -----------------------------


def test_snake_case_directional_strategy():
    f = interpret_hedge({"strategy": "iron_condor"})
    assert f.interpretation == Interpretation.DIRECTIONAL_SPREAD


# -- 5. Field path resolution (nested keys) ---------------------


def test_nested_strategy_path_resolves():
    f = interpret_hedge({"advisory": {"strategy": "CollarPlan"}})
    assert f.interpretation == Interpretation.PERSONALIZED_PROTECTION
    assert "strategy" in f.evidence_paths


def test_kind_field_used_as_fallback():
    f = interpret_hedge({"kind": "ProtectivePutPlan"})
    assert f.interpretation == Interpretation.PERSONALIZED_PROTECTION


def test_held_units_field_used_as_fallback_for_covered():
    f = interpret_hedge({
        "strategy": "ProtectivePutPlan",
        "held_units": 1,
        "hedge_ratio": 1.0,
    })
    assert f.interpretation == Interpretation.PERSONALIZED_PROTECTION
    assert f.covered_units == 1


# -- 6. JSON serialization ---------------------------------------


def test_finding_as_dict_includes_all_fields():
    f = interpret_hedge({
        "strategy": "ProtectivePutPlan",
        "hedge_ratio": 1.0,
        "covered_units": 1,
    })
    serialized = finding_as_dict(f)
    assert set(serialized.keys()) == {
        "interpretation",
        "strategy",
        "hedge_ratio",
        "covered_units",
        "protected_units",
        "reason",
        "evidence_paths",
        "missing_fields",
    }
    assert serialized["interpretation"] == "PERSONALIZED_PROTECTION"


def test_format_report_renders_human_readable_text():
    f = interpret_hedge({"strategy": "CollarPlan"})
    text = format_report(f)
    assert "Hedge interpretation" in text
    assert "PERSONALIZED_PROTECTION" in text
    assert "CollarPlan" in text


# -- 7. CLI integration via subprocess --------------------------


def _run_cli(card_path: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH), str(card_path)],
        cwd=str(WORKDIR),
        capture_output=True, text=True, timeout=15,
    )


def test_cli_personalized_protection_returns_exit_zero(tmp_path):
    card_path = tmp_path / "hedge.json"
    card_path.write_text(
        json.dumps({
            "strategy": "ProtectivePutPlan",
            "covered_units": 1,
            "hedge_ratio": 1.0,
        }),
        encoding="utf-8",
    )
    result = _run_cli(card_path)
    assert result.returncode == 0
    assert "PERSONALIZED_PROTECTION" in result.stdout


def test_cli_directional_spread_returns_exit_zero(tmp_path):
    card_path = tmp_path / "hedge.json"
    card_path.write_text(
        json.dumps({"strategy": "BullPutSpreadPlan"}),
        encoding="utf-8",
    )
    result = _run_cli(card_path)
    assert result.returncode == 0
    assert "DIRECTIONAL_SPREAD" in result.stdout


def test_cli_unclear_returns_exit_two(tmp_path):
    card_path = tmp_path / "hedge.json"
    card_path.write_text(json.dumps({}), encoding="utf-8")
    result = _run_cli(card_path)
    assert result.returncode == 2
    assert "UNCLEAR" in result.stdout


def test_cli_missing_file_returns_exit_two(tmp_path):
    bogus = tmp_path / "does_not_exist.json"
    result = _run_cli(bogus)
    assert result.returncode == 2


def test_cli_json_flag_emits_valid_json(tmp_path):
    card_path = tmp_path / "hedge.json"
    card_path.write_text(
        json.dumps({"strategy": "CollarPlan"}),
        encoding="utf-8",
    )
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), str(card_path), "--json"],
        cwd=str(WORKDIR),
        capture_output=True, text=True, timeout=15,
    )
    assert result.returncode == 0
    parsed = json.loads(result.stdout)
    assert parsed["interpretation"] == "PERSONALIZED_PROTECTION"
