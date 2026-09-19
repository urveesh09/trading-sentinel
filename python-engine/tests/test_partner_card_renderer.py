"""[WORKFLOW-E.4 2026-09-17] Tests for the partner card renderer.

Per Workstream E in NEXT_AGENT_PLAN.md:
> Improve cards around decisions a manual trader can take:
> index/exchange, timestamp/validity, setup rationale, entry
> trigger and bounded price, exact contract legs/expiry/lot,
> total debit and modeled costs, maximum defined loss,
> invalidation/target and intraday deadline. Explain
> uncertainty and liquidity limits without overwhelming the
> message.

These tests pin the renderer contract:
  - Required fields appear in the rendered text.
  - Per-scope pieces (MARKET_SETUP, CONDITIONAL_PROTECTION)
    are correctly differentiated.
  - Per-leg rendering (side/ratio/tradingsymbol/expiry/
    strike/option_type/lot/bid/ask).
  - Telegram size limit enforced.
  - validate_rendered_card catches missing pieces.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Add python-engine to sys.path so we can import the renderer.
PYTHON_ENGINE = Path(__file__).resolve().parents[2] / "python-engine"
sys.path.insert(0, str(PYTHON_ENGINE))

from partner_card_renderer import (  # noqa: E402  -- import path
    MAX_TELEGRAM_CHARS,
    CardRenderError,
    render_and_validate,
    render_card,
    validate_rendered_card,
)


def _base_card() -> dict:
    return {
        "scope": "MARKET_SETUP",
        "underlying": "NIFTY",
        "exchange": "NSE",
        "policy_version": "v1",
        "evidence": "QUALIFIED_FOR_ADVISORY",
        "thesis_id": "t1",
        "advisory_id": "abc123",
        "quote_time": "2026-09-17T09:30:00+05:30",
        "valid_until": "2026-09-17T15:30:00+05:30",
        "why_now": ["ORB broke above opening range"],
        "uncertainty": "liquidity uncertain",
        "invalidation": "below opening low",
        "management": "exit at target",
        "holding_horizon": "INTRADAY",
        "management_deadline": "2026-09-17T15:15:00+05:30",
        "direction": "LONG",
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
             "bid": 100, "ask": 105},
            {"side": "SELL", "ratio": 1, "lot_size": 75,
             "expiry": "2026-09-26", "option_type": "CE", "strike": 24200,
             "tradingsymbol": "NIFTY24200CE",
             "bid": 50, "ask": 55},
        ],
    }


# -- 1. Happy path -----------------------------------------------


def test_render_card_returns_non_empty_string():
    text = render_card(_base_card())
    assert isinstance(text, str)
    assert len(text) > 100


def test_render_card_contains_header_with_underlying_and_exchange():
    text = render_card(_base_card())
    assert "[MARKET SETUP]" in text
    assert "NIFTY" in text
    assert "NSE" in text


def test_render_card_contains_quote_time_and_valid_until():
    text = render_card(_base_card())
    assert "2026-09-17T09:30:00+05:30" in text
    assert "2026-09-17T15:30:00+05:30" in text
    assert "Data" in text
    assert "Valid until" in text


def test_render_card_contains_intraday_warning():
    text = render_card(_base_card())
    assert "INTRADAY ONLY" in text
    assert "Manual action only" in text


def test_render_card_contains_why_now():
    text = render_card(_base_card())
    assert "Why now: ORB broke above opening range" in text


def test_render_card_contains_each_leg_full_detail():
    text = render_card(_base_card())
    assert "BUY 1× NIFTY24100CE | 2026-09-26 24100CE | lot 75 | bid/ask 100/105" in text
    assert "SELL 1× NIFTY24200CE | 2026-09-26 24200CE | lot 75 | bid/ask 50/55" in text


def test_render_card_contains_net_debit_bounded_price():
    text = render_card(_base_card())
    assert "Act only if: combined debit ≤ ₹150.00 before fees" in text


def test_render_card_contains_max_loss_with_market_setup_label():
    text = render_card(_base_card())
    assert "Risk: theoretical maximum loss" in text
    assert "₹150.00" in text


def test_render_card_contains_breakevens():
    text = render_card(_base_card())
    assert "24,150.00" in text


def test_render_card_contains_entry_trigger_with_correct_comparator_for_long():
    """[WORKFLOW-E.4 2026-09-17] Direction=LONG -> 'above'."""
    text = render_card(_base_card())
    assert "Entry trigger: underlying confirms above 24,100.00" in text


def test_render_card_contains_invalidation_level_and_target_level():
    text = render_card(_base_card())
    assert "Thesis invalidation level: 24,000.00" in text
    assert "First profit-taking / review level: 24,300.00" in text


def test_render_card_contains_holding_horizon_and_deadline():
    text = render_card(_base_card())
    assert "Holding horizon: INTRADAY" in text
    assert "2026-09-17T15:15:00+05:30" in text


def test_render_card_contains_invalidation_management_uncertainty_evidence():
    text = render_card(_base_card())
    assert "Invalidation: below opening low" in text
    assert "Management: exit at target" in text
    assert "Uncertainty: liquidity uncertain" in text
    assert "Evidence: QUALIFIED_FOR_ADVISORY" in text


# -- 2. Per-scope differentiation --------------------------------


def test_render_card_short_direction_uses_below_comparator():
    card = _base_card()
    card["direction"] = "SHORT"
    text = render_card(card)
    assert "below 24,100.00" in text


def test_render_card_conditional_protection_uses_protection_premium_label():
    card = _base_card()
    card["scope"] = "CONDITIONAL_PROTECTION"
    card["coverage_units"] = 1
    card["exposure_assumption"] = "owner holds 1 lot of NIFTY long"
    card.pop("breakevens", None)  # breakevens not required for hedge
    text = render_card(card)
    assert "Protection premium at risk" in text
    assert "not the loss bound of an unknown protected position" in text
    assert "[CONDITIONAL PROTECTION]" in text
    assert "Coverage assumption: owner holds 1 lot of NIFTY long" in text


def test_render_card_conditional_protection_no_bounded_price():
    """[WORKFLOW-E.4 2026-09-17] CONDITIONAL_PROTECTION does
    not have a bounded entry debit/credit like MARKET_SETUP
    does -- it's a hedge, not an entry."""
    card = _base_card()
    card["scope"] = "CONDITIONAL_PROTECTION"
    card.pop("net_debit_rs", None)
    card.pop("breakevens", None)
    text = render_card(card)
    assert "Act only if: combined debit" not in text


# -- 3. Render-validator ----------------------------------------


def test_validate_rendered_card_passes_for_base_card():
    card = _base_card()
    text = render_card(card)
    failures = validate_rendered_card(text, card)
    assert failures == [], (
        "expected no failures for a complete card; got: "
        f"{failures}"
    )


def test_validate_rendered_card_flags_missing_intraday_warning():
    card = _base_card()
    text = render_card(card).replace("INTRADAY ONLY", "")
    failures = validate_rendered_card(text, card)
    assert any("intraday_warning" in f for f in failures)


def test_validate_rendered_card_flags_missing_legs():
    card = _base_card()
    text = render_card(card)
    # Remove all leg lines (any line containing "BUY " or "SELL "
    # followed by ratio + tradingsymbol).
    import re
    text = re.sub(r"^(BUY|SELL) .*\n?", "", text, flags=re.MULTILINE)
    failures = validate_rendered_card(text, card)
    assert any("leg[0]" in f for f in failures), (
        f"expected leg[0] missing; got: {failures}"
    )


def test_validate_rendered_card_flags_market_setup_without_bounded_price():
    card = _base_card()
    card["net_debit_rs"] = None
    card["net_credit_rs"] = None
    text = render_card(card)
    failures = validate_rendered_card(text, card)
    assert any("bounded price" in f for f in failures)


def test_validate_rendered_card_flags_market_setup_without_max_loss():
    card = _base_card()
    card["max_loss_rs"] = None
    text = render_card(card)
    failures = validate_rendered_card(text, card)
    assert any("max loss" in f for f in failures)


def test_validate_rendered_card_flags_conditional_protection_without_premium_line():
    card = _base_card()
    card["scope"] = "CONDITIONAL_PROTECTION"
    card["max_loss_rs"] = None
    text = render_card(card)
    failures = validate_rendered_card(text, card)
    assert any("protection premium" in f for f in failures)


# -- 4. Error handling ------------------------------------------


def test_render_card_raises_on_missing_scope():
    card = _base_card()
    card.pop("scope")
    with pytest.raises(CardRenderError) as exc:
        render_card(card)
    assert "scope is required" in str(exc.value)


def test_render_card_raises_on_missing_underlying():
    card = _base_card()
    card.pop("underlying")
    with pytest.raises(CardRenderError):
        render_card(card)


def test_render_card_raises_on_empty_legs():
    card = _base_card()
    card["legs"] = []
    with pytest.raises(CardRenderError):
        render_card(card)


def test_render_card_raises_on_oversized_payload():
    """[WORKFLOW-E.4 2026-09-17] Telegram's hard cap is 4096
    chars; renderer must raise to prevent silent truncation."""
    card = _base_card()
    # Make why_now a giant blob to blow past MAX_TELEGRAM_CHARS.
    card["why_now"] = ["x" * 5000]
    with pytest.raises(CardRenderError) as exc:
        render_card(card)
    assert "advisory_card_over_telegram_limit" in str(exc.value)


def test_max_telegram_chars_constant_is_4096():
    assert MAX_TELEGRAM_CHARS == 4096


def test_render_card_raises_on_non_dict():
    with pytest.raises(CardRenderError):
        render_card("not a dict")  # type: ignore[arg-type]


def test_render_card_raises_on_non_dict_leg():
    card = _base_card()
    card["legs"] = ["not a dict"]
    with pytest.raises(CardRenderError):
        render_card(card)


def test_render_card_raises_on_naive_datetime():
    """[WORKFLOW-E.4 2026-09-17] The original code enforces
    timezone-aware datetimes. Renderer must do the same."""
    import datetime as _dt
    card = _base_card()
    card["quote_time"] = _dt.datetime(2026, 9, 17, 9, 30, 0)  # Naive.
    with pytest.raises(ValueError):
        render_card(card)


def test_render_card_accepts_iso_string_timestamps():
    """The dict shape uses ISO strings (from
    ``_candidate_payload``); the renderer must accept them."""
    card = _base_card()
    # Already ISO strings in _base_card -- should render fine.
    text = render_card(card)
    assert "Data 2026-09-17T09:30:00+05:30" in text


def test_render_and_validate_returns_text_and_failures():
    card = _base_card()
    text, failures = render_and_validate(card)
    assert isinstance(text, str)
    assert failures == []


# -- 5. Strike formatting parity with the original --------------


def test_strike_int_renders_without_decimal():
    """[WORKFLOW-E.4 2026-09-17] The original code uses
    ``:g`` formatting; ``24100`` stays as ``24100``."""
    card = _base_card()
    text = render_card(card)
    assert "24100CE" in text
    assert "24100.0CE" not in text


def test_strike_float_renders_with_decimal():
    card = _base_card()
    card["legs"][0]["strike"] = 24100.5
    text = render_card(card)
    assert "24100.5CE" in text


# -- 6. rupee formatting ---------------------------------------


def test_net_debit_uses_thousands_separator():
    card = _base_card()
    card["net_debit_rs"] = 12345.67
    text = render_card(card)
    assert "₹12,345.67" in text


def test_max_loss_uses_thousands_separator():
    card = _base_card()
    card["max_loss_rs"] = 1000000.0
    text = render_card(card)
    assert "₹1,000,000.00" in text
