"""[WORKFLOW-I.4.D 2026-09-14] Tests for the agent-side
classifier helpers.

The agent module exposes two helpers that the classifier
feature flag uses:

  * ``_fetch_news_items_for_ticker(ticker)`` -- fetches the raw
    NewsItem list that ``scrape_sentiment`` would render.

  * ``_maybe_classify_news(ticker)`` -- opt-in wrapper that
    checks ``ENABLE_NEWS_CLASSIFIER`` and the classifier's
    own ``DISABLE_CLASSIFIER`` and returns either None (off),
    [] (on but no items), or a list of ClassificationResult.

These are pure helpers (never raise). Tests pin:

  * ``_maybe_classify_news`` returns None when the flag is off
    (the existing caller's path -- default).
  * ``_maybe_classify_news`` returns [] when the flag is on but
    no items are fetched.
  * ``_maybe_classify_news`` returns [] when the classifier is
    disabled (DISABLE_CLASSIFIER=1) even if the flag is on.
  * ``_fetch_news_items_for_ticker`` never raises (network
    failures degrade to empty list with a warning).
  * ``_fetch_news_items_for_ticker`` uses the same URLs as
    ``scrape_sentiment`` (so the operator gets the same items).
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

import agent
import news_classifier
from news_classifier import (
    ClassificationResult,
    NewsCategory,
)
from agent import NewsItem


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _stub_news_item(title: str) -> NewsItem:
    """Build a NewsItem with the minimum fields the classifier
    expects. We don't use ``datetime.now()`` because the
    classifier only reads .title, .age_label, .source_name.
    """
    return NewsItem(
        title=title,
        source_url="https://example.com/" + title.replace(" ", "-"),
        published_at_raw="Sun, 20 Sep 2026 09:00:00 GMT",
        published_at_parsed=datetime(2026, 9, 20, 9, 0, tzinfo=timezone.utc),
        source_name="Example",
        age_label="fresh",
    )


# ---------------------------------------------------------------------------
# _maybe_classify_news -- flag off
# ---------------------------------------------------------------------------


def test_maybe_classify_returns_none_when_flag_off(monkeypatch):
    """Default: ENABLE_NEWS_CLASSIFIER is unset, so the
    helper returns None and the verdict pipeline consumes
    raw sentiment_text. Existing callers' path is preserved.
    """
    monkeypatch.delenv("ENABLE_NEWS_CLASSIFIER", raising=False)
    monkeypatch.setattr(agent.news_classifier, "CLASSIFIER_DISABLED", False)
    result = agent._maybe_classify_news("RELIANCE")
    assert result is None


def test_maybe_classify_returns_none_when_flag_explicit_off(monkeypatch):
    """ENABLE_NEWS_CLASSIFIER=0 is also off (only '1' enables)."""
    monkeypatch.setenv("ENABLE_NEWS_CLASSIFIER", "0")
    result = agent._maybe_classify_news("RELIANCE")
    assert result is None


# ---------------------------------------------------------------------------
# _maybe_classify_news -- flag on
# ---------------------------------------------------------------------------


def test_maybe_classify_returns_list_when_flag_on(monkeypatch):
    """When ENABLE_NEWS_CLASSIFIER=1 and items are available,
    the helper returns a list of ClassificationResult.
    """
    monkeypatch.setenv("ENABLE_NEWS_CLASSIFIER", "1")
    monkeypatch.setattr(agent.news_classifier, "CLASSIFIER_DISABLED", False)

    items = [_stub_news_item("RELIANCE Q3 results")]
    with patch.object(agent, "_fetch_news_items_for_ticker", return_value=items), \
         patch.object(
             agent.news_classifier,
             "classify_news_items",
             return_value=[
                 ClassificationResult(
                     ticker="Example", title_hash="abc123def456",
                     category=NewsCategory.EARNINGS, confidence=0.9,
                     rationale="Q3 beat.", prompt_version="v1",
                     classified_at=None,
                 )
             ],
         ):
        result = agent._maybe_classify_news("RELIANCE")
    assert result is not None
    assert len(result) == 1
    assert result[0].category == NewsCategory.EARNINGS


def test_maybe_classify_passes_the_dedicated_no_retry_client(monkeypatch):
    monkeypatch.setenv("ENABLE_NEWS_CLASSIFIER", "1")
    monkeypatch.setattr(agent.news_classifier, "CLASSIFIER_DISABLED", False)
    dedicated = MagicMock()
    monkeypatch.setattr(agent, "classifier_client", dedicated)
    items = [_stub_news_item("RELIANCE Q3 results")]
    with patch.object(agent, "_fetch_news_items_for_ticker", return_value=items), \
         patch.object(agent.news_classifier, "classify_news_items", return_value=[]) as classify:
        assert agent._maybe_classify_news("RELIANCE") == []
    assert classify.call_args.kwargs["client"] is dedicated


def test_classifier_client_builder_configures_zero_sdk_retries(monkeypatch):
    constructed = []

    def fake_openai(**kwargs):
        constructed.append(kwargs)
        return object()

    monkeypatch.setattr(agent, "OpenAI", fake_openai)
    monkeypatch.setattr(agent, "MINIMAX_API_KEY", "test-key")
    built = agent._build_classifier_client()

    assert built is not None
    assert constructed[0]["max_retries"] == agent.news_classifier.CLASSIFIER_MAX_RETRIES == 0


def test_maybe_classify_returns_empty_list_when_no_items(monkeypatch):
    """Flag is on but the feeds fail: returns [] (the verdict
    pipeline renders the placeholder, not None)."""
    monkeypatch.setenv("ENABLE_NEWS_CLASSIFIER", "1")
    monkeypatch.setattr(agent.news_classifier, "CLASSIFIER_DISABLED", False)
    with patch.object(agent, "_fetch_news_items_for_ticker", return_value=[]):
        result = agent._maybe_classify_news("RELIANCE")
    assert result == []


def test_maybe_classify_returns_empty_when_classifier_disabled(monkeypatch):
    """ENABLE_NEWS_CLASSIFIER=1 but DISABLE_CLASSIFIER=1: the
    helper returns [] (the classifier would have returned
    UNKNOWN-only anyway; skip the model call).
    """
    monkeypatch.setenv("ENABLE_NEWS_CLASSIFIER", "1")
    monkeypatch.setattr(agent.news_classifier, "CLASSIFIER_DISABLED", True)
    with patch.object(agent, "_fetch_news_items_for_ticker") as fetch_mock:
        result = agent._maybe_classify_news("RELIANCE")
    # fetch was never called -- short-circuit.
    fetch_mock.assert_not_called()
    assert result == []


# ---------------------------------------------------------------------------
# _maybe_classify_news -- fail-closed
# ---------------------------------------------------------------------------


def test_maybe_classify_returns_empty_on_unexpected_failure(monkeypatch):
    """An unexpected exception in fetch_news_items is caught
    and the helper returns []. The verdict pipeline is never
    broken by a classifier failure.
    """
    monkeypatch.setenv("ENABLE_NEWS_CLASSIFIER", "1")
    monkeypatch.setattr(agent.news_classifier, "CLASSIFIER_DISABLED", False)

    def boom(*args, **kwargs):
        raise RuntimeError("unexpected")

    with patch.object(agent, "_fetch_news_items_for_ticker", side_effect=boom):
        result = agent._maybe_classify_news("RELIANCE")
    assert result == []


# ---------------------------------------------------------------------------
# _fetch_news_items_for_ticker -- never raises
# ---------------------------------------------------------------------------


def test_fetch_news_items_handles_yahoo_failure(monkeypatch):
    """If the Yahoo fetch raises, the helper logs a warning
    and returns whatever Google returned (possibly empty).
    """
    def fetch_boom(url, **kwargs):
        if "yahoo" in url:
            raise RuntimeError("yahoo down")
        return [_stub_news_item("headline from google")]

    monkeypatch.setattr(agent, "fetch_news_items", fetch_boom)
    items = agent._fetch_news_items_for_ticker("RELIANCE")
    assert len(items) == 1
    assert items[0].title == "headline from google"


def test_fetch_news_items_handles_google_failure(monkeypatch):
    """If the Google fetch raises, the helper logs a warning
    and returns whatever Yahoo returned.
    """
    def fetch_boom(url, **kwargs):
        if "google" in url:
            raise RuntimeError("google down")
        return [_stub_news_item("headline from yahoo")]

    monkeypatch.setattr(agent, "fetch_news_items", fetch_boom)
    items = agent._fetch_news_items_for_ticker("RELIANCE")
    assert len(items) == 1
    assert items[0].title == "headline from yahoo"


def test_fetch_news_items_handles_both_failure(monkeypatch):
    """Both feeds fail: helper returns empty list, never raises."""
    def fetch_boom(url, **kwargs):
        raise RuntimeError("all down")

    monkeypatch.setattr(agent, "fetch_news_items", fetch_boom)
    items = agent._fetch_news_items_for_ticker("RELIANCE")
    assert items == []


# ---------------------------------------------------------------------------
# URL contract: same URLs as scrape_sentiment
# ---------------------------------------------------------------------------


def test_fetch_news_items_uses_same_urls_as_scrape_sentiment(monkeypatch):
    """The helper must hit the same URLs as scrape_sentiment
    (Yahoo + Google) so the classifier sees exactly the items
    the verdict pipeline is about to see.
    """
    captured_urls: list[str] = []

    def fetch_capture(url, **kwargs):
        captured_urls.append(url)
        return []

    monkeypatch.setattr(agent, "fetch_news_items", fetch_capture)
    agent._fetch_news_items_for_ticker("RELIANCE")
    assert len(captured_urls) == 2
    assert any("yahoo" in u for u in captured_urls)
    assert any("google" in u for u in captured_urls)
    # Both URLs are for the ticker we passed.
    for u in captured_urls:
        assert "RELIANCE" in u


def test_collect_news_context_fetches_once_and_classifies_rendered_objects(monkeypatch):
    """Rendered text and classifications must derive from one feed snapshot."""
    yahoo = _stub_news_item("Yahoo headline")
    google = _stub_news_item("Google headline")
    fetch = MagicMock(side_effect=[[yahoo], [google]])
    classify = MagicMock(return_value=[])
    monkeypatch.setattr(agent, "fetch_news_items", fetch)
    monkeypatch.setattr(agent.news_classifier, "classify_news_items", classify)
    monkeypatch.setattr(agent.news_classifier, "CLASSIFIER_DISABLED", False)
    monkeypatch.setenv("ENABLE_NEWS_CLASSIFIER", "1")

    rendered, classifications = agent._collect_news_context("RELIANCE")

    assert fetch.call_count == 2
    assert "Yahoo headline" in rendered
    assert "Google headline" in rendered
    assert classifications == []
    classified_items = classify.call_args.args[0]
    assert classified_items[0] is yahoo
    assert classified_items[1] is google
    assert classify.call_args.kwargs == {
        "ticker": "RELIANCE", "client": agent.classifier_client,
    }
