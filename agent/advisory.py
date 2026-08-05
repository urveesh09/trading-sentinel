"""[ADVISORY 2026-08-05] Typed verdicts for the MiniMax conviction gate.

THE DEFECT
----------
`analyze_with_minimax` returned a dict on success and `None` on failure, and
`None` collapsed four genuinely different outcomes into one:

    the request timed out after 100s
    the model returned prose instead of JSON
    the JSON was missing a field
    the API itself errored

All four then took the SAME path as each other, and that path was "send the
EXEC button anyway with an 'AI analysis failed' banner". Meanwhile a conviction
of 30 -- the model working perfectly and saying no -- blocked the button.

So the gate blocks when it works and permits when it breaks. On 2026-08-04 the
single trade this system executed got its button precisely because MiniMax
timed out; it lost Rs 8.41. Three signals the model actively vetoed never
reached the operator at all.

THE FIX, AND WHAT IT DELIBERATELY DOES NOT CHANGE
-------------------------------------------------
Borrowed from HKUDS/Vibe-Trading's `src/live/advisory` (MIT), which separates
an OBSERVATIONAL risk opinion from the deterministic gate that actually decides.
Their verdict set is approve / approve_with_concerns / reject /
review_unavailable, aggregated worst-case, and the fourth value is ranked MORE
severe than "approve with concerns" so a broken reviewer is loud rather than
invisible.

We adopt the vocabulary and the ranking. We do NOT adopt their policy of never
blocking, because that would change who decides trades, and that is the
operator's call to make rather than a refactor's side effect. So:

  * REJECT still blocks the EXEC button, exactly as today.
  * REVIEW_UNAVAILABLE still lets the alert through by default, exactly as
    today -- but it now carries WHY, that reason reaches the operator's phone,
    and it is a distinct verdict rather than an absence.
  * `unavailable_policy="block"` flips the second behaviour for anyone who
    would rather trade nothing than trade unreviewed. Off by default.

Pure and dependency-free so it can be tested without an API key.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class Verdict(str, Enum):
    """The reviewer's opinion on one signal."""

    APPROVE = "approve"
    APPROVE_WITH_CONCERNS = "approve_with_concerns"
    REVIEW_UNAVAILABLE = "review_unavailable"
    REJECT = "reject"


#: Worst-case ordering. REVIEW_UNAVAILABLE outranks APPROVE_WITH_CONCERNS on
#: purpose: "I could not look" is a worse state to trade into than "I looked and
#: had reservations", and burying it below a mild approval is how it stayed
#: invisible for a month.
VERDICT_SEVERITY = {
    Verdict.APPROVE: 0,
    Verdict.APPROVE_WITH_CONCERNS: 1,
    Verdict.REVIEW_UNAVAILABLE: 2,
    Verdict.REJECT: 3,
}

#: Below this the reviewer is vetoing. Unchanged from the shipped gate.
CONVICTION_REJECT_BELOW = 50

#: Between reject and this, the reviewer is uneasy but not opposed. Purely a
#: labelling distinction today -- it does not gate anything.
CONVICTION_CONCERN_BELOW = 65


@dataclass(frozen=True)
class Review:
    """One reviewer opinion, with everything the operator needs to judge it.

    Attributes:
        verdict: The typed outcome.
        conviction: 0-100 score, or None when the review never completed.
        reason: For REVIEW_UNAVAILABLE, WHY it is unavailable ("timeout_100s",
            "unparseable_output", "schema_mismatch", "api_error"). Empty
            otherwise. This is the field that did not exist before.
        payload: The model's parsed output when there is one, so existing
            renderers can keep reading pitch / rationale / risks.
    """

    verdict: Verdict
    conviction: Optional[int] = None
    reason: str = ""
    payload: dict[str, Any] = field(default_factory=dict)

    @property
    def available(self) -> bool:
        """Did the reviewer actually render an opinion?"""
        return self.verdict is not Verdict.REVIEW_UNAVAILABLE

    def blocks(self, *, unavailable_policy: str = "proceed") -> bool:
        """Should this stop the EXEC button from being sent?

        Args:
            unavailable_policy: "proceed" (default, today's behaviour) sends
                the alert when the reviewer is unavailable. "block" refuses.
                The choice is a genuine risk-posture decision -- proceed means
                trading unreviewed, block means a MiniMax outage stops the
                book -- so it is configuration, not a default someone inherits.
        """
        if self.verdict is Verdict.REJECT:
            return True
        if self.verdict is Verdict.REVIEW_UNAVAILABLE:
            return unavailable_policy == "block"
        return False

    def banner(self) -> str:
        """One line for the top of the Telegram alert."""
        if self.verdict is Verdict.REVIEW_UNAVAILABLE:
            return f"AI review UNAVAILABLE ({self.reason or 'unknown'}) - unreviewed"
        if self.verdict is Verdict.REJECT:
            return f"AI REJECTED (conviction {self.conviction}/100)"
        if self.verdict is Verdict.APPROVE_WITH_CONCERNS:
            return f"AI approved WITH CONCERNS (conviction {self.conviction}/100)"
        return f"AI approved (conviction {self.conviction}/100)"


def unavailable(reason: str) -> Review:
    """Build a REVIEW_UNAVAILABLE carrying the specific failure."""
    return Review(verdict=Verdict.REVIEW_UNAVAILABLE, reason=reason)


def from_payload(payload: dict[str, Any]) -> Review:
    """Classify a parsed model response into a verdict.

    A payload that validated but carries no usable conviction is treated as
    UNAVAILABLE rather than silently scored 0 -- scoring it 0 would turn a
    reviewer malfunction into a confident veto, which is the same category of
    mistake as the one this module exists to fix, pointing the other way.
    """
    raw = payload.get("conviction_score")
    try:
        conviction = int(raw)
    except (TypeError, ValueError):
        return Review(
            verdict=Verdict.REVIEW_UNAVAILABLE,
            reason="missing_conviction_score",
            payload=payload,
        )

    if conviction < CONVICTION_REJECT_BELOW:
        verdict = Verdict.REJECT
    elif conviction < CONVICTION_CONCERN_BELOW:
        verdict = Verdict.APPROVE_WITH_CONCERNS
    else:
        verdict = Verdict.APPROVE
    return Review(verdict=verdict, conviction=conviction, payload=payload)


def worst(*reviews: Review) -> Review:
    """Worst-case aggregation, for when more than one reviewer exists.

    Only one runs today. The function is here because the aggregation rule is
    the part that is easy to get wrong later, and pinning it now with tests
    costs nothing.
    """
    live = [r for r in reviews if r is not None]
    if not live:
        return unavailable("no_reviewers")
    return max(live, key=lambda r: VERDICT_SEVERITY[r.verdict])
