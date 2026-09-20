"""[WORKFLOW-I.4.D 2026-09-14] Tests for the AsyncReviewQueue
extension that carries pre_classifications through the queue.

The bounded classifier's verdict-prompt surface is wired into
the momentum pipeline via this extension: when the operator
flips ENABLE_NEWS_CLASSIFIER=1, the call site computes a list
of ClassificationResult, passes it to queue_optional_ai_
review (which forwards it to AsyncReviewQueue.submit as a
keyword), the queue carries it inside _Task, and the worker
forwards it to the reviewer (analyze_with_minimax).

These tests pin:

  * The queue accepts pre_classifications as a submit kwarg.
  * The reviewer receives pre_classifications when present.
  * The reviewer receives pre_classifications=None when the
    caller passes None (the default).
  * A reviewer without the pre_classifications keyword (e.g.
    a test lambda) is invoked with the legacy 3-arg shape --
    backwards compatibility.
  * Frozen-dataclass semantics: pre_classifications is a tuple
    inside _Task (so the queue does not mutate the list).
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import List
from unittest.mock import MagicMock

import pytest

import async_reviews
from async_reviews import AsyncReviewQueue, _Task
from news_classifier import ClassificationResult, NewsCategory
from advisory import Review, Verdict, unavailable


def _wait_for(queue, key, states, timeout_s: float = 2.0):
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        status = queue.status(key)
        if status is not None and status.state in states:
            return status
        time.sleep(0.01)
    raise AssertionError(f"timed out waiting for {key} -> {states}")


def _stub_classification(
    title_hash: str,
    category: NewsCategory = NewsCategory.EARNINGS,
    confidence: float = 0.9,
) -> ClassificationResult:
    now = datetime.now(timezone.utc)
    return ClassificationResult(
        ticker="RELIANCE", title_hash=title_hash,
        category=category, confidence=confidence,
        rationale="ok", prompt_version="v1",
        classified_at=now,
        source_name="Reuters", source_url=f"https://example.test/{title_hash}",
        published_at=now - timedelta(minutes=5), source_ref=title_hash.ljust(64, "0"),
        source_valid_until=now + timedelta(days=6),
    )


# ---------------------------------------------------------------------------
# submit(): pre_classifications kwarg accepted
# ---------------------------------------------------------------------------


def test_submit_accepts_pre_classifications_kwarg():
    """The submit() signature gains a pre_classifications keyword
    argument. When supplied, the queue task carries it.
    """
    captured: dict = {}

    def reviewer(signal, sentiment, regime, *, pre_classifications=None):
        captured["pre_classifications"] = pre_classifications
        captured["signal"] = signal
        return Review(Verdict.APPROVE, conviction=80)

    queue = AsyncReviewQueue(reviewer)
    try:
        items = [_stub_classification("h1"), _stub_classification("h2")]
        queue.submit(
            "k1", {"ticker": "RELIANCE"}, "raw", "BULL",
            pre_classifications=items,
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=30),
        )
        _wait_for(queue, "k1", {"READY"})
        # The reviewer received the kwarg.
        assert "pre_classifications" in captured
        # The queue stored the items as a tuple and re-emitted
        # them as a list at review time -- item equality, not
        # identity.
        assert captured["pre_classifications"] is not None
        assert len(captured["pre_classifications"]) == len(items)
        for got, want in zip(captured["pre_classifications"], items):
            assert got.title_hash == want.title_hash
            assert got.category == want.category
        assert captured["signal"] == {"ticker": "RELIANCE"}
    finally:
        queue.shutdown()


def test_submit_default_pre_classifications_is_none():
    """When the caller does NOT supply pre_classifications, the
    queue's task carries an empty tuple (the reviewer still
    receives pre_classifications=None so the prompt renders
    the placeholder text).
    """
    captured: dict = {}

    def reviewer(signal, sentiment, regime, *, pre_classifications=None):
        captured["pre_classifications"] = pre_classifications
        return Review(Verdict.APPROVE, conviction=80)

    queue = AsyncReviewQueue(reviewer)
    try:
        queue.submit(
            "k1", {"ticker": "RELIANCE"}, "raw", "BULL",
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=30),
        )
        _wait_for(queue, "k1", {"READY"})
        # The kwarg was passed as None (the placeholder path).
        assert captured["pre_classifications"] is None
    finally:
        queue.shutdown()


def test_submit_with_empty_list_passes_none_to_reviewer():
    """pre_classifications=[] (empty list) is normalised to None
    so the reviewer renders the placeholder text. Same behavior
    as the kwarg being omitted.
    """
    captured: dict = {}

    def reviewer(signal, sentiment, regime, *, pre_classifications=None):
        captured["pre_classifications"] = pre_classifications
        return Review(Verdict.APPROVE, conviction=80)

    queue = AsyncReviewQueue(reviewer)
    try:
        queue.submit(
            "k1", {"ticker": "RELIANCE"}, "raw", "BULL",
            pre_classifications=[],
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=30),
        )
        _wait_for(queue, "k1", {"READY"})
        assert captured["pre_classifications"] is None
    finally:
        queue.shutdown()


# ---------------------------------------------------------------------------
# Backwards compatibility: reviewer without pre_classifications kwarg
# ---------------------------------------------------------------------------


def test_submit_calls_legacy_reviewer_with_3_args():
    """A reviewer that doesn't accept pre_classifications (e.g.
    a test lambda) is called with the original 3-arg shape so
    this queue stays backwards-compatible with the existing
    test suite.
    """
    captured: dict = {}

    def reviewer(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return Review(Verdict.APPROVE, conviction=80)

    queue = AsyncReviewQueue(reviewer)
    try:
        items = [_stub_classification("h")]
        queue.submit(
            "k1", {"ticker": "RELIANCE"}, "raw", "BULL",
            pre_classifications=items,
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=30),
        )
        _wait_for(queue, "k1", {"READY"})
        # The 3-arg shape was used (positional only).
        assert len(captured["args"]) == 3
        assert captured["args"][0] == {"ticker": "RELIANCE"}
        assert captured["args"][1] == "raw"
        assert captured["args"][2] == "BULL"
        # No kwargs passed.
        assert captured["kwargs"] == {}
    finally:
        queue.shutdown()


# ---------------------------------------------------------------------------
# _Task frozen semantics
# ---------------------------------------------------------------------------


def test_task_pre_classifications_is_immutable_tuple():
    """pre_classifications is stored as a tuple inside _Task,
    so the queue's in-flight task cannot be mutated by the
    reviewer (frozen dataclass + tuple).
    """
    task = _Task(
        key="k1", signal={"ticker": "RELIANCE"}, sentiment="raw",
        regime="BULL",
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=30),
        pre_classifications=("a", "b"),
    )
    # Tuple is immutable.
    with pytest.raises((TypeError, AttributeError)):
        task.pre_classifications.append("c")  # type: ignore[attr-defined]
    # Dataclass is frozen.
    with pytest.raises(Exception):
        task.key = "k2"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# The verdict pipeline integration: end-to-end smoke test
# ---------------------------------------------------------------------------


def test_pre_classifications_flows_through_queue_to_reviewer():
    """End-to-end: the bounded classification list captured at
    submit-time reaches the reviewer when the worker runs.
    The queue stores it as a tuple (immutable) and re-emits
    it as a list at review time, so the reviewer's view is a
    fresh list with the same items.
    """
    captured: list = []

    def reviewer(signal, sentiment, regime, *, pre_classifications=None):
        # Record the list reference (we assert identity below).
        captured.append(pre_classifications)
        return Review(Verdict.APPROVE, conviction=80)

    queue = AsyncReviewQueue(reviewer)
    try:
        items = [_stub_classification("h1"), _stub_classification("h2")]
        queue.submit(
            "k1", {"ticker": "RELIANCE"}, "raw", "BULL",
            pre_classifications=items,
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=30),
        )
        _wait_for(queue, "k1", {"READY"})
        assert len(captured) == 1
        # The reviewer received a non-None list.
        assert captured[0] is not None
        # Same items, same order.
        assert len(captured[0]) == len(items)
        for got, want in zip(captured[0], items):
            assert got.title_hash == want.title_hash
            assert got.category == want.category
    finally:
        queue.shutdown()


def test_same_external_key_with_changed_classification_is_cache_miss():
    seen: list[NewsCategory] = []

    def reviewer(_signal, _sentiment, _regime, *, pre_classifications=None):
        category = pre_classifications[0].category
        seen.append(category)
        verdict = Verdict.APPROVE if category is NewsCategory.EARNINGS else Verdict.REJECT
        return Review(verdict, conviction=80 if verdict is Verdict.APPROVE else 20)

    queue = AsyncReviewQueue(reviewer)
    try:
        expiry = datetime.now(timezone.utc) + timedelta(seconds=30)
        first = [_stub_classification("h", NewsCategory.EARNINGS)]
        second = [_stub_classification("h", NewsCategory.REGULATORY)]
        assert queue.submit(
            "same-key", {}, "raw", "BULL",
            pre_classifications=first, expires_at=expiry,
        ).state == "QUEUED"
        assert _wait_for(queue, "same-key", {"READY"}).review.verdict is Verdict.APPROVE
        assert queue.submit(
            "same-key", {}, "raw", "BULL",
            pre_classifications=second, expires_at=expiry,
        ).state == "QUEUED"
        assert _wait_for(queue, "same-key", {"READY"}).review.verdict is Verdict.REJECT
        assert seen == [NewsCategory.EARNINGS, NewsCategory.REGULATORY]
    finally:
        queue.shutdown()


@pytest.mark.parametrize("raise_error", [False, True])
def test_unavailable_worker_results_retain_context_and_expiry(raise_error):
    def reviewer(*_args, **_kwargs):
        if raise_error:
            raise RuntimeError("provider exploded")
        return unavailable("provider_down")

    queue = AsyncReviewQueue(reviewer)
    try:
        classification = _stub_classification("h")
        expiry = datetime.now(timezone.utc) + timedelta(seconds=30)
        queue.submit(
            "unavailable", {}, "raw", "BULL",
            pre_classifications=[classification], expires_at=expiry,
        )
        result = _wait_for(queue, "unavailable", {"UNAVAILABLE"}).review
        assert result.expires_at == expiry
        assert result.classification_count == 1
        assert result.classification_context_sha256
        assert result.source_references[0][0] == classification.source_ref
    finally:
        queue.shutdown()


def test_mixed_source_validity_bounds_queue_expiry_and_stale_is_rejected():
    clock = [datetime(2026, 9, 20, 10, 0, tzinfo=timezone.utc)]
    reviewer = MagicMock(return_value=Review(Verdict.APPROVE, conviction=80))
    queue = AsyncReviewQueue(reviewer, now=lambda: clock[0])
    try:
        base = _stub_classification("h")
        early = replace(base, source_valid_until=clock[0] + timedelta(seconds=5))
        later = replace(base, title_hash="h2", source_valid_until=clock[0] + timedelta(seconds=20))
        queue.submit(
            "mixed", {}, "raw", "BULL",
            pre_classifications=[later, early],
            expires_at=clock[0] + timedelta(seconds=30),
        )
        ready = _wait_for(queue, "mixed", {"READY"})
        assert ready.review.expires_at == clock[0] + timedelta(seconds=5)

        stale = replace(base, source_valid_until=clock[0])
        rejected = queue.submit(
            "stale", {}, "raw", "BULL", pre_classifications=[stale],
            expires_at=clock[0] + timedelta(seconds=30),
        )
        assert rejected.state == "EXPIRED"
        assert reviewer.call_count == 1
    finally:
        queue.shutdown()
