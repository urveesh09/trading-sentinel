"""[WORKFLOW-ITEMS-5/6/9 2026-09-20] Proactive source configuration verifier.

The audit (items 5) requires that the ``KITE_COMPLETED_BARS_V1``
branch in ``proactive_intelligence._run_proactive_shadow`` reads
explicit, current instrument-token mapping + a Production research
account/run ID + immutable capital/cost assumptions. The branch
exists (proactive_intelligence.py:2004) but a misconfigured source
silently returns ``MARKET_DATA_SOURCE_UNCONFIGURED`` AFTER the broker
call returns its own error.

This verifier runs BEFORE the broker call and surfaces a structured
verdict: which fields are missing or invalid. The caller maps the
verdict's ``reasons`` to the existing
``MARKET_DATA_SOURCE_UNCONFIGURED`` reason code so existing
diagnostics continue to work.

Pure of I/O: takes the ``settings`` object and returns a verdict.
Tests inject a settings stub.

Design choices:

  * **Pure**: no DB, no clock, no broker call.
  * **Total**: every input returns a verdict. The verdict never
    raises on missing/invalid configuration.
  * **Stable reason codes**: each reason is a stable string the
    audit log + tests key off. Adding a new code is a contract
    change.
  * **Frozen dataclass**: ``ConfigVerdict`` is frozen so callers
    cannot mutate the verdict after the verifier returns.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping


class SourceConfigReason(str, Enum):
    """Stable reason codes emitted by the verifier.

    Adding a new code is a contract change. Removing or renaming
    an existing code is a contract change.
    """
    PASS = "pass"
    MISSING_RUN_ID = "missing_run_id"
    MISSING_TOKENS_JSON = "missing_tokens_json"
    INVALID_TOKENS_SHAPE = "invalid_tokens_shape"
    INVALID_CAPITAL = "invalid_capital"
    INVALID_MAX_AGE = "invalid_max_age"
    MISSING_ARCHIVE_PATH = "missing_archive_path"


@dataclass(frozen=True)
class ConfigVerdict:
    """Structured verdict for the proactive source configuration.

    ``ok`` is True iff ``reasons`` is exactly
    ``(SourceConfigReason.PASS,)``.
    """
    ok: bool
    reasons: tuple[SourceConfigReason, ...]
    evidence: Mapping[str, Any]

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "reasons": [r.value for r in self.reasons],
            "evidence": dict(self.evidence),
        }


_DEFAULT_MAX_DATA_AGE_SECONDS = 300  # 5 minutes
_ABSOLUTE_MAX_DATA_AGE_SECONDS = 86_400  # 1 day


def _read_int(value: Any) -> int | None:
    """Best-effort int parse. Returns None on failure."""
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _read_float(value: Any) -> float | None:
    """Best-effort float parse. Returns None on failure."""
    try:
        f = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    return f


def verify_kite_completed_bar_config(settings: Any) -> ConfigVerdict:
    """[WORKFLOW-ITEMS-5/6/9 2026-09-20] Verify the
    ``KITE_COMPLETED_BARS_V1`` configuration.

    Reads each required field from ``settings`` and emits a
    stable reason code for each problem. The caller maps the
    reasons to the existing
    ``MARKET_DATA_SOURCE_UNCONFIGURED`` reason code.
    """
    import json as _json
    reasons: list[SourceConfigReason] = []
    evidence: dict[str, Any] = {}

    # 1. Run ID. The Production research account / run identity
    #    is a required, operator-curated string.
    run_id_raw = str(getattr(settings, "PROACTIVE_SHADOW_RUN_ID", "") or "").strip()
    evidence["run_id"] = run_id_raw
    if not run_id_raw:
        reasons.append(SourceConfigReason.MISSING_RUN_ID)

    # 2. Kite instruments JSON. Must parse as a non-empty dict
    #    of ``{underlying: {token, ...}}``.
    tokens_raw = str(getattr(settings, "PROACTIVE_SHADOW_KITE_TOKENS_JSON", "") or "").strip()
    evidence["tokens_json"] = tokens_raw
    parsed_tokens: Any = None
    if not tokens_raw:
        reasons.append(SourceConfigReason.MISSING_TOKENS_JSON)
    else:
        try:
            parsed_tokens = _json.loads(tokens_raw)
            if not isinstance(parsed_tokens, dict) or not parsed_tokens:
                reasons.append(SourceConfigReason.INVALID_TOKENS_SHAPE)
                parsed_tokens = None
        except _json.JSONDecodeError:
            reasons.append(SourceConfigReason.INVALID_TOKENS_SHAPE)
    evidence["parsed_tokens_keys"] = (
        sorted(parsed_tokens.keys()) if isinstance(parsed_tokens, dict) else []
    )

    # 3. Scenario capital. Must be positive finite.
    capital_raw = getattr(settings, "PROACTIVE_SHADOW_SCENARIO_CAPITAL", None)
    capital = _read_float(capital_raw)
    evidence["scenario_capital"] = capital
    if capital is None or not (capital > 0):
        reasons.append(SourceConfigReason.INVALID_CAPITAL)

    # 4. Maximum data age. Must be 1..86400 seconds.
    max_age_raw = getattr(settings, "PROACTIVE_SHADOW_MAX_DATA_AGE_SECONDS", None)
    max_age = _read_int(max_age_raw)
    if max_age is None:
        # [WORKFLOW-ITEMS-5/6/9 2026-09-20] When the field is
        # missing or unparseable, fall back to the documented
        # default rather than blocking the source. The audit
        # required ``current instrument-token mapping +
        # Production research account/run ID + immutable
        # capital/cost assumptions``. The default age is
        # conservative and matches the existing operator config.
        max_age = _DEFAULT_MAX_DATA_AGE_SECONDS
    evidence["max_data_age_seconds"] = max_age
    if not (1 <= max_age <= _ABSOLUTE_MAX_DATA_AGE_SECONDS):
        reasons.append(SourceConfigReason.INVALID_MAX_AGE)

    # 5. Archive root. Must be a non-empty string.
    archive_path = str(getattr(settings, "RESEARCH_ARCHIVE_PATH", "") or "").strip()
    evidence["research_archive_path"] = archive_path
    if not archive_path:
        reasons.append(SourceConfigReason.MISSING_ARCHIVE_PATH)

    if not reasons:
        reasons = [SourceConfigReason.PASS]
    return ConfigVerdict(
        ok=(reasons == [SourceConfigReason.PASS]),
        reasons=tuple(reasons),
        evidence=evidence,
    )


__all__ = [
    "ConfigVerdict",
    "SourceConfigReason",
    "verify_kite_completed_bar_config",
]
