"""Authenticated, read-only session inputs consumed by the Node gateway."""
from __future__ import annotations

import hashlib
import hmac

from fastapi import APIRouter, Query, Request

from config import settings
from engine_auth import _check_internal_secret
from market_calendar import is_cas_eligible


router = APIRouter(prefix="/market-session", tags=["market-session"])


def _eligibility_version() -> str:
    """Expose configuration lineage without disclosing the configured CSV."""
    raw = (settings.CAS_PHASE1_FNO_UNDERLYINGS or "").encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


def _eligibility_signature(symbol: str, eligible: bool, version: str) -> str:
    body = f"{symbol}|{str(eligible).lower()}|{version}".encode("utf-8")
    return hmac.new(settings.INTERNAL_API_SECRET.encode("utf-8"), body, hashlib.sha256).hexdigest()


@router.get("/cas-eligibility")
def cas_eligibility(
    request: Request,
    symbol: str = Query(..., min_length=1, max_length=64),
):
    """Return the authoritative Phase-1 CAS eligibility for one cash symbol.

    This is deliberately an internal read-only projection of
    ``market_calendar.is_cas_eligible``.  The Node gateway must not carry an
    independent environment list: its entry gate obtains an explicit boolean
    from this route and fails closed if that resolution is unavailable.
    """
    _check_internal_secret(request, "market_session_cas_eligibility")
    normalized = symbol.strip().upper()
    version = _eligibility_version()
    eligible = is_cas_eligible(normalized)
    return {
        "symbol": normalized,
        "cas_eligible": eligible,
        "source": "python-engine/market_calendar.py::is_cas_eligible",
        "source_version": version,
        "signature": _eligibility_signature(normalized, eligible, version),
    }
