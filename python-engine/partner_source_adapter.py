"""Provenance-gated partner snapshot adapter; transport remains external."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

from partner_fixture_adapter import _source_timestamp, apply_fixture_account


async def apply_partner_source_snapshot(db_path: str, envelope: dict[str,Any], *, received_at: datetime) -> dict:
    """Validate a complete source payload before the existing lifecycle writer.

    This is intentionally transport-neutral: an authorised API/CSV adapter
    supplies the envelope, while lifecycle mutation still goes through the
    proven atomic complete-snapshot path.
    """
    if not isinstance(envelope,dict) or str(envelope.get("mode","")).upper()!="ADVISORY": raise ValueError("source envelope must declare mode=ADVISORY")
    source_kind=str(envelope.get("source_kind","")).strip(); source=str(envelope.get("source","")).strip()
    if not source_kind or not source: raise ValueError("source provenance is required")
    observed=_source_timestamp(envelope.get("observed_at"),"observed_at")
    if observed>received_at: raise ValueError("source observation cannot be after receipt")
    declared=str(envelope.get("dataset_sha256","")).strip()
    payload={key:value for key,value in envelope.items() if key!="dataset_sha256"}
    actual=hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(",",":"),default=str).encode()).hexdigest()
    if declared and declared!=actual: raise ValueError("source dataset hash mismatch")
    result=await apply_fixture_account(db_path,{**envelope,"source":f"{source_kind}:{source}","complete":True},received_at=received_at)
    return {**result,"source_kind":source_kind,"dataset_sha256":actual,"advisory_only":True,"can_place_orders":False}
