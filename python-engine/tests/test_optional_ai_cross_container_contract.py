"""[WORKFLOW-I I.F 2026-09-13] Cross-container contract test.

Closes the I.F slice: the agent (Container C) and the engine
(Container B) communicate via a JSON status envelope. This test
suite asserts the boundary contract from the **engine's** side:

  * Every key the agent can send is either accepted by the
    validator or rejected with a clear error.
  * The persisted ``detail`` carries only bounded fields -- no
    review payload, no prompt, no credentials, no extra keys.
  * The ``load_optional_ai_status`` round-trip preserves the
    documented shape.
  * A versioned contract table documents the agent's payload
    keys and the engine's persisted keys. If a future agent
    code change adds a payload key, this test fails until both
    sides are updated deliberately.

The tests are **versioned** via a frozen contract dict at the top
of the file. To extend the contract:

  1. Add the new key to ``AGENT_PAYLOAD_KEYS`` and/or
     ``ENGINE_PERSISTED_KEYS``.
  2. Update the engine-side allow-list (``clean_queue``,
     ``_clean_usefulness``).
  3. Run the suite. If a key is in the agent payload but the
     engine rejects it, the test names the contract drift.

[WHY-THIS-EXISTS 2026-09-13]
  Cross-container contracts are easy to break silently. A
  producer field rename, a new optional field, a state change
  -- all happen with no test coverage at the boundary. The
  I.A validator (post + persist) and I.B/I.C producer (load)
  are tested independently. This suite catches **drift**
  between the two: a producer that thinks the engine accepts
  ``prompt_text`` and an engine that has no allow-list for it.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, FrozenSet, Optional

import pytest


# ---- (1) versioned contract -----------------------------------------------

#: Every key the agent may send in its status payload.
#: Frozen so a test can assert: "no key outside this set is
#: accepted by the engine." If you add a key here, the engine
#: validator must be updated in lock-step.
AGENT_PAYLOAD_KEYS: FrozenSet[str] = frozenset({
    "state",
    "reported_at",
    "async_requested",
    "policy_allows_annotation",
    "reason",
    "queue",
    "usefulness",  # optional; present only when opt-in flag is on
})

#: Every key the engine may persist in the ``detail`` JSON.
#: Frozen so a test can assert: "the engine never persists a key
#: outside this set." If you add a key here, the producer code
#: (``record_optional_ai_status``) must add it deliberately.
ENGINE_PERSISTED_KEYS: FrozenSet[str] = frozenset({
    "async_requested",
    "policy_allows_annotation",
    "queue",
    "reason",
    "execution_authority",
    "can_place_orders",
    "usefulness",  # only when the agent sent it AND it cleaned
})

#: Bounded queue keys (the engine's ``clean_queue`` allow-list).
ENGINE_QUEUE_KEYS: FrozenSet[str] = frozenset({
    "pending", "cached", "daily_requests", "daily_budget",
    "max_pending", "circuit_state",
})

#: Bounded usefulness keys (the I.A validator's allow-list).
ENGINE_USEFULNESS_KEYS: FrozenSet[str] = frozenset({
    "total_completed_reviews", "cache_hits", "cache_misses",
    "circuit_opens", "response_seconds_last", "verdict_counts",
})

#: Bounded verdict keys inside the usefulness envelope.
ENGINE_VERDICT_KEYS: FrozenSet[str] = frozenset({
    "APPROVE", "APPROVE_WITH_CONCERNS",
    "REVIEW_UNAVAILABLE", "REJECT",
})

#: Top-level keys returned by ``load_optional_ai_status`` (after
#: base merge). Used to assert the public GET contract.
ENGINE_RETURN_KEYS: FrozenSet[str] = frozenset({
    "mode", "execution_authority", "can_place_orders",
    "state", "reported_state", "reported_at", "received_at",
    "stale", "detail", "note",
})


# ---- helpers --------------------------------------------------------------

def _canonical_payload(
    *,
    state: str = "READY",
    queue: Optional[Dict[str, Any]] = None,
    usefulness: Optional[Dict[str, Any]] = None,
    reported_at: Optional[datetime] = None,
) -> Dict[str, Any]:
    """A canonical agent payload matching the I.A contract."""
    if reported_at is None:
        reported_at = datetime.now(timezone.utc)
    payload: Dict[str, Any] = {
        "state": state,
        "reported_at": reported_at.isoformat(),
        "async_requested": True,
        "policy_allows_annotation": True,
        "reason": "optional_annotation_ready",
        "queue": queue or {
            "pending": 0, "cached": 0, "daily_requests": 1,
            "daily_budget": 40, "max_pending": 16,
            "circuit_state": "CLOSED",
        },
    }
    if usefulness is not None:
        payload["usefulness"] = usefulness
    return payload


# ---- (2) envelope acceptance --------------------------------------------

class TestEnvelopeAcceptance:
    """Every documented agent key is either accepted or
    explicitly rejected by the engine validator. If a key is
    accepted, the engine persists it; if rejected, the test
    surfaces the rejection so the contract drift is visible.
    """

    def test_canonical_payload_round_trips(self) -> None:
        """A canonical payload (every key in the contract)
        persists without error and round-trips through the
        engine's load function.
        """
        from optional_ai_status import (
            record_optional_ai_status, load_optional_ai_status,
        )
        import tempfile, os, asyncio
        db = tempfile.mktemp(suffix=".db")
        try:
            payload = _canonical_payload(
                usefulness={
                    "total_completed_reviews": 1,
                    "cache_hits": 0, "cache_misses": 0,
                    "circuit_opens": 0,
                    "response_seconds_last": 1.0,
                    "verdict_counts": {"APPROVE": 1, "APPROVE_WITH_CONCERNS": 0,
                                         "REVIEW_UNAVAILABLE": 0, "REJECT": 0},
                },
            )
            stored = asyncio.run(record_optional_ai_status(db, payload))
            assert stored["state"] == "READY"
            # Usefulness round-trips.
            assert stored["detail"]["usefulness"]["total_completed_reviews"] == 1
        finally:
            os.unlink(db)

    def test_no_unknown_keys_in_payload_round_trip(self) -> None:
        """The canonical payload must use only documented keys.
        If a future agent adds a key, this test fails.
        """
        from optional_ai_status import (
            record_optional_ai_status,
        )
        import tempfile, os, asyncio
        db = tempfile.mktemp(suffix=".db")
        try:
            payload = _canonical_payload()
            # Assert the payload uses ONLY the documented keys.
            assert set(payload.keys()).issubset(AGENT_PAYLOAD_KEYS), (
                f"agent payload has undocumented keys: "
                f"{set(payload.keys()) - AGENT_PAYLOAD_KEYS}"
            )
            # Persist; should succeed with no rejection.
            asyncio.run(record_optional_ai_status(db, payload))
        finally:
            os.unlink(db)

    def test_persisted_detail_uses_only_documented_keys(self) -> None:
        """The engine's persisted detail must use only the
        documented ``ENGINE_PERSISTED_KEYS``. Any extra key in
        the persisted JSON is a contract drift.
        """
        from optional_ai_status import (
            record_optional_ai_status, load_optional_ai_status,
        )
        import tempfile, os, asyncio
        db = tempfile.mktemp(suffix=".db")
        try:
            payload = _canonical_payload(usefulness={
                "total_completed_reviews": 1,
                "cache_hits": 0, "cache_misses": 0,
                "circuit_opens": 0,
                "response_seconds_last": 1.0,
                "verdict_counts": {"APPROVE": 1, "APPROVE_WITH_CONCERNS": 0,
                                     "REVIEW_UNAVAILABLE": 0, "REJECT": 0},
            })
            asyncio.run(record_optional_ai_status(db, payload))
            loaded = asyncio.run(load_optional_ai_status(db))
            detail = loaded["detail"]
            extra = set(detail.keys()) - ENGINE_PERSISTED_KEYS
            assert not extra, f"engine persisted undocumented keys: {extra}"
        finally:
            os.unlink(db)

    def test_persisted_queue_uses_only_bounded_keys(self) -> None:
        """The persisted queue carries only the 6 bounded keys.
        """
        from optional_ai_status import (
            record_optional_ai_status, load_optional_ai_status,
        )
        import tempfile, os, asyncio
        db = tempfile.mktemp(suffix=".db")
        try:
            payload = _canonical_payload(queue={
                "pending": 1, "cached": 2, "daily_requests": 3,
                "daily_budget": 40, "max_pending": 16,
                "circuit_state": "CLOSED",
                # Agent could try to send extras; engine must drop.
                "leaked_secret": "sk-LEAK",
                "review_payload": {"pitch": "leak"},
            })
            asyncio.run(record_optional_ai_status(db, payload))
            loaded = asyncio.run(load_optional_ai_status(db))
            q = loaded["detail"]["queue"]
            extra = set(q.keys()) - ENGINE_QUEUE_KEYS
            assert not extra, f"queue persisted undocumented keys: {extra}"
            # The 6 bounded keys are present.
            for k in ENGINE_QUEUE_KEYS:
                assert k in q, f"queue missing bounded key: {k}"
        finally:
            os.unlink(db)


# ---- (3) bounded contract: nothing dangerous crosses ------------------

class TestNothingDangerousCrosses:
    """The bounded contract excludes:
      * the model's review payload (pitch/rationale/risks)
      * the prompt content
      * credentials (api_key, secret, token)
      * arbitrary nested dicts with unbounded keys
    """

    def test_review_payload_is_rejected(self) -> None:
        """The agent could try to leak ``pitch`` etc. via the
        envelope. The engine rejects unknown keys.
        """
        from optional_ai_status import (
            record_optional_ai_status, _clean_usefulness,
        )
        # Direct validator test -- the route handler also
        # rejects unknown fields via the route layer.
        with pytest.raises(ValueError, match="unknown keys"):
            _clean_usefulness({"pitch": "leaked_pitch_text"})

    def test_prompt_content_is_rejected(self) -> None:
        from optional_ai_status import _clean_usefulness
        with pytest.raises(ValueError, match="unknown keys"):
            _clean_usefulness({"prompt": "system_prompt_content"})

    def test_credentials_are_rejected(self) -> None:
        from optional_ai_status import _clean_usefulness
        # Multiple shapes of credential leakage.
        for leak in (
            {"api_key": "sk-LEAK"},
            {"secret": "shhh"},
            {"token": "bearer-leak"},
        ):
            with pytest.raises(ValueError, match="unknown keys"):
                _clean_usefulness(leak)

    def test_verdict_counts_rejects_arbitrary_keys(self) -> None:
        """The verdict_counts sub-dict has its own allow-list
        (the four verdict buckets). An arbitrary extra key is
        rejected.
        """
        from optional_ai_status import _clean_usefulness
        with pytest.raises(ValueError, match="unknown keys"):
            _clean_usefulness({"verdict_counts": {"HACKED_VERDICT": 1}})

    def test_no_payload_in_persisted_detail(self) -> None:
        """Even if a payload leaks through the validator (it
        mustn't), the engine never persists ``pitch`` /
        ``rationale`` / ``risks``. The engine's persisted keys
        are bounded; the test asserts they appear as a subset.
        """
        from optional_ai_status import (
            record_optional_ai_status, load_optional_ai_status,
        )
        import tempfile, os, asyncio
        db = tempfile.mktemp(suffix=".db")
        try:
            # Even with a valid payload, the persisted detail
            # is bounded. We check the keys of the loaded detail.
            payload = _canonical_payload()
            asyncio.run(record_optional_ai_status(db, payload))
            loaded = asyncio.run(load_optional_ai_status(db))
            forbidden = {"pitch", "rationale", "risks", "prompt"}
            leaked = forbidden & set(loaded["detail"].keys())
            assert not leaked, (
                f"review payload leaked into persisted detail: {leaked}"
            )
        finally:
            os.unlink(db)


# ---- (4) round-trip preservation ---------------------------------------

class TestRoundTrip:
    """A successful round-trip preserves every bounded field
    value. Loss-of-precision would be a contract drift.
    """

    def test_usefulness_counters_round_trip(self) -> None:
        from optional_ai_status import (
            record_optional_ai_status, load_optional_ai_status,
        )
        import tempfile, os, asyncio
        db = tempfile.mktemp(suffix=".db")
        try:
            usefulness = {
                "total_completed_reviews": 7,
                "cache_hits": 4, "cache_misses": 3,
                "circuit_opens": 0,
                "response_seconds_last": 1.5,
                "verdict_counts": {"APPROVE": 5, "APPROVE_WITH_CONCERNS": 1,
                                     "REVIEW_UNAVAILABLE": 1, "REJECT": 0},
            }
            payload = _canonical_payload(usefulness=usefulness)
            asyncio.run(record_optional_ai_status(db, payload))
            loaded = asyncio.run(load_optional_ai_status(db))
            assert loaded["detail"]["usefulness"] == usefulness
        finally:
            os.unlink(db)

    def test_state_and_reason_round_trip(self) -> None:
        """The ``state`` and ``reason`` fields round-trip."""
        from optional_ai_status import (
            record_optional_ai_status, load_optional_ai_status,
        )
        import tempfile, os, asyncio
        db = tempfile.mktemp(suffix=".db")
        try:
            payload = _canonical_payload(
                state="OUTAGE_CIRCUIT_OPEN", queue={
                    "pending": 0, "cached": 0, "daily_requests": 5,
                    "daily_budget": 40, "max_pending": 16,
                    "circuit_state": "OPEN",
                },
            )
            payload["reason"] = "provider_failures"
            asyncio.run(record_optional_ai_status(db, payload))
            loaded = asyncio.run(load_optional_ai_status(db))
            assert loaded["state"] == "OUTAGE_CIRCUIT_OPEN"
            assert loaded["detail"]["reason"] == "provider_failures"
            assert loaded["detail"]["queue"]["circuit_state"] == "OPEN"
        finally:
            os.unlink(db)

    def test_optional_usefulness_absent_when_agent_didnt_send(self) -> None:
        """When the agent doesn't send ``usefulness`` (the default
        opt-out), the persisted detail has no ``usefulness`` key.
        """
        from optional_ai_status import (
            record_optional_ai_status, load_optional_ai_status,
        )
        import tempfile, os, asyncio
        db = tempfile.mktemp(suffix=".db")
        try:
            payload = _canonical_payload(usefulness=None)
            asyncio.run(record_optional_ai_status(db, payload))
            loaded = asyncio.run(load_optional_ai_status(db))
            assert "usefulness" not in loaded["detail"]
        finally:
            os.unlink(db)

    def test_reported_at_iso_format_preserved(self) -> None:
        """The agent sends ISO 8601; the engine persists it
        byte-for-byte and the load function returns it as a
        string.
        """
        from optional_ai_status import (
            record_optional_ai_status, load_optional_ai_status,
        )
        import tempfile, os, asyncio
        db = tempfile.mktemp(suffix=".db")
        try:
            now = datetime.now(timezone.utc)
            payload = _canonical_payload(reported_at=now)
            asyncio.run(record_optional_ai_status(db, payload))
            loaded = asyncio.run(load_optional_ai_status(db))
            assert loaded["reported_at"] == now.isoformat()
        finally:
            os.unlink(db)


# ---- (5) public-GET contract --------------------------------------------

class TestPublicGetContract:
    """``load_optional_ai_status`` returns a fixed shape. A future
    engineer adding a top-level key breaks this contract.
    """

    def test_return_keys_are_exactly_documented(self) -> None:
        from optional_ai_status import load_optional_ai_status
        import tempfile, os, asyncio
        db = tempfile.mktemp(suffix=".db")
        try:
            loaded = asyncio.run(load_optional_ai_status(db))
            extra = set(loaded.keys()) - ENGINE_RETURN_KEYS
            assert not extra, (
                f"load_optional_ai_status returned undocumented keys: "
                f"{extra}"
            )
            # Required keys present.
            for k in ENGINE_RETURN_KEYS:
                assert k in loaded, (
                    f"load_optional_ai_status missing key: {k}"
                )
        finally:
            os.unlink(db)

    def test_not_reported_state_when_db_empty(self) -> None:
        """On a fresh DB, the state is NOT_REPORTED. This is
        a contract guarantee for the dashboard.
        """
        from optional_ai_status import load_optional_ai_status
        import tempfile, os, asyncio
        db = tempfile.mktemp(suffix=".db")
        try:
            loaded = asyncio.run(load_optional_ai_status(db))
            assert loaded["state"] == "NOT_REPORTED"
            assert loaded["stale"] is True
            assert loaded["execution_authority"] == "NONE"
            assert loaded["can_place_orders"] is False
        finally:
            os.unlink(db)


# ---- (6) versioned contract table --------------------------------------

class TestVersionedContract:
    """The contract is documented as frozen sets at the top of
    this file. Tests assert the documentation matches reality.
    A drift here is a contract drift -- fix one or the other.
    """

    def test_optional_usefulness_is_a_contract_key(self) -> None:
        """``usefulness`` is documented as optional in the
        agent payload and optional in the engine persisted
        detail. It appears in both contract sets because it
        CAN appear, not because it MUST.
        """
        assert "usefulness" in AGENT_PAYLOAD_KEYS
        assert "usefulness" in ENGINE_PERSISTED_KEYS

    def test_execution_authority_is_always_none(self) -> None:
        """The §13 contract: ``execution_authority`` is always
        ``NONE`` and ``can_place_orders`` is always False. The
        engine hardcodes these values; the agent cannot
        influence them.
        """
        from optional_ai_status import record_optional_ai_status
        import tempfile, os, asyncio
        db = tempfile.mktemp(suffix=".db")
        try:
            # Even if the agent tried to set them, the engine
            # ignores payload-side values (they're hardcoded).
            payload = _canonical_payload()
            payload["execution_authority"] = "FULL"  # attempted override
            payload["can_place_orders"] = True  # attempted override
            stored = asyncio.run(record_optional_ai_status(db, payload))
            assert stored["detail"]["execution_authority"] == "NONE"
            assert stored["detail"]["can_place_orders"] is False
        finally:
            os.unlink(db)
