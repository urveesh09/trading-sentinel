"""[ADVISORY 2026-08-05] Tests for the typed conviction verdicts.

The defect being fixed is a category error -- "the model said no" and "the model
never answered" were the same value -- so every test here is about keeping those
two apart under some pressure.
"""
import pytest

from advisory import (
    CONVICTION_CONCERN_BELOW,
    CONVICTION_REJECT_BELOW,
    Review,
    Verdict,
    from_payload,
    unavailable,
    worst,
)


# ── classification ────────────────────────────────────────────────────────

def test_a_high_conviction_score_approves():
    r = from_payload({"conviction_score": 80})
    assert r.verdict is Verdict.APPROVE
    assert r.conviction == 80
    assert r.available is True


def test_a_middling_score_approves_with_concerns():
    r = from_payload({"conviction_score": CONVICTION_CONCERN_BELOW - 1})
    assert r.verdict is Verdict.APPROVE_WITH_CONCERNS


def test_a_low_score_rejects():
    r = from_payload({"conviction_score": CONVICTION_REJECT_BELOW - 1})
    assert r.verdict is Verdict.REJECT


def test_the_reject_boundary_is_unchanged_from_the_shipped_gate():
    """The live gate was `< 50`. Moving it silently would change what trades."""
    assert CONVICTION_REJECT_BELOW == 50
    assert from_payload({"conviction_score": 49}).verdict is Verdict.REJECT
    assert from_payload({"conviction_score": 50}).verdict is not Verdict.REJECT


def test_the_payload_is_preserved_for_the_renderers():
    r = from_payload({"conviction_score": 80, "pitch": "clean breakout"})
    assert r.payload["pitch"] == "clean breakout"


# ── the category error this module exists to fix ──────────────────────────

def test_unavailable_is_distinct_from_reject():
    assert unavailable("timeout_100s").verdict is not from_payload(
        {"conviction_score": 10}).verdict


def test_unavailable_carries_the_specific_reason():
    """'AI analysis failed' covered a 100s timeout and malformed JSON alike."""
    assert unavailable("timeout_100s").reason == "timeout_100s"
    assert unavailable("unparseable_output").reason == "unparseable_output"


def test_a_payload_with_no_conviction_is_unavailable_not_a_veto():
    """Scoring a malfunction as 0 would turn a broken reviewer into a
    confident veto -- the same category error pointing the other way."""
    r = from_payload({"pitch": "no score field"})
    assert r.verdict is Verdict.REVIEW_UNAVAILABLE
    assert r.reason == "missing_conviction_score"


@pytest.mark.parametrize("bad", [None, "high", "", [], {}])
def test_a_non_integer_conviction_is_unavailable(bad):
    assert from_payload({"conviction_score": bad}).verdict is Verdict.REVIEW_UNAVAILABLE


# ── what blocks the EXEC button ───────────────────────────────────────────

def test_reject_blocks():
    assert from_payload({"conviction_score": 10}).blocks() is True


def test_approve_does_not_block():
    assert from_payload({"conviction_score": 90}).blocks() is False


def test_approve_with_concerns_does_not_block():
    """Deliberate: it is a label, not a gate. Making it gate would silently
    tighten what trades."""
    assert from_payload({"conviction_score": 55}).blocks() is False


def test_unavailable_proceeds_by_default_preserving_todays_behaviour():
    """The alert still goes out with a banner. Changing this would change who
    decides trades, which is not a refactor's call to make."""
    assert unavailable("timeout_100s").blocks() is False
    assert unavailable("timeout_100s").blocks(unavailable_policy="proceed") is False


def test_unavailable_can_be_configured_to_block():
    assert unavailable("timeout_100s").blocks(unavailable_policy="block") is True


def test_an_unrecognised_policy_falls_back_to_proceeding():
    """A typo in an env var must not silently stop the book from trading."""
    assert unavailable("timeout_100s").blocks(unavailable_policy="blokc") is False


def test_reject_blocks_regardless_of_the_unavailable_policy():
    assert from_payload({"conviction_score": 10}).blocks(
        unavailable_policy="proceed") is True


# ── worst-case aggregation ────────────────────────────────────────────────

def test_unavailable_outranks_approve_with_concerns():
    """The ranking that keeps a broken reviewer loud rather than invisible."""
    result = worst(from_payload({"conviction_score": 55}),
                   unavailable("timeout_100s"))
    assert result.verdict is Verdict.REVIEW_UNAVAILABLE


def test_reject_outranks_everything():
    result = worst(from_payload({"conviction_score": 95}),
                   unavailable("api_error"),
                   from_payload({"conviction_score": 5}))
    assert result.verdict is Verdict.REJECT


def test_all_approvals_aggregate_to_approve():
    result = worst(from_payload({"conviction_score": 90}),
                   from_payload({"conviction_score": 85}))
    assert result.verdict is Verdict.APPROVE


def test_no_reviewers_is_unavailable_not_approve():
    assert worst().verdict is Verdict.REVIEW_UNAVAILABLE


# ── the operator-facing line ──────────────────────────────────────────────

def test_the_banner_names_the_failure_for_an_unavailable_review():
    text = unavailable("timeout_100s").banner()
    assert "UNAVAILABLE" in text
    assert "timeout_100s" in text


def test_the_banner_gives_the_score_for_a_completed_review():
    assert "72" in from_payload({"conviction_score": 72}).banner()


def test_the_banner_says_rejected_when_rejected():
    assert "REJECTED" in from_payload({"conviction_score": 20}).banner()


def test_the_banner_flags_concerns():
    assert "CONCERNS" in from_payload({"conviction_score": 55}).banner()
