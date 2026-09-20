"""Bounded, non-blocking optional-AI review worker.

The queue is intentionally transport-agnostic: deterministic signal, risk and
alert paths receive their own decision immediately.  A model opinion is an
annotation that may arrive later, never authority to change a numeric trade
field or an already-created execution instruction.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from queue import Empty, Full, Queue
from threading import Event, RLock, Thread
from typing import Callable, List, Optional

from advisory import Review, unavailable


@dataclass(frozen=True)
class ReviewSubmission:
    key: str
    state: str
    review: Optional[Review] = None
    reason: str = ""


@dataclass(frozen=True)
class _Task:
    """[WORKFLOW-I.4.D 2026-09-14] Internal queue task. The
    optional ``pre_classifications`` field carries the bounded
    classifier's output through the queue so the async reviewer
    can render the CLASSIFIED SENTIMENT DATA section in the
    prompt. When None (the default, and every pre-I.4.D
    caller's path), the verdict pipeline consumes raw
    sentiment_text exactly as before.

    The field is frozen (the dataclass is frozen) and forwarded
    by reference -- the queue does not mutate the list. The caller
    binds its classification-context digest into ``key`` so changed
    evidence cannot retrieve an older review.
    """
    key: str
    signal: dict
    sentiment: str
    regime: str
    expires_at: datetime
    pre_classifications: tuple = ()
    classification_context_sha256: Optional[str] = None


def _classification_digest(pre_classifications) -> Optional[str]:
    if pre_classifications is None:
        return None
    from news_classifier import classification_context_sha256
    return classification_context_sha256(pre_classifications)


def _bound_expiry(expires_at: datetime, pre_classifications, now: datetime) -> datetime:
    if not pre_classifications:
        return expires_at
    bounds = [expires_at]
    for classification in pre_classifications:
        bound = classification.source_valid_until
        if bound is None:
            bound = classification.classified_at or now
        if bound.tzinfo is None or bound.utcoffset() is None:
            bound = now
        bounds.append(bound.astimezone(timezone.utc))
    return min(bounds)


def _attach_task_context(review: Review, task: _Task, expires_at: datetime) -> Review:
    references = tuple(dict.fromkeys(
        (
            c.source_ref,
            c.source_url,
            c.published_at.isoformat() if c.published_at else "",
        )
        for c in task.pre_classifications
        if c.source_ref or c.source_url or c.published_at
    ))
    return replace(
        review,
        classification_context_sha256=task.classification_context_sha256,
        classification_count=len(task.pre_classifications),
        source_references=references,
        expires_at=expires_at,
    )


class AsyncReviewQueue:
    """One bounded worker with cache, expiry, circuit breaker and daily cap."""

    def __init__(
        self,
        reviewer: Callable[..., Review],  # [WORKFLOW-I.4.D 2026-09-14] widened signature
        *,
        max_pending: int = 16,
        max_requests_per_day: int = 40,
        cache_ttl_seconds: float = 300,
        failure_limit: int = 3,
        cooldown_seconds: float = 300,
        state_ttl_seconds: float = 900,
        max_retained_states: int | None = None,
        budget_state_path: str | None = None,
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
        self._pending_context: dict[str, Optional[str]] = {}
        self._cache: dict[str, tuple[Review, datetime, Optional[str]]] = {}
        self._states: dict[str, ReviewSubmission] = {}
        self._state_recorded_at: dict[str, datetime] = {}
        self._review_expires_at: dict[str, datetime] = {}
        self._budget_state_path = Path(budget_state_path) if budget_state_path else None
        self._budget_state_available = True
        self._requests_by_day: dict[str, int] = self._load_budget_state()
        self._consecutive_failures = 0
        self._circuit_open_until: Optional[datetime] = None
        # [WORKFLOW-I I3 2026-09-13] Usefulness-instrumentation counters.
        # These are bounded by ``_cleanup_locked`` (each list capped at
        # ``max_retained_states``) so a long-running queue cannot leak
        # memory. ``response_seconds`` captures wall-clock duration of
        # the underlying model call so operators can see mean/p95
        # latency. ``verdict_counts`` lets them verify the queue's
        # APPROVE/REJECT distribution is sensible (e.g. an AI that
        # always vetoes is a regression). ``cache_hits`` and
        # ``cache_misses`` separate "the cache served it" from
        # "we paid a model call".
        self._response_seconds: list[float] = []
        self._verdict_counts: dict[str, int] = {
            "APPROVE": 0, "APPROVE_WITH_CONCERNS": 0,
            "REVIEW_UNAVAILABLE": 0, "REJECT": 0,
        }
        self._cache_hits: int = 0
        self._cache_misses: int = 0
        self._circuit_opens: int = 0
        self._last_response_seconds: Optional[float] = None
        self._last_completed_at: Optional[datetime] = None
        self._stop = Event()
        self._worker = Thread(target=self._run, name="optional-ai-review", daemon=True)
        self._worker.start()

    def submit(
        self, key: str, signal: dict, sentiment: str, regime: str, *,
        expires_at: datetime,
        pre_classifications: Optional[List["ClassificationResult"]] = None,
    ) -> ReviewSubmission:
        """Queue one immutable decision/event review without blocking callers.

        [WORKFLOW-I.4.D 2026-09-14] Optional ``pre_classifications``:
        forwarded to the reviewer when the queued task runs.
        ``None`` (the default, every pre-I.4.D caller's path)
        preserves the existing verdict-prompt shape (the
        "no pre-classifications supplied" placeholder renders
        and raw sentiment_text flows through unchanged). The
        list is captured by reference; the queue does not
        mutate it.
        """
        if not isinstance(key, str) or not key.strip():
            raise ValueError("review key is required")
        if expires_at.tzinfo is None or expires_at.utcoffset() is None:
            raise ValueError("review expiry must be timezone-aware")
        now = self._now()
        classifications_tuple = (
            tuple(pre_classifications) if pre_classifications else ()
        )
        classification_digest = _classification_digest(pre_classifications)
        expires_at = _bound_expiry(expires_at, classifications_tuple, now)
        if expires_at <= now:
            return self._remember(ReviewSubmission(key, "EXPIRED", reason="deadline_elapsed"))
        with self._lock:
            self._cleanup_locked(now)
            cached = self._cache.get(key)
            if cached is not None and cached[2] == classification_digest:
                valid_until = min(cached[1], expires_at)
                cached_review = replace(cached[0], expires_at=valid_until)
                self._cache[key] = (
                    cached_review, valid_until, classification_digest,
                )
                self._review_expires_at[key] = valid_until
                # [WORKFLOW-I I3 2026-09-13] Track cache hit.
                self._cache_hits += 1
                return self._remember(
                    ReviewSubmission(key, "CACHED", review=cached_review)
                )
            # [WORKFLOW-I I3 2026-09-13] Track cache miss. Anything
            # that falls through to the queue path is a miss.
            self._cache_misses += 1
            if key in self._pending:
                reason = (
                    "already_queued"
                    if self._pending_context.get(key) == classification_digest
                    else "classification_context_conflict"
                )
                return self._remember(ReviewSubmission(key, "PENDING", reason=reason))
            if len(self._pending) >= self._max_pending:
                return self._remember(ReviewSubmission(key, "QUEUE_FULL", reason="bounded_queue"))
            if self._circuit_open_until is not None and now < self._circuit_open_until:
                return self._remember(ReviewSubmission(key, "CIRCUIT_OPEN", reason="provider_failures"))
            if not self._budget_state_available:
                return self._remember(ReviewSubmission(key, "BUDGET_STATE_UNAVAILABLE", reason="durable_quota"))
            day = now.date().isoformat()
            if self._requests_by_day.get(day, 0) >= self._max_requests_per_day:
                return self._remember(ReviewSubmission(key, "BUDGET_EXHAUSTED", reason="daily_request_budget"))
            # [WORKFLOW-I.4.D 2026-09-14] The classifications tuple
            # is frozen (so the in-queue task cannot be mutated)
            # and carries the operator's per-call pre_classifications
            # through the queue to the reviewer. ``None`` becomes an
            # empty tuple so the reviewer signature is uniform.
            task = _Task(
                key, deepcopy(dict(signal)), str(sentiment), str(regime),
                expires_at, classifications_tuple, classification_digest,
            )
            self._requests_by_day[day] = self._requests_by_day.get(day, 0) + 1
            if not self._persist_budget_state():
                self._requests_by_day[day] -= 1
                return self._remember(ReviewSubmission(key, "BUDGET_STATE_UNAVAILABLE", reason="durable_quota"))
            try:
                self._queue.put_nowait(task)
            except Full:
                self._requests_by_day[day] -= 1
                self._persist_budget_state()
                return self._remember(ReviewSubmission(key, "QUEUE_FULL", reason="bounded_queue"))
            self._pending.add(key)
            self._pending_context[key] = classification_digest
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

    def usefulness_snapshot(self) -> dict[str, object]:
        """[WORKFLOW-I I3 2026-09-13] Bounded usefulness-instrumentation
        snapshot for operator dashboards and CLI tooling.

        Returns the raw numbers an operator needs to evaluate
        annotation usefulness separately from trading outcome
        (per plan §13). Does NOT invent a "did this help" metric;
        that requires operator-supplied ground truth.

        Fields
        ------
        total_completed_reviews
            Reviews that ran through the worker thread (cache misses
            served by the model). Excludes cache hits, queue-full
            rejects, and circuit-open rejects.
        verdict_counts
            Distribution of verdicts across the four buckets
            (APPROVE, APPROVE_WITH_CONCERNS, REVIEW_UNAVAILABLE,
            REJECT). Useful to detect "AI always vetoes" regressions.
        cache_hits / cache_misses
            Counts since the queue was constructed. ``cache_hit_rate``
            = ``hits / (hits + misses)`` when both are non-zero.
        circuit_opens
            Number of closed->open circuit transitions since startup.
            Operators correlate this with provider outage windows.
        response_seconds_mean / p95 / last
            Aggregates across the bounded ``_response_seconds``
            buffer (capped at ``max_retained_states``). ``last`` is
            the most recent value.
        last_completed_at
            UTC datetime of the most recent completion (None if
            the queue has never completed a review).
        """
        with self._lock:
            self._cleanup_locked(self._now())
            n_completed = sum(self._verdict_counts.values())
            samples = list(self._response_seconds)
            if samples:
                mean = sum(samples) / len(samples)
                sorted_samples = sorted(samples)
                # p95: nearest-rank with linear interpolation.
                idx = max(0, min(len(sorted_samples) - 1,
                                  int(round(0.95 * (len(sorted_samples) - 1)))))
                p95 = sorted_samples[idx]
            else:
                mean = None
                p95 = None
            total_lookups = self._cache_hits + self._cache_misses
            cache_hit_rate = (
                self._cache_hits / total_lookups if total_lookups else None
            )
            return {
                "total_completed_reviews": n_completed,
                "verdict_counts": dict(self._verdict_counts),
                "cache_hits": self._cache_hits,
                "cache_misses": self._cache_misses,
                "cache_hit_rate": cache_hit_rate,
                "circuit_opens": self._circuit_opens,
                "response_seconds_mean": mean,
                "response_seconds_p95": p95,
                "response_seconds_last": self._last_response_seconds,
                "last_completed_at": (
                    self._last_completed_at.isoformat()
                    if self._last_completed_at is not None else None
                ),
            }

    def shutdown(self, timeout: float = 1.0) -> None:
        self._stop.set()
        self._worker.join(timeout=timeout)

    def _remember(self, submission: ReviewSubmission) -> ReviewSubmission:
        self._states[submission.key] = submission
        self._state_recorded_at[submission.key] = self._now()
        return submission

    def _load_budget_state(self) -> dict[str, int]:
        if self._budget_state_path is None:
            return {}
        try:
            if not self._budget_state_path.exists():
                return {}
            raw = json.loads(self._budget_state_path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise ValueError("budget state must be an object")
            return {str(day): int(count) for day, count in raw.items() if int(count) >= 0}
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            self._budget_state_available = False
            return {}

    def _persist_budget_state(self) -> bool:
        if self._budget_state_path is None:
            return True
        try:
            self._budget_state_path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self._budget_state_path.with_suffix(self._budget_state_path.suffix + ".tmp")
            temporary.write_text(json.dumps(self._requests_by_day, sort_keys=True), encoding="utf-8")
            temporary.replace(self._budget_state_path)
            self._budget_state_available = True
            return True
        except OSError:
            # The optional annotation worker fails closed; the deterministic
            # signal and risk path does not depend on it.
            self._budget_state_available = False
            return False

    def _cleanup_locked(self, now: datetime) -> None:
        self._cache = {key: value for key, value in self._cache.items() if value[1] > now}
        for key, deadline in list(self._review_expires_at.items()):
            if deadline <= now:
                state = self._states.get(key)
                if state is not None and state.state in {"READY", "CACHED"}:
                    self._remember(ReviewSubmission(key, "EXPIRED", reason="review_validity_elapsed"))
                self._review_expires_at.pop(key, None)
        self._requests_by_day = {now.date().isoformat(): self._requests_by_day.get(now.date().isoformat(), 0)}
        if self._budget_state_available:
            self._persist_budget_state()
        for key, recorded_at in list(self._state_recorded_at.items()):
            if key not in self._pending and now - recorded_at > timedelta(seconds=self._state_ttl_seconds):
                self._states.pop(key, None)
                self._state_recorded_at.pop(key, None)
                self._review_expires_at.pop(key, None)
        if len(self._states) > self._max_retained_states:
            removable = sorted(
                (stamp, key) for key, stamp in self._state_recorded_at.items() if key not in self._pending
            )[:len(self._states) - self._max_retained_states]
            for _stamp, key in removable:
                self._states.pop(key, None)
                self._state_recorded_at.pop(key, None)
                self._review_expires_at.pop(key, None)
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
                        self._pending_context.pop(task.key, None)
                        self._remember(ReviewSubmission(task.key, "EXPIRED", reason="deadline_elapsed"))
                    continue
                with self._lock:
                    self._cleanup_locked(now)
                    if self._circuit_open_until is not None and now < self._circuit_open_until:
                        self._pending.discard(task.key)
                        self._pending_context.pop(task.key, None)
                        self._remember(ReviewSubmission(task.key, "CIRCUIT_OPEN", reason="provider_failures"))
                        continue
                try:
                    # [WORKFLOW-I.4.D 2026-09-14] Forward the
                    # queued pre_classifications to the reviewer
                    # when the reviewer accepts the
                    # ``pre_classifications`` keyword. Older
                    # reviewers (e.g. lambdas in tests) that don't
                    # accept the keyword are invoked with the
                    # original 3-arg shape so this queue stays
                    # backwards-compatible with the existing test
                    # suite.
                    import inspect
                    reviewer_params = inspect.signature(self._reviewer).parameters
                    accepts_pre_cls = (
                        "pre_classifications" in reviewer_params
                    )
                    if accepts_pre_cls and task.pre_classifications:
                        review = self._reviewer(
                            task.signal,
                            task.sentiment,
                            task.regime,
                            pre_classifications=list(task.pre_classifications),
                        )
                    elif accepts_pre_cls:
                        # Pre-classifications empty -> call with
                        # None so the renderer's "no pre-classifications
                        # supplied" placeholder still triggers.
                        review = self._reviewer(
                            task.signal,
                            task.sentiment,
                            task.regime,
                            pre_classifications=None,
                        )
                    else:
                        # Backwards-compatible: 3-arg call shape.
                        review = self._reviewer(
                            task.signal,
                            task.sentiment,
                            task.regime,
                        )
                except Exception:
                    review = unavailable("worker_exception")
                completed = self._now()
                review = _attach_task_context(review, task, task.expires_at)
                # [WORKFLOW-I I3 2026-09-13] Capture the model's response
                # time and verdict. ``review.response_seconds`` is the
                # producer-attached wall-clock duration (set by
                # ``analyze_with_minimax``); we use it when available,
                # otherwise fall back to ``(completed - now)``. Both
                # are non-negative.
                response_seconds = review.response_seconds
                if response_seconds is None:
                    response_seconds = max(0.0, (completed - now).total_seconds())
                verdict_name = review.verdict.name if hasattr(review.verdict, "name") else str(review.verdict)
                with self._lock:
                    self._pending.discard(task.key)
                    self._pending_context.pop(task.key, None)
                    # [WORKFLOW-I I3 2026-09-13] Track response time + last.
                    self._response_seconds.append(response_seconds)
                    if len(self._response_seconds) > self._max_retained_states:
                        self._response_seconds = self._response_seconds[-self._max_retained_states:]
                    self._last_response_seconds = response_seconds
                    self._last_completed_at = completed
                    # Track verdict distribution.
                    self._verdict_counts[verdict_name] = (
                        self._verdict_counts.get(verdict_name, 0) + 1
                    )
                    if completed >= task.expires_at:
                        expired_review = _attach_task_context(
                            unavailable("review_completed_late"),
                            task,
                            task.expires_at,
                        )
                        self._remember(ReviewSubmission(
                            task.key, "EXPIRED", review=expired_review,
                            reason="review_completed_late",
                        ))
                    elif review.available:
                        self._consecutive_failures = 0
                        valid_until = min(task.expires_at, completed + timedelta(seconds=self._cache_ttl_seconds))
                        review = replace(review, expires_at=valid_until)
                        self._cache[task.key] = (
                            review,
                            valid_until,
                            task.classification_context_sha256,
                        )
                        self._review_expires_at[task.key] = valid_until
                        self._remember(ReviewSubmission(task.key, "READY", review=review))
                    else:
                        self._consecutive_failures += 1
                        if self._consecutive_failures >= self._failure_limit:
                            # [WORKFLOW-I I3 2026-09-13] Track circuit-open
                            # transitions. Counted only when the circuit
                            # transitions from closed to open (i.e. when
                            # the threshold is crossed, not on every
                            # subsequent failure inside an already-open
                            # circuit).
                            self._circuit_opens += 1
                            self._circuit_open_until = (
                                completed + timedelta(seconds=self._cooldown_seconds)
                            )
                        self._remember(ReviewSubmission(task.key, "UNAVAILABLE", review=review,
                                                        reason=review.reason))
            finally:
                self._queue.task_done()
