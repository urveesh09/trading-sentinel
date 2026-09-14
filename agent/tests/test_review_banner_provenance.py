"""[WORKFLOW-I I.B 2026-09-13] Review banner provenance acceptance.

Closes the I.B slice: surface I1 provenance in the operator
alert. Per §13: "Store model/prompt/version ... response time
and expiry." The data is captured; this slice makes it visible
in the alert itself so the operator can audit which model and
prompt produced a verdict they acted on.

Coverage
--------
1. Banner suffix is empty when provenance is absent (legacy /
   pre-I1 reviews, default-constructed reviews).
2. Banner carries the model, prompt_version, and response_seconds
   when provenance is populated.
3. Banner is bounded: total length stays under 200 chars.
4. Format is `` · <model>@<prompt_version> <secs>s`` with the
   ``@`` separator.
5. Sub-100ms reviews render as ``0.1s`` (clamped), not ``0.0s``.
6. ``response_seconds=None`` renders as ``?s`` (honest about
   missing data, no fake zero).
7. UNAVAILABLE verdict still gets the suffix when provenance
   is present (the operator may want to know which prompt
   failed).
8. Missing-model OR missing-prompt_version: suffix absent
   (no half-provenance -- contract requires both).
9. Existing banner substring assertions (``UNAVAILABLE``,
   ``REJECTED``, ``CONCERNS``, ``72``) still pass on the
   suffixed banner -- backwards-compatible substring checks.
10. The four verdict banners stay distinct.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from advisory import (
    Review,
    Verdict,
    from_payload,
    unavailable,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _provenance_review(
    *, verdict: Verdict, response_seconds: float | None,
    conviction: int = 70,
) -> Review:
    """A Review with all three provenance fields populated."""
    return Review(
        verdict=verdict, conviction=conviction,
        model="MiniMax-M3", base_url="https://api.minimax.io/v1",
        prompt_version="v1",
        started_at=_now(),
        completed_at=_now(),
        response_seconds=response_seconds,
    )


# ---- (1) suffix presence/absence -----------------------------------------

class TestSuffixPresence:
    def test_no_provenance_means_no_suffix(self) -> None:
        """Legacy / pre-I1 Review: no model, no prompt_version,
        no suffix. The banner stays in its pre-I1 form."""
        r = Review(verdict=Verdict.APPROVE, conviction=70)
        b = r.banner()
        assert b == "AI approved (conviction 70/100)"
        assert "@" not in b
        assert "MiniMax" not in b

    def test_full_provenance_appends_suffix(self) -> None:
        r = _provenance_review(
            verdict=Verdict.APPROVE, response_seconds=1.5,
        )
        b = r.banner()
        assert b.endswith(" · MiniMax-M3@v1 1.5s")
        assert "AI approved (conviction 70/100)" in b

    def test_missing_model_means_no_suffix(self) -> None:
        """Half-provenance (model but no prompt_version, or vice
        versa) is treated as no-provenance. The contract requires
        both fields; emitting half would mislead operators.
        """
        r = Review(
            verdict=Verdict.APPROVE, conviction=70,
            model="MiniMax-M3",
            prompt_version=None,
            response_seconds=1.5,
        )
        assert "MiniMax" not in r.banner()

        r2 = Review(
            verdict=Verdict.APPROVE, conviction=70,
            model=None,
            prompt_version="v1",
            response_seconds=1.5,
        )
        assert "v1" not in r2.banner()


# ---- (2) format details ---------------------------------------------------

class TestFormatDetails:
    def test_format_uses_at_separator(self) -> None:
        """The ``@`` separator lets an operator scan the model
        and prompt version visually without context."""
        r = _provenance_review(verdict=Verdict.APPROVE, response_seconds=1.5)
        assert "@v1" in r.banner()

    def test_response_seconds_one_decimal(self) -> None:
        """Format to one decimal place: 1.5s, 12.34s -> 12.3s, 0s -> 0.1s."""
        r = _provenance_review(verdict=Verdict.APPROVE, response_seconds=12.34)
        assert "12.3s" in r.banner()
        assert "12.34s" not in r.banner()

    def test_sub_100ms_clamped_to_minimum(self) -> None:
        """A 0.05s review renders as ``0.1s`` (clamped), not
        ``0.0s`` (which would look like a no-op)."""
        r = _provenance_review(verdict=Verdict.APPROVE, response_seconds=0.05)
        assert "0.1s" in r.banner()
        assert "0.0s" not in r.banner()

    def test_response_seconds_none_renders_as_question_mark(self) -> None:
        """``None`` is honest about missing data: ``?s``. Operators
        can tell at a glance that the call did not complete.
        """
        r = _provenance_review(verdict=Verdict.APPROVE, response_seconds=None)
        assert "?s" in r.banner()

    def test_negative_response_seconds_clamped_to_minimum(self) -> None:
        """Defensive: clock skew could produce a negative
        duration (started_at > completed_at). Clamp to 0.1s.
        """
        r = _provenance_review(verdict=Verdict.APPROVE, response_seconds=-2.0)
        assert "0.1s" in r.banner()
        assert "-2.0s" not in r.banner()


# ---- (3) banner length bound ---------------------------------------------

class TestBannerLength:
    """The banner is a single line in a Telegram alert. It must
    stay readable -- a 500-char banner defeats the purpose.
    """

    @pytest.mark.parametrize("verdict,conviction", [
        (Verdict.APPROVE, 70),
        (Verdict.APPROVE_WITH_CONCERNS, 55),
        (Verdict.REJECT, 20),
        (Verdict.REVIEW_UNAVAILABLE, None),
    ])
    def test_banner_with_provenance_under_200_chars(
        self, verdict: Verdict, conviction: int | None,
    ) -> None:
        r = _provenance_review(verdict=verdict, response_seconds=120.0)
        if conviction is not None:
            r = Review(
                verdict=verdict, conviction=conviction,
                model=r.model, base_url=r.base_url,
                prompt_version=r.prompt_version,
                started_at=r.started_at, completed_at=r.completed_at,
                response_seconds=r.response_seconds,
            )
        else:
            r = unavailable("timeout_120s")
            r = Review(
                verdict=verdict, reason=r.reason,
                model=r.model, base_url=r.base_url,
                prompt_version=r.prompt_version,
                started_at=r.started_at, completed_at=r.completed_at,
                response_seconds=r.response_seconds,
            )
        assert len(r.banner()) < 200, (
            f"banner too long ({len(r.banner())} chars): {r.banner()!r}"
        )


# ---- (4) verdict-specific checks -----------------------------------------

class TestVerdictSpecific:
    def test_approved_carries_provenance(self) -> None:
        r = _provenance_review(verdict=Verdict.APPROVE, response_seconds=2.0)
        b = r.banner()
        assert b.startswith("AI approved (")
        assert " · MiniMax-M3@v1 2.0s" in b

    def test_approved_with_concerns_carries_provenance(self) -> None:
        r = _provenance_review(
            verdict=Verdict.APPROVE_WITH_CONCERNS, response_seconds=2.0,
        )
        b = r.banner()
        assert b.startswith("AI approved WITH CONCERNS (")
        assert " · MiniMax-M3@v1 2.0s" in b

    def test_rejected_carries_provenance(self) -> None:
        r = _provenance_review(verdict=Verdict.REJECT, response_seconds=2.0)
        b = r.banner()
        assert b.startswith("AI REJECTED (")
        assert " · MiniMax-M3@v1 2.0s" in b

    def test_unavailable_with_provenance_carries_provenance(self) -> None:
        """Even UNAVAILABLE verdicts get the suffix when
        provenance is present -- the operator may want to know
        which prompt/model timed out.
        """
        r = _provenance_review(
            verdict=Verdict.REVIEW_UNAVAILABLE, response_seconds=120.0,
        )
        # conviction=None is fine; we set reason instead.
        r = Review(
            verdict=Verdict.REVIEW_UNAVAILABLE,
            reason="timeout_120s", conviction=None,
            model=r.model, base_url=r.base_url,
            prompt_version=r.prompt_version,
            started_at=r.started_at, completed_at=r.completed_at,
            response_seconds=r.response_seconds,
        )
        b = r.banner()
        assert b.startswith("AI review UNAVAILABLE (")
        assert "timeout_120s" in b
        assert " · MiniMax-M3@v1 120.0s" in b

    def test_four_verdicts_produce_distinct_banners(self) -> None:
        """Belt-and-braces: the four verdict banners remain
        distinct even after adding the suffix.
        """
        banners = set()
        for v in (
            Verdict.APPROVE, Verdict.APPROVE_WITH_CONCERNS,
            Verdict.REJECT, Verdict.REVIEW_UNAVAILABLE,
        ):
            if v is Verdict.REVIEW_UNAVAILABLE:
                r = Review(
                    verdict=v, reason="timeout",
                    model="MiniMax-M3", prompt_version="v1",
                    response_seconds=1.0,
                )
            else:
                r = Review(
                    verdict=v, conviction=70,
                    model="MiniMax-M3", prompt_version="v1",
                    response_seconds=1.0,
                )
            banners.add(r.banner().split(" ·")[0])
        assert len(banners) == 4


# ---- (5) backwards-compatible substring checks ---------------------------

class TestBackwardsCompatSubstrings:
    """The pre-I1 banner tests assert substrings. They must
    still pass on the suffixed banner.
    """

    def test_unavailable_substring_still_matches(self) -> None:
        r = _provenance_review(
            verdict=Verdict.REVIEW_UNAVAILABLE, response_seconds=120.0,
        )
        r = Review(
            verdict=Verdict.REVIEW_UNAVAILABLE, reason="timeout_100s",
            model=r.model, prompt_version=r.prompt_version,
            response_seconds=r.response_seconds,
        )
        assert "UNAVAILABLE" in r.banner()
        assert "timeout_100s" in r.banner()

    def test_approved_score_substring_still_matches(self) -> None:
        r = _provenance_review(
            verdict=Verdict.APPROVE, response_seconds=1.0,
        )
        r = from_payload({"conviction_score": 72})
        r = Review(
            verdict=r.verdict, conviction=r.conviction,
            model="MiniMax-M3", prompt_version="v1",
            response_seconds=1.0,
        )
        assert "72" in r.banner()

    def test_rejected_substring_still_matches(self) -> None:
        r = from_payload({"conviction_score": 20})
        r = Review(
            verdict=r.verdict, conviction=r.conviction,
            model="MiniMax-M3", prompt_version="v1",
            response_seconds=1.0,
        )
        assert "REJECTED" in r.banner()

    def test_concerns_substring_still_matches(self) -> None:
        r = from_payload({"conviction_score": 55})
        r = Review(
            verdict=r.verdict, conviction=r.conviction,
            model="MiniMax-M3", prompt_version="v1",
            response_seconds=1.0,
        )
        assert "CONCERNS" in r.banner()
