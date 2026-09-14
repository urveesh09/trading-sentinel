"""[WORKFLOW-I.4.D 2026-09-14] Tests for the source-event
classifier.

The classifier is a bounded module: pure functions, frozen
dataclass output, fixed taxonomy. Tests cover:

  * Taxonomy enumeration (8 categories, all bounded)
  * JSON parser (think-block stripping, markdown fence,
    malformed input)
  * Output normaliser (category coercion, confidence coercion,
    rationale bounding)
  * Threshold rule (low confidence -> UNKNOWN)
  * Disabled / no-client path (returns UNKNOWN with reason)
  * Batch API (ordering preserved, empty input)
  * ``to_dict`` JSON-safety (frozen dataclass -> bounded dict)
  * Frozen-dataclass immutability
  * End-to-end with a mock client (happy path + parse failure
    + timeout)

The deep-research doc says "Tests: >=10 (taxonomy, edge
cases, classification fallback)"; this file ships 20+.
"""
from __future__ import annotations

import json
import time
from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

import news_classifier
from news_classifier import (
    CLASSIFIER_PROMPT_VERSION,
    CLASSIFIER_TIMEOUT_SEC,
    CONFIDENCE_THRESHOLD,
    NewsCategory,
    ClassificationResult,
    _build_classification,
    _classify_single,
    _coerce_category,
    _coerce_confidence,
    _extract_json_object,
    _rationale,
    _title_hash,
    classify_news_items,
    to_dict,
)


# ---------------------------------------------------------------------------
# Test NewsItem stand-in (avoids importing agent.py which opens
# network sockets at import time). The classifier's only
# requirement from NewsItem is .title, .age_label, .source_name.
# ---------------------------------------------------------------------------


class _StubItem:
    def __init__(self, title, age_label="fresh", source_name="Yahoo"):
        self.title = title
        self.age_label = age_label
        self.source_name = source_name


# ---------------------------------------------------------------------------
# Taxonomy
# ---------------------------------------------------------------------------


def test_news_category_has_exactly_eight_values():
    """The taxonomy is fixed at 8 categories per the I.4 doc."""
    expected = {
        "regulatory", "earnings", "m_and_a", "guidance",
        "macro", "rumor", "technical", "unknown",
    }
    actual = {c.value for c in NewsCategory}
    assert actual == expected


def test_news_category_is_string_enum():
    """``NewsCategory`` inherits from ``str`` so JSON
    serialisation works without a custom encoder.
    """
    assert NewsCategory.REGULATORY.value == "regulatory"
    assert isinstance(NewsCategory.REGULATORY, str)


# ---------------------------------------------------------------------------
# JSON extraction
# ---------------------------------------------------------------------------


def test_extract_json_strips_think_blocks():
    """MiniMax-M3 emits inline ``<think>...</think>`` blocks
    before the JSON. The parser strips them.
    """
    raw = (
        "<think>\nLet me analyse this carefully...\n</think>\n"
        '{"category": "earnings", "confidence": 0.85, '
        '"rationale": "Q3 results beat estimates."}'
    )
    payload = _extract_json_object(raw)
    assert payload == {
        "category": "earnings",
        "confidence": 0.85,
        "rationale": "Q3 results beat estimates.",
    }


def test_extract_json_strips_unclosed_think_block():
    """An UNCLOSED ``<think>`` (reasoning ran past max_tokens
    and no JSON was ever emitted) makes the parser return None.
    """
    raw = "<think>...reasoning ran past the budget..."
    assert _extract_json_object(raw) is None


def test_extract_json_strips_markdown_code_fence():
    """LLMs sometimes wrap JSON in ``\\`\\`\\`json ... \\`\\`\\```."""
    raw = (
        "```json\n"
        '{"category": "macro", "confidence": 0.7, '
        '"rationale": "RBI policy rate hike."}\n'
        "```"
    )
    payload = _extract_json_object(raw)
    assert payload["category"] == "macro"


def test_extract_json_handles_leading_prose():
    """Some LLMs emit prose before the JSON. The parser falls
    back to outermost-brace extraction.
    """
    raw = (
        "Here is the classification:\n"
        '{"category": "regulatory", "confidence": 0.9, '
        '"rationale": "SEBI order."}\n'
        "End."
    )
    payload = _extract_json_object(raw)
    assert payload["category"] == "regulatory"


def test_extract_json_returns_none_on_garbage():
    """Garbage text returns None, never a partial / wrong dict."""
    assert _extract_json_object("not json {") is None
    assert _extract_json_object("") is None
    assert _extract_json_object(None) is None


# ---------------------------------------------------------------------------
# Output normaliser
# ---------------------------------------------------------------------------


def test_coerce_category_accepts_bounded_values():
    for cat in NewsCategory:
        assert _coerce_category(cat.value) == cat
        # Case insensitive.
        assert _coerce_category(cat.value.upper()) == cat


def test_coerce_category_rejects_invented_values():
    """A category the model invents (outside the bounded set)
    maps to ``UNKNOWN``. The taxonomy is operator-defined; the
    model cannot extend it.
    """
    assert _coerce_category("sports_score") == NewsCategory.UNKNOWN
    assert _coerce_category("") == NewsCategory.UNKNOWN
    assert _coerce_category(None) == NewsCategory.UNKNOWN
    assert _coerce_category(42) == NewsCategory.UNKNOWN


def test_coerce_confidence_bounded_and_rejects_garbage():
    """Confidence is bounded to ``[0.0, 1.0]``. NaN/Inf/None/bool
    all map to 0.0 (fail-closed)."""
    assert _coerce_confidence(0.0) == 0.0
    assert _coerce_confidence(1.0) == 1.0
    assert _coerce_confidence(0.5) == 0.5
    assert _coerce_confidence(-0.1) == 0.0
    assert _coerce_confidence(1.5) == 1.0
    assert _coerce_confidence(None) == 0.0
    # Bool would coerce to 0/1 via int subclass; we reject
    # explicitly so a stray ``True`` does not become a 1.0
    # confidence claim.
    assert _coerce_confidence(True) == 0.0
    assert _coerce_confidence(False) == 0.0
    # Strings are not silently coerced to 0 (would let the
    # model "set" its own confidence by returning "1.0").
    assert _coerce_confidence("1.0") == 0.0


def test_rationale_bounded_to_280_chars():
    """A 1000-char rationale is truncated to 280 chars so one
    classification cannot leak into the verdict prompt budget.
    """
    long = "x" * 1000
    out = _rationale(long)
    assert len(out) <= 280
    assert out.endswith("...")
    # Short rationales pass through.
    assert _rationale("Q3 beat.") == "Q3 beat."
    # Non-strings become empty string.
    assert _rationale(None) == ""
    assert _rationale(42) == ""


# ---------------------------------------------------------------------------
# Threshold rule
# ---------------------------------------------------------------------------


def test_low_confidence_forced_to_unknown():
    """A non-UNKNOWN category below the threshold is forced to
    UNKNOWN. The dataclass is built with the threshold-applied
    category, so consumers never see a low-confidence non-UNKNOWN
    label.
    """
    result = _build_classification(
        ticker="RELIANCE",
        item_title="some headline",
        category=NewsCategory.EARNINGS,
        confidence=CONFIDENCE_THRESHOLD - 0.01,
        rationale="weak signal",
    )
    assert result.category == NewsCategory.UNKNOWN
    # The original confidence is preserved (audit trail), only
    # the category is re-mapped.
    assert result.confidence == pytest.approx(
        CONFIDENCE_THRESHOLD - 0.01
    )


def test_high_confidence_passes_through():
    """A high-confidence non-UNKNOWN category passes through."""
    result = _build_classification(
        ticker="RELIANCE",
        item_title="headline",
        category=NewsCategory.REGULATORY,
        confidence=CONFIDENCE_THRESHOLD + 0.05,
        rationale="SEBI order",
    )
    assert result.category == NewsCategory.REGULATORY


def test_unknown_category_passes_at_any_confidence():
    """The threshold rule only fires when the category is NOT
    UNKNOWN. UNKNOWN stays UNKNOWN regardless of confidence.
    """
    result = _build_classification(
        ticker="RELIANCE",
        item_title="h",
        category=NewsCategory.UNKNOWN,
        confidence=0.1,
        rationale="...",
    )
    assert result.category == NewsCategory.UNKNOWN


# ---------------------------------------------------------------------------
# Frozen dataclass immutability
# ---------------------------------------------------------------------------


def test_classification_result_is_frozen():
    """The dataclass is frozen -- a downstream consumer cannot
    silently mutate a classification after it was produced.
    """
    result = _build_classification(
        ticker="RELIANCE", item_title="h",
        category=NewsCategory.EARNINGS, confidence=0.9,
        rationale="Q3 beat.",
    )
    with pytest.raises(FrozenInstanceError):
        result.category = NewsCategory.UNKNOWN  # type: ignore[misc]


def test_classification_result_carries_provenance():
    """The result carries ticker, title_hash, prompt_version, and
    classified_at for the audit trail.
    """
    result = _build_classification(
        ticker="RELIANCE", item_title="RELIANCE Q3 results",
        category=NewsCategory.EARNINGS, confidence=0.9,
        rationale="Q3 beat.",
    )
    assert result.ticker == "RELIANCE"
    assert len(result.title_hash) == 12  # 48 bits of SHA-256
    assert result.title_hash == _title_hash("RELIANCE Q3 results")
    assert result.prompt_version == CLASSIFIER_PROMPT_VERSION
    assert isinstance(result.classified_at, datetime)
    # classified_at is timezone-aware UTC.
    assert result.classified_at.tzinfo is not None


# ---------------------------------------------------------------------------
# Title hashing
# ---------------------------------------------------------------------------


def test_title_hash_is_stable():
    """Same title -> same hash; different title -> different hash."""
    a = _title_hash("RELIANCE Q3 results beat estimates")
    b = _title_hash("RELIANCE Q3 results beat estimates")
    c = _title_hash("INFY Q3 results beat estimates")
    assert a == b
    assert a != c
    assert len(a) == 12


def test_title_hash_handles_non_ascii():
    """Non-ASCII titles hash without raising (utf-8 with replace)."""
    h = _title_hash("रिलायंस Q3 परिणाम")
    assert len(h) == 12


# ---------------------------------------------------------------------------
# Disabled / no-client paths
# ---------------------------------------------------------------------------


def test_disabled_returns_unknown_with_reason(monkeypatch):
    """``DISABLE_CLASSIFIER=1`` (or no client) returns UNKNOWN
    with a human-readable rationale. No model call is made.
    """
    monkeypatch.setattr(news_classifier, "CLASSIFIER_DISABLED", True)
    item = _StubItem("Some headline", "fresh", "Yahoo")
    mock_client = MagicMock()
    result = _classify_single(
        item, client=mock_client, model="MiniMax-M3", timeout_sec=1.0
    )
    assert result.category == NewsCategory.UNKNOWN
    assert result.confidence == 0.0
    assert "disabled" in result.rationale.lower()
    # No model call happened.
    mock_client.chat.completions.create.assert_not_called()


def test_no_client_returns_unknown_with_reason():
    """When ``client is None`` the classifier returns UNKNOWN
    instead of raising. Same fail-closed contract.
    """
    item = _StubItem("Some headline", "fresh", "Yahoo")
    result = _classify_single(
        item, client=None, model="MiniMax-M3", timeout_sec=1.0
    )
    assert result.category == NewsCategory.UNKNOWN
    assert result.confidence == 0.0
    assert "no minimax client" in result.rationale.lower()


# ---------------------------------------------------------------------------
# End-to-end with mock client
# ---------------------------------------------------------------------------


def _mock_client_with_payload(payload: dict, *, sleep_for: float = 0.0):
    """Build a MagicMock that mimics the OpenAI chat client."""
    message = MagicMock()
    message.content = json.dumps(payload)
    choice = MagicMock()
    choice.message = message
    response = MagicMock()
    response.choices = [choice]
    client = MagicMock()
    client.chat.completions.create.return_value = response

    if sleep_for > 0:
        # Simulate a slow model call.
        original_create = client.chat.completions.create

        def slow_create(*args, **kwargs):
            time.sleep(sleep_for)
            return original_create(*args, **kwargs)

        client.chat.completions.create.side_effect = slow_create
    return client


def test_classify_happy_path_with_mock_client():
    """A well-formed model response produces a non-UNKNOWN
    classification with the expected fields.
    """
    item = _StubItem(
        "RELIANCE Q3 results beat estimates by 8%",
        "fresh", "Reuters",
    )
    payload = {
        "category": "earnings",
        "confidence": 0.92,
        "rationale": "Quarterly beat vs consensus.",
    }
    client = _mock_client_with_payload(payload)
    result = _classify_single(
        item, client=client, model="MiniMax-M3", timeout_sec=1.0
    )
    assert result.category == NewsCategory.EARNINGS
    assert result.confidence == pytest.approx(0.92)
    assert "Quarterly beat" in result.rationale
    assert result.ticker == "Reuters"  # ticker field carries source_name


def test_classify_handles_think_block_in_response():
    """The model emits ``<think>...</think>`` before the JSON.
    The parser strips it.
    """
    item = _StubItem("Some headline", "fresh", "Reuters")
    payload_dict = {
        "category": "regulatory",
        "confidence": 0.88,
        "rationale": "SEBI order.",
    }
    message = MagicMock()
    message.content = (
        "<think>reasoning</think>\n"
        + json.dumps(payload_dict)
    )
    choice = MagicMock()
    choice.message = message
    response = MagicMock()
    response.choices = [choice]
    client = MagicMock()
    client.chat.completions.create.return_value = response
    result = _classify_single(
        item, client=client, model="MiniMax-M3", timeout_sec=1.0
    )
    assert result.category == NewsCategory.REGULATORY
    assert result.confidence == pytest.approx(0.88)


def test_classify_handles_parse_failure():
    """When the model returns garbage, the classifier returns
    UNKNOWN with a parse-failure rationale. Never raises.
    """
    item = _StubItem("Some headline", "fresh", "Reuters")
    message = MagicMock()
    message.content = "not json {"
    choice = MagicMock()
    choice.message = message
    response = MagicMock()
    response.choices = [choice]
    client = MagicMock()
    client.chat.completions.create.return_value = response
    result = _classify_single(
        item, client=client, model="MiniMax-M3", timeout_sec=1.0
    )
    assert result.category == NewsCategory.UNKNOWN
    assert result.confidence == 0.0
    assert "unparseable" in result.rationale.lower()


def test_classify_handles_schema_mismatch():
    """When the model returns a payload with extra / missing keys,
    the classifier returns UNKNOWN with a schema-mismatch rationale.
    """
    item = _StubItem("Some headline", "fresh", "Reuters")
    # Payload has an extra field ("verdict") -- schema mismatch.
    payload = {
        "category": "macro",
        "confidence": 0.7,
        "rationale": "RBI rate hike.",
        "verdict": "BUY",  # not allowed -- classifier is
                           # informational only
    }
    client = _mock_client_with_payload(payload)
    result = _classify_single(
        item, client=client, model="MiniMax-M3", timeout_sec=1.0
    )
    assert result.category == NewsCategory.UNKNOWN
    assert result.confidence == 0.0
    assert "schema" in result.rationale.lower()


def test_classify_handles_low_confidence_payload():
    """A well-formed payload with confidence below threshold is
    forced to UNKNOWN.
    """
    item = _StubItem("Some headline", "fresh", "Reuters")
    payload = {
        "category": "earnings",
        "confidence": 0.3,
        "rationale": "unclear.",
    }
    client = _mock_client_with_payload(payload)
    result = _classify_single(
        item, client=client, model="MiniMax-M3", timeout_sec=1.0
    )
    assert result.category == NewsCategory.UNKNOWN
    assert result.confidence == pytest.approx(0.3)


def test_classify_handles_model_exception():
    """If the model call raises (timeout, API error, etc.), the
    classifier returns UNKNOWN with the exception class name.
    Never propagates the exception.
    """
    item = _StubItem("Some headline", "fresh", "Reuters")
    client = MagicMock()
    client.chat.completions.create.side_effect = TimeoutError("API timed out")
    result = _classify_single(
        item, client=client, model="MiniMax-M3", timeout_sec=1.0
    )
    assert result.category == NewsCategory.UNKNOWN
    assert result.confidence == 0.0
    assert "TimeoutError" in result.rationale


# ---------------------------------------------------------------------------
# Batch API
# ---------------------------------------------------------------------------


def test_classify_news_items_preserves_order():
    """The batch classifier preserves item order: result[i] is
    the classification of items[i].
    """
    items = [
        _StubItem("RELIANCE earnings beat", "fresh", "Reuters"),
        _StubItem("INFY guidance update", "1 hour ago", "Bloomberg"),
        _StubItem("TCS M&A rumor", "2 days ago", "Moneycontrol"),
    ]
    payload_a = {"category": "earnings", "confidence": 0.9,
                 "rationale": "Q3 beat."}
    payload_b = {"category": "guidance", "confidence": 0.8,
                 "rationale": "Forward outlook."}
    payload_c = {"category": "rumor", "confidence": 0.6,
                 "rationale": "Unconfirmed."}
    client = MagicMock()
    client.chat.completions.create.side_effect = [
        _mock_client_with_payload(payload_a).chat.completions.create.return_value,
        _mock_client_with_payload(payload_b).chat.completions.create.return_value,
        _mock_client_with_payload(payload_c).chat.completions.create.return_value,
    ]
    results = classify_news_items(
        items, client=client, model="MiniMax-M3", timeout_sec=1.0
    )
    assert len(results) == 3
    assert results[0].category == NewsCategory.EARNINGS
    assert results[1].category == NewsCategory.GUIDANCE
    assert results[2].category == NewsCategory.RUMOR
    # Title hashes reflect the order.
    assert results[0].title_hash == _title_hash("RELIANCE earnings beat")
    assert results[1].title_hash == _title_hash("INFY guidance update")


def test_classify_news_items_empty_input():
    """Empty input returns an empty list without making any model
    calls.
    """
    client = MagicMock()
    assert classify_news_items(
        [], client=client, model="MiniMax-M3", timeout_sec=1.0
    ) == []
    client.chat.completions.create.assert_not_called()


def test_classify_news_items_per_item_failure_isolated():
    """A failure on one item doesn't fail the whole batch."""
    items = [
        _StubItem("a", "fresh", "x"),
        _StubItem("b", "fresh", "x"),
        _StubItem("c", "fresh", "x"),
    ]
    payload = {"category": "earnings", "confidence": 0.9,
               "rationale": "ok"}
    client = MagicMock()
    client.chat.completions.create.side_effect = [
        TimeoutError("API down"),
        _mock_client_with_payload(payload).chat.completions.create.return_value,
        _mock_client_with_payload(payload).chat.completions.create.return_value,
    ]
    results = classify_news_items(
        items, client=client, model="MiniMax-M3", timeout_sec=1.0
    )
    assert len(results) == 3
    assert results[0].category == NewsCategory.UNKNOWN
    assert "TimeoutError" in results[0].rationale
    assert results[1].category == NewsCategory.EARNINGS
    assert results[2].category == NewsCategory.EARNINGS


# ---------------------------------------------------------------------------
# to_dict JSON-safety
# ---------------------------------------------------------------------------


def test_to_dict_serialises_all_fields():
    """``to_dict`` produces bounded JSON-safe dicts from the
    frozen dataclass (datetime -> ISO string, enum -> value).
    """
    classified_at = datetime(2026, 9, 14, 9, 0, 0, tzinfo=timezone.utc)
    r = ClassificationResult(
        ticker="RELIANCE",
        title_hash="abcdef012345",
        category=NewsCategory.EARNINGS,
        confidence=0.9,
        rationale="Q3 beat.",
        prompt_version="v1",
        classified_at=classified_at,
    )
    [d] = to_dict([r])
    assert d["ticker"] == "RELIANCE"
    assert d["title_hash"] == "abcdef012345"
    assert d["category"] == "earnings"
    assert d["confidence"] == 0.9
    assert d["rationale"] == "Q3 beat."
    assert d["prompt_version"] == "v1"
    assert d["classified_at"] == "2026-09-14T09:00:00+00:00"
    # JSON-safe end-to-end.
    serialised = json.dumps(d)
    assert json.loads(serialised) == d


def test_to_dict_handles_null_classified_at():
    """When ``classified_at`` is None (timeout / error path),
    ``to_dict`` returns ``None`` for that field rather than
    crashing.
    """
    r = ClassificationResult(
        ticker="RELIANCE",
        title_hash="abc",
        category=NewsCategory.UNKNOWN,
        confidence=0.0,
        rationale="timeout",
        prompt_version="v1",
        classified_at=None,
    )
    [d] = to_dict([r])
    assert d["classified_at"] is None


def test_to_dict_empty_list():
    """Empty input returns an empty list."""
    assert to_dict([]) == []


# ---------------------------------------------------------------------------
# Configuration sanity
# ---------------------------------------------------------------------------


def test_classifier_timeout_within_doc_budget():
    """The default per-item timeout is <= 1.0s per the deep-
    research doc's latency budget.
    """
    assert CLASSIFIER_TIMEOUT_SEC <= 1.0


def test_confidence_threshold_is_in_unit_range():
    """The threshold is in ``[0.0, 1.0]``. Sanity pin."""
    assert 0.0 <= CONFIDENCE_THRESHOLD <= 1.0


def test_prompt_version_is_non_empty():
    """The prompt version is non-empty so cached results carry
    a version for the audit trail.
    """
    assert CLASSIFIER_PROMPT_VERSION


# ---------------------------------------------------------------------------
# End-to-end: classify_news_items without explicit client (uses
# module-level fallback). When ``agent.client`` is None the
# classifier returns UNKNOWN for every item without raising.
# ---------------------------------------------------------------------------


def test_classify_news_items_uses_module_client(monkeypatch):
    """``classify_news_items`` falls back to the agent module's
    ``client`` global when ``client=None`` is passed. The agent
    module's ``client`` is None in our test environment (no
    ``MINIMAX_API_KEY``); the classifier should return UNKNOWN
    for every item without raising.
    """
    import agent
    # The agent module's ``client`` is None in our test env
    # because conftest.py sets a fake MINIMAX_API_KEY but the
    # OpenAI client object is never instantiated when network
    # is unavailable. We patch it to None to simulate the
    # "no client" case deterministically.
    monkeypatch.setattr(agent, "client", None)
    items = [_StubItem("a"), _StubItem("b")]
    results = classify_news_items(items, client=None)
    assert len(results) == 2
    assert all(r.category == NewsCategory.UNKNOWN for r in results)
    assert all(r.confidence == 0.0 for r in results)
