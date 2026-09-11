"""Causal research adapter for the deployed intraday partner policy.

This module intentionally composes the same signal, candidate builder and
validation functions used by the advisory path.  It creates research facts;
it cannot write qualifications, dispatch advice, or place orders.
"""
from __future__ import annotations

import hashlib
import inspect
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from config import settings
from fno_chain import ChainSnapshot
from fno_engine_mom import MomSignal, evaluate_fno_mom
from fno_instruments import FnoInstruments
from partner_manual_advisory import (
    AdvisoryCandidate, AdvisoryScope, PartnerAdvisoryProfile, StrategyEvidence,
    build_directional_debit_spread, validate_candidate, validate_profile,
)


FULL_POLICY_EVALUATOR = "partner_manual_intraday_full_policy_v1"


def _sha(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def _clock(value: object, name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be a timezone-aware datetime")
    return value


def _signal_payload(signal: MomSignal) -> dict[str, Any]:
    value = asdict(signal)
    value["direction"] = signal.direction.value if signal.direction else None
    return value


def _bars_payload(bars: pd.DataFrame) -> list[dict[str, Any]]:
    if bars is None or bars.empty:
        return []
    required = {"open", "high", "low", "close", "volume"}
    if not required.issubset(bars.columns):
        raise ValueError("full policy bars are missing OHLCV columns")
    return [{"bar_start": str(index), **{field: float(row[field]) for field in sorted(required)}}
            for index, row in bars.sort_index().iterrows()]


def _causal_provenance(value: Mapping[str, Any], decision_at: datetime) -> dict[str, Any]:
    """Normalize event, receipt and retrieval clocks without hindsight repair."""
    if not isinstance(value, Mapping):
        raise ValueError("bar provenance is required")
    state = str(value.get("state", "")).upper()
    if state not in {"CONTEMPORANEOUS", "RETROSPECTIVE", "MISSING"}:
        raise ValueError("bar provenance state is invalid")
    normalized = {"state": state, "source": str(value.get("source", "")).strip()}
    if not normalized["source"]:
        raise ValueError("bar provenance source is required")
    for key in ("event_at", "received_at", "retrieved_at"):
        raw = value.get(key)
        if raw is None:
            normalized[key] = None
            continue
        parsed = _clock(raw, f"bar provenance {key}")
        normalized[key] = parsed.isoformat()
    if state == "CONTEMPORANEOUS":
        received = value.get("received_at")
        if received is None or _clock(received, "bar provenance received_at") > decision_at:
            raise ValueError("contemporaneous bar evidence was unavailable at decision time")
        event_at = value.get("event_at")
        if event_at is not None and _clock(event_at, "bar provenance event_at") > decision_at:
            raise ValueError("contemporaneous bar event is after decision time")
    if state == "MISSING" and any(value.get(key) is not None for key in ("event_at", "received_at")):
        raise ValueError("missing bar evidence cannot claim event or receipt timestamps")
    return normalized


def policy_manifest(*, underlying: str, structure_kind: str, bars: pd.DataFrame,
                    regime: str, decision_at: datetime, bar_provenance: Mapping[str, Any],
                    contract_master_sha256: str | None = None) -> dict[str, Any]:
    """Freeze code/config/input identity for one full-policy decision."""
    now = _clock(decision_at, "decision_at")
    name = underlying.upper()
    if name not in {"NIFTY", "SENSEX"} or structure_kind != "DIRECTIONAL_DEBIT_SPREAD":
        raise ValueError("only NIFTY/SENSEX directional debit-spread policy is supported")
    if contract_master_sha256 is not None and (len(contract_master_sha256) != 64 or any(c not in "0123456789abcdef" for c in contract_master_sha256.lower())):
        raise ValueError("contract_master_sha256 must be a SHA-256 digest")
    config = {key: getattr(settings, key) for key in (
        "FNO_OR_MINUTES", "FNO_ATR_LEN", "FNO_EMA_FAST", "FNO_EMA_SLOW", "FNO_RVOL_LOOKBACK_DAYS",
        "FNO_OR_BUFFER_ATR", "FNO_STOP_ATR_MULT", "FNO_TARGET_R", "FNO_MIN_RVOL",
        "PARTNER_MANUAL_ADVISORY_QUOTE_TTL_SEC", "PARTNER_MANUAL_ADVISORY_MAX_QUOTE_AGE_SEC",
        "PARTNER_MANUAL_ADVISORY_MAX_SPREAD_PCT", "PARTNER_MANUAL_ADVISORY_MIN_OI",
        "PARTNER_MANUAL_ADVISORY_MIN_VOLUME", "PARTNER_MANUAL_ADVISORY_MIN_DEPTH_UNITS",
    )}
    bar_rows = _bars_payload(bars)
    provenance = _causal_provenance(bar_provenance, now)
    deterministic = {
        "format": "partner_full_policy_manifest_v1", "evaluator": FULL_POLICY_EVALUATOR,
        "evaluator_source_sha256": hashlib.sha256(inspect.getsource(evaluate_fno_mom).encode()).hexdigest(),
        "underlying": name, "structure_kind": structure_kind, "regime": str(regime),
        "decision_at": now.isoformat(), "config": config, "config_sha256": _sha(config),
        "bars_sha256": _sha(bar_rows), "bar_count": len(bar_rows), "bar_provenance": provenance,
        "contract_master_sha256": contract_master_sha256,
    }
    return {**deterministic, "manifest_sha256": _sha(deterministic)}


@dataclass(frozen=True)
class FullPolicyDecision:
    decision_id: str
    state: str
    reason: str
    signal: MomSignal
    candidate: AdvisoryCandidate | None
    validation_reasons: tuple[str, ...]
    manifest: dict[str, Any]
    can_qualify: bool = False


def evaluate_deployed_full_policy(*, underlying: str, bars: pd.DataFrame, regime: str,
                                  decision_at: datetime, bar_provenance: Mapping[str, Any],
                                  book: FnoInstruments | None = None,
                                  snapshot: ChainSnapshot | None = None,
                                  profile: PartnerAdvisoryProfile | None = None,
                                  contract_master_sha256: str | None = None) -> FullPolicyDecision:
    """Reproduce deployed signal -> candidate -> profile/quote validation.

    A no-setup is a retained decision, not a missing row.  Historical bars
    retrieved after the fact remain labelled RETROSPECTIVE and cannot qualify
    a policy even when their deterministic decision matches production code.
    """
    now = _clock(decision_at, "decision_at")
    manifest = policy_manifest(underlying=underlying, structure_kind="DIRECTIONAL_DEBIT_SPREAD", bars=bars,
                               regime=regime, decision_at=now, bar_provenance=bar_provenance,
                               contract_master_sha256=contract_master_sha256)
    signal = evaluate_fno_mom(bars, regime, now)
    base = {"manifest": manifest["manifest_sha256"], "signal": _signal_payload(signal)}
    if signal.direction is None:
        return FullPolicyDecision(_sha(base), "NO_SETUP", signal.reject_reason or "no_direction", signal,
                                  None, (), manifest, False)
    if book is None or snapshot is None:
        return FullPolicyDecision(_sha(base), "REJECTED", "candidate_input_missing", signal,
                                  None, ("candidate_input_missing",), manifest, False)
    trigger = signal.or_high + settings.FNO_OR_BUFFER_ATR * signal.atr if signal.direction.value == "LONG" else signal.or_low - settings.FNO_OR_BUFFER_ATR * signal.atr
    candidate = build_directional_debit_spread(
        snapshot, book, signal.direction, now, evidence=StrategyEvidence.RESEARCH_ONLY,
        quote_ttl_seconds=settings.PARTNER_MANUAL_ADVISORY_QUOTE_TTL_SEC,
        thesis_id=f"{underlying.upper()}:{signal.direction.value}:{signal.bar_ts}", trigger_level=trigger,
        invalidation_level=signal.stop_underlying, target_level=signal.target_underlying,
    )
    if candidate is None:
        return FullPolicyDecision(_sha(base), "REJECTED", "candidate_construction_failed", signal,
                                  None, ("candidate_construction_failed",), manifest, False)
    validation = validate_candidate(
        candidate, now, max_quote_age_seconds=settings.PARTNER_MANUAL_ADVISORY_MAX_QUOTE_AGE_SEC,
        max_spread_pct=settings.PARTNER_MANUAL_ADVISORY_MAX_SPREAD_PCT,
        min_oi=settings.PARTNER_MANUAL_ADVISORY_MIN_OI,
        min_volume=settings.PARTNER_MANUAL_ADVISORY_MIN_VOLUME,
        min_depth_units=settings.PARTNER_MANUAL_ADVISORY_MIN_DEPTH_UNITS,
    )
    reasons = list(validation.reasons)
    if profile is not None:
        reasons.extend(validate_profile(profile, candidate, now))
        if not profile.permits(AdvisoryScope.MARKET_SETUP, candidate.underlying):
            reasons.append("profile_scope_not_permitted")
    reasons = tuple(sorted(set(reasons)))
    state = "ACCEPTED" if not reasons else "REJECTED"
    base["candidate"] = candidate.thesis_id
    return FullPolicyDecision(_sha(base), state, "accepted" if state == "ACCEPTED" else reasons[0], signal,
                              candidate, reasons, manifest, False)


def write_full_policy_decision(path: str | Path, decision: FullPolicyDecision) -> dict[str, Any]:
    """Atomically persist a research decision; never a qualification record."""
    candidate = decision.candidate
    payload = {
        "format": "partner_full_policy_decision_v1", "decision_id": decision.decision_id,
        "state": decision.state, "reason": decision.reason, "signal": _signal_payload(decision.signal),
        "validation_reasons": list(decision.validation_reasons), "manifest": decision.manifest,
        "candidate": None if candidate is None else {
            "thesis_id": candidate.thesis_id, "direction": candidate.direction,
            "net_debit_rs": candidate.net_debit_rs, "max_loss_rs": candidate.max_loss_rs,
            "max_profit_rs": candidate.max_profit_rs, "estimated_round_trip_cost_rs": candidate.estimated_round_trip_cost_rs,
            "trigger_level": candidate.trigger_level, "invalidation_level": candidate.invalidation_level,
            "target_level": candidate.target_level, "management_deadline": candidate.management_deadline.isoformat()
            if candidate.management_deadline else None,
            "selected_legs": [{"side": leg.side, "exchange": candidate.segment, "token": leg.instrument_token,
                                "symbol": leg.tradingsymbol, "expiry": leg.expiry, "strike": leg.strike,
                                "option_type": leg.option_type, "lot_size": leg.lot_size}
                              for leg in candidate.legs],
        },
        "can_qualify": False, "can_place_orders": False,
        "limitations": ["A deterministic research decision is not a strategy qualification or advice delivery authority."],
    }
    target = Path(path); target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str), encoding="utf-8")
    temporary.replace(target)
    return payload
