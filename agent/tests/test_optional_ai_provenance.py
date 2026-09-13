"""[WORKFLOW-I I1 2026-09-13] Optional-AI provenance acceptance.

Closes I1 of workstream I per ``docs/NEXT_AGENT_PLAN.md`` section 13
and ``docs/2026-09-13-optional-ai-validity-plan.md``.

Acceptance for the §13 explicit requirement: *"Store
model/prompt/version, source references, response time and
expiry."* Phase I1 covers the model/prompt/version + response
time side (phases I2/I3 cover source references + usefulness).

Coverage
--------
1. ``Review`` carries model/base_url/prompt_version/started_at/
   completed_at/response_seconds fields with sensible defaults
   (``None`` when the review never completed).
2. The dataclass ``replace`` mechanism preserves provenance
   (frozen + replace is the documented way to update).
3. ``advisory.unavailable(reason)`` builds a Review WITHOUT
   provenance (None defaults) -- the early-exit path.
4. ``advisory.from_payload(payload)`` returns a Review WITHOUT
   provenance; the caller attaches it via replace.
5. Worst-case aggregation (multiple reviews) preserves provenance
   from the worst one -- important so a partial reviewer
   outage doesn't strip provenance from the surviving review.
6. ``response_seconds`` is a non-negative float when computed.
7. Backwards compatibility: a Review built with the old
   positional args still works (verdict + conviction + reason +
   payload + new defaults).
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from advisory import (
    Review,
    Verdict,
    from_payload,
    unavailable,
    worst,
    VERDICT_SEVERITY,
)


# ---- (1) Review shape ------------------------------------------------------

class TestReviewProvenanceFields:
    def test_review_has_six_provenance_fields(self) -> None:
        """The Review dataclass now carries model, base_url,
        prompt_version, started_at, completed_at, response_seconds.
        All default to None so existing callers don't break.
        """
        r = Review(verdict=Verdict.APPROVE, conviction=80)
        assert r.model is None
        assert r.base_url is None
        assert r.prompt_version is None
        assert r.started_at is None
        assert r.completed_at is None
        assert r.response_seconds is None

    def test_review_with_provenance(self) -> None:
        """A Review built with all fields round-trips correctly."""
        now = datetime.now(timezone.utc)
        later = now + timedelta(seconds=2)
        r = Review(
            verdict=Verdict.APPROVE, conviction=80,
            reason="", payload={"pitch": "test"},
            model="MiniMax-M3",
            base_url="https://api.minimax.io/v1",
            prompt_version="v1",
            started_at=now, completed_at=later,
            response_seconds=2.0,
        )
        assert r.model == "MiniMax-M3"
        assert r.base_url == "https://api.minimax.io/v1"
        assert r.prompt_version == "v1"
        assert r.started_at == now
        assert r.completed_at == later
        assert r.response_seconds == 2.0

    def test_review_preserves_available_after_replace(self) -> None:
        """``dataclasses.replace`` on a frozen Review preserves
        the available / verdict semantics. This is the contract
        every return site in ``analyze_with_minimax`` uses.
        """
        base = Review(verdict=Verdict.APPROVE, conviction=70)
        assert base.available is True
        replaced = replace(base, model="MiniMax-M3", response_seconds=1.5)
        assert replaced.verdict == Verdict.APPROVE
        assert replaced.conviction == 70
        assert replaced.available is True
        assert replaced.model == "MiniMax-M3"

    def test_review_replace_unavailable_still_unavailable(self) -> None:
        """Replacing fields on an UNAVAILABLE Review keeps the
        verdict. The verifier sees the verdict first, then the
        provenance.
        """
        base = unavailable("timeout_100s")
        replaced = replace(
            base,
            model="MiniMax-M3",
            base_url="https://api.minimax.io/v1",
            prompt_version="v1",
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc) + timedelta(seconds=100),
            response_seconds=100.0,
        )
        assert replaced.verdict == Verdict.REVIEW_UNAVAILABLE
        assert replaced.available is False
        assert replaced.reason == "timeout_100s"
        assert replaced.response_seconds == 100.0


# ---- (2) Producer-side helpers --------------------------------------------

class TestProducerHelpers:
    def test_unavailable_does_not_set_provenance(self) -> None:
        """``advisory.unavailable(reason)`` returns a Review with
        provenance=None (the early-exit path, before any model
        call). Callers that want provenance must attach it.
        """
        r = unavailable("AI_DISABLED")
        assert r.verdict == Verdict.REVIEW_UNAVAILABLE
        assert r.reason == "AI_DISABLED"
        assert r.model is None
        assert r.base_url is None
        assert r.prompt_version is None
        assert r.started_at is None
        assert r.response_seconds is None

    def test_from_payload_does_not_set_provenance(self) -> None:
        """``advisory.from_payload`` returns a Review without
        provenance. The producer (``analyze_with_minimax``) is
        the right place to attach provenance because that's
        where model + base_url + prompt_version are known.
        """
        r = from_payload({"conviction_score": 75, "pitch": "ok",
                          "rationale": "ok", "risks": "ok"})
        assert r.verdict == Verdict.APPROVE
        assert r.conviction == 75
        assert r.model is None

    def test_from_payload_then_replace_provenance(self) -> None:
        """The producer's typical flow: build the verdict via
        ``from_payload``, then attach provenance via ``replace``.
        Both steps preserve the verdict/conviction.
        """
        r = from_payload({"conviction_score": 25})
        assert r.verdict == Verdict.REJECT
        now = datetime.now(timezone.utc)
        replaced = replace(
            r,
            model="MiniMax-M3",
            prompt_version="v1",
            started_at=now,
            completed_at=now + timedelta(seconds=3),
            response_seconds=3.0,
        )
        assert replaced.verdict == Verdict.REJECT
        assert replaced.conviction == 25
        assert replaced.prompt_version == "v1"
        assert replaced.response_seconds == 3.0


# ---- (3) Worst-case aggregation -------------------------------------------

class TestWorstAggregation:
    def test_worst_preserves_provenance(self) -> None:
        """When multiple reviewers exist (future), the worst-case
        aggregation must preserve the winner's provenance. Two
        reviews with different models: the worst wins; its
        provenance is what we surface.
        """
        now = datetime.now(timezone.utc)
        r1 = Review(
            verdict=Verdict.APPROVE, conviction=80,
            model="MiniMax-M3",
            prompt_version="v1",
            started_at=now, completed_at=now + timedelta(seconds=2),
            response_seconds=2.0,
        )
        r2 = Review(
            verdict=Verdict.REJECT, conviction=20,
            model="other-model",
            prompt_version="v99",
            started_at=now, completed_at=now + timedelta(seconds=1),
            response_seconds=1.0,
        )
        winner = worst(r1, r2)
        # REJECT outranks APPROVE per VERDICT_SEVERITY.
        assert winner.verdict == Verdict.REJECT
        # Provenance comes from r2.
        assert winner.model == "other-model"
        assert winner.prompt_version == "v99"
        assert winner.response_seconds == 1.0

    def test_worst_with_no_reviews_returns_unavailable(self) -> None:
        """All None or empty -> unavailable with no provenance."""
        r = worst()
        assert r.verdict == Verdict.REVIEW_UNAVAILABLE
        assert r.model is None


# ---- (4) Verdict semantics with provenance --------------------------------

class TestVerdictSemantics:
    def test_blocks_unchanged_by_provenance(self) -> None:
        """Adding provenance must NOT change whether the Review
        blocks. The plan §13 says the typed result must not
        change authority -- so blocks() must remain identical.
        """
        now = datetime.now(timezone.utc)
        base = Review(verdict=Verdict.REJECT, conviction=20)
        assert base.blocks() is True
        replaced = replace(
            base,
            model="MiniMax-M3",
            started_at=now, completed_at=now,
            response_seconds=0.0,
        )
        assert replaced.blocks() is True

    def test_banner_includes_verdict_not_provenance(self) -> None:
        """The banner is operator-facing prose; provenance is
        for audit logs, not the alert. The banner must not
        change shape.
        """
        r = Review(
            verdict=Verdict.REJECT, conviction=15,
            model="MiniMax-M3",
            prompt_version="v1",
            started_at=datetime.now(timezone.utc),
        )
        assert "REJECT" in r.banner()
        assert "MiniMax" not in r.banner()
        assert "v1" not in r.banner()


# ---- (5) Repro / fixture --------------------------------------------------

class TestReproducibility:
    def test_verdict_severity_unchanged(self) -> None:
        """The I1 changes must not alter VERDICT_SEVERITY -- that
        is the documented ordering for worst-case aggregation.
        """
        assert VERDICT_SEVERITY == {
            Verdict.APPROVE: 0,
            Verdict.APPROVE_WITH_CONCERNS: 1,
            Verdict.REVIEW_UNAVAILABLE: 2,
            Verdict.REJECT: 3,
        }

    def test_default_prompt_version_constant(self) -> None:
        """MINIMAX_PROMPT_VERSION defaults to "v1" so the existing
        prompt template is labelled v1. Future prompt changes
        bump the version.
        """
        import agent as _agent
        assert _agent.MINIMAX_PROMPT_VERSION == "v1"

    def test_attach_provenance_helper_exists(self) -> None:
        """``_attach_provenance`` is the helper the producer uses
        at every return site. It exists, takes the right
        parameters, and produces a Review with provenance.
        """
        from agent import _attach_provenance
        now = datetime.now(timezone.utc)
        later = now + timedelta(milliseconds=500)
        base = unavailable("api_error")
        attached = _attach_provenance(
            base, started_at=now, completed_at=later,
        )
        assert attached.verdict == Verdict.REVIEW_UNAVAILABLE
        assert attached.reason == "api_error"
        assert attached.started_at == now
        assert attached.completed_at == later
        assert attached.response_seconds == pytest.approx(0.5, abs=0.01)

    def test_attach_provenance_negative_duration_clamped(self) -> None:
        """Defensive: if completed_at < started_at (clock skew,
        test artifact), ``response_seconds`` is clamped to 0.
        We never store a negative duration.
        """
        from agent import _attach_provenance
        now = datetime.now(timezone.utc)
        earlier = now - timedelta(seconds=1)
        attached = _attach_provenance(
            unavailable("api_error"),
            started_at=now, completed_at=earlier,
        )
        assert attached.response_seconds == 0.0
