"""Bounded, non-blocking optional-AI review worker.

The queue is intentionally transport-agnostic: deterministic signal, risk and
alert paths receive their own decision immediately.  A model opinion is an
annotation that may arrive later, never authority to change a numeric trade
field or an already-created execution instruction.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from queue import Empty, Full, Queue
from threading import Event, RLock, Thread
from typing import Callable, Optional

from advisory import Review, unavailable


@dataclass(frozen=True)
class ReviewSubmission:
    key: str
    state: str
    review: Optional[Review] = None
    reason: str = ""


@dataclass(frozen=True)
class _Task:
    key: str
    signal: dict
    sentiment: str
    regime: str
    expires_at: datetime


class AsyncReviewQueue:
    """One bounded worker with cache, expiry, circuit breaker and daily cap."""

    def __init__(
        self,
        reviewer: Callable[[dict, str, str], Review],
        *,
        max_pending: int = 16,
        max_requests_per_day: int = 40,
        cache_ttl_seconds: float = 300,
        failure_limit: int = 3,
        cooldown_seconds: float = 300,
        state_ttl_seconds: float = 900,
        max_retained_states: int | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        if min(max_pending, max_requests_per_day, failure_limit) < 1:
            raise ValueError("queue limits must be positive")
        if cache_ttl_seconds <= 0 or cooldown_seconds <= 0 or state_ttl_seconds <= 0:
            raise ValueError("queue durations must be positive")
        self._reviewer = reviewer
        self._queue: Queue[_Task] = Queue(maxsize=max_pending)
        self._max_pending = max_pending
        self._max_requests_per_day = max_requests_per_day
        self._cache_ttl_seconds = cache_ttl_seconds
        self._failure_limit = failure_limit
        self._cooldown_seconds = cooldown_seconds
        self._state_ttl_seconds = state_ttl_seconds
        self._max_retained_states = max_retained_states or max_pending * 8
        if self._max_retained_states < max_pending:
            raise ValueError("max_retained_states must cover pending work")
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._lock = RLock()
        self._pending: set[str] = set()
        self._cache: dict[str, tuple[Review, datetime]] = {}
        self._states: dict[str, ReviewSubmission] = {}
        self._state_recorded_at: dict[str, datetime] = {}
        self._requests_by_day: dict[str, int] = {}
        self._consecutive_failures = 0
        self._circuit_open_until: Optional[datetime] = None
        self._stop = Event()
        self._worker = Thread(target=self._run, name="optional-ai-review", daemon=True)
        self._worker.start()

    def submit(
        self, key: str, signal: dict, sentiment: str, regime: str, *, expires_at: datetime,
    ) -> ReviewSubmission:
        """Queue one immutable decision/event review without blocking callers."""
        if not isinstance(key, str) or not key.strip():
            raise ValueError("review key is required")
        if expires_at.tzinfo is None or expires_at.utcoffset() is None:
            raise ValueError("review expiry must be timezone-aware")
        now = self._now()
        if expires_at <= now:
            return self._remember(ReviewSubmission(key, "EXPIRED", reason="deadline_elapsed"))
        with self._lock:
            self._cleanup_locked(now)
            cached = self._cache.get(key)
            if cached is not None:
                return self._remember(ReviewSubmission(key, "CACHED", review=cached[0]))
            if key in self._pending:
                return self._remember(ReviewSubmission(key, "PENDING", reason="already_queued"))
            if len(self._pending) >= self._max_pending:
                return self._remember(ReviewSubmission(key, "QUEUE_FULL", reason="bounded_queue"))
            if self._circuit_open_until is not None and now < self._circuit_open_until:
                return self._remember(ReviewSubmission(key, "CIRCUIT_OPEN", reason="provider_failures"))
            day = now.date().isoformat()
            if self._requests_by_day.get(day, 0) >= self._max_requests_per_day:
                return self._remember(ReviewSubmission(key, "BUDGET_EXHAUSTED", reason="daily_request_budget"))
            task = _Task(key, dict(signal), str(sentiment), str(regime), expires_at)
            try:
                self._queue.put_nowait(task)
            except Full:
                return self._remember(ReviewSubmission(key, "QUEUE_FULL", reason="bounded_queue"))
            self._pending.add(key)
            self._requests_by_day[day] = self._requests_by_day.get(day, 0) + 1
            return self._remember(ReviewSubmission(key, "QUEUED"))

    def status(self, key: str) -> Optional[ReviewSubmission]:
        with self._lock:
            self._cleanup_locked(self._now())
            return self._states.get(key)

    def snapshot(self) -> dict[str, int | str]:
        """Return bounded health counters, never review content or prompts."""
        with self._lock:
            now = self._now()
            self._cleanup_locked(now)
            day = now.date().isoformat()
            circuit_open = (
                self._circuit_open_until is not None and now < self._circuit_open_until
            )
            return {
                "pending": len(self._pending),
                "cached": len(self._cache),
                "daily_requests": self._requests_by_day.get(day, 0),
                "daily_budget": self._max_requests_per_day,
                "max_pending": self._max_pending,
                "circuit_state": "OPEN" if circuit_open else "CLOSED",
            }

    def shutdown(self, timeout: float = 1.0) -> None:
        self._stop.set()
        self._worker.join(timeout=timeout)

    def _remember(self, submission: ReviewSubmission) -> ReviewSubmission:
        self._states[submission.key] = submission
        self._state_recorded_at[submission.key] = self._now()
        return submission

    def _cleanup_locked(self, now: datetime) -> None:
        self._cache = {key: value for key, value in self._cache.items() if value[1] > now}
        self._requests_by_day = {now.date().isoformat(): self._requests_by_day.get(now.date().isoformat(), 0)}
        for key, recorded_at in list(self._state_recorded_at.items()):
            if key not in self._pending and now - recorded_at > timedelta(seconds=self._state_ttl_seconds):
                self._states.pop(key, None)
                self._state_recorded_at.pop(key, None)
        if len(self._states) > self._max_retained_states:
            removable = sorted(
                (stamp, key) for key, stamp in self._state_recorded_at.items() if key not in self._pending
            )[:len(self._states) - self._max_retained_states]
            for _stamp, key in removable:
                self._states.pop(key, None)
                self._state_recorded_at.pop(key, None)
        if self._circuit_open_until is not None and now >= self._circuit_open_until:
            self._circuit_open_until = None
            self._consecutive_failures = 0

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                task = self._queue.get(timeout=0.05)
            except Empty:
                continue
            try:
                now = self._now()
                if task.expires_at <= now:
                    with self._lock:
                        self._pending.discard(task.key)
                        self._remember(ReviewSubmission(task.key, "EXPIRED", reason="deadline_elapsed"))
                    continue
                with self._lock:
                    self._cleanup_locked(now)
                    if self._circuit_open_until is not None and now < self._circuit_open_until:
                        self._pending.discard(task.key)
                        self._remember(ReviewSubmission(task.key, "CIRCUIT_OPEN", reason="provider_failures"))
                        continue
                try:
                    review = self._reviewer(task.signal, task.sentiment, task.regime)
                except Exception:
                    review = unavailable("worker_exception")
                completed = self._now()
                with self._lock:
                    self._pending.discard(task.key)
                    if completed > task.expires_at:
                        self._remember(ReviewSubmission(task.key, "EXPIRED", reason="review_completed_late"))
                    elif review.available:
                        self._consecutive_failures = 0
                        self._cache[task.key] = (
                            review,
                            completed + timedelta(seconds=self._cache_ttl_seconds),
                        )
                        self._remember(ReviewSubmission(task.key, "READY", review=review))
                    else:
                        self._consecutive_failures += 1
                        if self._consecutive_failures >= self._failure_limit:
                            self._circuit_open_until = (
                                completed + timedelta(seconds=self._cooldown_seconds)
                            )
                        self._remember(ReviewSubmission(task.key, "UNAVAILABLE", review=review,
                                                        reason=review.reason))
            finally:
                self._queue.task_done()
