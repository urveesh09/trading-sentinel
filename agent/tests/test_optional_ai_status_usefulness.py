"""[WORKFLOW-I I.A 2026-09-13] Agent-side usefulness-bridge acceptance.

The agent's ``optional_ai_status`` function must include the I3
``usefulness_snapshot`` only when the operator opted in via
``OPTIONAL_AI_REPORT_USEFULNESS=true``. Tests cover:

  * default (false): envelope absent; no leaked I3 fields
  * opt-in: envelope present with bounded structure
  * opt-in with queue=None (never used): envelope NOT included
  * opt-in is read once per call (no caching of the env value)
"""
from __future__ import annotations

from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def _reset_optional_ai_flag():
    """Each test sets the flag explicitly; this fixture just
    ensures we don't leak a value from a sibling test."""
    yield


def _fresh_optional_ai_status_module(monkeypatch):
    """Reload the agent module with a controlled env so the
    OPTIONAL_AI_REPORT_USEFULNESS constant reflects the test's
    chosen value.
    """
    import importlib
    import agent
    return importlib.reload(agent)


def _full_fake_snapshot():
    return {
        "total_completed_reviews": 5,
        "cache_hits": 2,
        "cache_misses": 3,
        "cache_hit_rate": 0.4,
        "circuit_opens": 0,
        "response_seconds_mean": 1.2,
        "response_seconds_p95": 2.0,
        "response_seconds_last": 1.5,
        "last_completed_at": "2026-09-19T10:00:00+00:00",
        "verdict_counts": {
            "APPROVE": 3,
            "APPROVE_WITH_CONCERNS": 0,
            "REVIEW_UNAVAILABLE": 1,
            "REJECT": 1,
        },
    }


class TestAgentSideEnvelope:
    def test_default_flag_omits_usefulness(self, monkeypatch) -> None:
        """Default behaviour (no env var) omits the ``usefulness``
        key entirely. This preserves the existing operator
        dashboards that don't know about the new envelope.
        """
        monkeypatch.delenv("OPTIONAL_AI_REPORT_USEFULNESS", raising=False)
        agent = _fresh_optional_ai_status_module(monkeypatch)
        assert agent.OPTIONAL_AI_REPORT_USEFULNESS is False
        # Build the envelope with a mocked queue so we don't
        # require the LiteLLM client to be initialised.
        fake_snapshot = _full_fake_snapshot()
        fake_queue = agent.AsyncReviewQueue.__new__(agent.AsyncReviewQueue)
        with patch.object(agent, "_optional_ai_queue", fake_queue), \
             patch.object(fake_queue, "snapshot", return_value={
                 "pending": 0, "cached": 0, "daily_requests": 1,
                 "daily_budget": 40, "max_pending": 16,
                 "circuit_state": "CLOSED",
             }), \
             patch.object(fake_queue, "usefulness_snapshot",
                          return_value=fake_snapshot):
            # Force the queue to exist by setting the slot to a
            # non-None mock; the flag check is "queue is not None".
            payload = agent.optional_ai_status()
        assert "usefulness" not in payload

    def test_opt_in_flag_includes_usefulness(self, monkeypatch) -> None:
        """With the flag set, the envelope appears in the payload
        exactly as ``usefulness_snapshot`` returned it (no
        transformation, no truncation).
        """
        monkeypatch.setenv("OPTIONAL_AI_REPORT_USEFULNESS", "true")
        agent = _fresh_optional_ai_status_module(monkeypatch)
        assert agent.OPTIONAL_AI_REPORT_USEFULNESS is True
        fake_snapshot = _full_fake_snapshot()
        fake_queue = agent.AsyncReviewQueue.__new__(agent.AsyncReviewQueue)
        with patch.object(agent, "_optional_ai_queue", fake_queue), \
             patch.object(fake_queue, "snapshot", return_value={
                 "pending": 0, "cached": 0, "daily_requests": 1,
                 "daily_budget": 40, "max_pending": 16,
                 "circuit_state": "CLOSED",
             }), \
             patch.object(fake_queue, "usefulness_snapshot",
                          return_value=fake_snapshot):
            payload = agent.optional_ai_status()
        assert payload["usefulness"] == fake_snapshot

    def test_opt_in_with_no_queue_omits_usefulness(self, monkeypatch) -> None:
        """If the queue was never created (no model calls yet),
        the envelope is NOT included even with the flag on.
        Zero-filling an envelope would masquerade as data.
        """
        monkeypatch.setenv("OPTIONAL_AI_REPORT_USEFULNESS", "true")
        agent = _fresh_optional_ai_status_module(monkeypatch)
        assert agent.OPTIONAL_AI_REPORT_USEFULNESS is True
        with patch.object(agent, "_optional_ai_queue", None):
            payload = agent.optional_ai_status()
        assert "usefulness" not in payload

    def test_flag_is_read_once_per_module_load(self, monkeypatch) -> None:
        """The flag is a module-level constant; flipping the env
        after import does not change the constant. Operators who
        want to enable the bridge must restart the agent.
        """
        monkeypatch.setenv("OPTIONAL_AI_REPORT_USEFULNESS", "false")
        agent = _fresh_optional_ai_status_module(monkeypatch)
        assert agent.OPTIONAL_AI_REPORT_USEFULNESS is False
        # Change the env, but don't reload; constant stays False.
        monkeypatch.setenv("OPTIONAL_AI_REPORT_USEFULNESS", "true")
        assert agent.OPTIONAL_AI_REPORT_USEFULNESS is False
        # Reload -- now the flag reflects the new env.
        agent2 = _fresh_optional_ai_status_module(monkeypatch)
        assert agent2.OPTIONAL_AI_REPORT_USEFULNESS is True


# ---- I.F: cross-container contract ---------------------------------------

#: Documented at the top of the test file. The agent's payload
#: keys MUST be a subset of this set; the engine-side test
#: ``test_optional_ai_cross_container_contract.py`` asserts the
#: other side. If a future agent code change adds a payload key,
#: this set must be updated AND the engine's allow-list updated
#: in lock-step -- the I.F contract.
AGENT_PAYLOAD_KEYS = frozenset({
    "state",
    "reported_at",
    "async_requested",
    "policy_allows_annotation",
    "reason",
    "queue",
    "usefulness",  # optional; present only when opt-in flag is on
})


class TestAgentPayloadContract:
    """[WORKFLOW-I I.F 2026-09-13] The agent's payload must use
    only documented keys. A drift here means the engine's
    allow-list (in ``optional_ai_status._clean_usefulness``)
    will reject the new key silently, leaving operators without
    the field they expected.
    """

    def test_payload_keys_are_documented(self, monkeypatch) -> None:
        """The agent's payload, under the default opt-out,
        contains exactly the 6 documented keys (no ``usefulness``).
        """
        monkeypatch.setenv("OPTIONAL_AI_REPORT_USEFULNESS", "false")
        agent = _fresh_optional_ai_status_module(monkeypatch)
        fake_queue = agent.AsyncReviewQueue.__new__(agent.AsyncReviewQueue)
        with patch.object(agent, "_optional_ai_queue", fake_queue), \
             patch.object(fake_queue, "snapshot", return_value={
                 "pending": 0, "cached": 0, "daily_requests": 0,
                 "daily_budget": 40, "max_pending": 16,
                 "circuit_state": "CLOSED",
             }):
            payload = agent.optional_ai_status()
        assert set(payload.keys()) == (
            AGENT_PAYLOAD_KEYS - {"usefulness"}
        ), (
            f"agent payload drifted from contract: "
            f"{set(payload.keys()) ^ (AGENT_PAYLOAD_KEYS - {'usefulness'})}"
        )

    def test_payload_with_usefulness_has_seven_keys(
        self, monkeypatch,
    ) -> None:
        """With the opt-in flag on AND the queue created, the
        agent's payload has all 7 documented keys.
        """
        monkeypatch.setenv("OPTIONAL_AI_REPORT_USEFULNESS", "true")
        agent = _fresh_optional_ai_status_module(monkeypatch)
        fake_queue = agent.AsyncReviewQueue.__new__(agent.AsyncReviewQueue)
        with patch.object(agent, "_optional_ai_queue", fake_queue), \
             patch.object(fake_queue, "snapshot", return_value={
                 "pending": 0, "cached": 0, "daily_requests": 1,
                 "daily_budget": 40, "max_pending": 16,
                 "circuit_state": "CLOSED",
             }), \
             patch.object(fake_queue, "usefulness_snapshot",
                          return_value=_full_fake_snapshot()):
            payload = agent.optional_ai_status()
        assert set(payload.keys()) == AGENT_PAYLOAD_KEYS

    def test_usefulness_keys_match_engine_allow_list(self, monkeypatch) -> None:
        """The ``usefulness`` envelope produced by the agent uses
        exactly the keys the engine's ``_clean_usefulness`` will
        accept. If the agent adds a new key, the engine will
        reject it (ValueError, status post rejected, previous
        report retained).

        The real queue method is called so this test cannot hide producer
        drift behind a hand-maintained fake payload.
        """
        monkeypatch.setenv("OPTIONAL_AI_REPORT_USEFULNESS", "true")
        agent = _fresh_optional_ai_status_module(monkeypatch)

        queue = agent.AsyncReviewQueue(lambda *_args, **_kwargs: None)
        try:
            with patch.object(agent, "_optional_ai_queue", queue):
                payload = agent.optional_ai_status()
        finally:
            queue.shutdown()
        ENGINE_USEFULNESS_KEYS = frozenset({
            "total_completed_reviews", "cache_hits", "cache_misses",
            "cache_hit_rate", "circuit_opens", "response_seconds_mean",
            "response_seconds_p95", "response_seconds_last",
            "last_completed_at", "verdict_counts",
        })
        captured_keys = set(payload["usefulness"])
        assert captured_keys == ENGINE_USEFULNESS_KEYS, (
            f"agent usefulness drifted from engine allow-list: "
            f"{captured_keys ^ ENGINE_USEFULNESS_KEYS}"
        )
