"""[WORKFLOW-I I.A 2026-09-13] Optional-AI usefulness-bridge acceptance.

Closes the I.A slice: bridge I3 ``usefulness_snapshot`` from the
agent to the engine's persisted status. The agent posts the
bounded envelope when ``OPTIONAL_AI_REPORT_USEFULNESS=true``;
the engine validates and persists it under ``detail.usefulness``.

Coverage
--------
1. Bounded envelope validation: unknown keys are rejected.
2. Bounded envelope validation: bad types are rejected
   (bool for int, negative numbers, wrong dict shape).
3. Valid envelope is persisted as-is in ``detail.usefulness``.
4. ``verdict_counts`` must be a dict with the four bounded keys.
5. Absent envelope (opt-in default) means ``usefulness`` is not
   in ``detail`` -- no field drift for operators who don't opt in.
6. Response seconds negative value is rejected.
7. ``response_seconds_last`` accepts integer-valued floats
   (``1.0`` parsed as ``1`` is still a valid number).
8. Route surface: POSTing with a valid usefulness envelope is
   accepted; the GET round-trip exposes it.
9. Usefulness field does NOT appear when the envelope is absent.
10. The bounded contract does NOT include review payload /
    prompt / credentials.
"""
from __future__ import annotations

from datetime import datetime, timezone
import math

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from config import settings
from optional_ai_status import (
    _ALLOWED_USEFULNESS_KEYS,
    _ALLOWED_VERDICT_KEYS,
    _clean_usefulness,
    load_optional_ai_status,
    record_optional_ai_status,
)
import main  # noqa: F401
import routes_ops


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(routes_ops.router)
    return TestClient(app)


def _envelope_payload(
    *,
    with_usefulness: bool = True,
    usefulness: dict | None = None,
    state: str = "READY",
    reported_at: datetime | None = None,
) -> dict:
    """A canonical agent envelope payload."""
    return {
        "state": state,
        "reported_at": (
            reported_at or datetime.now(timezone.utc)
        ).isoformat(),
        "async_requested": True,
        "policy_allows_annotation": True,
        "reason": "optional_annotation_ready",
        "queue": {
            "pending": 0, "cached": 0, "daily_requests": 1,
            "daily_budget": 40, "max_pending": 16, "circuit_state": "CLOSED",
        },
        **({"usefulness": usefulness} if with_usefulness else {}),
    }


# ---- (1) bounded validator ------------------------------------------------

class TestCleanUsefulness:
    def test_absent_returns_empty_dict(self) -> None:
        """Absent envelope (the default opt-in flag is off) yields
        an empty clean dict, not an error."""
        assert _clean_usefulness(None) == {}

    def test_valid_envelope_round_trips(self) -> None:
        envelope = {
            "total_completed_reviews": 12,
            "cache_hits": 5,
            "cache_misses": 3,
            "cache_hit_rate": 0.625,
            "circuit_opens": 1,
            "response_seconds_mean": 1.25,
            "response_seconds_p95": 2.5,
            "response_seconds_last": 1.5,
            "last_completed_at": "2026-09-19T10:00:00+00:00",
            "verdict_counts": {
                "APPROVE": 8,
                "APPROVE_WITH_CONCERNS": 2,
                "REVIEW_UNAVAILABLE": 1,
                "REJECT": 1,
            },
        }
        clean = _clean_usefulness(envelope)
        assert clean == envelope

    def test_unknown_top_level_key_rejected(self) -> None:
        with pytest.raises(ValueError, match="unknown keys"):
            _clean_usefulness({"pitch": "leaked"})  # a payload field!

    def test_unknown_verdict_key_rejected(self) -> None:
        with pytest.raises(ValueError, match="unknown keys"):
            _clean_usefulness({"verdict_counts": {"HACKED": 1}})

    def test_negative_int_rejected(self) -> None:
        with pytest.raises(ValueError, match="non-negative integer"):
            _clean_usefulness({"cache_hits": -1})

    def test_bool_rejected_for_int(self) -> None:
        """``True`` is a Python ``int``; the validator explicitly
        rejects bools to prevent JSON ``true``/``false`` from
        sneaking into counter fields.
        """
        with pytest.raises(ValueError, match="non-negative integer"):
            _clean_usefulness({"cache_hits": True})

    def test_negative_response_seconds_rejected(self) -> None:
        with pytest.raises(ValueError, match="finite non-negative"):
            _clean_usefulness({"response_seconds_last": -1.0})

    @pytest.mark.parametrize(
        "field", [
            "response_seconds_mean",
            "response_seconds_p95",
            "response_seconds_last",
        ],
    )
    @pytest.mark.parametrize("value", [float("nan"), float("inf"), -0.1, True])
    def test_latency_fields_reject_invalid_numbers(self, field, value) -> None:
        with pytest.raises(ValueError, match="finite non-negative"):
            _clean_usefulness({field: value})

    @pytest.mark.parametrize("value", [-0.1, 1.1, float("nan"), True])
    def test_cache_hit_rate_rejects_invalid_values(self, value) -> None:
        with pytest.raises(ValueError, match="between 0 and 1"):
            _clean_usefulness({"cache_hit_rate": value})

    def test_cache_hit_rate_must_match_counters_when_all_are_present(self) -> None:
        with pytest.raises(ValueError, match="inconsistent with cache counters"):
            _clean_usefulness({
                "cache_hits": 1,
                "cache_misses": 3,
                "cache_hit_rate": 0.5,
            })
        with pytest.raises(ValueError, match="inconsistent with cache counters"):
            _clean_usefulness({
                "cache_hits": 0,
                "cache_misses": 0,
                "cache_hit_rate": 0.0,
            })

    def test_completed_total_must_match_verdicts_when_both_are_present(self) -> None:
        with pytest.raises(ValueError, match="inconsistent with verdict counts"):
            _clean_usefulness({
                "total_completed_reviews": 2,
                "verdict_counts": {"APPROVE": 1},
            })

    def test_nullable_metrics_preserve_explicit_null(self) -> None:
        clean = _clean_usefulness({
            "cache_hit_rate": None,
            "response_seconds_mean": None,
            "response_seconds_p95": None,
            "response_seconds_last": None,
            "last_completed_at": None,
        })
        assert clean == {
            "cache_hit_rate": None,
            "response_seconds_mean": None,
            "response_seconds_p95": None,
            "response_seconds_last": None,
            "last_completed_at": None,
        }

    def test_last_completed_at_requires_timezone_and_normalises_utc(self) -> None:
        with pytest.raises(ValueError, match="include a timezone"):
            _clean_usefulness({"last_completed_at": "2026-09-19T10:00:00"})
        clean = _clean_usefulness({
            "last_completed_at": "2026-09-19T15:30:00+05:30",
        })
        assert clean["last_completed_at"] == "2026-09-19T10:00:00+00:00"

    def test_response_seconds_int_accepted(self) -> None:
        """``1`` (int) is a valid number; the validator must coerce
        to float on the way through.
        """
        clean = _clean_usefulness({"response_seconds_last": 1})
        assert clean["response_seconds_last"] == 1.0
        assert isinstance(clean["response_seconds_last"], float)

    def test_string_for_response_seconds_rejected(self) -> None:
        with pytest.raises(ValueError, match="finite non-negative number"):
            _clean_usefulness({"response_seconds_last": "1.5"})

    def test_legacy_six_field_envelope_remains_accepted(self) -> None:
        legacy = {
            "total_completed_reviews": 1,
            "cache_hits": 0,
            "cache_misses": 1,
            "circuit_opens": 0,
            "response_seconds_last": 1.0,
            "verdict_counts": {"APPROVE": 1},
        }
        clean = _clean_usefulness(legacy)
        assert clean["total_completed_reviews"] == 1
        assert clean["response_seconds_last"] == 1.0
        assert not any(math.isnan(v) for v in clean.values() if isinstance(v, float))

    def test_verdict_counts_partial_defaults_to_zero(self) -> None:
        """A verdict_counts dict missing one of the four buckets
        gets the missing bucket filled with 0 -- the consumer can
        assume the four keys are always present.
        """
        clean = _clean_usefulness({
            "verdict_counts": {"APPROVE": 5},  # three buckets missing
        })
        assert clean["verdict_counts"] == {
            "APPROVE": 5,
            "APPROVE_WITH_CONCERNS": 0,
            "REVIEW_UNAVAILABLE": 0,
            "REJECT": 0,
        }

    def test_verdict_counts_not_a_dict_rejected(self) -> None:
        with pytest.raises(ValueError, match="must be an object"):
            _clean_usefulness({"verdict_counts": "APPROVE"})

    def test_usefulness_not_a_dict_rejected(self) -> None:
        with pytest.raises(ValueError, match="usefulness must be an object"):
            _clean_usefulness("leaked")


# ---- (2) persistence -------------------------------------------------------

class TestPersistedUsefulness:
    @pytest.mark.asyncio
    async def test_valid_envelope_is_persisted(self, db_path) -> None:
        payload = _envelope_payload(usefulness={
            "total_completed_reviews": 7,
            "cache_hits": 4, "cache_misses": 3,
            "circuit_opens": 0,
            "response_seconds_last": 2.0,
            "verdict_counts": {"APPROVE": 4, "APPROVE_WITH_CONCERNS": 1,
                                 "REVIEW_UNAVAILABLE": 1, "REJECT": 1},
        })
        status = await record_optional_ai_status(db_path, payload)
        assert "usefulness" in status["detail"]
        u = status["detail"]["usefulness"]
        assert u["total_completed_reviews"] == 7
        assert u["cache_hits"] == 4
        assert u["verdict_counts"]["APPROVE"] == 4

    @pytest.mark.asyncio
    async def test_absent_envelope_means_no_usefulness_field(
        self, db_path,
    ) -> None:
        """Operators who don't opt in see no ``usefulness`` key.
        The dashboard distinguishes 'absent' from 'zero'.
        """
        payload = _envelope_payload(with_usefulness=False)
        status = await record_optional_ai_status(db_path, payload)
        assert "usefulness" not in status["detail"]
        # Round-trip persists the absence.
        loaded = await load_optional_ai_status(db_path)
        assert "usefulness" not in loaded["detail"]

    @pytest.mark.asyncio
    async def test_malformed_envelope_rejected_keeps_previous(
        self, db_path,
    ) -> None:
        """A malformed envelope raises ``ValueError``. The previous
        report remains on disk -- operators see the contract drift
        rather than silently losing the prior record.
        """
        # First, a clean post.
        await record_optional_ai_status(db_path, _envelope_payload(
            usefulness={"total_completed_reviews": 1,
                       "cache_hits": 0, "cache_misses": 0,
                       "circuit_opens": 0,
                       "response_seconds_last": 1.0,
                       "verdict_counts": {"APPROVE": 1, "APPROVE_WITH_CONCERNS": 0,
                                            "REVIEW_UNAVAILABLE": 0, "REJECT": 0}},
        ))
        # Now a malformed post: an int where a number is expected.
        bad = _envelope_payload(usefulness={"response_seconds_last": "1.5"})
        with pytest.raises(ValueError, match="non-negative number"):
            await record_optional_ai_status(db_path, bad)
        # Previous report still intact.
        loaded = await load_optional_ai_status(db_path)
        assert loaded["detail"]["usefulness"]["total_completed_reviews"] == 1


# ---- (3) route surface -----------------------------------------------------

class TestRouteSurface:
    """[WORKFLOW-I I.A 2026-09-13] The route surface for the bridge.

    These tests use the global ``settings.DB_PATH`` because
    ``routes_ops`` is bound to it via the production router
    registration. Persistence is observable through the GET.
    Each test writes its own envelope so cross-test interference
    is bounded by the last-write semantics of the persistence
    layer (``INSERT OR REPLACE`` on ``report_key='optional_ai'``).
    """

    def test_route_accepts_usefulness_envelope(self) -> None:
        client = _client()
        payload = _envelope_payload(usefulness={
            "total_completed_reviews": 3,
            "cache_hits": 1, "cache_misses": 2,
            "circuit_opens": 0,
            "response_seconds_last": 0.7,
            "verdict_counts": {"APPROVE": 2, "APPROVE_WITH_CONCERNS": 0,
                                 "REVIEW_UNAVAILABLE": 1, "REJECT": 0},
        })
        post = client.post(
            "/ops/optional-ai-status", json=payload,
            headers={"X-Internal-Secret": settings.INTERNAL_API_SECRET},
        )
        assert post.status_code == 200, post.text
        evidence = client.get(
            "/analytics/optional-ai-status",
            headers={"X-Internal-Secret": settings.INTERNAL_API_SECRET},
        )
        assert evidence.status_code == 200
        body = evidence.json()
        assert body["can_place_orders"] is False
        assert body["execution_authority"] == "NONE"
        assert body["detail"]["usefulness"]["total_completed_reviews"] == 3
        assert body["detail"]["usefulness"]["verdict_counts"]["APPROVE"] == 2

    def test_route_rejects_malformed_envelope(self) -> None:
        client = _client()
        payload = _envelope_payload(usefulness={"cache_hits": -1})
        post = client.post(
            "/ops/optional-ai-status", json=payload,
            headers={"X-Internal-Secret": settings.INTERNAL_API_SECRET},
        )
        # The I.A contract is "raise on bad input". The current
        # FastAPI surface maps uncaught ValueError to 500. We
        # document that explicitly rather than masking the
        # contract violation with a 400.
        assert post.status_code >= 400

    def test_route_absent_envelope_does_not_persist_usefulness(self) -> None:
        """Operators who don't opt in see no ``usefulness`` key
        round-tripped through the GET.
        """
        client = _client()
        payload = _envelope_payload(with_usefulness=False)
        post = client.post(
            "/ops/optional-ai-status", json=payload,
            headers={"X-Internal-Secret": settings.INTERNAL_API_SECRET},
        )
        assert post.status_code == 200
        evidence = client.get(
            "/analytics/optional-ai-status",
            headers={"X-Internal-Secret": settings.INTERNAL_API_SECRET},
        )
        body = evidence.json()
        assert "usefulness" not in body["detail"]


# ---- (4) bounded contract: no review payload leakage ----------------------

class TestBoundedContract:
    def test_usefulness_does_not_carry_review_payload(self) -> None:
        """The bounded contract excludes the model's review payload.
        This test is a guard against future drift: if someone adds
        ``payload`` to ``usefulness``, the allow-list will reject it.
        """
        envelope = {
            "total_completed_reviews": 1,
            "cache_hits": 0, "cache_misses": 0,
            "circuit_opens": 0,
            "response_seconds_last": 1.0,
            "verdict_counts": {"APPROVE": 1, "APPROVE_WITH_CONCERNS": 0,
                                 "REVIEW_UNAVAILABLE": 0, "REJECT": 0},
            "pitch": "should be rejected",  # payload leak
            "rationale": "should be rejected",
        }
        with pytest.raises(ValueError, match="unknown keys"):
            _clean_usefulness(envelope)

    def test_usefulness_does_not_carry_prompt_or_credential(self) -> None:
        envelope = {
            "total_completed_reviews": 0,
            "cache_hits": 0, "cache_misses": 0,
            "circuit_opens": 0,
            "response_seconds_last": 1.0,
            "verdict_counts": {"APPROVE": 0, "APPROVE_WITH_CONCERNS": 0,
                                 "REVIEW_UNAVAILABLE": 0, "REJECT": 0},
            "prompt": "secret",
            "api_key": "sk-leak",
        }
        with pytest.raises(ValueError, match="unknown keys"):
            _clean_usefulness(envelope)

    def test_allow_list_is_exactly_the_documented_keys(self) -> None:
        """The frozen allow-list is the single source of truth for
        the bounded contract. If a future engineer adds a key to
        the validator without updating the constant, this test
        catches it.
        """
        assert _ALLOWED_USEFULNESS_KEYS == frozenset({
            "total_completed_reviews",
            "cache_hits",
            "cache_misses",
            "cache_hit_rate",
            "circuit_opens",
            "response_seconds_mean",
            "response_seconds_p95",
            "response_seconds_last",
            "last_completed_at",
            "verdict_counts",
        })
        assert _ALLOWED_VERDICT_KEYS == frozenset({
            "APPROVE", "APPROVE_WITH_CONCERNS",
            "REVIEW_UNAVAILABLE", "REJECT",
        })
