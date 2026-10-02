"""[S10 R3] Engine allow-list for the optional-AI ``diagnostics`` envelope.

The agent's ``diagnostics_snapshot`` plus completion counters must pass this
validator unchanged; unknown keys, prompt text and out-of-range values must
reject the whole status post so contract drift is visible.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import sys
from pathlib import Path

import pytest

from optional_ai_status import (
    _ALLOWED_DIAGNOSTIC_KEYS, _clean_diagnostics, load_optional_ai_status, record_optional_ai_status,
)

AGENT = Path(__file__).resolve().parents[2] / "agent"


def _valid():
    return {"submit_states": {"QUEUED": 2, "EXPIRED": 1}, "pending": 0, "inflight": 1, "ready": 1,
            "expired_before_submit": 1, "expired_in_queue": 0, "expired_after_call": 1,
            "source_excluded_total": 3, "classifier_calls": 2, "classifier_failures": 1,
            "classifier_seconds_mean": 1.0, "classifier_seconds_p95": 1.5, "analyst_seconds_mean": None,
            "analyst_seconds_p95": None, "late_results_discarded": 0, "shutdown_rejected": 0,
            "inflight_overruns": 0, "completion_published": 1, "completion_expired_not_published": 0,
            "completion_review_not_available": 0, "completion_worker_state_lost": 0,
            "completion_edit_failed": 0}


def test_agent_snapshot_keys_match_the_engine_allow_list():
    sys.path.insert(0, str(AGENT))
    try:
        from async_reviews import AsyncReviewQueue
        from contract_health import DIAGNOSTICS_ALLOWED_KEYS
        from advisory import Review, Verdict
        queue = AsyncReviewQueue(lambda *_a: Review(Verdict.APPROVE, conviction=1))
        try:
            produced = set(queue.diagnostics_snapshot()) | {
                f"completion_{name}" for name in ("published", "expired_not_published", "review_not_available",
                                                  "worker_state_lost", "edit_failed")}
        finally:
            queue.shutdown()
    finally:
        sys.path.remove(str(AGENT))
    assert produced == set(_ALLOWED_DIAGNOSTIC_KEYS) == set(DIAGNOSTICS_ALLOWED_KEYS)


def test_valid_envelope_round_trips_through_status(tmp_path):
    db = str(tmp_path / "status.db")
    payload = {"state": "READY", "reported_at": datetime.now(timezone.utc).isoformat(), "queue": {},
               "diagnostics": _valid()}
    asyncio.run(record_optional_ai_status(db, payload))
    status = asyncio.run(load_optional_ai_status(db))
    assert status["detail"]["diagnostics"]["completion_published"] == 1
    assert status["detail"]["diagnostics"]["submit_states"] == {"EXPIRED": 1, "QUEUED": 2}


@pytest.mark.parametrize("mutation", [
    {"prompt_text": "leak"},
    {"ready": -1},
    {"ready": True},
    {"inflight": 2},
    {"classifier_seconds_p95": float("inf")},
    {"submit_states": {"APPROVED_BY_AI": 1}},
    {"submit_states": {"QUEUED": -1}},
])
def test_invalid_envelopes_are_rejected(mutation):
    with pytest.raises(ValueError):
        _clean_diagnostics({**_valid(), **mutation})


def test_absent_diagnostics_adds_no_field(tmp_path):
    db = str(tmp_path / "status.db")
    asyncio.run(record_optional_ai_status(db, {"state": "READY", "reported_at": datetime.now(timezone.utc).isoformat()}))
    assert "diagnostics" not in asyncio.run(load_optional_ai_status(db))["detail"]
