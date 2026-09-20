"""[WORKFLOW-ITEMS-5/6/9 2026-09-20] Proactive source verifier tests.

Pins the audit's item-5 acceptance: the ``KITE_COMPLETED_BARS_V1``
configuration must be verified BEFORE the broker call. Each
required field surfaces a stable reason code.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest


PYTHON_ENGINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PYTHON_ENGINE))


from proactive_source_verifier import (  # noqa: E402
    ConfigVerdict,
    SourceConfigReason,
    verify_kite_completed_bar_config,
)


class _StubSettings:
    """Minimal settings stub for the verifier.

    Only the fields the verifier reads are exposed; everything
    else is left as ``None`` (the verifier uses ``getattr(..., "")``
    or numeric defaults so unknown attributes never raise).
    """
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)


def _full_settings() -> _StubSettings:
    """Fully configured settings the verifier accepts."""
    return _StubSettings(
        PROACTIVE_SHADOW_RUN_ID="research-run-2026-09-20",
        PROACTIVE_SHADOW_KITE_TOKENS_JSON='{"NIFTY": {"token": 256265}}',
        PROACTIVE_SHADOW_SCENARIO_CAPITAL=250000.0,
        PROACTIVE_SHADOW_MAX_DATA_AGE_SECONDS=300,
        RESEARCH_ARCHIVE_PATH="/data/research",
    )


# -- Audit acceptance: each missing field surfaces a stable code -


def test_missing_run_id_reports_missing_run_id():
    s = _full_settings()
    s.PROACTIVE_SHADOW_RUN_ID = ""
    verdict = verify_kite_completed_bar_config(s)
    assert not verdict.ok
    assert SourceConfigReason.MISSING_RUN_ID in verdict.reasons


def test_missing_tokens_json_reports_missing_tokens_json():
    s = _full_settings()
    s.PROACTIVE_SHADOW_KITE_TOKENS_JSON = ""
    verdict = verify_kite_completed_bar_config(s)
    assert not verdict.ok
    assert SourceConfigReason.MISSING_TOKENS_JSON in verdict.reasons


def test_invalid_tokens_shape_reports_invalid_tokens_shape():
    s = _full_settings()
    s.PROACTIVE_SHADOW_KITE_TOKENS_JSON = "[]"
    verdict = verify_kite_completed_bar_config(s)
    assert not verdict.ok
    assert SourceConfigReason.INVALID_TOKENS_SHAPE in verdict.reasons


def test_invalid_tokens_shape_on_empty_dict():
    s = _full_settings()
    s.PROACTIVE_SHADOW_KITE_TOKENS_JSON = "{}"
    verdict = verify_kite_completed_bar_config(s)
    assert not verdict.ok
    assert SourceConfigReason.INVALID_TOKENS_SHAPE in verdict.reasons


def test_invalid_capital_reports_invalid_capital():
    s = _full_settings()
    s.PROACTIVE_SHADOW_SCENARIO_CAPITAL = 0
    verdict = verify_kite_completed_bar_config(s)
    assert not verdict.ok
    assert SourceConfigReason.INVALID_CAPITAL in verdict.reasons


def test_invalid_capital_negative_reports_invalid_capital():
    s = _full_settings()
    s.PROACTIVE_SHADOW_SCENARIO_CAPITAL = -100
    verdict = verify_kite_completed_bar_config(s)
    assert not verdict.ok
    assert SourceConfigReason.INVALID_CAPITAL in verdict.reasons


def test_invalid_max_age_too_large_reports_invalid_max_age():
    s = _full_settings()
    s.PROACTIVE_SHADOW_MAX_DATA_AGE_SECONDS = 100_000
    verdict = verify_kite_completed_bar_config(s)
    assert not verdict.ok
    assert SourceConfigReason.INVALID_MAX_AGE in verdict.reasons


def test_invalid_max_age_zero_reports_invalid_max_age():
    s = _full_settings()
    s.PROACTIVE_SHADOW_MAX_DATA_AGE_SECONDS = 0
    verdict = verify_kite_completed_bar_config(s)
    assert not verdict.ok
    assert SourceConfigReason.INVALID_MAX_AGE in verdict.reasons


def test_missing_archive_path_reports_missing_archive_path():
    s = _full_settings()
    s.RESEARCH_ARCHIVE_PATH = ""
    verdict = verify_kite_completed_bar_config(s)
    assert not verdict.ok
    assert SourceConfigReason.MISSING_ARCHIVE_PATH in verdict.reasons


# -- Audit acceptance: a fully-configured deployment passes --


def test_fully_configured_settings_pass():
    verdict = verify_kite_completed_bar_config(_full_settings())
    assert verdict.ok
    assert verdict.reasons == (SourceConfigReason.PASS,)


def test_default_max_age_is_accepted():
    """Missing max-age falls back to the documented default."""
    s = _full_settings()
    del s.PROACTIVE_SHADOW_MAX_DATA_AGE_SECONDS
    verdict = verify_kite_completed_bar_config(s)
    assert verdict.ok
    assert verdict.evidence["max_data_age_seconds"] == 300


def test_invalid_max_age_falls_back_to_default():
    """An unparseable max-age falls back to the documented default."""
    s = _full_settings()
    s.PROACTIVE_SHADOW_MAX_DATA_AGE_SECONDS = "not-a-number"
    verdict = verify_kite_completed_bar_config(s)
    assert verdict.ok


# -- Evidence surface ----------------------------------------------


def test_evidence_dict_exposes_each_field():
    verdict = verify_kite_completed_bar_config(_full_settings())
    assert "run_id" in verdict.evidence
    assert "tokens_json" in verdict.evidence
    assert "scenario_capital" in verdict.evidence
    assert "max_data_age_seconds" in verdict.evidence
    assert "research_archive_path" in verdict.evidence
    assert verdict.evidence["parsed_tokens_keys"] == ["NIFTY"]


def test_verdict_to_dict_round_trip():
    verdict = verify_kite_completed_bar_config(_full_settings())
    payload = verdict.to_dict()
    assert payload["ok"] is True
    assert payload["reasons"] == ["pass"]


def test_multiple_reasons_reported():
    """Two simultaneous misconfigurations surface two reason codes."""
    s = _full_settings()
    s.PROACTIVE_SHADOW_RUN_ID = ""
    s.PROACTIVE_SHADOW_KITE_TOKENS_JSON = ""
    verdict = verify_kite_completed_bar_config(s)
    assert SourceConfigReason.MISSING_RUN_ID in verdict.reasons
    assert SourceConfigReason.MISSING_TOKENS_JSON in verdict.reasons
    assert SourceConfigReason.MISSING_ARCHIVE_PATH not in verdict.reasons
    assert not verdict.ok
