"""[WORKFLOW-E.2 2026-09-17] Tests for the partner card validator.

Per Workstream E in NEXT_AGENT_PLAN.md:
> Improve cards around decisions a manual trader can take:
> index/exchange, timestamp/validity, setup rationale, entry
> trigger and bounded price, exact contract legs/expiry/lot,
> total debit and modeled costs, maximum defined loss,
> invalidation/target and intraday deadline. Explain
> uncertainty and liquidity limits without overwhelming the
> message.

These tests pin the validator's contract. Each test is a
small case that exercises one rule.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

# We import the script as a module (so we can drive it
# programmatically) and also drive the CLI via subprocess for
# exit-code coverage.
SCRIPT_PATH = Path(__file__).resolve().parents[1] / "validate_partner_card.py"
WORKDIR = Path(__file__).resolve().parents[2]
# Make `from validate_partner_card import ...` resolve by
# adding scripts/ to sys.path (the script lives there).
SCRIPTS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS_DIR))

from validate_partner_card import (  # noqa: E402  -- import path
    Status,
    findings_as_dicts,
    format_report,
    validate_card,
)


def _base_card() -> dict:
    """Minimum valid MARKET_SETUP card."""
    return {
        "scope": "MARKET_SETUP",
        "underlying": "NIFTY",
        "exchange": "NSE",
        "policy_version": "v1",
        "evidence": "QUALIFIED_FOR_ADVISORY",
        "thesis_id": "t1",
        "quote_time": "2026-09-17T09:30:00+05:30",
        "valid_until": "2026-09-17T15:30:00+05:30",
        "why_now": ["ORB broke above opening range"],
        "uncertainty": "liquidity uncertain",
        "invalidation": "below opening low",
        "management": "exit at target",
        "holding_horizon": "INTRADAY",
        "management_deadline": "2026-09-17T15:15:00+05:30",
        "net_debit_rs": 150.0,
        "max_loss_rs": 150.0,
        "breakevens": [24150.0],
        "trigger_level": 24100.0,
        "invalidation_level": 24000.0,
        "target_level": 24300.0,
        "estimated_round_trip_cost_rs": 5.0,
        "legs": [
            {"side": "BUY", "ratio": 1, "lot_size": 75,
             "expiry": "2026-09-26", "option_type": "CE", "strike": 24100,
             "tradingsymbol": "NIFTY24100CE",
             "bid": 100, "ask": 105,
             "bid_quantity": 100, "ask_quantity": 50},
            {"side": "SELL", "ratio": 1, "lot_size": 75,
             "expiry": "2026-09-26", "option_type": "CE", "strike": 24200,
             "tradingsymbol": "NIFTY24200CE",
             "bid": 50, "ask": 55,
             "bid_quantity": 100, "ask_quantity": 50},
        ],
    }


# -- 1. Happy path -----------------------------------------------


def test_valid_market_setup_card_passes_with_zero_findings():
    """A fully-specified MARKET_SETUP card should produce zero findings."""
    findings = validate_card(_base_card())
    assert findings == [], (
        "expected no findings for a complete card, got: "
        f"{[f.field + ':' + f.message for f in findings]}"
    )


# -- 2. Missing required fields -----------------------------------


def test_missing_quote_time_is_a_fail():
    card = _base_card()
    card.pop("quote_time")
    findings = validate_card(card)
    fail_messages = [f for f in findings if f.status == Status.FAIL]
    assert any(f.field == "quote_time" for f in fail_messages), (
        f"expected quote_time to fail; got: "
        f"{[f.field + ':' + f.message for f in fail_messages]}"
    )


def test_missing_all_required_fields_yields_one_fail_per_field():
    card = {"scope": "MARKET_SETUP"}
    findings = validate_card(card)
    fail_messages = [f for f in findings if f.status == Status.FAIL]
    # We need at least 17 failures: 14 common required + 3 MARKET_SETUP.
    assert len(fail_messages) >= 17, (
        f"expected >= 17 failures; got {len(fail_messages)}: "
        f"{[f.field for f in fail_messages]}"
    )


def test_empty_why_now_list_is_a_fail():
    card = _base_card()
    card["why_now"] = []
    findings = validate_card(card)
    fail_messages = [f for f in findings if f.status == Status.FAIL]
    assert any(f.field == "why_now" for f in fail_messages), (
        f"expected why_now empty-list fail; got: "
        f"{[f.field for f in fail_messages]}"
    )


def test_blank_uncertainty_string_is_a_fail():
    card = _base_card()
    card["uncertainty"] = "   "
    findings = validate_card(card)
    fail_messages = [f for f in findings if f.status == Status.FAIL]
    assert any(f.field == "uncertainty" for f in fail_messages), (
        f"expected uncertainty empty-string fail; got: "
        f"{[f.field for f in fail_messages]}"
    )


# -- 3. Type / format errors --------------------------------------


def test_max_loss_rs_wrong_type_is_a_fail():
    card = _base_card()
    card["max_loss_rs"] = "fifty"
    findings = validate_card(card)
    fail_messages = [f for f in findings if f.status == Status.FAIL]
    assert any(
        f.field == "max_loss_rs" and "wrong type" in f.message
        for f in fail_messages
    )


def test_iso_datetime_validation_rejects_bad_string():
    card = _base_card()
    card["quote_time"] = "today"
    findings = validate_card(card)
    fail_messages = [f for f in findings if f.status == Status.FAIL]
    assert any(
        f.field == "quote_time" and "ISO 8601" in f.message
        for f in fail_messages
    )


def test_valid_until_must_be_after_quote_time():
    card = _base_card()
    card["quote_time"] = "2026-09-17T15:30:00+05:30"
    card["valid_until"] = "2026-09-17T09:30:00+05:30"
    findings = validate_card(card)
    fail_messages = [f for f in findings if f.status == Status.FAIL]
    assert any(
        f.field == "valid_until" and "after" in f.message
        for f in fail_messages
    )


def test_valid_until_equal_to_quote_time_is_a_fail():
    """[WORKFLOW-E.2 2026-09-17] The plan says 'validity' must
    be AFTER the quote time. Equal timestamps imply zero
    validity window -- invalid."""
    card = _base_card()
    card["quote_time"] = "2026-09-17T09:30:00+05:30"
    card["valid_until"] = "2026-09-17T09:30:00+05:30"
    findings = validate_card(card)
    fail_messages = [f for f in findings if f.status == Status.FAIL]
    assert any(f.field == "valid_until" for f in fail_messages)


def test_unknown_scope_is_a_fail():
    card = _base_card()
    card["scope"] = "INVALID_SCOPE"
    findings = validate_card(card)
    fail_messages = [f for f in findings if f.status == Status.FAIL]
    assert any(
        f.field == "scope" and "unknown scope" in f.message
        for f in fail_messages
    )


def test_unknown_evidence_is_a_fail():
    card = _base_card()
    card["evidence"] = "SOME_GIBBERISH"
    findings = validate_card(card)
    fail_messages = [f for f in findings if f.status == Status.FAIL]
    assert any(
        f.field == "evidence" and "unknown evidence" in f.message
        for f in fail_messages
    )


# -- 4. Per-leg validation ----------------------------------------


def test_leg_with_wrong_side_is_a_fail():
    card = _base_card()
    card["legs"][0]["side"] = "WRONG"
    findings = validate_card(card)
    fail_messages = [f for f in findings if f.status == Status.FAIL]
    assert any(
        f.field == "legs[0].side" and "side is not BUY" in f.message
        for f in fail_messages
    )


def test_leg_with_zero_ratio_is_a_fail():
    card = _base_card()
    card["legs"][1]["ratio"] = 0
    findings = validate_card(card)
    fail_messages = [f for f in findings if f.status == Status.FAIL]
    assert any(
        f.field == "legs[1].ratio" and "ratio must be" in f.message
        for f in fail_messages
    )


def test_leg_with_bad_expiry_is_a_fail():
    card = _base_card()
    card["legs"][0]["expiry"] = "2026-13-99"  # Not a real date.
    findings = validate_card(card)
    fail_messages = [f for f in findings if f.status == Status.FAIL]
    assert any(
        f.field == "legs[0].expiry" and "expiry must be" in f.message
        for f in fail_messages
    )


def test_leg_without_liquidity_data_emits_a_warn():
    """[WORKFLOW-E.2 2026-09-17] The plan says 'explain
    uncertainty and liquidity limits without overwhelming
    the message.' A missing bid/ask quantity should WARN."""
    card = _base_card()
    card["legs"][0].pop("bid_quantity", None)
    card["legs"][0].pop("ask_quantity", None)
    findings = validate_card(card)
    warns = [f for f in findings if f.status == Status.WARN]
    assert any(
        f.field == "legs[0].liquidity_limit" for f in warns
    ), f"expected liquidity WARN; got: {[f.field for f in warns]}"


# -- 5. Economics invariants --------------------------------------


def test_negative_net_debit_is_a_fail():
    card = _base_card()
    card["net_debit_rs"] = -100
    findings = validate_card(card)
    fail_messages = [f for f in findings if f.status == Status.FAIL]
    assert any(
        f.field == "net_debit_rs" and "must be positive" in f.message
        for f in fail_messages
    )


def test_zero_net_debit_is_a_fail():
    card = _base_card()
    card["net_debit_rs"] = 0
    findings = validate_card(card)
    fail_messages = [f for f in findings if f.status == Status.FAIL]
    assert any(
        f.field == "net_debit_rs" and "must be positive" in f.message
        for f in fail_messages
    )


# -- 6. CONDITIONAL_PROTECTION scope-specific checks --------------


def test_conditional_protection_requires_exposure_assumption():
    card = _base_card()
    card["scope"] = "CONDITIONAL_PROTECTION"
    # Drop the MARKET_SETUP-required fields, add CP-specific.
    for f in ("net_debit_rs", "breakevens", "trigger_level",
              "invalidation_level", "target_level",
              "estimated_round_trip_cost_rs"):
        card.pop(f, None)
    card["exposure_assumption"] = "owner holds 1 lot of NIFTY long"
    card["coverage_units"] = 1
    findings = validate_card(card)
    # No FAIL about exposure_assumption: it's present and
    # contains a personalization marker.
    fail_messages = [f for f in findings if f.status == Status.FAIL]
    assert not any(
        f.field == "exposure_assumption" for f in fail_messages
    ), f"expected no fail on exposure_assumption; got: "
    f"{[f.field for f in fail_messages]}"


def test_conditional_protection_with_vague_exposure_emits_warn():
    """[WORKFLOW-E.2 2026-09-17] Hedge-first must have an
    explicit interpretation: personalized vs generic."""
    card = _base_card()
    card["scope"] = "CONDITIONAL_PROTECTION"
    for f in ("net_debit_rs", "breakevens", "trigger_level",
              "invalidation_level", "target_level",
              "estimated_round_trip_cost_rs"):
        card.pop(f, None)
    card["exposure_assumption"] = "the operator has some position"
    card["coverage_units"] = 1
    findings = validate_card(card)
    warns = [f for f in findings if f.status == Status.WARN]
    assert any(
        f.field == "exposure_assumption" for f in warns
    ), f"expected hedge-interpretation WARN; got: {[f.field for f in warns]}"


def test_conditional_protection_with_personalized_marker_passes_clean():
    card = _base_card()
    card["scope"] = "CONDITIONAL_PROTECTION"
    for f in ("net_debit_rs", "breakevens", "trigger_level",
              "invalidation_level", "target_level",
              "estimated_round_trip_cost_rs"):
        card.pop(f, None)
    card["exposure_assumption"] = "owner holds 2 lots of NIFTY long"
    card["coverage_units"] = 2
    findings = validate_card(card)
    fail_messages = [f for f in findings if f.status == Status.FAIL]
    warn_messages = [f for f in findings if f.status == Status.WARN]
    assert not any(
        f.field == "exposure_assumption" for f in fail_messages + warn_messages
    )


def test_conditional_protection_with_generic_marker_passes_clean():
    card = _base_card()
    card["scope"] = "CONDITIONAL_PROTECTION"
    for f in ("net_debit_rs", "breakevens", "trigger_level",
              "invalidation_level", "target_level",
              "estimated_round_trip_cost_rs"):
        card.pop(f, None)
    card["exposure_assumption"] = "this is a generic market-view protection"
    card["coverage_units"] = 1
    findings = validate_card(card)
    fail_messages = [f for f in findings if f.status == Status.FAIL]
    warn_messages = [f for f in findings if f.status == Status.WARN]
    assert not any(
        f.field == "exposure_assumption" for f in fail_messages + warn_messages
    )


# -- 7. JSON serialization ----------------------------------------


def test_findings_as_dicts_emits_machine_readable_shape():
    card = _base_card()
    card["net_debit_rs"] = -50
    findings = validate_card(card)
    serialized = findings_as_dicts(findings)
    assert isinstance(serialized, list)
    if serialized:
        item = serialized[0]
        assert set(item.keys()) == {"field", "status", "message", "expected"}
        assert item["status"] in {"PASS", "WARN", "FAIL", "BLOCKER"}


def test_format_report_renders_human_readable_text():
    card = _base_card()
    card.pop("quote_time")
    findings = validate_card(card)
    text = format_report(findings)
    assert "Partner card validation" in text
    assert "[FAIL]" in text
    assert "quote_time" in text


# -- 8. CLI integration via subprocess ----------------------------


def _run_cli(card_path: Path) -> subprocess.CompletedProcess:
    """Run the validator as a CLI subprocess."""
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH), str(card_path)],
        cwd=str(WORKDIR),
        capture_output=True, text=True, timeout=15,
    )


def test_cli_passes_valid_card_with_exit_zero(tmp_path):
    card_path = tmp_path / "card.json"
    card_path.write_text(json.dumps(_base_card()), encoding="utf-8")
    result = _run_cli(card_path)
    assert result.returncode == 0, (
        f"expected exit 0; got {result.returncode}\n"
        f"STDOUT: {result.stdout}\nSTDERR: {result.stderr}"
    )
    assert "All checks passed" in result.stdout


def test_cli_returns_exit_one_on_failures(tmp_path):
    card = _base_card()
    card.pop("quote_time")
    card_path = tmp_path / "card.json"
    card_path.write_text(json.dumps(card), encoding="utf-8")
    result = _run_cli(card_path)
    assert result.returncode == 1, (
        f"expected exit 1; got {result.returncode}\n"
        f"STDOUT: {result.stdout}\nSTDERR: {result.stderr}"
    )


def test_cli_returns_exit_two_on_missing_file(tmp_path):
    """BLOCKER-equivalent: input file doesn't exist."""
    bogus = tmp_path / "does_not_exist.json"
    result = _run_cli(bogus)
    assert result.returncode == 2, (
        f"expected exit 2; got {result.returncode}\n"
        f"STDOUT: {result.stdout}\nSTDERR: {result.stderr}"
    )


def test_cli_json_flag_emits_valid_json(tmp_path):
    card_path = tmp_path / "card.json"
    card_path.write_text(json.dumps(_base_card()), encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), str(card_path), "--json"],
        cwd=str(WORKDIR),
        capture_output=True, text=True, timeout=15,
    )
    assert result.returncode == 0
    parsed = json.loads(result.stdout)
    assert isinstance(parsed, list)
