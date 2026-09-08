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


def test_open_circuit_cancels_already_queued_reviews_before_provider_dispatch():
    release = Event()
    calls = 0

    def reviewer(*_args):
        nonlocal calls
        calls += 1
        if calls == 1:
            release.wait(timeout=1)
        return unavailable("provider_down")

    queue = AsyncReviewQueue(reviewer, max_pending=2, failure_limit=1, cooldown_seconds=60)
    try:
        expiry = datetime.now(timezone.utc) + timedelta(minutes=1)
        assert queue.submit("first", {}, "", "UNKNOWN", expires_at=expiry).state == "QUEUED"
        assert queue.submit("second", {}, "", "UNKNOWN", expires_at=expiry).state == "QUEUED"
        release.set()
        assert _wait_for(queue, "first", {"UNAVAILABLE"}).reason == "provider_down"
        assert _wait_for(queue, "second", {"CIRCUIT_OPEN"}).reason == "provider_failures"
        assert calls == 1
    finally:
        queue.shutdown()


def test_terminal_state_retention_is_bounded_and_expires():
    clock = [datetime(2026, 9, 7, tzinfo=timezone.utc)]
    queue = AsyncReviewQueue(
        lambda *_args: unavailable("provider_down"), max_pending=2,
        state_ttl_seconds=1, max_retained_states=2, now=lambda: clock[0],
    )
    try:
        expired = queue.submit("expired", {}, "", "UNKNOWN", expires_at=clock[0])
        assert expired.state == "EXPIRED" and queue.status("expired") is not None
        clock[0] += timedelta(seconds=2)
        queue.snapshot()
        assert queue.status("expired") is None
    finally:
        queue.shutdown()


def test_daily_budget_survives_worker_restart(tmp_path):
    state = str(tmp_path / "ai-budget.json")
    expiry = datetime.now(timezone.utc) + timedelta(minutes=1)
    first = AsyncReviewQueue(lambda *_args: unavailable("offline"), max_requests_per_day=1, budget_state_path=state)
    try:
        assert first.submit("one", {}, "", "UNKNOWN", expires_at=expiry).state == "QUEUED"
    finally:
        first.shutdown()
    second = AsyncReviewQueue(lambda *_args: unavailable("offline"), max_requests_per_day=1, budget_state_path=state)
    try:
        assert second.submit("two", {}, "", "UNKNOWN", expires_at=expiry).state == "BUDGET_EXHAUSTED"
    finally:
        second.shutdown()


def test_unreadable_durable_budget_fails_closed_for_optional_ai(tmp_path):
    state = tmp_path / "ai-budget.json"
    state.write_text("not-json", encoding="utf-8")
    queue = AsyncReviewQueue(
        lambda *_args: unavailable("offline"),
        budget_state_path=str(state),
    )
    try:
        expiry = datetime.now(timezone.utc) + timedelta(minutes=1)
        assert queue.submit("blocked", {}, "", "UNKNOWN", expires_at=expiry).state == "BUDGET_STATE_UNAVAILABLE"
    finally:
        queue.shutdown()
