"""Authenticated, read-only session inputs consumed by the Node gateway."""
from __future__ import annotations

import hashlib
import hmac

from fastapi import APIRouter, Query, Request

from config import settings
from engine_auth import _check_internal_secret
from market_calendar import (
    cas_eligibility_reason,
    cas_membership_max_age_days,
    resolve_cas_eligibility,
    CasEligibilityReason,
    CasEligibilityState,
    _cas_membership_metadata,
)


router = APIRouter(prefix="/market-session", tags=["market-session"])


def _eligibility_version() -> str:
    """Expose configuration lineage without disclosing the configured CSV."""
    raw = (settings.CAS_PHASE1_FNO_UNDERLYINGS or "").encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


def _eligibility_signature(
    symbol: str, state: str, reason: str, version: str,
) -> str:
    """HMAC the three-state answer so Node can detect tampering.

    The signed payload now carries ``state`` and ``reason`` instead
    of a boolean. Existing Node callers that read only
    ``cas_eligible`` derive it from the state.
    """
    body = (
        f"{symbol}|{str(state).lower()}|{str(reason).lower()}|{version}"
    ).encode("utf-8")
    return hmac.new(
        settings.INTERNAL_API_SECRET.encode("utf-8"),
        body,
        hashlib.sha256,
    ).hexdigest()


@router.get("/cas-eligibility")
def cas_eligibility(
    request: Request,
    symbol: str = Query(..., min_length=1, max_length=64),
):
    """Return the authoritative Phase-1 CAS eligibility for one cash symbol.

    The route projects the bounded three-state contract from
    ``market_calendar.resolve_cas_eligibility``. The Node gateway
    must not carry an independent environment list: its entry gate
    obtains the three-state answer from this route and fails closed
    when the state is ``UNKNOWN``.

    Response schema (A1, 2026-09-20):

      * ``symbol`` (str): normalised uppercase symbol.
      * ``state`` (str): ``ELIGIBLE`` / ``NOT_ELIGIBLE`` / ``UNKNOWN``.
      * ``reason`` (str): stable reason code.
      * ``cas_eligible`` (bool): derived boolean; ``True`` only when
        ``state == ELIGIBLE``. Retained for the J.1 / J.3 byte-identity
        contract.
      * ``coverage`` (dict): membership provenance metadata.
      * ``as_of_utc`` (str): server-time ISO 8601 stamp.
      * ``source_version`` (str): 16-char sha256 prefix of the raw
        configured CSV.
      * ``signature`` (str): 64-char HMAC over
        ``symbol|state|reason|source_version``.
    """
    _check_internal_secret(request, "market_session_cas_eligibility")
    normalized = symbol.strip().upper()
    state = resolve_cas_eligibility(normalized)
    reason = cas_eligibility_reason(normalized)
    version = _eligibility_version()
    metadata = _cas_membership_metadata()
    return {
        "symbol": normalized,
        "state": state.value,
        "reason": reason.value,
        "cas_eligible": state is CasEligibilityState.ELIGIBLE,
        "coverage": {
            "configured_size": metadata.configured_size,
            "raw_csv_sha256": metadata.raw_csv_sha256,
            "max_age_days": metadata.max_age_days,
            "is_stale": metadata.is_stale,
        },
        "as_of_utc": _now_iso(),
        "source": "python-engine/market_calendar.py::resolve_cas_eligibility",
        "source_version": version,
        "signature": _eligibility_signature(
            normalized, state.value, reason.value, version,
        ),
    }


def _now_iso() -> str:
    """Return the current UTC time as an ISO 8601 string.

    Local import to avoid widening the module-level import surface.
    """
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()
