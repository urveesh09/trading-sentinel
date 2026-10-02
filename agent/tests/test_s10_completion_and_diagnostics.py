"""[S10 R3] Bounded diagnostics, strict worker shutdown and once-only completion updates."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from threading import Event
import time
from types import SimpleNamespace

import pytest

from advisory import Review, Verdict, unavailable
from async_reviews import AsyncReviewQueue, ReviewSubmission
from review_completion import MAX_ATTEMPTS, CompletionTracker


def _wait(predicate, timeout=2.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("condition not reached")


def _expiry(seconds=60):
    return datetime.now(timezone.utc) + timedelta(seconds=seconds)


# ---------------------------------------------------------------- diagnostics

def test_expiry_stages_are_counted_separately():
    release = Event()

    def slow(*_args):
        release.wait(1)
        return Review(Verdict.APPROVE, conviction=70)

    queue = AsyncReviewQueue(slow)
    try:
        assert queue.submit("past", {}, "", "R", expires_at=_expiry(-1)).state == "EXPIRED"
        assert queue.submit("first", {}, "", "R", expires_at=_expiry(0.3)).state == "QUEUED"
        assert queue.submit("second", {}, "", "R", expires_at=_expiry(0.2)).state == "QUEUED"
        time.sleep(0.4)
        release.set()
        _wait(lambda: queue.diagnostics_snapshot()["expired_in_queue"] == 1)
        diag = queue.diagnostics_snapshot()
        assert diag["expired_before_submit"] == 1
        assert diag["expired_after_call"] == 1      # "first" completed after its deadline
        assert diag["submit_states"] == {"EXPIRED": 1, "QUEUED": 2}
        assert diag["ready"] == 0
    finally:
        queue.shutdown()


def test_ready_classifier_and_source_counters_are_bounded_numbers():
    queue = AsyncReviewQueue(lambda *_a: Review(Verdict.APPROVE, conviction=80))
    try:
        queue.submit("k", {}, "", "R", expires_at=_expiry())
        _wait(lambda: queue.diagnostics_snapshot()["ready"] == 1)
        queue.record_source_exclusions(3)
        queue.record_source_exclusions(-2)            # ignored
        queue.record_classifier(0.5, ok=True)
        queue.record_classifier(1.5, ok=False)
        queue.record_classifier(float("nan"), ok=True)  # ignored
        diag = queue.diagnostics_snapshot()
        assert diag["source_excluded_total"] == 3
        assert (diag["classifier_calls"], diag["classifier_failures"]) == (2, 1)
        assert diag["classifier_seconds_mean"] == pytest.approx(1.0)
        assert diag["analyst_seconds_mean"] is not None
        assert all(not isinstance(v, str) for v in diag.values() if not isinstance(v, dict))
    finally:
        queue.shutdown()


# ---------------------------------------------------------- strict shutdown

def test_shutdown_fails_pending_closed_rejects_new_work_and_discards_late_results():
    started, release = Event(), Event()

    def stuck(*_args):
        started.set()
        release.wait(2)
        return Review(Verdict.APPROVE, conviction=90)

    queue = AsyncReviewQueue(stuck)
    queue.submit("inflight", {}, "", "R", expires_at=_expiry())
    started.wait(1)
    queue.submit("queued", {}, "", "R", expires_at=_expiry())
    queue.shutdown(timeout=0.05)
    assert queue.status("inflight").state == "UNAVAILABLE" and queue.status("inflight").reason == "worker_shutdown"
    assert queue.status("queued").state == "UNAVAILABLE"
    refused = queue.submit("after", {}, "", "R", expires_at=_expiry())
    assert (refused.state, refused.reason) == ("UNAVAILABLE", "worker_shutdown")
    release.set()
    _wait(lambda: queue.diagnostics_snapshot()["late_results_discarded"] == 1)
    assert queue.status("inflight").state == "UNAVAILABLE"   # the late APPROVE never became READY
    diag = queue.diagnostics_snapshot()
    assert diag["shutdown_rejected"] == 1 and diag["ready"] == 0
    _wait(lambda: not queue.worker_alive)


def test_inflight_call_past_its_deadline_is_counted_once():
    release = Event()
    queue = AsyncReviewQueue(lambda *_a: (release.wait(1), Review(Verdict.APPROVE, conviction=50))[1])
    try:
        queue.submit("slow", {}, "", "R", expires_at=_expiry(0.1))
        time.sleep(0.25)
        assert queue.diagnostics_snapshot()["inflight"] == 1
        assert queue.diagnostics_snapshot()["inflight_overruns"] == 1
        assert queue.diagnostics_snapshot()["inflight_overruns"] == 1
    finally:
        release.set()
        queue.shutdown()


# ------------------------------------------------------ once-only completion

class _Clock:
    def __init__(self):
        self.now = datetime(2026, 10, 2, 5, 0, tzinfo=timezone.utc)

    def __call__(self):
        return self.now


def _tracker(tmp_path, clock):
    return CompletionTracker(str(tmp_path / "completions.json"), now=clock)


def _register(tracker, clock, key="review-key", message_id=11):
    tracker.register(review_key=key, chat_id="chat", message_id=message_id, text="ALERT ACME Entry Rs100",
                     reply_markup='{"inline_keyboard":[["EM"]]}', valid_until=clock.now + timedelta(minutes=5))


READY = ReviewSubmission("review-key", "READY", review=Review(Verdict.APPROVE, conviction=81,
                                                                payload={"pitch": "p", "risks": "r"}))


def test_ready_review_edits_the_original_message_once_with_the_same_keyboard(tmp_path):
    clock, edits = _Clock(), []
    tracker = _tracker(tmp_path, clock)
    _register(tracker, clock)
    edit = lambda **kw: edits.append(kw) or "OK"
    assert tracker.deliver_due(lambda _k: READY, edit, lambda r: f"AI review completed: {r.conviction}")["published"] == 1
    assert tracker.deliver_due(lambda _k: READY, edit, lambda r: "x")["published"] == 0
    assert len(edits) == 1
    assert edits[0]["message_id"] == 11 and edits[0]["reply_markup"] == '{"inline_keyboard":[["EM"]]}'
    assert edits[0]["text"].startswith("ALERT ACME Entry Rs100\n\nAI review completed: 81")
    # A restarted process reloads the delivered state and never edits again.
    again = _tracker(tmp_path, clock)
    assert again.deliver_due(lambda _k: READY, edit, lambda r: "x")["published"] == 0 and len(edits) == 1


def test_ambiguous_edit_is_retried_and_not_modified_counts_as_delivered(tmp_path):
    clock = _Clock()
    tracker = _tracker(tmp_path, clock)
    _register(tracker, clock)
    results = iter(["AMBIGUOUS", "NOT_MODIFIED"])
    assert tracker.deliver_due(lambda _k: READY, lambda **_kw: next(results), lambda r: "a")["retry_later"] == 1
    assert tracker.deliver_due(lambda _k: READY, lambda **_kw: next(results), lambda r: "a")["published"] == 1


def test_persistent_edit_failure_stops_after_bounded_attempts(tmp_path):
    clock = _Clock()
    tracker = _tracker(tmp_path, clock)
    _register(tracker, clock)
    for _ in range(MAX_ATTEMPTS):
        tracker.deliver_due(lambda _k: READY, lambda **_kw: "FAILED", lambda r: "a")
    assert list(tracker.entries().values())[0]["state"] == "EDIT_FAILED"


@pytest.mark.parametrize("status, minutes, expected", [
    (READY, 6, "EXPIRED_NOT_PUBLISHED"),
    (None, 1, "WORKER_STATE_LOST"),
    (ReviewSubmission("review-key", "UNAVAILABLE", review=unavailable("x")), 1, "REVIEW_NOT_AVAILABLE"),
    (ReviewSubmission("review-key", "EXPIRED", reason="review_completed_late"), 1, "REVIEW_NOT_AVAILABLE"),
])
def test_unpublishable_completions_are_recorded_never_sent(tmp_path, status, minutes, expected):
    clock, edits = _Clock(), []
    tracker = _tracker(tmp_path, clock)
    _register(tracker, clock)
    clock.now += timedelta(minutes=minutes)
    tracker.deliver_due(lambda _k: status, lambda **kw: edits.append(kw) or "OK", lambda r: "a")
    assert edits == [] and list(tracker.entries().values())[0]["state"] == expected


def test_pending_review_stays_pending_without_an_edit(tmp_path):
    clock, edits = _Clock(), []
    tracker = _tracker(tmp_path, clock)
    _register(tracker, clock)
    pending = ReviewSubmission("review-key", "QUEUED")
    assert not any(tracker.deliver_due(lambda _k: pending, lambda **kw: edits.append(kw) or "OK", lambda r: "a").values())
    assert edits == []


# ------------------------------------------------------------ agent wiring

def test_agent_registers_only_pending_reviews_within_the_exec_window(tmp_path, monkeypatch):
    import agent
    monkeypatch.setattr(agent, "_completion_tracker", CompletionTracker(str(tmp_path / "c.json")))
    response = SimpleNamespace(json=lambda: {"result": {"message_id": 42}})
    sent_ts = int(datetime(2026, 10, 2, 5, 0, tzinfo=timezone.utc).timestamp())
    pending = unavailable("AI_REVIEW_PENDING")
    from dataclasses import replace
    pending = replace(pending, expires_at=datetime(2026, 10, 2, 5, 1, 30, tzinfo=timezone.utc))
    agent._register_pending_completion(response, pending, "key-1", "text", "{}", sent_ts)
    agent._register_pending_completion(response, unavailable("AI_REVIEW_QUEUE_FULL"), "key-2", "t", "{}", sent_ts)
    agent._register_pending_completion(response, Review(Verdict.APPROVE, conviction=1), "key-3", "t", "{}", sent_ts)
    entries = agent._completion_tracker.entries()
    assert [entry["review_key"] for entry in entries.values()] == ["key-1"]
    assert entries["key-1|42"]["valid_until"] == "2026-10-02T05:01:30+00:00"   # min(review expiry, +300 s)


def test_completion_annotation_never_restates_trade_fields():
    import agent
    text = agent._completion_annotation(Review(Verdict.REJECT, conviction=20,
                                               payload={"pitch": "weak", "risks": "chop"}))
    assert "Advisory only" in text and "Rs" not in text and "EXEC" not in text


def test_contract_health_accepts_bounded_diagnostics_and_rejects_unknown_keys():
    from contract_health import check_status_envelope_authority
    envelope = {"state": "READY", "reported_at": "2026-10-02T05:00:00+00:00", "queue": {},
                "diagnostics": {"ready": 1, "submit_states": {"QUEUED": 1}, "classifier_seconds_p95": 0.5}}
    assert check_status_envelope_authority(envelope).passed
    envelope["diagnostics"]["prompt_text"] = "leak"
    assert not check_status_envelope_authority(envelope).passed
