"""[WORKFLOW-I I3 2026-09-13] Optional-AI usefulness-instrumentation acceptance.

Closes I3 of workstream I per ``docs/NEXT_AGENT_PLAN.md`` section 13.
Satisfies the §13 mandate: *"Evaluate annotation usefulness
separately from trading outcome."* Phase I3 instruments the
existing AsyncReviewQueue; it does NOT invent a "did this help"
threshold (that requires operator-supplied ground truth).

Coverage
--------
1. ``usefulness_snapshot`` exposes the documented fields.
2. Cache hits/misses are tracked on submit; cache hit rate
   computed correctly.
3. Verdict counts increment per review.
4. Response-seconds mean / p95 / last match recorded values.
5. Circuit-open transitions are counted once per transition.
6. The snapshot is bounded -- never returns review content or
   prompt text.
7. CLI ``print-config`` runs without I/O.
8. CLI ``read-snapshot`` reads + pretty-prints a JSON file.
9. CLI exits 0 on success, 1 on I/O error.
10. Snapshot is JSON-serialisable (dashboard / log pipeline).
"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from advisory import (
    Review,
    Verdict,
    unavailable,
)


# ---- helper builders ------------------------------------------------------

class _FakeReview(Review):
    """``Review`` is frozen, so we cannot subclass-mutate. Use the
    public constructor via ``Review(...)`` and provide a
    ``response_seconds`` value via the dataclass.

    For tests that need a Review with provenance, this helper
    builds one with the desired ``verdict`` and ``response_seconds``.
    """
    @classmethod
    def make(cls, *, verdict: Verdict, response_seconds: float = 1.0,
              conviction: int = 70, reason: str = "") -> Review:
        now = datetime.now(timezone.utc)
        return Review(
            verdict=verdict,
            conviction=conviction,
            reason=reason,
            model="MiniMax-M3",
            base_url="https://api.minimax.io/v1",
            prompt_version="v1",
            started_at=now - timedelta(seconds=response_seconds),
            completed_at=now,
            response_seconds=response_seconds,
        )


def _make_queue(reviewer=None, **kwargs):
    """Build a queue with a controllable reviewer and a controllable clock.

    Returns ``(queue, advance_time)`` where ``advance_time(seconds)``
    moves the queue's clock forward by ``seconds``.
    """
    from async_reviews import AsyncReviewQueue
    current = {"t": datetime(2026, 9, 13, 10, 0, 0, tzinfo=timezone.utc)}
    def now_fn():
        return current["t"]
    if reviewer is None:
        reviewer = MagicMock(return_value=_FakeReview.make(verdict=Verdict.APPROVE))
    queue = AsyncReviewQueue(
        reviewer,
        now=now_fn,
        max_pending=kwargs.get("max_pending", 4),
        max_requests_per_day=kwargs.get("max_requests_per_day", 10),
        cache_ttl_seconds=kwargs.get("cache_ttl_seconds", 60),
        failure_limit=kwargs.get("failure_limit", 2),
        cooldown_seconds=kwargs.get("cooldown_seconds", 30),
        state_ttl_seconds=kwargs.get("state_ttl_seconds", 60),
    )
    def advance(seconds: float):
        current["t"] = current["t"] + timedelta(seconds=seconds)
    return queue, advance


def _drain(queue):
    """Wait for the queue's worker to finish any pending task."""
    import time
    for _ in range(100):
        snap = queue.snapshot()
        if snap["pending"] == 0:
            return
        time.sleep(0.01)


# ---- (1) snapshot shape ---------------------------------------------------

class TestUsefulnessSnapshotShape:
    def test_snapshot_exposes_required_fields(self) -> None:
        """The snapshot is a dict with the documented bounded keys.
        All values are JSON-serialisable.
        """
        q, _ = _make_queue()
        try:
            snap = q.usefulness_snapshot()
            assert "total_completed_reviews" in snap
            assert "verdict_counts" in snap
            assert "cache_hits" in snap
            assert "cache_misses" in snap
            assert "cache_hit_rate" in snap
            assert "circuit_opens" in snap
            assert "response_seconds_mean" in snap
            assert "response_seconds_p95" in snap
            assert "response_seconds_last" in snap
            assert "last_completed_at" in snap
            # All values must be JSON-serialisable.
            json.dumps(snap)
        finally:
            q.shutdown()

    def test_initial_snapshot_has_zero_counts(self) -> None:
        q, _ = _make_queue()
        try:
            snap = q.usefulness_snapshot()
            assert snap["total_completed_reviews"] == 0
            assert snap["cache_hits"] == 0
            assert snap["cache_misses"] == 0
            assert snap["cache_hit_rate"] is None
            assert snap["circuit_opens"] == 0
            assert snap["response_seconds_mean"] is None
            assert snap["response_seconds_p95"] is None
            assert snap["response_seconds_last"] is None
            assert snap["last_completed_at"] is None
        finally:
            q.shutdown()


# ---- (2) cache hit / miss tracking ---------------------------------------

class TestCacheTracking:
    def test_cache_hit_increments(self) -> None:
        """First submit misses; second submit with same key hits."""
        from async_reviews import AsyncReviewQueue
        reviewer = MagicMock(return_value=_FakeReview.make(verdict=Verdict.APPROVE))
        q, _ = _make_queue(reviewer=reviewer)
        try:
            key = "k1"
            expiry = datetime.now(timezone.utc) + timedelta(seconds=120)
            q.submit(key, {"a": 1}, "neutral", "BULL", expires_at=expiry)
            _drain(q)
            # Submit again with same key -- should be a cache hit.
            q.submit(key, {"a": 1}, "neutral", "BULL", expires_at=expiry)
            snap = q.usefulness_snapshot()
            assert snap["cache_misses"] == 1
            assert snap["cache_hits"] == 1
            assert snap["cache_hit_rate"] == 0.5
        finally:
            q.shutdown()

    def test_cache_hit_rate_is_none_until_first_lookup(self) -> None:
        """A fresh queue with no lookups reports None for hit_rate
        (avoid division by zero)."""
        q, _ = _make_queue()
        try:
            snap = q.usefulness_snapshot()
            assert snap["cache_hit_rate"] is None
        finally:
            q.shutdown()


# ---- (3) verdict counts --------------------------------------------------

class TestVerdictCounts:
    def test_review_completion_increments_verdict(self) -> None:
        """A Review with verdict=APPROVE increments the APPROVE bucket."""
        from async_reviews import AsyncReviewQueue
        reviewer = MagicMock(return_value=_FakeReview.make(
            verdict=Verdict.APPROVE,
        ))
        q, _ = _make_queue(reviewer=reviewer)
        try:
            expiry = datetime.now(timezone.utc) + timedelta(seconds=120)
            q.submit("k1", {}, "x", "BULL", expires_at=expiry)
            _drain(q)
            snap = q.usefulness_snapshot()
            assert snap["verdict_counts"]["APPROVE"] == 1
            assert snap["total_completed_reviews"] == 1
        finally:
            q.shutdown()

    def test_unavailable_increments_review_unavailable(self) -> None:
        """A UNAVAILABLE verdict increments the REVIEW_UNAVAILABLE bucket."""
        from async_reviews import AsyncReviewQueue
        reviewer = MagicMock(return_value=unavailable("api_error"))
        q, _ = _make_queue(reviewer=reviewer)
        try:
            expiry = datetime.now(timezone.utc) + timedelta(seconds=120)
            q.submit("k1", {}, "x", "BULL", expires_at=expiry)
            _drain(q)
            snap = q.usefulness_snapshot()
            assert snap["verdict_counts"]["REVIEW_UNAVAILABLE"] == 1
        finally:
            q.shutdown()


# ---- (4) response-seconds aggregates --------------------------------------

class TestResponseSecondsAggregates:
    def test_mean_and_p95_of_completed_reviews(self) -> None:
        """Submit three reviews with known response_seconds; mean
        and p95 reflect the recorded values.
        """
        from async_reviews import AsyncReviewQueue
        # Three reviews, with response_seconds = 1, 2, 10. Mean = 13/3.
        # Sorted = [1, 2, 10]; p95 idx = round(0.95 * 2) = 2 -> 10.
        responses = [1.0, 2.0, 10.0]
        call_count = {"n": 0}

        def reviewer(signal, sentiment, regime):
            r = responses[call_count["n"]]
            call_count["n"] += 1
            return _FakeReview.make(verdict=Verdict.APPROVE, response_seconds=r)

        q, _ = _make_queue(reviewer=reviewer)
        try:
            expiry = datetime.now(timezone.utc) + timedelta(seconds=120)
            for i in range(3):
                q.submit(f"k{i}", {}, "x", "BULL", expires_at=expiry)
            _drain(q)
            snap = q.usefulness_snapshot()
            assert snap["response_seconds_mean"] == pytest.approx(13 / 3, abs=0.01)
            assert snap["response_seconds_p95"] == 10
            assert snap["response_seconds_last"] == 10.0
        finally:
            q.shutdown()

    def test_last_response_seconds_is_most_recent(self) -> None:
        """``response_seconds_last`` tracks the most recent review."""
        from async_reviews import AsyncReviewQueue
        responses = [1.0, 5.0]
        call_count = {"n": 0}

        def reviewer(signal, sentiment, regime):
            r = responses[call_count["n"]]
            call_count["n"] += 1
            return _FakeReview.make(verdict=Verdict.APPROVE, response_seconds=r)

        q, _ = _make_queue(reviewer=reviewer)
        try:
            expiry = datetime.now(timezone.utc) + timedelta(seconds=120)
            q.submit("k1", {}, "x", "BULL", expires_at=expiry)
            _drain(q)
            q.submit("k2", {}, "x", "BULL", expires_at=expiry)
            _drain(q)
            snap = q.usefulness_snapshot()
            assert snap["response_seconds_last"] == 5.0
            assert snap["last_completed_at"] is not None
        finally:
            q.shutdown()


# ---- (5) circuit-opens tracking -----------------------------------------

class TestCircuitOpensTracking:
    def test_consecutive_failures_count_one_circuit_open(self) -> None:
        """failure_limit=2 means two consecutive UNAVAILABLE reviews
        flip the circuit open exactly once.
        """
        from async_reviews import AsyncReviewQueue
        reviewer = MagicMock(return_value=unavailable("api_error"))
        q, _ = _make_queue(reviewer=reviewer, failure_limit=2)
        try:
            expiry = datetime.now(timezone.utc) + timedelta(seconds=120)
            # First failure -> counter=1, no open.
            q.submit("k1", {}, "x", "BULL", expires_at=expiry)
            _drain(q)
            # Second failure -> counter=2, circuit opens.
            q.submit("k2", {}, "x", "BULL", expires_at=expiry)
            _drain(q)
            snap = q.usefulness_snapshot()
            assert snap["circuit_opens"] == 1
        finally:
            q.shutdown()


# ---- (6) bounded: no review content ---------------------------------------

class TestBoundedSnapshot:
    def test_snapshot_does_not_include_review_payload(self) -> None:
        """The bounded snapshot must NOT carry the ``pitch`` /
        ``rationale`` / ``risks`` payload of any review. Operators
        see counts, not the model's reasoning.
        """
        from async_reviews import AsyncReviewQueue
        reviewer = MagicMock(return_value=_FakeReview.make(
            verdict=Verdict.APPROVE,
        ))
        q, _ = _make_queue(reviewer=reviewer)
        try:
            expiry = datetime.now(timezone.utc) + timedelta(seconds=120)
            q.submit("k1", {}, "x", "BULL", expires_at=expiry)
            _drain(q)
            snap = q.usefulness_snapshot()
            blob = json.dumps(snap)
            # Ensure no review content leaked.
            assert "payload" not in blob
            assert "pitch" not in blob
            assert "rationale" not in blob
        finally:
            q.shutdown()


# ---- (7) CLI print-config -------------------------------------------------

class TestCLI:
    def test_print_config_runs(self, capsys) -> None:
        from optional_ai_metrics import main
        rc = main(["print-config"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "MINIMAX_BASE_URL" in out
        assert "MINIMAX_PROMPT_VERSION" in out
        assert "MINIMAX_ASYNC_REVIEW_ENABLED" in out

    def test_read_snapshot_runs(self, tmp_path, capsys) -> None:
        from optional_ai_metrics import main
        snap_path = tmp_path / "snap.json"
        snap_path.write_text(
            json.dumps({
                "total_completed_reviews": 3,
                "verdict_counts": {"APPROVE": 2, "REJECT": 1},
                "cache_hit_rate": 0.5,
            }),
            encoding="utf-8",
        )
        rc = main(["read-snapshot", str(snap_path)])
        assert rc == 0
        out = capsys.readouterr().out
        assert "total_completed_reviews" in out
        assert "APPROVE" in out

    def test_read_snapshot_io_error_returns_1(self, tmp_path, capsys) -> None:
        from optional_ai_metrics import main
        missing = tmp_path / "no_such_file.json"
        rc = main(["read-snapshot", str(missing)])
        assert rc == 1
        err = capsys.readouterr().err
        assert "i/o error" in err.lower()

    def test_read_snapshot_json_error_returns_1(self, tmp_path, capsys) -> None:
        from optional_ai_metrics import main
        bad = tmp_path / "bad.json"
        bad.write_text("not valid json {", encoding="utf-8")
        rc = main(["read-snapshot", str(bad)])
        assert rc == 1
        err = capsys.readouterr().err
        assert "json parse error" in err.lower()

    def test_config_contract_includes_provenance_knobs(self) -> None:
        """I1 provenance knobs are documented in the bounded contract."""
        from optional_ai_metrics import CONFIG_CONTRACT
        names = {entry["env_var"] for entry in CONFIG_CONTRACT}
        assert "MINIMAX_MODEL" in names
        assert "MINIMAX_BASE_URL" in names
        assert "MINIMAX_PROMPT_VERSION" in names
