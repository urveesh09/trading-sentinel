"""O8-A1 (Oct 8 audit): status heartbeat publish timeouts and overlap."""
import threading

import pytest
import requests


@pytest.fixture
def agent_mod(monkeypatch):
    import agent as module
    monkeypatch.setattr(module, "INTERNAL_API_SECRET", "test-secret")
    monkeypatch.setattr(module, "_status_publish", {"in_flight": False, "failures": 0, "last_ok": None})
    return module


class _Inline:
    """Run the publisher thread inline so the test is deterministic."""
    def __init__(self, target, name=None, daemon=None):
        self._target = target

    def start(self):
        self._target()


def test_publish_uses_a_read_timeout_and_tracks_failure_streaks(agent_mod, monkeypatch):
    calls = []
    outcomes = [requests.ReadTimeout(), requests.ReadTimeout(), None]

    def fake_post(url, json, headers, timeout):
        calls.append(timeout)
        outcome = outcomes.pop(0)
        if outcome is not None:
            raise outcome
        return type("R", (), {"status_code": 200})()

    monkeypatch.setattr(agent_mod.requests, "post", fake_post)
    monkeypatch.setattr(agent_mod.threading, "Thread", _Inline)
    for _ in range(2):
        agent_mod.publish_optional_ai_status()
    assert agent_mod._status_publish["failures"] == 2 and agent_mod._status_publish["last_ok"] is None
    agent_mod.publish_optional_ai_status()
    assert agent_mod._status_publish["failures"] == 0 and agent_mod._status_publish["last_ok"]
    assert agent_mod._status_publish["in_flight"] is False
    assert calls == [agent_mod.OPTIONAL_AI_STATUS_TIMEOUT] * 3 and calls[0][1] >= 10


def test_a_post_still_in_flight_makes_the_next_publish_skip(agent_mod, monkeypatch):
    started = []
    monkeypatch.setattr(agent_mod.threading, "Thread",
                        lambda target, name=None, daemon=None: type("T", (), {"start": lambda self: started.append(1)})())
    agent_mod.publish_optional_ai_status()
    agent_mod.publish_optional_ai_status()                 # first one never finished
    assert started == [1] and agent_mod._status_publish["in_flight"] is True
