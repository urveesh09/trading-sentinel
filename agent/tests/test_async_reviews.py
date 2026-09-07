from datetime import datetime, timedelta, timezone
from threading import Event
import time

from advisory import Review, Verdict, unavailable
from async_reviews import AsyncReviewQueue


def _wait_for(queue: AsyncReviewQueue, key: str, states: set[str]) -> object:
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        status = queue.status(key)
        if status is not None and status.state in states:
            return status
        time.sleep(.01)
    raise AssertionError(f"timed out waiting for {key}")


def test_queue_returns_immediately_then_caches_completed_annotation():
    calls = 0

    def reviewer(*_args):
        nonlocal calls
        calls += 1
        return Review(Verdict.APPROVE, conviction=80, payload={"pitch": "bounded"})

    queue = AsyncReviewQueue(reviewer, cache_ttl_seconds=60)
    try:
        expiry = datetime.now(timezone.utc) + timedelta(minutes=1)
        assert queue.submit("decision:event", {"ticker": "SYNTH"}, "news", "BULL", expires_at=expiry).state == "QUEUED"
        ready = _wait_for(queue, "decision:event", {"READY"})
        assert ready.review and ready.review.conviction == 80
        cached = queue.submit("decision:event", {"ticker": "SYNTH"}, "news", "BULL", expires_at=expiry)
        assert cached.state == "CACHED" and calls == 1
    finally:
        queue.shutdown()


def test_queue_is_bounded_and_circuit_breaker_is_explicit():
    release = Event()

    def slow_failure(*_args):
        release.wait(timeout=1)
        return unavailable("provider_down")

    queue = AsyncReviewQueue(slow_failure, max_pending=1, failure_limit=1, cooldown_seconds=60)
    try:
        expiry = datetime.now(timezone.utc) + timedelta(minutes=1)
        assert queue.submit("one", {}, "", "UNKNOWN", expires_at=expiry).state == "QUEUED"
        assert queue.submit("two", {}, "", "UNKNOWN", expires_at=expiry).state == "QUEUE_FULL"
        release.set()
        assert _wait_for(queue, "one", {"UNAVAILABLE"}).reason == "provider_down"
        assert queue.submit("three", {}, "", "UNKNOWN", expires_at=expiry).state == "CIRCUIT_OPEN"
        assert queue.snapshot()["circuit_state"] == "OPEN"
        assert queue.snapshot()["pending"] == 0
    finally:
        queue.shutdown()


def test_late_review_is_discarded_not_cached_or_reused():
    release = Event()

    def slow_success(*_args):
        release.wait(timeout=1)
        return Review(Verdict.APPROVE, conviction=75)

    queue = AsyncReviewQueue(slow_success)
    try:
        expiry = datetime.now(timezone.utc) + timedelta(milliseconds=40)
        assert queue.submit("late", {}, "", "UNKNOWN", expires_at=expiry).state == "QUEUED"
        time.sleep(.06)
        release.set()
        assert _wait_for(queue, "late", {"EXPIRED"}).reason == "review_completed_late"
    finally:
        queue.shutdown()
