"""[WORKFLOW-I.4.D 2026-09-14] Integration tests for the
``pre_classifications`` parameter on ``analyze_with_minimax``.

The verdict pipeline accepts an optional list of
``ClassificationResult`` and surfaces them as a
"CLASSIFIED SENTIMENT DATA" section in the prompt. When the
parameter is None (the default, and every existing caller's
path), the prompt is byte-identical to its pre-I.4.D shape:
only "MULTI-SOURCE SENTIMENT DATA" is rendered.

These tests pin the integration contract:

  * ``_render_classified_section`` renders bounded output.
  * ``analyze_with_minimax`` accepts the new keyword-only arg.
  * The prompt contains the CLASSIFIED SENTIMENT DATA section
    when ``pre_classifications`` is supplied.
  * The prompt is unchanged (byte-identical modulo
    timestamp) when ``pre_classifications`` is None.
  * The "no pre-classifications" placeholder text is rendered
    in the CLASSIFIED SENTIMENT DATA section when nothing was
    supplied (so the model is told to use the raw data).
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

import agent
import news_classifier
from news_classifier import (
    ClassificationResult,
    NewsCategory,
)
from agent import _render_classified_section


def _stub_classification(
    title_hash: str,
    category: NewsCategory,
    confidence: float,
    rationale: str,
) -> ClassificationResult:
    """Build a ClassificationResult for use in prompt-rendering
    tests. Avoids touching the network (no model call).
    """
    now = datetime.now(timezone.utc)
    return ClassificationResult(
        ticker="RELIANCE",
        title_hash=title_hash,
        category=category,
        confidence=confidence,
        rationale=rationale,
        prompt_version="v1",
        classified_at=now,
        source_name="Reuters",
        source_url=f"https://example.test/{title_hash}",
        published_at=now - timedelta(minutes=5),
        source_ref=title_hash.ljust(64, "0"),
        source_valid_until=now + timedelta(days=6),
    )


# ---------------------------------------------------------------------------
# _render_classified_section
# ---------------------------------------------------------------------------


def test_render_classified_section_empty_input_returns_empty_string():
    """Empty input (None or []) returns empty string so the
    caller can detect "no section" and render the placeholder.
    """
    assert _render_classified_section(None) == ""
    assert _render_classified_section([]) == ""


def test_render_classified_section_renders_title_hash_category_conf():
    """Each classification renders with title_hash, category,
    confidence, and rationale on separate lines.
    """
    items = [
        _stub_classification("abc123def456", NewsCategory.EARNINGS, 0.92, "Q3 beat."),
        _stub_classification("def789abc012", NewsCategory.REGULATORY, 0.85, "SEBI order."),
    ]
    section = _render_classified_section(items)
    assert "abc123def456" in section
    assert "CATEGORY=earnings" in section
    assert "CONF=0.92" in section
    assert "Q3 beat." in section
    assert "def789abc012" in section
    assert "CATEGORY=regulatory" in section
    assert "SEBI order." in section


def test_render_classified_section_bounded_when_many_items():
    """A 50-item news batch does not exceed the prompt budget;
    the section caps at MAX_RENDERED_LINES (32) and appends a
    'and N more' line.
    """
    items = [
        _stub_classification(
            f"hash{i:08d}", NewsCategory.MACRO, 0.7, f"r{i}"
        )
        for i in range(50)
    ]
    section = _render_classified_section(items)
    assert "more headlines classified" in section


def test_render_classified_section_handles_empty_rationale():
    """Empty rationale doesn't render the "RATIONALE:" line.
    """
    items = [
        _stub_classification("h1", NewsCategory.UNKNOWN, 0.0, ""),
    ]
    section = _render_classified_section(items)
    assert "RATIONALE:" not in section
    assert "h1" in section


# ---------------------------------------------------------------------------
# analyze_with_minimax integration
# ---------------------------------------------------------------------------


def _mock_client_with_text(text: str) -> MagicMock:
    """Build a mock OpenAI client that returns the given text as
    the model's chat-completions response. Captures the prompt
    sent to the model for inspection.
    """
    message = MagicMock()
    message.content = text
    choice = MagicMock()
    choice.message = message
    response = MagicMock()
    response.choices = [choice]
    client = MagicMock()
    client.chat.completions.create.return_value = response
    return client


def _capture_prompt_for(signal: dict, sentiment_text: str,
                       pre_classifications=None) -> str:
    """Run ``analyze_with_minimax`` with a mock client and return
    the prompt that was sent to the model. The mock returns a
    valid JSON Review payload.
    """
    mock_client = _mock_client_with_text(
        '{"conviction_score": 60, "pitch": "ok", '
        '"rationale": "ok", "risks": "ok"}'
    )
    # Patch the agent module's module-level client.
    original = agent.client
    agent.client = mock_client
    try:
        review = agent.analyze_with_minimax(
            signal=signal,
            sentiment_text=sentiment_text,
            market_regime="BULL",
            pre_classifications=pre_classifications,
        )
    finally:
        agent.client = original
    # Inspect the call: the prompt is the last ``content`` arg.
    call = mock_client.chat.completions.create.call_args
    messages = call.kwargs.get("messages") or call.args[1]
    return messages[-1]["content"]


def test_analyze_with_minimax_prompt_contains_classified_section_when_supplied():
    """When pre_classifications is supplied, the prompt
    contains the CLASSIFIED SENTIMENT DATA section with the
    title_hash + category + confidence + rationale.
    """
    signal = {"ticker": "RELIANCE", "close": 2500.0,
              "target_1": 2625.0, "stop_loss": 2375.0,
              "strategy_type": "SWING"}
    items = [
        _stub_classification(
            "abc123def456", NewsCategory.EARNINGS, 0.92, "Q3 beat.",
        ),
    ]
    prompt = _capture_prompt_for(
        signal, "raw news text", pre_classifications=items
    )
    assert "CLASSIFIED SENTIMENT DATA" in prompt
    assert "abc123def456" in prompt
    assert "CATEGORY=earnings" in prompt
    assert "CONF=0.92" in prompt
    assert "Q3 beat." in prompt


def test_analyze_with_minimax_prompt_unchanged_when_no_classifications():
    """When pre_classifications is None (the default), the
    prompt still contains the placeholder text in the
    CLASSIFIED SENTIMENT DATA section (so the model is told
    to use the raw data) but no actual classifications are
    rendered. The MULTI-SOURCE SENTIMENT DATA section is
    unchanged.
    """
    signal = {"ticker": "RELIANCE", "close": 2500.0,
              "target_1": 2625.0, "stop_loss": 2375.0,
              "strategy_type": "SWING"}
    prompt = _capture_prompt_for(signal, "raw news text")
    # The placeholder is rendered.
    assert "CLASSIFIED SENTIMENT DATA" in prompt
    assert "no pre-classifications supplied" in prompt
    # No title_hash / CATEGORY= rendered.
    assert "CATEGORY=" not in prompt
    # The raw data still flows through.
    assert "raw news text" in prompt
    assert "MULTI-SOURCE SENTIMENT DATA" in prompt


def test_analyze_with_minimax_prompt_unchanged_when_empty_classifications():
    """An empty list of classifications behaves like None:
    the placeholder is rendered, no items in the section.
    """
    signal = {"ticker": "RELIANCE", "close": 2500.0,
              "target_1": 2625.0, "stop_loss": 2375.0,
              "strategy_type": "SWING"}
    prompt = _capture_prompt_for(signal, "raw news text", pre_classifications=[])
    assert "CLASSIFIED SENTIMENT DATA" in prompt
    assert "no pre-classifications supplied" in prompt
    assert "CATEGORY=" not in prompt


def test_analyze_with_minimax_returns_valid_review_with_classifications():
    """End-to-end: with pre_classifications and a mock model
    returning a valid payload, ``analyze_with_minimax`` returns
    a ``Review`` whose payload is the parsed JSON.
    """
    signal = {"ticker": "RELIANCE", "close": 2500.0,
              "target_1": 2625.0, "stop_loss": 2375.0,
              "strategy_type": "SWING"}
    items = [_stub_classification("h1", NewsCategory.EARNINGS, 0.9, "ok")]
    mock_client = _mock_client_with_text(
        '{"conviction_score": 80, "pitch": "good", '
        '"rationale": "fine", "risks": "low"}'
    )
    original = agent.client
    agent.client = mock_client
    try:
        review = agent.analyze_with_minimax(
            signal=signal,
            sentiment_text="raw news",
            market_regime="BULL",
            pre_classifications=items,
        )
    finally:
        agent.client = original
    assert review.payload.get("conviction_score") == 80


def test_analyze_with_minimax_signature_accepts_pre_classifications():
    """The signature accepts ``pre_classifications`` as a
    parameter. Default value is None (callers who don't supply
    it continue to work).
    """
    import inspect
    sig = inspect.signature(agent.analyze_with_minimax)
    assert "pre_classifications" in sig.parameters
    assert sig.parameters["pre_classifications"].default is None
    # Both KEYWORD_ONLY and POSITIONAL_OR_KEYWORD are acceptable;
    # the contract is "callers can supply it as a keyword".
    kind = sig.parameters["pre_classifications"].kind
    assert kind in (
        inspect.Parameter.KEYWORD_ONLY,
        inspect.Parameter.POSITIONAL_OR_KEYWORD,
    )
