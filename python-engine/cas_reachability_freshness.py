"""[WORKFLOW-J.10.FRESHNESS 2026-09-14] Capture-freshness helpers.

The J.10 gate's per-branch count was always "files-on-disk that
exercise this branch". J.10.DEDUP made that "unique observations".
J.10.FRESHNESS adds the third dimension: **age**.

A capture collected in a previous quarter is not the same
evidence as a capture collected yesterday. The operator's
question "is the gate REACHABLE with captures from the last
7 days?" requires a freshness filter. Without one, an operator
who hasn't refreshed the captures directory in months sees a
green REACHABLE that's actually based on stale evidence.

This module exposes two pure helpers:

    capture_age_days(capture_path, *, now_utc=None) -> Optional[float]
        Days between ``capture_path``'s ``generated_at_utc`` (per
        the J.3 schema) and ``now_utc`` (defaults to ``datetime.now(UTC)``).
        Returns ``None`` when the capture is unreadable, has no
        ``generated_at_utc``, or the value cannot be parsed as
        an ISO 8601 timestamp. Pure / total / never raises.

    is_within_max_age(age_days, max_age_days) -> bool
        ``True`` when ``age_days <= max_age_days``. Handles
        ``age_days is None`` (always ``False`` -- we cannot
        verify freshness of a capture we cannot read).

The gate in ``cas_reachability_gate.py`` calls these helpers
inside the existing ``cas_reachability_report`` walk when the
caller passes ``max_age_days``. Stale captures increment
``captures_skipped_stale`` (a NEW report field) rather than
``captures_skipped`` (the existing field is reserved for
malformed / non-bounded captures -- the senior-dev distinction
between "we couldn't read this" and "we read it but it's old").

No new dependencies -- stdlib ``datetime`` only.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from json import JSONDecodeError
from pathlib import Path
from typing import Any, Optional


def capture_age_days(
    capture_path: Path, *, now_utc: Optional[datetime] = None
) -> Optional[float]:
    """Return the age of the capture in days (UTC), or ``None``.

    Reads the capture JSON; reads ``generated_at_utc`` at the
    top level (per the J.3 schema in
    ``tools/j2_cas_probe.py::CAPTURE_JSON_SCHEMA``). Parses the
    timestamp with ``datetime.fromisoformat`` (which handles the
    ``+00:00`` suffix the probe writes).

    Returns ``None`` when:
      * the file is unreadable,
      * the JSON cannot be parsed,
      * the document has no ``generated_at_utc``,
      * the timestamp is not a string,
      * the timestamp cannot be parsed as ISO 8601,
      * the parsed timestamp is naive (no tzinfo -- the J.3
        probe always writes aware timestamps; naive would be a
        schema violation).

    The function is pure / total / never raises. The gate
    counts unreadable captures via the existing
    ``captures_skipped`` path; this helper returns ``None``
    so the caller can branch on ``None`` vs a numeric age.
    """
    try:
        data = Path(capture_path).read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        doc: Any = json.loads(data)
    except JSONDecodeError:
        return None
    if not isinstance(doc, dict):
        return None
    raw = doc.get("generated_at_utc")
    if not isinstance(raw, str):
        return None
    try:
        ts = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if ts.tzinfo is None:
        # Schema violation (the probe writes aware timestamps);
        # treat as unreadable for freshness purposes.
        return None
    if now_utc is None:
        now_utc = datetime.now(timezone.utc)
    delta = now_utc - ts
    return delta.total_seconds() / 86400.0


def is_within_max_age(age_days: Optional[float], max_age_days: float) -> bool:
    """``True`` when ``age_days`` is within ``max_age_days`` days.

    A ``None`` age (unreadable / unparseable) returns ``False``
    -- we cannot verify freshness of a capture we cannot read,
    so the gate should skip it when freshness matters.
    """
    if age_days is None:
        return False
    return age_days <= max_age_days


__all__ = ["capture_age_days", "is_within_max_age"]
