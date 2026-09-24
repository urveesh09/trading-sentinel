"""[WORKFLOW-I.4.D 2026-09-14] Source-event classification.

This module classifies one or more ``NewsItem`` (from the I.2 news
provenance work) against a fixed taxonomy of 8 categories. The
classification is **informational only** -- the verdict pipeline
(``analyze_with_minimax``) is not modified; classification is
surfaced as a bounded annotation that the operator can inspect.

Per plan §13, the agent must "classify sourced events" before the
existing pipeline summarises them. Today the prompt to
``analyze_with_minimax`` includes raw news text and asks the model
to "evaluate whether the news/catalyst justifies a sustained move"
-- the model has to do its own classification implicitly. This
module makes that step explicit and bounded:

  1. Fixed taxonomy of 8 categories (see ``NewsCategory``).
     A category not in the taxonomy is labelled ``UNKNOWN``.
  2. One-shot classification with a bounded confidence score
     in [0.0, 1.0]. ``CONFIDENCE_THRESHOLD`` is the floor below
     which the result is forced to ``UNKNOWN`` (the gate is
     fail-closed: a low-confidence classifier must NOT pretend
     to know).
  3. Latency budget: the per-item MiniMax call uses a short
     prompt + a 1.0s ceiling (``CLASSIFIER_TIMEOUT_SEC``). The
     classification does NOT block the existing verdict path;
     if the classifier times out or the model returns garbage,
     the item is labelled ``UNKNOWN`` and the verdict path
     continues with raw text.
  4. Deterministic pipeline untouched: ``analyze_with_minimax``
     does not change shape. When the operator supplies pre-
     classifications (e.g. via a new ``--classify-news`` CLI),
     they are surfaced in the prompt as a "CLASSIFIED SENTIMENT
     DATA" section. When the operator does not, the verdict
     pipeline continues to consume raw ``sentiment_text`` as
     before.

This module is pure / total:

  * Never raises from a model API failure -- returns
    ``UNKNOWN`` with ``confidence=0.0`` and a human-readable
    ``rationale`` explaining the failure.
  * Never returns a category outside ``NewsCategory`` -- the
    parser maps unknown strings to ``UNKNOWN``.
  * Never mutates the input ``NewsItem`` (it's frozen).

Senior-dev honesty: this adds one model call per signal's news
batch (the same news that ``scrape_sentiment`` already collects).
Latency budget is enforced; on a busy day the worst case is a
1s-per-item classification delay before the verdict pipeline
continues. The verdict pipeline is unchanged so existing tests
are unaffected.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import TYPE_CHECKING, Iterable, List, Optional
from urllib.parse import urlsplit, urlunsplit

if TYPE_CHECKING:
    from agent import NewsItem

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# [WORKFLOW-I.4.D 2026-09-14] Per-item timeout for the classifier
# model call. The deep-research doc says "Latency budget: < 1s
# per item"; we cap the call at 1.0s and treat timeout as
# ``UNKNOWN``. The verdict pipeline is unaffected.
CLASSIFIER_TIMEOUT_SEC: float = float(os.getenv("CLASSIFIER_TIMEOUT_SEC", "1.0"))

# The classifier is informational and has a per-item latency contract. It must
# not inherit the verdict reviewer's retry budget: a second SDK attempt can
# turn a nominal one-second request into the observed multi-second wait.
CLASSIFIER_MAX_RETRIES: int = 0

# [WORKFLOW-I.4.D 2026-09-14] Confidence floor. A result below
# this threshold is forced to ``UNKNOWN`` (fail-closed). The
# taxonomy is fixed; we trust the model to assign a calibrated
# score; below ~60% we don't trust it enough to label the item.
CONFIDENCE_THRESHOLD: float = float(os.getenv("CLASSIFIER_CONFIDENCE_THRESHOLD", "0.6"))

# [WORKFLOW-I.4.D 2026-09-14] Prompt version. Bumped when the
# classifier prompt changes; cached results keep the version
# they were produced with so a prompt change never invalidates
# an old annotation silently (same pattern as the I.1 verdict
# provenance work).
CLASSIFIER_PROMPT_VERSION: str = os.getenv("CLASSIFIER_PROMPT_VERSION", "v1")

# [WORKFLOW-I.4.D 2026-09-14] Model. Same env var as the verdict
# path; the classifier uses a smaller / faster prompt and a
# tighter timeout, but its no-retry client is deliberately separate
# from the verdict client's longer retry policy.
CLASSIFIER_MODEL: str = os.getenv(
    "CLASSIFIER_MODEL", os.getenv("MINIMAX_MODEL", "MiniMax-M3")
)

# [WORKFLOW-I.4.D 2026-09-14] Toggle. ``DISABLE_CLASSIFIER=1``
# forces every classification to ``UNKNOWN`` (no model call).
# Useful for offline / CI / sandbox environments where the
# classifier model is unavailable but the verdict pipeline
# still runs.
CLASSIFIER_DISABLED: bool = os.getenv("DISABLE_CLASSIFIER", "0") == "1"

# Matches the existing ``stale_aged_Nd`` prompt vocabulary. At seven days the
# source ceases to be current evidence for a newly minted annotation.
SOURCE_MAX_AGE = timedelta(days=7)


# ---------------------------------------------------------------------------
# Taxonomy
# ---------------------------------------------------------------------------


class NewsCategory(str, Enum):
    """[WORKFLOW-I.4.D 2026-09-14] Fixed taxonomy of news categories.

    Eight bounded values per the I.4 deep-research doc:

      - ``REGULATORY``: SEBI / exchange / government action
      - ``EARNINGS``: quarterly / annual results, guidance beat/miss
      - ``M_AND_A``: acquisitions, mergers, spin-offs
      - ``GUIDANCE``: forward-looking company guidance
      - ``MACRO``: macro / sector / commodity / currency
      - ``RUMOR``: unverified social-media / unconfirmed report
      - ``TECHNICAL``: chart / momentum / pattern, no fundamental
      - ``UNKNOWN``: cannot classify (low confidence, parse
        failure, timeout, or category outside this set)

    A category the model invents but is not in this enum is
    mapped to ``UNKNOWN`` (fail-closed: the taxonomy is
    operator-defined, not model-defined).
    """

    REGULATORY = "regulatory"
    EARNINGS = "earnings"
    M_AND_A = "m_and_a"
    GUIDANCE = "guidance"
    MACRO = "macro"
    RUMOR = "rumor"
    TECHNICAL = "technical"
    UNKNOWN = "unknown"


# Public lookup for the parser; built from ``NewsCategory`` so a
# new enum value automatically gets accepted by the validator.
_VALID_CATEGORIES = frozenset(c.value for c in NewsCategory)


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ClassificationResult:
    """[WORKFLOW-I.4.D 2026-09-14] One classification of one ``NewsItem``.

    Frozen so a downstream consumer cannot silently mutate a
    classification after it was computed (same audit-trail
    discipline as ``NewsItem`` and ``Review``).

    Attributes:
        ticker: The ticker the news was associated with. Carried
            for convenience so a downstream consumer does not
            have to join on the source ``NewsItem``.
        title_hash: A short stable hash of the news title. The
            classification is keyed on the hash, NOT the raw
            title, so log lines do not leak news content.
        category: The bounded ``NewsCategory``. Always one of
            the 8 enum values; the parser maps anything else
            to ``UNKNOWN``.
        confidence: Bounded ``[0.0, 1.0]``. Below
            ``CONFIDENCE_THRESHOLD`` the result is forced to
            ``UNKNOWN`` (the dataclass is built with the
            threshold-applied category, not the raw model
            output, so consumers never see a low-confidence
            non-UNKNOWN label).
        rationale: One-sentence reason the model gave. Carried
            for audit; bounded to a max of 280 chars at the
            builder to prevent unbounded text leaking into the
            verdict pipeline prompt.
        prompt_version: The ``CLASSIFIER_PROMPT_VERSION`` the
            result was produced with. So a future prompt change
            never invalidates an old annotation silently.
        classified_at: UTC timestamp the model call completed.
            None when the call did not complete (timeout /
            error / disabled).
        source_name/source_url: Bounded publisher label and retrievable source
            reference from the exact rendered feed item.
        published_at: Normalised aware UTC publication time, or None when the
            feed clock was absent/invalid (which forces UNKNOWN).
        source_ref: Full SHA-256 over title plus normalised source evidence.
        source_valid_until: Publication time plus the declared seven-day
            freshness window, retained even when the item is already stale.
    """

    ticker: str
    title_hash: str
    category: NewsCategory
    confidence: float
    rationale: str
    prompt_version: str
    classified_at: Optional[datetime]
    source_name: str = ""
    source_url: str = ""
    published_at: Optional[datetime] = None
    source_ref: str = ""
    source_valid_until: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Title hashing
# ---------------------------------------------------------------------------


def _title_hash(title: str) -> str:
    """[WORKFLOW-I.4.D 2026-09-14] Short stable hash of a news
    title. Used so log lines and JSON envelopes can identify a
    classification without leaking the headline itself.

    Format: 12 hex chars (48 bits of SHA-256). Not for security
    use; just a deterministic, short identifier.
    """
    return hashlib.sha256(title.encode("utf-8", errors="replace")).hexdigest()[:12]


def _bounded_text(value: object, limit: int) -> str:
    return str(value or "").strip()[:limit]


def _normalise_source_url(value: object) -> str:
    raw = _bounded_text(value, 2048)
    try:
        parsed = urlsplit(raw)
        # Access validates non-numeric and out-of-range ports.
        _ = parsed.port
    except ValueError:
        return ""
    if (
        parsed.scheme.lower() not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
    ):
        return ""
    return urlunsplit((
        parsed.scheme.lower(), parsed.netloc.lower(), parsed.path or "/",
        parsed.query, "",
    ))


def _normalise_published_at(value: object) -> Optional[datetime]:
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        return None
    return value.astimezone(timezone.utc)


def _source_ref(
    *, title: str, source_name: str, source_url: str,
    published_at: Optional[datetime],
) -> str:
    """Return an immutable digest of the exact source evidence."""
    payload = json.dumps(
        {
            "title": str(title),
            "source_name": source_name,
            "source_url": source_url,
            "published_at": published_at.isoformat() if published_at else None,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8", errors="replace")).hexdigest()


def _item_source_metadata(
    item: "NewsItem", *, now: Optional[datetime] = None,
) -> tuple[
    str, str, Optional[datetime], Optional[datetime], str, Optional[str]
]:
    """Normalise source evidence and report why it cannot be trusted."""
    source_name = _bounded_text(getattr(item, "source_name", ""), 160)
    raw_source_url = getattr(item, "source_url", "")
    source_url = _normalise_source_url(raw_source_url)
    published_at = _normalise_published_at(
        getattr(item, "published_at", getattr(item, "published_at_parsed", None))
    )
    source_ref = _source_ref(
        title=str(getattr(item, "title", "")),
        source_name=source_name,
        source_url=source_url,
        published_at=published_at,
    )
    source_valid_until = (
        published_at + SOURCE_MAX_AGE if published_at is not None else None
    )
    if not source_url:
        reason = "missing source URL" if not str(raw_source_url or "").strip() else "invalid source URL"
        return source_name, source_url, published_at, source_valid_until, source_ref, reason
    if published_at is None:
        return source_name, source_url, published_at, source_valid_until, source_ref, "missing or invalid publication time"
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None or current.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    if published_at > current.astimezone(timezone.utc):
        return source_name, source_url, published_at, source_valid_until, source_ref, "future-dated publication time"
    if source_valid_until is not None and current.astimezone(timezone.utc) >= source_valid_until:
        return source_name, source_url, published_at, source_valid_until, source_ref, "stale publication time"
    return source_name, source_url, published_at, source_valid_until, source_ref, None


# ---------------------------------------------------------------------------
# JSON extraction
# ---------------------------------------------------------------------------


_THINK_BLOCK = re.compile(
    r"<think\b[^>]*>.*?</think>", flags=re.DOTALL | re.IGNORECASE
)
_OPEN_THINK = re.compile(r"<think\b[^>]*>", flags=re.IGNORECASE)


def _extract_json_object(text: Optional[str]) -> Optional[dict]:
    """[WORKFLOW-I.4.D 2026-09-14] Pull a single JSON object out
    of an LLM reply, tolerantly. Mirrors ``agent._extract_json_object``
    but lives in this module so the classifier is independent of
    the verdict path (a future change to one parser must not
    silently affect the other).

    Tolerates: ``<think>...</think>`` reasoning blocks
    (MiniMax-M3 emits inline CoT), ``\\`\\`\\`json\\`\\`\\` fences,
    leading prose, and trailing prose. Returns the parsed dict,
    or None if nothing valid can be recovered.
    """
    if not text:
        return None
    # Strip closed think blocks.
    text = _THINK_BLOCK.sub("", text)
    # If an unclosed <think> remains, drop from it to the end.
    open_think = _OPEN_THINK.search(text)
    if open_think:
        text = text[: open_think.start()]
    candidate = text.strip()
    if not candidate:
        return None
    # Strip a leading/trailing markdown code fence if present.
    if candidate.startswith("```"):
        parts = candidate.split("```", 2)
        if len(parts) >= 2:
            candidate = parts[1]
            if candidate.lstrip().lower().startswith("json"):
                candidate = candidate.lstrip()[4:]
            candidate = candidate.strip()
    for attempt in (candidate, text):
        try:
            parsed = json.loads(attempt)
            if isinstance(parsed, dict):
                return parsed
        except (json.JSONDecodeError, TypeError):
            pass
    # Last resort: outermost brace pair.
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            parsed = json.loads(text[start:end + 1])
            if isinstance(parsed, dict):
                return parsed
        except (json.JSONDecodeError, TypeError):
            pass
    return None


# ---------------------------------------------------------------------------
# Output normaliser
# ---------------------------------------------------------------------------


def _rationale(raw: object) -> str:
    """Bound the rationale to a max of 280 chars; replace
    non-strings with empty string. The verdict prompt will
    embed this; an unbounded string would let one classification
    leak into the prompt budget.
    """
    if not isinstance(raw, str):
        return ""
    s = raw.strip()
    if len(s) > 280:
        s = s[:277] + "..."
    return s


def _coerce_category(raw: object) -> NewsCategory:
    """Map a model output to a bounded ``NewsCategory``. Anything
    outside the enum (including ``None``, numbers, typos, or
    categories the model invented) maps to ``UNKNOWN``. This
    is the taxonomy-boundary check: the model cannot extend
    the taxonomy.
    """
    if isinstance(raw, str) and raw.strip().lower() in _VALID_CATEGORIES:
        return NewsCategory(raw.strip().lower())
    return NewsCategory.UNKNOWN


def _coerce_confidence(raw: object) -> float:
    """Map a model output to a bounded ``[0.0, 1.0]`` confidence.
    Anything outside the range (including NaN/Inf, None, or
    bool which would be coerced to 0/1 incorrectly) maps to 0.0.
    Bool is rejected explicitly: ``True`` would otherwise coerce
    to 1.0 which is a meaningful claim we don't want a stray
    boolean to carry.
    """
    if isinstance(raw, bool):
        return 0.0
    if not isinstance(raw, (int, float)):
        return 0.0
    try:
        v = float(raw)
    except (TypeError, ValueError):
        return 0.0
    if v != v or v in (float("inf"), float("-inf")):
        return 0.0
    if v < 0.0:
        return 0.0
    if v > 1.0:
        return 1.0
    return v


def _build_classification(
    ticker: str,
    item_title: str,
    category: NewsCategory,
    confidence: float,
    rationale: str,
    *,
    source_name: str = "",
    source_url: str = "",
    published_at: Optional[datetime] = None,
    source_ref: str = "",
    source_valid_until: Optional[datetime] = None,
) -> ClassificationResult:
    """[WORKFLOW-I.4.D 2026-09-14] Apply the threshold rule + dataclass
    constructor. A result below ``CONFIDENCE_THRESHOLD`` is forced
    to ``UNKNOWN`` (fail-closed). All rationale strings are
    bounded at 280 chars here.
    """
    # Fail-closed threshold rule.
    if confidence < CONFIDENCE_THRESHOLD and category != NewsCategory.UNKNOWN:
        category = NewsCategory.UNKNOWN
    return ClassificationResult(
        ticker=ticker,
        title_hash=_title_hash(item_title),
        category=category,
        confidence=confidence,
        rationale=_rationale(rationale),
        prompt_version=CLASSIFIER_PROMPT_VERSION,
        classified_at=datetime.now(timezone.utc),
        source_name=_bounded_text(source_name, 160),
        source_url=_bounded_text(source_url, 2048),
        published_at=_normalise_published_at(published_at),
        source_ref=_bounded_text(source_ref, 64),
        source_valid_until=_normalise_published_at(source_valid_until),
    )


# ---------------------------------------------------------------------------
# Single-item classifier
# ---------------------------------------------------------------------------


def _classify_single(
    item: "NewsItem", client: object, model: str, timeout_sec: float,
    *, ticker: str = "UNKNOWN", now: Optional[datetime] = None,
) -> ClassificationResult:
    """[WORKFLOW-I.4.D 2026-09-14] Classify one ``NewsItem`` via a
    small MiniMax call. The prompt asks for ``{category, confidence,
    rationale}`` only -- no verdict, no opinion, no execution
    authority. On any failure (timeout, parse error, schema
    mismatch, disabled), returns ``UNKNOWN`` with confidence=0.0.
    """
    ticker = _bounded_text(ticker, 64) or "UNKNOWN"
    (
        source_name, source_url, published_at, source_valid_until,
        source_ref, source_error,
    ) = (
        _item_source_metadata(item, now=now)
    )

    def _result(
        category: NewsCategory, confidence: float, rationale: str,
    ) -> ClassificationResult:
        return _build_classification(
            ticker=ticker,
            item_title=item.title,
            category=category,
            confidence=confidence,
            rationale=rationale,
            source_name=source_name,
            source_url=source_url,
            published_at=published_at,
            source_ref=source_ref,
            source_valid_until=source_valid_until,
        )

    # A label without a retrievable source and an auditable publication
    # clock is not reliable evidence. Preserve the metadata but do not call
    # the model or let the item acquire a confident category.
    if source_error is not None:
        return _result(NewsCategory.UNKNOWN, 0.0, source_error)

    if CLASSIFIER_DISABLED or client is None:
        return _result(
            NewsCategory.UNKNOWN,
            0.0,
            (
                "classifier disabled"
                if CLASSIFIER_DISABLED
                else "no MiniMax client available"
            ),
        )

    # The classifier prompt is intentionally short. The model is
    # not asked for verdict -- only category + confidence + a
    # one-sentence rationale. This is the bounded contract.
    prompt = (
        "You are a financial news classifier.\n"
        "Classify the headline into exactly one of these 8 "
        "categories:\n"
        "  regulatory, earnings, m_and_a, guidance, macro, "
        "rumor, technical, unknown\n\n"
        "Return a JSON object with exactly three fields:\n"
        '  {"category": <one-of-the-8>, '
        '"confidence": <float in [0.0, 1.0]>, '
        '"rationale": "<one short sentence>"}\n\n'
        "Do not include any other fields. Do not include "
        "verdicts. Do not include execution authority.\n\n"
        f"HEADLINE: {item.title}\n"
        f"AGE: {item.age_label}\n"
        f"SOURCE: {item.source_name or '<unknown>'}\n"
    )

    started = time.monotonic()
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            timeout=timeout_sec,
            temperature=0.0,
            max_tokens=128,
        )
    except Exception as exc:  # noqa: BLE001
        elapsed = time.monotonic() - started
        logger.warning(
            "news_classifier_call_failed elapsed=%.2fs ticker=%s err=%s",
            elapsed, ticker, type(exc).__name__,
        )
        return _result(
            NewsCategory.UNKNOWN, 0.0,
            f"classifier call failed: {type(exc).__name__}",
        )

    elapsed = time.monotonic() - started
    if elapsed > timeout_sec:
        logger.warning(
            "news_classifier_timeout elapsed=%.2fs ticker=%s",
            elapsed, ticker,
        )
        return _result(NewsCategory.UNKNOWN, 0.0, "classifier timeout")

    raw_text = response.choices[0].message.content if response.choices else None
    payload = _extract_json_object(raw_text)
    if payload is None:
        return _result(
            NewsCategory.UNKNOWN, 0.0,
            "classifier returned unparseable output",
        )

    # Schema check: exactly 3 keys (category, confidence, rationale).
    # Anything extra / missing -> UNKNOWN.
    expected = {"category", "confidence", "rationale"}
    if set(payload.keys()) != expected:
        return _result(
            NewsCategory.UNKNOWN, 0.0,
            "classifier payload schema mismatch",
        )

    category = _coerce_category(payload.get("category"))
    confidence = _coerce_confidence(payload.get("confidence"))
    rationale = _rationale(payload.get("rationale"))
    return _result(category, confidence, rationale)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def classify_news_items(
    items: List["NewsItem"],
    *,
    client: Optional[object] = None,
    model: Optional[str] = None,
    timeout_sec: Optional[float] = None,
    ticker: str = "UNKNOWN",
) -> List[ClassificationResult]:
    """[WORKFLOW-I.4.D 2026-09-14] Classify a batch of ``NewsItem``
    against the fixed taxonomy.

    Ordering is preserved: ``result[i]`` corresponds to
    ``items[i]``. Empty input returns an empty list. The model
    is called once per item (the deep-research doc says
    "latency budget < 1s per item"); this function does NOT
    batch items into one model call, because the bounded
    taxonomy is per-headline.

    The ``client`` argument is optional; the function will use
    the verdict pipeline's module-level ``client`` (imported
    from ``agent``) when ``None``. Tests can supply a mock.
    """
    if not items:
        return []
    if client is None:
        # The classifier must use the dedicated no-retry client. Do not fall
        # back to the verdict client: its configured retry policy is correct
        # for a long review, but violates the classifier's short budget.
        from agent import classifier_client as _classifier_client
        client = _classifier_client
    if model is None:
        model = CLASSIFIER_MODEL
    if timeout_sec is None:
        timeout_sec = CLASSIFIER_TIMEOUT_SEC

    results: List[ClassificationResult] = []
    for item in items:
        results.append(
            _classify_single(
                item, client, model, timeout_sec, ticker=ticker,
            )
        )
    return results


def classification_context_sha256(
    results: Iterable[ClassificationResult],
) -> str:
    """Digest classification meaning and source evidence, not wall time.

    ``classified_at`` is intentionally excluded: an equivalent re-run may
    reuse a review, while any changed source, category, confidence, rationale,
    ticker, or prompt version produces a different cache identity.
    """
    projection = [
        {
            "ticker": r.ticker,
            "title_hash": r.title_hash,
            "source_ref": r.source_ref,
            "source_valid_until": (
                r.source_valid_until.isoformat()
                if r.source_valid_until else None
            ),
            "source_name": r.source_name,
            "source_url": r.source_url,
            "published_at": r.published_at.isoformat() if r.published_at else None,
            "category": r.category.value,
            "confidence": r.confidence,
            "rationale": r.rationale,
            "prompt_version": r.prompt_version,
        }
        for r in results
    ]
    payload = json.dumps(
        projection, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8", errors="replace")).hexdigest()


def to_dict(results: List[ClassificationResult]) -> List[dict]:
    """[WORKFLOW-I.4.D 2026-09-14] Render a batch of
    ``ClassificationResult`` as a list of bounded JSON-safe
    dicts. The verdict-pipeline consumer uses this; the
    dataclass itself is frozen and not directly JSON-
    serialisable in every consumer.
    """
    out: List[dict] = []
    for r in results:
        out.append(
            {
                "ticker": r.ticker,
                "title_hash": r.title_hash,
                "category": r.category.value,
                "confidence": r.confidence,
                "rationale": r.rationale,
                "prompt_version": r.prompt_version,
                "classified_at": (
                    r.classified_at.isoformat()
                    if r.classified_at is not None
                    else None
                ),
                "source_name": r.source_name,
                "source_url": r.source_url,
                "published_at": (
                    r.published_at.isoformat()
                    if r.published_at is not None
                    else None
                ),
                "source_ref": r.source_ref,
                "source_valid_until": (
                    r.source_valid_until.isoformat()
                    if r.source_valid_until is not None
                    else None
                ),
            }
        )
    return out
